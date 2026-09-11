#!/usr/bin/env bash
# roles-stale-guard.sh — every generated stat in docs/ and manifest must
# match the live tree (numbers-only-via-generation law, mirror of the
# skills stale-number-guard). NEVER hand-edit generated numbers. This
# guard is non-mutating: it snapshots the committed file, regenerates,
# diffs, and RESTORES the snapshot, so a clean tree stays clean and a
# stale tree stays exactly as it was found.
#
# 2026-09-11 (relay tick): the byte-diff could never pass for
# eval/role-ratings.md, whose generator stamps wall-clock fields
# (``updated: <date>`` + ``regenerated <date> <time> UTC``). Every run
# regenerated a new timestamp, so the gate was structurally red and left
# the tree dirty on each check. Volatile timestamp fields are now
# normalized out of the comparison (everything else stays byte-exact:
# a changed rating/evidence row still fails). Detected while the
# committed COVERAGE-MATRIX.md had gone 3 days stale (637 vs 796 leaves).
set -uo pipefail
cd "$(dirname "$0")/.."
fail=0
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Drop wall-clock fields the generators stamp (informational only, never
# a work signal): ``updated: <date>`` lines and the ``regenerated <ts>``
# fragment in the ratings audit banner.
normalize() {
  sed -E \
    -e '/^updated: /d' \
    -e 's/regenerated [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2} UTC/regenerated <ts>/' \
    "$1"
}

check_generated() {
  local gen="$1" file="$2" name="$3"
  if [ ! -f "$file" ]; then
    echo "MISSING: $name ($file not committed)"
    fail=1
    return
  fi
  # snapshot the committed file, regenerate over it, diff, restore
  local committed="$TMP/$(basename "$file").committed"
  cp "$file" "$committed"
  if ! python3 "$gen" >/dev/null 2>&1; then
    echo "FAIL: $name generator crashed"
    cp "$committed" "$file"
    fail=1
    return
  fi
  if ! diff -q <(normalize "$committed") <(normalize "$file") >/dev/null 2>&1; then
    echo "STALE: $name — regenerated differs from committed (run $gen and commit)"
    fail=1
  fi
  # non-mutating: a check must never leave regenerated content in the tree
  cp "$committed" "$file"
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
