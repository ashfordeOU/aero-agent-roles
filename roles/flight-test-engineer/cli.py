#!/usr/bin/env python3
"""cli.py - run the Flight Test Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--bundle]   # build plan + report
                                # for the worked-example aircraft
                                # --bundle  also emit evidence/{model,gates,
                                #           provenance}.json (PROTOCOL.md)
  python3 cli.py check --file <file.md>         # gate-check a deliverable

The role ENGINE (core/flight_test_core.py) does the work standalone;
bound skills in Aero Agent Skills deepen individual stages when present.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import flight_test_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "flight-test-engineer"


def _provenance(model):
    """Where the deliverable numbers came from (PROTOCOL.md provenance).

    The core is the sole computation engine for this role run; no bound
    AeroSkills leaf logic is dispatched, so skills stays empty and the
    deliverable is valid but not skill-cross-checked."""
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/flight_test_core.py",
            "functions": ["v_speeds", "flutter_speed_from_damping",
                          "damping_margin", "stall_warning_verdict",
                          "mach_grid_row", "build_flight_test_deliverable",
                          "check_flight_test_deliverable"],
            "version": "0.1.0",
        },
        "skills": [],
        "cross_checked": False,
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def cmd_build(args):
    ac = core.example_aircraft()
    if args.aircraft_name:
        ac.name = args.aircraft_name
    model = core.build_flight_test_deliverable(ac)
    md = core.render_flight_test_markdown(model)

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

    gates = core.check_flight_test_deliverable(model)
    if args.out:
        with open(args.out, "w") as f:
            f.write(md)
        print(f"built flight test plan + envelope report -> {args.out}")
        if profile:
            print(f"profile: {profile.get('customer')} / "
                  f"{profile.get('program')}")
        print(f"gates: all_pass={gates['all_pass']} {gates}")
        if args.bundle:
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "flight test plan + envelope report", model, gates,
                _provenance(model))
            print(f"bundle: model={paths['model']}")
            print(f"        gates={paths['gates']}")
            print(f"        provenance={paths['provenance']}")
    else:
        print(md)
    return 0 if gates["all_pass"] else 1


def cmd_check(args):
    if not os.path.exists(args.file):
        print(f"file not found: {args.file}")
        return 1
    md = open(args.file).read()
    gates = core.check_flight_test_markdown(md)
    for name, ok in gates.items():
        if name != "all_pass":
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print(f"RESULT: {'PASS' if gates['all_pass'] else 'FAIL'}")
    return 0 if gates["all_pass"] else 1


def main():
    p = argparse.ArgumentParser(description="Flight Test Engineer role")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="", help="output file (default: stdout)")
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json")
    b.add_argument("--aircraft-name", default="",
                   help="override the worked-example aircraft name")
    b.add_argument("--profile", default="",
                   help="program profile JSON (customer tailoring, "
                        "docs/PROFILE-SCHEMA.md)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="flight test plan/report markdown to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
