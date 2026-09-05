#!/usr/bin/env python3
"""Role test: flight-test-engineer.

Verifies (offline, no network):
1. Every skill bound in ROLE.md frontmatter RESOLVES to a real leaf in
   the aero-agent-skills repo (the pinned skills_release band).
2. The workflow stage order is deterministic and complete.
3. The deliverable template is a FILLED worked example: complete
   sections, real numbers, no ___ blanks, DRAFT + not-a-clearance.
4. The executable core + cli exist and pass their own gates standalone
   (no AeroSkills checkout required).
"""
import os
import re
import sys
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "flight-test-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates", "flight-test-template.md")
CORE = os.path.join(ROLE_DIR, "core", "flight_test_core.py")
CLI = os.path.join(ROLE_DIR, "cli.py")

EXPECTED_BOUND = [
    "flight-test-operations/planning/flight-test-safety",
    "flight-test-operations/envelope/envelope-expansion",
    "flight-test-operations/envelope/v-speeds",
    "flight-test-operations/envelope/load-factor-envelope",
    "flight-test-operations/envelope/stall-characteristics-testing",
    "flight-test-operations/envelope/high-angle-of-attack-testing",
    "flight-test-operations/envelope/buffet-boundary-testing",
    "flight-test-operations/envelope/spin-testing",
    "flight-test-operations/envelope/icing-flight-test",
    "flight-test-operations/envelope/vmc-determination",
    "flight-test-operations/envelope/flight-loads-survey",
    "flight-test-operations/envelope/structural-coupling-test",
    "flight-test-operations/flutter/ground-vibration-testing",
    "flight-test-operations/flutter/flight-vibration-survey",
    "flight-test-operations/flutter/flutter-testing",
    "flight-test-operations/flutter/limit-cycle-oscillation",
    "flight-test-operations/performance/accelerate-stop-distance",
    "flight-test-operations/performance/climb-performance-flight-test",
    "flight-test-operations/performance/cruise-performance-flight-test",
    "flight-test-operations/performance/engine-failure-takeoff-flight-test",
    "flight-test-operations/performance/engine-flight-test"
]

STAGES = [
    "1. Safety planning",
    "2. Ground vibration",
    "3. Flutter build-up",
    "4. V-speeds",
    "5. Envelope expansion",
    "6. Stall/alpha",
    "7. Buffet/loads",
    "8. Spin/icing",
    "9. Structural coupling",
    "10. Performance",
    "11. Report"
]


def role_text():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    return open(p).read() if os.path.exists(p) else None


class TestFlightTestEngineerRole(unittest.TestCase):

    def test_bound_skills_resolve(self):
        if not HAS_SKILLS:
            self.skipTest("skills checkout absent (cross-repo dev check)")
        for leaf in EXPECTED_BOUND:
            self.assertTrue(
                os.path.exists(os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")),
                f"bound skill missing: {leaf}")

    def test_stages_ordered(self):
        role = role_text()
        self.assertIsNotNone(role)
        wf = role[role.find("## Workflow"):role.find("## Evidence gates")]
        idx = [wf.find(s) for s in STAGES]
        self.assertTrue(all(i >= 0 for i in idx), "stage missing in workflow")
        self.assertEqual(idx, sorted(idx), "stage order not deterministic")

    def test_how_to_run_present(self):
        role = role_text()
        self.assertIsNotNone(role)
        for phrase in ["cli.py build", "cli.py check", "flight_test_core"]:
            self.assertIn(phrase, role, f"missing run instruction: {phrase}")

    def test_executable_core_and_cli_present(self):
        self.assertTrue(os.path.exists(CORE), "core/flight_test_core.py missing")
        self.assertTrue(os.path.exists(CLI), "cli.py missing")
        # cli references the core engine
        cli = open(CLI).read()
        self.assertIn("flight_test_core", cli)

    def test_core_runs_standalone(self):
        # core must import and produce a passing model with no skills repo
        old = os.environ.get("AEROSKILLS_DEV")
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        try:
            sys.path.insert(0, os.path.join(ROLE_DIR, "core"))
            import flight_test_core as core
            model = core.build_flight_test_deliverable(core.example_aircraft())
            self.assertTrue(core.check_flight_test_deliverable(model)["all_pass"])
            md = core.render_flight_test_markdown(model)
            self.assertTrue(core.check_flight_test_markdown(md)["all_pass"])
        finally:
            if old is None:
                os.environ.pop("AEROSKILLS_DEV", None)
            else:
                os.environ["AEROSKILLS_DEV"] = old

    def test_template_complete_no_blanks(self):
        self.assertTrue(os.path.exists(TEMPLATE), "deliverable template missing")
        text = open(TEMPLATE).read()
        self.assertNotIn("___", text, "template still has blank placeholders")
        # filled deliverable sections 1..6
        for n in range(1, 7):
            self.assertTrue(re.search(rf"^## {n}\. ", text, re.M),
                            f"section {n} missing from template")
        low = text.lower()
        self.assertIn("not a clearance", low)
        self.assertIn("draft", low)
        self.assertIn("pass", low)
        self.assertIn("fail", low)
        # real numbers present (V-speeds, flutter margin, V_D)
        self.assertIn("v_d", low)
        self.assertTrue(re.search(r"\d+\.\d+", text))

    def test_boundaries(self):
        role = role_text()
        self.assertIsNotNone(role)
        low = role.lower()
        for phrase in ["sign_off_required: true", "forbidden",
                       "never clear an envelope", "not a clearance"]:
            self.assertIn(phrase, low, f"missing boundary: {phrase}")

    def test_sources(self):
        self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, "SOURCES.md")),
                        "SOURCES.md missing")


if __name__ == "__main__":
    unittest.main()
