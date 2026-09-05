#!/usr/bin/env python3
"""cli.py - run the Flight Test Engineer role.

Usage:
  python3 cli.py build --out <file.md>          # build plan + report for the
                                                # worked-example aircraft
  python3 cli.py check --file <file.md>         # gate-check a deliverable

The role ENGINE (core/flight_test_core.py) does the work standalone;
bound skills in Aero Agent Skills deepen individual stages when present.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))
import flight_test_core as core


def cmd_build(args):
    ac = core.example_aircraft()
    if args.aircraft_name:
        ac.name = args.aircraft_name
    model = core.build_flight_test_deliverable(ac)
    md = core.render_flight_test_markdown(model)
    gates = core.check_flight_test_deliverable(model)
    if args.out:
        with open(args.out, "w") as f:
            f.write(md)
        print(f"built flight test plan + envelope report -> {args.out}")
        print(f"gates: all_pass={gates['all_pass']} {gates}")
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
    b.add_argument("--aircraft-name", default="",
                   help="override the worked-example aircraft name")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="flight test plan/report markdown to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
