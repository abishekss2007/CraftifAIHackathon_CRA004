"""Normalise PipeGen / DeepStream metadata into SafeSight frames.

PipeGen's generated DeepStream app can emit JSON metadata (file, MQTT, Kafka).
DeepStream's nvmsgconv has two payload schemas, and custom PipeGen probes may
emit a flat list, so we accept all of them and turn each into:

    {"frame": int, "ts": float, "source": str, "width": int, "height": int,
     "objects": [{"id": str, "label": str, "conf": float,
                  "box": [x1, y1, x2, y2], "kps": [[x, y, c], ...] | None}]}
"""
import json
import time

PERSON_LABELS = {"person", "people", "pedestrian", "worker", "human", "0"}


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _box(o):
    b = o.get("bbox") or o.get("box") or o.get("rect") or o
    if isinstance(b, (list, tuple)) and len(b) >= 4:
        x1, y1, a, b2 = map(_f, b[:4])
        # [x, y, w, h] if the 3rd/4th values look like sizes smaller than origin
        if o.get("bbox_format") == "xywh":
            return [x1, y1, x1 + a, y1 + b2]
        return [x1, y1, a, b2]
    if "topleftx" in b:  # nvmsgconv full schema
        return [_f(b["topleftx"]), _f(b["toplefty"]), _f(b["bottomrightx"]), _f(b["bottomrighty"])]
    if "left" in b:
        l, t = _f(b["left"]), _f(b["top"])
        if "width" in b:
            return [l, t, l + _f(b["width"]), t + _f(b["height"])]
        return [l, t, _f(b.get("right")), _f(b.get("bottom"))]
    if "x1" in b:
        return [_f(b["x1"]), _f(b["y1"]), _f(b["x2"]), _f(b["y2"])]
    return None


def _obj(o):
    # nvmsgconv minimal schema: "trackingId|left|top|right|bottom|label"
    if isinstance(o, str):
        p = o.split("|")
        if len(p) < 6:
            return None
        return {"id": p[0], "label": p[5].strip().lower(), "conf": _f(p[6], 1.0) if len(p) > 6 else 1.0,
                "box": [_f(p[1]), _f(p[2]), _f(p[3]), _f(p[4])], "kps": None}
    box = _box(o)
    if not box:
        return None
    label = str(o.get("label") or o.get("type") or o.get("objectType") or o.get("class") or o.get("class_id") or "person").lower()
    kps = o.get("keypoints") or o.get("kps") or (o.get("pose") or {}).get("keypoints")
    return {"id": str(o.get("id") or o.get("object_id") or o.get("trackingId") or o.get("track_id") or id(o)),
            "label": label,
            "conf": _f(o.get("confidence") or o.get("conf") or o.get("score"), 1.0),
            "box": box, "kps": kps}


def normalise(msg):
    """Turn one decoded JSON payload (dict) into a SafeSight frame, or None."""
    if isinstance(msg, (bytes, str)):
        msg = json.loads(msg)
    objs = msg.get("objects") or msg.get("detections") or msg.get("objs") or []
    if not objs and isinstance(msg.get("object"), dict):  # full schema: one object per message
        objs = [dict(msg["object"], label=msg["object"].get("type") or msg["object"].get("objectType", "person"))]
    out = [x for x in (_obj(o) for o in objs) if x]
    for o in out:
        if o["label"] in PERSON_LABELS:
            o["label"] = "person"
    return {
        "frame": int(_f(msg.get("frame") or msg.get("frame_num") or msg.get("frameId"), 0)),
        "ts": _f(msg.get("ts"), 0) or time.time(),
        "source": str(msg.get("source") or msg.get("sensorId") or (msg.get("sensor") or {}).get("id") or "cam-0"),
        "width": int(_f(msg.get("width"), 1280)),
        "height": int(_f(msg.get("height"), 720)),
        "objects": out,
    }
