#!/usr/bin/env python3
"""Test aircraft_design_core: the executable engine of the aircraft
conceptual design engineer role.

Proves the role can DO its job standalone (no AeroSkills needed):
constraint-analysis T/W rules, mission fuel-fraction models, class-I
empty-weight fit, MTOW convergence within 0.5%, concept package
generation, and evidence-gate checks.
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))
from aircraft_design_core import (          # noqa: E402
    EMPTY_WEIGHT_FRACTION_BANDS, breguet_cruise_fuel_fraction,
    breguet_loiter_fuel_fraction, build_concept, chain_mission, check_concept,
    check_concept_markdown, check_empty_weight_fraction, climb_constraint_tw,
    constraint_tw, cruise_constraint_tw, empty_weight_fraction,
    example_item, example_concept_markdown, render_concept_markdown,
    segment_fuel_fraction, size_mtow, stall_max_ws, takeoff_constraint_tw,
    tow_estimate, weight_breakdown_ok,
)

G = 9.80665
RHO_SL = 1.225


class TestConstraintAnalysis(unittest.TestCase):
    """Matching-chart rules must match the AeroSkills leaf formulas."""

    def test_stall_max_ws(self):
        # W/S = 0.5*rho*CLmax*VS^2: 0.5*1.225*2.5*60^2
        self.assertAlmostEqual(stall_max_ws(60.0, 2.5), 0.5 * 1.225 * 2.5 * 3600.0)
        with self.assertRaises(ValueError):
            stall_max_ws(-1.0, 2.5)

    def test_takeoff_constraint(self):
        # T/W = 1.21*(W/S)/(rho*g*CLmax*s_TO) with clean SI inputs
        ws, rho, cl, s_to = 4000.0, 1.225, 2.0, 1500.0
        expected = 1.21 * ws / (rho * G * cl * s_to)
        self.assertAlmostEqual(takeoff_constraint_tw(ws, rho, cl, s_to), expected)
        # dispatcher agrees with the direct leaf call
        self.assertAlmostEqual(
            constraint_tw("takeoff", W_S=ws, rho=rho, CLmax=cl, s_TO=s_to),
            expected)
        with self.assertRaises(ValueError):
            takeoff_constraint_tw(-5.0, rho, cl, s_to)

    def test_climb_constraint(self):
        # T/W = 1/LD + gamma
        self.assertAlmostEqual(climb_constraint_tw(20.0, 0.03), 1.0 / 20.0 + 0.03)
        # OEI second-segment on the installed basis: x n/(n-1)
        raw = constraint_tw("climb", LD=12.0, gamma=0.024)
        inst = constraint_tw("climb", LD=12.0, gamma=0.024, engines=2)
        self.assertAlmostEqual(raw, 1.0 / 12.0 + 0.024)
        self.assertAlmostEqual(inst, 2.0 * raw)
        with self.assertRaises(ValueError):
            constraint_tw("climb", LD=12.0, gamma=0.024, engines=1)

    def test_cruise_constraint_shape(self):
        # q*CD0/W_S + k*W_S/q is U-shaped in W/S with its minimum at
        # W/S* = q*sqrt(CD0/k); takeoff grows with W/S, so high W/S values
        # are takeoff-bound while very low W/S values are cruise-bound.
        v, rho, cd0, k = 231.3, 0.3796, 0.018, 0.0419
        q = 0.5 * rho * v * v
        ws_opt = q * math.sqrt(cd0 / k)
        vals = [cruise_constraint_tw(w, v, rho, cd0, k)
                for w in (ws_opt * 0.7, ws_opt, ws_opt * 1.3)]
        self.assertLess(vals[1], vals[0])
        self.assertLess(vals[1], vals[2])
        with self.assertRaises(ValueError):
            cruise_constraint_tw(-1.0, v, rho, cd0, k)
        with self.assertRaises(ValueError):
            constraint_tw("bogus", W_S=4000.0)

    def test_design_point_on_feasible_boundary(self):
        item = example_item()
        model = build_concept(item)
        dp = model["design_point"]
        # chosen W/S below the stall limit and inside the feasible region
        self.assertLessEqual(dp["ws_nm2"], dp["ws_stall_max_nm2"])
        self.assertTrue(dp["feasible"])
        # required T/W equals the max over the constraint curves at that W/S
        max_curve = max(dp["curves"][name]["tw_at_design"]
                        for name in dp["curves"])
        self.assertAlmostEqual(dp["tw_required"], max_curve, places=6)
        self.assertIn(dp["binding_constraint"], dp["curves"])
        # the example has a real, defensible regional-jet design point
        self.assertGreater(dp["tw_required"], 0.10)
        self.assertLess(dp["tw_required"], 0.35)


class TestMissionFuelFractions(unittest.TestCase):
    """Segment fuel models must match the sizing-mission-profile leaf."""

    def test_breguet_cruise_fraction_matches_doc_case(self):
        # AeroSkills worked example: 3000 nm, V 450 kt, TSFC 0.6, L/D 18,
        # W0 150000 lb burns 69088.9 lb on the cruise leg -> fraction 0.46059
        frac = breguet_cruise_fuel_fraction(3000.0, 450.0, 0.6, 18.0)
        self.assertAlmostEqual(frac * 150000.0, 69088.9, delta=1.0)

    def test_loiter_endurance_fraction(self):
        # hold 0.75 hr at TSFC 0.5, L/D 15: 1 - exp(-0.75*0.5/15)
        frac = breguet_loiter_fuel_fraction(0.75, 0.5, 15.0)
        self.assertAlmostEqual(frac, 1.0 - math.exp(-0.75 * 0.5 / 15.0))

    def test_segment_fuel_fraction_dispatch(self):
        # absolute-flow segments scale with the start weight (W0-dependent)
        f1 = segment_fuel_fraction("taxi", {"fuel_flow": 1200.0, "time": 0.25},
                                   120000.0)
        self.assertAlmostEqual(f1, 300.0 / 120000.0)
        # climb fraction model returns the fraction directly
        self.assertAlmostEqual(
            segment_fuel_fraction("climb", {"fraction": 0.01}, 120000.0), 0.01)
        # cruise dispatches to Breguet range
        fc = segment_fuel_fraction("cruise", {"R_nm": 1500.0, "V_kt": 450.0,
                                              "TSFC": 0.6, "LD": 18.0},
                                   120000.0)
        self.assertAlmostEqual(fc, 1.0 - math.exp(-1500.0 / (450.0 * 0.6 * 18.0)))
        with self.assertRaises(ValueError):
            segment_fuel_fraction("weird", {}, 120000.0)

    def test_mission_chains_weights_and_balances_fractions(self):
        item = example_item()
        mission = chain_mission(item, 150000.0)
        # weight chains: block fuel < start weight, landing weight positive
        self.assertGreater(mission["block_fuel_lb"], 0.0)
        self.assertGreater(mission["landing_weight_lb"], 0.0)
        # required fuel = block + reserve; reserve = hold + 5% of trip
        self.assertAlmostEqual(mission["required_fuel_lb"],
                               mission["block_fuel_lb"] + mission["reserve_fuel_lb"])
        # per-segment fractions of MTOW sum to the block-fuel fraction
        total_frac = sum(s["fraction_of_mtow"] for s in mission["segments"])
        self.assertAlmostEqual(total_frac,
                               mission["block_fuel_lb"] / 150000.0)
        # segment types in the expected order
        types = [s["type"] for s in mission["segments"]]
        self.assertEqual(types, ["taxi", "takeoff", "climb", "cruise", "descent"])


class TestEmptyFractionAndTow(unittest.TestCase):
    """Class-I empty-weight fit and the tow-estimation leaf parity."""

    def test_empty_weight_fraction_band_and_fit(self):
        self.assertEqual(EMPTY_WEIGHT_FRACTION_BANDS["transport"], (0.42, 0.55))
        # representative fraction is the transport band midpoint
        self.assertAlmostEqual(empty_weight_fraction("transport"), 0.485)
        with self.assertRaises(ValueError):
            empty_weight_fraction("airship")

    def test_empty_fraction_in_band_check(self):
        in_band, band, frac = check_empty_weight_fraction(58300.0, 120000.0,
                                                          "transport")
        self.assertTrue(in_band)
        self.assertEqual(band, (0.42, 0.55))
        self.assertAlmostEqual(frac, 58300.0 / 120000.0)
        # out-of-band case fails
        in_band2, _, _ = check_empty_weight_fraction(80000.0, 120000.0, "transport")
        self.assertFalse(in_band2)

    def test_tow_estimate_leaf(self):
        # W0 = payload/(1 - empty - fuel)
        self.assertAlmostEqual(tow_estimate(20000.0, 0.485, 0.35),
                               20000.0 / (1.0 - 0.485 - 0.35))
        with self.assertRaises(ValueError):
            tow_estimate(20000.0, 0.6, 0.5)  # fractions reach 1.0

    def test_weight_breakdown_balances(self):
        self.assertTrue(weight_breakdown_ok(58000.0, 42000.0, 20000.0, 120000.0))
        self.assertFalse(weight_breakdown_ok(60000.0, 42000.0, 20000.0, 120000.0))


class TestMTOWConvergence(unittest.TestCase):
    """The sizing loop must genuinely iterate and converge within 0.5%."""

    def test_mtow_converges_within_tolerance(self):
        item = example_item()
        sizing = size_mtow(item)
        self.assertTrue(sizing["converged"])
        self.assertEqual(sizing["tolerance"], 0.005)
        self.assertGreaterEqual(len(sizing["iterations"]), 2)
        # final successive estimates within the 0.5% band
        last = sizing["iterations"][-1]
        self.assertLess(last["rel_change"], 0.005)
        # MTOW dominates payload and matches a 100-pax regional jet class
        self.assertGreater(sizing["mtow_lb"], 3.0 * sizing["payload_lb"])
        self.assertGreater(sizing["mtow_lb"], 90000.0)
        self.assertLess(sizing["mtow_lb"], 160000.0)

    def test_fuel_fraction_is_weight_dependent(self):
        # fixed-fuel segments make the fuel fraction fall as W0 grows
        f_small = chain_mission(example_item(), 80000.0)["fuel_fraction"]
        f_large = chain_mission(example_item(), 160000.0)["fuel_fraction"]
        self.assertLess(f_large, f_small)

    def test_breakdown_balances_at_convergence(self):
        sizing = size_mtow(example_item())
        self.assertTrue(weight_breakdown_ok(
            sizing["empty_weight_lb"], sizing["required_fuel_lb"],
            sizing["payload_lb"], sizing["mtow_lb"], tol=0.01))

    def test_converges_from_a_different_guess(self):
        item = example_item()
        item.initial_guess_lb = 250000.0
        sizing = size_mtow(item)
        self.assertTrue(sizing["converged"])
        # converges to the same fixed point regardless of the start guess
        base = size_mtow(example_item())["mtow_lb"]
        self.assertAlmostEqual(sizing["mtow_lb"], base, delta=base * 0.005)


class TestConceptPackageAndGates(unittest.TestCase):

    def test_build_concept_model_complete(self):
        model = build_concept(example_item())
        for key in ("document_type", "status", "item", "requirement",
                    "design_point", "mission", "sizing", "engine",
                    "mass_statement"):
            self.assertIn(key, model)
        ms = model["mass_statement"]
        self.assertEqual(model["status"], "draft-for-review")
        self.assertTrue(model["sizing"]["empty_in_band"])
        # mass statement carries the three rows and a total
        self.assertEqual(len(ms["rows"]), 3)
        self.assertAlmostEqual(ms["total_lb"], model["sizing"]["mtow_lb"])
        # engine check: 2 engines, positive thrust, top-of-climb margin >= 1
        self.assertEqual(model["engine"]["n_engines"], 2)
        self.assertGreater(model["engine"]["toc_margin"], 1.0)
        self.assertTrue(model["engine"]["toc_ok"])

    def test_core_gates_all_pass(self):
        model = build_concept(example_item())
        gates = check_concept(model)
        self.assertTrue(gates["all_pass"], gates)

    def test_markdown_gates_all_pass_and_no_blanks(self):
        md = example_concept_markdown()
        self.assertGreater(len(md), 3000)
        self.assertNotIn("___", md)
        gates = check_concept_markdown(md)
        self.assertTrue(gates["all_pass"], gates)

    def test_render_contains_key_numbers(self):
        md = example_concept_markdown()
        model = build_concept(example_item())
        s = model["sizing"]
        dp = model["design_point"]
        # converged MTOW, W/S-T/W point, and the mass statement are present
        self.assertIn(f"{s['mtow_lb']:,.0f}", md)
        self.assertIn(f"{dp['ws_nm2']:,.0f} N/m^2", md)
        self.assertIn(f"{dp['tw_required']:.4f}", md)
        self.assertIn("CONVERGED", md.upper())
        self.assertIn("not an approval", md.lower())

    def test_standalone_no_skills_repo(self):
        # Core must work with no AeroSkills present and no local paths.
        os.environ["AEROSKILLS_DEV"] = "/nonexistent"
        model = build_concept(example_item())
        md = render_concept_markdown(model)
        self.assertTrue(model["sizing"]["converged"])
        self.assertGreater(len(md), 3000)
        gates = check_concept(model)
        self.assertTrue(gates["all_pass"], gates)


if __name__ == "__main__":
    unittest.main()
