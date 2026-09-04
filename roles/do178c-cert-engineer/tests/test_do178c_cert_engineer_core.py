#!/usr/bin/env python3
"""Test do178c_core: the executable engine of the DO-178C role.

Proves the role can DO its job standalone (no AeroSkills needed):
DAL determination, coverage targets, independence, life cycle data,
PSAC generation, and evidence-gate checks.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))
from do178c_core import (
    SEVERITY_TO_DAL, build_psac, check_psac, check_psac_markdown,
    coverage_adequate, coverage_target, example_item,
    example_psac_markdown, independence_required, life_cycle_data,
    render_psac_markdown, structural_coverage,
)


class TestCoreDomainRules(unittest.TestCase):

    def test_severity_to_dal_mapping(self):
        self.assertEqual(SEVERITY_TO_DAL["catastrophic"], "A")
        self.assertEqual(SEVERITY_TO_DAL["hazardous"], "B")
        self.assertEqual(SEVERITY_TO_DAL["major"], "C")
        self.assertEqual(SEVERITY_TO_DAL["minor"], "D")

    def test_coverage_targets(self):
        self.assertEqual(coverage_target("A"), 0.98)
        self.assertEqual(coverage_target("C"), 0.95)
        self.assertIsNone(coverage_target("E"))

    def test_structural_by_dal(self):
        self.assertIn("mc-dc", structural_coverage("A"))
        self.assertIn("decision", structural_coverage("B"))
        self.assertEqual(structural_coverage("C"), ["statement"])
        self.assertEqual(structural_coverage("D"), [])

    def test_independence(self):
        self.assertTrue(independence_required("A"))
        self.assertTrue(independence_required("B"))
        self.assertFalse(independence_required("C"))

    def test_life_cycle_scope(self):
        self.assertGreater(len(life_cycle_data("A")), len(life_cycle_data("D")))
        self.assertIn("plan for software aspects of certification",
                      life_cycle_data("B"))

    def test_coverage_adequate(self):
        self.assertTrue(coverage_adequate("A", 0.99))
        self.assertFalse(coverage_adequate("A", 0.97))
        self.assertTrue(coverage_adequate("E", 0.0))  # no target


class TestPsacBuilder(unittest.TestCase):

    def test_example_level_b(self):
        model = build_psac(example_item())
        self.assertEqual(model["software_level"], "B")
        self.assertEqual(model["coverage_target"], 0.98)
        self.assertEqual(model["status"], "draft-for-review")

    def test_psac_has_required_sections(self):
        md = example_psac_markdown()
        for sec in ["## 1. Scope", "## 5. Software verification strategy",
                    "## 6. Software configuration management", "## 9. Objectives"]:
            self.assertIn(sec, md)
        self.assertIn("not an approval", md.lower())

    def test_core_gates_all_pass(self):
        model = build_psac(example_item())
        gates = check_psac(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_all_pass(self):
        md = example_psac_markdown()
        gates = check_psac_markdown(md, "B")
        self.assertTrue(gates["all_pass"], gates)

    def test_standalone_no_skills_repo(self):
        # Core must work with no AeroSkills present: set env to a bad path.
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = build_psac(example_item())
        self.assertTrue(model["software_level"] in "ABCDE")
        md = render_psac_markdown(model)
        self.assertGreater(len(md), 1000)


if __name__ == "__main__":
    unittest.main()
