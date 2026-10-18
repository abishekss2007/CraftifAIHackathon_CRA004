"""SafeSight decision layer: turns per-frame detections into safety events.

Rules (all per tracked person):
  FALL         upright -> lying transition (torso angle from pose keypoints,
               or bounding-box aspect ratio when no pose) confirmed for
               `fall_confirm_s`.
  MAN_DOWN     still lying `man_down_s` after the fall: no recovery -> CRITICAL.
  ZONE_BREACH  feet point inside a restricted polygon for `zone_dwell_s`.
  OVERCROWD    more than `max_people` people in a zone that sets a limit.
"""
import math
import time
from collections import deque

SEVERITY = {"FALL": "high", "MAN_DOWN": "critical", "ZONE_BREACH": "warning", "OVERCROWD": "warning", "RECOVERED": "info"}

DEFAULTS = {
    "lying_aspect": 1.25,     # bbox width / height above this = horizontal body
    "lying_angle": 55.0,      # torso degrees from vertical above this = lying
    "fall_confirm_s": 0.4,
    "upright_memory_s": 2.0,  # must have been upright this recently (it's a fall, not someone sleeping)
    "man_down_s": 4.0,
    "zone_dwell_s": 0.5,
    "cooldown_s": 8.0,
    "track_ttl_s": 3.0,
}


def point_in_poly(x, y, poly):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi:
            inside = not inside
        j = i
    return inside


def torso_angle(kps):
    """Degrees from vertical of the shoulder-mid -> hip-mid line (COCO-17 keypoints)."""
    try:
        ls, rs, lh, rh = kps[5], kps[6], kps[11], kps[12]
    except (IndexError, TypeError):
        return None
    pts = [ls, rs, lh, rh]
    if any(len(p) > 2 and p[2] < 0.3 for p in pts):
        return None
    sx, sy = (ls[0] + rs[0]) / 2, (ls[1] + rs[1]) / 2
    hx, hy = (lh[0] + rh[0]) / 2, (lh[1] + rh[1]) / 2
    return math.degrees(math.atan2(abs(hx - sx), abs(hy - sy) or 1e-9))


class Track:
    def __init__(self, tid):
        self.id = tid
        self.last_seen = 0.0
        self.last_upright = None
        self.lying_since = None
        self.fallen_at = None
        self.man_down_sent = False
        self.zone_since = {}
        self.posture = "unknown"
        self.hist = deque(maxlen=30)


class Engine:
    def __init__(self, zones=None, **cfg):
        self.cfg = dict(DEFAULTS, **cfg)
        self.zones = zones or []
        self.tracks = {}
        self.cooldown = {}
        self.stats = {"frames": 0, "people": 0, "events": 0, "fps": 0.0}
        self._fps_t = deque(maxlen=60)

    # -- helpers ---------------------------------------------------------
    def _emit(self, events, kind, now, track=None, zone=None, frame=None, **extra):
        key = (kind, track.id if track else None, zone["name"] if zone else None)
        if now - self.cooldown.get(key, -1e9) < self.cfg["cooldown_s"]:
            return
        self.cooldown[key] = now
        ev = {"type": kind, "severity": SEVERITY[kind], "ts": now, "track": track.id if track else None,
              "zone": zone["name"] if zone else None, "source": frame["source"] if frame else None,
              "frame": frame["frame"] if frame else None}
        ev.update(extra)
        ev["message"] = self._describe(ev)
        self.stats["events"] += 1
        events.append(ev)

    @staticmethod
    def _describe(ev):
        who = f"Person #{ev['track']}" if ev.get("track") else "Zone"
        return {
            "FALL": f"{who} fell",
            "MAN_DOWN": f"{who} has not got up for {ev.get('down_s', 0):.0f}s, send help",
            "ZONE_BREACH": f"{who} entered restricted zone '{ev.get('zone')}'",
            "OVERCROWD": f"{ev.get('count')} people in '{ev.get('zone')}' (limit {ev.get('limit')})",
            "RECOVERED": f"{who} is back on their feet",
        }[ev["type"]]

    def _lying(self, o, W, H):
        ang = torso_angle(o["kps"]) if o.get("kps") else None
        x1, y1, x2, y2 = o["box"]
        aspect = (x2 - x1) / max(y2 - y1, 1e-6)
        if ang is not None:
            return ang > self.cfg["lying_angle"], ang, aspect
        return aspect > self.cfg["lying_aspect"], None, aspect

    # -- main ------------------------------------------------------------
    def process(self, frame, now=None):
        now = frame.get("ts") or now or time.time()
        events = []
        W, H = frame["width"], frame["height"]
        people = [o for o in frame["objects"] if o["label"] == "person"]
        self.stats["frames"] += 1
        self.stats["people"] = len(people)
        self._fps_t.append(now)
        if len(self._fps_t) > 1:
            self.stats["fps"] = round((len(self._fps_t) - 1) / max(self._fps_t[-1] - self._fps_t[0], 1e-6), 1)

        zone_counts = {z["name"]: 0 for z in self.zones}
        annotated = []
        for o in people:
            t = self.tracks.get(o["id"]) or self.tracks.setdefault(o["id"], Track(o["id"]))
            t.last_seen = now
            lying, ang, aspect = self._lying(o, W, H)
            x1, y1, x2, y2 = o["box"]
            fx, fy = (x1 + x2) / 2 / W, y2 / H  # feet point, normalised

            if not lying:
                if t.fallen_at and t.posture == "down":
                    self._emit(events, "RECOVERED", now, t, frame=frame)
                t.last_upright, t.lying_since, t.fallen_at, t.man_down_sent = now, None, None, False
                t.posture = "upright"
            else:
                t.lying_since = t.lying_since or now
                recent_upright = t.last_upright is not None and now - t.last_upright < self.cfg["upright_memory_s"] + self.cfg["fall_confirm_s"]
                if t.fallen_at is None and now - t.lying_since >= self.cfg["fall_confirm_s"] and recent_upright:
                    t.fallen_at = now
                    t.posture = "down"
                    self._emit(events, "FALL", now, t, frame=frame, angle=ang, aspect=round(aspect, 2), box=o["box"])
                elif t.fallen_at and not t.man_down_sent and now - t.fallen_at >= self.cfg["man_down_s"]:
                    t.man_down_sent = True
                    self._emit(events, "MAN_DOWN", now, t, frame=frame, down_s=now - t.fallen_at, box=o["box"])
                elif t.fallen_at is None:
                    t.posture = "lying"

            in_zones = []
            for z in self.zones:
                if point_in_poly(fx, fy, z["polygon"]):
                    zone_counts[z["name"]] += 1
                    in_zones.append(z["name"])
                    if z.get("restricted", True):
                        since = t.zone_since.setdefault(z["name"], now)
                        if now - since >= self.cfg["zone_dwell_s"]:
                            self._emit(events, "ZONE_BREACH", now, t, z, frame=frame, box=o["box"])
                else:
                    t.zone_since.pop(z["name"], None)
            annotated.append({**o, "posture": t.posture, "zones": in_zones,
                              "angle": None if ang is None else round(ang, 1), "aspect": round(aspect, 2)})

        for z in self.zones:
            lim = z.get("max_people")
            if lim is not None and zone_counts[z["name"]] > lim:
                self._emit(events, "OVERCROWD", now, zone=z, frame=frame, count=zone_counts[z["name"]], limit=lim)

        for tid in [k for k, v in self.tracks.items() if now - v.last_seen > self.cfg["track_ttl_s"]]:
            del self.tracks[tid]

        return events, {**frame, "objects": annotated + [o for o in frame["objects"] if o["label"] != "person"],
                        "zone_counts": zone_counts}
