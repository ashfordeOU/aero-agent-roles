#!/usr/bin/env python3
"""Test composites_structures_core: the executable engine of the
Composite Structures Engineer role.

Proves the role can DO its job standalone (no AeroSkills needed):
CLT laminate stiffness (A and D), failure criteria, first-ply-failure,
hygrothermal response, plate buckling, the report builder, and the
evidence-gate checks. Every anchor value here is either exact CLT
arithmetic or a published worked-example value from the bound AeroSkills
composite leaves (T300/5208-style lamina constants).
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
import composites_structures_core as core  # noqa: E402

T = core.MAT_T300
E1, E2, G12, NU12 = T["e1_pa"], T["e2_pa"], T["g12_pa"], T["nu12"]
XT, XC, YT, YC, S = (T["xt_mpa"], T["xc_mpa"], T["yt_mpa"],
                     T["yc_mpa"], T["s_mpa"])
TPLIES = core._default_layup()


class TestLaminateStiffness(unittest.TestCase):

    def test_ply_q_leaf_worked_values(self):
        # T300/5208 plane-stress stiffness (leaf worked example):
        # q11 = 181.81 GPa, q22 = 10.35 GPa, q12 = 2.90 GPa, q66 = 7.17
        q = core.ply_q(E1, E2, NU12, G12)
        self.assertAlmostEqual(q[0] / 1e9, 181.81, places=1)
        self.assertAlmostEqual(q[2] / 1e9, 10.35, places=1)
        self.assertAlmostEqual(q[1] / 1e9, 2.90, places=1)
        self.assertAlmostEqual(q[3] / 1e9, 7.17, places=2)

    def test_rotation_zero_degrees_is_identity(self):
        q = core.ply_q(E1, E2, NU12, G12)
        qb = core.rotated_ply_stiffness(E1, E2, NU12, G12, 0.0)
        self.assertAlmostEqual(qb[0], q[0], places=3)   # q11b
        self.assertAlmostEqual(qb[1], q[1], places=3)   # q12b
        self.assertAlmostEqual(qb[3], q[2], places=3)   # q22b
        self.assertAlmostEqual(qb[5], q[3], places=3)   # q66b
        self.assertAlmostEqual(qb[2], 0.0, places=3)    # q16b
        self.assertAlmostEqual(qb[4], 0.0, places=3)    # q26b

    def test_unidirectional_a11_identity(self):
        # 8 x 0-deg plies: A11 = q11 * total thickness
        plies = [(0.0, T["t_ply_m"])] * 8
        a = core.laminate_a_matrix(plies, E1, E2, NU12, G12)
        q11 = core.ply_q(E1, E2, NU12, G12)[0]
        self.assertAlmostEqual(a[0], q11 * 8 * T["t_ply_m"], places=1)

    def test_single_ply_d11_closed_form(self):
        # One ply of thickness h: D11 = q11 * h^3 / 12
        h = 2.0 * T["t_ply_m"]
        plies = [(0.0, h)]
        d = core.laminate_d_matrix(plies, E1, E2, NU12, G12)
        q11 = core.ply_q(E1, E2, NU12, G12)[0]
        self.assertAlmostEqual(d[0], q11 * h ** 3 / 12.0, places=1)

    def test_qi_effective_constants(self):
        it = core.example_item()
        st = core.analyze_stiffness(it)
        self.assertAlmostEqual(st["h_mm"], 2.0, places=3)
        self.assertTrue(st["balanced_symmetric"])
        # quasi-isotropic in-plane: Ex ~ 69.7 GPa, nu_xy ~ 0.296
        self.assertAlmostEqual(st["ex_gpa"], 69.7, delta=0.5)
        self.assertAlmostEqual(st["nu_xy"], 0.296, delta=0.01)
        self.assertAlmostEqual(st["a11_n_per_m"], 152.74e6,
                               delta=0.1e6)


class TestFailureCriteria(unittest.TestCase):

    def test_tsai_wu_uniaxial_tension_anchor(self):
        # Pure fiber tension at Xt must give F.I. = 1 exactly when
        # Xt = Xc: FI = F1*Xt + F11*Xt^2 = (1 - Xt/Xc) + Xt/Xc = 1.
        fi = core.tsai_wu_index(XT, 0.0, 0.0, XT, XC, YT, YC, S)
        self.assertAlmostEqual(fi, 1.0, places=9)

    def test_max_stress_by_sign(self):
        m1 = core.max_stress_index(700.0, 0.0, 0.0, XT, XC, YT, YC, S)
        self.assertAlmostEqual(m1, 700.0 / XT, places=9)
        m2 = core.max_stress_index(-900.0, 0.0, 0.0, XT, XC, YT, YC, S)
        self.assertAlmostEqual(m2, 900.0 / XC, places=9)

    def test_tsai_wu_rejects_nonpositive_allowables(self):
        with self.assertRaises(ValueError):
            core.tsai_wu_index(1.0, 0.0, 0.0, 0.0, XC, YT, YC, S)

    def test_governing_criterion_compression_panel(self):
        # Compression-dominated example: max-stress governs over Tsai-Wu.
        it = core.example_item()
        fl = core.analyze_failure(it)
        self.assertEqual(fl["governing_criterion"], "max-stress")
        self.assertGreater(fl["governing_index"], 0.0)
        self.assertGreater(fl["knockdowned_basis_rf"], 1.0)


class TestFirstPlyFailure(unittest.TestCase):

    def test_fpf_strain_anchor(self):
        # Leaf-worked numbers on the 16-ply QI stack: ex = -5.0634e-4
        # at Nx = -75 N/mm (checked against the bound leaf logic).
        it = core.example_item()
        fl = core.analyze_failure(it)
        self.assertAlmostEqual(fl["strain_midplane"]["ex"], -5.0634e-4,
                               places=6)
        self.assertEqual(len(fl["per_ply"]), 16)

    def test_per_ply_zero_ply_stress_recovered(self):
        it = core.example_item()
        fl = core.analyze_failure(it)
        zero = next(r for r in fl["per_ply"] if r["angle"] == 0)
        self.assertAlmostEqual(zero["s1_mpa"], -91.91, delta=0.5)
        self.assertLess(zero["tsai_wu"], 0.0)  # inside surface, compression

    def test_knockdown_product(self):
        it = core.example_item()
        val = core.knockdown(XC, it.env_factor, it.bvid_factor,
                             it.hole_factor)
        self.assertAlmostEqual(val, XC * 0.90 * 0.85 * 1.0, places=6)
        with self.assertRaises(ValueError):
            core.knockdown(XC, env_factor=1.2)  # factor > 1 rejected

    def test_basis_statements(self):
        self.assertIn("90%", core.basis_statement("B"))
        self.assertIn("99%", core.basis_statement("A"))
        with self.assertRaises(ValueError):
            core.basis_statement("C")


class TestHygrothermal(unittest.TestCase):

    def test_equilibrium_moisture(self):
        self.assertAlmostEqual(core.equilibrium_moisture_content(0.6),
                               0.009, places=9)
        with self.assertRaises(ValueError):
            core.equilibrium_moisture_content(1.2)

    def test_unidirectional_cte_identity(self):
        # Exact CLT must return alpha_1 for a 0-deg unidirectional ply.
        plies = [{"e1": E1, "e2": E2, "nu12": NU12, "g12": G12,
                  "theta_deg": 0.0, "t": T["t_ply_m"],
                  "alpha_1": T["alpha_1"], "alpha_2": T["alpha_2"],
                  "beta_1": T["beta_1"], "beta_2": T["beta_2"]}] * 8
        coefs = core.laminate_cte_cme(plies)
        self.assertAlmostEqual(coefs["alpha_x"], T["alpha_1"], places=15)

    def test_cross_ply_cte_leaf_worked_value(self):
        # [0/90]s worked example: alpha_x = 1.59998e-6/K,
        # beta_x = 0.04014 (leaf-documented real output).
        plies = []
        for th in (0.0, 90.0, 90.0, 0.0):
            plies.append({"e1": E1, "e2": E2, "nu12": NU12, "g12": G12,
                          "theta_deg": th, "t": T["t_ply_m"],
                          "alpha_1": T["alpha_1"],
                          "alpha_2": T["alpha_2"],
                          "beta_1": T["beta_1"], "beta_2": T["beta_2"]})
        coefs = core.laminate_cte_cme(plies)
        self.assertAlmostEqual(coefs["alpha_x"] * 1e6, 1.59998, places=3)
        self.assertAlmostEqual(coefs["beta_x"], 0.04014, places=4)

    def test_qi_hygrothermal_response_model(self):
        it = core.example_item()
        hy = core.analyze_hygrothermal(it)
        self.assertAlmostEqual(hy["equilibrium_moisture"], 0.009, places=6)
        self.assertAlmostEqual(hy["alpha_x_ppm"], 7.75, delta=0.02)
        # moisture swelling dominates the cooldown contraction
        self.assertGreater(hy["hygrothermal_strain_x"], 0.0)
        self.assertLess(hy["cure_strain_x"], 0.0)


class TestBuckling(unittest.TestCase):

    def test_critical_load_isotropic_plate_anchor(self):
        # Simply supported square isotropic plate, m=n=1:
        # N_x_cr = 4*pi^2*D / a^2 for the isotropic relation
        # D11 = D, D12 = nu*D, D66 = D(1-nu)/2 with D22 = D.
        d = 10.0
        nu = 0.3
        d12 = nu * d
        d66 = d * (1.0 - nu) / 2.0
        a = 0.5
        # terms: D(m/a)^2 + 2(D12+2D66)(n/b)^2 + D n^4 a^2/(m^2 b^4)
        # with a=b: each of the two equal to D/a^2*... total = 4 D / a^2
        ncr = core.plate_critical_load(d, d, d12, d66, a, a, 1, 1)
        self.assertAlmostEqual(ncr, 4.0 * math.pi ** 2 * d / a ** 2,
                               places=6)

    def test_example_panel_margin(self):
        it = core.example_item()
        sb = core.analyze_stability(it)
        self.assertEqual(sb["mode"], (1, 1))
        self.assertGreater(sb["margin"], 1.0)   # no predicted buckling
        self.assertAlmostEqual(sb["margin"], 1.31, delta=0.02)

    def test_buckling_margin_requires_positive_load(self):
        with self.assertRaises(ValueError):
            core.buckling_margin(1, 1, 1, 1, 0.1, 0.1, 0.0)


class TestBuilderAndGates(unittest.TestCase):

    def test_example_report_model(self):
        model = core.build_report(core.example_item())
        self.assertEqual(model["status"], "draft-for-review")
        self.assertEqual(model["item"]["name"],
                         "Vertical stabilizer skin panel, bay P2 "
                         "(between stringers S3 and S4)")
        self.assertEqual(model["material"]["basis"], "B")

    def test_core_gates_all_pass(self):
        model = core.build_report(core.example_item())
        gates = core.check_report(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_sign_off_gate_fails_when_status_changed(self):
        model = core.build_report(core.example_item())
        model["status"] = "approved"
        gates = core.check_report(model)
        self.assertFalse(gates["sign_off_honest"])
        self.assertFalse(gates["all_pass"])

    def test_markdown_gates_all_pass(self):
        md = core.example_report_markdown()
        gates = core.check_report_markdown(md)
        self.assertTrue(gates["all_pass"], gates)

    def test_rendered_report_structure(self):
        md = core.example_report_markdown()
        for sec in ["## 1. Scope", "## 2. Materials and design allowables",
                    "## 3. Laminate definition and stiffness",
                    "## 4. Stress analysis and failure indices",
                    "## 5. Hygrothermal response",
                    "## 6. Stability (plate buckling)",
                    "## 7. Conclusions and certification readiness"]:
            self.assertIn(sec, md)
        low = md.lower()
        self.assertIn("not an approval", low)
        self.assertIn("not a certification", low)
        self.assertIn("tsai-wu", low)
        self.assertIn("n_x_cr", low)

    def test_standalone_no_skills_repo(self):
        # Core must work with no AeroSkills present. Restore the env var
        # afterwards so later tests in the same pytest process (which
        # import cli.py and re-read AEROSKILLS_DEV at import time) still
        # see the real skills checkout.
        old = os.environ.get("AEROSKILLS_DEV")
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        try:
            model = core.build_report(core.example_item())
            gates = core.check_report(model)
            self.assertTrue(gates["all_pass"], gates)
            md = core.render_report_markdown(model)
            self.assertGreater(len(md), 3000)
        finally:
            if old is None:
                os.environ.pop("AEROSKILLS_DEV", None)
            else:
                os.environ["AEROSKILLS_DEV"] = old


if __name__ == "__main__":
    unittest.main()
