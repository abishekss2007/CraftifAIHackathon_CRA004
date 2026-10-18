# SafeSight: pitch and demo script (about 3 minutes)

## 0:00 Hook (20 s)
"When a worker collapses on a factory floor, the injury isn't always what kills them.
The minutes before anyone notices are. There are cameras everywhere, but nobody's watching.
We built SafeSight: a camera that notices in under a second and calls for help."

## 0:20 What it is (30 s)
"SafeSight is a real-time safety pipeline. CraftifAI PipeGen builds and runs all of the perception:
person detection, tracking and pose, compiled to TensorRT and running on DeepStream.
SafeSight is the decision and action layer on top: falls, man-down, danger zones and crowding,
and it acts physically through an ESP32 siren beacon."

## 0:50 PipeGen walkthrough (40 s): show the screenshots
1. **Requirement**: "We described the goal in plain English." (show `pipegen/REQUIREMENT.md`)
2. **Pipeline IR**: "PipeGen planned source → detector → tracker → pose → message broker." (IR graph)
3. **Model + Compiler**: "Compiled to TensorRT. FP16 runs at __ FPS; INT8 runs at __ FPS with __ % accuracy change." (speed report, Edge Optimization bonus)
4. **Run**: "`run.sh` is live on this camera right now, streaming JSON over MQTT."

## 1:30 Live demo (60 s)
1. Dashboard open, camera live. "Every person gets an ID and a skeleton, straight from PipeGen."
2. **Draw a zone** around a table: "Say this is a press machine." Walk into it → amber alert, beacon blinks amber.
3. **Fall**: teammate lies down on a mat in view → "Person #N fell" (red). Stay down → after 4 s the **MAN DOWN** banner appears and the ESP32 strobes and buzzes. "That's the closed loop: vision driving hardware."
4. Teammate stands up → "back on their feet". Press ACK on the beacon.
5. **Load-bearing proof:** press Ctrl+C on PipeGen's `run.sh`. The dashboard flips to *NO PIPEGEN FEED* and the people vanish. "Without PipeGen, SafeSight is blind. PipeGen *is* our perception." Restart it and detections return.
6. Point at the KPIs: "Decision latency is about 0.1 ms. The GPU does the heavy lifting, so this runs on a Jetson at the edge."

*Backup if the camera or GPU fails:* `python3 -m safesight --source replay:samples/live_run.jsonl` (record it beforehand with `--record`) or `--source sim`.

## 2:30 Why it matters and what's next (30 s)
"No new cameras needed. It works on existing CCTV over RTSP. Only metadata leaves the device, so it's privacy-friendly.
Next up: PPE detection (helmets and vests) as another PipeGen model, multi-camera tracking, and WhatsApp alerts to supervisors.
SafeSight: PipeGen sees it, SafeSight acts on it. Thank you."

## Likely judge questions
* *How do you avoid false alarms when someone sits or bends?* We need a sustained torso angle above 55° for 0.4 s, **and** the person must have been upright within the last 2 s. Bending forward never passes the angle threshold for long.
* *Is PipeGen really load-bearing?* Yes. SafeSight has no vision model; remove PipeGen and it sees nothing.
* *Why the bounding-box fallback?* So it still works with a detector-only engine (for example, an INT8 detector on a small Jetson).
