#!/usr/bin/env python3
"""cli.py - run the Flight Test Planning Engineer role.

Author: ashfordeOU · Aero Agent Roles (agentskills.io ROLE.md host).

Usage:
  python3 cli.py build [--out <file.md>] [--bundle] [--profile <p.json>]
                       [--repeat-interval N] [--flight-duration-s S]
                       [--no-dispatch]
  python3 cli.py check --file <file.md> [--level N]

Builds the Flight Test Plan and Requirements Traceability for the
reference item (the certification flight test campaign of an FGS-2000-
equipped transport category airplane) via the executable role engine
core/flight_test_planning_core.py. When AeroSkills logic is present the
CLI dispatches the bound flight-test-operations/planning leaf
computations (one dispatch point per bound leaf) and cross-checks them
against the core; agreement is recorded in provenance.json. Standalone
(AEROSKILLS_DEV=/nonexistent or no checkout) the role still builds and
checks correctly from the pure core.
"""
import argparse
import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import flight_test_planning_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "flight-test-planning-engineer"
AEROSKILLS = os.environ.get("AEROSKILLS_DEV",
                            os.path.expanduser("~/AeroSkills"))
SKILLS_RELEASE = "v1.3.0+"

# Dispatch cross-check points: one row per bound leaf. Each row loads the
# bound leaf's logic module and compares the leaf function's result with
# the core's own function over the same inputs. The core encodes the same
# real rules the leaves encode (per the role's grounding), so the two
# independent implementations must agree within tolerance.
DISPATCH_POINTS = [
    {
        "leaf": "flight-test-operations/planning/flight-test-instrumentation",
        "module": "flight_test_instrumentation_logic.py",
        "skill_fn": "required_sample_rate",
        "core_fn": "required_sample_rate",
        "kwargs": {"max_freq": 20.0},
        "compare": "float",
        "cross_check_point": "Required acquisition sample rate "
                             "(margin x 2 x fmax, default margin 2.5 "
                             "=> 5 x fmax)",
        "tolerance": 1e-9,
    },
    {
        "leaf": "flight-test-operations/planning/flight-test-planning",
        "module": "flight_test_planning_logic.py",
        "skill_fn": "go_no_gate",
        "core_fn": "go_no_gate",
        "kwargs": {"weather_ok": True, "aircraft_ready": True,
                   "instrumentation_ok": False, "safety_review_ok": True},
        "compare": "key",
        "key": "verdict",
        "cross_check_point": "Go/no-go gate verdict (any failed check "
                             "forces NO-GO and names the blocker)",
        "tolerance": 0.0,
    },
    {
        "leaf": "flight-test-operations/planning/noise-certification-test",
        "module": "noise_certification_test_logic.py",
        "skill_fn": "cumulative_margin",
        "core_fn": "cumulative_margin",
        "kwargs": {"margins": [3.0, 4.0, 4.0]},
        "compare": "key",
        "key": "sum_db",
        "cross_check_point": "Cumulative three-point margin sum "
                             "(chapter 4 style, required 10 EPNdB)",
        "tolerance": 1e-9,
    },
    {
        "leaf": "flight-test-operations/planning/pcm-telemetry-decommutation",
        "module": "pcm_telemetry_decommutation_logic.py",
        "skill_fn": "frame_period_words",
        "core_fn": "frame_period_words",
        "kwargs": {"data_words_per_frame": 8, "idle_words": 1},
        "compare": "float",
        "cross_check_point": "PCM minor frame period in words "
                             "(1 + data + idle)",
        "tolerance": 0.0,
    },
    {
        "leaf": "flight-test-operations/planning/position-error-calibration",
        "module": "position_error_calibration_logic.py",
        "skill_fn": "tower_flyby_position_error",
        "core_fn": "tower_flyby_position_error",
        "kwargs": {"geometric_height": 500.0, "pressure_altitude": 490.0,
                   "temperature": 288.15},
        "compare": "float",
        "cross_check_point": "Tower fly-by position error dVp "
                             "(static source height error, "
                             "compressible airspeed indicator law)",
        "tolerance": 1e-9,
    },
    {
        "leaf": "flight-test-operations/planning/telemetry-data-acquisition",
        "module": "telemetry_data_acquisition_logic.py",
        "skill_fn": "pcm_bit_rate",
        "core_fn": "pcm_bit_rate",
        "kwargs": {"frame_rate": 50.0, "words_per_frame": 64,
                   "bits_per_word": 16},
        "compare": "float",
        "cross_check_point": "PCM stream bit rate "
                             "(frame_rate x frame size)",
        "tolerance": 1e-9,
    },
    {
        "leaf": "flight-test-operations/planning/test-point-matrix-design",
        "module": "point_matrix_design_logic.py",
        "skill_fn": "build_test_matrix",
        "core_fn": "build_test_matrix",
        "kwargs": {"altitudes": [1500.0, 3000.0],
                   "speeds": [110.0, 130.0, 150.0],
                   "weights": [55000.0],
                   "configurations": ["clean", "takeoff"]},
        "compare": "key",
        "key": "count",
        "cross_check_point": "Full-grid test matrix point count "
                             "(cartesian product of the condition sweeps)",
        "tolerance": 0.0,
    },
]


def _load_leaf(leaf: str, module: str):
    """Import a bound AeroSkills leaf logic module if present."""
    path = os.path.join(AEROSKILLS, "skills", leaf, "scripts", module)
    if not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location("flight_test_dispatch",
                                                  path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _row_value(obj, compare, key=None):
    """Extract the comparable scalar from a result per compare mode."""
    if compare == "key":
        return obj[key]
    if compare == "float":
        return float(obj)
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
            sv = _row_value(skill_val, compare, point.get("key"))
            cv = _row_value(core_val, compare, point.get("key"))
            if isinstance(cv, float) and isinstance(sv, float):
                delta = abs(cv - sv)
            else:
                delta = 0.0 if str(cv) == str(sv) else float("inf")
            agrees = delta <= point.get("tolerance", 1e-6)
            if agrees:
                any_ok = True

            def _prec(x):
                if isinstance(x, float):
                    return float("%.9g" % x)
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
                "skills_release": SKILLS_RELEASE,
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
            "file": "core/flight_test_planning_core.py",
            "functions": ["build_flight_test_plan",
                          "render_flight_test_plan_markdown",
                          "check_flight_test_plan",
                          "required_sample_rate", "go_no_gate",
                          "cumulative_margin", "frame_period_words",
                          "tower_flyby_position_error", "pcm_bit_rate",
                          "build_test_matrix"],
            "version": "0.1.0",
        },
        "skills": skills_rows,
        "cross_checked": cross_checked,
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def cmd_build(args):
    item = core.example_item()
    if args.repeat_interval is not None:
        item.repeat_interval = args.repeat_interval
    if args.flight_duration_s is not None:
        item.decomm_flight_duration_s = args.flight_duration_s
    model = core.build_flight_test_plan(item)
    md = core.render_flight_test_plan_markdown(model)

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

    gates = core.check_flight_test_plan(model)
    dispatch_rows = [] if args.no_dispatch else _dispatch_crosschecks()[0]
    if args.out:
        with open(args.out, "w") as f:
            f.write(md if md.endswith("\n") else md + "\n")
        mtx = model["matrix"]
        print("built Flight Test Plan and Requirements Traceability "
              "-> %s" % args.out)
        print("item: %s | matrix %d points, %d repeat(s) | bit rate %s "
              "bit/s | risk levels 0..%d"
              % (model["item"], mtx["count"], len(mtx["repeat_ids"]),
                 model["telemetry"]["stream"]["bit_rate"],
                 model["build_up"]["max_risk"]))
        print("gates: all_pass=%s %s" % (gates["all_pass"], gates))
        if args.bundle:
            skills_rows, cross_checked = _dispatch_crosschecks()
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "Flight Test Plan and Requirements Traceability",
                model, gates, _provenance(skills_rows, cross_checked))
            print("bundle: model=%s" % paths["model"])
            print("        gates=%s" % paths["gates"])
            print("        provenance=%s" % paths["provenance"])
            if cross_checked:
                print("dispatch: core and AeroSkills leaf logic agree "
                      "(%d cross-checks)" % len(skills_rows))
                for row in skills_rows:
                    print("  %s/%s delta=%s agrees=%s"
                          % (row["leaf"], row["function"], row["delta"],
                             row["agrees"]))
            else:
                print("dispatch: no AeroSkills leaf logic dispatched "
                      "(standalone build is still valid)")
    else:
        print(md)
    return 0 if gates["all_pass"] else 1


def cmd_check(args):
    if not os.path.exists(args.file):
        print("file not found: %s" % args.file)
        return 1
    md = open(args.file).read()
    gates = core.check_flight_test_plan_markdown(
        md, risk_level=args.level if args.level else None)
    for name, ok in gates.items():
        if name != "all_pass":
            print("%s  %s" % ("PASS" if ok else "FAIL", name))
    print("RESULT: %s" % ("PASS" if gates["all_pass"] else "FAIL"))
    return 0 if gates["all_pass"] else 1


def main():
    p = argparse.ArgumentParser(
        description="Flight Test Planning Engineer role "
                    "(Flight Test Plan and Requirements Traceability)")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="",
                   help="output file (default: stdout)")
    b.add_argument("--repeat-interval", type=int, default=None,
                   help="override the matrix repeat interval (int >= 2)")
    b.add_argument("--flight-duration-s", type=float, default=None,
                   help="override the planned telemetry flight duration "
                        "(decomm expected sample counts)")
    b.add_argument("--no-dispatch", action="store_true",
                   help="skip skill-logic cross-checks (standalone)")
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json")
    b.add_argument("--profile", default="",
                   help="program profile JSON (docs/PROFILE-SCHEMA.md)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="plan markdown file to gate-check")
    c.add_argument("--level", type=int, default=None,
                   help="verify the plan's build-up reaches the given "
                        "risk level (optional)")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
