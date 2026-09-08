#!/usr/bin/env python3
"""cli.py - run the Navigation Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--vehicle <name>] \
      [--outage-s <seconds>] [--budget-m <meters>] [--bundle]
    # build the navigation architecture and error analysis report
    # --bundle      also emit evidence/{model,gates,provenance}.json (PROTOCOL.md)
  python3 cli.py check --file <file.md>             # gate-check a report

The role ENGINE (core/navigation_engineer_core.py) does the work
standalone; bound skills in Aero Agent Skills deepen individual stages
when present.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import navigation_engineer_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "navigation-engineer"


def cmd_build(args):
    proj = core.example_project()
    if args.vehicle:
        proj.vehicle = args.vehicle
    if args.outage_s:
        proj.outage_s = float(args.outage_s)
    if args.budget_m:
        proj.req_position_budget_m = float(args.budget_m)
    model = core.build_report(proj)
    md = core.render_report_markdown(model)

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
    if args.out:
        with open(args.out, "w") as f:
            f.write(md)
        print("built navigation architecture report (%s) -> %s"
              % (model["vehicle"], args.out))
        if profile:
            print("profile: %s / %s" % (profile.get("customer"),
                                        profile.get("program")))
        print("gates: all_pass=%s %s" % (gates["all_pass"], gates))
        if args.bundle:
            prov = {
                "role": ROLE_SLUG,
                "core": {
                    "file": "core/navigation_engineer_core.py",
                    "functions": ["wgs84_frame_constants",
                                  "ins_coasting_error_growth",
                                  "pseudorange_least_squares", "dop_from_geometry",
                                  "raim_fault_detection", "carrier_smoothed_variance",
                                  "doppler_velocity_accuracy",
                                  "rtk_double_difference_baseline",
                                  "ins_gnss_kalman_update",
                                  "tercom_correlation_match",
                                  "sitan_slope_update",
                                  "bearing_only_geometry", "build_report"],
                    "version": "0.1.0",
                },
                "skills": [],
                "cross_checked": False,
                "disclaimer": "DRAFT for human review. Not an approval document.",
            }
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "navigation architecture and position error analysis report",
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
    p = argparse.ArgumentParser(description="Navigation Engineer role")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="", help="output file (default: stdout)")
    b.add_argument("--vehicle", default="", help="vehicle / project name")
    b.add_argument("--outage-s", default="",
                   help="GNSS-denied outage duration (s)")
    b.add_argument("--budget-m", default="",
                   help="integrated position error budget (m, 1-sigma)")
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json")
    b.add_argument("--profile", default="",
                   help="program profile JSON (customer tailoring, "
                        "docs/PROFILE-SCHEMA.md)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="navigation report markdown to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
