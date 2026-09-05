#!/usr/bin/env python3
"""Test the evidence bundle + skill-dispatch protocol (PROTOCOL.md v1).

Verifies:
- build --bundle emits evidence/{model,gates,provenance}.json
- bundle JSON parses, model contains computed numbers, gates all_pass
- skill dispatch cross-checks the estimator computations against the
  bound estimation-filtering leaf logic (agreeing within tolerance)
  when AeroSkills is present
- standalone (no AeroSkills) emits the bundle honestly with
  cross_checked=false
- check --file passes the gate vocabulary
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROLE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROLE_DIR, "cli.py")

AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))

EXPECTED_DISPATCH_FNS = ["steady_state_gains", "gains_from_tracking_index",
                         "forward_kalman", "jacobian_h", "nees",
                         "effective_sample_size"]


def run_build(outdir, env_extra=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    args = [sys.executable, CLI, "build", "--out",
            os.path.join(outdir, "report.md"), "--bundle"]
    return subprocess.run(args, capture_output=True, text=True, env=env)


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
            self.assertTrue(os.path.exists(os.path.join(ev, f)),
                            f + " missing")

    def test_model_has_numbers_and_status(self):
        run_build(self.tmp)
        m = json.load(open(os.path.join(self.tmp, "evidence", "model.json")))
        self.assertIn("kalman", m)
        self.assertIn("final", m["kalman"])
        self.assertIn("gain", m["kalman"]["final"])
        self.assertEqual(m.get("status"), "draft-for-review")
        self.assertIn("role", m)
        self.assertIn("ekf", m)

    def test_gates_all_pass_exit_zero(self):
        run_build(self.tmp)
        g = json.load(open(os.path.join(self.tmp, "evidence", "gates.json")))
        self.assertTrue(g["all_pass"])
        self.assertEqual(g["exit_code"], 0)
        self.assertGreaterEqual(len(g["gates"]), 5)

    def test_dispatch_crosschecks_when_skills_present(self):
        if not HAS_SKILLS:
            self.skipTest("AeroSkills not present")
        r = run_build(self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        p = json.load(open(os.path.join(self.tmp, "evidence",
                                        "provenance.json")))
        self.assertTrue(p["cross_checked"])
        self.assertGreaterEqual(len(p["skills"]), 5)
        fns = [row["function"] for row in p["skills"]]
        for fn in EXPECTED_DISPATCH_FNS:
            self.assertIn(fn, fns, f"dispatch row missing: {fn}")
        for row in p["skills"]:
            self.assertTrue(row["dispatched"])
            self.assertTrue(row["agrees"], "core/skill disagree: %s" % row)
            self.assertLessEqual(row["delta"], 1e-6)

    def test_standalone_honest_no_skills(self):
        r = run_build(self.tmp, env_extra={"AEROSKILLS_DEV": "/nonexistent"})
        self.assertEqual(r.returncode, 0)
        p = json.load(open(os.path.join(self.tmp, "evidence",
                                        "provenance.json")))
        self.assertFalse(p["cross_checked"])
        self.assertEqual(len(p["skills"]), 0)

    def test_check_still_works(self):
        run_build(self.tmp)
        md = os.path.join(self.tmp, "report.md")
        c = subprocess.run([sys.executable, CLI, "check", "--file", md],
                           capture_output=True, text=True)
        self.assertEqual(c.returncode, 0, c.stdout)
        self.assertIn("RESULT: PASS", c.stdout)


if __name__ == "__main__":
    unittest.main()
