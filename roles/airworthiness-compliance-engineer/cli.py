#!/usr/bin/env python3
"""cli.py - run the Airworthiness Compliance Engineer role.

Usage:
  python3 cli.py build --out <file.md>          # build the compliance matrix
  python3 cli.py check --file <file.md>         # gate-check an existing matrix

The role ENGINE (core/airworthiness_core.py) does the work standalone;
bound skills in Aero Agent Skills deepen individual stages when present.

Author: ashfordeOU
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))
import airworthiness_core as core


def cmd_build(args):
    item = core.example_item()
    # allow overriding jurisdiction/aircraft from CLI for different bases
    if args.jurisdiction:
        item.jurisdiction = args.jurisdiction
    if args.aircraft:
        item.aircraft_type = args.aircraft
    if args.path:
        item.certification_path = args.path
    model = core.build_matrix(item)
    md = core.render_matrix_markdown(model)
    gates = core.check_matrix(model)
    if args.out:
        with open(args.out, "w") as f:
            f.write(md)
        print("built compliance matrix (basis %s, %d regs, coverage %.0f%%)"
              " -> %s"
              % (model["certification_basis"], model["row_count"],
                 model["coverage"] * 100.0, args.out))
        print("gates: all_pass=%s %s" % (gates["all_pass"], gates))
    else:
        print(md)
    return 0 if gates["all_pass"] else 1


def cmd_check(args):
    if not os.path.exists(args.file):
        print("file not found: %s" % args.file)
        return 1
    md = open(args.file).read()
    gates = core.check_matrix_markdown(md)
    for name, ok in gates.items():
        if name != "all_pass":
            print("%s  %s" % ("PASS" if ok else "FAIL", name))
    print("RESULT: %s" % ("PASS" if gates["all_pass"] else "FAIL"))
    return 0 if gates["all_pass"] else 1


def main():
    p = argparse.ArgumentParser(
        description="Airworthiness Compliance Engineer role")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="", help="output file (default: stdout)")
    b.add_argument("--jurisdiction", default="",
                   help="FAA (FAR-25 basis) or EASA (CS-25 basis)")
    b.add_argument("--aircraft", default="", help="aircraft type (default: transport)")
    b.add_argument("--path", default="", help="certification path (default: STC)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="compliance matrix markdown file to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
