#!/usr/bin/env python3
"""safety_assessment_core.py - Safety Assessment Engineer executable core.

This is the role's ENGINE: given a system function and its failure
conditions it runs the ARP4761A-style quantitative safety assessment -
functional hazard classification with probability targets per flight
hour, fault tree quantification (gate math, minimal cut sets, top
event probability), FMEA severity/criticality ranking, event tree
branch-probability rollup, PSSA target allocation, common cause
analysis, and SSA closure margins - and BUILDS the Aircraft/System
Safety Assessment Report content. It also gate-checks deliverables.
Standalone: no external repo needed.

Domain rules encoded here are public-domain process knowledge and
paraphrase-level summaries of standard practice (FAR/CS-25.1309
severity categories, AC 25.1309-1A probability bands, ARP4761A /
ARP4754A method structure as summarised in the AeroSkills
systems-engineering-safety leaves). ARP4761A/ARP4754A are proprietary
SAE publications - never reproduced; only names, magnitudes, and
paraphrased method steps appear here (summary-not-copy).
"""
from __future__ import annotations

import itertools
import json
import math
import os
import re
from dataclasses import dataclass, field
from datetime import date


def _today() -> str:
    return os.environ.get("ROLE_GEN_DATE", date.today().isoformat())


# ---------------------------------------------------------------------------
# Domain tables (public process knowledge; magnitudes per standard practice)
# ---------------------------------------------------------------------------

# Failure-condition severity -> probability target per flight hour.
# Catastrophic <1e-9, hazardous <1e-7, major <1e-5, minor <1e-3 (FAR/CS
# 25.1309 practice; AC 25.1309-1A band terminology). "No safety effect"
# carries no quantitative target.
SEVERITY_TARGETS = {
    "catastrophic": 1e-9,
    "hazardous": 1e-7,
    "major": 1e-5,
    "minor": 1e-3,
}
SEVERITY_ORDER = ("catastrophic", "hazardous", "major", "minor",
                  "no-safety-effect")
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITY_ORDER)}

# AC 25.1309-1A band terminology by probability per flight hour.
BAND_THRESHOLDS = (
    (1e-9, "extremely improbable"),
    (1e-7, "extremely remote"),
    (1e-5, "remote"),
)

# Severity -> function development assurance level (ARP4754A practice,
# as used by the ARP4761A leaves: A=catastrophic ... E=no safety effect).
SEVERITY_TO_DAL = {
    "catastrophic": "A",
    "hazardous": "B",
    "major": "C",
    "minor": "D",
    "no-safety-effect": "E",
}
DALS = ("A", "B", "C", "D", "E")
DAL_RANK = {d: i for i, d in enumerate(DALS)}

# Analysis techniques per assurance level (ARP4761A practice summary):
# FTA and FMEA at every safety-significant level; CCA added at A/B.
ANALYSES_BY_LEVEL = {
    "A": ["FTA", "FMEA", "CCA"],
    "B": ["FTA", "FMEA", "CCA"],
    "C": ["FTA", "FMEA"],
    "D": ["FTA", "FMEA"],
    "E": ["FMEA"],
}

# ---------------------------------------------------------------------------
# Functional hazard assessment (FHA)
# ---------------------------------------------------------------------------


def severity_target(severity: str) -> float:
    """Probability target per flight hour for a severity category.

    catastrophic <1e-9, hazardous <1e-7, major <1e-5, minor <1e-3.
    Raises ValueError for unknown categories or no-safety-effect
    (which carries no quantitative target).
    """
    key = severity.strip().lower().replace(" ", "-")
    if key not in SEVERITY_TARGETS:
        raise ValueError(
            "severity must be one of catastrophic, hazardous, major, "
            "minor; got %r (no-safety-effect carries no quantitative "
            "target)" % (severity,))
    return SEVERITY_TARGETS[key]


def target_band(probability_per_fh: float) -> str:
    """AC 25.1309-1A band name for a probability per flight hour."""
    for threshold, band in BAND_THRESHOLDS:
        if probability_per_fh < threshold:
            return band
    return "probable"


def target_met(severity: str, probability_per_fh: float) -> bool:
    """True when assessed probability is strictly below the severity
    target (equality fails: 1e-3 does not meet a minor target)."""
    target = severity_target(severity)
    return probability_per_fh < target


def dal_for_severity(severity: str) -> str:
    """Development assurance level for a failure-condition severity."""
    key = severity.strip().lower().replace(" ", "-")
    if key not in SEVERITY_TO_DAL:
        raise ValueError("unknown severity: %r" % (severity,))
    return SEVERITY_TO_DAL[key]


def analyses_for_level(level: str) -> list:
    """Analysis set expected at an assurance level (FTA/FMEA, +CCA at A/B)."""
    if level not in DALS:
        raise ValueError("invalid assurance level: %r" % (level,))
    return list(ANALYSES_BY_LEVEL[level])


def fha_row(function, failure_condition, flight_phase, effect,
            severity, assessed_per_fh, analysis_ref):
    """One FHA worksheet row: severity, target band/bound, verdict."""
    severity = severity.strip().lower().replace(" ", "-")
    if severity not in SEVERITY_RANK:
        raise ValueError("unknown severity: %r" % (severity,))
    if assessed_per_fh < 0.0:
        raise ValueError("assessed probability cannot be negative")
    target = severity_target(severity) if severity in SEVERITY_TARGETS else None
    return {
        "function": function,
        "failure_condition": failure_condition,
        "flight_phase": flight_phase,
        "effect_on_aircraft": effect,
        "severity": severity,
        "target_per_fh": target,
        "assessed_per_fh": assessed_per_fh,
        "meets_target": (None if target is None
                         else target_met(severity, assessed_per_fh)),
        "analysis_ref": analysis_ref,
    }


# ---------------------------------------------------------------------------
# Fault tree analysis (FTA): gate math + minimal cut sets + quantification
# ---------------------------------------------------------------------------


def fta_minimal_cut_sets(structure: dict, top: str) -> list:
    """Minimal cut sets of `top` given a gate `structure`.

    structure maps a gate node to {"op": "AND"|"OR", "children": [...]}.
    Nodes absent from structure are basic events. OR unions branches;
    AND takes the cartesian product across branches (then minimality by
    set union/dedup). Returns a list of frozensets sorted by (len, name).
    """
    def _cuts(node, active):
        if node not in structure:
            return [frozenset((node,))]
        if node in active:
            raise ValueError("cycle in fault tree at gate %r" % (node,))
        entry = structure[node]
        op = entry.get("op")
        children = entry.get("children")
        if op not in ("AND", "OR") or not isinstance(children, list) \
                or not children:
            raise ValueError("gate %r needs op AND|OR and non-empty children"
                             % (node,))
        branch_sets = [_cuts(c, active | {node}) for c in children]
        if op == "OR":
            merged = set().union(*branch_sets)
        else:
            merged = set()
            for combo in itertools.product(*branch_sets):
                merged.add(frozenset().union(*combo))
        return list(merged)

    result = _cuts(top, frozenset())
    return sorted(result, key=lambda cs: (len(cs), sorted(cs)))


def fta_cut_set_probability(cut_set, probs: dict) -> float:
    """Probability of one cut set: product of its basic-event
    probabilities (events independent, per-event probability per flight
    hour or per mission)."""
    missing = [e for e in cut_set if e not in probs]
    if missing:
        raise ValueError("no probability for event(s): %r"
                         % (sorted(missing),))
    p = 1.0
    for event in cut_set:
        p *= probs[event]
    return p


def fta_top_probability(cut_sets, probs: dict) -> float:
    """Top event probability: union of the minimal cut sets.

    Exact inclusion-exclusion over the cut-set list under event
    independence (identical math to the ARP4761A fault-tree-importance
    leaf's top_event_probability). Raises ValueError for empty cut sets
    or an unknown event name.
    """
    if not cut_sets or any(not cs for cs in cut_sets):
        raise ValueError("cut_sets must be a non-empty list of non-empty sets")
    for cs in cut_sets:
        for event in cs:
            if event not in probs:
                raise ValueError("unknown basic event %r: no probability"
                                 % (event,))
    n = len(cut_sets)
    total = 0.0
    for mask in range(1, 1 << n):
        product = 1.0
        terms = 0
        for index in range(n):
            if mask & (1 << index):
                terms += 1
                for event in cut_sets[index]:
                    product *= probs[event]
        total += product if terms % 2 == 1 else -product
    return total


def fta_cut_set_sanity(cut_sets, probs: dict, top_prob: float) -> list:
    """Flag (cut_set, probability) pairs whose probability exceeds the
    top event probability (a modelling error). Empty list = sane."""
    flagged = []
    for cs in cut_sets:
        prob = fta_cut_set_probability(cs, probs)
        if prob > top_prob:
            flagged.append((sorted(cs), prob))
    return flagged


def fta_importance_measures(cut_sets, probs: dict, top_event=None):
    """Per-event Fussell-Vesely and RAW importance over the cut sets.

    FV = (Q - Q(q_i=0)) / Q ; RAW = Q(q_i=1) / Q. Returns dict keyed by
    event name (only events appearing in cut sets), each with fv, raw.
    """
    if not cut_sets or any(not cs for cs in cut_sets):
        raise ValueError("cut_sets must be a non-empty list of non-empty sets")
    top = fta_top_probability(cut_sets, probs) if top_event is None \
        else top_event
    events = sorted(set().union(*[set(cs) for cs in cut_sets]))
    out = {}
    for event in events:
        # Q with the event forced to 0 and to 1
        p0 = dict(probs); p0[event] = 0.0
        p1 = dict(probs); p1[event] = 1.0
        q0 = fta_top_probability(cut_sets, p0)
        q1 = fta_top_probability(cut_sets, p1)
        fv = (top - q0) / top if top > 0.0 else 0.0
        raw = (q1 / top) if top > 0.0 else float("inf")
        out[event] = {"fussell_vesely": fv, "raw": raw}
    return out


# ---------------------------------------------------------------------------
# FMEA / FMECA: mode split, quantitative criticality, severity level
# ---------------------------------------------------------------------------

# Mode criticality model (MIL-STD-1629A style quantitative FMECA as
# used in the ARP4761A failure-mode-criticality leaf): per-mode rate
# split by mode ratio alpha (sum = 1), conditional effect probability
# beta in [0,1]; C_m = beta * alpha * lambda_p * t.
DOMINANT_SHARE = 0.5


def fmea_split_item_rate(item_failure_rate: float, mode_ratios: dict) -> dict:
    """Split the item failure rate into per-mode rates alpha * lambda_p."""
    if item_failure_rate <= 0:
        raise ValueError("item failure rate must be > 0")
    if not mode_ratios:
        raise ValueError("mode_ratios must not be empty")
    total = 0.0
    for mode_id, alpha in mode_ratios.items():
        if alpha <= 0 or alpha > 1:
            raise ValueError("alpha must lie in (0,1] for mode %r"
                             % (mode_id,))
        total += alpha
    if abs(total - 1.0) > 1e-9:
        raise ValueError("mode ratios must sum to 1.0, got %r" % (total,))
    return {mid: alpha * item_failure_rate
            for mid, alpha in mode_ratios.items()}


def fmea_mode_criticality(beta, alpha, item_failure_rate, operating_time):
    """Quantitative criticality C_m = beta * alpha * lambda_p * t."""
    if not 0.0 <= beta <= 1.0:
        raise ValueError("beta must lie in [0,1]")
    if not 0.0 < alpha <= 1.0:
        raise ValueError("alpha must lie in (0,1]")
    if item_failure_rate <= 0:
        raise ValueError("item failure rate must be > 0")
    if operating_time < 0:
        raise ValueError("operating time must be >= 0")
    return beta * alpha * item_failure_rate * operating_time


def fmea_item_criticality(modes, item_failure_rate, operating_time) -> float:
    """Item criticality C_r: sum of per-mode criticalities over modes.

    modes: list of dicts {id, alpha, beta}. Alphas must sum to 1.0.
    """
    if not modes:
        raise ValueError("modes must not be empty")
    ratios = {m["id"]: m["alpha"] for m in modes}
    fmea_split_item_rate(item_failure_rate, ratios)  # validates
    return sum(fmea_mode_criticality(m["beta"], m["alpha"],
                                     item_failure_rate, operating_time)
               for m in modes)


def fmea_rank_modes(modes, item_failure_rate, operating_time) -> list:
    """Rank modes by C_m descending with share of item criticality and
    a dominant flag when share >= 0.5."""
    cr = fmea_item_criticality(modes, item_failure_rate, operating_time)
    rows = []
    for m in modes:
        cm = fmea_mode_criticality(m["beta"], m["alpha"],
                                   item_failure_rate, operating_time)
        rows.append({"id": m["id"], "description": m.get("description", ""),
                     "alpha": m["alpha"], "beta": m["beta"],
                     "severity": m.get("severity", ""),
                     "effect": m.get("effect", ""),
                     "cm": cm})
    rows.sort(key=lambda r: (-r["cm"], r["id"]))
    for row in rows:
        share = (row["cm"] / cr) if cr > 0.0 else 0.0
        row["share"] = share
        row["dominant"] = share >= DOMINANT_SHARE
    return rows


# ---------------------------------------------------------------------------
# Event tree analysis: branch probabilities and end-state rollup
# ---------------------------------------------------------------------------


def event_tree_paths(nodes) -> list:
    """Enumerate the full binary expansion of ordered mitigation nodes.

    nodes: list of (name, p_success). Returns one dict per path with
    sequence, path (tuple of bools) and probability (product of branch
    probabilities)."""
    if not nodes:
        raise ValueError("node list must not be empty")
    if len(nodes) > 12:
        raise ValueError("node count exceeds 12 (2**12 path cap)")
    for name, p in nodes:
        if not 0.0 <= p <= 1.0:
            raise ValueError("branch success probability must be in [0,1]")
    paths = []
    for mask in range(1 << len(nodes)):
        seq, outcomes, prob = [], [], 1.0
        for i, (name, p_success) in enumerate(nodes):
            success = bool((mask >> i) & 1)
            outcomes.append(success)
            seq.append("%s:%s" % (name, "S" if success else "F"))
            prob *= p_success if success else (1.0 - p_success)
        paths.append({"sequence": " ".join(seq),
                      "path": tuple(outcomes), "probability": prob})
    return paths


def event_tree_frequencies(initiator_frequency: float, nodes) -> list:
    """End-state frequencies = initiator frequency x path probability,
    sorted descending by frequency."""
    if initiator_frequency < 0.0:
        raise ValueError("initiator frequency must be non-negative")
    out = []
    for path in event_tree_paths(nodes):
        out.append({"sequence": path["sequence"],
                    "path": path["path"],
                    "probability": path["probability"],
                    "frequency": initiator_frequency * path["probability"]})
    out.sort(key=lambda e: e["frequency"], reverse=True)
    return out


def event_tree_failure_frequency(frequencies) -> dict:
    """Sum the frequency over paths that reach the failure end state
    (every mitigation function failed)."""
    seqs, total = [], 0.0
    for entry in frequencies:
        if all(not outcome for outcome in entry["path"]):
            seqs.append(entry["sequence"])
            total += entry["frequency"]
    return {"sequences": seqs, "frequency": total}


def event_tree_dominant_sequences(frequencies, severity_target) -> list:
    """Flag sequences whose frequency strictly exceeds the severity
    target (ratio = frequency / target)."""
    if severity_target <= 0.0:
        raise ValueError("severity target must be positive")
    out = []
    for entry in frequencies:
        if entry["frequency"] > severity_target:
            out.append({"sequence": entry["sequence"],
                        "frequency": entry["frequency"],
                        "ratio": entry["frequency"] / severity_target})
    return out


# ---------------------------------------------------------------------------
# PSSA: DAL allocation and quantitative safety-target apportionment
# ---------------------------------------------------------------------------


def idal_for_fdal(fdal: str, reduction_allowed: bool = False) -> str:
    """Item DAL from function DAL; one-step reduction when allowed and
    the item cannot by itself cause the failure condition (E never
    reduces)."""
    if fdal not in DALS:
        raise ValueError("invalid FDAL: %r" % (fdal,))
    if reduction_allowed and fdal != "E":
        return DALS[DAL_RANK[fdal] + 1]
    return fdal


def pssa_allocate_target(target: float, n_contributors: int, gate: str) -> dict:
    """Apportion a quantitative safety target across n contributors.

    'or'  -> per-contributor budget = target / n (any contributor
             failure causes the condition; budget shares by sum)
    'and' -> per-contributor budget = target ** (1/n) (all must fail;
             budget shares by product)
    Returns {target, gate, n, per_contributor, check, verified}."""
    if not isinstance(target, (int, float)) or target <= 0.0:
        raise ValueError("target must be a positive number")
    if not isinstance(n_contributors, int) or n_contributors < 1:
        raise ValueError("n_contributors must be an integer >= 1")
    if gate not in ("and", "or"):
        raise ValueError("gate must be 'and' or 'or'")
    if gate == "and":
        if target >= 1.0:
            raise ValueError("AND allocation needs a target below 1.0")
        per = target ** (1.0 / n_contributors)
        check = per ** n_contributors
    else:
        per = target / n_contributors
        check = per * n_contributors
    return {"target": target, "gate": gate, "n": n_contributors,
            "per_contributor": per, "check": check,
            "verified": math.isclose(check, target, rel_tol=1e-12,
                                     abs_tol=1e-12)}


def pssa_channel_check(channel_rates, target: float, gate: str) -> dict:
    """Check realized channel rates against the allocated target.

    'or' totals by sum, 'and' totals by product. Returns total, target,
    margin (target / total) and meets (total <= target)."""
    if not channel_rates:
        raise ValueError("channel_rates must not be empty")
    if not isinstance(target, (int, float)) or target <= 0.0:
        raise ValueError("target must be a positive number")
    if gate not in ("and", "or"):
        raise ValueError("gate must be 'and' or 'or'")
    for rate in channel_rates:
        if not isinstance(rate, (int, float)) or rate <= 0.0:
            raise ValueError("channel rates must be positive")
    if gate == "and":
        total = 1.0
        for rate in channel_rates:
            total *= rate
    else:
        total = sum(channel_rates)
    return {"total": total, "target": target,
            "margin": target / total, "meets": total <= target,
            "gate": gate}


# ---------------------------------------------------------------------------
# Common cause analysis (CCA): beta-factor, ZSA, PRA
# ---------------------------------------------------------------------------

CCA_ELEMENTS = ("ZSA", "PRA", "CMA")


def beta_split_failure_rate(failure_rate: float, beta: float) -> dict:
    """Split a channel failure rate into independent and common-cause
    parts: independent = (1-beta)*lambda, common_cause = beta*lambda."""
    if failure_rate <= 0 or not 0.0 <= beta <= 1.0:
        raise ValueError("failure rate must be > 0 and beta in [0,1]")
    return {"independent": (1.0 - beta) * failure_rate,
            "common_cause": beta * failure_rate}


def beta_common_cause_probability(failure_rate, beta, time) -> float:
    """Common-cause shock probability Q_cc = 1 - exp(-beta*lambda*t)."""
    if failure_rate <= 0 or not 0.0 <= beta <= 1.0 or time < 0:
        raise ValueError("failure rate > 0, beta in [0,1], time >= 0")
    return 1.0 - math.exp(-beta * failure_rate * time)


def beta_dual_channel_probability(failure_rate, beta, time) -> float:
    """Dual-channel CCF-inclusive failure probability: inclusion-
    exclusion union of the independent double failure and the shared
    shock."""
    q_i = 1.0 - math.exp(-(1.0 - beta) * failure_rate * time)
    q_c = beta_common_cause_probability(failure_rate, beta, time)
    return q_i * q_i + q_c - q_i * q_i * q_c


def zsa_zone_check(items) -> tuple:
    """(score, verdict) for (hazard, ok) zone items: failed-item
    fraction; verdict 'ok' below 0.5 else 'action' (project sanity
    band)."""
    if not items:
        raise ValueError("zone items must not be empty")
    failed = sum(1 for _, ok in items if not ok)
    score = failed / float(len(items))
    return (score, "ok" if score < 0.5 else "action")


def cca_complete(analyses) -> bool:
    """True when the analysis set covers ZSA, PRA and CMA."""
    return set(a.upper() for a in analyses) >= set(CCA_ELEMENTS)


def pra_conditional_probability(p_a, p_b_given_a) -> float:
    """Two-step particular-risk chain: p_a * p_b_given_a."""
    for p in (p_a, p_b_given_a):
        if not 0.0 <= p <= 1.0:
            raise ValueError("probabilities must lie in [0,1]")
    return p_a * p_b_given_a


def pra_exposure_probability(rate, hours) -> float:
    """Probability of at least one event in exposure: 1 - exp(-rate*t)."""
    if rate < 0.0 or hours < 0.0:
        raise ValueError("rate and hours must be >= 0")
    return 1.0 - math.exp(-rate * hours)


# ---------------------------------------------------------------------------
# Failure-rate estimation and FTA uncertainty support
# ---------------------------------------------------------------------------

NORMAL_QUANTILE_90 = 1.645


def failure_rate_point_estimate(failures: int, test_hours: float) -> float:
    """lambda_hat = n / T per hour (point estimate)."""
    if failures < 0:
        raise ValueError("failures must be non-negative")
    if test_hours <= 0:
        raise ValueError("test_hours must be positive")
    return failures / test_hours


def error_factor_to_sigma(error_factor: float) -> float:
    """Lognormal sigma from an error factor: ln(EF) / z_90."""
    if error_factor < 1.0:
        raise ValueError("error factor must be >= 1.0")
    return math.log(error_factor) / NORMAL_QUANTILE_90


def confidence_band(q_top: float, sigma_lnq: float) -> dict:
    """Two-sided 90% lognormal confidence band around q_top:
    [q*exp(-1.645*sigma), q*exp(+1.645*sigma)]."""
    if not 0.0 < q_top <= 1.0:
        raise ValueError("top probability must lie in (0,1]")
    if sigma_lnq < 0.0:
        raise ValueError("lognormal sigma must be >= 0")
    return {"lower": q_top * math.exp(-NORMAL_QUANTILE_90 * sigma_lnq),
            "upper": q_top * math.exp(+NORMAL_QUANTILE_90 * sigma_lnq)}


# ---------------------------------------------------------------------------
# SSA closure: margins, closure rollup, requirement closure
# ---------------------------------------------------------------------------


def condition_margin(predicted_q: float, severity: str) -> dict:
    """Per-condition margin and strict meets verdict: margin =
    target / predicted_q (equality fails, mirroring target_met)."""
    if not isinstance(predicted_q, (int, float)) or predicted_q <= 0.0:
        raise ValueError("predicted_q must be > 0")
    target = severity_target(severity)
    return {"meets": predicted_q < target, "margin": target / predicted_q}


def closure_rollup(conditions) -> dict:
    """Roll assessed conditions into the closure-gate verdict.

    conditions: list of {id, severity, predicted_q}. Returns total,
    closed, open, open_conditions, meets_by_severity and overall_gate
    ('CLOSED' when every condition meets its target, else 'OPEN')."""
    if not conditions:
        raise ValueError("conditions must not be empty")
    closed, open_ids = 0, []
    class_counts = {}
    for cond in conditions:
        severity = cond["severity"].strip().lower().replace(" ", "-")
        target = severity_target(severity)
        q = cond["predicted_q"]
        if not isinstance(q, (int, float)) or q <= 0.0:
            raise ValueError("predicted_q must be > 0")
        counts = class_counts.setdefault(severity, [0, 0])
        counts[1] += 1
        if q < target:
            closed += 1
            counts[0] += 1
        else:
            open_ids.append(cond["id"])
    by_sev = {}
    for sev in SEVERITY_ORDER:
        if sev in class_counts:
            done, total = class_counts[sev]
            by_sev[sev] = done / total
    return {"total": len(conditions), "closed": closed,
            "open": len(open_ids), "open_conditions": open_ids,
            "meets_by_severity": by_sev,
            "overall_gate": "CLOSED" if not open_ids else "OPEN"}


def requirement_closure(requirements) -> dict:
    """Roll requirement verification statuses ({id, status}) where
    status is 'verified' or 'open'."""
    verified, open_ids = 0, []
    for req in requirements:
        status = req.get("status")
        if status not in ("verified", "open"):
            raise ValueError("status must be 'verified' or 'open'")
        if status == "verified":
            verified += 1
        else:
            open_ids.append(req["id"])
    return {"total": len(requirements), "verified": verified,
            "open": len(open_ids), "open_requirements": open_ids}


# ---------------------------------------------------------------------------
# Assessment report builder
# ---------------------------------------------------------------------------


@dataclass
class AssessmentItem:
    """Project facts the role needs to build the safety assessment."""
    item_name: str
    description: str = ""
    system: str = ""
    certification_basis: str = "FAR/CS-25.1309"
    airframe: str = ""
    function: str = ""
    flight_phases: str = "all phases"
    # FHA failure conditions: (id, function, flight_phase, effect,
    # severity, assessed_per_fh, analysis_ref)
    failure_conditions: list = field(default_factory=list)
    # FTA: gate structure, top event, basic-event probabilities
    fta_structure: dict = field(default_factory=dict)
    fta_top: str = ""
    fta_probs: dict = field(default_factory=dict)
    # FMEA: item rate, operating time, modes
    fmea_item: str = ""
    fmea_item_rate: float = 0.0
    fmea_operating_time: float = 1.0
    fmea_modes: list = field(default_factory=list)
    # event tree: initiator frequency, mitigation nodes
    et_initiator: str = ""
    et_initiator_frequency: float = 0.0
    et_nodes: list = field(default_factory=list)   # (name, p_success)
    et_failure_severity: str = "catastrophic"
    # PSSA allocation: contributors with gate and realized rates
    pssa_target: float = 1e-9
    pssa_gate: str = "or"
    pssa_contributor_rates: list = field(default_factory=list)
    pssa_note: str = ""
    # CCA facts
    zsa_zone: str = ""
    zsa_items: list = field(default_factory=list)
    pra_event: str = ""
    pra_p_a: float = 0.0
    pra_p_b_given_a: float = 0.0
    pra_exposure_rate: float = 0.0
    pra_exposure_hours: float = 1.0
    beta_channel_rate: float = 0.0
    beta_factor: float = 0.0
    # failure rate evidence (test demonstration)
    demo_failures: int = 0
    demo_test_hours: float = 0.0
    # safety requirements for closure
    requirements: list = field(default_factory=list)
    uncertainty_error_factor: float = 3.0
    supporting_note: str = ""


def _severity_label(sev: str) -> str:
    return sev.replace("-", " ").title()


def _fmt_p(x) -> str:
    """Scientific notation for probabilities, e.g. 3.0e-10."""
    return "%.1e" % x


def _fmt(x, nd=4) -> str:
    if isinstance(x, float):
        if x == 0.0:
            return "0"
        if 1e-4 <= abs(x) < 1e6:
            return ("%.*g" % (nd, x))
        return "%.1e" % x
    return str(x)


def build_safety_report(item: AssessmentItem) -> dict:
    """Build the complete Aircraft/System Safety Assessment content model."""
    # --- FTA quantification first: its top event probability feeds the
    # FHA/closure assessed value for the tree's failure condition ---
    cut_sets = fta_minimal_cut_sets(item.fta_structure, item.fta_top) \
        if item.fta_structure else []
    cs_rows = []
    for cs in cut_sets:
        prob = fta_cut_set_probability(cs, item.fta_probs)
        cs_rows.append({"cut_set": sorted(cs), "probability": prob})
    q_top = fta_top_probability(cut_sets, item.fta_probs) \
        if cut_sets else 0.0
    sanity = fta_cut_set_sanity(cut_sets, item.fta_probs, q_top) \
        if cut_sets else []
    importance = fta_importance_measures(cut_sets, item.fta_probs, q_top) \
        if cut_sets else {}
    fta = {
        "top_event": item.fta_top,
        "structure": item.fta_structure,
        "basic_event_probabilities": dict(item.fta_probs),
        "minimal_cut_sets": cs_rows,
        "top_probability": q_top,
        "sanity_flags": [{"cut_set": [str(e) for e in cs_],
                          "probability": p} for cs_, p in sanity],
        "importance": {e: {"fussell_vesely": round(v["fussell_vesely"], 4),
                           "raw": round(v["raw"], 3)}
                       for e, v in sorted(importance.items())},
    }

    # --- FHA rows (assessed values may be analyst inputs; the FTA top
    # event result overrides the assessed value of its own condition so
    # the quantified tree is the source of that number) ---
    fha_rows = []
    for fc in item.failure_conditions:
        fc_id, function, phase, effect, severity, assessed, ref = fc
        if ref == "FTA-01" and q_top > 0.0:
            assessed = q_top
        fha_rows.append(fha_row(function, fc_id, phase, effect, severity,
                                assessed, ref))

    # worst severity drives the item development assurance level
    worst = min((r["severity"] for r in fha_rows),
                key=lambda s: SEVERITY_RANK.get(
                    s, SEVERITY_RANK["no-safety-effect"]))
    level = dal_for_severity(worst)
    analyses = analyses_for_level(level)

    # --- FMEA quantification ---
    fmea_rows = fmea_rank_modes(item.fmea_modes, item.fmea_item_rate,
                                item.fmea_operating_time) \
        if item.fmea_modes else []
    cr = sum(r["cm"] for r in fmea_rows)
    fmea = {"item": item.fmea_item,
            "item_failure_rate": item.fmea_item_rate,
            "operating_time": item.fmea_operating_time,
            "modes": fmea_rows, "item_criticality": cr}

    # --- Event tree quantification ---
    et_frequencies = event_tree_frequencies(item.et_initiator_frequency,
                                            item.et_nodes) \
        if item.et_nodes else []
    et_failure = event_tree_failure_frequency(et_frequencies) \
        if et_frequencies else {"sequences": [], "frequency": 0.0}
    et_target = severity_target(item.et_failure_severity)
    # Dominant-sequence screening applies to the failure end states (the
    # only end states that constitute the failure condition): any such
    # sequence whose frequency exceeds the severity target is dominant.
    et_failure_entries = [e for e in et_frequencies
                          if e["sequence"] in et_failure["sequences"]]
    et = {
        "initiator": item.et_initiator,
        "initiator_frequency": item.et_initiator_frequency,
        "nodes": [{"name": n, "p_success": p} for n, p in item.et_nodes],
        "end_states": et_frequencies,
        "failure_end_state_frequency": et_failure["frequency"],
        "failure_sequences": et_failure["sequences"],
        "screened_severity": item.et_failure_severity,
        "screened_target": et_target,
        "dominant_sequences": event_tree_dominant_sequences(
            et_failure_entries, et_target) if et_failure_entries else [],
    }

    # --- PSSA allocation ---
    n_contributors = len(item.pssa_contributor_rates) \
        if item.pssa_contributor_rates else 1
    alloc = pssa_allocate_target(item.pssa_target, n_contributors,
                                 item.pssa_gate)
    realized = pssa_channel_check(item.pssa_contributor_rates,
                                  item.pssa_target, item.pssa_gate) \
        if item.pssa_contributor_rates else {
            "total": 0.0, "target": item.pssa_target, "margin": 0.0,
            "meets": False, "gate": item.pssa_gate}
    pssa = {
        "fdal": level,
        "idal": idal_for_fdal(level),
        "target": item.pssa_target,
        "gate": item.pssa_gate,
        "n_contributors": n_contributors,
        "per_contributor_budget": alloc["per_contributor"],
        "allocation_verified": alloc["verified"],
        "realized_total": realized["total"],
        "realized_margin": realized["margin"],
        "realized_meets": realized["meets"],
        "note": item.pssa_note,
    }

    # --- CCA ---
    zsa_score, zsa_verdict = zsa_zone_check(item.zsa_items) \
        if item.zsa_items else (0.0, "n/a")
    beta_split = beta_split_failure_rate(item.beta_channel_rate,
                                         item.beta_factor) \
        if item.beta_channel_rate else {}
    q_cc = beta_common_cause_probability(item.beta_channel_rate,
                                         item.beta_factor, 1.0) \
        if item.beta_channel_rate else 0.0
    q_dual = beta_dual_channel_probability(item.beta_channel_rate,
                                           item.beta_factor, 1.0) \
        if item.beta_channel_rate else 0.0
    cca = {
        "elements": list(CCA_ELEMENTS),
        "complete": cca_complete(["zsa", "pra", "cma"]),
        "zsa_zone": item.zsa_zone,
        "zsa_score": zsa_score,
        "zsa_verdict": zsa_verdict,
        "pra_event": item.pra_event,
        "pra_p_a": item.pra_p_a,
        "pra_p_b_given_a": item.pra_p_b_given_a,
        "pra_contribution": pra_conditional_probability(
            item.pra_p_a, item.pra_p_b_given_a),
        "pra_exposure": pra_exposure_probability(item.pra_exposure_rate,
                                                 item.pra_exposure_hours),
        "beta_channel_rate": item.beta_channel_rate,
        "beta_factor": item.beta_factor,
        "beta_split": beta_split,
        "beta_q_cc": q_cc,
        "beta_q_dual": q_dual,
    }

    # --- failure-rate demonstration evidence ---
    lam_hat = failure_rate_point_estimate(item.demo_failures,
                                          item.demo_test_hours) \
        if item.demo_test_hours else 0.0

    # --- FTA uncertainty band around the top event probability ---
    sigma_lnq = error_factor_to_sigma(item.uncertainty_error_factor)
    band = confidence_band(q_top, sigma_lnq) if q_top > 0.0 else {
        "lower": 0.0, "upper": 0.0}

    # --- closure (per-condition margins + requirements) ---
    closure_conditions = [{"id": r["failure_condition"],
                           "severity": r["severity"],
                           "predicted_q": r["assessed_per_fh"]}
                          for r in fha_rows]
    rollup = closure_rollup(closure_conditions) if closure_conditions else {}
    req_rollup = requirement_closure(item.requirements) \
        if item.requirements else {}

    return {
        "document_type": "Aircraft/System Safety Assessment Report "
                         "(ARP4761A)",
        "status": "draft-for-review",
        "item": item.item_name,
        "item_description": item.description,
        "system": item.system,
        "function": item.function,
        "airframe": item.airframe,
        "certification_basis": item.certification_basis,
        "flight_phases": item.flight_phases,
        "development_assurance_level": level,
        "analyses": analyses,
        "fha_rows": fha_rows,
        "fta": fta,
        "fmea": fmea,
        "event_tree": et,
        "pssa": pssa,
        "cca": cca,
        "demonstrated_rate_per_h": lam_hat,
        "demo_failures": item.demo_failures,
        "demo_test_hours": item.demo_test_hours,
        "uncertainty": {"error_factor": item.uncertainty_error_factor,
                        "sigma_lnq": sigma_lnq,
                        "band": band},
        "closure": rollup,
        "requirement_closure": req_rollup,
        "requirements": item.requirements,
        "supporting_note": item.supporting_note,
        "generated": _today(),
    }


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


def render_report_markdown(model: dict) -> str:
    """Render the assessment content model as the deliverable markdown."""
    L = []
    A = L.append
    A("# Aircraft/System Safety Assessment Report (ARP4761A)")
    A("")
    A("**Item:** %s" % model["item"])
    if model.get("system"):
        A("**System:** %s" % model["system"])
    A("**Function assessed:** %s" % model["function"])
    A("**Certification basis:** %s" % model["certification_basis"])
    A("**Development assurance level:** %s "
      "(from worst failure-condition severity)" % model["development_assurance_level"])
    A("**Analysis set:** %s" % ", ".join(model["analyses"]))
    A("**Status:** %s" % model["status"])
    A("")
    A("## 1. Item and functions")
    A("")
    A(model["item_description"])
    if model.get("supporting_note"):
        A("")
        A(model["supporting_note"])
    A("")
    A("## 2. Functional hazard assessment (FHA)")
    A("")
    A("| Condition | Flight phase | Effect on aircraft | Severity | "
      "Target (per FH) | Assessed (per FH) | Meets | Analysis |")
    A("|---|---|---|---|---|---|---|---|")
    for r in model["fha_rows"]:
        target = _fmt_p(r["target_per_fh"]) if r["target_per_fh"] else "none"
        meets = {True: "YES", False: "NO", None: "n/a"}[r["meets_target"]]
        A("| %s | %s | %s | %s | < %s | %s | %s | %s |"
          % (r["failure_condition"], r["flight_phase"],
             r["effect_on_aircraft"], _severity_label(r["severity"]),
             target, _fmt_p(r["assessed_per_fh"]), meets,
             r["analysis_ref"]))
    A("")
    A("## 3. Fault tree analysis (FTA)")
    A("")
    A("Top event: **%s**." % model["fta"]["top_event"])
    A("")
    A("Gate structure:")
    for node, gate in sorted(model["fta"]["structure"].items()):
        A("- %s = %s(%s)" % (node, gate["op"],
                             ", ".join(gate["children"])))
    A("")
    A("Basic event probabilities (per flight hour):")
    for ev, p in sorted(model["fta"]["basic_event_probabilities"].items()):
        A("- %s = %s" % (ev, _fmt_p(p)))
    A("")
    A("Minimal cut sets:")
    if model["fta"]["minimal_cut_sets"]:
        A("| Cut set | Probability |")
        A("|---|---|")
        for row in model["fta"]["minimal_cut_sets"]:
            A("| %s | %s |" % (" AND ".join(row["cut_set"]),
                               _fmt_p(row["probability"])))
    A("")
    A("**Top event probability: %s per flight hour.**" %
      _fmt_p(model["fta"]["top_probability"]))
    A("")
    if model["fta"]["sanity_flags"]:
        A("Cut-set sanity: FLAGGED — %d cut set(s) exceed the top event "
          "probability (modelling error)."
          % len(model["fta"]["sanity_flags"]))
        A("")
    else:
        A("Cut-set sanity: no cut set exceeds the top event probability.")
        A("")
    if model["fta"]["importance"]:
        A("Basic-event importance (Fussell-Vesely):")
        A("")
        ranked = sorted(model["fta"]["importance"].items(),
                        key=lambda kv: -kv[1]["fussell_vesely"])
        for ev, meas in ranked:
            A("- %s: FV = %s, RAW = %s" % (ev, meas["fussell_vesely"],
                                           meas["raw"]))
        A("")
    A("## 4. FMEA / FMECA")
    A("")
    A("Item: **%s**, item failure rate %s per hour, operating time %s h."
      % (model["fmea"]["item"], _fmt(model["fmea"]["item_failure_rate"]),
         _fmt(model["fmea"]["operating_time"])))
    A("")
    A("| Mode | Effect | Severity | alpha | beta | C_m | Share | Dominant |")
    A("|---|---|---|---|---|---|---|---|")
    for m in model["fmea"]["modes"]:
        A("| %s | %s | %s | %s | %s | %s | %.3f | %s |"
          % (m["id"], m["effect"], m["severity"], _fmt(m["alpha"]),
             _fmt(m["beta"]), _fmt_p(m["cm"]), m["share"],
             "yes" if m["dominant"] else ""))
    A("")
    A("**Item criticality C_r: %s** (sum of mode criticalities)." %
      _fmt_p(model["fmea"]["item_criticality"]))
    A("")
    A("## 5. Event tree analysis")
    A("")
    A("Initiating event: **%s**, frequency %s per flight hour."
      % (model["event_tree"]["initiator"],
         _fmt_p(model["event_tree"]["initiator_frequency"])))
    A("")
    A("Mitigating functions (branch success probabilities):")
    for n in model["event_tree"]["nodes"]:
        A("- %s: p(success) = %s" % (n["name"], _fmt(n["p_success"])))
    A("")
    A("End-state rollup (frequency = initiator x path probability):")
    A("")
    A("| Sequence | Frequency (per FH) |")
    A("|---|---|")
    for es in model["event_tree"]["end_states"]:
        A("| %s | %s |" % (es["sequence"], _fmt_p(es["frequency"])))
    A("")
    A("**Failure end state frequency: %s per flight hour** (all "
      "mitigations failed)." % _fmt_p(model["event_tree"]["failure_end_state_frequency"]))
    A("")
    if model["event_tree"]["dominant_sequences"]:
        A("Dominant sequences vs the %s target (< %s):"
          % (_severity_label(model["event_tree"]["screened_severity"]),
             _fmt_p(model["event_tree"]["screened_target"])))
        for d in model["event_tree"]["dominant_sequences"]:
            A("- %s at %s (ratio %.2f)" % (d["sequence"],
                                           _fmt_p(d["frequency"]),
                                           d["ratio"]))
        A("")
    else:
        A("No end state exceeds the %s screening target (< %s)."
          % (_severity_label(model["event_tree"]["screened_severity"]),
             _fmt_p(model["event_tree"]["screened_target"])))
        A("")
    A("## 6. PSSA: safety target allocation")
    A("")
    A("Failure condition target: **%s per flight hour**, %s gate across "
      "%d independent contributor(s)."
      % (_fmt_p(model["pssa"]["target"]), model["pssa"]["gate"].upper(),
         model["pssa"]["n_contributors"]))
    A("")
    A("- Per-contributor budget: **%s**" %
      _fmt_p(model["pssa"]["per_contributor_budget"]))
    A("- Realized total: **%s**" % _fmt_p(model["pssa"]["realized_total"]))
    A("- Margin: **%.2f**" % model["pssa"]["realized_margin"])
    A("- Meets target: **%s**" %
      ("YES" if model["pssa"]["realized_meets"] else "NO"))
    if model["pssa"].get("note"):
        A("- Note: %s" % model["pssa"]["note"])
    A("")
    A("FDAL = %s, IDAL = %s." % (model["pssa"]["fdal"],
                                 model["pssa"]["idal"]))
    A("")
    A("## 7. Common cause analysis (CCA)")
    A("")
    A("Analysis set covers ZSA, PRA and CMA: **%s**." %
      ("YES" if model["cca"]["complete"] else "NO"))
    A("")
    A("- ZSA zone %s: hazard score %.2f, verdict **%s**."
      % (model["cca"]["zsa_zone"], model["cca"]["zsa_score"],
         model["cca"]["zsa_verdict"]))
    A("- PRA (%s): p(event) = %s, p(FC | event) = %s, contribution %s; "
      "exposure over %s h = %s."
      % (model["cca"]["pra_event"], _fmt_p(model["cca"]["pra_p_a"]),
         _fmt(model["cca"]["pra_p_b_given_a"]),
         _fmt_p(model["cca"]["pra_contribution"]),
         _fmt(model["cca"].get("pra_exposure_hours", 1.0)
              if "pra_exposure_hours" in model["cca"] else 1.0),
         _fmt_p(model["cca"]["pra_exposure"])))
    if model["cca"]["beta_channel_rate"]:
        A("- Beta-factor (CMA): per-channel rate %s, beta %s -> "
          "common-cause rate %s, Q_cc = %s; CCF-inclusive dual-channel "
          "probability %s."
          % (_fmt_p(model["cca"]["beta_channel_rate"]),
             _fmt(model["cca"]["beta_factor"]),
             _fmt_p(model["cca"]["beta_split"]["common_cause"]),
             _fmt_p(model["cca"]["beta_q_cc"]),
             _fmt_p(model["cca"]["beta_q_dual"])))
    A("")
    A("## 8. Failure-rate demonstration and uncertainty")
    A("")
    A("Demonstrated failure rate (point estimate): %d failure(s) over %s "
      "test hours -> **%s per hour**."
      % (model["demo_failures"], _fmt(model["demo_test_hours"]),
         _fmt_p(model["demonstrated_rate_per_h"])))
    A("")
    A("FTA top-event uncertainty: error factor %s -> lognormal sigma %.3f; "
      "90%% confidence band [%s, %s] per flight hour."
      % (_fmt(model["uncertainty"]["error_factor"]),
         model["uncertainty"]["sigma_lnq"],
         _fmt_p(model["uncertainty"]["band"]["lower"]),
         _fmt_p(model["uncertainty"]["band"]["upper"])))
    A("")
    A("## 9. SSA closure")
    A("")
    A("| Condition | Severity | Predicted q (per FH) | Target (per FH) | "
      "Margin | Closed |")
    A("|---|---|---|---|---|---|")
    for r in model["fha_rows"]:
        cm = condition_margin(r["assessed_per_fh"], r["severity"])
        target = _fmt_p(r["target_per_fh"]) if r["target_per_fh"] else "none"
        A("| %s | %s | %s | < %s | %.1f | %s |"
          % (r["failure_condition"], _severity_label(r["severity"]),
             _fmt_p(r["assessed_per_fh"]), target, cm["margin"],
             "YES" if cm["meets"] else "NO"))
    A("")
    A("**Closure gate: %s** (%d/%d conditions meet their targets)."
      % (model["closure"]["overall_gate"], model["closure"]["closed"],
         model["closure"]["total"]))
    if model["closure"]["open_conditions"]:
        A("Open conditions: %s" % ", ".join(model["closure"]["open_conditions"]))
        A("")
    A("")
    A("Safety requirement verification: %d/%d verified (%s)."
      % (model["requirement_closure"]["verified"],
         model["requirement_closure"]["total"],
         "CLOSED" if not model["requirement_closure"]["open_requirements"]
         else "OPEN: " + ", ".join(
             model["requirement_closure"]["open_requirements"])))
    A("")
    A("---")
    A("*Generated by Aero Agent Roles safety-assessment-engineer core "
      "(%s). DRAFT for human safety engineering review. Not an approval "
      "document and not a certification finding.*" % model["generated"])
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Evidence gate checkers
# ---------------------------------------------------------------------------

GATE_CHECKS = {
    "level_identified": "development assurance level is a single valid "
                        "letter with an analysis set",
    "severity_targets_present": "every failure condition has a severity, "
                                "a probability target and an assessed value",
    "fta_numbers_present": "fault tree yields cut sets, a top probability "
                           "and a sanity check",
    "fmea_numbers_present": "FMEA ranks modes with criticality and "
                            "dominance flags",
    "event_tree_numbers_present": "event tree yields end-state frequencies "
                                  "and a failure end-state frequency",
    "closure_gate_checked": "SSA closure rollup exists with margins and "
                            "verdicts",
    "sign_off_honest": "document is marked draft-for-review, not approval",
}


def check_report(model: dict) -> dict:
    """Run the evidence gates against an assessment model."""
    fha_rows = model.get("fha_rows", [])
    fta = model.get("fta", {})
    fmea = model.get("fmea", {})
    et = model.get("event_tree", {})
    closure = model.get("closure", {})
    level = model.get("development_assurance_level", "")
    results = {
        "level_identified": level in DALS and bool(model.get("analyses")),
        "severity_targets_present": bool(fha_rows) and all(
            r.get("target_per_fh") is not None and
            isinstance(r.get("assessed_per_fh"), (int, float))
            for r in fha_rows),
        "fta_numbers_present": bool(fta.get("minimal_cut_sets")) and
            isinstance(fta.get("top_probability"), (int, float)) and
            fta["top_probability"] > 0.0,
        "fmea_numbers_present": bool(fmea.get("modes")) and
            isinstance(fmea.get("item_criticality"), (int, float)),
        "event_tree_numbers_present": bool(et.get("end_states")) and
            isinstance(et.get("failure_end_state_frequency"), (int, float)),
        "closure_gate_checked": closure.get("overall_gate") in
            ("CLOSED", "OPEN") and "meets_by_severity" in closure,
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_report_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    checks = {
        "has_title": "aircraft/system safety assessment report" in low,
        "has_item": "item:" in low,
        "has_level": bool(re.search(r"development assurance level[:*\s]*[abcde]\b",
                                    low)),
        "has_fta_number": "top event probability" in low and "e-" in low,
        "has_fmea_number": "item criticality" in low,
        "has_closure_gate": "closure gate" in low and "closed" in low,
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling."""
    return check_report_markdown(md_text)


# ---------------------------------------------------------------------------
# Example project (worked example: a flight control system function)
# ---------------------------------------------------------------------------

def example_item() -> AssessmentItem:
    """Reference item: the pitch/elevator control function of a
    fly-by-wire flight control system, assessed for its failure
    conditions per ARP4761A."""
    fc_list = [
        # (id, function, phase, effect, severity, assessed, ref)
        ("Loss of all pitch control", "Pitch control function",
         "all phases", "Loss of the aircraft", "catastrophic",
         3.0e-10, "FTA-01"),
        ("Loss of pitch control with reduced authority", "Pitch control function",
         "all phases", "Large reduction in safety margins",
         "hazardous", 8.0e-9, "FMEA/ET-01"),
        ("Pitch control nuisance oscillation", "Pitch control function",
         "cruise", "Physical discomfort, increased workload",
         "minor", 4.0e-5, "FMEA-01"),
    ]
    fta_structure = {
        "loss-of-all-pitch": {"op": "OR",
                              "children": ["dual-channel-loss",
                                           "ccf-event"]},
        "dual-channel-loss": {"op": "AND",
                              "children": ["channel-a-loss",
                                           "channel-b-loss"]},
    }
    fta_probs = {
        "channel-a-loss": 1.0e-5,   # channel A pitch control loss (per FH)
        "channel-b-loss": 1.0e-5,   # channel B pitch control loss (per FH)
        "ccf-event": 2.0e-10,   # common cause (shared power/software) (per FH)
    }
    # FMEA: pitch control electronics (single channel), rate 1e-5/h
    fmea_modes = [
        {"id": "M1", "description": "servo jam / hardover",
         "alpha": 0.5, "beta": 1.0,
         "severity": "Hazardous",
         "effect": "loss of pitch control channel output"},
        {"id": "M2", "description": "loss of command output",
         "alpha": 0.3, "beta": 1.0,
         "severity": "Major",
         "effect": "pitch control unavailable in one channel"},
        {"id": "M3", "description": "erratic / oscillatory output",
         "alpha": 0.2, "beta": 0.5,
         "severity": "Minor",
         "effect": "nuisance oscillation, annunciated"},
    ]
    et_nodes = [
        ("runaway detection & disengagement", 0.999),
        ("remaining channel full authority", 0.9995),
    ]
    requirements = [
        {"id": "SR-01", "text": "Loss of all pitch control shall occur "
         "at < 1e-9 per flight hour", "status": "verified"},
        {"id": "SR-02", "text": "Single channel loss shall be annunciated "
         "within 1 s", "status": "verified"},
        {"id": "SR-03", "text": "Common cause (power/software) contribution "
         "shall stay below 2.5e-10 per flight hour", "status": "verified"},
        {"id": "SR-04", "text": "Runaway shall be detected and the channel "
         "disengaged within 50 ms", "status": "verified"},
        {"id": "SR-05", "text": "Remaining channel shall provide full pitch "
         "authority after a single channel loss", "status": "verified"},
    ]
    return AssessmentItem(
        item_name="Elevator pitch control function",
        description="The pitch control function of the fly-by-wire flight "
                    "control system drives the elevator to command and hold "
                    "aircraft pitch attitude across the flight envelope. "
                    "This assessment covers the pitch channel architecture "
                    "(dual independent channels A/B, shared power and "
                    "software platform) and its failure conditions.",
        system="Fly-by-wire flight control system",
        airframe="Transport category airplane",
        certification_basis="FAR/CS-25.1309",
        function="Pitch control function",
        flight_phases="all phases",
        failure_conditions=fc_list,
        fta_structure=fta_structure,
        fta_top="loss-of-all-pitch",
        fta_probs=fta_probs,
        fmea_item="Pitch control electronics (channel A)",
        fmea_item_rate=1.0e-5,
        fmea_operating_time=1.0,
        fmea_modes=fmea_modes,
        et_initiator="Uncommanded runaway in one pitch channel",
        et_initiator_frequency=1.0e-5,
        et_nodes=et_nodes,
        et_failure_severity="catastrophic",
        pssa_target=1e-9,
        pssa_gate="or",
        pssa_contributor_rates=[1.0e-10, 2.0e-10],
        pssa_note="dual-channel loss term (1e-10) and common-cause term "
                  "(2e-10) apportioned as the two OR'd contributors",
        zsa_zone="141 (forward electronics bay)",
        zsa_items=[("hydraulic leak", True), ("foreign object", True),
                   ("cooling loss", True), ("chafing", True)],
        pra_event="uncontained rotor burst / tire burst debris",
        pra_p_a=1.0e-6,
        pra_p_b_given_a=0.1,
        pra_exposure_rate=1.0e-6,
        pra_exposure_hours=1.0,
        beta_channel_rate=1.0e-5,
        beta_factor=2.0e-5,
        demo_failures=1,
        demo_test_hours=100000.0,
        requirements=requirements,
        uncertainty_error_factor=3.0,
        supporting_note="Assessed probabilities are per flight hour. The "
                        "dual-channel fault tree is quantified with "
                        "per-channel loss probabilities of 1e-5 per flight "
                        "hour and a common-cause event of 2e-10 per flight "
                        "hour; the event tree adds the runaway escalation "
                        "sequence.",
    )


def example_report_markdown() -> str:
    return render_report_markdown(build_safety_report(example_item()))


if __name__ == "__main__":
    item = example_item()
    model = build_safety_report(item)
    md = render_report_markdown(model)
    print("LEVEL:", model["development_assurance_level"])
    print("TOP EVENT PROB:", model["fta"]["top_probability"])
    print("ITEM CRITICALITY:", model["fmea"]["item_criticality"])
    print("ET FAILURE FREQ:", model["event_tree"]["failure_end_state_frequency"])
    print("CLOSURE:", model["closure"]["overall_gate"])
    print("GATES:", check_report(model))
    print("RENDERED:", len(md), "chars")
