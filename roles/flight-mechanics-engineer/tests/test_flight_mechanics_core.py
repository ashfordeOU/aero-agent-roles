#!/usr/bin/env python3
"""Test flight_mechanics_core: the executable engine of the role.

Proves the role can DO its job standalone (no AeroSkills needed): the
domain rules produce REAL numbers (range, ROC, takeoff, static margin,
short-period damping) that are physically plausible, the builder produces
the full report model, the evidence gates pass, and the markdown
deliverable carries every gate marker.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from flight_mechanics_core import (  # noqa: E402
    ExampleTransport, analyze_vehicle, assess_dutch_roll,
    assess_phugoid, assess_roll_mode, assess_short_period, assess_spiral,
    breguet_range, build_report, c_m_alpha_from_sm, check_report,
    check_report_markdown, cl_beta_dihedral, cn_beta_vertical_tail,
    elevator_to_trim, example_report_markdown, example_vehicle,
    far_25_121_minimum, isa, jet_endurance, landing_ground_roll, neutral_point,
    oei_gradient_pct, oei_thrust, phugoid_damping, render_report_markdown,
    roll_time_constant, short_period_damping, short_period_frequency,
    specific_air_range, spiral_eigenvalue, spiral_stability_parameter,
    stall_speed, static_margin, takeoff_ground_roll,
)

G = 9.80665


class TestDomainRules(unittest.TestCase):
    """Real formulas from the bound flight-mechanics leaves."""

    def test_isa_atmosphere(self):
        sl = isa(0.0)
        self.assertAlmostEqual(sl["rho"], 1.225, places=3)
        self.assertAlmostEqual(sl["p"], 101325.0, delta=1.0)
        self.assertAlmostEqual(sl["sigma"], 1.0, places=6)
        fl350 = isa(10668.0)
        self.assertTrue(0.35 < fl350["rho"] < 0.41, fl350["rho"])
        self.assertAlmostEqual(fl350["T"], 218.81, delta=0.5)
        self.assertAlmostEqual(fl350["a"] * 0.78, 231.3, delta=2.0)

    def test_breguet_range_hand(self):
        # R = (V/(TSFC*g))*(L/D)*ln(m0/m1) in meters
        r = breguet_range(231.3, 1.55e-5, 17.2, 78000.0, 60840.0)
        expect = (231.3 / (1.55e-5 * G)) * 17.2 * \
            __import__("math").log(78000.0 / 60840.0)
        self.assertAlmostEqual(r, expect, places=1)
        self.assertGreater(r / 1000.0, 5000.0)  # multi-thousand km class

    def test_breguet_rejects_no_fuel(self):
        with self.assertRaises(ValueError):
            breguet_range(231.3, 1.55e-5, 17.2, 78000.0, 78000.0)

    def test_jet_endurance_hours(self):
        e = jet_endurance(1.55e-5, 17.2, 62000.0 * G, 59000.0 * G)
        self.assertGreater(e, 3000.0)   # ~1.5 h loiter
        self.assertLess(e, 20000.0)

    def test_specific_air_range_units(self):
        sar = specific_air_range(231.3, 1.55e-5, 78000.0 * G, 17.2)
        self.assertTrue(100.0 < sar < 1000.0)  # ~0.3 km/kg

    def test_takeoff_rules(self):
        vs = stall_speed(6119.0, 1.225, 1.9)
        self.assertAlmostEqual(vs, 72.5, delta=1.0)   # ~141 kt
        sg = takeoff_ground_roll(78000.0 * G, 125.0, 220000.0, 1.225, 1.9)
        self.assertTrue(1000.0 < sg < 2500.0, sg)     # realistic ground roll
        with self.assertRaises(ValueError):
            takeoff_ground_roll(78000.0 * G, 125.0, 1000.0, 1.225, 1.9)

    def test_landing_certified_factor(self):
        res = analyze_vehicle(example_vehicle())
        self.assertAlmostEqual(res["land_certified"],
                               res["land_actual"] * 1.67, places=3)
        self.assertTrue(1000.0 < res["land_certified"] < 3000.0)

    def test_oei_far_25_121(self):
        self.assertEqual(far_25_121_minimum("second-segment", 2), 2.4)
        self.assertEqual(far_25_121_minimum("approach", 2), 2.1)
        self.assertEqual(far_25_121_minimum("landing", 4), 3.2)
        t = oei_thrust(220000.0, 2, 1)
        self.assertEqual(t, 110000.0)
        res = analyze_vehicle(example_vehicle())
        self.assertGreater(res["oei"]["gradient_pct"],
                           res["oei"]["min_pct"])  # meets 25.121(b)

    def test_neutral_point_and_margin(self):
        np_ = neutral_point(0.25, 0.862, 0.72, 0.45)
        self.assertAlmostEqual(np_, 0.591, places=3)
        self.assertAlmostEqual(static_margin(np_, 0.44), 0.1515, places=3)
        with self.assertRaises(ValueError):
            static_margin(1.2, 0.3)

    def test_cm_alpha_sign(self):
        self.assertAlmostEqual(c_m_alpha_from_sm(5.5, 0.1515), -0.833, places=3)
        self.assertLess(c_m_alpha_from_sm(5.5, 0.15), 0.0)

    def test_lateral_stability_build(self):
        clb = cl_beta_dihedral(0.603, 5.2)
        self.assertAlmostEqual(clb, -0.0547, places=3)  # -CL*Gamma
        cnb_vt = cn_beta_vertical_tail(0.95, 0.0512626, 3.4, 0.08)
        self.assertAlmostEqual(cnb_vt, 0.1788, places=3)
        aero = analyze_vehicle(example_vehicle())["aero"]
        self.assertGreater(aero["cn_beta"], 0.0)   # directionally stable
        self.assertLess(aero["cl_beta"], 0.0)      # laterally stable

    def test_short_period_hand_identity(self):
        # short period from the dynamic-stability leaf formulas
        qbar = 0.5 * 0.37949 * 231.3 ** 2
        za = -(qbar * 125.0 * 5.5) / 78000.0
        cm_a = c_m_alpha_from_sm(5.5, 0.1515)
        ma = qbar * 125.0 * 3.4916 * cm_a / 3.4e6
        mq = qbar * 125.0 * 3.4916 ** 2 * (-30.0) / (2 * 231.3 * 3.4e6)
        om = short_period_frequency(za, ma, mq, 231.3)
        zeta = short_period_damping(za, ma, mq, 231.3)
        self.assertTrue(0.9 < om < 1.4, om)
        self.assertTrue(0.2 < zeta < 0.45, zeta)

    def test_phugoid_damping_small(self):
        z = phugoid_damping(17.2)
        self.assertAlmostEqual(z, 1.0 / (1.41421356 * 17.2), places=5)
        self.assertGreater(z, 0.0)

    def test_spiral_roll_dutch_roll_helpers(self):
        # stable spiral criterion term > 0 -> convergent
        self.assertGreater(spiral_stability_parameter(-1.8, 0.23, 0.84,
                                                       -0.14), 0.0)
        lam = spiral_eigenvalue(-1.8, 0.23, 0.84, -0.14, -0.74, 231.3)
        self.assertLess(lam, 0.0)                      # convergent spiral
        with self.assertRaises(ValueError):
            roll_time_constant(0.5)                     # L_p must be < 0
        self.assertAlmostEqual(roll_time_constant(-0.74), 1.351, places=3)


class TestFlyingQualitiesAssessors(unittest.TestCase):
    """Level criteria as summarized by the mil-std-1797a leaf."""

    def test_short_period_level1(self):
        r = assess_short_period(0.50, 3.5, "A", "III", 1.0)
        self.assertEqual(r["level"], 1)

    def test_short_period_frequency_degrade(self):
        r = assess_short_period(0.50, 2.0, "A", "III", 3.0)  # floor 6.0
        self.assertEqual(r["level"], 2)

    def test_short_period_band_boundary(self):
        r = assess_short_period(0.31, 2.0, "B", "III", 1.0)
        self.assertEqual(r["level"], 1)   # cat B floor 0.30

    def test_dutch_roll_levels(self):
        self.assertEqual(assess_dutch_roll(0.1, 1.6, "B", "III"), 1)
        self.assertEqual(assess_dutch_roll(0.1, 0.5, "B", "III"), 2)
        self.assertEqual(assess_dutch_roll(-0.01, 0.5, "B", "III"), 3)

    def test_phugoid_spiral_roll_levels(self):
        self.assertEqual(assess_phugoid(0.041), 1)
        self.assertEqual(assess_phugoid(0.02), 2)
        self.assertEqual(assess_phugoid(-0.01), 3)
        self.assertEqual(assess_spiral(-0.004, "B"), 1)
        self.assertEqual(assess_roll_mode(1.3, "B"), 1)
        self.assertEqual(assess_roll_mode(1.3, "C"), 2)


class TestAnalysisAndBuilder(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.vehicle = example_vehicle()
        cls.results = analyze_vehicle(cls.vehicle)
        cls.model = build_report(cls.vehicle, cls.results)

    def test_example_transport_realistic_class(self):
        v = self.vehicle
        self.assertTrue(100.0 < v.s < 200.0)
        self.assertTrue(60000.0 < v.m_mtow < 100000.0)
        self.assertTrue(0.25 < v.thrust_total_to / v.w_mtow < 0.35)

    def test_range_number(self):
        self.assertTrue(5500.0 < self.results["range_km"] < 8000.0,
                        self.results["range_km"])

    def test_climb_roc_number(self):
        self.assertTrue(10.0 < self.results["roc_sl"] < 30.0)
        self.assertTrue(2.0 < self.results["roc_350"] < 12.0)

    def test_takeoff_number(self):
        self.assertTrue(1000.0 < self.results["to_ground_roll"] < 2500.0)

    def test_static_margins(self):
        sm_f = self.results["aero"]["sm_fwd"]
        sm_a = self.results["aero"]["sm_aft"]
        self.assertGreater(sm_f, sm_a)
        self.assertGreater(sm_a, 0.05)   # above the minimum margin band

    def test_short_period_numbers(self):
        ca = self.results["sp_cruise_aft"]
        aa = self.results["sp_appr_aft"]
        self.assertTrue(0.8 < ca["omega_sp"] < 2.0)
        self.assertTrue(0.25 < ca["zeta_sp"] < 0.5)
        self.assertTrue(0.5 < aa["omega_sp"] < 1.5)
        self.assertTrue(0.4 < aa["zeta_sp"] < 0.9)
        # aft CG short period damping exceeds the FAR heavy-damping band
        self.assertGreaterEqual(aa["zeta_sp"], 0.30)

    def test_modes_all_stable(self):
        self.assertGreater(self.results["phugoid_cruise"]["zeta"], 0.0)
        self.assertGreater(self.results["lat_cruise"]["zeta_dr"], 0.0)
        self.assertLess(self.results["lat_cruise"]["lambda_spiral"], 0.0)
        self.assertGreater(self.results["lat_appr"]["zeta_dr"], 0.0)

    def test_derivative_signs(self):
        sp = self.results["sp_cruise_aft"]
        self.assertLess(sp["za"], 0.0)      # Z_alpha negative
        self.assertLess(sp["ma"], 0.0)      # M_alpha negative (stable)
        self.assertLess(sp["mq"], 0.0)      # M_q negative (damping)
        la = self.results["lat_cruise"]
        self.assertGreater(la["nb"], 0.0)   # yaw stiffness
        self.assertLess(la["lp"], 0.0)      # roll damping

    def test_elevator_trim_within_authority(self):
        tr = self.results["trim_cruise"]
        ta = self.results["trim_appr"]
        lim = self.vehicle.elevator_limit_deg
        self.assertLess(abs(tr["de_deg"]), lim)
        self.assertLess(abs(ta["de_deg"]), lim)

    def test_model_has_all_sections(self):
        self.assertEqual(self.model["document_type"],
                         "Performance and S&C Analysis Report")
        self.assertEqual(self.model["status"], "draft-for-review")


class TestGatesAndDeliverable(unittest.TestCase):

    def test_core_gates_all_pass(self):
        r = analyze_vehicle(example_vehicle())
        gates = check_report(r)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_all_pass(self):
        md = example_report_markdown()
        gates = check_report_markdown(md)
        self.assertTrue(gates["all_pass"], gates)

    def test_rendered_sections(self):
        md = example_report_markdown()
        for sec in ["## 1. Mission performance", "## 4. Stability",
                    "## 5. Dynamic modes", "## 7. Handling qualities",
                    "## 9. Conclusions"]:
            self.assertIn(sec, md)
        self.assertIn("not an approval", md.lower())
        self.assertIn("draft", md.lower())

    def test_template_zero_blanks(self):
        here = os.path.dirname(os.path.abspath(__file__))
        tmpl = os.path.join(here, "..", "templates",
                            "perf-sc-report-template.md")
        with open(tmpl) as f:
            text = f.read()
        self.assertNotIn("___", text)
        self.assertIn("AeroLine AT-78", text)

    def test_standalone_no_skills_repo(self):
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        v = example_vehicle()
        r = analyze_vehicle(v)
        md = render_report_markdown(build_report(v, r))
        self.assertGreater(len(md), 5000)
        self.assertTrue(check_report(r)["all_pass"])
        self.assertTrue(check_report_markdown(md)["all_pass"])


if __name__ == "__main__":
    unittest.main()
