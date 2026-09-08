#!/usr/bin/env python3
"""Test boundary_layer_engineer_core: the executable engine of the
Boundary-Layer Engineer role.

Proves the role can DO its job standalone (no AeroSkills needed):
laminar growth and Michel-criterion transition, Squire-Young profile
drag against the Blasius flat-plate reduction, the Mangler
axisymmetric transform, laminar far-wake drag, rough-wall skin
friction, stagnation-point flow, Stokes creeping-flow drag, the
unsteady laminar Stokes layer, report generation, and evidence-gate
checks. Anchor numbers match the bound AeroSkills leaves under
aerodynamics/boundary-layer/.
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
import boundary_layer_engineer_core as bl  # noqa: E402


class TestDomainRules(unittest.TestCase):

    def test_blasius_flat_plate_anchors(self):
        # boundary-layer-theory leaf: Re_c = 1e6 -> delta, theta, Cf
        re_c = 1.0e6
        self.assertAlmostEqual(bl.blasius_theta(1.0, re_c), 0.664 / 1000.0,
                               delta=1e-9)
        self.assertAlmostEqual(bl.blasius_delta(1.0, re_c), 5.0 / 1000.0,
                               delta=1e-9)
        self.assertAlmostEqual(bl.blasius_delta_star(1.0, re_c),
                               1.7208 / 1000.0, delta=1e-9)
        self.assertAlmostEqual(bl.blasius_cf_average(re_c), 1.328 / 1000.0,
                               delta=1e-9)

    def test_squire_young_reduces_to_blasius_identity(self):
        # zero-pressure-gradient identity: when U_TE = U_inf (no edge-
        # velocity variation), the Squire-Young profile-drag mapping on
        # the Blasius trailing-edge momentum thickness must reduce
        # EXACTLY to the average Blasius flat-plate reduction
        # 1.328/sqrt(Re_c) (squire-young-profile-drag leaf).
        re_c = 3.5e6
        c = 0.65
        theta_te = bl.blasius_theta(c, re_c)
        cdp = bl.squire_young_profile_drag(theta_te, c, 79.0, 79.0)
        self.assertAlmostEqual(cdp, bl.blasius_cf_average(re_c), delta=1e-12)

    def test_mangler_ratio_exact(self):
        # mangler-axisymmetric-transform leaf: cone momentum thickness
        # at equal running length is EXACTLY 1/sqrt(3) of the flat-plate
        # value; cone skin friction is EXACTLY sqrt(3) of the flat value.
        theta_flat = 0.3127e-3
        self.assertAlmostEqual(
            bl.cone_momentum_thickness(theta_flat) / theta_flat,
            1.0 / math.sqrt(3.0), delta=1e-12)
        cf_flat = 2.6e-4
        self.assertAlmostEqual(bl.cone_skin_friction(cf_flat) / cf_flat,
                               math.sqrt(3.0), delta=1e-12)

    def test_transition_location_anchor(self):
        # boundary-layer-transition leaf worked example: Ue=30 m/s,
        # nu=1.46e-5 m2/s over a 2 m run -> x_tr ~ 0.81 m
        trans = bl.flat_plate_transition(1.46e-5, 30.0, 2.0)
        self.assertIsNotNone(trans["x_tr_m"])
        self.assertAlmostEqual(trans["x_tr_m"], 0.81, delta=0.02)
        # at the transition station the flat-plate closed-form Re_theta
        # exactly meets the Michel threshold (bisection root)
        re_x_tr = trans["re_x_tr"]
        self.assertAlmostEqual(bl.re_theta_flat_plate(re_x_tr),
                               bl.michel_threshold(re_x_tr), delta=1e-2)

    def test_michel_criterion_monotonic(self):
        # below the threshold: not yet transitioned; above: transitioned
        re_x = 2.0e6
        thr = bl.michel_threshold(re_x)
        self.assertFalse(bl.michel_criterion(re_x, thr - 1.0))
        self.assertTrue(bl.michel_criterion(re_x, thr + 1.0))

    def test_stokes_creeping_drag_positive_and_sane(self):
        # stokes-creeping-flow-drag leaf: F = 6*pi*mu*a*U > 0, and the
        # pressure/friction split is the exact 1:2 ratio (1/3 and 2/3
        # of the total).
        mu, a, u = 1.7885e-5, 1.0e-4, 0.01
        f = bl.stokes_drag(mu, a, u)
        fp = bl.stokes_pressure_drag(mu, a, u)
        ff = bl.stokes_friction_drag(mu, a, u)
        self.assertGreater(f, 0.0)
        self.assertAlmostEqual(fp + ff, f, delta=1e-15)
        self.assertAlmostEqual(fp, f / 3.0, delta=1e-15)
        self.assertAlmostEqual(ff, 2.0 * f / 3.0, delta=1e-15)
        # Oseen correction only adds drag (never reduces it) for Re > 0
        nu = 1.46e-5
        self.assertGreater(bl.oseen_drag(mu, a, u, nu), f)

    def test_rough_wall_regime_classification(self):
        self.assertEqual(bl.classify_regime(1.0), "smooth")
        self.assertEqual(bl.classify_regime(30.0), "transitional")
        self.assertEqual(bl.classify_regime(100.0), "fully-rough")

    def test_stagnation_layer_positive(self):
        a = bl.stagnation_velocity_gradient("sphere", 79.0, 0.20)
        self.assertGreater(a, 0.0)
        delta = bl.stagnation_boundary_layer_thickness(1.46e-5, a)
        self.assertGreater(delta, 0.0)

    def test_unsteady_penetration_depth_positive(self):
        omega = 2.0 * math.pi * 20.0
        delta = bl.stokes_penetration_depth(1.46e-5, omega)
        self.assertGreater(delta, 0.0)
        # amplitude decays with depth (Stokes second problem)
        amp0 = bl.stokes_second_amplitude_at_depth(2.0, 0.0, delta)
        amp1 = bl.stokes_second_amplitude_at_depth(2.0, delta, delta)
        self.assertGreater(amp0, amp1)

    def test_invalid_inputs_raise(self):
        with self.assertRaises(ValueError):
            bl.reynolds_number(0.0, 1.0, 1.46e-5)
        with self.assertRaises(ValueError):
            bl.squire_young_profile_drag(1.0e-4, 1.0, 30.0, 30.0, 1.0)
        with self.assertRaises(ValueError):
            bl.classify_regime(-1.0)
        with self.assertRaises(ValueError):
            bl.rough_wall_cf(1.0, 1.0)  # x/k_s below validity floor
        with self.assertRaises(ValueError):
            bl.stagnation_velocity_gradient("unknown", 79.0, 0.2)
        with self.assertRaises(ValueError):
            bl.laminar_separation_station([1.0], [30.0], 1.46e-5)


class TestReportBuilder(unittest.TestCase):

    def test_builder_produces_content_model(self):
        model = bl.build_report(bl.example_item())
        self.assertEqual(model["role"], "boundary-layer-engineer")
        self.assertTrue(model["item"])
        for key in ("transition", "profile_drag", "mangler", "wake",
                   "roughness", "stagnation", "stokes", "unsteady",
                   "drag_table", "verdict"):
            self.assertIn(key, model)
        self.assertGreater(model["transition"]["re_c"], 0.0)
        self.assertGreater(model["profile_drag"]["cdp_both_surfaces"], 0.0)
        self.assertGreater(len(model["drag_table"]), 0)

    def test_model_gates_all_pass(self):
        model = bl.build_report(bl.example_item())
        gates = bl.check_report(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_all_pass(self):
        md = bl.example_report_markdown()
        gates = bl.check_report_markdown(md)
        self.assertTrue(gates["all_pass"], gates)

    def test_report_markdown_sections(self):
        md = bl.example_report_markdown()
        for n in range(1, 10):
            self.assertIn("## %d." % n, md, "missing section %d" % n)
        low = md.lower()
        self.assertIn("draft", low)
        self.assertIn("not an approval", low)
        self.assertIn("not a certification approval", low)
        self.assertNotIn("___", md)

    def test_gates_fail_on_tampered_model(self):
        # tamper with the model: no transition location found must fail
        # transition_located and all_pass
        model = bl.build_report(bl.example_item())
        model["transition"]["x_tr_m"] = None
        gates = bl.check_report(model)
        self.assertFalse(gates["all_pass"])
        self.assertFalse(gates["transition_located"])

        # tamper with the Mangler ratio: must break mangler_ratio_correct
        model2 = bl.build_report(bl.example_item())
        model2["mangler"]["theta_ratio_cone_over_2d"] = 0.5
        gates2 = bl.check_report(model2)
        self.assertFalse(gates2["all_pass"])
        self.assertFalse(gates2["mangler_ratio_correct"])

        # tamper with sign-off status: must break sign_off_honest
        model3 = bl.build_report(bl.example_item())
        model3["status"] = "approved"
        gates3 = bl.check_report(model3)
        self.assertFalse(gates3["all_pass"])
        self.assertFalse(gates3["sign_off_honest"])

    def test_gates_fail_on_tampered_markdown(self):
        md = bl.example_report_markdown()
        tampered = md.replace("draft", "REVIEW").replace("DRAFT", "REVIEW")
        gates = bl.check_report_markdown(tampered)
        self.assertFalse(gates["all_pass"])
        self.assertFalse(gates["has_draft_marker"])

    def test_standalone_no_skills_repo(self):
        # Core must work with no AeroSkills present: it never imports or
        # reaches out to AEROSKILLS_DEV at all.
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = bl.build_report(bl.example_item())
        gates = bl.check_report(model)
        self.assertTrue(gates["all_pass"], gates)
        md = bl.render_report_markdown(model)
        self.assertGreater(len(md), 3000)


if __name__ == "__main__":
    unittest.main()
