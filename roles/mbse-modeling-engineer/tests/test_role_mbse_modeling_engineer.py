#!/usr/bin/env python3
"""Role test: MBSE Modeling Engineer.

Verifies (offline, no network):
1. Every skill bound in ROLE.md frontmatter RESOLVES to a real leaf in
   the aero-agent-skills repo (the pinned skills_release band).
2. The workflow stage order is deterministic and complete.
3. The deliverable template is a complete worked example with zero
   blanks, numbered sections, and the honesty markers.
4. The role anatomy (executable core + cli + tests) is present.
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
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "mbse-modeling-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates", "mbse-plan-template.md")

EXPECTED_BOUND = [
    "systems-engineering-safety/mbse/requirements-modeling",
    "systems-engineering-safety/mbse/sysml-modeling",
    "systems-engineering-safety/mbse/systems-engineering",
    "systems-engineering-safety/mbse/n2-diagram",
    "systems-engineering-safety/mbse/state-machine",
    "systems-engineering-safety/mbse/trade-study-analysis",
]

# Canonical MBSE stages (from the systems-engineering leaf) in the order
# the Workflow table must present them.
EXPECTED_STAGES = [
    "Requirements modeling", "Functional architecture",
    "Logical architecture", "Allocation", "Analysis", "Traceability",
]

EXPECTED_SECTIONS = [
    "## 1. Scope", "## 2. Model architecture (diagram suite)",
    "## 3. Viewpoint coverage", "## 4. Requirements architecture",
    "## 5. Functional and logical architecture",
    "## 6. Block definition and internal structure",
    "## 7. Interface model (N2)", "## 8. Behavioral model",
    "## 9. Parametric constraints", "## 10. Traceability and model review",
    "## 11. Model governance",
]


def read_role_md():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    if not os.path.exists(p):
        return None
    return open(p).read()


def workflow_table_text(role):
    """The ROLE.md Workflow table region only (robust ordering check)."""
    start = role.find("## Workflow")
    end = role.find("## Evidence gates")
    if start < 0 or end < 0 or end < start:
        return ""
    return role[start:end]


class TestMbseRole(unittest.TestCase):

    def test_bound_skills_resolve_in_aeroskills(self):
        if not HAS_SKILLS:
            self.skipTest("Aero Agent Skills checkout not present "
                          "(cross-repo dev check)")
        for leaf in EXPECTED_BOUND:
            sk = os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")
            self.assertTrue(
                os.path.exists(sk),
                "bound skill not found in aero-agent-skills: %s" % leaf)

    def test_bound_skills_have_logic_files(self):
        """100% standard: bound leaves deepen the workflow with logic."""
        if not HAS_SKILLS:
            self.skipTest("Aero Agent Skills checkout not present")
        for leaf in EXPECTED_BOUND:
            scripts = os.path.join(AEROSKILLS, "skills", leaf, "scripts")
            logic = [f for f in os.listdir(scripts)
                     if f.endswith(".py") and not f.startswith("test_")] \
                if os.path.isdir(scripts) else []
            self.assertTrue(logic, "bound leaf has no logic file: %s" % leaf)

    def test_bound_skills_listed_in_frontmatter(self):
        role = read_role_md()
        self.assertIsNotNone(role)
        for leaf in EXPECTED_BOUND:
            self.assertIn(leaf, role, "missing in ROLE.md skills_bound: "
                          + leaf)

    def test_workflow_stages_deterministic(self):
        role = read_role_md()
        table = workflow_table_text(role)
        # every expected stage appears inside the Workflow table
        idx = [table.find(stage) for stage in EXPECTED_STAGES]
        self.assertTrue(all(i >= 0 for i in idx), "a stage is missing "
                        "from the workflow table")
        self.assertEqual(idx, sorted(idx),
                         "stage order not deterministic in workflow table")

    def test_deliverable_template_complete(self):
        if not os.path.exists(TEMPLATE):
            self.fail("mbse-plan-template.md missing")
        text = open(TEMPLATE).read()
        for sec in EXPECTED_SECTIONS:
            self.assertIn(sec, text, "section %r missing" % sec)
        self.assertNotIn("___", text)
        low = text.lower()
        self.assertIn("draft", low)
        self.assertIn("not an approval", low)
        self.assertIn("Cabin Pressure Control System", text)

    def test_forbidden_lines_present(self):
        role = read_role_md()
        for phrase in ["declare a model complete without traceability "
                       "closure", "claim engineering approval",
                       "reproduce proprietary", "sign_off_required: true"]:
            self.assertIn(phrase, role, "missing boundary: " + phrase)

    def test_sources_register_exists(self):
        p = os.path.join(ROLE_DIR, "SOURCES.md")
        self.assertTrue(os.path.exists(p), "SOURCES.md missing for role")

    def test_core_engine_exists(self):
        """100% standard: every role ships an executable core + cli."""
        for f in ["core", "cli.py"]:
            self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, f)),
                            "%s missing - role is not executable" % f)


if __name__ == "__main__":
    unittest.main()
