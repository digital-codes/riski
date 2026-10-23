#!/usr/bin/env bash
# Overnight completion of the name-vector backfill (categorization-indexing
# task 4.1). Resume-safe: already-embedded items are skipped, so it can be
# re-run at any time (e.g. after an interruption).
#
# Run it detached (copy-paste this line):
#   nohup utils/backfill_namevecs_overnight.sh >/dev/null 2>&1 &
#
# Progress:  tail -f /tmp/opencode/namevec_overnight.log
# Remaining after backfill (categorization-indexing @ ~600 done each):
#   ~1.9k Meetings + ~12.9k Papers + ~17.8k AgendaItems + ~47.2k Files
# At the observed ~8 vectors/s (6 workers, deepinfra) that is ~2.5-3 h.

# START HERE — background backfill command:
# nohup utils/backfill_namevecs_overnight.sh >/dev/null 2>&1 &

set -u

WORKERS="${NAMEVEC_WORKERS:-6}"
LOG="${NAMEVEC_LOG:-/tmp/opencode/namevec_overnight.log}"
cd "$(dirname "$0")/.."

echo "=== name-vec overnight backfill starting $(date) (workers=$WORKERS) ===" >> "$LOG"
python3 src/pgBackfillNameVecs.py --workers "$WORKERS" >> "$LOG" 2>&1
echo "=== finished $(date) ===" >> "$LOG"
