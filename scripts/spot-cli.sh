#!/usr/bin/env bash
# spot-check: every role's cli build + check works standalone (no skills repo)
set -uo pipefail
cd "$(dirname "$0")/.."
FAILS=0
for role in roles/*/; do
  slug=$(basename "$role")
  if [ -f "$role/cli.py" ]; then
    OUT=/tmp/spot_$slug.md
    AEROSKILLS_DEV=/nonexistent python3 "$role/cli.py" build --out "$OUT" >/dev/null 2>&1 || { echo "BUILD FAIL $slug"; FAILS=1; continue; }
    AEROSKILLS_DEV=/nonexistent python3 "$role/cli.py" check --file "$OUT" >/dev/null 2>&1 || { echo "CHECK FAIL $slug"; FAILS=1; continue; }
    echo "  OK  $slug (standalone build + check)"
  fi
done
[ "$FAILS" = "0" ] && echo "ALL CLI STANDALONE: PASS" || echo "FAILURES above"
exit "$FAILS"
