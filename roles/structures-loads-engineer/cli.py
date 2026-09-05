#!/usr/bin/env python3
"""cli.py - run the Structures and Loads Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--category <normal|commuter|transport>]
                       [--weight <lb>] [--bundle] [--no-dispatch]
    # build the loads + strength report
    # --bundle      also emit evidence/{model,gates,provenance}.json (PROTOCOL.md)
    # --no-dispatch skip dispatching bound AeroSkills logic for cross-check
  python3 cli.py check --file <file.md>   # gate-check an existing report

The role ENGINE (core/structures_loads_core.py) does the work standalone:
FAR 25 gust/maneuver envelope, limit/ultimate loads, root internal loads,
margins of safety per critical component, fatigue screening with the
S-N basis and Miner sum, dynamics, and the evidence gates. When
AeroSkills is present (AEROSKILLS_DEV or ~/AeroSkills), the CLI
dispatches the bound gust-maneuver-loads leaf logic and cross-checks its
gust load factor against the core's — two independent implementations
agreeing is recorded in provenance.json.
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
import structures_loads_core as core  # noqa: E402
import evidence  # noqa: E402

AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
GUST_LEAF = os.path.join(AEROSKILLS, "skills", "structures", "loads",
                         "gust-maneuver-loads", "scripts", "gust_load_logic.py")

ROLE_SLUG = "structures-loads-engineer"


def _load_gust_logic():
    """Import the bound AeroSkills gust logic if present."""
    if not os.path.exists(GUST_LEAF):
        return None
    spec = importlib.util.spec_from_file_location("aeroskills_gust", GUST_LEAF)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _dispatch_crosscheck(item, model):
    """Run the bound skill's gust logic and compare with the core value.

    Cross-check point: VC discrete-gust load factor. The vn model stores
    speeds in ft/s EAS and per-region design gust velocities (FAR
    25.341: 66 fps VB/VC boundary, 50 fps VC, 25 fps VD). Both the core
    and the AeroSkills leaf implement the same formula:
      n = 1 + (rho0 * V_e * a * K_g * U_de) / (2 * W/S)
    Returns a provenance 'skills' row (or None when dispatch unavailable).
    """
    gust = _load_gust_logic()
    vn = model.get("vn", {})
    ws = vn.get("ws")
    cbar = vn.get("cbar_ft")
    a = vn.get("a")
    vc_fps = vn.get("vc")          # ft/s EAS
    u_de = vn.get("gust_velocities", {}).get("vc", 50.0)
    if not (gust and ws and cbar and a and vc_fps):
        return None
    try:
        core_kg = core.gust_alleviation_factor(ws, cbar, a)
        skill_kg = gust.gust_alleviation_factor(ws, cbar, a, rho=core.RHO0)
        core_n = core.gust_load_factor(vc_fps, ws, a, u_de, kg=core_kg)
        skill_n = gust.gust_load_factor(vc_fps, ws, a, u_de, kg=skill_kg)
        delta = abs(core_n - skill_n)
        return {
            "leaf": "structures/loads/gust-maneuver-loads",
            "skill_md": "SKILL.md",
            "logic_file": "scripts/gust_load_logic.py",
            "function": "gust_load_factor",
            "dispatched": True,
            "cross_check_point": "VC discrete gust, U_de=%.0f fps EAS" % u_de,
            "core_value": round(core_n, 6),
            "skill_value": round(skill_n, 6),
            "delta": round(delta, 9),
            "agrees": delta <= 1e-6,
            "tolerance": 1e-6,
            "skills_release": "v1.3.0+",
        }
    except Exception as e:
        return {"leaf": "structures/loads/gust-maneuver-loads",
                "dispatched": True, "error": str(e), "agrees": False}


def _provenance(item, model, dispatch_row):
    vn = model.get("vn", {})
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/structures_loads_core.py",
            "functions": ["gust_load_factor", "vn_diagram",
                          "margin_of_safety", "cumulative_damage"],
            "version": "0.1.0",
        },
        "skills": [dispatch_row] if dispatch_row else [],
        "cross_checked": bool(dispatch_row and dispatch_row.get("dispatched")
                              and not dispatch_row.get("error")),
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def cmd_build(args):
    item = core.example_item()
    if args.category:
        item.category = args.category
    if args.weight:
        item.resize_for_weight(float(args.weight))
    model = core.build_report(item)
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

    dispatch_row = None
    if not args.no_dispatch:
        dispatch_row = _dispatch_crosscheck(item, model)

    if args.out:
        with open(args.out, "w") as f:
            f.write(md if md.endswith("\n") else md + "\n")
        print("built loads + strength report -> %s" % args.out)
        print("design limit: %s, n_limit=%.2f, n_ult=%.2f"
              % (model["loads_condition"], model["n_limit"], model["n_ult"]))
        print("gates: all_pass=%s %s" % (gates["all_pass"], gates))
        if args.bundle:
            prov = _provenance(item, model, dispatch_row)
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "loads + strength report", model, gates, prov)
            print("bundle: model=%s" % paths["model"])
            print("        gates=%s" % paths["gates"])
            print("        provenance=%s" % paths["provenance"])
            if dispatch_row:
                print("cross-check: core=%.6f skill=%.6f delta=%.9f agrees=%s"
                      % (dispatch_row["core_value"],
                         dispatch_row["skill_value"],
                         dispatch_row["delta"], dispatch_row["agrees"]))
            else:
                print("cross-check: not dispatched (no AeroSkills logic)")
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
        description="Structures and Loads Engineer role")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="", help="output file (default: stdout)")
    b.add_argument("--category", default="",
                   help="normal/commuter/transport (default: example)")
    b.add_argument("--weight", default="",
                   help="gross weight in lb to re-size the example wing")
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json")
    b.add_argument("--no-dispatch", action="store_true",
                   help="skip dispatching bound AeroSkills logic")
    b.add_argument("--profile", default="",
                   help="program profile JSON (customer tailoring, "
                        "docs/PROFILE-SCHEMA.md)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="loads + strength report markdown to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
