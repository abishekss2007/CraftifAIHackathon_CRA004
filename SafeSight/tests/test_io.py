import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from itertools import islice

from safesight import sources
from safesight.parse import normalise

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sample(name):
    with open(os.path.join(ROOT, "samples", name)) as f:
        return json.load(f)


class ParseTest(unittest.TestCase):
    def test_full_schema_sample(self):
        f = normalise(sample("deepstream_full_schema.json"))
        self.assertEqual(f["source"], "cam-3")
        self.assertEqual(f["objects"][0]["box"], [10, 20, 60, 200])
        self.assertEqual(f["objects"][0]["label"], "person")

    def test_minimal_schema_sample(self):
        f = normalise(sample("deepstream_minimal_schema.json"))
        self.assertEqual([o["id"] for o in f["objects"]], ["7", "8"])
        self.assertEqual(f["source"], "cam-2")

    def test_box_formats(self):
        cases = [
            ({"bbox": [10, 20, 30, 40], "bbox_format": "xywh"}, [10, 20, 40, 60]),
            ({"bbox": {"left": 1, "top": 2, "width": 3, "height": 4}}, [1, 2, 4, 6]),
            ({"bbox": {"left": 1, "top": 2, "right": 5, "bottom": 9}}, [1, 2, 5, 9]),
            ({"box": {"x1": 1, "y1": 2, "x2": 3, "y2": 4}}, [1, 2, 3, 4]),
        ]
        for obj, want in cases:
            self.assertEqual(normalise({"objects": [obj]})["objects"][0]["box"], want, obj)

    def test_labels_and_bytes_input(self):
        f = normalise(json.dumps({"frame_num": 4, "objects": [{"bbox": [0, 0, 1, 1], "label": "Forklift", "score": 0.7},
                                                               {"bbox": [0, 0, 1, 1], "class_id": 0}]}).encode())
        self.assertEqual(f["frame"], 4)
        self.assertEqual([o["label"] for o in f["objects"]], ["forklift", "person"])
        self.assertAlmostEqual(f["objects"][0]["conf"], 0.7)

    def test_unusable_objects_are_dropped(self):
        self.assertEqual(normalise({"objects": ["1|2|3", {"bbox": "?"}]})["objects"], [])


class SourcesTest(unittest.TestCase):
    def test_tail_reads_lines_and_skips_bad_json(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "meta.jsonl")
            with open(path, "w") as f:
                f.write('{"frame": 1}\nnot json\n{"frame": 2}\n')
            got = list(islice(sources.tail_jsonl(path, from_start=True), 2))
            self.assertEqual([g["frame"] for g in got], [1, 2])

    def test_replay_keeps_order_and_restamps_time(self):
        rows = list(sources.replay_jsonl(os.path.join(ROOT, "samples", "demo_meta.jsonl"), speed=1e6, loop=False))
        self.assertEqual(len(rows), 390)
        self.assertEqual(rows[0]["frame"] + 1, rows[1]["frame"])
        self.assertGreater(rows[0]["ts"], 1.7e9)

    def test_webhook_receives_alert(self):
        got = []

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                got.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(204)
                self.end_headers()

        srv = HTTPServer(("127.0.0.1", 0), H)
        t = threading.Thread(target=srv.handle_request)
        t.start()
        a = sources.Actions(webhook=f"http://127.0.0.1:{srv.server_address[1]}/hook")
        a._post({"type": "MAN_DOWN", "severity": "critical", "message": "Person #1 is down"})
        t.join(5)
        srv.server_close()
        self.assertEqual(got[0]["text"], "SafeSight CRITICAL: Person #1 is down")

    def test_verify_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "events.jsonl")
            a = sources.Actions(path)
            a.fire({"type": "FALL", "severity": "high", "message": "Person #1 fell", "ts": 1})
            a.log.close()
            run = lambda: subprocess.run([sys.executable, "-m", "safesight.verify", path], cwd=ROOT,  # noqa: E731
                                         capture_output=True, text=True)
            ok = run()
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
            self.assertIn("hash chain intact", ok.stdout)
            with open(path) as f:
                text = f.read().replace("fell", "slipped")
            with open(path, "w") as f:
                f.write(text)
            bad = run()
            self.assertEqual(bad.returncode, 1)
            self.assertIn("TAMPERED", bad.stdout)


if __name__ == "__main__":
    unittest.main()
