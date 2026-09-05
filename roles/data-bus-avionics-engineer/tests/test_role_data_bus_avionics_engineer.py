#!/usr/bin/env python3
"""Role test: Data Bus / Avionics Network Engineer.

Verifies (offline, no network):
1. Every skill bound in ROLE.md frontmatter RESOLVES to a real leaf in
   the aero-agent-skills repo (the pinned skills_release band).
2. The workflow stage order is deterministic and complete.
3. Evidence-gate smoke: the filled template deliverable carries the
   loading numbers, conformance checks, DRAFT and not-an-approval
   markers with zero blank fields.
"""
import os
import re
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))          # repo root (4 up from tests/)
# Bound-skill resolution requires the Aero Agent Skills checkout. It is a
# cross-repo dev check: when the skills repo is absent (fresh public clone),
# skip resolution rather than fail - the role's bound list is verified in CI.
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "data-bus-avionics-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates", "bus-assessment-template.md")

EXPECTED_BOUND = [
    "avionics/data-bus/arinc429-protocol",
    "avionics/data-bus/arinc429-bus-loading",
    "avionics/data-bus/arinc664-afdx",
    "avionics/data-bus/mil-std-1553",
    "avionics/data-bus/mil-std-1553-bus-loading",
]

EXPECTED_STAGES = [
    "Architecture inventory",
    "ARINC 429 decode review",
    "ARINC 429 bus loading",
    "MIL-STD-1553 word review",
    "MIL-STD-1553 bus loading",
    "AFDX bandwidth check",
    "Conformance gate",
    "Assessment package",
]


def read_role_md():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    if not os.path.exists(p):
        return None
    return open(p).read()


class TestDataBusRole(unittest.TestCase):

    def test_bound_skills_resolve_in_aeroskills(self):
        if not HAS_SKILLS:
            self.skipTest("Aero Agent Skills checkout not present "
                          "(cross-repo dev check)")
        for leaf in EXPECTED_BOUND:
            sk = os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")
            self.assertTrue(
                os.path.exists(sk),
                f"bound skill not found in aero-agent-skills: {leaf}")
            logic_dir = os.path.join(AEROSKILLS, "skills", leaf, "scripts")
            self.assertTrue(
                any(f.endswith("_logic.py")
                    for f in os.listdir(logic_dir)),
                f"bound skill has no logic file: {leaf}")

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
        if not os.path.exists(TEMPLATE):
            self.fail("bus-assessment-template.md missing")
        text = open(TEMPLATE).read()
        # all 7 numbered sections present, zero blanks
        for n in range(1, 8):
            self.assertTrue(
                re.search(rf"^## {n}\. ", text, re.M),
                f"section {n} missing")
        self.assertNotIn("___", text)
        low = text.lower()
        for marker in ["arinc 429", "mil-std-1553", "afdx", "utilization",
                       "parity", "draft", "not an approval", "document"]:
            self.assertIn(marker, low, f"template missing marker: {marker}")

    def test_forbidden_lines_present(self):
        role = read_role_md()
        for phrase in ["issue bus architecture sign-off",
                       "network qualification approval",
                       "sign_off_required: true"]:
            self.assertIn(phrase, role, f"missing boundary: {phrase}")

    def test_sources_register_exists(self):
        p = os.path.join(ROLE_DIR, "SOURCES.md")
        self.assertTrue(os.path.exists(p), "SOURCES.md missing for role")

    def test_core_engine_exists(self):
        """100% standard: every role ships an executable core + cli."""
        for f in ["core", "cli.py"]:
            self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, f)),
                            f"{f} missing - role is not executable")

    def test_author_ashfordeou(self):
        role = read_role_md()
        self.assertIn("ashfordeOU", role, "author not set")


if __name__ == "__main__":
    unittest.main()
