#!/usr/bin/env python3
"""Test numerical_analysis_core: the executable engine of the
Numerical Analysis Engineer role.

Proves the role can DO its job standalone (no AeroSkills needed):
reference quadrature + Richardson error estimation, Newton/bisection
root finding with the area-Mach anchor, pivoted reference solves,
condition numbers, the three-mesh convergence study (observed order,
Richardson extrapolation, GCI), the memo builder, evidence-gate checks,
and the filled template.
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from numerical_analysis_core import (  # noqa: E402
    EPS_MACH, GCI_FS, RULE_SELECTION,
    area_mach_derivative, area_mach_ratio, area_mach_residual, bisection,
    bracket_straddles, build_report, check_report, check_report_markdown,
    condition_number, condition_report, convergence_verdict,
    example_item, example_report_markdown, forward_error_bound,
    grid_convergence_index, lift_intensity, max_abs_component_diff,
    newton_iterations, newton_raphson, observed_order,
    render_report_markdown, richardson_error_n, richardson_error_trapezoid,
    richardson_extrapolation, root_sensitivity, select_integration_rule,
    simpson, solve, trapezoid,
)

# Deterministic across midnight: the committed template carries the
# generation date 2026-09-06 (wave R6 regeneration); pin fresh renders
# to it (CI override wins).
os.environ.setdefault("ROLE_GEN_DATE", "2026-09-06")

ROLE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROLE_DIR, "templates",
                        "verification-memo-template.md")


class TestQuadratureRules(unittest.TestCase):

    def test_trapezoid_linear_exact(self):
        # trapezoid is exact for linears: integral of x on [0, 2] = 2
        self.assertAlmostEqual(trapezoid(lambda x: x, 0.0, 2.0, 4), 2.0,
                               places=12)

    def test_quadratic_anchor_x2(self):
        # integral of x^2 on [0, 2] = 8/3; trapezoid converges O(h^2)
        est = trapezoid(lambda x: x * x, 0.0, 2.0, 1000)
        self.assertAlmostEqual(est, 8.0 / 3.0, places=4)
        # Simpson n=2 is exact for the quadratic
        self.assertAlmostEqual(simpson(lambda x: x * x, 0.0, 2.0, 2),
                               8.0 / 3.0, places=12)

    def test_sin_anchor(self):
        # integral of sin(x) on [0, pi] = 2 (leaf textbook anchor)
        self.assertAlmostEqual(simpson(math.sin, 0.0, math.pi, 1000), 2.0,
                               places=8)

    def test_invalid_panels_raise(self):
        with self.assertRaises(ValueError):
            trapezoid(lambda x: x, 0.0, 1.0, 0)
        with self.assertRaises(ValueError):
            simpson(lambda x: x, 0.0, 1.0, 3)   # odd n raises
        with self.assertRaises(ValueError):
            trapezoid(lambda x: x, 0.0, 1.0, 2.5)

    def test_richardson_error_estimate(self):
        # error(2n) = |I_2n - I_n| / 3 ; on the smooth quadratic
        # half-span load at n=16 this is 12.3046875 N (measured)
        f = lambda y: lift_intensity(y, 4200.0, 36.0)
        self.assertAlmostEqual(
            richardson_error_trapezoid(f, 0.0, 18.0, 16), 12.3046875,
            places=9)

    def test_richardson_error_n_recovers_trapezoid_error(self):
        # for an order-2 rule E_n = |I_n - I_2n|/(1 - 2^-2); on the
        # quadratic integrand the trapezoid error is exactly known:
        # I16 - exact = -49.21875 N
        f = lambda y: lift_intensity(y, 4200.0, 36.0)
        i16 = trapezoid(f, 0.0, 18.0, 16)
        i32 = trapezoid(f, 0.0, 18.0, 32)
        self.assertAlmostEqual(richardson_error_n(i16, i32, 2),
                               abs(i16 - 4200.0 * 36.0 / 3.0), places=6)
        self.assertAlmostEqual(richardson_error_n(i16, i32, 2), 49.21875,
                               places=6)


class TestRuleSelection(unittest.TestCase):

    def test_smooth_selects_simpson(self):
        sel = select_integration_rule("smooth")
        self.assertEqual(sel["rule"], "composite Simpson")
        self.assertEqual(sel["order"], 4)

    def test_noisy_selects_trapezoid(self):
        sel = select_integration_rule("arbitrary-or-noisy")
        self.assertIn("trapezoid", sel["rule"])
        self.assertEqual(sel["order"], 2)

    def test_all_classes_have_rationale(self):
        for cls, sel in RULE_SELECTION.items():
            self.assertTrue(sel["rationale"])

    def test_unknown_class_raises(self):
        with self.assertRaises(ValueError):
            select_integration_rule("not-a-class")


class TestRootFinding(unittest.TestCase):

    def test_sqrt2_anchors(self):
        # f = x^2 - 2, root sqrt(2) = 1.4142135623730951
        root_b = bisection(lambda x: x * x - 2.0, 1.0, 2.0)
        root_n = newton_raphson(lambda x: x * x - 2.0, lambda x: 2.0 * x,
                                1.5)
        self.assertAlmostEqual(root_b, math.sqrt(2.0), places=9)
        self.assertAlmostEqual(root_n, math.sqrt(2.0), places=9)

    def test_newton_quadratic_speed(self):
        # three Newton steps reach ~machine precision from x0 = 1.5
        r = newton_iterations(lambda x: x * x - 2.0, lambda x: 2.0 * x, 1.5)
        self.assertLessEqual(r["iterations"], 3)
        self.assertLess(r["residual"], 1e-10)

    def test_area_mach_subsonic_anchor(self):
        # isentropic area-Mach relation, A/A* = 1.2, gamma = 1.4:
        # subsonic root M = 0.59024876099 (leaf-tested anchor)
        resid = lambda M: area_mach_residual(M, 1.2, 1.4)
        deriv = lambda M: area_mach_derivative(M, 1.4)
        rn = newton_raphson(resid, deriv, 0.3)
        rb = bisection(resid, 0.2, 0.99)
        self.assertAlmostEqual(rn, 0.59024876099, places=9)
        self.assertAlmostEqual(rb, 0.59024876099, places=9)
        self.assertLess(abs(area_mach_residual(rn, 1.2, 1.4)), 1e-10)

    def test_bracket_behavior(self):
        resid = lambda M: area_mach_residual(M, 1.2, 1.4)
        ok = bracket_straddles(resid, 0.2, 0.99)
        self.assertTrue(ok["straddles"])
        bad = bracket_straddles(resid, 0.05, 0.4)  # both sides positive
        self.assertFalse(bad["straddles"])
        with self.assertRaises(ValueError):
            bisection(resid, 0.05, 0.4)            # no sign change
        # Newton step undefined when the derivative vanishes before
        # convergence: f = x^3 - 1 from x0 = 0 has df(0) = 0
        with self.assertRaises(ValueError):
            newton_raphson(lambda x: x ** 3 - 1.0, lambda x: 3.0 * x * x, 0.0)

    def test_root_sensitivity(self):
        # simple root: sensitivity 1/|f'|; multiple root: unbounded
        self.assertAlmostEqual(root_sensitivity(-2.0), 0.5)
        self.assertEqual(root_sensitivity(0.0), float("inf"))


class TestLinearSolveAndConditioning(unittest.TestCase):

    def test_solve_leaf_anchor(self):
        # matrix-operations leaf worked anchor:
        # A x = b with A = [[2,1,-1],[-3,-1,2],[-2,1,2]], b = [8,-11,-3]
        # gives x = [2, 3, -1]
        A = [[2.0, 1.0, -1.0], [-3.0, -1.0, 2.0], [-2.0, 1.0, 2.0]]
        b = [8.0, -11.0, -3.0]
        x = solve(A, b)
        self.assertAlmostEqual(x[0], 2.0, places=10)
        self.assertAlmostEqual(x[1], 3.0, places=10)
        self.assertAlmostEqual(x[2], -1.0, places=10)

    def test_singular_matrix_raises(self):
        with self.assertRaises(ValueError):
            solve([[1.0, 2.0], [2.0, 4.0]], [1.0, 2.0])

    def test_max_abs_component_diff(self):
        self.assertAlmostEqual(max_abs_component_diff([1.0, 2.0],
                                                      [1.0, 2.5]), 0.5)

    def test_condition_number(self):
        # kappa = s_max/s_min: [1.75, 0.25] -> 7
        self.assertAlmostEqual(condition_number([1.75, 0.25]), 7.0)
        self.assertEqual(condition_number([1.0, 0.0]), float("inf"))
        with self.assertRaises(ValueError):
            condition_number([])
        with self.assertRaises(ValueError):
            condition_number([-1.0])

    def test_condition_report_and_bound(self):
        rep = condition_report([1.75, 0.25])
        self.assertAlmostEqual(rep["kappa"], 7.0)
        self.assertAlmostEqual(rep["digits_lost_max"],
                               math.log10(7.0), places=3)
        self.assertFalse(rep["at_precision_limit"])
        # classical forward-error bound: kappa * backward error
        self.assertAlmostEqual(forward_error_bound(7.0, 1e-12), 7e-12)
        # at the precision limit kappa >= 1/eps
        lim = condition_report([EPS_MACH, 1.0])
        self.assertTrue(lim["at_precision_limit"])


class TestConvergenceStudy(unittest.TestCase):

    # three-mesh trapezoid outputs of the half-span quadratic load
    F1, F2, F3 = 50396.923828125, 50387.6953125, 50350.78125

    def test_observed_order_is_two(self):
        # trapezoid on a quadratic: exactly second order, ratio 4
        p = observed_order(self.F1, self.F2, self.F3, 2.0)
        self.assertAlmostEqual(p, 2.0, places=9)

    def test_richardson_extrapolation_recovers_exact(self):
        p = observed_order(self.F1, self.F2, self.F3, 2.0)
        exact = richardson_extrapolation(self.F1, self.F2, 2.0, p)
        self.assertAlmostEqual(exact, 50400.0, places=6)

    def test_gci_fraction(self):
        p = observed_order(self.F1, self.F2, self.F3, 2.0)
        gci = grid_convergence_index(self.F1, self.F2, 2.0, p)
        self.assertAlmostEqual(gci, 7.62986022096e-05, places=12)
        self.assertEqual(GCI_FS, 1.25)

    def test_convergence_verdicts(self):
        v = convergence_verdict(self.F1, self.F2, self.F3, 2.0)
        self.assertEqual(v["verdict"], "monotone converged")
        self.assertAlmostEqual(v["order"], 2.0, places=9)
        # diverging: |ratio| > 1 on the negative branch
        vd = convergence_verdict(1.0, 0.5, 2.0, 2.0)
        self.assertEqual(vd["verdict"], "diverging")
        # oscillatory: ratio < 0 with |ratio| <= 1
        vo = convergence_verdict(1.0, 0.5, 0.75, 2.0)
        self.assertEqual(vo["verdict"], "oscillatory")
        self.assertIsNone(vo["order"])

    def test_invalid_studies_raise(self):
        with self.assertRaises(ValueError):
            observed_order(1.0, 2.0, 3.0, 1.0)      # r <= 1
        with self.assertRaises(ValueError):
            observed_order(1.0, 1.0, 1.5, 2.0)      # f2 == f1
        with self.assertRaises(ValueError):
            observed_order(1.0, 0.5, 0.6, 2.0)      # non-monotone


class TestMemoBuilder(unittest.TestCase):

    def test_example_item_reports(self):
        item = example_item()
        # code reported the n=16 trapezoid value (50350.78125 N) and the
        # subsonic area-Mach root to 9 decimals
        self.assertAlmostEqual(item.code_integral, 50350.78125, places=6)
        self.assertAlmostEqual(item.code_mach, 0.590248761, places=9)

    def test_model_structure(self):
        model = build_report(example_item())
        self.assertEqual(model["document_type"],
                         "Numerical Methods Verification Memo")
        self.assertEqual(model["status"], "draft-for-review")
        self.assertEqual(len(model["checks"]), 3)
        self.assertEqual(len(model["method_selection"]), 3)
        self.assertTrue(model["findings"])

    def test_example_verdicts(self):
        # integration fails (49.2 N vs 1 N claim); root and solve pass
        int_chk = build_report(example_item())["integration"]
        self.assertEqual(int_chk["verdict"], "FAIL")
        self.assertAlmostEqual(int_chk["discrepancy"], 49.21875, places=6)
        root_chk = build_report(example_item())["root_finding"]
        self.assertEqual(root_chk["verdict"], "PASS")
        self.assertLess(root_chk["discrepancy"], 1e-9)
        solve_chk = build_report(example_item())["linear_solve"]
        self.assertEqual(solve_chk["verdict"], "PASS")
        self.assertAlmostEqual(solve_chk["conditioning"]["kappa"], 7.0)

    def test_convergence_in_model(self):
        conv = build_report(example_item())["convergence"]
        self.assertAlmostEqual(conv["observed_order"], 2.0, places=6)
        self.assertAlmostEqual(conv["gci_fraction"], 7.62986022096e-05,
                               places=12)
        self.assertEqual(conv["verdict"], "monotone converged")
        self.assertAlmostEqual(conv["richardson_extrapolated"], 50400.0,
                               places=6)

    def test_correct_report_flips_verdict(self):
        # re-verify a code report that is actually correct: all PASS
        item = example_item()
        item.code_integral = 50400.0
        model = build_report(item)
        for c in model["checks"]:
            self.assertEqual(c["verdict"], "PASS")

    def test_core_gates_all_pass(self):
        model = build_report(example_item())
        gates = check_report(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_all_pass(self):
        md = example_report_markdown()
        gates = check_report_markdown(md)
        self.assertTrue(gates["all_pass"], gates)

    def test_sign_off_gate_fails_when_honest_marker_removed(self):
        model = build_report(example_item())
        model["status"] = "approved"
        gates = check_report(model)
        self.assertFalse(gates["sign_off_honest"])
        self.assertFalse(gates["all_pass"])

    def test_convergence_gate_fails_when_study_missing(self):
        model = build_report(example_item())
        model["convergence"] = {"meshes": []}
        gates = check_report(model)
        self.assertFalse(gates["convergence_study_present"])
        self.assertFalse(gates["all_pass"])

    def test_render_is_draft_and_not_approval(self):
        md = example_report_markdown()
        self.assertIn("draft", md.lower())
        self.assertIn("not an approval", md.lower())
        self.assertIn("Numerical Methods Verification Memo", md)

    def test_template_is_the_filled_example(self):
        # ROLE-STANDARD: the template IS the example deliverable
        # generated by the core - byte-identical, zero blanks.
        with open(TEMPLATE) as fh:
            template = fh.read()
        self.assertNotIn("___", template)
        self.assertEqual(template, example_report_markdown())

    def test_standalone_no_skills_repo(self):
        # Core must work with no AeroSkills present
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = build_report(example_item())
        md = render_report_markdown(model)
        self.assertGreater(len(md), 2000)
        self.assertTrue(check_report(model)["all_pass"])


if __name__ == "__main__":
    unittest.main()
