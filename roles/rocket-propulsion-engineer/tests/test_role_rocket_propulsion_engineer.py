#!/usr/bin/env python3
"""Role test: Rocket Propulsion Engineer.

Verifies (offline, no network):
1. Every skill bound in ROLE.md frontmatter RESOLVES to a real leaf in
   the aero-agent-skills repo (the propulsion/rocket cluster).
2. The workflow stage order is deterministic and complete.
3. The deliverable template is a FILLED worked example with no blank
   sections, DRAFT markers, and no approval claims.
4. The 100% standard anatomy is present: core engine, cli.py, SOURCES.
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
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "rocket-propulsion-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates",
                        "rocket-propulsion-report-template.md")

EXPECTED_BOUND = [
    "propulsion/rocket/cold-gas-thruster",
    "propulsion/rocket/combustion-chamber-design",
    "propulsion/rocket/hybrid-rocket-motor",
    "propulsion/rocket/injector-design",
    "propulsion/rocket/nozzle-design",
    "propulsion/rocket/propellant-selection",
    "propulsion/rocket/rocket-engine-cycle",
    "propulsion/rocket/rocket-gravity-loss",
    "propulsion/rocket/rocket-nozzle-flow-separation",
    "propulsion/rocket/rocket-sizing",
    "propulsion/rocket/rocket-staging",
    "propulsion/rocket/solid-rocket-motor",
    "propulsion/rocket/thrust-chamber-cooling",
    "propulsion/rocket/thrust-vector-control",
]

EXPECTED_STAGES = [
    "Mission requirements and propellant screening",
    "Staging and sizing",
    "Powered-ascent gravity-loss accounting",
    "Engine cycle and feed system",
    "Thrust-chamber design",
    "Nozzle design and flow separation",
    "Thrust-chamber cooling",
    "Injection and thrust-vector control",
    "Upper stage and reaction control",
    "Alternate concepts screening",
    "Performance summary and open items",
]


def read_role_md():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    if not os.path.exists(p):
        return None
    return open(p).read()


class TestRocketPropulsionRole(unittest.TestCase):

    def test_bound_skills_resolve_in_aeroskills(self):
        if not HAS_SKILLS:
            self.skipTest("Aero Agent Skills checkout not present "
                          "(cross-repo dev check)")
        for leaf in EXPECTED_BOUND:
            sk = os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")
            self.assertTrue(os.path.exists(sk),
                            f"bound skill not found in aero-agent-skills: "
                            f"{leaf}")
            logic = os.path.join(AEROSKILLS, "skills", leaf, "scripts")
            self.assertTrue(os.path.isdir(logic),
                            f"bound leaf has no scripts dir: {leaf}")

    def test_bound_skills_listed_in_frontmatter(self):
        role = read_role_md()
        self.assertIsNotNone(role)
        for leaf in EXPECTED_BOUND:
            self.assertIn(leaf, role,
                          f"missing in ROLE.md skills_bound: {leaf}")

    def test_all_fourteen_rocket_leaves_bound(self):
        role = read_role_md()
        fm = role.split("---", 2)[1]
        in_block = False
        bound = []
        for line in fm.splitlines():
            if line.strip().startswith("skills_bound:"):
                in_block = True
                continue
            if in_block:
                if re.match(r"^\s+-\s+", line):
                    bound.append(line.strip().lstrip("- ").strip())
                elif line.strip() and not line.startswith(" "):
                    break
        self.assertEqual(len(bound), 14,
                         "all 14 propulsion/rocket leaves must be bound")
        self.assertTrue(all(b.startswith("propulsion/rocket/")
                            for b in bound))

    def test_workflow_stages_deterministic(self):
        role = read_role_md()
        # every expected stage appears in order (indexes ascending)
        idx = [role.find(stage) for stage in EXPECTED_STAGES]
        self.assertTrue(all(i >= 0 for i in idx), "a stage is missing")
        self.assertEqual(idx, sorted(idx),
                         "stage order not deterministic")

    def test_deliverable_template_complete(self):
        if not os.path.exists(TEMPLATE):
            self.fail("rocket-propulsion-report-template.md missing")
        text = open(TEMPLATE).read()
        # all 13 numbered sections present
        for n in range(1, 14):
            self.assertTrue(re.search(rf"^## {n}\. ", text, re.M),
                            f"section {n} missing")
        low = text.lower()
        self.assertIn("draft", low)
        self.assertIn("not an approval", low)
        self.assertIn("not a launch readiness decision", low)
        # no blank template fields
        self.assertNotIn("___", text)
        self.assertNotIn("TBD", text)
        # numbers present
        self.assertIn("m/s", text)
        self.assertIn("MPa", text)
        self.assertIn("kg", text)

    def test_forbidden_lines_present(self):
        role = read_role_md()
        for phrase in ["launch readiness", "sign_off_required: true",
                       "reproduce"]:
            self.assertIn(phrase, role, f"missing boundary: {phrase}")

    def test_sources_register_exists(self):
        p = os.path.join(ROLE_DIR, "SOURCES.md")
        self.assertTrue(os.path.exists(p), "SOURCES.md missing for role")

    def test_core_engine_exists(self):
        """100% standard: every role ships an executable core + cli."""
        for f in ["core", "cli.py"]:
            self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, f)),
                            f"{f} missing - role is not executable")
        core_files = os.listdir(os.path.join(ROLE_DIR, "core"))
        self.assertTrue(any(f.endswith("_core.py") for f in core_files))

    def test_author_ashfordeou(self):
        role = read_role_md()
        self.assertIn("author: ashfordeOU", role)

    def test_standalone_build_and_check(self):
        """The role runs STANDALONE: cli build + check with no skills repo."""
        import subprocess
        import tempfile
        env = dict(os.environ, AEROSKILLS_DEV="/nonexistent")
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "report.md")
            b = subprocess.run([sys.executable, os.path.join(ROLE_DIR,
                                                             "cli.py"),
                                "build", "--out", out],
                               capture_output=True, text=True, env=env)
            self.assertEqual(b.returncode, 0, b.stdout + b.stderr)
            c = subprocess.run([sys.executable, os.path.join(ROLE_DIR,
                                                             "cli.py"),
                                "check", "--file", out],
                               capture_output=True, text=True, env=env)
            self.assertEqual(c.returncode, 0, c.stdout)
            self.assertIn("RESULT: PASS", c.stdout)


if __name__ == "__main__":
    unittest.main()
