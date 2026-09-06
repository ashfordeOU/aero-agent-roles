#!/usr/bin/env python3
"""Test the evidence bundle + skill-dispatch protocol (PROTOCOL.md v1).

Verifies:
- build --bundle emits evidence/{model,gates,provenance}.json
- bundle JSON parses; model contains the computed performance numbers
  (balanced V1 / field length, propeller range, sustained load factor,
  hover endurance, cruise range) and the honest draft status
- the nine bound flight-mechanics/performance leaf logic modules
  dispatch and cross-check their numbers against the core (agree
  within tolerance) when AeroSkills is present
- standalone (no AeroSkills) emits the bundle honestly with
  cross_checked=false
- build --profile prepends a program context header
- per-fact overrides (--available-power, --load-factor) re-run the
  H-1 power-limited cases
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
    "balanced-field-length", "propeller-range",
    "rotorcraft-axial-descent-flow-states",
    "rotorcraft-blade-flapping-dynamics",
    "rotorcraft-hover-ground-effect", "rotorcraft-lead-lag-dynamics",
    "rotorcraft-main-rotor-sizing", "rotorcraft-range-endurance",
    "rotorcraft-turn-performance",
}

EXPECTED_N_SECTIONS = 10


def run_build(outdir, env_extra=None, extra_args=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    args = [sys.executable, CLI, "build", "--out",
            os.path.join(outdir, "performance-report.md"), "--bundle"]
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
        self.assertEqual(m["role"], "aircraft-performance-engineer")
        self.assertEqual(m["deliverable_type"],
                         "Aircraft Performance Analysis Report")
        # the model must carry the numbers that appear in the markdown
        self.assertAlmostEqual(m["bfl"]["v1_ms"], 77.2815, places=2)
        self.assertAlmostEqual(m["bfl"]["balanced_field_length_m"], 2138.10,
                               places=1)
        self.assertAlmostEqual(m["propeller"]["range_km"], 1472.24,
                               delta=0.01)
        self.assertGreater(m["turn"]["sustained"]["load_factor"], 2.0)
        self.assertAlmostEqual(m["fuel"]["hover_endurance_s"], 20927.3,
                               delta=1.0)
        self.assertGreater(m["fuel"]["cruise_range_m"], 2.0e6)

    def test_markdown_sections_all_present(self):
        run_build(self.tmp)
        md = open(os.path.join(self.tmp, "performance-report.md")).read()
        for n in range(1, EXPECTED_N_SECTIONS + 1):
            self.assertIn("## %d. " % n, md, "section %d missing" % n)
        low = md.lower()
        self.assertIn("draft", low)
        self.assertIn("not an approval", low)

    def test_gates_all_pass_exit_zero(self):
        r = run_build(self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        g = json.load(open(os.path.join(self.tmp, "evidence", "gates.json")))
        self.assertTrue(g["all_pass"])
        self.assertEqual(g["exit_code"], 0)
        self.assertGreaterEqual(len(g["gates"]), 10)

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
            self.assertEqual(row["delta"], 0.0)
        funcs = {row["function"] for row in p["skills"]}
        self.assertIn("balanced_v1", funcs)
        self.assertIn("propeller_range", funcs)
        self.assertIn("cruise_range", funcs)
        self.assertIn("turn_power", funcs)

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
        md = open(os.path.join(self.tmp, "performance-report.md")).read()
        self.assertIn("Example Airframers Ltd", md)
        self.assertIn("Program context (profile)", md)
        m = json.load(open(os.path.join(self.tmp, "evidence", "model.json")))
        self.assertEqual(m["profile"]["customer"], "Example Airframers Ltd")

    def test_available_power_override_recomputes_sustained_turn(self):
        # default: 600 kW sustains ~2.005 g at 60 m/s; at 500 kW the
        # sustained load factor must fall (level total 460336 W < 500 kW)
        run_build(self.tmp)
        m = json.load(open(os.path.join(self.tmp, "evidence", "model.json")))
        default_n = m["turn"]["sustained"]["load_factor"]
        r = run_build(self.tmp, extra_args=["--available-power", "500000"])
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        m2 = json.load(open(os.path.join(self.tmp, "evidence", "model.json")))
        self.assertLess(m2["turn"]["sustained"]["load_factor"], default_n)
        self.assertGreater(m2["turn"]["sustained"]["load_factor"], 1.2)
        self.assertAlmostEqual(m2["turn"]["sustained"]["total_power"],
                               500000.0, delta=1.0)
        # hover-IGE case re-runs on the same power: no IGE ceiling at 500 kW
        self.assertIsNone(m2["hover_ige"]["max_hover_height"])

    def test_load_factor_override(self):
        run_build(self.tmp, extra_args=["--load-factor", "1.5"])
        m = json.load(open(os.path.join(self.tmp, "evidence", "model.json")))
        self.assertEqual(m["turn"]["load_factor"], 1.5)
        self.assertLess(m["turn"]["breakdown"]["total_power"],
                        600000.0)   # n = 1.5 turn needs less than the n = 2

    def test_check_still_works(self):
        run_build(self.tmp)
        md = os.path.join(self.tmp, "performance-report.md")
        c = subprocess.run([sys.executable, CLI, "check", "--file", md],
                           capture_output=True, text=True)
        self.assertEqual(c.returncode, 0, c.stdout)
        self.assertIn("RESULT: PASS", c.stdout)


if __name__ == "__main__":
    unittest.main()
