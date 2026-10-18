"""Check that the incident log has not been edited: python -m safesight.verify [events.jsonl]"""
import sys

from .sources import verify_log

path = sys.argv[1] if len(sys.argv) > 1 else "events.jsonl"
ok, n, bad = verify_log(path)
if ok:
    print(f"OK: {n} incidents, hash chain intact")
else:
    print(f"TAMPERED: chain breaks at line {bad} (after {n - 1} good incidents)")
    sys.exit(1)
