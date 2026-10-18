# SafeSight: a camera that calls for help when a worker goes down

**Hack With Bangalore 4.0 · Track A: PipeGen (Computer Vision & Edge AI)**
Problem areas: Workplace Safety + Fall Detection · Bonuses: Closed Loop, Edge Optimization

Every year, workers get hurt on factory floors and in warehouses, and the
deadliest minutes are the ones *after* the accident, when nobody has noticed
yet. CCTV is everywhere, but nobody watches it live.

SafeSight turns an ordinary camera into a safety officer that never blinks:

* **Fall detection**: spots the moment a person goes from standing to lying, using pose keypoints (torso angle) with a bounding-box fallback.
* **Man-down escalation**: if they don't get up within 4 s, it raises a **critical** alarm.
* **Danger zones**: draw a polygon around a press machine or forklift lane in the dashboard; anyone who steps in triggers an alert.
* **Crowding**: per-zone occupancy limits (for example, one person in the loading bay).
* **Acts in the physical world**: a live control-room dashboard, an **ESP32 siren beacon** over serial, MQTT alerts, and a webhook (Slack, Discord or Teams).

## How PipeGen is load-bearing

PipeGen *is* the perception layer. SafeSight has no vision model of its own: every box, track ID
and skeleton it reasons about comes from the DeepStream app that PipeGen generated and compiled.

```
Camera ─▶ [PipeGen: Requirement → Pipeline IR → Model → Compiler (TensorRT) → Run (DeepStream)]
                                                     │ JSON metadata (file / MQTT)
                                                     ▼
                         SafeSight decide (fall · man-down · zones · crowding)  ~0.1 ms/frame
                                                     │
                 ┌───────────────┬───────────────────┼──────────────────┐
             Dashboard      ESP32 beacon         MQTT alerts         Webhook
```

* `pipegen/REQUIREMENT.md` is the exact plain-English requirement given to PipeGen, plus the evidence checklist for all five stages.
* `pipegen/trt_report.txt` is PipeGen's TensorRT speed report (FP16 vs INT8). It is shown on the dashboard with `--report`.
* `docs/pipeline-ir.png` is the PipeGen Pipeline IR graph screenshot.

## Evidence for the judges

| Claim | Proof |
|---|---|
| PipeGen ran all 5 stages | `docs/pipeline-ir.png` + stage screenshots |
| TensorRT engine built | `pipegen/trt_report.txt` (FP16 vs INT8), also shown on the dashboard |
| Runs live on hardware | live demo on USB camera + `samples/live_run_*.jsonl` recorded from PipeGen's real output |
| Actionable output | `events.jsonl` alerts, MQTT `safesight/alerts/*`, ESP32 siren |
| PipeGen is load-bearing | stop PipeGen's `run.sh` mid-demo: the dashboard flips to **NO PIPEGEN FEED** and no alerts can fire |

## Run it

Track A submission steps and requirement mapping: see [TRACK_A_CHECKLIST.md](TRACK_A_CHECKLIST.md). On the GPU machine: `./run_with_pipegen.sh /path/to/pipegen/export`.

**Quickest (Windows):** double-click `OPEN-DEMO.html` to open the built-in browser demo, with no Python needed. Or double-click `START.bat` to run the real server and open http://localhost:8080 automatically.

Needs Python 3.9+ only. No pip installs are needed for the core.

```bash
# 1. Rehearsal mode: scripted factory scene, no GPU needed
python3 -m safesight --source sim
#    open http://localhost:8080 and click "Enable sound"

# 2. Live with PipeGen: run the PipeGen-generated app, then point SafeSight at its JSON output
./run.sh                                   # inside the PipeGen export folder
python3 -m safesight --source file:$HOME/safesight/meta.jsonl --report pipegen/trt_report.txt
#    or over MQTT (pip install paho-mqtt):
python3 -m safesight --source mqtt://localhost:1883/pipegen/meta

# 3. Replay a recorded session (great for a backup demo)
python3 -m safesight --source replay:samples/demo_meta.jsonl
#    record your own live run with:  --record samples/live_run.jsonl
```

Optional actuators:

```bash
--serial /dev/ttyUSB0            # ESP32 beacon (pip install pyserial), flash firmware/safesight_beacon
--alerts-mqtt localhost:1883     # publishes safesight/alerts/<severity>
--webhook https://hooks.slack.com/services/...   # any endpoint that accepts {"text": ...}
```

Run the tests with `python3 -m unittest`.

## Dashboard at a glance

* **Floor status line**: one plain sentence (All clear / Watch / Act now) so anyone glancing at the screen knows what to do.
* **Colour legend** under the camera view; the same colours are used everywhere.
* **Voice alerts** (button top right): beeps and reads each incident aloud, for control rooms where nobody is staring at the screen.
* **Tamper-evident incident log**: every alert in `events.jsonl` carries the SHA-256 of the previous one, so edits or deletions are detectable for safety audits. Check it with `python3 -m safesight.verify events.jsonl`; the dashboard shows the result live.

## Repo layout

| Path | What |
|---|---|
| `safesight/parse.py` | Normalises PipeGen / DeepStream JSON (nvmsgconv minimal and full schemas, xyxy or xywh boxes, pose keypoints) |
| `safesight/engine.py` | Per-track state machine: upright → lying → FALL → MAN_DOWN → RECOVERED, zone dwell, crowding, cooldowns |
| `safesight/sources.py` | Inputs (tail file, replay, MQTT, stdin) and actions (log, MQTT, serial, webhook) |
| `safesight/__main__.py` | Pipeline thread + HTTP server + Server-Sent Events stream |
| `dashboard/index.html` | Control-room UI: live skeletons, zone editor, alert feed with ack, siren banner |
| `firmware/safesight_beacon` | ESP32 sketch: red strobe and buzzer for man-down, amber for zones, ACK button |
| `pipegen/` | PipeGen requirement, stage evidence and TensorRT report |
| `tests/` | Scenario tests: fall, man-down, recovery, zones, crowding, bbox-only fallback |

## Why it's built this way

* **Fall ≠ lying down.** A fall is only raised when a tracked person was upright within the last 2 s, so someone already lying under a machine for maintenance doesn't trigger alarms (covered by a unit test).
* **Pose first, box fallback.** Torso angle from the shoulder and hip keypoints is robust to camera angle; aspect ratio keeps it working with a detector-only pipeline.
* **Edge-friendly.** The decision layer is pure Python with no dependencies, at about 0.1 ms per frame. All heavy compute stays in PipeGen's TensorRT engines on the GPU or Jetson.
* **Privacy.** Only metadata (boxes and keypoints) leaves the GPU box. No video is stored or streamed by SafeSight.
