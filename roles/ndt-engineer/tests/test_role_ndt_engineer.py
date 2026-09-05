#!/usr/bin/env python3
"""Role test: NDT Engineer.

Verifies (offline, no network):
1. Every skill bound in ROLE.md frontmatter RESOLVES to a real leaf in
   the aero-agent-skills repo (the pinned skills_release band).
2. The workflow stage order is deterministic and complete.
3. The deliverable template is filled (zero blanks) and carries the
   DRAFT / not-an-approval boundary.
4. ROLE.md boundaries and the executable core + cli exist.
"""
import os
import re
import sys
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))          # repo root (4 up from tests/)
# Bound-skill resolution requires the Aero Agent Skills checkout. It is a
# cross-repo dev check: when the skills repo is absent (fresh public clone),
# skip resolution rather than fail - the role's bound list is verified in CI.
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "ndt-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates", "ndt-plan-template.md")

EXPECTED_BOUND = [
    "manufacturing-quality/ndt/ndt-method-selection",
    "manufacturing-quality/ndt/eddy-current-inspection",
    "manufacturing-quality/ndt/liquid-penetrant-inspection",
    "manufacturing-quality/ndt/radiographic-inspection",
    "manufacturing-quality/ndt/computed-tomography",
    "manufacturing-quality/ndt/magnetic-particle-inspection",
    "manufacturing-quality/ndt/leak-testing",
    "manufacturing-quality/ndt/acoustic-emission-inspection",
    "manufacturing-quality/ndt/shearography-inspection",
    "manufacturing-quality/ndt/ndt-personnel-qualification",
]

EXPECTED_STAGES = [
    "Method selection per defect class",
    "Eddy current parameter set",
    "Liquid penetrant dwell sizing",
    "Radiography technique verdict",
    "Computed tomography resolution plan",
    "Magnetic particle magnetization plan",
    "Leak test plan and disposition",
    "Acoustic emission monitoring plan",
    "Shearography strain plan",
    "Personnel qualification review",
]

# Each bound leaf must ship the logic file the core mirrors (and that the
# CLI dispatches for cross-checks when the skills repo is present).
EXPECTED_LOGIC = {
    "ndt-method-selection": "ndt_selection_logic.py",
    "eddy-current-inspection": "eddy_current_inspection_logic.py",
    "liquid-penetrant-inspection": "liquid_penetrant_inspection_logic.py",
    "radiographic-inspection": "radiographic_inspection.py",
    "computed-tomography": "computed_tomography_logic.py",
    "magnetic-particle-inspection": "magnetic_particle_inspection_logic.py",
    "leak-testing": "leak_testing_logic.py",
    "acoustic-emission-inspection": "acoustic_emission_inspection_logic.py",
    "shearography-inspection": "shearography_inspection_logic.py",
    "ndt-personnel-qualification": "ndt_personnel_qualification_logic.py",
}


def read_role_md():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    if not os.path.exists(p):
        return None
    return open(p).read()


class TestNdtRole(unittest.TestCase):

    def test_bound_skills_resolve_in_aeroskills(self):
        if not HAS_SKILLS:
            self.skipTest("Aero Agent Skills checkout not present "
                          "(cross-repo dev check)")
        for leaf in EXPECTED_BOUND:
            sk = os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")
            self.assertTrue(os.path.exists(sk),
                            f"bound skill not found: {leaf}")

    def test_bound_leaves_ship_logic_files(self):
        if not HAS_SKILLS:
            self.skipTest("Aero Agent Skills checkout not present")
        for leaf, logic in EXPECTED_LOGIC.items():
            p = os.path.join(AEROSKILLS, "skills",
                             "manufacturing-quality/ndt", leaf,
                             "scripts", logic)
            self.assertTrue(os.path.exists(p),
                            f"logic file missing for {leaf}: {logic}")

    def test_bound_skills_listed_in_frontmatter(self):
        role = read_role_md()
        self.assertIsNotNone(role)
        for leaf in EXPECTED_BOUND:
            self.assertIn(leaf, role, f"missing in ROLE.md skills_bound: "
                                      f"{leaf}")

    def test_workflow_stages_deterministic(self):
        role = read_role_md()
        idx = [role.find(stage) for stage in EXPECTED_STAGES]
        self.assertTrue(all(i >= 0 for i in idx), "a stage is missing")
        self.assertEqual(idx, sorted(idx), "stage order not deterministic")

    def test_deliverable_template_complete(self):
        self.assertTrue(os.path.exists(TEMPLATE),
                        "ndt-plan-template.md missing")
        text = open(TEMPLATE).read()
        # all 5 numbered sections present
        for n in range(1, 6):
            self.assertTrue(re.search(rf"^## {n}\. ", text, re.M),
                            f"section {n} missing")
        self.assertIn("Nondestructive Test Plan and Method Selection Report",
                      text)
        # ZERO blank ___ fields (filled deliverable)
        self.assertNotIn("___", text)
        low = text.lower()
        self.assertIn("draft", low)
        self.assertIn("not an approval", low)

    def test_forbidden_lines_present(self):
        role = read_role_md()
        for phrase in ["issue acceptance or disposition approval",
                       "certify NDT personnel",
                       "sign_off_required: true"]:
            self.assertIn(phrase, role, f"missing boundary: {phrase}")

    def test_sources_register_exists(self):
        self.assertTrue(os.path.exists(os.path.join(ROLE_DIR,
                                                    "SOURCES.md")))

    def test_core_engine_exists(self):
        """100% standard: every role ships an executable core + cli."""
        for f in ["core", "cli.py"]:
            self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, f)),
                            f"{f} missing - role is not executable")
        core_dir = os.path.join(ROLE_DIR, "core")
        self.assertTrue(any(f.endswith("_core.py")
                            for f in os.listdir(core_dir)))


if __name__ == "__main__":
    unittest.main()
