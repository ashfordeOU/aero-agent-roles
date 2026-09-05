#!/usr/bin/env python3
"""Test the do254-hardware-engineer evidence bundle + profile + dispatch.

Verifies (offline, no network):
- build --bundle emits evidence/{model,gates,provenance}.json
- bundle JSON parses, model carries the PHAC numbers, gates all_pass
- skill dispatch cross-checks the bound do254 leaf logics against the
  core when AeroSkills is present (all agree)
- standalone (no AeroSkills) exits 0 with cross_checked=false
- build --profile prepends the program-context header and records the
  customer in model.json (PROFILE-SCHEMA.md)
- malformed profile fails loudly with exit 1
- cli check PASSes the built PHAC
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
# repo root is 4 up from tests/ (tests -> role -> roles -> repo)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
PROFILE = os.path.join(REPO_ROOT, "profiles", "example-airframer.json")
EXPECTED_CUSTOMER = "Example Airframers Ltd"

AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))


def run_build(outdir, env_extra=None, extra_args=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    args = [sys.executable, CLI, "build", "--out",
            os.path.join(outdir, "phac.md"), "--bundle"]
    if extra_args:
        args.extend(extra_args)
    return subprocess.run(args, capture_output=True, text=True, env=env)


class TestDo254BundleProfile(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _model(self):
        return json.load(open(os.path.join(self.tmp, "evidence",
                                           "model.json")))

    def test_bundle_emits_three_files(self):
        r = run_build(self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        ev = os.path.join(self.tmp, "evidence")
        for f in ("model.json", "gates.json", "provenance.json"):
            self.assertTrue(os.path.exists(os.path.join(ev, f)), f + " missing")

    def test_model_has_phac_content(self):
        r = run_build(self.tmp)
        self.assertEqual(r.returncode, 0)
        m = self._model()
        self.assertEqual(m["role"], "do254-hardware-engineer")
        self.assertEqual(m["deliverable_type"],
                         "Plan for Hardware Aspects of Certification")
        self.assertIn("assurance_level", m)
        self.assertIn("aeh_class", m)
        self.assertEqual(m["aeh_class"], "complex")
        self.assertEqual(m.get("status"), "draft-for-review")

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
        # all four bound leaves dispatch at least one logic cross-check
        leaves = {row["leaf"] for row in p["skills"]}
        for leaf in ("avionics/do254/hardware-planning",
                     "avionics/do254/verification",
                     "avionics/do254/configuration-management",
                     "avionics/do254/requirements-capture"):
            self.assertIn(leaf, leaves, f"no dispatch row for {leaf}")
        for row in p["skills"]:
            self.assertTrue(row["dispatched"])
            self.assertTrue(row["agrees"], "core/skill disagree: %s" % row)

    def test_standalone_honest_no_skills(self):
        r = run_build(self.tmp, env_extra={"AEROSKILLS_DEV": "/nonexistent"})
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        p = json.load(open(os.path.join(self.tmp, "evidence",
                                        "provenance.json")))
        self.assertFalse(p["cross_checked"])
        self.assertEqual(len(p["skills"]), 0)
        g = json.load(open(os.path.join(self.tmp, "evidence", "gates.json")))
        self.assertTrue(g["all_pass"])

    def test_profile_prepends_context_and_records_customer(self):
        if not os.path.exists(PROFILE):
            self.skipTest("profiles/example-airframer.json not present")
        r = run_build(self.tmp, extra_args=["--profile", PROFILE])
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        md = open(os.path.join(self.tmp, "phac.md")).read()
        self.assertTrue(md.startswith("## Program context"),
                        "profile context header must lead the PHAC")
        self.assertIn("Customer: " + EXPECTED_CUSTOMER, md)
        m = self._model()
        self.assertEqual(m["profile"]["customer"], EXPECTED_CUSTOMER)
        self.assertEqual(m["profile"]["authority"], "FAA")
        # profiled PHAC still passes the gate-check command
        c = subprocess.run(
            [sys.executable, CLI, "check", "--file",
             os.path.join(self.tmp, "phac.md"), "--dal", "B"],
            capture_output=True, text=True)
        self.assertEqual(c.returncode, 0, c.stdout)
        self.assertIn("RESULT: PASS", c.stdout)

    def test_malformed_profile_fails_loudly(self):
        bad = os.path.join(self.tmp, "bad-profile.json")
        with open(bad, "w") as f:
            json.dump({"program": "no customer here"}, f)
        r = run_build(self.tmp, extra_args=["--profile", bad])
        self.assertEqual(r.returncode, 1)
        self.assertIn("error: bad profile", r.stdout)

    def test_check_still_works(self):
        r = run_build(self.tmp)
        self.assertEqual(r.returncode, 0)
        c = subprocess.run(
            [sys.executable, CLI, "check", "--file",
             os.path.join(self.tmp, "phac.md"), "--dal", "B"],
            capture_output=True, text=True)
        self.assertEqual(c.returncode, 0, c.stdout)
        self.assertIn("RESULT: PASS", c.stdout)


if __name__ == "__main__":
    unittest.main()
