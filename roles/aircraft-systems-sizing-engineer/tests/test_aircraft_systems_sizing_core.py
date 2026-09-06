#!/usr/bin/env python3
"""Test aircraft_systems_sizing_core: the executable engine of the role.

Proves the role can DO its job standalone (no AeroSkills needed): real
sizing formulas per system (electrical load rollup, ACM pack balance,
avionics bay cooling, oxygen, brakes, valves, fuel feed, jettison,
inerting, hydraulic actuation, gear layout, RAT, tires, windows), the
report builder, the evidence gates, and - when the AeroSkills checkout
is present - cross-check agreement with the bound leaf logic files.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from aircraft_systems_sizing_core import (  # noqa: E402
    build_report, check_report, check_report_markdown,
    continuous_load, design_pressure_differential, example_item,
    example_report_markdown, generator_out_margin, jettison_summary,
    pane_thickness, render_report_markdown, required_bleed_flow,
    required_jettison_rate, static_load_per_tire, tire_diameter_inches,
    tipback_angle, rto_energy_J,
)

AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))


class TestDomainRules(unittest.TestCase):

    def test_continuous_load_duty_weighted(self):
        # 10 kVA at 0.5 duty -> 5 kVA continuous
        r = continuous_load({"pump": (10.0, 0.5), "avionics": (5.0, 1.0)})
        self.assertAlmostEqual(r["continuous_kva"], 10.0)
        self.assertEqual(r["rollup"], [5.0, 5.0])

    def test_generator_out_margin(self):
        # 2 x 90 kVA, essential 26.5 kVA -> remaining 90, margin +0.706
        out = generator_out_margin(2, 90.0, 26.5)
        self.assertEqual(out["remaining_kva"], 90.0)
        self.assertGreater(out["margin"], 0.7)
        self.assertEqual(out["verdict"], "PASS")
        # single generator: no redundancy
        out1 = generator_out_margin(1, 90.0, 26.5)
        self.assertEqual(out1["verdict"], "FAIL")
        self.assertEqual(out1["margin"], -1.0)

    def test_rto_energy(self):
        # 0.5 * 79000 * 77^2 = 234.1 MJ
        self.assertAlmostEqual(rto_energy_J(79000.0, 77.0),
                               0.5 * 79000 * 77 * 77, places=1)

    def test_jettison_rate_900s(self):
        # (79000-66000)/900 = 14.44 kg/s
        self.assertAlmostEqual(required_jettison_rate(79000.0, 66000.0),
                               13000.0 / 900.0, places=3)
        s = jettison_summary(79000.0, 66000.0, 2)
        self.assertLessEqual(s["time_s"], 900.0)
        self.assertEqual(s["verdict"], "PASS")

    def test_tire_fit(self):
        # 39187 lb -> diameter ~45.6 in (class-I fit exponents)
        d = tire_diameter_inches(39187.0)
        self.assertGreater(d, 40.0)
        self.assertLess(d, 50.0)
        sl = static_load_per_tire(79000.0, 0.9, 4)
        self.assertAlmostEqual(sl, 17775.0)

    def test_tipback(self):
        # margin 0.7 m / h_cg 1.8 m -> atan(0.3889) ~ 21.3 deg
        a = tipback_angle(1.8, 15.0, 14.3)
        self.assertAlmostEqual(a, 21.25, places=1)

    def test_window_pressure(self):
        w = design_pressure_differential(2438.0, 11887.0)
        self.assertGreater(w["design_differential_pa"], 70000.0)
        t = pane_thickness(w["design_differential_pa"], 0.145, 40e6)
        self.assertGreater(t, 0.004)
        self.assertLess(t, 0.008)


class TestReportBuilder(unittest.TestCase):

    def test_example_all_verdicts_pass(self):
        model = build_report(example_item())
        self.assertEqual(len(model["verdicts"]), 14)
        for name, ver in model["verdicts"].items():
            self.assertEqual(ver, "PASS", "system %s failed: %s"
                             % (name, ver))
        self.assertEqual(model["status"], "draft-for-review")

    def test_fourteen_systems_sized(self):
        model = build_report(example_item())
        self.assertEqual(len(model["systems"]), 14)
        # spot-check real numbers are present per system
        s = model["systems"]
        self.assertGreater(s["electrical"]["continuous_kva"], 30.0)
        self.assertGreater(s["air_cycle_machine"]["t2_k"], 450.0)
        self.assertGreater(s["oxygen"]["bottle_volume_l"], 5.0)
        self.assertGreater(s["brakes"]["E_rto_J"], 1e8)
        self.assertGreater(s["windows"]["pane_thickness_mm"], 4.0)

    def test_core_gates_all_pass(self):
        model = build_report(example_item())
        gates = check_report(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_all_pass(self):
        md = example_report_markdown()
        gates = check_report_markdown(md)
        self.assertTrue(gates["all_pass"], gates)
        for n in range(1, 15):
            self.assertIn("## %d." % n, md)

    def test_standalone_no_skills_repo(self):
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = build_report(example_item())
        self.assertTrue(model["status"] == "draft-for-review")
        md = render_report_markdown(model)
        self.assertGreater(len(md), 3000)
        self.assertIn("not an approval", md.lower())


class TestDispatchCrossCheck(unittest.TestCase):
    """When AeroSkills is present, core numbers agree with the leaves."""

    def _import_leaf(self, leaf):
        import importlib.util
        logic_dir = os.path.join(AEROSKILLS, "skills", leaf, "scripts")
        if not os.path.isdir(logic_dir):
            return None
        for lf in sorted(os.listdir(logic_dir)):
            if lf.endswith("_logic.py"):
                path = os.path.join(logic_dir, lf)
                spec = importlib.util.spec_from_file_location("l", path)
                mod = importlib.util.module_from_spec(spec)
                try:
                    spec.loader.exec_module(mod)
                    return mod
                except Exception:
                    continue
        return None

    def test_electrical_leaf_agrees(self):
        if not HAS_SKILLS:
            self.skipTest("AeroSkills not present")
        mod = self._import_leaf("vehicle-design/sizing/"
                                "aircraft-electrical-load-analysis")
        item = example_item()
        core_v = continuous_load(item.consumers)["continuous_kva"]
        skill_v = mod.continuous_load(item.consumers)["continuous_kva"]
        self.assertAlmostEqual(core_v, skill_v, places=6)

    def test_bleed_flow_leaf_agrees(self):
        if not HAS_SKILLS:
            self.skipTest("AeroSkills not present")
        mod = self._import_leaf("vehicle-design/sizing/air-cycle-machine-sizing")
        # same state as the example pack: cooling load = cp*flow*(T4-288)
        core_v = required_bleed_flow(7133.611867836247, 280.0, 288.0)
        skill_v = mod.required_bleed_flow(7133.611867836247, 280.0, 288.0)
        self.assertAlmostEqual(core_v, skill_v, places=6)

    def test_window_leaf_agrees(self):
        if not HAS_SKILLS:
            self.skipTest("AeroSkills not present")
        mod = self._import_leaf("vehicle-design/sizing/window-aperture-sizing")
        item = example_item()
        w = design_pressure_differential(item.window_cabin_altitude_m,
                                         item.window_flight_altitude_m)
        core_v = pane_thickness(w["design_differential_pa"],
                                item.window_radius_m,
                                item.window_allowable_stress_pa)
        skill_v = mod.pane_thickness(w["design_differential_pa"],
                                     item.window_radius_m,
                                     item.window_allowable_stress_pa)
        self.assertAlmostEqual(core_v, skill_v, places=9)


if __name__ == "__main__":
    unittest.main()
