#!/usr/bin/env python3
"""Role test: engineering-analysis-engineer."""
import os
import re
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "engineering-analysis-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates", "analysis-memo-template.md")

EXPECTED_BOUND = [
    "cross-cutting/units-atmos/isa-atmosphere",
    "cross-cutting/units-atmos/density-altitude",
    "cross-cutting/units-atmos/airspeed-conversion",
    "cross-cutting/units-atmos/unit-conversion",
    "cross-cutting/units-atmos/dimensional-analysis",
    "cross-cutting/units-atmos/temperature-conversion",
    "cross-cutting/numerics/finite-difference-derivatives",
    "cross-cutting/numerics/numerical-integration",
    "cross-cutting/numerics/ode-solvers",
    "cross-cutting/numerics/root-finding",
    "cross-cutting/numerics/interpolation",
    "cross-cutting/numerics/least-squares-regression",
    "cross-cutting/numerics/optimization-algorithms",
    "cross-cutting/numerics/eigenvalue-decomposition",
    "cross-cutting/numerics/singular-value-decomposition",
    "cross-cutting/numerics/matrix-operations",
    "cross-cutting/numerics/complex-number-algebra",
    "cross-cutting/numerics/quaternion-algebra",
    "cross-cutting/numerics/fast-fourier-transform",
    "cross-cutting/numerics/fir-filter-design",
    "cross-cutting/numerics/digital-filter-design",
    "cross-cutting/numerics/power-spectral-density",
    "cross-cutting/numerics/uncertainty-propagation",
    "cross-cutting/numerics/monte-carlo-sampling",
    "cross-cutting/numerics/probability-distributions",
    "cross-cutting/numerics/confidence-interval-estimation",
    "cross-cutting/numerics/hypothesis-testing",
    "cross-cutting/numerics/descriptive-statistics",
    "cross-cutting/numerics/cross-correlation-analysis",
    "cross-cutting/numerics/information-entropy",
    "cross-cutting/numerics/convergence-verification",
    "cross-cutting/numerics/grubbs-outlier-test",
    "cross-cutting/numerics/runs-test",
    "cross-cutting/numerics/rank-based-hypothesis-testing",
    "cross-cutting/tolerancing/gdandt-basics",
    "cross-cutting/tolerancing/datum-reference-frames",
    "cross-cutting/tolerancing/position-tolerance-calc",
    "cross-cutting/tolerancing/tolerance-stackup",
    "cross-cutting/documentation/engineering-report",
    "cross-cutting/documentation/engineering-margins",
    "cross-cutting/data-sources/aeronautical-data-sources",
    "cross-cutting/export-control/export-control-awareness"
]

STAGES = [
    "1. Unit/atmosphere",
          "2. Numerics",
          "3. Regression/opt",
          "4. Linear algebra",
          "5. Signal",
          "6. Uncertainty",
          "7. Statistics",
          "8. Convergence",
          "9. Tolerancing",
          "10. Data sourcing",
          "11. Export control",
          "12. Report"
]


def role_text():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    return open(p).read() if os.path.exists(p) else None


class TestEngineeringAnalysisEngineerRole(unittest.TestCase):

    def test_bound_skills_resolve(self):
        if not HAS_SKILLS:
            self.skipTest("skills checkout absent (cross-repo dev check)")
        for leaf in EXPECTED_BOUND:
            self.assertTrue(
                os.path.exists(os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")),
                f"bound skill missing: {leaf}")

    def test_stages_ordered(self):
        role = role_text()
        self.assertIsNotNone(role)
        wf = role[role.find("## Workflow"):role.find("## Evidence gates")]
        idx = [wf.find(s) for s in STAGES]
        self.assertTrue(all(i >= 0 for i in idx), "stage missing in workflow")
        self.assertEqual(idx, sorted(idx), "stage order not deterministic")

    def test_template_present(self):
        self.assertTrue(os.path.exists(TEMPLATE), "deliverable template missing")

    def test_boundaries(self):
        role = role_text()
        self.assertIsNotNone(role)
        for phrase in ["sign_off_required: true", "forbidden"]:
            self.assertIn(phrase, role)

    def test_sources(self):
        self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, "SOURCES.md")),
                        "SOURCES.md missing")


if __name__ == "__main__":
    unittest.main()
