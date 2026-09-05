#!/usr/bin/env python3
"""cli.py - run the Numerical Analysis Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--bundle] [--profile <file.json>]
                       [--no-dispatch]
                       [--code-integral <N>] [--code-mach <M>]
                       [--code-solve <c0,c1>]
    # build the Numerical Methods Verification Memo for the example item
    # (Loads Post-Processor v2.3.1) and gate-check it
    # --bundle   also emit evidence/{model,gates,provenance}.json (PROTOCOL.md)
    # --profile  program profile JSON for customer tailoring
    #            (docs/PROFILE-SCHEMA.md) -> prepended context header
    # --no-dispatch skip dispatching bound AeroSkills numerics logic
    # the --code-* flags re-verify a different code report of the same
    # operations (integration value, Mach root, linear-solve result)
  python3 cli.py check --file <file.md>    # gate-check an existing memo

The role ENGINE (core/numerical_analysis_core.py) does the work standalone:
reference quadrature, Newton/bisection root finding, dense solve,
convergence study (observed order, Richardson, GCI), conditioning, and
the evidence gates. When AeroSkills is present (AEROSKILLS_DEV or
~/AeroSkills), the CLI dispatches the bound cross-cutting/numerics leaf
logic modules and cross-checks their numbers against the core's - two
independent implementations agreeing is recorded in provenance.json.
"""
import argparse
import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import numerical_analysis_core as core  # noqa: E402
import evidence  # noqa: E402

AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
NUMERICS_ROOT = os.path.join(AEROSKILLS, "skills", "cross-cutting", "numerics")
ROLE_SLUG = "numerical-analysis-engineer"
SKILLS_RELEASE = "v1.3.0+"

# Bound leaves and their dispatch points (leaf module names as on disk).
BOUND_LEAVES = [
    ("numerical-integration", "numerical_integration_logic.py"),
    ("root-finding", "root_finding_logic.py"),
    ("convergence-verification", "convergence_verification_logic.py"),
    ("singular-value-decomposition", "singular_value_decomposition_logic.py"),
    ("matrix-operations", "matrix_operations_logic.py"),
]


def _load_leaf(leaf, logic_file):
    """Import a bound leaf's *_logic.py module, or None when unavailable."""
    path = os.path.join(NUMERICS_ROOT, leaf, "scripts", logic_file)
    if not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location(
        "numerics_leaf_" + leaf.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _row(leaf, logic_file, fn, core_val, skill_val, point, tol=1e-6):
    delta = abs(float(core_val) - float(skill_val))
    return {
        "leaf": "cross-cutting/numerics/" + leaf,
        "skill_md": "SKILL.md",
        "logic_file": "scripts/" + logic_file,
        "function": fn,
        "dispatched": True,
        "cross_check_point": point,
        "core_value": round(float(core_val), 9),
        "skill_value": round(float(skill_val), 9),
        "delta": round(delta, 12),
        "agrees": delta <= tol,
        "tolerance": tol,
        "skills_release": SKILLS_RELEASE,
    }


def _row_err(leaf, logic_file, fn, exc):
    return {"leaf": "cross-cutting/numerics/" + leaf,
            "logic_file": "scripts/" + logic_file,
            "function": fn, "dispatched": True,
            "error": str(exc), "agrees": False}


def _run_crosschecks(item, model):
    """Cross-check core numbers against the five bound numerics leaves.

    Each row compares the same quantity computed two independent ways:
    the role core implementation and the AeroSkills leaf logic. Rows
    are empty when the skills library is absent.
    """
    rows = []
    a, b = float(item.interval[0]), float(item.interval[1])
    f = lambda y: core.lift_intensity(y, item.integrand_w0,
                                      item.integrand_span)
    ar, gam = item.area_ratio, item.gamma
    resid = lambda M: core.area_mach_residual(M, ar, gam)
    deriv = lambda M: core.area_mach_derivative(M, gam)

    # 1. numerical-integration: trapezoid at the code's panel count
    mod = _load_leaf("numerical-integration",
                     "numerical_integration_logic.py")
    if mod is not None and hasattr(mod, "trapezoid"):
        try:
            core_val = core.trapezoid(f, a, b, item.code_integral_n)
            skill_val = mod.trapezoid(f, a, b, item.code_integral_n)
            rows.append(_row("numerical-integration",
                             "numerical_integration_logic.py", "trapezoid",
                             core_val, skill_val,
                             "code-panel trapezoid of the spanwise load"))
        except Exception as e:  # pragma: no cover
            rows.append(_row_err("numerical-integration",
                                 "numerical_integration_logic.py",
                                 "trapezoid", e))

    # 2. numerical-integration: reference Simpson value
    if mod is not None and hasattr(mod, "simpson"):
        try:
            n_ref = max(2 * item.code_integral_n, 64)
            core_val = core.simpson(f, a, b, n_ref)
            skill_val = mod.simpson(f, a, b, n_ref)
            rows.append(_row("numerical-integration",
                             "numerical_integration_logic.py", "simpson",
                             core_val, skill_val,
                             "reference Simpson integral of the spanwise "
                             "load"))
        except Exception as e:  # pragma: no cover
            rows.append(_row_err("numerical-integration",
                                 "numerical_integration_logic.py",
                                 "simpson", e))

    # 3. numerical-integration: Richardson error estimate error(2n)
    if mod is not None and hasattr(mod, "error_estimate_trapezoid"):
        try:
            core_val = core.richardson_error_trapezoid(
                f, a, b, item.code_integral_n)
            skill_val = mod.error_estimate_trapezoid(
                f, a, b, item.code_integral_n)
            rows.append(_row("numerical-integration",
                             "numerical_integration_logic.py",
                             "error_estimate_trapezoid", core_val, skill_val,
                             "Richardson error estimate of the trapezoid "
                             "result"))
        except Exception as e:  # pragma: no cover
            rows.append(_row_err("numerical-integration",
                                 "numerical_integration_logic.py",
                                 "error_estimate_trapezoid", e))

    # 4. root-finding: Newton-Raphson subsonic area-Mach root
    mod = _load_leaf("root-finding", "root_finding_logic.py")
    if mod is not None and hasattr(mod, "newton_raphson"):
        try:
            core_val = core.newton_raphson(resid, deriv, item.newton_guess)
            skill_val = mod.newton_raphson(resid, deriv, item.newton_guess)
            rows.append(_row("root-finding", "root_finding_logic.py",
                             "newton_raphson", core_val, skill_val,
                             "subsonic root of A/A* = %g, gamma = %g"
                             % (ar, gam)))
        except Exception as e:  # pragma: no cover
            rows.append(_row_err("root-finding", "root_finding_logic.py",
                                 "newton_raphson", e))

    # 5. root-finding: bisection bracket cross-check
    if mod is not None and hasattr(mod, "bisection"):
        try:
            core_val = core.bisection(resid, item.bracket[0], item.bracket[1])
            skill_val = mod.bisection(resid, item.bracket[0], item.bracket[1])
            rows.append(_row("root-finding", "root_finding_logic.py",
                             "bisection", core_val, skill_val,
                             "bisection cross-check on [%g, %g]"
                             % (item.bracket[0], item.bracket[1])))
        except Exception as e:  # pragma: no cover
            rows.append(_row_err("root-finding", "root_finding_logic.py",
                                 "bisection", e))

    # 6. convergence-verification: grid-study order + GCI
    mod = _load_leaf("convergence-verification",
                     "convergence_verification_logic.py")
    if mod is not None and hasattr(mod, "convergence_verdict"):
        try:
            meshes = model["convergence"]["meshes"]
            f1, f2, f3 = (m["f"] for m in meshes)
            r = model["convergence"]["refinement_ratio"]
            core_cv = core.convergence_verdict(f1, f2, f3, r)
            skill_cv = mod.convergence_verdict(f1, f2, f3, r)
            if core_cv["order"] is not None and skill_cv["order"] is not None:
                rows.append(_row("convergence-verification",
                                 "convergence_verification_logic.py",
                                 "convergence_verdict.order",
                                 core_cv["order"], skill_cv["order"],
                                 "observed order of the three-mesh study"))
                rows.append(_row("convergence-verification",
                                 "convergence_verification_logic.py",
                                 "convergence_verdict.gci",
                                 core_cv["gci"], skill_cv["gci"],
                                 "grid convergence index of the study"))
            rows.append(_row("convergence-verification",
                             "convergence_verification_logic.py",
                             "convergence_verdict.verdict",
                             1.0 if core_cv["verdict"] == skill_cv["verdict"]
                             else 0.0,
                             1.0,
                             "convergence verdict classification"))
        except Exception as e:  # pragma: no cover
            rows.append(_row_err("convergence-verification",
                                 "convergence_verification_logic.py",
                                 "convergence_verdict", e))

    # 7. singular-value-decomposition: condition number of the solve
    mod = _load_leaf("singular-value-decomposition",
                     "singular_value_decomposition_logic.py")
    if mod is not None and hasattr(mod, "condition_number"):
        try:
            sv = model["linear_solve"]["conditioning"]["singular_values"]
            core_val = core.condition_number(sv)
            skill_val = mod.condition_number(sv)
            rows.append(_row("singular-value-decomposition",
                             "singular_value_decomposition_logic.py",
                             "condition_number", core_val, skill_val,
                             "2-norm condition number s_max/s_min of A"))
        except Exception as e:  # pragma: no cover
            rows.append(_row_err("singular-value-decomposition",
                                 "singular_value_decomposition_logic.py",
                                 "condition_number", e))

    # 8. matrix-operations: reference dense solve of A c = b
    mod = _load_leaf("matrix-operations", "matrix_operations_logic.py")
    if mod is not None and hasattr(mod, "solve"):
        try:
            core_val = core.solve(item.system_A, item.system_b)[0]
            skill_val = mod.solve(item.system_A, item.system_b)[0]
            rows.append(_row("matrix-operations", "matrix_operations_logic.py",
                             "solve", core_val, skill_val,
                             "first component of c = A^-1 b"))
        except Exception as e:  # pragma: no cover
            rows.append(_row_err("matrix-operations",
                                 "matrix_operations_logic.py", "solve", e))
    return rows


def _provenance(rows):
    ok_rows = [r for r in rows if r.get("dispatched") and not r.get("error")]
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/numerical_analysis_core.py",
            "functions": ["trapezoid", "simpson",
                          "richardson_error_trapezoid", "newton_raphson",
                          "bisection", "convergence_verdict", "solve",
                          "condition_number", "build_report",
                          "check_report"],
            "version": "0.1.0",
        },
        "skills": rows,
        "cross_checked": bool(ok_rows) and all(r.get("agrees")
                                               for r in ok_rows),
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def _parse_csv_floats(text):
    return [float(t) for t in str(text).split(",") if t.strip()]


def cmd_build(args):
    item = core.example_item()
    # allow re-verifying different code reports from the CLI
    if args.code_integral is not None:
        item.code_integral = args.code_integral
    if args.code_integral_tol is not None:
        item.code_integral_tol = args.code_integral_tol
    if args.code_mach is not None:
        item.code_mach = args.code_mach
    if args.code_mach_tol is not None:
        item.code_mach_tol = args.code_mach_tol
    if args.code_solve:
        vals = _parse_csv_floats(args.code_solve)
        if len(vals) != len(item.system_b):
            print("error: --code-solve needs %d comma-separated values"
                  % len(item.system_b))
            return 1
        item.code_solution = vals
    if args.code_solve_tol is not None:
        item.code_solve_tol = args.code_solve_tol

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

    rows = []
    if not args.no_dispatch:
        rows = _run_crosschecks(item, model)

    if args.out:
        with open(args.out, "w") as f:
            f.write(md if md.endswith("\n") else md + "\n")
        print("built Numerical Methods Verification Memo -> %s" % args.out)
        for c in model["checks"]:
            print("  %-12s verdict=%-4s discrepancy=%.6g (tol %g)"
                  % (c["operation"][:12], c["verdict"], c["discrepancy"],
                     c["code_tolerance"]))
        conv = model["convergence"]
        print("  grid study: p=%s gci=%s verdict=%s"
              % (conv["observed_order"], conv["gci_fraction"],
                 conv["verdict"]))
        print("gates: all_pass=%s %s" % (gates["all_pass"], gates))
        if profile:
            print("profile: %s / %s" % (profile.get("customer"),
                                        profile.get("program")))
        if args.bundle:
            prov = _provenance(rows)
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "Numerical Methods Verification Memo", model, gates, prov)
            print("bundle: model=%s" % paths["model"])
            print("        gates=%s" % paths["gates"])
            print("        provenance=%s" % paths["provenance"])
            if rows:
                for r in rows:
                    if r.get("dispatched") and not r.get("error"):
                        print("cross-check: %-32s core=%-12s skill=%-12s "
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
    gates = core.check_report_markdown(md)
    for name, ok in gates.items():
        if name != "all_pass":
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print(f"RESULT: {'PASS' if gates['all_pass'] else 'FAIL'}")
    return 0 if gates["all_pass"] else 1


def main():
    p = argparse.ArgumentParser(
        description="Numerical Analysis Engineer role: numerical methods "
                    "verification memo")
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
    b.add_argument("--code-integral", type=float, default=None,
                   help="code-reported integral (N) to re-verify")
    b.add_argument("--code-integral-tol", type=float, default=None,
                   help="code-claimed integral tolerance (N)")
    b.add_argument("--code-mach", type=float, default=None,
                   help="code-reported subsonic Mach root to re-verify")
    b.add_argument("--code-mach-tol", type=float, default=None,
                   help="code-claimed root residual tolerance")
    b.add_argument("--code-solve", default="",
                   help="code-reported solution as c0,c1 to re-verify")
    b.add_argument("--code-solve-tol", type=float, default=None,
                   help="code-claimed solve component tolerance")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="verification memo markdown to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
