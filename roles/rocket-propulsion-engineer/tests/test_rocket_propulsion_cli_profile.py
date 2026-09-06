#!/usr/bin/env python3
"""CLI test: rocket-propulsion-engineer build --profile (PROFILE-SCHEMA v1).

Verifies the --profile path end-to-end through cli.py (offline, no
network): a program profile (customer launch program context) prepends
the '## Program context' header to the design report and records
profile.customer in the evidence model.json, exactly like the
do178c-cert-engineer reference. Also checks the no-profile path is
unchanged, the profiled report still passes every gate, the
provenance bundle dispatches all 14 bound rocket leaves when the
skills library is present, and a malformed profile fails loudly with
exit 1.
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


def run_build(outdir, extra_args=None):
    args = [sys.executable, CLI, "build", "--out",
            os.path.join(outdir, "report.md"), "--bundle"]
    if extra_args:
        args.extend(extra_args)
    return subprocess.run(args, capture_output=True, text=True)


class TestRocketPropulsionCliProfile(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        if not os.path.exists(PROFILE):
            self.skipTest("profiles/example-airframer.json not present")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _model(self):
        return json.load(open(os.path.join(self.tmp, "evidence",
                                           "model.json")))

    def test_build_with_profile_exits_zero_header_first(self):
        r = run_build(self.tmp, ["--profile", PROFILE])
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-800:])
        md = open(os.path.join(self.tmp, "report.md")).read()
        self.assertTrue(md.startswith("## Program context"),
                        "profile context header must lead the report")
        self.assertIn("Customer: " + EXPECTED_CUSTOMER, md)
        self.assertIn("profile: " + EXPECTED_CUSTOMER, r.stdout)

    def test_model_json_records_profile_customer(self):
        r = run_build(self.tmp, ["--profile", PROFILE])
        self.assertEqual(r.returncode, 0)
        m = self._model()
        self.assertEqual(m["role"], "rocket-propulsion-engineer")
        self.assertEqual(m["deliverable_type"],
                         "Rocket Propulsion System Design Report")
        self.assertIn("profile", m)
        self.assertEqual(m["profile"]["customer"], EXPECTED_CUSTOMER)
        self.assertEqual(m["profile"]["basis"], "FAR-25")
        self.assertEqual(m["profile"]["authority"], "FAA")
        # profile tailors context; the report body is still the design
        self.assertEqual(m["status"], "draft-for-review")
        self.assertTrue(m["staging"]["booster"]["m0_kg"] > 0)
        self.assertIn("Meridian-9", m["item"])

    def test_profiled_report_still_passes_gates(self):
        r = run_build(self.tmp, ["--profile", PROFILE])
        self.assertEqual(r.returncode, 0)
        g = json.load(open(os.path.join(self.tmp, "evidence",
                                        "gates.json")))
        self.assertTrue(g["all_pass"])
        self.assertEqual(g["exit_code"], 0)
        # gate-check command also passes on the profiled markdown
        c = subprocess.run([sys.executable, CLI, "check", "--file",
                            os.path.join(self.tmp, "report.md")],
                           capture_output=True, text=True)
        self.assertEqual(c.returncode, 0, c.stdout)
        self.assertIn("RESULT: PASS", c.stdout)

    def test_bundle_provenance_dispatches_when_library_present(self):
        # With the skills library reachable, provenance records the
        # fourteen bound-leaf cross-checks and they all agree.
        r = run_build(self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        prov = json.load(open(os.path.join(self.tmp, "evidence",
                                           "provenance.json")))
        skills = [s for s in prov.get("skills", [])
                  if s.get("dispatched") and not s.get("error")]
        if not skills:
            self.skipTest("AeroSkills checkout not present "
                          "(cross-repo dev check)")
        self.assertEqual(len(skills), 14,
                         "all fourteen bound leaves must dispatch")
        for s in skills:
            self.assertTrue(s["agrees"],
                            "dispatch disagree: %s" % s.get("leaf"))
        self.assertTrue(prov["cross_checked"])
        self.assertIn("not a launch readiness decision",
                      prov["disclaimer"])

    def test_standalone_bundle_no_dispatch(self):
        # Without the library, dispatch rows report honestly and the
        # bundle still passes.
        env = dict(os.environ, AEROSKILLS_DEV="/nonexistent")
        r = subprocess.run(
            [sys.executable, CLI, "build", "--out",
             os.path.join(self.tmp, "report.md"), "--bundle"],
            capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        prov = json.load(open(os.path.join(self.tmp, "evidence",
                                           "provenance.json")))
        self.assertFalse(prov["cross_checked"])
        g = json.load(open(os.path.join(self.tmp, "evidence",
                                        "gates.json")))
        self.assertTrue(g["all_pass"])

    def test_no_profile_unchanged(self):
        r = run_build(self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        md = open(os.path.join(self.tmp, "report.md")).read()
        self.assertTrue(md.startswith("# Rocket Propulsion System "
                                      "Design Report"))
        self.assertNotIn("profile", self._model())

    def test_malformed_profile_fails_loudly(self):
        bad = os.path.join(self.tmp, "bad-profile.json")
        with open(bad, "w") as f:
            json.dump({"program": "no customer here"}, f)
        r = run_build(self.tmp, ["--profile", bad])
        self.assertEqual(r.returncode, 1)
        self.assertIn("error: bad profile", r.stdout)


if __name__ == "__main__":
    unittest.main()
