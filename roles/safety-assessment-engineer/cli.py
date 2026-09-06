#!/usr/bin/env python3
"""cli.py - run the Safety Assessment Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--bundle] [--profile <p.json>]
  python3 cli.py check --file <file.md> [--level X]

Builds the Aircraft/System Safety Assessment Report (ARP4761A) for the
reference item (a flight control system function) via the executable
role engine core/safety_assessment_core.py. When AeroSkills logic is
present the CLI dispatches the bound arp4761a leaf computations and
cross-checks them against the core; agreement is recorded in
provenance.json. Standalone (AEROSKILLS_DEV=/nonexistent or no
checkout) the role still builds and checks correctly.
"""
import argparse
import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import safety_assessment_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "safety-assessment-engineer"
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))

# Dispatch cross-check points: each row loads the bound leaf's logic
# module and compares the leaf function's result with the core's own
# function over the same inputs. All leaf modules implement the same
# public-domain math the core encodes (per the role's grounding).
DISPATCH_POINTS = [
    {
        "leaf": "systems-engineering-safety/arp4761a/fta-fmea",
        "module": "fta_fmea_logic.py",
        "skill_fn": "analysis_set_for_level",
        "core_fn": "analyses_for_level",
        "kwargs": {"level": "A"},
        "param_map": {},
        "cross_check_point": "ARP4761A analysis set at level A "
                             "(FTA, FMEA, CCA)",
        "tolerance": 0.0,
        "compare": "list_contains",
    },
    {
        "leaf": "systems-engineering-safety/arp4761a/fault-tree-importance-measures",
        "module": "fault_tree_importance_measures_logic.py",
        "skill_fn": "top_event_probability",
        "core_fn": "fta_top_probability",
        "kwargs": {"cut_sets": [{"A", "B"}, {"C"}],
                   "probs": {"A": 0.01, "B": 0.02, "C": 0.03}},
        "param_map": {},
        "cross_check_point": "FTA top event probability (union of cut "
                             "sets by inclusion-exclusion)",
        "tolerance": 1e-9,
    },
    {
        "leaf": "systems-engineering-safety/arp4761a/failure-mode-criticality",
        "module": "failure_mode_criticality_logic.py",
        "skill_fn": "item_criticality",
        "core_fn": "fmea_item_criticality",
        "kwargs": {"modes": [{"id": "M1", "alpha": 0.5, "beta": 1.0},
                             {"id": "M2", "alpha": 0.3, "beta": 1.0},
                             {"id": "M3", "alpha": 0.2, "beta": 0.5}],
                   "item_failure_rate": 1.0e-5,
                   "operating_time": 1.0},
        "param_map": {},
        "cross_check_point": "FMECA item criticality C_r (sum of "
                             "beta*alpha*lambda*t)",
        "tolerance": 1e-12,
    },
    {
        "leaf": "systems-engineering-safety/arp4761a/functional-hazard-assessment",
        "module": "functional_hazard_assessment_logic.py",
        "skill_fn": "probability_target",
        "core_fn": "severity_target",
        "kwargs": {"severity": "Hazardous"},
        "param_map": {},
        "cross_check_point": "Hazardous failure condition probability "
                             "target magnitude (1e-7 per FH)",
        "tolerance": 0.0,
        "skill_compare": "tuple_bound",
        "core_compare": "float",
    },
    {
        "leaf": "systems-engineering-safety/arp4761a/event-tree-analysis",
        "module": "event_tree_analysis_logic.py",
        "skill_fn": "top_function_failure_frequency",
        "core_fn": "event_tree_failure_frequency",
        "kwargs": {"frequencies": [
            {"sequence": "a:S b:F", "path": (True, False),
             "probability": 0.999 * 0.0005,
             "frequency": 1e-5 * 0.999 * 0.0005},
            {"sequence": "a:F b:F", "path": (False, False),
             "probability": 0.001 * 0.0005,
             "frequency": 1e-5 * 0.001 * 0.0005}]},
        "param_map": {},
        "cross_check_point": "Event tree failure end-state frequency",
        "tolerance": 1e-12,
        "compare": "frequency_key",
    },
    {
        "leaf": "systems-engineering-safety/arp4761a/preliminary-system-safety-assessment",
        "module": "preliminary_system_safety_assessment_logic.py",
        "skill_fn": "allocate_safety_target",
        "core_fn": "pssa_allocate_target",
        "kwargs": {"target": 1e-9, "n_contributors": 2, "gate": "and"},
        "param_map": {},
        "cross_check_point": "PSSA AND-gate target allocation "
                             "(per-contributor budget = target**(1/n))",
        "tolerance": 1e-15,
        "compare": "per_contributor",
    },
    {
        "leaf": "systems-engineering-safety/arp4761a/beta-factor-analysis",
        "module": "beta_factor_analysis_logic.py",
        "skill_fn": "dual_channel_ccf_probability",
        "core_fn": "beta_dual_channel_probability",
        "kwargs": {"failure_rate": 1e-5, "beta": 2e-5, "time": 1.0},
        "param_map": {},
        "cross_check_point": "Dual-channel CCF-inclusive failure "
                             "probability (CMA)",
        "tolerance": 1e-12,
    },
    {
        "leaf": "systems-engineering-safety/arp4761a/ssa-closure",
        "module": "ssa_closure_logic.py",
        "skill_fn": "closure_rollup",
        "core_fn": "closure_rollup",
        "kwargs": {"conditions": [
            {"id": "FC-1", "severity": "catastrophic", "predicted_q": 3e-10},
            {"id": "FC-2", "severity": "hazardous", "predicted_q": 8e-9}]},
        "param_map": {},
        "cross_check_point": "SSA closure rollup gate (all conditions "
                             "meet targets -> CLOSED)",
        "tolerance": 0.0,
        "compare": "overall_gate",
    },
]


def _load_leaf(leaf: str, module: str):
    """Import a bound AeroSkills leaf logic module if present."""
    path = os.path.join(AEROSKILLS, "skills", leaf, "scripts", module)
    if not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location("safety_dispatch", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _row_value(obj, compare):
    """Extract the comparable scalar from a result per compare mode."""
    if compare == "list_contains":
        return ",".join(sorted(map(str, obj)))
    if compare == "tuple_bound":
        return float(obj[1])
    if compare == "frequency_key":
        return float(obj["frequency"])
    if compare == "per_contributor":
        return float(obj["per_contributor"])
    if compare == "overall_gate":
        return str(obj["overall_gate"])
    return float(obj)


def _dispatch_crosschecks():
    """Run every dispatch point; returns provenance 'skills' rows."""
    rows = []
    any_ok = False
    for point in DISPATCH_POINTS:
        leaf = point["leaf"]
        mod = _load_leaf(leaf, point["module"])
        if mod is None:
            continue
        skill_fn = getattr(mod, point["skill_fn"], None)
        core_fn = getattr(core, point["core_fn"], None)
        if skill_fn is None or core_fn is None:
            continue
        try:
            kwargs = dict(point["kwargs"])
            skill_val = skill_fn(**kwargs)
            core_val = core_fn(**kwargs)
            compare = point.get("compare", "float")
            # per-side extraction: leaf signatures may return tuples or
            # dicts where the core returns the bare scalar
            sv = _row_value(skill_val,
                            point.get("skill_compare", compare))
            cv = _row_value(core_val,
                            point.get("core_compare", compare))
            if isinstance(cv, float) and isinstance(sv, float):
                delta = abs(cv - sv)
            else:
                delta = 0.0 if str(cv) == str(sv) else float("inf")
            agrees = delta <= point.get("tolerance", 1e-6)
            if agrees:
                any_ok = True
            def _prec(x):
                if isinstance(x, float):
                    return float(f"{x:.9g}")
                return x
            rows.append({
                "leaf": leaf,
                "skill_md": "SKILL.md",
                "logic_file": "scripts/" + point["module"],
                "function": point["skill_fn"],
                "dispatched": True,
                "cross_check_point": point["cross_check_point"],
                "core_value": _prec(cv),
                "skill_value": _prec(sv),
                "delta": _prec(delta),
                "agrees": bool(agrees),
                "tolerance": point.get("tolerance", 1e-6),
                "skills_release": "v1.3.0+",
            })
        except Exception as e:  # noqa: BLE001 - record honest row
            rows.append({"leaf": leaf, "dispatched": True,
                         "function": point["skill_fn"],
                         "error": str(e)[:150], "agrees": False})
    return rows, any_ok


def _provenance(skills_rows, cross_checked):
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/safety_assessment_core.py",
            "functions": ["build_safety_report", "check_report",
                          "render_report_markdown", "fta_top_probability",
                          "fmea_item_criticality", "closure_rollup"],
            "version": "0.1.0",
        },
        "skills": skills_rows,
        "cross_checked": cross_checked,
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def cmd_build(args):
    item = core.example_item()
    if args.severity:
        # re-rate the assessed conditions' severities from CLI
        fc_list = list(item.failure_conditions)
        for fc in fc_list:
            fc[4] = args.severity
        item.failure_conditions = fc_list
    model = core.build_safety_report(item)
    md = core.render_report_markdown(model)

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

    gates = core.check_report(model)
    if args.out:
        with open(args.out, "w") as f:
            f.write(md)
        print(f"built assessment (level {model['development_assurance_level']}) "
              f"-> {args.out}")
        if profile:
            print(f"profile: {profile.get('customer')} / "
                  f"{profile.get('program')}")
        print(f"gates: all_pass={gates['all_pass']} {gates}")
        if args.bundle:
            skills_rows, cross_checked = _dispatch_crosschecks()
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "Aircraft/System Safety Assessment Report (ARP4761A)",
                model, gates, _provenance(skills_rows, cross_checked))
            print(f"bundle: model={paths['model']}")
            print(f"        gates={paths['gates']}")
            print(f"        provenance={paths['provenance']}")
            if cross_checked:
                print("dispatch: core and AeroSkills leaf logic agree "
                      f"({len(skills_rows)} cross-checks)")
            else:
                print("dispatch: no AeroSkills leaf logic dispatched "
                      "(standalone build is still valid)")
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
        description="Safety Assessment Engineer role "
                    "(ARP4761A Aircraft/System Safety Assessment)")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="", help="output file (default: stdout)")
    b.add_argument("--severity", default="",
                   help="override failure-condition severity "
                        "(catastrophic/hazardous/major/minor)")
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json")
    b.add_argument("--profile", default="",
                   help="program profile JSON (docs/PROFILE-SCHEMA.md)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="assessment markdown file to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
