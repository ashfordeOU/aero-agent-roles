#!/usr/bin/env python3
"""Test safety_assessment_core: the executable engine of the Safety
Assessment Engineer role.

Proves the role can DO its job standalone (no AeroSkills needed):
severity/probability-target classification, FTA gate math and cut sets,
FMEA/FMECA criticality, event tree frequency rollup, PSSA allocation,
SSA closure, report generation, and evidence-gate checks.

Real anchors are taken from the ARP4761A practice the AeroSkills leaves
encode: catastrophic <1e-9, hazardous <1e-7, major <1e-5, minor <1e-3
per flight hour; OR gate unions and AND gates take the cartesian
product; C_m = beta*alpha*lambda*t; event tree failure end state is the
all-mitigations-failed path; SSA closure gate closes only when every
condition meets its target.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from safety_assessment_core import (  # noqa: E402
    SEVERITY_TARGETS, analyses_for_level, build_safety_report,
    check_report, check_report_markdown, closure_rollup, dal_for_severity,
    error_factor_to_sigma, event_tree_failure_frequency,
    event_tree_frequencies, example_item, example_report_markdown,
    fmea_item_criticality, fmea_rank_modes, fta_cut_set_probability,
    fta_minimal_cut_sets, fta_top_probability, pssa_allocate_target,
    pssa_channel_check, render_report_markdown, requirement_closure,
    severity_target, target_band, target_met,
)


class TestSeverityTargets(unittest.TestCase):

    def test_per_fh_target_magnitudes(self):
        self.assertEqual(SEVERITY_TARGETS["catastrophic"], 1e-9)
        self.assertEqual(SEVERITY_TARGETS["hazardous"], 1e-7)
        self.assertEqual(SEVERITY_TARGETS["major"], 1e-5)
        self.assertEqual(SEVERITY_TARGETS["minor"], 1e-3)

    def test_severity_target_lookup(self):
        self.assertEqual(severity_target("Catastrophic"), 1e-9)
        self.assertEqual(severity_target("Hazardous"), 1e-7)

    def test_target_met_strict(self):
        # 5e-10 < 1e-9 catastrophic: meets; equality fails
        self.assertTrue(target_met("catastrophic", 5e-10))
        self.assertFalse(target_met("catastrophic", 1e-9))
        self.assertFalse(target_met("major", 2e-5))   # 2e-5 is not < 1e-5
        self.assertTrue(target_met("major", 9e-6))

    def test_band_terminology(self):
        self.assertEqual(target_band(1e-10), "extremely improbable")
        self.assertEqual(target_band(5e-8), "extremely remote")
        self.assertEqual(target_band(1e-6), "remote")
        self.assertEqual(target_band(1e-4), "probable")

    def test_dal_mapping(self):
        self.assertEqual(dal_for_severity("Catastrophic"), "A")
        self.assertEqual(dal_for_severity("Hazardous"), "B")
        self.assertEqual(dal_for_severity("Major"), "C")
        self.assertEqual(dal_for_severity("Minor"), "D")

    def test_analyses_set_per_level(self):
        self.assertIn("CCA", analyses_for_level("A"))
        self.assertIn("CCA", analyses_for_level("B"))
        self.assertNotIn("CCA", analyses_for_level("C"))
        self.assertIn("FTA", analyses_for_level("D"))


class TestFaultTreeLogic(unittest.TestCase):

    def test_single_or_gate(self):
        structure = {"top": {"op": "OR", "children": ["a", "b"]}}
        self.assertEqual(fta_minimal_cut_sets(structure, "top"),
                         [frozenset({"a"}), frozenset({"b"})])

    def test_single_and_gate(self):
        structure = {"top": {"op": "AND", "children": ["a", "b"]}}
        self.assertEqual(fta_minimal_cut_sets(structure, "top"),
                         [frozenset({"a", "b"})])

    def test_and_of_ors_cartesian(self):
        structure = {
            "top": {"op": "AND", "children": ["x", "y"]},
            "x": {"op": "OR", "children": ["a", "b"]},
            "y": {"op": "OR", "children": ["c", "d"]},
        }
        result = fta_minimal_cut_sets(structure, "top")
        self.assertEqual(len(result), 4)
        self.assertIn(frozenset({"a", "c"}), result)
        self.assertIn(frozenset({"b", "d"}), result)

    def test_or_of_ands(self):
        structure = {
            "top": {"op": "OR", "children": ["x", "y"]},
            "x": {"op": "AND", "children": ["a", "b"]},
            "y": {"op": "AND", "children": ["c", "d"]},
        }
        result = fta_minimal_cut_sets(structure, "top")
        self.assertEqual(result, [frozenset({"a", "b"}),
                                  frozenset({"c", "d"})])

    def test_cut_set_probability_is_product(self):
        probs = {"a": 0.1, "b": 0.2, "c": 0.5}
        self.assertAlmostEqual(
            fta_cut_set_probability(frozenset({"a", "b", "c"}), probs),
            0.01)

    def test_top_event_probability_union_anchor(self):
        # two independent cut sets {A,B} (0.01*0.02) and {C} (0.03):
        # Q = 0.0002 + 0.03 - 0.0002*0.03 = 0.030194
        cut_sets = [frozenset({"A", "B"}), frozenset({"C"})]
        probs = {"A": 0.01, "B": 0.02, "C": 0.03}
        self.assertAlmostEqual(fta_top_probability(cut_sets, probs),
                               0.030194, places=6)

    def test_top_event_probability_overlapping_cut_sets(self):
        cut_sets = [frozenset({"A", "B"}), frozenset({"B", "C"})]
        probs = {"A": 0.1, "B": 0.2, "C": 0.3}
        expected = 0.02 + 0.06 - 0.02 * 0.06
        self.assertAlmostEqual(fta_top_probability(cut_sets, probs),
                               expected, places=12)


class TestFmeaCriticality(unittest.TestCase):

    def test_item_criticality_sum_of_modes(self):
        # C_r = sum beta*alpha*lambda*t ; example modes sum to 9e-6
        modes = [{"id": "M1", "alpha": 0.5, "beta": 1.0},
                 {"id": "M2", "alpha": 0.3, "beta": 1.0},
                 {"id": "M3", "alpha": 0.2, "beta": 0.5}]
        self.assertAlmostEqual(
            fmea_item_criticality(modes, 1.0e-5, 1.0), 9.0e-6)

    def test_mode_criticality_formula(self):
        # C_m = beta * alpha * lambda * t
        modes = [{"id": "M1", "alpha": 1.0, "beta": 1.0}]
        self.assertAlmostEqual(
            fmea_item_criticality(modes, 1.0e-5, 1.0), 1.0e-5)

    def test_rank_modes_dominant_flag(self):
        modes = [{"id": "M1", "alpha": 0.5, "beta": 1.0},
                 {"id": "M2", "alpha": 0.3, "beta": 1.0},
                 {"id": "M3", "alpha": 0.2, "beta": 0.5}]
        ranked = fmea_rank_modes(modes, 1.0e-5, 1.0)
        self.assertEqual(ranked[0]["id"], "M1")
        self.assertTrue(ranked[0]["dominant"])   # share 5/9 >= 0.5
        self.assertAlmostEqual(sum(r["cm"] for r in ranked), 9.0e-6)


class TestEventTree(unittest.TestCase):

    def test_failure_end_state_all_barriers_failed(self):
        # initiator 1e-5; detection p=0.999; remaining channel p=0.9995
        nodes = [("detect", 0.999), ("remain", 0.9995)]
        freqs = event_tree_frequencies(1e-5, nodes)
        self.assertEqual(len(freqs), 4)
        fail = event_tree_failure_frequency(freqs)
        expected = 1e-5 * (1 - 0.999) * (1 - 0.9995)
        self.assertAlmostEqual(fail["frequency"], expected)
        self.assertEqual(len(fail["sequences"]), 1)

    def test_total_probability_preserved(self):
        nodes = [("a", 0.99), ("b", 0.98)]
        freqs = event_tree_frequencies(2e-5, nodes)
        total = sum(f["frequency"] for f in freqs)
        self.assertAlmostEqual(total, 2e-5)


class TestPssa(unittest.TestCase):

    def test_or_allocation_shares_by_sum(self):
        alloc = pssa_allocate_target(1e-9, 2, "or")
        self.assertAlmostEqual(alloc["per_contributor"], 5e-10)
        self.assertTrue(alloc["verified"])

    def test_and_allocation_shares_by_product(self):
        alloc = pssa_allocate_target(1e-9, 2, "and")
        self.assertAlmostEqual(alloc["per_contributor"], 1e-9 ** 0.5)
        self.assertTrue(alloc["verified"])

    def test_channel_check(self):
        res = pssa_channel_check([1.0e-10, 2.0e-10], 1e-9, "or")
        self.assertAlmostEqual(res["total"], 3e-10)
        self.assertTrue(res["meets"])
        self.assertAlmostEqual(res["margin"], 1e-9 / 3e-10)


class TestClosure(unittest.TestCase):

    def test_closure_rollup_closed(self):
        conditions = [
            {"id": "FC-1", "severity": "catastrophic", "predicted_q": 3e-10},
            {"id": "FC-2", "severity": "hazardous", "predicted_q": 8e-9},
        ]
        rollup = closure_rollup(conditions)
        self.assertEqual(rollup["overall_gate"], "CLOSED")
        self.assertEqual(rollup["closed"], 2)

    def test_closure_rollup_open_when_condition_misses(self):
        conditions = [
            {"id": "FC-1", "severity": "catastrophic", "predicted_q": 3e-10},
            {"id": "FC-2", "severity": "hazardous", "predicted_q": 2e-7},
        ]
        rollup = closure_rollup(conditions)
        self.assertEqual(rollup["overall_gate"], "OPEN")
        self.assertEqual(rollup["open_conditions"], ["FC-2"])

    def test_requirement_closure(self):
        reqs = [{"id": "SR-1", "status": "verified"},
                {"id": "SR-2", "status": "open"}]
        out = requirement_closure(reqs)
        self.assertEqual(out["verified"], 1)
        self.assertEqual(out["open_requirements"], ["SR-2"])


class TestUncertainty(unittest.TestCase):

    def test_error_factor_three_sigma(self):
        # EF=3 -> sigma = ln(3)/1.645 (90% quantile)
        sigma = error_factor_to_sigma(3.0)
        self.assertAlmostEqual(sigma, 0.6678, places=3)

    def test_confidence_band_symmetry(self):
        from safety_assessment_core import confidence_band
        band = confidence_band(3e-10, error_factor_to_sigma(3.0))
        self.assertAlmostEqual(band["lower"], 1e-10)
        self.assertAlmostEqual(band["upper"], 9e-10)


class TestReportBuilder(unittest.TestCase):

    def test_example_model(self):
        model = build_safety_report(example_item())
        self.assertEqual(model["development_assurance_level"], "A")
        self.assertIn("CCA", model["analyses"])
        self.assertEqual(model["status"], "draft-for-review")
        # FTA top probability feeds the assessed catastrophic condition
        fta_q = model["fta"]["top_probability"]
        cat_row = [r for r in model["fha_rows"]
                   if r["severity"] == "catastrophic"][0]
        self.assertEqual(cat_row["assessed_per_fh"], fta_q)
        self.assertTrue(cat_row["meets_target"])
        self.assertEqual(model["closure"]["overall_gate"], "CLOSED")

    def test_top_event_probability_example(self):
        model = build_safety_report(example_item())
        # dual channel AND 1e-10 OR CCF 2e-10 -> ~3e-10
        self.assertAlmostEqual(model["fta"]["top_probability"], 3e-10,
                               delta=1e-19)

    def test_markdown_has_required_sections(self):
        md = example_report_markdown()
        for sec in ["## 1. Item and functions", "## 2. Functional hazard",
                    "## 3. Fault tree analysis", "## 4. FMEA",
                    "## 5. Event tree analysis", "## 6. PSSA",
                    "## 7. Common cause analysis", "## 8. Failure-rate",
                    "## 9. SSA closure"]:
            self.assertIn(sec, md)
        self.assertIn("not an approval", md.lower())
        self.assertIn("draft", md.lower())

    def test_core_gates_all_pass(self):
        model = build_safety_report(example_item())
        gates = check_report(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_all_pass(self):
        gates = check_report_markdown(example_report_markdown())
        self.assertTrue(gates["all_pass"], gates)

    def test_failing_report_fails_gate(self):
        # a condition that misses its target must flip the closure gate
        item = example_item()
        fc_list = [list(fc) for fc in item.failure_conditions]
        fc_list[1][5] = 2e-7   # hazardous condition now misses <1e-7
        item.failure_conditions = [tuple(fc) for fc in fc_list]
        model = build_safety_report(item)
        self.assertEqual(model["closure"]["overall_gate"], "OPEN")

    def test_standalone_no_skills_repo(self):
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = build_safety_report(example_item())
        self.assertTrue(model["development_assurance_level"] in "ABCDE")
        md = render_report_markdown(model)
        self.assertGreater(len(md), 3000)


if __name__ == "__main__":
    unittest.main()
