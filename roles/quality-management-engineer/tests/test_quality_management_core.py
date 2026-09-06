#!/usr/bin/env python3
"""Test quality_management_core: the executable engine of the QMS role.

Proves the role can DO its job standalone (no AeroSkills needed): gage
R&R by ANOVA and by the range method, bias/linearity, attribute
agreement, X-bar/R limits + capability, I-MR, CUSUM/EWMA, p-chart,
acceptance sampling, the derived findings/conformance model, evidence
gates, and the filled report. Anchors are the values verified against
the bound AeroSkills leaf logic.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from quality_management_core import (  # noqa: E402
    ANOVA_STUDY, RATINGS_MATRIX, build_report, capability_indices,
    check_report, check_report_markdown, code_letter, example_item,
    example_report_markdown, gage_bias_linearity_study, imr_summary,
    kappa_verdict, oc_acceptance_probability, p_chart, process_sigma,
    render_report_markdown, sampling_plan, small_shift_monitoring_report,
    study_summary, verdict_for_percent_grr, xbar_r_limits,
)


class TestDomainRules(unittest.TestCase):

    def test_percent_grr_bands(self):
        self.assertEqual(verdict_for_percent_grr(5.0), "acceptable")
        self.assertEqual(verdict_for_percent_grr(10.0), "conditional")
        self.assertEqual(verdict_for_percent_grr(30.0), "conditional")
        self.assertEqual(verdict_for_percent_grr(45.0), "unacceptable")

    def test_kappa_bands(self):
        self.assertEqual(kappa_verdict(0.80), "good")
        self.assertEqual(kappa_verdict(0.50), "marginal")
        self.assertEqual(kappa_verdict(0.30), "poor")

    def test_xbar_r_limits_and_sigma(self):
        # n=5 constants: A2 0.577, D4 2.114, D3 0, d2 2.326
        ucl_x, lcl_x, ucl_r, lcl_r = xbar_r_limits(6.0007, 0.00875, 5)
        self.assertAlmostEqual(ucl_x, 6.00575, places=5)
        self.assertAlmostEqual(lcl_x, 5.99565, places=4)
        self.assertAlmostEqual(ucl_r, 0.0184975, places=6)
        self.assertEqual(lcl_r, 0.0)
        self.assertAlmostEqual(process_sigma(0.00875, 5),
                               0.00875 / 2.326, places=6)

    def test_capability_indices(self):
        cp, cpu, cpl, cpk = capability_indices(6.015, 5.985, 6.0007,
                                               0.00875 / 2.326)
        self.assertAlmostEqual(cp, 1.33, places=2)
        self.assertAlmostEqual(cpk, 1.27, places=2)
        self.assertAlmostEqual(cpk, min(cpu, cpl), places=6)

    def test_oc_acceptance_probability_anchors(self):
        # ANSI/ASQ Z1.4-style plan (80, 2, 3): OC 0.9534 at 1% and
        # 0.3748 at 4% - the anchor values the bound leaf asserts.
        self.assertAlmostEqual(oc_acceptance_probability(80, 2, 0.01),
                               0.9534, places=4)
        self.assertAlmostEqual(oc_acceptance_probability(80, 2, 0.04),
                               0.3748, places=4)

    def test_attribute_plan_lookup(self):
        self.assertEqual(code_letter(500, "II"), "J")
        self.assertEqual(sampling_plan("J", 1.0), (80, 2, 3))


class TestExampleAnalyses(unittest.TestCase):
    """Anchor checks: the worked example numbers verified against the
    bound AeroSkills leaf logic (both implementations agree)."""

    def setUp(self):
        self.model = build_report(example_item())

    def test_anova_grr_anchor(self):
        an = self.model["msa"]["anova"]
        self.assertAlmostEqual(an["percent_grr"], 11.05, places=2)
        self.assertEqual(an["verdict"], "conditional")
        self.assertEqual(an["ndc"], 12)

    def test_range_method_grr_anchor(self):
        rng = self.model["msa"]["range"]
        self.assertAlmostEqual(rng["percent_grr"], 10.68, places=2)
        self.assertEqual(rng["verdict"], "conditional")
        self.assertEqual(rng["ndc"], 13)
        # dual estimators agree within 1 percentage point
        self.assertLess(self.model["msa"]["dual_delta_pp"], 1.0)

    def test_bias_linearity_anchor(self):
        bl = self.model["msa"]["bias_linearity"]
        self.assertAlmostEqual(bl["mean_bias"], 0.0218, places=4)
        self.assertTrue(bl["significant"])
        self.assertEqual(bl["overall"], "REVIEW")
        self.assertTrue(bl["per_level_acceptable"])
        self.assertAlmostEqual(bl["t_stat"], 3.27, places=2)

    def test_attribute_agreement_anchor(self):
        ag = self.model["msa"]["attribute"]
        self.assertAlmostEqual(ag["kappa"], 0.33, places=2)
        self.assertEqual(ag["verdict"], "poor")

    def test_capability_anchor(self):
        xr = self.model["spc"]["xbar_r"]
        self.assertAlmostEqual(xr["cpk"], 1.27, places=2)
        self.assertAlmostEqual(xr["cp"], 1.33, places=2)
        self.assertEqual(xr["verdict"], "in-control")
        self.assertEqual(xr["ooc_rules"], [])

    def test_imr_anchor(self):
        imr = self.model["spc"]["imr"]
        self.assertEqual(imr["verdict"], "out-of-control")
        self.assertEqual(imr["flagged_individuals"], [16])  # lot 17
        self.assertGreater(imr["x_ucl"], 124.0)

    def test_shift_monitoring_anchor(self):
        sm = self.model["spc"]["shift_monitoring"]
        self.assertFalse(sm["any_signal"])
        self.assertIsNone(sm["first_signal_index"])

    def test_p_chart_anchor(self):
        p = self.model["spc"]["p_chart"]
        self.assertEqual(p["verdict"], "in-control")
        self.assertAlmostEqual(p["pbar"], 0.01225, places=5)

    def test_attribute_sampling_anchor(self):
        a = self.model["sampling"]["attribute"]
        self.assertEqual(a["code"], "J")
        self.assertEqual((a["n"], a["ac"], a["re"]), (80, 2, 3))
        self.assertEqual(a["decision"], "accept")
        self.assertAlmostEqual(a["oc_at_aql"], 0.9534, places=4)
        self.assertAlmostEqual(a["producer_risk_pct"], 4.66, places=2)

    def test_variables_sampling_anchor(self):
        v = self.model["sampling"]["variables"]
        self.assertEqual(v["code"], "J")
        self.assertEqual(v["n"], 35)
        self.assertEqual(v["k"], 1.62)
        self.assertAlmostEqual(v["Q"], 4.90, places=2)
        self.assertTrue(v["accept"])

    def test_findings_derived_from_verdicts(self):
        ids = [f["id"] for f in self.model["findings"]]
        self.assertEqual(ids, ["NC-01", "NC-02", "NC-03",
                               "OFI-01", "OFI-02"])
        self.assertEqual(self.model["counts"],
                         {"major": 0, "minor": 3, "ofi": 2, "total": 5})
        for f in self.model["findings"]:
            self.assertEqual(f["status"], "open")
            self.assertIn("evidence", f)
            # every finding is marked open: the role never closes findings
            self.assertNotIn("closed", f["status"])

    def test_conformance_derived(self):
        rows = {c["clause"]: c for c in self.model["conformance"]}
        self.assertEqual(rows["7.1.5.1"]["status"], "minor nonconformity")
        self.assertEqual(rows["7.1.5.2"]["status"], "minor nonconformity")
        self.assertEqual(rows["8.5.1"]["status"], "minor nonconformity")
        self.assertEqual(rows["8.6"]["status"], "conforming")


class TestVerdictDrivenFindings(unittest.TestCase):
    """Engine behavior: fix the data, verdicts and findings follow."""

    def test_no_nc03_when_reaction_recorded(self):
        item = example_item()
        item.coating_reaction_recorded = True
        model = build_report(item)
        ids = [f["id"] for f in model["findings"]]
        self.assertNotIn("NC-03", ids)

    def test_no_nc01_when_bias_insignificant(self):
        item = example_item()
        item.mic_biases = [0.001, -0.001, 0.002, 0.001, -0.002]
        model = build_report(item)
        bl = model["msa"]["bias_linearity"]
        self.assertFalse(bl["significant"])
        ids = [f["id"] for f in model["findings"]]
        self.assertNotIn("NC-01", ids)

    def test_no_ofi02_when_grr_acceptable(self):
        item = example_item()
        # near-identical trials and wide part spread -> small %GRR
        item.anova_study = {
            "Inspector A. Brandt": {p + 1: [11.90 + 0.02 * p] * 3
                                    for p in range(10)},
            "Inspector M. Sato": {p + 1: [11.90 + 0.02 * p] * 3
                                  for p in range(10)},
            "Inspector S. Okafor": {p + 1: [11.90 + 0.02 * p] * 3
                                    for p in range(10)},
        }
        model = build_report(item)
        self.assertEqual(model["msa"]["anova"]["verdict"], "acceptable")
        ids = [f["id"] for f in model["findings"]]
        self.assertNotIn("OFI-02", ids)


class TestReportAndGates(unittest.TestCase):

    def test_core_gates_all_pass(self):
        model = build_report(example_item())
        gates = check_report(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_all_pass(self):
        md = example_report_markdown()
        gates = check_report_markdown(md)
        self.assertTrue(gates["all_pass"], gates)

    def test_report_required_sections(self):
        md = example_report_markdown()
        for sec in ["## 1. Scope and audit basis", "## 3. Measurement "
                    "systems analysis audit", "## 5. Acceptance sampling "
                    "audit", "## 6. Findings", "## 7. Clause conformance "
                    "summary"]:
            self.assertIn(sec, md)
        low = md.lower()
        self.assertIn("not an approval", low)
        self.assertIn("not a certification", low)
        self.assertIn("draft", low)

    def test_model_is_json_clean(self):
        import json
        model = build_report(example_item())
        text = json.dumps(model)  # no NaN / non-serializable members
        self.assertGreater(len(text), 5000)

    def test_standalone_no_skills_repo(self):
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = build_report(example_item())
        self.assertEqual(model["standard"], "AS9100D")
        self.assertEqual(model["status"], "draft-for-review")
        md = render_report_markdown(model)
        self.assertGreater(len(md), 8000)

    def test_render_contains_computed_numbers(self):
        md = example_report_markdown()
        self.assertIn("11.05%", md)     # ANOVA %GRR
        self.assertIn("Cpk", md)
        self.assertIn("0.9534", md)     # OC at AQL


if __name__ == "__main__":
    unittest.main()
