#!/usr/bin/env python3
"""Test structures_loads_core: the executable engine of the Structures
and Loads Engineer role.

Proves the role can DO its job standalone (no AeroSkills needed): FAR 25
gust + maneuver envelope, limit/ultimate loads, root internal loads,
margins of safety per component, fatigue screening (S-N basis + Miner),
dynamics, evidence gates, and the worked-example report. Anchor values
are taken from the bound AeroSkills leaves' own behavior contracts
(gust load factor ~2.3-2.4 band at VB, lug margins +1.800/+1.135/+0.926
governing tearout, Basquin life 1.69e5 cycles at S=300/A=1000/b=-0.1).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from structures_loads_core import (
    CANTILEVER_BETA1_L, MATERIALS, NEGATIVE_MANEUVER_LIMIT,
    basquin_life, build_report, cantilever_frequency_hz, check_report,
    check_report_markdown, column_check, cumulative_damage,
    design_limit_load_factor, effective_length_factor, envelope_margins,
    euler_buckling_load, example_item, example_report_markdown,
    far25_gust_velocity, goodman_effective_amplitude, gust_alleviation_factor,
    gust_load_factor, gust_mass_ratio, level_landing_reactions,
    lug_analysis, maneuver_limit_load_factor, margin_of_safety,
    plate_buckling_stress, render_report_markdown, shear_buckling_stress,
    vn_diagram,
)

KSI_MPA = 6.894757


class TestGustManeuverDomain(unittest.TestCase):
    """Domain rules mirroring the bound gust-maneuver-loads leaf."""

    def test_far25_gust_velocities(self):
        self.assertAlmostEqual(far25_gust_velocity("vb-vc", 0.0), 66.0)
        self.assertAlmostEqual(far25_gust_velocity("vc", 0.0), 50.0)
        self.assertAlmostEqual(far25_gust_velocity("vd", 0.0), 25.0)
        self.assertAlmostEqual(far25_gust_velocity("vc", 15000.0), 25.0)
        self.assertAlmostEqual(far25_gust_velocity("vd", 50000.0), 12.5)

    def test_alleviation_anchor(self):
        # Transport anchor: W/S=100 psf, cbar=11.18 ft, a=5.7 -> mu_g ~41,
        # K_g ~0.78 (same band as the leaf's cbar=12.5 anchor of 36.7/0.769).
        mu = gust_mass_ratio(100.0, 11.18, 5.7)
        kg = gust_alleviation_factor(100.0, 11.18, 5.7)
        self.assertAlmostEqual(mu, 41.02, delta=0.5)
        self.assertAlmostEqual(kg, 0.779, delta=0.02)
        self.assertLess(kg, 0.88)

    def test_gust_load_factor_band(self):
        # 66 fps design gust at VB on the example wing: n in the 2.3-2.5 band.
        n = gust_load_factor(414.0, 100.0, 5.7, 66.0, cbar=11.18)
        self.assertGreater(n, 2.3)
        self.assertLess(n, 2.6)
        vn = vn_diagram(100.0, 230.0, 621.0, 5.7, 11.18,
                        weight_lb=100_000.0)
        n_vb = [p["n_pos"] for p in vn["gust_points"] if p["speed"] == "VB"][0]
        self.assertAlmostEqual(n_vb, n, delta=0.01)

    def test_maneuver_factor_far337(self):
        # FAR 25.337(b): n = max(2.5, min(3.8, 2.1+24000/(W+10000))).
        self.assertAlmostEqual(maneuver_limit_load_factor(100_000.0,
                                                          "transport"), 2.5)
        self.assertAlmostEqual(maneuver_limit_load_factor(3_000.0,
                                                          "transport"), 3.8)
        self.assertEqual(maneuver_limit_load_factor(50_000.0, "normal"), 2.5)
        self.assertEqual(maneuver_limit_load_factor(50_000.0, "commuter"), 3.8)
        self.assertEqual(maneuver_limit_load_factor(50_000.0, "transport",
                                                    negative=True),
                         NEGATIVE_MANEUVER_LIMIT)

    def test_vn_speed_ordering_and_corner(self):
        vn = vn_diagram(100.0, 230.0, 621.0, 5.7, 11.18,
                        weight_lb=100_000.0)
        self.assertTrue(vn["vs"] < vn["va"] < vn["vb"] < vn["vc"] < vn["vd"])
        import math
        self.assertAlmostEqual(vn["va"], 230.0 * math.sqrt(2.5), places=3)
        self.assertEqual(len(vn["gust_points"]), 3)

    def test_design_limit_and_gust_critical(self):
        vn = vn_diagram(100.0, 230.0, 621.0, 5.7, 11.18,
                        weight_lb=100_000.0)
        design = design_limit_load_factor(vn)
        self.assertAlmostEqual(design["n_limit_pos"], 2.5)
        em = envelope_margins(vn)
        # gust-criticality is checked at least somewhere on the envelope
        self.assertTrue(any(v["gust_critical_pos"] or v["gust_critical_neg"]
                            for v in em.values())
                        or all(v["margin_pos"] >= 0 for v in em.values()))


class TestStrengthDomain(unittest.TestCase):
    """Strength rules mirroring the bound buckling / plate-buckling /
    lug-joint leaves."""

    def test_margin_of_safety(self):
        self.assertEqual(margin_of_safety(100.0, 80.0), 0.25)
        self.assertEqual(margin_of_safety(100.0, 100.0), 0.0)
        self.assertEqual(margin_of_safety(100.0, 200.0), -0.5)
        with self.assertRaises(ValueError):
            margin_of_safety(0.0, 1.0)

    def test_euler_anchor(self):
        # Euler scaling anchor: doubling K quarters Pcr (leaf behavior).
        pcr2 = euler_buckling_load(29_000.0, 0.6, 22.0)
        pcr_half = euler_buckling_load(29_000.0, 0.6, 22.0, "fixed-free")
        self.assertAlmostEqual(pcr_half / pcr2, 0.25, places=4)

    def test_end_conditions(self):
        self.assertEqual(effective_length_factor("pinned-pinned"), 1.0)
        self.assertEqual(effective_length_factor("fixed-fixed"), 0.5)
        self.assertEqual(effective_length_factor("fixed-pinned"), 0.7)
        self.assertEqual(effective_length_factor("cantilever"), 2.0)

    def test_column_check_transition(self):
        # Stocky column: yield-governed; slender column: Euler-governed.
        stocky = column_check(10_400.0, 0.60, 1.2, 8.0, "pinned-pinned",
                              40_000.0, 73.0)
        self.assertFalse(stocky["euler_governs"])
        slender = column_check(10_400.0, 0.60, 1.2, 60.0, "pinned-pinned",
                              40_000.0, 73.0)
        self.assertTrue(slender["euler_governs"])

    def test_plate_buckling(self):
        # k=4 long plate anchor: E=10,400 ksi, nu=0.33, t=0.25, b=6
        # -> sigma_cr ~ 66.7 ksi (matches the worked example wing panel).
        sig = plate_buckling_stress(10_400.0, 0.33, 0.25, 6.0, k=4.0)
        self.assertAlmostEqual(sig, 66.7, delta=1.0)
        # clamped long plate k=6.97 is stiffer than ssss k=4
        sig_c = plate_buckling_stress(10_400.0, 0.33, 0.25, 6.0, k=6.97)
        self.assertGreater(sig_c, sig)

    def test_lug_worked_example_anchor(self):
        # Bound lug leaf worked example, converted to US customary:
        # 7075-T6 D=20mm,t=12mm,e=24mm,w=48mm,P=90kN with Ftu=572,
        # Fsu=331, Fbru=1050 MPa -> margins +1.800/+1.135/+0.926, tearout
        # governs, passes.
        d_in = 20.0 / 25.4
        t_in = 12.0 / 25.4
        e_in = 24.0 / 25.4
        w_in = 48.0 / 25.4
        p_lb = 90_000.0 / 4.448222
        lug = lug_analysis(p_lb, d_in, t_in, w_in, e_in,
                           572.0 / KSI_MPA, 331.0 / KSI_MPA,
                           1050.0 / KSI_MPA)
        self.assertAlmostEqual(lug["bearing_margin"], 1.800, delta=0.02)
        self.assertAlmostEqual(lug["net_tension_margin"], 1.135, delta=0.02)
        self.assertAlmostEqual(lug["tearout_margin"], 0.926, delta=0.02)
        self.assertEqual(lug["governing_mode"], "tearout")
        self.assertTrue(lug["passes"])


class TestFatigueDomain(unittest.TestCase):
    """Fatigue rules mirroring the bound stress-life / goodman / miner
    leaves."""

    def test_basquin_anchor(self):
        # stress-life leaf anchor: A=1000, b=-0.1, S=300 -> N ~1.69e5.
        n = basquin_life(300.0, 1000.0, -0.1)
        self.assertAlmostEqual(n, 1.6935e5, delta=0.05e5)

    def test_goodman_effective_amplitude(self):
        self.assertAlmostEqual(goodman_effective_amplitude(10.0, 0.0, 83.0),
                               10.0)
        # A tensile mean stress raises the equivalent fully-reversed
        # amplitude (same damage at zero mean needs a bigger amplitude).
        self.assertLess(goodman_effective_amplitude(10.0, 0.0, 83.0),
                        goodman_effective_amplitude(10.0, 30.0, 83.0))
        self.assertAlmostEqual(goodman_effective_amplitude(10.0, 30.0, 83.0),
                               10.0 / (1.0 - 30.0 / 83.0), places=6)
        with self.assertRaises(ValueError):
            goodman_effective_amplitude(10.0, 90.0, 83.0)

    def test_miner_sum(self):
        self.assertEqual(cumulative_damage([(100, 200)]), 0.5)
        d = cumulative_damage([(500, 1000), (300, 600)])
        self.assertEqual(d, 1.0)
        with self.assertRaises(ValueError):
            cumulative_damage([])
        with self.assertRaises(ValueError):
            cumulative_damage([(10, 0)])

    def test_fatigue_report_fields(self):
        model = build_report(example_item())
        f = model["fatigue"]
        self.assertIn("damage_per_flight", f)
        self.assertGreater(f["damage_per_flight"], 0.0)
        self.assertLess(f["damage_per_flight"], 1.0)
        self.assertTrue(f["gust_blocks"])


class TestBuilderAndGates(unittest.TestCase):

    def test_example_report_model(self):
        model = build_report(example_item())
        self.assertEqual(model["document_type"], "Loads and Strength Report")
        self.assertEqual(model["status"], "draft-for-review")
        self.assertGreaterEqual(len(model["margins"]), 5)
        # the example wing must pass: every margin of safety >= 0
        for m in model["margins"]:
            self.assertGreaterEqual(m["MS"], 0.0,
                                    "example margin negative: %s" % m)
            for key in ("component", "load", "allowable", "basis"):
                self.assertTrue(m[key], "missing %s in margin row" % key)

    def test_ground_loads(self):
        g = level_landing_reactions(100_000.0, 18.0, 6.0, 2.5)
        self.assertAlmostEqual(g["total_lb"], 250_000.0, places=1)

    def test_dynamics_frequency_sane(self):
        model = build_report(example_item())
        # regional transport wing first bending: ~1-4 Hz
        self.assertGreater(model["dynamics_f1_hz"], 1.0)
        self.assertLess(model["dynamics_f1_hz"], 4.0)
        self.assertAlmostEqual(CANTILEVER_BETA1_L, 1.87510407, places=5)

    def test_core_gates_all_pass(self):
        model = build_report(example_item())
        gates = check_report(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_all_pass(self):
        md = example_report_markdown()
        gates = check_report_markdown(md)
        self.assertTrue(gates["all_pass"], gates)

    def test_rendered_report_structure(self):
        md = example_report_markdown()
        for sec in ["## 1. Loads", "## 3. Strength/stability margins",
                    "## 6. Fatigue", "## 9. Margin summary"]:
            self.assertIn(sec, md)
        self.assertIn("not an approval", md.lower())
        # no template blanks left in the worked example
        self.assertNotIn("___", md)

    def test_standalone_no_skills_repo(self):
        # Core must work with no AeroSkills present.
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = build_report(example_item())
        self.assertGreaterEqual(len(model["margins"]), 5)
        md = render_report_markdown(model)
        self.assertGreater(len(md), 2000)
        self.assertTrue(check_report(model)["all_pass"])
        self.assertTrue(check_report_markdown(md)["all_pass"])

    def test_material_allowables_grounded(self):
        # The allowables used in the example report must be the leaf
        # anchors (572/503/331/1050 MPa -> 83.0/73.0/48.0/152.3 ksi).
        mat = MATERIALS["al-7075-t6"]
        self.assertAlmostEqual(mat["Ftu_ksi"], 572.0 / KSI_MPA, places=2)
        self.assertAlmostEqual(mat["Fty_ksi"], 503.0 / KSI_MPA, places=2)
        self.assertAlmostEqual(mat["Fsu_ksi"], 331.0 / KSI_MPA, places=2)
        self.assertAlmostEqual(mat["Fbru_ksi"], 1050.0 / KSI_MPA, places=2)


if __name__ == "__main__":
    unittest.main()
