#!/usr/bin/env python3
"""cli.py - run the Flight Test Performance Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--bundle] [--profile <file.json>]
    # build the Flight Test Performance Data Analysis Report for the
    # worked-example sortie data set
    # --bundle   also emit evidence/{model,gates,provenance}.json (PROTOCOL.md)
    # --profile  program profile JSON for customer tailoring
    #            (docs/PROFILE-SCHEMA.md) -> prepended context header
  python3 cli.py check --file <file.md>    # gate-check an existing report

The role ENGINE (core/flight_test_performance_core.py) does the work
standalone (real domain rules -> real numbers); bound Aero Agent Skills
performance leaves cross-check the core's reductions when the checkout is
present (provenance records core_value/skill_value/delta/agrees per point).
"""
import argparse
import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import flight_test_performance_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "flight-test-performance-engineer"
SKILLS_RELEASE = "v1.3.0+"


def _leaf_module(rel_leaf):
    """Import the bound AeroSkills leaf's *_logic.py module, or None."""
    root = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
    logic_dir = os.path.join(root, "skills", rel_leaf, "scripts")
    if not os.path.isdir(logic_dir):
        return None
    logic_files = sorted(f for f in os.listdir(logic_dir)
                         if f.endswith("_logic.py"))
    for lf in logic_files:
        try:
            spec = importlib.util.spec_from_file_location(
                "role_dispatch_leaf", os.path.join(logic_dir, lf))
            mod = importlib.util.module_from_spec(spec)
            if spec is None or spec.loader is None or mod is None:
                continue
            spec.loader.exec_module(mod)
            return mod
        except Exception:
            continue
    return None


def _dispatch_row(rel_leaf, fn_name, kwargs, core_value, tolerance=1e-6,
                  label=None, result_key=None):
    """Run the leaf logic fn with the same inputs as the core, compare.

    Returns a provenance 'skills' row (or None when dispatch unavailable).
    core_value may be a number or a zero-arg callable resolving lazily.
    """
    mod = _leaf_module(rel_leaf)
    if mod is None or not hasattr(mod, fn_name):
        return None
    if callable(core_value) and not isinstance(core_value, (int, float)):
        core_value = core_value()
    try:
        skill_value = getattr(mod, fn_name)(**kwargs)
        if result_key is not None and isinstance(skill_value, dict):
            skill_value = skill_value.get(result_key)
        if not isinstance(skill_value, (int, float)) or \
           not isinstance(core_value, (int, float)):
            return None
        delta = abs(float(core_value) - float(skill_value))
        row = {
            "leaf": rel_leaf,
            "skill_md": "SKILL.md",
            "logic_file": "scripts/%s" % os.path.basename(
                str(mod.__file__)),
            "function": fn_name,
            "dispatched": True,
            "core_value": round(float(core_value), 6),
            "skill_value": round(float(skill_value), 6),
            "delta": round(delta, 9),
            "agrees": delta <= tolerance,
            "tolerance": tolerance,
            "skills_release": SKILLS_RELEASE,
        }
        if label:
            row["cross_check_point"] = label
        return row
    except Exception:
        return None


def _dispatch_crosschecks(model):
    """Cross-check the core reductions against the bound skill leaves.

    Every point runs the SAME inputs through the role core and the bound
    AeroSkills leaf logic (independent implementations of the same public
    method) and records agreement in the provenance 'skills' list.
    """
    r = model["results"]
    ac = model["aircraft"]
    to_run = r["takeoff"]["run"]
    la = r["level_accel"]
    ld = r["landing"]
    rows = []

    def add(leaf, fn, kwargs, core_value, label, tol=1e-6,
            result_key=None):
        row = _dispatch_row(leaf, fn, kwargs, core_value, tolerance=tol,
                            label=label, result_key=result_key)
        if row:
            rows.append(row)

    # 1. takeoff ground roll (trapezoid integration of the recorded run)
    add("flight-test-operations/performance/takeoff-distance-determination",
        "ground_roll_distance",
        {"v_m_s_list": to_run["speeds_mps"], "t_s_list": to_run["times_s"]},
        lambda: core.ground_roll_integrate(to_run["speeds_mps"],
                                           to_run["times_s"]),
        "takeoff ground roll (trapezoid), run TO-1")

    # 2. rotation leg v_rot * t_rot (takeoff-distance leaf)
    add("flight-test-operations/performance/takeoff-distance-determination",
        "rotation_distance",
        {"v_rot_m_s": to_run["v_rot_mps"],
         "t_rot_s": to_run["rotation_time_s"]},
        lambda: to_run["rotation_m"],
        "rotation leg v_rot*t_rot")

    # 3. airborne climb to the 35-ft obstacle height (takeoff-distance leaf)
    add("flight-test-operations/performance/takeoff-distance-determination",
        "climb_distance",
        {"v_liftoff_m_s": to_run["liftoff_mps"], "h_target_m": 10.668,
         "climb_rate_m_s": to_run["climb_rate_mps"]},
        lambda: to_run["climb_35ft_m"],
        "airborne climb to 35 ft")

    # 4. rejected takeoff accelerate-stop distance (accelerate-stop leaf)
    asd = r["takeoff"]["accelerate_stop"]
    add("flight-test-operations/performance/accelerate-stop-distance",
        "accelerate_stop_distance",
        {"v1_m_s": r["takeoff"]["v1_mps"], "a_acc_m_s2": 2.3,
         "a_brake_m_s2": 0.42 * core.G0},
        lambda: asd["total_m"],
        "rejected takeoff accelerate-stop distance", result_key="total_m")

    # 5. certified landing field length 1.67 x demonstrated
    add("flight-test-operations/performance/landing-distance-determination",
        "certified_field_length",
        {"demonstrated_m": ld["demonstrated_m"],
         "factor": ld["field_length_factor"]},
        lambda: ld["certified_field_length_m"],
        "certified landing field length (1.67 factor)",
        result_key="certified_m")

    # 6. specific excess power P_s = V*a/g (level-acceleration leaf)
    add("flight-test-operations/performance/level-acceleration-test",
        "specific_excess_power", {"v": 160.0, "a": la["mean_acceleration"]},
        lambda: la["mean_specific_excess_power"],
        "P_s = V*a/g at the assessment mean acceleration", tol=1e-3)

    # 7. parabolic polar drag at the mid-trace airspeed
    rho_la = la["density_kgm3"]
    add("flight-test-operations/performance/level-acceleration-test",
        "drag_from_polar",
        {"v": 160.0, "rho": rho_la, "s": ac["s_m2"],
         "w": la["weight_n"], "cd0": ac["cd0"], "k": ac["k"]},
        lambda: core.drag_from_polar(160.0, rho_la, ac["s_m2"],
                                     la["weight_n"], ac["cd0"], ac["k"]),
        "parabolic polar drag at the mid-trace airspeed")

    # 8. cruise fuel-flow weight correction sqrt(w_ref/w_test)
    pt0 = r["cruise"]["points"][0]
    add("flight-test-operations/performance/cruise-performance-flight-test",
        "corrected_fuel_flow",
        {"wf_measured": pt0["wf_measured_kg_s"],
         "w_test": pt0["w_test_kg"], "w_ref": r["cruise"]["w_ref_kg"]},
        lambda: pt0["wf_corr"],
        "sqrt(w_ref/w_test) fuel-flow correction, M=%.2f" % pt0["mach"])

    # 9. stall speed weight correction (stall-speed leaf)
    stall = r["speeds"]["stall_rows"][0]
    add("flight-test-operations/performance/stall-speed-determination",
        "weight_corrected_stall_speed",
        {"vs_ref": ac["vs1g_ref_eas_ms"], "w_ref": ac["w_ref_n"],
         "w_new": stall["weight_n"]},
        lambda: stall["vs_predicted_eas_ms"],
        "Vs1g weight-corrected to the stall-run gross weight")

    # 10. Mach-to-TAS reduction at the cruise altitude (cruise leaf)
    add("flight-test-operations/performance/cruise-performance-flight-test",
        "tas_from_mach",
        {"mach": pt0["mach"], "altitude_m": pt0["altitude_m"]},
        lambda: core.tas_from_mach(pt0["mach"], pt0["altitude_m"]),
        "Mach-to-TAS reduction at FL350", tol=1e-2)
    return rows


def _provenance(model, dispatch_rows):
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/flight_test_performance_core.py",
            "functions": ["analyze_sortie", "build_report",
                          "reduce_takeoff_run", "reduce_landing_run",
                          "reduce_level_accel_run", "reduce_cruise_points",
                          "check_report", "render_report_markdown"],
            "version": "0.1.0",
        },
        "skills": dispatch_rows,
        "cross_checked": bool(dispatch_rows),
        "skills_release": SKILLS_RELEASE,
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def cmd_build(args):
    item = core.example_item()
    model = core.build_report(item)
    md = core.render_report_markdown(model)

    # program profile (customer tailoring): load + apply context header
    profile = None
    try:
        profile = evidence.load_profile(args.profile)
    except ValueError as e:
        print("error: bad profile: %s" % e)
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
    dispatch_rows = _dispatch_crosschecks(model)
    prov = _provenance(model, dispatch_rows)

    if args.out:
        with open(args.out, "w") as f:
            f.write(md if md.endswith("\n") else md + "\n")
        res = model["results"]
        print("built Flight Test Performance Data Analysis Report for "
              "%s (%s) -> %s" % (model["item"], model["sortie_id"],
                                 args.out))
        print("takeoff distance: %.1f m (35 ft); landing certified: "
              "%.1f m" % (res["takeoff"]["run"]["total_m"],
                          res["landing"]["certified_field_length_m"]))
        print("level-accel thrust available: %.1f N; cruise MRC M=%.3f"
              % (res["level_accel"]["mean_thrust_available"],
                 res["cruise"]["max_rp_mach"]))
        dispatched = [x for x in dispatch_rows if x.get("dispatched")]
        print("cross-checks: %d dispatch row(s); all agree=%s"
              % (len(dispatched),
                 all(x.get("agrees", False) for x in dispatched)))
        print("gates: all_pass=%s %s" % (gates["all_pass"], gates))
        if args.bundle:
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "Flight Test Performance Data Analysis Report",
                model, gates, prov)
            print("bundle: model=%s" % paths["model"])
            print("        gates=%s" % paths["gates"])
            print("        provenance=%s" % paths["provenance"])
    else:
        print(md)
    return 0 if gates["all_pass"] else 1


def cmd_check(args):
    if not os.path.exists(args.file):
        print("file not found: %s" % args.file)
        return 1
    md = open(args.file).read()
    gates = core.check_report_markdown(md)
    for name, ok in gates.items():
        if name != "all_pass":
            print("%s  %s" % ("PASS" if ok else "FAIL", name))
    print("RESULT: %s" % ("PASS" if gates["all_pass"] else "FAIL"))
    return 0 if gates["all_pass"] else 1


def main():
    p = argparse.ArgumentParser(
        description="Flight Test Performance Engineer role: performance "
                    "data analysis report")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="",
                   help="output file (default: stdout)")
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json")
    b.add_argument("--profile", default="",
                   help="program profile JSON (customer tailoring, "
                        "docs/PROFILE-SCHEMA.md)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="report markdown to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
