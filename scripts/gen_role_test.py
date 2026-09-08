#!/usr/bin/env python3
"""Generate a role test file from a role dir (consistent pattern).

Usage: python3 scripts/gen_role_test.py <role-slug> <expected-bound...>
Reads ROLE.md, extracts workflow stages from the table, and writes a
standard test: bound skills resolve (skip w/o skills), stages ordered
within Workflow, template complete, boundaries, SOURCES present.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    slug = sys.argv[1]
    role_dir = os.path.join(ROOT, "roles", slug)
    role_md = os.path.join(role_dir, "ROLE.md")
    if not os.path.exists(role_md):
        print(f"missing {role_md}"); return 1
    text = open(role_md).read()
    # extract stage names from workflow table first column
    wf = re.search(r"\| Stage.*?\n\|[-|\s]*?\n((?:\|.*\n)+)", text, re.S)
    stages = []
    if wf:
        for line in wf.group(1).splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 2 and cells[0] not in ("", "Stage"):
                stages.append(cells[0])
    if not stages:
        print(f"no workflow stages found for {slug}"); return 1
    # bound skills from frontmatter block
    fm = re.match(r"^---\n(.*?)\n---", text, re.S)
    bound = []
    if fm:
        m = re.search(r"^skills_bound:\s*\n(.*?)(?=^[a-z_]+:|^---)", fm.group(1), re.M | re.S)
        if m:
            bound = re.findall(r"^\s+-\s+([a-z0-9\-/]+)$", m.group(1), re.M)
    templates = [f for f in os.listdir(os.path.join(role_dir, "templates"))
                 if f.endswith(".md")] if os.path.isdir(os.path.join(role_dir, "templates")) else []
    template_var = templates[0].replace(".md", "").replace("-", "_") if templates else "template"
    bound_lit = ",\n    ".join(f'"{b}"' for b in bound)
    stages_lit = ",\n          ".join(f'"{s}"' for s in stages)
    tmpl = os.path.join(role_dir, "templates", templates[0]).replace(ROOT + "/", "")
    out = f'''#!/usr/bin/env python3
"""Role test: {slug}."""
import os
import re
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/company-ops/aero-agent-skills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "{slug}")
TEMPLATE = os.path.join(ROLE_DIR, "templates", "{templates[0]}")

EXPECTED_BOUND = [
    {bound_lit}
]

STAGES = [
    {stages_lit}
]


def role_text():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    return open(p).read() if os.path.exists(p) else None


class Test{slug.replace("-", "_").title().replace("_", "")}Role(unittest.TestCase):

    def test_bound_skills_resolve(self):
        if not HAS_SKILLS:
            self.skipTest("skills checkout absent (cross-repo dev check)")
        for leaf in EXPECTED_BOUND:
            self.assertTrue(
                os.path.exists(os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")),
                f"bound skill missing: {{leaf}}")

    def test_stages_ordered(self):
        role = role_text()
        self.assertIsNotNone(role)
        wf = role[role.find("## Workflow"):role.find("## Evidence gates")]
        idx = [wf.find(s) for s in STAGES]
        self.assertTrue(all(i >= 0 for i in idx), "stage missing in workflow")
        self.assertEqual(idx, sorted(idx), "stage order not deterministic")

    def test_template_present(self):
        self.assertTrue(os.path.exists(TEMPLATE), "deliverable template missing")

    def test_boundaries(self):
        role = role_text()
        self.assertIsNotNone(role)
        for phrase in ["sign_off_required: true", "forbidden"]:
            self.assertIn(phrase, role)

    def test_sources(self):
        self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, "SOURCES.md")),
                        "SOURCES.md missing")


if __name__ == "__main__":
    unittest.main()
'''
    test_name = slug.replace("-", "_")
    test_path = os.path.join(role_dir, "tests", f"test_role_{test_name}.py")
    os.makedirs(os.path.join(role_dir, "tests"), exist_ok=True)
    open(test_path, "w").write(out)
    print(f"wrote {test_path} ({len(out)} bytes, {len(stages)} stages, {len(bound)} bound)")


if __name__ == "__main__":
    sys.exit(main())
