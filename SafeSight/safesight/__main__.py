"""SafeSight server: PipeGen detections in, safety alerts + live dashboard out.

    python -m safesight --source sim                      # rehearsal, no GPU
    python -m safesight --source file:/home/me/pipegen_out/meta.jsonl
    python -m safesight --source mqtt://localhost:1883/pipegen/meta
"""
import argparse
import json
import os
import queue
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import simulate, sources
from .engine import Engine
from .parse import normalise

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASH = os.path.join(ROOT, "dashboard")


class Hub:
    def __init__(self):
        self.clients = set()
        self.lock = threading.Lock()
        self.recent = deque(maxlen=200)
        self.last_frame = None

    def subscribe(self):
        q = queue.Queue(maxsize=200)
        with self.lock:
            self.clients.add(q)
        return q

    def unsubscribe(self, q):
        with self.lock:
            self.clients.discard(q)

    def publish(self, kind, data):
        msg = f"event: {kind}\ndata: {json.dumps(data)}\n\n".encode()
        with self.lock:
            for q in list(self.clients):
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    pass  # slow client: drop frames, never block the pipeline


def validate_zones(zones):
    """Check a zone list from the dashboard; raise ValueError with a readable reason."""
    if not isinstance(zones, list) or len(zones) > 50:
        raise ValueError("zones must be a list of at most 50 zones")
    names, out = set(), []
    for z in zones:
        if not isinstance(z, dict):
            raise ValueError("each zone must be an object")
        name = str(z.get("name", "")).strip()[:40]
        if not name or name.lower() in names:
            raise ValueError(f"zone name {name!r} is empty or used twice")
        names.add(name.lower())
        poly = z.get("polygon")
        if not isinstance(poly, list) or not 3 <= len(poly) <= 64:
            raise ValueError(f"zone {name!r} needs 3 to 64 corners")
        pts = []
        for p in poly:
            x, y = float(p[0]), float(p[1])
            if not (0 <= x <= 1 and 0 <= y <= 1):
                raise ValueError(f"zone {name!r} has a corner outside the camera view")
            pts.append([round(x, 4), round(y, 4)])
        zone = {"name": name, "restricted": bool(z.get("restricted", True)), "polygon": pts}
        if z.get("max_people") is not None:
            m = int(z["max_people"])
            if not 1 <= m <= 50:
                raise ValueError(f"zone {name!r}: max people must be 1 to 50")
            zone["max_people"] = m
        out.append(zone)
    return out


def open_source(spec, args):
    if spec == "sim":
        return simulate.frames(fps=args.fps)
    if spec == "stdin":
        return sources.stdin_jsonl()
    kind, _, rest = spec.partition(":")
    if kind == "file":
        return sources.tail_jsonl(rest, from_start=args.from_start)
    if kind == "replay":
        return sources.replay_jsonl(rest)
    if kind == "mqtt":
        hostport, _, topic = rest.lstrip("/").partition("/")
        host, _, port = hostport.partition(":")
        return sources.mqtt_messages(host, int(port or 1883), topic or "pipegen/#")
    raise SystemExit(f"unknown source {spec!r}")


def run_pipeline(args, engine, hub, actions, state):
    rec = open(args.record, "w") if args.record else None
    for raw in open_source(args.source, args):
        try:
            frame = normalise(raw)
        except Exception:  # noqa: BLE001 - one malformed payload must not kill the monitor
            continue
        if rec:
            rec.write(json.dumps(raw) + "\n")
        t0 = time.perf_counter()
        events, annotated = engine.process(frame)
        state["decide_ms"] = round((time.perf_counter() - t0) * 1000, 3)
        hub.last_frame = annotated
        hub.publish("frame", {"frame": annotated, "stats": {**engine.stats, "decide_ms": state["decide_ms"]}})
        for ev in events:
            hub.recent.append(ev)
            actions.fire(ev)
            hub.publish("alert", ev)


def make_handler(engine, hub, args):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            if isinstance(body, (dict, list)):
                body = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            p = self.path.split("?")[0]
            if p in ("/", "/index.html"):
                with open(os.path.join(DASH, "index.html"), "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            if p == "/api/zones":
                return self._send(200, engine.zones)
            if p == "/api/events":
                return self._send(200, list(hub.recent))
            if p == "/api/report":
                if args.report and os.path.exists(args.report):
                    with open(args.report, "rb") as f:
                        return self._send(200, f.read(), "text/plain; charset=utf-8")
                return self._send(404, {"error": "no report"})
            if p == "/api/integrity":
                if not args.log or not os.path.exists(args.log):
                    return self._send(200, {"ok": True, "entries": 0})
                ok, n, bad = sources.verify_log(args.log)
                return self._send(200, {"ok": ok, "entries": n, "bad_line": bad})
            if p == "/api/config":
                return self._send(200, {"source": args.source, "rules": engine.cfg, "has_report": bool(args.report)})
            if p == "/stream":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                q = hub.subscribe()
                try:
                    self.wfile.write(f"event: hello\ndata: {json.dumps({'zones': engine.zones, 'recent': list(hub.recent)[-30:]})}\n\n".encode())
                    while True:
                        try:
                            self.wfile.write(q.get(timeout=10))
                        except queue.Empty:
                            self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    hub.unsubscribe(q)
                return
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if self.path == "/api/zones":
                n = int(self.headers.get("Content-Length", 0))
                if n > 65536:
                    return self._send(413, {"error": "zone list too large"})
                try:
                    zones = validate_zones(json.loads(self.rfile.read(n) or b"[]"))
                except (ValueError, TypeError) as e:
                    return self._send(400, {"error": str(e)})
                engine.zones = zones
                if args.zones:
                    with open(args.zones, "w") as f:
                        json.dump(zones, f, indent=2)
                hub.publish("zones", zones)
                return self._send(200, {"ok": True})
            self._send(404, {"error": "not found"})

    return H


def main():
    ap = argparse.ArgumentParser(prog="safesight")
    ap.add_argument("--source", default="sim", help="sim | file:PATH | replay:PATH | mqtt://host:port/topic | stdin")
    ap.add_argument("--zones", default=os.path.join(ROOT, "zones.json"))
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--fps", type=float, default=15)
    ap.add_argument("--from-start", action="store_true", help="with file:, read the file from the beginning")
    ap.add_argument("--record", help="save every raw payload to this JSONL file (replay it later)")
    ap.add_argument("--log", default=os.path.join(ROOT, "events.jsonl"), help="append alerts here")
    ap.add_argument("--webhook", help="POST each alert as JSON (Slack/Discord/Teams-compatible 'text')")
    ap.add_argument("--alerts-mqtt", help="host[:port] to publish alerts on safesight/alerts/<severity>")
    ap.add_argument("--serial", help="serial port of the ESP32 beacon, e.g. /dev/ttyUSB0")
    ap.add_argument("--report", help="PipeGen TensorRT speed report to show on the dashboard")
    args = ap.parse_args()

    zones = []
    if args.zones and os.path.exists(args.zones):
        with open(args.zones) as f:
            zones = json.load(f)
    engine = Engine(zones)
    hub = Hub()
    actions = sources.Actions(args.log, args.webhook, args.alerts_mqtt, args.serial)
    threading.Thread(target=run_pipeline, args=(args, engine, hub, actions, {}), daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", args.port), make_handler(engine, hub, args))
    srv.daemon_threads = True
    print(f"[safesight] source={args.source}  dashboard http://localhost:{args.port}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
