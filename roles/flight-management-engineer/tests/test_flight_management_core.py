#!/usr/bin/env python3
"""Test flight_management_core: the executable engine of the
Flight Management Engineer role.

Proves the role can DO its job standalone (no AeroSkills needed) and
that the domain numbers are real: RNP containment (ANP = 2 x sigma,
95% containment), the 70/110 holding-entry sector rule, outbound leg
timing and the 1-in-60 wind correction (leaf worked anchor 94.7140),
RF leg construction (radius circle, swept angle, exit track, chord),
DME arc geometry and bank angle, great-circle/rhumb anchors (1 deg on
the equator = R*pi/180), the RTA speed-command law, VNAV top-of-descent
and gradients, the ECON cruise clamp, radio navaid slant range, plus
the builder, the evidence gates and standalone mode.
"""
import json
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from flight_management_core import (  # noqa: E402
    NM_TO_M, G_MS2, R_EARTH_M,
    anp_from_sigma, build_report, check_report, check_report_markdown,
    containment_analysis, containment_margin_m, containment_pass,
    dme_arc_bank_angle_deg, dme_arc_chord_nm, dme_arc_geometry,
    dme_arc_length_nm, dme_arc_turn_radius_nm, example_item,
    example_report_markdown, fpa_gradient_ft_nm, great_circle_distance_m,
    great_circle_track_deg, hold_alpha_deg, hold_entry_analysis,
    holding_entry_lap_seconds, holding_entry_type, isa_speed_of_sound_m_s,
    margin_available_m, nav_bearing_deg, nav_dme_slant_range_m,
    nav_radial_deg, outbound_leg_seconds, perf_cost_index,
    perf_econ_mach_from_cost_index, perf_econ_summary,
    perf_max_range_speed_kts, perf_tas_from_mach, render_report_markdown,
    rf_leg_geometry, rhumb_course_deg, rhumb_distance_m,
    rhumb_vs_great_circle, rnp_nm_to_m, rta_achievable_window,
    rta_eta_s, rta_required_ground_speed_m_s, rta_speed_command,
    rta_time_error_s, vertical_band_ok, vnav_altitude_at_ft,
    vnav_constraint_ok, vnav_descent_gradient_ft_nm, vnav_fpa_deg,
    vnav_tod_distance_nm, wind_corrected_heading,
)


class TestRnpContainment(unittest.TestCase):
    """ANP = 2 x 1-sigma (95% containment), margin and verdict rules."""

    def test_anp_two_sigma(self):
        self.assertAlmostEqual(anp_from_sigma(92.6), 185.2, places=3)
        self.assertAlmostEqual(anp_from_sigma(200.0), 400.0, places=3)

    def test_rnp_nm_to_m(self):
        self.assertAlmostEqual(rnp_nm_to_m(0.3), 0.3 * 1852.0, places=6)
        self.assertAlmostEqual(rnp_nm_to_m(0.3), 555.6, places=1)

    def test_margin_and_available(self):
        self.assertAlmostEqual(containment_margin_m(555.6, 0.10), 55.56,
                               places=6)
        self.assertAlmostEqual(margin_available_m(185.2, 555.6, 0.10),
                               555.6 - 55.56 - 185.2, places=6)

    def test_containment_pass_inclusive(self):
        # boundary inclusive: anp == rnp passes with zero margin
        self.assertTrue(containment_pass(555.6, 555.6, 0.0))
        self.assertTrue(containment_pass(185.2, 555.6, 0.10))
        self.assertFalse(containment_pass(556.0, 555.6, 0.0))

    def test_analysis_verdicts(self):
        ok = containment_analysis(sigma_lateral_m=200.0, rnp_m=555.6,
                                  margin_fraction=0.10)
        self.assertTrue(ok["pass"])
        self.assertEqual(ok["verdict"], "PASS")
        bad = containment_analysis(sigma_lateral_m=400.0, rnp_m=555.6,
                                   margin_fraction=0.10)
        self.assertFalse(bad["pass"])
        self.assertEqual(bad["verdict"], "FAIL")

    def test_analysis_anp_direct(self):
        r = containment_analysis(anp_m=400.0, rnp_m=555.6, margin_fraction=0.0)
        self.assertAlmostEqual(r["anp_m"], 400.0, places=3)


class TestHoldingEntry(unittest.TestCase):
    """70/110 sector rule, outbound timing, 1-in-60 wind correction."""

    def test_alpha_arithmetic(self):
        self.assertAlmostEqual(hold_alpha_deg(180.0, 260.0), 80.0, places=6)
        self.assertAlmostEqual(hold_alpha_deg(90.0, 90.0), 0.0, places=6)
        self.assertAlmostEqual(hold_alpha_deg(90.0, 270.0), 180.0, places=6)
        self.assertAlmostEqual(hold_alpha_deg(350.0, 10.0), 20.0, places=6)
        self.assertAlmostEqual(hold_alpha_deg(30.0, 90.0), 60.0, places=6)

    def test_entry_sector_boundaries(self):
        self.assertEqual(holding_entry_type(0.0, "right"), "direct")
        self.assertEqual(holding_entry_type(70.0, "right"), "direct")
        self.assertEqual(holding_entry_type(70.001, "right"), "teardrop")
        self.assertEqual(holding_entry_type(90.0, "right"), "teardrop")
        self.assertEqual(holding_entry_type(110.0, "right"), "teardrop")
        self.assertEqual(holding_entry_type(110.001, "right"), "parallel")
        self.assertEqual(holding_entry_type(180.0, "right"), "parallel")

    def test_left_hand_mirrors(self):
        for alpha in (50.0, 90.0, 130.0, 70.0, 110.0):
            self.assertEqual(holding_entry_type(alpha, "left"),
                             holding_entry_type(alpha, "right"))

    def test_entry_valueerrors(self):
        with self.assertRaises(ValueError):
            holding_entry_type(-1.0, "right")
        with self.assertRaises(ValueError):
            holding_entry_type(181.0, "right")
        with self.assertRaises(ValueError):
            holding_entry_type(50.0, "bank")

    def test_outbound_leg_timing(self):
        self.assertEqual(outbound_leg_seconds(12000.0), 60.0)
        self.assertEqual(outbound_leg_seconds(14000.0), 60.0)
        self.assertEqual(outbound_leg_seconds(14001.0), 90.0)
        self.assertEqual(outbound_leg_seconds(20000.0), 90.0)

    def test_wind_correction_leaf_anchor(self):
        # Worked anchor from the holding-pattern-entry leaf: 4.71 deg at
        # outbound 090, wind from 135/20 kt, TAS 180 kt.
        corr, raw = wind_corrected_heading(90.0, 135.0, 20.0, 180.0)
        self.assertAlmostEqual(corr, 94.7140, places=3)
        self.assertAlmostEqual(raw, 4.7140, places=3)
        corr2, raw2 = wind_corrected_heading(90.0, 315.0, 20.0, 180.0)
        self.assertAlmostEqual(corr + corr2, 180.0, places=6)
        self.assertAlmostEqual(raw2, -4.7140, places=3)

    def test_entry_lap_times(self):
        self.assertEqual(holding_entry_lap_seconds("direct", 60.0), 240.0)
        self.assertEqual(holding_entry_lap_seconds("teardrop", 90.0), 330.0)
        self.assertEqual(holding_entry_lap_seconds("parallel", 60.0), 360.0)

    def test_full_hold_analysis(self):
        h = hold_entry_analysis(arrival_track_deg=180.0,
                                hold_inbound_course_deg=260.0,
                                turn_direction="right", altitude_ft=20000.0,
                                outbound_heading_deg=80.0,
                                wind_from_deg=40.0, wind_speed_kt=30.0,
                                tas_kt=260.0)
        self.assertEqual(h["entry"], "teardrop")
        self.assertAlmostEqual(h["alpha_deg"], 80.0, places=1)
        self.assertEqual(h["outbound_leg_s"], 90.0)
        self.assertEqual(h["entry_lap_s"], 330.0)


class TestLateralGeometry(unittest.TestCase):
    """Great-circle and rhumb anchors (R = 6371000 m)."""

    def test_great_circle_equator_degree(self):
        # 1 deg of longitude at the equator = R * pi/180
        expected = R_EARTH_M * math.pi / 180.0
        self.assertAlmostEqual(great_circle_distance_m(0.0, 0.0, 0.0, 1.0),
                               expected, places=1)

    def test_great_circle_meridian_degree(self):
        self.assertAlmostEqual(great_circle_distance_m(0.0, 0.0, 1.0, 0.0),
                               R_EARTH_M * math.pi / 180.0, places=1)

    def test_great_circle_tracks(self):
        self.assertAlmostEqual(great_circle_track_deg(0.0, 0.0, 0.0, 10.0),
                               90.0, places=6)
        self.assertAlmostEqual(great_circle_track_deg(0.0, 0.0, 10.0, 0.0),
                               0.0, places=6)
        self.assertAlmostEqual(great_circle_track_deg(0.0, 0.0, -10.0, 0.0),
                               180.0, places=6)

    def test_rhumb_meridian_equals_gc(self):
        r = rhumb_vs_great_circle(40.0, -75.0, 41.0, -75.0)
        self.assertAlmostEqual(r["delta_m"], 0.0, places=6)
        self.assertEqual(rhumb_course_deg(0.0, 0.0, 10.0, 0.0), 0.0)
        self.assertEqual(rhumb_course_deg(0.0, 0.0, 0.0, 10.0), 90.0)

    def test_rhumb_parallel_at_60(self):
        # along-parallel at lat 60 over 1 deg: R*rad(1)*cos(60)
        expected = 6371000.0 * math.radians(1.0) * math.cos(math.radians(60.0))
        self.assertAlmostEqual(rhumb_distance_m(60.0, 0.0, 60.0, 1.0),
                               expected, places=1)

    def test_rhumb_longer_than_gc(self):
        r = rhumb_vs_great_circle(30.0, -70.0, 32.0, -65.0)
        self.assertGreaterEqual(r["delta_m"], 0.0)
        self.assertGreater(r["great_circle_m"], 0.0)


class TestRfLeg(unittest.TestCase):
    """RF construction anchors: EF(0,0), inbound 090, R=15 NM, RIGHT."""

    def test_rf_geometry_anchor(self):
        g = rf_leg_geometry((0.0, 0.0), 90.0, 15.0, "RIGHT", 90.0)
        self.assertAlmostEqual(g["center_nm"][0], 0.0, places=3)
        self.assertAlmostEqual(g["center_nm"][1], -15.0, places=3)
        self.assertAlmostEqual(g["xf"][0], 15.0, places=3)
        self.assertAlmostEqual(g["xf"][1], -15.0, places=3)
        self.assertTrue(g["exit_on_arc"])
        self.assertAlmostEqual(g["sweep_deg"], 90.0, places=6)
        self.assertAlmostEqual(g["arc_length_nm"], 15.0 * math.pi / 2.0,
                               places=3)
        self.assertAlmostEqual(g["chord_nm"], 15.0 * math.sqrt(2.0), places=3)
        self.assertAlmostEqual(g["exit_track_deg"], 180.0, places=6)
        self.assertTrue(g["valid"])

    def test_rf_left_mirror(self):
        g = rf_leg_geometry((0.0, 0.0), 90.0, 15.0, "LEFT", 90.0)
        self.assertAlmostEqual(g["center_nm"][1], 15.0, places=3)
        self.assertAlmostEqual(g["exit_track_deg"], 0.0, places=6)


class TestDmeArc(unittest.TestCase):
    """DME arc length/chord/bank: r=15 NM over 60 deg of radial."""

    def test_arc_length_chord(self):
        self.assertAlmostEqual(dme_arc_length_nm(15.0, 60.0),
                               15.0 * math.pi / 3.0, places=3)
        self.assertAlmostEqual(dme_arc_chord_nm(15.0, 60.0), 15.0, places=3)

    def test_arc_bank_angle(self):
        # bank = atan(V^2/(g*r)), V = 250 kt, r = 15 NM in SI
        v = 250.0 * 0.514444
        r_m = 15.0 * NM_TO_M
        expected = math.degrees(math.atan(v * v / (G_MS2 * r_m)))
        self.assertAlmostEqual(dme_arc_bank_angle_deg(250.0, 15.0),
                               expected, places=6)
        self.assertAlmostEqual(dme_arc_bank_angle_deg(250.0, 15.0),
                               3.475, places=2)

    def test_turn_radius(self):
        v = 250.0 * 0.514444
        r_m = v * v / (G_MS2 * math.tan(math.radians(25.0)))
        self.assertAlmostEqual(dme_arc_turn_radius_nm(250.0, 25.0),
                               r_m / NM_TO_M, places=6)

    def test_arc_geometry(self):
        g = dme_arc_geometry(15.0, 30.0, 90.0)
        self.assertAlmostEqual(g["turn_angle_deg"], 60.0, places=6)
        self.assertAlmostEqual(g["arc_length_nm"], 15.0 * math.pi / 3.0,
                               places=3)


class TestRta(unittest.TestCase):
    """RTA law anchors (SI)."""

    def test_eta(self):
        self.assertEqual(rta_eta_s(200000.0, 250.0), 800.0)
        with self.assertRaises(ValueError):
            rta_eta_s(200000.0, 0.0)

    def test_required_ground_speed(self):
        self.assertEqual(rta_required_ground_speed_m_s(100000.0, 500.0, 0.0),
                         200.0)

    def test_time_error(self):
        self.assertEqual(rta_time_error_s(800.0, 800.0, 0.0), 0.0)
        self.assertEqual(rta_time_error_s(800.0, 750.0, 0.0), 50.0)

    def test_isa_speed_of_sound_sea_level(self):
        expected = math.sqrt(1.4 * 287.05 * 288.15)
        self.assertAlmostEqual(isa_speed_of_sound_m_s(0.0), expected, places=2)
        self.assertAlmostEqual(isa_speed_of_sound_m_s(0.0), 340.29, places=1)

    def test_feasible_slowdown(self):
        # Route-shaped case: FL200 (a ~316 m/s), demand 25 s late.
        alt = 20000.0 * 0.3048
        a = isa_speed_of_sound_m_s(alt)
        eta = rta_eta_s(87952.0, 240.0)
        rta = rta_speed_command(remaining_distance_m=87952.0,
                                ground_speed_m_s=240.0,
                                wind_along_m_s=-5.0,
                                rta_time_s=eta + 25.0, altitude_m=alt)
        self.assertTrue(rta["feasible"])
        self.assertEqual(rta["verdict"], "rta-feasible")
        expected_req = 87952.0 / (eta + 25.0)
        self.assertAlmostEqual(rta["required_gs_m_s"], expected_req, places=2)
        expected_mach = (expected_req + 5.0) / a
        self.assertAlmostEqual(rta["command_mach"], expected_mach, places=4)
        self.assertAlmostEqual(rta["remaining_error_s"], 0.0, places=6)

    def test_unfeasible_high_demand(self):
        alt = 20000.0 * 0.3048
        eta = rta_eta_s(87952.0, 240.0)
        rta = rta_speed_command(remaining_distance_m=87952.0,
                                ground_speed_m_s=240.0,
                                wind_along_m_s=-5.0,
                                rta_time_s=max(1.0, eta - 100.0),
                                altitude_m=alt)
        self.assertFalse(rta["feasible"])
        self.assertEqual(rta["verdict"], "rta-unfeasible")
        self.assertEqual(rta["command_mach"], 0.82)

    def test_window(self):
        alt = 20000.0 * 0.3048
        w = rta_achievable_window(87952.0, alt, -5.0, 0.70, 0.82)
        self.assertGreater(w["eta_min_s"], 0.0)
        self.assertGreater(w["eta_max_s"], w["eta_min_s"])


class TestVnavAndPerf(unittest.TestCase):
    """Top of descent, gradient/FPA math, ECON clamps, band checks."""

    def test_tod(self):
        self.assertAlmostEqual(vnav_tod_distance_nm(35000.0, 20000.0, 318.4),
                               15000.0 / 318.4, places=4)

    def test_fpa_roundtrip(self):
        grad = fpa_gradient_ft_nm(3.0)
        self.assertAlmostEqual(vnav_fpa_deg(grad), 3.0, places=6)
        self.assertAlmostEqual(grad,
                               math.tan(math.radians(3.0)) * 6076.1154,
                               places=3)

    def test_gradient_and_altitude(self):
        g = vnav_descent_gradient_ft_nm(20000.0, 6000.0, 47.49)
        self.assertAlmostEqual(g, 14000.0 / 47.49, places=3)
        alt = vnav_altitude_at_ft(20000.0, g, 47.49)
        self.assertAlmostEqual(alt, 6000.0, places=0)

    def test_constraint_verdicts(self):
        self.assertTrue(vnav_constraint_ok(6005.0, 6000.0, False, tol_ft=20.0))
        self.assertFalse(vnav_constraint_ok(5194.0, 6000.0, False,
                                            tol_ft=20.0))
        self.assertTrue(vnav_constraint_ok(5194.0, 5000.0, True))

    def test_vertical_bands(self):
        self.assertTrue(vertical_band_ok(35000.0, 33000.0, 39000.0))
        self.assertTrue(vertical_band_ok(20000.0, 19500.0, 20500.0))
        self.assertFalse(vertical_band_ok(12000.0, 20000.0, 20000.0))

    def test_cost_index(self):
        self.assertEqual(perf_cost_index(60.0, 1.0), 60.0)
        self.assertEqual(perf_cost_index(0.0, 2.0), 0.0)

    def test_econ_clamped_and_positive(self):
        for ci in (0.0, 30.0, 100.0):
            m = perf_econ_mach_from_cost_index(ci, 62000.0, 35000.0)
            self.assertGreaterEqual(m, 0.70)
            self.assertLessEqual(m, 0.82)
            self.assertGreater(perf_max_range_speed_kts(62000.0, 35000.0), 0.0)

    def test_mach_tas_roundtrip(self):
        tas = perf_tas_from_mach(0.78, 35000.0)
        mach_back = tas / (math.sqrt(1.4 * 287.05
                                     * (288.15 - 0.0065 * 35000.0 * 0.3048))
                           * 1.943844492)
        self.assertAlmostEqual(mach_back, 0.78, places=6)

    def test_econ_summary_shape(self):
        s = perf_econ_summary(30.0, 62000.0, 35000.0)
        self.assertIn("mach", s)
        self.assertGreater(s["fuel_per_nm_kg"], 0.0)


class TestNavaidGeometry(unittest.TestCase):
    """DME slant range and VOR bearing/radial conversions."""

    def test_slant_range(self):
        # 15 NM ground range at FL200: sqrt(27780^2 + 6096^2)
        expected = math.hypot(15.0 * NM_TO_M, 20000.0 * 0.3048)
        self.assertAlmostEqual(nav_dme_slant_range_m(15.0 * NM_TO_M, 0.0,
                                                     20000.0 * 0.3048),
                               expected, places=1)

    def test_bearing_radial(self):
        self.assertEqual(nav_bearing_deg(0.0, 10.0), 0.0)
        self.assertEqual(nav_bearing_deg(10.0, 0.0), 90.0)
        self.assertEqual(nav_radial_deg(30.0), 210.0)
        self.assertEqual(nav_radial_deg(210.0), 30.0)


class TestBuilderAndGates(unittest.TestCase):

    def test_example_route_facts(self):
        model = build_report(example_item())
        self.assertEqual(len(model["legs"]), 4)
        self.assertEqual(len(model["waypoints"]), 5)
        self.assertEqual(model["hold"]["entry"], "teardrop")
        self.assertEqual(model["rnp"]["rnp_nm"], 0.3)
        self.assertTrue(model["rnp"]["containment"]["pass"])
        self.assertTrue(model["rta"]["feasible"])
        # example deliberately surfaces the W005 crossing finding
        self.assertFalse(model["vnav"]["w005_crossing_ok"])
        self.assertGreaterEqual(model["n_findings"], 1)
        self.assertEqual(model["status"], "draft-for-review")
        self.assertEqual(model["total_distance_nm"], sum(
            leg["distance_nm"] for leg in model["legs"]))

    def test_core_gates_all_pass(self):
        model = build_report(example_item())
        gates = check_report(model)
        self.assertTrue(gates["all_pass"], gates)
        for gate in ("route_stated", "rnp_present", "containment_checked",
                     "entries_correct", "sign_off_honest"):
            self.assertTrue(gates[gate], gate)

    def test_containment_fail_still_gate_checked(self):
        item = example_item()
        item.sigma_lateral_m = 400.0  # ANP 800 m > RNP 555.6 m + margin
        model = build_report(item)
        self.assertFalse(model["rnp"]["containment"]["pass"])
        self.assertEqual(model["rnp"]["containment"]["verdict"], "FAIL")
        gates = check_report(model)
        self.assertTrue(gates["all_pass"], gates)  # structural gates

    def test_markdown_gates_all_pass(self):
        md = example_report_markdown()
        gates = check_report_markdown(md)
        self.assertTrue(gates["all_pass"], gates)
        self.assertGreater(len(md), 2000)

    def test_markdown_sections_present(self):
        md = example_report_markdown()
        for n in range(1, 9):
            self.assertIn("## %d. " % n, md, "section %d missing" % n)
        low = md.lower()
        self.assertIn("not an approval", low)
        self.assertIn("draft", low)
        self.assertIn("teardrop", low)

    def test_model_plain_json(self):
        # protocol: model is plain JSON (no NaN / non-serializable objects)
        model = build_report(example_item())
        text = json.dumps(model)
        self.assertGreater(len(text), 1500)
        self.assertNotIn("NaN", text)

    def test_standalone_no_skills_repo(self):
        # Core must work with no AeroSkills present.
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = build_report(example_item())
        self.assertTrue(model["rnp"]["containment"]["verdict"] in ("PASS", "FAIL"))
        md = render_report_markdown(model)
        self.assertGreater(len(md), 2000)


if __name__ == "__main__":
    unittest.main()
