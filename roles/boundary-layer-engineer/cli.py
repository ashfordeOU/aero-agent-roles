#!/usr/bin/env python3
"""cli.py - run the Boundary-Layer Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--chord-m N] [--u-inf-ms N]
                       [--bundle] [--no-dispatch] [--profile <profile.json>]
    # build the Boundary-Layer and Viscous Drag Analysis Report for the
    # reference NLF sailplane wing section + fuselage forebody item;
    # --bundle also emits evidence/{model,gates,provenance}.json
    # (docs/PROTOCOL.md); --profile applies a program profile
  python3 cli.py check --file <file.md>
    # gate-check an existing report (exit 0 = PASS)

The role ENGINE (core/boundary_layer_engineer_core.py) does the work
standalone: laminar growth and Michel-criterion transition, Squire-
Young profile drag, the Mangler axisymmetric transform, laminar
far-wake drag, rough-wall skin friction, stagnation-point flow, Stokes
creeping-flow drag and the unsteady laminar Stokes layer. When Aero
Skills is present (AEROSKILLS_DEV or ~/AeroSkills) the CLI dispatches
a representative function from each bound aerodynamics/boundary-layer
leaf's logic and cross-checks the core's value against the leaf's
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
import boundary_layer_engineer_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "boundary-layer-engineer"
PACK = "aerodynamics/boundary-layer"
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))

# One cross-check per dispatched leaf: (leaf, function, args). The
# function exists under the IDENTICAL name in the role core AND in the
# leaf's *_logic.py, called positionally so parameter-name differences
# don't matter; each args tuple is a real, valid input (several taken
# straight from the leaf's own worked example).
DISPATCH = [
    ("boundary-layer-theory", "shape_factor", (0.0017208, 0.000664)),
    ("boundary-layer-transition", "michel_threshold", (2.0548e6,)),
    ("rough-wall-skin-friction", "smooth_turbulent_cf", (8.12155e6,)),
    ("stagnation-flow-boundary-layer", "stagnation_velocity_gradient",
     ("sphere", 79.0, 0.20)),
    ("laminar-far-wake", "momentum_thickness_blasius",
     (5.0, 1.0, 1.46e-5)),
    ("mangler-axisymmetric-transform", "cone_skin_friction", (3.32e-4,)),
    ("squire-young-profile-drag", "squire_young_profile_drag",
     (3.0e-3, 1.0, 27.0, 30.0, 1.4)),
    ("stokes-creeping-flow-drag", "stokes_drag", (1.7885e-5, 1.0e-4, 0.01)),
    ("unsteady-laminar-stokes-layers", "stokes_penetration_depth",
     (1.46e-5, 50.0)),
]
# boundary-layer-separation is bound for coherence (the attached-flow
# check in Section 2 uses its Thwaites-lambda logic directly) but is
# not wired into this cross-check set.
UNDISPATCHED_LEAVES = ["boundary-layer-separation"]


def _load_leaf(leaf):
    """Import the leaf's *_logic.py module if present, else None."""
    logic_dir = os.path.join(AEROSKILLS, "skills", PACK, leaf, "scripts")
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
    """Cross-check the core against the bound leaf logic modules."""
    rows = []
    for leaf, fn, args in DISPATCH:
        core_fn = getattr(core, fn, None)
        if core_fn is None:
            rows.append({"leaf": PACK + "/" + leaf, "function": fn,
                        "dispatched": False,
                        "reason": "core function missing"})
            continue
        mod = _load_leaf(leaf)
        if mod is None or not hasattr(mod, fn):
            rows.append({"leaf": PACK + "/" + leaf, "function": fn,
                        "dispatched": False,
                        "reason": "skill logic unavailable"})
            continue
        try:
            core_val = core_fn(*args)
            skill_val = getattr(mod, fn)(*args)
            delta = abs(float(core_val) - float(skill_val))
            rows.append({
                "leaf": PACK + "/" + leaf, "function": fn,
                "logic_file": "scripts/*_logic.py", "dispatched": True,
                "core_value": round(float(core_val), 9),
                "skill_value": round(float(skill_val), 9),
                "delta": round(delta, 12), "agrees": delta <= 1e-6,
                "tolerance": 1e-6,
            })
        except Exception as e:
            rows.append({"leaf": PACK + "/" + leaf, "function": fn,
                        "dispatched": True, "error": str(e)[:150],
                        "agrees": False})
    for leaf in UNDISPATCHED_LEAVES:
        rows.append({"leaf": PACK + "/" + leaf, "dispatched": False,
                    "reason": "bound for coherence, not wired into this "
                              "role's cross-check set"})
    return rows


def _provenance(dispatch_rows):
    dispatched = [r for r in dispatch_rows
                 if r.get("dispatched") and not r.get("error")]
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/boundary_layer_engineer_core.py",
            "functions": ["build_report", "check_report",
                         "render_report_markdown", "flat_plate_transition",
                         "fully_laminar_profile_drag", "cone_skin_friction",
                         "drag_from_wake", "cf_with_roughness",
                         "stagnation_wall_shear", "stokes_drag",
                         "stokes_second_shear_amplitude"],
            "version": "0.1.0",
        },
        "skills": dispatch_rows,
        "cross_checked": bool(dispatched and all(r["agrees"]
                                                 for r in dispatched)),
        "disclaimer": ("DRAFT for human review. Not an approval document "
                      "and not a certification approval."),
    }


def cmd_build(args):
    item = core.example_item()
    if args.chord_m:
        item.chord_m = float(args.chord_m)
    if args.u_inf_ms:
        item.u_inf_ms = float(args.u_inf_ms)
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
        dispatch_rows = _dispatch_rows()

    if args.out:
        with open(args.out, "w") as f:
            f.write(md if md.endswith("\n") else md + "\n")
        print("built Boundary-Layer and Viscous Drag Analysis Report -> %s"
             % args.out)
        print("chord Re_c: %.4e, Squire-Young c_d,p (both surfaces): %.5f"
             % (model["transition"]["re_c"],
                model["profile_drag"]["cdp_both_surfaces"]))
        print("gates: all_pass=%s %s" % (gates["all_pass"], gates))
        if profile:
            print("profile: %s / %s" % (profile.get("customer"),
                                        profile.get("program")))
        if args.bundle:
            prov = _provenance(dispatch_rows)
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "Boundary-Layer and Viscous Drag Analysis Report", model,
                gates, prov)
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
        description="Boundary-Layer Engineer role: build/check the "
                    "Boundary-Layer and Viscous Drag Analysis Report")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="", help="output file (default: stdout)")
    b.add_argument("--chord-m", default="",
                  help="wing section chord in m (default: 0.65)")
    b.add_argument("--u-inf-ms", default="",
                  help="freestream speed in m/s (default: 79.0)")
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
