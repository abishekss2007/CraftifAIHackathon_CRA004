#!/usr/bin/env bash
# Run on the NVIDIA GPU Linux machine (or Jetson) AFTER PipeGen's Run stage.
# Usage: ./run_with_pipegen.sh <pipegen_export_dir> [meta.jsonl path]
#   1. starts the PipeGen-generated DeepStream app (run.sh) on the camera/video
#   2. starts SafeSight on PipeGen's JSON metadata and opens the dashboard
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
EXPORT="${1:?give the PipeGen export folder (the one containing run.sh)}"
META="${2:-$HOME/safesight/meta.jsonl}"
mkdir -p "$(dirname "$META")" "$HERE/samples"

echo "[1/2] Starting PipeGen pipeline: $EXPORT/run.sh"
( cd "$EXPORT" && ./run.sh ) &
PG=$!
trap 'kill $PG 2>/dev/null || true' EXIT

echo "[2/2] Starting SafeSight on $META (dashboard: http://localhost:8080)"
REPORT=()
[ -f "$HERE/pipegen/trt_report.txt" ] && REPORT=(--report "$HERE/pipegen/trt_report.txt")
SERIAL=()
[ -e /dev/ttyUSB0 ] && SERIAL=(--serial /dev/ttyUSB0)
( sleep 3; xdg-open http://localhost:8080 >/dev/null 2>&1 || true ) &
cd "$HERE"
python3 -m safesight --source "file:$META" \
  --record "samples/live_run_$(date +%H%M).jsonl" "${REPORT[@]}" "${SERIAL[@]}"
