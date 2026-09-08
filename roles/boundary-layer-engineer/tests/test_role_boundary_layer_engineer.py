#!/usr/bin/env python3
"""Role test: boundary-layer-engineer."""
import os
import re
import sys
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "boundary-layer-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates",
                        "boundary-layer-analysis-report-template.md")
CORE_DIR = os.path.join(ROLE_DIR, "core")

sys.path.insert(0, CORE_DIR)
import boundary_layer_engineer_core as bl_core  # noqa: E402

EXPECTED_BOUND = [
    "aerodynamics/boundary-layer/laminar-far-wake",
    "aerodynamics/boundary-layer/mangler-axisymmetric-transform",
    "aerodynamics/boundary-layer/squire-young-profile-drag",
    "aerodynamics/boundary-layer/stokes-creeping-flow-drag",
    "aerodynamics/boundary-layer/unsteady-laminar-stokes-layers",
    "aerodynamics/boundary-layer/boundary-layer-theory",
    "aerodynamics/boundary-layer/boundary-layer-transition",
    "aerodynamics/boundary-layer/boundary-layer-separation",
    "aerodynamics/boundary-layer/rough-wall-skin-friction",
    "aerodynamics/boundary-layer/stagnation-flow-boundary-layer",
]

STAGES = [
    "Laminar growth & transition",
    "Section profile drag",
    "Fuselage forebody",
    "Downstream wake",
    "Surface finish",
    "Nose stagnation flow",
    "Small protruding component",
    "Surface oscillation",
]

REQUIRED_SECTIONS = [
    "Role identity", "Deliverable contract", "Workflow",
    "Evidence gates", "Boundary", "Verification", "Compliance",
]


def role_text():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return f.read()


class TestBoundaryLayerEngineerRole(unittest.TestCase):

    def test_bound_skills_resolve(self):
        if not HAS_SKILLS:
            self.skipTest("skills checkout absent (cross-repo dev check)")
        for leaf in EXPECTED_BOUND:
            self.assertTrue(
                os.path.exists(os.path.join(AEROSKILLS, "skills", leaf,
                                            "SKILL.md")),
                f"bound skill missing: {leaf}")

    def test_required_sections_present(self):
        role = role_text()
        self.assertIsNotNone(role)
        for sec in REQUIRED_SECTIONS:
            self.assertIn("## " + sec, role, f"section missing: {sec}")

    def test_stages_ordered(self):
        role = role_text()
        self.assertIsNotNone(role)
        wf = role[role.find("## Workflow"):role.find("## Evidence gates")]
        idx = [wf.find(s) for s in STAGES]
        self.assertTrue(all(i >= 0 for i in idx), "stage missing in workflow")
        self.assertEqual(idx, sorted(idx), "stage order not deterministic")

    def test_template_present(self):
        self.assertTrue(os.path.exists(TEMPLATE), "deliverable template missing")

    def test_template_is_filled_deliverable(self):
        """100% standard: template is the FILLED worked example - all 9
        numbered sections, zero blank fields, draft markers."""
        self.assertTrue(os.path.exists(TEMPLATE))
        with open(TEMPLATE) as f:
            text = f.read()
        for n in range(1, 10):
            self.assertTrue(
                re.search(rf"^## {n}\. ", text, re.M),
                f"report section {n} missing")
        self.assertNotIn("___", text)
        low = text.lower()
        self.assertIn("draft", low)
        self.assertIn("not an approval", low)
        self.assertIn("not a certification approval", low)

    def test_template_passes_core_gates(self):
        """The shipped template must pass the engine's own markdown
        evidence gates (standalone core, no skills repo needed)."""
        with open(TEMPLATE) as f:
            text = f.read()
        gates = bl_core.check_report_markdown(text)
        self.assertTrue(gates["all_pass"], gates)

    def test_core_and_cli_present(self):
        self.assertTrue(os.path.exists(
            os.path.join(CORE_DIR, "boundary_layer_engineer_core.py")),
            "core/boundary_layer_engineer_core.py missing (100% standard)")
        self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, "cli.py")),
                        "cli.py missing (100% standard)")

    def test_core_standalone_example_gates(self):
        """Core produces a correct, gate-passing report with no skills."""
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = bl_core.build_report(bl_core.example_item())
        gates = bl_core.check_report(model)
        self.assertTrue(gates["all_pass"], gates)
        md = bl_core.example_report_markdown()
        mgates = bl_core.check_report_markdown(md)
        self.assertTrue(mgates["all_pass"], mgates)

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
