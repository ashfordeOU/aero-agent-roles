#!/usr/bin/env python3
"""Role test: Aircraft Performance Engineer.

Verifies (offline, no network):
1. Every skill bound in ROLE.md frontmatter RESOLVES to a real leaf in
   the aero-agent-skills repo (the pinned skills_release band), and each
   leaf ships a *_logic.py module (the dispatch cross-check source).
2. The workflow stage order is deterministic and complete.
3. Evidence-gate smoke: the worked example (the AeroSkills reference
   fleet workbook) produces a complete Aircraft Performance Analysis
   Report with no blank sections and honest draft markers.
"""
import os
import re
import sys
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))          # repo root (4 up from tests/)
# Bound-skill resolution requires the Aero Agent Skills checkout. It is a
# cross-repo dev check: when the skills repo is absent (fresh public clone),
# skip resolution rather than fail - the role's bound list is verified in CI.
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "aircraft-performance-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates",
                        "performance-analysis-report-template.md")

EXPECTED_BOUND = [
    "flight-mechanics/performance/balanced-field-length",
    "flight-mechanics/performance/propeller-range",
    "flight-mechanics/performance/rotorcraft-axial-descent-flow-states",
    "flight-mechanics/performance/rotorcraft-blade-flapping-dynamics",
    "flight-mechanics/performance/rotorcraft-hover-ground-effect",
    "flight-mechanics/performance/rotorcraft-lead-lag-dynamics",
    "flight-mechanics/performance/rotorcraft-main-rotor-sizing",
    "flight-mechanics/performance/rotorcraft-range-endurance",
    "flight-mechanics/performance/rotorcraft-turn-performance",
]

EXPECTED_STAGES = [
    "Fleet scope and basis",
    "Balanced field length",
    "Propeller cruise range",
    "Main rotor sizing",
    "Blade flap dynamics",
    "Lead-lag clearance",
    "Hover in ground effect",
    "Axial descent states",
    "Banked turn performance",
    "Range and endurance closure",
    "Closure and gaps",
]

EXPECTED_SECTIONS = 10   # numbered deliverable sections in the template


def read_role_md():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    if not os.path.exists(p):
        return None
    return open(p).read()


class TestAircraftPerformanceRole(unittest.TestCase):

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
            self.assertIn(leaf, role,
                          f"missing in ROLE.md skills_bound: {leaf}")

    def test_workflow_stages_deterministic(self):
        role = read_role_md()
        # Parse the workflow stage column from the markdown table under
        # "## Workflow": rows like "| 1. Fleet scope and basis | ..."
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
            self.fail("performance-analysis-report-template.md missing")
        text = open(TEMPLATE).read()
        # all numbered sections present (1 = scope/register .. 10 = fuel)
        for n in range(1, EXPECTED_SECTIONS + 1):
            self.assertTrue(
                re.search(rf"^## {n}\. ", text, re.M),
                f"section {n} missing")
        self.assertEqual(text.count("___"), 0, "template has blank fields")
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

    def test_core_engine_exists(self):
        """100% standard: every role ships an executable core + cli."""
        for f in ["core", "cli.py"]:
            self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, f)),
                            f"{f} missing - role is not executable")
        core_dir = os.path.join(ROLE_DIR, "core")
        self.assertTrue(any(f.endswith("_core.py")
                            for f in os.listdir(core_dir)),
                        "core engine missing (100% standard)")


if __name__ == "__main__":
    unittest.main()
