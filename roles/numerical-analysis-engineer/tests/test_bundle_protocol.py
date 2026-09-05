#!/usr/bin/env python3
"""Test the evidence bundle + skill-dispatch protocol (PROTOCOL.md v1).

Verifies:
- build --bundle emits evidence/{model,gates,provenance}.json
- bundle JSON parses, model contains the computed reference numbers,
  gates all_pass
- the ten dispatch rows agree with the bound numerics leaf logic
  modules (delta <= 1e-6) when AeroSkills is present
- standalone (no AeroSkills) emits the bundle honestly with
  cross_checked=false
- build --profile prepends a program context header
- CLI overrides re-verify a different code report
- check gate-checks a built memo
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

EXPECTED_LEAVES = {
    "numerical-integration", "root-finding", "convergence-verification",
    "singular-value-decomposition", "matrix-operations",
}
EXPECTED_FUNCS = {"trapezoid", "simpson", "error_estimate_trapezoid",
                  "newton_raphson", "bisection", "condition_number", "solve"}


def run_build(outdir, env_extra=None, extra_args=None):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    args = [sys.executable, CLI, "build", "--out",
            os.path.join(outdir, "memo.md"), "--bundle"]
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
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-800:])
        ev = os.path.join(self.tmp, "evidence")
        for f in ("model.json", "gates.json", "provenance.json"):
            self.assertTrue(os.path.exists(os.path.join(ev, f)), f + " missing")

    def test_model_has_numbers_and_status(self):
        run_build(self.tmp)
        m = json.load(open(os.path.join(self.tmp, "evidence", "model.json")))
        self.assertEqual(m["role"], "numerical-analysis-engineer")
        self.assertEqual(m["deliverable_type"],
                         "Numerical Methods Verification Memo")
        self.assertEqual(m.get("status"), "draft-for-review")
        # the model must carry the numbers that appear in the markdown
        self.assertAlmostEqual(m["integration"]["code_value"], 50350.78125,
                               places=6)
        self.assertAlmostEqual(m["integration"]["reference_value"], 50400.0,
                               places=6)
        self.assertAlmostEqual(
            m["root_finding"]["reference_root"], 0.59024876099, places=9)
        self.assertAlmostEqual(m["convergence"]["observed_order"], 2.0,
                               places=6)
        self.assertAlmostEqual(m["linear_solve"]["conditioning"]["kappa"],
                               7.0, places=6)

    def test_gates_all_pass_exit_zero(self):
        r = run_build(self.tmp)
        self.assertEqual(r.returncode, 0)
        g = json.load(open(os.path.join(self.tmp, "evidence", "gates.json")))
        self.assertTrue(g["all_pass"])
        self.assertEqual(g["exit_code"], 0)
        self.assertGreaterEqual(len(g["gates"]), 5)

    def test_dispatch_crosschecks_when_skills_present(self):
        if not HAS_SKILLS:
            self.skipTest("AeroSkills not present")
        r = run_build(self.tmp)
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-800:])
        p = json.load(open(os.path.join(self.tmp, "evidence",
                                        "provenance.json")))
        self.assertTrue(p["cross_checked"])
        rows = [row for row in p["skills"] if row.get("dispatched")
                and not row.get("error")]
        self.assertGreaterEqual(len(rows), 10)
        leafs = {row["leaf"].rsplit("/", 1)[-1] for row in rows}
        self.assertEqual(leafs, EXPECTED_LEAVES)
        funcs = {row["function"] for row in rows}
        self.assertTrue(EXPECTED_FUNCS.issubset(funcs), funcs)
        for row in rows:
            self.assertTrue(row["agrees"],
                            "core/skill disagree for %s: %s"
                            % (row["function"], row))
            self.assertLessEqual(row["delta"], 1e-6)
            self.assertIn("cross-cutting/numerics/", row["leaf"])

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
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-800:])
        md = open(os.path.join(self.tmp, "memo.md")).read()
        self.assertIn("Example Airframers Ltd", md)
        self.assertIn("Program context (profile)", md)
        m = json.load(open(os.path.join(self.tmp, "evidence", "model.json")))
        self.assertEqual(m["profile"]["customer"], "Example Airframers Ltd")

    def test_cli_overrides_flip_verdict(self):
        # re-verify a code report that reports the correct integral:
        # the integration check must now PASS
        r = run_build(self.tmp, extra_args=["--code-integral", "50400.0"])
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-800:])
        m = json.load(open(os.path.join(self.tmp, "evidence", "model.json")))
        self.assertEqual(m["integration"]["verdict"], "PASS")
        self.assertTrue(all(c["verdict"] == "PASS" for c in m["checks"]))
        # findings become observations, not discrepancies
        self.assertTrue(all(fd["severity"] == "observation"
                            for fd in m["findings"]))

    def test_check_still_works(self):
        run_build(self.tmp)
        md = os.path.join(self.tmp, "memo.md")
        c = subprocess.run([sys.executable, CLI, "check", "--file", md],
                           capture_output=True, text=True)
        self.assertEqual(c.returncode, 0, c.stdout)
        self.assertIn("RESULT: PASS", c.stdout)


if __name__ == "__main__":
    unittest.main()
