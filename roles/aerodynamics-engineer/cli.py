#!/usr/bin/env python3
"""cli.py - run the Aerodynamics Engineer role.

Usage:
  python3 cli.py build [--out file.md] [--mach M] [--altitude m] [--ws N/m2]
  python3 cli.py check --file file.md

`build` computes the aerodynamic design report for the reference aircraft
(example_item) with the role ENGINE (core/aerodynamics_core.py), applying
any condition overrides:
  --mach <x>        cruise Mach number (default 0.78)
  --altitude <m>    cruise altitude in metres (default 10668)
  --ws <N/m2>       cruise wing loading W/S override; the cruise weight
                    becomes ws * S_ref (geometry stays fixed)
`check` gate-checks an existing report markdown document.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))
import aerodynamics_core as core


def cmd_build(args):
    item = core.example_item()
    if args.mach is not None:
        item.cruise_mach = args.mach
    if args.altitude is not None:
        item.cruise_altitude_m = args.altitude
    if args.ws is not None:
        if args.ws <= 0:
            print("error: --ws must be > 0")
            return 1
        item.w_cruise = args.ws * item.s_ref
    model = core.build_report(item)
    md = core.render_report_markdown(model)
    gates = core.check_report(model)
    if args.out:
        with open(args.out, "w") as f:
            f.write(md)
        print("built aerodynamic design report for %s -> %s"
              % (model["aircraft"], args.out))
        print("CL_cruise=%.3f  CD0=%.5f  L/D=%.2f  M_DD=%.3f  "
              "flutter_margin=%.2f"
              % (model["cl_cruise"], model["cd0"], model["ld_cruise"],
                 model["m_dd"], model["flutter_margin"]))
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
    for name, ok in sorted(gates.items()):
        if name != "all_pass":
            print("%s  %s" % ("PASS" if ok else "FAIL", name))
    print("RESULT: %s" % ("PASS" if gates["all_pass"] else "FAIL"))
    return 0 if gates["all_pass"] else 1


def main():
    p = argparse.ArgumentParser(description="Aerodynamics Engineer role")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="", help="output file (default: stdout)")
    b.add_argument("--mach", type=float, default=None,
                   help="cruise Mach override (default 0.78)")
    b.add_argument("--altitude", type=float, default=None,
                   help="cruise altitude override in metres (default 10668)")
    b.add_argument("--ws", type=float, default=None,
                   help="cruise wing loading W/S override in N/m2 "
                        "(cruise weight = ws * S_ref)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="aerodynamic design report markdown to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
