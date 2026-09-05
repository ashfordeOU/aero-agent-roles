#!/usr/bin/env python3
"""Test flight_test_core: the executable engine of the flight-test-engineer role.

Proves the role can DO its job standalone (no AeroSkills needed):
V-speed margins, corner speed, stall warning/recovery rules, flutter
build-up with the damping requirement and margin ratio, altitude/Mach
grid, safety/go-no-go, deliverable generation, and evidence-gate checks.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from flight_test_core import (
    MIN_DAMPING, MIN_FREQ_SEPARATION, accelerated_stall_speed,
    build_flight_test_deliverable, check_flight_test_deliverable,
    check_flight_test_markdown, classify_airspeed, corner_speed,
    damping_margin, example_aircraft, example_deliverable_markdown,
    example_flight_data, flutter_margin_ratio, flutter_required_speed,
    flutter_speed_from_damping, frequency_separation, isa_density_ratio,
    level_turn_load_factor, mach_grid_row, render_flight_test_markdown,
    risk_index, speed_block_targets, stall_recovery_verdict,
    stall_warning_required, stall_warning_verdict, v_speeds,
)


class TestDomainRules(unittest.TestCase):

    def test_v_speed_factors(self):
        ac = example_aircraft()
        s = v_speeds(ac)
        # vref = 1.3*vs0 = 46.8, v2 = 1.2*vs1 = 48.0, vr = 1.1*vs1 = 44.0
        self.assertAlmostEqual(s["vref"], 46.8, places=3)
        self.assertAlmostEqual(s["v2"], 48.0, places=3)
        self.assertAlmostEqual(s["vr"], 44.0, places=3)

    def test_corner_speed(self):
        # VA = VS * sqrt(n_max): 44 * sqrt(2.5)
        self.assertAlmostEqual(corner_speed(44.0, 2.5),
                               44.0 * 2.5 ** 0.5, places=3)
        with self.assertRaises(ValueError):
            corner_speed(0, 2.5)
        with self.assertRaises(ValueError):
            corner_speed(44.0, 1.0)

    def test_placard_ordering_validation(self):
        ac = example_aircraft()
        self.assertAlmostEqual(v_speeds(ac)["va"], corner_speed(44.0, 2.5))
        ac.vne_eas_ms = 50.0  # breaks vfe < va < vno < vne < vd
        with self.assertRaises(ValueError):
            build_flight_test_deliverable(ac)

    def test_airspeed_classification(self):
        ac = example_aircraft()
        va = v_speeds(ac)["va"]
        self.assertEqual(classify_airspeed(60, ac.vfe_eas_ms, va,
                                           ac.vno_eas_ms, ac.vne_eas_ms),
                         "below-vfe")
        self.assertEqual(classify_airspeed(90.1, ac.vfe_eas_ms, va,
                                           ac.vno_eas_ms, ac.vne_eas_ms),
                         "vno-to-vne")
        self.assertEqual(classify_airspeed(95.4, ac.vfe_eas_ms, va,
                                           ac.vno_eas_ms, ac.vne_eas_ms),
                         "at-or-above-vne")

    def test_stall_warning_margin(self):
        # 1.05 * VS1g or VS1g + 3 kt, whichever is greater
        req = stall_warning_required(44.0)
        self.assertAlmostEqual(req, max(44.0 * 1.05, 44.0 + 3 * 0.514444),
                               places=3)
        self.assertTrue(stall_warning_verdict(44.0, req + 0.1)["ok"])
        self.assertFalse(stall_warning_verdict(44.0, req - 0.1)["ok"])

    def test_accelerated_stall_and_bank(self):
        # 60 deg bank doubles load factor: stall rises ~41%
        n60 = level_turn_load_factor(60.0)
        self.assertAlmostEqual(n60, 2.0, places=4)
        v = accelerated_stall_speed(44.0, n60)
        self.assertAlmostEqual(v, 44.0 * 2.0 ** 0.5, places=3)
        with self.assertRaises(ValueError):
            accelerated_stall_speed(44.0, 0.9)

    def test_stall_recovery_verdict(self):
        ac = example_aircraft()
        good = stall_recovery_verdict(ac, 18.0, 3.0, 6.0)
        self.assertTrue(good["ok"])
        bad = stall_recovery_verdict(ac, 18.0, 12.0, 6.0)  # pitch-up excess
        self.assertFalse(bad["ok"])
        self.assertFalse(bad["pitch_up_ok"])

    def test_flutter_required_speed(self):
        ac = example_aircraft()
        self.assertAlmostEqual(flutter_required_speed(ac.vd_eas_ms),
                               1.2 * 106.0, places=3)

    def test_damping_margin_rule(self):
        self.assertTrue(damping_margin(0.100)["pass"])
        self.assertTrue(damping_margin(0.03)["pass"])  # boundary passes
        self.assertFalse(damping_margin(0.02)["pass"])
        self.assertEqual(MIN_DAMPING, 0.03)

    def test_frequency_separation(self):
        r = frequency_separation(11.6, 14.8)
        self.assertAlmostEqual(r["separation"], 3.2 / 13.2, places=3)
        self.assertTrue(r["pass"])
        self.assertEqual(MIN_FREQ_SEPARATION, 0.10)

    def test_flutter_extrapolation_and_margin(self):
        # simulated damping trend over the block speeds
        vf = flutter_speed_from_damping([90.1, 95.4, 100.7, 106.0],
                                        [0.120, 0.115, 0.108, 0.100])
        self.assertGreater(vf, 106.0 * 1.2)  # clears the 1.2 margin
        m = flutter_margin_ratio(vf, 106.0)
        self.assertTrue(m["pass"])
        with self.assertRaises(ValueError):
            flutter_speed_from_damping([90.1, 95.4], [0.1, 0.12])  # rising

    def test_risk_index_high_threshold(self):
        self.assertEqual(risk_index(5, 3), 15)     # high risk boundary
        self.assertEqual(risk_index(5, 2), 10)     # mitigated in example
        with self.assertRaises(ValueError):
            risk_index(6, 1)
        with self.assertRaises(ValueError):
            risk_index(0, 1)

    def test_mach_grid(self):
        g0 = mach_grid_row(example_aircraft(), 0.0, 106.0)
        self.assertAlmostEqual(g0["sigma"], 1.0, places=3)
        self.assertLess(g0["mach"], g0["mmo"])     # EAS-limited at SL
        # density ratio at 11000 m is the standard ~0.297 troposphere top
        self.assertAlmostEqual(isa_density_ratio(11000.0), 0.29707,
                               places=3)

    def test_speed_blocks_equal_steps_to_limit(self):
        blocks = speed_block_targets(106.0)
        fracs = [b["fraction"] for b in blocks]
        self.assertEqual(fracs, [0.85, 0.90, 0.95, 1.00])
        self.assertAlmostEqual(blocks[-1]["target_eas_ms"], 106.0)
        with self.assertRaises(ValueError):
            speed_block_targets(106.0, (0.85, 0.95, 1.00))  # uneven steps


class TestDeliverableBuilder(unittest.TestCase):

    def test_example_model_complete(self):
        model = build_flight_test_deliverable(example_aircraft())
        self.assertEqual(model["document_type"],
                         "Flight Test Plan and Envelope Expansion Report")
        self.assertEqual(model["status"], "draft-for-review")
        self.assertEqual(len(model["speed_blocks"]), 4)
        self.assertEqual(len(model["flutter"]["points"]), 4)
        self.assertEqual(len(model["stall_rows"]), 3)
        self.assertEqual(len(model["n_blocks"]), 3)
        self.assertTrue(model["flutter"]["pass"])
        self.assertTrue(model["stall_all_ok"])
        self.assertTrue(model["go_no_go"]["go"])
        self.assertTrue(model["safety_no_unmitigated"])

    def test_every_limit_change_traces_to_data_point(self):
        model = build_flight_test_deliverable(example_aircraft())
        for ch in model["limit_changes"]:
            self.assertTrue(ch["data_point"])
            self.assertTrue(ch["ok"])
        # each change maps to a real block id
        ids = {b["id"] for b in model["speed_blocks"]}
        for ch in model["limit_changes"]:
            self.assertIn(ch["data_point"], ids)

    def test_markdown_has_all_sections(self):
        md = example_deliverable_markdown()
        for sec in ["## 1. Objectives", "## 2. Safety", "## 3. Build-up",
                    "## 4. Results", "## 5. Findings", "## 6. Sign-off",
                    "### 3.2 Altitude / Mach grid", "### 4.1 Flutter"]:
            self.assertIn(sec, md)
        self.assertIn("not a clearance", md.lower())
        self.assertIn("draft", md.lower())

    def test_core_gates_all_pass(self):
        model = build_flight_test_deliverable(example_aircraft())
        gates = check_flight_test_deliverable(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_all_pass(self):
        md = example_deliverable_markdown()
        gates = check_flight_test_markdown(md)
        self.assertTrue(gates["all_pass"], gates)

    def test_sign_off_gate_fails_when_status_changed(self):
        model = build_flight_test_deliverable(example_aircraft())
        model["status"] = "cleared"
        gates = check_flight_test_deliverable(model)
        self.assertFalse(gates["all_pass"])
        self.assertFalse(gates["sign_off_honest"])

    def test_markdown_gate_fails_without_clearance_marker(self):
        md = example_deliverable_markdown()
        import re
        stripped = re.sub(r"(?i)not a clearance", "noted", md)
        self.assertNotIn("not a clearance", stripped.lower())
        gates = check_flight_test_markdown(stripped)
        self.assertFalse(gates["all_pass"])
        self.assertFalse(gates["has_not_clearance"])

    def test_markdown_gate_fails_with_blank_placeholders(self):
        md = example_deliverable_markdown().replace("clean", "___clean___")
        gates = check_flight_test_markdown(md)
        self.assertFalse(gates["no_blank_blanks"])

    def test_standalone_no_skills_repo(self):
        # Core must work with no AeroSkills present: set env to a bad path.
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = build_flight_test_deliverable(example_aircraft())
        self.assertEqual(len(model["speed_blocks"]), 4)
        md = render_flight_test_markdown(model)
        self.assertGreater(len(md), 4000)
        self.assertTrue(check_flight_test_markdown(md)["all_pass"])

    def test_example_data_must_cover_blocks(self):
        data = example_flight_data()
        data["flutter_points"]["dampings"] = [0.1, 0.1, 0.1]
        with self.assertRaises(ValueError):
            build_flight_test_deliverable(example_aircraft(), data)


if __name__ == "__main__":
    unittest.main()
