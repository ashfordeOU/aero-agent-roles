#!/usr/bin/env python3
"""Role test: Aerodynamics Engineer.

Offline verification: bound skills resolve, workflow deterministic,
report template complete, boundaries present, SOURCES present.
"""
import os
import re
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "aerodynamics-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates", "aero-design-report-template.md")

EXPECTED_BOUND = [
    "aerodynamics/airfoil/xfoil-analysis",
    "aerodynamics/airfoil/airfoil-selection",
    "aerodynamics/wing-design/wing-planform-design",
    "aerodynamics/drag-polars/drag-polar",
    "aerodynamics/drag-polars/parasite-drag",
    "aerodynamics/drag-polars/lift-curve-slope",
    "aerodynamics/high-lift/high-lift-systems",
    "aerodynamics/cfd/vortex-lattice-method",
    "aerodynamics/cfd/cfd-validation",
    "aerodynamics/cfd/cfd-convergence",
    "aerodynamics/cfd/cfd-mesh-generation",
    "aerodynamics/cfd/cfd-turbulence-modeling",
    "aerodynamics/high-speed/swept-wing-aerodynamics",
    "aerodynamics/high-speed/transonic-similarity",
    "aerodynamics/high-speed/supercritical-airfoil",
    "aerodynamics/high-speed/wave-drag-area-rule",
    "aerodynamics/high-speed/normal-shock",
    "aerodynamics/boundary-layer/boundary-layer-theory",
    "aerodynamics/boundary-layer/boundary-layer-transition",
    "aerodynamics/aeroelasticity/flutter-speed-prediction",
    "aerodynamics/aeroelasticity/aeroelastic-gust-response",
    "aerodynamics/ground-effects/ground-effect",
    "aerodynamics/wind-tunnel/windtunnel-data-reduction",
    "aerodynamics/wind-tunnel/windtunnel-wall-corrections",
]

STAGES = ["Airfoil analysis", "Airfoil optimization", "Wing planform",
          "High-lift", "Drag buildup", "Winglet / 3D", "CFD validation",
          "Transonic", "Boundary layer", "Aeroelastic screen",
          "Ground/wind tunnel", "Report"]


def role_text():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    return open(p).read() if os.path.exists(p) else None


class TestAerodynamicsRole(unittest.TestCase):

    def test_bound_skills_resolve(self):
        if not HAS_SKILLS:
            self.skipTest("skills checkout absent")
        for leaf in EXPECTED_BOUND:
            self.assertTrue(
                os.path.exists(os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")),
                f"bound skill missing: {leaf}")

    def test_stages_ordered(self):
        role = role_text()
        self.assertIsNotNone(role)
        # check order within the Workflow section only
        wf = role[role.find("## Workflow"):role.find("## Evidence gates")]
        idx = [wf.find(s) for s in STAGES]
        self.assertTrue(all(i >= 0 for i in idx), "a stage missing in workflow")
        self.assertEqual(idx, sorted(idx), "stage order not deterministic")

    def test_template_sections(self):
        if not os.path.exists(TEMPLATE):
            self.fail("template missing")
        text = open(TEMPLATE).read()
        for n in range(1, 9):
            self.assertTrue(re.search(rf"^## {n}\. ", text, re.M), f"section {n}")
        self.assertIn("DRAFT", text)

    def test_boundaries(self):
        role = role_text()
        self.assertIsNotNone(role)
        for phrase in ["claim certification approval", "sign_off_required: true"]:
            self.assertIn(phrase, role)

    def test_sources(self):
        self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, "SOURCES.md")))


if __name__ == "__main__":
    unittest.main()
