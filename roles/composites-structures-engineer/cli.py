#!/usr/bin/env python3
"""cli.py - run the Composite Structures Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--basis <A|B>]
                       [--env-factor <f>] [--bvid-factor <f>]
                       [--bundle] [--profile <p.json>] [--no-dispatch]
    # build the composite structure analysis + certification report
    # --bundle      also emit evidence/{model,gates,provenance}.json
    #               (docs/PROTOCOL.md) with skill-dispatch cross-checks
    # --profile     apply a customer/program profile
  python3 cli.py check --file <file.md>
    # gate-check an existing report (exit 0 = PASS, 1 = FAIL)

The role ENGINE (core/composites_structures_core.py) does the work
STANDALONE: CLT laminate stiffness (A and D), per-ply Tsai-Wu and
max-stress failure indices, first-ply-failure reserve, hygrothermal
response, and plate buckling margins. When AeroSkills is present
(AEROSKILLS_DEV or ~/AeroSkills) the CLI dispatches the bound
structures/composites leaf logic and cross-checks each stage against
the core's own computation - two independent implementations agreeing
is recorded in provenance.json.
"""
import argparse
import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "scripts"))
import composites_structures_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "composites-structures-engineer"
AEROSKILLS = os.environ.get("AEROSKILLS_DEV",
                            os.path.expanduser("~/AeroSkills"))
COMPOSITES = os.path.join(AEROSKILLS, "skills", "structures", "composites")
SKILLS_RELEASE = "v1.3.0+"


def _load_logic(leaf, logic_file):
    """Import one bound leaf's logic module if present (stdlib only)."""
    path = os.path.join(COMPOSITES, leaf, "scripts", logic_file)
    if not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location("role_dispatch_" + leaf,
                                                  path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _dispatch_row(leaf, logic_file, function, cross_check_point, args,
                  kwargs, core_fn, description, tol_rel=1e-6,
                  pick=None):
    """Run one bound leaf function and compare with the core value.

    core_fn: zero-arg callable returning the core's computed value.
    args/kwargs are passed identically to the leaf function. pick maps
    the leaf's raw return (tuple/list/dict) to the scalar being
    compared (default: identity). Returns a provenance row (or None
    when dispatch is unavailable).
    """
    mod = _load_logic(leaf, logic_file)
    if mod is None or not hasattr(mod, function):
        return None
    try:
        raw = getattr(mod, function)(*args, **kwargs)
        skill_value = raw if pick is None else pick(raw)
        core_value = core_fn()
        if not isinstance(skill_value, (int, float)) or \
           not isinstance(core_value, (int, float)):
            return None
        delta = abs(float(core_value) - float(skill_value))
        tol = max(1e-9, tol_rel * abs(float(core_value)))
        return {
            "leaf": "structures/composites/" + leaf,
            "skill_md": "SKILL.md",
            "logic_file": "scripts/" + logic_file,
            "function": function,
            "dispatched": True,
            "cross_check_point": cross_check_point,
            "core_value": round(float(core_value), 9),
            "skill_value": round(float(skill_value), 9),
            "delta": round(delta, 12),
            "agrees": delta <= tol,
            "tolerance": tol_rel,
            "skills_release": SKILLS_RELEASE,
        }
    except Exception as e:
        return {"leaf": "structures/composites/" + leaf,
                "logic_file": "scripts/" + logic_file,
                "function": function, "dispatched": True,
                "cross_check_point": cross_check_point,
                "error": str(e), "agrees": False}


def _dispatch_all(item, model):
    """Dispatch the bound composite logic leaves and cross-check the
    core's numbers for every analysis stage."""
    st = model["stiffness"]
    fl = model["failure"]
    hy = model["hygrothermal"]
    sb = model["stability"]
    mat = item.material
    mpa = core.material_mpa(mat)
    plies = item.ply_list()
    angles_deg = [th for th, _ in plies]

    # ---- stage: laminate stiffness (A matrix, N/m) ----
    row_a = _dispatch_row(
        "laminate-stiffness", "laminate_stiffness_logic.py",
        "laminate_a_matrix",
        "CLT in-plane A11 of the [45/-45/0/90]2s stack",
        [plies], {"e1": mat["e1_pa"], "e2": mat["e2_pa"],
                  "nu12": mat["nu12"], "g12": mat["g12_pa"]},
        lambda: st["a11_n_per_m"],
        "laminate stiffness A11",
        pick=lambda r: r[0])

    # ---- stage: failure criteria at the governing ply (MPa) ----
    gov = next(r for r in fl["per_ply"]
               if r["angle"] == fl["governing_ply_deg"])
    row_tw = _dispatch_row(
        "failure-criteria", "failure_criteria_logic.py", "tsai_wu_index",
        "Tsai-Wu index at the governing 0-deg ply stress state",
        [gov["s1_mpa"], gov["s2_mpa"], gov["t12_mpa"]],
        {"Xt": mat["xt_mpa"], "Xc": mat["xc_mpa"], "Yt": mat["yt_mpa"],
         "Yc": mat["yc_mpa"], "S": mat["s_mpa"]},
        lambda: next(r["tsai_wu"] for r in fl["per_ply"]
                     if r["angle"] == fl["governing_ply_deg"]),
        "Tsai-Wu failure index")
    row_ms = _dispatch_row(
        "failure-criteria", "failure_criteria_logic.py", "max_stress_index",
        "max-stress index at the governing 0-deg ply stress state",
        [gov["s1_mpa"], gov["s2_mpa"], gov["t12_mpa"]],
        {"Xt": mat["xt_mpa"], "Xc": mat["xc_mpa"], "Yt": mat["yt_mpa"],
         "Yc": mat["yc_mpa"], "S": mat["s_mpa"]},
        lambda: next(r["max_stress"] for r in fl["per_ply"]
                     if r["angle"] == fl["governing_ply_deg"]),
        "max-stress failure index")

    # ---- stage: first-ply-failure chain (MPa, N/mm, mm) ----
    q = core.q_matrix_from_constants(mpa["e1"], mpa["e2"], mpa["nu12"],
                                     mpa["g12"])
    allowables = (mpa["xt"], mpa["xc"], mpa["yt"], mpa["yc"], mpa["s"])
    a_mm = core.a_matrix_from_plies(angles_deg, q, item.t_ply_m * 1e3)
    a_inv = core.a_inverse_compliance(*a_mm)
    row_fpf = _dispatch_row(
        "laminate-first-ply-failure",
        "laminate_first_ply_failure_logic.py", "ply_failure_indices",
        "per-ply Tsai-Wu indices under the ultimate resultants (max)",
        [angles_deg, q, allowables],
        {"nx": fl["load_case_n_per_mm"]["nx"],
         "ny": fl["load_case_n_per_mm"]["ny"],
         "nxy": fl["load_case_n_per_mm"]["nxy"],
         "a_components": a_inv},
        lambda: max(fl["tsai_wu_indices"]),
        "first-ply-failure Tsai-Wu max index",
        pick=max)

    # ---- stage: plate buckling (N*m, m, N/m) ----
    row_bk = _dispatch_row(
        "laminate-plate-buckling", "laminate_plate_buckling_logic.py",
        "buckling_margin",
        "simply-supported panel critical-load margin at ultimate",
        [st["d11_n_m"], st["d22_n_m"], st["d12_n_m"], st["d66_n_m"],
         item.panel_a_m, item.panel_b_m, sb["applied_n_per_m"]], {},
        lambda: sb["margin"],
        "plate buckling margin")

    # ---- stage: hygrothermal response (raw SI CLT) ----
    hy_plies = []
    for th, t in plies:
        hy_plies.append({"e1": mat["e1_pa"], "e2": mat["e2_pa"],
                         "nu12": mat["nu12"], "g12": mat["g12_pa"],
                         "theta_deg": th, "t": t,
                         "alpha_1": mat["alpha_1"],
                         "alpha_2": mat["alpha_2"],
                         "beta_1": mat["beta_1"],
                         "beta_2": mat["beta_2"]})
    row_hy = _dispatch_row(
        "laminate-hygrothermal-response",
        "laminate_hygrothermal_response_logic.py", "laminate_cte_cme",
        "laminate CTE alpha_x by the exact 2x2 CLT inversion",
        [hy_plies], {},
        lambda: hy["alpha_x_ppm"] * 1e-6,
        "laminate CTE alpha_x (raw 1/K)",
        pick=lambda r: r["alpha_x"])

    # ---- stage: allowables knockdown (B-basis design value) ----
    row_kd = _dispatch_row(
        "cmh17-allowables", "cmh17_allowables_logic.py", "knockdown",
        "B-basis Xc design allowable after env/BVID knockdowns",
        [mat["xc_mpa"]], {"env_factor": item.env_factor,
                          "bvid_factor": item.bvid_factor,
                          "hole_factor": item.hole_factor},
        lambda: fl["knockdown"]["xc_mpa"],
        "knockdowned Xc allowable",
        pick=lambda r: r[0])

    return [r for r in (row_a, row_tw, row_ms, row_fpf, row_bk, row_hy,
                        row_kd) if r is not None]


def _provenance(dispatch_rows):
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/composites_structures_core.py",
            "functions": ["laminate_a_matrix", "laminate_d_matrix",
                          "tsai_wu_index", "max_stress_index",
                          "ply_failure_indices", "laminate_cte_cme",
                          "buckling_margin", "knockdown", "build_report"],
            "version": "0.1.0",
        },
        "skills": dispatch_rows,
        "cross_checked": bool(dispatch_rows) and all(
            r.get("agrees", False) for r in dispatch_rows),
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def cmd_build(args):
    item = core.example_item()
    if args.basis:
        item.allowables_basis = args.basis
    if args.env_factor is not None:
        item.env_factor = args.env_factor
    if args.bvid_factor is not None:
        item.bvid_factor = args.bvid_factor
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

    rows = []
    if not args.no_dispatch:
        rows = _dispatch_all(item, model)
        for r in rows:
            if r.get("error"):
                print("dispatch %s: ERROR %s" % (r["function"], r["error"]))

    if args.out:
        with open(args.out, "w") as f:
            f.write(md if md.endswith("\n") else md + "\n")
        print("built composite structure analysis + certification "
              "report -> %s" % args.out)
        print("basis: %s  buckling margin=%.2f  knockdowned basis RF=%.2f"
              % (item.allowables_basis, model["stability"]["margin"],
                 model["failure"]["knockdowned_basis_rf"]))
        print("gates: all_pass=%s %s" % (gates["all_pass"], gates))
        if args.bundle:
            prov = _provenance(rows)
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "composite structure analysis + certification report",
                model, gates, prov)
            print("bundle: model=%s" % paths["model"])
            print("        gates=%s" % paths["gates"])
            print("        provenance=%s" % paths["provenance"])
            if rows:
                n_agree = sum(1 for r in rows if r.get("agrees"))
                print("cross-check: %d/%d rows agree"
                      % (n_agree, len(rows)))
                for r in rows:
                    print("  %-24s core=%-12s skill=%-12s delta=%s "
                          "agrees=%s"
                          % (r["function"], r["core_value"],
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
    gates = core.check_report_markdown(md)
    for name, ok in gates.items():
        if name != "all_pass":
            print("%s  %s" % ("PASS" if ok else "FAIL", name))
    print("RESULT: %s" % ("PASS" if gates["all_pass"] else "FAIL"))
    return 0 if gates["all_pass"] else 1


def main():
    p = argparse.ArgumentParser(
        description="Composite Structures Engineer role")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="",
                   help="output file (default: stdout)")
    b.add_argument("--basis", default="",
                   help="allowable basis A or B (default: B)")
    b.add_argument("--env-factor", type=float, default=None,
                   help="environmental knockdown factor (default: 0.90)")
    b.add_argument("--bvid-factor", type=float, default=None,
                   help="BVID knockdown factor (default: 0.85)")
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
