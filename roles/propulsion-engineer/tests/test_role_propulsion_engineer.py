#!/usr/bin/env python3
"""Role test: propulsion-engineer."""
import os
import re
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "propulsion-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates", "propulsion-report-template.md")

EXPECTED_BOUND = [
    "propulsion/gas-turbine-cycle/gas-turbine-cycle",
    "propulsion/gas-turbine-cycle/real-cycle-effects",
    "propulsion/gas-turbine-cycle/afterburner-cycle",
    "propulsion/gas-turbine-cycle/regenerative-cycle",
    "propulsion/gas-turbine-cycle/propelling-nozzle",
    "propulsion/gas-turbine-cycle/subsonic-inlet-recovery",
    "propulsion/gas-turbine-cycle/combustor-design",
    "propulsion/turbofan/turbofan-cycle",
    "propulsion/turbofan/bypass-ratio-trade",
    "propulsion/turbofan/turbofan-off-design",
    "propulsion/turboprop/turboprop-cycle",
    "propulsion/turboprop/free-turbine",
    "propulsion/axial-compressor/axial-compressor-stage",
    "propulsion/axial-compressor/compressor-map",
    "propulsion/axial-compressor/multi-stage-compressor",
    "propulsion/axial-compressor/turbine-stage",
    "propulsion/axial-compressor/turbine-blade-cooling",
    "propulsion/engine-airframe/engine-airframe-integration",
    "propulsion/rocket/rocket-engine-cycle",
    "propulsion/rocket/nozzle-design",
    "propulsion/rocket/combustion-chamber-design",
    "propulsion/rocket/injector-design",
    "propulsion/rocket/propellant-selection",
    "propulsion/rocket/solid-rocket-motor",
    "propulsion/rocket/hybrid-rocket-motor",
    "propulsion/rocket/thrust-chamber-cooling",
    "propulsion/rocket/thrust-vector-control",
    "propulsion/rocket/cold-gas-thruster",
    "propulsion/combustion/cea-rocket-combustion",
    "propulsion/electric/hall-thruster",
    "propulsion/electric/gridded-ion-thruster",
    "propulsion/electric/electrothermal-thruster",
    "propulsion/ramjet/ramjet-cycle",
    "propulsion/ramjet/ramjet-inlet"
]

STAGES = [
    "1. Airbreathing cycle",
          "2. Bypass/regenerative/AB trades",
          "3. Off-design",
          "4. Components",
          "5. Turbine cooling",
          "6. Integration",
          "7. Rocket cycle",
          "8. Solid/hybrid",
          "9. Cooling/TVC",
          "10. Combustion",
          "11. Electric",
          "12. Ramjet",
          "13. Report"
]


def role_text():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    return open(p).read() if os.path.exists(p) else None


class TestPropulsionEngineerRole(unittest.TestCase):

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
