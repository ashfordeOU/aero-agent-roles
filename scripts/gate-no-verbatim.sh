#!/usr/bin/env bash
# gate-no-verbatim.sh — roles repo copyright gate: templates/ + SOURCES.md
# must never reproduce proprietary standard text (DO-178C, AS9100, etc.).
# TIER-1 public-domain sources (FAR/CS) are quotable with citation, but
# even those keep paraphrase preferred (AeroSkills brief 06 discipline).
set -uo pipefail
cd "$(dirname "$0")/.."
fail=0

# Heuristic: flag long verbatim-looking runs of standard boilerplate.
# Real check is maintainer review before any public release.
for f in roles/*/templates/*.md roles/*/SOURCES.md; do
  [ -f "$f" ] || continue
  # flag phrases that indicate copied proprietary text
  if grep -qiE "copyright (c|©) (rtca|eurocae|sae|iaqg)|reprinted with permission" "$f"; then
    echo "FAIL: $f appears to carry proprietary text"
    fail=1
  fi
done
[ "$fail" = "0" ] && echo "no-verbatim: clean"
exit "$fail"
