#!/usr/bin/env python3
"""Test data_bus_avionics_core: the executable engine of the Data Bus role.

Proves the role can DO its job standalone (no AeroSkills needed):
ARINC 429 word decode/build with odd parity, ARINC 429 bus loading %,
MIL-STD-1553 word encode/decode and message classification, MIL-STD-1553
BC minor-frame bus loading, AFDX VL bandwidth and link budget, the
assessment builder + evidence gates, and standalone operation.

Real computed anchors (from the bound AeroSkills leaf logic tests):
- ARINC 429 build_word(8, 1, 1234, 3) == 1611876616 (0x60134908)
- MIL-STD-1553 encode_command_word(5, 12, 16, 1) == 93316
- MIL-STD-1553 encode_data_word(0x7FFF) == 262139
- MIL-STD-1553 encode_status_word(5, busy=1) == 606276
- AFDX vl_bandwidth(4 ms, 1518) == 3036000.0 bps
- AFDX 30 x (4 ms, 1518) VLs == 91.08% of the 100 Mbps link
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from data_bus_avionics_core import (  # noqa: E402
    a429_bnr_decode, a429_bnr_encode, a429_build_word, a429_decode_word,
    a429_loading_summary, a429_parity_ok, a429_total_word_rate,
    a429_utilization_pct, a429_word_capacity,
    afdx_end_to_end_latency_us, afdx_jitter_slack,
    afdx_largest_bag_for_bandwidth, afdx_link_utilization_pct,
    afdx_transmission_time_us, afdx_vl_bandwidth,
    analyze_architecture, build_assessment, check_assessment,
    check_assessment_markdown, example_assessment_markdown, example_item,
    m1553_classify_message, m1553_decode_command_word,
    m1553_decode_status_word, m1553_encode_command_word,
    m1553_encode_data_word, m1553_encode_status_word, m1553_message_time_us,
    m1553_schedule_utilization, m1553_wire_words, render_assessment_markdown,
)

A429_WORD = 1611876616          # 0x60134908: label 010, SDI 1, data 1234
M1553_CMD = 93316               # RT 5, SA 12, WC 16, T/R 1
M1553_STATUS = 606276           # RT 5, busy=1


class TestArinc429Protocol(unittest.TestCase):

    def test_word_build_anchor(self):
        self.assertEqual(a429_build_word(8, 1, 1234, 3), A429_WORD)
        self.assertEqual(a429_build_word("010", 1, 1234, 3), A429_WORD)

    def test_word_decode_fields(self):
        d = a429_decode_word(A429_WORD)
        self.assertEqual(d["label"], 8)          # octal 010
        self.assertEqual(d["sdi"], 1)
        self.assertEqual(d["data"], 1234)
        self.assertEqual(d["ssm"], 3)
        self.assertTrue(d["parity_ok"])
        self.assertTrue(a429_parity_ok(A429_WORD))

    def test_word_round_trip(self):
        w = a429_build_word(0o365, 2, 777, 1)
        d = a429_decode_word(w)
        self.assertEqual((d["label"], d["sdi"], d["data"], d["ssm"]),
                         (0o365, 2, 777, 1))

    def test_bnr_encode_decode(self):
        self.assertEqual(a429_bnr_encode(123.4, 0.1), 1234)
        self.assertAlmostEqual(a429_bnr_decode(1234, 0.1), 123.4, places=6)
        neg = a429_bnr_encode(-12.3, 0.1)
        self.assertEqual(neg, 524165)
        self.assertAlmostEqual(a429_bnr_decode(neg, 0.1), -12.3, places=6)


class TestArinc429Loading(unittest.TestCase):

    def test_total_word_rate_and_load(self):
        rates = {"010": 100.0, "011": 100.0}
        self.assertEqual(a429_total_word_rate(rates), 200.0)
        self.assertAlmostEqual(a429_utilization_pct(200.0), 7.2, places=6)
        self.assertAlmostEqual(a429_utilization_pct(200.0, 12500.0),
                               57.6, places=6)

    def test_capacity(self):
        # ~2777.8 words/s at 100 kbps, ~347.2 at 12.5 kbps (36 bit-times)
        self.assertAlmostEqual(a429_word_capacity(100000.0), 2777.7778,
                               places=3)
        self.assertAlmostEqual(a429_word_capacity(12500.0), 347.2222,
                               places=3)

    def test_fits_with_headroom(self):
        s = a429_loading_summary({"010": 250.0}, 100000.0)
        self.assertEqual(s["capacity_verdict"], "FITS")
        self.assertEqual(s["guideline_verdict"], "FITS")
        self.assertAlmostEqual(s["utilization_pct"], 9.0, places=6)
        self.assertAlmostEqual(s["headroom_pct"], 71.0, places=6)

    def test_guideline_violation_not_capacity_over(self):
        # 2500 words/s -> 90% of the 100 kbps link: fits capacity,
        # violates the 80% design guideline.
        s = a429_loading_summary({"010": 2500.0}, 100000.0)
        self.assertAlmostEqual(s["utilization_pct"], 90.0, places=6)
        self.assertEqual(s["capacity_verdict"], "FITS")
        self.assertEqual(s["guideline_verdict"], "VIOLATION")
        self.assertEqual(s["headroom_pct"], 0.0)

    def test_capacity_over(self):
        # 3100 words/s -> 111.6%: beyond the link itself.
        s = a429_loading_summary({"010": 3100.0}, 100000.0)
        self.assertAlmostEqual(s["utilization_pct"], 111.6, places=6)
        self.assertEqual(s["capacity_verdict"], "OVER")

    def test_low_speed_line_near_guideline(self):
        # 13 labels x 20 wps = 260 wps -> 74.88% of the 12.5 kbps link
        rates = {oct(0o250 + i)[2:]: 20.0 for i in range(13)}
        s = a429_loading_summary(rates, 12500.0)
        self.assertAlmostEqual(s["total_words_per_s"], 260.0, places=6)
        self.assertAlmostEqual(s["utilization_pct"], 74.88, places=4)
        self.assertEqual(s["guideline_verdict"], "FITS")


class TestM1553Protocol(unittest.TestCase):

    def test_command_word_anchor(self):
        self.assertEqual(m1553_encode_command_word(5, 12, 16, 1), M1553_CMD)
        d = m1553_decode_command_word(M1553_CMD)
        self.assertEqual(d["rt_address"], 5)
        self.assertEqual(d["subaddress"], 12)
        self.assertEqual(d["word_count"], 16)
        self.assertEqual(d["transmit_receive"], 1)
        self.assertTrue(d["parity_ok"])

    def test_data_word_anchor(self):
        self.assertEqual(m1553_encode_data_word(0x7FFF), 262139)

    def test_status_word_anchor(self):
        self.assertEqual(m1553_encode_status_word(5, busy=1), M1553_STATUS)
        d = m1553_decode_status_word(M1553_STATUS)
        self.assertEqual(d["rt_address"], 5)
        self.assertEqual(d["busy"], 1)
        self.assertTrue(d["parity_ok"])

    def test_message_classification(self):
        self.assertEqual(m1553_classify_message(5, 12, 16, 1), "rt-to-bc")
        self.assertEqual(m1553_classify_message(5, 12, 16, 0), "bc-to-rt")
        self.assertEqual(m1553_classify_message(31, 8, 8, 0), "broadcast")
        self.assertEqual(m1553_classify_message(3, 0, 17, 0), "mode-code")


class TestM1553Loading(unittest.TestCase):

    MESSAGES = [("BCRT", 32), ("RTBC", 16), ("BCRT", 16), ("RTRT", 8),
                ("RTBC", 8), ("BCRT", 8), ("BCRT", 4), ("RTRT", 4)]

    def test_wire_words(self):
        self.assertEqual(m1553_wire_words("BCRT", 16), 18)
        self.assertEqual(m1553_wire_words("RTBC", 32), 34)
        self.assertEqual(m1553_wire_words("RTRT", 8), 11)
        self.assertEqual(m1553_message_time_us("RTRT", 8), 264.0)

    def test_schedule_utilization_anchor(self):
        s = m1553_schedule_utilization(self.MESSAGES, 5000.0)
        # 114 wire words x 24 us = 2736 us of a 5000 us minor frame
        self.assertEqual(s["total_wire_words"], 114)
        self.assertEqual(s["total_us"], 2736.0)
        self.assertAlmostEqual(s["utilization_pct"], 54.72, places=6)
        self.assertEqual(s["budget_us"], 4000.0)
        self.assertEqual(s["headroom_us"], 1264.0)
        self.assertEqual(s["verdict"], "FITS")

    def test_schedule_over_budget(self):
        heavy = [("BCRT", 32)] * 6 + [("RTRT", 32)] * 6
        s = m1553_schedule_utilization(heavy, 5000.0)
        self.assertEqual(s["verdict"], "OVER")


class TestAfdx(unittest.TestCase):

    def test_vl_bandwidth_anchors(self):
        self.assertEqual(afdx_vl_bandwidth(4, 1518), 3036000.0)
        self.assertEqual(afdx_vl_bandwidth(128, 1518), 94875.0)

    def test_link_utilization(self):
        self.assertAlmostEqual(afdx_link_utilization_pct([(4, 1518)] * 30),
                               91.08, places=4)
        with self.assertRaises(ValueError):
            afdx_link_utilization_pct([(4, 1518)] * 33)

    def test_timing_anchors(self):
        self.assertAlmostEqual(afdx_transmission_time_us(1518), 121.44,
                               places=6)
        self.assertAlmostEqual(afdx_end_to_end_latency_us(1518, 2, 150.0),
                               542.88, places=4)
        self.assertEqual(afdx_jitter_slack(420.0, 500.0), 80.0)
        self.assertEqual(afdx_jitter_slack(620.0, 500.0), -120.0)

    def test_largest_bag_for_bandwidth(self):
        self.assertEqual(afdx_largest_bag_for_bandwidth(1e6, 1518), 8)
        with self.assertRaises(ValueError):
            afdx_largest_bag_for_bandwidth(13e6, 1518)


class TestAssessmentBuilder(unittest.TestCase):

    def test_example_architecture_loads(self):
        item = example_item()
        results = analyze_architecture(item)
        model = build_assessment(item, results)
        self.assertEqual(len(model["arinc429"]), 3)
        # worked example numbers: 1553 54.72%, AFDX 10.81575%
        self.assertAlmostEqual(
            model["m1553"]["schedule"]["utilization_pct"], 54.72, places=4)
        self.assertAlmostEqual(model["afdx"]["utilization_pct"], 10.81575,
                               places=4)
        self.assertFalse(model["afdx"]["oversubscribed"])
        # low-speed line is the loaded one (74.88%) -> observation raised
        self.assertTrue(model["observations"])
        self.assertEqual(model["status"], "draft-for-review")

    def test_conformance_samples_decode(self):
        item = example_item()
        conf = analyze_architecture(item)["conformance"]
        self.assertEqual(conf["a429_word"]["label"], 8)
        self.assertTrue(conf["a429_word"]["parity_ok"])
        self.assertAlmostEqual(conf["a429_bnr"]["engineering_value"], 123.4,
                               places=6)
        self.assertEqual(conf["m1553_command"]["rt_address"], 5)
        self.assertTrue(conf["m1553_command"]["parity_ok"])
        self.assertEqual(conf["m1553_status"]["busy"], 1)

    def test_deliverable_sections(self):
        md = example_assessment_markdown()
        for sec in ["## 1. Scope", "## 2. ARINC 429 bus loading",
                    "## 3. MIL-STD-1553 bus loading",
                    "## 4. ARINC 664 AFDX network",
                    "## 5. Protocol conformance checks",
                    "## 6. Findings and observations"]:
            self.assertIn(sec, md)
        self.assertIn("not an approval", md.lower())
        self.assertGreater(len(md), 3000)

    def test_core_gates_all_pass(self):
        item = example_item()
        model = build_assessment(item, analyze_architecture(item))
        gates = check_assessment(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_all_pass(self):
        md = example_assessment_markdown()
        gates = check_assessment_markdown(md)
        self.assertTrue(gates["all_pass"], gates)

    def test_standalone_no_skills_repo(self):
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = build_assessment(example_item(),
                                 analyze_architecture(example_item()))
        md = render_assessment_markdown(model)
        self.assertGreater(len(md), 3000)
        self.assertTrue(check_assessment(model)["all_pass"])


if __name__ == "__main__":
    unittest.main()
