#!/usr/bin/env python3
"""cli.py - run the State Estimation Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--dt <s>] [--steps <n>]
                       [--q <m2/s3>] [--r <m2>] [--alpha <a>]
                       [--bundle] [--no-dispatch] [--profile <p.json>]
    # build the Navigation State Estimator Design Report
    # --bundle      also emit evidence/{model,gates,provenance}.json
    #               (docs/PROTOCOL.md v1)
    # --profile     apply a program/customer profile header
  python3 cli.py check --file <file.md>   # gate-check an existing report

The role ENGINE (core/state_estimation_core.py) does the work standalone:
complementary-filter attitude design, constant-velocity Kalman recursion,
alpha-beta (Benedict-Bordner/Kalata) gains, EKF linearization, RTS
smoothing, observability, and the evidence gates. When AeroSkills is
present (AEROSKILLS_DEV or ~/AeroSkills), the CLI dispatches the bound
estimation-filtering leaf logic files and cross-checks identical
computations (alpha-beta gains, Kalman recursion, EKF Jacobian, NEES,
effective sample size); agreement is recorded in provenance.json.
"""
from __future__ import annotations  # PEP 604 unions (dict | None) on Python 3.9

import argparse
import importlib.util
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import state_estimation_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "state-estimation-engineer"
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
SKILLS_RELEASE = "v1.3.0+"


def _load_logic(leaf: str):
    """Import the first *_logic.py under an AeroSkills leaf (or None)."""
    logic_dir = os.path.join(AEROSKILLS, "skills", leaf, "scripts")
    if not os.path.isdir(logic_dir):
        return None
    for lf in sorted(f for f in os.listdir(logic_dir)
                     if f.endswith("_logic.py")):
        spec = importlib.util.spec_from_file_location(
            "role_dispatch", os.path.join(logic_dir, lf))
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
            return mod, lf
        except Exception:
            continue
    return None


def _dispatch_row(leaf, item, model, spec) -> dict | None:
    """Run one bound-leaf computation and compare with the core value.

    spec: {function, skill_kwargs(item)->kwargs, select(result)->float,
           core(item, model)->float, note}  -- select turns the leaf
    return value into the comparable scalar.
    """
    loaded = _load_logic(leaf)
    if loaded is None:
        return None
    mod, logic_file = loaded
    if not hasattr(mod, spec["function"]):
        return None
    try:
        skill_val = spec["select"](
            getattr(mod, spec["function"])(**spec["skill_kwargs"](item)))
        core_val = spec["core"](item, model)
        delta = abs(float(core_val) - float(skill_val))
        return {
            "leaf": leaf,
            "skill_md": "SKILL.md",
            "logic_file": "scripts/" + logic_file,
            "function": spec["function"],
            "dispatched": True,
            "cross_check_point": spec["note"](item),
            "core_value": round(float(core_val), 9),
            "skill_value": round(float(skill_val), 9),
            "delta": round(delta, 12),
            "agrees": delta <= spec.get("tolerance", 1e-6),
            "tolerance": spec.get("tolerance", 1e-6),
            "skills_release": SKILLS_RELEASE,
        }
    except Exception as e:  # noqa: BLE001 - dispatch must never crash build
        return {"leaf": leaf, "function": spec["function"],
                "dispatched": True, "error": str(e)[:150],
                "agrees": False}


def dispatch_crosschecks(item, model) -> list:
    """Cross-check the core against all bound leaves with shared math."""

    def ab_leaf(lam):
        return {"leaf": "gnc-autonomy/estimation-filtering/alpha-beta-filter",
                "function": "gains_from_tracking_index",
                "skill_kwargs": lambda it: {"tracking_index": it.tracking_index()},
                "select": lambda v: v["alpha"],
                "core": lambda it, m: core.kalata_gains(it.tracking_index())[
                    "alpha"],
                "note": lambda it: "Kalata alpha from lambda=%.6f"
                                  % it.tracking_index(),
                "tolerance": 1e-6}

    def beta_bb(lam):
        return {"leaf": "gnc-autonomy/estimation-filtering/alpha-beta-filter",
                "function": "steady_state_gains",
                "skill_kwargs": lambda it: {"alpha": it.alpha},
                "select": lambda v: v["beta"],
                "core": lambda it, m: core.steady_state_beta(it.alpha),
                "note": lambda it: "Benedict-Bordner beta at alpha=%.3f"
                                  % it.alpha,
                "tolerance": 1e-6}

    def kf_final(lam):
        return {"leaf": "gnc-autonomy/estimation-filtering/rts-smoother",
                "function": "forward_kalman",
                "skill_kwargs": lambda it: {
                    "measurements": it.measurement_sequence(), "dt": it.dt,
                    "q": it.process_noise_intensity, "r": it.meas_variance,
                    "x0": [0.0, 0.0],
                    "p0": [[it.initial_pos_var, 0.0],
                           [0.0, it.initial_vel_var]]},
                "select": lambda v: v[-1]["P_filt"][0][0],
                "core": lambda it, m: m["kalman"]["final"]["pos_var_after"],
                "note": lambda it: "final position variance, CV Kalman "
                                   "recursion (step %d)" % it.horizon_steps,
                "tolerance": 1e-6}

    def ekf_h(lam):
        op = [float(v) for v in item.ekf_op_point]
        return {"leaf":
                "gnc-autonomy/estimation-filtering/extended-kalman-filter",
                "function": "jacobian_h",
                "skill_kwargs": lambda it: {
                    "h": _skill_bearing_range, "x": op},
                "select": lambda v: v[0][0],
                "core": lambda it, m: m["ekf"]["H"][0][0],
                "note": lambda it: "EKF Jacobian H[0][0] at the operating "
                                   "point (range row)",
                "tolerance": 1e-6}

    def nees_chk(lam):
        op = [float(v) for v in item.ekf_op_point]
        p2 = [[item.initial_pos_var, 0.0], [0.0, item.initial_pos_var]]
        return {"leaf":
                "gnc-autonomy/estimation-filtering/unscented-kalman-filter",
                "function": "nees",
                "skill_kwargs": lambda it: {"x_est": op[:2], "p_est": p2,
                                            "x_true": [op[0] - 5.0,
                                                       op[1] + 2.0]},
                "select": lambda v: float(v),
                "core": lambda it, m: core.nees(op[:2], p2,
                                                [op[0] - 5.0, op[1] + 2.0]),
                "note": lambda it: "NEES consistency sample on the "
                                   "position subspace",
                "tolerance": 1e-6}

    def ess_chk(lam):
        w = [1.0 / item.particle_count] * item.particle_count
        return {"leaf": "gnc-autonomy/estimation-filtering/particle-filter",
                "function": "effective_sample_size",
                "skill_kwargs": lambda it: {"weights": w},
                "select": lambda v: float(v),
                "core": lambda it, m: core.effective_sample_size(w),
                "note": lambda it: "ESS of a uniform %d-particle ensemble"
                                  % it.particle_count,
                "tolerance": 1e-9}

    specs = [beta_bb(item), ab_leaf(item), kf_final(item), ekf_h(item),
             nees_chk(item), ess_chk(item)]
    rows = []
    for s in specs:
        row = _dispatch_row(s["leaf"], item, model, s)
        if row:
            rows.append(row)
    return rows


def _skill_bearing_range(x):
    """Bearing/range measurement used only for the dispatch comparison
    (same model as the extended-kalman-filter leaf)."""
    import math
    return [math.hypot(x[0], x[1]), math.atan2(x[1], x[0])]


def _provenance(item, model, dispatch_rows):
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/state_estimation_core.py",
            "functions": ["run_cv_kalman", "kalata_gains",
                          "steady_state_beta", "ekf_correct", "nees",
                          "effective_sample_size", "steady_state_verdict",
                          "rts_smooth", "observability_rank"],
            "version": "0.1.0",
        },
        "skills": dispatch_rows,
        "cross_checked": bool(dispatch_rows) and all(
            r.get("dispatched") and not r.get("error") and r.get("agrees")
            for r in dispatch_rows),
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def cmd_build(args):
    item = core.example_item()
    if args.dt:
        item.dt = float(args.dt)
    if args.steps:
        item.horizon_steps = int(args.steps)
    if args.q:
        item.process_noise_intensity = float(args.q)
    if args.r:
        item.meas_variance = float(args.r)
    if args.alpha:
        item.alpha = float(args.alpha)
    model = core.build_report(item)
    md = core.render_report_markdown(model)

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
        dispatch_rows = dispatch_crosschecks(item, model)

    if args.out:
        with open(args.out, "w") as f:
            f.write(md if md.endswith("\n") else md + "\n")
        print(f"built Navigation State Estimator Design Report -> {args.out}")
        print(f"estimator class: {model['estimator_class']}")
        print(f"kalman final gain: {model['kalman']['final']['gain']}  "
              f"pos var: {model['kalman']['final']['pos_var_after']:.4f} m^2")
        print(f"gates: all_pass={gates['all_pass']} {gates}")
        if args.bundle:
            prov = _provenance(item, model, dispatch_rows)
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "Navigation State Estimator Design Report", model, gates,
                prov)
            print(f"bundle: model={paths['model']}")
            print(f"        gates={paths['gates']}")
            print(f"        provenance={paths['provenance']}")
            for row in dispatch_rows:
                if "error" in row:
                    print(f"cross-check: {row['leaf']} error: {row['error']}")
                else:
                    print(f"cross-check: {row['leaf']} "
                          f"{row['function']} core={row['core_value']} "
                          f"skill={row['skill_value']} "
                          f"delta={row['delta']} agrees={row['agrees']}")
            if not dispatch_rows:
                print("cross-check: not dispatched (no AeroSkills logic)")
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
        description="State Estimation Engineer role")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="", help="output file (default: stdout)")
    b.add_argument("--dt", default="", help="nav update interval in s")
    b.add_argument("--steps", default="", help="design horizon in steps")
    b.add_argument("--q", default="", help="process noise intensity m^2/s^3")
    b.add_argument("--r", default="", help="measurement variance m^2")
    b.add_argument("--alpha", default="", help="alpha-beta smoothing factor")
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json")
    b.add_argument("--no-dispatch", action="store_true",
                   help="skip dispatching bound AeroSkills logic")
    b.add_argument("--profile", default="",
                   help="program profile JSON (docs/PROFILE-SCHEMA.md)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="report markdown to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
