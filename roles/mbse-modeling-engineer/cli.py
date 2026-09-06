#!/usr/bin/env python3
"""cli.py - run the MBSE Modeling Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--failure-condition <sev>]
                       [--bundle] [--profile <p.json>] [--no-dispatch]
    # build the System Model Architecture and MBSE Plan for the example
    # item (Cabin Pressure Control System); --failure-condition re-runs
    # the development assurance level; --bundle emits
    # evidence/{model,gates,provenance}.json
  python3 cli.py check --file <file.md>
    # gate-check an existing plan document

The role ENGINE (core/mbse_modeling_core.py) does the work standalone:
diagram-kind selection, requirement screening and traceability
coverage, block/allocation closure, N2 interface counts, state-machine
reachability, parametric constraint evaluation, and the evidence
gates. When AeroSkills is present (AEROSKILLS_DEV or ~/AeroSkills),
the CLI dispatches the bound MBSE leaf logic and cross-checks it
against the core's computation - two independent implementations
agreeing is recorded in provenance.json.
"""
import argparse
import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import mbse_modeling_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "mbse-modeling-engineer"
SKILLS_ROOT = os.environ.get("AEROSKILLS_DEV",
                             os.path.expanduser("~/AeroSkills"))
_MBSE_PREFIX = os.path.join(SKILLS_ROOT, "skills",
                            "systems-engineering-safety", "mbse")
SKILLS_RELEASE = "v1.3.0+"


def _load_leaf_fn(leaf, fn_name):
    """Import a bound mbse leaf's scripts module exposing fn_name."""
    scripts = os.path.join(_MBSE_PREFIX, leaf, "scripts")
    if not os.path.isdir(scripts):
        return None
    for f in sorted(os.listdir(scripts)):
        if not f.endswith(".py") or f.startswith("test_"):
            continue
        spec = importlib.util.spec_from_file_location(
            "mbse_" + leaf.replace("-", "_"), os.path.join(scripts, f))
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception:
            continue
        if hasattr(mod, fn_name):
            return mod
    return None


def _row(leaf, logic_file_hint, fn_name, core_value, skill_value,
         point, tolerance=1e-6):
    delta = abs(float(core_value) - float(skill_value))
    return {
        "leaf": "systems-engineering-safety/mbse/" + leaf,
        "skill_md": "SKILL.md",
        "logic_file": logic_file_hint,
        "function": fn_name,
        "dispatched": True,
        "cross_check_point": point,
        "core_value": round(float(core_value), 6),
        "skill_value": round(float(skill_value), 6),
        "delta": round(delta, 9),
        "agrees": delta <= tolerance,
        "tolerance": tolerance,
        "skills_release": SKILLS_RELEASE,
    }


def _dispatch_crosschecks(model):
    """Cross-check core numbers against the bound AeroSkills MBSE logic.

    One numeric pair per modeling check that has a leaf implementation:
    requirement shall-clause counts (requirements-modeling), the total
    N2 interface entries (n2-diagram), and the architecture decision
    weighted score (trade-study-analysis). Rows are absent when the
    skills checkout (or a leaf) is absent; the role then simply ran
    standalone.
    """
    rows = []

    def try_row(leaf, fn_name, skill_kwargs, core_value, point,
                logic_file=None):
        mod = _load_leaf_fn(leaf, fn_name)
        if mod is None or core_value is None:
            return
        try:
            skill_value = getattr(mod, fn_name)(**skill_kwargs)
            lf = logic_file or os.path.basename(mod.__file__ or leaf)
            rows.append(_row(leaf, lf, fn_name, core_value, skill_value,
                             point))
        except Exception:
            return

    # 1. requirements-modeling: shall-clause count per requirement text
    for r in model.get("requirements", []):
        try_row("requirements-modeling", "count_shall_clauses",
                {"text": r["text"]}, r["shall_clauses"],
                "requirement %s: atomicity shall-clause count"
                % r["id"])

    # 2. n2-diagram: total modeled interface entries
    n2 = model.get("n2", {})
    if n2.get("matrix"):
        try_row("n2-diagram", "total_interfaces",
                {"elements": n2["elements"], "matrix": n2["matrix"]},
                n2["total"],
                "N2 matrix: total modeled interface entries")

    # 3. trade-study-analysis: weighted score of the leading alternative
    dec = model.get("decision_record", {})
    alts = dec.get("alternatives") or []
    if alts:
        lead = alts[0]
        try_row("trade-study-analysis", "weighted_score",
                {"weights": dec["weights"], "scores": lead["scores"]},
                lead["score"],
                "concept decision record: weighted score of %s (%s)"
                % (lead["name"], lead["id"]))
    return rows


def _provenance(model, dispatch_rows):
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/mbse_modeling_core.py",
            "functions": ["sysml_diagram_for", "model_viewpoint_verdict",
                          "requirement_verifiability", "satisfy_coverage",
                          "verify_coverage", "rollup_verification_status",
                          "allocation_closure", "traceability_status",
                          "build_matrix", "interface_counts",
                          "total_interfaces", "missing_links",
                          "unreachable_states", "transition_conflicts",
                          "constraint_verdict", "weighted_score",
                          "build_plan", "render_plan_markdown",
                          "check_plan"],
            "version": "0.1.0",
        },
        "skills": dispatch_rows,
        "cross_checked": bool(dispatch_rows),
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def cmd_build(args):
    item = core.example_item()
    if args.failure_condition:
        item.failure_condition = args.failure_condition
        item.system_safety_ref = args.safety_ref or item.system_safety_ref
    model = core.build_plan(item)
    md = core.render_plan_markdown(model)

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

    gates = core.check_plan(model)
    dispatch_rows = [] if args.no_dispatch else _dispatch_crosschecks(model)
    if args.out:
        with open(args.out, "w") as f:
            f.write(md if md.endswith("\n") else md + "\n")
        print("built System Model Architecture and MBSE Plan -> %s" % args.out)
        print("item: %s | FDAL %s (from %s)"
              % (model["item"], model["development_assurance_level"],
                 model["severity_source"]))
        print("requirements: %d | satisfy %.0f%% verify %.0f%% | review %s"
              % (model["requirements_total"],
                 model["satisfy_fraction"] * 100.0,
                 model["verify_fraction"] * 100.0, model["model_review"]))
        print("gates: all_pass=%s %s" % (gates["all_pass"], gates))
        if args.bundle:
            prov = _provenance(model, dispatch_rows)
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "System Model Architecture and MBSE Plan",
                model, gates, prov)
            print("bundle: model=%s" % paths["model"])
            print("        gates=%s" % paths["gates"])
            print("        provenance=%s" % paths["provenance"])
            if dispatch_rows:
                print("cross-checks: %d pair(s) vs bound mbse leaf logic"
                      % len(dispatch_rows))
                for row in dispatch_rows:
                    print("  %s/%s delta=%.2e agrees=%s"
                          % (row["leaf"], row["function"], row["delta"],
                             row["agrees"]))
    else:
        print(md)
    return 0 if gates["all_pass"] else 1


def cmd_check(args):
    if not os.path.exists(args.file):
        print("file not found: %s" % args.file)
        return 1
    md = open(args.file).read()
    gates = core.check_plan_markdown(md)
    for name, ok in gates.items():
        if name != "all_pass":
            print("%s  %s" % ("PASS" if ok else "FAIL", name))
    print("RESULT: %s" % ("PASS" if gates["all_pass"] else "FAIL"))
    return 0 if gates["all_pass"] else 1


def main():
    p = argparse.ArgumentParser(description="MBSE Modeling Engineer role")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="",
                   help="output file (default: stdout)")
    b.add_argument("--failure-condition", default="",
                   help="catastrophic/hazardous/major/minor/... "
                        "(development assurance level input)")
    b.add_argument("--safety-ref", default="",
                   help="system safety reference (FHA/PSSA)")
    b.add_argument("--no-dispatch", action="store_true",
                   help="skip skill-logic cross-checks (standalone)")
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json")
    b.add_argument("--profile", default="",
                   help="program profile JSON (customer tailoring, "
                        "docs/PROFILE-SCHEMA.md)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="plan markdown file to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
