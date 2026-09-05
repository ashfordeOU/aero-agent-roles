#!/usr/bin/env python3
"""Test high_speed_aero_core: the executable engine of the High-Speed
Aerodynamics role.

Proves the role can DO its job standalone (no AeroSkills checkout
needed): formula correctness against the same known anchors the bound
Aero Agent Skills leaves verify (isentropic ratios, Mach-area, normal
and oblique shocks, Prandtl-Meyer, Karman-Tsien, Korn rule, boundary
layer, heating, standoff), the memo builder, evidence gates, markdown
completeness, and STANDALONE mode.
"""
import math
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
import high_speed_aero_core as hs


class TestIsentropicAndMachArea(unittest.TestCase):
    """Anchors from the isentropic-flow-relations leaf contract tests."""

    def test_total_static_ratios_anchor_m2(self):
        r = hs.total_static_ratios(2.0)
        self.assertAlmostEqual(r["t0_over_t"], 1.8, delta=1e-9)
        self.assertAlmostEqual(r["p0_over_p"], 7.8244490669, delta=1e-9)
        self.assertAlmostEqual(r["rho0_over_rho"], 4.3469161483, delta=1e-9)
        sl = hs.total_static_ratios(0.0)
        self.assertEqual(sl["t0_over_t"], 1.0)

    def test_area_ratio_anchors(self):
        # A/A* at M2 = 1.6875 exactly (leaf test anchor)
        self.assertAlmostEqual(hs.area_ratio(2.0), 1.6875, delta=1e-12)
        self.assertAlmostEqual(hs.area_ratio(0.5), 1.33984375, delta=1e-12)
        self.assertEqual(hs.area_ratio(1.0), 1.0)
        # inverse on both branches round-trips (leaf anchors)
        self.assertAlmostEqual(hs.mach_from_area_ratio(1.6875, subsonic=False),
                               2.0, delta=1e-9)
        self.assertAlmostEqual(hs.mach_from_area_ratio(1.6875, subsonic=True),
                               0.372244486203, delta=1e-9)
        with self.assertRaises(ValueError):
            hs.area_ratio(0.0)

    def test_static_to_total_and_choked_flow(self):
        # leaf anchor: static 30000 Pa, 200 K, M 2 -> p0 ~ 234733
        tot = hs.static_to_total(30000.0, 200.0, 2.0)
        self.assertAlmostEqual(tot["p0"], 234733.472, delta=1e-2)
        # choked mass flow at the leaf anchor p0 1e5, T0 300, A* 0.01
        self.assertAlmostEqual(hs.choked_mass_flow(100000.0, 300.0, 0.01),
                               2.3335585606, delta=1e-8)


class TestCompressibilityCorrections(unittest.TestCase):
    """Anchors from the transonic-similarity leaf logic."""

    def test_pg_factor_and_kt_correction(self):
        self.assertAlmostEqual(hs.prandtl_glauert_factor(0.5),
                               1.0 / math.sqrt(0.75))
        # leaf anchor: Karman-Tsien at cp0 -0.6, M 0.5 -> -0.7265391
        self.assertAlmostEqual(hs.karman_tsien_correction(-0.6, 0.5),
                               -0.7265391210, delta=1e-9)
        with self.assertRaises(ValueError):
            hs.karman_tsien_correction(-0.6, 0.9)  # documented to M ~ 0.85

    def test_critical_pressure_and_mach(self):
        # Cp* at M 0.8134 is negative; critical Mach from Cp0 -0.55 ~ 0.702
        self.assertAlmostEqual(hs.critical_pressure_coefficient(0.8134),
                               -0.3969978925, delta=1e-9)
        self.assertAlmostEqual(hs.critical_mach_number(-0.55),
                               0.7017202167, delta=1e-6)
        with self.assertRaises(ValueError):
            hs.critical_mach_number(0.1)

    def test_transonic_similarity_and_sweep(self):
        k = hs.transonic_similarity_parameter(0.85, 0.03)
        self.assertAlmostEqual(k, (1 - 0.85 ** 2) / 0.03 ** (2.0 / 3.0))
        self.assertAlmostEqual(hs.effective_mach(0.85, 66.0),
                               0.85 * math.cos(math.radians(66.0)))
        with self.assertRaises(ValueError):
            hs.effective_mach(1.1, 45.0)  # subsonic only


class TestShockRelations(unittest.TestCase):
    """Anchors from the normal-shock and oblique-shock leaf tests."""

    def test_normal_shock_anchor_m2(self):
        # Anderson table A.2 anchor at M1 = 2: M2 0.5774, p2/p1 4.5 ...
        p = hs.normal_shock(2.0)
        self.assertAlmostEqual(p["m2"], 0.5773503, places=6)
        self.assertAlmostEqual(p["p2_p1"], 4.5, places=6)
        self.assertAlmostEqual(p["rho2_rho1"], 2.6666667, places=6)
        self.assertAlmostEqual(p["t2_t1"], 1.6875, places=6)
        self.assertAlmostEqual(p["p02_p01"], 0.7208739, places=6)
        with self.assertRaises(ValueError):
            hs.normal_shock(1.0)

    def test_oblique_shock_anchor(self):
        # Anderson example 4.2: M1 2, theta 10 deg -> weak beta 39.31,
        # M2 1.64, p2/p1 1.707 (leaf contract anchor)
        p = hs.oblique_shock(2.0, 10.0)
        self.assertAlmostEqual(p["beta_deg"], 39.31393, delta=1e-3)
        self.assertAlmostEqual(p["m2"], 1.64052, delta=1e-3)
        self.assertAlmostEqual(p["p2_p1"], 1.70658, delta=1e-3)
        self.assertAlmostEqual(p["p02_p01"], 0.984644, delta=1e-4)
        self.assertAlmostEqual(hs.deflection_limit(2.0), 22.9735, delta=1e-2)
        self.assertGreater(p["theta_max_deg"], 10.0)  # attached
        # detached above theta_max
        with self.assertRaises(ValueError):
            hs.oblique_shock(2.0, 40.0)

    def test_mach_angle_and_regular_reflection(self):
        self.assertAlmostEqual(hs.mach_angle(2.0), 30.0, delta=1e-9)
        v = hs.shock_reflection_verdict(2.0, 10.0)
        self.assertEqual(v["verdict"], "regular")   # leaf anchor
        v2 = hs.shock_reflection_verdict(hs.oblique_shock(2.0, 10.0)["m2"], 10.0)
        self.assertEqual(v2["verdict"], "mach")     # leaf anchor @ M2 1.64

    def test_prandtl_meyer(self):
        # nu(2.0) = 0.460414 rad = 26.3799 deg (leaf anchor, Anderson A.5)
        self.assertAlmostEqual(hs.prandtl_meyer_function(2.0),
                               0.4604136821, delta=1e-9)
        self.assertAlmostEqual(hs.prandtl_meyer_function(1.0), 0.0)
        # expansion from M 1.64 through 10 deg -> ~ M 1.988 (leaf anchor)
        exp = hs.expansion_properties(1.6405222, 10.0)
        self.assertAlmostEqual(exp["m2"], 1.987794, delta=1e-3)
        self.assertLess(exp["pressure_ratio_p2_p1"], 1.0)  # expansion drops p

    def test_shock_expansion_airfoil_anchor(self):
        # diamond airfoil M2, alpha 2, eps 2 (shock-expansion-airfoil leaf)
        r = hs.shock_expansion_airfoil(2.0, 2.0, 2.0)
        self.assertAlmostEqual(r["cl"], 0.0808190, delta=1e-4)
        self.assertAlmostEqual(r["cd_wave"], 0.0056500, delta=1e-4)
        self.assertAlmostEqual(r["cm_le"], 0.0386972, delta=1e-4)
        self.assertGreater(r["cd_wave"], 0.0)


class TestTransonicAndWaveDrag(unittest.TestCase):
    """Anchors from supercritical-airfoil and wave-drag-area-rule leaves."""

    def test_korn_and_terminating_shock(self):
        self.assertAlmostEqual(hs.drag_divergence_mach(0.03, 0.12, True),
                               0.95 - 0.03 - 0.012)
        self.assertAlmostEqual(hs.drag_divergence_mach(0.035, 0.12, False),
                               0.90 - 0.035 - 0.012)
        # terminating shock strength: p2/p1 at local M 1.3 = 1.805,
        # at 1.15 = 1.37625 (leaf anchors)
        self.assertAlmostEqual(hs.terminating_shock_strength(1.3), 1.805)
        self.assertAlmostEqual(hs.terminating_shock_strength(1.15),
                               1.37625, delta=1e-9)

    def test_wave_drag_penalty_and_sears_haack(self):
        # penalty index zero below M_DD, (M-M_DD)^3 above (supercritical leaf)
        self.assertEqual(hs.wave_drag_penalty(0.85, 0.908), 0.0)
        self.assertAlmostEqual(hs.wave_drag_penalty(0.95, 0.853),
                               0.097 ** 3, delta=1e-9)
        # Sears-Haack zero-lift wave drag area (area-rule leaf anchor):
        # D/q for L=62, r_max=1.6 -> 0.2378804 m2
        self.assertAlmostEqual(hs.sears_haack_wave_drag_area(62.0, 1.6),
                               0.2378804128, delta=1e-6)
        # parabolic rise above M_DD: k (M-M_DD)^2
        self.assertAlmostEqual(hs.wave_drag_rise_coef(0.95, 0.853, k=20.0),
                               0.18818, delta=1e-6)


class TestBoundaryLayerAndHeating(unittest.TestCase):
    """Anchors from the boundary-layer and heating leaf logic."""

    def test_flat_plate_thicknesses_laminar(self):
        # Blasius at Re 1e5, x=1: delta 5/sqrt(1e5) = 0.0158 m
        bl = hs.flat_plate_thicknesses(1.0, 1e5)
        self.assertEqual(bl["regime"], "laminar")
        self.assertAlmostEqual(bl["delta"], 5.0 / math.sqrt(1e5))
        self.assertAlmostEqual(bl["delta_star"],
                               1.7208 / math.sqrt(1e5))
        self.assertAlmostEqual(bl["cf_local"], 0.664 / math.sqrt(1e5))
        self.assertAlmostEqual(bl["shape_factor"], 1.7208 / 0.664)

    def test_flat_plate_thicknesses_turbulent_and_loglaw(self):
        # 1/7-power turbulent at Re 2.866e7, x=6 m (cruise-state anchor)
        bl = hs.flat_plate_thicknesses(6.0, 2.866e7)
        self.assertEqual(bl["regime"], "turbulent")
        self.assertAlmostEqual(bl["delta"], 0.37 * 6.0 / (2.866e7) ** 0.2,
                               delta=1e-4)
        self.assertAlmostEqual(bl["shape_factor"], 9.0 / 7.0)
        self.assertAlmostEqual(hs.cf_turbulent_log_law(1e7),
                               0.455 / (7.0 ** 2.58), delta=1e-9)

    def test_transition_and_roughness(self):
        # flat-plate natural transition at the cruise state ~0.349 m
        x_tr = hs.flat_plate_transition(1.236e-4, 590.0, 6.0)
        self.assertIsNotNone(x_tr)
        self.assertAlmostEqual(x_tr, 0.3489, delta=1e-2)
        # roughness: k+ 0.887 is smooth
        self.assertEqual(hs.roughness_regime(0.887), "smooth")
        self.assertEqual(hs.roughness_regime(20.0), "transitional")
        self.assertEqual(hs.roughness_regime(100.0), "fully-rough")

    def test_stagnation_flow_layer(self):
        a = hs.stagnation_velocity_gradient("cylinder", 590.0, 0.05)
        self.assertAlmostEqual(a, 2.0 * 590.0 / 0.05)
        self.assertAlmostEqual(hs.stagnation_bl_thickness(1.236e-4, a),
                               2.4 * math.sqrt(1.236e-4 / a), delta=1e-6)

    def test_heating_and_standoff(self):
        # Sutton-Graves: q at the cruise nose state ~5.7e4 W/m2 (leaf run)
        q = hs.stagnation_heat_flux(0.115, 590.0, 0.05)
        self.assertAlmostEqual(q, 56999.5, delta=1.0)
        t = hs.radiation_equilibrium_temp(q)
        self.assertAlmostEqual(t, 1042.82, delta=0.5)
        # recovery factor turbulent Pr^(1/3), laminar sqrt(Pr)
        self.assertAlmostEqual(hs.recovery_factor("turbulent"),
                               0.71 ** (1.0 / 3.0))
        self.assertAlmostEqual(hs.recovery_factor("laminar"),
                               math.sqrt(0.71))
        # adiabatic wall temp at M2, 216.65 K -> 371.27 K (leaf anchor)
        self.assertAlmostEqual(hs.adiabatic_wall_temperature(2.0, 216.65,
                                                             "turbulent"),
                               371.2709, delta=1e-3)
        # Billig sphere standoff at M2: Delta/R = 0.32145
        self.assertAlmostEqual(hs.bow_shock_standoff_ratio(2.0, "sphere"),
                               0.143 * math.exp(3.24 / 4.0), delta=1e-9)


class TestMemoBuilderAndGates(unittest.TestCase):

    def test_example_memo_numbers(self):
        model = hs.build_memo(hs.example_item())
        # isentropic anchor at M2.0: A/A* = 1.6875 exactly
        self.assertAlmostEqual(model["area_ratio"], 1.6875, delta=1e-9)
        # normal-shock anchor at the cruise Mach: recovery ~0.721
        self.assertAlmostEqual(model["shocks"]["normal"]["p02_p01"],
                               0.720874, delta=1e-4)
        # two-shock intake recovery beats a single normal shock
        self.assertGreater(model["shocks"]["recovery_total"],
                           model["shocks"]["recovery_single"])
        # supersonic cruise with a subsonic leading edge (sweep 66 deg)
        self.assertLess(model["corrections"]["m_eff_cruise"], 1.0)
        # drag-divergence margin positive at the cruise effective Mach
        self.assertGreater(model["corrections"]["m_dd"],
                           model["corrections"]["m_eff_cruise"])
        # boundary layer real at the cruise station
        self.assertGreater(model["bl"]["re"], 1e6)
        self.assertGreater(model["bl"]["flat_plate"]["delta"], 0.0)

    def test_core_gates_all_pass(self):
        model = hs.build_memo(hs.example_item())
        gates = hs.check_memo(model)
        self.assertTrue(gates["all_pass"], gates)
        self.assertGreaterEqual(len(model["margins"]), 4)
        for m in model["margins"]:
            self.assertIn("stage ", m["source"])
            self.assertGreater(m["value"], 0.0)

    def test_memo_markdown_complete_and_no_blanks(self):
        md = hs.example_memo_markdown()
        for n in range(1, 9):
            self.assertTrue(re.search(rf"^## {n}\. ", md, re.M),
                            "section %d missing" % n)
        for banned in ["___", "TBD", "OPEN item"]:
            self.assertNotIn(banned, md)
        self.assertIn("DRAFT", md)
        self.assertIn("not an approval", md.lower())
        self.assertIn("HSX-1", md)
        self.assertGreater(len(md), 3000)
        gates = hs.check_memo_markdown(md)
        self.assertTrue(gates["all_pass"], gates)

    def test_standalone_no_skills_repo(self):
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = hs.build_memo(hs.example_item())
        md = hs.render_memo_markdown(model)
        self.assertTrue(hs.check_memo(model)["all_pass"])
        self.assertGreater(len(md), 3000)


if __name__ == "__main__":
    unittest.main()
