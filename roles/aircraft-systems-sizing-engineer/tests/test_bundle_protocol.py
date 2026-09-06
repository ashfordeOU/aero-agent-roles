#!/usr/bin/env python3
"""Test the evidence bundle + skill-dispatch protocol (PROTOCOL.md v1).

Verifies:
- build --bundle emits evidence/{model,gates,provenance}.json
- bundle JSON parses; model contains all 14 systems with numbers; gates
  all_pass
- skill dispatch cross-checks bound sizing leaf logic against the core
  (agrees within tolerance) when AeroSkills is present
- standalone (no AeroSkills) emits the bundle honestly with
  cross_checked=false
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

EXPECTED_SYSTEMS = ["electrical", "air_cycle_machine", "avionics_bay_cooling",
                    "oxygen", "brakes", "valves", "fuel_feed",
                    "fuel_jettison", "fuel_tank_inerting",
                    "hydraulic_actuator", "landing_gear_layout",
                    "ram_air_turbine", "tires", "windows"]


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
            self.assertTrue(os.path.exists(os.path.join(ev, f)),
                            f + " missing")

    def test_model_has_all_systems_and_status(self):
        run_build(self.tmp)
        m = json.load(open(os.path.join(self.tmp, "evidence", "model.json")))
        self.assertEqual(m.get("status"), "draft-for-review")
        self.assertIn("role", m)
        self.assertIn("systems", m)
        for sys_name in EXPECTED_SYSTEMS:
            self.assertIn(sys_name, m["systems"])
        self.assertEqual(len(m["verdicts"]), 14)

    def test_gates_all_pass_exit_zero(self):
        r = run_build(self.tmp)
        g = json.load(open(os.path.join(self.tmp, "evidence", "gates.json")))
        self.assertTrue(g["all_pass"])
        self.assertEqual(g["exit_code"], 0)
        self.assertGreaterEqual(len(g["gates"]), 5)

    def test_dispatch_crosschecks_when_skills_present(self):
        if not HAS_SKILLS:
            self.skipTest("AeroSkills not present")
        r = run_build(self.tmp)
        p = json.load(open(os.path.join(self.tmp, "evidence",
                                        "provenance.json")))
        self.assertTrue(p["cross_checked"])
        self.assertGreaterEqual(len(p["skills"]), 14,
                                "expected >= 14 dispatch rows (one or more "
                                "per bound leaf)")
        rows = [x for x in p["skills"] if x.get("dispatched")]
        self.assertGreaterEqual(len(rows), 14)
        self.assertTrue(all(x["agrees"] for x in rows),
                        "core/skill mismatch: %s"
                        % [x for x in rows if not x["agrees"]])
        # dispatch covers all 14 bound leaves
        leaves = {x["leaf"].split("/")[-1] for x in rows}
        self.assertGreaterEqual(len(leaves), 14)

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
