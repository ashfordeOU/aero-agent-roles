#!/usr/bin/env python3
"""Role test: gnc-engineer."""
import os
import re
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "gnc-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates", "gnc-report-template.md")

EXPECTED_BOUND = [
    "gnc-autonomy/control/pid-control-design",
    "gnc-autonomy/control/lead-lag-compensation",
    "gnc-autonomy/control/frequency-response-design",
    "gnc-autonomy/control/digital-control-design",
    "gnc-autonomy/control/observer-design",
    "gnc-autonomy/control/control-allocation",
    "gnc-autonomy/control/gain-scheduling",
    "gnc-autonomy/control/adaptive-control",
    "gnc-autonomy/navigation/navigation-frames",
    "gnc-autonomy/navigation/inertial-navigation",
    "gnc-autonomy/navigation/kalman-filter-design",
    "gnc-autonomy/navigation/gnss-pseudorange-positioning",
    "gnc-autonomy/navigation/gnss-raim-fde",
    "gnc-autonomy/navigation/dilution-of-precision",
    "gnc-autonomy/guidance/pursuit-guidance",
    "gnc-autonomy/optimal-control/lqr-design",
    "gnc-autonomy/optimal-control/model-predictive-control",
    "gnc-autonomy/optimal-control/bang-bang-control",
    "gnc-autonomy/optimal-control/dymos-trajectory",
    "gnc-autonomy/space/attitude-dynamics",
    "gnc-autonomy/space/orbit-dynamics",
    "gnc-autonomy/space/orbit-determination",
    "gnc-autonomy/space/rendezvous-phasing"
]

STAGES = [
    "1. Frames + plant",
          "2. Navigation filter",
          "3. Inner loop",
          "4. Digital implementation",
          "5. State estimation",
          "6. Allocation/scheduling",
          "7. Guidance",
          "8. Optimal control",
          "9. Space GNC",
          "10. Report"
]


def role_text():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    return open(p).read() if os.path.exists(p) else None


class TestGncEngineerRole(unittest.TestCase):

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
