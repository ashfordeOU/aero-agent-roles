#!/usr/bin/env python3
"""cli.py - run the Flight Mechanics Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--bundle]
    # build the Performance + S&C report for the example transport
    # --bundle  also emit evidence/{model,gates,provenance}.json (PROTOCOL.md)
  python3 cli.py check --file <file.md>    # gate-check an existing report

The role ENGINE (core/flight_mechanics_core.py) does the work standalone
(real domain rules -> real numbers); bound flight-mechanics skills in Aero
Agent Skills deepen individual stages when present.
"""
import argparse
import dataclasses
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import flight_mechanics_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "flight-mechanics-engineer"


def _jsonable(obj):
    """Recursively convert the content model to plain JSON types.

    The model embeds the ExampleTransport configuration dataclass inside
    results['aircraft']; the evidence bundle (PROTOCOL.md v1) requires
    plain JSON that round-trips, so dataclass instances become dicts.
    """
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return _jsonable(dataclasses.asdict(obj))
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


def _provenance():
    """Provenance for the bundle: role core, no skill dispatch in this
    role yet (core ran standalone), same honesty boundary as the report."""
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/flight_mechanics_core.py",
            "functions": ["analyze_vehicle", "build_report",
                          "check_report", "render_report_markdown"],
            "version": "0.1.0",
        },
        "skills": [],
        "cross_checked": False,
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


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
        if args.bundle:
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG, "Performance and S&C Analysis Report",
                _jsonable(model), gates, _provenance())
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
    p = argparse.ArgumentParser(
        description="Flight Mechanics Engineer role: performance + S&C "
                    "analysis report")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="",
                   help="output file (default: stdout)")
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="Performance + S&C report markdown to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
