#!/usr/bin/env python3
"""Test the evidence bundle + skill-dispatch protocol (PROTOCOL.md v1)
for the Systems Integration Engineer role.

Verifies:
- build --bundle emits evidence/{model,gates,provenance}.json
- bundle JSON parses, model contains the computed assurance numbers,
  gates all_pass, provenance carries core + disclaimer
- skill dispatch cross-checks the core against the bound ARP4754A leaf
  logic when AeroSkills is present (every dispatched row agrees)
- standalone (AEROSKILLS_DEV=/nonexistent) still builds and emits the
  bundle honestly with no dispatch rows
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
        self.assertEqual(m["status"], "draft-for-review")
        self.assertEqual(m["max_dal"], "A")
        self.assertEqual(m["allocation"]["coverage"], 1.0)
        self.assertEqual(m["traceability"]["status"], "closed")
        self.assertEqual(m["objectives"]["coverage"], 1.0)
        self.assertEqual(len(m["functions"]), 4)
        self.assertEqual(len(m["lifecycle_stages"]), 6)

    def test_gates_all_pass_in_bundle(self):
        r = run_build(self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        g = json.load(open(os.path.join(self.tmp, "evidence",
                                        "gates.json")))
        self.assertTrue(g["all_pass"])
        self.assertEqual(g["exit_code"], 0)
        names = [row["gate"] for row in g["gates"]]
        self.assertIn("level_identified", names)
        self.assertIn("lifecycle_stages_pass", names)
        self.assertTrue(all(row["pass"] for row in g["gates"]))

    def test_provenance_core_and_disclaimer(self):
        run_build(self.tmp)
        p = json.load(open(os.path.join(self.tmp, "evidence",
                                        "provenance.json")))
        self.assertEqual(p["role"], "systems-integration-engineer")
        self.assertIn("build_report", p["core"]["functions"])
        self.assertIn("not an approval", p["disclaimer"].lower())

    def test_dispatch_rows_agree_when_skills_present(self):
        if not HAS_SKILLS:
            self.skipTest("Aero Agent Skills checkout not present "
                          "(cross-repo dev check)")
        r = run_build(self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        p = json.load(open(os.path.join(self.tmp, "evidence",
                                        "provenance.json")))
        rows = [x for x in p.get("skills", []) if x.get("dispatched")]
        self.assertGreaterEqual(len(rows), 4,
                                "expected dispatch rows from ARP4754A leaves")
        for row in rows:
            self.assertTrue(row["agrees"],
                            "%s: core %s vs skill %s (delta %s)"
                            % (row.get("cross_check_point", row["leaf"]),
                               row["core_value"], row["skill_value"],
                               row["delta"]))
        self.assertTrue(p["cross_checked"])

    def test_standalone_bundle_honest_no_dispatch(self):
        env = {"AEROSKILLS_DEV": "/nonexistent"}
        r = run_build(self.tmp, env_extra=env)
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        p = json.load(open(os.path.join(self.tmp, "evidence",
                                        "provenance.json")))
        self.assertEqual(p.get("skills"), [])
        self.assertFalse(p["cross_checked"])
        m = json.load(open(os.path.join(self.tmp, "evidence",
                                        "model.json")))
        self.assertEqual(m["allocation"]["coverage"], 1.0)

    def test_severity_flag_drives_dal_variant(self):
        # --severity Minor re-rates every failure condition -> max DAL D
        r = run_build(self.tmp, extra_args=["--severity", "Minor"])
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        m = json.load(open(os.path.join(self.tmp, "evidence",
                                        "model.json")))
        self.assertEqual(m["max_dal"], "D")


if __name__ == "__main__":
    unittest.main()
