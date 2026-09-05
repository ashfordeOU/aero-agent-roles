#!/usr/bin/env python3
"""Test airworthiness_core: the executable engine of the
airworthiness-compliance-engineer role.

Proves the role can DO its job standalone (no AeroSkills needed):
applicability determination, means-of-compliance selection, compliance
matrix generation, and evidence-gate checks.

Author: ashfordeOU
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from airworthiness_core import (  # noqa: E402
    MOC_IDS, MOC_NAMES, REGS, SEVERITY_TO_DAL,
    build_matrix, check_matrix, check_matrix_markdown,
    compliance_row, determine_applicability, example_item,
    example_matrix_markdown, moc_is_valid, moc_suitability,
    render_matrix_markdown, safety_assessment_required, select_moc,
    severity_to_dal,
)


class TestCoreDomainRules(unittest.TestCase):

    def test_severity_to_dal_mapping(self):
        self.assertEqual(SEVERITY_TO_DAL["catastrophic"], "A")
        self.assertEqual(SEVERITY_TO_DAL["hazardous"], "B")
        self.assertEqual(SEVERITY_TO_DAL["major"], "C")
        self.assertEqual(SEVERITY_TO_DAL["minor"], "D")
        self.assertEqual(severity_to_dal("hazardous"), "B")

    def test_safety_assessment_rule(self):
        # 25.1309 practice: catastrophic/hazardous/major need the SSA.
        self.assertTrue(safety_assessment_required("catastrophic"))
        self.assertTrue(safety_assessment_required("hazardous"))
        self.assertTrue(safety_assessment_required("major"))
        self.assertFalse(safety_assessment_required("minor"))
        self.assertFalse(safety_assessment_required("no-safety-effect"))
        with self.assertRaises(ValueError):
            safety_assessment_required("very-bad")

    def test_moc_suitability_rules(self):
        # Structure: analysis primary, static/ground test evidence.
        self.assertEqual(moc_suitability("structure", "n/a", "n/a"), [1, 2])
        # Novel structure adds flight test.
        self.assertEqual(
            moc_suitability("structure", "n/a", "n/a", novel=True), [1, 2, 3])
        # Hazardous systems: analysis + MOC 6 safety assessment.
        self.assertEqual(
            moc_suitability("systems", "hazardous", "B"), [1, 6])
        # Equipment: qualification ground test with analysis support.
        self.assertEqual(moc_suitability("equipment"), [2, 1])
        with self.assertRaises(ValueError):
            moc_suitability("quantum", "n/a", "n/a")

    def test_real_regs_are_real(self):
        # Regs in the register must be real FAR-25 paragraphs (public
        # domain; register verified against the public eCFR titles).
        for number, rec in REGS.items():
            self.assertRegex(number, r"^25\.\d{3,4}$")
            self.assertTrue(rec["title"])
            self.assertIn(rec["subpart"], "ABCDEFGH")
        for num in ("25.1309", "25.1329", "25.301", "25.571",
                    "25.607", "25.683", "25.671", "25.1301"):
            self.assertIn(num, REGS)

    def test_applicability_transport(self):
        verdict = determine_applicability("25.1309", "transport")
        self.assertTrue(verdict["applicable"])
        verdict2 = determine_applicability("25.1329", "transport-category")
        self.assertTrue(verdict2["applicable"])

    def test_applicability_not_transport(self):
        # Part 25 paragraphs do not apply to a normal-category airplane
        # (that certifies under Part 23 / CS-23).
        verdict = determine_applicability("25.1309", "normal")
        self.assertFalse(verdict["applicable"])
        self.assertIn("Part 23", verdict["reason"])
        with self.assertRaises(ValueError):
            determine_applicability("25.1309", "airship")
        with self.assertRaises(ValueError):
            determine_applicability("99.9999", "transport")
        with self.assertRaises(ValueError):
            determine_applicability("25.9999", "transport")

    def test_applicability_change_scope(self):
        # Structure paragraphs screen out when the STC touches only
        # systems/flight-controls/equipment.
        scope = ["systems", "flight-controls", "equipment"]
        self.assertTrue(
            determine_applicability("25.1309", "transport", scope)["applicable"])
        self.assertFalse(
            determine_applicability("25.571", "transport", scope)["applicable"])
        self.assertFalse(
            determine_applicability("25.301", "transport", scope)["applicable"])


class TestMocSelection(unittest.TestCase):

    def test_select_moc_far25_vocabulary(self):
        moc = select_moc("25.1309", "FAR-25")
        self.assertEqual(moc["reg"], "25.1309")
        self.assertEqual(moc["item_kind"], "systems")
        self.assertEqual(moc["dal"], "B")          # hazardous context
        self.assertTrue(moc["safety_assessment"])
        # Real vocabulary words only.
        for m in moc["methods"]:
            self.assertTrue(moc_is_valid(m))
        self.assertIn("analysis", moc["moc_display"])
        self.assertIn("safety assessment", moc["moc_display"])

    def test_select_moc_cs25_scheme(self):
        moc = select_moc("25.1309", "CS-25")
        self.assertIn("MOC", moc["moc_display"])
        self.assertIn("MOC 6 safety assessment", moc["moc_display"])
        # ids must all be real MOC class ids
        for i in moc["moc_ids"]:
            self.assertIn(i, MOC_IDS)

    def test_select_moc_extras_and_novelty(self):
        # Autopilot flight guidance is novel on the type: ground test is
        # added; the reg carries flight test from demonstration practice.
        moc = select_moc("25.1329", "FAR-25", novel=True)
        self.assertIn("flight test", moc["methods"])
        self.assertIn(2, moc["moc_ids"])   # test MOC present for novel item
        # 25.683 operation tests carries a ground test MOC.
        moc683 = select_moc("25.683", "FAR-25")
        self.assertIn("ground test", moc683["methods"])

    def test_moc_names_real(self):
        self.assertEqual(MOC_NAMES[1], "engineering/analysis")
        self.assertEqual(MOC_NAMES[5], "certification by similarity")
        self.assertEqual(MOC_NAMES[6], "safety assessment")
        self.assertFalse(moc_is_valid("quantum compliance"))
        with self.assertRaises(ValueError):
            select_moc("25.9999", "FAR-25")


class TestMatrixBuilder(unittest.TestCase):

    def test_build_matrix_example(self):
        model = build_matrix(example_item())
        self.assertEqual(model["certification_basis"], "FAR-25")
        self.assertEqual(model["status"], "draft-for-review")
        # 8 candidate regs: 5 applicable, 3 screened out.
        self.assertEqual(model["row_count"], 8)
        self.assertEqual(model["applicable_count"], 5)
        self.assertEqual(model["coverage"], 1.0)
        self.assertEqual(model["issues"], [])
        # The applicable autopilot regs are present.
        regs_app = {r["reg"] for r in model["rows"] if r["applicable"]}
        self.assertEqual(regs_app,
                         {"25.1301", "25.1309", "25.1329", "25.671", "25.683"})

    def test_compliance_row_fields(self):
        row = compliance_row("25.1309", example_item())
        self.assertTrue(row["applicable"])
        self.assertEqual(row["status"], "proposed")
        self.assertEqual(row["dal"], "B")
        self.assertTrue(row["safety_assessment"])
        self.assertIn("System safety assessment", row["compliance_document"])
        self.assertTrue(row["owner"])
        # No blank fields anywhere in the row.
        for v in row.values():
            self.assertNotIn("___", str(v))

    def test_matrix_has_no_blanks(self):
        md = example_matrix_markdown()
        self.assertNotIn("___", md)
        self.assertGreater(len(md), 1500)


class TestGates(unittest.TestCase):

    def test_core_gates_all_pass(self):
        model = build_matrix(example_item())
        gates = check_matrix(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_core_gates_fail_on_missing_doc(self):
        model = build_matrix(example_item())
        # Break a row: applicable reg without a compliance document.
        row = next(r for r in model["rows"] if r["applicable"])
        row["compliance_document"] = ""
        gates = check_matrix(model)
        self.assertFalse(gates["all_pass"])
        self.assertFalse(gates["all_applicable_have_doc"])

    def test_core_gates_fail_on_found_status(self):
        model = build_matrix(example_item())
        model["rows"][0]["status"] = "compliant"
        gates = check_matrix(model)
        self.assertFalse(gates["all_pass"])
        self.assertFalse(gates["statuses_honest"])

    def test_markdown_gates_all_pass(self):
        md = example_matrix_markdown()
        gates = check_matrix_markdown(md)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_fail_on_blank(self):
        md = example_matrix_markdown().replace("## Compliance matrix",
                                               "## Compliance ___ matrix")
        gates = check_matrix_markdown(md)
        self.assertFalse(gates["all_pass"])
        self.assertFalse(gates["no_blank_fields"])

    def test_standalone_no_skills_repo(self):
        # Core must work with no AeroSkills present.
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = build_matrix(example_item())
        self.assertTrue(model["row_count"] >= 5)
        self.assertTrue(model["coverage"] >= 0.5)
        md = render_matrix_markdown(model)
        self.assertGreater(len(md), 1500)
        self.assertTrue(check_matrix_markdown(md)["all_pass"])


if __name__ == "__main__":
    unittest.main()
