#!/usr/bin/env python3
"""Test gnc_core: the executable engine of the GNC Engineer role.

Proves the role can DO its job standalone (no AeroSkills needed):
PID pole placement, bandwidth/natural-frequency rules, margin
computation, LQR Riccati solution, Kalman steady state, observer
gains, guidance commands, digital design checks, Monte Carlo
robustness, report generation, and evidence-gate checks. Anchor
numbers match the bound AeroSkills leaves (pid-control-design,
frequency-response-design, lqr-design, kalman-filter-design,
observer-design, pursuit-guidance, digital-control-design).
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
import gnc_core as gnc  # noqa: E402


class TestDomainRules(unittest.TestCase):

    def test_bandwidth_factor_anchors(self):
        # f(0.7071) == 1 exactly (bandwidth = natural frequency at the
        # classic 0.707 damping); f(0.5) = 1.27201965...
        self.assertAlmostEqual(gnc.second_order_bandwidth_factor(
            math.sqrt(2) / 2.0), 1.0, delta=1e-12)
        self.assertAlmostEqual(gnc.second_order_bandwidth_factor(0.5),
                               1.272019649514069, delta=1e-12)

    def test_natural_frequency_from_bandwidth(self):
        # at zeta = 0.707 the required wn equals the bandwidth
        self.assertAlmostEqual(
            gnc.natural_frequency_from_bandwidth(3.0, math.sqrt(2) / 2.0),
            3.0, delta=1e-9)
        # at zeta = 0.5, wn < bandwidth
        self.assertLess(gnc.natural_frequency_from_bandwidth(3.0, 0.5), 3.0)

    def test_pid_pole_placement_anchors(self):
        # leaf anchors (pid-control-design): a=2,b=1,wn=3,zeta=0.7
        kp, ki = gnc.pid_gains_first_order(2.0, 1.0, 3.0, 0.7)
        self.assertAlmostEqual(kp, 2.2, delta=1e-9)
        self.assertAlmostEqual(ki, 9.0, delta=1e-9)
        # a1=2,a0=1,b=1,wn=3,zeta=0.7,p3=4 -> kp=24.8 ki=36 kd=6.2
        kp2, ki2, kd2 = gnc.pid_gains_second_order(2.0, 1.0, 1.0, 3.0,
                                                   0.7, 4.0)
        self.assertAlmostEqual(kp2, 24.8, delta=1e-6)
        self.assertAlmostEqual(ki2, 36.0, delta=1e-6)
        self.assertAlmostEqual(kd2, 6.2, delta=1e-6)

    def test_type1_margins_anchor(self):
        # leaf anchor: L = 2/(s(s+2)) -> PM 65.5305 deg, GM inf
        m = gnc.type1_margins(2.0, 2.0)
        self.assertAlmostEqual(m["crossover_rad_s"], 0.9101797, delta=1e-4)
        self.assertAlmostEqual(m["phase_margin_deg"], 65.5305, delta=1e-2)
        self.assertEqual(m["gain_margin"], float("inf"))

    def test_loop_margins_canonical_anchor(self):
        # frequency-response-design anchor: G = 2/(s(s+1)(s+2)) ->
        # GM 3.0 (9.5424 dB) at w_pc = sqrt(2), PM ~ 32.61 deg at
        # w_gc ~ 0.74935 rad/s
        m = gnc.loop_margins([2.0], [1.0, 3.0, 2.0, 0.0])
        self.assertAlmostEqual(m["gain_margin"], 3.0, delta=1e-3)
        self.assertAlmostEqual(m["gain_margin_db"], 9.5424, delta=1e-2)
        self.assertAlmostEqual(m["phase_crossover_rad_s"],
                               math.sqrt(2.0), delta=1e-2)
        self.assertAlmostEqual(m["gain_crossover_rad_s"], 0.74935,
                               delta=1e-2)
        self.assertAlmostEqual(m["phase_margin_deg"], 32.61, delta=1e-1)

    def test_riccati_anchor(self):
        # q1=10, q2=1, r=0.1, a=2 -> P and K closed form
        r = gnc.riccati_solution([[0, 1], [0, -2]], [0, 1],
                                 [[10, 0], [0, 1]], 0.1)
        self.assertAlmostEqual(r["P"][0][0], 5.8310, delta=1e-3)
        self.assertAlmostEqual(r["P"][1][1], 0.3831, delta=1e-3)
        self.assertAlmostEqual(r["K"][0], 10.0, delta=1e-9)
        self.assertAlmostEqual(r["K"][1], 3.8310, delta=1e-3)
        self.assertTrue(r["stable"])

    def test_kalman_steady_state_anchor(self):
        # q=1, r=1, f=h=1 -> P_inf = (1+sqrt(5))/2 (golden ratio),
        # K = P/(P+1) ~ 0.61803
        k = gnc.kalman_steady_state(1.0, 1.0, 1.0, 1.0)
        self.assertAlmostEqual(k["p_pred"], (1.0 + math.sqrt(5)) / 2.0,
                               delta=1e-9)
        self.assertAlmostEqual(k["gain"], 0.61803398875, delta=1e-9)
        self.assertAlmostEqual(k["p_apost"],
                               (1.0 - k["gain"]) * k["p_pred"], delta=1e-12)

    def test_observer_gain_2state_anchor(self):
        # A = [[0,1],[0,-2]], C = [1,0], poles -30,-30 -> L = [58, 784]
        o = gnc.observer_gain_2state([[0, 1], [0, -2]], [[1, 0]],
                                     [-30.0, -30.0])
        self.assertAlmostEqual(o["L"][0], 58.0, delta=1e-6)
        self.assertAlmostEqual(o["L"][1], 784.0, delta=1e-6)
        self.assertAlmostEqual(o["settling_time_s"], 4.0 / 30.0, delta=1e-9)

    def test_pn_acceleration(self):
        # rx=1000, ry=0, vx=-100, vy=10 -> Vc=100, lam_dot=0.01,
        # a_c = N * 1.0 for N
        a = gnc.pn_acceleration(1000.0, 0.0, -100.0, 10.0, 4.0)
        self.assertAlmostEqual(a["closing_speed_m_s"], 100.0, delta=1e-9)
        self.assertAlmostEqual(a["los_rate_rad_s"], 0.01, delta=1e-12)
        self.assertAlmostEqual(a["accel_cmd_m_s2"], 4.0, delta=1e-9)

    def test_discrete_pid_velocity(self):
        d = gnc.discrete_pid_velocity(2.0, 3.0, 4.0, 0.1)
        self.assertAlmostEqual(d["b0"], 2.0 + 3.0 * 0.1 + 4.0 / 0.1,
                               delta=1e-12)
        self.assertAlmostEqual(d["b1"], -2.0 - 2.0 * 4.0 / 0.1, delta=1e-12)
        self.assertAlmostEqual(d["b2"], 4.0 / 0.1, delta=1e-12)
        self.assertEqual(d["a1"], -1.0)
        # b0 + b1 + b2 == Ki*T (constant-error injection per step)
        self.assertAlmostEqual(d["b0"] + d["b1"] + d["b2"], 3.0 * 0.1,
                               delta=1e-12)

    def test_sample_rate_rule(self):
        r = gnc.sample_rate_rule(10.0, 0.02)     # 50 Hz vs 10 rad/s loop
        self.assertAlmostEqual(r["w_s_min_rad_s"], 100.0, delta=1e-9)
        self.assertEqual(r["verdict"], "ok")
        self.assertEqual(gnc.sample_rate_rule(10.0, 0.1)["verdict"],
                         "too-slow")

    def test_monte_carlo_deterministic(self):
        a1 = gnc.monte_carlo_outer_margins(10.0, 5.0, 100, seed=7)
        a2 = gnc.monte_carlo_outer_margins(10.0, 5.0, 100, seed=7)
        self.assertEqual(a1["pm_min_deg"], a2["pm_min_deg"])
        self.assertEqual(a1["pm_max_deg"], a2["pm_max_deg"])
        self.assertEqual(a1["pm_mean_deg"], a2["pm_mean_deg"])

    def test_invalid_inputs_raise(self):
        with self.assertRaises(ValueError):
            gnc.pid_gains_second_order(2, 1, 0.0, 3, 0.7, 4)
        with self.assertRaises(ValueError):
            gnc.type1_margins(0.0, 2.0)
        with self.assertRaises(ValueError):
            gnc.kalman_steady_state(1.0, 1.0, 1.0, 0.0)
        with self.assertRaises(ValueError):
            gnc.riccati_solution([[0, 1], [0, -2]], [0, 1],
                                 [[10, 0], [0, 1]], 0.0)
        with self.assertRaises(ValueError):
            gnc.observer_gain_2state([[0, 1], [0, -2]], [[1, 0]],
                                     [-30.0, 5.0])   # unstable pole
        with self.assertRaises(ValueError):
            gnc.observer_gain_2state([[0, 1], [0, -2]], [[0, 0]],
                                     [-30.0, -30.0])  # not observable
        with self.assertRaises(ValueError):
            gnc.pn_acceleration(0.0, 0.0, -100.0, 10.0, 4.0)  # zero range


class TestReportBuilder(unittest.TestCase):

    def test_example_model_values(self):
        m = gnc.build_gnc_report(gnc.example_project())
        # inner loop gains from the documented example facts
        self.assertAlmostEqual(m["inner"]["kp"], 156.6, delta=1e-6)
        self.assertAlmostEqual(m["inner"]["ki"], 864.0, delta=1e-6)
        self.assertAlmostEqual(m["inner"]["kd"], 9.75, delta=1e-6)
        # inner margins: comfortable PM, infinite GM (type-1 loop with
        # numerator lead)
        self.assertGreater(m["inner"]["margins"]["pm_deg"], 45.0)
        self.assertEqual(m["inner"]["margins"]["gm_db"], float("inf"))
        # outer loop numbers
        self.assertAlmostEqual(m["outer"]["kp_theta"], 5.4, delta=1e-9)
        self.assertAlmostEqual(m["outer"]["zeta_theta"],
                               math.sqrt(2) / 2.0, delta=1e-9)
        self.assertGreater(m["outer"]["bw_rad_s"], 3.0)
        # nav budget
        self.assertLess(m["nav"]["sigma_deg"], m["nav"]["budget_deg"])
        self.assertAlmostEqual(m["nav"]["gain"], 0.02956, delta=1e-3)
        # lqr + observer + guidance real
        self.assertTrue(m["lqr"]["stable"])
        self.assertAlmostEqual(m["observer"]["L"][0], 58.0, delta=1e-6)
        self.assertAlmostEqual(m["observer"]["L"][1], 784.0, delta=1e-6)
        self.assertGreater(m["guidance"]["accel_cmd_m_s2"], 0.0)

    def test_requirements_recorded(self):
        m = gnc.build_gnc_report(gnc.example_project())
        self.assertEqual(m["requirements"]["phase_margin_deg"], 45.0)
        self.assertEqual(m["requirements"]["gain_margin_db"], 6.0)
        self.assertEqual(m["requirements"]["bandwidth_rad_s"], 3.0)
        self.assertEqual(m["verdicts"]["inner_margins"], "PASS")
        self.assertEqual(m["verdicts"]["outer_margins"], "PASS")
        self.assertEqual(m["verdicts"]["outer_bandwidth"], "PASS")
        self.assertEqual(m["verdicts"]["nav_budget"], "PASS")
        self.assertEqual(m["verdicts"]["mc_robustness"], "PASS")

    def test_report_markdown_sections(self):
        md = gnc.example_report_markdown()
        for sec in ["## 1. Architecture", "## 2. Navigation",
                    "## 3. Control design", "## 4. Digital",
                    "## 5. State estimation", "## 6. Guidance",
                    "## 7. Space GNC", "## 8. Monte Carlo",
                    "## 9. Conclusions"]:
            self.assertIn(sec, md, "missing section %s" % sec)
        low = md.lower()
        self.assertIn("not an approval", low)
        self.assertIn("not flight software release", low)
        self.assertNotIn("___", md)

    def test_model_gates_all_pass(self):
        m = gnc.build_gnc_report(gnc.example_project())
        gates = gnc.check_gnc_report(m)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_all_pass(self):
        md = gnc.example_report_markdown()
        gates = gnc.check_gnc_report_markdown(md)
        self.assertTrue(gates["all_pass"], gates)

    def test_gates_fail_on_bad_input(self):
        # tamper with the model: margins below requirement must fail
        m = gnc.build_gnc_report(gnc.example_project())
        m["inner"]["margins"]["pm_deg"] = 20.0
        gates = gnc.check_gnc_report(m)
        self.assertFalse(gates["all_pass"])
        self.assertFalse(gates["margins_meet_requirement"])
        # tampered markdown: no draft marker must fail
        md = (gnc.example_report_markdown().replace("draft", "REVIEW")
              .replace("DRAFT", "REVIEW"))
        g = gnc.check_gnc_report_markdown(md)
        self.assertFalse(g["all_pass"])
        self.assertFalse(g["has_draft_marker"])

    def test_standalone_no_skills_repo(self):
        # Core must work with no AeroSkills present.
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = gnc.build_gnc_report(gnc.example_project())
        self.assertTrue(model["inner"]["req_ok"])
        md = gnc.render_gnc_report_markdown(model)
        self.assertGreater(len(md), 3000)


if __name__ == "__main__":
    unittest.main()
