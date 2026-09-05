#!/usr/bin/env python3
"""Test as9100_core: the executable engine of the AS9100 auditor role.

Proves the role can DO its job standalone (no AeroSkills needed):
NC classification on the finding ladder, corrective action closure
chain scoring, audit program numbers (sample size, due date), findings
report generation, and evidence-gate checks.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))
from as9100_core import (
    AS9100D_SECTIONS, BASE_INTERVAL_MONTHS, CLAUSE_BY_ID,
    NC_CLASSIFICATIONS, audit_due_date, audit_findings, audit_sample_size,
    build_findings, check_findings, check_findings_markdown,
    classify_nc, containment_ok, corrective_action_status,
    effectiveness_evidence_ok, example_findings_markdown, example_item,
    render_findings_markdown, root_cause_chain_ok,
)


class TestClassificationLadder(unittest.TestCase):

    def test_high_severity_is_major(self):
        self.assertEqual(classify_nc(4, False, False), "major")
        self.assertEqual(classify_nc(5, False, False), "major")

    def test_mid_severity_is_minor(self):
        self.assertEqual(classify_nc(2, False, False), "minor")
        self.assertEqual(classify_nc(3, False, False), "minor")

    def test_systemic_escalates_minor_to_major(self):
        self.assertEqual(classify_nc(2, True, False), "major")
        self.assertEqual(classify_nc(3, True, False), "major")

    def test_escaped_detection_escalates_to_major(self):
        # Detection failure means containment of suspect output is
        # required, which is a major regardless of severity.
        self.assertEqual(classify_nc(1, False, True), "major")
        self.assertEqual(classify_nc(2, False, True), "major")

    def test_low_severity_is_observation(self):
        self.assertEqual(classify_nc(1, False, False), "observation")

    def test_severity_out_of_range_raises(self):
        for bad in (0, 6, -1, 9):
            with self.assertRaises(ValueError):
                classify_nc(bad, False, False)


class TestCorrectiveActionChain(unittest.TestCase):

    def test_closure_chain_stages(self):
        record = {
            "problem": "recurring defect",
            "containment": "quarantine suspect lot",
            "whys": ["cause a", "cause b", "cause c"],
            "corrective_action": "update process control",
            "effectiveness_evidence": "",
            "root_cause_statement": "cause c",
        }
        self.assertEqual(corrective_action_status(record),
                         "effectiveness-pending")
        record["effectiveness_evidence"] = "three clean lots observed"
        self.assertEqual(corrective_action_status(record), "closed")

    def test_circular_effectiveness_evidence_fails(self):
        record = {
            "problem": "recurring defect",
            "containment": "quarantine",
            "whys": ["a", "b", "c"],
            "corrective_action": "update control",
            "effectiveness_evidence": "cause c",
            "root_cause_statement": "cause c",
        }
        self.assertFalse(effectiveness_evidence_ok(
            record["effectiveness_evidence"],
            record["root_cause_statement"]))
        self.assertEqual(corrective_action_status(record),
                         "effectiveness-pending")

    def test_chain_helpers(self):
        self.assertTrue(containment_ok("quarantine"))
        self.assertFalse(containment_ok("none"))
        self.assertTrue(root_cause_chain_ok(["a", "b", "c"]))
        self.assertFalse(root_cause_chain_ok(["a", "b"]))
        self.assertFalse(root_cause_chain_ok(["a", "a", "a"]))


class TestAuditNumbers(unittest.TestCase):

    def test_sample_size_at_confidence_anchors(self):
        self.assertEqual(audit_sample_size(400, 0.95), 20)
        self.assertEqual(audit_sample_size(400, 0.90), 16)
        self.assertEqual(audit_sample_size(400, 0.99), 24)

    def test_sample_size_validation(self):
        with self.assertRaises(ValueError):
            audit_sample_size(0)
        with self.assertRaises(ValueError):
            audit_sample_size(10, 0.4)

    def test_audit_due_date_risk_scaling(self):
        # 12-month base scaled by risk: high 0.5, low 1.5.
        self.assertEqual(audit_due_date("2026-03-15", "high"), "2026-09-15")
        self.assertEqual(audit_due_date("2026-03-15", "medium"), "2027-03-15")
        self.assertEqual(audit_due_date("2026-03-15", "low"), "2027-09-15")

    def test_audit_due_date_clamps_month_end(self):
        self.assertEqual(audit_due_date("2026-01-31", "medium"), "2027-01-31")
        self.assertEqual(audit_due_date("2024-01-31", "high"), "2024-07-31")


class TestFindingsBuilder(unittest.TestCase):

    def test_example_audit_covers_all_classifications(self):
        item = example_item()
        model = audit_findings(item)
        cls = {f["classification"] for f in model["findings"]}
        self.assertTrue({"major", "minor", "observation"} <= cls)
        self.assertGreaterEqual(model["counts"]["major"], 1)
        self.assertGreaterEqual(model["counts"]["minor"], 1)
        self.assertGreaterEqual(model["counts"]["observation"], 1)
        self.assertEqual(model["counts"]["total"], len(item.issues))

    def test_findings_model_complete(self):
        model = audit_findings(example_item())
        self.assertEqual(model["document_type"],
                         "AS9100 Internal Audit Findings Report")
        self.assertIn("AS9100D", " ".join(model["audit"]["criteria"]))
        for f in model["findings"]:
            self.assertIn(f["clause"], CLAUSE_BY_ID)
            self.assertIn(f["classification"], NC_CLASSIFICATIONS)
            self.assertTrue(f["objective_evidence"])
            self.assertTrue(f["requirement"])
            if f["classification"] in ("major", "minor"):
                ca = f["corrective_action"]
                self.assertTrue(containment_ok(ca["containment"]))
                self.assertTrue(root_cause_chain_ok(ca["whys"]))
                self.assertTrue(ca["corrective_action"])
                self.assertEqual(f["ca_status"], "effectiveness-pending")
            else:
                self.assertIsNone(f["corrective_action"])
                self.assertEqual(f["ca_status"], "not-required")

    def test_clause_ids_are_real(self):
        # Example NCs cite only leaf-verified AS9100D clause ids.
        model = audit_findings(example_item())
        cited = {f["clause"] for f in model["findings"]}
        self.assertTrue({"8.7", "10.2"} <= cited)
        self.assertTrue(cited <= set(CLAUSE_BY_ID))
        self.assertGreaterEqual(len(AS9100D_SECTIONS), 7)  # sections 4-10

    def test_example_numbers_match_formulas(self):
        item = example_item()
        model = audit_findings(item)
        self.assertEqual(model["sampling"]["sample_size"],
                         audit_sample_size(item.record_population,
                                           item.confidence_level))
        self.assertEqual(model["sampling"]["sample_size"], 20)
        self.assertEqual(model["audit"]["next_audit_due"],
                         audit_due_date(item.audit_date, item.process_risk))

    def test_build_findings_matches_audit_findings(self):
        item = example_item()
        self.assertEqual(build_findings(item), audit_findings(item))


class TestGatesAndRender(unittest.TestCase):

    def test_core_gates_all_pass(self):
        model = audit_findings(example_item())
        gates = check_findings(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_all_pass(self):
        md = example_findings_markdown()
        gates = check_findings_markdown(md)
        self.assertTrue(gates["all_pass"], gates)

    def test_render_has_no_blanks(self):
        md = example_findings_markdown()
        low = md.lower()
        self.assertNotIn("___", md)
        self.assertNotIn("| |", md)
        self.assertNotIn("| - |", md)
        self.assertIn("proposed", low)
        self.assertIn("not a", low)

    def test_standalone_no_skills_repo(self):
        # Core must work with no AeroSkills present: set env to a bad path.
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        item = example_item()
        model = build_findings(item)
        md = render_findings_markdown(model)
        self.assertGreater(len(md), 1500)
        self.assertTrue(check_findings(model)["all_pass"])
        self.assertTrue(check_findings_markdown(md)["all_pass"])


if __name__ == "__main__":
    unittest.main()
