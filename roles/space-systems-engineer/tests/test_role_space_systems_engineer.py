#!/usr/bin/env python3
"""Role test: space-systems-engineer."""
import os
import re
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "space-systems-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates", "space-systems-template.md")

EXPECTED_BOUND = [
    "space-systems/mission-design/mission-delta-v-budget",
    "space-systems/mission-design/launch-window-analysis",
    "space-systems/mission-design/c3-departure-energy",
    "space-systems/mission-design/entry-descent-landing",
    "space-systems/mission-design/radiation-debris",
    "space-systems/orbit-mechanics/keplerian-elements",
    "space-systems/orbit-mechanics/kepler-orbit-propagation",
    "space-systems/orbit-mechanics/hohmann-transfer",
    "space-systems/orbit-mechanics/bi-elliptic-transfer",
    "space-systems/orbit-mechanics/plane-change-maneuver",
    "space-systems/orbit-mechanics/lambert-transfer",
    "space-systems/orbit-mechanics/gravity-assist-swingby",
    "space-systems/orbit-mechanics/low-thrust-spiral",
    "space-systems/orbit-mechanics/orbital-perturbations",
    "space-systems/orbit-mechanics/sun-synchronous-inclination",
    "space-systems/orbit-mechanics/ground-track-repeat",
    "space-systems/orbit-mechanics/eclipse-time",
    "space-systems/orbit-mechanics/satellite-coverage",
    "space-systems/orbit-mechanics/walker-delta-constellation",
    "space-systems/orbit-mechanics/geostationary-station-keeping",
    "space-systems/orbit-mechanics/conjunction-assessment",
    "space-systems/orbit-mechanics/three-body-libration",
    "space-systems/orbit-mechanics/orbital-decay",
    "space-systems/orbit-mechanics/clohessy-wiltshire",
    "space-systems/adcs/attitude-determination-triad",
    "space-systems/adcs/attitude-determination-quest",
    "space-systems/adcs/star-tracker",
    "space-systems/adcs/sun-pointing",
    "space-systems/adcs/reaction-wheel-control",
    "space-systems/adcs/control-moment-gyro",
    "space-systems/adcs/magnetorquer-control",
    "space-systems/adcs/attitude-control-sizing",
    "space-systems/adcs/pointing-error-budget",
    "space-systems/adcs/gyro-allan-variance",
    "space-systems/subsystems/communication-link-budget",
    "space-systems/subsystems/antenna-aperture-sizing",
    "space-systems/subsystems/power-thermal-budget",
    "space-systems/subsystems/solar-array-sizing",
    "space-systems/subsystems/spacecraft-battery-sizing",
    "space-systems/subsystems/thermal-design",
    "space-systems/subsystems/propellant-tank-sizing",
    "space-systems/subsystems/command-data-handling",
    "space-systems/ecss/systems-engineering",
    "space-systems/ecss/software-engineering",
    "space-systems/ecss/software-verification"
]

STAGES = [
    "1. Mission delta-v",
          "2. Transfers",
          "3. Launch window",
          "4. Constellation/coverage",
          "5. Environment",
          "6. Rendezvous",
          "7. ADCS determination",
          "8. ADCS control",
          "9. Power/thermal",
          "10. Comms",
          "11. Propulsion/C&DH",
          "12. ECSS context",
          "13. Report"
]


def role_text():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    return open(p).read() if os.path.exists(p) else None


class TestSpaceSystemsEngineerRole(unittest.TestCase):

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
