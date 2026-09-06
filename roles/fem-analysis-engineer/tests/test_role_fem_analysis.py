#!/usr/bin/env python3
"""Role test: Finite Element Analysis Engineer.

Verifies (offline, no network):
1. Every skill bound in ROLE.md frontmatter RESOLVES to a real leaf in
   the aero-agent-skills repo (the pinned skills_release band).
2. The workflow stage order is deterministic and complete.
3. The filled deliverable template is complete: all 11 report sections,
   DRAFT marker, no-approval boundary, no blank fields.
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
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "fem-analysis-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates", "fem-report-template.md")

EXPECTED_BOUND = [
    "structures/fem/truss-analysis",
    "structures/fem/beam-frame-analysis",
    "structures/fem/beam-column-analysis",
    "structures/fem/beam-vibration",
    "structures/fem/buckling-analysis",
    "structures/fem/modal-analysis",
    "structures/fem/shear-center-analysis",
    "structures/fem/lug-joint-analysis",
]

EXPECTED_STAGES = [
    "Truss model", "Frame model", "Beam-column check", "Buckling check",
    "Beam vibration", "Modal analysis", "Shear center", "Lug joint",
]


def read_role_md():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    if not os.path.exists(p):
        return None
    return open(p).read()


class TestFemRole(unittest.TestCase):

    def test_bound_skills_resolve_in_aeroskills(self):
        if not HAS_SKILLS:
            self.skipTest("Aero Agent Skills checkout not present (cross-repo dev check)")
        for leaf in EXPECTED_BOUND:
            sk = os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")
            self.assertTrue(
                os.path.exists(sk),
                "bound skill not found in aero-agent-skills: %s" % leaf)
            logic = os.path.join(AEROSKILLS, "skills", leaf, "scripts")
            self.assertTrue(
                any(f.endswith("_logic.py") for f in os.listdir(logic))
                if os.path.isdir(logic) else False,
                "bound skill has no *logic.py for dispatch: %s" % leaf)

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
        self.assertEqual(idx, sorted(idx), "stage order not deterministic")

    def test_deliverable_template_complete(self):
        self.assertTrue(os.path.exists(TEMPLATE), "template missing")
        text = open(TEMPLATE).read()
        for n in range(1, 12):
            self.assertTrue(
                re.search(r"^## %d\. " % n, text, re.M),
                "section %d missing" % n)
        self.assertIn("DRAFT", text)
        low = text.lower()
        self.assertIn("not an approval", low)
        self.assertIn("margin", low)
        self.assertNotIn("___", text)

    def test_forbidden_lines_present(self):
        role = read_role_md()
        for phrase in ["issue certification approval", "regulatory sign-off",
                       "declare a compliance finding", "reproduce proprietary",
                       "sign_off_required: true"]:
            self.assertIn(phrase, role, "missing boundary: %s" % phrase)

    def test_sources_register_exists(self):
        p = os.path.join(ROLE_DIR, "SOURCES.md")
        self.assertTrue(os.path.exists(p), "SOURCES.md missing for role")

    def test_core_engine_exists(self):
        """100% standard: every role ships an executable core + cli."""
        for f in ["core", "cli.py"]:
            self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, f)),
                            "%s missing - role is not executable" % f)

    def test_cli_standalone_smoke(self):
        """cli build + check must work with no AeroSkills present."""
        import subprocess
        import tempfile
        env = dict(os.environ, AEROSKILLS_DEV="/nonexistent")
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "report.md")
            r1 = subprocess.run([sys.executable,
                                 os.path.join(ROLE_DIR, "cli.py"),
                                 "build", "--out", out],
                                capture_output=True, text=True, env=env)
            self.assertEqual(r1.returncode, 0, r1.stderr)
            r2 = subprocess.run([sys.executable,
                                 os.path.join(ROLE_DIR, "cli.py"),
                                 "check", "--file", out],
                                capture_output=True, text=True, env=env)
            self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)


if __name__ == "__main__":
    unittest.main()
