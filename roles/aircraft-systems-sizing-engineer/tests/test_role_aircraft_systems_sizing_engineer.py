#!/usr/bin/env python3
"""Role test: Aircraft Systems Sizing Engineer.

Verifies (offline, no network):
1. Every skill bound in ROLE.md frontmatter RESOLVES to a real leaf in
   the AeroSkills repo (the pinned skills_release band).
2. The workflow stage order is deterministic and complete.
3. The role is a 100% executable worker: core engine + cli.py exist,
   and the filled deliverable template (generated worked example) has
   zero blanks and carries the gate-check vocabulary.
4. Boundaries are present in ROLE.md.
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
ROLE_DIR = os.path.join(ROLES_REPO, "roles",
                        "aircraft-systems-sizing-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates",
                        "systems-sizing-report-template.md")

EXPECTED_BOUND = [
    "vehicle-design/sizing/aircraft-electrical-load-analysis",
    "vehicle-design/sizing/air-cycle-machine-sizing",
    "vehicle-design/sizing/avionics-bay-cooling-sizing",
    "vehicle-design/sizing/aircraft-oxygen-system-sizing",
    "vehicle-design/sizing/brake-energy-sizing",
    "vehicle-design/sizing/cabin-outflow-valve-sizing",
    "vehicle-design/sizing/fuel-feed-system-sizing",
    "vehicle-design/sizing/fuel-jettison-sizing",
    "vehicle-design/sizing/fuel-tank-inerting-sizing",
    "vehicle-design/sizing/hydraulic-actuator-sizing",
    "vehicle-design/sizing/landing-gear-layout",
    "vehicle-design/sizing/ram-air-turbine-sizing",
    "vehicle-design/sizing/tire-sizing",
    "vehicle-design/sizing/window-aperture-sizing",
]

EXPECTED_STAGES = [
    "Electrical sizing", "ECS sizing", "Equipment cooling",
    "Emergency systems", "Braking + gear layout", "Cabin pressure valves",
    "Fuel systems", "Hydraulic sizing", "Cabin structure apertures",
    "Report assembly",
]


def read_role_md():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    if not os.path.exists(p):
        return None
    return open(p).read()


class TestAircraftSystemsSizingRole(unittest.TestCase):

    def test_bound_skills_resolve_in_aeroskills(self):
        if not HAS_SKILLS:
            self.skipTest("Aero Agent Skills checkout not present "
                          "(cross-repo dev check)")
        for leaf in EXPECTED_BOUND:
            sk = os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")
            self.assertTrue(os.path.exists(sk),
                            "bound skill not found in aero-agent-skills: %s"
                            % leaf)

    def test_bound_skills_listed_in_frontmatter(self):
        role = read_role_md()
        self.assertIsNotNone(role)
        for leaf in EXPECTED_BOUND:
            self.assertIn(leaf, role,
                          "missing in ROLE.md skills_bound: %s" % leaf)

    def test_bound_skills_have_logic_files(self):
        """The bound sizing leaves ship executable *_logic.py (the 100%
        standard requires the role to bind REAL leaves, not placeholders)."""
        if not HAS_SKILLS:
            self.skipTest("Aero Agent Skills checkout not present")
        for leaf in EXPECTED_BOUND:
            scripts = os.path.join(AEROSKILLS, "skills", leaf, "scripts")
            logic = [f for f in os.listdir(scripts)
                     if f.endswith("_logic.py")] \
                if os.path.isdir(scripts) else []
            self.assertTrue(logic,
                            "bound leaf has no logic file: %s" % leaf)

    def test_workflow_stages_deterministic(self):
        role = read_role_md()
        idx = [role.find(stage) for stage in EXPECTED_STAGES]
        self.assertTrue(all(i >= 0 for i in idx), "a stage is missing")
        self.assertEqual(idx, sorted(idx),
                         "stage order not deterministic")

    def test_deliverable_template_complete(self):
        if not os.path.exists(TEMPLATE):
            self.fail("systems-sizing-report-template.md missing")
        text = open(TEMPLATE).read()
        self.assertNotIn("___", text, "template has unfilled blanks")
        for n in range(1, 15):
            self.assertTrue(re.search(r"^## %d\. " % n, text, re.M),
                            "section %d missing" % n)
        low = text.lower()
        self.assertIn("draft", low)
        self.assertIn("not an approval", low)
        self.assertIn("verdict summary", low)

    def test_forbidden_lines_present(self):
        role = read_role_md()
        for phrase in ["issue certification approval",
                       "regulatory sign-off",
                       "reproduce proprietary",
                       "sign_off_required: true"]:
            self.assertIn(phrase, role, "missing boundary: %s" % phrase)

    def test_author_is_ashfordeou(self):
        role = read_role_md()
        self.assertIn("ashfordeOU", role)

    def test_sources_register_exists(self):
        p = os.path.join(ROLE_DIR, "SOURCES.md")
        self.assertTrue(os.path.exists(p), "SOURCES.md missing for role")

    def test_core_engine_exists(self):
        """100% standard: every role ships an executable core + cli."""
        for f in ["core", "cli.py"]:
            self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, f)),
                            "%s missing - role is not executable" % f)
        core_file = os.path.join(ROLE_DIR, "core",
                                 "aircraft_systems_sizing_core.py")
        self.assertTrue(os.path.exists(core_file))


if __name__ == "__main__":
    unittest.main()
