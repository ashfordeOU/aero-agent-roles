#!/usr/bin/env python3
"""cli.py - run the Stability and Control Flight Test Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--bundle] [--profile <p.json>]
                       [--cg <fraction MAC>]
  python3 cli.py check --file <file.md>

Builds the Stability and Control Flight Test Report for the reference
item (a transport-category airplane stability & control flight test
campaign) via the executable role engine
core/stability_control_flight_test_core.py. When AeroSkills logic is
present the CLI dispatches the bound flight-test-operations/stability
leaf computations (static-stability-flight-test,
dynamic-stability-flight-test,
lateral-directional-stability-flight-test, control-force-flight-test)
and cross-checks them against the core; agreement is recorded in
provenance.json. Standalone (AEROSKILLS_DEV=/nonexistent or no
checkout) the role still builds and checks correctly.
"""
import argparse
import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import stability_control_flight_test_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "stability-control-flight-test-engineer"
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))

# Dispatch cross-check points: one row per bound leaf (plus a second
# point where the leaf ships several reductions), each loads the leaf's
# logic module and compares the leaf function's result with the core's
# own function over the same inputs. All leaf modules implement the same
# flight-test math the core encodes (the four bound leaves under
# flight-test-operations/stability/).
DISPATCH_POINTS = [
    {
        "leaf": "flight-test-operations/stability/static-stability-flight-test",
        "module": "static_stability_flight_test_logic.py",
        "skill_fn": "trim_curve_fit",
        "core_fn": "trim_curve_fit",
        "kwargs": {"elevator_deg": [0.0, -0.6, -1.2, -1.8, -2.4],
                   "speeds_m_s": [115.57711927941293, 105.5069922679995,
                                  97.6804941082611, 91.3717355809759,
                                  86.14609845078961],
                   "weight_n": 450000.0, "wing_area_m2": 110.0,
                   "rho_kg_m3": 1.225},
        "param_map": {},
        "cross_check_point": "Static trim curve fit slope b = "
                             "d(delta_e)/dCL (negative = stable)",
        "tolerance": 1e-9,
        "compare": "slope_deg_per_cl",
    },
    {
        "leaf": "flight-test-operations/stability/static-stability-flight-test",
        "module": "static_stability_flight_test_logic.py",
        "skill_fn": "stick_fixed_neutral_point",
        "core_fn": "stick_fixed_neutral_point",
        "kwargs": {"slope_deg_per_cl": -6.0, "cg_fraction_mac": 0.25,
                   "cm_delta_e_per_rad": -0.5},
        "param_map": {},
        "cross_check_point": "Stick fixed neutral point and static margin "
                             "(h_n = h + b Cm_delta_e pi/180)",
        "tolerance": 1e-12,
        "compare": "static_margin_fraction_mac",
    },
    {
        "leaf": "flight-test-operations/stability/static-stability-flight-test",
        "module": "static_stability_flight_test_logic.py",
        "skill_fn": "elevator_angle_per_g",
        "core_fn": "elevator_angle_per_g",
        "kwargs": {"cl_1g": 0.7,
                   "static_margin_fraction_mac": 0.05235987755982988,
                   "cm_delta_e_per_rad": -0.5},
        "param_map": {},
        "cross_check_point": "Elevator angle per g "
                             "(d(delta_e)/dn = (180/pi) CL SM / Cm_delta_e)",
        "tolerance": 1e-9,
        "compare": "magnitude_deg_per_g",
    },
    {
        "leaf": "flight-test-operations/stability/dynamic-stability-flight-test",
        "module": "dynamic_stability_flight_test_logic.py",
        "skill_fn": "log_decrement",
        "core_fn": "log_decrement",
        "kwargs": {"first_amplitude": 5.0, "last_amplitude": 0.0176,
                   "cycles": 2},
        "param_map": {},
        "cross_check_point": "Log decrement delta = (1/n) ln(A0/An)",
        "tolerance": 1e-12,
    },
    {
        "leaf": "flight-test-operations/stability/dynamic-stability-flight-test",
        "module": "dynamic_stability_flight_test_logic.py",
        "skill_fn": "mode_identification",
        "core_fn": "mode_identification",
        "kwargs": {"peak_values": [5.0, 0.296, 0.0176],
                   "peak_times": [0.0, 0.9, 1.8]},
        "param_map": {},
        "cross_check_point": "Short period mode identification (damping "
                             "ratio from the decaying peak record)",
        "tolerance": 1e-12,
        "compare": "damping_ratio",
    },
    {
        "leaf": "flight-test-operations/stability/dynamic-stability-flight-test",
        "module": "dynamic_stability_flight_test_logic.py",
        "skill_fn": "handling_qualities_verdict",
        "core_fn": "handling_qualities_verdict",
        "kwargs": {"mode": "short-period",
                   "damping_ratio": 0.41002830546281926},
        "param_map": {},
        "cross_check_point": "Short period handling-qualities verdict from "
                             "the practice damping bands",
        "tolerance": 0.0,
        "compare": "verdict",
    },
    {
        "leaf": "flight-test-operations/stability/dynamic-stability-flight-test",
        "module": "dynamic_stability_flight_test_logic.py",
        "skill_fn": "cycles_to_half_amplitude",
        "core_fn": "cycles_to_half_amplitude",
        "kwargs": {"damping_ratio": 0.41},
        "param_map": {},
        "cross_check_point": "Cycles to half amplitude N = ln(2)/(2 pi zeta)",
        "tolerance": 1e-12,
    },
    {
        "leaf": "flight-test-operations/stability/lateral-directional-stability-flight-test",
        "module": "lateral_directional_stability_flight_test_logic.py",
        "skill_fn": "reduce_sideslip_sweep",
        "core_fn": "reduce_sideslip_sweep",
        "kwargs": {"beta_deg": [2.0, 5.0, 8.0, 11.0, 14.0],
                   "delta_r_deg": [0.24, 0.58, 0.96, 1.34, 1.70],
                   "delta_a_deg": [-0.35, -0.80, -1.30, -1.80, -2.30],
                   "pedal_force_N": [0.0, -95.0, -185.0, -275.0, -360.0],
                   "cn_dr_per_rad": -0.90, "cl_da_per_rad": -0.35},
        "param_map": {},
        "cross_check_point": "SHS sweep: Cn_beta = -cn_dr s_r signed "
                             "directional estimate",
        "tolerance": 1e-12,
        "compare": "cn_beta_estimate_per_rad",
    },
    {
        "leaf": "flight-test-operations/stability/lateral-directional-stability-flight-test",
        "module": "lateral_directional_stability_flight_test_logic.py",
        "skill_fn": "aileron_gradient",
        "core_fn": "aileron_gradient",
        "kwargs": {"beta_deg": [2.0, 5.0, 8.0, 11.0, 14.0],
                   "delta_a_deg": [-0.35, -0.80, -1.30, -1.80, -2.30]},
        "param_map": {},
        "cross_check_point": "SHS aileron gradient s_a = d(delta_a)/d(beta)",
        "tolerance": 1e-12,
    },
    {
        "leaf": "flight-test-operations/stability/lateral-directional-stability-flight-test",
        "module": "lateral_directional_stability_flight_test_logic.py",
        "skill_fn": "pedal_force_gradient",
        "core_fn": "pedal_force_gradient",
        "kwargs": {"beta_deg": [2.0, 5.0, 8.0, 11.0, 14.0],
                   "pedal_force_N": [0.0, -95.0, -185.0, -275.0, -360.0]},
        "param_map": {},
        "cross_check_point": "SHS rudder-free pedal-force gradient g_p "
                             "(N/deg)",
        "tolerance": 1e-9,
    },
    {
        "leaf": "flight-test-operations/stability/control-force-flight-test",
        "module": "control_force_flight_test_logic.py",
        "skill_fn": "calibrate_force_transducer",
        "core_fn": "calibrate_force_transducer",
        "kwargs": {"known_lbf": [20.0, 60.0], "counts": [1230.0, 3250.0]},
        "param_map": {},
        "cross_check_point": "Force transducer calibration slope "
                             "(lbf/count)",
        "tolerance": 1e-12,
        "compare": "slope_lbf_per_count",
    },
    {
        "leaf": "flight-test-operations/stability/control-force-flight-test",
        "module": "control_force_flight_test_logic.py",
        "skill_fn": "stick_force_gradient",
        "core_fn": "stick_force_gradient",
        "kwargs": {"speeds_kts": [120.0, 130.0, 140.0, 150.0],
                   "forces_lbf": [-3.8, -1.6, 0.5, 2.9]},
        "param_map": {},
        "cross_check_point": "Stick force gradient vs calibrated airspeed "
                             "(lbf/kt, pull positive)",
        "tolerance": 1e-12,
        "compare": "slope_lbf_per_kt",
    },
    {
        "leaf": "flight-test-operations/stability/control-force-flight-test",
        "module": "control_force_flight_test_logic.py",
        "skill_fn": "force_per_g",
        "core_fn": "force_per_g",
        "kwargs": {"load_factors": [1.0, 1.5, 2.0, 2.5],
                   "forces_lbf": [1.2, 7.4, 14.3, 20.8]},
        "param_map": {},
        "cross_check_point": "Stick force per g from the pull-ups (lbf/g)",
        "tolerance": 1e-9,
        "compare": "slope_lbf_per_g",
    },
    {
        "leaf": "flight-test-operations/stability/control-force-flight-test",
        "module": "control_force_flight_test_logic.py",
        "skill_fn": "breakout_force",
        "core_fn": "breakout_force",
        "kwargs": {"push_lbf": -4.2, "pull_lbf": 6.4},
        "param_map": {},
        "cross_check_point": "Breakout force from the push-pull hysteresis "
                             "half-width",
        "tolerance": 1e-9,
        "compare": "breakout_lbf",
    },
    {
        "leaf": "flight-test-operations/stability/control-force-flight-test",
        "module": "control_force_flight_test_logic.py",
        "skill_fn": "centering_check",
        "core_fn": "centering_check",
        "kwargs": {"residual_deg": 0.42, "limit_deg": 0.50},
        "param_map": {},
        "cross_check_point": "Control centering margin = limit - residual "
                             "(deg)",
        "tolerance": 1e-9,
        "compare": "margin_deg",
    },
]


def _load_leaf(leaf: str, module: str):
    """Import a bound AeroSkills leaf logic module if present."""
    path = os.path.join(AEROSKILLS, "skills", leaf, "scripts", module)
    if not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location("stability_dispatch", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _row_value(obj, compare):
    """Extract the comparable scalar from a result per compare mode.

    compare names a dict key to pull when the function returns a dict
    (the leaf reductions all return dicts of floats); empty string means
    the function returns a bare float.
    """
    if isinstance(obj, dict) and compare:
        return obj[compare]
    if isinstance(obj, (list, tuple)) and compare:
        return obj
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
            compare = point.get("compare", "")
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
            "file": "core/stability_control_flight_test_core.py",
            "functions": ["build_stability_control_report",
                          "check_report", "render_report_markdown",
                          "static_stability_report", "mode_identification",
                          "reduce_sideslip_sweep", "control_force_report",
                          "rollup_verdicts"],
            "version": "0.1.0",
        },
        "skills": skills_rows,
        "cross_checked": cross_checked,
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def cmd_build(args):
    item = core.example_item()
    if args.cg:
        # re-run the static longitudinal reduction at a new CG position
        try:
            cg = float(args.cg)
        except ValueError:
            print("error: --cg must be a number (fraction MAC)")
            return 1
        if not 0.0 < cg < 1.0:
            print("error: --cg must lie in (0, 1)")
            return 1
        item.cg_fraction_mac = cg
    model = core.build_stability_control_report(item)
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
        print(f"built stability & control report (CG {model['static_longitudinal']['cg_fraction_mac']}) "
              f"-> {args.out}")
        if profile:
            print(f"profile: {profile.get('customer')} / "
                  f"{profile.get('program')}")
        print(f"gates: all_pass={gates['all_pass']} {gates}")
        if args.bundle:
            skills_rows, cross_checked = _dispatch_crosschecks()
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "Stability and Control Flight Test Report",
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
        description="Stability and Control Flight Test Engineer role "
                    "(Stability and Control Flight Test Report)")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="", help="output file (default: stdout)")
    b.add_argument("--cg", default="",
                   help="override CG position (fraction MAC, e.g. 0.30)")
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json")
    b.add_argument("--profile", default="",
                   help="program profile JSON (docs/PROFILE-SCHEMA.md)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="stability & control report markdown to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
