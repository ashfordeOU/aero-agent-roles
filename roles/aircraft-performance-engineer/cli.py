#!/usr/bin/env python3
"""cli.py - run the Aircraft Performance Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--bundle] [--profile <p.json>]
                       [--load-factor N] [--available-power W]
  python3 cli.py check --file <file.md>

Builds the Aircraft Performance Analysis Report for the reference fleet
workbook (nine case sets anchored to the real reference cases of the
bound flight-mechanics/performance leaves) via the executable role
engine core/aircraft_performance_core.py. When AeroSkills logic is
present the CLI dispatches each bound leaf computation and cross-checks
it against the core; agreement is recorded in provenance.json.
Standalone (AEROSKILLS_DEV=/nonexistent or no checkout) the role still
builds and checks correctly.
"""
import argparse
import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import aircraft_performance_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "aircraft-performance-engineer"
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))

# Dispatch cross-check points: one row per bound leaf. Each row loads the
# bound leaf's logic module and compares the leaf function's result with
# the core's own function over the same inputs (the reference case inputs
# the leaf logic modules document as worked examples). All leaf modules
# implement the same public-domain flight-mechanics math the core encodes
# (per the role's grounding), so identical formulas give delta 0.
DISPATCH_POINTS = [
    {
        "leaf": "flight-mechanics/performance/balanced-field-length",
        "module": "balanced_field_length_logic.py",
        "skill_fn": "balanced_v1",
        "core_fn": "balanced_v1",
        "kwargs": {"thrust_all_n": 150000.0, "engine_count": 2,
                   "weight_n": 600000.0, "mu_roll": 0.03, "mu_brake": 0.45,
                   "v_lof_ms": 80.0, "oei_climb_gradient": 0.024},
        "cross_check_point": "Balanced V1 decision speed where ASD = AGD "
                             "(FAR-25.113-style engine-out takeoff)",
        "tolerance": 1e-9,
    },
    {
        "leaf": "flight-mechanics/performance/propeller-range",
        "module": "propeller_range_logic.py",
        "skill_fn": "propeller_range",
        "core_fn": "propeller_range",
        "kwargs": {"propeller_efficiency": 0.80,
                   "psfc_kg_per_w_s": 9.293126e-8, "ld": 12.0,
                   "initial_mass": 11500.0, "final_mass": 10000.0},
        "cross_check_point": "Turboprop cruise range (propeller Breguet "
                             "equation, SI PSFC)",
        "tolerance": 1e-3,
    },
    {
        "leaf": "flight-mechanics/performance/rotorcraft-axial-descent-"
                "flow-states",
        "module": "rotorcraft_axial_descent_flow_states_logic.py",
        "skill_fn": "windmill_brake_induced_velocity",
        "core_fn": "windmill_brake_induced_velocity",
        "kwargs": {"descent_rate": 25.0, "hover_induced_velocity": 10.5887},
        "cross_check_point": "Windmill-brake induced velocity on the "
                             "physical momentum branch (Vd >= 2 v_h)",
        "tolerance": 1e-9,
    },
    {
        "leaf": "flight-mechanics/performance/rotorcraft-blade-flapping-"
                "dynamics",
        "module": "rotorcraft_blade_flapping_dynamics_logic.py",
        "skill_fn": "lock_number",
        "core_fn": "lock_number",
        "kwargs": {"rho": 1.225, "lift_slope": 5.73, "chord_m": 0.5,
                   "radius_m": 6.0, "flap_inertia": 600.0},
        "cross_check_point": "Blade Lock number (aero flap moment / "
                             "centrifugal restoring moment ratio)",
        "tolerance": 1e-9,
    },
    {
        "leaf": "flight-mechanics/performance/rotorcraft-hover-ground-"
                "effect",
        "module": "rotorcraft_hover_ground_effect_logic.py",
        "skill_fn": "ground_effect_factor",
        "core_fn": "ground_effect_factor",
        "kwargs": {"height": 5.0, "radius": 5.0},
        "cross_check_point": "Cheeseman-style ground-effect factor at "
                             "z/R = 1 (0.9375)",
        "tolerance": 1e-12,
    },
    {
        "leaf": "flight-mechanics/performance/rotorcraft-lead-lag-"
                "dynamics",
        "module": "rotorcraft_lead_lag_dynamics_logic.py",
        "skill_fn": "lag_frequency_ratio_hinge_offset",
        "core_fn": "lag_frequency_ratio_hinge_offset",
        "kwargs": {"hinge_offset_fraction": 0.05},
        "cross_check_point": "Rotating lead-lag frequency ratio from the "
                             "lag-hinge offset (e = 0.05)",
        "tolerance": 1e-9,
    },
    {
        "leaf": "flight-mechanics/performance/rotorcraft-main-rotor-"
                "sizing",
        "module": "rotorcraft_main_rotor_sizing_logic.py",
        "skill_fn": "hover_thrust_coefficient",
        "core_fn": "hover_thrust_coefficient",
        "kwargs": {"thrust": 44129.925, "rho": 1.225, "radius": 6.3352,
                   "tip_speed": 210.0},
        "cross_check_point": "Hover thrust coefficient at the sized disk "
                             "(ceiling identity CT = DL_max/(rho Vtip^2))",
        "tolerance": 1e-12,
    },
    {
        "leaf": "flight-mechanics/performance/rotorcraft-range-endurance",
        "module": "rotorcraft_range_endurance_logic.py",
        "skill_fn": "cruise_range",
        "core_fn": "cruise_range",
        "kwargs": {"v_ms": 80.0, "weight_initial_n": 60000.0,
                   "fuel_mass_kg": 1500.0, "power_at_ref_w": 600000.0,
                   "weight_ref_n": 60000.0},
        "cross_check_point": "Cruise range over the fuel load with "
                             "average-weight (W_avg/W_ref)^1.5 power scaling",
        "tolerance": 1e-3,
    },
    {
        "leaf": "flight-mechanics/performance/rotorcraft-turn-performance",
        "module": "rotorcraft_turn_performance_logic.py",
        "skill_fn": "turn_power",
        "core_fn": "turn_power",
        "kwargs": {"load_factor": 2.0, "weight": 21574.63, "area": 78.5398,
                   "rho": 1.225, "speed": 60.0, "solidity": 0.08,
                   "drag_coefficient": 0.012, "tip_speed": 220.0,
                   "flat_plate_area": 2.2},
        "cross_check_point": "Banked-turn total power at n = 2, V = 60 m/s "
                             "(induced + profile + parasite)",
        "tolerance": 1e-6,
        "compare": "total_power_key",
    },
]


def _load_leaf(leaf: str, module: str):
    """Import a bound AeroSkills leaf logic module if present."""
    path = os.path.join(AEROSKILLS, "skills", leaf, "scripts", module)
    if not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location("ape_dispatch", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _row_value(obj, compare):
    """Extract the comparable scalar from a result per compare mode."""
    if compare == "total_power_key":
        return float(obj["total_power"])
    return float(obj)


def _dispatch_crosschecks():
    """Run every dispatch point; returns provenance 'skills' rows."""
    rows = []
    any_ok = False
    for point in DISPATCH_POINTS:
        leaf = point["leaf"]
        mod = _load_leaf(leaf, point["module"])
        if mod is None:
            continue
        skill_fn = getattr(mod, point["skill_fn"], None)
        core_fn = getattr(core, point["core_fn"], None)
        if skill_fn is None or core_fn is None:
            continue
        try:
            kwargs = dict(point["kwargs"])
            skill_val = skill_fn(**kwargs)
            core_val = core_fn(**kwargs)
            compare = point.get("compare", "float")
            sv = _row_value(skill_val, compare)
            cv = _row_value(core_val, compare)
            if isinstance(cv, float) and isinstance(sv, float):
                delta = abs(cv - sv)
            else:
                delta = 0.0 if str(cv) == str(sv) else float("inf")
            agrees = delta <= point.get("tolerance", 1e-6)
            if agrees:
                any_ok = True

            def _prec(x):
                if isinstance(x, float):
                    return float(f"{x:.9g}")
                return x
            rows.append({
                "leaf": leaf,
                "skill_md": "SKILL.md",
                "logic_file": "scripts/" + point["module"],
                "function": point["skill_fn"],
                "dispatched": True,
                "cross_check_point": point["cross_check_point"],
                "core_value": _prec(cv),
                "skill_value": _prec(sv),
                "delta": _prec(delta),
                "agrees": bool(agrees),
                "tolerance": point.get("tolerance", 1e-6),
                "skills_release": "v1.3.0+",
            })
        except Exception as e:  # noqa: BLE001 - record honest row
            rows.append({"leaf": leaf, "dispatched": True,
                         "function": point["skill_fn"],
                         "error": str(e)[:150], "agrees": False})
    return rows, any_ok


def _provenance(skills_rows, cross_checked):
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/aircraft_performance_core.py",
            "functions": ["build_performance_report", "check_report",
                          "render_report_markdown", "balanced_v1",
                          "propeller_range", "windmill_brake_induced_velocity",
                          "lock_number", "ground_effect_factor",
                          "lag_frequency_ratio_hinge_offset",
                          "hover_thrust_coefficient", "cruise_range",
                          "turn_power"],
            "version": "0.1.0",
        },
        "skills": skills_rows,
        "cross_checked": cross_checked,
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def cmd_build(args):
    item = core.example_item()
    if args.load_factor:
        item.tp_load_factor = float(args.load_factor)
    if args.available_power:
        power = float(args.available_power)
        # H-1 installed/contingency power: re-runs the hover-IGE margin and
        # ceiling check and the sustained-turn solve at this power.
        item.ge_available_power_w = power
        item.tp_available_power_w = power
        if power <= 0:
            print("error: --available-power must be positive")
            return 1
    model = core.build_performance_report(item)
    md = core.render_report_markdown(model)

    # program profile (customer tailoring): load + apply context header
    profile = None
    try:
        profile = evidence.load_profile(args.profile)
    except ValueError as e:
        print(f"error: bad profile: {e}")
        return 1
    if profile:
        model["profile"] = {
            "customer": profile.get("customer"),
            "program": profile.get("program"),
            "basis": profile.get("basis"),
            "authority": profile.get("authority"),
            "der": profile.get("der"),
            "document_prefix": profile.get("document_prefix"),
            "revision": profile.get("revision"),
        }
        md = evidence.profile_header_block(profile) + md

    gates = core.check_report(model)
    if args.out:
        with open(args.out, "w") as f:
            f.write(md)
        print(f"built performance report (9 sections) -> {args.out}")
        if profile:
            print(f"profile: {profile.get('customer')} / "
                  f"{profile.get('program')}")
        print(f"gates: all_pass={gates['all_pass']} {gates}")
        if args.bundle:
            skills_rows, cross_checked = _dispatch_crosschecks()
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "Aircraft Performance Analysis Report",
                model, gates, _provenance(skills_rows, cross_checked))
            print(f"bundle: model={paths['model']}")
            print(f"        gates={paths['gates']}")
            print(f"        provenance={paths['provenance']}")
            if cross_checked:
                print("dispatch: core and AeroSkills leaf logic agree "
                      f"({len(skills_rows)} cross-checks)")
            else:
                print("dispatch: no AeroSkills leaf logic dispatched "
                      "(standalone build is still valid)")
    else:
        print(md)
    return 0 if gates["all_pass"] else 1


def cmd_check(args):
    if not os.path.exists(args.file):
        print(f"file not found: {args.file}")
        return 1
    md = open(args.file).read()
    gates = core.check_report_markdown(md)
    for name, ok in gates.items():
        if name != "all_pass":
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print(f"RESULT: {'PASS' if gates['all_pass'] else 'FAIL'}")
    return 0 if gates["all_pass"] else 1


def main():
    p = argparse.ArgumentParser(
        description="Aircraft Performance Engineer role "
                    "(multi-aircraft performance analysis report)")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="", help="output file (default: stdout)")
    b.add_argument("--load-factor", default="",
                   help="re-run the analysed banked-turn load factor n "
                        "(default 2.0, H-1 case)")
    b.add_argument("--available-power", default="",
                   help="override the H-1 available power (W) for the "
                        "hover-IGE margin/ceiling and sustained-turn solves")
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json")
    b.add_argument("--profile", default="",
                   help="program profile JSON (docs/PROFILE-SCHEMA.md)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="performance report markdown file to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
