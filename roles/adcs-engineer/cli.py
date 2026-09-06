#!/usr/bin/env python3
"""cli.py - run the ADCS Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--requirement-arcsec <n>]
                       [--slew-deg <n>] [--bundle] [--no-dispatch]
                       [--profile <p.json>]
    # build the Attitude Determination and Control Subsystem Report
    # --bundle      also emit evidence/{model,gates,provenance}.json
    # --no-dispatch skip dispatching bound AeroSkills logic for cross-check
  python3 cli.py check --file <file.md> [--requirement-arcsec <n>]
                       # gate-check an existing report (exit 0 = PASS)

The role ENGINE (core/adcs_core.py) does the work standalone. When the
Aero Agent Skills library is present (AEROSKILLS_DEV or ~/AeroSkills),
the CLI dispatches six bound ADCS leaf logic modules on the SAME inputs
the core used - TRIAD, QUEST/Wahba, reaction wheel PD torque, the
magnetorquer desaturation dipole, the pointing error budget RSS and the
gyro angle random walk - and records core-vs-skill agreement per row in
provenance.json (docs/PROTOCOL.md cross-check semantics).
"""
import argparse
import importlib.util
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import adcs_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "adcs-engineer"
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
ADCS_DIR = os.path.join(AEROSKILLS, "skills", "space-systems", "adcs")


def _load_leaf_logic(leaf):
    """Import a bound ADCS leaf's *_logic.py, or None when unavailable."""
    logic_dir = os.path.join(ADCS_DIR, leaf, "scripts")
    if not os.path.isdir(logic_dir):
        return None
    logic_files = sorted(f for f in os.listdir(logic_dir)
                         if f.endswith("_logic.py"))
    for lf in logic_files:
        path = os.path.join(logic_dir, lf)
        spec = importlib.util.spec_from_file_location(
            "adcs_dispatch_" + leaf.replace("-", "_"), path)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
            return mod, lf
        except Exception:
            continue
    return None


def _row(leaf, function, cross_check_point, core_value, skill_value,
         tolerance, logic_file):
    delta = abs(float(core_value) - float(skill_value))
    return {
        "leaf": "space-systems/adcs/" + leaf,
        "skill_md": "SKILL.md",
        "logic_file": "scripts/" + logic_file,
        "function": function,
        "dispatched": True,
        "cross_check_point": cross_check_point,
        "core_value": round(float(core_value), 6),
        "skill_value": round(float(skill_value), 6),
        "delta": round(delta, 9),
        "agrees": delta <= tolerance,
        "tolerance": tolerance,
        "skills_release": "v1.3.0+",
    }


def _run_crosschecks(item, model):
    """Dispatch the bound ADCS leaf logic and compare with core values.

    Six cross-check points, each on inputs identical to the core's:
    1. TRIAD rotation angle recovered from the sun/magnetometer pair.
    2. QUEST Wahba cost at the optimal quaternion (3 weighted obs).
    3. Reaction wheel PD torque magnitude at a mid-slew state.
    4. Magnetorquer desaturation dipole magnitude for the unload torque.
    5. Pointing error budget RSS 3-sigma error.
    6. Gyro angle random walk coefficient from the deterministic series.
    """
    rows = []
    obs_set = core.example_observation_set(item.slew_target_deg)
    tr = obs_set["triad"]
    qs = obs_set["quest"]
    ct = model["control"]
    gy = model["gyro"]

    try:
        loaded = _load_leaf_logic("attitude-determination-triad")
        if loaded:
            mod, lf = loaded
            a_skill = mod.triad_matrix(tr["b1"], tr["b2"], tr["r1"], tr["r2"])
            skill_val = mod.rotation_angle_deg(a_skill)
            a_core = core.triad_matrix(tr["b1"], tr["b2"], tr["r1"], tr["r2"])
            core_val = core.rotation_angle_deg(a_core)
            rows.append(_row(
                "attitude-determination-triad", "rotation_angle_deg",
                "TRIAD recovered rotation angle, 10 deg z slew "
                "(truth-model pair)", core_val, skill_val, 1e-9, lf))
    except Exception as e:  # pragma: no cover - dispatch robustness
        rows.append({"leaf": "space-systems/adcs/attitude-determination-triad",
                     "dispatched": True, "error": str(e), "agrees": False})

    try:
        loaded = _load_leaf_logic("attitude-determination-quest")
        if loaded:
            mod, lf = loaded
            skill_val = mod.quest_solution(
                list(qs["observations"]), list(qs["references"]),
                list(qs["weights"]))["wahba_cost"]
            core_val = core.quest_solution(
                list(qs["observations"]), list(qs["references"]),
                list(qs["weights"]))["wahba_cost"]
            rows.append(_row(
                "attitude-determination-quest", "quest_solution",
                "QUEST Wahba cost at the optimal quaternion (3 obs)",
                core_val, skill_val, 1e-12, lf))
    except Exception as e:  # pragma: no cover
        rows.append({"leaf": "space-systems/adcs/attitude-determination-quest",
                     "dispatched": True, "error": str(e), "agrees": False})

    try:
        loaded = _load_leaf_logic("reaction-wheel-control")
        if loaded:
            mod, lf = loaded
            kp = ct["kp_z_nm_per_rad"]
            kd = ct["kd_z_nm_s_per_rad"]
            te = (0.0, 0.0, math.radians(5.0))   # mid-slew attitude error
            oe = (0.0, 0.0, 0.001)               # rad/s body rate error
            core_tau = core.pd_wheel_torque(kp, kd, te, oe)
            skill_tau = mod.pd_wheel_torque(kp, kd, te, oe)
            rows.append(_row(
                "reaction-wheel-control", "pd_wheel_torque",
                "Wheel torque command magnitude, 5 deg error @ 0.001 rad/s",
                core.norm3(core_tau), core.norm3(skill_tau), 1e-12, lf))
    except Exception as e:  # pragma: no cover
        rows.append({"leaf": "space-systems/adcs/reaction-wheel-control",
                     "dispatched": True, "error": str(e), "agrees": False})

    try:
        loaded = _load_leaf_logic("magnetorquer-control")
        if loaded:
            mod, lf = loaded
            b_vec = (0.0, item.b_field_t, 0.0)
            tau_desat = (0.0, 0.0, -ct["desat_torque_nm"])
            core_m, _ = core.dipole_from_torque(tau_desat, b_vec)
            skill_m, _ = mod.dipole_from_torque(tau_desat, b_vec)
            rows.append(_row(
                "magnetorquer-control", "dipole_from_torque",
                "Desaturation dipole magnitude for the unload torque",
                core.norm3(core_m), core.norm3(skill_m), 1e-12, lf))
    except Exception as e:  # pragma: no cover
        rows.append({"leaf": "space-systems/adcs/magnetorquer-control",
                     "dispatched": True, "error": str(e), "agrees": False})

    try:
        loaded = _load_leaf_logic("pointing-error-budget")
        if loaded:
            mod, lf = loaded
            contrib = model["pointing_budget"]["contributors_arcsec_1sigma"]
            core_val = core.three_sigma_error(contrib)
            skill_val = mod.three_sigma_error(contrib)
            rows.append(_row(
                "pointing-error-budget", "three_sigma_error",
                "RSS 3-sigma pointing error over the contributor set",
                core_val, skill_val, 1e-9, lf))
    except Exception as e:  # pragma: no cover
        rows.append({"leaf": "space-systems/adcs/pointing-error-budget",
                     "dispatched": True, "error": str(e), "agrees": False})

    try:
        loaded = _load_leaf_logic("gyro-allan-variance")
        if loaded:
            mod, lf = loaded
            samples = core.example_gyro_samples()
            core_val = gy["arw_deg_per_sqrt_h"]
            skill_val = mod.gyro_noise_summary(samples, 1.0,
                                               [1.0, 2.0])[
                                                   "arw_deg_per_sqrt_h"]
            rows.append(_row(
                "gyro-allan-variance", "gyro_noise_summary",
                "Angle random walk coefficient, deterministic 2 h series",
                core_val, skill_val, 1e-6, lf))
    except Exception as e:  # pragma: no cover
        rows.append({"leaf": "space-systems/adcs/gyro-allan-variance",
                     "dispatched": True, "error": str(e), "agrees": False})

    return rows


def _provenance(item, model, dispatch_rows):
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/adcs_core.py",
            "functions": ["build_report", "check_report",
                          "triad_matrix", "quest_solution",
                          "gyro_noise_characterization",
                          "wheel_slew_run_z", "dipole_from_torque",
                          "pointing_error_budget"],
            "version": "0.1.0",
        },
        "skills": dispatch_rows,
        "cross_checked": bool(dispatch_rows)
                         and all(r.get("dispatched") and not r.get("error")
                                 and r.get("agrees") for r in dispatch_rows),
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def cmd_build(args):
    item = core.example_item()
    if args.requirement_arcsec:
        item.requirement_arcsec_3sigma = float(args.requirement_arcsec)
    if args.slew_deg:
        item.slew_target_deg = float(args.slew_deg)
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
        dispatch_rows = _run_crosschecks(item, model)

    if args.out:
        with open(args.out, "w") as f:
            f.write(md if md.endswith("\n") else md + "\n")
        pb = model["pointing_budget"]
        print("built ADCS report -> %s" % args.out)
        print("pointing: requirement=%.1f arcsec 3-sigma, rss=%.2f arcsec "
              "3-sigma, margin=%.2fx, met=%s"
              % (model["requirement_arcsec_3sigma"], pb["rss_3sigma_arcsec"],
                 pb["margin"], pb["requirement_met"]))
        print("determination: TRIAD=%.4f deg, QUEST eigenangle=%.4f deg, "
              "ARW=%.4f deg/sqrt(h)"
              % (model["determination"]["triad_rotation_angle_deg"],
                 model["determination"]["quest_eigenangle_deg"],
                 model["gyro"]["arw_deg_per_sqrt_h"]))
        print("gates: all_pass=%s %s" % (gates["all_pass"], gates))
        if args.bundle:
            prov = _provenance(item, model, dispatch_rows)
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "Attitude Determination and Control Subsystem Report",
                model, gates, prov)
            print("bundle: model=%s" % paths["model"])
            print("        gates=%s" % paths["gates"])
            print("        provenance=%s" % paths["provenance"])
            for i, row in enumerate(dispatch_rows, 1):
                if row.get("error"):
                    print("cross-check[%d/%d]: %s ERROR %s"
                          % (i, len(dispatch_rows), row["leaf"],
                             row["error"]))
                else:
                    print("cross-check[%d/%d]: %s core=%.6f skill=%.6f "
                          "delta=%.9f agrees=%s"
                          % (i, len(dispatch_rows),
                             row.get("cross_check_point", row["leaf"]),
                             row["core_value"], row["skill_value"],
                             row["delta"], row["agrees"]))
            if not dispatch_rows:
                print("cross-check: not dispatched (no AeroSkills logic)")
            elif not prov["cross_checked"]:
                print("cross-check: DISAGREEMENT or dispatch error - "
                      "review before use")
    else:
        print(md)
    return 0 if gates["all_pass"] else 1


def cmd_check(args):
    if not os.path.exists(args.file):
        print("file not found: %s" % args.file)
        return 1
    md = open(args.file).read()
    req = float(args.requirement_arcsec) if args.requirement_arcsec else 0.0
    gates = core.check_report_markdown(md, req)
    for name, ok in gates.items():
        if name != "all_pass":
            print("%s  %s" % ("PASS" if ok else "FAIL", name))
    print("RESULT: %s" % ("PASS" if gates["all_pass"] else "FAIL"))
    return 0 if gates["all_pass"] else 1


def main():
    p = argparse.ArgumentParser(description="ADCS Engineer role")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="", help="output file (default: stdout)")
    b.add_argument("--requirement-arcsec", default="",
                   help="3-sigma pointing requirement in arcsec")
    b.add_argument("--slew-deg", default="", help="acquisition slew in deg")
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
                   help="ADCS report markdown to gate-check")
    c.add_argument("--requirement-arcsec", default="",
                   help="expected 3-sigma pointing requirement (arcsec)")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
