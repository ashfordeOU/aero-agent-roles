#!/usr/bin/env python3
"""wave-planner.py — AUTONOMOUS role-wave selection (the growth brain).

Reads the binding ledger + coverage matrix and DETERMINISTICALLY selects
the next role wave's target roles from coverage gaps — no human (or
CEO) hand-picking. Same idea as the skills wave briefs, but the target
selection is computed from the ledger.

Selection rule (mirror of the wave doctrine in docs/WAVE-BRIEF.md):
1. Family below the 70% binding bar.
2. Within it, clusters (family/subcluster) with >= 4 unbound leaves.
3. Pick the top cluster by unbound count; its natural role = the
   cluster's family+subcluster -> role slug.
4. A wave = up to 5 roles, chosen largest-unbound-first across families
   (so no single family monopolizes a wave), each role binding a
   coherent sub-cluster.

Emits the wave plan as JSON + a human brief ready for a builder.

Usage:
  python3 scripts/wave-planner.py            # print plan
  python3 scripts/wave-planner.py --json     # machine-readable
  python3 scripts/wave-planner.py --brief    # write ops/automation/wave-next-brief.md
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "scripts", "binding-ledger.py")

BINDING_BAR = 0.70
MIN_CLUSTER_UNBOUND = 4
MAX_ROLES_PER_WAVE = 5

# cluster -> proposed role slug + deliverable type (deterministic map;
# extend when a cluster becomes role-ready and a slug convention exists)
CLUSTER_ROLE_MAP = {
    "avionics/flight-management": ("flight-management-engineer",
                                   "Flight Plan and RNAV/RNP Route Assessment"),
    "avionics/do160": ("do160-environmental-engineer",
                       "Equipment Environmental Qualification Report"),
    "avionics/data-bus": ("data-bus-avionics-engineer",
                          "Avionics Data Bus Loading Assessment"),
    "avionics/do254": ("do254-hardware-engineer",
                       "Plan for Hardware Aspects of Certification"),
    "aerodynamics/high-speed": ("high-speed-aerodynamics-engineer",
                                "High-Speed Aerodynamic Analysis Memo"),
    "cross-cutting/numerics": ("numerical-analysis-engineer",
                               "Numerical Methods Verification Memo"),
    "flight-test-operations/performance": (
        "flight-test-performance-engineer",
        "Flight Test Performance Data Analysis Report"),
    "manufacturing-quality/inspection": ("aerospace-inspection-engineer",
                                         "Inspection Planning and FAI Report"),
    "systems-engineering-safety/certification": (
        "certification-planning-engineer",
        "Certification Basis and Means of Compliance Plan"),
    "gnc-autonomy/autopilot": ("autopilot-control-engineer",
                               "Autopilot Control Law Design Report"),
    # weak-family clusters (wave R3+ targets)
    "systems-engineering-safety/arp4754a": (
        "systems-integration-engineer",
        "Aircraft-Level System Integration and ARP4754A Plan"),
    "systems-engineering-safety/arp4761a": (
        "safety-assessment-engineer",
        "Functional Hazard and System Safety Assessment"),
    "systems-engineering-safety/safety-case": (
        "safety-case-engineer",
        "Safety Case Report"),
    "systems-engineering-safety/mbse": (
        "mbse-modeling-engineer",
        "Model-Based Systems Engineering Plan"),
    "manufacturing-quality/as9102": (
        "first-article-inspection-engineer",
        "First Article Inspection Report (AS9102)"),
    "manufacturing-quality/as9103": (
        "aerospace-variation-management-engineer",
        "Key Characteristic and Variation Management Plan"),
    "manufacturing-quality/ndt": (
        "ndt-engineer",
        "Nondestructive Test Plan and Method Selection"),
    "manufacturing-quality/special-processes": (
        "special-processes-engineer",
        "Special Process Qualification Plan"),
    "manufacturing-quality/composites": (
        "composites-manufacturing-engineer",
        "Composite Part Manufacturing and Inspection Plan"),
    "manufacturing-quality/additive": (
        "additive-manufacturing-engineer",
        "Additive Manufacturing Qualification Report"),
    "gnc-autonomy/estimation-filtering": (
        "state-estimation-engineer",
        "Navigation State Estimator Design Report"),
    "gnc-autonomy/guidance": (
        "guidance-engineer",
        "Guidance Law Design Report"),
    "gnc-autonomy/optimal-control": (
        "optimal-control-engineer",
        "Optimal Control Design Report"),
    "vehicle-design/landing-gear": ("landing-gear-engineer",
                                    "Landing Gear System Design Report"),
    # wave R6+ targets (coverage matrix 2026-09-06)
    "avionics/fsw": ("flight-software-engineer",
                     "Flight Software Design and Verification Plan"),
    "avionics/surveillance": ("surveillance-systems-engineer",
                              "Surveillance System Compliance Report"),
    "flight-test-operations/planning": (
        "flight-test-planning-engineer",
        "Flight Test Plan and Requirements Traceability"),
    "flight-test-operations/stability": (
        "stability-control-flight-test-engineer",
        "Stability and Control Flight Test Report"),
    "cross-cutting/sep2640": ("modeling-simulation-engineer",
                              "Modeling and Simulation V&V Plan"),
    "flight-mechanics/performance": ("aircraft-performance-engineer",
                                     "Aircraft Performance Analysis Report"),
    # wave R7+ targets (ledger 2026-09-06 — families with zero roles yet)
    "vehicle-design/sizing": ("aircraft-systems-sizing-engineer",
                              "Aircraft System Sizing Report"),
    "manufacturing-quality/as9100": (
        "quality-management-engineer",
        "AS9100 Quality Management System Audit Report"),
    "structures/composites": ("composites-structures-engineer",
                              "Composite Structure Analysis and Certification Report"),
    "structures/fem": ("fem-analysis-engineer",
                       "Finite Element Analysis Report"),
    "propulsion/rocket": ("rocket-propulsion-engineer",
                          "Rocket Propulsion System Design Report"),
    "space-systems/adcs": ("adcs-engineer",
                           "Attitude Determination and Control Subsystem Report"),
    "manufacturing-quality/assembly": (
        "assembly-integration-engineer",
        "Assembly and Installation Quality Plan"),
    "propulsion/gas-turbine-cycle": (
        "gas-turbine-cycle-engineer",
        "Gas Turbine Cycle Analysis Report"),
    "space-systems/mission-design": (
        "mission-design-engineer",
        "Space Mission Design Report"),
}


def load_ledger() -> dict:
    r = subprocess.run([sys.executable, LEDGER, "--json"],
                       capture_output=True, text=True, cwd=ROOT)
    return json.loads(r.stdout)


def cluster_unbound_counts(ledger: dict) -> Counter:
    counts = Counter()
    for leaf in ledger.get("role_ready_clusters", []):
        parts = leaf.split("/")
        if len(parts) >= 2:
            counts["/".join(parts[:2])] += 1
    return counts


def family_of_cluster(cluster: str) -> str:
    return cluster.split("/")[0]


def plan_next_wave() -> dict:
    ledger = load_ledger()
    fam = ledger.get("per_family", {})
    counts = cluster_unbound_counts(ledger)
    existing_roles = {
        d for d in os.listdir(os.path.join(ROOT, "roles"))
        if os.path.isdir(os.path.join(ROOT, "roles", d))
    }

    # families below the bar, sorted worst-first
    weak_families = sorted(
        [f for f, st in fam.items()
         if st["leaves"] and st["bound"] / st["leaves"] < BINDING_BAR],
        key=lambda f: fam[f]["bound"] / fam[f]["leaves"])

    chosen = []
    used_clusters = set()
    # pass 1: worst family first, take its largest ready cluster
    for fam_name in weak_families:
        cands = [(c, n) for c, n in counts.items()
                 if family_of_cluster(c) == fam_name
                 and c not in used_clusters
                 and n >= MIN_CLUSTER_UNBOUND
                 and c in CLUSTER_ROLE_MAP
                 and CLUSTER_ROLE_MAP[c][0] not in existing_roles]
        cands.sort(key=lambda t: -t[1])
        if cands:
            cluster, n = cands[0]
            slug, deliverable = CLUSTER_ROLE_MAP[cluster]
            chosen.append({
                "role": slug,
                "cluster": cluster,
                "unbound_leaves": n,
                "family": fam_name,
                "deliverable_type": deliverable,
                "family_coverage_pct": round(
                    fam[fam_name]["bound"] / fam[fam_name]["leaves"] * 100, 1),
            })
            used_clusters.add(cluster)
        if len(chosen) >= MAX_ROLES_PER_WAVE:
            break

    # pass 2: if under the cap, top clusters anywhere (still role-ready)
    if len(chosen) < MAX_ROLES_PER_WAVE:
        for cluster, n in sorted(counts.items(),
                                 key=lambda t: -t[1]):
            if cluster in used_clusters or cluster not in CLUSTER_ROLE_MAP:
                continue
            if n < MIN_CLUSTER_UNBOUND:
                continue
            slug, deliverable = CLUSTER_ROLE_MAP[cluster]
            if slug in existing_roles:
                continue  # already built — do not re-propose
            f = family_of_cluster(cluster)
            chosen.append({
                "role": slug,
                "cluster": cluster,
                "unbound_leaves": n,
                "family": f,
                "deliverable_type": deliverable,
                "family_coverage_pct": round(
                    fam[f]["bound"] / fam[f]["leaves"] * 100, 1)
                if fam[f]["leaves"] else 0.0,
            })
            used_clusters.add(cluster)
            if len(chosen) >= MAX_ROLES_PER_WAVE:
                break

    return {
        "roles_total": ledger["roles"],
        "leaves_total": ledger["leaves_total"],
        "coverage_pct": ledger["coverage_pct"],
        "weak_families": weak_families,
        "wave": chosen,
        "note": ("Selection is deterministic from the ledger: families "
                 "below the binding bar, clusters >= {min} unbound "
                 "leaves, largest-first, max {max} per wave.").format(
                     min=MIN_CLUSTER_UNBOUND, max=MAX_ROLES_PER_WAVE),
    }


def main() -> int:
    plan = plan_next_wave()
    if "--json" in sys.argv:
        print(json.dumps(plan, indent=1))
        return 0

    print(f"ROLES {plan['roles_total']} · LEAVES {plan['leaves_total']} · "
          f"COVERAGE {plan['coverage_pct']}%")
    print(f"WEAK FAMILIES (<{int(BINDING_BAR*100)}% bar): "
          f"{', '.join(plan['weak_families']) if plan['weak_families'] else 'none'}")
    if not plan["wave"]:
        print("NO WAVE READY — all role-ready clusters are bound or no "
              "cluster reaches the threshold.")
        return 0
    print(f"\nNEXT WAVE ({len(plan['wave'])} roles):")
    for r in plan["wave"]:
        print(f"  {r['role']:<38} <- {r['cluster']} "
              f"({r['unbound_leaves']} unbound, "
              f"family {r['family_coverage_pct']}%)")
    print(f"\n{plan['note']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
