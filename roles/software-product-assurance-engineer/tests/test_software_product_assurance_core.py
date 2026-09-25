#!/usr/bin/env python3
"""Test software_product_assurance_core: the engine of the Software Product
Assurance Engineer role.

Proves the role does its job standalone (no Aero Agent Skills needed):
category derivation and tailoring, the compliance-matrix rules, the
document trace, the milestone evidence check and review-pack grading, the
SPAMR skeleton, the metrics grading, the evidence gates on the model and on
the rendered Markdown (including a human-appended sign-off), and the worked
example anchors. The example anchors were cross-checked against the bound
q80 leaf logic (both implementations agree).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
import software_product_assurance_core as core  # noqa: E402


def ev(*rows):
    """Evidence rows from (clause, document, section, status, justification)."""
    return [dict(zip(("clause", "document", "section", "status",
                      "justification"), r)) for r in rows]


def row_of(matrix, clause):
    return next(r for r in matrix["rows"] if r["clause"] == clause)


class TestNormalisation(unittest.TestCase):

    def test_category_spellings(self):
        for v in ("B", "b", " cat-B ", "category B"):
            self.assertEqual(core.normalise_category(v), "B")
        with self.assertRaises(ValueError):
            core.normalise_category("E")

    def test_severity_spellings(self):
        self.assertEqual(core.normalise_severity("catastrophic"), "I")
        self.assertEqual(core.normalise_severity("3"), "III")
        self.assertEqual(core.normalise_severity("iv"), "IV")
        with self.assertRaises(ValueError):
            core.normalise_severity("V")

    def test_clause_id_forms(self):
        for v in ("6.2.3.4", "6.2.3.4a", "6.2.3.4.a", "cl. 6.2.3.4",
                  "clause 6.2.3.4", " 06.02.3.4 "):
            self.assertEqual(core.normalise_clause_id(v), "6.2.3.4")
        with self.assertRaises(ValueError):
            core.normalise_clause_id("section six")

    def test_status_vocabulary_is_closed(self):
        self.assertEqual(core.normalise_status("PC"), "partially-compliant")
        self.assertEqual(core.normalise_status("n/a"), "not-applicable")
        self.assertEqual(core.normalise_status("Non-Compliant"),
                         "not-compliant")
        with self.assertRaises(ValueError):
            core.normalise_status("mostly")

    def test_review_and_scope(self):
        self.assertEqual(core.normalise_review("PDR"), "pdr")
        self.assertEqual(core.normalise_review("critical design review"),
                         "cdr")
        with self.assertRaises(ValueError):
            core.normalise_review("MDR")
        self.assertEqual(core.normalise_scope(["Reuse", "suppliers"]),
                         ("reuse", "suppliers"))
        with self.assertRaises(ValueError):
            core.normalise_scope(["cots"])


class TestCategoryAndTailoring(unittest.TestCase):

    def test_severity_maps_to_base_category(self):
        for sev, cat in zip(core.SEVERITIES, core.CATEGORIES):
            self.assertEqual(core.derive_category(sev)["category"], cat)

    def test_provision_lowers_one_step(self):
        d = core.derive_category("I", ["hardware"])
        self.assertEqual((d["base_category"], d["category"]), ("A", "B"))
        self.assertTrue(d["lowered_by_provision"])

    def test_software_provision_carries_a_constraint(self):
        d = core.derive_category("II", ["software"])
        self.assertEqual(d["category"], "C")
        self.assertTrue(any("category B" in c for c in d["constraints"]))

    def test_no_credit_below_d(self):
        d = core.derive_category("IV", ["hardware"])
        self.assertEqual(d["category"], "D")
        self.assertFalse(d["lowered_by_provision"])

    def test_provision_software_takes_no_credit(self):
        d = core.derive_category("III", ["hardware"],
                                 provides_provision_for="II")
        self.assertEqual(d["category"], "B")
        self.assertFalse(d["lowered_by_provision"])

    def test_tailored_status_codes(self):
        self.assertEqual(core.tailored_status("5.7.1", "D"), "not-applicable")
        self.assertEqual(core.tailored_status("5.7.1", "C"), "applicable")
        self.assertEqual(core.tailored_status("5.1.5.1", "D"), "reduced")
        self.assertEqual(core.tailored_status("6.2.3.7", "C"),
                         "not-applicable")
        self.assertEqual(core.tailored_status("6.2.3.7", "B"), "applicable")
        self.assertEqual(core.tailored_status("6.3.8.2", "C"), "reduced")

    def test_security_clauses_follow_sensitivity(self):
        for cat in core.CATEGORIES:
            self.assertEqual(core.tailored_status("6.2.9.1", cat),
                             "not-applicable")
            self.assertEqual(core.tailored_status("6.2.9.1", cat, True),
                             "applicable")

    def test_unknown_clause(self):
        self.assertEqual(core.tailored_status("6.3.7.4", "A"), "unknown")

    def test_requirement_list_is_unique(self):
        self.assertEqual(len(core.REQUIREMENT_IDS),
                         len(set(core.REQUIREMENT_IDS)))
        self.assertTrue(all(c in core._REQUIREMENT_SET
                            for c in core.APPLICABILITY))

    def test_tailoring_summary_totals(self):
        n = len(core.REQUIREMENT_IDS)
        for cat in core.CATEGORIES:
            t = core.tailoring_summary(cat)["totals"]
            self.assertEqual(sum(t.values()), n)
        b = core.tailoring_summary("B")["totals"]
        self.assertEqual(b, {"applicable": 253, "reduced": 0,
                             "not-applicable": 11})
        self.assertEqual(core.tailoring_summary("B", True)["totals"][
            "not-applicable"], 0)
        d = core.tailoring_summary("D")
        self.assertTrue(d["reduced"])
        self.assertTrue(all(r["note"] for r in d["reduced"]))


class TestMatrixRules(unittest.TestCase):

    def m(self, rows, clauses=None, cat="B", sec=False):
        clauses = clauses or list(dict.fromkeys(r["clause"] for r in rows))
        return core.build_matrix(clauses, rows, cat, sec)

    def test_silence_is_not_compliance(self):
        mx = core.build_matrix(["5.2.3"], [], "B")
        r = row_of(mx, "5.2.3")
        self.assertEqual(r["status"], "not-compliant")
        self.assertEqual(r["gaps"], ["no-evidence"])

    def test_tailored_out_prefills_not_applicable(self):
        mx = core.build_matrix(["5.7.1"], [], "D")
        r = row_of(mx, "5.7.1")
        self.assertEqual(r["status"], "not-applicable")
        self.assertEqual(r["gaps"], [])
        self.assertIn("category D", r["justification"])

    def test_claim_without_reference_is_downgraded(self):
        mx = self.m(ev(("5.2.4", "", "", "compliant", "we do it")))
        r = row_of(mx, "5.2.4")
        self.assertEqual(r["status"], "partially-compliant")
        self.assertIn("no-evidence-reference", r["gaps"])

    def test_reference_without_section(self):
        mx = self.m(ev(("6.1.3", "SDP", "", "compliant", "")))
        self.assertEqual(row_of(mx, "6.1.3")["gaps"],
                         ["reference-without-section"])

    def test_weakest_status_wins(self):
        mx = self.m(ev(("6.2.4.2", "SCMP", "2", "compliant", ""),
                       ("6.2.4.2", "AUDIT", "F3", "not-compliant",
                        "finding")))
        r = row_of(mx, "6.2.4.2")
        self.assertEqual(r["status"], "not-compliant")
        self.assertEqual(r["documents"], ["SCMP", "AUDIT"])

    def test_not_applicable_against_tailoring_is_a_gap(self):
        mx = self.m(ev(("5.4.4", "SPAP", "7", "na", "no subcontractor")))
        r = row_of(mx, "5.4.4")
        self.assertEqual(r["status"], "not-applicable")
        self.assertEqual(r["gaps"], ["na-conflicts-with-tailoring"])

    def test_not_applicable_needs_justification(self):
        mx = self.m(ev(("6.2.9.1", "", "", "na", "")))
        self.assertEqual(row_of(mx, "6.2.9.1")["gaps"],
                         ["na-without-justification"])

    def test_evidence_on_tailored_out_clause(self):
        mx = self.m(ev(("5.7.1", "SPAP", "9", "compliant", "")), cat="D")
        self.assertIn("evidence-for-tailored-out-clause",
                      row_of(mx, "5.7.1")["gaps"])

    def test_conflicting_statuses(self):
        mx = self.m(ev(("5.3.1", "SPAP", "6", "compliant", ""),
                       ("5.3.1", "SPAP", "6", "na", "x")))
        self.assertIn("conflicting-status", row_of(mx, "5.3.1")["gaps"])

    def test_deviation_without_justification(self):
        mx = self.m(ev(("5.3.1", "SPAP", "6", "pc", "")))
        self.assertIn("deviation-without-justification",
                      row_of(mx, "5.3.1")["gaps"])

    def test_orphan_evidence_is_reported_not_dropped(self):
        mx = core.build_matrix(["5.3.1"], ev(
            ("5.3.1", "SPAP", "6", "c", ""),
            ("6.3.7.4", "SDP", "8", "pc", "old list")), "B")
        self.assertEqual(mx["orphan_evidence"], ["6.3.7.4"])
        self.assertIn(("6.3.7.4", "evidence-for-unlisted-clause"),
                      [(g["clause"], g["kind"]) for g in mx["gaps"]])

    def test_duplicate_clause_refused(self):
        with self.assertRaises(ValueError):
            core.build_matrix(["5.3.1", "5.3.1a"], [], "B")

    def test_loose_csv_headers(self):
        rows = core.parse_evidence_csv(
            "Requirement,Doc,Paragraph,Compliance,Comment\n"
            "5.3.1,SPAP,6,C,\n\n")
        self.assertEqual(rows, [{"clause": "5.3.1", "document": "SPAP",
                                 "section": "6", "status": "C",
                                 "justification": ""}])

    def test_csv_needs_clause_and_status(self):
        with self.assertRaises(ValueError):
            core.parse_evidence_csv("clause,document\n5.3.1,SPAP\n")

    def test_bad_status_names_the_row(self):
        with self.assertRaises(ValueError) as cm:
            core.index_evidence(ev(("5.3.1", "SPAP", "6", "mostly", "")))
        self.assertIn("row 1", str(cm.exception))

    def test_coverage_fractions(self):
        mx = core.build_matrix(
            ["5.3.1", "5.2.3", "5.2.4", "6.2.9.1"],
            ev(("5.3.1", "SPAP", "6", "c", ""),
               ("5.2.3", "SPAP", "4", "pc", "audits from CDR")), "B")
        cov = mx["coverage"]
        self.assertEqual(cov["applicable"], 3)
        self.assertEqual(cov["counts"]["not-applicable"], 1)
        self.assertEqual(cov["compliant_fraction"], round(1 / 3, 4))
        self.assertEqual(cov["evidenced_fraction"], round(2 / 3, 4))
        self.assertIsNone(cov["traced_fraction"])

    def test_every_gap_has_a_next_skill(self):
        mx = core.build_matrix(["5.2.3", "6.1.1", "7.1.1", "7.4.1"], [], "B")
        routes = {g["clause"]: g["next_skill"].rsplit("/", 1)[-1]
                  for g in mx["gaps"]}
        self.assertEqual(routes["5.2.3"], "q80-software-product-assurance-plan")
        self.assertEqual(routes["6.1.1"], "q80-software-process-assurance")
        self.assertEqual(routes["7.1.1"],
                         "q80-software-product-quality-metrics")
        self.assertEqual(routes["7.4.1"], "q80-software-product-assurance-plan")

    def test_customer_clause_list(self):
        cl = core.parse_clause_list("id,title\n5.3.1,risk\n6.1.1\n# note\n")
        self.assertEqual(cl, [("5.3.1", "risk"), ("6.1.1", core.topic_of(
            "6.1.1"))])
        with self.assertRaises(ValueError):
            core.parse_clause_list("5.3.1\n5.3.1\n")


class TestDocumentTrace(unittest.TestCase):

    FILES = ["plans/SPAP-001.md", "SDP-001.pdf", ".hidden", "notes.txt"]

    def test_resolution_ignores_case_extension_and_folder(self):
        self.assertEqual(core.resolve_document("spap-001", self.FILES),
                         "plans/SPAP-001.md")
        self.assertEqual(core.resolve_document("SDP-001.pdf", self.FILES),
                         "SDP-001.pdf")
        self.assertIsNone(core.resolve_document("SVR-001", self.FILES))

    def test_missing_document_is_a_gap_and_downgrades(self):
        mx = core.build_matrix(["6.2.6.5", "6.2.6.6"], ev(
            ("6.2.6.5", "SVR-001", "3", "c", ""),
            ("6.2.6.6", "SVR-001", "4", "c", ""),
            ("6.2.6.6", "SDP-001", "5", "c", "")), "B")
        core.apply_document_trace(mx, self.FILES, "docs/")
        a, b = row_of(mx, "6.2.6.5"), row_of(mx, "6.2.6.6")
        self.assertEqual(a["status"], "partially-compliant")
        self.assertIn("document-not-found", a["gaps"])
        self.assertTrue(a["notes"])
        # one of two citations resolves: the gap stays, no downgrade
        self.assertEqual(b["status"], "compliant")
        self.assertIn("document-not-found", b["gaps"])
        self.assertEqual(mx["trace"]["missing"],
                         {"SVR-001": ["6.2.6.5", "6.2.6.6"]})
        self.assertEqual(mx["coverage"]["traced_fraction"], 0.5)
        self.assertIn("plans/SPAP-001.md", mx["trace"]["uncited_files"])

    def test_list_documents(self):
        here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                            "example", "docs")
        files = core.list_documents(here)
        self.assertIn("EX-SPAP-001.md", files)
        self.assertFalse(any(f.startswith(".") for f in files))
        with self.assertRaises(ValueError):
            core.list_documents(os.path.join(here, "no-such-folder"))


class TestMilestone(unittest.TestCase):

    def owed(self, review, cat, scope=()):
        return [d["document"] for d in core.evidence_due(review, cat, scope)]

    def test_scope_turns_documents_on(self):
        self.assertIn("software-reuse-file", self.owed("pdr", "B", ["reuse"]))
        self.assertNotIn("software-reuse-file", self.owed("pdr", "B"))

    def test_independent_verification_plan_by_category(self):
        self.assertIn("isvv-plan", self.owed("pdr", "B"))
        self.assertNotIn("isvv-plan", self.owed("pdr", "C"))

    def test_spap_owed_at_srr(self):
        self.assertIn("spap", self.owed("srr", "D"))

    def test_pack_grading(self):
        res = core.assess_review_pack("pdr", "C", [
            {"document": "spap", "maturity": "issued"},
            {"document": "sdp", "maturity": "draft"},
            {"document": "acceptance-documentation", "maturity": "draft"}])
        self.assertIn("sdp", res["immature"])
        self.assertIn("coding-standards", res["missing"])
        self.assertEqual(res["unplanned"], ["acceptance-documentation"])
        self.assertFalse(res["complete"])

    def test_pack_refuses_unknown_kind_and_duplicates(self):
        with self.assertRaises(ValueError):
            core.assess_review_pack("pdr", "B", [{"document": "memo",
                                                  "maturity": "issued"}])
        with self.assertRaises(ValueError):
            core.assess_review_pack("pdr", "B", [
                {"document": "spap", "maturity": "issued"},
                {"document": "spap", "maturity": "draft"}])

    def test_spamr_skeleton(self):
        sk = core.spamr_skeleton("cdr", {"metrics": ["M"], "testing": []})
        st = {s["id"]: s["status"] for s in sk["sections"]}
        self.assertEqual(st["1"], "boilerplate")
        self.assertEqual(st["7"], "filled")
        self.assertEqual(st["8"], "missing-input")
        self.assertIn("testing", sk["missing_inputs"])
        self.assertTrue(sk["status"].startswith("DRAFT"))

    def test_plan_maturity(self):
        self.assertEqual(core.PLAN_MATURITY_BY_REVIEW["srr"], "issued")
        self.assertEqual(core.PLAN_MATURITY_BY_REVIEW["qr"], "maintained")

    def test_pack_csv(self):
        rows = core.parse_pack_csv("document,maturity\nspap,issued\n,\n")
        self.assertEqual(rows, [{"document": "spap", "maturity": "issued",
                                 "file": ""}])
        with self.assertRaises(ValueError):
            core.parse_pack_csv("kind,state\nspap,issued\n")


class TestMetrics(unittest.TestCase):

    def test_thresholds_and_overrides(self):
        t = core.thresholds_for("B", {"mcdc_coverage": 0.9,
                                      "cyclomatic_complexity": None})
        self.assertEqual(t["mcdc_coverage"], (0.9, "project"))
        self.assertNotIn("cyclomatic_complexity", t)
        self.assertEqual(t["function_size_loc"], (80, "default"))
        with self.assertRaises(ValueError):
            core.thresholds_for("B", {"lines_of_joy": 1})

    def test_grading(self):
        res = core.evaluate_metrics({"cyclomatic_complexity": 12,
                                     "comment_density": 0.3,
                                     "made_up": 1}, "B")
        rows = {r["metric"]: r for r in res["rows"]}
        self.assertEqual(rows["cyclomatic_complexity"]["status"], "fail")
        self.assertEqual(rows["cyclomatic_complexity"]["margin"], -2)
        self.assertEqual(rows["comment_density"]["status"], "pass")
        self.assertEqual(rows["decision_coverage"]["status"], "missing")
        self.assertEqual(res["unknown"], ["made_up"])
        self.assertEqual(res["verdict"], "fail")

    def test_metrics_csv(self):
        m = core.parse_metrics_csv("metric,value\nnesting_depth,3\n"
                                   "statement_coverage,\n")
        self.assertEqual(m, {"nesting_depth": 3.0,
                             "statement_coverage": None})
        with self.assertRaises(ValueError):
            core.parse_metrics_csv("metric,value\nnesting_depth,deep\n")


class TestWorkedExample(unittest.TestCase):
    """Anchors of the bundled example (agree with the bound q80 leaves)."""

    @classmethod
    def setUpClass(cls):
        cls.model = core.build_report(core.example_item())
        cls.mx = cls.model["matrix"]

    def test_category_derived(self):
        self.assertEqual(self.model["category"], "B")
        self.assertEqual(self.model["category_derivation"]["base_category"],
                         "A")

    def test_coverage_anchor(self):
        cov = self.mx["coverage"]
        self.assertEqual((cov["clauses"], cov["applicable"]), (264, 226))
        self.assertEqual(cov["counts"], {"compliant": 129,
                                         "partially-compliant": 91,
                                         "not-compliant": 6,
                                         "not-applicable": 38})
        self.assertEqual(cov["traced_fraction"], 0.9646)
        self.assertEqual(len(self.mx["gaps"]), 129)

    def test_trace_finds_the_absent_report(self):
        self.assertEqual(self.mx["trace"]["missing"],
                         {"EX-SVR-001": ["6.2.6.5", "6.2.6.6"]})
        self.assertEqual(row_of(self.mx, "6.2.6.5")["status"],
                         "partially-compliant")

    def test_audit_finding_outweighs_plan(self):
        self.assertEqual(row_of(self.mx, "6.2.4.2")["status"],
                         "not-compliant")

    def test_orphan_from_older_list(self):
        self.assertEqual(self.mx["orphan_evidence"], ["6.3.7.4"])

    def test_milestone_pack(self):
        pk = self.model["milestone"]["pack"]
        self.assertEqual(pk["missing"], ["isvv-plan", "isvv-report",
                                         "software-verification-report"])
        self.assertEqual(pk["immature"], ["software-verification-plan",
                                          "spamr"])
        self.assertEqual(self.model["milestone"]["spap_maturity_due"],
                         "updated")

    def test_metrics_verdict(self):
        self.assertEqual(self.model["metrics"]["failing"], [
            "coding_standard_violations", "cyclomatic_complexity",
            "requirement_test_coverage"])


class TestGates(unittest.TestCase):

    def setUp(self):
        self.model = core.build_report(core.example_item())
        self.md = core.render_report_markdown(self.model)

    def test_model_gates_pass(self):
        g = core.check_report(self.model)
        self.assertTrue(g["all_pass"], g)

    def test_model_gate_catches_self_approval(self):
        self.model["status"] = "APPROVED"
        self.assertFalse(core.check_report(self.model)["draft_status"])

    def test_model_gate_catches_edited_coverage(self):
        self.model["matrix"]["coverage"]["counts"]["compliant"] += 1
        self.assertFalse(core.check_report(self.model)["coverage_consistent"])

    def test_model_gate_catches_silent_compliance(self):
        r = row_of(self.model["matrix"], "7.4.1")
        r["status"], r["gaps"] = "compliant", []
        g = core.check_report(self.model)
        self.assertFalse(g["no_silent_compliance"])

    def test_markdown_gates_pass(self):
        g = core.check_report_markdown(self.md)
        self.assertTrue(g["all_pass"], g)
        self.assertEqual(g["sign_off"]["state"], "unsigned")

    def test_markdown_ends_at_stop_line(self):
        self.assertEqual(self.md.rstrip().splitlines()[-1], core.STOP_LINE)
        self.assertNotIn("Signed-off-by", self.md)

    def test_markdown_gate_catches_removed_stop_line(self):
        g = core.check_report_markdown(self.md.replace(core.STOP_LINE, ""))
        self.assertFalse(g["sign_off_honest"])

    def test_markdown_gate_catches_edited_status(self):
        md = self.md.replace("| 7.4.1 | buying ground hardware | applicable "
                             "| not-compliant |",
                             "| 7.4.1 | buying ground hardware | applicable "
                             "| compliant |")
        self.assertNotEqual(md, self.md)
        self.assertFalse(core.check_report_markdown(md)[
            "coverage_matches_rows"])

    def test_markdown_gate_catches_gap_count(self):
        md = self.md.replace("Open gaps: 129.", "Open gaps: 12.")
        self.assertFalse(core.check_report_markdown(md)["open_gaps_match"])

    def sign(self, **kw):
        block = {"Signed-off-by": "A. Person", "Sign-off-role":
                 "software PA manager", "Sign-off-date": "2026-10-01",
                 "Sign-off-decision": "approved", "Accepted-open-gaps": "129"}
        block.update(kw)
        return self.md + "\n" + "\n".join(
            "%s: %s" % (k, v) for k, v in block.items() if v is not None) \
            + "\n"

    def test_human_sign_off_accepted(self):
        g = core.check_report_markdown(self.sign())
        self.assertTrue(g["all_pass"], g)
        self.assertEqual(g["sign_off"]["signatory"], "A. Person")

    def test_approval_over_gaps_must_accept_them(self):
        g = core.check_report_markdown(self.sign(**{
            "Accepted-open-gaps": None}))
        self.assertFalse(g["sign_off_honest"])

    def test_sign_off_needs_name_and_iso_date(self):
        self.assertFalse(core.check_report_markdown(self.sign(**{
            "Signed-off-by": ""}))["sign_off_honest"])
        self.assertFalse(core.check_report_markdown(self.sign(**{
            "Sign-off-date": "1 Oct 2026"}))["sign_off_honest"])

    def test_rejection_needs_no_gap_acceptance(self):
        g = core.check_report_markdown(self.sign(**{
            "Sign-off-decision": "rejected", "Accepted-open-gaps": None}))
        self.assertTrue(g["all_pass"], g)


class TestRenderingAndStandalone(unittest.TestCase):

    def test_csv_marks_every_row_draft(self):
        model = core.build_report(core.example_item())
        lines = core.render_matrix_csv(model).splitlines()
        self.assertTrue(lines[0].startswith("clause,topic,tailoring,status"))
        self.assertEqual(len(lines), 1 + 264 + 1)
        self.assertTrue(all(l.endswith(",DRAFT") for l in lines[1:]))
        self.assertIn(core.STOP_LINE, lines[-1])

    def test_markdown_structure(self):
        md = core.example_report_markdown()
        for n in range(1, 12):
            self.assertRegex(md, r"(?m)^## %d\. " % n)
        low = md.lower()
        for marker in ("draft", "not an approval", "not a certification",
                       "not a statement of compliance"):
            self.assertIn(marker, low)

    def test_trace_not_run_is_said(self):
        item = core.ProjectInputs(project="p", category="C",
                                  evidence_text="clause,status\n5.3.1,c\n")
        md = core.render_report_markdown(core.build_report(item))
        self.assertIn("traced fraction not run", md)
        self.assertIn("Not run: no document folder was given", md)

    def test_category_conflict_is_an_open_point(self):
        item = core.ProjectInputs(category="C", severity="I",
                                  evidence_text="clause,status\n")
        model = core.build_report(item)
        self.assertEqual(model["category"], "C")
        self.assertTrue(model["category_notes"])

    def test_category_is_required(self):
        with self.assertRaises(ValueError):
            core.build_report(core.ProjectInputs(
                evidence_text="clause,status\n"))

    def test_standalone_no_skills_repo(self):
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = core.build_report(core.example_item())
        self.assertEqual(model["status"], "DRAFT")
        self.assertTrue(model["requires_human_sign_off"])
        self.assertGreater(len(core.render_report_markdown(model)), 20000)


if __name__ == "__main__":
    unittest.main()
