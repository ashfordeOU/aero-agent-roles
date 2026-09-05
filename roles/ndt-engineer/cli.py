#!/usr/bin/env python3
"""cli.py - run the NDT Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--bundle] [--profile <p.json>]
                       [--leak-limit-sccs <limit>] [--no-dispatch]
    # build the Nondestructive Test Plan and Method Selection Report for
    # the example item (critical cast aluminum gearbox housing);
    # --leak-limit-sccs re-runs the leak disposition against another
    # allowable; --bundle emits evidence/{model,gates,provenance}.json
  python3 cli.py check --file <file.md>
    # gate-check an existing report document

The role ENGINE (core/ndt_core.py) does the work standalone: method
selection per defect/material class, inspection parameters per method,
personnel qualification, acceptance framing, and the evidence gates.
When AeroSkills is present (AEROSKILLS_DEV or ~/AeroSkills), the CLI
dispatches the bound ndt leaf logic and cross-checks it against the
core's computation - two independent implementations agreeing is
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
import ndt_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "ndt-engineer"
SKILLS_ROOT = os.environ.get("AEROSKILLS_DEV",
                             os.path.expanduser("~/AeroSkills"))
_NDT_PREFIX = os.path.join(SKILLS_ROOT, "skills", "manufacturing-quality",
                           "ndt")
SKILLS_RELEASE = "v1.3.0+"


def _load_leaf_fn(leaf, fn_name):
    """Import a bound ndt leaf's scripts module exposing fn_name."""
    scripts = os.path.join(_NDT_PREFIX, leaf, "scripts")
    if not os.path.isdir(scripts):
        return None
    for f in sorted(os.listdir(scripts)):
        if not f.endswith(".py") or f.startswith("test_"):
            continue
        spec = importlib.util.spec_from_file_location(
            "ndt_" + leaf.replace("-", "_"), os.path.join(scripts, f))
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception:
            continue
        if hasattr(mod, fn_name):
            return mod
    return None


def _row(leaf, logic_file_hint, fn_name, skill_mod, core_value, skill_value,
         point, tolerance=1e-6):
    delta = abs(float(core_value) - float(skill_value))
    return {
        "leaf": "manufacturing-quality/ndt/" + leaf,
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
    """Cross-check core numbers against the bound AeroSkills ndt logic.

    One numeric pair per method family present in the model:
    ET frequency selection, PT capillary pressure, RT exposure + IQI,
    CT projection/tube energy/porosity/void diameter, leak decay rate
    and gauge time. Rows are absent when the skills checkout (or a
    leaf) is absent; the role then simply ran standalone.
    """
    rows = []
    cards = model.get("parameter_cards", {})

    def try_row(leaf, fn_name, skill_kwargs, core_value, point,
                logic_file=None):
        mod = _load_leaf_fn(leaf, fn_name)
        if mod is None or core_value is None:
            return
        try:
            skill_value = getattr(mod, fn_name)(**skill_kwargs)
            lf = logic_file or os.path.basename(mod.__file__ or leaf)
            rows.append(_row(leaf, lf, fn_name, mod, core_value,
                             skill_value, point))
        except Exception:
            return

    if "eddy-current-surface" in cards:
        c = cards["eddy-current-surface"]
        try_row("eddy-current-inspection", "select_frequency_for_flaw",
                {"flaw_depth": c["inputs"]["flaw_depth_m"],
                 "conductivity": core.conductivity_from_iacs(c["percent_iacs"]),
                 "penetration_factor": c["inputs"]["penetration_factor"]},
                c["frequency_hz"],
                "ET surface zone: frequency for a %.3g m flaw at factor %.1f"
                % (c["flaw_depth_m"], c["penetration_factor"]))
    if "eddy-current-subsurface" in cards:
        c = cards["eddy-current-subsurface"]
        try_row("eddy-current-inspection", "select_frequency_for_flaw",
                {"flaw_depth": c["inputs"]["flaw_depth_m"],
                 "conductivity": core.conductivity_from_iacs(c["percent_iacs"]),
                 "penetration_factor": c["inputs"]["penetration_factor"]},
                c["frequency_hz"],
                "ET subsurface zone: frequency for a %.3g m flaw at factor "
                "%.1f" % (c["flaw_depth_m"], c["penetration_factor"]))
    if "liquid-penetrant" in cards:
        c = cards["liquid-penetrant"]
        try_row("liquid-penetrant-inspection", "capillary_pressure",
                {"surface_tension": c["surface_tension_nm"],
                 "contact_angle_deg": c["contact_angle_deg"],
                 "radius": c["effective_capillary_radius_m"]},
                c["capillary_pressure_pa"],
                "PT: capillary pressure across the meniscus of the %.3g m "
                "radius crack" % c["effective_capillary_radius_m"])
        try_row("liquid-penetrant-inspection", "washburn_penetration_depth",
                {"surface_tension": c["surface_tension_nm"],
                 "contact_angle_deg": c["contact_angle_deg"],
                 "viscosity": c["viscosity_pas"],
                 "radius": c["effective_capillary_radius_m"],
                 "time": c["reference_dwell_s"]},
                c["washburn_depth_at_reference_s_m"],
                "PT: Washburn penetration at the %g s reference dwell"
                % c["reference_dwell_s"])
    if "radiography" in cards:
        c = cards["radiography"]
        try_row("radiographic-inspection", "exposure_time",
                {"base_time": c["inputs"]["base_exposure_min"],
                 "distance": c["sod_mm"] + c["odd_mm"],
                 "reference_distance": c["inputs"]["reference_distance_mm"]},
                c["exposure_min"],
                "RT: inverse-square exposure at the working distance")
        try_row("radiographic-inspection", "iqi_sensitivity_percent",
                {"visible_thickness_mm": c["iq_visible_mm"],
                 "part_thickness_mm": c["section_thickness_mm"]},
                c["iqi_sensitivity_percent"],
                "RT: IQI sensitivity on the %.0f mm section"
                % c["section_thickness_mm"])
    if "computed-tomography" in cards:
        c = cards["computed-tomography"]
        try_row("computed-tomography", "projection_count",
                {"columns_span": c["inputs"]["columns_span"]},
                c["projection_count"],
                "CT: cone-beam projection count for %d columns"
                % c["inputs"]["columns_span"])
        try_row("computed-tomography", "tube_energy_kv",
                {"material": c["inputs"]["material"],
                 "thickness_mm": c["inputs"]["thickness_mm"]},
                c["tube_energy_kv"],
                "CT: tube energy for %s at %.0f mm"
                % (c["inputs"]["material"], c["inputs"]["thickness_mm"]))
        try_row("computed-tomography", "porosity_fraction",
                {"void_voxels": c["inputs"]["void_voxels"],
                 "total_voxels": c["inputs"]["total_voxels"]},
                c["porosity_percent"],
                "CT: porosity volume fraction in the ROI")
        try_row("computed-tomography", "void_diameter",
                {"void_voxels": c["inputs"]["void_voxels"],
                 "voxel_size_m": c["voxel_size_m"]},
                c["void_diameter_m"],
                "CT: equivalent spherical void diameter")
    if "leak-test" in cards:
        c = cards["leak-test"]
        try_row("leak-testing", "pressure_decay_rate",
                {"volume_L": c["volume_L"], "dP_bar": c["dP_bar"],
                 "time_s": c["time_s"]},
                c["leak_rate_sccs"],
                "LT: pressure-decay leak rate over the %.0f s test"
                % c["time_s"])
        try_row("leak-testing", "gauge_resolution_time",
                {"volume_L": c["volume_L"], "gauge_res_bar": c["gauge_res_bar"],
                 "target_sccs": c["max_allowable_sccs"]},
                c["gauge_resolution_time_s"],
                "LT: time for the gauge to resolve the allowable leak")
    return rows


def _provenance(model, dispatch_rows):
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/ndt_core.py",
            "functions": ["select_method", "et_plan", "pt_plan", "rt_plan",
                          "ct_plan", "mt_plan", "leak_plan",
                          "qualification_review", "acceptance_framing",
                          "build_report", "render_report_markdown",
                          "check_report"],
            "version": "0.1.0",
        },
        "skills": dispatch_rows,
        "cross_checked": bool(dispatch_rows),
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def cmd_build(args):
    item = core.example_item()
    if args.leak_limit_sccs is not None:
        if item.leak:
            item.leak["max_allowable_sccs"] = float(args.leak_limit_sccs)
    model = core.build_report(item)
    md = core.render_report_markdown(model)

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
    dispatch_rows = [] if args.no_dispatch else _dispatch_crosschecks(model)
    if args.out:
        with open(args.out, "w") as f:
            f.write(md if md.endswith("\n") else md + "\n")
        tops = [r["top_method"] for r in model["defect_population"]]
        print("built NDT plan + method selection report -> %s" % args.out)
        print("item: %s | selected methods: %s"
              % (model["item"], ", ".join(tops)))
        print("leak disposition: %s (%.2f dB)"
              % (model["parameter_cards"]["leak-test"]["verdict"],
                 model["parameter_cards"]["leak-test"]["margin_db"])
              if "leak-test" in model["parameter_cards"] else "")
        print("gates: all_pass=%s %s" % (gates["all_pass"], gates))
        if args.bundle:
            prov = _provenance(model, dispatch_rows)
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "Nondestructive Test Plan and Method Selection Report",
                model, gates, prov)
            print("bundle: model=%s" % paths["model"])
            print("        gates=%s" % paths["gates"])
            print("        provenance=%s" % paths["provenance"])
            if dispatch_rows:
                print("cross-checks: %d pair(s) vs bound ndt leaf logic"
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
    gates = core.check_report_markdown(md)
    for name, ok in gates.items():
        if name != "all_pass":
            print("%s  %s" % ("PASS" if ok else "FAIL", name))
    print("RESULT: %s" % ("PASS" if gates["all_pass"] else "FAIL"))
    return 0 if gates["all_pass"] else 1


def main():
    p = argparse.ArgumentParser(description="NDT Engineer role")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="",
                   help="output file (default: stdout)")
    b.add_argument("--leak-limit-sccs", type=float, default=None,
                   help="re-run the leak disposition against this allowable "
                        "(scc/s)")
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
                   help="report markdown file to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
