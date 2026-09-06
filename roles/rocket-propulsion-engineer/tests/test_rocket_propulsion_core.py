#!/usr/bin/env python3
"""Test rocket_propulsion_core: the executable engine of the Rocket
Propulsion Engineer.

Proves the role can DO its job standalone (no AeroSkills needed):
rocket-equation sizing, staging mass budgets, gravity-loss accounting,
feed-cycle balance, chamber c-star sizing, nozzle expansion and flow
separation, regenerative cooling, injector/TVC/RCS sizing, solid and
hybrid ballistics, report builder + evidence gates, and standalone
mode.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from rocket_propulsion_core import (  # noqa: E402
    bartz_hot_gas_coefficient, build_report, burn_rate,
    chamber_cooling_summary, chamber_volume, check_report,
    check_report_markdown, choked_mass_flow, contraction_ratio,
    coolant_side_coefficient, density_impulse, engine_cycle_analysis,
    equilibrium_chamber_pressure, example_item, example_report_markdown,
    exit_mach_from_area_ratio, ideal_thrust, mass_flow,
    mass_ratio_from_indices, optimal_equal_stage_split,
    payload_fraction_from_mass_ratio, render_report_markdown,
    rocket_equation_delta_v, side_force, solid_mass_flow,
    stage_count_for_delta_v, stage_delta_v_from_indices,
    structural_index, theoretical_cstar, throat_area,
    vacuum_specific_impulse,
)

# Deterministic across midnight: pin fresh renders to the date the
# committed template carries (CI override wins).
os.environ.setdefault("ROLE_GEN_DATE", "2026-09-06")


class TestCoreDomainRules(unittest.TestCase):
    """Public-standard anchors mirrored from the bound AeroSkills leaves."""

    def test_rocket_equation_anchor(self):
        # g0*300*ln(2) = 2039.24 m/s (rocket-sizing leaf anchor).
        self.assertAlmostEqual(rocket_equation_delta_v(300.0, 100000.0,
                                                       50000.0),
                               2039.24, delta=0.01)

    def test_mass_ratio_anchor(self):
        # exp(2039.24/(300*g0)) = 2.0 (leaf anchor).
        self.assertAlmostEqual(mass_ratio_from_indices(0.1, 0.05),
                               6.8966, delta=1e-3)
        r = 2.0
        lam = payload_fraction_from_mass_ratio(0.1, r)
        self.assertAlmostEqual(lam, (1.0 / 2.0 - 0.1) / 0.9)

    def test_structural_index_anchor(self):
        self.assertAlmostEqual(structural_index(10000.0, 90000.0), 0.1)

    def test_equal_stage_split_anchor(self):
        # Two identical stages, 9000 m/s at Isp 300, eps 0.1:
        # r* = 4.6162, lam_stage = 0.12959, lam_total = 0.01679.
        r, lam, lam_tot = optimal_equal_stage_split(9000.0, 2, 300.0, 0.1)
        self.assertAlmostEqual(r, 4.6162, delta=1e-3)
        self.assertAlmostEqual(lam, 0.12959, delta=1e-4)
        self.assertAlmostEqual(lam_tot, 0.01679, delta=1e-4)

    def test_stage_count_anchor(self):
        # stage_count_for_delta_v(9000, 300, 0.1, 0.02) = (3, 0.0243).
        n, lam_tot = stage_count_for_delta_v(9000.0, 300.0, 0.1, 0.02)
        self.assertEqual(n, 3)
        self.assertAlmostEqual(lam_tot, 0.0243, delta=1e-3)

    def test_stage_dv_from_indices_anchor(self):
        # 300 s, eps 0.1, lam 0.05 -> 5681.06 m/s (leaf anchor).
        self.assertAlmostEqual(stage_delta_v_from_indices(300.0, 0.1, 0.05),
                               5681.06, delta=0.5)

    def test_characteristic_velocity_anchor(self):
        # delivered c* = Pc*At/mdot: 7 MPa, 0.02 m2, 80 kg/s -> 1750.
        self.assertAlmostEqual(theoretical_cstar(3670.0, 23.0, 1.2),
                               1776.05, delta=0.5)
        from rocket_propulsion_core import characteristic_velocity
        self.assertAlmostEqual(characteristic_velocity(7.0e6, 0.02, 80.0),
                               1750.0, places=6)

    def test_chamber_geometry_relations(self):
        self.assertAlmostEqual(contraction_ratio(0.07, 0.02), 3.5)
        self.assertAlmostEqual(chamber_volume(0.9, 0.02), 0.018)
        self.assertAlmostEqual(vacuum_specific_impulse(252000.0, 80.0),
                               321.2, delta=0.1)

    def test_nozzle_mach_and_thrust(self):
        # Supersonic branch only: area ratio <= 1 must raise.
        with self.assertRaises(ValueError):
            exit_mach_from_area_ratio(1.0)
        me = exit_mach_from_area_ratio(16.0, 1.2)
        self.assertGreater(me, 3.0)
        # F = mdot*ve + (Pe - Pa)*Ae
        self.assertAlmostEqual(ideal_thrust(10.0, 3000.0, 50000.0,
                                            101325.0, 0.01),
                               30000.0 + (50000.0 - 101325.0) * 0.01)

    def test_solid_ballistics(self):
        # Vieille rate at 7 MPa: a=2e-5, n=0.35 -> ~4.98 mm/s.
        rate = burn_rate(7.0e6, 2.0e-5, 0.35)
        self.assertAlmostEqual(rate, 4.98e-3, delta=1e-4)
        # Equilibrium pressure closes the mass balance (Kn = 500).
        pc = equilibrium_chamber_pressure(1800.0, 2.0e-5, 0.35, 180.5,
                                          0.361, 1600.0)
        self.assertAlmostEqual(pc / 1.0e6, 7.25, delta=0.1)
        mdot_choked = solid_mass_flow(pc, 0.361, 1600.0)
        mdot_gen = 1800.0 * 180.5 * burn_rate(pc, 2.0e-5, 0.35)
        self.assertAlmostEqual(mdot_choked / mdot_gen, 1.0, delta=1e-2)

    def test_cooling_worked_anchors(self):
        # Leaf worked LOX/RP-1 subscale chamber anchors.
        aw = chamber_cooling_summary(
            7.0e6, 1750.0, 3500.0, 1.2, 0.15, 12000.0,
            hydraulic_diameter_m=0.002)
        self.assertAlmostEqual(aw["throat_area_m2"], 0.017671, delta=1e-5)
        self.assertAlmostEqual(aw["chamber_mass_flow_kg_s"], 70.6858,
                               delta=1e-2)
        self.assertAlmostEqual(aw["recovery_temp_k"], 3466.998, delta=0.1)
        self.assertAlmostEqual(aw["h_g"], 10681.98, delta=1.0)
        self.assertAlmostEqual(aw["h_c"], 10391.44, delta=1.0)
        self.assertAlmostEqual(aw["heat_flux_wm2"], 16.350e6, delta=1e4)
        self.assertAlmostEqual(aw["hot_wall_temp_k"], 1936.34, delta=1.0)
        self.assertTrue(aw["film_cooling_handoff"])
        self.assertAlmostEqual(aw["required_mass_flux"], 137168.0,
                               delta=50.0)
        self.assertAlmostEqual(throat_area(0.15), 0.017671, delta=1e-5)
        hg = bartz_hot_gas_coefficient(7.0e6, 1750.0, 0.15, 8.0e-5, 2000.0,
                                       0.72)
        self.assertAlmostEqual(hg, 10681.98, delta=1.0)
        co = coolant_side_coefficient(12000.0, 0.002, 0.0022, 2000.0, 0.13)
        self.assertAlmostEqual(co["reynolds"], 10909.09, delta=1.0)
        self.assertAlmostEqual(co["prandtl"], 33.846, delta=0.1)
        self.assertAlmostEqual(co["nusselt"], 159.87, delta=1.0)

    def test_feed_cycle_balance(self):
        res = engine_cycle_analysis("gas-generator", 4105.0e3, 10.0e6,
                                    "LOX/RP-1", burn_time=190.0)
        self.assertTrue(res["feasible"])
        self.assertAlmostEqual(res["mdot"], 4105.0e3 / (300.0 * 9.80665),
                               delta=0.1)
        self.assertAlmostEqual(res["mdot_ox"] / res["mdot_f"], 2.56,
                               delta=1e-9)
        self.assertGreater(res["turbine_power"], res["pump_power_total"])
        self.assertGreaterEqual(res["power_balance"], 0.0)

    def test_density_impulse(self):
        self.assertEqual(density_impulse(300.0, 1000.0), 300000.0)

    def test_choked_cold_gas(self):
        # nitrogen factor at 300 K: p*A/sqrt(T) scaling.
        m = choked_mass_flow(25.0e6, 300.0, 7.854e-7)
        self.assertAlmostEqual(m, 0.04505, delta=1e-3)

    def test_tvc_side_force(self):
        self.assertAlmostEqual(side_force(4105.0e3, 0.0873),
                               4105.0e3 * 0.0872, delta=4105.0e3 * 1e-3)


class TestReportBuilder(unittest.TestCase):

    def test_example_report_gates_pass(self):
        model = build_report(example_item())
        self.assertEqual(model["status"], "draft-for-review")
        self.assertTrue(model["staging"]["booster"]["m0_kg"] > 0)
        self.assertTrue(model["staging"]["upper"]["m0_kg"] > 0)
        gates = check_report(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_example_markdown_complete(self):
        md = example_report_markdown()
        for sec in ["## 1. Mission requirements", "## 3. Staging and sizing",
                    "## 5. Booster engine feed cycle", "## 8. Booster "
                    "thrust-chamber cooling", "## 12. Performance summary"]:
            self.assertIn(sec, md)
        low = md.lower()
        self.assertIn("not an approval", low)
        self.assertIn("not a launch readiness decision", low)
        self.assertIn("gas-generator", low)
        self.assertIn("staged-combustion", low)
        self.assertIn("m/s", md)
        self.assertIn("MPa", md)
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
        self.assertGreater(len(md), 5000)
        self.assertTrue(check_report(model)["all_pass"])

    def test_smaller_payload_still_closes(self):
        item = example_item()
        item.payload_kg = 2000.0
        model = build_report(item)
        self.assertTrue(check_report(model)["all_pass"])
        self.assertGreater(model["ascent"]["margin_ms"], 200.0)

    def test_model_json_roundtrip(self):
        import json
        model = build_report(example_item())
        text = json.dumps(model)
        back = json.loads(text)
        self.assertEqual(back["document_type"],
                         "Rocket Propulsion System Design Report")
        self.assertEqual(back["staging"]["booster"]["pair"], "LOX/RP-1")


if __name__ == "__main__":
    unittest.main()
