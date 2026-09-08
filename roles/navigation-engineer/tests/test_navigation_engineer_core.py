#!/usr/bin/env python3
"""Test navigation_engineer_core: the executable engine of the
Navigation Engineer.

Proves the role can DO its job standalone (no AeroSkills needed):
WGS84 frame geodesy, INS coasting error growth, GNSS pseudorange
least-squares fix with DOP, RAIM/FDE fault detection, carrier
smoothing, Doppler velocity, RTK integer ambiguity resolution,
INS-GNSS Kalman integration, TERCOM/SITAN terrain-referenced
navigation, bearing-only localization, report builder + evidence
gates, and standalone mode.
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from navigation_engineer_core import (  # noqa: E402
    LAMBDA_L1, WGS84_A, WGS84_F, bearing_only_wls_fix, build_report,
    check_report, check_report_markdown, compute_dops,
    example_item, example_project, example_report_markdown,
    gyro_drift_position_error, accel_bias_position_error, geodetic_to_ecef,
    ins_coasting_error_growth, measurement_update, predict_step,
    raim_fault_detection, render_report_markdown, rtk_ambiguity_search,
    rtk_float_solve, rtk_fixed_baseline_solve, state_transition_matrix,
    tercom_match, terrain_height,
)

# Deterministic across midnight: pin fresh renders to the date the
# committed template carries (CI override wins).
os.environ.setdefault("ROLE_GEN_DATE", "2026-09-08")


class TestCoreDomainRules(unittest.TestCase):
    """Public-standard anchors mirrored from the bound AeroSkills leaves."""

    def test_wgs84_geodesy_anchor(self):
        # Equator, prime meridian, sea level -> ECEF (a, 0, 0).
        x, y, z = geodetic_to_ecef(0.0, 0.0, 0.0)
        self.assertAlmostEqual(x, WGS84_A, delta=1e-6)
        self.assertAlmostEqual(y, 0.0, delta=1e-6)
        self.assertAlmostEqual(z, 0.0, delta=1e-6)
        # Pole -> ECEF z = polar radius b = a*(1-f) (navigation-frames).
        _, _, zp = geodetic_to_ecef(math.pi / 2.0, 0.0, 0.0)
        self.assertAlmostEqual(zp, WGS84_A * (1.0 - WGS84_F), delta=1e-6)

    def test_ins_coasting_error_growth_anchor(self):
        # dx = 0.5*b*t^2: bias 1e-3 m/s^2, t=60s -> 1.8 m (leaf anchor).
        self.assertAlmostEqual(accel_bias_position_error(1e-3, 60.0), 1.8,
                               delta=1e-9)
        # dx = (1/6)*g*eps*t^3: eps=1e-4 rad/s, t=60s -> 35.3039 m.
        self.assertAlmostEqual(gyro_drift_position_error(1e-4, 60.0),
                               35.3039, delta=1e-3)
        result = ins_coasting_error_growth(1e-3, 20.6264806, 0.3, 60.0)
        self.assertAlmostEqual(result["total_position_1sigma_m"],
                               math.hypot(1.8, 35.3039), delta=1e-2)
        self.assertGreater(result["accel_bias_position_error_m"], 0.0)
        self.assertGreater(result["gyro_drift_position_error_m"], 0.0)
        # Error grows monotonically with outage duration.
        shorter = ins_coasting_error_growth(1e-3, 20.6264806, 0.3, 30.0)
        longer = ins_coasting_error_growth(1e-3, 20.6264806, 0.3, 120.0)
        self.assertLess(shorter["total_position_1sigma_m"],
                        result["total_position_1sigma_m"])
        self.assertLess(result["total_position_1sigma_m"],
                        longer["total_position_1sigma_m"])
        with self.assertRaises(ValueError):
            ins_coasting_error_growth(1e-3, 5.0, 0.3, 0.0)

    def test_pseudorange_fix_converges(self):
        model = build_report(example_project())
        g = model["gnss_fix"]
        self.assertGreater(g["iterations"], 0)
        self.assertLessEqual(g["iterations"], 8)
        # Recovered clock bias must track the true injected bias closely.
        self.assertAlmostEqual(g["clock_bias_m"], g["true_clock_bias_m"],
                               delta=5.0)
        self.assertLess(g["sse"], 50.0)

    def test_dop_values_sane(self):
        az_el = [(45.0, 60.0), (135.0, 55.0), (225.0, 50.0), (315.0, 45.0),
                 (60.0, 25.0), (280.0, 20.0)]
        unit_enu = []
        for az, el in az_el:
            a, e = math.radians(az), math.radians(el)
            unit_enu.append((math.cos(e) * math.sin(a),
                             math.cos(e) * math.cos(a), math.sin(e)))
        dops = compute_dops(unit_enu)
        for key in ("gdop", "pdop", "hdop", "vdop", "tdop"):
            self.assertGreater(dops[key], 0.0)
        # PDOP <= GDOP (position-only subset of the full geometry+clock
        # covariance) and PDOP^2 = HDOP^2 + VDOP^2 by construction.
        self.assertLessEqual(dops["pdop"], dops["gdop"] + 1e-9)
        self.assertAlmostEqual(dops["pdop"] ** 2,
                               dops["hdop"] ** 2 + dops["vdop"] ** 2,
                               delta=1e-6)
        with self.assertRaises(ValueError):
            compute_dops(unit_enu[:3])

    def test_raim_detects_fault_on_faulted_set(self):
        az_el = [(45.0, 60.0), (135.0, 55.0), (225.0, 50.0), (315.0, 45.0),
                 (60.0, 25.0), (280.0, 20.0)]
        h = []
        for az, el in az_el:
            a, e = math.radians(az), math.radians(el)
            h.append([math.cos(e) * math.sin(a), math.cos(e) * math.cos(a),
                     math.sin(e), 1.0])
        y_clean = [0.3, -0.4, 0.2, -0.1, 0.35, -0.25]
        clean = raim_fault_detection(h, y_clean, sigma=6.0)
        self.assertFalse(clean["fault_detected"])
        self.assertLess(clean["test_statistic"], clean["threshold"])

        y_fault = list(y_clean)
        y_fault[0] += 80.0
        faulted = raim_fault_detection(h, y_fault, sigma=6.0)
        self.assertTrue(faulted["fault_detected"])
        self.assertGreater(faulted["test_statistic"], faulted["threshold"])

    def test_rtk_ambiguity_search_recovers_known_integers(self):
        # A well-spread synthetic pass (unlike a slowly-drifting real
        # pass) with a known integer baseline: the search must recover
        # the exact true integer cycles on a clean baseline.
        az_el_epochs = [
            [(30.0, 70.0), (140.0, 40.0), (260.0, 55.0)],
            [(80.0, 60.0), (190.0, 35.0), (310.0, 50.0)],
            [(10.0, 45.0), (150.0, 65.0), (240.0, 30.0)],
            [(100.0, 50.0), (200.0, 55.0), (320.0, 40.0)],
        ]
        true_baseline = (5.0, 3.0, 1.0)
        true_cycles = (4.0, -2.0)
        m = len(az_el_epochs[0]) - 1
        h_rows, y_rows = [], []
        for ei, ael in enumerate(az_el_epochs):
            u_list = []
            for az, el in ael:
                a, e = math.radians(az), math.radians(el)
                u_list.append((math.cos(e) * math.sin(a),
                              math.cos(e) * math.cos(a), math.sin(e)))
            u_ref = u_list[0]
            for j in range(1, len(u_list)):
                du = tuple(u_list[j][k] - u_ref[k] for k in range(3))
                row = [-du[0], -du[1], -du[2]] + [0.0] * m
                row[3 + (j - 1)] = -LAMBDA_L1
                true_dd = -sum(du[k] * true_baseline[k] for k in range(3)) \
                    - LAMBDA_L1 * true_cycles[j - 1]
                noise = 0.001 * LAMBDA_L1 * (1 if ((ei + j) % 2) else -1)
                h_rows.append(row)
                y_rows.append(true_dd + noise)

        float_sol = rtk_float_solve(h_rows, y_rows)
        for k in range(3):
            self.assertAlmostEqual(float_sol["x"][k], true_baseline[k],
                                   delta=0.01)
        search = rtk_ambiguity_search(float_sol["x"], float_sol["cov"], 3,
                                      radius=2)
        self.assertTrue(search["resolved"])
        self.assertEqual(search["fixed_cycles"], (4, -2))
        self.assertGreaterEqual(search["ratio"], 3.0)

        h_base = [row[:3] for row in h_rows]
        y_fixed = []
        idx = 0
        for ael in az_el_epochs:
            for j in range(1, len(ael)):
                y_fixed.append(y_rows[idx] +
                               LAMBDA_L1 * search["fixed_cycles"][j - 1])
                idx += 1
        fixed = rtk_fixed_baseline_solve(h_base, y_fixed)
        for k in range(3):
            self.assertAlmostEqual(fixed["baseline_m"][k], true_baseline[k],
                                   delta=0.01)

    def test_ins_gnss_integration_covariance_shrinks(self):
        x0 = [30.0, 30.0, 0.05, 0.0, 0.001]
        p0 = [[0.0] * 5 for _ in range(5)]
        for i, v in enumerate([900.0, 900.0, 0.01, 0.01, 1e-6]):
            p0[i][i] = v
        q = [[0.0] * 5 for _ in range(5)]
        q[0][0] = q[1][1] = 1e-4
        q[2][2] = q[3][3] = 1e-3
        q[4][4] = 1e-8
        phi = state_transition_matrix(0.2, 0.05, 1.0)
        x_pred, p_pred = predict_step(x0, p0, phi, q)
        self.assertGreaterEqual(p_pred[0][0], p0[0][0])
        h = [[1.0, 0.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0, 0.0]]
        r = [[9.0, 0.0], [0.0, 9.0]]
        x_upd, p_upd, innov = measurement_update(x_pred, p_pred, [0.0, 0.0],
                                                  h, r)
        self.assertLess(p_upd[0][0], p_pred[0][0])
        self.assertLess(p_upd[1][1], p_pred[1][1])
        self.assertTrue(all(math.isfinite(v) for v in x_upd))

    def test_tercom_offset_recovery(self):
        n_samp = 10
        dt = 90.0 / (n_samp - 1)
        track_true = [(25.0 * i * dt, 0.0) for i in range(n_samp)]
        true_offset = (50.0, -25.0)
        track_ins = [(x + true_offset[0], y + true_offset[1])
                    for (x, y) in track_true]
        measured = [terrain_height(x, y) for (x, y) in track_true]
        step, hw = 25.0, 2
        candidates = [(i * step, j * step) for i in range(-hw, hw + 1)
                     for j in range(-hw, hw + 1)]
        tercom = tercom_match(measured, track_ins, candidates)
        self.assertAlmostEqual(tercom["best"]["dx"], true_offset[0],
                               delta=step)
        self.assertAlmostEqual(tercom["best"]["dy"], true_offset[1],
                               delta=step)
        self.assertGreater(tercom["best"]["r"], 0.99)

    def test_bearing_only_fix_finite(self):
        observers = [(0.0, 0.0), (1800.0, 200.0), (900.0, 1600.0)]
        target = (950.0, 700.0)
        bearings = [math.degrees(math.atan2(target[1] - oy, target[0] - ox))
                   % 360.0 for ox, oy in observers]
        fix = bearing_only_wls_fix(observers, bearings, 1.5)
        self.assertTrue(math.isfinite(fix["x_m"]))
        self.assertTrue(math.isfinite(fix["y_m"]))
        self.assertAlmostEqual(fix["x_m"], target[0], delta=1.0)
        self.assertAlmostEqual(fix["y_m"], target[1], delta=1.0)
        with self.assertRaises(ValueError):
            bearing_only_wls_fix(observers[:1], bearings[:1], 1.5)


class TestReportBuilder(unittest.TestCase):

    def test_example_report_gates_pass(self):
        model = build_report(example_item())
        self.assertEqual(model["status"], "draft-for-review")
        self.assertGreater(model["ins"]["total_position_1sigma_m"], 0.0)
        self.assertGreater(model["gnss_fix"]["dops"]["pdop"], 0.0)
        gates = check_report(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_example_markdown_complete(self):
        md = example_report_markdown()
        for sec in ["## 1. Frames and geodesy", "## 3. GNSS epoch solution",
                    "## 5. RTK", "## 7. GNSS-denied segment",
                    "## 9. Integrated error budget and verdict"]:
            self.assertIn(sec, md)
        low = md.lower()
        self.assertIn("draft", low)
        self.assertIn("not an approval", low)
        self.assertIn("not flight software release", low)
        self.assertIn("wgs84", low)
        self.assertIn("m/s", md)
        self.assertNotIn("___", md)

    def test_markdown_gates_all_pass(self):
        md = example_report_markdown()
        gates = check_report_markdown(md)
        self.assertTrue(gates["all_pass"], gates)

    def test_standalone_no_skills_repo(self):
        # Core must work with no AeroSkills present.
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        item = example_item()
        model = build_report(item)
        self.assertEqual(model["status"], "draft-for-review")
        md = render_report_markdown(model)
        self.assertGreater(len(md), 3000)
        self.assertTrue(check_report(model)["all_pass"])

    def test_check_report_gate_pass_and_fail(self):
        good = build_report(example_item())
        gates = check_report(good)
        self.assertTrue(gates["all_pass"], gates)

        tampered = build_report(example_item())
        tampered["status"] = "approved"
        self.assertFalse(check_report(tampered)["sign_off_honest"])
        self.assertFalse(check_report(tampered)["all_pass"])

        tampered2 = build_report(example_item())
        tampered2["budget"]["ok"] = False
        self.assertFalse(check_report(tampered2)["position_budget_met"])
        self.assertFalse(check_report(tampered2)["all_pass"])

    def test_check_report_markdown_gate_fail_on_blank_field(self):
        md = example_report_markdown()
        tampered_md = md.replace("navigation-engineering lead review",
                                 "___")
        gates = check_report_markdown(tampered_md)
        self.assertFalse(gates["no_blank_fields"])
        self.assertFalse(gates["all_pass"])

    def test_rtk_ambiguities_recovered_in_example(self):
        # Regression guard: the example project's RTK integer search
        # must land on the true injected ambiguities, not just report
        # a ratio > threshold on the wrong integers.
        model = build_report(example_item())
        rtk = model["rtk"]
        self.assertEqual(tuple(round(v) for v in rtk["fixed_cycles"]),
                         tuple(int(v) for v in rtk["true_cycles"]))
        self.assertTrue(rtk["ambiguity_resolved"])
        for k in range(3):
            self.assertAlmostEqual(rtk["baseline_enu_m"][k],
                                   rtk["true_baseline_enu_m"][k], delta=0.5)

    def test_model_json_roundtrip(self):
        import json
        model = build_report(example_item())
        text = json.dumps(model)
        back = json.loads(text)
        self.assertEqual(back["document_type"],
                         "Navigation Architecture and Position Error "
                         "Analysis Report")
        self.assertIn("rtk", back)


if __name__ == "__main__":
    unittest.main()
