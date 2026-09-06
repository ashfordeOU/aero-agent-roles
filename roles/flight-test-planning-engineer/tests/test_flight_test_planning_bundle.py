#!/usr/bin/env python3
"""Test the evidence bundle + skill-dispatch protocol (PROTOCOL.md v1)
for the Flight Test Planning Engineer role.

Author: ashfordeOU · Aero Agent Roles.

Verifies:
- build --bundle emits evidence/{model,gates,provenance}.json
- bundle JSON parses; the model contains the computed planning numbers
  (matrix count, PCM bit rate, decomm frame period, cumulative margin
  rule) with honest draft status
- all seven bound flight-test-operations/planning leaf logic modules
  dispatch and cross-check their numbers against the core (agree
  within tolerance) when AeroSkills is present
- standalone (AEROSKILLS_DEV=/nonexistent) emits the bundle honestly
  with cross_checked=false and no dispatch rows
- build --profile prepends a program context header
- check gate-checks a built report; check --level verifies the
  build-up reaches a requested risk level (and fails above it)
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
PROFILE = os.path.normpath(os.path.join(ROLE_DIR, "..", "..", "profiles",
                                        "example-airframer.json"))

AEROSKILLS = os.environ.get("AEROSKILLS_DEV",
                            os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))

EXPECTED_DISPATCH_LEAVES = {
    "flight-test-instrumentation",
    "flight-test-planning",
    "noise-certification-test",
    "pcm-telemetry-decommutation",
    "position-error-calibration",
    "telemetry-data-acquisition",
    "test-point-matrix-design",
}


def run_build(outdir, env_extra=None, extra_args=None):
    env = dict(os.environ)
    env.setdefault("ROLE_GEN_DATE", "2026-09-06")
    if env_extra:
        env.update(env_extra)
    args = [sys.executable, CLI, "build", "--out",
            os.path.join(outdir, "plan.md"), "--bundle"]
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
            self.assertTrue(os.path.exists(os.path.join(ev, f)),
                            f + " missing")

    def test_model_has_numbers_and_status(self):
        r = run_build(self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        m = json.load(open(os.path.join(self.tmp, "evidence",
                                        "model.json")))
        self.assertEqual(m.get("status"), "draft-for-review")
        self.assertEqual(m["role"], "flight-test-planning-engineer")
        self.assertEqual(m["deliverable_type"],
                         "Flight Test Plan and Requirements Traceability")
        # the model must carry the numbers that appear in the markdown
        self.assertEqual(m["matrix"]["count"], 12)
        self.assertEqual(m["matrix"]["repeat_ids"], ["tp5", "tp10"])
        self.assertAlmostEqual(m["telemetry"]["stream"]["bit_rate"],
                               51200.0)
        self.assertEqual(m["telemetry"]["frame"]["frame_size_bits"], 1024)
        self.assertEqual(m["decommutation"]["period_words"], 10)
        self.assertEqual(m["decommutation"]["frames_expected"], 180000)
        self.assertEqual(m["noise"]["acceptance"]["cumulative_required_db"],
                         10.0)
        self.assertEqual(m["go_no_go"]["verdict"], "GO")
        self.assertEqual(m["traceability"]["requirement_verdict"],
                         "trace-complete")

    def test_gates_all_pass_exit_zero(self):
        r = run_build(self.tmp)
        g = json.load(open(os.path.join(self.tmp, "evidence",
                                        "gates.json")))
        self.assertTrue(g["all_pass"])
        self.assertEqual(g["exit_code"], 0)
        self.assertGreaterEqual(len(g["gates"]), 12)

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
        self.assertIn("required_sample_rate", funcs)
        self.assertIn("tower_flyby_position_error", funcs)
        self.assertIn("pcm_bit_rate", funcs)
        self.assertIn("frame_period_words", funcs)

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
        md = open(os.path.join(self.tmp, "plan.md")).read()
        self.assertIn("Example Airframers Ltd", md)
        self.assertIn("Program context (profile)", md)
        m = json.load(open(os.path.join(self.tmp, "evidence",
                                        "model.json")))
        self.assertEqual(m["profile"]["customer"], "Example Airframers Ltd")

    def test_check_still_works(self):
        run_build(self.tmp)
        md = os.path.join(self.tmp, "plan.md")
        c = subprocess.run([sys.executable, CLI, "check", "--file", md],
                           capture_output=True, text=True)
        self.assertEqual(c.returncode, 0, c.stdout)
        self.assertIn("RESULT: PASS", c.stdout)

    def test_check_level_gate(self):
        run_build(self.tmp)
        md = os.path.join(self.tmp, "plan.md")
        ok = subprocess.run([sys.executable, CLI, "check", "--file", md,
                             "--level", "3"],
                            capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stdout)
        self.assertIn("risk_level_3_covered", ok.stdout)
        fail = subprocess.run([sys.executable, CLI, "check", "--file", md,
                               "--level", "5"],
                              capture_output=True, text=True)
        self.assertEqual(fail.returncode, 1)
        self.assertIn("RESULT: FAIL", fail.stdout)


if __name__ == "__main__":
    unittest.main()
