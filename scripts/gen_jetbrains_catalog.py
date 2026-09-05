#!/usr/bin/env python3
"""Generate the JetBrains plugin role catalog (catalog.json).

Reads packages/aero-agent-roles/manifest.json (itself generated from the
tree at HEAD by gen_npm_manifest.py) and emits a compact JSON list for the
IDE catalog browser. The plugin bundle task copies this into the plugin
resources so the tool window works offline. Never hand-typed, same as
every other public figure in this repo.

Usage: gen_jetbrains_catalog.py [--check]
  --check  regenerate in memory and fail (exit 1) if the committed
           catalog differs — wired into `make visuals-check`.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "packages" / "aero-agent-roles" / "manifest.json"
OUT = ROOT / "packages" / "jetbrains-plugin" / "src" / "main" / "resources" / "catalog" / "catalog.json"


def build():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = [
        {
            "slug": r["slug"],
            "title": r["title"],
            "domain": r["domain"],
            "deliverable_type": r["deliverable_type"],
            "skills_bound": r["skills_bound"],
        }
        for r in m["roles"]
    ]
    return {
        "count": len(rows),
        "source": "https://github.com/ashfordeOU/aero-agent-roles",
        "roles": rows,
    }


def main() -> int:
    out = build()
    text = json.dumps(out)
    if "--check" in sys.argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else None
        if current != text:
            print("FAIL jetbrains-catalog-check: catalog.json is stale — run `make visuals`")
            return 1
        print(f"jetbrains catalog: OK ({out['count']} roles)")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT} ({out['count']} roles)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
