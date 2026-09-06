#!/usr/bin/env python3
"""Role test: Composite Structures Engineer.

Verifies (offline, no network):
1. Every skill bound in ROLE.md frontmatter RESOLVES to a real leaf in
   the AeroSkills repo (the pinned skills_release band) and ships a
   logic file the role can dispatch.
2. Dispatch cross-checks: the role core and the bound leaf logic agree
   on the computed numbers (two independent implementations).
3. The filled deliverable template is complete (zero blanks), matches
   the engine's own worked-example output, and carries the DRAFT /
   not-an-approval / not-a-certification markers.
4. Standalone mode: cli.py build + check work with no skills repo.
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))          # repo root (4 up from tests/)
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "composites-structures-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates",
                        "composite-analysis-report-template.md")

EXPECTED_BOUND = [
    "structures/composites/adhesive-bonded-joints",
    "structures/composites/cmh17-allowables",
    "structures/composites/composite-bolted-joints",
    "structures/composites/composite-repair",
    "structures/composites/delamination-growth",
    "structures/composites/failure-criteria",
    "structures/composites/laminate-first-ply-failure",
    "structures/composites/laminate-hygrothermal-response",
    "structures/composites/laminate-plate-buckling",
    "structures/composites/laminate-stiffness",
    "structures/composites/peel-stress-bonded-joints",
    "structures/composites/sandwich-panels",
]

EXPECTED_STAGES = [
    "1. Allowables basis", "2. Laminate stiffness",
    "3. Failure criteria", "4. Hygrothermal response",
    "5. Stability", "6. Joints and details",
    "7. Damage and repair",
]


def read_role_md():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    if not os.path.exists(p):
        return None
    return open(p).read()


class TestCompositesRole(unittest.TestCase):

    def test_bound_skills_resolve_in_aeroskills(self):
        if not HAS_SKILLS:
            self.skipTest("Aero Agent Skills checkout not present "
                          "(cross-repo dev check)")
        for leaf in EXPECTED_BOUND:
            sk = os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")
            self.assertTrue(os.path.exists(sk),
                            "bound skill not found: %s" % leaf)

    def test_bound_leaves_ship_logic_files(self):
        if not HAS_SKILLS:
            self.skipTest("Aero Agent Skills checkout not present")
        for leaf in EXPECTED_BOUND:
            scripts = os.path.join(AEROSKILLS, "skills", leaf, "scripts")
            self.assertTrue(os.path.isdir(scripts),
                            "leaf %s has no scripts/ dir" % leaf)
            logic = [f for f in os.listdir(scripts)
                     if f.endswith("_logic.py")]
            self.assertTrue(logic, "leaf %s has no logic file" % leaf)

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

    def test_dispatch_crosschecks_agree(self):
        if not HAS_SKILLS:
            self.skipTest("Aero Agent Skills checkout not present")
        sys.path.insert(0, os.path.join(ROLE_DIR, "core"))
        sys.path.insert(0, os.path.join(ROLE_DIR, "..", "..", "scripts"))
        sys.path.insert(0, ROLE_DIR)
        import composites_structures_core as core
        import cli
        item = core.example_item()
        model = core.build_report(item)
        rows = cli._dispatch_all(item, model)
        self.assertGreaterEqual(len(rows), 6,
                                "expected >= 6 dispatched cross-checks")
        for row in rows:
            self.assertNotIn("error", row, "dispatch error: %s" % row)
            self.assertTrue(row["agrees"],
                            "cross-check disagrees: %s" % row)

    def test_filled_template_zero_blanks(self):
        self.assertTrue(os.path.exists(TEMPLATE),
                        "composite report template missing")
        text = open(TEMPLATE).read()
        self.assertNotRegex(text, r"___")
        self.assertNotRegex(text, r"TODO|TBD")
        # all 7 numbered sections present
        for n in range(1, 8):
            self.assertTrue(re.search(rf"^## {n}\. ", text, re.M),
                            "section %d missing" % n)

    def test_template_matches_engine_output(self):
        """The template IS the engine's filled worked example."""
        os.environ["ROLE_GEN_DATE"] = "2026-09-06"
        sys.path.insert(0, os.path.join(ROLE_DIR, "core"))
        import composites_structures_core as core
        rendered = core.example_report_markdown().strip()
        with open(TEMPLATE) as fh:
            self.assertEqual(rendered, fh.read().strip())

    def test_boundaries(self):
        role = read_role_md()
        for phrase in ["issue certification approval", "airworthiness approval",
                       "sign_off_required: true", "not a certification"]:
            self.assertIn(phrase, role, "missing boundary: %s" % phrase)
        low = role.lower()
        for phrase in ["not an approval", "reproduce proprietary",
                       "statistical basis"]:
            self.assertIn(phrase, low, "missing boundary: %s" % phrase)

    def test_sources_and_executable_anatomy(self):
        for f in ["SOURCES.md", "cli.py", "core", "tests"]:
            self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, f)),
                            "%s missing - role is not executable" % f)
        sources = open(os.path.join(ROLE_DIR, "SOURCES.md")).read()
        self.assertIn("CMH-17", sources)
        self.assertIn("summary", sources.lower())

    def test_cli_standalone_build_and_check(self):
        """cli.py build + check work with no skills repo (exit 0)."""
        cli = os.path.join(ROLE_DIR, "cli.py")
        env = dict(os.environ, AEROSKILLS_DEV="/nonexistent",
                   ROLE_GEN_DATE="2026-09-06")
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "report.md")
            r = subprocess.run([sys.executable, cli, "build", "--out", out],
                               capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            r = subprocess.run([sys.executable, cli, "check",
                                "--file", out],
                               capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
