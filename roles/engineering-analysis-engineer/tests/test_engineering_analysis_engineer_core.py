#!/usr/bin/env python3
"""Test engineering_analysis_engineer_core: the executable engine of the
Engineering Analysis and Data Engineer role.

Proves the role can DO its job standalone (no AeroSkills needed): ISA
reference values, GUM uncertainty propagation, t confidence intervals,
tolerance stack-up (worst case + RSS), Richardson/GCI convergence
verification, engineering margins, memo generation, evidence gates, and
the filled deliverable template.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "core"))
from engineering_analysis_engineer_core import (  # noqa: E402
    ISA_G, ISA_LAPSE, ISA_P0, ISA_R, ISA_T0, StackMember,
    check_memo, check_memo_markdown, combined_standard_uncertainty,
    confidence_interval_mean, convergence_verdict, density_altitude_m,
    density_from_measured, example_chain, example_memo_markdown,
    expanded_uncertainty, grid_convergence_index, isa_density_kgm3,
    isa_pressure_pa, isa_reference_values, isa_temperature_k,
    margin_of_safety, margin_verdict, nominal_total, observed_order,
    render_memo_markdown, richardson_extrapolation, rss_shares, rss_total,
    t_ppf_two_sided, uncertainty_contributions, worst_case_total,
    build_memo, trapezoid_hydrostatic_pressure,
)

ROLE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROLE_DIR, "templates", "analysis-memo-template.md")


class TestIsaAtmosphere(unittest.TestCase):

    def test_sea_level_values(self):
        self.assertAlmostEqual(isa_temperature_k(0), ISA_T0, places=9)
        self.assertAlmostEqual(isa_pressure_pa(0), ISA_P0, places=6)
        rho0 = ISA_P0 / (ISA_R * ISA_T0)
        self.assertAlmostEqual(isa_density_kgm3(0), rho0, places=9)
        self.assertAlmostEqual(rho0, 1.225, places=3)

    def test_tropopause(self):
        self.assertAlmostEqual(isa_temperature_k(11000), 216.65, places=9)
        self.assertAlmostEqual(isa_temperature_k(15000), 216.65, places=9)

    def test_known_troposphere_point(self):
        # 3000 m: T = 288.15 - 0.0065*3000 = 268.65 K
        self.assertAlmostEqual(isa_temperature_k(3000), 268.65, places=9)
        p3 = isa_pressure_pa(3000)
        t3 = isa_temperature_k(3000)
        self.assertAlmostEqual(isa_density_kgm3(3000),
                               p3 / (ISA_R * t3), places=12)
        self.assertGreater(isa_pressure_pa(1000), isa_pressure_pa(3000))

    def test_pressure_monotonic_and_reference_dict(self):
        vals = [isa_reference_values(h) for h in (0, 3000, 11000)]
        ps = [v["pressure_pa"] for v in vals]
        self.assertEqual(ps, sorted(ps, reverse=True))
        self.assertEqual(set(vals[0]), {"altitude_m", "temperature_k",
                                        "pressure_pa", "density_kgm3"})

    def test_out_of_range_raises(self):
        for h in (-1, 21000):
            with self.assertRaises(ValueError):
                isa_temperature_k(h)
            with self.assertRaises(ValueError):
                isa_pressure_pa(h)

    def test_density_from_measured(self):
        # Ideal gas EOS rho = p / (R T)
        self.assertAlmostEqual(density_from_measured(101325, 288.15),
                               101325 / (ISA_R * 288.15), places=12)


class TestUncertaintyPropagation(unittest.TestCase):

    def test_combined_standard(self):
        # u_c = sqrt((2*0.5)^2 + (3*1)^2) = sqrt(1 + 9) = sqrt(10)
        self.assertAlmostEqual(combined_standard_uncertainty([2, 3],
                                                             [0.5, 1.0]),
                               (10.0) ** 0.5, places=12)
        # single input: u_c = s*u
        self.assertAlmostEqual(combined_standard_uncertainty([4], [0.25]),
                               1.0, places=12)

    def test_expanded(self):
        self.assertAlmostEqual(expanded_uncertainty(2.0), 4.0, places=12)
        self.assertAlmostEqual(expanded_uncertainty(2.0, k=3), 6.0, places=12)
        with self.assertRaises(ValueError):
            expanded_uncertainty(1.0, k=0)

    def test_contributions_and_shares(self):
        contribs = uncertainty_contributions([2, 3], [0.5, 1.0])
        self.assertAlmostEqual(sum(c["percent"] for c in contribs), 100.0,
                               places=9)
        self.assertEqual(contribs[0]["index"], 1)  # dominant first
        # invalid inputs
        with self.assertRaises(ValueError):
            combined_standard_uncertainty([1], [1, 2])
        with self.assertRaises(ValueError):
            combined_standard_uncertainty([1], [-1])

    def test_example_density_chain_uncertainty(self):
        # Example: p = 70050 +/- 35 Pa, T = 271 +/- 1.2 K, rho = p/(R T)
        chain = example_chain()
        t = chain.temperature_k
        sens_p = 1.0 / (ISA_R * t)
        sens_t = -chain.pressure_pa / (ISA_R * t * t)
        uc = combined_standard_uncertainty([sens_p, sens_t],
                                           [chain.pressure_unc_pa,
                                            chain.temperature_unc_k])
        U = expanded_uncertainty(uc, chain.coverage_factor)
        rho = density_from_measured(chain.pressure_pa, t)
        # temperature dominates the budget (~99%)
        contribs = uncertainty_contributions([sens_p, sens_t],
                                             [chain.pressure_unc_pa,
                                              chain.temperature_unc_k])
        self.assertAlmostEqual(uc, 0.0040127, places=6)
        self.assertAlmostEqual(U, 2 * uc, places=12)
        self.assertGreater(contribs[0]["percent"], 90.0)
        self.assertAlmostEqual(rho, 0.900495, places=5)


class TestConfidenceInterval(unittest.TestCase):

    def test_t_quantile_known_values(self):
        self.assertAlmostEqual(t_ppf_two_sided(0.95, 9), 2.262157, places=4)
        self.assertAlmostEqual(t_ppf_two_sided(0.95, 4), 2.776445, places=4)
        self.assertAlmostEqual(t_ppf_two_sided(0.99, 10), 3.169273, places=4)
        with self.assertRaises(ValueError):
            t_ppf_two_sided(0.0, 5)
        with self.assertRaises(ValueError):
            t_ppf_two_sided(0.95, 0.5)

    def test_confidence_interval_mean(self):
        x = [1.8, -2.2, 3.1, -0.7, 2.4, -1.5, 0.9, 2.8, -1.1, 0.4]
        ci = confidence_interval_mean(x)
        mean = sum(x) / len(x)
        self.assertAlmostEqual(ci["mean"], mean, places=12)
        self.assertEqual(ci["n"], 10)
        self.assertEqual(ci["df"], 9.0)
        self.assertLess(ci["lower"], mean)
        self.assertGreater(ci["upper"], mean)
        # 95% of the interval width comes from t * s / sqrt(n)
        import math
        s = math.sqrt(sum((v - mean) ** 2 for v in x) / 9.0)
        self.assertAlmostEqual(ci["se"], s / math.sqrt(10), places=12)
        self.assertAlmostEqual(ci["t_quantile"], 2.262157, places=4)

    def test_degenerate_constant_sample(self):
        ci = confidence_interval_mean([5.0, 5.0, 5.0])
        self.assertEqual(ci["lower"], ci["upper"])

    def test_short_sample_raises(self):
        with self.assertRaises(ValueError):
            confidence_interval_mean([1.0])


class TestToleranceStackup(unittest.TestCase):

    def _stack(self):
        return [StackMember("bracket", 120.0, 0.50, +1),
                StackMember("adapter", 45.0, 0.25, +1),
                StackMember("probe inset", 60.0, 0.40, -1)]

    def test_nominal_total(self):
        self.assertAlmostEqual(nominal_total(self._stack()), 105.0, places=9)

    def test_worst_case_total(self):
        self.assertAlmostEqual(worst_case_total(self._stack()), 1.15,
                               places=9)

    def test_rss_total(self):
        # sqrt(0.5^2 + 0.25^2 + 0.4^2)
        self.assertAlmostEqual(rss_total(self._stack()),
                               (0.25 + 0.0625 + 0.16) ** 0.5, places=9)
        # RSS never exceeds worst case
        self.assertLessEqual(rss_total(self._stack()),
                             worst_case_total(self._stack()))

    def test_rss_shares(self):
        shares = rss_shares(self._stack())
        self.assertAlmostEqual(sum(shares), 100.0, places=9)
        self.assertGreater(shares[0], shares[1])  # bracket dominant
        self.assertAlmostEqual(shares[0], 52.910, places=2)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            nominal_total([])
        with self.assertRaises(ValueError):
            worst_case_total([])
        with self.assertRaises(ValueError):
            rss_total([])


class TestConvergenceVerification(unittest.TestCase):

    def test_observed_order_monotone(self):
        # r = 2, ratio (f3-f2)/(f2-f1) = 4 -> order exactly 2
        self.assertAlmostEqual(observed_order(1.000, 1.010, 1.050, 2.0),
                               2.0, places=9)

    def test_richardson_and_gci(self):
        f1, f2, r, p = 70107.96199725207, 70107.04297140652, 2.0, 2.0
        fex = richardson_extrapolation(f1, f2, r, p)
        gci = grid_convergence_index(f1, f2, r, p)
        # extrapolated value recovers the closed-form ISA pressure at 3000 m
        closed = isa_pressure_pa(3000)
        self.assertAlmostEqual(fex, closed, delta=1e-4)
        self.assertAlmostEqual(gci, 5.462e-6, places=8)

    def test_verdict_monotone(self):
        v = convergence_verdict(1.000, 1.010, 1.050, 2.0)
        self.assertEqual(v["verdict"], "monotone converged")
        self.assertAlmostEqual(v["order"], 2.0, places=9)
        self.assertIsNotNone(v["extrapolated"])
        self.assertIsNotNone(v["gci"])

    def test_verdict_oscillatory_and_diverging(self):
        # oscillatory: (f3-f2)/(f2-f1) in (-1, 0)
        v = convergence_verdict(1.0, 1.1, 1.05, 2.0)
        self.assertEqual(v["verdict"], "oscillatory")
        self.assertIsNone(v["order"])
        # diverging: |ratio| > 1 on the negative branch
        v = convergence_verdict(1.0, 1.1, 0.6, 2.0)
        self.assertEqual(v["verdict"], "diverging")

    def test_trapezoid_hydrostatic_agrees_with_closed_form(self):
        # fine-grid integration must approach the closed-form ISA pressure
        exact = isa_pressure_pa(3000)
        fine = trapezoid_hydrostatic_pressure(3000, 24)
        coarse = trapezoid_hydrostatic_pressure(3000, 6)
        self.assertLess(abs(fine - exact), abs(coarse - exact))
        self.assertLess(abs(fine - exact) / exact, 1e-4)


class TestDensityAltitudeRootFinding(unittest.TestCase):

    def test_inversion_round_trip(self):
        # rho_ISA at 3000 m must invert back to ~3000 m
        rho3 = isa_density_kgm3(3000)
        res = density_altitude_m(rho3, h0=2800)
        self.assertTrue(res["converged"])
        self.assertAlmostEqual(res["altitude_m"], 3000.0, delta=1e-3)

    def test_warm_day_density_altitude(self):
        # measured density below ISA at 3000 m -> density altitude above it
        chain = example_chain()
        rho_m = density_from_measured(chain.pressure_pa, chain.temperature_k)
        res = density_altitude_m(rho_m, h0=3000)
        self.assertGreater(res["altitude_m"], 3000.0)
        self.assertAlmostEqual(res["altitude_m"], 3092.55, delta=0.5)


class TestMargins(unittest.TestCase):

    def test_margin_of_safety(self):
        self.assertAlmostEqual(margin_of_safety(125000, 100000), 0.25,
                               places=12)
        self.assertAlmostEqual(margin_of_safety(90000, 100000), -0.1,
                               places=12)

    def test_margin_verdict(self):
        self.assertEqual(margin_verdict(0.25), "PASS")
        self.assertEqual(margin_verdict(-0.1), "FAIL")
        self.assertEqual(margin_verdict(0.0), "PASS")


class TestMemoBuilder(unittest.TestCase):

    def test_example_model_numbers(self):
        model = build_memo(example_chain())
        self.assertEqual(model["document_type"], "Analysis Verification Memo")
        self.assertEqual(model["status"], "draft-for-review")
        self.assertAlmostEqual(model["density_kgm3"], 0.900495, places=5)
        self.assertAlmostEqual(model["u_c"], 0.0040127, places=6)
        self.assertAlmostEqual(model["expanded_U"], 0.0080255, places=6)
        # ISA values at the test altitude
        self.assertAlmostEqual(model["isa"]["temperature_k"], 268.65,
                               places=9)
        self.assertAlmostEqual(model["isa"]["pressure_pa"],
                               isa_pressure_pa(3000), places=6)
        # stack numbers
        st = model["stack"]
        self.assertAlmostEqual(st["nominal_mm"], 105.0, places=6)
        self.assertAlmostEqual(st["worst_case_mm"], 1.15, places=6)
        self.assertAlmostEqual(st["rss_mm"], 0.687386, places=5)
        self.assertEqual(st["dominant"], "mounting bracket")
        # margins
        self.assertAlmostEqual(model["ms_density"], 0.68307, places=4)
        self.assertAlmostEqual(st["ms_rss"], 0.16383, places=4)
        self.assertAlmostEqual(st["ms_wc"], -0.30435, places=4)
        # convergence
        cv = model["convergence"]
        self.assertEqual(cv["verdict"], "monotone converged")
        self.assertAlmostEqual(cv["order"], 2.0, delta=0.01)
        self.assertLess(cv["gci"], 0.001)
        # bias CI contains the mean and zero
        ci = model["bias_ci"]
        self.assertAlmostEqual(ci["mean"], 0.59, places=9)
        self.assertLess(ci["lower"], 0.0)
        self.assertGreater(ci["upper"], 0.0)

    def test_custom_altitude(self):
        chain = example_chain()
        chain.altitude_m = 6000.0
        model = build_memo(chain)
        self.assertAlmostEqual(model["isa"]["temperature_k"],
                               isa_temperature_k(6000), places=9)
        self.assertAlmostEqual(model["altitude_m"], 6000.0, places=9)

    def test_model_gates_all_pass(self):
        model = build_memo(example_chain())
        gates = check_memo(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_all_pass(self):
        md = example_memo_markdown()
        gates = check_memo_markdown(md)
        self.assertTrue(gates["all_pass"], gates)

    def test_render_contains_required_sections(self):
        md = example_memo_markdown()
        for sec in ["## 1. Scope and inputs", "## 2. Unit/atmosphere basis",
                    "## 3. Method and verification", "## 4. Results",
                    "## 5. Tolerances", "## 6. Data sources",
                    "## 7. Margins and conclusions", "## 8. Open items"]:
            self.assertIn(sec, md)
        self.assertIn("not an approval", md.lower())

    def test_gate_failures_are_caught(self):
        model = build_memo(example_chain())
        model["status"] = "approved"          # dishonest sign-off
        self.assertFalse(check_memo(model)["sign_off_honest"])
        model2 = build_memo(example_chain())
        model2["isa"]["pressure_pa"] = 1.0    # ISA values not real
        self.assertFalse(check_memo(model2)["isa_values_real"])
        model3 = build_memo(example_chain())
        model3["u_c"] = 0.0                   # uncertainty not real
        self.assertFalse(check_memo(model3)["uncertainty_valid"])
        bad_md = "# nothing here"
        self.assertFalse(check_memo_markdown(bad_md)["all_pass"])

    def test_standalone_no_skills_repo(self):
        # Core must work with no AeroSkills present.
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = build_memo(example_chain())
        self.assertGreater(model["density_kgm3"], 0.1)
        md = render_memo_markdown(model)
        self.assertGreater(len(md), 3000)

    def test_template_is_the_filled_example(self):
        # ROLE-STANDARD: the template IS the example deliverable generated
        # by the core - byte-identical, zero blanks.
        self.assertTrue(os.path.exists(TEMPLATE))
        template = open(TEMPLATE).read()
        self.assertNotIn("___", template)
        self.assertEqual(template, example_memo_markdown())


if __name__ == "__main__":
    unittest.main()
