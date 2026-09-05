#!/usr/bin/env python3
"""Role test: Flight Management Engineer.

Verifies (offline, no network):
1. Every skill bound in ROLE.md frontmatter RESOLVES to a real leaf in
   the Aero Agent Skills repo (avionics/flight-management cluster).
2. The workflow stage order is deterministic and complete.
3. The filled deliverable template is complete: numbered sections,
   DRAFT marker, not-an-approval boundary, no blank placeholders.
4. Boundaries, author, SOURCES.md and the executable core/cli anatomy.
"""
import os
import re
import sys
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))          # repo root (4 up from tests/)
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "flight-management-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates", "route-assessment-template.md")

EXPECTED_BOUND = [
    "avionics/flight-management/flight-planning",
    "avionics/flight-management/lateral-navigation",
    "avionics/flight-management/vertical-navigation",
    "avionics/flight-management/holding-pattern-entry",
    "avionics/flight-management/dme-arc-leg",
    "avionics/flight-management/radius-to-fix-leg",
    "avionics/flight-management/rhumb-line-leg",
    "avionics/flight-management/radio-navigation-aids",
    "avionics/flight-management/rnp-anp-containment",
    "avionics/flight-management/performance-computation",
    "avionics/flight-management/rta-time-control",
]

EXPECTED_STAGES = [
    "Route structure & constraints",
    "Lateral track geometry",
    "RF leg construction",
    "Rhumb line legs",
    "RNP containment",
    "Holding entry",
    "DME arc legs",
    "Navaid geometry",
    "RTA control",
    "VNAV & performance",
    "Findings & sign-off",
]


def read_role_md():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    if not os.path.exists(p):
        return None
    return open(p).read()


class TestFlightManagementRole(unittest.TestCase):

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
            self.assertIn(leaf, role, "missing in ROLE.md skills_bound: %s"
                          % leaf)

    def test_workflow_stages_deterministic(self):
        role = read_role_md()
        idx = [role.find(stage) for stage in EXPECTED_STAGES]
        self.assertTrue(all(i >= 0 for i in idx), "a stage is missing")
        self.assertEqual(idx, sorted(idx),
                         "stage order not deterministic")

    def test_deliverable_template_complete(self):
        if not os.path.exists(TEMPLATE):
            self.fail("route-assessment-template.md missing")
        text = open(TEMPLATE).read()
        # all 8 numbered sections present
        for n in range(1, 9):
            self.assertTrue(re.search(r"^## %d\. " % n, text, re.M),
                            "section %d missing" % n)
        self.assertIn("DRAFT", text)
        low = text.lower()
        self.assertIn("not an approval", low)
        self.assertIn("document", low)
        # zero blank placeholders
        self.assertNotRegex(text, r"_{3,}|\[TBD\]|TODO|Lorem")

    def test_forbidden_lines_present(self):
        role = read_role_md()
        for phrase in ["approve the flight plan", "issue a clearance",
                       "reproduce proprietary", "sign_off_required: true"]:
            self.assertIn(phrase, role, "missing boundary: %s" % phrase)

    def test_author_ashfordeou(self):
        role = read_role_md()
        self.assertIn("ashfordeOU", role, "author not set")

    def test_sources_register_exists(self):
        p = os.path.join(ROLE_DIR, "SOURCES.md")
        self.assertTrue(os.path.exists(p), "SOURCES.md missing for role")

    def test_core_engine_exists(self):
        """100% standard: every role ships an executable core + cli."""
        for f in ["core", "cli.py"]:
            self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, f)),
                            "%s missing - role is not executable" % f)


if __name__ == "__main__":
    unittest.main()
