#!/usr/bin/env python3
"""cli.py - run the Aircraft Systems Sizing Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--bundle] [--profile <p.json>]
                       [--no-dispatch]
    # build the Aircraft System Sizing Report for the worked-example
    # 180-seat single-aisle transport
    # --bundle      also emit evidence/{model,gates,provenance}.json
    #               (docs/PROTOCOL.md)
    # --profile     program profile JSON (customer tailoring)
    # --no-dispatch skip dispatching bound AeroSkills sizing logic
  python3 cli.py check --file <file.md>   # gate-check an existing report

The role ENGINE (core/aircraft_systems_sizing_core.py) does the work
STANDALONE: every number in the report is computed by code from the real
formulas of the bound vehicle-design/sizing leaves (electrical load
analysis, air cycle machine, avionics bay cooling, oxygen, brakes,
cabin outflow/relief valves, fuel feed, fuel jettison, fuel tank
inerting, hydraulic actuation, landing gear layout, ram air turbine,
tires, window apertures). When AeroSkills is present (AEROSKILLS_DEV or
~/AeroSkills), the CLI dispatches the bound leaves' own logic functions
on the same inputs and cross-checks the core's numbers - agreement of
two independent implementations is recorded in provenance.json.
"""
import argparse
import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import aircraft_systems_sizing_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "aircraft-systems-sizing-engineer"
SKILLS_RELEASE = "v1.3.0+"


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
            mod = importlib.util.module_from_spec(spec)
            if spec is None or spec.loader is None or mod is None:
                continue
            spec.loader.exec_module(mod)
            return mod
        except Exception:
            continue
    return None


def _dispatch_row(rel_leaf, fn_name, kwargs, core_value, tolerance=1e-6,
                  label=None, result_key=None):
    """Run the leaf logic fn with the same inputs as the core, compare."""
    mod = _leaf_module(rel_leaf)
    if mod is None or not hasattr(mod, fn_name):
        return None
    if callable(core_value) and not isinstance(core_value, (int, float)):
        core_value = core_value()
    try:
        skill_value = getattr(mod, fn_name)(**kwargs)
        if result_key is not None and isinstance(skill_value, dict):
            skill_value = skill_value.get(result_key)
        if not isinstance(skill_value, (int, float)) or \
           not isinstance(core_value, (int, float)):
            return None
        delta = abs(float(core_value) - float(skill_value))
        row = {
            "leaf": rel_leaf,
            "skill_md": "SKILL.md",
            "logic_file": "scripts/%s" % os.path.basename(str(mod.__file__)),
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


def _dispatch_crosschecks(model, item):
    """Cross-check core numbers against the bound sizing leaf logic.

    Every pair runs the SAME inputs through the role core and the bound
    AeroSkills leaf (independent implementations of the same formulas)
    and records agreement/delta in the provenance 'skills' list.
    """
    s = model["systems"]
    rows = []

    def add(leaf, fn, kwargs, core_value, label, tol=1e-6, result_key=None):
        row = _dispatch_row(leaf, fn, kwargs, core_value, tolerance=tol,
                            label=label, result_key=result_key)
        if row:
            rows.append(row)

    # 1. electrical: continuous + essential load rollup
    add("vehicle-design/sizing/aircraft-electrical-load-analysis",
        "continuous_load",
        {"consumers": dict(item.consumers)},
        lambda: s["electrical"]["continuous_kva"], "continuous load rollup",
        result_key="continuous_kva")
    add("vehicle-design/sizing/aircraft-electrical-load-analysis",
        "essential_load",
        {"consumers": dict(item.consumers),
         "essential_names": list(item.essential_names)},
        lambda: s["electrical"]["essential_kva"], "essential load at full power",
        result_key="essential_kva")
    # 2. air cycle machine: compressor exit + required bleed flow
    acm = s["air_cycle_machine"]
    add("vehicle-design/sizing/air-cycle-machine-sizing",
        "compressor_exit",
        {"bleed_p1": item.pack_bleed_p1_pa, "bleed_t1": item.pack_bleed_t1_k,
         "pr_c": item.pack_pr_c, "eta_c": item.pack_eta_c},
        lambda: acm["t2_k"], "compressor exit T2", result_key="t2")
    add("vehicle-design/sizing/air-cycle-machine-sizing",
        "required_bleed_flow",
        {"q_load": acm["heat_load_w"], "t4_effective": acm["t4_k"],
         "target_t": item.pack_target_t_k},
        lambda: acm["required_bleed_flow_kg_s"],
        "bleed flow for the pack cooling load")
    # 3. avionics bay cooling: mass flow + LRU case temperature
    av = s["avionics_bay_cooling"]
    add("vehicle-design/sizing/avionics-bay-cooling-sizing",
        "cooling_mass_flow",
        {"total_heat_w": av["bay_heat_load_w"],
         "supply_temp_c": av["supply_temp_c"],
         "exhaust_limit_c": av["exhaust_limit_c"]},
        lambda: av["mass_flow_kg_s"], "bay cooling airflow",
        result_key="mass_flow_kg_s")
    add("vehicle-design/sizing/avionics-bay-cooling-sizing",
        "lru_case_temperature",
        {"power_w": item.lru_dissipations_w[0], "conductance_w_k": 12.0,
         "inlet_air_temp_c": av["supply_temp_c"]},
        lambda: av["case_temps_c"]["0"], "LRU 0 case temperature",
        result_key="case_temp_c")
    # 4. oxygen: passenger demand + crew bottle volume
    ox = s["oxygen"]
    add("vehicle-design/sizing/aircraft-oxygen-system-sizing",
        "passenger_demand",
        {"n_passengers": item.n_passengers},
        lambda: ox["passenger_demand_sl"], "pax oxygen demand",
        result_key="volume_sl")
    add("vehicle-design/sizing/aircraft-oxygen-system-sizing",
        "bottle_volume",
        {"mass_kg": ox["crew_mass_kg"],
         "service_pressure_psi": item.oxygen_service_pressure_psi},
        lambda: ox["bottle_volume_l"], "crew bottle volume",
        result_key="volume_l")
    # 5. brakes: RTO energy + governing per-brake energy
    br = s["brakes"]
    add("vehicle-design/sizing/brake-energy-sizing",
        "rto_energy_J",
        {"mtow_kg": item.mtow_kg, "v1_m_s": item.v1_m_s},
        lambda: br["E_rto_J"], "RTO kinetic energy at V1")
    add("vehicle-design/sizing/brake-energy-sizing",
        "per_brake_energy_J",
        {"total_energy_J": br["E_rto_J"],
         "n_braked_wheels": item.n_braked_wheels},
        lambda: br["per_brake_rto_J"], "RTO energy per braked wheel")
    # 6. valves: outflow valve area
    va = s["valves"]
    add("vehicle-design/sizing/cabin-outflow-valve-sizing",
        "valve_area",
        {"m_dot_kg_s": item.outflow_m_pack_kg_s,
         "p_cab_pa": item.outflow_p_cab_pa},
        lambda: va["outflow_area_m2"], "outflow valve effective area",
        result_key="area_m2")
    # 7. fuel feed: NPSHa
    ff = s["fuel_feed"]
    add("vehicle-design/sizing/fuel-feed-system-sizing",
        "npsh_available",
        {"source_pressure_pa": item.feed_source_pressure_pa,
         "static_head_pa": ff["static_head_pa"],
         "line_loss_pa": ff["total_line_loss_pa"],
         "vapor_pressure_pa": item.fuel_vapor_pressure_pa,
         "density_kg_m3": item.fuel_density_kg_m3},
        lambda: ff["npsh_available_m"], "NPSHa at the boost pump inlet")
    # 8. jettison: dumpable mass + required rate
    jt = s["fuel_jettison"]
    add("vehicle-design/sizing/fuel-jettison-sizing",
        "dumpable_fuel_mass",
        {"mtow_kg": item.mtow_kg, "mlw_kg": item.mlw_kg},
        lambda: jt["dumpable_mass_kg"], "dumpable fuel to MLW")
    add("vehicle-design/sizing/fuel-jettison-sizing",
        "required_jettison_rate",
        {"mtow_kg": item.mtow_kg, "mlw_kg": item.mlw_kg},
        lambda: jt["required_rate_kg_s"], "15-min average jettison rate")
    # 9. inerting: NEA flow required
    in_ = s["fuel_tank_inerting"]
    add("vehicle-design/sizing/fuel-tank-inerting-sizing",
        "nea_flow_required",
        {"ullage_m3": item.inerting_ullage_m3,
         "target_o2_fraction": item.inerting_target_o2,
         "time_s": item.inerting_time_s},
        lambda: in_["flow_m3_s"], "NEA flow for the ullage washout",
        result_key="flow_m3_s")
    # 10. hydraulic actuator: piston area + rod buckling
    hy = s["hydraulic_actuator"]
    add("vehicle-design/sizing/hydraulic-actuator-sizing",
        "piston_area",
        {"load_N": item.actuator_load_N,
         "pressure_Pa": item.system_pressure_pa},
        lambda: hy["piston_area"], "required piston area")
    add("vehicle-design/sizing/hydraulic-actuator-sizing",
        "rod_buckling_diameter",
        {"load_N": item.actuator_load_N,
         "rod_length_m": item.actuator_rod_length_m},
        lambda: hy["rod_buckling_mm"] / 1000.0, "rod Euler buckling diameter")
    # 11. landing gear layout: tipback + nose load fractions
    lg = s["landing_gear_layout"]
    add("vehicle-design/sizing/landing-gear-layout",
        "tipback_angle",
        {"h_cg": item.h_cg_m, "x_mg": item.x_mg_m,
         "x_cg_aft": item.x_cg_aft_m},
        lambda: lg["tipback_angle_deg"], "tipback angle at the aft CG")
    add("vehicle-design/sizing/landing-gear-layout",
        "nose_gear_static_load_fraction",
        {"x_cg": item.x_cg_aft_m, "x_mg": item.x_mg_m, "x_ng": item.x_ng_m},
        lambda: lg["nose_load_fraction_aft"],
        "nose gear fraction at the aft CG limit")
    # 12. RAT: swept area
    rt = s["ram_air_turbine"]
    add("vehicle-design/sizing/ram-air-turbine-sizing",
        "rat_swept_area",
        {"p_req_w": item.rat_p_req_w, "v_m_s": item.rat_v_m_s},
        lambda: rt["area_m2"], "RAT swept area at the emergency condition")
    # 13. tires: static load per tire + diameter fit
    ti = s["tires"]
    add("vehicle-design/sizing/tire-sizing",
        "static_load_per_tire",
        {"mtow_kg": item.mtow_kg, "gear_fraction": item.main_gear_fraction,
         "n_tires": item.n_tires_per_main_gear * 2},
        lambda: ti["load_per_tire_kg"], "main gear static load per tire")
    add("vehicle-design/sizing/tire-sizing",
        "tire_diameter_inches",
        {"load_lb": ti["load_per_tire_lb"]},
        lambda: ti["diameter_in"], "tire diameter class-I fit")
    # 14. windows: pane thickness
    wi = s["windows"]
    add("vehicle-design/sizing/window-aperture-sizing",
        "pane_thickness",
        {"pressure_pa": wi["design_differential_pa"],
         "radius_m": item.window_radius_m,
         "allowable_stress_pa": item.window_allowable_stress_pa},
        lambda: wi["pane_thickness_required_mm"] / 1000.0,
        "required window pane thickness")
    return rows


def _provenance(model, dispatch_rows):
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/aircraft_systems_sizing_core.py",
            "functions": ["build_report", "render_report_markdown",
                          "check_report", "continuous_load",
                          "required_bleed_flow", "brake_energy_analyze",
                          "actuator_review", "jettison_summary",
                          "design_pressure_differential", "check_report_markdown"],
            "version": "0.1.0",
        },
        "skills": dispatch_rows,
        "cross_checked": bool(dispatch_rows),
        "skills_release": SKILLS_RELEASE,
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def cmd_build(args):
    item = core.example_item()
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
    dispatch_rows = [] if args.no_dispatch else _dispatch_crosschecks(model,
                                                                       item)
    prov = _provenance(model, dispatch_rows)

    if args.out:
        with open(args.out, "w") as f:
            f.write(md if md.endswith("\n") else md + "\n")
        v = model["verdicts"]
        print("built Aircraft System Sizing Report for %s -> %s"
              % (model["item"], args.out))
        print("electrical continuous %.1f kVA; ACM bleed %.3f kg/s; "
              "brake governing %s" % (model["systems"]["electrical"]
                                       ["continuous_kva"],
                                      model["systems"]["air_cycle_machine"]
                                      ["required_bleed_flow_kg_s"],
                                      model["systems"]["brakes"]
                                      ["governing_case"]))
        pass_count = sum(1 for x in v.values() if x == "PASS")
        print("verdicts: %d/14 PASS" % pass_count)
        dispatched = [x for x in dispatch_rows if x.get("dispatched")]
        print("cross-checks: %d dispatch row(s); all agree=%s"
              % (len(dispatched),
                 all(x.get("agrees", False) for x in dispatched)))
        print("gates: all_pass=%s %s" % (gates["all_pass"], gates))
        if args.bundle:
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "Aircraft System Sizing Report", model, gates, prov)
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
        description="Aircraft Systems Sizing Engineer role: aircraft system "
                    "sizing report")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="",
                   help="output file (default: stdout)")
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json")
    b.add_argument("--no-dispatch", action="store_true",
                   help="skip dispatching bound AeroSkills sizing logic")
    b.add_argument("--profile", default="",
                   help="program profile JSON (customer tailoring, "
                        "docs/PROFILE-SCHEMA.md)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="report markdown to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
