#!/usr/bin/env python3
"""Test do254_hardware_core: the executable engine of the DO-254 role.

Proves the role can DO its job standalone (no AeroSkills needed):
DAL determination, AEH classification, verification expectations,
configuration management, requirement traceability, PHAC generation,
and evidence-gate checks.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from do254_hardware_core import (  # noqa: E402
    SEVERITY_TO_DAL, build_phac, capture_readiness, check_phac,
    check_phac_markdown, classify_aeh, classify_derived, cm_actions,
    coverage_adequate, coverage_ratio, example_item,
    example_phac_markdown, hci_entry, hw_change_class,
    independence_required, life_cycle_data, planning_artifacts,
    render_phac_markdown, req_issues, traceability_summary,
    verification_complete, verification_methods_for,
)


class TestCoreDomainRules(unittest.TestCase):

    def test_severity_to_dal_mapping(self):
        self.assertEqual(SEVERITY_TO_DAL["catastrophic"], "A")
        self.assertEqual(SEVERITY_TO_DAL["hazardous"], "B")
        self.assertEqual(SEVERITY_TO_DAL["major"], "C")
        self.assertEqual(SEVERITY_TO_DAL["minor"], "D")
        self.assertEqual(SEVERITY_TO_DAL["no-safety-effect"], "E")

    def test_aeh_classification_complex(self):
        # programmable logic / internal state / not fully verifiable from
        # top data / safety significant => complex (full process)
        self.assertEqual(classify_aeh(True, False, True, False), "complex")
        self.assertEqual(classify_aeh(False, True, True, False), "complex")
        self.assertEqual(classify_aeh(False, False, False, False), "complex")
        self.assertEqual(classify_aeh(False, False, True, True), "complex")
        self.assertEqual(classify_aeh(False, False, True, False), "simple")

    def test_planning_artifacts(self):
        self.assertIn("phac", planning_artifacts("complex"))
        self.assertNotIn("detailed-design", planning_artifacts("simple"))
        self.assertIn("verification", planning_artifacts("simple"))

    def test_verification_methods(self):
        self.assertEqual(verification_methods_for("complex", "B"),
                         {"test", "analysis", "review"})
        self.assertEqual(verification_methods_for("simple", "B"),
                         {"review"})

    def test_coverage_ratios(self):
        self.assertEqual(coverage_ratio("A"), 0.98)
        self.assertEqual(coverage_ratio("B"), 0.98)
        self.assertEqual(coverage_ratio("C"), 0.95)
        self.assertEqual(coverage_ratio("D"), 0.95)
        self.assertIsNone(coverage_ratio("E"))

    def test_independence(self):
        self.assertTrue(independence_required("A"))
        self.assertTrue(independence_required("B"))
        self.assertFalse(independence_required("C"))
        self.assertFalse(independence_required("D"))

    def test_coverage_adequate(self):
        self.assertTrue(coverage_adequate("A", 0.99))
        self.assertFalse(coverage_adequate("A", 0.97))
        self.assertTrue(coverage_adequate("E", 0.0))  # no target

    def test_verification_complete(self):
        self.assertTrue(verification_complete(
            ["test", "analysis", "review"], ["test", "review"]))
        self.assertFalse(verification_complete(["review"], ["test"]))

    def test_life_cycle_scope(self):
        self.assertGreater(len(life_cycle_data("A")),
                           len(life_cycle_data("D")))
        self.assertIn("plan for hardware aspects of certification (PHAC)",
                      life_cycle_data("B"))


class TestConfigManagementRules(unittest.TestCase):

    def test_change_class_1_conditions(self):
        # functional change => class 1
        self.assertEqual(hw_change_class(
            {"hardware_class": "simple", "safety_effect": "none",
             "functional_change": True})["class"], 1)
        # safety effect alone forces class 1
        self.assertEqual(hw_change_class(
            {"hardware_class": "simple", "safety_effect": "minor",
             "functional_change": False})["class"], 1)
        # complex hardware => class 1
        self.assertEqual(hw_change_class(
            {"hardware_class": "complex", "safety_effect": "none",
             "functional_change": False})["class"], 1)

    def test_change_class_2(self):
        self.assertEqual(hw_change_class(
            {"hardware_class": "simple", "safety_effect": "none",
             "functional_change": False})["class"], 2)

    def test_cm_actions_map(self):
        c1 = cm_actions(1)
        self.assertTrue(c1["reverification_required"])
        self.assertTrue(c1["independent_review"])
        c2 = cm_actions(2)
        self.assertFalse(c2["reverification_required"])
        self.assertFalse(c2["independent_review"])
        self.assertTrue(c2["ecr_required"])  # documented ECR still required

    def test_hci_entry_format(self):
        self.assertEqual(hci_entry("HW-A", "Rev B", "BL-1"),
                         "HW-A Rev B BL-1")


class TestRequirementsRules(unittest.TestCase):

    def test_vague_wording_flagged(self):
        self.assertIn("vague", req_issues(
            {"id": "R1", "text": "The item shall be suitable for flight.",
             "traceable": True}))
        self.assertNotIn("vague", req_issues(
            {"id": "R2", "text": "The item shall assert the output.",
             "traceable": True}))

    def test_missing_id_and_trace(self):
        issues = req_issues({"id": "", "text": "Req without id.",
                             "traceable": False})
        self.assertIn("missing-id", issues)
        self.assertIn("not-traceable", issues)

    def test_derived_classification(self):
        self.assertEqual(classify_derived(True), "allocated")
        self.assertEqual(classify_derived(False), "derived")

    def test_capture_readiness(self):
        reqs = [
            {"id": "R1", "text": "clean requirement one", "traceable": True},
            {"id": "R2", "text": "clean requirement two", "traceable": True},
            {"id": "R3", "text": "vague and adequate wording",
             "traceable": True},
        ]
        ready, score = capture_readiness(reqs)
        self.assertAlmostEqual(score, 2 / 3)
        self.assertFalse(ready)  # below 0.7 threshold

    def test_traceability_summary(self):
        item = example_item()
        t = traceability_summary(item.requirements)
        self.assertEqual(t["total"], 12)
        self.assertEqual(t["allocated"], 10)
        self.assertEqual(t["derived"], 2)
        self.assertTrue(t["allocated_traced_complete"])
        self.assertTrue(t["derived_justified_complete"])
        self.assertTrue(t["ready"])


class TestPhacBuilder(unittest.TestCase):

    def test_example_level_b_complex(self):
        model = build_phac(example_item())
        self.assertEqual(model["assurance_level"], "B")
        self.assertEqual(model["aeh_class"], "complex")
        self.assertEqual(model["coverage_ratio"], 0.98)
        self.assertEqual(model["status"], "draft-for-review")

    def test_phac_has_required_sections(self):
        md = example_phac_markdown()
        for sec in ["## 1. Scope", "## 5. Requirements capture",
                    "## 7. Verification strategy",
                    "## 8. Configuration management",
                    "## 11. Objectives summary"]:
            self.assertIn(sec, md)
        self.assertIn("not an approval", md.lower())

    def test_core_gates_all_pass(self):
        model = build_phac(example_item())
        gates = check_phac(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_all_pass(self):
        md = example_phac_markdown()
        gates = check_phac_markdown(md, "B")
        self.assertTrue(gates["all_pass"], gates)

    def test_standalone_no_skills_repo(self):
        # Core must work with no AeroSkills present: set env to a bad path.
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = build_phac(example_item())
        self.assertIn(model["assurance_level"], "ABCDE")
        md = render_phac_markdown(model)
        self.assertGreater(len(md), 1000)


if __name__ == "__main__":
    unittest.main()
