# Track A (PipeGen) requirement checklist

| Requirement | How SafeSight meets it | Evidence to submit |
|---|---|---|
| **Full PipeGen flow** (Requirement → Pipeline IR → Model → Compiler → Run) | The whole perception layer is built in PipeGen from `pipegen/REQUIREMENT.md`. SafeSight has no vision model of its own. | Screenshot of each stage, especially the Pipeline IR graph → `docs/pipeline-ir.png` |
| **TensorRT engine + speed report** | Detector (and pose model) compiled in the Compiler stage, FP16 plus INT8 for the Edge Optimization bonus | PipeGen speed report text → `pipegen/trt_report.txt` (shown on the dashboard) |
| **Live run** on video / USB / CSI / RTSP on an NVIDIA GPU or Jetson | PipeGen's generated `run.sh` (DeepStream) on a USB camera or a video file under /home | Live demo + `samples/live_run_*.jsonl` recorded automatically |
| **Actionable output** beyond boxes | PipeGen JSON/MQTT metadata → SafeSight raises FALL, MAN_DOWN, ZONE_BREACH, OVERCROWD alerts, writes `events.jsonl`, publishes MQTT `safesight/alerts/*`, optional webhook and ESP32 siren | Dashboard screenshot with alerts + `events.jsonl` |

## Exact steps on the GPU machine (Linux x86-64 + NVIDIA GPU, or Jetson on JetPack 6)

Run from an **X11 desktop session** (not Wayland: pick "Ubuntu on Xorg" at login) and keep test videos **under /home**. Kit needed: a USB camera; optional ESP32 + USB cable + LEDs/buzzer for the Closed Loop bonus (PRD: `firmware/FIRMGEN_PRD.md`, sent over serial).

```bash
pipegen --version                 # must print 0.5.1
git clone https://github.com/abishekss2007/CraftifAIHackathon_CRA004 && cd CraftifAIHackathon_CRA004/SafeSight
```

1. Start PipeGen and paste the block from `pipegen/REQUIREMENT.md` as the Requirement.
2. Accept the Pipeline IR (screenshot it), pick models, compile to TensorRT FP16 (and INT8), and save the speed report to `pipegen/trt_report.txt`.
3. In the Run stage, set the source to your USB camera (`/dev/video0`) or a video under `/home`, and the JSON output to `~/safesight/meta.jsonl` (or MQTT topic `pipegen/meta`).
4. Run everything:

```bash
./run_with_pipegen.sh /path/to/pipegen/export        # starts run.sh + SafeSight + dashboard
# MQTT instead of a file:
python3 -m safesight --source mqtt://localhost:1883/pipegen/meta --report pipegen/trt_report.txt
```

5. Demo: walk into a drawn zone → amber alert; lie down → FALL, then MAN DOWN after 4 s; stand up → recovered.

If no people appear on the dashboard, PipeGen's JSON fields differ: send one line of `~/safesight/meta.jsonl` to Claude.
