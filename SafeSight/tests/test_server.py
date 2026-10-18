import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from argparse import Namespace
from http.server import ThreadingHTTPServer

from safesight import sources
from safesight.__main__ import Hub, make_handler
from safesight.engine import Engine

ZONE = [{"name": "Press", "restricted": True, "polygon": [[0, 0], [0.5, 0], [0.5, 0.5]]}]


class ServerTest(unittest.TestCase):
    """Start the real HTTP server on a free port and call every endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = cls.tmp.name
        cls.log = os.path.join(d, "events.jsonl")
        report = os.path.join(d, "trt_report.txt")
        with open(report, "w") as f:
            f.write("FP16 1.9 ms\n")
        actions = sources.Actions(cls.log)
        actions.fire({"type": "FALL", "severity": "high", "message": "Person #1 fell", "ts": 1})
        actions.log.close()
        args = Namespace(source="sim", report=report, log=cls.log, zones=os.path.join(d, "zones.json"))
        cls.engine = Engine(list(ZONE))
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.engine, Hub(), args))
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as r:
            return r.status, r.read()

    def post(self, path, body):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_dashboard_served(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"SafeSight", body)

    def test_api_endpoints(self):
        self.assertEqual(json.loads(self.get("/api/zones")[1])[0]["name"], "Press")
        self.assertEqual(json.loads(self.get("/api/events")[1]), [])
        self.assertEqual(json.loads(self.get("/api/config")[1])["source"], "sim")
        self.assertIn(b"FP16", self.get("/api/report")[1])
        integrity = json.loads(self.get("/api/integrity")[1])
        self.assertEqual((integrity["ok"], integrity["entries"]), (True, 1))

    def test_unknown_path_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.get("/nope")
        self.assertEqual(cm.exception.code, 404)

    def test_zone_post_validates(self):
        status, body = self.post("/api/zones", [{"name": "", "polygon": [[0, 0], [1, 0], [1, 1]]}])
        self.assertEqual(status, 400)
        self.assertIn("error", body)
        good = [{"name": "Lane", "polygon": [[0, 0], [1, 0], [1, 1]], "max_people": 2}]
        self.assertEqual(self.post("/api/zones", good), (200, {"ok": True}))
        self.assertEqual(self.engine.zones[0]["name"], "Lane")
        self.post("/api/zones", ZONE)


if __name__ == "__main__":
    unittest.main()
