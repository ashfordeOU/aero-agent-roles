#!/usr/bin/env python3
"""Test fem_analysis_core: the executable engine of the FEM role.

Proves the role can DO its job standalone (no AeroSkills needed):
2D truss and frame direct-stiffness solves, beam-column interaction,
Euler buckling, beam vibration, 2-DOF modal, shear center and lug
analyses, the Finite Element Analysis Report builder, and the evidence
gates. Reference numbers are the documented anchors of the bound FEM
leaf logic modules (verified against them during role build).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
import fem_analysis_core as core  # noqa: E402

E_STEEL = 200e9
I_BAR = 1e-6
L_BAR = 3.0


class TestDomainRules(unittest.TestCase):

    def test_euler_load_anchor(self):
        # steel column E=200 GPa, I=1e-6, L=3 m -> 219.3 kN (pinned)
        self.assertAlmostEqual(core.euler_load(E_STEEL, I_BAR, L_BAR, 1.0),
                               219324.54224643015, places=3)
        # cantilever (K=2) quarters the pinned load
        self.assertAlmostEqual(core.euler_load(E_STEEL, I_BAR, L_BAR, 2.0),
                               219324.54224643015 / 4.0, places=3)

    def test_buckling_helpers(self):
        self.assertAlmostEqual(
            core.critical_buckling_load(E_STEEL, I_BAR, L_BAR, 1.0),
            219324.54224643015, places=3)
        self.assertAlmostEqual(core.radius_of_gyration(1e-6, 1e-3),
                               0.0316227766, places=6)
        self.assertAlmostEqual(core.transition_slenderness(E_STEEL, 250e6),
                               88.8626, places=2)

    def test_column_check_anchor(self):
        cc = core.column_check(E_STEEL, I_BAR, 1e-3, L_BAR,
                               "pinned-pinned", 100e3, 250e6)
        self.assertAlmostEqual(cc["margin_of_safety"], 1.193245, places=3)
        self.assertGreater(cc["slenderness_ratio"],
                           cc["transition_slenderness"])
        self.assertTrue(cc["euler_governs"])

    def test_beam_column_anchor(self):
        # worked brace: 28 mm round, L = 0.424264 m, P = 50.912 kN
        pe = core.euler_load(71.7e9, 3.017185584507638e-08, 0.4242640687)
        self.assertAlmostEqual(pe, 118617.40536, places=2)
        amp = core.moment_amplification(50911.688245, pe, 0.85)
        self.assertAlmostEqual(amp, 1.489162, places=5)
        inter = core.interaction_check(50911.688245, pe, 101.823376,
                                       1010.757171, pe)
        self.assertAlmostEqual(inter["margin"], 0.650980, places=5)
        self.assertTrue(inter["pass"])

    def test_truss_anchor_three_bar(self):
        # symmetric three-bar truss, 100 kN apex load (leaf anchor)
        nodes = [(0.0, 0.0), (4.0, 3.0), (8.0, 0.0)]
        elements = [(0, 1, E_STEEL, 1e-3), (1, 2, E_STEEL, 1e-3),
                    (0, 2, E_STEEL, 1e-3)]
        r = core.truss_analysis(nodes, elements,
                                {(1, "y"): -100e3},
                                [(0, "x"), (0, "y"), (2, "y")])
        self.assertAlmostEqual(r["displacements"][3], -5.25e-3, places=6)
        self.assertAlmostEqual(r["member_forces"][0], -83333.333, places=1)
        self.assertAlmostEqual(r["member_forces"][2], 66666.667, places=1)
        self.assertAlmostEqual(r["reactions"][(0, "y")], 50e3, places=0)
        self.assertAlmostEqual(r["reactions"][(2, "y")], 50e3, places=0)

    def test_frame_anchor_cantilever(self):
        # cantilever beam element anchor: P=1000 N, E=70 GPa, I=4e-6, L=2 m
        r = core.solve_frame(
            [(0.0, 0.0), (2.0, 0.0)],
            [{"i": 0, "j": 1, "E": 70e9, "A": 1e-3, "I": 4e-6}],
            [(0, ("u", "v", "theta"))],
            {(1, "v"): -1000.0})
        self.assertAlmostEqual(r["displacements"][(1, "v")],
                               -0.0095238, places=5)
        self.assertAlmostEqual(r["displacements"][(1, "theta")],
                               0.0071429, places=5)
        self.assertAlmostEqual(r["reactions"][(0, "v")], 1000.0, places=2)
        self.assertAlmostEqual(r["reactions"][(0, "theta")], -2000.0,
                               places=1)
        self.assertTrue(r["equilibrium_ok"])

    def test_beam_vibration_anchor(self):
        # steel rod d=10 mm, L=0.45 m: f1 ~ 100.3 Hz
        e_rod, d_rod, l_rod, rho = 210e9, 0.010, 0.45, 7850.0
        a = 3.141592653589793 * d_rod ** 2 / 4.0
        i = 3.141592653589793 * d_rod ** 4 / 64.0
        m = rho * a
        self.assertAlmostEqual(
            core.pinned_pinned_frequency(1, e_rod * i, m, l_rod),
            100.302019, places=4)
        f2 = core.pinned_pinned_frequency(2, e_rod * i, m, l_rod)
        f1 = core.pinned_pinned_frequency(1, e_rod * i, m, l_rod)
        self.assertAlmostEqual(f2, 4.0 * f1, places=6)

    def test_cantilever_root_first(self):
        # published first cantilever root 1.87510407 -> frequency check
        ei, m, l = 103.083, 0.6165, 0.45
        f1 = core.cantilever_frequency(1, ei, m, l)
        f1_clamped = core.clamped_clamped_frequency(1, ei, m, l)
        # cantilever first root < clamped first root (4.730) < cant 2nd (4.694)
        self.assertLess(f1, f1_clamped)
        # f = (beta1 L)^2 sqrt(EI/(m L^4)) / 2pi with beta1 = 1.87510407
        self.assertAlmostEqual(
            f1, 1.87510407 ** 2 * (ei / (m * l ** 4)) ** 0.5
            / (2 * 3.141592653589793), places=6)

    def test_modal_two_dof(self):
        wns = core.natural_frequencies(1.0, 1.0, 1.0, 1.0)
        # equal masses/springs: w^2 = (3 +- sqrt(5))/2
        w2_low = (3.0 - 5.0 ** 0.5) / 2.0
        self.assertAlmostEqual(wns[0], w2_low ** 0.5, places=6)
        self.assertEqual(len(core.mode_shapes(1.0, 1.0, 1.0, 1.0)), 2)
        rc = core.resonance_check(wns[0], wns, 0.1)
        self.assertTrue(rc["resonance"])
        rc2 = core.resonance_check(0.01, wns, 0.1)
        self.assertFalse(rc2["resonance"])

    def test_shear_center_anchor(self):
        self.assertAlmostEqual(core.channel_classical_e(0.1, 0.05),
                               0.01875, places=6)
        e_m, fx, fy, ixx = core.shear_center_channel(0.1, 0.05, 0.004,
                                                     1000.0, 400)
        self.assertAlmostEqual(abs(e_m), 0.01875, places=5)
        self.assertAlmostEqual(ixx, 1.3338666667e-6, places=9)

    def test_lug_anchor(self):
        r = core.lug_analysis(36000.0, 0.0127, 0.00635, 0.0381, 0.01905,
                              469e6, 296e6, 552e6)
        self.assertAlmostEqual(r["bearing_stress_pa"], 446.4e6, delta=1e3)
        self.assertEqual(r["governing_mode"], "bearing")
        self.assertAlmostEqual(r["min_margin"], 0.236557, places=4)
        self.assertTrue(r["passes"])
        cap = core.lug_allowable_capacity(0.0127, 0.00635, 0.01905,
                                          469e6, 296e6, 552e6)
        self.assertEqual(cap["limiting_mode"], "bearing")
        self.assertAlmostEqual(cap["limiting_capacity_n"], 44516.04,
                               places=1)


class TestReportBuilder(unittest.TestCase):

    def test_example_report_model(self):
        model = core.build_report(core.example_item())
        self.assertEqual(model["status"], "draft-for-review")
        self.assertEqual(model["document_type"],
                         "Finite Element Analysis Report")
        for stage in ("truss", "frame", "beam_column", "buckling",
                      "beam_vibration", "modal", "shear_center", "lug"):
            self.assertIn(stage, model["stages"])
        self.assertAlmostEqual(
            model["stages"]["beam_column"]["margin"], 0.650980, places=4)
        self.assertAlmostEqual(
            model["stages"]["buckling"]["margin_of_safety"], 1.329866,
            places=4)
        self.assertAlmostEqual(
            model["stages"]["lug"]["min_margin"], 0.236557, places=4)
        self.assertAlmostEqual(model["stages"]["truss"]["member_forces_n"][1],
                               -50911.688, places=1)

    def test_all_stages_pass(self):
        model = core.build_report(core.example_item())
        self.assertTrue(model["all_stages_pass"])
        self.assertTrue(all(r["status"] == "pass" for r in model["summary"]))

    def test_report_sections_and_markers(self):
        md = core.example_report_markdown()
        for sec in ["# Finite Element Analysis Report", "## 1. Scope",
                    "## 2. Stage 1", "## 10. Margin summary"]:
            self.assertIn(sec, md)
        low = md.lower()
        self.assertIn("draft", low)
        self.assertIn("not an approval", low)
        self.assertIn("ultimate", low)
        self.assertNotIn("___", md)

    def test_core_gates_all_pass(self):
        model = core.build_report(core.example_item())
        gates = core.check_report(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_all_pass(self):
        md = core.example_report_markdown()
        gates = core.check_report_markdown(md)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_catch_missing_draft(self):
        md = core.example_report_markdown()
        md = md.replace("DRAFT", "FINAL").replace("draft", "final")
        gates = core.check_report_markdown(md)
        self.assertFalse(gates["all_pass"])
        self.assertFalse(gates["has_draft_marker"])

    def test_standalone_no_skills_repo(self):
        # core must work with no AeroSkills present
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = core.build_report(core.example_item())
        self.assertTrue(model["all_stages_pass"])
        md = core.render_report_markdown(model)
        self.assertGreater(len(md), 3000)

    def test_dispatch_rows_self_consistent(self):
        # the dispatch kwargs rebuilt from the model reproduce the model
        model = core.build_report(core.example_item())
        rows = core.dispatch_rows(model)
        self.assertEqual(len(rows), 14)
        by_fn = {r["core_fn"]: r for r in rows}
        # truss row reproduces the apex displacement
        t = by_fn["truss_analysis"]
        out = core.truss_analysis(**t["kwargs"])
        self.assertAlmostEqual(out["displacements"][3],
                               model["stages"]["truss"]["apex_displacement_m"],
                               places=9)
        # lug row reproduces the min margin
        l = by_fn["lug_analysis"]
        self.assertAlmostEqual(core.lug_analysis(**l["kwargs"])["min_margin"],
                               model["stages"]["lug"]["min_margin"], places=9)
        # rod frequency row reproduces the stored rod f1
        bv = model["stages"]["beam_vibration"]
        self.assertAlmostEqual(
            core.pinned_pinned_frequency(**by_fn["pinned_pinned_frequency"]
                                         ["kwargs"]),
            bv["rod"]["frequencies_hz"][0], places=9)


if __name__ == "__main__":
    unittest.main()
