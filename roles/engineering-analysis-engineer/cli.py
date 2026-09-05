#!/usr/bin/env python3
"""cli.py - run the Engineering Analysis and Data Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--altitude 3000] [--pressure 70050]
                       [--pressure-unc 35] [--temperature 271]
                       [--temperature-unc 1.2] [--bundle]
                       # build the Analysis Verification Memo for the example
                       # measurement chain (overrides optional)
                       # --bundle  also emit evidence/{model,gates,provenance}.json
                       #           (docs/PROTOCOL.md v1)
  python3 cli.py check --file <file.md>   # gate-check an existing memo

The role ENGINE (core/engineering_analysis_engineer_core.py) does the work
standalone; bound skills in Aero Agent Skills deepen individual stages
when present.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import engineering_analysis_engineer_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "engineering-analysis-engineer"


def cmd_build(args):
    chain = core.example_chain()
    if args.altitude is not None:
        chain.altitude_m = args.altitude
    if args.pressure is not None:
        chain.pressure_pa = args.pressure
    if args.pressure_unc is not None:
        chain.pressure_unc_pa = args.pressure_unc
    if args.temperature is not None:
        chain.temperature_k = args.temperature
    if args.temperature_unc is not None:
        chain.temperature_unc_k = args.temperature_unc
    model = core.build_memo(chain)
    md = core.render_memo_markdown(model)

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

    gates = core.check_memo(model)
    if args.out:
        with open(args.out, "w") as f:
            f.write(md)
        print(f"built Analysis Verification Memo -> {args.out}")
        print(f"density {model['density_kgm3']:.6g} +/- "
              f"{model['expanded_U']:.6g} kg/m3; "
              f"gates: all_pass={gates['all_pass']}")
        if profile:
            print(f"profile: {profile.get('customer')} / "
                  f"{profile.get('program')}")
        if args.bundle:
            prov = {
                "role": ROLE_SLUG,
                "core": {
                    "file": "core/engineering_analysis_engineer_core.py",
                    "functions": ["isa_reference_values",
                                  "combined_standard_uncertainty",
                                  "confidence_interval_mean",
                                  "rss_total", "convergence_verdict",
                                  "density_altitude_m", "margin_of_safety"],
                    "version": "0.1.0",
                },
                "skills": [],
                "cross_checked": False,
                "disclaimer": "DRAFT for human review. Not an approval "
                              "document.",
            }
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "Analysis Verification Memo", model, gates, prov)
            print("bundle: model=%s" % paths["model"])
            print("        gates=%s" % paths["gates"])
            print("        provenance=%s" % paths["provenance"])
    else:
        print(md)
    return 0 if gates["all_pass"] else 1


def cmd_check(args):
    if not os.path.exists(args.file):
        print(f"file not found: {args.file}")
        return 1
    md = open(args.file).read()
    gates = core.check_memo_markdown(md)
    for name, ok in gates.items():
        if name != "all_pass":
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print(f"RESULT: {'PASS' if gates['all_pass'] else 'FAIL'}")
    return 0 if gates["all_pass"] else 1


def main():
    p = argparse.ArgumentParser(
        description="Engineering Analysis and Data Engineer role")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="", help="output file (default: stdout)")
    b.add_argument("--altitude", type=float, default=None,
                   help="test point geometric altitude in m")
    b.add_argument("--pressure", type=float, default=None,
                   help="measured static pressure in Pa")
    b.add_argument("--pressure-unc", type=float, default=None,
                   help="static pressure 1-sigma uncertainty in Pa")
    b.add_argument("--temperature", type=float, default=None,
                   help="measured temperature in K")
    b.add_argument("--temperature-unc", type=float, default=None,
                   help="temperature 1-sigma uncertainty in K")
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json")
    b.add_argument("--profile", default="",
                   help="program profile JSON (customer tailoring, "
                        "docs/PROFILE-SCHEMA.md)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True, help="memo markdown file")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
