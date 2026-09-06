#!/usr/bin/env python3
"""Role test: Systems Integration Engineer.

Verifies (offline, no network):
1. Every skill bound in ROLE.md frontmatter RESOLVES to a real leaf in
   the aero-agent-skills repo (the pinned skills_release band).
2. The workflow stage order is deterministic and complete.
3. The filled deliverable template (worked example) has zero blanks,
   numbered sections, and the honest DRAFT / not-an-approval markers;
   the template IS the core's example render.
4. The role carries the executable core + cli (100% standard) and the
   boundary/forbidden lines, and metadata credits the author.
"""
import os
import re
import subprocess
import sys
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))          # repo root
sys.path.insert(0, os.path.join(ROLES_REPO, "roles",
                                "systems-integration-engineer", "core"))
import systems_integration_core as core  # noqa: E402
# Deterministic across midnight: pin fresh renders to the date the
# committed template carries (CI override wins).
os.environ.setdefault("ROLE_GEN_DATE", "2026-09-06")
AEROSKILLS = os.environ.get("AEROSKILLS_DEV",
                            os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles",
                        "systems-integration-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates", "sdai-plan-template.md")

EXPECTED_BOUND = [
    "systems-engineering-safety/arp4754a/systems-planning",
    "systems-engineering-safety/arp4754a/development-assurance-levels",
    "systems-engineering-safety/arp4754a/requirements-allocation",
    "systems-engineering-safety/arp4754a/requirements-traceability",
    "systems-engineering-safety/arp4754a/derived-requirements",
    "systems-engineering-safety/arp4754a/validation",
    "systems-engineering-safety/arp4754a/verification-planning",
    "systems-engineering-safety/arp4754a/configuration-management",
]

EXPECTED_STAGES = [
    "1. Planning & cert basis", "2. Assurance assignment",
    "3. Requirements allocation", "4. Requirements traceability",
    "5. Derived requirements", "6. Validation",
    "7. Integration verification", "8. Configuration management",
    "9. Plan + gates",
]


def read_role_md():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    if not os.path.exists(p):
        return None
    return open(p).read()


class TestSystemsIntegrationRole(unittest.TestCase):

    def test_bound_skills_resolve_in_aeroskills(self):
        if not HAS_SKILLS:
            self.skipTest("Aero Agent Skills checkout not present "
                          "(cross-repo dev check)")
        for leaf in EXPECTED_BOUND:
            sk = os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")
            self.assertTrue(
                os.path.exists(sk),
                "bound skill not found in aero-agent-skills: %s" % leaf)
            # every bound leaf ships logic (dispatch cross-check source)
            logic = os.path.join(AEROSKILLS, "skills", leaf, "scripts")
            self.assertTrue(
                os.path.isdir(logic),
                "bound leaf has no scripts/ logic dir: %s" % leaf)

    def test_bound_skills_listed_in_frontmatter(self):
        role = read_role_md()
        self.assertIsNotNone(role)
        for leaf in EXPECTED_BOUND:
            self.assertIn(leaf, role,
                          "missing in ROLE.md skills_bound: %s" % leaf)

    def test_workflow_stages_deterministic(self):
        role = read_role_md()
        idx = [role.find(stage) for stage in EXPECTED_STAGES]
        self.assertTrue(all(i >= 0 for i in idx), "a stage is missing")
        self.assertEqual(idx, sorted(idx),
                         "stage order not deterministic")

    def test_deliverable_template_complete(self):
        if not os.path.exists(TEMPLATE):
            self.fail("sdai-plan-template.md missing")
        text = open(TEMPLATE).read()
        self.assertNotIn("___", text, "template has blank fields")
        # numbered sections 1..12 present
        for n in range(1, 13):
            self.assertTrue(
                re.search(r"^## %d\. " % n, text, re.M),
                "section %d missing" % n)
        self.assertIn("System Development Assurance and Integration "
                      "Plan (ARP4754A)", text)
        low = text.lower()
        self.assertIn("draft", low)
        self.assertIn("not an approval", low)

    def test_template_is_the_worked_example(self):
        """The filled template matches the core's example render."""
        template = open(TEMPLATE).read().strip()
        rendered = core.example_report_markdown().strip()
        self.assertEqual(template, rendered)

    def test_forbidden_lines_present(self):
        role = read_role_md()
        for phrase in ["issue certification approval",
                       "regulatory sign-off", "reproduce proprietary",
                       "sign_off_required: true",
                       "without the system-safety severity evidence"]:
            self.assertIn(phrase, role, "missing boundary: %s" % phrase)

    def test_author_ashfordeou(self):
        role = read_role_md()
        self.assertIn("ashfordeOU", role)

    def test_sources_register_exists(self):
        p = os.path.join(ROLE_DIR, "SOURCES.md")
        self.assertTrue(os.path.exists(p), "SOURCES.md missing for role")

    def test_core_engine_exists(self):
        """100% standard: every role ships an executable core + cli."""
        for f in ["core", "cli.py"]:
            self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, f)),
                            "%s missing - role is not executable" % f)
        core_files = [f for f in os.listdir(os.path.join(ROLE_DIR, "core"))
                      if f.endswith("_core.py")]
        self.assertEqual(len(core_files), 1)

    def test_standalone_cli_smoke(self):
        """cli.py build must run with no AeroSkills checkout."""
        env = dict(os.environ)
        env["AEROSKILLS_DEV"] = "/nonexistent"
        env.setdefault("ROLE_GEN_DATE", "2026-09-06")
        out = os.path.join(ROLE_DIR, "tests", ".smoke-plan.md")
        try:
            r = subprocess.run(
                [sys.executable, os.path.join(ROLE_DIR, "cli.py"),
                 "build", "--out", out],
                capture_output=True, text=True, env=env, cwd=ROLE_DIR)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            md = open(out).read()
            self.assertIn("System Development Assurance and Integration "
                          "Plan (ARP4754A)", md)
            self.assertIn("not an approval", md.lower())
        finally:
            if os.path.exists(out):
                os.remove(out)


if __name__ == "__main__":
    unittest.main()
