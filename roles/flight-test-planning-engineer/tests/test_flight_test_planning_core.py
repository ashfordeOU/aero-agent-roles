#!/usr/bin/env python3
"""Test flight_test_planning_core: the executable engine of the Flight
Test Planning Engineer role.

Author: ashfordeOU · Aero Agent Roles.

Proves the role can DO its job standalone (no AeroSkills needed):
Nyquist-rate instrumentation sizing, PCM frame and bit rate arithmetic,
super/subcommutation assignment, IRIG-B time coding, latency/link/
quality verdicts, decommutation frame period arithmetic, compressible
airspeed PEC relations, EPNL integration and the cumulative margin
rule, test matrix grid expansion with repeats and steady-state
validation, build-up ordering and go/no-go gating, plan generation,
and evidence-gate checks.

Real anchors are taken from the bound flight-test-operations/planning
leaves' worked examples: fs_req = 2.5 * 2 * fmax (5 x fmax);
64 words x 16 bits = 1024 bits/frame; 50 frames/s -> 51200 bit/s;
IRIG-B day 32 at 43200 s -> 2721600 s; frame period 8 data + 1 idle
= 10 words; tower fly-by 500 m / 490 m / 288.15 K -> dVp +0.88 m/s;
GPS doublet 98/102 m/s -> 100 m/s TAS and 94.87 m/s CAS at
rho/rho0 0.9; constant 90 dB PNLT run -> EPNL 93.0103 EPNdB;
cumulative margins [3, 4, 4] sum to 11.0 EPNdB (pass, required 10.0);
grid of 2 altitudes x 3 speeds x 1 weight x 2 configurations = 12
points with repeats at tp5 and tp10.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from flight_test_planning_core import (  # noqa: E402
    NOISE_CUMULATIVE_REQUIRED_DB, PEC_COVERAGE_MIN, PEC_RESIDUAL_RMS_MAX,
    add_repeat_points, build_flight_test_plan, build_test_matrix,
    build_up_order, calibrated_airspeed, calibration_verdict,
    check_flight_test_plan, check_flight_test_plan_markdown,
    conditioning_verdict, cumulative_margin, epnl_from_pnlt,
    example_item, example_plan_markdown, frame_period_words, go_no_gate,
    gps_doublet_tas, ground_link_ok, impact_pressure_from_cas,
    instrumentation_complete, irig_b_time_of_year, latency_buffer_samples,
    latency_ok, margin_to_limit, noise_geometry, noise_test_matrix,
    nyquist_ok, pcm_bit_rate, pcm_frame_size, position_error,
    quantization_error, render_flight_test_plan_markdown,
    required_sample_rate, sensor_range_verdict, sequence_for_efficiency,
    steady_state_check, subcommutated_instances,
    supercommutated_instances, tas_to_cas, telemetry_quality_ok,
    total_latency, tower_flyby_position_error,
)
from flight_test_planning_core import (  # noqa: E402  (alias: pytest would
    test_matrix_complete as matrix_coverage_check,  # collect any module attr
)                                                  # named test_* as a test)


class TestInstrumentation(unittest.TestCase):

    def test_nyquist_criterion(self):
        self.assertTrue(nyquist_ok(100.0, 20.0))
        self.assertTrue(nyquist_ok(40.0, 20.0))   # exactly at Nyquist
        self.assertFalse(nyquist_ok(39.0, 20.0))  # below -> aliasing
        with self.assertRaises(ValueError):
            nyquist_ok(0.0, 20.0)

    def test_required_sample_rate_default_margin(self):
        # fs_req = margin * 2 * fmax, default margin 2.5 (5 x fmax)
        self.assertEqual(required_sample_rate(20.0), 100.0)
        self.assertEqual(required_sample_rate(10.0), 50.0)
        self.assertEqual(required_sample_rate(10.0, margin=2.0), 40.0)
        with self.assertRaises(ValueError):
            required_sample_rate(-1.0)

    def test_sensor_range_verdict(self):
        self.assertEqual(sensor_range_verdict(90000.0, 110000.0), "ok")
        self.assertEqual(sensor_range_verdict(110000.0, 110000.0), "ok")
        self.assertEqual(sensor_range_verdict(110001.0, 110000.0),
                         "over-range")
        with self.assertRaises(ValueError):
            sensor_range_verdict(1.0, 0.0)

    def test_quantization_error(self):
        # 10 V span / 2^16 = 1.52587890625e-4 V per LSB
        self.assertAlmostEqual(quantization_error(16, 10.0),
                               1.52587890625e-4)
        with self.assertRaises(ValueError):
            quantization_error(0, 10.0)

    def test_calibration_verdict(self):
        self.assertTrue(calibration_verdict(True, False))
        self.assertFalse(calibration_verdict(True, True))
        self.assertFalse(calibration_verdict(False, False))
        with self.assertRaises(ValueError):
            calibration_verdict("yes", False)


class TestTelemetry(unittest.TestCase):

    def test_pcm_frame_size_and_bit_rate(self):
        self.assertEqual(pcm_frame_size(64, 16), 1024)
        self.assertEqual(pcm_bit_rate(50.0, 64, 16), 51200.0)
        with self.assertRaises(ValueError):
            pcm_frame_size(0, 16)

    def test_supercommutation(self):
        self.assertEqual(supercommutated_instances(200.0, 50.0), 4)
        with self.assertRaises(ValueError):
            supercommutated_instances(175.0, 50.0)   # 3.5, non-integer
        with self.assertRaises(ValueError):
            supercommutated_instances(50.0, 50.0)    # not > 1

    def test_subcommutation(self):
        self.assertEqual(subcommutated_instances(50.0, 12.5), 4)
        with self.assertRaises(ValueError):
            subcommutated_instances(50.0, 20.0)      # non-integer

    def test_irig_time_of_year(self):
        # (day 32 - 1) * 86400 + 43200 = 2721600 s
        self.assertEqual(irig_b_time_of_year(32, 43200.0), 2721600.0)
        with self.assertRaises(ValueError):
            irig_b_time_of_year(0, 0.0)

    def test_conditioning(self):
        self.assertEqual(conditioning_verdict(4.0, 2.0, 10.0), "ok")
        self.assertEqual(conditioning_verdict(4.0, 3.0, 10.0), "over-range")

    def test_latency(self):
        self.assertEqual(total_latency(5.0, 10.0, 25.0), 40.0)
        self.assertTrue(latency_ok(40.0, 50.0))
        self.assertTrue(latency_ok(50.0, 50.0))
        self.assertFalse(latency_ok(51.0, 50.0))
        self.assertEqual(latency_buffer_samples(0.05, 200.0), 10)
        self.assertEqual(latency_buffer_samples(0.05, 201.0), 11)

    def test_ground_link(self):
        self.assertTrue(ground_link_ok(-95.0, -110.0, 10.0))
        self.assertFalse(ground_link_ok(-104.9, -110.0, 10.0))

    def test_telemetry_quality(self):
        self.assertTrue(telemetry_quality_ok(1.0e-5, 0.5, 1.0e-4, 1.0))
        self.assertFalse(telemetry_quality_ok(2.0e-4, 0.5, 1.0e-4, 1.0))
        self.assertFalse(telemetry_quality_ok(1.0e-5, 1.5, 1.0e-4, 1.0))


class TestDecommutation(unittest.TestCase):

    def test_frame_period_words(self):
        self.assertEqual(frame_period_words(8, 1), 10)
        self.assertEqual(frame_period_words(8, 0), 9)
        with self.assertRaises(ValueError):
            frame_period_words(-1, 0)


class TestPositionErrorCalibration(unittest.TestCase):

    def test_compressible_identity(self):
        qc = impact_pressure_from_cas(100.0)
        self.assertAlmostEqual(qc, 6258.4, delta=0.5)   # leaf: 6258.4 Pa
        self.assertAlmostEqual(calibrated_airspeed(qc), 100.0, delta=1e-6)
        self.assertAlmostEqual(position_error(100.0, 100.0), 0.0,
                               delta=1e-9)

    def test_tower_flyby_worked_example(self):
        # 500 m geometric, 490 m altimeter (10 m low), 288.15 K
        dvp = tower_flyby_position_error(500.0, 490.0, 288.15)
        self.assertAlmostEqual(dvp, 0.88, places=2)     # leaf: +0.88 m/s
        # altimeter 10 m high flips the sign (leaf: -0.89 m/s)
        dvp_high = tower_flyby_position_error(500.0, 510.0, 288.15)
        self.assertAlmostEqual(dvp_high, -0.89, places=2)
        self.assertLess(dvp_high, 0.0)
        # pass-speed sensitivity (leaf: 0.99 @ 90 m/s, 0.72 @ 120 m/s)
        self.assertAlmostEqual(
            tower_flyby_position_error(500.0, 490.0, 288.15, 90.0),
            0.99, places=2)
        self.assertAlmostEqual(
            tower_flyby_position_error(500.0, 490.0, 288.15, 120.0),
            0.72, places=2)
        # zero height error -> zero correction
        self.assertAlmostEqual(
            tower_flyby_position_error(500.0, 500.0, 288.15),
            0.0, delta=1e-9)

    def test_gps_doublet_worked_example(self):
        self.assertEqual(gps_doublet_tas(98.0, 102.0), 100.0)
        self.assertAlmostEqual(tas_to_cas(100.0, 0.9), 94.8683, places=3)
        self.assertAlmostEqual(position_error(100.0, tas_to_cas(100.0, 0.9)),
                               -5.13, places=2)


class TestNoiseCertification(unittest.TestCase):

    def test_reference_geometry(self):
        fly = noise_geometry("flyover")
        self.assertEqual(fly["distance_m"], 6500.0)
        side = noise_geometry("sideline")
        self.assertEqual(side["lateral_m"], 450.0)
        app = noise_geometry("approach")
        self.assertEqual(app["distance_m"], 1200.0)
        self.assertEqual(app["altitude_m"], 120.0)
        self.assertEqual(app["glide_deg"], 3.0)
        with self.assertRaises(ValueError):
            noise_geometry("hover")

    def test_epnl_constant_run_closed_form(self):
        # 41 x 90 dB at 0.5 s -> 90 + 10*log10(20/10) = 93.0103 EPNdB
        epnl, t0, t1, truncated = epnl_from_pnlt([90.0] * 41, 0.5)
        self.assertAlmostEqual(epnl, 93.0103, places=4)
        self.assertAlmostEqual(t0, 0.0)
        self.assertAlmostEqual(t1, 20.0)
        self.assertFalse(truncated)

    def test_margin_to_limit(self):
        margin, verdict = margin_to_limit(93.01, 95.0)
        self.assertAlmostEqual(margin, 1.99, places=2)
        self.assertEqual(verdict, "pass")
        self.assertEqual(margin_to_limit(96.0, 95.0)[1], "fail")

    def test_cumulative_margin_rule(self):
        self.assertEqual(NOISE_CUMULATIVE_REQUIRED_DB, 10.0)
        ok = cumulative_margin([3.0, 4.0, 4.0])
        self.assertEqual(ok["sum_db"], 11.0)
        self.assertEqual(ok["verdict"], "pass")
        short = cumulative_margin([3.0, 3.0, 3.0])
        self.assertEqual(short["verdict"], "fail")     # sum 9 < 10
        neg = cumulative_margin([-1.0, 6.0, 6.0])
        self.assertEqual(neg["verdict"], "fail")       # negative margin

    def test_noise_test_matrix(self):
        rows = noise_test_matrix(78000.0, 62000.0, 155.0, 135.0,
                                 {"flyover": 89.0, "sideline": 94.0,
                                  "approach": 98.0})
        self.assertEqual(len(rows), 3)
        by = {r["condition"]: r for r in rows}
        self.assertEqual(by["flyover"]["reference_speed_kt"], 165.0)  # V2+10
        self.assertEqual(by["sideline"]["reference_speed_kt"], 155.0)
        self.assertEqual(by["approach"]["configuration"], "landing")
        self.assertEqual(by["approach"]["limit"], 98.0)
        self.assertEqual(by["flyover"]["target_epnl"], 89.0)


class TestMatrixAndPlanning(unittest.TestCase):

    def test_grid_expansion_count_and_order(self):
        grid = build_test_matrix([1500.0, 3000.0], [110.0, 130.0, 150.0],
                                 [55000.0], ["clean", "takeoff"])
        self.assertEqual(grid["count"], 12)
        self.assertEqual(grid["points"][0]["id"], "tp1")
        self.assertEqual(grid["points"][0]["configuration"], "clean")
        self.assertEqual(grid["points"][1]["configuration"], "takeoff")
        self.assertEqual(grid["points"][6]["altitude"], 3000.0)

    def test_repeat_marking(self):
        grid = build_test_matrix([1500.0, 3000.0], [110.0, 130.0, 150.0],
                                 [55000.0], ["clean", "takeoff"])
        points = add_repeat_points(grid["points"], 5)
        repeats = [p["id"] for p in points if p["repeat"]]
        self.assertEqual(repeats, ["tp5", "tp10"])
        with self.assertRaises(ValueError):
            add_repeat_points(grid["points"], 1)

    def test_efficiency_sequence(self):
        grid = build_test_matrix([1500.0, 3000.0], [110.0, 130.0, 150.0],
                                 [55000.0], ["clean", "takeoff"])
        seq = sequence_for_efficiency(grid["points"])
        ids = [p["id"] for p in seq]
        self.assertEqual(ids[:3], ["tp1", "tp3", "tp5"])   # clean, 1500 m
        self.assertEqual(ids[6], "tp2")                    # takeoff opens

    def test_steady_state_check(self):
        grid = build_test_matrix([1500.0, 3000.0], [110.0, 130.0, 150.0],
                                 [55000.0], ["clean", "takeoff"])
        tol = {"altitude": 30.0, "speed": 2.0, "weight": 500.0}
        observed = {p["id"]: {"altitude": p["altitude"],
                              "speed": p["speed"],
                              "weight": p["weight"]}
                    for p in grid["points"]}
        res = steady_state_check(grid["points"], tol, observed)
        self.assertEqual(res["verdict"], "all-valid")
        self.assertEqual(len(res["valid"]), 12)
        bad = dict(observed)
        bad["tp1"] = {"altitude": 1500.0, "speed": 116.0, "weight": 55000.0}
        res2 = steady_state_check(grid["points"], tol, bad)
        self.assertEqual(res2["verdict"], "invalid-points")
        self.assertEqual(res2["invalid"], ["tp1"])

    def test_build_up_order(self):
        blocks = [{"id": "B2", "risk": 2, "prerequisites": ["B1"]},
                  {"id": "B1", "risk": 1, "prerequisites": []},
                  {"id": "B3", "risk": 1, "prerequisites": []}]
        out = build_up_order(blocks)
        self.assertEqual([b["id"] for b in out["ordered"]],
                         ["B1", "B3", "B2"])   # ties keep input order
        self.assertEqual(out["verdict"], "ok")
        broken = [{"id": "X", "risk": 1, "prerequisites": ["ghost"]}]
        out2 = build_up_order(broken)
        self.assertEqual(out2["verdict"], "missing-prerequisites")
        self.assertEqual(out2["missing_prerequisites"][0]["point"], "X")

    def test_go_no_gate(self):
        res = go_no_gate(True, True, True, True)
        self.assertEqual(res["verdict"], "GO")
        self.assertEqual(res["blockers"], [])
        res2 = go_no_gate(True, True, False, True)
        self.assertEqual(res2["verdict"], "NO-GO")
        self.assertEqual(res2["blockers"], ["instrumentation_ok"])
        with self.assertRaises(ValueError):
            go_no_gate(True, True, "yes", True)

    def test_instrumentation_complete(self):
        res = instrumentation_complete(["a", "b"], ["a", "b", "c"])
        self.assertEqual(res["verdict"], "complete")
        res2 = instrumentation_complete(["a", "b"], ["a"])
        self.assertEqual(res2["verdict"], "incomplete")
        self.assertEqual(res2["missing"], ["b"])

    def test_matrix_coverage_complete(self):
        points = [{"id": "p1", "covers": ["OBJ-1"]},
                  {"id": "p2", "covers": ["OBJ-2"]}]
        res = matrix_coverage_check(points, ["OBJ-1", "OBJ-2"])
        self.assertEqual(res["verdict"], "complete")
        res2 = matrix_coverage_check(points, ["OBJ-1", "OBJ-2", "OBJ-3"])
        self.assertEqual(res2["verdict"], "incomplete")
        self.assertEqual(res2["uncovered"], ["OBJ-3"])


class TestPlanBuilder(unittest.TestCase):

    def test_example_model_numbers(self):
        model = build_flight_test_plan(example_item())
        self.assertEqual(model["document_type"],
                         "Flight Test Plan and Requirements Traceability")
        self.assertEqual(model["status"], "draft-for-review")
        # matrix: 2 x 3 x 1 x 2 = 12 points, repeats tp5/tp10
        self.assertEqual(model["matrix"]["count"], 12)
        self.assertEqual(model["matrix"]["repeat_ids"], ["tp5", "tp10"])
        self.assertEqual(len(model["matrix"]["efficiency_order"]), 12)
        self.assertEqual(model["matrix"]["steady_state"]["verdict"],
                         "all-valid")
        # telemetry chain numbers
        self.assertEqual(model["telemetry"]["frame"]["frame_size_bits"],
                         1024)
        self.assertAlmostEqual(model["telemetry"]["stream"]["bit_rate"],
                               51200.0)
        self.assertEqual(model["telemetry"]["irig"]["seconds_of_year"],
                         2721600.0)
        self.assertAlmostEqual(model["telemetry"]["latency"]["total_ms"],
                               40.0)
        self.assertTrue(model["telemetry"]["latency"]["ok"])
        self.assertAlmostEqual(model["telemetry"]["link"]["margin_db"],
                               15.0)
        self.assertTrue(model["telemetry"]["link"]["ok"])
        self.assertTrue(model["telemetry"]["quality"]["ok"])
        # decommutation plan numbers
        self.assertEqual(model["decommutation"]["period_words"], 10)
        self.assertEqual(model["decommutation"]["frames_expected"], 180000)
        by_ch = {r["channel"]: r for r in model["decommutation"]["layout"]}
        self.assertEqual(by_ch["A2"]["samples"], 360000)
        self.assertEqual(by_ch["S"]["samples_per_subframe_id"], 45000)
        # PEC acceptance and noise rules
        self.assertAlmostEqual(
            model["pec"]["acceptance"]["coverage_min"], PEC_COVERAGE_MIN)
        self.assertAlmostEqual(model["pec"]["acceptance"]["residual_rms_max"],
                               PEC_RESIDUAL_RMS_MAX)
        self.assertAlmostEqual(
            model["noise"]["acceptance"]["cumulative_required_db"],
            NOISE_CUMULATIVE_REQUIRED_DB)
        self.assertEqual(len(model["noise"]["geometry"]), 3)
        self.assertEqual(len(model["noise"]["matrix_rows"]), 3)
        # build-up and gate
        self.assertEqual(model["build_up"]["verdict"], "ok")
        self.assertEqual(model["build_up"]["max_risk"], 3)
        self.assertEqual(model["go_no_go"]["verdict"], "GO")
        # traceability
        self.assertEqual(model["traceability"]["objective_verdict"],
                         "complete")
        self.assertEqual(model["traceability"]["requirement_verdict"],
                         "trace-complete")
        self.assertEqual(
            model["traceability"]["requirement_status_counts"]["planned"], 6)
        # instrumentation released with current calibration
        self.assertEqual(model["instrumentation"]["release"]["verdict"],
                         "released")
        # validation cards all pass
        self.assertTrue(model["validation_cards_all_pass"])
        self.assertEqual(len(model["validation_cards"]), 15)

    def test_markdown_sections_and_markers(self):
        md = example_plan_markdown()
        for n in range(1, 13):
            self.assertIn("## %d. " % n, md, "section %d missing" % n)
        self.assertIn("draft", md.lower())
        self.assertIn("not an approval", md.lower())
        self.assertGreater(len(md), 12000)

    def test_core_gates_all_pass(self):
        model = build_flight_test_plan(example_item())
        gates = check_flight_test_plan(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_risk_level_gate(self):
        model = build_flight_test_plan(example_item())
        self.assertTrue(check_flight_test_plan(model, risk_level=3)[
            "risk_level_3_covered"])
        g5 = check_flight_test_plan(model, risk_level=5)
        self.assertFalse(g5["risk_level_5_covered"])
        self.assertFalse(g5["all_pass"])

    def test_markdown_gates_all_pass(self):
        gates = check_flight_test_plan_markdown(example_plan_markdown())
        self.assertTrue(gates["all_pass"], gates)
        g3 = check_flight_test_plan_markdown(example_plan_markdown(),
                                             risk_level=3)
        self.assertTrue(g3["risk_level_3_covered"])
        g5 = check_flight_test_plan_markdown(example_plan_markdown(),
                                             risk_level=5)
        self.assertFalse(g5["risk_level_5_covered"])

    def test_failing_instrumentation_flips_gate(self):
        item = example_item()
        item.channels = [dict(c) for c in item.channels]
        item.channels[0]["cal_due"] = True
        model = build_flight_test_plan(item)
        self.assertEqual(model["instrumentation"]["release"]["verdict"],
                         "not-released")
        gates = check_flight_test_plan(model)
        self.assertFalse(gates["instrumentation_released"])
        self.assertFalse(gates["all_pass"])

    def test_standalone_no_skills_repo(self):
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = build_flight_test_plan(example_item())
        self.assertEqual(model["matrix"]["count"], 12)
        md = render_flight_test_plan_markdown(model)
        self.assertGreater(len(md), 12000)
        self.assertTrue(check_flight_test_plan_markdown(md)["all_pass"])


if __name__ == "__main__":
    unittest.main()
