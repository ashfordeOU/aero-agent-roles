#!/usr/bin/env python3
"""cli.py - run the Rocket Propulsion Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--payload-kg N]
                       [--ideal-dv-ms N] [--bundle] [--no-dispatch]
                       [--profile <profile.json>]
    # build the Rocket Propulsion System Design Report for the reference
    # two-stage launch vehicle; --bundle also emits
    # evidence/{model,gates,provenance}.json (docs/PROTOCOL.md);
    # --profile applies a program profile (customer tailoring)
  python3 cli.py check --file <file.md>
    # gate-check an existing report (exit 0 = PASS)

The role ENGINE (core/rocket_propulsion_core.py) does the work
standalone: staging/sizing, gravity-loss accounting, feed-cycle
balance, chamber and nozzle design, flow separation, regenerative
cooling, injector and TVC sizing, cold-gas RCS, solid and hybrid
screening. When Aero Skills is present (AEROSKILLS_DEV or
~/AeroSkills) the CLI dispatches every bound propulsion/rocket leaf's
logic and cross-checks the core's values against the leaf's
independent implementation - agreement is recorded in
provenance.json.
"""
import argparse
import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import rocket_propulsion_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "rocket-propulsion-engineer"
ROCKET = "propulsion/rocket"
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))

# One cross-check per bound leaf: (leaf, function, kwargs). Every
# function exists under the same name in the role core AND in the
# leaf's *_logic.py, and returns a scalar (float/int).
DISPATCH = [
    ("nozzle-design", "mass_flow",
     dict(p0_pa=7.0e6, t0_k=3500.0, a_throat_m2=0.02, gamma=1.2,
          r_j_kgk=350.0)),
    ("rocket-sizing", "rocket_equation_delta_v",
     dict(isp_s=300.0, m0_kg=100000.0, mf_kg=50000.0)),
    ("rocket-staging", "structural_index",
     dict(structure_kg=10000.0, propellant_kg=90000.0)),
    ("rocket-engine-cycle", "pump_power",
     dict(mdot_prop=100.0, p_discharge=12.0e6, p_inlet=0.3e6,
          rho_prop=1140.0, eta_pump=0.7)),
    ("combustion-chamber-design", "theoretical_cstar",
     dict(chamber_temp=3670.0, molecular_weight=23.0, gamma=1.2)),
    ("solid-rocket-motor", "equilibrium_chamber_pressure",
     dict(rho_p=1800.0, a=2.0e-5, n=0.35, A_b=180.5, A_t=0.361,
          c_star=1600.0)),
    ("thrust-chamber-cooling", "bartz_hot_gas_coefficient",
     dict(chamber_pressure_pa=7.0e6, cstar_m_s=1750.0,
          throat_diameter_m=0.15, mu_gas=8.0e-5, cp_gas=2000.0,
          prandtl_gas=0.72)),
    ("cold-gas-thruster", "choked_mass_flow",
     dict(pressure=25.0e6, temperature=300.0, throat_area=7.854e-7,
          gamma=1.4, gas_const=296.8)),
    ("hybrid-rocket-motor", "regression_rate",
     dict(g_o=200.0, fuel="HTPB-N2O")),
    ("injector-design", "orifice_count",
     dict(total_mass_flow_kgs=0.4, per_orifice_mass_flow_kgs=0.1)),
    ("propellant-selection", "density_impulse",
     dict(isp_s=300.0, bulk_density_kg_m3=1000.0)),
    ("rocket-gravity-loss", "gravity_loss_pitched",
     dict(burn_time_s=190.0, mean_path_angle_deg=45.0)),
    ("rocket-nozzle-flow-separation", "separation_mach",
     dict(pc=10.0e6, p_sep=40530.0, gamma=1.2)),
    ("thrust-vector-control", "side_force",
     dict(thrust=4105.0e3, deflection_rad=0.0873)),
]


def _load_leaf(leaf):
    """Import the leaf's *_logic.py module if present, else None."""
    logic_dir = os.path.join(AEROSKILLS, "skills", ROCKET, leaf, "scripts")
    if not os.path.isdir(logic_dir):
        return None
    for f in sorted(os.listdir(logic_dir)):
        if f.endswith("_logic.py") and not f.startswith("test_"):
            spec = importlib.util.spec_from_file_location(
                "role_dispatch_" + leaf.replace("-", "_"),
                os.path.join(logic_dir, f))
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
            except Exception:
                continue
            return mod
    return None


def _dispatch_rows():
    """Cross-check the core against all 14 bound rocket leaf logic modules.

    Each row runs the SAME computation in the role core and in the bound
    Aero Skills leaf and records core_value, skill_value, delta and
    agrees. Rows report dispatched=false when the skills checkout is
    absent or a leaf has no logic file - standalone runs stay valid.
    """
    rows = []
    for leaf, fn, kwargs in DISPATCH:
        core_fn = getattr(core, fn, None)
        if core_fn is None:
            rows.append({"leaf": ROCKET + "/" + leaf, "function": fn,
                         "dispatched": False,
                         "reason": "core function missing"})
            continue
        mod = _load_leaf(leaf)
        if mod is None or not hasattr(mod, fn):
            rows.append({"leaf": ROCKET + "/" + leaf, "function": fn,
                         "dispatched": False,
                         "reason": "skill logic unavailable"})
            continue
        try:
            core_val = core_fn(**dict(kwargs))
            skill_val = getattr(mod, fn)(**dict(kwargs))
            if isinstance(core_val, bool) or isinstance(skill_val, bool):
                delta = 0.0 if bool(core_val) == bool(skill_val) else 1.0
            else:
                delta = abs(float(core_val) - float(skill_val))
            rows.append({
                "leaf": ROCKET + "/" + leaf, "function": fn,
                "logic_file": "scripts/*_logic.py", "dispatched": True,
                "core_value": round(float(core_val), 6),
                "skill_value": round(float(skill_val), 6),
                "delta": round(delta, 9),
                "agrees": delta <= 1e-6,
                "tolerance": 1e-6,
            })
        except Exception as e:
            rows.append({"leaf": ROCKET + "/" + leaf, "function": fn,
                         "dispatched": True, "error": str(e)[:150],
                         "agrees": False})
    return rows


def _provenance(dispatch_rows):
    dispatched = [r for r in dispatch_rows
                  if r.get("dispatched") and not r.get("error")]
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/rocket_propulsion_core.py",
            "functions": ["build_report", "check_report",
                          "render_report_markdown", "engine_cycle_analysis",
                          "exit_mach_from_area_ratio",
                          "optimal_equal_stage_split",
                          "chamber_cooling_summary"],
            "version": "0.1.0",
        },
        "skills": dispatch_rows,
        "cross_checked": bool(dispatched and all(r["agrees"]
                                                 for r in dispatched)),
        "disclaimer": ("DRAFT for human review. Not an approval document "
                       "and not a launch readiness decision."),
    }


def cmd_build(args):
    item = core.example_item()
    if args.payload_kg:
        item.payload_kg = float(args.payload_kg)
    if args.ideal_dv_ms:
        item.ideal_dv_budget_ms = float(args.ideal_dv_ms)
        item.booster_dv_ms = float(args.ideal_dv_ms) * 5700.0 / 9600.0
        item.upper_dv_ms = float(args.ideal_dv_ms) * 3900.0 / 9600.0
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

    dispatch_rows = []
    if not args.no_dispatch:
        dispatch_rows = _dispatch_rows()

    if args.out:
        with open(args.out, "w") as f:
            f.write(md if md.endswith("\n") else md + "\n")
        print("built Rocket Propulsion System Design Report -> %s" % args.out)
        print("liftoff mass: %.0f kg, total ideal delta-v: %.0f m/s"
              % (model["performance"]["liftoff_mass_kg"],
                 model["performance"]["total_ideal_dv_ms"]))
        print("gates: all_pass=%s %s" % (gates["all_pass"], gates))
        if profile:
            print("profile: %s / %s" % (profile.get("customer"),
                                        profile.get("program")))
        if args.bundle:
            prov = _provenance(dispatch_rows)
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "Rocket Propulsion System Design Report", model, gates, prov)
            print("bundle: model=%s" % paths["model"])
            print("        gates=%s" % paths["gates"])
            print("        provenance=%s" % paths["provenance"])
            agreed = [r for r in dispatch_rows
                      if r.get("dispatched") and not r.get("error")
                      and r.get("agrees")]
            if agreed:
                print("cross-check: %d/%d bound leaves agree"
                      % (len(agreed), len([r for r in dispatch_rows
                                           if r.get("dispatched")
                                           and not r.get("error")])))
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
        description="Rocket Propulsion Engineer role: build/check the "
                    "Rocket Propulsion System Design Report")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="",
                   help="output file (default: stdout)")
    b.add_argument("--payload-kg", default="",
                   help="payload mass in kg (default: 5000)")
    b.add_argument("--ideal-dv-ms", default="",
                   help="total ideal delta-v budget in m/s "
                        "(default: 9600)")
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
                   help="report markdown file to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
