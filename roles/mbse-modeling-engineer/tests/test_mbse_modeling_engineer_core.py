#!/usr/bin/env python3
"""Test mbse_modeling_core: the executable engine of the MBSE role.

Proves the role can DO its job standalone (no AeroSkills needed):
diagram-kind selection vs modeling purpose, requirement id/atomicity/
verifiability screening, satisfy/verify coverage and status roll-up,
block-definition and allocation closure, N2 interface counts and
missing links, state-machine reachability and conflicts, parametric
constraint verdicts, plan generation, and evidence-gate checks.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from mbse_modeling_core import (  # noqa: E402
    DEFAULT_MARGIN_THRESHOLD, SEVERITY_TO_FDAL, allocation_closure,
    block_definition_verdict, build_matrix, build_plan, check_plan,
    check_plan_markdown, constraint_verdict, count_shall_clauses,
    derive_chain_check, diagram_kind_name, example_item,
    example_plan_markdown, fdal_from_severity, find_vague_terms,
    interface_counts, isolated_elements, missing_links,
    model_viewpoint_verdict, render_plan_markdown, requirement_verifiability,
    rollup_verification_status, satisfy_coverage, selection_verdict,
    sum_values, sysml_diagram_for, total_interfaces, traceability_status,
    transition_conflicts, unreachable_states, validate_requirement_id,
    verify_coverage, weighted_score,
)


class TestDiagramSelection(unittest.TestCase):

    def test_purpose_to_kind_mapping(self):
        self.assertEqual(sysml_diagram_for("system-composition"), "bdd")
        self.assertEqual(sysml_diagram_for("internal-connections"), "ibd")
        self.assertEqual(sysml_diagram_for("constraint-analysis"), "param")
        self.assertEqual(sysml_diagram_for("requirements-traceability"), "req")
        self.assertEqual(sysml_diagram_for("functional-flow"), "act")
        self.assertEqual(sysml_diagram_for("message-ordering"), "seq")
        self.assertEqual(sysml_diagram_for("state-transition"), "stm")
        self.assertEqual(sysml_diagram_for("use-case-scoping"), "uc")
        self.assertEqual(sysml_diagram_for("model-organization"), "pkg")

    def test_unknown_purpose_raises(self):
        with self.assertRaises(ValueError):
            sysml_diagram_for("not-a-purpose")

    def test_diagram_names(self):
        self.assertEqual(diagram_kind_name("bdd"), "block definition diagram")
        self.assertEqual(diagram_kind_name("param"), "parametric diagram")

    def test_block_definition_verdict(self):
        parts = ["A", "B", "C"]
        self.assertEqual(block_definition_verdict(parts, ["A", "B"]), "valid")
        self.assertEqual(block_definition_verdict(parts, ["A", "D"]), "invalid")
        self.assertEqual(block_definition_verdict([], ["A"]), "invalid")

    def test_viewpoint_coverage(self):
        full = {"structure": True, "behavior": True,
                "requirements": True, "parametric": True}
        self.assertEqual(model_viewpoint_verdict(full), "complete")
        gap = dict(full, parametric=False)
        self.assertEqual(model_viewpoint_verdict(gap), "missing")
        with self.assertRaises(ValueError):
            model_viewpoint_verdict({"structure": True, "bogus": True})


class TestRequirementsModeling(unittest.TestCase):

    def test_requirement_id_format(self):
        self.assertTrue(validate_requirement_id("SYS-001"))
        self.assertTrue(validate_requirement_id("CPCS-0042"))
        self.assertFalse(validate_requirement_id("sys-001"))
        self.assertFalse(validate_requirement_id("SYS-1"))
        self.assertFalse(validate_requirement_id("SYS-0000001"))

    def test_shall_clause_count(self):
        self.assertEqual(count_shall_clauses("The system shall do X."), 1)
        self.assertEqual(
            count_shall_clauses("The system shall do X and shall do Y."), 2)
        self.assertEqual(count_shall_clauses("No obligation here."), 0)

    def test_vague_terms_detected(self):
        self.assertEqual(find_vague_terms("Shall be adequate and suitable."),
                         ["adequate", "suitable"])
        self.assertEqual(find_vague_terms("Shall hold 0.05 psi."), [])

    def test_verifiability_verdict(self):
        ok = {"id": "SYS-001", "method": "test",
              "text": "The system shall open the valve within 2 s."}
        self.assertTrue(requirement_verifiability(ok)["verifiable"])
        bad = {"id": "SYS-002", "method": "test",
               "text": "The system shall respond adequately and shall recover "
                       "timely."}
        v = requirement_verifiability(bad)
        self.assertFalse(v["verifiable"])
        self.assertTrue(any("shall-clause" in r for r in v["reasons"]))
        self.assertTrue(any("vague terms" in r for r in v["reasons"]))

    def test_rollup(self):
        self.assertEqual(rollup_verification_status([]), "not-assessed")
        self.assertEqual(rollup_verification_status(["verified", "verified"]),
                         "verified")
        self.assertEqual(rollup_verification_status(
            ["verified", "failed"]), "failed")
        self.assertEqual(rollup_verification_status(
            ["verified", "in-review"]), "in-review")

    def test_satisfy_verify_coverage(self):
        ids = ["SYS-001", "SYS-002", "SYS-003"]
        frac, missing = satisfy_coverage(ids, [("SYS-001", "B1"),
                                               ("SYS-003", "B3")])
        self.assertEqual(frac, 2 / 3.0)
        self.assertEqual(missing, ["SYS-002"])
        frac2, _ = verify_coverage(ids, [("SYS-001", "V1"),
                                         ("SYS-002", "V2"),
                                         ("SYS-003", "V3")])
        self.assertEqual(frac2, 1.0)

    def test_derive_chain_check(self):
        ok, issues = derive_chain_check([("SYS-001", "SYS-101")])
        self.assertTrue(ok)
        self.assertEqual(issues, [])
        bad, issues2 = derive_chain_check([("SYS-001", "SYS-001")])
        self.assertFalse(bad)
        self.assertIn("self-derive 'SYS-001'", issues2)


class TestAllocationAndTraceability(unittest.TestCase):

    def test_allocation_closure(self):
        closed, unalloc = allocation_closure(
            ["f1", "f2"], ["f1", "f2"])
        self.assertTrue(closed)
        self.assertEqual(unalloc, [])
        closed2, unalloc2 = allocation_closure(["f1", "f2"], ["f1"])
        self.assertFalse(closed2)
        self.assertEqual(unalloc2, ["f2"])

    def test_traceability_status_thresholds(self):
        # critical (FDAL A/B) requires full closure
        self.assertEqual(traceability_status(5, 5, critical=True), "closed")
        self.assertEqual(traceability_status(4, 5, critical=True), "open")
        # non-critical allows the 90% bar (int(5*0.9) == 4)
        self.assertEqual(traceability_status(5, 5, critical=False), "closed")
        self.assertEqual(traceability_status(4, 5, critical=False), "closed")
        self.assertEqual(traceability_status(3, 5, critical=False), "open")
        with self.assertRaises(ValueError):
            traceability_status(6, 5)


class TestN2InterfaceModel(unittest.TestCase):

    def _m(self):
        elements = ["A", "B", "C"]
        matrix = build_matrix(elements, [("A", "B"), ("B", "A"),
                                         ("A", "C")])
        return elements, matrix

    def test_build_matrix_and_total(self):
        elements, matrix = self._m()
        self.assertEqual(matrix[0][1], 1)
        self.assertEqual(matrix[1][0], 1)
        self.assertEqual(total_interfaces(elements, matrix), 3)

    def test_interface_counts_row_plus_column(self):
        elements, matrix = self._m()
        counts = interface_counts(elements, matrix)
        self.assertEqual(counts["A"], 3)   # sends 2, receives 1
        self.assertEqual(counts["B"], 2)
        self.assertEqual(counts["C"], 1)

    def test_missing_and_isolated(self):
        elements, matrix = self._m()
        self.assertEqual(missing_links(elements, matrix,
                                       [("B", "C")]), [("B", "C")])
        self.assertEqual(missing_links(elements, matrix,
                                       [("A", "B")]), [])
        self.assertEqual(isolated_elements(["A", "B", "D"],
                                           build_matrix(["A", "B", "D"],
                                                        [("A", "B")])),
                         ["D"])


class TestStateMachine(unittest.TestCase):

    def _machine(self):
        return {"states": ["S1", "S2", "S3"], "initial": "S1",
                "transitions": [
                    {"from": "S1", "event": "go", "to": "S2"},
                    {"from": "S2", "event": "back", "to": "S1"},
                ]}

    def test_unreachable_states(self):
        m = self._machine()
        m["transitions"].append({"from": "S3", "event": "lonely", "to": "S3"})
        self.assertEqual(unreachable_states(m, "S1"), ["S3"])

    def test_transition_conflicts(self):
        m = self._machine()
        m["transitions"].append({"from": "S1", "event": "go", "to": "S3"})
        self.assertEqual(transition_conflicts(m),
                         ["S1 enabled by event 'go': 2 transitions"])

    def test_no_conflicts_single_transition(self):
        self.assertEqual(transition_conflicts(self._machine()), [])


class TestParametricsAndTrade(unittest.TestCase):

    def test_constraint_sum(self):
        self.assertAlmostEqual(sum_values([4.2, 12.8, 6.5, 0.9]), 24.4)

    def test_constraint_verdict_le(self):
        v = constraint_verdict(24.4, 30.0, op="le")
        self.assertTrue(v["satisfied"])
        self.assertAlmostEqual(v["margin"], 5.6)
        self.assertAlmostEqual(v["ratio"], round(24.4 / 30.0, 6))

    def test_constraint_verdict_fail_and_eq(self):
        self.assertFalse(constraint_verdict(35.0, 30.0, op="le")["satisfied"])
        self.assertTrue(constraint_verdict(30.0, 30.0, op="eq")["satisfied"])
        self.assertFalse(constraint_verdict(30.5, 30.0, op="eq")["satisfied"])
        with self.assertRaises(ValueError):
            constraint_verdict(1.0, 2.0, op="zz")

    def test_weighted_score(self):
        self.assertAlmostEqual(weighted_score([0.5, 0.3, 0.2],
                                              [8, 6, 9]), 7.6)
        with self.assertRaises(ValueError):
            weighted_score([0.6, 0.3, 0.2], [8, 6, 9])  # sums to 1.1

    def test_selection_verdict(self):
        v = selection_verdict(7.6, 6.8, margin_threshold=0.05)
        self.assertEqual(v["winner"], "best")
        self.assertAlmostEqual(v["margin"], 0.8)
        self.assertTrue(v["confident"])
        t = selection_verdict(7.6, 7.6)
        self.assertEqual(t["winner"], "tie")


class TestPlanBuilderAndGates(unittest.TestCase):

    def test_example_level_b(self):
        model = build_plan(example_item())
        self.assertEqual(model["development_assurance_level"], "B")
        self.assertEqual(model["severity_source"], "hazardous")
        self.assertEqual(model["status"], "draft-for-review")
        self.assertTrue(model["critical"])

    def test_example_numbers(self):
        model = build_plan(example_item())
        self.assertEqual(model["requirements_total"], 5)
        self.assertEqual(model["verifiable_count"], 5)
        self.assertEqual(model["satisfy_fraction"], 1.0)
        self.assertEqual(model["verify_fraction"], 1.0)
        self.assertEqual(model["rollup"], "verified")
        self.assertEqual(model["traceability_status"], "closed")
        self.assertEqual(model["viewpoint_verdict"], "complete")
        self.assertEqual(model["bdd_verdict"], "valid")
        self.assertTrue(model["allocation_closed"])
        self.assertEqual(model["n2"]["total"], 4)
        self.assertEqual(model["n2"]["missing"], [])
        self.assertEqual(model["n2"]["isolated"], [])
        self.assertEqual(len(model["behavior"]["unreachable"]), 0)
        self.assertEqual(model["behavior"]["conflicts"], [])
        self.assertEqual(model["model_review"], "ready")
        # parametric numbers: mass 24.4 <= 30 kg; power 101 <= 120 W
        c0, c1 = model["constraints"]
        self.assertTrue(c0["satisfied"])
        self.assertAlmostEqual(c0["computed"], 24.4)
        self.assertAlmostEqual(c0["margin"], 5.6)
        self.assertAlmostEqual(c1["computed"], 101.0)
        # decision record: CON-A wins with margin 0.8
        self.assertEqual(model["decision_record"]["winner"]["id"], "CON-A")
        self.assertTrue(model["decision_record"]["selection"]["confident"])

    def test_fdal_override(self):
        item = example_item()
        item.failure_condition = "catastrophic"
        model = build_plan(item)
        self.assertEqual(model["development_assurance_level"], "A")
        self.assertTrue(model["critical"])
        self.assertEqual(model["traceability_status"], "closed")

    def test_core_gates_all_pass(self):
        model = build_plan(example_item())
        gates = check_plan(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_plan_has_required_sections(self):
        md = example_plan_markdown()
        for sec in ["## 1. Scope", "## 4. Requirements architecture",
                    "## 7. Interface model (N2)", "## 9. Parametric "
                    "constraints", "## 11. Model governance"]:
            self.assertIn(sec, md)
        self.assertIn("not an approval", md.lower())

    def test_markdown_gates_all_pass(self):
        md = example_plan_markdown()
        gates = check_plan_markdown(md)
        self.assertTrue(gates["all_pass"], gates)

    def test_standalone_no_skills_repo(self):
        # Core must work with no AeroSkills present.
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = build_plan(example_item())
        self.assertIn(model["development_assurance_level"], "ABCDE")
        md = render_plan_markdown(model)
        self.assertGreater(len(md), 3000)

    def test_severity_mapping(self):
        self.assertEqual(SEVERITY_TO_FDAL["catastrophic"], "A")
        self.assertEqual(fdal_from_severity("hazardous"), "B")
        self.assertEqual(fdal_from_severity("major"), "C")
        self.assertEqual(fdal_from_severity("nonsense"), "E")


if __name__ == "__main__":
    unittest.main()
