#!/usr/bin/env python3
"""cli.py - run the Systems Integration Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--bundle] [--profile <file.json>]
      [--severity <sev>] [--no-dispatch]
    # build the System Development Assurance and Integration Plan (ARP4754A)
    # for the worked-example flight control system
    # --bundle   also emit evidence/{model,gates,provenance}.json (PROTOCOL.md)
    # --profile  program profile JSON for customer tailoring
    #            (docs/PROFILE-SCHEMA.md) -> prepended context header
    # --severity re-rate every function failure condition's severity (A..E
    #            demo variants, e.g. --severity Minor -> DAL D system)
    # --no-dispatch  skip dispatching bound AeroSkills logic for cross-check
  python3 cli.py check --file <file.md>    # gate-check an existing plan

The role ENGINE (core/systems_integration_core.py) does the work standalone
(ARP4754A development assurance rules -> real numbers); bound Aero Agent
Skills leaves under systems-engineering-safety/arp4754a/ cross-check the
core's assurance, allocation, traceability, validation and verification
numbers when the checkout is present (provenance records
core_value/skill_value/delta/agrees per point).
"""
import argparse
import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import systems_integration_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "systems-integration-engineer"
SKILLS_RELEASE = "v1.3.0+"
ARP = "systems-engineering-safety/arp4754a"


def _leaf_module(rel_leaf):
    """Import the bound AeroSkills leaf's *_logic.py module, or None."""
    root = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
    logic_dir = os.path.join(root, "skills", rel_leaf, "scripts")
    if not os.path.isdir(logic_dir):
        return None
    logic_files = sorted(f for f in os.listdir(logic_dir)
                         if f.endswith("_logic.py"))
    for lf in logic_files:
        try:
            spec = importlib.util.spec_from_file_location(
                "role_dispatch_leaf", os.path.join(logic_dir, lf))
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        except Exception:
            continue
    return None


def _dispatch_row(rel_leaf, fn_name, kwargs, core_fn, tolerance=1e-6,
                  label=None, result_index=None, result_key=None):
    """Run the leaf logic fn with the same inputs as the core, compare.

    core_fn is a zero-arg callable resolving the core's value lazily.
    result_index/result_key pull a numeric element out of a tuple/dict
    return (the allocation coverage tuple, the validation closure tuple,
    the assurance_assignment dict). Returns a provenance 'skills' row (or
    None when dispatch is unavailable).
    """
    mod = _leaf_module(rel_leaf)
    if mod is None or not hasattr(mod, fn_name):
        return None
    try:
        skill_value = getattr(mod, fn_name)(**kwargs)
        core_value = core_fn()
        if result_index is not None and isinstance(skill_value, (tuple, list)):
            skill_value = skill_value[result_index]
        if result_key is not None and isinstance(skill_value, dict):
            skill_value = skill_value.get(result_key)
        if not isinstance(skill_value, (int, float)) or \
           not isinstance(core_value, (int, float)):
            return None
        delta = abs(float(core_value) - float(skill_value))
        row = {
            "leaf": rel_leaf,
            "skill_md": "SKILL.md",
            "logic_file": "scripts/%s" % os.path.basename(
                str(mod.__file__)),
            "function": fn_name,
            "dispatched": True,
            "core_value": round(float(core_value), 6),
            "skill_value": round(float(skill_value), 6),
            "delta": round(delta, 9),
            "agrees": delta <= tolerance,
            "tolerance": tolerance,
            "skills_release": SKILLS_RELEASE,
        }
        if label:
            row["cross_check_point"] = label
        return row
    except Exception:
        return None


def _dispatch_crosschecks(item, model):
    """Cross-check the core computations against the bound ARP4754A leaves.

    Every point runs the SAME inputs through the role core and the bound
    AeroSkills leaf logic (independent implementations of the same public
    development-assurance rules) and records agreement in provenance.
    """
    rows = []
    fdals = {f["function"]: f["fdal"] for f in model["functions"]}

    def add(leaf, fn, kwargs, core_fn, label, tol=1e-6,
            result_index=None, result_key=None):
        row = _dispatch_row(leaf, fn, kwargs, core_fn, tolerance=tol,
                            label=label, result_index=result_index,
                            result_key=result_key)
        if row:
            rows.append(row)

    # 1. FDAL from severity (development-assurance-levels leaf): the pitch
    #    function's most severe failure condition is Catastrophic -> FDAL A.
    pitch_sev = max(item.functions[0]["failure_conditions"],
                    key=lambda fc: core.severity_rank(fc["severity"]))[
                        "severity"]
    add("%s/development-assurance-levels" % ARP, "dal_from_severity",
        {"severity": pitch_sev},
        lambda: core.dal_index(fdals["Pitch control"]),
        "pitch-control FDAL from Catastrophic severity",
        result_index=None)
    # numeric agreement on the DAL index (A=5) of that FDAL
    add("%s/development-assurance-levels" % ARP, "dal_index",
        {"dal": fdals["Pitch control"]},
        lambda: core.dal_index(fdals["Pitch control"]),
        "DAL index A=5 for pitch-control FDAL")

    # 2. Item IDAL = highest FDAL among implemented functions (systems-
    #    planning leaf). PFCC implements pitch (A) + roll (A) -> IDAL A.
    pfcc_fdals = [fdals[n] for n in
                  ["Pitch control", "Roll control"]]
    add("%s/systems-planning" % ARP, "idal_for_item",
        {"function_fdals": pfcc_fdals},
        lambda: core.dal_index(model["items"][0]["idal"]),
        "PFCC IDAL = max(FDAL A, FDAL A) -> A (index 5)")

    # 3. Requirements allocation coverage (requirements-allocation leaf).
    add("%s/requirements-allocation" % ARP, "coverage",
        {"register": dict(item.allocation_register),
         "requirement_ids": list(item.requirement_ids)},
        lambda: model["allocation"]["coverage"],
        "allocation coverage over the 60-requirement set",
        result_index=2)

    # 4. Trace verified-closure ratio (requirements-traceability leaf).
    add("%s/requirements-traceability" % ARP, "closure_ratio",
        {"links": list(item.trace_links)},
        lambda: model["traceability"]["verified_ratio"],
        "trace verified-closure ratio (68 links)")

    # 5. Validation closure score (validation leaf): (ready, score) tuple.
    add("%s/validation" % ARP, "validation_closure",
        {"requirements": list(item.validation_entries)},
        lambda: model["validation"]["score"],
        "validation closure score over the requirement set",
        result_index=1)

    # 6. Verification method acceptability (verification-planning leaf):
    #    demonstration is NOT acceptable at level A (test/analysis only).
    #    Both implementations return a 0/1 verdict compared as a number.
    add("%s/verification-planning" % ARP, "method_allowed",
        {"method": "demonstration", "dal": model["max_dal"]},
        lambda: float(core.method_allowed("demonstration",
                                          model["max_dal"])),
        "demonstration rejected at level A (0/1 verdict)")
    return rows


def _provenance(dispatch_rows):
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/systems_integration_core.py",
            "functions": ["fdal_for_function", "item_idal",
                          "dal_propagation_ok", "allocation_coverage",
                          "trace_closure_status", "validation_closure_score",
                          "method_allowed", "stage_checks",
                          "build_report", "check_report"],
            "version": "0.1.0",
        },
        "skills": dispatch_rows,
        "cross_checked": bool(dispatch_rows),
        "skills_release": SKILLS_RELEASE,
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def cmd_build(args):
    item = core.example_item()
    if args.severity:
        sev = args.severity
        core._check_severity(sev)
        for fn in item.functions:
            for fc in fn["failure_conditions"]:
                fc["severity"] = sev
    model = core.build_report(item)
    md = core.render_report_markdown(model)

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

    gates = core.check_report(model)
    dispatch_rows = [] if args.no_dispatch else _dispatch_crosschecks(
        item, model)
    prov = _provenance(dispatch_rows)

    if args.out:
        with open(args.out, "w") as f:
            f.write(md if md.endswith("\n") else md + "\n")
        print("built System Development Assurance and Integration Plan "
              "(ARP4754A) for %s (max DAL %s) -> %s"
              % (model["item"], model["max_dal"], args.out))
        print("allocation coverage: %.1f%%; trace: %s (%.1f%% verified); "
              "validation closure: %.2f; objectives: %.1f%%"
              % (model["allocation"]["coverage"] * 100.0,
                 model["traceability"]["status"],
                 model["traceability"]["verified_ratio"] * 100.0,
                 model["validation"]["score"],
                 model["objectives"]["coverage"] * 100.0))
        if profile:
            print("profile: %s / %s" % (profile.get("customer"),
                                        profile.get("program")))
        dispatched = [x for x in dispatch_rows if x.get("dispatched")]
        print("cross-checks: %d dispatch row(s); all agree=%s"
              % (len(dispatched),
                 all(x.get("agrees", False) for x in dispatched)))
        print("gates: all_pass=%s %s" % (gates["all_pass"], gates))
        if args.bundle:
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "System Development Assurance and Integration Plan "
                "(ARP4754A)", model, gates, prov)
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
    gates = core.check_report_markdown(md)
    for name, ok in gates.items():
        if name != "all_pass":
            print("%s  %s" % ("PASS" if ok else "FAIL", name))
    print("RESULT: %s" % ("PASS" if gates["all_pass"] else "FAIL"))
    return 0 if gates["all_pass"] else 1


def main():
    p = argparse.ArgumentParser(
        description="Systems Integration Engineer role: System Development "
                    "Assurance and Integration Plan (ARP4754A)")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="",
                   help="output file (default: stdout)")
    b.add_argument("--severity", default="",
                   help="re-rate all failure conditions "
                        "(Catastrophic/Hazardous/Major/Minor/...)")
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json")
    b.add_argument("--profile", default="",
                   help="program profile JSON (customer tailoring, "
                        "docs/PROFILE-SCHEMA.md)")
    b.add_argument("--no-dispatch", action="store_true",
                   help="skip AeroSkills logic dispatch cross-checks")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="plan markdown to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
