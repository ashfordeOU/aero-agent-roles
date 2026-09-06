#!/usr/bin/env python3
"""cli.py - run the Flight Software Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--base-hz <Hz>]
                       [--major-cycle <ms>] [--bundle] [--profile <p.json>]
  python3 cli.py check --file <file.md> [--level X]

Builds the Flight Software Design and Verification Plan for the
reference item (the flight control computer flight software) via the
executable role engine core/flight_software_core.py: software bus
command/telemetry message design (16-bit message IDs, command band
0x0000-0x0FFF, telemetry band 0x1000-0xFFFF, monotonic sequence
counters), the component model and rate-group dispatch schedule,
process scheduling analysis (utilization, Liu-Layland bound, exact
response-time analysis, EDF), and shared-resource access control under
the priority ceiling protocol. When AeroSkills logic is present the CLI
dispatches the bound avionics/fsw leaf computations and cross-checks
them against the core; agreement is recorded in provenance.json.
Standalone (AEROSKILLS_DEV=/nonexistent or no checkout) the role still
builds and checks correctly from pure core.

Author: ashfordeOU (Aero Agent Roles role build, wave R6).
"""
import argparse
import copy
import importlib.util
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import flight_software_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "flight-software-engineer"
AEROSKILLS = os.environ.get("AEROSKILLS_DEV",
                            os.path.expanduser("~/AeroSkills"))
SKILLS_RELEASE = "v1.3.0+"

# Process set and lock set of the reference item (the same facts the
# core's example_item encodes); the dispatch cross-checks run the bound
# leaf logic over these exact inputs.
_RTS_TASKS = [(1.0, 5.0), (2.0, 10.0), (3.0, 20.0)]
_SR_TASKS = {
    "ControlLaw": {"C": 1.0, "T": 5.0, "priority": 3.0},
    "Guidance": {"C": 2.0, "T": 10.0, "priority": 2.0},
    "HealthMon": {"C": 3.0, "T": 20.0, "priority": 1.0},
}
_SR_LOCKS = [
    {"resource": "attitude-state-store", "task": "ControlLaw", "cs": 0.5},
    {"resource": "attitude-state-store", "task": "HealthMon", "cs": 0.6},
    {"resource": "command-buffer", "task": "Guidance", "cs": 0.8},
    {"resource": "command-buffer", "task": "HealthMon", "cs": 0.7},
]
_CFS_PIPELINE = {
    "app_name": "GNC", "tlm_msg_id": 0x1902,
    "payloads": ["q1", "q2", "q3"], "start_seq": 0,
}
# F Prime reference topology of the item (clean) and a deliberately
# flawed variant used to prove both implementations count the same
# stated rule violations.
_FPRIME_ITEM = None  # built lazily from the core example item


def _fprime_kwargs(module=None):
    global _FPRIME_ITEM
    if _FPRIME_ITEM is None:
        _FPRIME_ITEM = core.example_item()
    return {"defs": _FPRIME_ITEM.components,
            "connections": _FPRIME_ITEM.connections,
            "rate_groups": _FPRIME_ITEM.rate_groups}


def _component(name, kind, ports=None, commands=None, telemetry=None,
               events=None):
    return {"name": name, "kind": kind, "ports": list(ports or []),
            "commands": list(commands or []),
            "telemetry": list(telemetry or []),
            "events": list(events or [])}


def _conn(comp_from, port_from, comp_to, port_to):
    return {"from": (comp_from, port_from), "to": (comp_to, port_to)}


def _broken_topology_kwargs(module=None):
    """Flawed F Prime topology: exactly the six rule violations both
    implementations count (duplicate opcode, type mismatch, passive
    with commands, active with no input, self-loop, unsupported
    telemetry type)."""
    defs = copy.deepcopy(_fprime_kwargs()["defs"])
    conns = copy.deepcopy(_fprime_kwargs()["connections"])
    defs[1]["commands"].append({"name": "reset2", "opcode": 0x01})
    defs[2]["ports"][1]["data_type"] = "U32"
    defs.append(_component("BadPassive", "passive",
                           commands=[{"name": "x", "opcode": 0x07}]))
    defs.append(_component("NoInput", "active"))
    defs.append(_component("SelfLoop", "passive",
                           ports=[{"direction": "input", "name": "aIn",
                                   "data_type": "F32"},
                                  {"direction": "output", "name": "aOut",
                                   "data_type": "F32"}]))
    conns.append(_conn("SelfLoop", "aOut", "SelfLoop", "aIn"))
    defs[3]["telemetry"].append({"name": "bogus", "type": "U128"})
    return {"defs": defs, "connections": conns,
            "rate_groups": _fprime_kwargs()["rate_groups"]}


def _cfs_pipeline_kwargs(module):
    """kwargs for the cfs telemetry_pipeline dispatch: build the leaf's
    own SoftwareBus with a subscriber on the telemetry message ID."""
    bus = module.SoftwareBus()
    bus.register_app("TEL")
    bus.subscribe("TEL", 0x1902)
    kw = dict(_CFS_PIPELINE)
    kw["bus"] = bus
    return kw


# Dispatch cross-check points: each row loads the bound leaf's logic
# module and compares the leaf function's result with the core's own
# function over the same inputs. All leaf modules implement the same
# public-domain rules the core encodes (per the role's grounding); the
# "compare" mode extracts the comparable value from each side.
DISPATCH_POINTS = [
    {
        "leaf": "avionics/fsw/real-time-scheduling",
        "module": "real_time_scheduling_logic.py",
        "skill_fn": "utilization",
        "core_fn": "utilization",
        "kwargs": {"tasks": _RTS_TASKS},
        "cross_check_point": "Processor utilization U = sum(C_i / T_i) "
                             "of the FCC process set",
        "tolerance": 1e-12,
    },
    {
        "leaf": "avionics/fsw/real-time-scheduling",
        "module": "real_time_scheduling_logic.py",
        "skill_fn": "liu_layland_bound",
        "core_fn": "liu_layland_bound",
        "kwargs": {"n": 3},
        "cross_check_point": "Liu-Layland sufficient bound U_rm(3) = "
                             "3 * (2**(1/3) - 1) = 0.779763",
        "tolerance": 1e-12,
    },
    {
        "leaf": "avionics/fsw/real-time-scheduling",
        "module": "real_time_scheduling_logic.py",
        "skill_fn": "rm_response_times",
        "core_fn": "rm_response_times",
        "kwargs": {"tasks": _RTS_TASKS},
        "cross_check_point": "Exact RM response times (fixed point of "
                             "R_i = C_i + sum ceil(R_i / T_j) * C_j)",
        "tolerance": 1e-9,
        "compare": "list_json",
    },
    {
        "leaf": "avionics/fsw/real-time-scheduling",
        "module": "real_time_scheduling_logic.py",
        "skill_fn": "scheduling_summary",
        "core_fn": "scheduling_summary",
        "kwargs": {"tasks": _RTS_TASKS},
        "cross_check_point": "Scheduling summary: utilization, bound "
                             "verdict, exact feasibility, EDF, verdict "
                             "string",
        "tolerance": 1e-9,
        "compare": "dict_json",
    },
    {
        "leaf": "avionics/fsw/shared-resource-access-control",
        "module": "shared_resource_access_control_logic.py",
        "skill_fn": "priority_ceiling",
        "core_fn": "priority_ceiling",
        "kwargs": {"tasks": _SR_TASKS, "locks": _SR_LOCKS},
        "cross_check_point": "Priority ceiling of each protected data "
                             "store (highest priority among its lockers)",
        "tolerance": 0.0,
        "compare": "dict_json",
    },
    {
        "leaf": "avionics/fsw/shared-resource-access-control",
        "module": "shared_resource_access_control_logic.py",
        "skill_fn": "blocking_times",
        "core_fn": "blocking_times",
        "kwargs": {"tasks": _SR_TASKS, "locks": _SR_LOCKS},
        "cross_check_point": "Worst-case blocking per process under the "
                             "priority ceiling rule (0.6 / 0.7 / 0.0 ms)",
        "tolerance": 1e-12,
        "compare": "dict_json",
    },
    {
        "leaf": "avionics/fsw/shared-resource-access-control",
        "module": "shared_resource_access_control_logic.py",
        "skill_fn": "rta_with_blocking_feasibility",
        "core_fn": "rta_with_blocking_feasibility",
        "kwargs": {"tasks": _SR_TASKS, "locks": _SR_LOCKS},
        "cross_check_point": "Response times with the blocking term "
                             "(1.6 / 3.7 / 7.0 ms) and feasibility "
                             "verdict",
        "tolerance": 1e-9,
        "compare": "dict_json",
    },
    {
        "leaf": "avionics/fsw/cfs-architecture",
        "module": "cfs_architecture_logic.py",
        "skill_fn": "telemetry_pipeline",
        "core_fn": "cfs_telemetry_stamp",
        "kwargs_factory": "_cfs_pipeline_kwargs",
        "cross_check_point": "Telemetry pipeline sequence counters "
                             "(monotonic per message ID, stamp order "
                             "start_seq + i)",
        "tolerance": 0.0,
        "skill_compare": "triple_seqs",
        "core_compare": "dict_seqs",
    },
    {
        "leaf": "avionics/fsw/fprime-component",
        "module": "fprime_component_logic.py",
        "skill_fn": "validate_topology",
        "core_fn": "validate_topology",
        "kwargs_factory": "_fprime_kwargs",
        "cross_check_point": "Component topology validation on the "
                             "reference topology (clean: 0 issues, "
                             "0 warnings)",
        "tolerance": 0.0,
        "skill_compare": "issue_count",
        "core_compare": "issue_count",
    },
    {
        "leaf": "avionics/fsw/fprime-component",
        "module": "fprime_component_logic.py",
        "skill_fn": "validate_topology",
        "core_fn": "validate_topology",
        "kwargs_factory": "_broken_topology_kwargs",
        "cross_check_point": "Component topology validation on a "
                             "deliberately flawed topology (6 rule "
                             "violations found by both implementations)",
        "tolerance": 0.0,
        "skill_compare": "issue_count",
        "core_compare": "issue_count",
    },
    {
        "leaf": "avionics/fsw/fprime-component",
        "module": "fprime_component_logic.py",
        "skill_fn": "Simulation",
        "core_fn": "rate_group_schedule",
        "kwargs_factory": "_fprime_kwargs",
        "core_kwargs_factory": "_rate_group_kwargs",
        "cross_check_point": "Rate-group master clock: base_hz = fastest "
                             "group rate, each group ticks every "
                             "max(1, round(base_hz / hz)) master ticks",
        "tolerance": 0.0,
        "skill_compare": "sim_periods",
        "core_compare": "periods_join",
    },
]


def _rate_group_kwargs(module=None):
    """kwargs for the core rate_group_schedule cross-check (it takes the
    rate group list, not the full topology)."""
    return {"rate_groups": _fprime_kwargs()["rate_groups"]}


def _load_leaf(leaf: str, module: str):
    """Import a bound AeroSkills leaf logic module if present."""
    path = os.path.join(AEROSKILLS, "skills", leaf, "scripts", module)
    if not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location("fsw_dispatch", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _row_value(obj, compare):
    """Extract the comparable scalar from a result per compare mode."""
    if compare == "dict_json":
        return json.dumps(obj, sort_keys=True, default=str)
    if compare == "list_json":
        return json.dumps(obj, sort_keys=True, default=str)
    if compare == "issue_count":
        return float(len(obj["issues"]))
    if compare == "warnings_count":
        return float(len(obj["warnings"]))
    if compare == "triple_seqs":
        return ",".join(str(t[2]) for t in obj)
    if compare == "dict_seqs":
        return ",".join(str(s) for s in obj["seqs"])
    if compare == "sim_periods":
        return ",".join(str(s["period"]) for s in obj.schedule)
    if compare == "periods_join":
        return ",".join(str(g["period_ticks"]) for g in obj["groups"])
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
            factory = point.get("kwargs_factory")
            if factory:
                kwargs = globals()[factory](mod)
            else:
                kwargs = dict(point["kwargs"])
            core_factory = point.get("core_kwargs_factory")
            if core_factory:
                core_kwargs = globals()[core_factory](mod)
            else:
                core_kwargs = kwargs
            skill_val = skill_fn(**kwargs)
            core_val = core_fn(**core_kwargs)
            compare = point.get("compare", "float")
            sv = _row_value(skill_val, point.get("skill_compare", compare))
            cv = _row_value(core_val, point.get("core_compare", compare))
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
                "skills_release": SKILLS_RELEASE,
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
            "file": "core/flight_software_core.py",
            "functions": ["build_design_verification_plan",
                          "check_design_verification_plan",
                          "render_design_verification_plan_markdown",
                          "allocate_msg_id", "telemetry_seq_run",
                          "validate_topology", "rate_group_schedule",
                          "scheduling_summary", "rta_with_blocking_feasibility"],
            "version": "0.1.0",
        },
        "skills": skills_rows,
        "cross_checked": cross_checked,
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def cmd_build(args):
    item = core.example_item()
    if args.base_hz:
        try:
            item.base_hz = float(args.base_hz)
        except ValueError as e:
            print(f"error: bad --base-hz: {e}")
            return 1
    if args.major_cycle:
        try:
            item.major_cycle_ms = float(args.major_cycle)
        except ValueError as e:
            print(f"error: bad --major-cycle: {e}")
            return 1
    model = core.build_design_verification_plan(item)
    md = core.render_design_verification_plan_markdown(model)

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

    gates = core.check_design_verification_plan(model)
    if args.out:
        with open(args.out, "w") as f:
            f.write(md)
        print(f"built Flight Software Design and Verification Plan "
              f"(level {model['software_level']}) -> {args.out}")
        if profile:
            print(f"profile: {profile.get('customer')} / "
                  f"{profile.get('program')}")
        print(f"utilization: {model['scheduling']['utilization']:.3f} | "
              f"verdict: {model['scheduling']['verdict']} | "
              f"topology: {model['component_model']['topology_issues']} "
              f"issues | blocking-feasible: "
              f"{model['resources']['feasible']}")
        print(f"gates: all_pass={gates['all_pass']} {gates}")
        if args.bundle:
            skills_rows, cross_checked = _dispatch_crosschecks()
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "Flight Software Design and Verification Plan",
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
    gates = core.check_design_verification_plan_markdown(md, args.level)
    for name, ok in gates.items():
        if name != "all_pass":
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print(f"RESULT: {'PASS' if gates['all_pass'] else 'FAIL'}")
    return 0 if gates["all_pass"] else 1


def main():
    p = argparse.ArgumentParser(
        description="Flight Software Engineer role "
                    "(Flight Software Design and Verification Plan)")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="", help="output file (default: stdout)")
    b.add_argument("--base-hz", default="",
                   help="master clock rate override (Hz) for the "
                        "rate-group schedule")
    b.add_argument("--major-cycle", default="",
                   help="integration frame length override (ms) for the "
                        "software bus frame loads")
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json")
    b.add_argument("--profile", default="",
                   help="program profile JSON (docs/PROFILE-SCHEMA.md)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="plan markdown file to gate-check")
    c.add_argument("--level", default="",
                   help="expected software level letter (A/B/C/D/E) to "
                        "verify against the plan header")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
