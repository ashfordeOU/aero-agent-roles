#!/usr/bin/env python3
"""Test flight_test_performance_core: the executable engine of the
Flight Test Performance Engineer role.

Proves the role can DO its job standalone (no AeroSkills needed):
ISA reduction to standard conditions, takeoff/landing distance
reductions, level-acceleration thrust determination, cruise fuel-flow
reduction, speed corrections, report generation, and evidence gates.
Anchors are real worked values (ISA physics, leaf-documented method
anchors, and the deterministic worked-example sortie).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from flight_test_performance_core import (  # noqa: E402
    APPROACH_FACTOR, FIELD_LENGTH_FACTOR, G0, OBSTACLE_35FT_M,
    analyze_sortie, build_report, check_report, check_report_markdown,
    constant_accel_distance, corrected_fuel_flow, density_altitude_m,
    drag_from_polar, engine_failure_distance, example_item,
    example_report_markdown, example_report_model, excess_thrust_from_ps,
    ground_roll_integrate, isa_conditions, isa_density_ratio_m,
    ps_at_reference_conditions, range_performance, reduce_accelerate_stop,
    reduce_cruise_points, reduce_landing_run, reduce_level_accel_run,
    reduce_oei_takeoff, reduce_takeoff_run, render_report_markdown,
    specific_excess_power, stall_margin, tas_from_eas, tas_from_mach,
    day_sigma_from_alt_oat, vs1g_from_wing_loading,
    weight_corrected_ps,
    weight_corrected_speed,
)


class TestIsaAtmosphere(unittest.TestCase):
    """Reduction to ISA / standard conditions: real physics anchors."""

    def test_isa_sea_level_anchor(self):
        t, p, rho = isa_conditions(0.0)
        self.assertAlmostEqual(t, 288.15, places=2)
        self.assertAlmostEqual(p, 101325.0, places=1)
        self.assertAlmostEqual(rho, 1.225, places=5)

    def test_isa_8000m_anchor(self):
        t, p, rho = isa_conditions(8000.0)
        self.assertAlmostEqual(t, 236.15, places=2)
        self.assertAlmostEqual(rho, 0.52517, places=4)

    def test_isa_density_ratio_tropopause(self):
        self.assertAlmostEqual(isa_density_ratio_m(11000.0), 0.29707,
                               places=4)

    def test_tas_from_eas_anchor(self):
        # 110 m/s EAS at the 8000 m ISA density -> 168.0 m/s TAS
        self.assertAlmostEqual(tas_from_eas(110.0, 0.52517), 168.0,
                               places=1)

    def test_day_sigma_below_one_hot_day(self):
        sigma = day_sigma_from_alt_oat(152.4, 22.0)
        self.assertGreater(sigma, 0.9)
        self.assertLess(sigma, 1.0)

    def test_density_altitude_isa_day(self):
        # On the ISA day density altitude ~ pressure altitude (152.4 m).
        da = density_altitude_m(152.4, 14.0)
        self.assertAlmostEqual(da, 152.4, delta=5.0)


class TestSpeedCorrections(unittest.TestCase):
    """Stall/V-speed corrections (stall-speed leaf methods)."""

    def test_vs1g_from_wing_loading_anchor(self):
        # W/S = 250000/122.6 N/m^2, CLmax 2.0 at standard density.
        vs = vs1g_from_wing_loading(250000.0 / 122.6, 1.225, 2.0)
        self.assertAlmostEqual(vs, 40.799, places=2)

    def test_weight_corrected_speed_sqrt_law(self):
        v = weight_corrected_speed(50.0, 250000.0, 225000.0)
        self.assertAlmostEqual(v, 50.0 * 0.948683, places=4)

    def test_stall_margin(self):
        self.assertAlmostEqual(stall_margin(50.0, 55.0), 0.1, places=6)
        self.assertLess(stall_margin(50.0, 45.0), 0.0)


class TestTakeoffReduction(unittest.TestCase):
    """Takeoff legs: trapezoid ground roll, rotation, 35-ft climb."""

    def test_ground_roll_linear_ramp_anchor(self):
        # Linear ramp 0 -> 20 m/s over 10 s integrates to exactly 100 m.
        speeds = [2.0 * i for i in range(11)]
        times = [float(i) for i in range(11)]
        self.assertAlmostEqual(ground_roll_integrate(speeds, times), 100.0,
                               places=6)

    def test_ground_roll_validates(self):
        with self.assertRaises(ValueError):
            ground_roll_integrate([1.0, 2.0], [0.0, 0.0])

    def test_constant_accel_distance_anchor(self):
        self.assertAlmostEqual(constant_accel_distance(46.0, 2.3), 460.0,
                               places=3)

    def test_engine_failure_distance_linear_anchor(self):
        # v = 2t sampled each second; failure at v=10 m/s -> 25 m.
        speeds = [2.0 * i for i in range(11)]
        times = [float(i) for i in range(11)]
        self.assertAlmostEqual(engine_failure_distance(speeds, times, 10.0),
                               25.0, places=3)

    def test_oei_takeoff_legs_chain(self):
        res = reduce_oei_takeoff(250.0, 38.0, 46.3, 1.0, 2.2, 2.8)
        expect = 250.0 + 38.0 + (46.3 ** 2 - 38.0 ** 2) / (2.0 * 2.2) \
            + 46.3 * OBSTACLE_35FT_M / 2.8
        self.assertAlmostEqual(res["total_m"], expect, places=3)
        self.assertEqual(res["total_m"], res["failure_m"]
                         + res["recognition_m"] + res["ground_continue_m"]
                         + res["climb_m"])

    def test_accelerate_stop_total(self):
        res = reduce_accelerate_stop(38.0, 2.3, 0.42 * G0)
        self.assertAlmostEqual(res["total_m"], res["accelerate_m"]
                               + res["stop_m"], places=6)

    def test_example_takeoff_run_reduces(self):
        item = example_item()
        res = reduce_takeoff_run(item.takeoff_run)
        self.assertGreater(res["ground_roll_m"], 300.0)
        self.assertGreater(res["total_m"], res["ground_roll_m"])
        self.assertAlmostEqual(res["total_m"], res["ground_roll_m"]
                               + res["rotation_m"] + res["climb_35ft_m"],
                               places=3)
        # measured trapezoid vs constant-acceleration model differ a bit
        self.assertNotAlmostEqual(res["ground_roll_m"],
                                  res["ground_roll_predicted_m"], places=0)


class TestLandingReduction(unittest.TestCase):
    """Landing distance: Vref = 1.23 Vs0, 1.67 certified factor."""

    def test_approach_factor(self):
        self.assertEqual(APPROACH_FACTOR, 1.23)
        self.assertEqual(FIELD_LENGTH_FACTOR, 1.67)

    def test_example_landing_certified(self):
        item = example_item()
        res = reduce_landing_run(item.landing_run,
                                 item.vs0_ref_eas_ms(), item.w_ref_n,
                                 day_sigma_from_alt_oat(item.field_pressure_alt_m,
                                                item.field_oat_c),
                                 runway_m=item.runway_m)
        self.assertAlmostEqual(res["certified_field_length_m"],
                               1.67 * res["demonstrated_m"], places=3)
        self.assertAlmostEqual(res["vref_eas_ms"],
                               1.23 * res["vs0_run_eas_ms"], places=6)
        self.assertTrue(res["fits"])

    def test_short_runway_flagged(self):
        item = example_item()
        res = reduce_landing_run(item.landing_run,
                                 item.vs0_ref_eas_ms(), item.w_ref_n,
                                 day_sigma_from_alt_oat(item.field_pressure_alt_m,
                                                item.field_oat_c),
                                 runway_m=100.0)
        self.assertFalse(res["fits"])


class TestLevelAcceleration(unittest.TestCase):
    """Total-energy method: P_s, excess thrust, determined thrust."""

    def test_specific_excess_power_anchor(self):
        # Leaf-documented anchor: 160 m/s at 1 m/s^2 -> 16.3155 m/s.
        self.assertAlmostEqual(specific_excess_power(160.0, 1.0),
                               16.3155, places=3)

    def test_excess_thrust_anchor(self):
        # W 250000 N, P_s 16.3155 m/s at 160 m/s -> 25492.9 N.
        self.assertAlmostEqual(excess_thrust_from_ps(16.3155, 160.0,
                                                     250000.0),
                               25492.97, places=1)

    def test_weight_and_density_corrections(self):
        ps_ref_w = weight_corrected_ps(16.3155, 250000.0, 240000.0)
        self.assertAlmostEqual(ps_ref_w, 16.9953, places=3)
        ps_std = ps_at_reference_conditions(16.3155, 250000.0, 240000.0,
                                            1.225 * 0.9)
        self.assertAlmostEqual(ps_std, 16.6409, places=3)

    def test_example_level_accel_reduces(self):
        item = example_item()
        la = item.level_accel_run
        res = reduce_level_accel_run(
            la["times_s"], la["speeds_tas_ms"], la["weight_n"],
            isa_conditions(8000.0)[2], item.s_m2, item.cd0, item.k,
            w_ref_n=item.w_ref_n, rho_std=1.225, window=la["window"])
        self.assertAlmostEqual(res["mean_acceleration"], 1.0, places=3)
        self.assertAlmostEqual(res["mean_specific_excess_power"], 16.3155,
                               places=2)
        self.assertTrue(res["sustained_over_band"])
        self.assertGreater(res["mean_thrust_available"],
                           res["mean_drag"])


class TestCruiseReduction(unittest.TestCase):
    """Fuel flow reduction: sqrt weight correction + quadratic fit."""

    def test_corrected_fuel_flow_sqrt(self):
        # wf * sqrt(w_ref/w_test): heavier test weight -> lower correction.
        self.assertAlmostEqual(corrected_fuel_flow(0.5, 200000.0,
                                                   180000.0),
                               0.5 * 0.948683, places=5)

    def test_range_performance(self):
        rp = range_performance(230.0, 0.45)
        self.assertAlmostEqual(rp, 511.11, places=1)

    def test_tas_from_mach_fl350(self):
        # Mach 0.78 at 10668 m (troposphere, T = 218.8 K) -> ~231.3 m/s
        self.assertAlmostEqual(tas_from_mach(0.78, 10668.0), 231.3,
                               delta=0.3)

    def test_example_cruise_fit_finds_maximum(self):
        item = example_item()
        res = reduce_cruise_points(item.cruise_points, item.w_ref_n / G0)
        self.assertEqual(res["verdict"], "maximum-found")
        self.assertIsNotNone(res["max_rp_mach"])
        self.assertTrue(0.7 < res["max_rp_mach"] < 0.85)
        self.assertIsNotNone(res["lrc_mach"])
        self.assertGreater(res["lrc_mach"], res["max_rp_mach"])
        self.assertEqual(len(res["points"]), len(item.cruise_points))


class TestReportBuilder(unittest.TestCase):
    """The report: content model, rendering, worked-example numbers."""

    def test_analyze_sortie_full(self):
        model = build_report(example_item())
        res = model["results"]
        # every discipline present with real numbers
        self.assertGreater(res["takeoff"]["run"]["total_m"], 0.0)
        self.assertGreater(res["takeoff"]["oei"]["total_m"], 0.0)
        self.assertGreater(res["landing"]["certified_field_length_m"], 0.0)
        self.assertGreater(res["level_accel"]["mean_thrust_available"], 0.0)
        self.assertTrue(0.7 < res["cruise"]["max_rp_mach"] < 0.85)
        self.assertTrue(res["speeds"]["stall_rows"])
        self.assertTrue(res["scatter"]["rows"])
        self.assertTrue(res["scatter"]["within_band"])

    def test_conditions_recorded(self):
        res = analyze_sortie(example_item())
        c = res["conditions"]
        self.assertGreater(c["density_altitude_m"], 0.0)
        self.assertGreater(c["sigma_test"], 0.9)
        self.assertLess(c["sigma_test"], 1.0)

    def test_render_has_sections_and_numbers(self):
        md = example_report_markdown()
        for sec in ["## 1. Test conditions", "## 2. Takeoff performance",
                    "## 3. Landing performance",
                    "## 4. Level-acceleration thrust determination",
                    "## 5. Cruise performance",
                    "## 6. Stall speeds and V-speed corrections",
                    "## 7. Computed vs predicted scatter",
                    "## 8. Findings"]:
            self.assertIn(sec, md)
        self.assertIn("density altitude", md)
        self.assertIn("1.67", md)
        self.assertIn("thrust available", md)
        self.assertIn("not an approval", md.lower())
        self.assertIn("draft", md)
        self.assertNotIn("___", md)

    def test_model_json_roundtrip_plain(self):
        import json
        model = example_report_model()
        text = json.dumps(model)  # must not raise (plain JSON types)
        self.assertGreater(len(text), 2000)
        self.assertIn("draft-for-review", text)


class TestGates(unittest.TestCase):
    def test_core_gates_all_pass(self):
        model = build_report(example_item())
        gates = check_report(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_all_pass(self):
        md = example_report_markdown()
        gates = check_report_markdown(md)
        self.assertTrue(gates["all_pass"], gates)

    def test_sign_off_honest_model(self):
        model = build_report(example_item())
        self.assertEqual(model["status"], "draft-for-review")


class TestStandalone(unittest.TestCase):
    def test_no_skills_repo_required(self):
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = build_report(example_item())
        self.assertEqual(model["document_type"],
                         "Flight Test Performance Data Analysis Report")
        md = render_report_markdown(model)
        self.assertGreater(len(md), 2000)


if __name__ == "__main__":
    unittest.main()
