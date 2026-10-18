# PipeGen Stage 1: Requirement (paste this into PipeGen)

> Build a real-time workplace-safety vision pipeline for a factory floor camera.
> Detect every **person**, give each one a stable **tracking ID**, and estimate
> **body pose (COCO 17 keypoints)** for each tracked person, so a downstream
> service can tell standing from lying down and detect falls.
>
> Input: a USB camera (or a test video file under /home, or RTSP) at 1280x720, 15 fps or higher.
> Models: a person detector (YOLO-family, person class) and a top-down or
> bottom-up pose model; use the PipeGen catalog where possible.
> Tracker: NvDCF or IOU tracker so IDs persist across frames.
> Compile all models to **TensorRT FP16**, and also build an **INT8** engine of
> the detector so we can compare speed, power and accuracy.
>
> Output, every frame:
> 1. On-screen display with boxes, track IDs and skeletons.
> 2. **JSON metadata, one line per frame**, written to `~/safesight/meta.jsonl`
>    **and** published to MQTT `localhost:1883` topic `pipegen/meta`, with:
>    `frame`, `ts` (unix seconds), `source`, `width`, `height`, and an `objects`
>    list where each object has `id` (tracking ID), `label`, `confidence`,
>    `bbox` as `[x1, y1, x2, y2]` pixels and `keypoints` as 17 `[x, y, score]`.
>
> Target: under 50 ms end-to-end latency per frame on the GPU.

## Stage checklist for the demo (the track requires all five)

| Stage | What to capture as evidence |
|---|---|
| 1 Requirement | Screenshot of the text above accepted by PipeGen |
| 2 Pipeline IR | **Screenshot of the IR graph** (source → detector → tracker → pose → msgconv/broker) → save as `docs/pipeline-ir.png` |
| 3 Model | Screenshot of the chosen models |
| 4 Compiler | **TensorRT speed report** (FP16 vs INT8) → copy text to `pipegen/trt_report.txt` |
| 5 Run | `run.sh` running live on the camera, plus SafeSight dashboard reacting |

## If the JSON PipeGen emits looks different

SafeSight's parser (`safesight/parse.py`) already accepts DeepStream's
nvmsgconv minimal schema (`"id|left|top|right|bottom|label"` strings), the full
schema (`object.bbox.topleftx…`), and `left/top/width/height` boxes. If pose
keypoints are missing it falls back to bounding-box aspect ratio for fall
detection, so the demo still works with a detector-only pipeline.

## Edge Optimization bonus

Put FP16 vs INT8 numbers from the Compiler stage here and in the pitch:

| Engine | Latency (ms) | FPS | Power (W) | mAP / accuracy |
|---|---|---|---|---|
| FP32 | | | | |
| FP16 | | | | |
| INT8 | | | | |
