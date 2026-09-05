#!/usr/bin/env python3
"""update-role-ratings.py — regenerate eval/role-ratings.md from the live
tree (mirror of AeroSkills ops/automation/update-skill-ratings.py).

Rating rule (mechanical, evidence-based — no hand-typing):
  baseline 10.0
  - 1.0 if core tests do not all pass
  - 0.5 if a blank template field is found (deliverable not filled)
  - 0.3 if audit-100 fails the role
  - 0.2 if the role has no dispatchable bound logic (skills growth)
  keeps existing CEO rating floor: never below 7.0 for a passing role

Run: python3 scripts/update-role-ratings.py
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "eval", "role-ratings.md")


def count_blank_fields(role_dir: str) -> int:
    """Count unfilled template markers (TODO/___/blank brackets)."""
    blanks = 0
    for t in glob.glob(os.path.join(role_dir, "templates", "*.md")):
        text = open(t).read()
        blanks += len(re.findall(r"(TODO|_+[A-Z][A-Z0-9_]*_+|TBD)", text))
    return blanks


def core_tests_pass(slug: str) -> bool:
    tests = glob.glob(os.path.join(ROOT, "roles", slug, "tests",
                                   "test_*_core.py"))
    for t in tests:
        r = subprocess.run([sys.executable, t], capture_output=True,
                           cwd=ROOT)
        if r.returncode != 0:
            return False
    return True


def role_pass_audit100(slug: str) -> bool:
    """The role appears in audit-100 as pass (cheap: run its own cli build)."""
    cli = os.path.join(ROOT, "roles", slug, "cli.py")
    r = subprocess.run([sys.executable, cli, "build", "--out",
                        "/tmp/role_rating_check.md"], capture_output=True,
                       cwd=ROOT)
    return r.returncode == 0


def main() -> int:
    rows = []
    for role_md in sorted(glob.glob(os.path.join(ROOT, "roles", "*", "ROLE.md"))):
        slug = os.path.basename(os.path.dirname(role_md))
        role_dir = os.path.dirname(role_md)
        title = ""
        text = open(role_md).read()
        m = re.search(r"^title:\s*(.+)$", text, re.M)
        if m:
            title = m.group(1).strip().strip('"')

        score = 10.0
        reasons = []
        if not core_tests_pass(slug):
            score -= 1.0
            reasons.append("core tests failing")
        blanks = count_blank_fields(role_dir)
        if blanks:
            score -= 0.5
            reasons.append(f"{blanks} blank template field(s)")
        if not role_pass_audit100(slug):
            score -= 0.3
            reasons.append("audit-100 build failing")
        # dispatchable logic present?
        bound = []
        fm = text.split("---", 2)[1] if text.startswith("---") else ""
        in_block = False
        for line in fm.splitlines():
            if line.strip().startswith("skills_bound:"):
                in_block = True
                continue
            if in_block:
                if re.match(r"^\s+-\s+", line):
                    bound.append(line.strip().lstrip("- ").strip())
                elif line.strip() and not line.startswith(" "):
                    break
        if not bound:
            score -= 0.2
            reasons.append("no bound skills")

        score = max(7.0, min(10.0, score))
        rows.append({
            "slug": slug, "title": title, "score": round(score, 1),
            "reasons": reasons or ["all checks pass"],
        })

    rows.sort(key=lambda r: -r["score"])
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "---",
        "type: eval",
        "title: Role ratings (evidence-based)",
        "status: generated",
        "updated: " + now.split()[0],
        "tags: [aero, roles, ratings, eval]",
        "pipeline: generated",
        "---",
        "",
        "# Role ratings",
        "",
        f"Audit: CEO, Ashforde OÜ - regenerated {now} · mechanical "
        "evidence only (tests, blanks, audit-100, bound skills).",
        "",
        "| Role | Rating | Evidence |",
        "|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['slug']} | {r['score']:.1f} | "
                     f"{'; '.join(r['reasons'])} |")
    lines.append("")

    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    open(LEDGER, "w").write("\n".join(lines))
    print(f"wrote {LEDGER} ({len(rows)} roles)")
    for r in rows:
        print(f"  {r['score']:.1f}  {r['slug']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
