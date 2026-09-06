#!/usr/bin/env python3
"""cli.py - run the Finite Element Analysis Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--ultimate-load <N>] \\
      [--bundle] [--profile <p.json>]
    # build the Finite Element Analysis Report for the example item
    # --bundle  also emit evidence/{model,gates,provenance}.json
              (docs/PROTOCOL.md); when the Aero Agent Skills library is
              present the bound FEM leaves are dispatched on the same
              inputs and each row records core value, skill value,
              delta and agreement
  python3 cli.py check --file <file.md>            # gate-check a report

The role ENGINE (core/fem_analysis_core.py) does the work standalone:
2D truss and frame direct-stiffness solvers, beam-column, Euler
buckling, beam vibration, 2-DOF modal, shear-center and lug analyses
that produce the Finite Element Analysis Report. No AeroSkills
checkout is required. Bound Aero Agent Skills leaves deepen each stage
when the library is present; their *_logic.py implementations are
dispatched on the same inputs and recorded in provenance.json
(delta ~ 0 = two independent implementations agree).
"""
import argparse
import importlib.util
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import fem_analysis_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "fem-analysis-engineer"
CORE_FUNCTIONS = [
    "truss_analysis", "solve_frame", "element_stiffness_local",
    "element_stiffness_global", "euler_load", "moment_amplification",
    "secant_stress", "interaction_check", "critical_buckling_load",
    "column_check", "pinned_pinned_frequency", "cantilever_frequency",
    "natural_frequencies", "resonance_check", "section_properties",
    "channel_classical_e", "shear_center_channel", "lug_analysis",
    "lug_allowable_capacity", "build_report", "check_report",
    "render_report_markdown", "dispatch_rows",
]


def _load_skill_logic(leaf, skills_root):
    """Import the leaf's *_logic.py module (stdlib) or return None.

    Returns (module, logic_file_basename) or (None, None)."""
    logic_dir = os.path.join(skills_root, "skills", leaf, "scripts")
    if not os.path.isdir(logic_dir):
        return None, None
    logic_files = sorted(f for f in os.listdir(logic_dir)
                         if f.endswith("_logic.py"))
    for lf in logic_files:
        spec = importlib.util.spec_from_file_location(
            "role_dispatch_" + leaf.replace("/", "_"),
            os.path.join(logic_dir, lf))
        if spec is None or spec.loader is None:
            continue
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception:
            continue
        return mod, lf
    return None, None


def _extract(value, path):
    """Follow a value path (list of keys/indexes/tuples) into a result."""
    for step in path:
        if isinstance(step, int):
            value = value[step]
        elif isinstance(step, tuple):
            value = value[step]
        else:
            value = value[step]
    return value


def _dispatch_rows(model, skills_root=""):
    """Dispatch each core computation against the bound leaf logic.

    Returns provenance rows: dispatched True with core/skill value,
    delta and agrees when the leaf logic is reachable, else a
    dispatched False row (the core ran standalone - still valid).
    """
    root = skills_root or os.environ.get(
        "AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
    rows = []
    for row in core.dispatch_rows(model):
        mod, logic_file = _load_skill_logic(row["leaf"], root)
        if mod is None or not hasattr(mod, row["skill_fn"]):
            rows.append({
                "leaf": row["leaf"],
                "logic_file": "n/a (standalone)",
                "function": row["skill_fn"],
                "dispatched": False,
                "reason": "skill logic unavailable (standalone build)",
            })
            continue
        try:
            skill_result = getattr(mod, row["skill_fn"])(**row["kwargs"])
            core_result = getattr(core, row["core_fn"])(**row["kwargs"])
            path = row.get("value_path", [])
            if path:
                skill_val = _extract(skill_result, path)
                core_val = _extract(core_result, path)
            else:
                skill_val = skill_result
                core_val = core_result
            if not isinstance(skill_val, (int, float)) or \
               not isinstance(core_val, (int, float)):
                raise TypeError("non-numeric cross-check value")
            delta = abs(float(core_val) - float(skill_val))
            rows.append({
                "leaf": row["leaf"],
                "logic_file": "scripts/" + (logic_file or "unknown.py"),
                "function": row["skill_fn"],
                "dispatched": True,
                "core_value": round(float(core_val), 6),
                "skill_value": round(float(skill_val), 6),
                "delta": round(delta, 9),
                "agrees": delta <= row["tolerance"],
                "tolerance": row["tolerance"],
            })
        except Exception as exc:  # noqa: BLE001 - provenance must not crash
            rows.append({
                "leaf": row["leaf"],
                "function": row["skill_fn"],
                "dispatched": False,
                "reason": "dispatch error: %s" % exc,
            })
    return rows


def _provenance(model):
    """Provenance for the bundle: role core + leaf dispatch rows."""
    rows = _dispatch_rows(model)
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/fem_analysis_core.py",
            "functions": CORE_FUNCTIONS,
            "version": "0.1.0",
        },
        "skills": rows,
        "cross_checked": any(r.get("dispatched") for r in rows),
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def _model_jsonable(model):
    """Deep-copy the model into plain JSON types (tuples -> lists)."""
    return json.loads(json.dumps(model))


def cmd_build(args):
    item = core.example_item()
    if args.ultimate_load:
        item["ultimate_load_n"] = float(args.ultimate_load)
    if args.item:
        item["item"] = args.item
    model = core.build_report(item)
    md = core.render_report_markdown(model)

    # program profile (customer tailoring): load + apply context header
    profile = None
    try:
        profile = evidence.load_profile(args.profile)
    except ValueError as exc:
        print("error: bad profile: %s" % exc)
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
    if args.out:
        with open(args.out, "w") as f:
            f.write(md)
        print("built Finite Element Analysis Report (%s) -> %s"
              % (model["item"], args.out))
        if profile:
            print("profile: %s / %s" % (profile.get("customer"),
                                        profile.get("program")))
        print("gates: all_pass=%s" % gates["all_pass"])
        if args.bundle:
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "Finite Element Analysis Report",
                _model_jsonable(model), gates, _provenance(model))
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
        description="Finite Element Analysis Engineer role")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="",
                   help="output file (default: stdout)")
    b.add_argument("--ultimate-load", default="",
                   help="override the ultimate load in N (default 36000)")
    b.add_argument("--item", default="",
                   help="override the analyzed item name")
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json")
    b.add_argument("--profile", default="",
                   help="program profile JSON (customer tailoring, "
                        "docs/PROFILE-SCHEMA.md)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="Finite Element Analysis Report markdown to "
                        "gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
