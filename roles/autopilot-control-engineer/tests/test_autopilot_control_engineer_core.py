#!/usr/bin/env python3
"""Test autopilot_control_engineer_core: the executable engine of the
Autopilot Control Engineer.

Proves the role can DO its job standalone (no AeroSkills needed):
reduced-order state-space plant models, inner/outer loop PID/P gain
design with margins, roll-attitude root-locus design, a yaw-rate
damper, an Ackermann observer, L1 adaptive augmentation (simulation +
convergence), gain scheduling, digital discretization + sample-rate
rule, control allocation, package builder + evidence gates, and
standalone mode.
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from autopilot_control_engineer_core import (  # noqa: E402
    AutopilotProject, build_package, check_package, check_package_markdown,
    closed_loop_bandwidth, closed_loop_poles_rl, companion_form_2state,
    controllable_2state, damping_ratio_rl, discrete_pid_velocity, eig2x2,
    example_item, example_package_markdown, gain_for_damping_rl,
    l1_adaptive_update, l1_control_output, l1_convergence_report,
    l1_filter_step, l1_projection, l1_simulate, l1_sigma_true, loop_margins,
    observable_2state, observer_gain_2state, pid_gains_second_order,
    pseudoinverse_alloc_row, rate_limited_scheduling_variable,
    render_package_markdown, sample_rate_rule, schedule_gain,
    second_order_bandwidth_factor, stability_verdict_rl, type1_margins,
    zoh_first_order,
)

# Deterministic across midnight: pin fresh renders to the date the
# committed template carries (CI override wins).
os.environ.setdefault("ROLE_GEN_DATE", "2026-09-08")


class TestStateSpaceAnalysis(unittest.TestCase):

    def test_companion_form_realization(self):
        # G(s) = 5/(s^2 + 8.64 s + 51.84): A=[[0,1],[-51.84,-8.64]]
        ss = companion_form_2state(8.64, 51.84, 5.0)
        self.assertEqual(ss["A"], [[0.0, 1.0], [-51.84, -8.64]])
        self.assertEqual(ss["B"], [[0.0], [5.0]])
        with self.assertRaises(ValueError):
            companion_form_2state(1.0, 1.0, 0.0)

    def test_eig2x2_matches_wn_zeta(self):
        # wn=7.2, zeta=0.6 -> a1=8.64, a0=51.84; poles = -4.32 +/- j5.76
        res = eig2x2([[0.0, 1.0], [-51.84, -8.64]])
        self.assertAlmostEqual(res["poles"][0][0], -4.32, delta=1e-9)
        self.assertAlmostEqual(res["poles"][0][1], 5.76, delta=1e-9)
        self.assertAlmostEqual(res["wn"], 7.2, delta=1e-9)
        self.assertAlmostEqual(res["zeta"], 0.6, delta=1e-9)
        self.assertTrue(res["stable"])

    def test_controllable_observable(self):
        A = [[0.0, 1.0], [-51.84, -8.64]]
        B = [[0.0], [5.0]]
        self.assertTrue(controllable_2state(A, B))
        self.assertFalse(controllable_2state(A, [[0.0], [0.0]]))
        C = [[0.0, 1.0]]
        self.assertTrue(observable_2state(A, C))
        self.assertFalse(observable_2state(A, [[0.0, 0.0]]))


class TestInnerOuterLoopDesign(unittest.TestCase):

    def test_bandwidth_factor_anchor(self):
        # f(0.7071) == 1 exactly (classic 0.707 damping)
        self.assertAlmostEqual(second_order_bandwidth_factor(
            math.sqrt(2.0) / 2.0), 1.0, delta=1e-12)
        self.assertAlmostEqual(closed_loop_bandwidth(
            8.41, math.sqrt(2.0) / 2.0), 8.41, delta=1e-2)

    def test_pid_pole_placement_anchor(self):
        # a1=2, a0=1, b=1, wn=3, zeta=0.7, p3=4 -> kp=24.8 ki=36 kd=6.2
        kp, ki, kd = pid_gains_second_order(2.0, 1.0, 1.0, 3.0, 0.7, 4.0)
        self.assertAlmostEqual(kp, 24.8, delta=1e-6)
        self.assertAlmostEqual(ki, 36.0, delta=1e-6)
        self.assertAlmostEqual(kd, 6.2, delta=1e-6)
        with self.assertRaises(ValueError):
            pid_gains_second_order(2.0, 1.0, 0.0, 3.0, 0.7, 4.0)

    def test_type1_margins_infinite_gain_margin(self):
        m = type1_margins(2.857, 4.082)
        self.assertGreater(m["phase_margin_deg"], 0.0)
        self.assertTrue(math.isinf(m["gain_margin_db"]))

    def test_loop_margins_general(self):
        # inner PID loop open-loop transfer, sp plant a1=8.64, a0=51.84
        kp, ki, kd = pid_gains_second_order(8.64, 51.84, 5.0, 14.0, 0.85,
                                            28.0)
        num = [5.0 * kd, 5.0 * kp, 5.0 * ki]
        den = [1.0, 8.64, 51.84, 0.0]
        m = loop_margins(num, den)
        self.assertGreater(m["phase_margin_deg"], 0.0)
        self.assertTrue(m["phase_margin_ok"])


class TestRootLocusAndYawDamper(unittest.TestCase):

    def test_gain_for_damping_and_poles(self):
        a = 2.857
        K = gain_for_damping_rl(a, math.sqrt(2.0) / 2.0)
        self.assertAlmostEqual(K, a * a / 2.0, delta=1e-9)
        poles = closed_loop_poles_rl(a, K)["poles"]
        self.assertAlmostEqual(poles[0][0], -a / 2.0, delta=1e-9)
        self.assertAlmostEqual(damping_ratio_rl(a, K),
                               math.sqrt(2.0) / 2.0, delta=1e-6)
        self.assertTrue(stability_verdict_rl(a, K))
        self.assertFalse(stability_verdict_rl(a, 0.0))

    def test_root_locus_domain_errors(self):
        with self.assertRaises(ValueError):
            closed_loop_poles_rl(-1.0, 1.0)
        with self.assertRaises(ValueError):
            gain_for_damping_rl(1.0, 1.5)


class TestObserver(unittest.TestCase):

    def test_ackermann_anchor_1(self):
        # A=[[0,1],[0,0]], C=[1,0], poles -4,-5 -> L=[9,20]
        res = observer_gain_2state([[0.0, 1.0], [0.0, 0.0]], [[1.0, 0.0]],
                                   [-4.0, -5.0])
        self.assertAlmostEqual(res["L"][0], 9.0, delta=1e-6)
        self.assertAlmostEqual(res["L"][1], 20.0, delta=1e-6)

    def test_ackermann_anchor_2(self):
        # A=[[0,1],[0,-2]], C=[1,0], poles -30,-30 -> L=[58,784]
        res = observer_gain_2state([[0.0, 1.0], [0.0, -2.0]], [[1.0, 0.0]],
                                   [-30.0, -30.0])
        self.assertAlmostEqual(res["L"][0], 58.0, delta=1e-6)
        self.assertAlmostEqual(res["L"][1], 784.0, delta=1e-6)

    def test_observer_requires_stable_poles(self):
        with self.assertRaises(ValueError):
            observer_gain_2state([[0.0, 1.0], [0.0, 0.0]], [[1.0, 0.0]],
                                 [1.0, -5.0])


class TestL1AdaptiveControl(unittest.TestCase):

    def test_projection_clamps_at_bound(self):
        self.assertEqual(l1_projection(2.5, 1.0, 2.5), 0.0)
        self.assertEqual(l1_projection(-2.5, -1.0, 2.5), 0.0)
        self.assertEqual(l1_projection(0.0, 3.0, 2.5), 3.0)

    def test_adaptive_update_clamped(self):
        v = l1_adaptive_update(0.0, 10.0, 15.0, 0.01, 2.5)
        self.assertAlmostEqual(v, max(-2.5, min(2.5, -0.01 * 15.0 * 10.0)))

    def test_filter_step_converges_toward_input(self):
        nu = 0.0
        for _ in range(2000):
            nu = l1_filter_step(nu, 2.0, 10.0, 0.01)
        self.assertAlmostEqual(nu, 2.0, delta=1e-3)

    def test_control_output_feedforward(self):
        u = l1_control_output(0.5, 1.0, -2.0, 1.0)
        self.assertAlmostEqual(u, 2.0 - 0.5, delta=1e-9)

    def test_sigma_true(self):
        s = l1_sigma_true(1.0, -1.0, -2.0, 1.0, 1.0)
        self.assertAlmostEqual(s, (-1.0 - -2.0) * 1.0 / 1.0 + 1.0)

    def test_l1_simulate_and_convergence(self):
        res = l1_simulate(-1.0, -2.0, 1.0, 2.0, 1.0, 0.0, 1.0, 0.01, 15.0,
                          10.0, 2.5, 6000, tail=1000)
        self.assertLess(res["tail_abs_pred"], 1e-3)
        converged, criteria = l1_convergence_report(res, -1.0, -2.0, 1.0,
                                                     1.0)
        self.assertTrue(converged)
        self.assertLess(criteria["sigma_dev"], 0.05)

    def test_l1_domain_errors(self):
        with self.assertRaises(ValueError):
            l1_simulate(-1.0, 1.0, 1.0, 2.0, 1.0, 0.0, 1.0, 0.01, 15.0,
                       10.0, 2.5, 100)  # a_m must be < 0


class TestGainSchedulingAndDigital(unittest.TestCase):

    def test_schedule_gain_linear_interp(self):
        table = [(100.0, 10.0), (200.0, 20.0), (300.0, 15.0)]
        self.assertAlmostEqual(schedule_gain(table, 150.0), 15.0)
        self.assertAlmostEqual(schedule_gain(table, 50.0), 10.0)  # clamp lo
        self.assertAlmostEqual(schedule_gain(table, 500.0), 15.0)  # clamp hi
        with self.assertRaises(ValueError):
            schedule_gain([(1.0, 1.0)], 1.0)

    def test_rate_limited_scheduling_variable(self):
        v = rate_limited_scheduling_variable(100.0, 500.0, 400.0, 0.05)
        self.assertAlmostEqual(v, 120.0, delta=1e-9)

    def test_zoh_first_order_unity_dc_gain(self):
        z = zoh_first_order(2.857, 0.01)
        self.assertAlmostEqual(z["A"] + z["B"], 1.0, delta=1e-12)
        with self.assertRaises(ValueError):
            zoh_first_order(-1.0, 0.01)

    def test_discrete_pid_velocity_coeffs(self):
        c = discrete_pid_velocity(10.0, 100.0, 1.0, 0.01)
        self.assertAlmostEqual(c["b0"], 10.0 + 100.0 * 0.01 + 1.0 / 0.01)
        self.assertEqual(c["a1"], -1.0)

    def test_sample_rate_rule_verdict(self):
        ok = sample_rate_rule(14.0, 0.01)
        self.assertEqual(ok["verdict"], "ok")
        too_slow = sample_rate_rule(14.0, 0.1)
        self.assertEqual(too_slow["verdict"], "too-slow")


class TestControlAllocation(unittest.TestCase):

    def test_pseudoinverse_alloc_anchor(self):
        # B=[[1,1]], m=0.8 -> u=[0.4,0.4]
        res = pseudoinverse_alloc_row([1.0, 1.0], 0.8)
        self.assertAlmostEqual(res["u"][0], 0.4, delta=1e-9)
        self.assertAlmostEqual(res["u"][1], 0.4, delta=1e-9)
        self.assertAlmostEqual(res["error"], 0.0, delta=1e-9)

    def test_pseudoinverse_zero_row_raises(self):
        with self.assertRaises(ValueError):
            pseudoinverse_alloc_row([0.0, 0.0], 1.0)


class TestPackageBuilder(unittest.TestCase):

    def test_example_package_gates_pass(self):
        model = build_package(example_item())
        self.assertEqual(model["status"], "draft-for-review")
        self.assertTrue(model["roll_rl"]["stable"])
        gates = check_package(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_example_markdown_complete(self):
        md = example_package_markdown()
        for sec in ["## 1. State-space plant models",
                    "## 2. Inner/outer loop gain design",
                    "## 4. L1 adaptive augmentation",
                    "## 7. Control allocation",
                    "## 8. Control-law summary and verdict"]:
            self.assertIn(sec, md)
        low = md.lower()
        self.assertIn("draft", low)
        self.assertIn("not an approval", low)
        self.assertIn("not flight software release", low)
        self.assertIn("rad/s", md)
        self.assertNotIn("___", md)

    def test_markdown_gates_all_pass(self):
        md = example_package_markdown()
        gates = check_package_markdown(md)
        self.assertTrue(gates["all_pass"], gates)

    def test_standalone_no_skills_repo(self):
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        item = example_item()
        model = build_package(item)
        self.assertEqual(model["status"], "draft-for-review")
        md = render_package_markdown(model)
        self.assertGreater(len(md), 3000)
        self.assertTrue(check_package(model)["all_pass"])

    def test_tampered_bandwidth_requirement_fails_outer_gate(self):
        item = example_item()
        item.req_bandwidth_rad_s = 500.0  # unattainable bandwidth
        model = build_package(item)
        gates = check_package(model)
        self.assertFalse(gates["all_pass"])
        self.assertFalse(gates["outer_margins_bandwidth_meet_requirement"])

    def test_tampered_l1_bound_fails_gate(self):
        item = example_item()
        item.l1_ebound_req = 1e-9  # impossibly tight transient bound
        model = build_package(item)
        gates = check_package(model)
        self.assertFalse(gates["all_pass"])
        self.assertFalse(gates["l1_transient_bound_met"])

    def test_tampered_status_fails_sign_off_gate(self):
        item = example_item()
        model = build_package(item)
        model["status"] = "approved"
        gates = check_package(model)
        self.assertFalse(gates["all_pass"])
        self.assertFalse(gates["sign_off_honest"])

    def test_model_json_roundtrip(self):
        import json
        model = build_package(example_item())
        text = json.dumps(model)
        back = json.loads(text)
        self.assertEqual(back["vehicle"], model["vehicle"])
        self.assertAlmostEqual(back["inner"]["kp"], model["inner"]["kp"])


if __name__ == "__main__":
    unittest.main()
