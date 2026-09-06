#!/usr/bin/env python3
"""Test adcs_core: the executable engine of the ADCS Engineer role.

Proves the role can DO its job standalone (no AeroSkills needed):
orbit, TRIAD + QUEST determination, gyro Allan-variance
characterization, reaction wheel control law + momentum management,
magnetorquer actuation, pointing error budget assembly, report
generation, and evidence-gate checks.
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from adcs_core import (  # noqa: E402
    allocate_error_budget, angle_random_walk_coeff, attitude_profile,
    bdot_dipole, build_report, check_report,
    check_report_markdown, classify_noise, coil_current_for_dipole,
    desaturation_torque, dipole_from_torque, dominant_error_source,
    dot3, example_item, example_report_markdown, example_gyro_samples,
    example_observation_set, gyro_noise_characterization, momentum_saturation,
    orbit_mean_motion, orbit_period_min, orthogonality_error,
    overlapping_allan_deviation, pd_gains, pd_wheel_torque, qnorm,
    quest_solution, rotation_angle_deg,
    rss_pointing_error, three_sigma_error, three_sigma_verdict,
    torque_authority, torque_saturation, triad_matrix, wahba_cost,
    wheel_slew_run_z, cross3, norm3,
)


class TestOrbitRules(unittest.TestCase):

    def test_leo_mean_motion_and_period(self):
        n = orbit_mean_motion(600.0e3)
        self.assertAlmostEqual(n, 1.0847e-3, places=6)
        t = orbit_period_min(600.0e3)
        self.assertAlmostEqual(t, 96.54, places=1)

    def test_lower_altitude_faster(self):
        self.assertGreater(orbit_mean_motion(400.0e3),
                           orbit_mean_motion(800.0e3))

    def test_negative_altitude_rejected(self):
        with self.assertRaises(ValueError):
            orbit_mean_motion(-1.0)


class TestTriadDetermination(unittest.TestCase):

    def test_triad_recovers_slew_angle(self):
        obs = example_observation_set(10.0)
        tr = obs["triad"]
        a = triad_matrix(tr["b1"], tr["b2"], tr["r1"], tr["r2"])
        self.assertAlmostEqual(rotation_angle_deg(a), 10.0, places=9)
        self.assertLess(orthogonality_error(a), 1e-12)

    def test_triad_parallel_observations_rejected(self):
        obs = example_observation_set(10.0)
        tr = obs["triad"]
        with self.assertRaises(ValueError):
            triad_matrix(tr["b1"], tr["b1"], tr["r1"], tr["r2"])


class TestQuestDetermination(unittest.TestCase):

    def test_quest_optimal_solution(self):
        obs = example_observation_set(10.0)
        qs = obs["quest"]
        sol = quest_solution(list(qs["observations"]),
                             list(qs["references"]), list(qs["weights"]))
        q = sol["q_optimal"]
        self.assertAlmostEqual(sol["eigenangle_deg"], 10.0, places=9)
        self.assertAlmostEqual(qnorm(q), 1.0, places=12)
        # truth model: cost and residuals collapse to zero
        self.assertLess(sol["wahba_cost"], 1e-12)
        self.assertLess(max(sol["residuals"]), 1e-12)

    def test_quest_needs_two_observations(self):
        with self.assertRaises(ValueError):
            quest_solution([(1, 0, 0)], [(1, 0, 0)])

    def test_wahba_cost_of_identity_on_rotated_set(self):
        obs = example_observation_set(10.0)
        qs = obs["quest"]
        q_identity = (1.0, 0.0, 0.0, 0.0)
        cost = wahba_cost(q_identity, list(qs["observations"]),
                          list(qs["references"]), list(qs["weights"]))
        self.assertGreater(cost, 0.01)  # identity is far from the 10 deg state

    def test_profile_matrix_symmetric_role(self):
        obs = example_observation_set(10.0)
        qs = obs["quest"]
        b = attitude_profile(list(qs["observations"]),
                             list(qs["references"]), list(qs["weights"]))
        self.assertAlmostEqual(b[2][1], b[1][2], places=12)


class TestGyroAllan(unittest.TestCase):

    def test_deterministic_series(self):
        s1 = example_gyro_samples()
        s2 = example_gyro_samples()
        self.assertEqual(len(s1), 7200)
        self.assertEqual(s1[:100], s2[:100])  # bit-identical, no RNG state

    def test_white_noise_classifies_angle_random_walk(self):
        gy = gyro_noise_characterization(example_gyro_samples())
        self.assertLess(gy["fitted_slope"], -0.35)
        self.assertGreater(gy["fitted_slope"], -0.65)
        self.assertEqual(gy["noise_class"], "angle-random-walk")
        # sigma 1e-5 rad/s at tau0 = 1 s -> N ~ 0.0344 deg/sqrt(h)
        self.assertGreater(gy["arw_deg_per_sqrt_h"], 0.0330)
        self.assertLess(gy["arw_deg_per_sqrt_h"], 0.0360)

    def test_allan_deviation_cluster_limits(self):
        samples = example_gyro_samples()[:200]
        with self.assertRaises(ValueError):
            overlapping_allan_deviation(samples, 1.0, [250.0])  # m too long
        with self.assertRaises(ValueError):
            overlapping_allan_deviation(samples, 1.0, [0.5])  # below tau0

    def test_arw_conversion_constant(self):
        # AD(1 s) of a sigma-rate series ~= sigma -> N = sigma * 3437.748
        self.assertAlmostEqual(angle_random_walk_coeff(1e-5, 1.0),
                               1e-5 * 57.2958 * math.sqrt(3600.0), places=12)

    def test_noise_class_bands(self):
        self.assertEqual(classify_noise(-0.5), "angle-random-walk")
        self.assertEqual(classify_noise(0.5), "rate-random-walk")
        self.assertEqual(classify_noise(-1.0), "quantization-noise")
        self.assertEqual(classify_noise(0.0), "bias-instability")


class TestReactionWheelControl(unittest.TestCase):

    def test_pd_gains_from_bandwidth(self):
        kp, kd = pd_gains(35.0, 0.05, 0.8)
        self.assertAlmostEqual(kp, 35.0 * 0.05 ** 2, places=12)
        self.assertAlmostEqual(kd, 2 * 0.8 * 0.05 * 35.0, places=12)

    def test_torque_opposes_error(self):
        tau = pd_wheel_torque(1.0, 1.0, (0.0, 0.0, 0.1), (0.0, 0.0, 0.0))
        self.assertLess(tau[2], 0.0)

    def test_saturation_clips_and_flags(self):
        clipped, flag = torque_saturation((2.0, -0.5, 0.0), 1.0)
        self.assertEqual(clipped, (1.0, -0.5, 0.0))
        self.assertTrue(flag)
        clipped2, flag2 = torque_saturation((0.5, -0.5, 0.0), 1.0)
        self.assertFalse(flag2)

    def test_momentum_saturation_flag(self):
        excess, flag = momentum_saturation((0.15, 0.05, 0.0), 0.2)
        self.assertFalse(flag)
        self.assertEqual(excess, (0.0, 0.0, 0.0))
        excess2, flag2 = momentum_saturation((0.25, 0.05, 0.0), 0.2)
        self.assertTrue(flag2)
        self.assertAlmostEqual(excess2[0], 0.05, places=12)

    def test_desaturation_torque(self):
        tau = desaturation_torque((0.0, 0.0, 0.14), (0.0, 0.0, 0.02), 600.0)
        self.assertAlmostEqual(abs(tau[2]), 0.12 / 600.0, places=15)

    def test_slew_run_metrics(self):
        run = wheel_slew_run_z(35.0, math.radians(10.0), 0.05, 0.8,
                               0.01, 0.2)
        # initial demand exceeds the wheel limit -> clipped, then converges
        self.assertGreater(run["tau0_demand"], 0.01)
        self.assertTrue(run["tau0_demand_clipped"])
        self.assertLess(run["settle_time_1pct_s"], 200.0)
        # momentum demand within wheel capacity -> no saturation flag
        self.assertLess(run["h_peak_nms"], 0.2)
        self.assertFalse(run["momentum_saturation"])


class TestMagnetorquer(unittest.TestCase):

    def test_dipole_solves_torque_cross_b(self):
        tau = (0.0, 0.0, -2.0e-4)
        b = (0.0, 2.5e-5, 0.0)
        m, along_b = dipole_from_torque(tau, b)
        self.assertAlmostEqual(norm3(m), 8.0, places=9)
        self.assertAlmostEqual(norm3(cross3(m, b)), 2.0e-4, places=15)
        self.assertAlmostEqual(norm3(along_b), 0.0, places=15)

    def test_zero_field_rejected(self):
        with self.assertRaises(ValueError):
            dipole_from_torque((1e-4, 0.0, 0.0), (0.0, 0.0, 0.0))
        with self.assertRaises(ValueError):
            bdot_dipole((0.01, 0.0, 0.0), (0.0, 0.0, 0.0), 1.0)

    def test_bdot_dipole_damps_rate(self):
        rate = (0.01, 0.0, 0.0)
        b = (0.0, 0.0, 2.5e-5)
        m = bdot_dipole(rate, b, 1.0e7)
        # omega x B = (0, -2.5e-7, 0) for this geometry
        self.assertAlmostEqual(m[1], -2.5, places=3)
        # torque m x B opposes the body rate component
        self.assertLess(dot3(cross3(m, b), rate), 0.0)

    def test_torque_authority_and_coil_current(self):
        self.assertAlmostEqual(torque_authority(20.0, (0.0, 2.5e-5, 0.0)),
                               5.0e-4, places=15)
        self.assertAlmostEqual(coil_current_for_dipole(20.0, 200, 0.1),
                               1.0, places=12)
        with self.assertRaises(ValueError):
            coil_current_for_dipole(20.0, 0, 0.1)


class TestPointingBudget(unittest.TestCase):

    def test_rss_and_three_sigma(self):
        comps = {"a": 2.0, "b": 2.0, "c": 1.0}
        self.assertAlmostEqual(rss_pointing_error(comps), 3.0, places=12)
        self.assertAlmostEqual(three_sigma_error(comps), 9.0, places=12)

    def test_verdict_and_margin(self):
        self.assertTrue(three_sigma_verdict({"a": 2.0, "b": 2.0}, 30.0))
        self.assertFalse(three_sigma_verdict({"a": 12.0, "b": 2.0}, 30.0))

    def test_dominant_and_allocation(self):
        comps = {"tracker": 2.0, "deadband": 3.0, "jitter": 1.0}
        name, share = dominant_error_source(comps)
        self.assertEqual(name, "deadband")
        self.assertAlmostEqual(share, 9.0 / (4.0 + 9.0 + 1.0), places=9)
        alloc = allocate_error_budget(30.0, comps)
        self.assertAlmostEqual(alloc,
                               math.sqrt((30.0 / 3.0) ** 2 - 14.0),
                               places=9)

    def test_example_budget_meets_requirement(self):
        model = build_report(example_item())
        pb = model["pointing_budget"]
        self.assertTrue(pb["requirement_met"])
        self.assertGreater(pb["margin"], 2.0)
        self.assertLess(pb["rss_3sigma_arcsec"],
                        model["requirement_arcsec_3sigma"])


class TestReportBuilder(unittest.TestCase):

    def test_example_model_complete(self):
        model = build_report(example_item())
        self.assertEqual(model["status"], "draft-for-review")
        self.assertEqual(model["requirement_arcsec_3sigma"], 30.0)
        self.assertEqual(len(model["determination"]["q_optimal"]), 4)
        self.assertEqual(model["gyro"]["noise_class"], "angle-random-walk")
        self.assertTrue(model["pointing_budget"]["requirement_met"])
        self.assertAlmostEqual(
            model["determination"]["triad_rotation_angle_deg"], 10.0,
            places=9)
        self.assertEqual(model["item"]["orbit_altitude_km"], 600.0)

    def test_deterministic_build(self):
        m1 = build_report(example_item())
        m2 = build_report(example_item())
        self.assertEqual(m1["gyro"]["arw_deg_per_sqrt_h"],
                         m2["gyro"]["arw_deg_per_sqrt_h"])
        self.assertEqual(m1["determination"]["q_optimal"],
                         m2["determination"]["q_optimal"])

    def test_requirement_override_changes_margin(self):
        item = example_item()
        item.requirement_arcsec_3sigma = 12.0  # impossibly tight
        model = build_report(item)
        self.assertFalse(model["pointing_budget"]["requirement_met"])

    def test_render_has_sections_and_markers(self):
        md = example_report_markdown()
        for sec in ["## 1. Scope", "## 4. Attitude determination",
                    "## 5. Gyro noise characterization", "## 7. Pointing "
                    "error budget"]:
            self.assertIn(sec, md)
        low = md.lower()
        self.assertIn("not an approval", low)
        self.assertIn("draft", low)
        self.assertNotIn("___", md)

    def test_core_gates_all_pass(self):
        model = build_report(example_item())
        gates = check_report(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_all_pass(self):
        md = example_report_markdown()
        gates = check_report_markdown(md)
        self.assertTrue(gates["all_pass"], gates)

    def test_gate_signoff_honest_rejects_approval_status(self):
        model = build_report(example_item())
        model["status"] = "approved-for-flight"
        gates = check_report(model)
        self.assertFalse(gates["sign_off_honest"])
        self.assertFalse(gates["all_pass"])

    def test_gate_requirement_identified_rejects_missing(self):
        model = build_report(example_item())
        del model["requirement_arcsec_3sigma"]
        gates = check_report(model)
        self.assertFalse(gates["requirement_identified"])
        self.assertFalse(gates["all_pass"])

    def test_standalone_no_skills_repo(self):
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = build_report(example_item())
        self.assertTrue(model["pointing_budget"]["requirement_met"])
        md = example_report_markdown()
        self.assertGreater(len(md), 2000)


if __name__ == "__main__":
    unittest.main()
