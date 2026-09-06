#!/usr/bin/env python3
"""Test aircraft_performance_core: the executable engine of the Aircraft
Performance Engineer role.

Proves the role can DO its job standalone (no AeroSkills needed): the
FAR-25.113-style balanced field length / V1 balance, the propeller
Breguet cruise range, main rotor sizing, blade flap dynamics, lead-lag
dynamics with ground-resonance clearance, hover in ground effect,
axial-descent flow states with the windmill-brake momentum model,
banked-turn performance, the range/endurance fuel closure, report
generation, and evidence-gate checks.

Real anchors are taken from the bound AeroSkills leaves' own worked
examples (which this engine reproduces): balanced V1 77.2815 m/s and
balanced field length 2138.10 m for the twin-engine transport case;
propeller range 1472.24 km for the turboprop case; disk radius 6.3352 m
and CT 0.006479 for the 4500 kg / 350 Pa sizing case; Lock number
7.58079 and coning 5.6103 deg for the blade case; coincidence 43.6924
rad/s with a resonance-adjacent verdict for the 5.0 Hz airframe case;
IGE total 369230 W and a ~4.0 m hover ceiling at 360 kW; windmill-brake
power -352017.6 W at Vd = 25 m/s; turn total 599092 W at n = 2 with a
2.00491 sustained load factor at 600 kW; hover endurance 20927.3 s and
cruise range 2433442 m for the six-tonne fuel closure case.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from aircraft_performance_core import (  # noqa: E402
    G0, accelerate_go_distance, accelerate_stop_distance,
    axial_flow_state, balanced_field_length, balanced_v1,
    best_endurance_speed, best_range_speed, blade_area_chord,
    blade_flap_inertia_uniform, blade_flapping_summary,
    braking_deceleration, build_performance_report, check_report,
    check_report_markdown, coincidence_rotor_speed, cruise_endurance,
    cruise_range, descent_summary, disk_area, disk_area_and_radius,
    example_item, example_report_markdown, final_mass_from_fuel_fraction,
    fixed_frame_lag_modes, flap_frequency_ratio, fuel_flow,
    generalized_induced_velocity, ground_acceleration,
    ground_effect_factor, ground_resonance_clearance, hover_coning_angle,
    hover_endurance, hover_ground_effect, hover_power, hover_power_constant,
    hover_thrust_coefficient, ige_induced_power, ige_total_power,
    lag_frequency_ratio_hinge_offset, lead_lag_summary, lock_number,
    max_hover_height, oei_thrust, oge_total_power, parasite_power,
    power_margin, profile_power, propeller_range, propeller_range_km,
    psfc_lb_per_hp_h_to_kg_per_w_s, render_report_markdown,
    rotor_descent_power, rotor_descent_torque, solidity_closure,
    specific_range, sustained_load_factor, tip_mach,
    torque_reversal_condition, turn_power, vortex_ring_band_limits,
    windmill_brake_induced_velocity,
)


class TestBalancedFieldLength(unittest.TestCase):
    """Airplane A-1 anchors (balanced-field-length leaf worked case)."""

    def test_oei_thrust_split(self):
        self.assertAlmostEqual(oei_thrust(150000.0, 2), 75000.0)
        with self.assertRaises(ValueError):
            oei_thrust(150000.0, 1)  # OEI needs >= 2 engines

    def test_worked_case_v1_and_bfl_anchors(self):
        kwargs = dict(thrust_all_n=150000.0, engine_count=2, weight_n=600000.0,
                      mu_roll=0.03, mu_brake=0.45, v_lof_ms=80.0,
                      oei_climb_gradient=0.024)
        v1 = balanced_v1(**kwargs)
        self.assertAlmostEqual(v1, 77.2815, places=2)
        bfl = balanced_field_length(v1, **kwargs)
        self.assertAlmostEqual(bfl, 2138.10, places=1)
        # the balance identity: ASD(V1) == AGD(V1) to machine precision
        asd = accelerate_stop_distance(v1, 150000.0, 600000.0, 0.03, 0.45)
        agd = accelerate_go_distance(v1, 150000.0, 2, 600000.0, 0.03,
                                     80.0, 0.024)
        self.assertAlmostEqual(asd, agd, places=6)
        self.assertLess(v1, 80.0)

    def test_bracket_monotonicity(self):
        # ASD rises and AGD falls with V1: unique crossing inside the bracket
        self.assertEqual(accelerate_stop_distance(0.0, 150000.0, 600000.0,
                                                   0.03, 0.45), 0.0)
        self.assertGreater(accelerate_go_distance(0.0, 150000.0, 2, 600000.0,
                                                  0.03, 80.0, 0.024),
                           accelerate_go_distance(40.0, 150000.0, 2, 600000.0,
                                                  0.03, 80.0, 0.024))
        self.assertLess(accelerate_stop_distance(40.0, 150000.0, 600000.0,
                                                 0.03, 0.45),
                        accelerate_stop_distance(80.0, 150000.0, 600000.0,
                                                 0.03, 0.45))

    def test_valueerror_rejections(self):
        with self.assertRaises(ValueError):
            balanced_v1(150000.0, 2, 600000.0, 0.03, 0.45, 80.0, 0.024,
                        reaction_time_s=-1.0)
        with self.assertRaises(ValueError):
            braking_deceleration(1.0)   # unity friction is not physical
        with self.assertRaises(ValueError):
            ground_acceleration(1000.0, 600000.0, 0.03)  # cannot accelerate


class TestPropellerRange(unittest.TestCase):
    """Airplane A-2 anchors (propeller-range leaf worked case)."""

    def test_psfc_conversion_anchor(self):
        self.assertAlmostEqual(psfc_lb_per_hp_h_to_kg_per_w_s(0.55),
                               9.293126e-8, delta=1e-13)

    def test_range_anchor(self):
        cp = psfc_lb_per_hp_h_to_kg_per_w_s(0.55)
        rm = propeller_range(0.80, cp, 12.0, 11500.0, 10000.0)
        self.assertAlmostEqual(rm, 1472236.70, delta=1.0)
        self.assertAlmostEqual(propeller_range_km(0.80, cp, 12.0,
                                                  11500.0, 10000.0),
                               1472.24, delta=0.01)

    def test_fuel_fraction_derivation(self):
        self.assertEqual(final_mass_from_fuel_fraction(11500.0,
                                                       1500.0 / 11500.0),
                         10000.0)
        with self.assertRaises(ValueError):
            final_mass_from_fuel_fraction(11500.0, 1.0)

    def test_scaling_laws(self):
        cp = psfc_lb_per_hp_h_to_kg_per_w_s(0.55)
        base = propeller_range(0.80, cp, 12.0, 11500.0, 10000.0)
        self.assertAlmostEqual(propeller_range(0.90, cp, 12.0, 11500.0,
                                               10000.0),
                               base * 0.9 / 0.8, delta=1e-3)
        self.assertAlmostEqual(propeller_range(0.80, 2 * cp, 12.0, 11500.0,
                                               10000.0),
                               base / 2.0, delta=1e-3)

    def test_valueerror_rejections(self):
        cp = psfc_lb_per_hp_h_to_kg_per_w_s(0.55)
        with self.assertRaises(ValueError):
            propeller_range(1.2, cp, 12.0, 11500.0, 10000.0)
        with self.assertRaises(ValueError):
            propeller_range(0.8, cp, 12.0, 11500.0, 12000.0)  # m1 >= m0


class TestMainRotorSizing(unittest.TestCase):
    """Rotorcraft H-2 anchors (main-rotor-sizing leaf worked case)."""

    def test_disk_sized_at_ceiling(self):
        thrust = 4500.0 * G0
        area, radius = disk_area_and_radius(thrust, 350.0)
        self.assertAlmostEqual(area, 126.0855, places=3)
        self.assertAlmostEqual(radius, 6.3352, places=3)
        self.assertAlmostEqual(thrust / area, 350.0, places=6)
        self.assertAlmostEqual(3.141592653589793 * radius ** 2, area,
                               places=6)

    def test_ct_ceiling_identity(self):
        thrust = 4500.0 * G0
        ct = hover_thrust_coefficient(thrust, 1.225,
                                      disk_area_and_radius(thrust, 350.0)[1],
                                      210.0)
        self.assertAlmostEqual(ct, 0.006479, delta=1e-6)
        self.assertAlmostEqual(ct, 350.0 / (1.225 * 210.0 ** 2), places=9)

    def test_solidity_closure_round_trip(self):
        ct = 0.0064787819889860696
        sigma = solidity_closure(ct, 0.12)
        self.assertAlmostEqual(sigma, 0.053990, places=5)
        self.assertAlmostEqual(sigma * 0.12, ct, places=12)

    def test_blade_layout(self):
        area, radius = disk_area_and_radius(4500.0 * G0, 350.0)
        ba, chord = blade_area_chord(0.053990, area, 4, radius)
        self.assertAlmostEqual(ba, 6.8073, places=3)
        self.assertAlmostEqual(chord, 0.2686, places=3)
        self.assertAlmostEqual(4 * chord * radius / area, 0.053990,
                               places=5)

    def test_tip_mach(self):
        self.assertAlmostEqual(tip_mach(210.0, 340.3), 0.61710, places=4)

    def test_valueerror_rejections(self):
        with self.assertRaises(ValueError):
            blade_area_chord(0.05, 100.0, 3.5, 6.0)  # fractional blade count
        with self.assertRaises(ValueError):
            disk_area_and_radius(0.0, 350.0)


class TestBladeFlapDynamics(unittest.TestCase):
    """Rotorcraft H-3 anchors (blade-flapping leaf worked case)."""

    def test_uniform_inertia(self):
        self.assertEqual(blade_flap_inertia_uniform(50.0, 6.0), 600.0)

    def test_lock_number_anchor(self):
        gamma = lock_number(1.225, 5.73, 0.5, 6.0, 600.0)
        self.assertAlmostEqual(gamma, 7.58079, places=4)
        self.assertTrue(5.0 <= gamma <= 12.0)   # published band

    def test_coning_anchor(self):
        a0 = hover_coning_angle(7.58079, 0.170, 0.050)
        self.assertAlmostEqual(a0, 0.09792, places=4)
        self.assertAlmostEqual(a0 * 180.0 / 3.141592653589793, 5.6103,
                               places=3)

    def test_coning_balance_zero(self):
        # theta0/4 = lambda/3 -> a0 = 0 exactly
        self.assertAlmostEqual(hover_coning_angle(7.58079, 0.08, 0.06),
                               0.0, places=12)

    def test_flap_frequency_ratio(self):
        self.assertEqual(flap_frequency_ratio(0.0), 1.0)   # central hinge
        self.assertAlmostEqual(flap_frequency_ratio(0.05), 1.03872,
                               places=4)
        self.assertAlmostEqual(flap_frequency_ratio(0.5),
                               (2.5) ** 0.5, places=6)

    def test_summary_keys_and_bands(self):
        s = blade_flapping_summary(50.0, 6.0, 0.50, 0.170, 0.050, 0.05)
        self.assertEqual(set(s.keys()),
                         {"lock_number", "flap_inertia_kg_m2",
                          "coning_angle_rad", "coning_angle_deg",
                          "flap_frequency_ratio", "flap_frequency_per_rev"})
        self.assertAlmostEqual(s["flap_frequency_per_rev"],
                               s["flap_frequency_ratio"])
        self.assertTrue(5.0 <= s["lock_number"] <= 12.0)
        self.assertTrue(3.0 <= s["coning_angle_deg"] <= 8.0)


class TestLeadLagDynamics(unittest.TestCase):
    """Rotorcraft H-1 anchors (lead-lag leaf worked case)."""

    def test_lag_frequency_ratio(self):
        self.assertEqual(lag_frequency_ratio_hinge_offset(0.0), 0.0)
        nu = lag_frequency_ratio_hinge_offset(0.05)
        self.assertAlmostEqual(nu, 0.28098, places=4)
        self.assertTrue(0.2 <= nu <= 0.4)
        self.assertAlmostEqual(lag_frequency_ratio_hinge_offset(0.5),
                               1.5 ** 0.5, places=6)

    def test_fixed_frame_modes(self):
        nu = lag_frequency_ratio_hinge_offset(0.05)
        modes = fixed_frame_lag_modes(nu, 44.0)
        self.assertAlmostEqual(modes["collective_hz"], 1.96762, places=4)
        self.assertAlmostEqual(modes["regressing_hz"], 5.03520, places=4)
        self.assertAlmostEqual(modes["advancing_hz"], 8.97044, places=4)

    def test_coincidence_and_verdict(self):
        nu = lag_frequency_ratio_hinge_offset(0.05)
        self.assertAlmostEqual(coincidence_rotor_speed(nu, 5.0), 43.69244,
                               places=4)
        res = ground_resonance_clearance(nu, 44.0, 5.0)
        self.assertEqual(res["verdict"], "resonance-adjacent")
        self.assertAlmostEqual(res["clearance_fraction"], -0.00699,
                               places=4)
        clear = ground_resonance_clearance(nu, 44.0, 3.5)
        self.assertEqual(clear["verdict"], "clear")
        self.assertAlmostEqual(clear["coincidence_omega"], 30.58471,
                               places=4)

    def test_guard_nu_equals_one(self):
        with self.assertRaises(ValueError):
            coincidence_rotor_speed(1.0, 5.0)   # |1 - nu| = 0 guard

    def test_summary_convention(self):
        # first arg below 1 is treated as a hinge offset e, >= 1 as nu
        s = lead_lag_summary(0.05, 44.0, 5.0)
        self.assertAlmostEqual(s["lag_frequency_ratio"], 0.28098,
                               places=4)
        self.assertIn("verdict", s)


class TestHoverGroundEffect(unittest.TestCase):
    """Rotorcraft H-1 anchors (hover-ground-effect leaf worked case)."""

    def test_factor_exact_anchors(self):
        self.assertEqual(ground_effect_factor(5.0, 5.0), 0.9375)
        self.assertEqual(ground_effect_factor(2.5, 5.0), 0.75)
        self.assertEqual(ground_effect_factor(10.0, 5.0), 0.984375)

    def test_factor_floor(self):
        with self.assertRaises(ValueError):
            ground_effect_factor(2.0, 5.0)   # z/R = 0.4 < 0.5 floor

    def test_power_terms(self):
        r = hover_ground_effect(2200.0, 5.0, 5.0, available_power=360000.0)
        self.assertAlmostEqual(r["hover_induced_velocity"], 10.5887,
                               places=3)
        self.assertAlmostEqual(r["ideal_induced_power_W"], 228448.0,
                               delta=1.0)
        self.assertAlmostEqual(r["profile_power_W"], 122935.0, delta=1.0)
        self.assertAlmostEqual(r["ige_induced_power_W"],
                               r["ideal_induced_power_W"]
                               * r["ground_effect_factor"], places=6)
        self.assertAlmostEqual(r["ige_total_power_W"], 369230.0, delta=1.0)
        self.assertAlmostEqual(r["oge_total_power_W"], 385650.0, delta=1.0)
        self.assertLess(r["ige_total_power_W"], r["oge_total_power_W"])
        self.assertAlmostEqual(r["power_margin_W"], -9230.0, delta=1.0)
        # bisected ceiling root about 4.0 m at 360 kW
        self.assertTrue(3.9 <= r["max_hover_height"] <= 4.1)

    def test_ceiling_none_above_oge(self):
        self.assertIsNone(max_hover_height(2200.0, 5.0, 400000.0))

    def test_ceiling_root_consistency(self):
        z = max_hover_height(2200.0, 5.0, 360000.0)
        self.assertIsNotNone(z)
        r = hover_ground_effect(2200.0, 5.0, z, available_power=360000.0)
        # IGE total power at the returned height equals the available power
        self.assertAlmostEqual(r["ige_total_power_W"], 360000.0, delta=1.0)

    def test_power_identity(self):
        r = hover_ground_effect(2200.0, 5.0, 5.0, available_power=None)
        self.assertIsNone(r["power_margin_W"])
        self.assertIsNone(r["max_hover_height"])
        self.assertAlmostEqual(ige_total_power(
            r["ideal_induced_power_W"], r["profile_power_W"],
            r["ground_effect_factor"], 1.15), r["ige_total_power_W"],
            places=6)
        self.assertAlmostEqual(oge_total_power(r["ideal_induced_power_W"],
                                               r["profile_power_W"], 1.15),
                               r["oge_total_power_W"], places=6)


class TestAxialDescent(unittest.TestCase):
    """Rotorcraft H-1 anchors (axial-descent leaf worked case)."""

    def test_flow_state_classification(self):
        vh = 10.5887
        self.assertEqual(axial_flow_state(0.0, vh), "hover")
        self.assertEqual(axial_flow_state(15.0, vh), "vortex-ring-band")
        self.assertEqual(axial_flow_state(25.0, vh), "windmill-brake")
        self.assertEqual(axial_flow_state(2.0 * vh, vh), "windmill-brake")
        with self.assertRaises(ValueError):
            axial_flow_state(-5.0, vh)   # climb is not a descent state

    def test_band_limits(self):
        self.assertEqual(vortex_ring_band_limits(10.5887)[1], 2 * 10.5887)

    def test_windmill_brake_anchor_and_identity(self):
        vh = 10.5887
        self.assertAlmostEqual(windmill_brake_induced_velocity(25.0, vh),
                               5.8570, places=3)
        # boundary identity v_i(2 v_h) = v_h
        self.assertAlmostEqual(windmill_brake_induced_velocity(2.0 * vh, vh),
                               vh, places=6)
        with self.assertRaises(ValueError):
            windmill_brake_induced_velocity(15.0, vh)  # band: momentum-invalid

    def test_signed_power_and_torque_anchors(self):
        thrust = 2200.0 * G0
        vh = 10.588725632796958
        vi25 = windmill_brake_induced_velocity(25.0, vh)
        self.assertAlmostEqual(rotor_descent_power(thrust, 25.0, vi25,
                                                   122935.0),
                               -352017.6, delta=1.0)
        vi30 = windmill_brake_induced_velocity(30.0, vh)
        p30 = rotor_descent_power(thrust, 30.0, vi30, 122935.0)
        self.assertAlmostEqual(p30, -512828.7, delta=1.0)
        self.assertAlmostEqual(rotor_descent_torque(p30, 44.0), -11655.2,
                               delta=1.0)
        # rotor absorbs power from the airstream across the band: P < 0
        vi40 = windmill_brake_induced_velocity(40.0, vh)
        self.assertLess(rotor_descent_power(thrust, 40.0, vi40, 122935.0),
                        0.0)

    def test_torque_reversal_unreachable(self):
        thrust = 2200.0 * G0
        vh = 10.588725632796958
        tr = torque_reversal_condition(122935.0, thrust, 1.15, vh)
        self.assertAlmostEqual(tr["c"], 4.9549, places=3)
        self.assertTrue(tr["c_less_than_vh"])   # 4.955 < 10.589
        self.assertIsNone(tr["momentum_root_Vd"])

    def test_descent_summary_keys(self):
        s = descent_summary(2200.0 * G0, 5.0, 122935.0, 25.0)
        self.assertEqual(set(s.keys()),
                         {"flow_state", "v_h", "band_limits",
                          "induced_velocity", "power_W", "torque_Nm",
                          "momentum_root_reachable"})
        self.assertEqual(s["flow_state"], "windmill-brake")
        self.assertIsNotNone(s["induced_velocity"])
        self.assertFalse(s["momentum_root_reachable"])


class TestBankedTurn(unittest.TestCase):
    """Rotorcraft H-1 anchors (turn-performance leaf worked case)."""

    def test_turn_power_anchor(self):
        bk = turn_power(2.0, 21574.63, 78.5398, 1.225, 60.0, 0.08, 0.012,
                        220.0, 2.2)
        self.assertAlmostEqual(bk["induced_power"], 185097.0, delta=1.0)
        self.assertAlmostEqual(bk["profile_power"], 122935.0, delta=1.0)
        self.assertAlmostEqual(bk["parasite_power"], 291060.0, delta=1.0)
        self.assertAlmostEqual(bk["total_power"], 599092.0, delta=1.0)
        # level-flight identity at n = 1
        level = turn_power(1.0, 21574.63, 78.5398, 1.225, 60.0, 0.08,
                           0.012, 220.0, 2.2)
        self.assertAlmostEqual(level["total_power"], 460336.0, delta=1.0)

    def test_generalized_induced_velocity_identity(self):
        # V = 0 returns sqrt(n) * v_h
        vi2 = generalized_induced_velocity(2.0, 21574.63, 78.5398, 1.225,
                                           0.0)
        vh = generalized_induced_velocity(1.0, 21574.63, 78.5398, 1.225,
                                          0.0)
        self.assertAlmostEqual(vi2, (2.0 ** 0.5) * vh, places=6)
        vi = generalized_induced_velocity(2.0, 21574.63, 78.5398, 1.225,
                                          60.0)
        self.assertAlmostEqual(vi, 3.73017, places=4)

    def test_sustained_load_factor_anchor(self):
        su = sustained_load_factor(600000.0, 21574.63, 78.5398, 1.225,
                                   60.0, 0.08, 0.012, 220.0, 2.2)
        self.assertAlmostEqual(su["load_factor"], 2.00491, places=4)
        self.assertEqual(su["note"], "power-limited")
        # power round trip: total at the sustained point = available power
        self.assertAlmostEqual(su["total_power"], 600000.0, delta=1.0)
        # cos(bank) = 1/n identity
        import math
        self.assertAlmostEqual(math.cos(su["bank_angle"]),
                               1.0 / su["load_factor"], places=9)

    def test_sustained_lower_at_higher_speed(self):
        hi = sustained_load_factor(450000.0, 21574.63, 78.5398, 1.225,
                                   40.0, 0.08, 0.012, 220.0, 2.2)
        lo = sustained_load_factor(450000.0, 21574.63, 78.5398, 1.225,
                                   50.0, 0.08, 0.012, 220.0, 2.2)
        self.assertGreater(hi["load_factor"], lo["load_factor"])

    def test_level_flight_floor(self):
        with self.assertRaises(ValueError):
            sustained_load_factor(100000.0, 21574.63, 78.5398, 1.225,
                                  60.0, 0.08, 0.012, 220.0, 2.2)

    def test_valueerror_rejections(self):
        with self.assertRaises(ValueError):
            turn_power(0.9, 21574.63, 78.5398, 1.225, 60.0, 0.08, 0.012,
                       220.0, 2.2)
        with self.assertRaises(ValueError):
            parasite_power(1.225, -5.0, 2.2)


class TestRangeEndurance(unittest.TestCase):
    """Rotorcraft H-4 anchors (range-endurance leaf worked case)."""

    def test_hover_power_terms(self):
        self.assertAlmostEqual(disk_area(8.0), 201.062, places=3)
        self.assertAlmostEqual(hover_power_constant(8.0), 0.0600746,
                               delta=1e-5)
        self.assertAlmostEqual(hover_power(60000.0, 8.0), 882912.0,
                               delta=10.0)
        self.assertAlmostEqual(fuel_flow(60000.0, 8.0), 0.0882912,
                               delta=1e-5)

    def test_hover_endurance_anchor(self):
        t = hover_endurance(60000.0, 1500.0, 8.0)
        self.assertAlmostEqual(t, 20927.3, delta=1.0)
        self.assertEqual(hover_endurance(60000.0, 0.0, 8.0), 0.0)

    def test_cruise_closure_anchors(self):
        curve = [(40.0, 620000.0), (50.0, 560000.0), (60.0, 540000.0),
                 (70.0, 555000.0), (80.0, 600000.0)]
        self.assertEqual(best_range_speed(curve), 80.0)
        self.assertEqual(best_endurance_speed(curve), 60.0)
        self.assertAlmostEqual(specific_range(60.0, 540000.0), 113.302,
                               delta=0.01)
        self.assertAlmostEqual(cruise_range(80.0, 60000.0, 1500.0,
                                            600000.0, 60000.0),
                               2433442.0, delta=100.0)
        self.assertAlmostEqual(cruise_endurance(60.0, 60000.0, 1500.0,
                                                540000.0, 60000.0),
                               33797.8, delta=10.0)

    def test_weight_scaling_reduces_power(self):
        # W1 = W0 - g0 * fuel stays positive and below W0
        w1 = 60000.0 - G0 * 1500.0
        self.assertAlmostEqual(w1, 45290.025, places=3)

    def test_valueerror_rejections(self):
        with self.assertRaises(ValueError):
            hover_endurance(60000.0, 7000.0, 8.0)   # fuel zeroes the weight
        with self.assertRaises(ValueError):
            specific_range(0.0, 540000.0)
        with self.assertRaises(ValueError):
            best_range_speed([])


class TestReportBuilder(unittest.TestCase):

    def test_example_model_anchors(self):
        model = build_performance_report(example_item())
        self.assertEqual(model["document_type"],
                         "Aircraft Performance Analysis Report")
        self.assertEqual(model["status"], "draft-for-review")
        # Airplane A-1: balanced V1 and field length
        self.assertAlmostEqual(model["bfl"]["v1_ms"], 77.2815, places=2)
        self.assertAlmostEqual(model["bfl"]["balanced_field_length_m"],
                               2138.10, places=1)
        # Airplane A-2: propeller range
        self.assertAlmostEqual(model["propeller"]["range_km"], 1472.24,
                               delta=0.01)
        # H-2 sizing
        self.assertAlmostEqual(model["sizing"]["disk_radius_m"], 6.3352,
                               places=3)
        self.assertAlmostEqual(model["sizing"]["thrust_coefficient"],
                               0.006479, delta=1e-6)
        # H-3 flap dynamics
        self.assertAlmostEqual(model["flap"]["lock_number"], 7.58079,
                               places=4)
        # H-1 lead-lag
        self.assertEqual(model["leadlag"]["verdict"], "resonance-adjacent")
        self.assertAlmostEqual(model["leadlag"]["coincidence_omega"],
                               43.6924, places=3)
        # H-1 hover IGE
        self.assertAlmostEqual(model["hover_ige"]["ige_total_power_W"],
                               369230.0, delta=1.0)
        self.assertTrue(3.9 <= model["hover_ige"]["max_hover_height"] <= 4.1)
        # H-1 descent: windmill-brake power at Vd = 25 negative
        case25 = [c for c in model["descent"]["cases"]
                  if c["vd_ms"] == 25.0][0]
        self.assertAlmostEqual(case25["power_W"], -352017.6, delta=1.0)
        # H-1 turn
        self.assertAlmostEqual(model["turn"]["breakdown"]["total_power"],
                               599092.0, delta=10.0)
        self.assertAlmostEqual(model["turn"]["sustained"]["load_factor"],
                               2.00491, places=3)
        # H-4 fuel closure
        self.assertAlmostEqual(model["fuel"]["hover_endurance_s"], 20927.3,
                               delta=1.0)
        self.assertAlmostEqual(model["fuel"]["cruise_range_m"], 2433442.0,
                               delta=100.0)
        self.assertAlmostEqual(model["fuel"]["cruise_endurance_s"], 33797.8,
                               delta=10.0)

    def test_markdown_sections_and_markers(self):
        md = example_report_markdown()
        for n in range(1, 11):
            self.assertIn("## %d. " % n, md, "section %d missing" % n)
        low = md.lower()
        self.assertIn("draft", low)
        self.assertIn("not an approval", low)

    def test_core_gates_all_pass(self):
        model = build_performance_report(example_item())
        gates = check_report(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_all_pass(self):
        gates = check_report_markdown(example_report_markdown())
        self.assertTrue(gates["all_pass"], gates)

    def test_tampered_model_fails_gate(self):
        model = build_performance_report(example_item())
        model["status"] = "approved-by-engineer"    # dishonest status
        gates = check_report(model)
        self.assertFalse(gates["sign_off_honest"])
        self.assertFalse(gates["all_pass"])

    def test_unbalanced_case_flips_gate(self):
        # a case with no balanced decision raises: honest failure, not a
        # fabricated balance (very strong brakes push the root past V_LOF)
        with self.assertRaises(ValueError):
            balanced_v1(150000.0, 2, 600000.0, 0.03, 0.8, 80.0, 0.024)

    def test_standalone_no_skills_repo(self):
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = build_performance_report(example_item())
        gates = check_report(model)
        self.assertTrue(gates["all_pass"], gates)
        md = render_report_markdown(model)
        self.assertGreater(len(md), 8000)


if __name__ == "__main__":
    unittest.main()
