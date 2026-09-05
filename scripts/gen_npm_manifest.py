#!/usr/bin/env python3
"""Generate packages/aero-agent-roles/manifest.json from the tree at HEAD.

The npm package (CLI + MCP server) must never hand-carry metadata: this
reuses gen_visuals.py's own frontmatter parser (roles/*/ROLE.md) and its
STANDARD_META lookup, so the package's data is byte-derived from the same
single source of truth as README.md and STANDARDS.md — never a second,
divergent copy.

Usage: gen_npm_manifest.py [--check]
  --check  regenerate in memory and fail (exit 1) if the committed
            manifest differs — wired into `make visuals-check`.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_visuals as gv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "packages" / "aero-agent-roles" / "manifest.json"


def build():
    m = gv.collect_metrics()
    roles = []
    for r in sorted(m["per_role"], key=lambda r: r["slug"]):
        roles.append({
            "slug": r["slug"],
            "title": r["title"],
            "domain": r["domain"],
            "deliverable_type": r["deliverable_type"],
            "status": r["status"],
            "standards": [rid for rid, _gated in r["standards"]],
            "skills_bound": r["skills_bound"],
            "tests": r["tests"],
        })
    standards = []
    for sid in sorted(m["per_standard"]):
        entry = m["per_standard"][sid]
        name, publisher = gv.STANDARD_META.get(sid, (sid, "unknown"))
        standards.append({
            "id": sid, "name": name, "publisher": publisher,
            "gated": entry["gated"], "roles": sorted(entry["roles"]),
        })
    manifest = {
        "schema": "aero-agent-roles/manifest@1",
        "counts": {
            "roles": m["roles"], "domains": m["domains"],
            "skills_bound": m["skills_bound"], "tests": m["tests"],
            "standards": m["standards"],
        },
        "roles": roles,
        "standards": standards,
    }
    return json.dumps(manifest, indent=1, ensure_ascii=False) + "\n"


def main():
    text = build()
    if "--check" in sys.argv[1:]:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print(f"FAIL manifest-check: {OUT.relative_to(ROOT)} is stale — run `make visuals`", file=sys.stderr)
            return 1
        print(f"PASS manifest-check: {OUT.relative_to(ROOT)} regenerates to zero diff")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f'wrote {OUT.relative_to(ROOT)} ({len(json.loads(text)["roles"])} roles, '
          f'{len(json.loads(text)["standards"])} standards)')
    return 0


if __name__ == "__main__":
    sys.exit(main())
