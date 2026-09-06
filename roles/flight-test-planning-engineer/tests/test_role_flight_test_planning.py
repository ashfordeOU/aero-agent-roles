#!/usr/bin/env python3
"""Role test: Flight Test Planning Engineer.

Author: ashfordeOU · Aero Agent Roles.

Verifies (offline, no network):
1. Every skill bound in ROLE.md frontmatter RESOLVES to a real leaf in
   the aero-agent-skills tree (the pinned skills_release band) and each
   leaf ships a logic module.
2. The workflow stage order is deterministic and complete.
3. Evidence-gate smoke: the worked example (the certification flight
   test campaign of an FGS-2000-equipped transport airplane) produces a
   complete Flight Test Plan template with all 12 sections, no blank
   fields and honest draft markers.
"""
import os
import re
import sys
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))          # repo root (4 up from tests/)
# Bound-skill resolution requires the Aero Agent Skills checkout. It is a
# cross-repo dev check: when the skills repo is absent (fresh public
# clone), skip resolution rather than fail - the role's bound list is
# verified in CI.
AEROSKILLS = os.environ.get("AEROSKILLS_DEV",
                            os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "flight-test-planning-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates",
                        "flight-test-plan-template.md")

EXPECTED_BOUND = [
    "flight-test-operations/planning/flight-test-instrumentation",
    "flight-test-operations/planning/flight-test-planning",
    "flight-test-operations/planning/noise-certification-test",
    "flight-test-operations/planning/pcm-telemetry-decommutation",
    "flight-test-operations/planning/position-error-calibration",
    "flight-test-operations/planning/telemetry-data-acquisition",
    "flight-test-operations/planning/test-point-matrix-design",
]

EXPECTED_STAGES = [
    "Program basis & requirements traceability",
    "Test point matrix design",
    "Instrumentation design & release",
    "Telemetry & data acquisition design",
    "PCM telemetry decommutation plan",
    "Airspeed position error calibration (PEC) campaign",
    "Noise certification measurement campaign",
    "Build-up sequencing & go/no-go gating",
    "Plan issue, evidence gates & traceability close-out",
]


def read_role_md():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    if not os.path.exists(p):
        return None
    return open(p).read()


class TestFlightTestPlanningRole(unittest.TestCase):

    def test_bound_skills_resolve_in_aeroskills(self):
        if not HAS_SKILLS:
            self.skipTest("Aero Agent Skills checkout not present "
                          "(cross-repo dev check)")
        for leaf in EXPECTED_BOUND:
            sk = os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")
            self.assertTrue(
                os.path.exists(sk),
                "bound skill not found in aero-agent-skills: %s" % leaf)
            logic = os.path.join(AEROSKILLS, "skills", leaf, "scripts")
            logic_files = [f for f in os.listdir(logic)
                           if f.endswith("_logic.py")] \
                if os.path.isdir(logic) else []
            self.assertTrue(logic_files,
                            "bound leaf ships no logic file: %s" % leaf)

    def test_bound_skills_listed_in_frontmatter(self):
        role = read_role_md()
        self.assertIsNotNone(role)
        for leaf in EXPECTED_BOUND:
            self.assertIn(leaf, role,
                          "missing in ROLE.md skills_bound: %s" % leaf)

    def test_frontmatter_metadata(self):
        role = read_role_md()
        for token in ["type: role", "name: flight-test-planning-engineer",
                      "title: \"Flight Test Planning Engineer\"",
                      "status: draft",
                      "domain: flight-test-operations",
                      "deliverable_type: \"Flight Test Plan and "
                      "Requirements Traceability\"",
                      "tools_allowed: [stdlib, offline-file-processing]",
                      "sign_off_required: true", "license: Apache-2.0",
                      "author: ashfordeOU", "skills_release: \"v1.3.0+\""]:
            self.assertIn(token, role, "frontmatter missing: %s" % token)

    def test_workflow_stages_deterministic(self):
        role = read_role_md()
        # Parse the workflow stage column from the markdown table under
        # "## Workflow": rows like "| 1. Stage name | ... |"
        wf = role.split("## Workflow", 1)[1]
        wf = wf.split("## Evidence gates", 1)[0]
        stage_rows = re.findall(r"^\|\s*(\d+)\.\s+([^|]+?)\s*\|", wf, re.M)
        self.assertGreaterEqual(len(stage_rows), len(EXPECTED_STAGES),
                                "workflow table has too few rows")
        parsed = [name.strip() for _, name in stage_rows]
        numbers = [int(n) for n, _ in stage_rows]
        self.assertEqual(numbers, sorted(numbers),
                         "workflow stage numbers not ascending")
        self.assertEqual(parsed[:len(EXPECTED_STAGES)], EXPECTED_STAGES,
                         "workflow stage order/names mismatch")

    def test_deliverable_template_complete(self):
        if not os.path.exists(TEMPLATE):
            self.fail("flight-test-plan-template.md missing")
        text = open(TEMPLATE).read()
        # all 12 numbered sections present
        for n in range(1, 13):
            self.assertTrue(
                re.search(r"^## %d\. " % n, text, re.M),
                "section %d missing" % n)
        self.assertEqual(text.count("_" * 3), 0, "template has blank fields")
        self.assertIn("DRAFT", text)
        low = text.lower()
        self.assertIn("not an approval", low)
        self.assertIn("document", low)
        self.assertIn("go/no-go", low)

    def test_forbidden_lines_present(self):
        role = read_role_md()
        for phrase in ["issue certification approval", "regulatory sign-off",
                       "reproduce proprietary", "sign_off_required: true",
                       "go/no-go authority"]:
            self.assertIn(phrase, role, "missing boundary: %s" % phrase)

    def test_sources_register_exists(self):
        p = os.path.join(ROLE_DIR, "SOURCES.md")
        self.assertTrue(os.path.exists(p), "SOURCES.md missing for role")
        text = open(p).read()
        for leaf in EXPECTED_BOUND:
            self.assertIn(leaf.rsplit("/", 1)[-1], text,
                          "SOURCES.md missing bound leaf %s" % leaf)

    def test_core_engine_exists(self):
        """100% standard: every role ships an executable core + cli."""
        for f in ["core", "cli.py"]:
            self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, f)),
                            "%s missing - role is not executable" % f)
        core_dir = os.path.join(ROLE_DIR, "core")
        self.assertTrue(any(f.endswith("_core.py")
                            for f in os.listdir(core_dir)),
                        "no *_core.py engine present")

    def test_no_local_paths_in_role_files(self):
        """No machine-local absolute paths anywhere in the role files."""
        local_marker = "/" + "Users" + "/"
        blank_marker = "_" * 3
        todo_marker = "TO" + "DO"
        for root, _dirs, files in os.walk(ROLE_DIR):
            for f in files:
                if f.endswith(".pyc"):
                    continue
                path = os.path.join(root, f)
                text = open(path).read()
                self.assertNotIn(local_marker, text,
                                 "local path in %s" % path)
                self.assertNotIn(blank_marker, text,
                                 "blank field in %s" % path)
                self.assertNotIn(todo_marker, text)


if __name__ == "__main__":
    unittest.main()
