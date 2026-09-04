#!/usr/bin/env python3
"""cli.py - run the DO-178C Certification Engineer role.

Usage:
  python3 cli.py build --out <file.md>          # build PSAC for the example item
  python3 cli.py check --file <file.md>         # gate-check an existing PSAC

The role ENGINE (core/do178c_core.py) does the work standalone; bound
skills in Aero Agent Skills deepen individual stages when present.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))
import do178c_core as core


def cmd_build(args):
    item = core.example_item()
    # allow overriding the failure condition from CLI for different DALs
    if args.failure_condition:
        item.failure_condition = args.failure_condition
        item.system_safety_ref = args.safety_ref or item.system_safety_ref
    model = core.build_psac(item)
    md = core.render_psac_markdown(model)
    gates = core.check_psac(model)
    if args.out:
        with open(args.out, "w") as f:
            f.write(md)
        print(f"built PSAC (level {model['software_level']}) -> {args.out}")
        print(f"gates: all_pass={gates['all_pass']} {gates}")
    else:
        print(md)
    return 0 if gates["all_pass"] else 1


def cmd_check(args):
    if not os.path.exists(args.file):
        print(f"file not found: {args.file}")
        return 1
    md = open(args.file).read()
    # determine level from the doc if not given
    dal = (args.dal or "B").upper()
    gates = core.check_psac_markdown(md, dal)
    for name, ok in gates.items():
        if name != "all_pass":
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print(f"RESULT: {'PASS' if gates['all_pass'] else 'FAIL'}")
    return 0 if gates["all_pass"] else 1


def main():
    p = argparse.ArgumentParser(description="DO-178C Certification Engineer role")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="", help="output file (default: stdout)")
    b.add_argument("--failure-condition", default="", help="hazardous/major/minor/...")
    b.add_argument("--safety-ref", default="", help="system safety reference")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True, help="PSAC markdown file to gate-check")
    c.add_argument("--dal", default="", help="expected software level")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
