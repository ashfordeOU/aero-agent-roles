#!/usr/bin/env python3
"""Role test: Airworthiness Compliance Engineer.

Offline verification:
1. Every bound skill resolves in aero-agent-skills.
2. Workflow stage order deterministic + complete.
3. Compliance matrix template has the required columns/rows.
4. Boundaries + sign-off present.
"""
import os
import re
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
# Bound-skill resolution requires the Aero Agent Skills checkout (cross-repo
# dev check); skip when absent so fresh public clones can still run make validate.
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "airworthiness-compliance-engineer")
MATRIX = os.path.join(ROLE_DIR, "templates", "compliance-matrix-template.md")

EXPECTED_BOUND = [
    "avionics/far-cs25/airworthiness",
    "avionics/far-cs25/special-conditions",
    "systems-engineering-safety/certification/certification-basis",
    "systems-engineering-safety/certification/equivalent-level-of-safety",
    "systems-engineering-safety/certification/means-of-compliance",
    "systems-engineering-safety/certification/mmel-development",
    "systems-engineering-safety/continued-airworthiness/airworthiness-directive-compliance",
    "systems-engineering-safety/continued-airworthiness/type-certificate-data-sheet",
    "systems-engineering-safety/continued-airworthiness/in-service-safety-assessment",
]

STAGES = ["Certification basis", "Special conditions", "ELOS",
          "Means of compliance", "Airworthiness mapping", "MMEL",
          "Continued airworthiness", "Compliance matrix"]


def role_text():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    return open(p).read() if os.path.exists(p) else None


class TestAirworthinessRole(unittest.TestCase):

    def test_bound_skills_resolve(self):
        if not HAS_SKILLS:
            self.skipTest("Aero Agent Skills checkout not present (cross-repo dev check)")
        for leaf in EXPECTED_BOUND:
            self.assertTrue(
                os.path.exists(os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")),
                f"bound skill missing: {leaf}")

    def test_stages_ordered(self):
        role = role_text()
        self.assertIsNotNone(role)
        idx = [role.find(s) for s in STAGES]
        self.assertTrue(all(i >= 0 for i in idx))
        self.assertEqual(idx, sorted(idx), "stage order not deterministic")

    def test_matrix_columns_present(self):
        if not os.path.exists(MATRIX):
            self.fail("compliance-matrix-template.md missing")
        text = open(MATRIX).read()
        for col in ["Reg", "Applicable?", "Means of compliance",
                    "Compliance document", "Status", "Owner"]:
            self.assertIn(col, text, f"column missing: {col}")
        self.assertIn("proposed", text.lower())

    def test_boundaries(self):
        role = role_text()
        self.assertIsNotNone(role)
        for phrase in ["declare a compliance finding", "claim certification approval",
                       "sign_off_required: true"]:
            self.assertIn(phrase, role)

    def test_sources_register(self):
        self.assertTrue(
            os.path.exists(os.path.join(ROLE_DIR, "SOURCES.md")),
            "SOURCES.md missing")


if __name__ == "__main__":
    unittest.main()
