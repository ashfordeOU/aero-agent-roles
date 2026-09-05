#!/usr/bin/env python3
"""cli.py - run the DO-160G Environmental Qualification Engineer role.

Usage:
  python3 cli.py build --out <file.md>   # build the qualification report
                                          # for the example LRU
  python3 cli.py check --file <file.md>  # gate-check an existing report

The role ENGINE (core/do160_environmental_core.py) does the work
standalone; bound avionics/do160 skills in Aero Agent Skills deepen
individual stages when present.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import do160_environmental_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "do160-environmental-engineer"
DELIVERABLE = "Equipment Environmental Qualification Plan/Report"


def _provenance() -> dict:
    """Provenance for the report bundle: role core, no skill dispatch."""
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/do160_environmental_core.py",
            "functions": ["build_qualification_report",
                          "render_qualification_report_markdown",
                          "check_qualification_report"],
            "version": "0.1.0",
        },
        "skills": [],
        "cross_checked": False,
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def cmd_build(args):
    item = core.example_item()
    # allow overriding the temperature category / lightning level from CLI
    if args.temperature_category:
        item.temperature_category = args.temperature_category
    if args.lightning_level:
        item.lightning_level = args.lightning_level
    try:
        model = core.build_qualification_report(item)
    except ValueError as e:
        print(f"error: bad item facts: {e}")
        return 1
    md = core.render_qualification_report_markdown(model)

    # program profile (customer tailoring): load + apply context header
    profile = None
    try:
        profile = evidence.load_profile(args.profile)
    except ValueError as e:
        print(f"error: bad profile: {e}")
        return 1
    if profile:
        model["profile"] = {
            "customer": profile.get("customer"),
            "program": profile.get("program"),
            "basis": profile.get("basis"),
            "authority": profile.get("authority"),
            "der": profile.get("der"),
            "document_prefix": profile.get("document_prefix"),
            "revision": profile.get("revision"),
        }
        md = evidence.profile_header_block(profile) + md

    gates = core.check_qualification_report(model)
    if args.out:
        with open(args.out, "w") as f:
            f.write(md)
        cat = model["temperature_category"]
        print(f"built qualification report (category {cat}, "
              f"item {model['item']}) -> {args.out}")
        if profile:
            print(f"profile: {profile.get('customer')} / "
                  f"{profile.get('program')}")
        print(f"gates: all_pass={gates['all_pass']} {gates}")
        if args.bundle:
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG, DELIVERABLE, model, gates,
                _provenance())
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
    gates = core.check_qualification_report_markdown(
        md, args.category or "")
    for name, ok in gates.items():
        if name != "all_pass":
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print(f"RESULT: {'PASS' if gates['all_pass'] else 'FAIL'}")
    return 0 if gates["all_pass"] else 1


def main():
    p = argparse.ArgumentParser(
        description="DO-160G Environmental Qualification Engineer role")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="",
                   help="output file (default: stdout)")
    b.add_argument("--temperature-category", default="",
                   help="equipment category A1..D2 (default: auto-select "
                        "from expected extremes)")
    b.add_argument("--lightning-level", type=int, default=0,
                   help="Section 22 test level 1-5 (default: 3)")
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json")
    b.add_argument("--profile", default="",
                   help="program profile JSON (customer tailoring, "
                        "docs/PROFILE-SCHEMA.md)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="qualification report markdown to gate-check")
    c.add_argument("--category", default="",
                   help="expected temperature category (e.g. B1)")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
