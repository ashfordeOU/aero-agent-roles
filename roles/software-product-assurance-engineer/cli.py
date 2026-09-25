#!/usr/bin/env python3
"""cli.py - run the Software Product Assurance Engineer role.

Usage:
  python3 cli.py build --out matrix.md
      # the bundled worked example (example/): category B on-board
      # software at PDR, evidence index, stub documents, review pack,
      # measurement set
  python3 cli.py build --out matrix.md --evidence evidence.csv \\
      --category B [--docs DIR] [--review PDR] [--pack pack.csv] \\
      [--metrics metrics.csv] [--scope reuse,suppliers] \\
      [--security-sensitive] [--clauses customer-list.csv] [--bundle]
      # a real project; --severity I --provision hardware derives the
      # category instead of --category
  python3 cli.py check --file matrix.md
      # gate-check a matrix (a draft, or one a human has signed)

Every output is a DRAFT that ends at the stop line: human sign-off
required. The role never marks a matrix approved.

The role ENGINE (core/software_product_assurance_core.py) does the work
standalone. When AEROSKILLS_DEV points at an aero-agent-skills checkout or
installed package, the CLI also dispatches the bound q80 leaves and
cross-checks the engine against them (recorded in provenance.json).

Author: ashfordeOU
"""
import argparse
import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "core"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                "..", "..", "scripts"))
import software_product_assurance_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "software-product-assurance-engineer"
DELIVERABLE = "ECSS-Q-ST-80C Rev.2 software product assurance compliance matrix"
ECSS = "space-systems/ecss/"
Q80_LEAVES = (
    "q80-compliance-matrix",
    "q80-software-criticality-tailoring",
    "q80-milestone-assurance-evidence",
    "q80-software-product-assurance-plan",
    "q80-software-product-quality-metrics",
    "q80-software-process-assurance",
)
HOW_TO_POINT = (
    "To cross-check against the bound skills, point AEROSKILLS_DEV at an "
    "aero-agent-skills checkout, or at an installed package that carries "
    "the q80 leaves:\n"
    "    npm install aero-agent-skills\n"
    "    export AEROSKILLS_DEV=\"$(npm root)/aero-agent-skills\"\n"
    "    (a global install: export AEROSKILLS_DEV=\"$(npm root -g)/"
    "aero-agent-skills\")")


class InputError(Exception):
    pass


# ---------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------

def _read(path, what):
    if not os.path.isfile(path):
        raise InputError("%s not found: %s" % (what, path))
    with open(path, encoding="utf-8-sig") as f:
        return f.read()


def _label(path, folder=False):
    """A basename label: absolute paths never reach the deliverable."""
    base = os.path.basename(os.path.normpath(path))
    return base + "/" if folder else base


def _flags(value):
    out = []
    for part in (value or "").replace(";", ",").split(","):
        if part.strip():
            out.append(part.strip())
    return out


def gather(args):
    """Build the ProjectInputs from the command line (or the example)."""
    if not args.evidence:
        if args.docs or args.pack or args.metrics or args.clauses:
            raise InputError("--docs, --pack, --metrics and --clauses need "
                             "--evidence (without --evidence the bundled "
                             "worked example is used)")
        item = core.example_item()
        if args.category:
            item.category, item.severity = args.category, None
        if args.severity:
            item.severity, item.category = args.severity, None
            item.provisions = args.provision or []
        if args.review:
            item.review = args.review
        if args.scope:
            item.scope = _flags(args.scope)
        if args.security_sensitive:
            item.security_sensitive = True
        return item
    if not (args.category or args.severity):
        raise InputError("give the software criticality category "
                         "(--category A-D) or the function severity to "
                         "derive it (--severity I-IV [--provision hardware])")
    item = core.ProjectInputs(
        project=args.project or "",
        category=args.category or None, severity=args.severity or None,
        provisions=args.provision or [],
        provides_provision_for=args.provides_provision_for or None,
        security_sensitive=args.security_sensitive,
        scope=_flags(args.scope), review=args.review or None,
        evidence_text=_read(args.evidence, "evidence CSV"),
        evidence_label=_label(args.evidence))
    if args.clauses:
        try:
            item.clauses = core.parse_clause_list(
                _read(args.clauses, "clause list"))
        except ValueError as e:
            raise InputError("clause list %s: %s" % (args.clauses, e))
        item.clause_label = "customer clause list %s" % _label(args.clauses)
    if args.docs:
        if not os.path.isdir(args.docs):
            raise InputError("document folder not found: %s" % args.docs)
        item.docs_files = core.list_documents(args.docs)
        item.docs_label = _label(args.docs, folder=True)
    if args.pack:
        item.pack_text = _read(args.pack, "review pack CSV")
        item.pack_label = _label(args.pack)
        if not item.review:
            raise InputError("--pack needs --review (the review it is for)")
    if args.metrics:
        item.metrics_text = _read(args.metrics, "metrics CSV")
        item.metrics_label = _label(args.metrics)
    return item


# ---------------------------------------------------------------------------
# cross-check against the bound q80 leaves (optional)
# ---------------------------------------------------------------------------

def _skills_root():
    return os.environ.get("AEROSKILLS_DEV", "").strip()


def _load_leaf(root, leaf):
    """Import a leaf's *_logic.py module, or None."""
    logic_dir = os.path.join(root, "skills", ECSS + leaf, "scripts")
    if not os.path.isdir(logic_dir):
        return None
    for f in sorted(os.listdir(logic_dir)):
        if f.endswith("_logic.py") and not f.startswith("test_"):
            spec = importlib.util.spec_from_file_location(
                "spa_dispatch_" + leaf.replace("-", "_"),
                os.path.join(logic_dir, f))
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
            except Exception:
                return None
            return mod
    return None


def skills_status():
    """(root or None, loaded modules, reason when nothing can be loaded)."""
    root = _skills_root()
    if not root:
        return None, {}, "AEROSKILLS_DEV is not set"
    if not os.path.isdir(os.path.join(root, "skills")):
        return None, {}, "AEROSKILLS_DEV has no skills/ folder: %s" % root
    mods = {leaf: _load_leaf(root, leaf) for leaf in Q80_LEAVES}
    if not any(mods.values()):
        return None, {}, ("the skills at AEROSKILLS_DEV carry no q80 leaves "
                          "(an older release?)")
    return root, mods, ""


def _row(rows, leaf, function, core_val, skill_val, detail=""):
    rows.append({"leaf": ECSS + leaf, "function": function,
                 "dispatched": True, "core_value": core_val,
                 "skill_value": skill_val, "agrees": core_val == skill_val,
                 "detail": detail})


def _guard(rows, leaf, function, fn):
    try:
        fn()
    except Exception as e:   # a leaf that throws is a disagreement, not a crash
        rows.append({"leaf": ECSS + leaf, "function": function,
                     "dispatched": True, "error": str(e)[:200],
                     "agrees": False})


def dispatch_rows(item, model, mods):
    """Run the same computation in the bound leaf and compare.

    Every comparison is made on the engine's output BEFORE the role's own
    additions (the document trace), because that layer has no counterpart
    in the leaves.
    """
    rows = []
    cat, sec = model["category"], model["security_sensitive"]
    scope = tuple(model["scope"])
    review = model["review"]
    ev_text = item.evidence_text
    clauses = (item.clauses if item.clauses is not None
               else core.default_clauses())

    m = mods.get("q80-compliance-matrix")
    if m is not None:
        def matrix():
            plain = core.build_matrix(clauses, core.parse_evidence_csv(ev_text),
                                      cat, sec)
            sk = m.build_matrix([{"id": c, "title": t} for c, t in clauses],
                                m.index_evidence(m.parse_evidence_csv(ev_text)),
                                category=cat, security_sensitive=sec)
            mine = [(r["clause"], r["status"], r["tailoring"], r["gaps"])
                    for r in plain["rows"]]
            theirs = [(r["clause"], r["status"], r["tailoring"], r["gaps"])
                      for r in sk["rows"]]
            differ = sum(1 for a, b in zip(mine, theirs) if a != b) + abs(
                len(mine) - len(theirs))
            _row(rows, "q80-compliance-matrix", "build_matrix.rows",
                 "%d rows" % len(mine),
                 "%d rows" % len(theirs) if not differ else
                 "%d rows, %d differ" % (len(theirs), differ))
            keys = ("clauses", "counts", "applicable", "compliant_fraction",
                    "evidenced_fraction", "rows_with_gaps")
            _row(rows, "q80-compliance-matrix", "coverage_summary",
                 {k: plain["coverage"][k] for k in keys},
                 {k: sk["coverage"][k] for k in keys})
            _row(rows, "q80-compliance-matrix", "find_gaps",
                 [(g["clause"], g["kind"]) for g in plain["gaps"]],
                 [(g["clause"], g["kind"]) for g in sk["gaps"]],
                 "%d gaps" % len(plain["gaps"]))
            _row(rows, "q80-compliance-matrix", "orphan_evidence",
                 plain["orphan_evidence"], sk["orphan_evidence"])
        _guard(rows, "q80-compliance-matrix", "build_matrix", matrix)

    t = mods.get("q80-software-criticality-tailoring")
    if t is not None:
        def tailoring():
            der = model["category_derivation"]
            if der:
                sk = t.assign_category(der["severity"], der["provisions"],
                                       item.provides_provision_for or None)
                _row(rows, "q80-software-criticality-tailoring",
                     "assign_category", der["category"], sk["category"])
            counts = {"applicable": 0, "reduced": 0, "not-applicable": 0}
            for r in t.tailoring_matrix(cat, sec):
                counts[r["status"]] += 1
            _row(rows, "q80-software-criticality-tailoring",
                 "tailoring_matrix", model["tailoring"]["totals"], counts)
        _guard(rows, "q80-software-criticality-tailoring", "tailoring",
               tailoring)

    ms = mods.get("q80-milestone-assurance-evidence")
    if ms is not None and review:
        def milestone():
            mine = [(d["document"], d["clauses"])
                    for d in core.evidence_due(review, cat, scope)]
            sk = [(d["document"], d["clauses"])
                  for d in ms.evidence_due(review, cat, scope)]
            _row(rows, "q80-milestone-assurance-evidence", "evidence_due",
                 mine, sk, "%d documents owed" % len(mine))
            pk = model["milestone"]["pack"]
            if pk is not None:
                sub = [{"document": p["document"], "maturity": p["maturity"]}
                       for p in core.parse_pack_csv(item.pack_text)]
                _row(rows, "q80-milestone-assurance-evidence",
                     "assess_review_pack", pk,
                     ms.assess_review_pack(review, cat, sub, scope))
            inputs = core.spamr_inputs(model["matrix"], model["metrics"])
            sk_sp = ms.spamr_skeleton(review, inputs)
            _row(rows, "q80-milestone-assurance-evidence", "spamr_skeleton",
                 [(s["id"], s["status"]) for s in model["spamr"]["sections"]],
                 [(s["id"], s["status"]) for s in sk_sp["sections"]])
        _guard(rows, "q80-milestone-assurance-evidence", "milestone",
               milestone)

    p = mods.get("q80-software-product-assurance-plan")
    if p is not None and review and review in core.PLAN_MATURITY_BY_REVIEW:
        _guard(rows, "q80-software-product-assurance-plan",
               "plan_maturity_due", lambda: _row(
                   rows, "q80-software-product-assurance-plan",
                   "plan_maturity_due",
                   model["milestone"]["spap_maturity_due"],
                   p.plan_maturity_due(review)))

    q = mods.get("q80-software-product-quality-metrics")
    if q is not None and model["metrics"] is not None:
        def metrics():
            meas = core.parse_metrics_csv(item.metrics_text)
            sk = q.evaluate_metrics(meas, cat)
            key = ("metric", "value", "threshold", "status", "margin")
            _row(rows, "q80-software-product-quality-metrics",
                 "evaluate_metrics",
                 [tuple(r[k] for k in key) for r in model["metrics"]["rows"]]
                 + [model["metrics"]["verdict"]],
                 [tuple(r[k] for k in key) for r in sk["rows"]]
                 + [sk["verdict"]])
        _guard(rows, "q80-software-product-quality-metrics",
               "evaluate_metrics", metrics)
    return rows


def _provenance(rows, reason):
    return {
        "role": ROLE_SLUG,
        "generator": "core/software_product_assurance_core.py",
        "core": {
            "file": "core/software_product_assurance_core.py",
            "functions": ["derive_category", "tailoring_summary",
                          "build_matrix", "apply_document_trace",
                          "milestone_check", "assess_review_pack",
                          "spamr_skeleton", "evaluate_metrics",
                          "build_report", "check_report"],
            "version": core.__version__,
        },
        "skills": rows,
        "skills_not_dispatched_reason": reason,
        "cross_checked": bool(rows) and all(r.get("agrees") for r in rows),
        "disclaimer": "DRAFT for human review. Not an approval, not a "
                      "certification, not a statement of compliance.",
    }


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_build(args):
    try:
        item = gather(args)
        model = core.build_report(item)
    except (InputError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 2

    root, mods, reason = (None, {}, "--no-dispatch given") \
        if args.no_dispatch else skills_status()
    if args.require_cross_check and not mods:
        print("error: cross-check required but not possible: %s.\n%s"
              % (reason, HOW_TO_POINT), file=sys.stderr)
        return 2

    md = core.render_report_markdown(model)
    profile = None
    try:
        profile = evidence.load_profile(args.profile)
    except ValueError as e:
        print("error: bad profile: %s" % e, file=sys.stderr)
        return 2
    if profile:
        model["profile"] = {k: profile.get(k) for k in (
            "customer", "program", "basis", "authority", "der",
            "document_prefix", "revision")}
        md = evidence.profile_header_block(profile) + md

    gates = core.check_report(model)
    rows = dispatch_rows(item, model, mods) if mods else []

    if not args.out:
        sys.stdout.write(md)
        return 0 if gates["all_pass"] else 1

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(md)
    csv_path = args.csv or os.path.splitext(args.out)[0] + ".csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        f.write(core.render_matrix_csv(model))

    mx = model["matrix"]
    if item.example:
        print("using the bundled worked example (example/): invented "
              "project, not a real mission")
    print("built compliance matrix (DRAFT) -> %s" % args.out)
    print("  csv -> %s" % csv_path)
    if profile:
        print("  profile: %s / %s" % (profile.get("customer"),
                                      profile.get("program")))
    print("  standard: %s; software category %s%s" % (
        core.STANDARD, model["category"],
        " (derived from severity %s)" % model["category_derivation"][
            "severity"] if model["category_derivation"] else ""))
    for n in model["category_notes"]:
        print("  open point: %s" % n)
    print("  " + core.coverage_line(mx["coverage"]))
    print("  open gaps: %d" % len(mx["gaps"]))
    tr = mx["trace"]
    if tr["ran"]:
        print("  document trace: %d cited, %d found, %d missing%s" % (
            tr["cited"], len(tr["found"]), len(tr["missing"]),
            (" (" + ", ".join(tr["missing"]) + ")") if tr["missing"] else ""))
    else:
        print("  document trace: not run (no --docs folder given)")
    ms = model["milestone"]
    if ms:
        line = "  %s: %d documents owed" % (ms["review"].upper(),
                                            len(ms["owed"]))
        if ms["pack"]:
            pk = ms["pack"]
            line += "; pack missing %d, immature %d, complete %s" % (
                len(pk["missing"]), len(pk["immature"]),
                "yes" if pk["complete"] else "no")
        print(line)
    if model["metrics"]:
        mt = model["metrics"]
        print("  metrics: %s (failing %d, not measured %d)" % (
            mt["verdict"], len(mt["failing"]), len(mt["missing"])))
    print("  gates: all_pass=%s" % gates["all_pass"])
    if not gates["all_pass"]:
        print("  failing gates: %s" % ", ".join(
            k for k, v in gates.items() if k != "all_pass" and not v))

    disagree = [r for r in rows if not r.get("agrees")]
    if rows:
        print("  dispatch cross-check: %d/%d agree against the bound q80 "
              "leaf logic" % (len(rows) - len(disagree), len(rows)))
        for r in disagree:
            print("    DISAGREE %s %s: %s" % (
                r["leaf"].rsplit("/", 1)[-1], r["function"],
                r.get("error") or "core and skill differ"))
    else:
        print("  dispatch cross-check: not dispatched (%s). The matrix is "
              "complete without it." % reason)
        if not args.no_dispatch:
            for line in HOW_TO_POINT.splitlines():
                print("  " + line)
    if args.bundle:
        paths = evidence.write_bundle(args.out, ROLE_SLUG, DELIVERABLE,
                                      model, gates,
                                      _provenance(rows, reason))
        print("  bundle: model=%s" % paths["model"])
        print("          gates=%s" % paths["gates"])
        print("          provenance=%s" % paths["provenance"])
    print(core.STOP_LINE)
    if disagree:
        return 1
    return 0 if gates["all_pass"] else 1


def cmd_check(args):
    if not os.path.exists(args.file):
        print("file not found: %s" % args.file)
        return 1
    with open(args.file, encoding="utf-8") as f:
        md = f.read()
    gates = core.check_report_markdown(md)
    for name, ok in gates.items():
        if name in ("all_pass", "sign_off"):
            continue
        print("%s  %s" % ("PASS" if ok else "FAIL", name))
    so = gates["sign_off"]
    if so["state"] == "unsigned":
        print("SIGN-OFF: none recorded. " + core.STOP_LINE)
    else:
        print("SIGN-OFF: %s by %s (%s) on %s" % (
            so["decision"] or "?", so["signatory"] or "?", so["role"] or "?",
            so["date"] or "?"))
        for e in so["errors"]:
            print("  sign-off problem: %s" % e)
    print("RESULT: %s" % ("PASS" if gates["all_pass"] else "FAIL"))
    return 0 if gates["all_pass"] else 1


def main():
    p = argparse.ArgumentParser(
        description="Software Product Assurance Engineer role "
                    "(ECSS-Q-ST-80C Rev.2 compliance matrix)")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="build the compliance matrix (DRAFT)")
    b.add_argument("--out", default="",
                   help="Markdown output (default: stdout); the CSV goes "
                        "beside it")
    b.add_argument("--csv", default="", help="CSV output path")
    b.add_argument("--evidence", default="",
                   help="evidence CSV: clause,document,section,status,"
                        "justification (omit for the bundled example)")
    b.add_argument("--category", default="",
                   help="software criticality category A-D")
    b.add_argument("--severity", default="",
                   help="highest function severity I-IV (derives the "
                        "category)")
    b.add_argument("--provision", action="append", default=[],
                   help="compensating provision at system level: hardware, "
                        "software or operational-procedure (repeatable)")
    b.add_argument("--provides-provision-for", default="",
                   help="severity of the functions this software is itself "
                        "the compensating provision for")
    b.add_argument("--security-sensitive", action="store_true",
                   help="the software is security sensitive")
    b.add_argument("--scope", default="",
                   help="comma list: suppliers, procured, reuse, security, "
                        "operations")
    b.add_argument("--review", default="",
                   help="target review: SRR, PDR, CDR, TRR, QR, AR or ORR")
    b.add_argument("--docs", default="",
                   help="the project's document folder: every cited "
                        "document must resolve to a file in it")
    b.add_argument("--pack", default="",
                   help="review pack CSV: document (kind),maturity")
    b.add_argument("--metrics", default="",
                   help="measurement set CSV: metric,value")
    b.add_argument("--clauses", default="",
                   help="customer clause list (one id per line or id,title "
                        "CSV); default: every requirement of the standard")
    b.add_argument("--project", default="", help="project name")
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json")
    b.add_argument("--profile", default="",
                   help="program profile JSON (docs/PROFILE-SCHEMA.md)")
    b.add_argument("--no-dispatch", action="store_true",
                   help="skip the cross-check against the bound skills")
    b.add_argument("--require-cross-check", action="store_true",
                   help="fail (exit 2) when the bound skills cannot be "
                        "dispatched")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check", help="gate-check a matrix file")
    c.add_argument("--file", required=True,
                   help="compliance matrix Markdown to gate-check")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
