#!/usr/bin/env python3
"""Role test: aircraft-design-engineer."""
import os
import re
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "aircraft-design-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates", "concept-design-template.md")

EXPECTED_BOUND = [
    "vehicle-design/conceptual/constraint-analysis",
    "vehicle-design/conceptual/sizing-mission-profile",
    "vehicle-design/conceptual/payload-range-diagram",
    "vehicle-design/conceptual/tow-estimation",
    "vehicle-design/conceptual/openvsp-geometry",
    "vehicle-design/sizing/ws-tw-trade",
    "vehicle-design/sizing/weight-estimation",
    "vehicle-design/sizing/engine-sizing",
    "vehicle-design/sizing/fuselage-sizing",
    "vehicle-design/sizing/wing-planform-sizing",
    "vehicle-design/sizing/tail-sizing",
    "vehicle-design/sizing/landing-gear-sizing",
    "vehicle-design/sizing/control-surface-sizing",
    "vehicle-design/sizing/fuel-tank-sizing",
    "vehicle-design/sizing/battery-sizing",
    "vehicle-design/sizing/environmental-control-sizing",
    "vehicle-design/sizing/electrical-wire-sizing",
    "vehicle-design/sizing/apu-fuel-burn-sizing",
    "vehicle-design/sizing/bleed-air-system-sizing",
    "vehicle-design/sizing/fire-protection-sizing",
    "vehicle-design/sizing/ice-protection-sizing",
    "vehicle-design/sizing/hydraulic-system-sizing",
    "vehicle-design/sizing/landing-gear-retraction-sizing",
    "vehicle-design/mass-properties/mass-budget",
    "vehicle-design/mass-properties/cg-envelope",
    "vehicle-design/mass-properties/inertia-estimation",
    "vehicle-design/mdo/design-of-experiments",
    "vehicle-design/mdo/multidisciplinary-optimization",
    "vehicle-design/mdo/surrogate-modeling",
    "vehicle-design/cost-estimation/parametric-cost",
    "vehicle-design/cost-estimation/operating-cost",
    "vehicle-design/cost-estimation/life-cycle-cost",
    "vehicle-design/structures-integration/wing-box-sizing",
    "vehicle-design/structures-integration/fuselage-skin-stringer"
]

STAGES = [
    "1. Requirements framing",
          "2. Sizing mission",
          "3. Initial layout",
          "4. W/S vs T/W trade",
          "5. Weight iteration",
          "6. Component sizing",
          "7. Subsystem sizing",
          "8. Mass + CG",
          "9. MDO exploration",
          "10. Payload-range",
          "11. Cost",
          "12. Structures check",
          "13. Package"
]


def role_text():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    return open(p).read() if os.path.exists(p) else None


class TestAircraftDesignEngineerRole(unittest.TestCase):

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
