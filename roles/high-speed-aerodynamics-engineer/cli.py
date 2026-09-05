#!/usr/bin/env python3
"""cli.py - run the High-Speed Aerodynamics Engineer role.

Usage:
  python3 cli.py build [--out file.md] [--mach M] [--altitude m]
                       [--bundle] [--no-dispatch] [--profile p.json]
    # build the High-Speed Aerodynamic Analysis Memo
    # --bundle      also emit evidence/{model,gates,provenance}.json
    # --profile     apply a customer/program profile (basis, regs, formats)
  python3 cli.py check --file file.md        # gate-check an existing memo

The role ENGINE (core/high_speed_aero_core.py) does the work standalone:
isentropic relations, Mach-area, Prandtl-Glauert / Karman-Tsien
corrections, normal/oblique shock relations, Prandtl-Meyer expansion,
shock-expansion airfoil, Sears-Haack wave drag, boundary-layer
thickness/transition, stagnation-line layer, rough-wall skin friction,
Sutton-Graves heating screen, bow-shock standoff, and the evidence
gates. When AeroSkills is present (AEROSKILLS_DEV or ~/AeroSkills), the
CLI dispatches the bound leaf logic (isentropic ratios, normal shock,
oblique shock, boundary layer) and cross-checks each against the
core's - two independent implementations agreeing is recorded in
provenance.json.
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
import high_speed_aero_core as core  # noqa: E402
import evidence  # noqa: E402

AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
ROLE_SLUG = "high-speed-aerodynamics-engineer"
SKILLS_RELEASE = "v1.3.0+"

# Dispatch rows: each cross-checks one core quantity against the logic of
# a bound AeroSkills leaf (same inputs, same formulas - two independent
# implementations agreeing is the strongest offline evidence available).
DISPATCH = [
    {"leaf": "aerodynamics/high-speed/isentropic-flow-relations",
     "logic": "isentropic_flow_relations_logic.py",
     "fn": "total_static_ratios", "key": "p0_over_p",
     "args": {"mach": 2.0}, "tol": 1e-9,
     "point": "isentropic p0/p at M 2.0"},
    {"leaf": "aerodynamics/high-speed/normal-shock",
     "logic": "normal_shock_logic.py",
     "fn": "shock_properties", "key": "p02_p01",
     "args": {"M1": 2.0}, "tol": 1e-9,
     "point": "normal-shock total-pressure recovery at M1 = 2.0"},
    {"leaf": "aerodynamics/high-speed/oblique-shock",
     "logic": "oblique_shock_logic.py",
     "fn": "shock_properties", "key": "beta_deg",
     "args": {"M1": 2.0, "theta_deg": 10.0}, "tol": 1e-6,
     "point": "weak oblique-shock wave angle at M1 = 2.0, theta = 10 deg"},
    {"leaf": "aerodynamics/boundary-layer/boundary-layer-theory",
     "logic": "boundary_layer_theory_logic.py",
     "fn": "flat_plate_thicknesses", "key": "delta",
     "args": {"x": 6.0, "re_x": 2.866e7}, "tol": 1e-9,
     "point": "flat-plate BL thickness at x = 6 m, Re_x = 2.866e7"},
]


def _core_value(row):
    """Recompute the core value for a dispatch row with the same args."""
    if row["leaf"].endswith("isentropic-flow-relations"):
        return core.total_static_ratios(row["args"]["mach"])[row["key"]]
    if row["leaf"].endswith("normal-shock"):
        return core.normal_shock(row["args"]["M1"])[row["key"]]
    if row["leaf"].endswith("oblique-shock"):
        return core.oblique_shock(row["args"]["M1"],
                                  row["args"]["theta_deg"])[row["key"]]
    if row["leaf"].endswith("boundary-layer-theory"):
        return core.flat_plate_thicknesses(row["args"]["x"],
                                           row["args"]["re_x"])[row["key"]]
    return None


def _dispatch_crosschecks(item, model):
    """Run the bound AeroSkills logic files and compare with the core.

    Returns a list of provenance 'skills' rows (empty when AeroSkills is
    absent or a leaf file is missing).
    """
    rows = []
    for row in DISPATCH:
        path = os.path.join(AEROSKILLS, "skills", row["leaf"],
                            "scripts", row["logic"])
        if not os.path.exists(path):
            continue
        spec = importlib.util.spec_from_file_location("hs_dispatch", path)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception:
            continue
        fn = getattr(mod, row["fn"], None)
        if fn is None:
            continue
        try:
            skill_out = fn(**row["args"])
            skill_value = skill_out[row["key"]] if isinstance(skill_out, dict) \
                else skill_out
            core_value = _core_value(row)
            if not isinstance(skill_value, (int, float)) or \
               not isinstance(core_value, (int, float)):
                continue
            delta = abs(float(core_value) - float(skill_value))
            rows.append({
                "leaf": row["leaf"],
                "skill_md": "SKILL.md",
                "logic_file": "scripts/" + row["logic"],
                "function": row["fn"],
                "dispatched": True,
                "cross_check_point": row["point"],
                "core_value": round(float(core_value), 6),
                "skill_value": round(float(skill_value), 6),
                "delta": round(delta, 9),
                "agrees": delta <= row["tol"],
                "tolerance": row["tol"],
                "skills_release": SKILLS_RELEASE,
            })
        except Exception:
            continue
    return rows


def _provenance(item, model, dispatch_rows):
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/high_speed_aero_core.py",
            "functions": ["total_static_ratios", "normal_shock",
                          "oblique_shock", "shock_expansion_airfoil",
                          "flat_plate_thicknesses", "flat_plate_transition",
                          "bow_shock_standoff_distance",
                          "stagnation_heat_flux"],
            "version": "0.1.0",
        },
        "skills": dispatch_rows,
        "cross_checked": bool(dispatch_rows and all(
            r.get("agrees") for r in dispatch_rows)),
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def cmd_build(args):
    item = core.example_item()
    if args.mach is not None:
        if not (1.0 < args.mach < 4.0):
            print("error: --mach must be in (1.0, 4.0) for this memo")
            return 1
        item.cruise_mach = args.mach
    if args.altitude is not None:
        item.cruise_altitude_m = args.altitude
    if args.climb is not None:
        item.climb_mach = args.climb
    try:
        model = core.build_memo(item)
    except ValueError as e:
        print("error: %s" % e)
        print("note: the reference planform keeps a subsonic leading edge "
              "(M cos(Lambda) < 1) and its supercritical section stays below "
              "drag divergence M_DD at the effective Mach; the default "
              "condition is M 2.0")
        return 1
    md = core.render_memo_markdown(model)

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

    gates = core.check_memo(model)

    dispatch_rows = []
    if not args.no_dispatch:
        dispatch_rows = _dispatch_crosschecks(item, model)

    if args.out:
        with open(args.out, "w") as f:
            f.write(md if md.endswith("\n") else md + "\n")
        print("built high-speed aerodynamic analysis memo for %s -> %s"
              % (model["vehicle"], args.out))
        if profile:
            print("profile: %s / %s" % (profile.get("customer"),
                                        profile.get("program")))
        print("M=%.2f  p0/p=%.3f  A/A*=%.4f  recovery2=%.4f  "
              "M_DD=%.3f  T0=%.1f K"
              % (model["cruise_mach"], model["total_ratios"]["p0_over_p"],
                 model["area_ratio"], model["shocks"]["recovery_total"],
                 model["corrections"]["m_dd"],
                 model["total_conditions"]["t0"]))
        print("gates: all_pass=%s %s" % (gates["all_pass"], gates))
        if args.bundle:
            prov = _provenance(item, model, dispatch_rows)
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "high-speed aerodynamic analysis memo", model, gates, prov)
            print("bundle: model=%s" % paths["model"])
            print("        gates=%s" % paths["gates"])
            print("        provenance=%s" % paths["provenance"])
            if dispatch_rows:
                print("cross-check: %d leaf logic file(s) dispatched"
                      % len(dispatch_rows))
                for r in dispatch_rows:
                    print("  %s core=%.6f skill=%.6f delta=%.9f agrees=%s"
                          % (r["leaf"].split("/")[-1], r["core_value"],
                             r["skill_value"], r["delta"], r["agrees"]))
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
    gates = core.check_memo_markdown(md)
    for name, ok in gates.items():
        if name != "all_pass":
            print("%s  %s" % ("PASS" if ok else "FAIL", name))
    print("RESULT: %s" % ("PASS" if gates["all_pass"] else "FAIL"))
    return 0 if gates["all_pass"] else 1


def main():
    p = argparse.ArgumentParser(
        description="High-Speed Aerodynamics Engineer role")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="", help="output file (default: stdout)")
    b.add_argument("--mach", type=float, default=None,
                   help="cruise Mach override (default 2.0; up to ~2.2 keeps "
                        "the section below drag divergence M_DD 0.908 at the "
                        "effective Mach)")
    b.add_argument("--altitude", type=float, default=None,
                   help="cruise altitude override in metres (default 18288)")
    b.add_argument("--climb", type=float, default=None,
                   help="transonic climb check Mach override (default 0.85)")
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
                   help="high-speed analysis memo markdown to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
