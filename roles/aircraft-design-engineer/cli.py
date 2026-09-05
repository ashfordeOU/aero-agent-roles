#!/usr/bin/env python3
"""cli.py - run the Aircraft Conceptual Design Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--pax N] [--range-nm R]
                       [--cruise-mach M] [--design-ws N]
  python3 cli.py check --file <file.md>

The role ENGINE (core/aircraft_design_core.py) does the work standalone;
bound skills in Aero Agent Skills deepen individual stages when present.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))
import aircraft_design_core as core


def cmd_build(args):
    item = core.example_item()
    # allow overriding the top-level requirement from the CLI
    if args.pax is not None:
        item.pax = args.pax
    if args.payload_per_pax is not None:
        item.payload_per_pax_lb = args.payload_per_pax
    if args.range_nm is not None:
        item.range_nm = args.range_nm
    if args.cruise_mach is not None:
        item.cruise_mach = args.cruise_mach
    if args.tofl_m is not None:
        item.tofl_m = args.tofl_m
    if args.design_ws is not None:
        item.design_ws_nm2 = args.design_ws
    model = core.build_concept(item)
    md = core.render_concept_markdown(model)
    gates = core.check_concept(model)
    s = model["sizing"]
    dp = model["design_point"]
    if args.out:
        with open(args.out, "w") as f:
            f.write(md)
        print(f"built concept package -> {args.out}")
    else:
        print(md)
    print(f"MTOW {s['mtow_lb']:,.0f} lb converged in {s['n_iterations']} "
          f"iterations; design point W/S {dp['ws_nm2']:,.0f} N/m^2, "
          f"T/W {dp['tw_required']:.4f} ({dp['binding_constraint']})")
    print(f"gates: all_pass={gates['all_pass']} {gates}")
    return 0 if gates["all_pass"] else 1


def cmd_check(args):
    if not os.path.exists(args.file):
        print(f"file not found: {args.file}")
        return 1
    md = open(args.file).read()
    gates = core.check_concept_markdown(md)
    for name, ok in gates.items():
        if name != "all_pass":
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print(f"RESULT: {'PASS' if gates['all_pass'] else 'FAIL'}")
    return 0 if gates["all_pass"] else 1


def main():
    p = argparse.ArgumentParser(
        description="Aircraft Conceptual Design Engineer role")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="", help="output file (default: stdout)")
    b.add_argument("--pax", type=int, default=None, help="passenger count")
    b.add_argument("--payload-per-pax", type=float, default=None,
                   help="payload per passenger, lb")
    b.add_argument("--range-nm", type=float, default=None,
                   help="design range, nm")
    b.add_argument("--cruise-mach", type=float, default=None,
                   help="cruise Mach number")
    b.add_argument("--tofl-m", type=float, default=None,
                   help="takeoff field length, m")
    b.add_argument("--design-ws", type=float, default=None,
                   help="design wing loading, N/m^2 (default: example)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="concept design package markdown to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
