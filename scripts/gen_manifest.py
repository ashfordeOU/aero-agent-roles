#!/usr/bin/env python3
"""gen_manifest.py — generate manifest.json from the roles tree.

Derives every entry from ROLE.md frontmatter (single source of truth).
Usage: gen_manifest.py [--check]
  --check  regenerate in memory + fail if committed manifest differs.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "manifest.json")


def fm_block(text, key):
    """Return the indented list block under frontmatter key."""
    m = re.search(rf"^{key}:\s*\n(.*?)(?=^[a-z_]+:|^---)", text, re.M | re.S)
    return m.group(1) if m else ""


def list_items(block):
    """Capture `- xxx` and `- id: xxx` list entries."""
    items = re.findall(r"^\s+-\s+id:\s*([a-z0-9\-/]+)\s*$", block, re.M)
    if not items:
        items = re.findall(r"^\s+-\s+([a-z0-9\-/]+)\s*$", block, re.M)
    return items


def load_roles():
    roles = []
    rdir = os.path.join(ROOT, "roles")
    for slug in sorted(os.listdir(rdir)):
        p = os.path.join(rdir, slug, "ROLE.md")
        if not os.path.exists(p):
            continue
        text = open(p).read()
        m = re.match(r"^---\n(.*?)\n---", text, re.S)
        fm = {}
        if m:
            for line in m.group(1).splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip().strip('"')
        roles.append({
            "slug": slug,
            "title": fm.get("title", ""),
            "domain": fm.get("domain", ""),
            "deliverable_type": fm.get("deliverable_type", ""),
            "status": fm.get("status", ""),
            "standards": list_items(fm_block(text, "standards_bound")),
            "skills_bound": len(list_items(fm_block(text, "skills_bound"))),
        })
    return roles


def main():
    roles = load_roles()
    manifest = {
        "schema_version": 1,
        "generated_from": "roles/*/ROLE.md frontmatter",
        "count": len(roles),
        "roles": roles,
    }
    text = json.dumps(manifest, indent=1)
    if "--check" in sys.argv:
        if os.path.exists(OUT) and open(OUT).read() == text:
            print(f"manifest: OK ({len(roles)} roles)")
            return 0
        print(f"manifest: STALE (tree has {len(roles)} roles, committed differs)")
        return 1
    open(OUT, "w").write(text)
    print(f"manifest: wrote {len(roles)} roles")


if __name__ == "__main__":
    sys.exit(main())
