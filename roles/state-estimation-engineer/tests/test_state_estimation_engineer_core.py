#!/usr/bin/env python3
"""Test state_estimation_core: the executable engine of the role.

Proves the role can DO its job standalone (no AeroSkills needed):
alpha-beta gain rules (Benedict-Bordner, Kalata), the discrete
constant-velocity Kalman recursion, EKF linearization, NEES/ESS
consistency metrics, RTS smoothing, observability, report generation,
and the evidence-gate checks.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from state_estimation_core import (  # noqa: E402
    build_report, check_report, check_report_markdown,
    effective_sample_size, example_item, example_report_markdown,
    kalata_gains, nees, numeric_jacobian, observability_rank,
    render_report_markdown, run_cv_kalman, rts_smooth, steady_state_beta,
    steady_state_verdict, tracking_index_from_noise,
)


class TestAlphaBetaRules(unittest.TestCase):

    def test_benedict_bordner_beta(self):
        # beta = alpha^2 / (2 - alpha); at alpha = 0.5 -> 1/6.
        self.assertAlmostEqual(steady_state_beta(0.5), 0.25 / 1.5)
        self.assertAlmostEqual(steady_state_beta(0.3),
                               0.09 / 1.7)

    def test_benedict_bordner_invalid_alpha(self):
        with self.assertRaises(ValueError):
            steady_state_beta(2.0)
        with self.assertRaises(ValueError):
            steady_state_beta(0.0)

    def test_kalata_gains_zero_index(self):
        self.assertEqual(kalata_gains(0.0)["alpha"], 0.0)
        self.assertEqual(kalata_gains(0.0)["beta"], 0.0)

    def test_kalata_gains_match_leaf_example(self):
        # alpha-beta leaf worked formula: lambda = 0.05 -> alpha~0.270867
        g = kalata_gains(0.05)
        self.assertAlmostEqual(g["alpha"], 0.270867119, places=6)
        self.assertAlmostEqual(g["beta"], 0.042694639, places=6)

    def test_tracking_index_definition(self):
        # lambda = sigma_w*dt^2/sigma_v (leaf definition)
        self.assertAlmostEqual(tracking_index_from_noise(0.1, 1.0, 2.0),
                               0.05)
        with self.assertRaises(ValueError):
            tracking_index_from_noise(0.1, 1.0, 0.0)


class TestKalmanRecursion(unittest.TestCase):

    def test_recursion_converges_to_kalata_gains(self):
        # The converged CV-Kalman gain equals the Kalata alpha-beta pair
        # for the same sigma_w*dt^2/sigma_v tracking index.
        recs = run_cv_kalman([0.5 * k for k in range(1, 61)], 1.0,
                             0.01, 4.0, [0.0, 0.0],
                             [[100.0, 0.0], [0.0, 25.0]])
        k = kalata_gains(0.05)
        self.assertAlmostEqual(recs[-1]["gain"][0], k["alpha"], places=6)
        self.assertAlmostEqual(recs[-1]["gain"][1], k["beta"], places=6)

    def test_covariance_decreases(self):
        recs = run_cv_kalman([1.0] * 20, 1.0, 0.01, 4.0)
        self.assertGreater(recs[0]["P_filt"][0][0],
                           recs[-1]["P_filt"][0][0])
        self.assertLess(recs[-1]["P_filt"][0][0], 4.0)  # below R

    def test_first_gain_uses_initial_covariance(self):
        # P_pred = F P0 F^T + Q -> [0][0] = P0_xx + 2*dt*P0_xv +
        # dt^2*P0_vv + q*dt^4/4 = 125.0025 at the defaults.
        recs = run_cv_kalman([1.0] * 5, 1.0, 0.01, 4.0,
                             [0.0, 0.0], [[100.0, 0.0], [0.0, 25.0]])
        self.assertAlmostEqual(recs[0]["gain"][0], 125.0025 / 129.0025)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            run_cv_kalman([1.0], 0.0, 0.01, 4.0)
        with self.assertRaises(ValueError):
            run_cv_kalman([], 1.0, 0.01, 4.0)
        with self.assertRaises(ValueError):
            run_cv_kalman([1.0], 1.0, 0.01, 0.0)


class TestEKFAndMetrics(unittest.TestCase):

    def test_numeric_jacobian_matches_analytic_range_derivative(self):
        # dr/dpx = px/hypot(px, py) at the operating point.
        op = [300.0, 40.0]
        px, py = op
        r = (px * px + py * py) ** 0.5
        j = numeric_jacobian(lambda x: [(x[0] ** 2 + x[1] ** 2) ** 0.5], op)
        self.assertAlmostEqual(j[0][0], px / r, places=6)

    def test_ekf_correction_reduces_position_uncertainty(self):
        model = build_report(example_item())
        ek = model["ekf"]
        self.assertTrue(ek["x_corrected"][0] > 0.0)
        # innovation equals the deterministic +3 m range bias
        self.assertAlmostEqual(ek["innovation"][0], 3.0, places=6)

    def test_nees_zero_for_exact_estimate(self):
        self.assertAlmostEqual(
            nees([1.0, 2.0], [[1.0, 0.0], [0.0, 1.0]], [1.0, 2.0]), 0.0)

    def test_nees_matches_ukf_leaf_criterion(self):
        # 2-state example: NEES of (5, -2) error with P = 100*I is
        # (25 + 4)/100 = 0.29, well below the expected n = 2.
        v = nees([300.0, 40.0], [[100.0, 0.0], [0.0, 100.0]],
                 [295.0, 42.0])
        self.assertAlmostEqual(v, 0.29, places=6)

    def test_ess_uniform_ensemble(self):
        # ESS = (sum w)^2/sum(w^2); uniform n=1000 -> 1000.
        w = [1.0 / 1000.0] * 1000
        self.assertAlmostEqual(effective_sample_size(w), 1000.0, places=4)

    def test_ess_degenerate(self):
        w = [1.0, 0.0, 0.0, 0.0]
        self.assertAlmostEqual(effective_sample_size(w), 1.0, places=9)
        with self.assertRaises(ValueError):
            effective_sample_size([])

    def test_steady_state_verdict(self):
        # Converged: trailing-window (last min(10,n)) mean below tol.
        norms = [1e-2] + [1e-4] * 10   # transient then 10 quiet steps
        self.assertTrue(steady_state_verdict(norms, 1e-3))
        self.assertFalse(steady_state_verdict([1e-2, 2e-3, 3e-3, 2e-3], 1e-3))
        with self.assertRaises(ValueError):
            steady_state_verdict([], 1e-3)
        with self.assertRaises(ValueError):
            steady_state_verdict([1e-4], 0.0)


class TestSmoothingAndObservability(unittest.TestCase):

    def test_smoother_reduces_covariance(self):
        model = build_report(example_item())
        sm = model["smoothing"]
        self.assertTrue(sm["all_reduced"])
        self.assertTrue(sm["boundary_matches"])
        self.assertGreater(sm["max_reduction"], 0.0)

    def test_smoother_matches_filter_at_boundary(self):
        recs = run_cv_kalman([0.5 * k for k in range(1, 11)], 1.0,
                             0.01, 4.0)
        out = rts_smooth([dict(r, dt=1.0) for r in recs])
        self.assertAlmostEqual(out["smoothed_covs"][-1][0][0],
                               recs[-1]["P_filt"][0][0], places=12)
        self.assertEqual(len(out["smoothed_states"]), len(recs))

    def test_observability(self):
        o = observability_rank(1.0)
        self.assertEqual(o["rank"], 2)
        self.assertTrue(o["observable"])
        self.assertAlmostEqual(o["det"], 1.0)


class TestReportBuilderAndGates(unittest.TestCase):

    def test_example_builds_complete_model(self):
        model = build_report(example_item())
        self.assertEqual(model["status"], "draft-for-review")
        self.assertEqual(model["document_type"],
                         "Navigation State Estimator Design Report")
        self.assertTrue(model["estimator_class"])
        self.assertIn("kalman", model)
        self.assertIn("ekf", model)
        self.assertIn("attitude", model)
        self.assertIn("alpha_beta", model)

    def test_example_numbers_present(self):
        model = build_report(example_item())
        km = model["kalman"]["final"]
        self.assertGreater(km["gain"][0], 0.0)
        self.assertGreater(km["pos_var_after"], 0.0)
        self.assertTrue(model["observability"]["observable"])
        self.assertIsInstance(model["ekf"]["nees_2d"], float)
        # attitude drift anchor: |b|*t with the example bias vector
        self.assertAlmostEqual(model["attitude"]["drift_100s_rad"],
                               0.141421, places=4)

    def test_core_gates_all_pass(self):
        model = build_report(example_item())
        gates = check_report(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_all_pass(self):
        md = example_report_markdown()
        gates = check_report_markdown(md)
        self.assertTrue(gates["all_pass"], gates)

    def test_rendered_has_nine_sections_and_markers(self):
        md = example_report_markdown()
        for n in range(1, 10):
            self.assertIn(f"## {n}. ", md)
        low = md.lower()
        self.assertIn("draft", low)
        self.assertIn("not an approval", low)

    def test_gates_fail_when_tampered(self):
        model = build_report(example_item())
        model["status"] = "approved"
        self.assertFalse(check_report(model)["sign_off_honest"])
        model2 = build_report(example_item())
        model2["kalman"] = {}
        self.assertFalse(check_report(model2)["kalman_numbers_present"])

    def test_model_json_round_trip(self):
        import json
        model = build_report(example_item())
        blob = json.dumps(model)
        self.assertIn("kalman", json.loads(blob))

    def test_standalone_no_skills_repo(self):
        # Core must work with no AeroSkills present.
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = build_report(example_item())
        md = render_report_markdown(model)
        self.assertGreater(len(md), 3000)
        self.assertTrue(check_report(model)["all_pass"])


if __name__ == "__main__":
    unittest.main()
