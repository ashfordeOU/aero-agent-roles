#!/usr/bin/env python3
"""suggest-role.py — REVERSE BINDING: given a skill path (or a task in
plain words), find the role(s) that bind that skill and the roles that
own the deliverable. The forward map (role -> skills_bound) lives in each
ROLE.md; this tool inverts it (skill -> roles) so an agent holding a
loaded skill can ask 'who owns the deliverable for this method?' and pull
the matching role.

Usage:
  python3 scripts/suggest-role.py <skill-path>        # e.g. avionics/do178c/planning
  python3 scripts/suggest-role.py --task "certification plan"
  python3 scripts/suggest-role.py --list-unbound      # leaves with no role yet
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

ROLES_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_ROOT = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/company-ops/aero-agent-skills"))
SKILLS_MD = os.path.join(SKILLS_ROOT, "skills")


def role_bindings() -> dict[str, list[str]]:
    """role slug -> bound leaf paths."""
    out = {}
    for role_md in sorted(glob.glob(os.path.join(ROLES_ROOT, "roles", "*", "ROLE.md"))):
        slug = os.path.basename(os.path.dirname(role_md))
        text = open(role_md).read()
        fm = text.split("---", 2)[1] if text.startswith("---") else ""
        in_block = False
        bound = []
        for line in fm.splitlines():
            if line.strip() == "skills_bound:":
                in_block = True
                continue
            if in_block:
                if re.match(r"^\S", line):
                    in_block = False
                else:
                    m = re.match(r"^\s+-\s+([a-z0-9\-/]+)", line)
                    if m:
                        bound.append(m.group(1))
        if bound:
            out[slug] = bound
    return out


def invert(bindings: dict[str, list[str]]) -> dict[str, list[str]]:
    """leaf path -> role slugs that bind it."""
    inv = {}
    for role, leaves in bindings.items():
        for leaf in leaves:
            inv.setdefault(leaf, []).append(role)
    return inv


def all_skill_paths() -> list[str]:
    if not os.path.isdir(SKILLS_MD):
        return []
    out = []
    for md in glob.glob(os.path.join(SKILLS_MD, "**", "SKILL.md"), recursive=True):
        rel = os.path.relpath(md, SKILLS_MD).replace(os.sep, "/")[:-len("/SKILL.md")]
        # only 3-level leaves (family/pack/skill); skip pack routers
        if rel.count("/") == 2:
            out.append(rel)
    return out


def task_search(bindings: dict[str, list[str]], query: str) -> list[tuple[str, str]]:
    """Rank roles by token overlap with query over slug/title/deliverable."""
    tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
    scored = []
    for role_md in sorted(glob.glob(os.path.join(ROLES_ROOT, "roles", "*", "ROLE.md"))):
        slug = os.path.basename(os.path.dirname(role_md))
        text = open(role_md).read()
        title_m = re.search(r'^title:\s*"([^"]+)"', text, re.M)
        title = title_m.group(1) if title_m else slug
        hay = set(re.findall(r"[a-z0-9]+", (slug + " " + title).lower()))
        score = sum(1 for w in tokens if w in hay)
        if score:
            scored.append((score, f"{slug}: {title}"))
    scored.sort(key=lambda x: -x[0])
    return [(s[1], str(s[0])) for s in scored[:8]]


def main() -> int:
    bindings = role_bindings()
    inv = invert(bindings)
    args = sys.argv[1:]
    if args and args[0] == "--list-unbound":
        leaves = all_skill_paths()
        unbound = [l for l in leaves if l not in inv]
        print(f"unbound leaves: {len(unbound)} / {len(leaves)}")
        for l in unbound[:40]:
            print(f"  {l}")
        return 0
    if args and args[0] == "--task":
        if len(args) < 2:
            print("usage: suggest-role.py --task <query>", file=sys.stderr)
            return 1
        for line, score in task_search(bindings, " ".join(args[1:])):
            print(line)
        return 0
    if not args:
        print(__doc__.strip())
        return 0
    raw = args[0]
    target = raw.rstrip("/")
    if target in inv:
        print(f"{target}\n  bound by roles:")
        for r in inv[target]:
            print(f"    -> roles/{r}/ROLE.md")
        return 0
    # prefix match: skill family/pack query
    hits = sorted(p for p in inv if p.startswith(target))
    if hits:
        print(f"leaves under {target} bound by roles:")
        for p in hits[:25]:
            print(f"  {p}: {', '.join(inv[p])}")
        return 0
    print(f"no role binds '{target}' — it is unbound (candidate for a future wave).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
