#!/usr/bin/env python3
"""Test the evidence bundle + skill-dispatch protocol for
mbse-modeling-engineer (PROTOCOL.md v1).

Verifies:
- build --bundle emits evidence/{model,gates,provenance}.json
- bundle JSON parses; model contains the diagram suite, requirement
  coverage, N2 counts, constraints; gates all_pass; exit code 0
- skill dispatch cross-checks core numbers against the bound MBSE leaf
  logic (agreeing within tolerance) when AeroSkills is present
- standalone (AEROSKILLS_DEV=/nonexistent) emits the bundle honestly
  with cross_checked=false
- build --failure-condition catastrophic re-runs the FDAL variant
- check --file passes the gate vocabulary
- a malformed profile fails loudly with exit 1
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
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
PROFILE = os.path.join(REPO_ROOT, "profiles", "example-airframer.json")
EXPECTED_CUSTOMER = "Example Airframers Ltd"

AEROSKILLS = os.environ.get("AEROSKILLS_DEV",
                            os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))

# Functions the CLI should dispatch against the bound leaf logic.
EXPECTED_DISPATCH_FNS = [
    "count_shall_clauses",   # requirements-modeling
    "total_interfaces",      # n2-diagram
    "weighted_score",        # trade-study-analysis
]


def run_build(outdir, extra_args=None, env_extra=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    args = [sys.executable, CLI, "build", "--out",
            os.path.join(outdir, "plan.md"), "--bundle"]
    if extra_args:
        args.extend(extra_args)
    return subprocess.run(args, capture_output=True, text=True, env=env)


class TestMbseCliBundle(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _model(self):
        return json.load(open(os.path.join(self.tmp, "evidence",
                                           "model.json")))

    def _gates(self):
        return json.load(open(os.path.join(self.tmp, "evidence",
                                           "gates.json")))

    def _prov(self):
        return json.load(open(os.path.join(self.tmp, "evidence",
                                           "provenance.json")))

    def test_bundle_emits_three_files_exit_zero(self):
        r = run_build(self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        for f in ("model.json", "gates.json", "provenance.json"):
            self.assertTrue(os.path.exists(os.path.join(self.tmp, "evidence",
                                                        f)))

    def test_model_content_and_gates(self):
        r = run_build(self.tmp)
        self.assertEqual(r.returncode, 0)
        m = self._model()
        self.assertEqual(m["role"], "mbse-modeling-engineer")
        self.assertEqual(m["status"], "draft-for-review")
        self.assertEqual(
            m["document_type"], "System Model Architecture and MBSE Plan")
        self.assertEqual(m["development_assurance_level"], "B")
        self.assertEqual(m["requirements_total"], 5)
        self.assertEqual(m["satisfy_fraction"], 1.0)
        self.assertEqual(m["verify_fraction"], 1.0)
        self.assertEqual(m["viewpoint_verdict"], "complete")
        self.assertEqual(m["n2"]["total"], 4)
        self.assertEqual(m["bdd_verdict"], "valid")
        self.assertTrue(all(c["satisfied"] for c in m["constraints"]))
        g = self._gates()
        self.assertTrue(g["all_pass"])
        self.assertEqual(g["exit_code"], 0)

    def test_dispatch_crosscheck_when_skills_present(self):
        r = run_build(self.tmp)
        self.assertEqual(r.returncode, 0)
        prov = self._prov()
        fns = [row["function"] for row in prov["skills"]]
        if HAS_SKILLS:
            for fn in EXPECTED_DISPATCH_FNS:
                self.assertIn(fn, fns, "expected dispatch fn missing: " + fn)
            self.assertTrue(prov["cross_checked"])
            self.assertTrue(all(row["agrees"] for row in prov["skills"]),
                            [row for row in prov["skills"]
                             if not row["agrees"]])
            for row in prov["skills"]:
                self.assertLessEqual(row["delta"], 1e-6)
        else:
            self.assertEqual(prov["skills"], [])
            self.assertFalse(prov["cross_checked"])

    def test_standalone_honest_bundle(self):
        r = run_build(self.tmp, env_extra={"AEROSKILLS_DEV": "/nonexistent"})
        self.assertEqual(r.returncode, 0)
        prov = self._prov()
        self.assertEqual(prov["skills"], [])
        self.assertFalse(prov["cross_checked"])
        # deliverable is still complete and gate-passing standalone
        m = self._model()
        self.assertEqual(m["requirements_total"], 5)
        g = self._gates()
        self.assertTrue(g["all_pass"])

    def test_failure_condition_override_changes_fdal(self):
        r = run_build(self.tmp, ["--failure-condition", "catastrophic"])
        self.assertEqual(r.returncode, 0)
        m = self._model()
        self.assertEqual(m["development_assurance_level"], "A")
        # level gate stays green; the FDAL data is honest
        self.assertTrue(self._gates()["all_pass"])

    def test_profile_header_and_model(self):
        if not os.path.exists(PROFILE):
            self.skipTest("profiles/example-airframer.json not present")
        r = run_build(self.tmp, ["--profile", PROFILE])
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        md = open(os.path.join(self.tmp, "plan.md")).read()
        self.assertTrue(md.startswith("## Program context"))
        self.assertIn("Customer: " + EXPECTED_CUSTOMER, md)
        m = self._model()
        self.assertEqual(m["profile"]["customer"], EXPECTED_CUSTOMER)
        self.assertEqual(m["status"], "draft-for-review")
        # gate-check still passes on the profiled markdown
        c = subprocess.run([sys.executable, CLI, "check", "--file",
                            os.path.join(self.tmp, "plan.md")],
                           capture_output=True, text=True)
        self.assertEqual(c.returncode, 0, c.stdout)
        self.assertIn("RESULT: PASS", c.stdout)

    def test_malformed_profile_fails_loudly(self):
        bad = os.path.join(self.tmp, "bad-profile.json")
        with open(bad, "w") as f:
            json.dump({"program": "no customer here"}, f)
        r = run_build(self.tmp, ["--profile", bad])
        self.assertEqual(r.returncode, 1)
        self.assertIn("error: bad profile", r.stdout)

    def test_check_command_gate_vocabulary(self):
        r = run_build(self.tmp)
        self.assertEqual(r.returncode, 0)
        c = subprocess.run([sys.executable, CLI, "check", "--file",
                            os.path.join(self.tmp, "plan.md")],
                           capture_output=True, text=True)
        self.assertEqual(c.returncode, 0)
        self.assertIn("RESULT: PASS", c.stdout)
        for name in ("has_title", "has_level", "has_coverage",
                     "has_parametric", "has_not_approval"):
            self.assertIn(name, c.stdout)


if __name__ == "__main__":
    unittest.main()
