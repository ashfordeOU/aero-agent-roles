#!/usr/bin/env python3
"""Role test: Autopilot Control Engineer.

Verifies (offline, no network):
1. Every skill bound in ROLE.md frontmatter RESOLVES to a real leaf in
   the aero-agent-skills repo (the gnc-autonomy/control cluster).
2. The workflow stage order is deterministic and complete.
3. The deliverable template is a FILLED worked example with no blank
   sections, DRAFT markers, and no approval claims.
4. The 100% standard anatomy is present: core engine, cli.py, SOURCES.
5. The role runs standalone: cli build + check with no skills repo.
"""
import os
import re
import subprocess
import sys
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))          # repo root (4 up from tests/)
# Bound-skill resolution requires the Aero Agent Skills checkout. It is a
# cross-repo dev check: when the skills repo is absent (fresh public clone),
# skip resolution rather than fail - the role's bound list is verified in CI.
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "autopilot-control-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates",
                        "autopilot-control-law-package-template.md")
CORE_DIR = os.path.join(ROLE_DIR, "core")

sys.path.insert(0, CORE_DIR)
import autopilot_control_engineer_core as core  # noqa: E402

EXPECTED_BOUND = [
    "gnc-autonomy/control/l1-adaptive-control",
    "gnc-autonomy/control/python-control-design",
    "gnc-autonomy/control/root-locus-design",
    "gnc-autonomy/control/state-space-analysis",
    "gnc-autonomy/control/pid-control-design",
    "gnc-autonomy/control/lead-lag-compensation",
    "gnc-autonomy/control/frequency-response-design",
    "gnc-autonomy/control/digital-control-design",
    "gnc-autonomy/control/observer-design",
    "gnc-autonomy/control/control-allocation",
    "gnc-autonomy/control/gain-scheduling",
    "gnc-autonomy/control/adaptive-control",
]

EXPECTED_STAGES = [
    "State-space plant models",
    "Inner pitch-rate loop",
    "Outer pitch-attitude loop",
    "Roll-attitude loop",
    "Yaw-rate damper",
    "Observer",
    "L1 adaptive augmentation",
    "Gain schedule",
    "Digital implementation",
    "Control allocation",
]


def read_role_md():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    if not os.path.exists(p):
        return None
    return open(p).read()


class TestAutopilotControlEngineerRole(unittest.TestCase):

    def test_bound_skills_resolve_in_aeroskills(self):
        if not HAS_SKILLS:
            self.skipTest("Aero Agent Skills checkout not present "
                          "(cross-repo dev check)")
        for leaf in EXPECTED_BOUND:
            sk = os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")
            self.assertTrue(os.path.exists(sk),
                            f"bound skill not found in aero-agent-skills: "
                            f"{leaf}")

    def test_bound_skills_listed_in_frontmatter(self):
        role = read_role_md()
        self.assertIsNotNone(role)
        for leaf in EXPECTED_BOUND:
            self.assertIn(leaf, role,
                          f"missing in ROLE.md skills_bound: {leaf}")

    def test_all_twelve_control_leaves_bound(self):
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
        self.assertEqual(len(bound), 12,
                         "all 12 gnc-autonomy/control leaves must be bound")
        self.assertTrue(all(b.startswith("gnc-autonomy/control/")
                            for b in bound))
        self.assertEqual(sorted(bound), sorted(EXPECTED_BOUND))

    def test_workflow_stages_deterministic(self):
        role = read_role_md()
        wf = role[role.find("## Workflow"):role.find("## Evidence gates")]
        idx = [wf.find(stage) for stage in EXPECTED_STAGES]
        self.assertTrue(all(i >= 0 for i in idx), "a stage is missing")
        self.assertEqual(idx, sorted(idx),
                         "stage order not deterministic")

    def test_template_present(self):
        self.assertTrue(os.path.exists(TEMPLATE),
                        "deliverable template missing")

    def test_deliverable_template_complete(self):
        text = open(TEMPLATE).read()
        for n in range(1, 9):
            self.assertTrue(re.search(rf"^## {n}\. ", text, re.M),
                            f"section {n} missing")
        self.assertIn("Appendix A", text)
        low = text.lower()
        self.assertIn("draft", low)
        self.assertIn("not an approval", low)
        self.assertIn("not flight software release", low)
        self.assertNotIn("___", text)
        self.assertNotIn("TBD", text)
        self.assertIn("rad/s", text)
        self.assertIn("deg", text)

    def test_template_passes_core_gates(self):
        text = open(TEMPLATE).read()
        gates = core.check_package_markdown(text)
        self.assertTrue(gates["all_pass"], gates)

    def test_forbidden_lines_present(self):
        role = read_role_md()
        for phrase in ["certification approval", "sign_off_required: true",
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
        core_files = os.listdir(CORE_DIR)
        self.assertTrue(any(f.endswith("_core.py") for f in core_files))

    def test_core_standalone_example_gates(self):
        """Core produces a correct, gate-passing package with no skills."""
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = core.build_package(core.example_item())
        gates = core.check_package(model)
        self.assertTrue(gates["all_pass"], gates)
        md = core.example_package_markdown()
        mgates = core.check_package_markdown(md)
        self.assertTrue(mgates["all_pass"], mgates)

    def test_standalone_build_and_check(self):
        """The role runs STANDALONE: cli build + check with no skills repo."""
        import tempfile
        env = dict(os.environ, AEROSKILLS_DEV="/nonexistent")
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "package.md")
            b = subprocess.run([sys.executable,
                               os.path.join(ROLE_DIR, "cli.py"),
                               "build", "--out", out],
                              capture_output=True, text=True, env=env)
            self.assertEqual(b.returncode, 0, b.stdout + b.stderr)
            c = subprocess.run([sys.executable,
                               os.path.join(ROLE_DIR, "cli.py"),
                               "check", "--file", out],
                              capture_output=True, text=True, env=env)
            self.assertEqual(c.returncode, 0, c.stdout)
            self.assertIn("RESULT: PASS", c.stdout)


if __name__ == "__main__":
    unittest.main()
