#!/usr/bin/env python3
"""Role test: structures-loads-engineer.

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
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "structures-loads-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates",
                        "loads-strength-report-template.md")

EXPECTED_BOUND = [
    "structures/loads/gust-maneuver-loads",
    "structures/loads/landing-ground-loads",
    "structures/loads/random-vibration-analysis",
    "structures/loads/shock-response-spectrum",
    "structures/fem/beam-frame-analysis",
    "structures/fem/truss-analysis",
    "structures/fem/calculix-linear",
    "structures/fem/calculix-nonlinear",
    "structures/fem/buckling-analysis",
    "structures/fem/plate-buckling",
    "structures/fem/cylindrical-shell-buckling",
    "structures/fem/modal-analysis",
    "structures/fem/beam-vibration",
    "structures/fem/lug-joint-analysis",
    "structures/fem/contact-analysis",
    "structures/fem/pressure-bulkhead",
    "structures/materials/material-selection",
    "structures/materials/mmpsd-allowables",
    "structures/materials/ramberg-osgood",
    "structures/materials/creep-rupture",
    "structures/materials/fracture-toughness",
    "structures/fatigue/goodman-diagram",
    "structures/fatigue/stress-life-curve",
    "structures/fatigue/strain-life-fatigue",
    "structures/fatigue/miner-damage",
    "structures/fatigue/notch-sensitivity",
    "structures/fatigue/load-spectrum-counting",
    "structures/damage-tolerance/crack-growth",
    "structures/damage-tolerance/residual-strength",
    "structures/damage-tolerance/bird-strike",
    "structures/damage-tolerance/widespread-fatigue-damage",
    "structures/composites/laminate-stiffness",
    "structures/composites/laminate-first-ply-failure",
    "structures/composites/failure-criteria",
    "structures/composites/sandwich-panels",
    "structures/composites/composite-repair",
    "structures/thermal-structures/thermal-stress-analysis",
    "structures/thermal-structures/thermal-buckling"
]

STAGES = [
    "1. Design loads",
    "2. Global FEM",
    "3. Nonlinear/buckling",
    "4. Detail joints",
    "5. Dynamics",
    "6. Materials",
    "7. Fatigue",
    "8. Damage tolerance",
    "9. Composites",
    "10. Thermal",
    "11. Report",
]


def role_text():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    return open(p).read() if os.path.exists(p) else None


class TestStructuresLoadsEngineerRole(unittest.TestCase):

    def test_bound_skills_resolve(self):
        if not HAS_SKILLS:
            self.skipTest("skills checkout absent (cross-repo dev check)")
        for leaf in EXPECTED_BOUND:
            self.assertTrue(
                os.path.exists(os.path.join(AEROSKILLS, "skills", leaf,
                                            "SKILL.md")),
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

    def test_filled_template_zero_blanks(self):
        # ROLE-STANDARD 100% bar: templates hold ONE filled deliverable
        # (the generated worked example). Zero ___ placeholders.
        if not os.path.exists(TEMPLATE):
            self.fail("template missing")
        text = open(TEMPLATE).read()
        self.assertNotIn("___", text, "template still has blanks")
        low = text.lower()
        # gate-check vocabulary must exist in the filled deliverable
        for phrase in ["loads and strength report", "margins", "draft",
                       "not an approval"]:
            self.assertIn(phrase, low, f"gate vocabulary missing: {phrase}")
        # a real margin-of-safety number is present (MS like +0.xxx)
        self.assertRegex(text, r"\*\*[+-]\d\.\d{3}\*\*")

    def test_executable_core_and_cli(self):
        # 100% worker anatomy: executable domain engine + runnable CLI.
        for rel in ("core/structures_loads_core.py", "cli.py",
                    "tests/test_structures_loads_core.py"):
            self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, rel)),
                            f"missing executable part: {rel}")

    def test_boundaries(self):
        role = role_text()
        self.assertIsNotNone(role)
        role = role or ""
        for phrase in ["sign_off_required: true", "forbidden",
                       "never invent allowables", "not an approval"]:
            self.assertIn(phrase, role, f"missing boundary: {phrase}")

    def test_sources(self):
        self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, "SOURCES.md")),
                        "SOURCES.md missing")


if __name__ == "__main__":
    unittest.main()
