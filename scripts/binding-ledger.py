#!/usr/bin/env python3
"""binding-ledger.py — the roles-repo GROWTH METER.

Scans every role's ROLE.md skills_bound against the AeroSkills leaf
tree and reports coverage: how many leaves exist, how many are bound to
>=1 role, per-family coverage, and which sub-clusters are role-ready
(unbound but present in the skills tree — the next wave candidates).

Mirror of the skills leaf ledger (ops/automation in AeroSkills).

Usage:
  python3 scripts/binding-ledger.py [--json]
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

ROLES_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_ROOT = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))


def role_bindings() -> dict[str, list[str]]:
    """role slug -> bound leaf paths (from ROLE.md frontmatter skills_bound)."""
    out = {}
    for role_md in sorted(glob.glob(os.path.join(ROLES_ROOT, "roles", "*", "ROLE.md"))):
        slug = os.path.basename(os.path.dirname(role_md))
        text = open(role_md).read()
        # collect indented list items under skills_bound in frontmatter
        fm = text.split("---", 2)[1] if text.startswith("---") else ""
        in_block = False
        bound = []
        for line in fm.splitlines():
            if line.strip().startswith("skills_bound:"):
                in_block = True
                continue
            if in_block:
                if re.match(r"^\s+-\s+", line):
                    bound.append(line.strip().lstrip("- ").strip())
                elif line.strip() and not line.startswith(" "):
                    break
        out[slug] = bound
    return out


def all_leaves() -> list[str]:
    """Every AeroSkills leaf path (skills/FAMILY/sub/.../SKILL.md)."""
    leaves = []
    if not os.path.isdir(SKILLS_ROOT):
        return leaves
    for f in glob.glob(os.path.join(SKILLS_ROOT, "skills", "**", "SKILL.md"),
                       recursive=True):
        rel = f.replace(os.path.join(SKILLS_ROOT, "skills") + os.sep, "")
        parts = rel.split(os.sep)
        if len(parts) < 2:
            continue
        leaves.append("/".join(parts[:-1]))  # drop SKILL.md
    return sorted(set(leaves))


def family_of(leaf: str) -> str:
    return leaf.split("/")[0]


def main() -> int:
    bindings = role_bindings()
    roles = sorted(bindings)
    leaves = all_leaves()

    # flatten bound set
    bound_set = set()
    role_family = {}  # leaf -> roles that bind it
    for slug, bound in bindings.items():
        for b in bound:
            b = b.rstrip("/")
            bound_set.add(b)
            role_family.setdefault(b, []).append(slug)

    unbound = [l for l in leaves if l not in bound_set]

    # per-family stats
    fam_roles: dict[str, set] = {}
    fam_leaves: dict[str, int] = {}
    fam_bound: dict[str, int] = {}
    for slug, bound in bindings.items():
        # role family = from the role name we can't infer; use bound leaf
        # families (a role may bind one family mostly)
        pass
    for leaf in leaves:
        f = family_of(leaf)
        fam_leaves[f] = fam_leaves.get(f, 0) + 1
        if leaf in bound_set:
            fam_bound[f] = fam_bound.get(f, 0) + 1

    coverage = (len(bound_set) / len(leaves) * 100.0) if leaves else 0.0

    result = {
        "generated": "roles-repo binding ledger",
        "skills_root": SKILLS_ROOT,
        "roles": len(roles),
        "leaves_total": len(leaves),
        "leaves_bound": len(bound_set),
        "coverage_pct": round(coverage, 1),
        "unbound_leaves": len(unbound),
        "per_family": {
            f: {"leaves": fam_leaves.get(f, 0),
                "bound": fam_bound.get(f, 0)}
            for f in sorted(fam_leaves)
        },
        "role_ready_clusters": [
            # sub-cluster candidates = unbound leaves grouped by parent dir
            l for l in sorted(unbound)[:80]
        ],
    }
    if "--json" in sys.argv:
        print(json.dumps(result, indent=1))
    else:
        print(f"ROLES: {len(roles)}")
        print(f"AEROSKILLS LEAVES: {len(leaves)}")
        print(f"BOUND: {len(bound_set)}  ({coverage:.1f}%)  UNBOUND: {len(unbound)}")
        print("PER-FAMILY:")
        for f, st in result["per_family"].items():
            print(f"  {f}: {st['bound']}/{st['leaves']} leaves bound "
                  f"({st['bound']/st['leaves']*100:.0f}%)" if st["leaves"] else f"  {f}: 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
