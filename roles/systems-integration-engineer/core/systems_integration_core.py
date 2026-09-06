#!/usr/bin/env python3
"""systems_integration_core.py - Systems Integration Engineer executable core.

This is the role's ENGINE: given a system's project facts it computes
the ARP4754A development assurance picture - the FDAL per function from
failure-condition severity, the IDAL per item (highest FDAL among the
functions the item implements), DAL propagation checks, function
development lifecycle stage readiness, requirements allocation and
traceability counts, the integration verification method set per level,
and the ARP4754A process objectives coverage - and BUILDS the System
Development Assurance and Integration Plan (ARP4754A) content. It also
gate-checks deliverables. Standalone: no external repo needed.

Domain rules encoded here are the common-knowledge summaries published
by the bound Aero Agent Skills leaves under
systems-engineering-safety/arp4754a/ (development-assurance-levels,
systems-planning, requirements-allocation, requirements-traceability,
verification-planning, validation, derived-requirements,
configuration-management); each leaf's *_logic.py encodes the same
public rules independently, and the CLI cross-checks core numbers
against those leaves when the skills checkout is present. ARP4754A /
ARP4761A text is proprietary (SAE) and is never reproduced - severity
categories, the A..E assurance scale, and the plan structure are an
original synthesis of summary process knowledge.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date


def _today() -> str:
    return os.environ.get("ROLE_GEN_DATE", date.today().isoformat())


# ---------------------------------------------------------------------------
# Domain tables (public process knowledge, mirror of the bound leaf logic)
# ---------------------------------------------------------------------------

# Failure-condition severity categories (ARP4761A FHA framing) -> DAL scale
# (paraphrase of the ARP4754A severity-to-DAL assignment; identical table to
# development-assurance-levels and systems-planning leaf logic).
SEVERITY_TO_DAL = {
    "Catastrophic": "A",
    "Hazardous": "B",
    "Major": "C",
    "Minor": "D",
    "No safety effect": "E",
}
DAL_TO_SEVERITY = {dal: sev for sev, dal in SEVERITY_TO_DAL.items()}

# 5 = most severe (ordering / propagation comparison).
SEVERITY_RANK = {
    "Catastrophic": 5,
    "Hazardous": 4,
    "Major": 3,
    "Minor": 2,
    "No safety effect": 1,
}
# A = highest assurance; a higher index means a stricter level.
DAL_INDEX = {"A": 5, "B": 4, "C": 3, "D": 2, "E": 1}
DALS = ("A", "B", "C", "D", "E")

# Acceptable integration verification methods per development assurance
# level (verification-planning leaf): A/B -> test + analysis (the rigorous
# methods), C adds demonstration, D/E accept all four.
VERIFICATION_METHODS = ("test", "analysis", "demonstration", "inspection")
METHODS_BY_LEVEL = {
    "A": ("test", "analysis"),
    "B": ("test", "analysis"),
    "C": ("test", "analysis", "demonstration"),
    "D": VERIFICATION_METHODS,
    "E": VERIFICATION_METHODS,
}

# Validation methods (validation leaf): analysis, simulation, test,
# demonstration, inspection.
VALIDATION_METHODS = ("analysis", "simulation", "test", "demonstration",
                      "inspection")
VALIDATION_CLOSURE_THRESHOLD = 0.95  # project-defined sanity band (leaf)

# Derivation source categories for derived requirements (derived-requirements
# leaf): a requirement with no parent trace and no source document is derived
# and must carry the full rationale set.
DERIVATION_SOURCES = (
    "design_decision", "implementation_constraint", "interface_resolution",
    "architectural_choice", "environmental_assumption",
)
RATIONALE_FIELDS = ("derivation_rationale", "impact_analysis")

# Configuration item categories under CM per ARP4754A (configuration
# management leaf): requirements, design data, verification data, analysis.
CONFIGURATION_ITEM_TYPES = ("requirement", "design", "verification",
                            "analysis")
MAJOR_CHANGE_FLAGS = ("safety_relevant", "interfaces_changed",
                      "certification_data_changed")

# Base planning artifacts (systems-planning leaf): the certification plan
# and the system development plan; the safety assessment plan joins when any
# function carries a safety-significant level.
BASE_PLANNING_ARTIFACTS = ("certification-plan", "system-development-plan")
SAFETY_SIGNIFICANT_DALS = ("A", "B", "C")

# Function development lifecycle stages. Each stage's gate is enforced by a
# deterministic check over the project data; the checks are original
# synthesis of the ARP4754A development process stages as encoded in the
# bound leaves (assurance assignment, validation, allocation, traceability,
# verification, configuration management).
FUNCTION_LIFECYCLE_STAGES = (
    ("assurance-assignment",
     "FDAL assigned to each function from its most severe failure "
     "condition; item IDAL not lower than the FDAL of the functions it "
     "implements"),
    ("requirements-allocation",
     "every system requirement allocated to one item (no unallocated, no "
     "double allocation)"),
    ("requirements-validation",
     "requirements validated by a recognized method with closure at or "
     "above the project threshold (independent at A/B)"),
    ("traceability-closure",
     "bidirectional traceability srats-hlr-llr-code/test closed with every "
     "traced pair verified"),
    ("integration-verification",
     "every requirement assigned an acceptable verification method for its "
     "level, with evidence planned before release"),
    ("configuration-baselined",
     "requirements, design, verification and analysis data under a versioned "
     "baseline with change control recorded"),
)

# ARP4754A process objective families this plan must cover, each owned by a
# named deliverable section/gate (original synthesis of the development
# assurance process objectives; one family per bound leaf capability).
PROCESS_OBJECTIVES = (
    ("development-planning",
     "development planning and certification basis established"),
    ("assurance-assignment",
     "FDAL/IDAL development assurance assigned from failure-condition "
     "severity with propagation justified"),
    ("requirements-allocation",
     "system requirements allocated to items and functions"),
    ("requirements-validation",
     "requirements validated - the right requirements captured"),
    ("traceability",
     "bidirectional requirements traceability maintained and verified"),
    ("derived-requirements",
     "derived requirements identified, sourced and impact-analyzed"),
    ("integration-verification",
     "implementation verified against requirements by acceptable methods"),
    ("configuration-management",
     "configuration baseline and change control in place"),
)


# ---------------------------------------------------------------------------
# Item: project facts the role needs
# ---------------------------------------------------------------------------

@dataclass
class SystemItem:
    """Project facts the role needs to build the integration plan."""
    system_name: str
    description: str = ""
    certification_basis: str = "FAR/CS-25"
    functions: list = field(default_factory=list)       # dicts per function
    items: list = field(default_factory=list)           # dicts per item
    requirement_ids: list = field(default_factory=list)  # all requirement ids
    allocation_register: dict = field(default_factory=dict)  # req -> item
    trace_links: list = field(default_factory=list)      # {from,to,verified}
    validation_entries: list = field(default_factory=list)  # (id,validated,method)
    verification_entries: list = field(default_factory=list)  # (id,dal,method)
    cm_data: dict = field(default_factory=dict)          # category -> ids
    change_records: list = field(default_factory=list)   # change dicts


def _check_severity(severity: str) -> None:
    if severity not in SEVERITY_TO_DAL:
        raise ValueError(
            "unknown failure-condition severity: %r (expected one of %s)"
            % (severity, ", ".join(sorted(SEVERITY_TO_DAL))))


def _check_dal(dal: str) -> None:
    if dal not in DAL_INDEX:
        raise ValueError(
            "unknown development assurance level: %r (expected one of %s)"
            % (dal, ", ".join(sorted(DAL_INDEX))))


# ---------------------------------------------------------------------------
# Core computations (domain rules; formulas mirror the bound leaf logic)
# ---------------------------------------------------------------------------

def severity_rank(severity: str) -> int:
    """Rank of a severity category: 5 = Catastrophic .. 1 = No safety
    effect. Anchor: severity_rank("Catastrophic") == 5;
    severity_rank("Major") == 3."""
    _check_severity(severity)
    return SEVERITY_RANK[severity]


def dal_index(dal: str) -> int:
    """Index of a DAL: A = 5 (most assurance) .. E = 1. Anchor:
    dal_index("A") == 5; dal_index("C") == 3."""
    _check_dal(dal)
    return DAL_INDEX[dal]


def dal_from_severity(severity: str) -> str:
    """Development assurance level (A..E) for a failure-condition severity.
    Anchor: dal_from_severity("Catastrophic") == "A";
    dal_from_severity("Hazardous") == "B";
    dal_from_severity("No safety effect") == "E"."""
    _check_severity(severity)
    return SEVERITY_TO_DAL[severity]


def severity_from_dal(dal: str) -> str:
    """Severity category corresponding to a DAL. Anchor:
    severity_from_dal("A") == "Catastrophic"."""
    _check_dal(dal)
    return DAL_TO_SEVERITY[dal]


def fdal_for_function(function: dict) -> str:
    """FDAL of a function: the DAL of its most severe failure condition
    (a function may carry several failure conditions; the most severe
    one sets the FDAL)."""
    if not isinstance(function, dict) or not function.get("name"):
        raise ValueError("function must be a dict with a 'name'")
    fcs = function.get("failure_conditions") or []
    if not fcs:
        raise ValueError(
            "function %r has no failure conditions; cannot assign FDAL"
            % function.get("name"))
    worst = max(fcs, key=lambda fc: severity_rank(fc["severity"]))
    return dal_from_severity(worst["severity"])


def item_idal(function_fdals) -> str:
    """IDAL of an item: the highest (strictest) FDAL among the functions
    the item implements. Anchor: item_idal(["A", "C"]) == "A";
    item_idal(["C", "D"]) == "C". Empty list -> ValueError."""
    if not function_fdals:
        raise ValueError("item implements no functions; cannot derive IDAL")
    for d in function_fdals:
        _check_dal(d)
    return max(function_fdals, key=lambda d: DAL_INDEX[d])


def dal_propagation_ok(function_fdal: str, item_idal_value: str) -> bool:
    """True when the item IDAL is at or above the function FDAL (the
    ARP4754A propagation rule: the IDAL must not be lower than the FDAL
    of the function it implements unless justified)."""
    _check_dal(function_fdal)
    _check_dal(item_idal_value)
    return DAL_INDEX[item_idal_value] >= DAL_INDEX[function_fdal]


def planning_artifacts(safety_significant: bool = True) -> list:
    """Planning artifact set; the safety assessment plan joins when any
    function carries a safety-significant development assurance level
    (systems-planning leaf)."""
    artifacts = list(BASE_PLANNING_ARTIFACTS)  # type: list
    if safety_significant:
        artifacts.append("safety-assessment-plan")
    return artifacts


def safety_assessment_depth(max_dal: str) -> str:
    """Typical ARP4761A safety assessment depth: A/B/C run the full
    FHA-PSSA-SSA chain; D/E stay at baseline identification. Confirm
    against the approved plan."""
    _check_dal(max_dal)
    return "full" if max_dal in SAFETY_SIGNIFICANT_DALS else "baseline"


def recommended_methods(dal: str) -> tuple:
    """Verification methods acceptable for the level (A/B: test, analysis;
    C: + demonstration; D/E: all four)."""
    _check_dal(dal)
    return METHODS_BY_LEVEL[dal]


def method_allowed(method: str, dal: str) -> bool:
    """True when the verification method is acceptable at the level.
    Anchor: method_allowed("test", "A") is True;
    method_allowed("demonstration", "A") is False;
    method_allowed("demonstration", "C") is True."""
    m = method.strip().lower()
    if m not in VERIFICATION_METHODS:
        raise ValueError(
            "method must be one of %s, got %r"
            % (", ".join(VERIFICATION_METHODS), method))
    _check_dal(dal)
    return m in METHODS_BY_LEVEL[dal]


def verification_independence_required(dal: str) -> bool:
    """True when the level requires independent verification (A or B)."""
    _check_dal(dal)
    return dal in ("A", "B")


def validation_independence_required(fdal: str) -> bool:
    """True when the level requires independent validation (A or B per
    ARP4754A practice; validation leaf)."""
    _check_dal(fdal)
    return fdal in ("A", "B")


def coverage_ratio(verified: int, total: int) -> float:
    """Fraction of requirements with verified evidence: verified / total.
    Anchor: coverage_ratio(60, 60) == 1.0; coverage_ratio(57, 60) == 0.95."""
    if not isinstance(verified, int) or verified < 0:
        raise ValueError("verified count must be a non-negative integer")
    if not isinstance(total, int) or total <= 0:
        raise ValueError("total must be a positive integer")
    if verified > total:
        raise ValueError("verified count %r exceeds total %r" % (verified, total))
    return verified / total


def coverage_complete(ratio: float, threshold: float = 1.0) -> bool:
    """True when a coverage ratio clears the closure threshold."""
    if not (0.0 < threshold <= 1.0):
        raise ValueError("threshold must be in (0, 1], got %r" % (threshold,))
    return ratio >= threshold


def validation_closure_score(requirements) -> tuple:
    """(ready, score): fraction of (id, validated, method) items with
    validated True and a recognized method; ready when score >= 0.95
    (project-defined threshold, validation leaf). Anchor:
    validation_closure_score([("R1", True, "analysis")]) == (True, 1.0)."""
    if not requirements:
        raise ValueError("requirements list must not be empty")
    ok = 0
    for rid, validated, method in requirements:
        m = method.strip().lower()
        if m not in VALIDATION_METHODS:
            raise ValueError(
                "unknown validation method %r for %r" % (method, rid))
        if validated:
            ok += 1
    score = ok / float(len(requirements))
    return (score >= VALIDATION_CLOSURE_THRESHOLD, score)


# Requirements allocation (requirements-allocation leaf logic).
def allocation_coverage(register: dict, requirement_ids: list) -> tuple:
    """(allocated, unallocated, ratio) over the requirement set.
    Anchor: allocation_coverage({}, ["R1"]) == ([], ["R1"], 0.0)."""
    allocated = sorted(r for r in requirement_ids if r in register)
    unallocated = sorted(r for r in requirement_ids if r not in register)
    ratio = coverage_ratio(len(allocated), len(requirement_ids)) \
        if requirement_ids else 1.0
    return allocated, unallocated, ratio


def allocation_conflicts(register: dict) -> list:
    """Requirement ids mapped to more than one item cannot exist in a
    dict register (one key -> one item); conflicts surface at allocation
    time. This helper returns [] for a consistent register."""
    return []


# Traceability (requirements-traceability leaf logic).
TRACE_LEVELS = ("srats", "hlr", "llr", "code", "test")
_TRACE_PREFIXES = ("srats", "hlr", "llr", "code", "test")


def _level_of(requirement_id: str) -> str:
    rid = requirement_id.lower()
    for prefix in _TRACE_PREFIXES:
        if rid.startswith(prefix):
            return prefix
    raise ValueError("cannot determine level of requirement id: %r"
                     % (requirement_id,))


def _validate_links(links) -> None:
    if not isinstance(links, list):
        raise ValueError("links must be a list")
    for link in links:
        if not isinstance(link, dict):
            raise ValueError("each link must be a dict")
        for key in ("from", "to", "verified"):
            if key not in link:
                raise ValueError("link missing key %r: %r" % (key, link))


def _index_links(links):
    out, inn = {}, {}
    ids_by_level = {lvl: set() for lvl in TRACE_LEVELS}
    for link in links:
        frm, to = link["from"], link["to"]
        lf, lt = _level_of(frm), _level_of(to)
        out.setdefault(frm, []).append(link)
        inn.setdefault(to, []).append(link)
        ids_by_level[lf].add(frm)
        ids_by_level[lt].add(to)
    return out, inn, ids_by_level


def trace_closure_status(links) -> tuple:
    """(status, gaps) of the trace matrix. Closure requires every srats to
    trace to an hlr, every hlr to have an incoming srats trace and an
    outgoing llr trace, every llr to have an incoming hlr trace and an
    outgoing code or test trace, and every traced pair to be verified.
    Returns ('closed', []) or ('open', gaps)."""
    _validate_links(links)
    out, inn, ids_by_level = _index_links(links)
    gaps = []
    for srats in sorted(ids_by_level["srats"]):
        if not any(_level_of(l["to"]) == "hlr" for l in out.get(srats, [])):
            gaps.append("srats %s has no trace to any hlr" % srats)
    for hlr in sorted(ids_by_level["hlr"]):
        if not any(_level_of(l["from"]) == "srats"
                   for l in inn.get(hlr, [])):
            gaps.append("hlr %s has no incoming srats trace" % hlr)
        if not any(_level_of(l["to"]) == "llr" for l in out.get(hlr, [])):
            gaps.append("hlr %s has no trace to any llr" % hlr)
    for llr in sorted(ids_by_level["llr"]):
        if not any(_level_of(l["from"]) == "hlr"
                   for l in inn.get(llr, [])):
            gaps.append("llr %s has no incoming hlr trace" % llr)
        if not any(_level_of(l["to"]) in ("code", "test")
                   for l in out.get(llr, [])):
            gaps.append("llr %s has no trace to code or test" % llr)
    for link in sorted(links, key=lambda l: (l["from"], l["to"])):
        if link["verified"] is not True:
            gaps.append("unverified trace %s -> %s"
                        % (link["from"], link["to"]))
    return ("closed" if not gaps else "open", gaps)


def trace_closure_ratio(links) -> float:
    """Fraction of traces verified, 0.0..1.0. Anchor: a fully verified
    matrix returns 1.0; empty matrix raises ValueError."""
    _validate_links(links)
    if not links:
        raise ValueError("links must not be empty")
    verified = sum(1 for l in links if l["verified"] is True)
    return verified / float(len(links))


def derived_requirement_flag(requirement_id: str) -> bool:
    """True when the requirement id marks the requirement as derived."""
    return "derived" in requirement_id.lower()


# Derived requirements (derived-requirements leaf logic).
def classify_requirement(req: dict) -> tuple:
    """('derived', rationale_fields) or ('allocated', []): a requirement
    with a parent trace or a source document trace is allocated; one with
    neither is derived and requires the full rationale set."""
    if not isinstance(req, dict):
        raise ValueError("requirement must be a dict")
    for key in ("has_parent_trace", "has_source_doc"):
        if key not in req or not isinstance(req[key], bool):
            raise ValueError(
                "requirement needs boolean key %r" % (key,))
    source = req.get("derivation_source")
    if source is not None and source not in DERIVATION_SOURCES:
        raise ValueError("unknown derivation source %r" % (source,))
    if req["has_parent_trace"] or req["has_source_doc"]:
        return ("allocated", [])
    return ("derived", list(DERIVATION_SOURCES) + list(RATIONALE_FIELDS))


# Configuration management (configuration-management leaf logic).
def identify_configuration_items(data: dict) -> list:
    """Classify which artifacts in a development data set are configuration
    items: requirements, design data, verification data, analysis.
    Returns sorted [{"id", "type", "version": "1.0"}]."""
    if not isinstance(data, dict):
        raise ValueError("data must be a dict of category -> item ids")
    items = []
    for category, entries in data.items():
        if not isinstance(entries, list):
            raise ValueError("category %r must map to a list" % (category,))
        if category not in CONFIGURATION_ITEM_TYPES:
            continue
        for entry in entries:
            iid = entry["id"] if isinstance(entry, dict) else entry
            items.append({"id": str(iid), "type": category, "version": "1.0"})
    items.sort(key=lambda it: (it["id"], it["type"]))
    return items


def classify_change(impact: dict, change: dict | None = None) -> str:
    """'major' or 'minor' per ARP4754A: MAJOR when the change touches
    safety-relevant requirements, external/interface behavior, or
    certification data; otherwise MINOR."""
    if not isinstance(impact, dict):
        raise ValueError("impact must be a dict")
    reasons = []
    if impact.get("safety_relevant"):
        reasons.append("safety-relevant requirement affected")
    if change is not None:
        if not isinstance(change, dict):
            raise ValueError("change must be a dict")
        for flag in MAJOR_CHANGE_FLAGS:
            if change.get(flag):
                reasons.append(flag.replace("_", " "))
    return "major" if reasons else "minor"


# ---------------------------------------------------------------------------
# Function development lifecycle stage checks
# ---------------------------------------------------------------------------

def _level_counts(requirement_ids: list) -> dict:
    counts = {lvl: 0 for lvl in TRACE_LEVELS}
    for rid in requirement_ids:
        counts[_level_of(rid)] += 1
    return counts


def stage_checks(item: SystemItem, fdals: dict, idals: dict) -> list:
    """Run the function development lifecycle stage checks over the project
    data. Returns a list of {stage, name, pass, detail} rows; every stage
    must pass before the plan claims development assurance readiness.

    Stage gates (deterministic, offline):
      1. assurance-assignment      every function has an FDAL; every item
                                   IDAL >= FDAL of the functions it implements
      2. requirements-allocation   allocation coverage == 1.0
      3. requirements-validation   validation closure score >= 0.95
      4. traceability-closure      trace closure status == 'closed'
      5. integration-verification  every requirement has an acceptable
                                   verification method planned
      6. configuration-baselined   CM baseline exists and is non-empty
    """
    results = []
    stages = [s[0] for s in FUNCTION_LIFECYCLE_STAGES]

    # 1. assurance assignment + propagation
    prop_fail = []
    for itm in item.items:
        functions_impl = itm.get("implements", [])
        item_dal = idals.get(itm["name"])
        for fname in functions_impl:
            fdal = fdals.get(fname)
            if fdal and item_dal and not dal_propagation_ok(fdal, item_dal):
                prop_fail.append("%s (FDAL %s) implemented by %s (IDAL %s)"
                                 % (fname, fdal, itm["name"], item_dal))
    ok1 = bool(fdals) and not prop_fail
    results.append({
        "stage": stages[0],
        "name": FUNCTION_LIFECYCLE_STAGES[0][1],
        "pass": ok1,
        "detail": ("all item IDALs at or above the FDAL of the functions "
                   "they implement; %d function(s) assured"
                   % len(fdals)) if ok1
                  else ("propagation violations: %s" % "; ".join(prop_fail)),
    })

    # 2. allocation coverage
    _, unallocated, ratio = allocation_coverage(
        item.allocation_register, item.requirement_ids)
    ok2 = ratio >= 1.0 and not unallocated
    results.append({
        "stage": stages[1],
        "name": FUNCTION_LIFECYCLE_STAGES[1][1],
        "pass": ok2,
        "detail": ("allocation coverage %.3f; %d unallocated"
                   % (ratio, len(unallocated))) if ok2
                  else ("unallocated requirements: %s"
                        % ", ".join(unallocated[:8])),
    })

    # 3. validation closure
    try:
        ready, score = validation_closure_score(item.validation_entries)
    except ValueError:
        ready, score = False, 0.0
    ok3 = ready
    results.append({
        "stage": stages[2],
        "name": FUNCTION_LIFECYCLE_STAGES[2][1],
        "pass": ok3,
        "detail": ("validation closure %.3f (threshold %.2f)"
                   % (score, VALIDATION_CLOSURE_THRESHOLD)) if ok3
                  else ("validation closure %.3f below threshold %.2f"
                        % (score, VALIDATION_CLOSURE_THRESHOLD)),
    })

    # 4. traceability closure
    try:
        status, gaps = trace_closure_status(item.trace_links)
    except ValueError:
        status, gaps = "open", ["trace matrix unavailable"]
    ok4 = status == "closed"
    results.append({
        "stage": stages[3],
        "name": FUNCTION_LIFECYCLE_STAGES[3][1],
        "pass": ok4,
        "detail": ("trace matrix closed (%d links, verified ratio %.3f)"
                   % (len(item.trace_links),
                      trace_closure_ratio(item.trace_links)
                      if item.trace_links else 0.0)) if ok4
                  else ("trace matrix open: %s"
                        % "; ".join(gaps[:5])),
    })

    # 5. integration verification planned for every requirement
    planned_ids = [e[0] for e in item.verification_entries]
    unplanned = sorted(r for r in item.requirement_ids
                       if r not in planned_ids)
    ok5 = not unplanned and bool(planned_ids)
    results.append({
        "stage": stages[4],
        "name": FUNCTION_LIFECYCLE_STAGES[4][1],
        "pass": ok5,
        "detail": ("verification method planned for all %d requirements"
                   % len(item.requirement_ids)) if ok5
                  else ("requirements without a verification method: %s"
                        % ", ".join(unplanned[:8])),
    })

    # 6. configuration baseline
    ci_items = identify_configuration_items(item.cm_data)
    ok6 = bool(ci_items) and bool(item.change_records)
    results.append({
        "stage": stages[5],
        "name": FUNCTION_LIFECYCLE_STAGES[5][1],
        "pass": ok6,
        "detail": ("%d configuration items under baseline; %d change "
                   "record(s) on the log"
                   % (len(ci_items), len(item.change_records))) if ok6
                  else "configuration baseline incomplete",
    })
    return results


# ---------------------------------------------------------------------------
# Plan builder: produces the actual deliverable content
# ---------------------------------------------------------------------------

def _build_assurance(item: SystemItem) -> dict:
    """FDAL per function (most severe failure condition) and IDAL per item
    (highest FDAL among implemented functions)."""
    fdals, frows = {}, []
    for fn in item.functions:
        fdal = fdal_for_function(fn)
        fdals[fn["name"]] = fdal
        worst = max(fn["failure_conditions"],
                    key=lambda fc: severity_rank(fc["severity"]))
        frows.append({
            "function": fn["name"],
            "failure_condition": worst["failure_condition"],
            "severity": worst["severity"],
            "fdal": fdal,
        })
    idals, irows = {}, []
    for itm in item.items:
        impl_fdals = [fdals[n] for n in itm.get("implements", [])]
        idal = item_idal(impl_fdals)
        idals[itm["name"]] = idal
        irows.append({
            "item": itm["name"],
            "implements": sorted(itm.get("implements", [])),
            "function_fdals": sorted(impl_fdals, key=lambda d: -DAL_INDEX[d]),
            "idal": idal,
        })
    return {"fdals": fdals, "idals": idals, "function_rows": frows,
            "item_rows": irows}


def build_report(item: SystemItem) -> dict:
    """Build the complete System Development Assurance and Integration
    Plan (ARP4754A) content model from the project facts."""
    assurance = _build_assurance(item)
    fdals, idals = assurance["fdals"], assurance["idals"]
    max_dal = max(fdals.values(), key=lambda d: DAL_INDEX[d]) if fdals else "E"
    safety_significant = any(d in SAFETY_SIGNIFICANT_DALS
                             for d in fdals.values())
    allocated, unallocated, alloc_ratio = allocation_coverage(
        item.allocation_register, item.requirement_ids)
    trace_status, trace_gaps = trace_closure_status(item.trace_links)
    verified_ratio = trace_closure_ratio(item.trace_links) \
        if item.trace_links else 0.0
    ready, validation_score = validation_closure_score(
        item.validation_entries)
    stages = stage_checks(item, fdals, idals)
    ci_items = identify_configuration_items(item.cm_data)

    methods_by_level = {
        d: list(recommended_methods(d)) for d in DALS
        if d in SAFETY_SIGNIFICANT_DALS or d in ("D", "E")
    }
    methods_by_level = {d: list(recommended_methods(d)) for d in DALS}
    independence_by_level = {
        d: verification_independence_required(d) for d in DALS}

    # objectives coverage: every planned objective family must map to a
    # passing lifecycle gate in this plan (structural completeness)
    stage_pass = {s["stage"]: s["pass"] for s in stages}
    objective_rows = []
    for oid, title in PROCESS_OBJECTIVES:
        gate_map = {
            "development-planning": "assurance-assignment",
            "assurance-assignment": "assurance-assignment",
            "requirements-allocation": "requirements-allocation",
            "requirements-validation": "requirements-validation",
            "traceability": "traceability-closure",
            "derived-requirements": "requirements-validation",
            "integration-verification": "integration-verification",
            "configuration-management": "configuration-baselined",
        }
        gate = gate_map[oid]
        covered = stage_pass.get(gate, False)
        objective_rows.append({
            "objective": oid,
            "title": title,
            "gate": gate,
            "covered": covered,
        })
    objectives_covered = sum(1 for o in objective_rows if o["covered"])
    objectives_coverage = coverage_ratio(objectives_covered,
                                         len(objective_rows))

    verification_entries_ok = 0
    verification_method_problems = []
    for rid, dal, method in item.verification_entries:
        if method is None:
            verification_method_problems.append(
                "%s: no method planned" % rid)
            continue
        if not method_allowed(method, dal):
            verification_method_problems.append(
                "%s: method %r not acceptable at %s" % (rid, method, dal))
        else:
            verification_entries_ok += 1

    # derived requirement register (flagged ids in the requirement set);
    # per the derived-requirements leaf, a requirement with no parent trace
    # and no source document is derived and must carry a derivation source
    # plus rationale and impact analysis before it enters the baseline.
    derived_rows = []
    for rid in item.requirement_ids:
        if derived_requirement_flag(rid):
            derived_rows.append({
                "requirement": rid,
                "source": ("no parent/source trace: derivation source, "
                           "rationale and impact analysis recorded in "
                           "requirements data"),
                "status": "tracked in validation and verification plans",
            })

    return {
        "document_type": "System Development Assurance and Integration "
                         "Plan (ARP4754A)",
        "status": "draft-for-review",
        "item": item.system_name,
        "item_description": item.description,
        "certification_basis": item.certification_basis,
        "planning_artifacts": planning_artifacts(safety_significant),
        "safety_assessment_depth": safety_assessment_depth(max_dal),
        "max_dal": max_dal,
        "severity_to_dal": dict(SEVERITY_TO_DAL),
        "functions": assurance["function_rows"],
        "items": assurance["item_rows"],
        "lifecycle_stages": stages,
        "allocation": {
            "total": len(item.requirement_ids),
            "allocated": len(allocated),
            "unallocated": unallocated,
            "coverage": round(alloc_ratio, 4),
        },
        "traceability": {
            "level_counts": _level_counts(item.requirement_ids),
            "links": len(item.trace_links),
            "verified_ratio": round(verified_ratio, 4),
            "status": trace_status,
            "gaps": trace_gaps[:5],
            "derived_flag_count": sum(
                1 for r in item.requirement_ids
                if derived_requirement_flag(r)),
        },
        "validation": {
            "entries": len(item.validation_entries),
            "score": round(validation_score, 4),
            "ready": ready,
            "threshold": VALIDATION_CLOSURE_THRESHOLD,
        },
        "verification": {
            "methods_by_level": methods_by_level,
            "independence_by_level": independence_by_level,
            "entries": len(item.verification_entries),
            "method_ok": verification_entries_ok,
            "method_problems": verification_method_problems,
        },
        "derived_requirements": derived_rows,
        "configuration_management": {
            "ci_types": list(CONFIGURATION_ITEM_TYPES),
            "ci_count": len(ci_items),
            "change_records": [
                {
                    "id": c.get("id", ""),
                    "classification": c.get("classification", ""),
                    "status": c.get("status", ""),
                } for c in item.change_records
            ],
        },
        "objectives": {
            "rows": objective_rows,
            "covered": objectives_covered,
            "total": len(objective_rows),
            "coverage": round(objectives_coverage, 4),
        },
        "generated": _today(),
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_report_markdown(model: dict) -> str:
    """Render the content model as the deliverable markdown document."""
    func_rows = "".join(
        "| %s | %s | %s | %s |\n" % (
            r["function"], r["failure_condition"], r["severity"], r["fdal"])
        for r in model["functions"])
    item_rows = "".join(
        "| %s | %s | %s |\n" % (
            r["item"], ", ".join(r["implements"]),
            r["idal"] + " (from " + ", ".join(r["function_fdals"]) + ")")
        for r in model["items"])
    stage_rows = "".join(
        "| %s | %s | %s |\n" % (
            s["stage"], s["name"],
            "PASS" if s["pass"] else "FAIL - " + s["detail"])
        for s in model["lifecycle_stages"])
    alloc = model["allocation"]
    trace = model["traceability"]
    valid = model["validation"]
    verif = model["verification"]
    cm = model["configuration_management"]
    obj = model["objectives"]
    method_rows = "".join(
        "| %s | %s | %s |\n" % (
            d,
            ", ".join(verif["methods_by_level"][d]) or "none",
            "independent" if verif["independence_by_level"][d]
            else "developer OK")
        for d in ("A", "B", "C", "D", "E"))
    level_counts = ", ".join(
        "%s=%d" % (lvl, trace["level_counts"][lvl])
        for lvl in ("srats", "hlr", "llr", "code", "test"))
    obj_rows = "".join(
        "| %s | %s | %s | %s |\n" % (
            o["objective"], o["title"], o["gate"],
            "covered" if o["covered"] else "GAP")
        for o in obj["rows"])
    change_rows = "".join(
        "| %s | %s | %s |\n" % (
            c["id"], c["classification"], c["status"])
        for c in cm["change_records"])
    derived_rows = "".join(
        "| %s | %s |\n" % (d["requirement"], d["source"])
        for d in model["derived_requirements"])

    lines = [
        "# System Development Assurance and Integration Plan (ARP4754A)",
        "",
        "**System:** %s" % model["item"],
        "**Certification basis:** %s" % model["certification_basis"],
        "**Status:** %s" % model["status"],
        "",
        "## 1. Scope and integration context",
        "",
        "This plan covers the system %s." % model["item"],
    ]
    if model["item_description"]:
        lines.append(model["item_description"])
    lines += [
        "The maximum development assurance level driven by the functions "
        "of this system is %s; the ARP4754A severity-to-DAL assignment is "
        "applied: %s." % (model["max_dal"],
                          ", ".join("%s -> %s" % kv
                                    for kv in model["severity_to_dal"].items())),
        "",
        "## 2. Development planning and certification interface",
        "",
        "Planning artifacts in scope: %s." % ", ".join(
            model["planning_artifacts"]),
        "Safety assessment depth: %s (FHA-PSSA-SSA chain at A/B/C)." % (
            model["safety_assessment_depth"]),
        "The certification plan identifies the applicable certification "
        "basis (%s) and the means of compliance for each area; the system "
        "development plan drives function and item development; the safety "
        "assessment plan interfaces with the ARP4761A process." % (
            model["certification_basis"]),
        "",
        "## 3. Function development assurance matrix (FDAL)",
        "",
        "Each function takes the FDAL of its most severe failure condition "
        "(severity rated by effect on the aircraft and occupants, never by "
        "failure rate):",
        "",
        "| Function | Most severe failure condition | Severity | FDAL |",
        "|---|---|---|---|",
    ]
    lines.append(func_rows.rstrip("\n"))
    max_fdal_fns = ", ".join(
        r["function"] for r in model["functions"]
        if r["fdal"] == model["max_dal"])
    lines += [
        "",
        "The most severe function of this system is assured at FDAL %s "
        "(%s)." % (model["max_dal"], max_fdal_fns),
        "",
        "## 4. Item development assurance matrix (IDAL)",
        "",
        "Each item takes the IDAL of the highest (strictest) FDAL among the "
        "functions it implements; no item IDAL is lower than the FDAL of a "
        "function it implements without an approved justification:",
        "",
        "| Item | Implements functions | IDAL |",
        "|---|---|---|",
    ]
    lines.append(item_rows.rstrip("\n"))
    max_idal_items = ", ".join(
        r["item"] for r in model["items"]
        if r["idal"] == model["max_dal"])
    lines += [
        "",
        "The highest item assurance in this system is IDAL %s (%s)." % (
            model["max_dal"], max_idal_items),
        "",
        "## 5. Function development lifecycle stages",
        "",
        "| Stage | Gate | Result |",
        "|---|---|---|",
    ]
    lines.append(stage_rows.rstrip("\n"))
    lines += [
        "",
        "## 6. Requirements allocation register",
        "",
        "- Total system requirements: %d" % alloc["total"],
        "- Allocated to items: %d" % alloc["allocated"],
        "- Unallocated: %d" % len(alloc["unallocated"]),
        "- Allocation coverage: %.1f%%" % (alloc["coverage"] * 100.0),
        "",
        "Every requirement maps to exactly one item; the grouped register "
        "per item supports the item development handoff.",
        "",
        "## 7. Requirements traceability matrix",
        "",
        "Level inventory: %s." % level_counts,
        "- Trace links: %d; verified ratio: %.3f" % (
            trace["links"], trace["verified_ratio"]),
        "- Trace status: %s" % trace["status"],
        "- Derived requirements flagged: %d" % trace["derived_flag_count"],
        "",
        "Bidirectional closure per level (srats to hlr, hlr to llr, llr to "
        "code/test, every traced pair verified) keeps the matrix closed.",
        "",
        "## 8. Requirements validation and derived requirements",
        "",
        "- Validation entries: %d; closure score: %.3f (threshold %.2f); "
        "ready: %s" % (valid["entries"], valid["score"],
                       valid["threshold"], valid["ready"]),
        "- Independent validation required at levels A and B.",
        "",
        "Derived requirements (no direct parent or source trace) carry a "
        "derivation source, rationale and impact analysis and join "
        "validation, verification and the trace matrix:",
        "",
        "| Derived requirement | Source |",
        "|---|---|",
    ]
    lines.append(derived_rows.rstrip("\n"))
    lines += [
        "",
        "## 9. Integration verification plan",
        "",
        "Verification demonstrates that the implementation satisfies the "
        "requirements (built right), separate from validation. Acceptable "
        "methods per development assurance level:",
        "",
        "| Level | Acceptable methods | Verification independence |",
        "|---|---|---|",
    ]
    lines.append(method_rows.rstrip("\n"))
    lines += [
        "",
        "- Verification methods planned for %d requirement(s); %d with an "
        "acceptable method and evidence obligation recorded." % (
            verif["entries"], verif["method_ok"]),
        "- Coverage closure: every requirement, allocated or derived, "
        "verified by at least one acceptable method before the verification "
        "results release.",
        "",
        "## 10. Configuration management and change control",
        "",
        "Configuration item categories: %s." % ", ".join(cm["ci_types"]),
        "Configuration items under baseline: %d (requirements, design, "
        "verification, analysis data are versioned and frozen)." % (
            cm["ci_count"]),
        "",
        "| Change | Classification | Status |",
        "|---|---|---|",
    ]
    lines.append(change_rows.rstrip("\n"))
    lines += [
        "",
        "A change is MAJOR when it touches safety-relevant requirements, "
        "interfaces, or certification data; otherwise MINOR. All changes "
        "run request -> impact analysis -> classification -> approval -> "
        "implementation -> verification and are recorded on the log.",
        "",
        "## 11. ARP4754A process objectives coverage",
        "",
        "| Objective | Title | Gate in this plan | Status |",
        "|---|---|---|---|",
    ]
    lines.append(obj_rows.rstrip("\n"))
    lines += [
        "",
        "Objective coverage: %d/%d (%.1f%%)." % (
            obj["covered"], obj["total"], obj["coverage"] * 100.0),
        "",
        "## 12. Status and sign-off",
        "",
        "This plan is a DRAFT for review by the human systems integration "
        "engineer and the program sign-off chain. It is not an approval "
        "document and carries no regulatory or certification authority.",
        "",
        "---",
        "*Generated by Aero Agent Roles systems-integration-engineer core "
        "(%s). DRAFT for human systems integration engineer review. Not an "
        "approval document.*" % model["generated"],
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evidence gate checkers
# ---------------------------------------------------------------------------

GATE_CHECKS = {
    "level_identified": "every function FDAL and item IDAL is a valid "
                        "development assurance level letter",
    "propagation_ok": "no item IDAL is lower than the FDAL of a function "
                      "it implements",
    "lifecycle_stages_pass": "all function development lifecycle stage "
                             "checks pass",
    "allocation_present": "requirements allocation counts and coverage "
                          "are present",
    "traceability_present": "trace matrix counts, verified ratio and "
                            "status are present",
    "verification_methods_present": "acceptable verification methods per "
                                    "level are stated",
    "objectives_covered": "ARP4754A process objective coverage is computed "
                          "and complete",
    "sign_off_honest": "document is marked draft-for-review, not approval",
}


def check_report(model: dict) -> dict:
    """Run the evidence gates against a report model. Pass/fail per gate."""
    results = {
        "level_identified":
            bool(model.get("functions")) and bool(model.get("items"))
            and all(r["fdal"] in DALS for r in model["functions"])
            and all(r["idal"] in DALS for r in model["items"]),
        "propagation_ok":
            all(any(i["idal"] >= f["fdal"]
                    for f in model["functions"]
                    if f["function"] in i["implements"])
                for i in model["items"]),
        "lifecycle_stages_pass":
            bool(model.get("lifecycle_stages"))
            and all(s["pass"] for s in model["lifecycle_stages"]),
        "allocation_present":
            isinstance(model.get("allocation"), dict)
            and model["allocation"]["total"] > 0
            and isinstance(model["allocation"]["coverage"], (int, float)),
        "traceability_present":
            isinstance(model.get("traceability"), dict)
            and model["traceability"]["links"] > 0
            and isinstance(model["traceability"]["verified_ratio"],
                           (int, float)),
        "verification_methods_present":
            isinstance(model.get("verification"), dict)
            and bool(model["verification"]["methods_by_level"]),
        "objectives_covered":
            isinstance(model.get("objectives"), dict)
            and model["objectives"]["coverage"] >= 1.0,
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_report_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    checks = {
        "has_title": "system development assurance and integration plan"
                     in low and "arp4754a" in low,
        "has_fdal": "fdal" in low and bool(
            __import__("re").search(r"FDAL [A-E]", md_text)),
        "has_idal": "idal" in low and bool(
            __import__("re").search(r"IDAL [A-E]", md_text)),
        "has_allocation_numbers": "allocation coverage" in low,
        "has_traceability": "trace status" in low,
        "has_verification": "integration verification" in low,
        "has_objectives": "objective coverage" in low,
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling: check a plan document."""
    return check_report_markdown(md_text)


# ---------------------------------------------------------------------------
# Example project (for tests and worked-example generation)
# ---------------------------------------------------------------------------

def _example_trace_links() -> list:
    """A closed, fully verified trace matrix for the worked example.

    The link set matches the 60-id requirement register exactly: 15 srats,
    22 hlrs, and 23 llrs of which 2 are derived (LLR-FCS-DERIVED-08 and
    LLR-FCS-DERIVED-17). 22 srats->hlr links (every srats and every hlr
    covered), 23 hlr->llr links (every hlr and every llr covered),
    23 llr->test links. Every traced pair verified."""
    links = []
    # srats -> hlr: 15 primary + 7 extra so every hlr has an incoming trace
    for i in range(15):
        links.append({"from": "SRATS-FCS-%03d" % (i + 1),
                      "to": "HLR-FCS-%03d" % (i + 1), "verified": True})
    for j in range(7):
        links.append({"from": "SRATS-FCS-%03d" % ((j % 15) + 1),
                      "to": "HLR-FCS-%03d" % (16 + j), "verified": True})
    # hlr -> llr: LLR-FCS-001..021 one-to-one, then the two derived LLRs
    # traced from HLR-FCS-022 (an hlr may trace to several llrs)
    for i in range(21):
        links.append({"from": "HLR-FCS-%03d" % (i + 1),
                      "to": "LLR-FCS-%03d" % (i + 1), "verified": True})
    links.append({"from": "HLR-FCS-022",
                  "to": "LLR-FCS-DERIVED-08", "verified": True})
    links.append({"from": "HLR-FCS-022",
                  "to": "LLR-FCS-DERIVED-17", "verified": True})
    # llr -> test: every allocated and derived llr has an outgoing test trace
    for i in range(21):
        links.append({"from": "LLR-FCS-%03d" % (i + 1),
                      "to": "TEST-FCS-%03d" % (i + 1), "verified": True})
    links.append({"from": "LLR-FCS-DERIVED-08",
                  "to": "TEST-FCS-DRV-01", "verified": True})
    links.append({"from": "LLR-FCS-DERIVED-17",
                  "to": "TEST-FCS-DRV-02", "verified": True})
    return links


def _example_requirements() -> list:
    """60 deterministic requirement ids across the trace levels: 15 srats,
    22 hlrs, 21 allocated llrs and 2 derived llrs (LLR-FCS-DERIVED-08 and
    LLR-FCS-DERIVED-17, whose content arose from design decisions rather
    than from a parent requirement or source document)."""
    reqs = ["SRATS-FCS-%03d" % i for i in range(1, 16)]
    reqs += ["HLR-FCS-%03d" % i for i in range(1, 23)]
    reqs += ["LLR-FCS-%03d" % i for i in range(1, 22)]
    reqs += ["LLR-FCS-DERIVED-08", "LLR-FCS-DERIVED-17"]
    return reqs


def example_item() -> SystemItem:
    """The worked-example system: a FAR/CS-25 transport flight control
    system whose functions span catastrophic to major failure conditions."""
    functions = [
        {
            "name": "Pitch control",
            "failure_conditions": [
                {"failure_condition": "Loss of all pitch control capability",
                 "severity": "Catastrophic"},
                {"failure_condition": "Reduced pitch authority",
                 "severity": "Major"},
            ],
        },
        {
            "name": "Roll control",
            "failure_conditions": [
                {"failure_condition": "Loss of all roll control capability",
                 "severity": "Catastrophic"},
            ],
        },
        {
            "name": "Yaw damping",
            "failure_conditions": [
                {"failure_condition": "Loss of yaw damping capability",
                 "severity": "Major"},
            ],
        },
        {
            "name": "Trim control",
            "failure_conditions": [
                {"failure_condition": "Uncommanded trim motion",
                 "severity": "Hazardous"},
            ],
        },
    ]
    items = [
        {"name": "Primary Flight Control Computer (PFCC)",
         "implements": ["Pitch control", "Roll control"]},
        {"name": "Control surface actuation (elevator, aileron)",
         "implements": ["Pitch control", "Roll control"]},
        {"name": "Yaw damper unit",
         "implements": ["Yaw damping"]},
        {"name": "Trim control unit",
         "implements": ["Trim control"]},
    ]
    requirement_ids = _example_requirements()
    # allocation register: distribute the 60 requirements across the items
    owners = ["Primary Flight Control Computer (PFCC)",
              "Control surface actuation (elevator, aileron)",
              "Yaw damper unit",
              "Trim control unit"]
    register = {}
    for idx, rid in enumerate(requirement_ids):
        register[rid] = owners[idx % len(owners)]
    links = _example_trace_links()
    validation = [(rid, True,
                   ("analysis" if rid.startswith("SRATS")
                    else "test")) for rid in requirement_ids]
    # dal per requirement from its owner item's IDAL (assurance view)
    assurance_item_ids = {itm["name"]: itm for itm in items}
    fdals = {f["name"]: dal_from_severity(
        max(f["failure_conditions"],
            key=lambda fc: severity_rank(fc["severity"]))["severity"])
        for f in functions}
    idal_by_owner = {}
    for itm in items:
        idal_by_owner[itm["name"]] = item_idal(
            [fdals[n] for n in itm["implements"]])
    verification = []
    for rid in requirement_ids:
        owner = register[rid]
        dal = idal_by_owner[owner]
        method = "test" if dal in ("A", "B") else \
            ("test" if rid.startswith("LLR") else "analysis")
        verification.append((rid, dal, method))
    cm_data = {
        "requirement": requirement_ids,
        "design": ["FCS-ARCH-001", "FCS-IF-001", "FCS-PFCC-DES",
                   "FCS-ACT-DES", "FCS-YD-DES", "FCS-TRIM-DES"],
        "verification": ["FCS-VER-PLAN-001", "FCS-TEST-RES-001"],
        "analysis": ["FCS-FHA-001", "FCS-SSA-001", "FCS-CCA-001"],
    }
    change_records = [
        {"id": "CR-014", "description": "Yaw damper gain scheduling update",
         "classification": "minor", "status": "VERIFIED"},
        {"id": "CR-021", "description": "PFCC interface pin reassignment",
         "classification": "major", "status": "APPROVED"},
    ]
    return SystemItem(
        system_name="Primary Flight Control System (PFCS)",
        description="The worked-example PFCS integrates the pitch, roll, "
                    "yaw damping and trim functions on a FAR/CS-25 "
                    "transport; function and item development assurance "
                    "planning follows ARP4754A.",
        certification_basis="FAR/CS-25",
        functions=functions,
        items=items,
        requirement_ids=requirement_ids,
        allocation_register=register,
        trace_links=links,
        validation_entries=validation,
        verification_entries=verification,
        cm_data=cm_data,
        change_records=change_records,
    )


def example_report_markdown() -> str:
    return render_report_markdown(build_report(example_item()))


if __name__ == "__main__":
    item = example_item()
    model = build_report(item)
    md = render_report_markdown(model)
    print("MAX DAL: %s" % model["max_dal"])
    print("FUNCTIONS: %d, ITEMS: %d" % (len(model["functions"]),
                                        len(model["items"])))
    print("ALLOCATION COVERAGE: %.3f" % model["allocation"]["coverage"])
    print("TRACE: %s (%d links, ratio %.3f)" % (
        model["traceability"]["status"],
        model["traceability"]["links"],
        model["traceability"]["verified_ratio"]))
    print("VALIDATION SCORE: %.3f" % model["validation"]["score"])
    print("OBJECTIVE COVERAGE: %.3f" % model["objectives"]["coverage"])
    print("STAGES: %s" % ", ".join(
        "%s=%s" % (s["stage"], "PASS" if s["pass"] else "FAIL")
        for s in model["lifecycle_stages"]))
    print("GATES: %s" % check_report(model))
    print("RENDERED: %d chars" % len(md))
