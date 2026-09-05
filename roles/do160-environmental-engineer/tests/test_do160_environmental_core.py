#!/usr/bin/env python3
"""Test do160_environmental_core: the executable engine of the DO-160G
Environmental Qualification Engineer role.

Proves the role can DO its job standalone (no AeroSkills needed):
category selection, matrix completeness, ESD/lightning/power/RF domain
rules, report generation, and evidence-gate checks. Every numeric
anchor mirrors the bound AeroSkills avionics/do160 leaf logic files.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from do160_environmental_core import (  # noqa: E402
    CE102_BAND_HI_HZ, CE102_BAND_LO_HZ,
    RE102_BAND_HI_HZ, RE102_BAND_LO_HZ, RE102_FLOOR_DBU_VPM,
    SECTIONS, TEMPERATURE_RANGES,
    build_qualification_report, check_qualification_report,
    check_qualification_report_markdown,
    cs114_category_offset, cs114_limit_dbu_a, dbu_v_per_m_from_v_per_m,
    dbu_v_from_volts, emission_verdict, esd_category_test_level_kv,
    esd_current_30ns_amps, esd_current_60ns_amps, esd_discharge_count_valid,
    esd_pass_verdict, esd_peak_current_amps, esd_rc_time_constant_ns,
    esd_rise_time_valid_ns, esd_stored_energy_joules,
    esd_test_point_applicable, example_item,
    example_qualification_report_markdown, field_strength_from_erp,
    frequency_deviation, frequency_within_tolerance, lightning_level_valid,
    lightning_pass_verdict, lightning_waveform_valid, limits_margins,
    margin_check_dbu, matrix_complete, power_for_field_strength,
    required_amp_power_for_test, required_sections, re102_limit_db,
    render_qualification_report_markdown, ripple_percent,
    sag_depth_percent, section_name, select_temperature_category,
    surge_height_percent, temperature_category_range, temp_within_range,
    transient_check, transient_recovery_ok, voltage_within_limits,
    worst_case_frequency,
)


class TestEnvironmentalQualificationDomain(unittest.TestCase):
    """Mirrors avionics/do160/environmental-qualification logic anchors."""

    def test_section_names(self):
        self.assertEqual(section_name(16), "Power input")
        self.assertEqual(section_name(25), "Electrostatic discharge")
        self.assertEqual(section_name(20), "Radio frequency susceptibility")
        self.assertEqual(section_name(21), "Emission of radio frequency energy")
        self.assertEqual(section_name(22),
                         "Lightning induced transient susceptibility")
        with self.assertRaises(ValueError):
            section_name(99)

    def test_temperature_ranges(self):
        self.assertEqual(temperature_category_range("B1"), (-55, 55))
        self.assertEqual(temperature_category_range("A2"), (-55, 70))
        self.assertEqual(TEMPERATURE_RANGES["B2"], (-55, 70))
        with self.assertRaises(ValueError):
            temperature_category_range("Z9")

    def test_temp_within_range(self):
        self.assertTrue(temp_within_range(-40, "B1"))
        self.assertTrue(temp_within_range(55, "B1"))    # inclusive top
        self.assertFalse(temp_within_range(60, "B1"))

    def test_category_selection_covers_extremes(self):
        # example LRU: -40..55 deg C in a pressurized bay -> B1 covers
        cat = select_temperature_category(-40, 55)
        self.assertEqual(cat, "B1")
        lo, hi = temperature_category_range(cat)
        self.assertLessEqual(-40, hi) and self.assertGreaterEqual(55, lo)
        # any declared extremes must be inside the selected typical range
        cat2 = select_temperature_category(-55, 70)
        self.assertTrue(temp_within_range(-55, cat2))
        self.assertTrue(temp_within_range(70, cat2))

    def test_required_sections_full_set(self):
        req = required_sections("B1")
        # full leaf section set, sorted
        self.assertEqual(req, sorted(SECTIONS))
        self.assertIn(22, req)  # lightning induced - never omitted by default
        self.assertIn(25, req)  # ESD

    def test_matrix_complete(self):
        missing, ok = matrix_complete(sorted(SECTIONS), "B1")
        self.assertEqual(missing, [])
        self.assertTrue(ok)
        missing2, ok2 = matrix_complete([4, 5, 6], "B1")
        self.assertIn(25, missing2)
        self.assertFalse(ok2)
        with self.assertRaises(ValueError):
            matrix_complete([99], "B1")


class TestEsdDomain(unittest.TestCase):
    """Mirrors avionics/do160/electrostatic-discharge logic anchors."""

    def test_category_level(self):
        self.assertEqual(esd_category_test_level_kv("A"), 15.0)
        self.assertEqual(esd_category_test_level_kv("a"), 15.0)
        with self.assertRaises(ValueError):
            esd_category_test_level_kv("B")

    def test_stored_energy_anchors(self):
        # 150 pF at 15 kV -> 16.875 mJ; at 8 kV -> 4.8 mJ
        self.assertAlmostEqual(esd_stored_energy_joules(150.0, 15.0),
                               0.016875, places=9)
        self.assertAlmostEqual(esd_stored_energy_joules(150.0, 8.0),
                               0.0048, places=9)

    def test_waveform_current_anchors(self):
        self.assertAlmostEqual(esd_peak_current_amps(15.0), 56.25, places=2)
        self.assertAlmostEqual(esd_peak_current_amps(2.0), 7.5, places=2)
        self.assertAlmostEqual(esd_current_30ns_amps(15.0), 30.0, places=2)
        self.assertAlmostEqual(esd_current_60ns_amps(15.0), 15.0, places=2)

    def test_rise_and_rc(self):
        self.assertTrue(esd_rise_time_valid_ns(0.8))
        self.assertFalse(esd_rise_time_valid_ns(0.5))
        self.assertFalse(esd_rise_time_valid_ns(1.2))
        self.assertAlmostEqual(esd_rc_time_constant_ns(330.0, 150.0),
                               49.5, places=1)

    def test_discharge_counts(self):
        self.assertTrue(esd_discharge_count_valid(10, 10))
        self.assertFalse(esd_discharge_count_valid(9, 10))
        self.assertFalse(esd_discharge_count_valid(10, 9))
        with self.assertRaises(ValueError):
            esd_discharge_count_valid(10.5, 10)

    def test_test_point_applicability(self):
        self.assertTrue(esd_test_point_applicable(True, False, False))
        self.assertTrue(esd_test_point_applicable(False, True, False))
        # connector pins are NOT applicable test points (DO-160G)
        self.assertFalse(esd_test_point_applicable(True, False, True))
        self.assertFalse(esd_test_point_applicable(False, False, False))

    def test_pass_verdict(self):
        self.assertTrue(esd_pass_verdict(True, True))
        self.assertFalse(esd_pass_verdict(False, True))
        self.assertFalse(esd_pass_verdict(True, False))


class TestLightningDomain(unittest.TestCase):
    """Mirrors avionics/do160/lightning-protection logic anchors."""

    def test_level_range(self):
        self.assertTrue(lightning_level_valid(3))
        self.assertTrue(lightning_level_valid(1))
        self.assertTrue(lightning_level_valid(5))
        self.assertFalse(lightning_level_valid(0))
        self.assertFalse(lightning_level_valid(6))
        with self.assertRaises(ValueError):
            lightning_level_valid("3")
        with self.assertRaises(ValueError):
            lightning_level_valid(3.5)

    def test_waveforms(self):
        for w in "ABCDEFGH":
            self.assertTrue(lightning_waveform_valid(w))
        self.assertTrue(lightning_waveform_valid("c"))  # case-insensitive
        self.assertFalse(lightning_waveform_valid("I"))
        self.assertFalse(lightning_waveform_valid(""))
        with self.assertRaises(ValueError):
            lightning_waveform_valid(7)

    def test_pass_verdict(self):
        self.assertTrue(lightning_pass_verdict(False, False, False))
        self.assertFalse(lightning_pass_verdict(True, False, False))
        self.assertFalse(lightning_pass_verdict(False, True, False))
        self.assertFalse(lightning_pass_verdict(False, False, True))


class TestPowerInputDomain(unittest.TestCase):
    """Mirrors avionics/do160/power-input logic anchors (data-driven)."""

    def test_sag_surge(self):
        self.assertAlmostEqual(sag_depth_percent(28.0, 21.0), 25.0, places=6)
        self.assertAlmostEqual(surge_height_percent(28.0, 32.2), 15.0,
                               places=6)
        with self.assertRaises(ValueError):
            sag_depth_percent(28.0, 32.0)  # that is a surge

    def test_frequency(self):
        dev_hz, dev_pct = frequency_deviation(412.0, 400.0)
        self.assertAlmostEqual(dev_hz, 12.0, places=6)
        self.assertAlmostEqual(dev_pct, 3.0, places=6)
        self.assertTrue(frequency_within_tolerance(412.0, 400.0, 5.0))
        self.assertFalse(frequency_within_tolerance(422.0, 400.0, 5.0))

    def test_limits_and_margins(self):
        self.assertTrue(voltage_within_limits(27.5, 22.0, 29.0))
        self.assertFalse(voltage_within_limits(21.0, 22.0, 29.0))
        ml, mh = limits_margins(27.5, 22.0, 29.0)
        self.assertAlmostEqual(ml, 5.5, places=6)
        self.assertAlmostEqual(mh, 1.5, places=6)

    def test_transients(self):
        self.assertTrue(transient_recovery_ok(60.0, 100.0))
        ok, dm, dp = transient_check(80.0, 20.0, 100.0, 25.0)
        self.assertTrue(ok)
        self.assertAlmostEqual(dm, 20.0, places=6)
        self.assertAlmostEqual(dp, 5.0, places=6)

    def test_ripple(self):
        self.assertAlmostEqual(ripple_percent(29.0, 27.0, 28.0),
                               3.5714285714, places=6)


class TestRfSusceptibilityDomain(unittest.TestCase):
    """Mirrors avionics/do160/radio-frequency-susceptibility anchors."""

    def test_amp_budget_anchor(self):
        # 100 V/m at 3 m, 3 dBi, 3 dB cable loss, 6 dB margin -> ~12 kW
        w = required_amp_power_for_test(100.0, 3.0, 3.0, 3.0, 6.0)
        self.assertAlmostEqual(w, 11970.0, delta=120)

    def test_power_roundtrip(self):
        # E = sqrt(30*P*G)/d; P = E^2 d^2 / (30 G)
        self.assertAlmostEqual(power_for_field_strength(5.477, 1.0, 10.0),
                               100.0, delta=0.1)

    def test_cs114_category_steps(self):
        self.assertEqual(cs114_category_offset("A"), 0.0)
        self.assertEqual(cs114_category_offset("B"), 10.0)
        self.assertEqual(cs114_category_offset("C"), 20.0)
        self.assertEqual(cs114_category_offset("J"), 80.0)
        with self.assertRaises(ValueError):
            cs114_category_offset("I")  # letter I is skipped
        self.assertAlmostEqual(cs114_limit_dbu_a("B"), 65.7, places=1)

    def test_margin_check(self):
        margin, ok = margin_check_dbu(60.0, 65.7)
        self.assertTrue(ok)
        self.assertAlmostEqual(margin, 5.7, places=1)
        _, bad = margin_check_dbu(70.0, 65.7)
        self.assertFalse(bad)


class TestRfEmissionsDomain(unittest.TestCase):
    """Mirrors avionics/do160/radio-frequency-emissions anchors."""

    def test_conversions(self):
        self.assertAlmostEqual(dbu_v_from_volts(1.0), 120.0, places=6)
        self.assertAlmostEqual(dbu_v_per_m_from_v_per_m(1.0), 120.0,
                               places=6)

    def test_limit_curves(self):
        self.assertEqual(RE102_FLOOR_DBU_VPM, {"A": 24.0, "B": 34.0,
                                               "C": 44.0})
        self.assertAlmostEqual(re102_limit_db(100e6, "A"), 24.0, places=6)
        self.assertAlmostEqual(re102_limit_db(100e6, "C"), 44.0, places=6)
        self.assertEqual(CE102_BAND_LO_HZ, 10e3)
        self.assertEqual(CE102_BAND_HI_HZ, 10e6)
        self.assertEqual(RE102_BAND_LO_HZ, 2e6)
        self.assertEqual(RE102_BAND_HI_HZ, 18e9)

    def test_erp_sanity_check(self):
        # 100 W ERP at 10 m -> 5.477 V/m (~134.77 dBuV/m)
        e = field_strength_from_erp(100.0, 10.0)
        self.assertAlmostEqual(e, 5.477, places=2)
        self.assertAlmostEqual(dbu_v_per_m_from_v_per_m(e), 134.77,
                               places=1)

    def test_worst_case_and_verdict(self):
        freqs = [50e3, 150e3, 5e6]
        margins = [8.0, 5.0, 8.0]
        wf, wm = worst_case_frequency(freqs, margins)
        self.assertEqual(wf, 150e3)
        self.assertAlmostEqual(wm, 5.0, places=6)
        v = emission_verdict(margins, freqs, "A", "CE102")
        self.assertTrue(v["pass"])
        # negative worst margin fails
        v2 = emission_verdict([-2.0], [100e6], "A", "RE102")
        self.assertFalse(v2["pass"])


class TestQualificationReportBuilder(unittest.TestCase):

    def test_example_report_all_gates_pass(self):
        model = build_qualification_report(example_item())
        self.assertEqual(model["temperature_category"], "B1")
        self.assertEqual(model["status"], "draft-for-review")
        self.assertTrue(model["matrix_complete"])
        self.assertEqual(model["esd"]["test_level_kv"], 15.0)
        gates = check_qualification_report(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_report_sections_present(self):
        md = example_qualification_report_markdown()
        for sec in ["## 1. Scope", "## 3. Qualification test matrix",
                    "## 6. Power input (Section 16)",
                    "## 7. Radio frequency susceptibility (Section 20)",
                    "## 9. Verdicts and open items"]:
            self.assertIn(sec, md)
        self.assertIn("not an approval", md.lower())

    def test_markdown_gates_all_pass(self):
        md = example_qualification_report_markdown()
        gates = check_qualification_report_markdown(md, "B1")
        self.assertTrue(gates["all_pass"], gates)

    def test_standalone_no_skills_repo(self):
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = build_qualification_report(example_item())
        self.assertTrue(model["matrix_complete"])
        md = render_qualification_report_markdown(model)
        self.assertGreater(len(md), 2000)


if __name__ == "__main__":
    unittest.main()
