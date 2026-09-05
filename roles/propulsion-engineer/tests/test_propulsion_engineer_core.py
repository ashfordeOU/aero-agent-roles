#!/usr/bin/env python3
"""Test propulsion_core: the executable engine of the Propulsion Engineer.

Proves the role can DO its job standalone (no AeroSkills needed): ISA,
Brayton/real-cycle relations, turbofan on-design thrust/TSFC/efficiency,
nozzle choked/unchoked logic, compressor-map surge verdicts, off-design
envelope, bypass-ratio trade, rocket Isp/mass-split/cycle feasibility,
report builder + evidence gates, and standalone mode.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from propulsion_core import (  # noqa: E402
    PROPELLANTS, bpr_trend, build_report, build_rocket_report,
    build_turbofan_report, brayton_thermal_efficiency, check_report,
    check_report_markdown, compressor_exit_temperature,
    cycle_feasibility, example_rocket_item, example_rocket_markdown,
    example_turbofan_item, example_turbofan_markdown, exit_mach_from_area_ratio,
    isa, map_verdict, mass_flow_split, off_design_envelope, operating_line_clearance,
    real_thermal_efficiency, render_report_markdown, rocket_mass_flow,
    rocket_nozzle_sizing, thrust_split, turbofan_design_point,
    turbine_exit_temperature, turbine_power,
)

# Deterministic across midnight: pin fresh renders to the date the
# committed template carries (CI override wins).
os.environ.setdefault("ROLE_GEN_DATE", "2026-09-05")


class TestCoreDomainRules(unittest.TestCase):
    """Public-standard anchors mirrored from the bound AeroSkills leaves."""

    def test_isa_at_sea_level(self):
        s = isa(0.0)
        self.assertAlmostEqual(s["t"], 288.15, places=2)
        self.assertAlmostEqual(s["p"], 101325.0, places=1)

    def test_brayton_anchor_pr8(self):
        # Ideal Brayton at PR 8, gamma 1.4: 0.44795 (leaf anchor).
        self.assertAlmostEqual(brayton_thermal_efficiency(8.0), 0.44795,
                               delta=1e-3)

    def test_compressor_anchor(self):
        # T2 = T1*PR^((g-1)/g), 288 K / PR 8: 521.70 K (leaf anchor).
        self.assertAlmostEqual(compressor_exit_temperature(288.0, 8.0),
                               521.70, delta=0.1)
        # real-cycle with efficiency raises the exit temperature
        self.assertGreater(
            compressor_exit_temperature(288.0, 8.0, eta_c=0.85),
            compressor_exit_temperature(288.0, 8.0, eta_c=1.0))

    def test_turbine_anchor(self):
        # T4 = T3/PR^((g-1)/g), 1400 K / PR 8: 772.86 K (leaf anchor).
        self.assertAlmostEqual(turbine_exit_temperature(1400.0, 8.0, 1.4),
                               772.86, delta=0.1)

    def test_real_thermal_efficiency_order(self):
        # Requires physically ordered stations; net/heat < 1.
        eta = real_thermal_efficiency(288.0, 600.0, 1500.0, 900.0)
        self.assertGreater(eta, 0.0)
        self.assertLess(eta, 1.0)
        with self.assertRaises(ValueError):
            real_thermal_efficiency(600.0, 288.0, 1500.0, 900.0)

    def test_area_mach_supersonic(self):
        # area ratio 2 -> Mach ~1.5-2 on the supersonic branch (gamma 1.2)
        m = exit_mach_from_area_ratio(2.0, 1.2)
        self.assertGreater(m, 1.0)
        with self.assertRaises(ValueError):
            exit_mach_from_area_ratio(1.0, 1.2)  # sonic is not supersonic


class TestTurbofanDesignPoint(unittest.TestCase):
    """On-design cycle: real numbers, physical ordering, gates."""

    def test_cruise_design_point_realistic(self):
        # Reference item: BPR 8 / OPR 30 / TIT 1650 at M0.78 FL350.
        d = turbofan_design_point(0.78, 10668.0, 8.0, 1.6, 30.0, 1650.0)
        # station temperature ordering
        st = d["stations"]
        self.assertLess(st["2"]["tt"], st["13"]["tt"])
        self.assertLess(st["13"]["tt"], st["3"]["tt"])
        self.assertLess(st["3"]["tt"], st["4"]["tt"])
        self.assertLess(st["5"]["tt"], st["4"]["tt"])
        # realistic compressor exit for OPR 30 at cruise (700 K ballpark)
        self.assertTrue(600 < st["3"]["tt"] < 850, st["3"]["tt"])
        # net thrust per kg/s air positive and in a physical band (N)
        self.assertTrue(150 < d["f_net_per_kg"] < 250, d["f_net_per_kg"])
        # cruise TSFC in the modern high-bypass band: 12-20 g/(kN s)
        tsfc = d["tsfc_kg_Ns"] * 1e6
        self.assertTrue(12.0 < tsfc < 20.0, tsfc)
        # efficiencies bounded and consistent: eta_o = eta_th * eta_p
        self.assertLess(d["eta_o"], 1.0)
        self.assertLess(d["eta_p"], 1.0)
        self.assertAlmostEqual(d["eta_o"], d["eta_th"] * d["eta_p"], delta=1e-6)

    def test_scaled_to_thrust_requirement(self):
        item = example_turbofan_item()
        model = build_turbofan_report(item)
        d = model["design"]
        # sizing hits the requirement
        self.assertAlmostEqual(d["f_net"], 30000.0, delta=100.0)
        self.assertGreater(d["mdot0"], 50.0)          # 100+ kg/s class airflow
        self.assertGreater(d["mdot_fuel"], 0.3)       # kg/s fuel flow

    def test_sls_static_nozzles_unchoked(self):
        # at SLS (M0, sea level) the nozzle pressure ratios are below the
        # critical ratio (fan NPR ~1.6 < 1.89), so both are unchoked and
        # fully expanded to ambient.
        d = turbofan_design_point(0.0, 0.0, 8.0, 1.6, 30.0, 1650.0)
        self.assertFalse(d["nozzle_core"]["choked"])
        self.assertFalse(d["nozzle_fan"]["choked"])
        self.assertEqual(d["v0"], 0.0)
        # at the M0.78 / FL350 design point both nozzles are choked
        c = turbofan_design_point(0.78, 10668.0, 8.0, 1.6, 30.0, 1650.0)
        self.assertTrue(c["nozzle_core"]["choked"])
        self.assertTrue(c["nozzle_fan"]["choked"])

    def test_bad_inputs_raise(self):
        with self.assertRaises(ValueError):
            turbofan_design_point(1.2, 0.0, 8.0, 1.6, 30.0, 1650.0)
        with self.assertRaises(ValueError):
            turbofan_design_point(0.78, 10668.0, 0.0, 1.6, 30.0, 1650.0)
        with self.assertRaises(ValueError):
            turbofan_design_point(0.78, 10668.0, 8.0, 1.0, 30.0, 1650.0)
        with self.assertRaises(ValueError):
            turbofan_design_point(0.78, 10668.0, 8.0, 1.6, 30.0, 1400.0)

    def test_thrust_identity(self):
        # momentum+pressure form reproduces thrust: F = mdot(V9-V0)+(P9-P0)A9
        d = turbofan_design_point(0.78, 10668.0, 8.0, 1.6, 30.0, 1650.0)
        nc, nf = d["nozzle_core"], d["nozzle_fan"]
        f = (d["mdot_core_frac"] * (1 + d["f_air_core"]) * (nc["ve"] - d["v0"])
             + (nc["pe"] - d["p0"]) * nc["a_exit"]
             + d["mdot_fan_frac"] * (nf["ve"] - d["v0"])
             + (nf["pe"] - d["p0"]) * nf["a_exit"])
        self.assertAlmostEqual(f, d["f_net_per_kg"], delta=1e-6)


class TestOffDesignAndTrade(unittest.TestCase):
    def test_off_design_envelope_covers_points(self):
        d = turbofan_design_point(0.78, 10668.0, 8.0, 1.6, 30.0, 1650.0)
        d["mdot0"] = 100.0
        pts = [("SLS", 0.0, 0.0, 1.0), ("FL250", 7620.0, 0.78, 1.0),
               ("part power", 10668.0, 0.78, 0.6)]
        rows = off_design_envelope(d, pts)
        self.assertEqual(len(rows), 3)
        for r in rows:
            self.assertGreater(r["mdot_phys"], 0.0)
            self.assertGreater(r["f_net"], 0.0)
            self.assertIn(r["map_verdict"], ("on-map", "approaching-surge"))
            self.assertTrue(r["surge_clearance_pct"] > 0.0)
        # named point carried through, part-power below the max row
        self.assertEqual(rows[0]["name"], "SLS")
        self.assertLess(rows[2]["f_throttled"], rows[2]["f_net"])

    def test_surge_clearance_and_verdict(self):
        # clearance positive below surge; verdict on-map until within 5%
        self.assertAlmostEqual(operating_line_clearance(20.0, 23.0), 15.0)
        self.assertEqual(map_verdict(20.0, 23.0), "on-map")
        self.assertEqual(map_verdict(22.4, 23.0), "approaching-surge")
        with self.assertRaises(ValueError):
            map_verdict(23.0, 23.0)  # on/above the surge line is rejected

    def test_thrust_split_and_bpr_trend(self):
        s = thrust_split(8.0, 90.0, 500.0, 300.0, 231.0)
        self.assertGreater(s["f_total"], 0.0)
        # trend signature: bpr_trend(mdot_total, vj_core, vj_fan, v0, f_core)
        trend = bpr_trend(90.0, 500.0, 300.0, 231.0, 0.02)
        self.assertEqual(len(trend), 6)
        # fixed core/fan jet velocities, fixed total flow (leaf model):
        # higher BPR shifts flow to the slower fan stream -> specific
        # thrust and TSFC both fall monotonically.
        specs = [r["specific_thrust"] for r in trend]
        tsfcs = [r["tsfc_g_kN_s"] for r in trend]
        self.assertEqual(specs, sorted(specs, reverse=True))
        self.assertEqual(tsfcs, sorted(tsfcs, reverse=True))


class TestRocketDomain(unittest.TestCase):
    def test_propellant_table(self):
        # reference-typical values from the rocket-engine-cycle leaf
        self.assertEqual(PROPELLANTS["LOX/LH2"], (1140.0, 71.0, 5.5, 430.0))
        self.assertEqual(PROPELLANTS["LOX/RP-1"], (1140.0, 820.0, 2.56, 300.0))

    def test_mass_flow_from_isp(self):
        # mdot = F/(Isp*g0): 110 kN at Isp 430 -> ~26.1 kg/s
        m = rocket_mass_flow(110000.0, 430.0)
        self.assertAlmostEqual(m, 26.1, delta=0.2)
        mdot, mox, mf = mass_flow_split(110000.0, 430.0, 5.5)
        self.assertAlmostEqual(mdot, mox + mf, delta=1e-9)
        self.assertAlmostEqual(mox / mf, 5.5, delta=1e-9)

    def test_cycle_feasibility_bounds(self):
        # pressure-fed bound at 3 MPa; expander LOX/LH2 <= 10 MPa
        ok, _ = cycle_feasibility("pressure-fed", "LOX/LH2", 2.0e6)
        self.assertTrue(ok)
        ok, _ = cycle_feasibility("pressure-fed", "LOX/LH2", 4.0e6)
        self.assertFalse(ok)
        ok, _ = cycle_feasibility("expander", "LOX/LH2", 8.0e6)
        self.assertTrue(ok)
        ok, _ = cycle_feasibility("expander", "LOX/RP-1", 4.0e6)
        self.assertFalse(ok)   # expander needs the LH2 fuel
        ok, _ = cycle_feasibility("staged-combustion", "LOX/RP-1", 20.0e6)
        self.assertTrue(ok)

    def test_turbine_power_positive(self):
        p = turbine_power(4.0, 2000.0, 1200.0, 0.6, 1.2, 3.2e6, 0.2e6)
        self.assertGreater(p, 0.0)

    def test_nozzle_sizing(self):
        n = rocket_nozzle_sizing(26.1, 4.0e6, 3500.0, 1.2, 84.0, r_gas=693.0)
        self.assertGreater(n["a_star"], 0.0)
        self.assertGreater(n["me"], 3.0)       # supersonic, high area ratio
        self.assertLess(n["pe"], 4.0e6)
        self.assertGreater(n["cf_ideal"], 1.5)  # vacuum Cf of a good nozzle
        # ideal exit velocity implies ideal vacuum Isp > real typical
        self.assertGreater(n["ve"] / 9.80665, 430.0)

    def test_rocket_report_builder(self):
        model = build_rocket_report(example_rocket_item())
        self.assertEqual(model["engine_kind"], "rocket")
        self.assertEqual(model["cycle"]["propellant"], "LOX/LH2")
        self.assertTrue(model["cycle"]["feasible"])
        gates = check_report(model)
        self.assertTrue(gates["all_pass"], gates)
        md = render_report_markdown(model)
        self.assertIn("not an approval", md.lower())


class TestReportBuilderAndGates(unittest.TestCase):
    def test_turbofan_report_gates(self):
        model = build_report(example_turbofan_item())
        self.assertEqual(model["document_type"], "Propulsion Design Report")
        self.assertEqual(model["status"], "draft-for-review")
        gates = check_report(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates(self):
        md = example_turbofan_markdown()
        gates = check_report_markdown(md)
        self.assertTrue(gates["all_pass"], gates)
        for section in ("## 1. Requirement", "## 2. Cycle analysis",
                        "## 3. Off-design", "## 4. Component selection",
                        "## 8. Bypass-ratio trade"):
            self.assertIn(section, md)
        self.assertIn("not an approval", md.lower())

    def test_report_has_computed_numbers(self):
        # evidence gate: every headline performance claim is a number
        md = example_turbofan_markdown()
        self.assertRegex(md, r"kN")
        self.assertRegex(md, r"g/\(kN\.s\)|lb/\(lbf\.h\)")
        self.assertRegex(md, r"\d+\.\d+ kg/s")
        self.assertRegex(md, r"K")

    def test_rocket_markdown_no_blank_template(self):
        md = example_rocket_markdown()
        self.assertNotIn("___", md)
        self.assertIn("not an approval", md.lower())

    def test_deliverable_template_filled(self):
        # templates/propulsion-report-template.md is the FILLED example
        # deliverable (the reference turbofan item): zero blanks, and it
        # matches what the core renders today (modulo the date footer).
        here = os.path.dirname(os.path.abspath(__file__))
        tmpl = os.path.join(here, "..", "templates",
                            "propulsion-report-template.md")
        with open(tmpl) as f:
            text = f.read()
        self.assertNotIn("___", text)
        low = text.lower()
        self.assertIn("not an approval", low)
        self.assertIn("draft", low)
        fresh = example_turbofan_markdown()
        norm = lambda s: re.sub(r"\(20\d\d-\d\d-\d\d\)", "(DATE)", s)
        self.assertEqual(norm(text), norm(fresh))

    def test_standalone_no_skills_repo(self):
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        for item, render in ((example_turbofan_item(), example_turbofan_markdown),
                             (example_rocket_item(), example_rocket_markdown)):
            model = build_report(item)
            self.assertTrue(check_report(model)["all_pass"])
            md = render()
            self.assertGreater(len(md), 1000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
