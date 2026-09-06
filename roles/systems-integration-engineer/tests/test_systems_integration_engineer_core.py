#!/usr/bin/env python3
"""Test systems_integration_core: the executable engine of the Systems
Integration Engineer role.

Proves the role can DO its job standalone (no AeroSkills needed):
ARP4754A FDAL/IDAL assignment from severity, DAL propagation, function
development lifecycle stage checks, requirements allocation and
traceability counts, validation closure, integration verification method
selection, process objectives coverage, plan generation, and evidence
gates.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from systems_integration_core import (  # noqa: E402
    SEVERITY_TO_DAL, allocation_coverage, build_report, check_report,
    check_report_markdown, classify_change, classify_requirement,
    coverage_ratio, dal_from_severity, dal_index, dal_propagation_ok,
    example_item, example_report_markdown, fdal_for_function,
    identify_configuration_items, item_idal, method_allowed,
    recommended_methods, render_report_markdown, severity_rank,
    stage_checks, trace_closure_ratio, trace_closure_status,
    validation_closure_score, validation_independence_required,
    verification_independence_required,
)
os.environ.setdefault("ROLE_GEN_DATE", "2026-09-06")


class TestDomainRules(unittest.TestCase):

    def test_severity_to_dal_mapping(self):
        self.assertEqual(SEVERITY_TO_DAL["Catastrophic"], "A")
        self.assertEqual(SEVERITY_TO_DAL["Hazardous"], "B")
        self.assertEqual(SEVERITY_TO_DAL["Major"], "C")
        self.assertEqual(SEVERITY_TO_DAL["Minor"], "D")
        self.assertEqual(SEVERITY_TO_DAL["No safety effect"], "E")

    def test_severity_and_dal_index_anchors(self):
        self.assertEqual(severity_rank("Catastrophic"), 5)
        self.assertEqual(severity_rank("Major"), 3)
        self.assertEqual(dal_index("A"), 5)
        self.assertEqual(dal_index("C"), 3)

    def test_dal_from_severity_roundtrip(self):
        self.assertEqual(dal_from_severity("Hazardous"), "B")
        self.assertEqual(dal_from_severity("No safety effect"), "E")
        with self.assertRaises(ValueError):
            dal_from_severity("Unlikely")

    def test_fdal_from_most_severe_failure_condition(self):
        # a function with a catastrophic AND a major condition takes A
        fn = {"name": "Pitch control",
              "failure_conditions": [
                  {"failure_condition": "Reduced pitch authority",
                   "severity": "Major"},
                  {"failure_condition": "Loss of all pitch control",
                   "severity": "Catastrophic"}]}
        self.assertEqual(fdal_for_function(fn), "A")

    def test_item_idal_is_highest_fdal(self):
        self.assertEqual(item_idal(["A", "C"]), "A")
        self.assertEqual(item_idal(["C", "D", "B"]), "B")
        self.assertEqual(item_idal(["D"]), "D")
        with self.assertRaises(ValueError):
            item_idal([])

    def test_dal_propagation(self):
        self.assertTrue(dal_propagation_ok("A", "A"))
        self.assertTrue(dal_propagation_ok("C", "A"))   # higher is fine
        self.assertFalse(dal_propagation_ok("A", "C"))  # lower violates

    def test_verification_methods_by_level(self):
        self.assertEqual(recommended_methods("A"), ("test", "analysis"))
        self.assertIn("demonstration", recommended_methods("C"))
        self.assertEqual(len(recommended_methods("E")), 4)
        self.assertTrue(method_allowed("test", "A"))
        self.assertFalse(method_allowed("demonstration", "A"))
        self.assertTrue(method_allowed("demonstration", "C"))

    def test_independence_by_level(self):
        for dal in ("A", "B"):
            self.assertTrue(verification_independence_required(dal))
            self.assertTrue(validation_independence_required(dal))
        self.assertFalse(verification_independence_required("C"))
        self.assertFalse(validation_independence_required("E"))

    def test_allocation_coverage(self):
        reg = {"R1": "item-a", "R2": "item-b"}
        allocated, unallocated, ratio = allocation_coverage(
            reg, ["R1", "R2", "R3"])
        self.assertEqual(allocated, ["R1", "R2"])
        self.assertEqual(unallocated, ["R3"])
        self.assertAlmostEqual(ratio, 2.0 / 3.0)

    def test_trace_closure_on_example(self):
        item = example_item()
        status, gaps = trace_closure_status(item.trace_links)
        self.assertEqual(status, "closed")
        self.assertEqual(gaps, [])
        self.assertAlmostEqual(trace_closure_ratio(item.trace_links), 1.0)

    def test_trace_closure_detects_gap(self):
        links = [{"from": "SRATS-1", "to": "HLR-1", "verified": True},
                 {"from": "HLR-1", "to": "LLR-1", "verified": True},
                 {"from": "LLR-1", "to": "CODE-1", "verified": False}]
        status, gaps = trace_closure_status(links)
        self.assertEqual(status, "open")
        self.assertTrue(any("unverified" in g for g in gaps))

    def test_validation_closure(self):
        reqs = [("R1", True, "analysis"), ("R2", True, "test"),
                ("R3", False, "test")]
        ready, score = validation_closure_score(reqs)
        self.assertAlmostEqual(score, 2.0 / 3.0)
        self.assertFalse(ready)  # below 0.95 threshold
        self.assertTrue(validation_closure_score(
            [("R1", True, "analysis")])[0])

    def test_derived_requirement_classification(self):
        kind, fields = classify_requirement(
            {"has_parent_trace": False, "has_source_doc": False})
        self.assertEqual(kind, "derived")
        self.assertIn("derivation_rationale", fields)
        kind2, _ = classify_requirement(
            {"has_parent_trace": True, "has_source_doc": False})
        self.assertEqual(kind2, "allocated")

    def test_configuration_items_and_change_class(self):
        data = {"requirement": ["R-1", "R-2"],
                "design": ["D-1"],
                "verification": ["V-1"],
                "analysis": ["A-1"],
                "minutes": ["M-1"]}  # not a CI category
        cis = identify_configuration_items(data)
        self.assertEqual(len(cis), 5)
        self.assertTrue(all(c["type"] != "minutes" for c in cis))
        self.assertEqual(
            classify_change({"safety_relevant": True},
                            {"id": "C1", "interfaces_changed": True}),
            "major")
        self.assertEqual(classify_change({"safety_relevant": False},
                                        {"id": "C2"}), "minor")

    def test_coverage_ratio_anchors(self):
        self.assertEqual(coverage_ratio(60, 60), 1.0)
        self.assertEqual(coverage_ratio(57, 60), 0.95)
        with self.assertRaises(ValueError):
            coverage_ratio(61, 60)


class TestLifecycleStages(unittest.TestCase):

    def test_example_all_stages_pass(self):
        item = example_item()
        fdals = {f["name"]: fdal_for_function(f) for f in item.functions}
        idals = {it["name"]: item_idal(
            [fdals[n] for n in it["implements"]]) for it in item.items}
        stages = stage_checks(item, fdals, idals)
        self.assertEqual(len(stages), 6)
        for s in stages:
            self.assertTrue(s["pass"], "%s: %s" % (s["stage"], s["detail"]))

    def test_unallocated_requirement_fails_allocation_stage(self):
        item = example_item()
        fdals = {f["name"]: fdal_for_function(f) for f in item.functions}
        idals = {it["name"]: item_idal(
            [fdals[n] for n in it["implements"]]) for it in item.items}
        # drop one allocation -> stage 2 must fail
        reg = dict(item.allocation_register)
        orphan = item.requirement_ids[0]
        del reg[orphan]
        item.allocation_register = reg
        stages = stage_checks(item, fdals, idals)
        alloc_stage = [s for s in stages
                       if s["stage"] == "requirements-allocation"][0]
        self.assertFalse(alloc_stage["pass"])
        self.assertIn(orphan, alloc_stage["detail"])

    def test_unverified_trace_fails_trace_stage(self):
        item = example_item()
        fdals = {f["name"]: fdal_for_function(f) for f in item.functions}
        idals = {it["name"]: item_idal(
            [fdals[n] for n in it["implements"]]) for it in item.items}
        links = [dict(l) for l in item.trace_links]
        links[0]["verified"] = False
        item.trace_links = links
        stages = stage_checks(item, fdals, idals)
        tr_stage = [s for s in stages
                    if s["stage"] == "traceability-closure"][0]
        self.assertFalse(tr_stage["pass"])


class TestPlanBuilder(unittest.TestCase):

    def test_example_model_shape(self):
        model = build_report(example_item())
        self.assertEqual(model["status"], "draft-for-review")
        self.assertEqual(model["max_dal"], "A")
        self.assertEqual(len(model["functions"]), 4)
        self.assertEqual(len(model["items"]), 4)
        self.assertIn("safety-assessment-plan",
                      model["planning_artifacts"])
        self.assertEqual(model["safety_assessment_depth"], "full")
        self.assertEqual(model["allocation"]["total"], 60)
        self.assertEqual(model["allocation"]["unallocated"], [])
        self.assertEqual(model["traceability"]["status"], "closed")
        self.assertEqual(model["traceability"]["derived_flag_count"], 2)
        self.assertEqual(model["objectives"]["coverage"], 1.0)
        # all lifecycle stages pass in the worked example
        self.assertTrue(all(s["pass"] for s in model["lifecycle_stages"]))

    def test_plan_has_required_sections(self):
        md = example_report_markdown()
        for sec in ["## 1. Scope", "## 3. Function development assurance",
                    "## 5. Function development lifecycle",
                    "## 9. Integration verification plan",
                    "## 11. ARP4754A process objectives"]:
            self.assertIn(sec, md)
        self.assertIn("not an approval", md.lower())

    def test_core_gates_all_pass(self):
        model = build_report(example_item())
        gates = check_report(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_all_pass(self):
        md = example_report_markdown()
        gates = check_report_markdown(md)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_catch_bad_doc(self):
        gates = check_report_markdown("# nothing here")
        self.assertFalse(gates["all_pass"])

    def test_standalone_no_skills_repo(self):
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = build_report(example_item())
        self.assertIn(model["max_dal"], "ABCDE")
        md = render_report_markdown(model)
        self.assertGreater(len(md), 2000)


if __name__ == "__main__":
    unittest.main()
