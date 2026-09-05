#!/usr/bin/env python3
"""Test guidance_core: the executable engine of the Guidance Engineer role.

Proves the role can DO its job standalone (no AeroSkills needed):
PN/APN commands, pursuit geometry, waypoint steering, acceleration
limits, zero-effort miss, report generation, evidence-gate checks, and
the cli build --bundle + --profile evidence bundle. Every domain anchor
is the real anchor asserted by the bound leaf gate-3 contract tests.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from guidance_core import (  # noqa: E402
    G0, accel_limit_m_s2, accel_utilization, accel_within_limit,
    apn_command, build_report, capture_possible, check_report,
    check_report_markdown, closing_velocity, commanded_acceleration,
    commanded_accel_g, commanded_heading, course_error, desired_heading,
    example_project, example_report_markdown, guidance_command,
    handover_check, heading_error, intercept_time, lead_angle,
    line_of_sight_angle, line_of_sight_rate, miss_within_requirement,
    render_report_markdown, velocity_to_be_gained, zero_effort_miss,
)

# Real leaf anchors (proportional-navigation leaf gate-3 test):
#   rx=1000, ry=100, vx=-200, vy=0, N=4
PN_RANGE = 1004.987562112089
PN_VC = 199.007438042
PN_LAM = 0.0198019801980198
PN_ACC = 15.762965390

ROLE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROLES_REPO = os.path.dirname(os.path.dirname(ROLE_DIR))


class TestGuidanceLawRules(unittest.TestCase):

    def test_closing_velocity_anchor(self):
        self.assertAlmostEqual(
            closing_velocity(1000.0, 100.0, -200.0, 0.0), PN_VC, places=4)

    def test_closing_velocity_pure(self):
        self.assertAlmostEqual(
            closing_velocity(1000.0, 0.0, -200.0, 0.0), 200.0, places=4)

    def test_los_rate_anchor(self):
        self.assertAlmostEqual(
            line_of_sight_rate(1000.0, 100.0, -200.0, 0.0), PN_LAM, places=4)

    def test_pn_command_anchor(self):
        a = commanded_acceleration(1000.0, 100.0, -200.0, 0.0, 4.0)
        self.assertAlmostEqual(a, PN_ACC, places=4)

    def test_pn_linear_in_nav_constant(self):
        a4 = commanded_acceleration(1000.0, 100.0, -200.0, 0.0, 4.0)
        a6 = commanded_acceleration(1000.0, 100.0, -200.0, 0.0, 6.0)
        self.assertAlmostEqual(a6 / a4, 1.5, places=4)

    def test_pn_zero_on_collision_course(self):
        # Pure closing: lam_dot = 0 -> no lateral command
        self.assertAlmostEqual(
            commanded_acceleration(1000.0, 0.0, -200.0, 0.0, 4.0), 0.0,
            places=6)

    def test_pn_invalid_inputs_raise(self):
        with self.assertRaises(ValueError):
            commanded_acceleration(0.0, 0.0, -200.0, 0.0, 4.0)
        with self.assertRaises(ValueError):
            commanded_acceleration(1000.0, 100.0, -200.0, 0.0, 0.0)
        with self.assertRaises(ValueError):
            commanded_acceleration(1000.0, 100.0, -200.0, 0.0, -2.0)

    def test_guidance_command_bundle(self):
        cmd = guidance_command(1000.0, 100.0, -200.0, 0.0, n_nav=4.0)
        self.assertAlmostEqual(cmd["range"], PN_RANGE, places=4)
        self.assertAlmostEqual(cmd["accel_cmd"], PN_ACC, places=4)
        self.assertEqual(cmd["n_nav"], 4.0)

    def test_apn_augmentation_term(self):
        # a_apn = a_pn + N*a_T/2: with N=4, a_T=20 -> +40 m/s^2
        vc = closing_velocity(1000.0, 100.0, -200.0, 0.0)
        lam = line_of_sight_rate(1000.0, 100.0, -200.0, 0.0)
        apn = apn_command(4.0, vc, lam, 20.0)
        self.assertAlmostEqual(apn, PN_ACC + 40.0, places=4)

    def test_accel_in_g(self):
        self.assertAlmostEqual(commanded_accel_g(PN_ACC), PN_ACC / G0,
                               places=6)


class TestPursuitGeometry(unittest.TestCase):

    def test_los_angle(self):
        lam = line_of_sight_angle(1000.0, 100.0)
        self.assertAlmostEqual(lam, 0.09966865249, places=6)  # 5.7106 deg

    def test_heading_error(self):
        eta = heading_error(0.0, 1000.0, 100.0)
        self.assertAlmostEqual(eta, 0.09966865249, places=6)

    def test_lead_angle_speed_ratio(self):
        # beta = -5.7106 deg, Vt/Vi = 1/3 -> lead ~ -1.9007 deg
        lead = lead_angle(100.0, 300.0, -0.09966865249)
        self.assertAlmostEqual(lead, -0.03317399, places=6)

    def test_capture_condition(self):
        self.assertTrue(capture_possible(300.0, 100.0))
        self.assertFalse(capture_possible(90.0, 100.0))

    def test_tail_chase_intercept_time(self):
        # r = 1000, Vi = 300, Vt = 250 -> t = 20 s exactly
        self.assertAlmostEqual(intercept_time(1000.0, 300.0, 250.0), 20.0,
                               places=6)
        with self.assertRaises(ValueError):
            intercept_time(1000.0, 100.0, 300.0)  # never closes


class TestWaypointSteering(unittest.TestCase):

    def test_desired_heading_anchor(self):
        # (0,0) -> (1000,500) = 26.565 deg (leaf anchor)
        psi_d = desired_heading((0.0, 0.0), (1000.0, 500.0))
        self.assertAlmostEqual(psi_d, 0.4636476090, places=6)
        self.assertAlmostEqual(psi_d, 26.5650511771 * 0.0174532925, places=3)

    def test_course_error_wraps(self):
        # heading 45 deg vs 26.565 deg course -> -18.435 deg (leaf anchor)
        e = course_error((0.0, 0.0), (1000.0, 500.0), 0.7853981634)
        self.assertAlmostEqual(e, -0.3217505544, places=6)

    def test_turn_rate_limit_clamps(self):
        # 5 deg/s, 1 s step: 26.565 deg error applied at 5 deg/step
        psi_c = commanded_heading((0.0, 0.0), (1000.0, 500.0), 0.0,
                                  0.0872664626, 1.0)
        self.assertAlmostEqual(psi_c, 0.0872664626, places=6)

    def test_turn_rate_full_error_passes(self):
        # 30 deg/s, 1 s step: full error passes -> psi_c = psi_d
        psi_c = commanded_heading((0.0, 0.0), (1000.0, 500.0), 0.0,
                                  0.5235987756, 1.0)
        self.assertAlmostEqual(psi_c, 0.4636476090, places=6)

    def test_velocity_to_be_gained_anchor(self):
        # leaf anchor: V=250, e=20 deg, V_target=300 -> 65.08 m/s
        vgo = velocity_to_be_gained(250.0, 0.3490658504, 300.0)
        self.assertAlmostEqual(vgo, 65.0768, places=2)


class TestMissDistanceAndLimits(unittest.TestCase):

    def test_zem_leaf_anchor(self):
        # interceptor (0,0) at 300 m/s +x vs stationary target (6000,150)
        # -> t_go = 20 s, ZEM = 150 m (leaf anchor)
        zem = zero_effort_miss((0.0, 0.0), (300.0, 0.0),
                               (6000.0, 150.0), (0.0, 0.0))
        self.assertAlmostEqual(zem["time_to_go"], 20.0, places=6)
        self.assertAlmostEqual(zem["zem"], 150.0, places=6)

    def test_zem_zero_on_collision(self):
        zem = zero_effort_miss((0.0, 0.0), (300.0, 0.0),
                               (9000.0, 0.0), (100.0, 0.0))
        self.assertAlmostEqual(zem["zem"], 0.0, places=6)

    def test_handover_check(self):
        self.assertTrue(handover_check((0.0, 0.0), (8000.0, 0.0), 8000.0))
        self.assertFalse(handover_check((0.0, 0.0), (9000.0, 0.0), 8000.0))

    def test_accel_limit_and_utilization(self):
        self.assertAlmostEqual(accel_limit_m_s2(30.0), 30.0 * G0, places=6)
        # example PN command 15.763 m/s^2 -> 5.36% of a 30 g limit
        util = accel_utilization(15.76296539, 30.0)
        self.assertAlmostEqual(util, 0.0535792, places=6)
        self.assertTrue(accel_within_limit(15.76296539, 30.0))
        self.assertFalse(accel_within_limit(5000.0, 30.0))

    def test_miss_requirement(self):
        self.assertTrue(miss_within_requirement(5.0, 10.0))
        self.assertFalse(miss_within_requirement(100.0, 10.0))


class TestReportBuilder(unittest.TestCase):

    def test_example_report_model(self):
        model = build_report(example_project())
        self.assertEqual(model["recommended_law"], "proportional navigation")
        self.assertEqual(model["n_nav"], 4.0)
        self.assertEqual(model["status"], "draft-for-review")
        self.assertAlmostEqual(model["pn"]["accel_pn_m_s2"], PN_ACC, places=4)
        self.assertAlmostEqual(model["pn"]["accel_apn_m_s2"],
                               PN_ACC + 40.0, places=4)
        self.assertAlmostEqual(model["miss"]["zem_m"], 100.0, places=4)
        self.assertAlmostEqual(model["miss"]["time_to_go_s"], 5.0, places=4)

    def test_example_has_all_sections(self):
        md = example_report_markdown()
        for n in range(1, 10):
            self.assertIn("## %d. " % n, md, "section %d missing" % n)
        self.assertIn("not an approval", md.lower())
        self.assertIn("not flight software release", md.lower())

    def test_core_gates_all_pass(self):
        model = build_report(example_project())
        gates = check_report(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_all_pass(self):
        md = example_report_markdown()
        gates = check_report_markdown(md)
        self.assertTrue(gates["all_pass"], gates)

    def test_standalone_no_skills_repo(self):
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = build_report(example_project())
        self.assertEqual(model["status"], "draft-for-review")
        md = render_report_markdown(model)
        self.assertGreater(len(md), 1000)

    def test_cli_build_bundle_standalone(self):
        """cli build --bundle exits 0 and emits valid evidence (PROTOCOL)."""
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "report.md")
            env = dict(os.environ, AEROSKILLS_DEV="/nonexistent")
            r = subprocess.run(
                [sys.executable, os.path.join(ROLE_DIR, "cli.py"), "build",
                 "--out", out, "--bundle"],
                cwd=ROLE_DIR, env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            ev = os.path.join(td, "evidence")
            for name in ("model.json", "gates.json", "provenance.json"):
                self.assertTrue(os.path.exists(os.path.join(ev, name)),
                                name + " missing")
            gates = json.load(open(os.path.join(ev, "gates.json")))
            self.assertTrue(gates["all_pass"])
            self.assertEqual(gates["exit_code"], 0)
            model = json.load(open(os.path.join(ev, "model.json")))
            self.assertEqual(model["status"], "draft-for-review")
            self.assertEqual(model["miss"]["zem_m"], 100.0)
            prov = json.load(open(os.path.join(ev, "provenance.json")))
            self.assertGreaterEqual(len(prov["skills"]), 1)
            # standalone: every row reports no dispatch, no crash
            for row in prov["skills"]:
                self.assertFalse(row["dispatched"])

    def test_cli_build_with_profile(self):
        """--profile tailors the deliverable and still passes gates."""
        profile = os.path.join(ROLES_REPO, "profiles", "example-airframer.json")
        if not os.path.exists(profile):
            self.skipTest("example profile not present")
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "report.md")
            env = dict(os.environ, AEROSKILLS_DEV="/nonexistent")
            r = subprocess.run(
                [sys.executable, os.path.join(ROLE_DIR, "cli.py"), "build",
                 "--out", out, "--profile", profile],
                cwd=ROLE_DIR, env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            md = open(out).read()
            self.assertIn("Program context (profile)", md)
            gates = check_report_markdown(md)
            self.assertTrue(gates["all_pass"], gates)


if __name__ == "__main__":
    unittest.main()
