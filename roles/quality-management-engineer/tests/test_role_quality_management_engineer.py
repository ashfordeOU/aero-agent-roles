#!/usr/bin/env python3
"""Role test: AS9100 Quality Management Engineer.

Verifies (offline, no network):
1. Every skill bound in ROLE.md frontmatter RESOLVES to a real leaf in
   the aero-agent-skills repo (the pinned skills_release band), and
   every bound leaf ships a logic file the role can dispatch.
2. The workflow stage order is deterministic and complete.
3. The filled deliverable template carries no blanks and the role's
   no-approval boundary markers.
4. The role ships the 100% anatomy (core engine, cli, SOURCES) and the
   author is ashfordeOU.
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
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "quality-management-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates", "qms-audit-report-template.md")

EXPECTED_BOUND = [
    "manufacturing-quality/as9100/acceptance-sampling",
    "manufacturing-quality/as9100/attribute-agreement-analysis",
    "manufacturing-quality/as9100/attribute-control-charts",
    "manufacturing-quality/as9100/cusum-ewma-monitoring",
    "manufacturing-quality/as9100/gage-linearity-bias-study",
    "manufacturing-quality/as9100/gage-rr-anova",
    "manufacturing-quality/as9100/individuals-and-moving-range-chart",
    "manufacturing-quality/as9100/measurement-systems-analysis",
    "manufacturing-quality/as9100/statistical-process-control",
    "manufacturing-quality/as9100/variables-acceptance-sampling",
]

EXPECTED_STAGES = [
    "Gage R&R", "Bias/linearity", "Attribute agreement", "Variable SPC",
    "Single-measurement SPC", "Small-shift monitoring", "Attribute SPC",
    "Attribute sampling", "Variables sampling", "Report + gates",
]


def read_role_md():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    if not os.path.exists(p):
        return None
    return open(p).read()


class TestQualityManagementRole(unittest.TestCase):

    def test_bound_skills_resolve_in_aeroskills(self):
        if not HAS_SKILLS:
            self.skipTest("Aero Agent Skills checkout not present "
                          "(cross-repo dev check)")
        for leaf in EXPECTED_BOUND:
            sk = os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")
            self.assertTrue(os.path.exists(sk),
                            "bound skill not found in aero-agent-skills: "
                            "%s" % leaf)
            scripts = os.path.join(AEROSKILLS, "skills", leaf, "scripts")
            logic = [f for f in os.listdir(scripts)
                     if f.endswith("_logic.py") and not f.startswith("test_")]
            self.assertTrue(logic,
                            "bound leaf has no dispatchable logic: %s" % leaf)

    def test_bound_skills_listed_in_frontmatter(self):
        role = read_role_md()
        self.assertIsNotNone(role)
        for leaf in EXPECTED_BOUND:
            self.assertIn(leaf, role,
                          "missing in ROLE.md skills_bound: %s" % leaf)

    def test_workflow_stages_deterministic(self):
        role = read_role_md()
        idx = [role.find(stage) for stage in EXPECTED_STAGES]
        self.assertTrue(all(i >= 0 for i in idx), "a stage is missing")
        self.assertEqual(idx, sorted(idx),
                         "stage order not deterministic")

    def test_deliverable_template_complete(self):
        if not os.path.exists(TEMPLATE):
            self.fail("qms-audit-report-template.md missing")
        text = open(TEMPLATE).read()
        for n in [1, 2, 3, 4, 5, 6, 7, 8]:
            self.assertTrue(re.search(r"^## %d\. " % n, text, re.M),
                            "section %d missing" % n)
        self.assertEqual(len(re.findall(r"___|TODO|TBD", text)), 0,
                         "template must be a FILLED deliverable (0 blanks)")
        low = text.lower()
        self.assertIn("draft", low)
        self.assertIn("not an approval", low)
        self.assertIn("not a certification", low)
        self.assertIn("as9100d", low)

    def test_forbidden_lines_present(self):
        role = read_role_md()
        for phrase in ["issue QMS certification", "close a finding",
                       "sign_off_required: true", "reproduce AS9100D"]:
            self.assertIn(phrase, role, "missing boundary: %s" % phrase)

    def test_sources_register_exists(self):
        p = os.path.join(ROLE_DIR, "SOURCES.md")
        self.assertTrue(os.path.exists(p), "SOURCES.md missing for role")
        text = open(p).read()
        self.assertIn("AS9100D", text)
        self.assertIn("summary", text.lower())

    def test_core_engine_exists(self):
        """100% standard: every role ships an executable core + cli."""
        for f in ["core", "cli.py", "templates"]:
            self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, f)),
                            "%s missing - role is not executable" % f)

    def test_author_ashfordeou(self):
        role = read_role_md()
        self.assertIn("author: ashfordeOU", role, "author not set")

    def test_no_approval_claims_in_template(self):
        text = open(TEMPLATE).read()
        for phrase in ["certified", "approved by", "conforms to AS9100"]:
            self.assertNotIn(phrase.lower(), text.lower(),
                             "template must not claim approval: %s" % phrase)


if __name__ == "__main__":
    unittest.main()
