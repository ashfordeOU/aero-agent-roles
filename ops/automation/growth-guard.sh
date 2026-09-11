#!/usr/bin/env bash
# growth-guard.sh — fail-closed gate: this repo's committed generated stats
# must be current at the moment of a push.
#
# WHY (VEDA-0053, 2026-09-11): docs/COVERAGE-MATRIX.md and the generated
# visuals (README.md, docs/metrics.json, docs/statline-*.svg/.png,
# docs/gates-*.svg/.png) are committed outputs that rot SILENTLY whenever the
# AeroSkills leaf count moves. Measured twice in nine hours: 796 -> 974 leaves
# left the committed matrix understating the unbound gap by 178 leaves, and
# nothing on this repo's push path regenerates them. This guard is that
# missing gate. Policy is not prose: the check blocks the push.
#
# Usage: bash ops/automation/growth-guard.sh [repo_root]
#   [repo_root] defaults to this script's repo; the override lets the test run
#   the guard against a throwaway worktree without touching the live tree.
set -euo pipefail

ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$ROOT"

HEAD="$(git rev-parse --short HEAD 2>/dev/null || echo 'no-git')"

check() {
  local label="$1" fix="$2"
  shift 2
  local out
  if ! out="$("$@" 2>&1)"; then
    echo "FAIL growth-guard: $label is red at $HEAD" >&2
    echo "$out" >&2
    echo "  fix: $fix" >&2
    echo "  then commit the regenerated files and push again." >&2
    exit 1
  fi
}

check "make growth (coverage matrix + stale stats)" \
      "python3 scripts/coverage-matrix.py && make growth" \
      make growth

check "make visuals-check (generated docs/README stats)" \
      "python3 scripts/gen_visuals.py && make visuals-check" \
      make visuals-check

echo "PASS growth-guard: coverage matrix + generated visuals are current at $HEAD"
exit 0
