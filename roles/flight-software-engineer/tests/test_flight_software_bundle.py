#!/usr/bin/env python3
"""Test the evidence bundle + skill-dispatch protocol (PROTOCOL.md v1)
for the Flight Software Engineer role.

Verifies:
- build --bundle emits evidence/{model,gates,provenance}.json
- bundle JSON parses; model contains the computed design numbers
  (message ID band sizes, rate-group base clock, utilization 0.55,
  response times with blocking, feasibility verdicts)
- the bound avionics/fsw leaf logic modules dispatch and cross-check
  their numbers against the core (agree within tolerance) when
  AeroSkills is present
- standalone (no AeroSkills) emits the bundle honestly with
  cross_checked=false
- build --profile prepends a program context header
- check gate-checks a built plan
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

AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))

EXPECTED_DISPATCH_LEAVES = {
    "cfs-architecture", "fprime-component", "real-time-scheduling",
    "shared-resource-access-control",
}


def run_build(outdir, env_extra=None, extra_args=None):
    env = dict(os.environ)
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
            self.assertTrue(os.path.exists(os.path.join(ev, f)), f + " missing")

    def test_model_has_numbers_and_status(self):
        run_build(self.tmp)
        m = json.load(open(os.path.join(self.tmp, "evidence", "model.json")))
        self.assertEqual(m.get("status"), "draft-for-review")
        self.assertEqual(m["role"], "flight-software-engineer")
        self.assertEqual(m["deliverable_type"],
                         "Flight Software Design and Verification Plan")
        self.assertEqual(m["software_level"], "A")
        # the model must carry the numbers that appear in the markdown
        self.assertEqual(m["bus_design"]["space_size"], 65536)
        self.assertEqual(m["bus_design"]["command_band_size"], 4096)
        self.assertEqual(m["bus_design"]["telemetry_band_size"], 61440)
        self.assertEqual(m["bus_design"]["total_msgs_per_frame"], 12)
        self.assertAlmostEqual(m["scheduling"]["utilization"], 0.55)
        self.assertEqual(m["scheduling"]["rm_exact_response_times"],
                         [1.0, 3.0, 7.0])
        self.assertEqual(m["scheduling"]["verdict"], "RM-guaranteed-by-UB")
        self.assertEqual(m["component_model"]["topology_issues"], 0)
        self.assertEqual(m["component_model"]["schedule"]["base_hz"], 200.0)
        self.assertAlmostEqual(m["resources"]["response_times"]["Guidance"],
                               3.7)
        self.assertTrue(m["resources"]["feasible"])

    def test_gates_all_pass_exit_zero(self):
        r = run_build(self.tmp)
        g = json.load(open(os.path.join(self.tmp, "evidence", "gates.json")))
        self.assertTrue(g["all_pass"])
        self.assertEqual(g["exit_code"], 0)
        self.assertGreaterEqual(len(g["gates"]), 7)

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
        self.assertIn("utilization", funcs)
        self.assertIn("blocking_times", funcs)
        self.assertIn("validate_topology", funcs)
        self.assertIn("telemetry_pipeline", funcs)

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
        m = json.load(open(os.path.join(self.tmp, "evidence", "model.json")))
        self.assertEqual(m["profile"]["customer"], "Example Airframers Ltd")

    def test_check_still_works(self):
        run_build(self.tmp)
        md = os.path.join(self.tmp, "plan.md")
        c = subprocess.run([sys.executable, CLI, "check", "--file", md],
                           capture_output=True, text=True)
        self.assertEqual(c.returncode, 0, c.stdout)
        self.assertIn("RESULT: PASS", c.stdout)
        c = subprocess.run([sys.executable, CLI, "check", "--file", md,
                            "--level", "A"], capture_output=True, text=True)
        self.assertEqual(c.returncode, 0, c.stdout)

    def test_build_flag_overrides_recompute(self):
        """--base-hz must recompute the rate-group schedule periods."""
        r = run_build(self.tmp, extra_args=["--base-hz", "400"])
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        m = json.load(open(os.path.join(self.tmp, "evidence", "model.json")))
        periods = [(g["name"], g["period_ticks"])
                   for g in m["component_model"]["schedule"]["groups"]]
        self.assertEqual(periods,
                         [("RG200", 2), ("RG100", 4), ("RG50", 8)])


if __name__ == "__main__":
    unittest.main()
