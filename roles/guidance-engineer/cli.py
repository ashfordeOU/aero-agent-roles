#!/usr/bin/env python3
"""cli.py - run the Guidance Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--n-nav <N>] \\
      [--miss-requirement <m>] [--accel-limit <g>] [--bundle]
    # build the Guidance Law Design and Assessment Report for the
    # example item (interceptor terminal homing loop)
    # --bundle  also emit evidence/{model,gates,provenance}.json (PROTOCOL.md)
  python3 cli.py check --file <file.md>             # gate-check a report

The role ENGINE (core/guidance_core.py) does the work standalone; bound
Aero Agent Skills leaves in gnc-autonomy/guidance carry the same laws as
*_logic.py files, and when the library is present their implementations
are dispatched on the same inputs and recorded in provenance.json
(delta ~ 0 = two independent implementations agree).
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
import guidance_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "guidance-engineer"

# Functions the core exports with leaf-identical signatures, dispatched
# against the bound leaf *_logic.py when the skills tree is present.
DISPATCH_ROWS = [
    {
        "leaf": "gnc-autonomy/guidance/proportional-navigation",
        "skill_fn": "commanded_acceleration",
        "core_fn": "commanded_acceleration",
        "kwargs": {"rx": 1000.0, "ry": 100.0, "vx": -200.0, "vy": 0.0,
                   "n_nav": 4.0},
        "tolerance": 1e-6,
    },
    {
        "leaf": "gnc-autonomy/guidance/augmented-proportional-navigation",
        "skill_fn": "apn_command",
        "core_fn": "apn_command",
        "kwargs": {"navigation_ratio": 4.0,
                   "closing_velocity": 199.007438041998,
                   "los_rate": 0.019801980198,
                   "target_lateral_accel": 20.0},
        "tolerance": 1e-6,
    },
    {
        "leaf": "gnc-autonomy/guidance/pursuit-guidance",
        "skill_fn": "heading_error",
        "core_fn": "heading_error",
        "kwargs": {"psi": 0.0, "rx": 1000.0, "ry": 100.0},
        "tolerance": 1e-6,
    },
    {
        "leaf": "gnc-autonomy/guidance/midcourse-guidance",
        "skill_fn": "desired_heading",
        "core_fn": "desired_heading",
        "kwargs": {"position": (0.0, 0.0), "waypoint": (1000.0, 500.0)},
        "tolerance": 1e-6,
    },
    {
        "leaf": "gnc-autonomy/guidance/midcourse-guidance",
        "skill_fn": "zero_effort_miss",
        "core_fn": "zero_effort_miss",
        "kwargs": {"interceptor_pos": (0.0, 0.0),
                   "interceptor_vel": (300.0, 0.0),
                   "target_pos": (6000.0, 150.0),
                   "target_vel": (0.0, 0.0)},
        "value_key": "zem",
        "tolerance": 1e-6,
    },
]


def _load_skill_logic(leaf, skills_root):
    """Import the leaf's *_logic.py module (stdlib) or return None.

    Returns (module, logic_file_basename) or (None, None)."""
    logic_dir = os.path.join(skills_root, "skills", leaf, "scripts")
    if not os.path.isdir(logic_dir):
        return None, None
    logic_files = sorted(f for f in os.listdir(logic_dir)
                         if f.endswith("_logic.py"))
    for lf in logic_files:
        spec = importlib.util.spec_from_file_location(
            "role_dispatch_" + leaf.replace("/", "_"),
            os.path.join(logic_dir, lf))
        if spec is None or spec.loader is None:
            continue
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception:
            continue
        return mod, lf
    return None, None


def _dispatch_rows(skills_root=""):
    """Dispatch each row against the bound leaf and the role core.

    Returns provenance rows: dispatched True with core/skill value,
    delta and agrees when the leaf logic is reachable, else a
    dispatched False row (role core ran standalone - still valid).
    """
    root = skills_root or os.environ.get(
        "AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
    rows = []
    for row in DISPATCH_ROWS:
        mod, logic_file = _load_skill_logic(row["leaf"], root)
        if mod is None or not hasattr(mod, row["skill_fn"]):
            rows.append({
                "leaf": row["leaf"],
                "logic_file": "n/a (standalone)",
                "function": row["skill_fn"],
                "dispatched": False,
                "reason": "skill logic unavailable (standalone build)",
            })
            continue
        try:
            skill_val = getattr(mod, row["skill_fn"])(**row["kwargs"])
            core_val = getattr(core, row["core_fn"])(**row["kwargs"])
            if row.get("value_key"):
                skill_val = skill_val[row["value_key"]]
                core_val = core_val[row["value_key"]]
            if not isinstance(skill_val, (int, float)) or \
               not isinstance(core_val, (int, float)):
                raise TypeError("non-numeric cross-check value")
            delta = abs(float(core_val) - float(skill_val))
            rows.append({
                "leaf": row["leaf"],
                "logic_file": "scripts/" + (logic_file or "unknown.py"),
                "function": row["skill_fn"],
                "dispatched": True,
                "core_value": round(float(core_val), 6),
                "skill_value": round(float(skill_val), 6),
                "delta": round(delta, 9),
                "agrees": delta <= row["tolerance"],
                "tolerance": row["tolerance"],
            })
        except Exception as exc:  # noqa: BLE001 - provenance must not crash
            rows.append({
                "leaf": row["leaf"],
                "function": row["skill_fn"],
                "dispatched": False,
                "reason": "dispatch error: %s" % exc,
            })
    return rows


def _provenance():
    """Provenance for the bundle: role core + leaf dispatch rows."""
    rows = _dispatch_rows()
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/guidance_core.py",
            "functions": ["commanded_acceleration", "apn_command",
                          "heading_error", "lead_angle", "desired_heading",
                          "commanded_heading", "zero_effort_miss",
                          "accel_utilization", "miss_within_requirement",
                          "build_report", "check_report",
                          "render_report_markdown"],
            "version": "0.1.0",
        },
        "skills": rows,
        "cross_checked": any(r.get("dispatched") for r in rows),
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def _model_jsonable(model):
    """Deep-copy the model into plain JSON types (tuples -> lists)."""
    return json.loads(json.dumps(model, default=list))


def cmd_build(args):
    proj = core.example_project()
    if args.n_nav:
        proj.n_nav = float(args.n_nav)
    if args.miss_requirement:
        proj.miss_requirement_m = float(args.miss_requirement)
    if args.accel_limit:
        proj.accel_limit_g = float(args.accel_limit)
    model = core.build_report(proj)
    md = core.render_report_markdown(model)

    # program profile (customer tailoring): load + apply context header
    profile = None
    try:
        profile = evidence.load_profile(args.profile)
    except ValueError as exc:
        print("error: bad profile: %s" % exc)
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
        print("built Guidance Law Design and Assessment Report (%s) -> %s"
              % (model["item"], args.out))
        if profile:
            print("profile: %s / %s" % (profile.get("customer"),
                                        profile.get("program")))
        print("gates: all_pass=%s %s" % (gates["all_pass"], gates))
        if args.bundle:
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "Guidance Law Design and Assessment Report",
                _model_jsonable(model), gates, _provenance())
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
    p = argparse.ArgumentParser(description="Guidance Engineer role")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="", help="output file (default: stdout)")
    b.add_argument("--n-nav", default="",
                   help="navigation constant N (default 4)")
    b.add_argument("--miss-requirement", default="",
                   help="miss distance requirement in m (default 10)")
    b.add_argument("--accel-limit", default="",
                   help="vehicle lateral acceleration limit in g (default 30)")
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json")
    b.add_argument("--profile", default="",
                   help="program profile JSON (customer tailoring, "
                        "docs/PROFILE-SCHEMA.md)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="Guidance Law Design and Assessment Report markdown "
                        "to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
