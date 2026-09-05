#!/usr/bin/env python3
"""Role test: Flight Test Performance Engineer.

Verifies (offline, no network):
1. Every skill bound in ROLE.md frontmatter RESOLVES to a real leaf in
   the aero-agent-skills repo (the pinned skills_release band).
2. The workflow stage order is deterministic and complete.
3. The filled deliverable template (worked example) has zero blanks,
   numbered sections, and the honest DRAFT / not-an-approval markers.
4. The role carries the executable core + cli (100% standard) and the
   boundary/forbidden lines, and metadata credits the author.
"""
import os
import re
import sys
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))          # repo root
sys.path.insert(0, os.path.join(ROLES_REPO, "roles",
                                "flight-test-performance-engineer", "core"))
import flight_test_performance_core as core  # noqa: E402
AEROSKILLS = os.environ.get("AEROSKILLS_DEV",
                            os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles",
                        "flight-test-performance-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates",
                        "performance-report-template.md")

EXPECTED_BOUND = [
    "flight-test-operations/performance/takeoff-distance-determination",
    "flight-test-operations/performance/accelerate-stop-distance",
    "flight-test-operations/performance/engine-failure-takeoff-flight-test",
    "flight-test-operations/performance/landing-distance-determination",
    "flight-test-operations/performance/level-acceleration-test",
    "flight-test-operations/performance/cruise-performance-flight-test",
    "flight-test-operations/performance/climb-performance-flight-test",
    "flight-test-operations/performance/engine-flight-test",
    "flight-test-operations/performance/stall-speed-determination",
    "flight-test-operations/performance/glide-flight-test",
    "flight-test-operations/performance/fuel-jettison-flight-test",
    "flight-test-operations/performance/in-flight-engine-relight-test",
    "flight-test-operations/performance/rotorcraft-performance-flight-test",
    "flight-test-operations/performance/"
    "rotorcraft-forward-flight-performance-test",
    "flight-test-operations/planning/flight-test-data-reduction",
]

EXPECTED_STAGES = [
    "1. Data reduction prep", "2. Conditions", "3. Takeoff",
    "4. Landing", "5. Level accel", "6. Cruise", "7. Speeds",
    "8. Climb / other", "9. Rotorcraft (if rotary)", "10. Report",
]


def read_role_md():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    if not os.path.exists(p):
        return None
    return open(p).read()


class TestFlightTestPerformanceRole(unittest.TestCase):

    def test_bound_skills_resolve_in_aeroskills(self):
        if not HAS_SKILLS:
            self.skipTest("Aero Agent Skills checkout not present "
                          "(cross-repo dev check)")
        for leaf in EXPECTED_BOUND:
            sk = os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")
            self.assertTrue(
                os.path.exists(sk),
                "bound skill not found in aero-agent-skills: %s" % leaf)

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
            self.fail("performance-report-template.md missing")
        text = open(TEMPLATE).read()
        self.assertNotIn("___", text, "template has blank fields")
        # numbered sections 1..8 present
        for n in range(1, 9):
            self.assertTrue(
                re.search(r"^## %d\. " % n, text, re.M),
                "section %d missing" % n)
        self.assertIn("Flight Test Performance Data Analysis Report", text)
        low = text.lower()
        self.assertIn("draft", low)
        self.assertIn("not an approval", low)
        self.assertIn("performance guarantee", low)

    def test_template_is_the_worked_example(self):
        """The filled template matches the core's example render."""
        template = open(TEMPLATE).read().strip()
        rendered = core.example_report_markdown().strip()
        self.assertEqual(template, rendered)

    def test_forbidden_lines_present(self):
        role = read_role_md()
        for phrase in ["clear an envelope", "declare airworthiness",
                       "authorize flight", "performance guarantee",
                       "sign_off_required: true", "reproduce proprietary"]:
            self.assertIn(phrase, role, "missing boundary: %s" % phrase)

    def test_author_ashfordeou(self):
        role = read_role_md()
        self.assertIn("ashfordeOU", role)

    def test_sources_register_exists(self):
        p = os.path.join(ROLE_DIR, "SOURCES.md")
        self.assertTrue(os.path.exists(p), "SOURCES.md missing for role")

    def test_core_engine_exists(self):
        """100% standard: every role ships an executable core + cli."""
        for f in ["core", "cli.py"]:
            self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, f)),
                            "%s missing - role is not executable" % f)
        core_files = [f for f in os.listdir(os.path.join(ROLE_DIR, "core"))
                      if f.endswith("_core.py")]
        self.assertEqual(len(core_files), 1)

    def test_standalone_cli_smoke(self):
        """cli.py build must run with no AeroSkills checkout."""
        import subprocess
        env = dict(os.environ)
        env["AEROSKILLS_DEV"] = "/nonexistent"
        out = os.path.join(ROLE_DIR, "tests", ".smoke-report.md")
        try:
            r = subprocess.run(
                [sys_executable(), os.path.join(ROLE_DIR, "cli.py"),
                 "build", "--out", out],
                capture_output=True, text=True, env=env, cwd=ROLE_DIR)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            md = open(out).read()
            self.assertIn("Flight Test Performance Data Analysis Report",
                          md)
        finally:
            if os.path.exists(out):
                os.remove(out)


def sys_executable():
    import sys
    return sys.executable


if __name__ == "__main__":
    unittest.main()
