#!/usr/bin/env python3
"""cli.py - run the Propulsion Engineer role.

Usage:
  python3 cli.py build --out <file.md>                # turbofan design report
  python3 cli.py build --engine rocket --out r.md     # rocket option report
  python3 cli.py build --engine turbofan --bpr 6 --opr 25  # parameter sweep
  python3 cli.py build --out <file.md> --bundle       # + evidence/{model,gates,provenance}.json
  python3 cli.py check --file <file.md>               # gate-check a report

The role ENGINE (core/propulsion_core.py) does the work standalone; bound
skills in Aero Agent Skills deepen individual stages when present. With
--bundle the CLI also writes the PROTOCOL.md v1 evidence bundle
(evidence/{model,gates,provenance}.json) next to the deliverable.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import propulsion_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "propulsion-engineer"


def _provenance(model):
    """Provenance for the evidence bundle (PROTOCOL.md v1).

    The propulsion role core computes every number standalone (cycle,
    envelope, trade, rocket sizing); no bound skill logic is dispatched,
    so the skills list is empty and the bundle is not cross-checked.
    """
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/propulsion_core.py",
            "functions": ["turbofan_design_point", "off_design_envelope",
                          "bpr_trend", "rocket_engine_cycle_analysis",
                          "rocket_nozzle_sizing"],
            "version": "0.1.0",
        },
        "skills": [],
        "cross_checked": False,
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def _apply_overrides(item, args):
    if args.bpr is not None:
        item.bpr = args.bpr
    if args.opr is not None:
        item.opr = args.opr
    if args.tit is not None:
        item.tit_k = args.tit
    if args.fpr is not None:
        item.fpr = args.fpr
    if args.thrust is not None:
        item.thrust_requirement_n = args.thrust * 1000.0
    if args.engine == "rocket":
        if args.thrust is not None:
            item.thrust_vac_n = args.thrust * 1000.0
    return item


def cmd_build(args):
    if args.engine == "rocket":
        item = core.example_rocket_item()
    else:
        item = core.example_turbofan_item()
    item = _apply_overrides(item, args)
    model = core.build_report(item)
    md = core.render_report_markdown(model)
    gates = core.check_report(model)
    if args.out:
        with open(args.out, "w") as f:
            f.write(md)
        kind = model["engine_kind"]
        print(f"built {kind} design report -> {args.out}")
        print(f"gates: all_pass={gates['all_pass']} {gates}")
        if args.bundle:
            prov = _provenance(model)
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG, "propulsion design report",
                model, dict(gates, checker="check_report"), prov)
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
    gates = core.check_report_markdown(md)
    for name, ok in gates.items():
        if name != "all_pass":
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print(f"RESULT: {'PASS' if gates['all_pass'] else 'FAIL'}")
    return 0 if gates["all_pass"] else 1


def main():
    p = argparse.ArgumentParser(description="Propulsion Engineer role")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="", help="output file (default: stdout)")
    b.add_argument("--engine", default="turbofan",
                   choices=["turbofan", "rocket"],
                   help="engine class for the reference item")
    b.add_argument("--bpr", type=float, default=None, help="bypass ratio")
    b.add_argument("--opr", type=float, default=None, help="overall pressure ratio")
    b.add_argument("--tit", type=float, default=None, help="turbine inlet temp (K)")
    b.add_argument("--fpr", type=float, default=None, help="fan pressure ratio")
    b.add_argument("--thrust", type=float, default=None,
                   help="thrust requirement (kN)")
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json "
                        "(PROTOCOL.md v1, requires --out)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True, help="report markdown to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
