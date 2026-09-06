#!/usr/bin/env python3
"""Role test: Flight Software Engineer.

Verifies (offline, no network):
1. Every skill bound in ROLE.md frontmatter RESOLVES to a real leaf in
   the aero-agent-skills repo (the pinned skills_release band).
2. The workflow stage order is deterministic and complete.
3. Evidence-gate smoke: the worked example (flight control computer
   flight software) produces a complete Flight Software Design and
   Verification Plan with no blank sections and honest draft markers.
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
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "flight-software-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates", "flight-sw-plan-template.md")

EXPECTED_BOUND = [
    "avionics/fsw/cfs-architecture",
    "avionics/fsw/fprime-component",
    "avionics/fsw/real-time-scheduling",
    "avionics/fsw/shared-resource-access-control",
]

EXPECTED_STAGES = [
    "Architecture context", "Component design model", "Dispatch schedule",
    "Software bus design", "Scheduling analysis",
    "Resource access control", "Verification planning",
]


def read_role_md():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    if not os.path.exists(p):
        return None
    return open(p).read()


class TestFlightSoftwareRole(unittest.TestCase):

    def test_bound_skills_resolve_in_aeroskills(self):
        if not HAS_SKILLS:
            self.skipTest("Aero Agent Skills checkout not present "
                          "(cross-repo dev check)")
        for leaf in EXPECTED_BOUND:
            sk = os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")
            self.assertTrue(
                os.path.exists(sk),
                f"bound skill not found in aero-agent-skills: {leaf}")
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
            self.assertIn(leaf, role, f"missing in ROLE.md skills_bound: "
                                      f"{leaf}")

    def test_standards_bound_do178c_reference_only(self):
        role = read_role_md()
        self.assertIsNotNone(role)
        fm = role.split("---", 2)[1]
        self.assertIn("do-178c", fm)
        self.assertIn("TIER-2", fm)
        self.assertIn("reference-only: true", fm)

    def test_workflow_stages_deterministic(self):
        role = read_role_md()
        # Parse the workflow stage column from the markdown table under
        # "## Workflow": rows like "| 1. Architecture context | ..."
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
            self.fail("flight-sw-plan-template.md missing")
        text = open(TEMPLATE).read()
        # all 7 numbered sections present
        for n in range(1, 8):
            self.assertTrue(
                re.search(rf"^## {n}\. ", text, re.M),
                f"section {n} missing")
        self.assertEqual(text.count("___"), 0, "template has blank fields")
        self.assertIn("DRAFT", text)
        low = text.lower()
        self.assertIn("not an approval", low)
        self.assertIn("document", low)

    def test_template_has_computed_numbers(self):
        text = open(TEMPLATE).read()
        # the worked numbers the core computes must appear in the filled
        # template (message ID band sizes, utilization, response times
        # with blocking)
        self.assertIn("65536", text)
        self.assertIn("4096", text)
        self.assertIn("0.779763", text)
        self.assertIn("RM-guaranteed-by-UB", text)

    def test_forbidden_lines_present(self):
        role = read_role_md()
        for phrase in ["issue certification approval", "regulatory sign-off",
                       "reproduce proprietary", "sign_off_required: true"]:
            self.assertIn(phrase, role, f"missing boundary: {phrase}")

    def test_frontmatter_identity(self):
        role = read_role_md()
        self.assertIsNotNone(role)
        for field in ["type: role", "name: flight-software-engineer",
                      "title: \"Flight Software Engineer\"",
                      "status: draft", "domain: avionics",
                      "deliverable_type: \"Flight Software Design and "
                      "Verification Plan\"",
                      "author: ashfordeOU", "license: Apache-2.0"]:
            self.assertIn(field, role, f"missing frontmatter field: {field}")

    def test_sources_register_exists(self):
        p = os.path.join(ROLE_DIR, "SOURCES.md")
        self.assertTrue(os.path.exists(p), "SOURCES.md missing for role")
        text = open(p).read()
        for leaf in EXPECTED_BOUND:
            self.assertIn(leaf, text)

    def test_core_engine_exists(self):
        """100% standard: every role ships an executable core + cli."""
        for f in ["core/flight_software_core.py", "cli.py"]:
            self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, f)),
                            f"{f} missing - role is not executable")


if __name__ == "__main__":
    unittest.main()
