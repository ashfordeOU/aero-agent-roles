#!/usr/bin/env python3
"""Test space_systems_core: the executable engine of the Space Systems role.

Proves the role can DO its job standalone (no AeroSkills needed): orbit
mechanics, delta-v budgeting and propellant sizing, reaction wheel
sizing, power/thermal closure, comms link budget, report generation,
and evidence-gate checks. Anchor values come from the bound AeroSkills
space-systems leaves (hohmann-transfer, mission-delta-v-budget,
power-thermal-budget, solar-array-sizing, eclipse-time,
reaction-wheel-control, communication-link-budget).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))
from space_systems_core import (          # noqa: E402
    MU_EARTH, RE_EARTH, apply_margin,
    battery_capacity_required, build_report, check_report,
    check_report_markdown, circular_velocity, comms_link_budget,
    eclipse_geometry, eol_specific_power, example_mission,
    example_report_markdown, free_space_path_loss, hohmann_burn_delta_v,
    mission_delta_v_budget, orbit_period_seconds, perigee_lowering_delta_v,
    pointing_error_budget, power_and_thermal, propellant_mass,
    radiator_area, reaction_wheel_sizing, render_report_markdown,
    slant_range_m, solar_array_daylight_power, sum_delta_v, wet_mass,
)


class TestOrbitMechanics(unittest.TestCase):
    """Domain rules: vis-viva, periods, Hohmann and disposal burns."""

    def test_circular_velocity_anchors(self):
        # hohmann-transfer leaf anchors: LEO 6878 km -> ~7613 m/s,
        # GEO 42164 km -> ~3075 m/s.
        self.assertAlmostEqual(circular_velocity(6878e3), 7612.7, delta=1.0)
        self.assertAlmostEqual(circular_velocity(42164e3), 3074.7, delta=1.0)

    def test_geostationary_period(self):
        self.assertAlmostEqual(orbit_period_seconds(42164e3) / 3600.0,
                               23.934, delta=0.05)

    def test_hohmann_leo_to_geo_total(self):
        # Leaf reference: LEO(Re+500 km) -> GEO totals about 3816 m/s.
        dv = hohmann_burn_delta_v(RE_EARTH + 500e3, 42164e3)
        self.assertAlmostEqual(dv["total_m_s"], 3816.0, delta=60.0)
        self.assertEqual(dv["total_m_s"],
                         dv["dv1_m_s"] + dv["dv2_m_s"])

    def test_disposal_burn_positive_and_bounded(self):
        dv = perigee_lowering_delta_v(600.0, 100.0)
        v_circ = circular_velocity(RE_EARTH + 600e3)
        self.assertGreater(dv, 0.0)
        self.assertLess(dv, v_circ)
        # 600 km -> 100 km perigee is a ~140 m/s class burn.
        self.assertAlmostEqual(dv, 141.7, delta=3.0)


class TestDeltaVAndPropellant(unittest.TestCase):
    """Domain rules: rocket equation, margins (mission-delta-v-budget)."""

    def test_propellant_mass_anchor(self):
        # Leaf anchor: dv 2941.995 m/s, 1000 kg dry, 300 s -> ~1718.28 kg.
        self.assertAlmostEqual(propellant_mass(2941.995, 1000.0, 300.0),
                               1718.28, delta=0.5)
        self.assertAlmostEqual(wet_mass(2941.995, 1000.0, 300.0),
                               2718.28, delta=0.5)

    def test_zero_dv_zero_propellant(self):
        self.assertEqual(propellant_mass(0.0, 1000.0, 300.0), 0.0)

    def test_sum_and_margin(self):
        self.assertEqual(sum_delta_v([100.0, 200.0, 50.0]), 350.0)
        self.assertAlmostEqual(apply_margin(350.0, 0.15), 402.5, places=6)
        self.assertEqual(apply_margin(350.0, 0.0), 350.0)

    def test_example_budget_structure(self):
        budget = mission_delta_v_budget(example_mission())
        self.assertAlmostEqual(
            budget["nominal_dv_m_s"],
            sum(budget["contributions"].values()), places=6)
        self.assertAlmostEqual(budget["budgeted_dv_m_s"],
                               budget["nominal_dv_m_s"] * 1.15, places=6)
        self.assertGreater(budget["propellant_mass_kg"], 0.0)
        self.assertLess(budget["propellant_fraction"], 0.2)
        # disposal dominates a 600 km mission budget (realism marker)
        self.assertGreater(
            budget["contributions"]["End-of-life disposal (perigee lowering)"],
            budget["contributions"]["Injection dispersion correction"])


class TestEclipseAndPower(unittest.TestCase):
    """Domain rules: eclipse geometry, battery and solar array sizing."""

    def test_eclipse_geometry_600km(self):
        g = eclipse_geometry(600.0)
        self.assertAlmostEqual(g["period_s"], 5801.0, delta=20.0)
        self.assertAlmostEqual(g["shadow_fraction"], 0.367, delta=0.005)
        self.assertAlmostEqual(g["eclipse_time_min"], 35.5, delta=0.4)
        self.assertAlmostEqual(g["daylight_fraction"],
                               1.0 - g["shadow_fraction"], places=9)

    def test_battery_capacity_required(self):
        # 80 W over a 35.5 min eclipse at 30% DoD / 90% efficiency.
        wh = battery_capacity_required(80.0, 35.5, 0.30, 0.90)
        self.assertAlmostEqual(wh, 175.3, delta=0.2)

    def test_solar_array_daylight_power_anchor(self):
        # power-thermal-budget leaf anchor: 500 W, f=0.35, no margin.
        self.assertAlmostEqual(solar_array_daylight_power(500.0, 0.35, 1.0),
                               769.23, delta=0.5)
        self.assertAlmostEqual(solar_array_daylight_power(500.0, 0.35, 1.0, 0.20),
                               923.08, delta=0.5)

    def test_eol_specific_power_anchor(self):
        # solar-array-sizing leaf anchor: 1367*0.30*0.85*0.98^10.
        self.assertAlmostEqual(eol_specific_power(1367.0, 0.30, 0.85, 0.02, 10),
                               284.82, delta=0.05)

    def test_radiator_area(self):
        # 55 W at 293.15 K, eps 0.9 -> ~0.15 m^2.
        self.assertAlmostEqual(radiator_area(55.0, 293.15, 3.0, 0.90),
                               0.146, delta=0.01)

    def test_example_power_closes(self):
        pw = power_and_thermal(example_mission())
        self.assertGreaterEqual(pw["battery_margin"], 0.20)
        self.assertAlmostEqual(pw["array_area_m2"], 0.79, delta=0.03)
        self.assertAlmostEqual(pw["battery_sized_wh"], 215.0, delta=1.0)


class TestAdcs(unittest.TestCase):
    """Domain rules: wheel sizing h = J*omega and pointing RSS."""

    def test_slew_momentum_is_j_times_omega(self):
        ad = reaction_wheel_sizing(example_mission(), 5801.0)
        omega = (3.141592653589793 / 2.0) / 90.0
        self.assertAlmostEqual(ad["omega_slew_rad_s"], omega, places=9)
        self.assertAlmostEqual(ad["slew_momentum_nms"], 20.0 * omega,
                               places=4)

    def test_wheel_inertia_from_momentum_capacity(self):
        ad = reaction_wheel_sizing(example_mission(), 5801.0)
        # h = J_w * omega_max: 1.0 N m s at 6000 rpm.
        self.assertAlmostEqual(ad["wheel_inertia_kgm2"], 1.0 / 628.3185,
                               delta=1e-6)
        self.assertGreater(ad["required_momentum_nms"], 0.3)
        self.assertLess(ad["required_momentum_nms"],
                        ad["wheel_momentum_capacity_nms"])

    def test_pointing_budget_meets(self):
        pt = pointing_error_budget(example_mission())
        self.assertAlmostEqual(pt["rss_deg"], 0.0482, delta=0.001)
        self.assertTrue(pt["meets"])
        self.assertGreater(pt["margin"], 2.0)


class TestComms(unittest.TestCase):
    """Domain rules: Friis path loss and link margins."""

    def test_slant_range_600km_5deg(self):
        self.assertAlmostEqual(slant_range_m(600.0, 5.0) / 1000.0,
                               2329.0, delta=10.0)

    def test_free_space_path_loss_x_band(self):
        fsl = free_space_path_loss(2329e3, 8.2e9)
        self.assertAlmostEqual(fsl, 178.1, delta=0.5)

    def test_example_links_close(self):
        cm = comms_link_budget(example_mission())
        self.assertGreaterEqual(cm["downlink"]["margin_db"], 3.0)
        self.assertGreaterEqual(cm["uplink"]["margin_db"], 3.0)
        self.assertGreater(cm["daily_capacity_gb"],
                           cm["imaging_data_gb_per_day"])


class TestReportBuilderAndGates(unittest.TestCase):

    def test_example_model_values(self):
        model = build_report(example_mission())
        self.assertEqual(model["status"], "draft-for-review")
        self.assertEqual(model["orbit"]["altitude_km"], 600.0)
        dv = model["delta_v"]
        self.assertGreater(dv["nominal_dv_m_s"], 180.0)
        self.assertAlmostEqual(dv["budgeted_dv_m_s"],
                               dv["nominal_dv_m_s"] * 1.15, places=6)
        self.assertGreater(dv["propellant_mass_kg"], 15.0)
        self.assertAlmostEqual(model["adcs"]["wheel_momentum_capacity_nms"],
                               1.0, places=3)
        self.assertLess(model["power"]["array_area_m2"], 1.0)
        self.assertTrue(model["pointing"]["meets"])
        self.assertTrue(model["comms"]["downlink_meets"])
        self.assertTrue(model["mass"]["closes"])
        self.assertTrue(all(model["verdicts"].values()), model["verdicts"])

    def test_render_has_all_sections_and_markers(self):
        md = example_report_markdown()
        for n in range(1, 10):
            self.assertIn(f"## {n}.", md, f"section {n} missing")
        low = md.lower()
        self.assertIn("draft", low)
        self.assertIn("not an approval", low)
        self.assertIn("not launch readiness", low)
        self.assertGreater(len(md), 4000)

    def test_core_gates_all_pass(self):
        model = build_report(example_mission())
        gates = check_report(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_all_pass(self):
        md = example_report_markdown()
        gates = check_report_markdown(md)
        self.assertTrue(gates["all_pass"], gates)

    def test_gate_fails_on_approval_status(self):
        model = build_report(example_mission())
        model["status"] = "approved"
        gates = check_report(model)
        self.assertFalse(gates["sign_off_honest"])
        self.assertFalse(gates["all_pass"])

    def test_gate_fails_when_pointing_exceeds(self):
        model = build_report(example_mission())
        model["pointing"]["requirement_deg"] = 0.01
        model["pointing"]["meets"] = False
        gates = check_report(model)
        self.assertFalse(gates["pointing_meets"])
        self.assertFalse(gates["all_pass"])

    def test_deterministic_build(self):
        a = build_report(example_mission())
        b = build_report(example_mission())
        self.assertEqual(a["delta_v"]["nominal_dv_m_s"],
                         b["delta_v"]["nominal_dv_m_s"])

    def test_standalone_no_skills_repo(self):
        # Core must work with no AeroSkills present.
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = build_report(example_mission())
        self.assertGreater(model["delta_v"]["budgeted_dv_m_s"], 0.0)
        md = render_report_markdown(model)
        self.assertGreater(len(md), 4000)


if __name__ == "__main__":
    unittest.main()
