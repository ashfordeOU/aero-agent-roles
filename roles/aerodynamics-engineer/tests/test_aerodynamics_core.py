#!/usr/bin/env python3
"""Test aerodynamics_core: the executable engine of the Aerodynamics role.

Proves the role can DO its job standalone (no AeroSkills checkout needed):
formula correctness against known values (the same anchors used by the
bound Aero Agent Skills leaves), ISA atmosphere, drag buildup, drag polar,
lift curve slope, high lift, transonic limits, aeroelastic margins, CFD
validation metrics, report generation, and evidence-gate checks.
"""
import math
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))
import aerodynamics_core as ac


class TestFormulaKnownValues(unittest.TestCase):
    """Formula anchors from the bound AeroSkills leaf contract tests."""

    def test_reynolds_and_skin_friction_anchors(self):
        # Re = rho*V*L/mu: sea-level air, V = 70 m/s, length 2.5 m
        # (parasite-drag leaf test).
        self.assertAlmostEqual(ac.reynolds(1.225, 70.0, 2.5, 1.7894e-5),
                               11980272.717, delta=1.0)
        with self.assertRaises(ValueError):
            ac.reynolds(0.0, 70.0, 2.5, 1.7894e-5)
        # Blasius, Schlichting and the mixed transition formula (leaf tests).
        self.assertAlmostEqual(ac.cf_laminar(1e5), 0.0041995047, delta=1e-9)
        self.assertAlmostEqual(ac.cf_turbulent(1e7), 0.0030037131, delta=1e-9)
        self.assertAlmostEqual(ac.cf_mixed(1e7, 5e5), 0.0028423311, delta=1e-9)
        with self.assertRaises(ValueError):
            ac.cf_turbulent(5.0)

    def test_form_factor_and_component_drag_anchors(self):
        # FF wing = 1 + 2(t/c) + 100(t/c)^4, fuselage/nacelle l/d forms.
        self.assertAlmostEqual(ac.form_factor("wing", t_over_c=0.12), 1.260736)
        self.assertAlmostEqual(ac.form_factor("tail", t_over_c=0.10), 1.21)
        self.assertAlmostEqual(ac.form_factor("fuselage", l_over_d=8.0), 1.1371875)
        self.assertAlmostEqual(ac.form_factor("nacelle", l_over_d=3.0),
                               1.1166666667, delta=1e-9)
        # CD_i = Cf * FF * Q * S_wet / S_ref (leaf test value).
        self.assertAlmostEqual(ac.component_drag(0.003, 1.26, 1.1, 50.0, 20.0),
                               0.010395)
        # assembled buildup: total Cd0 is the sum of the component terms
        buildup = ac.parasite_drag(
            [{"name": "wing", "kind": "wing", "length": 2.5, "s_wet": 218.5,
              "t_over_c": 0.105, "q": 1.0},
             {"name": "fuselage", "kind": "fuselage", "length": 37.6,
              "s_wet": 401.0, "l_over_d": 9.5, "q": 1.0}],
            s_ref=122.6, rho=1.225, v=70.0, mu=1.7894e-5)
        self.assertEqual(len(buildup["components"]), 2)
        self.assertAlmostEqual(buildup["cd0"],
                               sum(r["cd"] for r in buildup["components"]))
        self.assertGreater(buildup["cd0"], 0.0)

    def test_drag_polar_and_lift_slope_formulas(self):
        # k = 1/(pi*e*AR) with e = 0.8, AR = 8; CD = Cd0 + k*CL^2
        e, ar, cd0 = 0.8, 8.0, 0.01564
        k = 1.0 / (math.pi * e * ar)
        self.assertAlmostEqual(ac.induced_drag_factor(e, ar), k)
        cl = 0.5
        polar = ac.drag_polar(cd0, e, ar, cl)
        self.assertAlmostEqual(polar["cd"], cd0 + k * cl * cl)
        # cl_opt = sqrt(cd0/k), L/D_max = 1/(2*sqrt(cd0*k))
        self.assertAlmostEqual(polar["cl_opt"], math.sqrt(cd0 / k))
        self.assertAlmostEqual(polar["ld_max"], 1.0 / (2.0 * math.sqrt(cd0 * k)))
        self.assertAlmostEqual(polar["l_over_d"], cl / (cd0 + k * cl * cl))
        # lifting line with a0 = 2*pi and e = 1 reduces to a = a0*AR/(AR+2)
        slope = ac.lift_curve_slope(8.0, e=1.0, sweep_deg=0.0, mach=0.0)
        self.assertAlmostEqual(slope["a_finite"], 2 * math.pi * 8.0 / 10.0)
        # simple sweep theory: a_swept = a * cos(sweep)
        self.assertAlmostEqual(slope["a_finite"] * math.cos(math.radians(25.0)),
                               ac.lift_curve_slope(8.0, e=1.0,
                                                   sweep_deg=25.0)["a_swept"])
        # Prandtl-Glauert: a_mach = a / sqrt(1 - M^2), valid M < 0.7
        base = ac.lift_curve_slope(8.0, e=1.0, sweep_deg=25.0, mach=0.0)
        pg = ac.lift_curve_slope(8.0, e=1.0, sweep_deg=25.0, mach=0.5)
        self.assertAlmostEqual(pg["a_mach"], base["a_swept"] / math.sqrt(0.75))
        with self.assertRaises(ValueError):
            ac.lift_curve_slope(8.0, mach=0.8)  # P-G valid only M < 0.7

    def test_flutter_and_divergence_margins(self):
        # Classic typical-section anchors (flutter-speed leaf tests):
        # V_F = 88.8511 m/s.
        margin, ok = ac.flutter_margin(88.8511, 80.0)
        self.assertAlmostEqual(margin, 1.1106, delta=1e-3)
        self.assertFalse(ok)
        margin, ok = ac.flutter_margin(88.8511, 70.0)
        self.assertAlmostEqual(margin, 1.2693, delta=1e-3)
        self.assertTrue(ok)
        # Divergence: 40000/(16*2*5.0*0.2) = 1250 Pa exactly (divergence leaf)
        q = ac.divergence_dynamic_pressure(40000.0, 16.0, 2.0, 5.0, 0.2)
        self.assertAlmostEqual(q, 1250.0)
        self.assertAlmostEqual(ac.divergence_speed(q), 45.1754, delta=1e-3)
        with self.assertRaises(ValueError):
            ac.divergence_dynamic_pressure(40000.0, 16.0, 2.0, 5.0, 0.0)

    def test_high_lift_formulas(self):
        # Slotted flap at full deflection: reference increment 1.3 at the
        # reference flap chord fraction and full span.
        self.assertAlmostEqual(ac.flap_clmax_increment("slotted", 40.0), 1.3)
        # partial deflection scales with sin(delta)/sin(delta_max)
        inc_20 = ac.flap_clmax_increment("slotted", 20.0)
        self.assertAlmostEqual(inc_20, 1.3 * math.sin(math.radians(20.0))
                               / math.sin(math.radians(40.0)))
        # wing CLmax = 0.9 * clmax_section * cos(sweep)
        self.assertAlmostEqual(ac.wing_clmax(1.55, 25.0),
                               0.9 * 1.55 * math.cos(math.radians(25.0)))
        # stall speed sqrt(2W/(rho*S*CLmax)) - clean config ~88 m/s example
        vs = ac.stall_speed(735000.0, 122.6, 1.225,
                            ac.wing_clmax(1.55, 25.0))
        self.assertAlmostEqual(vs, 88.0, delta=1.5)

    def test_transonic_rules(self):
        # Korn rule: M_DD = 0.95 - t/c - CL/10 (supercritical base)
        self.assertAlmostEqual(ac.drag_divergence_mach(0.105, 0.5, True),
                               0.95 - 0.105 - 0.05)
        # conventional section uses the 0.90 base
        self.assertAlmostEqual(ac.drag_divergence_mach(0.105, 0.5, False),
                               0.90 - 0.105 - 0.05)
        # wave drag penalty: 0 below M_DD, (M - M_DD)^3 above
        self.assertEqual(ac.wave_drag_penalty(0.78, 0.795), 0.0)
        self.assertAlmostEqual(ac.wave_drag_penalty(0.84, 0.795), 0.045 ** 3)
        # effective Mach M*cos(sweep)
        self.assertAlmostEqual(ac.effective_mach(0.78, 25.0),
                               0.78 * math.cos(math.radians(25.0)))

    def test_cfd_validation_metrics(self):
        # Richardson on the example mesh series [fine, medium, coarse]
        rich = ac.richardson_extrapolation([0.02840, 0.02910, 0.03060], 2.0)
        p = math.log(0.0015 / 0.0007) / math.log(2.0)
        self.assertAlmostEqual(rich["apparent_order"], p)
        denom = 2.0 ** p - 1.0
        self.assertAlmostEqual(rich["extrapolated"], 0.02840 - 0.0007 / denom)
        self.assertAlmostEqual(rich["gci"], 1.25 * 0.0007 / denom)
        self.assertTrue(rich["monotone"])
        # validation verdict PASS inside the 5% band, FAIL outside
        v = ac.validation_verdict(0.0169, 0.0163)
        self.assertEqual(v["verdict"], "PASS")
        self.assertAlmostEqual(v["error"], 0.0006 / 0.0163)
        v2 = ac.validation_verdict(0.0185, 0.0163)
        self.assertEqual(v2["verdict"], "FAIL")
        with self.assertRaises(ValueError):
            ac.richardson_extrapolation([0.03, 0.02, 0.03])  # non-monotone


class TestIsaAtmosphere(unittest.TestCase):

    def test_isa_sea_level_and_cruise(self):
        sl = ac.atmosphere(0.0)
        self.assertAlmostEqual(sl["density"], 1.225, delta=1e-3)
        self.assertAlmostEqual(sl["pressure"], 101325.0, delta=5.0)
        self.assertAlmostEqual(sl["speed_of_sound"], 340.29, delta=0.2)
        # cruise at 10668 m (FL 350): rho ~0.38, a ~296.5 (used by the report)
        cr = ac.atmosphere(10668.0)
        self.assertAlmostEqual(cr["density"], 0.3796, delta=0.005)
        self.assertAlmostEqual(cr["speed_of_sound"], 296.5, delta=0.5)
        with self.assertRaises(ValueError):
            ac.atmosphere(-5.0)


class TestReportBuilder(unittest.TestCase):

    def test_example_report_numbers(self):
        model = ac.build_report(ac.example_item())
        # cruise CL ~0.50 at M 0.78/FL350 with W_cruise/S = 622000/122.6
        self.assertAlmostEqual(model["cl_cruise"], 0.5, delta=1e-2)
        self.assertAlmostEqual(model["span"], math.sqrt(8.0 * 122.6), delta=1e-6)
        self.assertAlmostEqual(model["mac"], 122.6 / math.sqrt(8.0 * 122.6),
                               delta=1e-6)
        # polar consistency: CD = Cd0 + k*CL^2 with k = 1/(pi*e*AR)
        expected_cd = (model["cd0"]
                       + model["cl_cruise"] ** 2
                       / (math.pi * model["oswald_e"] * model["aspect_ratio"]))
        self.assertAlmostEqual(model["cd_cruise"], expected_cd, delta=1e-6)
        self.assertGreater(model["ld_max"], model["ld_cruise"])
        # transonic: cruise below Korn M_DD, penalty zero
        self.assertGreater(model["m_dd"], model["cruise_mach"])
        self.assertEqual(model["wave_drag_penalty"], 0.0)
        # high lift: landing CLmax above clean; stall speeds ordered
        hl = model["high_lift"]
        self.assertGreater(hl["clmax_wing_land"], hl["clmax_wing_clean"])
        self.assertLess(hl["vs_land"], hl["vs_to"])
        self.assertLess(hl["vs_to"], hl["vs_clean"])

    def test_core_gates_all_pass(self):
        model = ac.build_report(ac.example_item())
        gates = ac.check_report(model)
        self.assertTrue(gates["all_pass"], gates)
        self.assertTrue(model["flutter_ok"])
        self.assertGreaterEqual(model["flutter_margin"], 1.15)
        self.assertGreaterEqual(len(model["margins"]), 4)
        # every margin names its workflow-stage source
        for m in model["margins"]:
            self.assertIn("stage ", m["source"])

    def test_report_markdown_complete_gates_and_no_blanks(self):
        md = ac.example_report_markdown()
        for n in range(1, 9):
            self.assertTrue(re.search(rf"^## {n}\. ", md, re.M),
                            "section %d missing" % n)
        for banned in ["___", "TBD", "OPEN item"]:
            self.assertNotIn(banned, md)
        self.assertIn("DRAFT", md)
        self.assertIn("not an approval", md.lower())
        self.assertIn("Flutter margin", md)
        self.assertIn("Drag-divergence Mach", md)
        self.assertGreater(len(md), 3000)
        gates = ac.check_report_markdown(md)
        self.assertTrue(gates["all_pass"], gates)
        self.assertTrue(gates["has_no_blanks"])

    def test_standalone_no_skills_repo(self):
        # Core must work with no AeroSkills present: env points nowhere.
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = ac.build_report(ac.example_item())
        md = ac.render_report_markdown(model)
        self.assertTrue(ac.check_report(model)["all_pass"])
        self.assertGreater(len(md), 3000)
        self.assertIn("TAC-150", md)


if __name__ == "__main__":
    unittest.main()
