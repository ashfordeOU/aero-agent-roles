#!/usr/bin/env python3
"""Role test: Numerical Analysis Engineer.

Verifies (offline, no network):
1. Every skill bound in ROLE.md frontmatter RESOLVES to a real leaf in
   the aero-agent-skills repo (the pinned skills_release band).
2. The workflow stage order is deterministic and complete.
3. The filled deliverable template is present with no blanks and the
   boundary markers.
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
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "numerical-analysis-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates", "verification-memo-template.md")

EXPECTED_BOUND = [
    "cross-cutting/numerics/numerical-integration",
    "cross-cutting/numerics/root-finding",
    "cross-cutting/numerics/convergence-verification",
    "cross-cutting/numerics/finite-difference-derivatives",
    "cross-cutting/numerics/ode-solvers",
    "cross-cutting/numerics/interpolation",
    "cross-cutting/numerics/least-squares-regression",
    "cross-cutting/numerics/matrix-operations",
    "cross-cutting/numerics/singular-value-decomposition",
    "cross-cutting/numerics/uncertainty-propagation",
]

EXPECTED_STAGES = [
    "Integration", "Root finding", "Derivatives", "ODE paths",
    "Interpolation paths", "Regression paths", "Linear solve",
    "Convergence", "Error budget", "Memo build",
]


def read_role_md():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    if not os.path.exists(p):
        return None
    return open(p).read()


class TestNumericalAnalysisEngineerRole(unittest.TestCase):

    def test_bound_skills_resolve_in_aeroskills(self):
        if not HAS_SKILLS:
            self.skipTest("Aero Agent Skills checkout not present "
                          "(cross-repo dev check)")
        for leaf in EXPECTED_BOUND:
            sk = os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")
            self.assertTrue(
                os.path.exists(sk),
                f"bound skill not found in aero-agent-skills: {leaf}")
            logic = os.path.join(AEROSKILLS, "skills", leaf, "scripts")
            self.assertTrue(
                any(f.endswith("_logic.py")
                    for f in os.listdir(logic)),
                f"bound leaf ships no logic file: {leaf}")

    def test_bound_skills_listed_in_frontmatter(self):
        role = read_role_md()
        self.assertIsNotNone(role)
        for leaf in EXPECTED_BOUND:
            self.assertIn(leaf, role,
                          f"missing in ROLE.md skills_bound: {leaf}")

    def test_workflow_stages_deterministic(self):
        role = read_role_md()
        # every expected stage appears in order (indexes ascending)
        idx = [role.find(stage) for stage in EXPECTED_STAGES]
        self.assertTrue(all(i >= 0 for i in idx), "a stage is missing")
        self.assertEqual(idx, sorted(idx), "stage order not deterministic")

    def test_deliverable_template_complete(self):
        if not os.path.exists(TEMPLATE):
            self.fail("verification-memo-template.md missing")
        with open(TEMPLATE) as fh:
            text = fh.read()
        # all 6 numbered sections present
        for n in range(1, 7):
            self.assertTrue(
                re.search(rf"^## {n}\. ", text, re.M),
                f"section {n} missing")
        self.assertIn("DRAFT", text)
        low = text.lower()
        self.assertIn("not an approval", low)
        self.assertIn("Numerical Methods Verification Memo", text)
        self.assertNotIn("___", text)   # filled deliverable, zero blanks

    def test_forbidden_lines_present(self):
        role = read_role_md()
        for phrase in ["issue engineering approval", "declare compliance",
                       "sign_off_required: true", "reproduce proprietary"]:
            self.assertIn(phrase, role, f"missing boundary: {phrase}")

    def test_sources_register_exists(self):
        p = os.path.join(ROLE_DIR, "SOURCES.md")
        self.assertTrue(os.path.exists(p), "SOURCES.md missing for role")

    def test_core_engine_exists(self):
        """100% standard: every role ships an executable core + cli."""
        for f in ["core", "cli.py"]:
            self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, f)),
                            f"{f} missing - role is not executable")


if __name__ == "__main__":
    unittest.main()
