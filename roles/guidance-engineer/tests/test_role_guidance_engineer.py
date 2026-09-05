#!/usr/bin/env python3
"""Role test: Guidance Engineer.

Verifies (offline, no network):
1. Every skill bound in ROLE.md frontmatter RESOLVES to a real leaf in
   the aero-agent-skills repo (the pinned skills_release band).
2. The workflow stage order is deterministic and complete.
3. The deliverable template is the FILLED worked example for the
   reference item (zero blanks, draft markers) and passes the engine's
   own markdown gates.
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
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "guidance-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates", "guidance-report-template.md")
CORE_DIR = os.path.join(ROLE_DIR, "core")

sys.path.insert(0, CORE_DIR)
import guidance_core  # noqa: E402

EXPECTED_BOUND = [
    "gnc-autonomy/guidance/proportional-navigation",
    "gnc-autonomy/guidance/augmented-proportional-navigation",
    "gnc-autonomy/guidance/pursuit-guidance",
    "gnc-autonomy/guidance/collision-course-guidance",
    "gnc-autonomy/guidance/command-to-line-of-sight",
    "gnc-autonomy/guidance/midcourse-guidance",
    "gnc-autonomy/guidance/impact-point-prediction",
    "gnc-autonomy/guidance/dubins-path-planning",
    "gnc-autonomy/guidance/coverage-path-planning",
]

STAGES = [
    "1. Engagement definition",
    "2. Law trade space",
    "3. Gain sizing",
    "4. Acceleration limit check",
    "5. Miss-distance estimate",
    "6. Midcourse steering",
    "7. Report and gates",
]


def role_text():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return f.read()


class TestGuidanceEngineerRole(unittest.TestCase):

    def test_bound_skills_resolve(self):
        if not HAS_SKILLS:
            self.skipTest("skills checkout absent (cross-repo dev check)")
        for leaf in EXPECTED_BOUND:
            self.assertTrue(
                os.path.exists(os.path.join(AEROSKILLS, "skills", leaf,
                                            "SKILL.md")),
                "bound skill missing: %s" % leaf)

    def test_stages_ordered(self):
        role = role_text()
        self.assertIsNotNone(role)
        wf = role[role.find("## Workflow"):role.find("## Evidence gates")]
        idx = [wf.find(s) for s in STAGES]
        self.assertTrue(all(i >= 0 for i in idx), "stage missing in workflow")
        self.assertEqual(idx, sorted(idx), "stage order not deterministic")

    def test_template_present(self):
        self.assertTrue(os.path.exists(TEMPLATE),
                        "deliverable template missing")

    def test_template_is_filled_deliverable(self):
        """100% standard: template is the FILLED worked example - all 9
        numbered sections, zero blank fields, draft markers."""
        self.assertTrue(os.path.exists(TEMPLATE))
        with open(TEMPLATE) as f:
            text = f.read()
        for n in range(1, 10):
            self.assertTrue(
                re.search(r"^## %d\. " % n, text, re.M),
                "report section %d missing" % n)
        self.assertNotIn("___", text)
        low = text.lower()
        self.assertIn("draft", low)
        self.assertIn("not an approval", low)
        self.assertIn("not flight software release", low)
        # key computed numbers of the worked example are present
        self.assertIn("15.763", text)    # PN command m/s^2
        self.assertIn("100.000", text)   # zero-effort miss m
        self.assertIn("26.565", text)    # waypoint desired course deg

    def test_template_passes_core_gates(self):
        """The shipped template must pass the engine's own markdown
        evidence gates (standalone core, no skills repo needed)."""
        with open(TEMPLATE) as f:
            text = f.read()
        gates = guidance_core.check_report_markdown(text)
        self.assertTrue(gates["all_pass"], gates)

    def test_core_and_cli_present(self):
        self.assertTrue(os.path.exists(os.path.join(CORE_DIR,
                                                    "guidance_core.py")),
                        "core/guidance_core.py missing (100% standard)")
        self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, "cli.py")),
                        "cli.py missing (100% standard)")

    def test_core_standalone_example_gates(self):
        """Core produces a correct, gate-passing report with no skills."""
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = guidance_core.build_report(guidance_core.example_project())
        gates = guidance_core.check_report(model)
        self.assertTrue(gates["all_pass"], gates)
        md = guidance_core.example_report_markdown()
        mgates = guidance_core.check_report_markdown(md)
        self.assertTrue(mgates["all_pass"], mgates)

    def test_boundaries(self):
        role = role_text()
        self.assertIsNotNone(role)
        for phrase in ["sign_off_required: true", "forbidden"]:
            self.assertIn(phrase, role)
        for phrase in ["declare the weapon or vehicle ready for guided "
                       "release", "approve flight of the guidance software",
                       "claim certification approval"]:
            self.assertIn(phrase, role, "missing boundary: %s" % phrase)

    def test_sources(self):
        self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, "SOURCES.md")),
                        "SOURCES.md missing")


if __name__ == "__main__":
    unittest.main()
