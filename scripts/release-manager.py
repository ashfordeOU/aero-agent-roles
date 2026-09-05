#!/usr/bin/env python3
"""Aero Agent Roles release manager (mirror of the skills convention).

RELEASE CONVENTION (founder 2026-09-05: roles must run as cleanly as
skills — npm and releases handled the same way): every role-count
milestone = one version. v1.0.0 @ 12 roles (baseline); v1.1.0 @ 25;
v1.2.0 @ 50; v1.3.0 @ 75; v2.0.0 @ 100.

The release is a DELIBERATE action from the JUST-PUBLISHED public
mirror (numbers must match what's actually public), never from dev
HEAD. npm publish is kept out of the automatic pipeline on purpose
(same as skills).

Usage:
  --status        show current role count + which release band
  --next          next release tag + roles remaining
  --changelog     release notes body from git log since last tag
  --verify        exit 0 if the current count warrants a release and
                  the package is publishable; else exit 1
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "packages", "aero-agent-roles")

BANDS = [
    (12, "v1.0.0"),
    (25, "v1.1.0"),
    (50, "v1.2.0"),
    (75, "v1.3.0"),
    (100, "v2.0.0"),
]


def role_count() -> int:
    roles_dir = os.path.join(ROOT, "roles")
    return len([d for d in os.listdir(roles_dir)
                if os.path.isdir(os.path.join(roles_dir, d))])


def current_band(count: int) -> str:
    reached = [v for n, v in BANDS if count >= n]
    return reached[-1] if reached else "pre-v1.0"


def next_band(count: int):
    for n, v in BANDS:
        if count < n:
            return n, v
    return None, None


def last_tag() -> str:
    r = subprocess.run(["git", "-C", ROOT, "tag", "--sort=-v:refname"],
                       capture_output=True, text=True)
    tags = [t.strip() for t in r.stdout.splitlines()
            if re.match(r"^roles-v?\d", t)]
    return tags[0] if tags else "none"


def changelog() -> str:
    base = last_tag()
    if base == "none":
        r = subprocess.run(["git", "-C", ROOT, "log", "--oneline", "-30"],
                           capture_output=True, text=True)
    else:
        r = subprocess.run(["git", "-C", ROOT, "log", "--oneline",
                            f"{base}..HEAD"], capture_output=True, text=True)
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    return "\n".join(lines[:60]) or "(no commits since last tag)"


def main() -> int:
    count = role_count()
    band = current_band(count)
    nxt_n, nxt_v = next_band(count)
    mode = sys.argv[1] if len(sys.argv) > 1 else "--status"

    if mode == "--status":
        print(f"ROLE COUNT: {count}")
        print(f"CURRENT BAND: {band}  (latest tag: {last_tag()})")
        if nxt_v:
            print(f"NEXT RELEASE: {nxt_v} at {nxt_n} roles "
                  f"({nxt_n - count} to go)")
        else:
            print("ALL RELEASE BANDS REACHED")
        return 0

    if mode == "--next":
        if nxt_v and nxt_n is not None:
            print(f"roles remaining to {nxt_v}: {nxt_n - count}")
        else:
            print("no next release")
        return 0

    if mode == "--changelog":
        print(changelog())
        return 0

    if mode == "--verify":
        # release warranted when count crossed a band that has no tag yet
        tag = last_tag()
        due = [v for n, v in BANDS
               if count >= n and tag != v
               and not _tag_exists(v)]
        if not due:
            print("release-manager: no release due")
            return 1
        # package must not be private for a real publish
        pkg = json.load(open(os.path.join(PKG, "package.json")))
        if pkg.get("private"):
            print(f"release due: {due[0]} but package is private:true — "
                  "clear it before publishing (deliberate act)")
            return 1
        print(f"release ready: {due[0]}")
        return 0
    return 0


def _tag_exists(v: str) -> bool:
    r = subprocess.run(["git", "-C", ROOT, "tag", "-l", v],
                       capture_output=True, text=True)
    return bool(r.stdout.strip())


if __name__ == "__main__":
    sys.exit(main())
