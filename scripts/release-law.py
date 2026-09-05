#!/usr/bin/env python3
"""release-law.py — role-count release law (v1.0 @12, v1.1 @25, v1.2 @50).

Deterministic: reads manifest.json role count, checks thresholds, and
when crossed prints the target version. Does NOT push or tag by itself
(CI/gate decides); --apply prints the tag command for the operator.

Usage:
  python3 scripts/release-law.py            # report current status
  python3 scripts/release-law.py --check    # exit 1 if a release is due
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "manifest.json")

# role-count -> version milestone (same style as the skills 100-law)
THRESHOLDS = [
    (12, "v1.0.0"),
    (25, "v1.1.0"),
    (50, "v1.2.0"),
    (75, "v1.3.0"),
    (100, "v2.0.0"),
]


def current_count() -> int:
    if not os.path.exists(MANIFEST):
        # fall back to counting role dirs
        return len([d for d in os.listdir(os.path.join(ROOT, "roles"))
                    if os.path.isdir(os.path.join(ROOT, "roles", d))])
    m = json.load(open(MANIFEST))
    return int(m.get("count", len(m.get("roles", []))))


def latest_tag() -> str:
    r = subprocess.run(["git", "-C", ROOT, "tag", "--sort=-v:refname"],
                       capture_output=True, text=True)
    tags = [t.strip() for t in r.stdout.splitlines()
            if t.strip().startswith("roles-v")]
    return tags[0] if tags else "none"


def main() -> int:
    count = current_count()
    due = [v for n, v in THRESHOLDS if count >= n]
    next_missing = [(n, v) for n, v in THRESHOLDS
                    if count >= n and v not in due]
    # the highest reached threshold is the current version
    current_v = due[-1] if due else "pre-v1.0"
    # next unreached threshold
    nxt = None
    for n, v in THRESHOLDS:
        if count < n:
            nxt = (n, v)
            break

    print(f"ROLE COUNT: {count}")
    print(f"CURRENT VERSION: {current_v}  (latest tag: {latest_tag()})")
    if nxt:
        print(f"NEXT MILESTONE: {nxt[1]} at {nxt[0]} roles "
              f"({nxt[0] - count} to go)")
    else:
        print("ALL MILESTONES REACHED")

    if "--check" in sys.argv:
        # a release is due when the count has crossed a threshold that has
        # no tag yet
        tagged = latest_tag()
        due_untagged = [v for n, v in THRESHOLDS
                        if count >= n and v != tagged
                        and not _tag_exists(v)]
        if due_untagged:
            print(f"RELEASE DUE: {due_untagged[0]}")
            return 1
        print("release-law: OK (no release due)")
        return 0
    return 0


def _tag_exists(v: str) -> bool:
    r = subprocess.run(["git", "-C", ROOT, "tag", "-l", v],
                       capture_output=True, text=True)
    return bool(r.stdout.strip())


if __name__ == "__main__":
    sys.exit(main())
