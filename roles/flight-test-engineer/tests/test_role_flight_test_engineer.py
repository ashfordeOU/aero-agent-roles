#!/usr/bin/env python3
"""Role test: flight-test-engineer."""
import os
import re
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "flight-test-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates", "flight-test-template.md")

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
