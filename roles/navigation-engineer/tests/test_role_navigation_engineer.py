#!/usr/bin/env python3
"""Role test: navigation-engineer."""
import os
import re
import sys
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "navigation-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates",
                        "navigation-analysis-report-template.md")
CORE_DIR = os.path.join(ROLE_DIR, "core")

sys.path.insert(0, CORE_DIR)
import navigation_engineer_core as nav  # noqa: E402

EXPECTED_BOUND = [
    "gnc-autonomy/navigation/navigation-frames",
    "gnc-autonomy/navigation/inertial-navigation",
    "gnc-autonomy/navigation/kalman-filter-design",
    "gnc-autonomy/navigation/gnss-pseudorange-positioning",
    "gnc-autonomy/navigation/gnss-raim-fde",
    "gnc-autonomy/navigation/dilution-of-precision",
    "gnc-autonomy/navigation/gnss-carrier-smoothing",
    "gnc-autonomy/navigation/gnss-doppler-velocity-positioning",
    "gnc-autonomy/navigation/gnss-rtk-positioning",
    "gnc-autonomy/navigation/ins-gnss-integrated-filter",
    "gnc-autonomy/navigation/tightly-coupled-ins-gnss",
    "gnc-autonomy/navigation/terrain-referenced-navigation",
    "gnc-autonomy/navigation/bearing-only-localization",
]

STAGES = [
    "1. Frames + geodesy",
    "2. INS coasting",
    "3. GNSS epoch fix",
    "4. Integrity",
    "5. Smoothing + Doppler",
    "6. RTK",
    "7. INS-GNSS integration",
    "8. GNSS-denied aiding",
    "9. Passive localization",
    "10. Report",
]


def role_text():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return f.read()


class TestNavigationEngineerRole(unittest.TestCase):

    def test_bound_skills_resolve(self):
        if not HAS_SKILLS:
            self.skipTest("skills checkout absent (cross-repo dev check)")
        for leaf in EXPECTED_BOUND:
            self.assertTrue(
                os.path.exists(os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")),
                f"bound skill missing: {leaf}")

    def test_seven_unbound_leaves_present(self):
        # the wave R9 coverage win: these 7 leaves must be bound
        wave_win = [
            "gnc-autonomy/navigation/bearing-only-localization",
            "gnc-autonomy/navigation/gnss-carrier-smoothing",
            "gnc-autonomy/navigation/gnss-doppler-velocity-positioning",
            "gnc-autonomy/navigation/gnss-rtk-positioning",
            "gnc-autonomy/navigation/ins-gnss-integrated-filter",
            "gnc-autonomy/navigation/terrain-referenced-navigation",
            "gnc-autonomy/navigation/tightly-coupled-ins-gnss",
        ]
        role = role_text()
        self.assertIsNotNone(role)
        for leaf in wave_win:
            self.assertIn(leaf, role, f"wave-win leaf not bound: {leaf}")

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
        """100% standard: template is the FILLED worked example - all 9
        numbered sections + appendix, zero blank fields, draft markers."""
        self.assertTrue(os.path.exists(TEMPLATE))
        with open(TEMPLATE) as f:
            text = f.read()
        for n in range(1, 10):
            self.assertTrue(
                re.search(rf"^## {n}\. ", text, re.M),
                f"report section {n} missing")
        self.assertIn("Appendix A", text)
        self.assertNotIn("___", text)
        low = text.lower()
        self.assertIn("draft", low)
        self.assertIn("not an approval", low)
        self.assertIn("not flight software release", low)
        self.assertNotIn("/users/", low)
        self.assertNotIn("/home/", low)

    def test_template_passes_core_gates(self):
        """The shipped template must pass the engine's own markdown
        evidence gates (standalone core, no skills repo needed)."""
        with open(TEMPLATE) as f:
            text = f.read()
        gates = nav.check_report_markdown(text)
        self.assertTrue(gates["all_pass"], gates)

    def test_core_and_cli_present(self):
        self.assertTrue(os.path.exists(os.path.join(CORE_DIR,
                                                    "navigation_engineer_core.py")),
                        "core/navigation_engineer_core.py missing (100% standard)")
        self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, "cli.py")),
                        "cli.py missing (100% standard)")

    def test_core_standalone_example_gates(self):
        """Core produces a correct, gate-passing report with no skills."""
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = nav.build_report(nav.example_project())
        gates = nav.check_report(model)
        self.assertTrue(gates["all_pass"], gates)
        md = nav.example_report_markdown()
        mgates = nav.check_report_markdown(md)
        self.assertTrue(mgates["all_pass"], mgates)

    def test_boundaries(self):
        role = role_text()
        self.assertIsNotNone(role)
        for phrase in ["sign_off_required: true", "forbidden"]:
            self.assertIn(phrase, role)
        for phrase in ["claim certification approval", "release flight software"]:
            self.assertIn(phrase, role)

    def test_sources(self):
        self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, "SOURCES.md")),
                        "SOURCES.md missing")


if __name__ == "__main__":
    unittest.main()
