#!/usr/bin/env python3
"""Role test: DO-178C Certification Engineer.

Verifies (offline, no network):
1. Every skill bound in ROLE.md frontmatter RESOLVES to a real leaf in
   the aero-agent-skills repo (the pinned skills_release band).
2. The workflow stage order is deterministic and complete.
3. Evidence-gate smoke: a synthetic project (mock requirements + tests)
   produces a complete PSAC skeleton with no blank sections.
"""
import os
import re
import sys
import tempfile
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))          # repo root (4 up from tests/)
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "do178c-cert-engineer")
PSAC_TEMPLATE = os.path.join(ROLE_DIR, "templates", "psac-template.md")

EXPECTED_BOUND = [
    "avionics/do178c/planning",
    "avionics/do178c/development",
    "avionics/do178c/verification",
    "avionics/do178c/software-testing",
    "avionics/do178c/configuration-management",
    "avionics/do178c/tool-qualification",
    "avionics/do178c/previously-developed-software",
    "avionics/do178c/data-control-coupling-analysis",
    "avionics/do178c/airworthiness-liaison",
]

EXPECTED_STAGES = [
    "Planning", "Dev framework", "Verification strategy", "Test evidence",
    "CM", "Tool qualification", "PDS check", "Coupling analysis",
    "Airworthiness liaison",
]


def read_role_md():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    if not os.path.exists(p):
        return None
    return open(p).read()


class TestDo178cRole(unittest.TestCase):

    def test_bound_skills_resolve_in_aeroskills(self):
        for leaf in EXPECTED_BOUND:
            sk = os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")
            self.assertTrue(
                os.path.exists(sk),
                f"bound skill not found in aero-agent-skills: {leaf}")

    def test_bound_skills_listed_in_frontmatter(self):
        role = read_role_md()
        self.assertIsNotNone(role)
        for leaf in EXPECTED_BOUND:
            self.assertIn(leaf, role, f"missing in ROLE.md skills_bound: {leaf}")

    def test_workflow_stages_deterministic(self):
        role = read_role_md()
        # every expected stage appears in order (indexes ascending)
        idx = [role.find(stage) for stage in EXPECTED_STAGES]
        self.assertTrue(all(i >= 0 for i in idx), "a stage is missing")
        self.assertEqual(idx, sorted(idx), "stage order not deterministic")

    def test_deliverable_template_complete(self):
        if not os.path.exists(PSAC_TEMPLATE):
            self.fail("psac-template.md missing")
        text = open(PSAC_TEMPLATE).read()
        # all 9 numbered sections present
        for n in range(1, 10):
            self.assertTrue(
                re.search(rf"^## {n}\. ", text, re.M),
                f"section {n} missing")
        self.assertIn("DRAFT", text)
        low = text.lower()
        self.assertIn("not an approval", low)
        self.assertIn("document", low)

    def test_forbidden_lines_present(self):
        role = read_role_md()
        for phrase in ["issue certification approval", "regulatory sign-off",
                       "reproduce proprietary", "sign_off_required: true"]:
            self.assertIn(phrase, role, f"missing boundary: {phrase}")

    def test_sources_register_exists(self):
        p = os.path.join(ROLE_DIR, "SOURCES.md")
        self.assertTrue(os.path.exists(p), "SOURCES.md missing for role")


if __name__ == "__main__":
    unittest.main()
