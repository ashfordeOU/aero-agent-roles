#!/usr/bin/env python3
"""cli.py - run the GNC Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--bandwidth <rad/s>] \
      [--phase-margin <deg>] [--gain-margin <dB>]   # build the GNC report
  python3 cli.py check --file <file.md>             # gate-check a report

The role ENGINE (core/gnc_core.py) does the work standalone; bound
skills in Aero Agent Skills deepen individual stages when present.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "core"))
import gnc_core as core  # noqa: E402


def cmd_build(args):
    proj = core.example_project()
    # allow overriding requirements / vehicle from the CLI
    if args.vehicle:
        proj.vehicle = args.vehicle
    if args.bandwidth:
        proj.req_bandwidth_rad_s = float(args.bandwidth)
    if args.phase_margin:
        proj.req_phase_margin_deg = float(args.phase_margin)
    if args.gain_margin:
        proj.req_gain_margin_db = float(args.gain_margin)
    model = core.build_gnc_report(proj)
    md = core.render_gnc_report_markdown(model)
    gates = core.check_gnc_report(model)
    if args.out:
        with open(args.out, "w") as f:
            f.write(md)
        print("built GNC design report (%s) -> %s"
              % (model["vehicle"], args.out))
        print("gates: all_pass=%s %s" % (gates["all_pass"], gates))
    else:
        print(md)
    return 0 if gates["all_pass"] else 1


def cmd_check(args):
    if not os.path.exists(args.file):
        print("file not found: %s" % args.file)
        return 1
    md = open(args.file).read()
    gates = core.check_gnc_report_markdown(md)
    for name, ok in gates.items():
        if name != "all_pass":
            print("%s  %s" % ("PASS" if ok else "FAIL", name))
    print("RESULT: %s" % ("PASS" if gates["all_pass"] else "FAIL"))
    return 0 if gates["all_pass"] else 1


def main():
    p = argparse.ArgumentParser(description="GNC Engineer role")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="", help="output file (default: stdout)")
    b.add_argument("--vehicle", default="", help="vehicle / project name")
    b.add_argument("--bandwidth", default="",
                   help="attitude bandwidth requirement (rad/s)")
    b.add_argument("--phase-margin", default="",
                   help="phase margin requirement (deg)")
    b.add_argument("--gain-margin", default="",
                   help="gain margin requirement (dB)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="GNC design report markdown to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
