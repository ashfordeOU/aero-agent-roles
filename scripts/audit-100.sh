#!/usr/bin/env bash
# 100% audit: every role must be an executable worker.
set -uo pipefail
cd "$(dirname "$0")/.."
PASS=0; FAIL=0; FAILURES=""

TOTAL=$(ls -d roles/*/ 2>/dev/null | wc -l | tr -d ' ')
echo "════════ ROLE 100% AUDIT ════════"
for role in roles/*/; do
  slug=$(basename "$role")
  probs=""
  # 1. core engine exists
  [ -d "$role/core" ] && [ -n "$(ls "$role"/core/*_core.py 2>/dev/null)" ] || probs="$probs no-core"
  # 2. cli.py exists
  [ -f "$role/cli.py" ] || probs="$probs no-cli"
  # 3. template has NO blank fields
  blanks=$(grep -c "___" "$role"/templates/*.md 2>/dev/null | awk -F: '{s+=$2} END {print s+0}')
  [ "$blanks" = "0" ] || probs="$probs blanks=$blanks"
  # 4. core test exists
  core_test=$(ls "$role"/tests/test_*_core.py 2>/dev/null | head -1)
  [ -n "$core_test" ] || probs="$probs no-core-test"
  # 5. core test passes
  if [ -n "$core_test" ]; then
    python3 "$core_test" >/dev/null 2>&1 || probs="$probs core-test-FAIL"
  fi
  # 6. cli build + check work standalone
  if [ -f "$role/cli.py" ]; then
    AEROSKILLS_DEV=/nonexistent python3 "$role/cli.py" build --out /tmp/audit_$slug.md >/dev/null 2>&1 || probs="$probs build-FAIL"
    AEROSKILLS_DEV=/nonexistent python3 "$role/cli.py" check --file /tmp/audit_$slug.md >/dev/null 2>&1 || probs="$probs check-FAIL"
  fi
  if [ -z "$probs" ]; then
    echo "  PASS  $slug"
    PASS=$((PASS+1))
  else
    echo "  FAIL  $slug:$probs"
    FAIL=$((FAIL+1)); FAILURES="$FAILURES $slug"
  fi
done
echo "════════════════════════════════"
echo "RESULT: $PASS pass, $FAIL fail"
[ -n "$FAILURES" ] && echo "FAILING:$FAILURES"
[ "$FAIL" = "0" ] && echo "ALL $TOTAL ROLES ARE 100% EXECUTABLE WORKERS" || exit 1
