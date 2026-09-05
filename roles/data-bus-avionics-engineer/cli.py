#!/usr/bin/env python3
"""cli.py - run the Data Bus / Avionics Network Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--bundle] [--profile <file.json>]
                       [--no-dispatch]
    # build the Avionics Data Bus Loading and Protocol Assessment for the
    # example aircraft bus architecture
    # --bundle   also emit evidence/{model,gates,provenance}.json (PROTOCOL.md)
    # --profile  program profile JSON for customer tailoring
    #            (docs/PROFILE-SCHEMA.md) -> prepended context header
    # --no-dispatch skip dispatching bound AeroSkills data-bus logic
  python3 cli.py check --file <file.md>    # gate-check an existing assessment

The role ENGINE (core/data_bus_avionics_core.py) does the work standalone:
ARINC 429 word decode + bus loading, MIL-STD-1553 word decode + BC schedule
loading, ARINC 664 AFDX VL bandwidth checks, and the evidence gates. When
AeroSkills is present (AEROSKILLS_DEV or ~/AeroSkills), the CLI dispatches
the five bound avionics/data-bus leaf logic modules and cross-checks their
numbers against the core's — two independent implementations agreeing is
recorded in provenance.json.
"""
import argparse
import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import data_bus_avionics_core as core  # noqa: E402
import evidence  # noqa: E402

AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
SKILLS_ROOT = os.path.join(AEROSKILLS, "skills", "avionics", "data-bus")
ROLE_SLUG = "data-bus-avionics-engineer"
SKILLS_RELEASE = "v1.3.0+"

# Bound leaves and their dispatch points (leaf module names as on disk).
BOUND_LEAVES = [
    ("arinc429-protocol", "arinc429_logic.py"),
    ("arinc429-bus-loading", "arinc429_bus_loading_logic.py"),
    ("arinc664-afdx", "arinc664_afdx_logic.py"),
    ("mil-std-1553", "mil_std_1553_logic.py"),
    ("mil-std-1553-bus-loading", "mil_std_1553_bus_loading_logic.py"),
]


def _load_leaf(leaf, logic_file):
    """Import a bound leaf's *_logic.py module, or None when unavailable."""
    path = os.path.join(SKILLS_ROOT, leaf, "scripts", logic_file)
    if not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location("data_bus_leaf_" + leaf
                                                  .replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _run_crosschecks(model):
    """Cross-check the core's numbers against the five bound leaf modules.

    Each row compares the same quantity computed two independent ways:
    the core implementation and the AeroSkills leaf logic. Returns a list
    of provenance rows (empty when the skills library is absent) with
    leaf, logic_file, function, dispatched, core_value, skill_value,
    delta, agrees, and the cross-check point description.
    """
    rows = []
    a429_lines = model.get("arinc429") or []

    # 1. arinc429-protocol: word build anchor label 010/SDI1/data 1234/SSM3
    mod = _load_leaf("arinc429-protocol", "arinc429_logic.py")
    if mod is not None and hasattr(mod, "build_word"):
        try:
            core_val = core.a429_build_word(8, 1, 1234, 3)
            skill_val = mod.build_word(8, 1, 1234, 3)
            rows.append(_row("arinc429-protocol", "arinc429_logic.py",
                             "build_word", core_val, skill_val,
                             "32-bit word label 010 SDI1 data 1234 SSM3"))
        except Exception as e:  # pragma: no cover
            rows.append(_row_err("arinc429-protocol", "arinc429_logic.py",
                                 "build_word", e))

    # 2. arinc429-bus-loading: utilization of the first example TX line
    mod = _load_leaf("arinc429-bus-loading", "arinc429_bus_loading_logic.py")
    if mod is not None and a429_lines and hasattr(mod, "bus_loading_summary"):
        try:
            rates = a429_lines[0]["label_rates"]
            link = a429_lines[0]["link_rate_bps"]
            core_val = core.a429_loading_summary(rates, link)["utilization_pct"]
            skill_val = mod.bus_loading_summary(rates, link)["utilization_pct"]
            rows.append(_row("arinc429-bus-loading",
                             "arinc429_bus_loading_logic.py",
                             "bus_loading_summary", core_val, skill_val,
                             "%s utilization" % a429_lines[0]["name"]))
        except Exception as e:  # pragma: no cover
            rows.append(_row_err("arinc429-bus-loading",
                                 "arinc429_bus_loading_logic.py",
                                 "bus_loading_summary", e))

    # 3. arinc664-afdx: VL bandwidth anchor (BAG 4 ms, 1518 bytes)
    mod = _load_leaf("arinc664-afdx", "arinc664_afdx_logic.py")
    if mod is not None and hasattr(mod, "vl_bandwidth"):
        try:
            core_val = core.afdx_vl_bandwidth(4, 1518)
            skill_val = mod.vl_bandwidth(4, 1518)
            rows.append(_row("arinc664-afdx", "arinc664_afdx_logic.py",
                             "vl_bandwidth", core_val, skill_val,
                             "VL bandwidth BAG 4 ms frame 1518 bytes"))
        except Exception as e:  # pragma: no cover
            rows.append(_row_err("arinc664-afdx", "arinc664_afdx_logic.py",
                                 "vl_bandwidth", e))

    # 4. mil-std-1553: command word anchor RT5 SA12 WC16 RT-to-BC
    mod = _load_leaf("mil-std-1553", "mil_std_1553_logic.py")
    if mod is not None and hasattr(mod, "encode_command_word"):
        try:
            core_val = core.m1553_encode_command_word(5, 12, 16, 1)
            skill_val = mod.encode_command_word(5, 12, 16, 1)
            rows.append(_row("mil-std-1553", "mil_std_1553_logic.py",
                             "encode_command_word", core_val, skill_val,
                             "20-bit command word RT5 SA12 WC16 T/R 1"))
        except Exception as e:  # pragma: no cover
            rows.append(_row_err("mil-std-1553", "mil_std_1553_logic.py",
                                 "encode_command_word", e))

    # 5. mil-std-1553-bus-loading: example BC minor-frame schedule loading
    mod = _load_leaf("mil-std-1553-bus-loading",
                     "mil_std_1553_bus_loading_logic.py")
    if mod is not None and hasattr(mod, "schedule_utilization"):
        try:
            item = core.example_item()
            messages = [(k, w) for k, w in item.m1553_bus.messages]
            frame_us = item.m1553_bus.frame_us
            core_val = core.m1553_schedule_utilization(
                messages, frame_us)["utilization_pct"]
            skill_val = mod.schedule_utilization(messages, frame_us)[
                "utilization_pct"]
            rows.append(_row("mil-std-1553-bus-loading",
                             "mil_std_1553_bus_loading_logic.py",
                             "schedule_utilization", core_val, skill_val,
                             "%s minor-frame utilization" %
                             item.m1553_bus.name))
        except Exception as e:  # pragma: no cover
            rows.append(_row_err("mil-std-1553-bus-loading",
                                 "mil_std_1553_bus_loading_logic.py",
                                 "schedule_utilization", e))
    return rows


def _row(leaf, logic_file, fn, core_val, skill_val, point, tol=1e-6):
    delta = abs(float(core_val) - float(skill_val))
    return {
        "leaf": "avionics/data-bus/" + leaf,
        "skill_md": "SKILL.md",
        "logic_file": "scripts/" + logic_file,
        "function": fn,
        "dispatched": True,
        "cross_check_point": point,
        "core_value": round(float(core_val), 6),
        "skill_value": round(float(skill_val), 6),
        "delta": round(delta, 9),
        "agrees": delta <= tol,
        "tolerance": tol,
        "skills_release": SKILLS_RELEASE,
    }


def _row_err(leaf, logic_file, fn, exc):
    return {"leaf": "avionics/data-bus/" + leaf,
            "logic_file": "scripts/" + logic_file,
            "function": fn, "dispatched": True,
            "error": str(exc), "agrees": False}


def _provenance(rows):
    ok_rows = [r for r in rows if r.get("dispatched") and not r.get("error")]
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/data_bus_avionics_core.py",
            "functions": ["a429_build_word", "a429_loading_summary",
                          "afdx_vl_bandwidth", "m1553_encode_command_word",
                          "m1553_schedule_utilization"],
            "version": "0.1.0",
        },
        "skills": rows,
        "cross_checked": bool(ok_rows) and all(r.get("agrees")
                                               for r in ok_rows),
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def cmd_build(args):
    item = core.example_item()
    results = core.analyze_architecture(item)
    model = core.build_assessment(item, results)
    md = core.render_assessment_markdown(model)

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

    gates = core.check_assessment(model)

    rows = []
    if not args.no_dispatch:
        rows = _run_crosschecks(model)

    if args.out:
        with open(args.out, "w") as f:
            f.write(md if md.endswith("\n") else md + "\n")
        a429_max = max(b["summary"]["utilization_pct"]
                       for b in model["arinc429"])
        print("built Avionics Data Bus Loading and Protocol Assessment "
              "-> %s" % args.out)
        print("ARINC 429 max line utilization: %.2f%%" % a429_max)
        print("MIL-STD-1553 bus utilization: %.2f%%"
              % model["m1553"]["schedule"]["utilization_pct"])
        print("AFDX link utilization: %.2f%%"
              % model["afdx"]["utilization_pct"])
        print("gates: all_pass=%s %s" % (gates["all_pass"], gates))
        if profile:
            print("profile: %s / %s" % (profile.get("customer"),
                                        profile.get("program")))
        if args.bundle:
            prov = _provenance(rows)
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "Avionics Data Bus Loading and Protocol Assessment",
                model, gates, prov)
            print("bundle: model=%s" % paths["model"])
            print("        gates=%s" % paths["gates"])
            print("        provenance=%s" % paths["provenance"])
            if rows:
                for r in rows:
                    if r.get("dispatched") and not r.get("error"):
                        print("cross-check: %-28s core=%-12s skill=%-12s "
                              "delta=%s agrees=%s"
                              % (r["function"], r["core_value"],
                                 r["skill_value"], r["delta"], r["agrees"]))
            else:
                print("cross-check: not dispatched (no AeroSkills logic)")
    else:
        print(md)
    return 0 if gates["all_pass"] else 1


def cmd_check(args):
    if not os.path.exists(args.file):
        print(f"file not found: {args.file}")
        return 1
    md = open(args.file).read()
    gates = core.check_assessment_markdown(md)
    for name, ok in gates.items():
        if name != "all_pass":
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print(f"RESULT: {'PASS' if gates['all_pass'] else 'FAIL'}")
    return 0 if gates["all_pass"] else 1


def main():
    p = argparse.ArgumentParser(
        description="Data Bus / Avionics Network Engineer role: avionics "
                    "data bus loading + protocol assessment")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="",
                   help="output file (default: stdout)")
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json")
    b.add_argument("--profile", default="",
                   help="program profile JSON (customer tailoring, "
                        "docs/PROFILE-SCHEMA.md)")
    b.add_argument("--no-dispatch", action="store_true",
                   help="skip dispatching bound AeroSkills logic")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="assessment markdown to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
