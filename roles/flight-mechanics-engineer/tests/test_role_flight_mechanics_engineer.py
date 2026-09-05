#!/usr/bin/env python3
"""Role test: flight-mechanics-engineer."""
import os
import re
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "flight-mechanics-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates", "perf-sc-report-template.md")

EXPECTED_BOUND = [
    "flight-mechanics/performance/breguet-range",
    "flight-mechanics/performance/breguet-endurance",
    "flight-mechanics/performance/specific-range",
    "flight-mechanics/performance/climb-performance",
    "flight-mechanics/performance/descent-performance",
    "flight-mechanics/performance/glide-performance",
    "flight-mechanics/performance/takeoff-performance",
    "flight-mechanics/performance/landing-performance",
    "flight-mechanics/performance/turn-performance",
    "flight-mechanics/performance/thrust-required",
    "flight-mechanics/performance/oei-climb-gradient",
    "flight-mechanics/performance/energy-height",
    "flight-mechanics/performance/speed-stability",
    "flight-mechanics/performance/wind-effects",
    "flight-mechanics/performance/windshear-analysis",
    "flight-mechanics/performance/rotorcraft-hover-performance",
    "flight-mechanics/performance/rotorcraft-forward-flight-performance",
    "flight-mechanics/performance/rotorcraft-blade-element-hover-performance",
    "flight-mechanics/performance/rotorcraft-autorotative-descent",
    "flight-mechanics/performance/rotorcraft-tail-rotor-sizing",
    "flight-mechanics/performance/rotorcraft-vertical-climb-performance",
    "flight-mechanics/stability-control/longitudinal-stability",
    "flight-mechanics/stability-control/lateral-directional-stability",
    "flight-mechanics/stability-control/dynamic-stability",
    "flight-mechanics/stability-control/short-period-mode-analysis",
    "flight-mechanics/stability-control/phugoid-mode-analysis",
    "flight-mechanics/stability-control/trim-analysis",
    "flight-mechanics/stability-control/stability-derivatives-avl",
    "flight-mechanics/stability-control/control-surface-effectiveness",
    "flight-mechanics/stability-control/aileron-reversal",
    "flight-mechanics/stability-control/deep-stall-analysis",
    "flight-mechanics/stability-control/spin-recovery",
    "flight-mechanics/handling-qualities/cooper-harper-rating",
    "flight-mechanics/handling-qualities/mil-std-1797a",
    "flight-mechanics/handling-qualities/pilot-induced-oscillation",
    "flight-mechanics/handling-qualities/pitch-bandwidth-criteria",
    "flight-mechanics/flight-dynamics-sim/point-mass-trajectory",
    "flight-mechanics/flight-dynamics-sim/six-dof-simulation"
]

STAGES = [
    "1. Range/endurance",
          "2. Mission performance",
          "3. Safety performance",
          "4. Rotorcraft performance",
          "5. Static stability",
          "6. Dynamic stability",
          "7. Control effectiveness",
          "8. Handling qualities",
          "9. Simulation",
          "10. Report"
]


def role_text():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return f.read()


class TestFlightMechanicsEngineerRole(unittest.TestCase):

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

    def test_template_is_filled_deliverable(self):
        """100% standard: the template IS a complete worked example report
        (zero blank ___, all sections, gate markers)."""
        with open(TEMPLATE) as f:
            text = f.read()
        self.assertNotIn("___", text)
        for n in range(1, 10):
            self.assertTrue(
                re.search(rf"^## {n}\. ", text, re.M),
                f"report section {n} missing")
        low = text.lower()
        self.assertIn("draft", low)
        self.assertIn("not an approval", low)
        self.assertIn("aeroline at-78", low)
        # key computed numbers present (range, ROC, static margin, damping)
        self.assertRegex(text, r"\d[\d,]*\s*km")
        self.assertRegex(text, r"static margin[^\n]*\d+\.\d+%")
        self.assertRegex(text, r"zeta\s*=\s*\d+\.\d+")

    def test_core_engine_exists(self):
        """100% standard: every role ships an executable core + cli."""
        for f in ["core", "cli.py"]:
            self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, f)),
                            f"{f} missing - role is not executable")

    def test_core_test_file_exists(self):
        core_test = os.path.join(ROLE_DIR, "tests",
                                 "test_flight_mechanics_core.py")
        self.assertTrue(os.path.exists(core_test),
                        "core test file missing")

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
