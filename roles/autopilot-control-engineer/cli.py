#!/usr/bin/env python3
"""cli.py - run the Autopilot Control Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--vehicle NAME]
      [--phase-margin <deg>] [--gain-margin <dB>] [--bundle]
      [--profile <profile.json>]
    # build the Autopilot Control-Law Design Package
    # --bundle      also emit evidence/{model,gates,provenance}.json (PROTOCOL.md)
    # --profile     apply a program profile (customer tailoring)
  python3 cli.py check --file <file.md>             # gate-check a package

The role ENGINE (core/autopilot_control_engineer_core.py) does the work
standalone; bound skills in Aero Agent Skills deepen individual stages
when the library is present.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import autopilot_control_engineer_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "autopilot-control-engineer"


def cmd_build(args):
    item = core.example_item()
    if args.vehicle:
        item.vehicle = args.vehicle
    if args.phase_margin:
        item.req_phase_margin_deg = float(args.phase_margin)
    if args.gain_margin:
        item.req_gain_margin_db = float(args.gain_margin)
    model = core.build_package(item)
    md = core.render_package_markdown(model)

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

    gates = core.check_package(model)
    if args.out:
        with open(args.out, "w") as f:
            f.write(md if md.endswith("\n") else md + "\n")
        print("built Autopilot Control-Law Design Package (%s) -> %s"
              % (model["vehicle"], args.out))
        if profile:
            print("profile: %s / %s" % (profile.get("customer"),
                                        profile.get("program")))
        print("gates: all_pass=%s %s" % (gates["all_pass"], gates))
        if args.bundle:
            prov = {
                "role": ROLE_SLUG,
                "core": {
                    "file": "core/autopilot_control_engineer_core.py",
                    "functions": ["companion_form_2state", "eig2x2",
                                  "pid_gains_second_order", "loop_margins",
                                  "type1_margins", "closed_loop_poles_rl",
                                  "gain_for_damping_rl",
                                  "observer_gain_2state", "l1_simulate",
                                  "l1_convergence_report", "schedule_gain",
                                  "zoh_first_order",
                                  "pseudoinverse_alloc_row",
                                  "build_package"],
                    "version": "0.1.0",
                },
                "skills": [],
                "cross_checked": False,
                "disclaimer": ("DRAFT for human review. Not an approval "
                              "document."),
            }
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG, "Autopilot Control-Law Design Package",
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
    gates = core.check_package_markdown(md)
    for name, ok in gates.items():
        if name != "all_pass":
            print("%s  %s" % ("PASS" if ok else "FAIL", name))
    print("RESULT: %s" % ("PASS" if gates["all_pass"] else "FAIL"))
    return 0 if gates["all_pass"] else 1


def main():
    p = argparse.ArgumentParser(
        description="Autopilot Control Engineer role: build/check the "
                    "Autopilot Control-Law Design Package")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="", help="output file (default: stdout)")
    b.add_argument("--vehicle", default="", help="vehicle / project name")
    b.add_argument("--phase-margin", default="",
                   help="phase margin requirement (deg)")
    b.add_argument("--gain-margin", default="",
                   help="gain margin requirement (dB)")
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json")
    b.add_argument("--profile", default="",
                   help="program profile JSON (customer tailoring, "
                        "docs/PROFILE-SCHEMA.md)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="Autopilot Control-Law Design Package markdown "
                        "to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
