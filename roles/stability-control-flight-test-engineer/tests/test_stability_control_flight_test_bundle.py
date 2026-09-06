#!/usr/bin/env python3
"""Test the evidence bundle + skill-dispatch protocol (PROTOCOL.md v1).

Verifies:
- build --bundle emits evidence/{model,gates,provenance}.json
- bundle JSON parses; model contains the computed stability & control
  numbers (static margin, Cn_beta estimate, damping ratios, rollup)
- the bound flight-test-operations/stability leaf logic modules
  dispatch and cross-check their numbers against the core (agree
  within tolerance) when AeroSkills is present
- standalone (no AeroSkills) emits the bundle honestly with
  cross_checked=false
- build --profile prepends a program context header
- check gate-checks a built report
"""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROLE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROLE_DIR, "cli.py")
PROFILE = os.path.normpath(os.path.join(ROLE_DIR, "..", "..", "profiles",
                                        "example-airframer.json"))

AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))

EXPECTED_DISPATCH_LEAVES = {
    "static-stability-flight-test", "dynamic-stability-flight-test",
    "lateral-directional-stability-flight-test",
    "control-force-flight-test",
}


def run_build(outdir, env_extra=None, extra_args=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    args = [sys.executable, CLI, "build", "--out",
            os.path.join(outdir, "report.md"), "--bundle"]
    if extra_args:
        args.extend(extra_args)
    r = subprocess.run(args, capture_output=True, text=True, env=env)
    return r


class TestBundleProtocol(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_bundle_emits_three_files(self):
        r = run_build(self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        ev = os.path.join(self.tmp, "evidence")
        for f in ("model.json", "gates.json", "provenance.json"):
            self.assertTrue(os.path.exists(os.path.join(ev, f)), f + " missing")

    def test_model_has_numbers_and_status(self):
        run_build(self.tmp)
        m = json.load(open(os.path.join(self.tmp, "evidence", "model.json")))
        self.assertEqual(m.get("status"), "draft-for-review")
        self.assertEqual(m["role"], "stability-control-flight-test-engineer")
        self.assertEqual(m["deliverable_type"],
                         "Stability and Control Flight Test Report")
        # the model must carry the numbers that appear in the markdown
        sm = m["static_longitudinal"]["stick_fixed"][
            "static_margin_fraction_mac"]
        self.assertAlmostEqual(sm, math.pi / 60.0, places=9)
        self.assertAlmostEqual(
            m["lateral_directional"]["gradients"][
                "cn_beta_estimate_per_rad"], 0.1104, places=9)
        self.assertAlmostEqual(
            m["dynamic_modes"][0]["damping_ratio"], 0.4100283, places=5)
        self.assertEqual(m["rollup"]["overall_gate"], "CLOSED")
        self.assertEqual(m["rollup"]["pass_count"], 11)

    def test_gates_all_pass_exit_zero(self):
        r = run_build(self.tmp)
        g = json.load(open(os.path.join(self.tmp, "evidence", "gates.json")))
        self.assertTrue(g["all_pass"])
        self.assertEqual(g["exit_code"], 0)
        self.assertGreaterEqual(len(g["gates"]), 6)

    def test_dispatch_crosschecks_when_skills_present(self):
        if not HAS_SKILLS:
            self.skipTest("AeroSkills not present")
        r = run_build(self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        p = json.load(open(os.path.join(self.tmp, "evidence",
                                        "provenance.json")))
        self.assertTrue(p["cross_checked"])
        leafs = {row["leaf"].rsplit("/", 1)[-1] for row in p["skills"]}
        self.assertEqual(leafs, EXPECTED_DISPATCH_LEAVES)
        for row in p["skills"]:
            self.assertTrue(row["dispatched"])
            self.assertTrue(row["agrees"],
                            "core/skill disagree for %s: %s"
                            % (row.get("function"), row))
        funcs = {row["function"] for row in p["skills"]}
        self.assertIn("trim_curve_fit", funcs)
        self.assertIn("mode_identification", funcs)
        self.assertIn("reduce_sideslip_sweep", funcs)
        self.assertIn("calibrate_force_transducer", funcs)

    def test_standalone_honest_no_skills(self):
        r = run_build(self.tmp, env_extra={"AEROSKILLS_DEV": "/nonexistent"})
        self.assertEqual(r.returncode, 0)
        p = json.load(open(os.path.join(self.tmp, "evidence",
                                        "provenance.json")))
        self.assertFalse(p["cross_checked"])
        self.assertEqual(len(p["skills"]), 0)

    def test_profile_header_applied(self):
        if not os.path.exists(PROFILE):
            self.skipTest("profiles/example-airframer.json not present")
        r = run_build(self.tmp, extra_args=["--profile", PROFILE])
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        md = open(os.path.join(self.tmp, "report.md")).read()
        self.assertIn("Example Airframers Ltd", md)
        self.assertIn("Program context (profile)", md)
        m = json.load(open(os.path.join(self.tmp, "evidence", "model.json")))
        self.assertEqual(m["profile"]["customer"], "Example Airframers Ltd")
        # the profile header must not remove the honesty markers
        low = md.lower()
        self.assertIn("not an approval", low)

    def test_check_still_works(self):
        run_build(self.tmp)
        md = os.path.join(self.tmp, "report.md")
        c = subprocess.run([sys.executable, CLI, "check", "--file", md],
                           capture_output=True, text=True)
        self.assertEqual(c.returncode, 0, c.stdout)
        self.assertIn("RESULT: PASS", c.stdout)


if __name__ == "__main__":
    unittest.main()
