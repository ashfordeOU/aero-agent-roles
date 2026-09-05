#!/usr/bin/env python3
"""cli.py - run the AS9100 Quality / Internal Auditor role.

Usage:
  python3 cli.py build --out <file.md>          # build the findings report for the example audit
  python3 cli.py build --out <file.md> --bundle # + evidence/{model,gates,provenance}.json
  python3 cli.py build --out <file.md> --bundle --profile <profile.json>
                                                # + program profile (audited supplier context,
                                                #   docs/PROFILE-SCHEMA.md)
  python3 cli.py check --file <file.md>         # gate-check an existing findings report

The role ENGINE (core/as9100_core.py) does the work standalone; bound
skills in Aero Agent Skills deepen individual stages when present.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import as9100_core as core
import evidence  # noqa: E402

ROLE_SLUG = "as9100-quality-auditor"


def _provenance():
    """Provenance for the evidence bundle: role core functions used."""
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/as9100_core.py",
            "functions": ["classify_nc", "corrective_action_status",
                          "audit_sample_size", "audit_due_date",
                          "audit_findings", "check_findings"],
            "version": "0.1.0",
        },
        "skills": [],
        "cross_checked": False,
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def cmd_build(args):
    item = core.example_item()
    if args.risk_category:
        item.process_risk = args.risk_category
    if args.audit_date:
        item.audit_date = args.audit_date
    model = core.audit_findings(item)
    md = core.render_findings_markdown(model)

    # program profile (audited supplier context): load + apply context header
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

    gates = core.check_findings(model)
    if args.out:
        with open(args.out, "w") as f:
            f.write(md)
        print("built findings report for %s -> %s" % (model["supplier"],
                                                      args.out))
        if profile:
            print("profile: %s / %s" % (profile.get("customer"),
                                        profile.get("program")))
        print("counts: %s" % model["counts"])
        print("gates: all_pass=%s %s" % (gates["all_pass"], gates))
        if args.bundle:
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "AS9100 internal audit findings report", model, gates,
                _provenance())
            print("bundle: model=%s" % paths["model"])
            print("        gates=%s" % paths["gates"])
            print("        provenance=%s" % paths["provenance"])
    else:
        print(md)
    return 0 if gates["all_pass"] else 1


def cmd_check(args):
    if not os.path.exists(args.file):
        print("file not found: %s" % args.file)
        return 1
    md = open(args.file).read()
    gates = core.check_findings_markdown(md)
    for name, ok in gates.items():
        if name != "all_pass":
            print("%s  %s" % ("PASS" if ok else "FAIL", name))
    print("RESULT: %s" % ("PASS" if gates["all_pass"] else "FAIL"))
    return 0 if gates["all_pass"] else 1


def main():
    p = argparse.ArgumentParser(description="AS9100 Quality / Internal Auditor role")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="", help="output file (default: stdout)")
    b.add_argument("--risk-category", default="",
                   help="low/medium/high process risk")
    b.add_argument("--audit-date", default="", help="audit date ISO YYYY-MM-DD")
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json")
    b.add_argument("--profile", default="",
                   help="program profile JSON (audited supplier context, "
                        "docs/PROFILE-SCHEMA.md)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="findings report markdown file to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
