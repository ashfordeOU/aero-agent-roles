#!/usr/bin/env python3
"""Role test: State Estimation Engineer.

Verifies (offline, no network):
1. Every skill bound in ROLE.md frontmatter RESOLVES to a real leaf in
   the aero-agent-skills repo (the pinned skills_release band).
2. The workflow stage order is deterministic and complete.
3. The filled deliverable template is complete (no blanks, draft
   markers, sections) and the role carries the executable anatomy.
4. The core engine builds the example deliverable standalone.
"""
import os
import re
import sys
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))          # repo root (4 up from tests/)
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "state-estimation-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates",
                        "nav-state-estimator-design-template.md")
CORE_DIR = os.path.join(ROLE_DIR, "core")

sys.path.insert(0, CORE_DIR)
import state_estimation_core  # noqa: E402

EXPECTED_BOUND = [
    "gnc-autonomy/estimation-filtering/alpha-beta-filter",
    "gnc-autonomy/estimation-filtering/complementary-filter",
    "gnc-autonomy/estimation-filtering/extended-kalman-filter",
    "gnc-autonomy/estimation-filtering/interacting-multiple-model-filter",
    "gnc-autonomy/estimation-filtering/particle-filter",
    "gnc-autonomy/estimation-filtering/rts-smoother",
    "gnc-autonomy/estimation-filtering/unscented-kalman-filter",
]

EXPECTED_STAGES = [
    "1. Architecture + noise model", "2. Attitude channel",
    "3. Navigation channel", "4. Fixed-gain companion",
    "5. Nonlinear updates", "6. Fallbacks",
    "7. Offline post-processing", "8. Observability", "9. Report",
]


def read_role_md():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    if not os.path.exists(p):
        return None
    return open(p).read()


class TestStateEstimationEngineerRole(unittest.TestCase):

    def test_bound_skills_resolve_in_aeroskills(self):
        if not HAS_SKILLS:
            self.skipTest("Aero Agent Skills checkout not present "
                          "(cross-repo dev check)")
        for leaf in EXPECTED_BOUND:
            sk = os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")
            self.assertTrue(
                os.path.exists(sk),
                f"bound skill not found in aero-agent-skills: {leaf}")

    def test_bound_skills_listed_in_frontmatter(self):
        role = read_role_md()
        self.assertIsNotNone(role)
        for leaf in EXPECTED_BOUND:
            self.assertIn(leaf, role,
                          f"missing in ROLE.md skills_bound: {leaf}")

    def test_workflow_stages_deterministic(self):
        role = read_role_md()
        wf = role[role.find("## Workflow"):role.find("## Evidence gates")]
        idx = [wf.find(stage) for stage in EXPECTED_STAGES]
        self.assertTrue(all(i >= 0 for i in idx), "a stage is missing")
        self.assertEqual(idx, sorted(idx), "stage order not deterministic")

    def test_deliverable_template_complete(self):
        self.assertTrue(os.path.exists(TEMPLATE),
                        "deliverable template missing")
        text = open(TEMPLATE).read()
        for n in range(1, 10):
            self.assertTrue(
                re.search(rf"^## {n}\. ", text, re.M),
                f"report section {n} missing")
        self.assertIn("Navigation State Estimator Design Report", text)
        self.assertNotIn("___", text)
        low = text.lower()
        self.assertIn("draft", low)
        self.assertIn("not an approval", low)
        self.assertIn("estimator class", low)

    def test_forbidden_lines_present(self):
        role = read_role_md()
        for phrase in ["release navigation/flight software",
                       "authorize flight", "claim certification approval",
                       "reproduce proprietary", "sign_off_required: true"]:
            self.assertIn(phrase, role, f"missing boundary: {phrase}")

    def test_sources_register_exists(self):
        p = os.path.join(ROLE_DIR, "SOURCES.md")
        self.assertTrue(os.path.exists(p), "SOURCES.md missing for role")

    def test_core_engine_exists(self):
        """100% standard: every role ships an executable core + cli."""
        for f in ["core", "cli.py"]:
            self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, f)),
                            f"{f} missing - role is not executable")

    def test_author_attribution(self):
        role = read_role_md()
        self.assertIn("author: ashfordeOU", role)

    def test_example_deliverable_builds_and_gates(self):
        """The engine produces the deliverable standalone and gates pass."""
        model = state_estimation_core.build_report(
            state_estimation_core.example_item())
        md = state_estimation_core.render_report_markdown(model)
        self.assertGreater(len(md), 3000)
        self.assertTrue(state_estimation_core.check_report(model)["all_pass"])
        self.assertTrue(state_estimation_core.check_report_markdown(md)["all_pass"])


if __name__ == "__main__":
    unittest.main()
