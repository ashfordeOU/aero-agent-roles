#!/usr/bin/env python3
"""cli.py - run the Flight Mechanics Engineer role.

Usage:
  python3 cli.py build [--out <file.md>]   # build the Performance + S&C report
                                           # for the example transport
  python3 cli.py check --file <file.md>    # gate-check an existing report

The role ENGINE (core/flight_mechanics_core.py) does the work standalone
(real domain rules -> real numbers); bound flight-mechanics skills in Aero
Agent Skills deepen individual stages when present.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "core"))
import flight_mechanics_core as core


def cmd_build(args):
    results = core.analyze_vehicle(core.example_vehicle())
    model = core.build_report(core.example_vehicle(), results)
    md = core.render_report_markdown(model)
    gates = core.check_report(results)
    if args.out:
        with open(args.out, "w") as f:
            f.write(md)
        print(f"built Performance + S&C report for {model['aircraft']} "
              f"-> {args.out}")
        print(f"gates: all_pass={gates['all_pass']} {gates}")
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
        description="Flight Mechanics Engineer role: performance + S&C "
                    "analysis report")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="",
                   help="output file (default: stdout)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="Performance + S&C report markdown to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
