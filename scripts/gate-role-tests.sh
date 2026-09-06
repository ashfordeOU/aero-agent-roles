#!/usr/bin/env bash
# gate-role-tests.sh — run every role test file (core + structure).
set -uo pipefail
cd "$(dirname "$0")/.."
fail=0
for t in roles/*/tests/test_*.py; do
  echo "== $t =="
  OUT=$(python3 "$t" 2>&1) || {
    echo "FAIL: $t"
    printf '%s\n' "$OUT" | tail -25
    fail=1
  }
done
[ "$fail" = "0" ] && echo "role-tests: ALL PASS" || echo "role-tests: FAILURES"
exit "$fail"
