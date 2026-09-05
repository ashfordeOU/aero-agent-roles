#!/usr/bin/env python3
"""cli.py - run the Flight Management Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--rnp-nm <nm>] [--sigma <m>]
                       [--bundle] [--profile <p.json>]
    # build the flight plan + RNAV/RNP route assessment for the example
    # route; --rnp-nm / --sigma re-run the containment check with other
    # facts; --bundle emits evidence/{model,gates,provenance}.json
  python3 cli.py check --file <file.md>
    # gate-check an existing assessment document

The role ENGINE (core/flight_management_core.py) does the work standalone:
route structure (great-circle/RF/DME-arc/rhumb geometry), RNP containment,
holding entry, RTA speed control, VNAV profile, ECON performance, radio
navaid checks, and the evidence gates. When AeroSkills is present
(AEROSKILLS_DEV or ~/AeroSkills), the CLI dispatches the bound
rnp-anp-containment and holding-pattern-entry leaf logic and cross-checks
it against the core's computation - two independent implementations
agreeing is recorded in provenance.json.
"""
import argparse
import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import flight_management_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "flight-management-engineer"
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
_LEAF_PREFIX = os.path.join(AEROSKILLS, "skills", "avionics",
                            "flight-management")


def _load_leaf_logic(leaf, logic_name):
    """Import a bound leaf's *logic.py if present; else None."""
    path = os.path.join(_LEAF_PREFIX, leaf, "scripts", logic_name)
    if not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location("aeroskills_" + leaf.replace("-", "_"),
                                                  path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _dispatch_crosschecks(model):
    """Cross-check core numbers against the bound AeroSkills leaf logic.

    Row 1: RNP containment margin (rnp-anp-containment leaf
    margin_available_m vs core margin_available_m).
    Row 2: holding entry lap time (holding-pattern-entry leaf
    entry_lap_time_seconds vs core holding_entry_lap_seconds).
    Rows are None when the skills checkout (or a leaf) is absent; the
    role then simply ran standalone.
    """
    rows = []
    rnp = model.get("rnp", {}).get("containment", {})
    rnp_mod = _load_leaf_logic("rnp-anp-containment",
                               "rnp_anp_containment_logic.py")
    if rnp_mod is not None and rnp.get("anp_m") is not None:
        try:
            core_margin = core.margin_available_m(
                rnp["anp_m"], rnp["rnp_m"], 0.0)
            skill_margin = rnp_mod.margin_available_m(
                anp_m=rnp["anp_m"], rnp_m=rnp["rnp_m"], margin_fraction=0.0)
            delta = abs(core_margin - skill_margin)
            rows.append({
                "leaf": "avionics/flight-management/rnp-anp-containment",
                "skill_md": "SKILL.md",
                "logic_file": "scripts/rnp_anp_containment_logic.py",
                "function": "margin_available_m",
                "dispatched": True,
                "cross_check_point": "ANP %.1f m vs RNP %.1f m, margin %.0f %%"
                                     % (rnp["anp_m"], rnp["rnp_m"],
                                        model["rnp"].get("rnp_margin_fraction",
                                                         0.0) * 100),
                "core_value": round(float(core_margin), 6),
                "skill_value": round(float(skill_margin), 6),
                "delta": round(delta, 9),
                "agrees": delta <= 1e-6,
                "tolerance": 1e-6,
                "skills_release": "v1.3.0+",
            })
        except Exception as e:
            rows.append({"leaf": "avionics/flight-management/"
                                 "rnp-anp-containment",
                         "dispatched": True, "error": str(e), "agrees": False})
    hold = model.get("hold", {})
    hold_mod = _load_leaf_logic("holding-pattern-entry",
                                "holding_pattern_entry_logic.py")
    if hold_mod is not None and hold.get("entry"):
        try:
            core_lap = core.holding_entry_lap_seconds(hold["entry"],
                                                      hold["outbound_leg_s"])
            skill_lap = hold_mod.entry_lap_time_seconds(hold["entry"],
                                                        hold["outbound_leg_s"])
            delta = abs(core_lap - skill_lap)
            rows.append({
                "leaf": "avionics/flight-management/holding-pattern-entry",
                "skill_md": "SKILL.md",
                "logic_file": "scripts/holding_pattern_entry_logic.py",
                "function": "entry_lap_time_seconds",
                "dispatched": True,
                "cross_check_point": ("%s entry, %.0f s outbound leg"
                                      % (hold["entry"], hold["outbound_leg_s"])),
                "core_value": round(float(core_lap), 6),
                "skill_value": round(float(skill_lap), 6),
                "delta": round(delta, 9),
                "agrees": delta <= 1e-6,
                "tolerance": 1e-6,
                "skills_release": "v1.3.0+",
            })
        except Exception as e:
            rows.append({"leaf": "avionics/flight-management/"
                                 "holding-pattern-entry",
                         "dispatched": True, "error": str(e), "agrees": False})
    return rows


def _provenance(model, dispatch_rows):
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/flight_management_core.py",
            "functions": ["containment_analysis", "hold_entry_analysis",
                          "rf_leg_geometry", "rhumb_vs_great_circle",
                          "dme_arc_geometry", "rta_speed_command",
                          "vnav_tod_distance_nm", "perf_econ_summary"],
            "version": "0.1.0",
        },
        "skills": dispatch_rows,
        "cross_checked": bool(dispatch_rows),
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def cmd_build(args):
    item = core.example_item()
    if args.rnp_nm:
        item.rnp_nm = float(args.rnp_nm)
    if args.sigma:
        item.sigma_lateral_m = float(args.sigma)
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
    dispatch_rows = [] if args.no_dispatch else _dispatch_crosschecks(model)
    if args.out:
        with open(args.out, "w") as f:
            f.write(md if md.endswith("\n") else md + "\n")
        print("built flight plan + RNAV/RNP route assessment -> %s" % args.out)
        print("route: %s" % model["route_id"])
        print("total distance: %.2f NM | RNP %.1f | containment: %s | "
              "hold entry: %s | RTA: %s"
              % (model["total_distance_nm"], model["rnp"]["rnp_nm"],
                 model["rnp"]["containment"]["verdict"], model["hold"]["entry"],
                 model["rta"]["verdict"]))
        print("gates: all_pass=%s %s" % (gates["all_pass"], gates))
        if args.bundle:
            prov = _provenance(model, dispatch_rows)
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "flight plan and RNAV/RNP route assessment",
                model, gates, prov)
            print("bundle: model=%s" % paths["model"])
            print("        gates=%s" % paths["gates"])
            print("        provenance=%s" % paths["provenance"])
            if dispatch_rows:
                for row in dispatch_rows:
                    if "error" in row:
                        print("cross-check: %s error: %s"
                              % (row["leaf"], row["error"]))
                    else:
                        print("cross-check: %s core=%.6f skill=%.6f "
                              "delta=%.9f agrees=%s"
                              % (row["leaf"], row["core_value"],
                                 row["skill_value"], row["delta"],
                                 row["agrees"]))
            else:
                print("cross-check: not dispatched (no AeroSkills logic)")
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
        description="Flight Management Engineer role")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="",
                   help="output file (default: stdout)")
    b.add_argument("--rnp-nm", default="",
                   help="RNP for the segment in NM (default: example 0.3)")
    b.add_argument("--sigma", default="",
                   help="1-sigma lateral position error in m (default: example)")
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json")
    b.add_argument("--no-dispatch", action="store_true",
                   help="skip dispatching bound AeroSkills logic")
    b.add_argument("--profile", default="",
                   help="program profile JSON (customer tailoring, "
                        "docs/PROFILE-SCHEMA.md)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="route assessment markdown to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
