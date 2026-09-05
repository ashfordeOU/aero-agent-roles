#!/usr/bin/env python3
"""Test ndt_core: the executable engine of the NDT Engineer role.

Proves the role can DO its job standalone (no AeroSkills needed):
method selection per defect/material, eddy current / penetrant /
radiography / CT / magnetic particle / leak / AE / shearography math
anchored to the bound ndt leaf logic values, personnel qualification,
report generation, and evidence-gate checks.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from ndt_core import (  # noqa: E402
    SENSITIVITY_RANK, add_months_clamped, anomaly_disposition,
    applicable_methods, bath_concentration_check, build_report,
    capillary_pressure, certification_status, check_report,
    check_report_markdown, coil_ampere_turns_high_fill,
    coil_ampere_turns_low_fill, coil_current_from_turns,
    conductivity_from_iacs, contrast_ratio, cost_rank,
    crack_radius_from_width, ct_number, density_verdict,
    developer_coverage_mass, discontinuity_class, disposition,
    dwell_time_for_depth, eddy_current_density_ratio, effective_diameter_hollow,
    effective_ld_ratio, example_item, example_report_markdown, exposure_time,
    felicity_ratio, frequency_for_depth, gauge_resolution_time,
    geometric_unsharpness, group_hits_to_events, head_shot_current,
    hit_threshold_check, indication_is_linear, iqi_sensitivity_percent,
    kaiser_effect_check, level_meets, magnification, magnetization_for_defect,
    material_class_from_ct_number, min_detectable_strain, particle_sensitivity,
    particle_size_class, phase_lag_degrees, porosity_fraction,
    pressure_decay_rate, projection_count, qualification_review, recert_due_date,
    render_report_markdown, residual_field_verdict, rt_setup_verdict,
    scan_time, select_frequency_for_flaw, select_load, select_method,
    sensitivity_rank, shear_for_defect, solenoid_field_strength,
    source_location_linear, standard_depth_of_penetration, strain_from_phase,
    supervision_valid, tangential_field_verdict, tube_energy_kv,
    upgrade_eligible, vision_due_date, void_diameter, voxel_size,
    washburn_penetration_depth,
)

# ---------------------------------------------------------------------------
# Method selection (ndt-method-selection leaf anchors)
# ---------------------------------------------------------------------------


class TestMethodSelection(unittest.TestCase):

    def test_applicable_sets(self):
        self.assertEqual(applicable_methods("surface", "ferromagnetic"),
                         ["MT", "PT"])
        self.assertEqual(applicable_methods("surface", "non-ferromagnetic"),
                         ["ET", "PT"])
        self.assertEqual(applicable_methods("surface", "non-conductive"),
                         ["PT"])
        self.assertEqual(applicable_methods("near-surface", "ferromagnetic"),
                         ["ET", "UT"])
        self.assertEqual(applicable_methods("internal", "ferromagnetic"),
                         ["RT", "UT"])

    def test_sensitivity_and_cost(self):
        self.assertEqual(SENSITIVITY_RANK["UT"], 5)
        self.assertEqual(sensitivity_rank("RT"), 4)
        self.assertEqual(cost_rank("PT"), 1)
        self.assertEqual(cost_rank("RT"), 4)

    def test_select_surface_non_ferromagnetic(self):
        pick = select_method("surface", "non-ferromagnetic")
        self.assertEqual(pick["method"], "ET")
        self.assertEqual(pick["alternates"], ["PT"])
        self.assertIn("highest-sensitivity", pick["rationale"])

    def test_select_internal_top_ut(self):
        pick = select_method("internal", "ferromagnetic")
        self.assertEqual(pick["method"], "UT")
        self.assertEqual(pick["alternates"], ["RT"])

    def test_surface_ferromagnetic_tie_breaks_to_pt(self):
        # MT and PT both rank 3; the fixed tie-break order picks PT.
        pick = select_method("surface", "ferromagnetic")
        self.assertEqual(pick["method"], "PT")
        self.assertIn("MT", pick["alternates"])


# ---------------------------------------------------------------------------
# Eddy current (eddy-current-inspection leaf anchors)
# ---------------------------------------------------------------------------


class TestEddyCurrent(unittest.TestCase):

    def test_conductivity_from_iacs(self):
        self.assertEqual(conductivity_from_iacs(100), 5.8e7)
        self.assertEqual(conductivity_from_iacs(30), 1.74e7)
        self.assertEqual(conductivity_from_iacs(5), 2.9e6)

    def test_standard_depth_anchors(self):
        self.assertAlmostEqual(standard_depth_of_penetration(1e5, 5.8e7),
                               2.0898e-4, places=8)
        self.assertAlmostEqual(standard_depth_of_penetration(60, 5.8e7),
                               8.5316e-3, places=6)

    def test_frequency_for_depth_roundtrip(self):
        f = frequency_for_depth(1e-3, 5.8e7)
        self.assertAlmostEqual(standard_depth_of_penetration(f, 5.8e7),
                               1e-3, places=6)

    def test_select_frequency_subsurface_anchor(self):
        # 1 mm flaw under aluminum 30 pct IACS, factor 2.0 -> 3639.4103 Hz
        self.assertAlmostEqual(
            select_frequency_for_flaw(1e-3, 1.74e7, penetration_factor=2.0),
            3639.4103, places=2)
        # surface sharp response factor 0.5 -> 58230.5653 Hz
        self.assertAlmostEqual(
            select_frequency_for_flaw(1e-3, 1.74e7, penetration_factor=0.5),
            58230.5653, places=1)

    def test_density_ratio_and_phase(self):
        self.assertAlmostEqual(eddy_current_density_ratio(1e-3, 1e-3),
                               0.3679, places=4)
        self.assertAlmostEqual(eddy_current_density_ratio(0.0, 1e-3), 1.0)
        self.assertAlmostEqual(phase_lag_degrees(1e-3, 1e-3), 57.2958,
                               places=4)
        self.assertAlmostEqual(phase_lag_degrees(1e-3, 2e-3), 28.6479,
                               places=4)

    def test_subsurface_flaw_stays_within_one_delta(self):
        f = select_frequency_for_flaw(1e-3, 1.74e7, penetration_factor=2.0)
        delta = standard_depth_of_penetration(f, 1.74e7)
        self.assertAlmostEqual(delta, 2e-3)
        self.assertAlmostEqual(eddy_current_density_ratio(1e-3, delta),
                               0.6065, places=4)


# ---------------------------------------------------------------------------
# Liquid penetrant (liquid-penetrant-inspection leaf anchors)
# ---------------------------------------------------------------------------


class TestLiquidPenetrant(unittest.TestCase):

    def test_capillary_pressure_anchor(self):
        self.assertAlmostEqual(capillary_pressure(0.032, 0, 1e-6), 64000.0)

    def test_washburn_dwell_roundtrip(self):
        depth = washburn_penetration_depth(0.032, 5, 0.008, 1e-6, 300)
        t = dwell_time_for_depth(depth, 0.032, 5, 0.008, 1e-6)
        self.assertAlmostEqual(t, 300.0, places=6)

    def test_dwell_scales_with_depth_squared(self):
        one = dwell_time_for_depth(1e-3, 0.032, 5, 0.008, 1e-6)
        two = dwell_time_for_depth(2e-3, 0.032, 5, 0.008, 1e-6)
        self.assertAlmostEqual(two, 4.0 * one, places=6)

    def test_crack_radius_bleedout_developer_contrast(self):
        self.assertAlmostEqual(crack_radius_from_width(2e-6), 1e-6)
        self.assertAlmostEqual(contrast_ratio(0.8, 0.05), 0.9375, places=4)
        self.assertAlmostEqual(developer_coverage_mass(1.0, 0.15), 0.15)


# ---------------------------------------------------------------------------
# Radiography (radiographic-inspection leaf anchors)
# ---------------------------------------------------------------------------


class TestRadiography(unittest.TestCase):

    def test_unsharpness_exposure_iqi_anchors(self):
        self.assertAlmostEqual(geometric_unsharpness(3.0, 500.0, 30.0),
                               0.18, places=6)
        self.assertAlmostEqual(exposure_time(4.0, 600.0, 900.0), 16.0 / 9.0,
                               places=6)
        self.assertAlmostEqual(iqi_sensitivity_percent(0.6, 30.0), 2.0)

    def test_density_verdicts(self):
        self.assertEqual(density_verdict(2.5)["verdict"], "acceptable")
        self.assertEqual(density_verdict(1.5)["verdict"], "too-low")
        self.assertEqual(density_verdict(4.5)["verdict"], "too-high")

    def test_discontinuity_classification(self):
        self.assertEqual(discontinuity_class("round globular gas pockets"),
                         "porosity")
        self.assertEqual(discontinuity_class("sharp elongated hairline"),
                         "crack")

    def test_setup_verdict_acceptable(self):
        v = rt_setup_verdict(0.18, 2.0, 2.5)
        self.assertTrue(v["acceptable"])
        self.assertEqual(v["reasons"], [])

    def test_setup_verdict_fails_on_bad_density(self):
        v = rt_setup_verdict(0.18, 2.0, 1.2)
        self.assertFalse(v["acceptable"])
        self.assertTrue(any("density" in r for r in v["reasons"]))


# ---------------------------------------------------------------------------
# Computed tomography (computed-tomography leaf anchors)
# ---------------------------------------------------------------------------


class TestComputedTomography(unittest.TestCase):

    def test_geometry(self):
        self.assertAlmostEqual(magnification(0.3, 0.3), 2.0)
        self.assertAlmostEqual(voxel_size(200e-6, 0.3, 0.3), 1.0e-4)

    def test_projection_and_energy(self):
        self.assertEqual(projection_count(1024), 1609)
        self.assertAlmostEqual(tube_energy_kv("aluminum", 50.0), 350.0)
        self.assertAlmostEqual(scan_time(1609, 0.1), 160.9)

    def test_ct_number_and_porosity(self):
        self.assertAlmostEqual(ct_number(28.0, 20.0), 400.0)
        self.assertEqual(material_class_from_ct_number(400.0), "light-alloy")
        self.assertEqual(material_class_from_ct_number(-1000.0), "air-or-gas")
        self.assertAlmostEqual(porosity_fraction(64000, 8000000), 0.8)
        d = void_diameter(64000, 1.0e-4)
        self.assertAlmostEqual(d, 0.0049628, places=5)
        self.assertEqual(void_diameter(0, 1.0e-4), 0.0)


# ---------------------------------------------------------------------------
# Magnetic particle (magnetic-particle-inspection leaf anchors)
# ---------------------------------------------------------------------------


class TestMagneticParticle(unittest.TestCase):

    def test_magnetization_current_anchors(self):
        self.assertEqual(head_shot_current(2.0, 800.0), 1600.0)
        self.assertAlmostEqual(effective_diameter_hollow(2.0, 1.0),
                               1.7320508, places=6)
        self.assertAlmostEqual(effective_ld_ratio(8.0, 1.7320508), 4.6188,
                               places=4)
        self.assertAlmostEqual(coil_ampere_turns_low_fill(4.0), 11250.0)
        self.assertAlmostEqual(coil_ampere_turns_high_fill(4.0), 5833.33,
                               places=2)
        self.assertAlmostEqual(coil_current_from_turns(11250.0, 250), 45.0)
        self.assertAlmostEqual(solenoid_field_strength(1000.0, 0.25), 4000.0)

    def test_field_verdict_bands(self):
        self.assertEqual(tangential_field_verdict(4000.0), "adequate")
        self.assertEqual(tangential_field_verdict(2000.0), "low")
        self.assertEqual(tangential_field_verdict(5000.0), "high")
        self.assertEqual(tangential_field_verdict(4000.0, fluorescent=False),
                         "high")  # visible band tops at 3200 A/m

    def test_particles_and_bath(self):
        self.assertEqual(particle_size_class(8.0), "extra-fine")
        self.assertEqual(particle_size_class(45.0), "coarse")
        self.assertEqual(particle_sensitivity(8.0), "high")
        self.assertEqual(particle_sensitivity(25.0), "standard")
        self.assertEqual(bath_concentration_check(0.2, "fluorescent"),
                         "within-range")
        self.assertEqual(bath_concentration_check(0.05, "fluorescent"),
                         "below-range")

    def test_indication_and_acceptance(self):
        self.assertTrue(indication_is_linear(6.0, 1.5))
        self.assertFalse(indication_is_linear(4.0, 2.0))
        self.assertEqual(magnetization_for_defect("longitudinal"), "circular")
        self.assertEqual(magnetization_for_defect("transverse"), "longitudinal")
        self.assertEqual(residual_field_verdict(5.0), "demagnetize")
        self.assertEqual(residual_field_verdict(2.0), "acceptable")


# ---------------------------------------------------------------------------
# Leak testing (leak-testing leaf anchors)
# ---------------------------------------------------------------------------


class TestLeakTesting(unittest.TestCase):

    def test_decay_rate_and_gauge_anchor(self):
        self.assertAlmostEqual(pressure_decay_rate(5.0, 0.02, 600.0),
                               0.1644872, places=6)
        self.assertAlmostEqual(gauge_resolution_time(5.0, 5e-4, 0.2),
                               12.3365, places=4)

    def test_disposition_bands(self):
        self.assertEqual(disposition(0.16, 0.2, "pressure-decay")["verdict"],
                         "accept")
        self.assertEqual(disposition(0.30, 0.2, "pressure-decay")["verdict"],
                         "reject")  # above 1.25x allowable
        self.assertEqual(disposition(0.22, 0.2, "pressure-decay")["verdict"],
                         "review")


# ---------------------------------------------------------------------------
# Acoustic emission + shearography (leaf anchors)
# ---------------------------------------------------------------------------


class TestAcousticEmission(unittest.TestCase):

    def test_hits_and_events(self):
        r = hit_threshold_check([40.0, 55.0, 60.0], 50.0)
        self.assertEqual(r["hit_count"], 2)
        events = group_hits_to_events([0.001, 0.002, 0.02, 0.021], 0.01)
        self.assertEqual(len(events), 2)

    def test_felicity(self):
        self.assertAlmostEqual(felicity_ratio(0.85, 1.0), 0.85)
        self.assertTrue(kaiser_effect_check(1.0, 1.0)["kaiser_effect_holds"])
        self.assertTrue(kaiser_effect_check(0.8, 1.0)["damage_indicated"])
        x = source_location_linear(2.0, [0.0001, 0.0003], 5000.0)
        self.assertAlmostEqual(x, 0.5)


class TestShearography(unittest.TestCase):

    def test_strain_phase_anchor(self):
        # 0.5 rad, 5 mm shear, 532 nm -> ~4.23 micron/m strain
        self.assertAlmostEqual(strain_from_phase(0.5, 5.0), 4.2335e-6,
                               places=9)
        self.assertAlmostEqual(shear_for_defect(10.0), 5.0)

    def test_load_and_disposition(self):
        self.assertEqual(select_load(6.0, "vacuum"), 40.0)
        self.assertEqual(select_load(2.0, "vacuum"), 20.0)
        self.assertEqual(anomaly_disposition(3.0, 4.0, 5.0)["verdict"],
                         "accept")
        self.assertEqual(anomaly_disposition(4.2, 4.0, 5.0)["verdict"],
                         "review")
        self.assertEqual(anomaly_disposition(5.0, 4.0, 5.0)["verdict"],
                         "reject")

    def test_min_detectable(self):
        self.assertAlmostEqual(min_detectable_strain(0.1, 5.0), 2.54e-6,
                               places=8)


# ---------------------------------------------------------------------------
# Personnel qualification (ndt-personnel-qualification leaf anchors)
# ---------------------------------------------------------------------------


class TestPersonnelQualification(unittest.TestCase):

    def test_due_dates_and_clamp(self):
        self.assertEqual(recert_due_date("2023-06-15"), "2026-06-15")
        self.assertEqual(vision_due_date("2026-02-01"), "2027-02-01")
        self.assertEqual(add_months_clamped("2026-01-31", 1), "2026-02-28")
        self.assertEqual(add_months_clamped("2024-01-31", 1), "2024-02-29")

    def test_status_current_and_overdue(self):
        self.assertEqual(certification_status("2023-06-15", "2026-06-15",
                                              "2027-02-01", "2026-09-04"),
                         "recert-due")
        self.assertEqual(certification_status("2023-06-15", "2027-06-15",
                                              "2027-02-01", "2026-09-04"),
                         "current")

    def test_supervision_and_levels(self):
        self.assertFalse(supervision_valid("i", "i"))
        self.assertTrue(supervision_valid("i", "iii"))
        self.assertTrue(supervision_valid("ii", "i"))  # II works independently
        self.assertTrue(level_meets("ii", "ii"))
        self.assertFalse(level_meets("i", "ii"))

    def test_upgrade_eligible(self):
        self.assertTrue(upgrade_eligible("i", "ii", 40, 40, 4, 4, True))
        self.assertFalse(upgrade_eligible("i", "ii", 10, 40, 4, 4, True))
        with self.assertRaises(ValueError):
            upgrade_eligible("i", "iii", 40, 40, 4, 4, True)


# ---------------------------------------------------------------------------
# Report builder + gates + standalone
# ---------------------------------------------------------------------------


class TestReportBuilder(unittest.TestCase):

    def test_example_report_all_gates_pass(self):
        model = build_report(example_item())
        gates = check_report(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_example_selections(self):
        model = build_report(example_item())
        tops = [r["top_method"] for r in model["defect_population"]]
        self.assertEqual(tops, ["ET", "UT", "UT"])
        self.assertIn("eddy-current-surface", model["parameter_cards"])
        self.assertIn("computed-tomography", model["parameter_cards"])
        self.assertIn("leak-test", model["parameter_cards"])

    def test_personnel_qualified_in_example(self):
        model = build_report(example_item())
        review = model["personnel"]["review"]
        self.assertEqual(review["certification_status"], "current")
        self.assertTrue(review["supervision_ok"])
        self.assertTrue(all(r["operator_meets"]
                            for r in model["personnel"]["method_levels"]))

    def test_leak_reject_path_fails_gate_only_on_disposition_data(self):
        # Gate structure: plan gates stay green; the leak card disposition
        # data honestly reflects the tighter allowable.
        item = example_item()
        item.leak["max_allowable_sccs"] = 0.1
        model = build_report(item)
        self.assertEqual(model["parameter_cards"]["leak-test"]["verdict"],
                         "reject")
        self.assertTrue(check_report(model)["all_pass"])

    def test_stale_personnel_fails_qualification_gate(self):
        model = build_report(example_item())
        model["personnel"]["review"]["certification_status"] = "recert-due"
        gates = check_report(model)
        self.assertFalse(gates["personnel_qualified"])
        self.assertFalse(gates["all_pass"])

    def test_markdown_gates_pass(self):
        md = example_report_markdown()
        gates = check_report_markdown(md)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_missing_approval_fails(self):
        md = example_report_markdown().replace("Not an approval",
                                               "review complete")
        gates = check_report_markdown(md)
        self.assertFalse(gates["all_pass"])

    def test_standalone_no_skills_repo(self):
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = build_report(example_item())
        self.assertTrue(model["defect_population"])
        self.assertTrue(check_report(model)["all_pass"])
        md = render_report_markdown(model)
        self.assertGreater(len(md), 4000)
        self.assertIn("not an approval", md.lower())


if __name__ == "__main__":
    unittest.main()
