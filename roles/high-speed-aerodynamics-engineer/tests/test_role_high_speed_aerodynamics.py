#!/usr/bin/env python3
"""Role test: high-speed-aerodynamics-engineer.

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
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "high-speed-aerodynamics-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates", "high-speed-memo-template.md")

EXPECTED_BOUND = [
    "aerodynamics/high-speed/isentropic-flow-relations",
    "aerodynamics/high-speed/normal-shock",
    "aerodynamics/high-speed/oblique-shock",
    "aerodynamics/high-speed/prandtl-meyer",
    "aerodynamics/high-speed/regular-shock-reflection",
    "aerodynamics/high-speed/shock-expansion-airfoil",
    "aerodynamics/high-speed/transonic-similarity",
    "aerodynamics/high-speed/swept-wing-aerodynamics",
    "aerodynamics/high-speed/supercritical-airfoil",
    "aerodynamics/high-speed/wave-drag-area-rule",
    "aerodynamics/high-speed/bow-shock-standoff",
    "aerodynamics/high-speed/aerodynamic-heating",
    "aerodynamics/high-speed/flat-plate-skin-friction-heating",
    "aerodynamics/high-speed/hypersonic-flow",
    "aerodynamics/boundary-layer/boundary-layer-theory",
    "aerodynamics/boundary-layer/boundary-layer-transition",
    "aerodynamics/boundary-layer/boundary-layer-separation",
    "aerodynamics/boundary-layer/rough-wall-skin-friction",
    "aerodynamics/boundary-layer/stagnation-flow-boundary-layer",
]

STAGES = [
    "1. Flow-state setup",
    "2. Isentropic relations",
    "3. Compressibility corrections",
    "4. Shock system",
    "5. Expansion",
    "6. Supersonic section",
    "7. Transonic limit",
    "8. Boundary layer",
    "9. BL separation screen",
    "10. Surface state",
    "11. Heating screen",
    "12. Memo",
]


def role_text():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    return open(p).read() if os.path.exists(p) else None


class TestHighSpeedAerodynamicsRole(unittest.TestCase):

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
        for phrase in ["high-speed aerodynamic analysis memo", "draft",
                       "not an approval", "margin summary"]:
            self.assertIn(phrase, low, f"gate vocabulary missing: {phrase}")
        # real compressible-flow numbers present (M 2.00, p0/p ~ 7.82)
        self.assertRegex(text, r"cruise M 2\.00")
        self.assertRegex(text, r"p0/p = 7\.8244")

    def test_executable_core_and_cli(self):
        # 100% worker anatomy: executable domain engine + runnable CLI.
        for rel in ("core/high_speed_aero_core.py", "cli.py",
                    "tests/test_high_speed_aero_core.py"):
            self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, rel)),
                            f"missing executable part: {rel}")

    def test_boundaries(self):
        role = role_text()
        self.assertIsNotNone(role)
        role = role or ""
        for phrase in ["sign_off_required: true", "forbidden",
                       "never", "claim certification approval", "screening"]:
            self.assertIn(phrase, role, f"missing boundary: {phrase}")

    def test_sources(self):
        self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, "SOURCES.md")),
                        "SOURCES.md missing")


if __name__ == "__main__":
    unittest.main()
