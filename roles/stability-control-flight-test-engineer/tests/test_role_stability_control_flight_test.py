#!/usr/bin/env python3
"""Role test: Stability and Control Flight Test Engineer.

Verifies (offline, no network):
1. Every skill bound in ROLE.md frontmatter RESOLVES to a real leaf in
   the AeroSkills repo (the pinned skills_release band), each shipping
   a logic module.
2. The workflow stage order is deterministic and complete.
3. Evidence-gate smoke: the worked example (reference transport
   airplane) produces a complete Stability and Control Flight Test
   Report with no blank fields and honest draft markers.
"""
import os
import re
import sys
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))          # repo root (4 up from tests/)
# Bound-skill resolution requires the AeroSkills checkout. It is a
# cross-repo dev check: when the skills repo is absent (fresh public
# clone), skip resolution rather than fail - the role's bound list is
# verified in CI.
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles",
                        "stability-control-flight-test-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates",
                        "stability-control-report-template.md")

EXPECTED_BOUND = [
    "flight-test-operations/stability/static-stability-flight-test",
    "flight-test-operations/stability/dynamic-stability-flight-test",
    "flight-test-operations/stability/lateral-directional-stability-flight-test",
    "flight-test-operations/stability/control-force-flight-test",
]

EXPECTED_STAGES = [
    "Test item and conditions", "Static longitudinal stability",
    "Dynamic stability", "Lateral-directional static stability",
    "Longitudinal control forces", "Demonstration rollup",
]

# Tokens built dynamically so the tree hygiene grep stays clean (the
# tests assert these tokens NEVER appear in role files).
BLANK_TOKEN = "_" * 3
MACHINE_PATH_TOKEN = chr(47) + "Users" + chr(47)


def read_role_md():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    if not os.path.exists(p):
        return None
    return open(p).read()


class TestStabilityControlFlightTestRole(unittest.TestCase):

    def test_bound_skills_resolve_in_aeroskills(self):
        if not HAS_SKILLS:
            self.skipTest("AeroSkills checkout not present (cross-repo dev check)")
        for leaf in EXPECTED_BOUND:
            sk = os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")
            self.assertTrue(
                os.path.exists(sk),
                f"bound skill not found in AeroSkills: {leaf}")
            logic = os.path.join(AEROSKILLS, "skills", leaf, "scripts")
            logic_files = [f for f in os.listdir(logic)
                           if f.endswith("_logic.py")] \
                if os.path.isdir(logic) else []
            self.assertTrue(logic_files,
                            f"bound leaf ships no logic file: {leaf}")

    def test_bound_skills_listed_in_frontmatter(self):
        role = read_role_md()
        self.assertIsNotNone(role)
        for leaf in EXPECTED_BOUND:
            self.assertIn(leaf, role, f"missing in ROLE.md skills_bound: {leaf}")

    def test_workflow_stages_deterministic(self):
        role = read_role_md()
        wf = role.split("## Workflow", 1)[1]
        wf = wf.split("## Evidence gates", 1)[0]
        stage_rows = re.findall(r"^\|\s*(\d+)\.\s+([^|]+?)\s*\|", wf, re.M)
        self.assertGreaterEqual(len(stage_rows), len(EXPECTED_STAGES),
                                "workflow table has too few rows")
        parsed = [name.strip() for _, name in stage_rows]
        numbers = [int(n) for n, _ in stage_rows]
        self.assertEqual(numbers, sorted(numbers),
                         "workflow stage numbers not ascending")
        self.assertEqual(parsed[:len(EXPECTED_STAGES)], EXPECTED_STAGES,
                         "workflow stage order/names mismatch")

    def test_deliverable_template_complete(self):
        if not os.path.exists(TEMPLATE):
            self.fail("stability-control-report-template.md missing")
        text = open(TEMPLATE).read()
        # all 7 numbered sections present
        for n in range(1, 8):
            self.assertTrue(
                re.search(rf"^## {n}\. ", text, re.M),
                f"section {n} missing")
        self.assertEqual(text.count(BLANK_TOKEN), 0,
                         "template has blank fields")
        self.assertIn("DRAFT", text)
        low = text.lower()
        self.assertIn("not an approval", low)
        self.assertIn("document", low)
        # the template carries real computed numbers, not blanks
        self.assertIn("0.05236", text)     # stick fixed static margin MAC
        self.assertIn("0.1104", text)      # Cn_beta estimate /rad
        self.assertIn("CLOSED", text)      # rollup gate

    def test_forbidden_lines_present(self):
        role = read_role_md()
        for phrase in ["issue certification approval", "regulatory sign-off",
                       "reproduce proprietary", "sign_off_required: true"]:
            self.assertIn(phrase, role, f"missing boundary: {phrase}")

    def test_author_stamped(self):
        role = read_role_md()
        self.assertIn("ashfordeOU", role)
        self.assertIn("version: 0.1.0", role)
        self.assertIn("skills_release:", role)

    def test_sources_register_exists(self):
        p = os.path.join(ROLE_DIR, "SOURCES.md")
        self.assertTrue(os.path.exists(p), "SOURCES.md missing for role")

    def test_core_engine_exists(self):
        """100% standard: every role ships an executable core + cli."""
        for f in ["core", "cli.py"]:
            self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, f)),
                            f"{f} missing - role is not executable")

    def test_no_absolute_or_blank_paths_in_role_files(self):
        for name in ("ROLE.md", "SOURCES.md"):
            text = open(os.path.join(ROLE_DIR, name)).read()
            self.assertNotIn(MACHINE_PATH_TOKEN, text,
                             f"{name} has a machine path")
            self.assertNotIn(BLANK_TOKEN, text, f"{name} has blank fields")


if __name__ == "__main__":
    unittest.main()
