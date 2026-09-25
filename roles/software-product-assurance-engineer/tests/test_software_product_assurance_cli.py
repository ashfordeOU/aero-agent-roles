#!/usr/bin/env python3
"""CLI test: software-product-assurance-engineer build / check end to end.

Runs cli.py as a user would (offline, no network): the bundled example,
a real-project run from a temporary evidence file and document folder,
the input errors, the evidence bundle and profile header, the check of a
draft and of a human-signed matrix, and the cross-check against the bound
q80 leaves (dispatched when AEROSKILLS_DEV points at the skills, and shown
to catch a disagreement; otherwise the not-dispatched message must say
how to point AEROSKILLS_DEV at an installed aero-agent-skills package).
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
REPO_ROOT = os.path.dirname(os.path.dirname(ROLE_DIR))
PROFILE = os.path.join(REPO_ROOT, "profiles", "example-airframer.json")
SKILLS = os.environ.get("AEROSKILLS_DEV", "")
HAS_Q80 = bool(SKILLS) and os.path.isdir(os.path.join(
    SKILLS, "skills", "space-systems", "ecss", "q80-compliance-matrix"))
STOP = "STOP: human sign-off required before submission."

EVIDENCE = (
    "clause,document,section,status,justification\n"
    "5.3.1,PLAN-001,section 6,compliant,\n"
    "5.2.3,PLAN-001,section 4,partially-compliant,audits start at CDR\n"
    "6.2.6.5,REPORT-009,section 3,compliant,\n"
    "7.1.1,,,compliant,in the specification\n")


def run(args, env_skills=None, cwd=None):
    env = dict(os.environ)
    if env_skills is not None:
        env["AEROSKILLS_DEV"] = env_skills
    return subprocess.run([sys.executable, CLI] + args, capture_output=True,
                          text=True, env=env, cwd=cwd)


class CliCase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def path(self, *p):
        return os.path.join(self.tmp, *p)

    def write(self, name, text):
        with open(self.path(name), "w") as f:
            f.write(text)
        return self.path(name)


class TestBuildExample(CliCase):

    def test_example_builds_markdown_and_csv(self):
        r = run(["build", "--out", self.path("out", "matrix.md")],
                env_skills="/nonexistent")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.exists(self.path("out", "matrix.csv")))
        self.assertIn("worked example", r.stdout)
        self.assertEqual(r.stdout.rstrip().splitlines()[-1], STOP)
        with open(self.path("out", "matrix.md")) as f:
            self.assertEqual(f.read().rstrip().splitlines()[-1], STOP)

    def test_check_passes_on_a_fresh_build(self):
        run(["build", "--out", self.path("m.md")], env_skills="/nonexistent")
        r = run(["check", "--file", self.path("m.md")])
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("SIGN-OFF: none recorded", r.stdout)
        self.assertIn("RESULT: PASS", r.stdout)

    def test_stdout_mode_prints_the_matrix(self):
        r = run(["build", "--no-dispatch"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith("# Software Product Assurance "
                                            "Compliance Matrix"))

    def test_bundle_records_honest_provenance(self):
        r = run(["build", "--out", self.path("m.md"), "--bundle"],
                env_skills="/nonexistent")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(self.path("evidence", "provenance.json")) as f:
            prov = json.load(f)
        self.assertFalse(prov["cross_checked"])
        self.assertEqual(prov["skills"], [])
        self.assertIn("AEROSKILLS_DEV", prov["skills_not_dispatched_reason"])
        with open(self.path("evidence", "model.json")) as f:
            model = json.load(f)
        self.assertEqual(model["status"], "DRAFT")
        self.assertTrue(model["requires_human_sign_off"])

    def test_profile_header(self):
        if not os.path.exists(PROFILE):
            self.skipTest("profiles/example-airframer.json not present")
        r = run(["build", "--out", self.path("m.md"), "--profile", PROFILE],
                env_skills="/nonexistent")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(self.path("m.md")) as f:
            self.assertTrue(f.read().startswith("## Program context"))


class TestBuildProject(CliCase):

    def test_real_project_with_trace(self):
        ev = self.write("ev.csv", EVIDENCE)
        os.makedirs(self.path("docs", "plans"))
        self.write(os.path.join("docs", "plans", "PLAN-001.docx"), "x")
        r = run(["build", "--out", self.path("m.md"), "--evidence", ev,
                 "--category", "C", "--docs", self.path("docs"),
                 "--review", "CDR", "--project", "Test craft"],
                env_skills="/nonexistent")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("1 missing (REPORT-009)", r.stdout)
        with open(self.path("m.md")) as f:
            md = f.read()
        self.assertIn("| REPORT-009 | 6.2.6.5 |", md)
        self.assertIn("Project: Test craft", md)
        self.assertIn("Evidence index: ev.csv (4 rows)", md)
        self.assertIn("Document folder: docs/ (1 files)", md)
        self.assertNotIn(self.tmp, md, "absolute path leaked into the matrix")
        self.assertEqual(run(["check", "--file", self.path("m.md")])
                         .returncode, 0)

    def test_severity_derives_the_category(self):
        ev = self.write("ev.csv", EVIDENCE)
        r = run(["build", "--out", self.path("m.md"), "--evidence", ev,
                 "--severity", "II", "--provision", "operational-procedure"],
                env_skills="/nonexistent")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("software category C (derived from severity II)",
                      r.stdout)
        self.assertIn("document trace: not run", r.stdout)

    def test_customer_clause_list(self):
        ev = self.write("ev.csv", EVIDENCE)
        cl = self.write("list.csv", "clause\n5.3.1\n5.2.3\n")
        r = run(["build", "--out", self.path("m.md"), "--evidence", ev,
                 "--category", "B", "--clauses", cl],
                env_skills="/nonexistent")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Coverage: 2 clauses", r.stdout)

    def test_missing_category_is_an_input_error(self):
        ev = self.write("ev.csv", EVIDENCE)
        r = run(["build", "--out", self.path("m.md"), "--evidence", ev])
        self.assertEqual(r.returncode, 2)
        self.assertIn("--category", r.stderr)

    def test_bad_status_is_an_input_error(self):
        ev = self.write("ev.csv", "clause,status\n5.3.1,mostly\n")
        r = run(["build", "--out", self.path("m.md"), "--evidence", ev,
                 "--category", "B"])
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown compliance status", r.stderr)

    def test_missing_files_are_input_errors(self):
        r = run(["build", "--evidence", self.path("none.csv"),
                 "--category", "B"])
        self.assertEqual(r.returncode, 2)
        ev = self.write("ev.csv", EVIDENCE)
        r = run(["build", "--evidence", ev, "--category", "B", "--docs",
                 self.path("no-docs")])
        self.assertEqual(r.returncode, 2)
        r = run(["build", "--evidence", ev, "--category", "B", "--pack", ev])
        self.assertEqual(r.returncode, 2)
        self.assertIn("--review", r.stderr)


class TestCheck(CliCase):

    def built(self):
        run(["build", "--out", self.path("m.md")], env_skills="/nonexistent")
        with open(self.path("m.md")) as f:
            return f.read()

    def test_human_signed_matrix_passes(self):
        md = self.built()
        gaps = [l for l in md.splitlines() if l.startswith("Open gaps: ")][0]
        n = gaps.split()[2].rstrip(".")
        self.write("m.md", md + "Signed-off-by: A. Person\n"
                   "Sign-off-role: software PA manager\n"
                   "Sign-off-date: 2026-10-01\nSign-off-decision: approved\n"
                   "Accepted-open-gaps: %s\n" % n)
        r = run(["check", "--file", self.path("m.md")])
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("SIGN-OFF: approved by A. Person", r.stdout)

    def test_signature_without_gap_acceptance_fails(self):
        md = self.built()
        self.write("m.md", md + "Signed-off-by: A. Person\n"
                   "Sign-off-role: software PA manager\n"
                   "Sign-off-date: 2026-10-01\nSign-off-decision: approved\n")
        r = run(["check", "--file", self.path("m.md")])
        self.assertEqual(r.returncode, 1)
        self.assertIn("sign-off problem", r.stdout)

    def test_tampered_matrix_fails(self):
        md = self.built().replace(STOP, "")
        self.write("m.md", md)
        r = run(["check", "--file", self.path("m.md")])
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL  sign_off_honest", r.stdout)

    def test_missing_file(self):
        self.assertEqual(run(["check", "--file", self.path("x.md")])
                         .returncode, 1)


class TestCrossCheck(CliCase):

    def test_not_dispatched_says_how_to_point_at_the_skills(self):
        r = run(["build", "--out", self.path("m.md")], env_skills="")
        self.assertEqual(r.returncode, 0)
        self.assertIn("not dispatched (AEROSKILLS_DEV is not set)", r.stdout)
        self.assertIn('export AEROSKILLS_DEV="$(npm root)/aero-agent-skills"',
                      r.stdout)

    def test_required_cross_check_fails_loud_without_skills(self):
        r = run(["build", "--out", self.path("m.md"),
                 "--require-cross-check"], env_skills="/nonexistent")
        self.assertEqual(r.returncode, 2)
        self.assertIn("npm install aero-agent-skills", r.stderr)
        self.assertFalse(os.path.exists(self.path("m.md")))

    def test_dispatch_agrees_with_the_bound_leaves(self):
        if not HAS_Q80:
            self.skipTest("AEROSKILLS_DEV with the q80 leaves not present")
        r = run(["build", "--out", self.path("m.md"), "--bundle",
                 "--require-cross-check"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(self.path("evidence", "provenance.json")) as f:
            prov = json.load(f)
        self.assertTrue(prov["cross_checked"])
        leaves = set(row["leaf"].rsplit("/", 1)[-1] for row in prov["skills"])
        for leaf in ("q80-compliance-matrix",
                     "q80-software-criticality-tailoring",
                     "q80-milestone-assurance-evidence",
                     "q80-software-product-assurance-plan",
                     "q80-software-product-quality-metrics"):
            self.assertIn(leaf, leaves)

    def test_dispatch_catches_a_disagreement(self):
        if not HAS_Q80:
            self.skipTest("AEROSKILLS_DEV with the q80 leaves not present")
        sys.path.insert(0, ROLE_DIR)
        import cli  # noqa: E402
        core = cli.core
        item = core.example_item()
        model = core.build_report(item)
        _root, mods, _reason = cli.skills_status()
        clean = cli.dispatch_rows(item, model, mods)
        self.assertTrue(clean and all(r["agrees"] for r in clean))
        model["metrics"]["verdict"] = "pass"          # a wrong engine answer
        model["tailoring"]["totals"]["reduced"] += 1
        bad = [r for r in cli.dispatch_rows(item, model, mods)
               if not r["agrees"]]
        self.assertEqual(sorted(r["function"] for r in bad),
                         ["evaluate_metrics", "tailoring_matrix"])


if __name__ == "__main__":
    unittest.main()
