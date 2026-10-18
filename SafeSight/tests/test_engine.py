import json
import os
import unittest

from safesight import simulate
from safesight.engine import Engine, point_in_poly
from safesight.parse import normalise

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(strip_pose=False):
    with open(os.path.join(ROOT, "zones.json")) as f:
        e = Engine(json.load(f))
    out = []
    for raw in simulate.frames(fps=15, realtime=False, loops=1):
        if strip_pose:
            for o in raw["objects"]:
                o.pop("keypoints")
        evs, _ = e.process(normalise(raw))
        out += [(ev["type"], ev["track"]) for ev in evs]
    return out


class EngineTest(unittest.TestCase):
    def test_scenario_with_pose(self):
        evs = run()
        self.assertIn(("FALL", "1"), evs)
        self.assertIn(("MAN_DOWN", "1"), evs)
        self.assertIn(("RECOVERED", "1"), evs)
        self.assertIn(("ZONE_BREACH", "2"), evs)
        self.assertIn("OVERCROWD", [t for t, _ in evs])
        self.assertEqual(sum(1 for t, _ in evs if t == "FALL"), 1)

    def test_scenario_bbox_only(self):
        self.assertIn(("FALL", "1"), run(strip_pose=True))

    def test_person_lying_from_start_is_not_a_fall(self):
        e = Engine()
        for i in range(60):
            evs, _ = e.process({"frame": i, "ts": i / 15, "source": "t", "width": 1280, "height": 720,
                                "objects": [{"id": "x", "label": "person", "conf": 1, "box": [0, 600, 300, 680], "kps": None}]})
            self.assertEqual(evs, [])

    def test_minimal_schema(self):
        f = normalise({"objects": ["7|100|100|160|300|Person"]})
        self.assertEqual(f["objects"][0]["box"], [100, 100, 160, 300])
        self.assertEqual(f["objects"][0]["label"], "person")

    def test_point_in_poly(self):
        sq = [[0, 0], [1, 0], [1, 1], [0, 1]]
        self.assertTrue(point_in_poly(0.5, 0.5, sq))
        self.assertFalse(point_in_poly(1.5, 0.5, sq))


class ZoneValidationTest(unittest.TestCase):
    def test_valid_zone_passes_and_is_cleaned(self):
        from safesight.__main__ import validate_zones
        z = validate_zones([{"name": " Lane ", "polygon": [[0, 0], [1, 0], [1, 1]], "max_people": "2"}])
        self.assertEqual(z[0]["name"], "Lane")
        self.assertEqual(z[0]["max_people"], 2)

    def test_bad_zones_rejected(self):
        from safesight.__main__ import validate_zones
        bad = [
            {"zones": 1},
            [{"name": "", "polygon": [[0, 0], [1, 0], [1, 1]]}],
            [{"name": "A", "polygon": [[0, 0], [1, 0]]}],
            [{"name": "A", "polygon": [[0, 0], [2, 0], [1, 1]]}],
            [{"name": "A", "polygon": [[0, 0], [1, 0], [1, 1]]}, {"name": "a", "polygon": [[0, 0], [1, 0], [1, 1]]}],
            [{"name": "A", "polygon": [[0, 0], [1, 0], [1, 1]], "max_people": 0}],
        ]
        for z in bad:
            with self.assertRaises((ValueError, TypeError)):
                validate_zones(z)


class EvidenceChainTest(unittest.TestCase):
    def test_chain_detects_edits(self):
        import tempfile
        from safesight.sources import Actions, verify_log
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "events.jsonl")
            a = Actions(path)
            for i in range(3):
                a.fire({"type": "FALL", "severity": "high", "message": f"Person #{i} fell", "ts": i})
            a.log.close()
            self.assertEqual(verify_log(path)[:2], (True, 3))
            b = Actions(path)  # restart continues the same chain
            b.fire({"type": "FALL", "severity": "high", "message": "again", "ts": 9})
            b.log.close()
            self.assertEqual(verify_log(path)[:2], (True, 4))
            lines = open(path).read().splitlines()
            lines[1] = lines[1].replace("Person #1 fell", "nothing happened")
            open(path, "w").write("\n".join(lines) + "\n")
            ok, _, bad = verify_log(path)
            self.assertFalse(ok)
            self.assertEqual(bad, 2)


if __name__ == "__main__":
    unittest.main()
