#!/usr/bin/env python3
"""cli.py - run the DO-254 Airborne Electronic Hardware Engineer role.

Usage:
  python3 cli.py build --out <file.md>          # build PHAC for the example item
  python3 cli.py build --out <file.md> --bundle # + evidence/{model,gates,provenance}.json
  python3 cli.py build --out <file.md> --bundle --profile <profile.json>
  python3 cli.py check --file <file.md>         # gate-check an existing PHAC

The role ENGINE (core/do254_hardware_core.py) does the work standalone;
bound avionics/do254 skills in Aero Skills deepen individual stages
when present and are dispatched for cross-check.
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
import do254_hardware_core as core  # noqa: E402
import evidence  # noqa: E402

ROLE_SLUG = "do254-hardware-engineer"
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
HAS_SKILLS = os.path.isdir(os.path.join(AEROSKILLS, "skills"))

# Bound avionics/do254 leaves and their logic files.
DO254_LEAVES = {
    "hardware-planning": "avionics/do254/hardware-planning",
    "verification": "avionics/do254/verification",
    "configuration-management": "avionics/do254/configuration-management",
    "requirements-capture": "avionics/do254/requirements-capture",
}


def _load_leaf(leaf: str):
    """Import a bound leaf's *logic.py module (or None when unavailable)."""
    if not HAS_SKILLS:
        return None
    logic_dir = os.path.join(AEROSKILLS, "skills", DO254_LEAVES[leaf], "scripts")
    if not os.path.isdir(logic_dir):
        return None
    logic_files = sorted(f for f in os.listdir(logic_dir)
                         if f.endswith("_logic.py"))
    if not logic_files:
        return None
    for lf in logic_files:
        path = os.path.join(logic_dir, lf)
        spec = importlib.util.spec_from_file_location(
            "do254_skill_" + leaf, path)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
            return mod
        except Exception:
            continue
    return None


def _dispatch_rows(item) -> list:
    """Dispatch the bound do254 skill logics and compare with the core.

    Cross-check points (each leaf that ships a logic file):
    1. hardware-planning: classify_aeh -> 'complex' for a programmable
       logic item (AEH classification).
    2. verification: coverage ratio adequate at the item's DAL (0.98 at B)
       and methods required for complex AEH at level B.
    3. configuration-management: change class for a class-1 change
       (functional change on complex hardware) + HCI entry format.
    4. requirements-capture: capture readiness score for the example
       requirements set.
    """
    rows = []
    item = item or core.example_item()
    dal = item.assurance_level()

    def add(leaf, function, core_value, skill_value, extra=None):
        if not isinstance(core_value, (int, float)) or \
           not isinstance(skill_value, (int, float)):
            agrees = str(core_value) == str(skill_value)
            delta = None
        else:
            delta = abs(float(core_value) - float(skill_value))
            agrees = delta <= 1e-6
        row = {
            "leaf": DO254_LEAVES[leaf],
            "skill_md": "SKILL.md",
            "logic_file": "scripts/" + os.path.basename(
                _leaf_logic_file(leaf) or ""),
            "function": function,
            "dispatched": True,
            "core_value": core_value if isinstance(core_value, (int, float))
                          else str(core_value),
            "skill_value": skill_value if isinstance(skill_value, (int, float))
                           else str(skill_value),
            "agrees": agrees,
            "skills_release": "v1.3.0+",
        }
        if delta is not None:
            row["delta"] = round(delta, 9)
            row["tolerance"] = 1e-6
        if extra:
            row["cross_check_point"] = extra
        rows.append(row)
        return row

    hp = _load_leaf("hardware-planning")
    if hp is not None and hasattr(hp, "classify_aeh"):
        add("hardware-planning", "classify_aeh",
            core.classify_aeh(item.has_programmable_logic,
                              item.has_internal_state,
                              item.fully_verifiable_from_top_data,
                              item.safety_significant),
            hp.classify_aeh(item.has_programmable_logic,
                            item.has_internal_state,
                            item.fully_verifiable_from_top_data,
                            item.safety_significant),
            "complex AEH classification for programmable-logic item")

    ver = _load_leaf("verification")
    if ver is not None and hasattr(ver, "requirements_based_coverage_ok"):
        # 196 of 200 requirements tested at DAL B -> 0.98 ratio met
        tested, total = 196, 200
        add("verification", "requirements_based_coverage_ok",
            int(core.coverage_adequate(dal, tested / total)),
            int(ver.requirements_based_coverage_ok(tested, total, dal,
                                                   min_ratio=0.98)),
            "requirements-based coverage 196/200 at DAL %s" % dal)
    if ver is not None and hasattr(ver, "verification_methods_for"):
        core_methods = sorted(core.verification_methods_for("complex", dal))
        skill_methods = sorted(ver.verification_methods_for("complex", dal))
        add("verification", "verification_methods_for",
            ",".join(core_methods), ",".join(skill_methods),
            "method set for complex AEH at DAL %s" % dal)
    if ver is not None and hasattr(ver, "independence_required"):
        add("verification", "independence_required",
            int(core.independence_required(dal)),
            int(ver.independence_required(dal)),
            "independence expectation at DAL %s" % dal)

    cm = _load_leaf("configuration-management")
    if cm is not None and hasattr(cm, "change_class"):
        change = {"hardware_class": "complex", "safety_effect": "major",
                  "functional_change": True}
        add("configuration-management", "change_class",
            core.hw_change_class(change)["class"],
            cm.change_class(change)["class"],
            "class-1 change on complex hardware")
    if cm is not None and hasattr(cm, "hci_entry"):
        add("configuration-management", "hci_entry",
            core.hci_entry("HW-ITEM-001", "Rev C", "BL-2.0"),
            cm.hci_entry("HW-ITEM-001", "Rev C", "BL-2.0"),
            "HCI entry format")

    rc = _load_leaf("requirements-capture")
    if rc is not None and hasattr(rc, "capture_readiness"):
        reqs = item.requirements or core.example_requirements()
        core_ready, core_score = core.capture_readiness(reqs)
        skill_ready, skill_score = rc.capture_readiness(reqs)
        add("requirements-capture", "capture_readiness",
            round(core_score, 6), round(skill_score, 6),
            "capture readiness score on example requirements")
        add("requirements-capture", "classify_derived",
            core.classify_derived(True), rc.classify_derived(True),
            "allocated-vs-derived classification")

    return rows


def _leaf_logic_file(leaf: str) -> str:
    """Return the basename of a leaf's logic file (best effort)."""
    if not HAS_SKILLS:
        return ""
    logic_dir = os.path.join(AEROSKILLS, "skills", DO254_LEAVES[leaf], "scripts")
    if os.path.isdir(logic_dir):
        files = sorted(f for f in os.listdir(logic_dir)
                       if f.endswith("_logic.py"))
        if files:
            return files[0]
    return ""


def _provenance(item, rows):
    dispatched_rows = [r for r in rows if r.get("dispatched")]
    all_agree = bool(dispatched_rows) and all(
        r.get("agrees") for r in dispatched_rows)
    return {
        "role": ROLE_SLUG,
        "core": {
            "file": "core/do254_hardware_core.py",
            "functions": ["classify_aeh", "coverage_adequate",
                          "verification_methods_for", "independence_required",
                          "hw_change_class", "hci_entry",
                          "capture_readiness", "build_phac", "check_phac"],
            "version": "0.1.0",
        },
        "skills": rows,
        "cross_checked": all_agree,
        "disclaimer": "DRAFT for human review. Not an approval document.",
    }


def cmd_build(args):
    item = core.example_item()
    # allow overriding the failure condition from CLI for different DALs
    if args.failure_condition:
        item.failure_condition = args.failure_condition
        item.system_safety_ref = args.safety_ref or item.system_safety_ref
    model = core.build_phac(item)
    md = core.render_phac_markdown(model)

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

    gates = core.check_phac(model)
    rows = _dispatch_rows(item)

    if args.out:
        with open(args.out, "w") as f:
            f.write(md)
        print(f"built PHAC (level {model['assurance_level']}, "
              f"{model['aeh_class']} AEH) -> {args.out}")
        if profile:
            print(f"profile: {profile.get('customer')} / "
                  f"{profile.get('program')}")
        print(f"gates: all_pass={gates['all_pass']} {gates}")
        if rows:
            n_agree = sum(1 for r in rows if r.get("agrees"))
            print(f"skill dispatch: {n_agree}/{len(rows)} cross-checks agree")
        else:
            print("skill dispatch: no AeroSkills logic available "
                  "(standalone)")
        if args.bundle:
            prov = _provenance(item, rows)
            paths = evidence.write_bundle(
                args.out, ROLE_SLUG,
                "Plan for Hardware Aspects of Certification",
                model, gates, prov)
            print(f"bundle: model={paths['model']}")
            print(f"        gates={paths['gates']}")
            print(f"        provenance={paths['provenance']}")
    else:
        print(md)
    return 0 if gates["all_pass"] else 1


def cmd_check(args):
    if not os.path.exists(args.file):
        print(f"file not found: {args.file}")
        return 1
    md = open(args.file).read()
    dal = (args.dal or "B").upper()
    gates = core.check_phac_markdown(md, dal)
    for name, ok in gates.items():
        if name != "all_pass":
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print(f"RESULT: {'PASS' if gates['all_pass'] else 'FAIL'}")
    return 0 if gates["all_pass"] else 1


def main():
    p = argparse.ArgumentParser(description="DO-254 Hardware Engineer role")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--out", default="", help="output file (default: stdout)")
    b.add_argument("--failure-condition", default="",
                   help="hazardous/major/minor/...")
    b.add_argument("--safety-ref", default="", help="system safety reference")
    b.add_argument("--bundle", action="store_true",
                   help="emit evidence/{model,gates,provenance}.json")
    b.add_argument("--profile", default="",
                   help="program profile JSON (customer tailoring, "
                        "docs/PROFILE-SCHEMA.md)")
    b.set_defaults(fn=cmd_build)

    c = sub.add_parser("check")
    c.add_argument("--file", required=True,
                   help="PHAC markdown file to gate-check")
    c.add_argument("--dal", default="", help="expected design assurance level")
    c.set_defaults(fn=cmd_check)

    args = p.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
