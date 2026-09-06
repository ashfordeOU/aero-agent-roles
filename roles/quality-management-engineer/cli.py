#!/usr/bin/env python3
"""cli.py - run the Quality Management Engineer role.

Usage:
  python3 cli.py build [--out <file.md>] [--bundle] [--no-dispatch]
                       [--profile <profile.json>]
    # build the AS9100 Quality Management System Audit Report for the
    # reference audit; --bundle also emits evidence/{model,gates,
    # provenance}.json (docs/PROTOCOL.md); --profile applies a program
    # profile (audited supplier context, docs/PROFILE-SCHEMA.md)
  python3 cli.py check --file <file.md>
    # gate-check an existing audit report (exit 0 = PASS)

The role ENGINE (core/quality_management_core.py) does the work
standalone: MSA (ANOVA and range-method gage R&R, bias/linearity,
attribute agreement), SPC (X-bar/R + capability, I-MR, CUSUM/EWMA,
p-chart) and acceptance sampling all computed from the raw datasets.
When Aero Skills is present (AEROSKILLS_DEV or ~/AeroSkills) the CLI
dispatches every bound as9100 leaf's logic and cross-checks the core's
values against the leaf's independent implementation - agreement is
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
import quality_management_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "quality-management-engineer"
AS9100 = os.path.join("manufacturing-quality", "as9100")
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))


def _load_leaf(leaf):
    """Import the leaf's *_logic.py module if present, else None."""
    logic_dir = os.path.join(AEROSKILLS, "skills", leaf, "scripts")
    if not os.path.isdir(logic_dir):
        return None
    for f in sorted(os.listdir(logic_dir)):
        if f.endswith("_logic.py") and not f.startswith("test_"):
            spec = importlib.util.spec_from_file_location(
                "role_dispatch_" + leaf.replace("/", "_").replace("-", "_"),
                os.path.join(logic_dir, f))
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
            except Exception:
                continue
            return mod
    return None


def _dispatch_rows(item, model):
    """Cross-check core values against the 10 bound leaf logic modules.

    Each row runs the SAME computation in the role core and in the bound
    Aero Skills leaf and records core_value, skill_value, delta, agrees.
    Rows are omitted (not failed) when the skills checkout is absent or a
    leaf has no logic file - standalone runs stay valid and honest.
    """
    msa, spc, sampling = model["msa"], model["spc"], model["sampling"]
    rows = []

    def row(leaf, function, core_val, skill_val, tolerance=1e-6):
        if isinstance(core_val, bool) or isinstance(skill_val, bool):
            same = bool(core_val) == bool(skill_val)
            delta = 0.0 if same else 1.0
        elif core_val is None and skill_val is None:
            same, delta = True, 0.0
        elif core_val is None or skill_val is None:
            same, delta = False, None
        else:
            delta = abs(float(core_val) - float(skill_val))
            same = delta <= tolerance
        rows.append({
            "leaf": leaf,
            "logic_file": "scripts/*_logic.py",
            "function": function,
            "dispatched": True,
            "core_value": core_val,
            "skill_value": skill_val,
            "delta": (round(delta, 9) if delta is not None else None),
            "agrees": same,
            "tolerance": tolerance,
        })

    # 1. gage R&R ANOVA -> percent_grr
    mod = _load_leaf(AS9100 + "/gage-rr-anova")
    if mod is not None:
        try:
            skill = mod.anova_grr_study(item.anova_study)["percent_grr"]
            row(AS9100 + "/gage-rr-anova", "anova_grr_study.percent_grr",
                round(msa["anova"]["percent_grr"], 6), round(skill, 6))
        except Exception as e:
            rows.append({"leaf": AS9100 + "/gage-rr-anova",
                         "function": "anova_grr_study", "dispatched": True,
                         "error": str(e)[:150], "agrees": False})

    # 2. range-method MSA -> grr_pct
    mod = _load_leaf(AS9100 + "/measurement-systems-analysis")
    if mod is not None:
        try:
            skill = mod.study_summary(item.range_table)["grr_pct"]
            row(AS9100 + "/measurement-systems-analysis",
                "study_summary.grr_pct",
                round(msa["range"]["percent_grr"], 6), round(skill, 6))
        except Exception as e:
            rows.append({"leaf": AS9100 + "/measurement-systems-analysis",
                         "function": "study_summary", "dispatched": True,
                         "error": str(e)[:150], "agrees": False})

    # 3. bias/linearity -> mean bias
    mod = _load_leaf(AS9100 + "/gage-linearity-bias-study")
    if mod is not None:
        try:
            skill = mod.gage_bias_linearity_study(item.mic_refs,
                                                  item.mic_biases)["mean_bias"]
            row(AS9100 + "/gage-linearity-bias-study",
                "gage_bias_linearity_study.mean_bias",
                round(msa["bias_linearity"]["mean_bias"], 6),
                round(skill, 6))
        except Exception as e:
            rows.append({"leaf": AS9100 + "/gage-linearity-bias-study",
                         "function": "gage_bias_linearity_study",
                         "dispatched": True, "error": str(e)[:150],
                         "agrees": False})

    # 4. attribute agreement -> fleiss kappa
    mod = _load_leaf(AS9100 + "/attribute-agreement-analysis")
    if mod is not None:
        try:
            skill = mod.agreement_summary(
                ratings_matrix=item.ratings_matrix)["kappa"]
            row(AS9100 + "/attribute-agreement-analysis",
                "agreement_summary.kappa",
                round(msa["attribute"]["kappa"], 6), round(skill, 6))
        except Exception as e:
            rows.append({"leaf": AS9100 + "/attribute-agreement-analysis",
                         "function": "agreement_summary", "dispatched": True,
                         "error": str(e)[:150], "agrees": False})

    # 5. SPC capability -> cpk (capability_indices returns (cp,cpu,cpl,cpk))
    mod = _load_leaf(AS9100 + "/statistical-process-control")
    if mod is not None:
        try:
            xr = spc["xbar_r"]
            skill = mod.capability_indices(item.pin_usl, item.pin_lsl,
                                           xr["xbar"], xr["sigma_hat"])[3]
            row(AS9100 + "/statistical-process-control",
                "capability_indices.cpk", round(xr["cpk"], 6),
                round(skill, 6))
        except Exception as e:
            rows.append({"leaf": AS9100 + "/statistical-process-control",
                         "function": "capability_indices", "dispatched": True,
                         "error": str(e)[:150], "agrees": False})

    # 6. I-MR chart -> individuals UCL
    mod = _load_leaf(AS9100 + "/individuals-and-moving-range-chart")
    if mod is not None:
        try:
            skill = mod.imr_summary(item.coating)["x_ucl"]
            row(AS9100 + "/individuals-and-moving-range-chart",
                "imr_summary.x_ucl", round(spc["imr"]["x_ucl"], 6),
                round(skill, 6))
        except Exception as e:
            rows.append({"leaf": AS9100 + "/individuals-and-moving-range-chart",
                         "function": "imr_summary", "dispatched": True,
                         "error": str(e)[:150], "agrees": False})

    # 7. CUSUM/EWMA -> first signal index (None = in control)
    mod = _load_leaf(AS9100 + "/cusum-ewma-monitoring")
    if mod is not None:
        try:
            skill = mod.small_shift_monitoring_report(
                item.deviations, 0.0, 2.9)["verdict"]["first_signal_index"]
            row(AS9100 + "/cusum-ewma-monitoring",
                "small_shift_monitoring_report.verdict.first_signal_index",
                spc["shift_monitoring"]["first_signal_index"], skill)
        except Exception as e:
            rows.append({"leaf": AS9100 + "/cusum-ewma-monitoring",
                         "function": "small_shift_monitoring_report",
                         "dispatched": True, "error": str(e)[:150],
                         "agrees": False})

    # 8. p-chart -> UCL
    mod = _load_leaf(AS9100 + "/attribute-control-charts")
    if mod is not None:
        try:
            skill = mod.p_chart(item.np_counts, 200)["UCL"]
            row(AS9100 + "/attribute-control-charts", "p_chart.UCL",
                round(spc["p_chart"]["ucl"], 6), round(skill, 6))
        except Exception as e:
            rows.append({"leaf": AS9100 + "/attribute-control-charts",
                         "function": "p_chart", "dispatched": True,
                         "error": str(e)[:150], "agrees": False})

    # 9. attribute acceptance sampling -> OC probability at AQL
    mod = _load_leaf(AS9100 + "/acceptance-sampling")
    if mod is not None:
        try:
            a = sampling["attribute"]
            skill = mod.oc_acceptance_probability(a["n"], a["ac"],
                                                  item.attr_aql / 100.0)
            row(AS9100 + "/acceptance-sampling",
                "oc_acceptance_probability",
                round(a["oc_at_aql"], 6), round(skill, 6))
        except Exception as e:
            rows.append({"leaf": AS9100 + "/acceptance-sampling",
                         "function": "oc_acceptance_probability",
                         "dispatched": True, "error": str(e)[:150],
                         "agrees": False})

    # 10. variables acceptance sampling -> Q statistic
    mod = _load_leaf(AS9100 + "/variables-acceptance-sampling")
    if mod is not None:
        try:
            v = sampling["variables"]
            skill = mod.variables_sampling_decision(
                v["lot_size"], v["aql"], v["usl"], v["xbar"], v["s"])["Q"]
            row(AS9100 + "/variables-acceptance-sampling",
                "variables_sampling_decision.Q", round(v["Q"], 6),
                round(skill, 6))
        except Exception as e:
            rows.append({"leaf": AS9100 + "/variables-acceptance-sampling",
                         "function": "variables_sampling_decision",
                         "dispatched": True, "error": str(e)[:150],
                         "agrees": False})
    return rows


def _provenance(item, model, dispatch_rows):
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/quality_management_core.py",
            "functions": ["anova_grr_study", "study_summary",
                          "gage_bias_linearity_study", "fleiss_kappa",
                          "capability_indices", "imr_summary",
                          "small_shift_monitoring_report", "p_chart",
                          "oc_acceptance_probability",
                          "variables_sampling_decision", "build_report",
                          "check_report"],
            "version": "0.1.0",
        },
        "skills": dispatch_rows,
        "cross_checked": bool(dispatch_rows and all(
            r.get("agrees") for r in dispatch_rows)),
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def cmd_build(args):
    item = core.example_item()
    model = core.build_report(item)
    md = core.render_report_markdown(model)

    # program profile (audited supplier context): load + apply header
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

    dispatch_rows = []
    if not args.no_dispatch:
        dispatch_rows = _dispatch_rows(item, model)

    if args.out:
        with open(args.out, "w") as f:
            f.write(md if md.endswith("\n") else md + "\n")
        print("built QMS audit report for %s -> %s"
              % (model["site"]["name"], args.out))
        if profile:
            print("profile: %s / %s" % (profile.get("customer"),
                                        profile.get("program")))
        print("results: %%GRR %.2f (ANOVA) / %.2f (range), Cpk %.2f, "
              "kappa %.2f"
              % (model["msa"]["anova"]["percent_grr"],
                 model["msa"]["range"]["percent_grr"],
                 model["spc"]["xbar_r"]["cpk"],
                 model["msa"]["attribute"]["kappa"]))
        print("counts: %s" % model["counts"])
        print("gates: all_pass=%s %s" % (gates["all_pass"], gates))
        if args.bundle:
            prov = _provenance(item, model, dispatch_rows)
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "AS9100 Quality Management System Audit Report",
                model, gates, prov)
            print("bundle: model=%s" % paths["model"])
            print("        gates=%s" % paths["gates"])
            print("        provenance=%s" % paths["provenance"])
        agree = [r for r in dispatch_rows
                 if r.get("dispatched") and not r.get("error")]
        n_disagree = sum(1 for r in agree if not r.get("agrees"))
        if agree:
            print("dispatch cross-check: %d/%d agree against bound leaf "
                  "logic" % (len(agree) - n_disagree, len(agree)))
        else:
            print("dispatch cross-check: not dispatched "
                  "(no AeroSkills logic present)")
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
        description="Quality Management Engineer role (AS9100 QMS audit)")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="", help="output file (default: stdout)")
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json")
    b.add_argument("--no-dispatch", action="store_true",
                   help="skip dispatching bound AeroSkills logic")
    b.add_argument("--profile", default="",
                   help="program profile JSON (audited supplier context, "
                        "docs/PROFILE-SCHEMA.md)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="audit report markdown to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
