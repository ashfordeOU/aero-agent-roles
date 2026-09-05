#!/usr/bin/env python3
"""cli.py - run the Structures and Loads Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--category <normal|commuter|transport>]
                       [--weight <lb>]    # build the loads + strength report
  python3 cli.py check --file <file.md>   # gate-check an existing report

The role ENGINE (core/structures_loads_core.py) does the work standalone:
FAR 25 gust/maneuver envelope, limit/ultimate loads, root internal loads,
margins of safety per critical component, fatigue screening with the
S-N basis and Miner sum, dynamics, and the evidence gates. Bound skills
in Aero Agent Skills deepen individual stages when present.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "core"))
import structures_loads_core as core


def cmd_build(args):
    item = core.example_item()
    # allow overriding category and gross weight from CLI for other wings
    if args.category:
        item.category = args.category
    if args.weight:
        item.resize_for_weight(float(args.weight))
    model = core.build_report(item)
    md = core.render_report_markdown(model)
    gates = core.check_report(model)
    if args.out:
        with open(args.out, "w") as f:
            f.write(md if md.endswith("\n") else md + "\n")
        print("built loads + strength report -> %s" % args.out)
        print("design limit: %s, n_limit=%.2f, n_ult=%.2f"
              % (model["loads_condition"], model["n_limit"], model["n_ult"]))
        print("gates: all_pass=%s %s" % (gates["all_pass"], gates))
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
        description="Structures and Loads Engineer role")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="", help="output file (default: stdout)")
    b.add_argument("--category", default="",
                   help="normal/commuter/transport (default: example)")
    b.add_argument("--weight", default="",
                   help="gross weight in lb to re-size the example wing")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="loads + strength report markdown to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
