"""Scripted camera scenario that emits PipeGen-style JSON frames.

Used for rehearsing the demo and testing rules without a GPU. Produces the
same payload shape SafeSight reads from PipeGen (tracked person boxes plus
COCO-17 pose keypoints), so the whole downstream path is exercised.
"""
import math
import time

W, H = 1280, 720
CYCLE = 26.0

# Standing skeleton in body units (x right, y down, feet at y=0, head at y=-1)
SKEL = [(0, -0.95), (-0.03, -0.97), (0.03, -0.97), (-0.06, -0.95), (0.06, -0.95),
        (-0.12, -0.80), (0.12, -0.80), (-0.16, -0.62), (0.16, -0.62), (-0.17, -0.46), (0.17, -0.46),
        (-0.08, -0.50), (0.08, -0.50), (-0.09, -0.26), (0.09, -0.26), (-0.09, 0.0), (0.09, 0.0)]


def body(cx, feet_y, height, angle_deg, stride=0.0):
    """Keypoints + box for a person whose feet are at (cx, feet_y), tilted by angle."""
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    kps = []
    for i, (x, y) in enumerate(SKEL):
        if i in (13, 15):
            x += stride * 0.08 * (1 if i == 15 else 0.5)
        if i in (14, 16):
            x -= stride * 0.08 * (1 if i == 16 else 0.5)
        # rotate around feet, so a fall pivots to the ground
        rx, ry = x * ca - y * sa, x * sa + y * ca
        kps.append([round(cx + rx * height, 1), round(feet_y + ry * height, 1), 0.92])
    xs, ys = [k[0] for k in kps], [k[1] for k in kps]
    pad = 0.05 * height
    return kps, [min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad * 0.3]


def _lerp(a, b, u):
    return a + (b - a) * max(0.0, min(1.0, u))


def actors(t):
    """Yield (id, cx, feet_y, height, angle, stride) for scene time t in [0, CYCLE)."""
    walk = math.sin(t * 6)
    # Person 1 walks across the floor, falls at 6s, stays down, gets up at 15s.
    if t < 6:
        x, ang = _lerp(180, 560, t / 6), 0
    elif t < 6.6:
        x, ang = 560 + (t - 6) * 60, _lerp(0, 88, (t - 6) / 0.6)
    elif t < 15:
        x, ang = 596, 88
    elif t < 16:
        x, ang = 596, _lerp(88, 0, t - 15)
    else:
        x, ang = _lerp(596, 1100, (t - 16) / 10), 0
    yield "1", x, 560, 300, ang, walk if ang == 0 else 0
    # Person 2 wanders into the restricted machine zone around 9s.
    x2 = _lerp(1360, 960, (t - 3) / 6) if t < 14 else _lerp(960, 1360, (t - 14) / 6)
    yield "2", x2, 645, 330, 0, walk
    # Person 3 and 4 walk into the loading bay together (limit 1) late in the cycle.
    if t > 17:
        yield "3", _lerp(-40, 260, (t - 17) / 5), 690, 360, 0, -walk
        yield "4", _lerp(-120, 170, (t - 17.5) / 5), 700, 370, 0, walk


def frames(fps=15, realtime=True, source="cam-floor-1", loops=None):
    n = 0
    start = time.time()
    per_loop = int(round(CYCLE * fps))
    while loops is None or n < loops * per_loop:
        t_scene = (n % per_loop) / fps
        objs = []
        for tid, cx, fy, h, ang, stride in actors(t_scene):
            kps, box = body(cx, fy, h, ang, stride)
            objs.append({"id": tid, "label": "person", "confidence": 0.9, "bbox": box, "keypoints": kps})
        ts = start + n / fps
        yield {"frame": n, "ts": ts, "source": source, "width": W, "height": H, "objects": objs}
        n += 1
        if realtime:
            delay = ts - time.time()
            if delay > 0:
                time.sleep(delay)
