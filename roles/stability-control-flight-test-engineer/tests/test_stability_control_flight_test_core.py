#!/usr/bin/env python3
"""Test stability_control_flight_test_core: the executable engine of the
Stability and Control Flight Test Engineer role.

Proves the role can DO its job standalone (no AeroSkills needed): static
longitudinal stability reduction (trim curve fit, stick fixed/free
neutral points, static margin, elevator angle per g), dynamic stability
(log decrement, damping ratio, mode identification, handling-qualities
verdicts), lateral-directional static stability (SHS gradients, signed
Cn_beta/Cl_beta estimates, weathercock/dihedral verdicts), control
force reduction (calibration, gradient, force per g, breakout,
centering), the demonstration rollup, report generation, and
evidence-gate checks.

Real anchors come from the four bound AeroSkills leaves under
flight-test-operations/stability/ (and their contract tests):
CL = 2 W / (rho V^2 S); delta_e = a + b CL; h_n = h + b Cm_delta_e
pi/180; stick free shift (Cm_delta_e Ch_alpha)/(CL_alpha Ch_delta_e);
d(delta_e)/dn = (180/pi) CL SM / Cm_delta_e; delta = (1/n) ln(A0/An);
zeta = delta/sqrt(delta^2 + 4 pi^2); w_n = w_d/sqrt(1 - zeta^2);
t_half = ln(2)/(zeta w_n); Cn_beta = -cn_dr s_r; Cl_beta = -cl_da s_a;
breakout = (pull - push)/2; margin = limit - residual.
"""
import math
import os
import sys
import unittest

os.environ.setdefault("ROLE_GEN_DATE", "2026-09-06")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from stability_control_flight_test_core import (  # noqa: E402
    CENTERED, EXCEEDS_LIMIT, STABLE_GRADIENT, UNSTABLE_GRADIENT,
    aileron_gradient, breakout_force, build_sideslip_matrix,
    build_stability_control_report, calibrate_force_transducer,
    centering_check, check_report, check_report_markdown,
    cycles_to_half_amplitude, damping_ratio_from_decrement,
    elevator_angle_per_g, example_item, example_report_markdown,
    force_per_g, handling_qualities_verdict, least_squares_fit,
    lift_coefficients, log_decrement, mode_identification,
    pedal_force_gradient, reduce_sideslip_sweep,
    render_report_markdown, rollup_verdicts, rudder_gradient,
    signed_directional_estimate, signed_lateral_estimate,
    static_stability_report, stick_fixed_neutral_point,
    stick_free_neutral_point, stick_force_gradient, time_to_half_amplitude,
    trim_curve_fit, verdict_pass, weathercock_verdict, dihedral_verdict,
)

TWO_PI = 2.0 * math.pi


class TestStaticLongitudinal(unittest.TestCase):

    def test_lift_coefficient_formula(self):
        # CL = 2 W / (rho V^2 S); rho=1, S=100, W=200000 -> CL = 4000/V^2
        cl = lift_coefficients([40.0, 50.0, 100.0], 200000.0, 100.0, 1.0)
        self.assertAlmostEqual(cl[0], 2.5, places=9)
        self.assertAlmostEqual(cl[1], 1.6, places=9)
        self.assertAlmostEqual(cl[2], 0.4, places=9)

    def test_least_squares_perfect_line(self):
        xs = [0.2, 0.4, 0.6, 0.8, 1.0]
        ys = [1.4, 0.8, 0.2, -0.4, -1.0]  # y = 2 - 3x exactly
        fit = least_squares_fit(xs, ys)
        self.assertAlmostEqual(fit["slope"], -3.0, places=9)
        self.assertAlmostEqual(fit["r_squared"], 1.0, places=9)

    def test_example_trim_slope_is_stable_six(self):
        item = example_item()
        fit = trim_curve_fit(item.elevator_deg, item.speeds_m_s,
                             item.weight_n, item.wing_area_m2,
                             item.rho_kg_m3)
        self.assertAlmostEqual(fit["slope_deg_per_cl"], -6.0, places=9)
        self.assertEqual(fit["n"], 5)
        self.assertAlmostEqual(fit["r_squared"], 1.0, places=9)

    def test_stick_fixed_neutral_point_anchor(self):
        # slope -6 deg/CL, cg 0.25, Cm_de -0.5/rad:
        # shift = -6*(-0.5)*pi/180 = pi/60 -> h_n = 0.25 + pi/60
        res = stick_fixed_neutral_point(-6.0, 0.25, -0.5)
        self.assertAlmostEqual(res["neutral_point_fraction_mac"],
                               0.25 + math.pi / 60.0, places=9)
        self.assertAlmostEqual(res["static_margin_fraction_mac"],
                               math.pi / 60.0, places=9)
        self.assertEqual(res["verdict"], "stable")

    def test_positive_slope_flags_unstable(self):
        res = stick_fixed_neutral_point(2.0, 0.25, -0.5)
        self.assertAlmostEqual(res["static_margin_fraction_mac"],
                               -math.pi / 180.0, places=9)
        self.assertEqual(res["verdict"], "unstable")

    def test_stick_free_shift_forward_of_fixed(self):
        # shift = (Cm_de Ch_a)/(CL_a Ch_de) = (-0.5*0.15)/(5*-0.8)
        #       = +0.01875 -> free neutral point forward of the fixed one
        fixed = 0.25 + math.pi / 60.0
        res = stick_free_neutral_point(fixed, 0.25, -0.5,
                                       0.15, -0.8, 5.0)
        self.assertAlmostEqual(res["shift_fraction_mac"], 0.01875,
                               places=9)
        self.assertAlmostEqual(res["neutral_point_fraction_mac"],
                               fixed - 0.01875, places=9)
        self.assertAlmostEqual(res["static_margin_fraction_mac"],
                               math.pi / 60.0 - 0.01875, places=9)
        self.assertEqual(res["verdict"], "stable")
        self.assertLess(res["neutral_point_fraction_mac"], fixed)

    def test_elevator_angle_per_g_anchor(self):
        # (180/pi) * 0.7 * (pi/60) / -0.5 = 3*0.7/-0.5 = -4.2 deg/g
        res = elevator_angle_per_g(0.7, math.pi / 60.0, -0.5)
        self.assertAlmostEqual(res["value_deg_per_g"], -4.2, places=9)
        self.assertAlmostEqual(res["magnitude_deg_per_g"], 4.2, places=9)
        self.assertIn("trailing-edge-up", res["assessment"])

    def test_static_stability_report_chain(self):
        item = example_item()
        rep = static_stability_report(
            item.elevator_deg, item.speeds_m_s, item.weight_n,
            item.wing_area_m2, item.rho_kg_m3, item.cg_fraction_mac,
            item.cm_delta_e_per_rad, ch_alpha_per_rad=0.15,
            ch_delta_e_per_rad=-0.8, cl_alpha_per_rad=5.0, cl_1g=0.7)
        self.assertEqual(rep["verdict"], "stable")
        self.assertIsNotNone(rep["stick_free"])
        self.assertIsNotNone(rep["elevator_angle_per_g"])


class TestDynamicStability(unittest.TestCase):

    def test_log_decrement_multi_cycle(self):
        # delta = (1/2) ln(5/0.0176) over two cycles
        expected = math.log(5.0 / 0.0176) / 2.0
        self.assertAlmostEqual(log_decrement(5.0, 0.0176, 2), expected,
                               places=9)

    def test_log_decrement_no_decay_raises(self):
        with self.assertRaises(ValueError):
            log_decrement(3.0, 3.0, 1)
        with self.assertRaises(ValueError):
            log_decrement(1.0, 3.0, 1)

    def test_damping_ratio_from_decrement_formula(self):
        delta = 0.2
        expected = delta / math.sqrt(delta * delta + TWO_PI * TWO_PI)
        self.assertAlmostEqual(damping_ratio_from_decrement(delta),
                               expected, places=12)
        self.assertEqual(damping_ratio_from_decrement(0.0), 0.0)

    def test_short_period_mode_identification_anchor(self):
        # peaks [5, 0.296, 0.0176] at 0/0.9/1.8 s over 2 cycles
        res = mode_identification([5.0, 0.296, 0.0176],
                                  [0.0, 0.9, 1.8])
        delta = math.log(5.0 / 0.0176) / 2.0
        zeta = delta / math.sqrt(delta * delta + TWO_PI * TWO_PI)
        wd = TWO_PI / 0.9
        wn = wd / math.sqrt(1.0 - zeta * zeta)
        self.assertAlmostEqual(res["decrement"], delta, places=9)
        self.assertAlmostEqual(res["damping_ratio"], zeta, places=9)
        self.assertEqual(res["cycles_used"], 2)
        self.assertAlmostEqual(res["damped_frequency_hz"], 1.0 / 0.9,
                               places=9)
        self.assertAlmostEqual(res["time_to_half_s"],
                               math.log(2.0) / (zeta * wn), places=9)

    def test_cycles_to_half_amplitude(self):
        self.assertAlmostEqual(cycles_to_half_amplitude(0.1),
                               math.log(2.0) / (TWO_PI * 0.1), places=9)

    def test_time_to_half_amplitude(self):
        self.assertAlmostEqual(time_to_half_amplitude(0.3, 1.0),
                               math.log(2.0) / 0.3, places=9)

    def test_handling_qualities_bands(self):
        self.assertEqual(handling_qualities_verdict("short-period", 0.41)
                         ["verdict"], "acceptable")
        self.assertEqual(handling_qualities_verdict("short-period", 0.05)
                         ["verdict"], "inadequate")
        self.assertEqual(handling_qualities_verdict("dutch-roll", 0.05)
                         ["verdict"], "marginal")
        self.assertEqual(handling_qualities_verdict("phugoid", 0.06)
                         ["verdict"], "acceptable")
        self.assertEqual(handling_qualities_verdict("spiral", 0.05)
                         ["verdict"], "acceptable")

    def test_example_modes_all_acceptable(self):
        model = build_stability_control_report(example_item())
        modes = {m["mode"]: m for m in model["dynamic_modes"]}
        self.assertSetEqual(set(modes), {"short-period", "phugoid",
                                         "dutch-roll", "spiral"})
        for m in modes.values():
            self.assertEqual(m["verdict"], "acceptable")
        # short period matches the independent anchor
        sp = modes["short-period"]
        self.assertAlmostEqual(sp["damping_ratio"], 0.4100283, places=5)
        self.assertAlmostEqual(sp["time_to_half_s"], 0.22085, places=4)


class TestLateralDirectional(unittest.TestCase):

    def test_worked_sweep_gradients(self):
        # leaf worked example: beta [2..14], dr, da, pedal force
        out = reduce_sideslip_sweep(
            [2.0, 5.0, 8.0, 11.0, 14.0],
            [0.24, 0.58, 0.96, 1.34, 1.70],
            [-0.35, -0.80, -1.30, -1.80, -2.30],
            pedal_force_N=[0.0, -95.0, -185.0, -275.0, -360.0],
            cn_dr_per_rad=-0.90, cl_da_per_rad=-0.35)
        self.assertAlmostEqual(out["rudder_gradient_per_deg"],
                               0.1226666667, places=6)
        self.assertAlmostEqual(out["aileron_gradient_per_deg"],
                               -0.1633333333, places=6)
        self.assertAlmostEqual(out["pedal_force_gradient_N_per_deg"],
                               -30.0, places=6)
        self.assertEqual(out["point_count"], 5)

    def test_signed_estimates_and_verdicts(self):
        # Cn_beta = -cn_dr s_r = -(-0.90)(0.12267) = +0.1104 /rad stable
        cn = signed_directional_estimate(-0.90, 0.12266666666666666)
        self.assertAlmostEqual(cn, 0.1104, places=9)
        self.assertEqual(weathercock_verdict(cn), "stable")
        # Cl_beta = -cl_da s_a = -(-0.35)(-0.16333) = -0.05717 /rad stable
        cl = signed_lateral_estimate(-0.35, -0.16333333333333333)
        self.assertAlmostEqual(cl, -0.0571666667, places=6)
        self.assertEqual(dihedral_verdict(cl), "stable")

    def test_reversed_signs_flip_verdicts(self):
        self.assertEqual(weathercock_verdict(-0.02), "unstable")
        self.assertEqual(weathercock_verdict(0.0), "unstable")
        self.assertEqual(dihedral_verdict(0.02), "unstable")
        self.assertEqual(dihedral_verdict(0.0), "unstable")

    def test_individual_gradients_least_squares(self):
        beta = [2.0, 5.0, 8.0, 11.0, 14.0]
        self.assertAlmostEqual(rudder_gradient(beta, [0.24, 0.58, 0.96,
                                                      1.34, 1.70]),
                               0.1226666667, places=6)
        self.assertAlmostEqual(aileron_gradient(beta, [-0.35, -0.80,
                                                       -1.30, -1.80,
                                                       -2.30]),
                               -0.1633333333, places=6)
        self.assertAlmostEqual(pedal_force_gradient(beta, [0.0, -95.0,
                                                           -185.0, -275.0,
                                                           -360.0]),
                               -30.0, places=6)

    def test_sideslip_matrix_limit_enforced(self):
        rows = build_sideslip_matrix([0.0, 5.0, 10.0], 80.0, 3000.0)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["cas_ms"], 80.0)
        with self.assertRaises(ValueError):
            build_sideslip_matrix([0.0, 20.0], 80.0, 3000.0)
        with self.assertRaises(ValueError):
            build_sideslip_matrix([0.0], 0.0, 3000.0)


class TestControlForces(unittest.TestCase):

    def test_calibration_worked_values(self):
        # leaf worked example: 20 lbf at 1230 counts, 60 lbf at 3250
        cal = calibrate_force_transducer([20.0, 60.0], [1230.0, 3250.0])
        self.assertAlmostEqual(cal["slope_lbf_per_count"], 0.0198019802,
                               places=6)
        self.assertAlmostEqual(cal["intercept_lbf"], -4.35644, places=4)

    def test_predicted_force_at_2100_counts(self):
        slope = calibrate_force_transducer([20.0, 60.0],
                                           [1230.0, 3250.0])[
            "slope_lbf_per_count"]
        intercept = calibrate_force_transducer([20.0, 60.0],
                                               [1230.0, 3250.0])[
            "intercept_lbf"]
        self.assertAlmostEqual(slope * 2100.0 + intercept, 37.2277,
                               places=3)

    def test_stick_force_gradient_verdict(self):
        grad = stick_force_gradient([120.0, 130.0, 140.0, 150.0],
                                    [-3.8, -1.6, 0.5, 2.9])
        self.assertAlmostEqual(grad["slope_lbf_per_kt"], 0.222, places=3)
        self.assertAlmostEqual(grad["r2"], 0.99927, places=4)
        self.assertEqual(grad["verdict"], STABLE_GRADIENT)
        rev = stick_force_gradient([120.0, 130.0, 140.0, 150.0],
                                   [2.9, 0.5, -1.6, -3.8])
        self.assertEqual(rev["verdict"], UNSTABLE_GRADIENT)

    def test_force_per_g(self):
        pg = force_per_g([1.0, 1.5, 2.0, 2.5], [1.2, 7.4, 14.3, 20.8])
        self.assertAlmostEqual(pg["slope_lbf_per_g"], 13.14, places=2)
        self.assertAlmostEqual(pg["r2"], 0.99962, places=4)

    def test_breakout_half_width(self):
        bo = breakout_force(-4.2, 6.4)
        self.assertAlmostEqual(bo["hysteresis_width_lbf"], 10.6, places=9)
        self.assertAlmostEqual(bo["breakout_lbf"], 5.3, places=9)
        with self.assertRaises(ValueError):
            breakout_force(2.0, 1.0)

    def test_centering_margin(self):
        ce = centering_check(0.42, 0.50)
        self.assertAlmostEqual(ce["margin_deg"], 0.08, places=9)
        self.assertEqual(ce["verdict"], CENTERED)
        bad = centering_check(0.80, 0.50)
        self.assertEqual(bad["verdict"], EXCEEDS_LIMIT)
        self.assertAlmostEqual(bad["margin_deg"], -0.30, places=9)


class TestRollup(unittest.TestCase):

    def test_verdict_pass_mapping(self):
        for ok in ("stable", "acceptable", STABLE_GRADIENT, CENTERED):
            self.assertTrue(verdict_pass(ok))
        for bad in ("unstable", "inadequate", "marginal", "neutral",
                    UNSTABLE_GRADIENT, EXCEEDS_LIMIT):
            self.assertFalse(verdict_pass(bad))

    def test_example_rollup_closed(self):
        model = build_stability_control_report(example_item())
        rollup = model["rollup"]
        self.assertEqual(rollup["overall_gate"], "CLOSED")
        self.assertEqual(rollup["pass_count"], 11)
        self.assertEqual(rollup["total"], 11)
        self.assertEqual(rollup["failed_subjects"], [])

    def test_open_when_subject_fails(self):
        rows = [{"subject": "A", "value": "x", "verdict": "stable",
                 "basis": "b"},
                {"subject": "B", "value": "y", "verdict": "unstable",
                 "basis": "b"}]
        rollup = rollup_verdicts(rows)
        self.assertEqual(rollup["overall_gate"], "OPEN")
        self.assertEqual(rollup["failed_subjects"], ["B"])


class TestReportBuilder(unittest.TestCase):

    def test_example_model_numbers(self):
        model = build_stability_control_report(example_item())
        self.assertEqual(model["document_type"],
                         "Stability and Control Flight Test Report")
        self.assertEqual(model["status"], "draft-for-review")
        s = model["static_longitudinal"]
        self.assertAlmostEqual(s["stick_fixed"]
                               ["static_margin_fraction_mac"],
                               math.pi / 60.0, places=9)
        self.assertEqual(s["stick_fixed"]["verdict"], "stable")
        lat = model["lateral_directional"]["gradients"]
        self.assertAlmostEqual(lat["cn_beta_estimate_per_rad"], 0.1104,
                               places=9)
        self.assertAlmostEqual(lat["cl_beta_estimate_per_rad"],
                               -0.0571666667, places=6)
        cf = model["control_forces"]
        self.assertAlmostEqual(cf["predicted_force_lbf"], 37.2277,
                               places=3)
        self.assertEqual(model["rollup"]["overall_gate"], "CLOSED")

    def test_aft_cg_override_opens_rollup_honestly(self):
        item = example_item()
        item.cg_fraction_mac = 0.36   # aft of the measured neutral point
        model = build_stability_control_report(item)
        self.assertEqual(model["static_longitudinal"]["stick_fixed"]
                         ["verdict"], "unstable")
        self.assertEqual(model["rollup"]["overall_gate"], "OPEN")
        self.assertIn("Static longitudinal stability, stick fixed",
                      model["rollup"]["failed_subjects"])
        md = render_report_markdown(model)
        self.assertIn("OPEN", md)
        self.assertIn("Open checks", md)

    def test_markdown_sections_and_markers(self):
        md = example_report_markdown()
        for n in range(1, 8):
            self.assertIn("## %d. " % n, md)
        low = md.lower()
        self.assertIn("not an approval", low)
        self.assertIn("draft", low)
        self.assertIn("rollup gate: closed", low)

    def test_core_gates_all_pass(self):
        model = build_stability_control_report(example_item())
        gates = check_report(model)
        self.assertTrue(gates["all_pass"], gates)
        self.assertTrue(gates["static_numbers_present"])
        self.assertTrue(gates["dynamic_modes_present"])
        self.assertTrue(gates["lateral_directional_present"])
        self.assertTrue(gates["control_forces_present"])
        self.assertTrue(gates["closure_gate_checked"])
        self.assertTrue(gates["sign_off_honest"])

    def test_markdown_gates_all_pass(self):
        gates = check_report_markdown(example_report_markdown())
        self.assertTrue(gates["all_pass"], gates)

    def test_truncated_report_fails_markdown_gates(self):
        md = example_report_markdown()[:200]
        self.assertFalse(check_report_markdown(md)["all_pass"])

    def test_standalone_no_skills_repo(self):
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = build_stability_control_report(example_item())
        self.assertEqual(model["rollup"]["overall_gate"], "CLOSED")
        md = render_report_markdown(model)
        self.assertGreater(len(md), 4000)


if __name__ == "__main__":
    unittest.main()
