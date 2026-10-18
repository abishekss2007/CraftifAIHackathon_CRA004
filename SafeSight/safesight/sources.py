"""Inputs (where PipeGen detections come from) and actions (where alerts go)."""
import hashlib
import json
import os
import sys
import threading
import time
import urllib.request


# ---------------------------------------------------------------- inputs
def tail_jsonl(path, from_start=False):
    """Follow a JSON-lines file that PipeGen's DeepStream app writes (like tail -F)."""
    while not os.path.exists(path):
        time.sleep(0.2)
    f = open(path, "r")
    if not from_start:
        f.seek(0, os.SEEK_END)
    buf = ""
    while True:
        chunk = f.readline()
        if not chunk:
            time.sleep(0.02)
            if os.path.getsize(path) < f.tell():  # file truncated / restarted
                f.seek(0)
            continue
        buf += chunk
        if not buf.endswith("\n"):
            continue
        line, buf = buf.strip(), ""
        if line:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                pass


def replay_jsonl(path, speed=1.0, loop=True):
    """Replay a recorded metadata file at its original pace (for the offline demo)."""
    while True:
        prev = None
        base = time.time()
        with open(path) as f:
            rows = [json.loads(l) for l in f if l.strip()]
        t0 = rows[0].get("ts", 0) if rows else 0
        for i, r in enumerate(rows):
            rt = r.get("ts", t0 + i / 15)
            wait = base + (rt - t0) / speed - time.time()
            if wait > 0:
                time.sleep(wait)
            r = dict(r, ts=time.time())
            yield r
        if not loop:
            return


def stdin_jsonl():
    for line in sys.stdin:
        line = line.strip()
        if line:
            yield json.loads(line)


def mqtt_messages(host, port, topic):
    import queue
    import paho.mqtt.client as mqtt  # pip install paho-mqtt

    q = queue.Queue()
    c = mqtt.Client()
    c.on_message = lambda _c, _u, m: q.put(m.payload)
    c.connect(host, port)
    c.subscribe(topic)
    c.loop_start()
    while True:
        try:
            yield json.loads(q.get())
        except json.JSONDecodeError:
            continue


# --------------------------------------------------------------- actions
GENESIS = "0" * 64


def entry_hash(ev):
    body = {k: v for k, v in ev.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def last_hash(path):
    try:
        with open(path) as f:
            lines = [l for l in f if l.strip()]
        return json.loads(lines[-1]).get("hash", GENESIS) if lines else GENESIS
    except (OSError, ValueError):
        return GENESIS


def verify_log(path):
    """Return (ok, entries_checked, first_bad_line_number or None)."""
    prev = GENESIS
    n = 0
    with open(path) as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            ev = json.loads(line)
            if "hash" not in ev:  # entries written before chaining was added
                continue
            n += 1
            if ev.get("prev_hash") != prev or entry_hash(ev) != ev["hash"]:
                return False, n, i
            prev = ev["hash"]
    return True, n, None

class Actions:
    """Fan an event out to every configured actuator. Each one is optional."""

    def __init__(self, log_path=None, webhook=None, mqtt=None, serial_port=None):
        self.prev_hash = last_hash(log_path) if log_path else GENESIS
        self.log = open(log_path, "a") if log_path else None
        self.webhook = webhook
        self.mqtt = None
        self.serial = None
        if mqtt:
            try:
                import paho.mqtt.client as m
                host, _, port = mqtt.partition(":")
                self.mqtt = m.Client()
                self.mqtt.connect(host, int(port or 1883))
                self.mqtt.loop_start()
            except Exception as e:  # noqa: BLE001
                print(f"[safesight] MQTT alerts disabled: {e}", file=sys.stderr)
        if serial_port:
            try:
                import serial  # pip install pyserial
                self.serial = serial.Serial(serial_port, 115200, timeout=0)
            except Exception as e:  # noqa: BLE001
                print(f"[safesight] serial beacon disabled: {e}", file=sys.stderr)

    def fire(self, ev):
        # Tamper-evident incident log: each entry carries the hash of the previous one,
        # so editing or deleting a past incident breaks the chain (python -m safesight.verify).
        ev["prev_hash"] = self.prev_hash
        ev["hash"] = entry_hash(ev)
        self.prev_hash = ev["hash"]
        line = json.dumps(ev)
        print(f"[{ev['severity'].upper():8}] {ev['message']}", flush=True)
        if self.log:
            self.log.write(line + "\n")
            self.log.flush()
        if self.mqtt:
            self.mqtt.publish(f"safesight/alerts/{ev['severity']}", line)
        if self.serial:
            # One char per severity keeps the firmware trivial: C, H, W, I
            self.serial.write(ev["severity"][0].upper().encode())
        if self.webhook:
            threading.Thread(target=self._post, args=(ev,), daemon=True).start()

    def _post(self, ev):
        body = json.dumps({"text": f"SafeSight {ev['severity'].upper()}: {ev['message']}", "event": ev}).encode()
        req = urllib.request.Request(self.webhook, body, {"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=4)
        except Exception as e:  # noqa: BLE001
            print(f"[safesight] webhook failed: {e}", file=sys.stderr)
