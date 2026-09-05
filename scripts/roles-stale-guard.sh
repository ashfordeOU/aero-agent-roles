#!/usr/bin/env bash
# roles-stale-guard.sh — every generated stat in docs/ and manifest must
# match the live tree (numbers-only-via-generation law, mirror of the
# skills stale-number-guard). NEVER hand-edit generated numbers. This
# guard is non-mutating: it regenerates into a temp dir and diffs, so a
# clean tree stays clean.
set -uo pipefail
cd "$(dirname "$0")/.."
fail=0
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

check_generated() {
  local gen="$1" file="$2" name="$3"
  if [ ! -f "$file" ]; then
    echo "MISSING: $name ($file not committed)"
    fail=1
    return
  fi
  # copy the committed file aside, regenerate over it, diff
  local committed="$TMP/$(basename "$file").committed"
  cp "$file" "$committed"
  if ! python3 "$gen" >/dev/null 2>&1; then
    echo "FAIL: $name generator crashed"
    fail=1
    return
  fi
  if ! diff -q "$committed" "$file" >/dev/null 2>&1; then
    echo "STALE: $name — regenerated differs from committed (run $gen and commit)"
    fail=1
  fi
}

check_generated scripts/coverage-matrix.py docs/COVERAGE-MATRIX.md "coverage matrix"
check_generated scripts/update-role-ratings.py eval/role-ratings.md "role ratings"
check_generated scripts/gen_manifest.py manifest.json "manifest"

if ! ls docs/*.png >/dev/null 2>&1; then
  echo "STALE: no generated visuals in docs/ (run make visuals)"
  fail=1
fi

[ "$fail" = "0" ] && echo "roles-stale-guard: OK (all generated stats current)"
exit "$fail"
