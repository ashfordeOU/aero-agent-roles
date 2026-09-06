#!/usr/bin/env python3
"""Role test: ADCS Engineer.

Verifies (offline, no network):
1. Every skill bound in ROLE.md frontmatter (the 14-leaf
   space-systems/adcs cluster) RESOLVES to a real leaf in the
   aero-agent-skills repo (the pinned skills_release band).
2. The workflow stage order is deterministic and complete.
3. The deliverable template is a FILLED worked example (no blanks).
4. The role is executable: cli build + check pass, and with AeroSkills
   present the six dispatch cross-checks agree (provenance.json).
"""
import json
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
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "adcs-engineer")
REPORT_TEMPLATE = os.path.join(ROLE_DIR, "templates",
                               "adcs-subsystem-report-template.md")

EXPECTED_BOUND = [
    "space-systems/adcs/attitude-control-sizing",
    "space-systems/adcs/attitude-determination-quest",
    "space-systems/adcs/attitude-determination-triad",
    "space-systems/adcs/control-moment-gyro",
    "space-systems/adcs/environmental-disturbance-torque-budget",
    "space-systems/adcs/gravity-gradient-stabilization",
    "space-systems/adcs/gyro-allan-variance",
    "space-systems/adcs/magnetometer-calibration",
    "space-systems/adcs/magnetorquer-control",
    "space-systems/adcs/pointing-error-budget",
    "space-systems/adcs/reaction-jet-limit-cycle",
    "space-systems/adcs/reaction-wheel-control",
    "space-systems/adcs/star-tracker",
    "space-systems/adcs/sun-pointing",
]

# Stage names as written in the ROLE.md workflow table, in order.
EXPECTED_STAGES = [
    "Pointing requirements",
    "Disturbance environment",
    "Passive stabilization screen",
    "Sensor suite",
    "Magnetometer calibration",
    "Sun acquisition / safe hold",
    "Coarse determination (TRIAD)",
    "Fine determination (QUEST)",
    "Gyro noise characterization",
    "Momentum actuation",
    "CMG screen",
    "RCS screen",
    "Magnetic actuation",
    "Actuator sizing and margins",
]

EXPECTED_DISPATCH_LEAVES = [
    "space-systems/adcs/attitude-determination-triad",
    "space-systems/adcs/attitude-determination-quest",
    "space-systems/adcs/reaction-wheel-control",
    "space-systems/adcs/magnetorquer-control",
    "space-systems/adcs/pointing-error-budget",
    "space-systems/adcs/gyro-allan-variance",
]


def read_role_md():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    if not os.path.exists(p):
        return None
    return open(p).read()


class TestAdcsRole(unittest.TestCase):

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
            self.assertIn(leaf, role, f"missing in ROLE.md: {leaf}")

    def test_workflow_stages_deterministic(self):
        role = read_role_md()
        idx = [role.find(stage) for stage in EXPECTED_STAGES]
        self.assertTrue(all(i >= 0 for i in idx), "a stage is missing")
        self.assertEqual(idx, sorted(idx), "stage order not deterministic")

    def test_deliverable_template_complete(self):
        if not os.path.exists(REPORT_TEMPLATE):
            self.fail("adcs-subsystem-report-template.md missing")
        text = open(REPORT_TEMPLATE).read()
        for n in range(1, 9):
            self.assertTrue(
                re.search(rf"^## {n}\. ", text, re.M),
                f"section {n} missing")
        self.assertIn("DRAFT", text)
        low = text.lower()
        self.assertIn("not an approval", low)
        self.assertNotIn("___", text)
        self.assertNotIn("TODO", text)
        # the worked example carries the real computed numbers
        self.assertIn("Attitude Determination and Control Subsystem Report",
                      text)
        self.assertIn("arcsec", low)

    def test_forbidden_lines_present(self):
        role = read_role_md()
        for phrase in ["claim certification approval", "flight-readiness",
                       "reproduce ECSS", "sign_off_required: true"]:
            self.assertIn(phrase, role, f"missing boundary: {phrase}")

    def test_sources_register_exists(self):
        p = os.path.join(ROLE_DIR, "SOURCES.md")
        self.assertTrue(os.path.exists(p), "SOURCES.md missing for role")

    def test_core_engine_exists(self):
        """100% standard: every role ships an executable core + cli."""
        for f in ["core", "cli.py"]:
            self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, f)),
                            f"{f} missing - role is not executable")

    def test_cli_build_and_check_standalone(self):
        """Executable role smoke: cli build + check exit 0 with no skills."""
        env = dict(os.environ, AEROSKILLS_DEV="/nonexistent")
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "report.md")
            r = subprocess.run([sys.executable,
                                os.path.join(ROLE_DIR, "cli.py"),
                                "build", "--out", out],
                               capture_output=True, text=True, env=env,
                               cwd=ROLES_REPO)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(os.path.exists(out))
            r2 = subprocess.run([sys.executable,
                                 os.path.join(ROLE_DIR, "cli.py"),
                                 "check", "--file", out],
                                capture_output=True, text=True, env=env,
                                cwd=ROLES_REPO)
            self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
            self.assertIn("RESULT: PASS", r2.stdout)

    def test_dispatch_crosschecks_agree(self):
        """With AeroSkills present, all six dispatch rows must agree."""
        if not HAS_SKILLS:
            self.skipTest("Aero Agent Skills checkout not present "
                          "(cross-repo dev check)")
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "report.md")
            r = subprocess.run([sys.executable,
                                os.path.join(ROLE_DIR, "cli.py"),
                                "build", "--out", out, "--bundle"],
                               capture_output=True, text=True, env=os.environ,
                               cwd=ROLES_REPO)
            self.assertEqual(r.returncode, 0, r.stderr)
            prov = json.load(open(os.path.join(tmp, "evidence",
                                               "provenance.json")))
            rows = prov["skills"]
            self.assertEqual(len(rows), len(EXPECTED_DISPATCH_LEAVES))
            for row in rows:
                self.assertFalse(row.get("error"), row)
                self.assertTrue(row["dispatched"], row)
                self.assertTrue(row["agrees"], row)
            self.assertTrue(prov["cross_checked"])
            # every dispatched leaf is a bound space-systems/adcs leaf
            self.assertEqual(
                {row["leaf"] for row in rows}, set(EXPECTED_DISPATCH_LEAVES))


if __name__ == "__main__":
    unittest.main()
