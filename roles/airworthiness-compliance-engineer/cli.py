#!/usr/bin/env python3
"""cli.py - run the Airworthiness Compliance Engineer role.

Usage:
  python3 cli.py build --out <file.md> [--bundle]   # build the compliance matrix
  python3 cli.py check --file <file.md>             # gate-check an existing matrix
    # --bundle  also emit evidence/{model,gates,provenance}.json (PROTOCOL.md)

The role ENGINE (core/airworthiness_core.py) does the work standalone;
bound skills in Aero Agent Skills deepen individual stages when present.

Author: ashfordeOU
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import airworthiness_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "airworthiness-compliance-engineer"


def _provenance():
    """Provenance for the evidence bundle (PROTOCOL.md v1).

    This role runs its core standalone: no bound skill logic is
    dispatched, so skills is empty and cross_checked is False (the
    role is still valid, just not cross-checked against a second
    implementation).
    """
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/airworthiness_core.py",
            "functions": ["determine_applicability", "select_moc",
                          "compliance_row", "build_matrix", "check_matrix"],
        },
        "skills": [],
        "cross_checked": False,
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


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

    # program profile (customer tailoring): load + apply context header
    profile = None
    try:
        profile = evidence.load_profile(args.profile)
    except ValueError as e:
        print("error: bad profile: %s" % e)
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

    gates = core.check_matrix(model)
    if args.out:
        with open(args.out, "w") as f:
            f.write(md)
        print("built compliance matrix (basis %s, %d regs, coverage %.0f%%)"
              " -> %s"
              % (model["certification_basis"], model["row_count"],
                 model["coverage"] * 100.0, args.out))
        if profile:
            print("profile: %s / %s" % (profile.get("customer"),
                                        profile.get("program")))
        print("gates: all_pass=%s %s" % (gates["all_pass"], gates))
        if args.bundle:
            prov = _provenance()
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "airworthiness compliance matrix", model, gates, prov)
            print("bundle: model=%s" % paths["model"])
            print("        gates=%s" % paths["gates"])
            print("        provenance=%s" % paths["provenance"])
            print("cross-check: not dispatched (role core runs standalone)")
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
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json")
    b.add_argument("--profile", default="",
                   help="program profile JSON (customer tailoring, "
                        "docs/PROFILE-SCHEMA.md)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="compliance matrix markdown file to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
