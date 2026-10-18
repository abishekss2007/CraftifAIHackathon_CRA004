#!/usr/bin/env bash
# Smoke test: start the real SafeSight server, exercise its HTTP API, wait for the
# scripted fall to raise FALL and MAN_DOWN, then prove the incident log is
# tamper-evident. Usage: tools/smoke.sh [sim|replay]   (run from anywhere)
set -euo pipefail
cd "$(dirname "$0")/.."

MODE=${1:-sim}
PORT=${PORT:-8080}
PY=${PYTHON:-python3}
WORK=$(mktemp -d)
LOG="$WORK/events.jsonl"
cp zones.json "$WORK/zones.json"
case "$MODE" in
  sim) SRC=sim ;;
  replay) SRC=replay:samples/demo_meta.jsonl ;;
  *) echo "unknown mode $MODE" >&2; exit 2 ;;
esac

"$PY" -m safesight --source "$SRC" --port "$PORT" --log "$LOG" --zones "$WORK/zones.json" >"$WORK/server.log" 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null || true; rm -rf "$WORK"' EXIT
BASE="http://127.0.0.1:$PORT"

for _ in $(seq 1 50); do curl -fsS "$BASE/api/config" >/dev/null 2>&1 && break; sleep 0.2; done
curl -fsS "$BASE/" | grep -q "SafeSight" || { echo "dashboard not served"; cat "$WORK/server.log"; exit 1; }
curl -fsS "$BASE/api/config" | grep -q "\"source\": \"$SRC\""
curl -fsS "$BASE/api/zones" | grep -q "Press machine"
echo "ok   dashboard and API answer on $BASE (source $SRC)"

CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
  -d '[{"name":"","polygon":[[0,0],[1,0],[1,1]]}]' "$BASE/api/zones")
[ "$CODE" = 400 ] || { echo "bad zone list returned $CODE, expected 400"; exit 1; }
echo "ok   invalid zone list rejected with 400"

for _ in $(seq 1 60); do
  EVENTS=$(curl -fsS "$BASE/api/events")
  if grep -q '"MAN_DOWN"' <<<"$EVENTS" && grep -q '"FALL"' <<<"$EVENTS"; then break; fi
  sleep 0.5
done
grep -q '"MAN_DOWN"' <<<"$EVENTS" || { echo "no MAN_DOWN alert within 30 s"; echo "$EVENTS"; exit 1; }
echo "ok   scripted fall raised FALL and MAN_DOWN"

curl -fsS "$BASE/api/integrity" | grep -q '"ok": true'
"$PY" -m safesight.verify "$LOG"
sed -i '1s/"severity": "[a-z]*"/"severity": "info"/' "$LOG"
if "$PY" -m safesight.verify "$LOG"; then echo "edited log was not detected"; exit 1; fi
echo "ok   editing the incident log is detected"
echo "smoke test ($MODE) passed"
