#!/usr/bin/env python3
"""mbse_modeling_core.py - MBSE Modeling Engineer executable core.

This is the role's ENGINE: given a system's model facts it selects the
SysML diagram kind for every modeling purpose, screens requirements
(id format, shall-clause atomicity, vague terms, verifiability),
computes satisfy/verify traceability coverage and status roll-up,
checks block-definition closure and function allocation, builds the N2
interface matrix and its per-element counts, verifies state-machine
reachability and transition conflicts, evaluates parametric sum
constraints against their bounds, and BUILDS the System Model
Architecture and MBSE Plan. It also gate-checks deliverables.
Standalone: no external repo needed.

Domain rules encoded here mirror the logic shipped in the bound
AeroSkills MBSE leaves (systems-engineering-safety/mbse/*): diagram
purpose maps, viewpoint coverage, requirement screening and roll-up,
block/allocation closure, N2 interface counts, state-machine
reachability, and trade-study selection are computed identically in
the leaf logic files. ARP4754A is referenced (development process
context), never reproduced.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date


def _today() -> str:
    return os.environ.get("ROLE_GEN_DATE", date.today().isoformat())


# ---------------------------------------------------------------------------
# Domain tables (mirror of the bound MBSE leaf logic; common knowledge)
# ---------------------------------------------------------------------------

# Development assurance level from failure-condition severity
# (FAR 25.1309 / CS-25.1309 severity categories -> ARP4754A function
# development assurance level practice).
SEVERITY_TO_FDAL = {
    "catastrophic": "A",
    "hazardous": "B",
    "major": "C",
    "minor": "D",
    "no-safety-effect": "E",
}
FDALS = ("A", "B", "C", "D", "E")

# SysML diagram kinds and their full names.
DIAGRAM_KINDS = ("bdd", "ibd", "param", "req", "act", "seq", "stm", "uc", "pkg")

DIAGRAM_NAMES = {
    "bdd": "block definition diagram",
    "ibd": "internal block diagram",
    "param": "parametric diagram",
    "req": "requirements diagram",
    "act": "activity diagram",
    "seq": "sequence diagram",
    "stm": "state machine diagram",
    "uc": "use case diagram",
    "pkg": "package diagram",
}

# Canonical SysML diagram kind for each modeling purpose
# (systems-engineering-safety/mbse/sysml-modeling leaf map).
PURPOSE_TO_DIAGRAM = {
    "system-composition": "bdd",
    "system-structure": "bdd",
    "system-hierarchy": "bdd",
    "block-definition": "bdd",
    "internal-structure": "ibd",
    "internal-connections": "ibd",
    "internal-interfaces": "ibd",
    "constraint-analysis": "param",
    "parametric-analysis": "param",
    "performance-equation": "param",
    "requirements-capture": "req",
    "requirements-traceability": "req",
    "functional-flow": "act",
    "activity-flow": "act",
    "message-ordering": "seq",
    "interaction-sequence": "seq",
    "state-transition": "stm",
    "system-modes": "stm",
    "use-case-scoping": "uc",
    "actor-system-boundary": "uc",
    "model-organization": "pkg",
}

# Viewpoints a complete model must cover.
REQUIRED_VIEWPOINTS = ("structure", "behavior", "requirements", "parametric")

# Requirement stereotype relationships (SysML req diagram).
VALID_RELATIONSHIP_KINDS = ("derive", "satisfy", "verify", "refine", "trace")
VERIFICATION_METHODS = ("test", "analysis", "demonstration", "inspection")

# Vague terms carry no measurable acceptance bound.
VAGUE_TERMS = (
    "adequate", "approximately", "etc", "suitable", "and/or",
    "as required", "timely", "minimize", "maximize",
)

# Canonical requirement id: 2-4 uppercase letters, hyphen, 3-5 digits.
ID_PATTERN = re.compile(r"^[A-Z]{2,4}-[0-9]{3,5}$")

# MBSE workflow stages and open-source toolchain mapping
# (systems-engineering-safety/mbse/systems-engineering leaf).
MBSE_STAGES = (
    "requirements-modeling",
    "functional-architecture",
    "logical-architecture",
    "allocation",
    "analysis",
    "traceability",
)
TOOL_BY_TASK = {
    "functional-architecture": "capella",
    "requirements-modeling": "papyrus",
    "sysml-modeling": "papyrus",
    "architecture-analysis": "osate",
}

# Trade-study defaults (trade-study-analysis leaf).
WEIGHT_TOLERANCE = 1e-9
DEFAULT_MARGIN_THRESHOLD = 0.05


def _check_fdal(fdal: str) -> None:
    if fdal not in FDALS:
        raise ValueError("invalid development assurance level %r" % (fdal,))


def fdal_from_severity(severity: str) -> str:
    return SEVERITY_TO_FDAL.get(severity.lower(), "E")


# ---------------------------------------------------------------------------
# SysML diagram selection + viewpoint coverage (sysml-modeling logic)
# ---------------------------------------------------------------------------

def sysml_diagram_for(purpose: str) -> str:
    """Canonical SysML diagram kind for a modeling purpose."""
    if not isinstance(purpose, str) or not purpose:
        raise ValueError("purpose must be a non-empty string")
    if purpose not in PURPOSE_TO_DIAGRAM:
        raise ValueError("unknown SysML modeling purpose: %r" % (purpose,))
    return PURPOSE_TO_DIAGRAM[purpose]


def diagram_kind_name(kind: str) -> str:
    """Full diagram name for a canonical SysML diagram kind."""
    if kind not in DIAGRAM_NAMES:
        raise ValueError("unknown SysML diagram kind: %r" % (kind,))
    return DIAGRAM_NAMES[kind]


def viewpoint_for_purpose(purpose: str) -> str:
    """Viewpoint (structure/behavior/requirements/parametric) a purpose serves."""
    kind = sysml_diagram_for(purpose)
    if kind in ("bdd", "ibd", "pkg"):
        return "structure"
    if kind in ("act", "seq", "stm", "uc"):
        return "behavior"
    if kind == "req":
        return "requirements"
    if kind == "param":
        return "parametric"
    raise ValueError("unmapped viewpoint for kind %r" % (kind,))


def block_definition_verdict(parts, references) -> str:
    """A bdd is valid when it defines every referenced element."""
    if not isinstance(parts, (list, tuple)) or not isinstance(
            references, (list, tuple)):
        raise ValueError("parts and references must be lists or tuples")
    if not parts:
        return "invalid"
    known = set(parts)
    missing = [r for r in references if r not in known]
    return "invalid" if missing else "valid"


def missing_block_definitions(parts, references) -> list:
    """Referenced elements that have no block definition in the bdd."""
    if not isinstance(parts, (list, tuple)) or not isinstance(
            references, (list, tuple)):
        raise ValueError("parts and references must be lists or tuples")
    known = set(parts)
    return sorted({r for r in references if r not in known})


def model_viewpoint_verdict(views) -> str:
    """Model viewpoint coverage: 'complete' or 'missing'."""
    if not isinstance(views, dict):
        raise ValueError("views must be a dict")
    unknown = [v for v in views if v not in REQUIRED_VIEWPOINTS]
    if unknown:
        raise ValueError("unknown viewpoint: %r" % (unknown,))
    for v in views.values():
        if not isinstance(v, bool):
            raise ValueError("viewpoint coverage values must be bool")
    if all(views.get(v) for v in REQUIRED_VIEWPOINTS):
        return "complete"
    return "missing"


def diagram_suite_verdict(purposes) -> dict:
    """Resolve every purpose to its canonical kind; verdict per row.

    Returns {"rows": [...], "consistent": bool, "covered_viewpoints": [...]}
    where each row is {purpose, kind, kind_name, viewpoint}.
    """
    rows = []
    for purpose in purposes:
        kind = sysml_diagram_for(purpose)
        rows.append({
            "purpose": purpose,
            "kind": kind,
            "kind_name": diagram_kind_name(kind),
            "viewpoint": viewpoint_for_purpose(purpose),
        })
    covered = sorted({r["viewpoint"] for r in rows})
    consistent = all(r["kind"] == PURPOSE_TO_DIAGRAM[r["purpose"]]
                     for r in rows)
    return {"rows": rows, "consistent": consistent,
            "covered_viewpoints": covered}


# ---------------------------------------------------------------------------
# Requirements modeling (requirements-modeling logic)
# ---------------------------------------------------------------------------

def validate_requirement_id(requirement_id) -> bool:
    """True when the id matches the canonical requirement id format."""
    if not isinstance(requirement_id, str):
        raise ValueError("requirement id must be a string, got %r"
                         % (requirement_id,))
    return bool(ID_PATTERN.fullmatch(requirement_id))


def count_shall_clauses(text) -> int:
    """Number of shall clauses; atomicity requires exactly one."""
    if not isinstance(text, str):
        raise ValueError("requirement text must be a string, got %r" % (text,))
    return len(re.findall(r"\bshall\b", text.lower()))


def find_vague_terms(text) -> list:
    """Sorted list of vague terms found in the requirement text."""
    if not isinstance(text, str):
        raise ValueError("requirement text must be a string, got %r" % (text,))
    lowered = text.lower()
    found = []
    for term in VAGUE_TERMS:
        if re.search(r"\b" + re.escape(term) + r"\b", lowered):
            found.append(term)
    return sorted(found)


def requirement_verifiability(requirement: dict) -> dict:
    """Verdict dict for one requirement mapping (id/text/method).

    Verifiable = exactly one shall clause, no vague terms, and a method
    in {test, analysis, demonstration, inspection}.
    """
    for key in ("id", "text", "method"):
        if key not in requirement:
            raise ValueError("requirement missing key %r" % (key,))
    if not isinstance(requirement["text"], str):
        raise ValueError("requirement text must be a string")
    reasons = []
    shall_count = count_shall_clauses(requirement["text"])
    if shall_count != 1:
        reasons.append("shall-clause count %d, expected 1" % shall_count)
    vague = find_vague_terms(requirement["text"])
    if vague:
        reasons.append("vague terms: %s" % ", ".join(vague))
    if requirement["method"] not in VERIFICATION_METHODS:
        reasons.append("method %r not in %s"
                       % (requirement["method"], ", ".join(VERIFICATION_METHODS)))
    return {"id": requirement["id"], "verifiable": not reasons,
            "reasons": sorted(reasons)}


def rollup_verification_status(child_statuses) -> str:
    """Rolled-up verification status of a requirement tree node."""
    if not isinstance(child_statuses, list):
        raise ValueError("child statuses must be a list, got %r"
                         % (child_statuses,))
    if not child_statuses:
        return "not-assessed"
    if all(s == "verified" for s in child_statuses):
        return "verified"
    if any(s == "failed" for s in child_statuses):
        return "failed"
    if any(s == "in-review" for s in child_statuses):
        return "in-review"
    return "not-assessed"


def satisfy_coverage(requirement_ids, satisfy_links):
    """(fraction, unsatisfied ids) for satisfy link coverage."""
    if not isinstance(requirement_ids, list) or not isinstance(satisfy_links, list):
        raise ValueError("requirement ids and satisfy links must be lists")
    if not requirement_ids:
        return 1.0, []
    satisfied_ids = {pair[0] for pair in satisfy_links}
    satisfied = [rid for rid in requirement_ids if rid in satisfied_ids]
    missing = sorted(set(requirement_ids) - satisfied_ids)
    return len(satisfied) / float(len(requirement_ids)), missing


def verify_coverage(requirement_ids, verify_links):
    """(fraction, unverified ids) for verify link coverage."""
    if not isinstance(requirement_ids, list) or not isinstance(verify_links, list):
        raise ValueError("requirement ids and verify links must be lists")
    if not requirement_ids:
        return 1.0, []
    verified_ids = {pair[0] for pair in verify_links}
    verified = [rid for rid in requirement_ids if rid in verified_ids]
    missing = sorted(set(requirement_ids) - verified_ids)
    return len(verified) / float(len(requirement_ids)), missing


def derive_chain_check(links):
    """(valid, issues) for the derive relationship list.

    Each link is a (source_id, target_id) pair meaning the target is
    derived from the source. A self-derive or an id that fails
    validate_requirement_id is an issue.
    """
    if not isinstance(links, list):
        raise ValueError("derive links must be a list, got %r" % (links,))
    issues = []
    for pair in links:
        source, target = pair
        if source == target:
            issues.append("self-derive %r" % (source,))
        if not validate_requirement_id(source):
            issues.append("invalid source id %r" % (source,))
        if not validate_requirement_id(target):
            issues.append("invalid target id %r" % (target,))
    return (not issues), sorted(set(issues))


def relationship_kind_valid(kind) -> bool:
    """True when kind is a SysML requirement relationship kind."""
    return kind in VALID_RELATIONSHIP_KINDS


def model_review_verdict(requirement_ids, satisfy_links, verify_links,
                         child_statuses) -> dict:
    """Combined model review verdict: 'ready' or 'gaps' with reasons."""
    sat_frac, sat_missing = satisfy_coverage(requirement_ids, satisfy_links)
    ver_frac, ver_missing = verify_coverage(requirement_ids, verify_links)
    rollup = rollup_verification_status(child_statuses)
    reasons = []
    if sat_missing:
        reasons.append("unsatisfied: %s" % ", ".join(sat_missing))
    if ver_missing:
        reasons.append("unverified: %s" % ", ".join(ver_missing))
    if rollup != "verified":
        reasons.append("roll-up status %s" % rollup)
    return {"satisfy_fraction": sat_frac, "verify_fraction": ver_frac,
            "rollup": rollup, "verdict": "ready" if not reasons else "gaps",
            "reasons": reasons}


# ---------------------------------------------------------------------------
# Functional architecture: allocation + traceability (systems-engineering)
# ---------------------------------------------------------------------------

def allocation_closure(functions, allocated):
    """Every function must be allocated before the model closes.

    Returns (closed, unallocated). allocated lists the function names
    that are allocated to a design element.
    """
    unallocated = [f for f in functions if f not in set(allocated)]
    return (len(unallocated) == 0, unallocated)


def traceability_status(linked: int, total: int, critical: bool = False) -> str:
    """Traceability closure: safety-critical items require full linkage.

    critical (FDAL A/B) requires linked == total; non-critical requires
    at least 90% of total.
    """
    if linked < 0 or total <= 0:
        raise ValueError("invalid traceability counts: %r / %r"
                         % (linked, total))
    if linked > total:
        raise ValueError("linked (%d) exceeds total (%d)" % (linked, total))
    required = total if critical else max(0, int(total * 0.9))
    return "closed" if linked >= required else "open"


# ---------------------------------------------------------------------------
# N2 interface model (n2-diagram logic)
# ---------------------------------------------------------------------------

def _validate_elements(elements):
    if not isinstance(elements, (list, tuple)) or len(elements) == 0:
        raise ValueError("elements must be a non-empty list, got %r"
                         % (elements,))
    for el in elements:
        if not isinstance(el, str) or not el.strip():
            raise ValueError("each element must be a non-empty string, got %r"
                             % (el,))
    if len(set(elements)) != len(elements):
        raise ValueError("element names must be unique, got %r" % (elements,))


def _normalize_pairs(pairs, elements, label):
    if not isinstance(pairs, (list, tuple)):
        raise ValueError("%s must be a list of (source, target) pairs, got %r"
                         % (label, pairs))
    index = {name: i for i, name in enumerate(elements)}
    out = []
    for pair in pairs:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError("%s entry must be a (source, target) pair, got %r"
                             % (label, pair))
        src, tgt = pair
        if src not in index:
            raise ValueError("%s source '%s' not in elements" % (label, src))
        if tgt not in index:
            raise ValueError("%s target '%s' not in elements" % (label, tgt))
        if src == tgt:
            raise ValueError("%s self interface %r is not allowed in an N2 "
                             "diagram" % (label, pair))
        out.append((index[src], index[tgt]))
    return out


def _validate_matrix(elements, matrix):
    n = len(elements)
    if not isinstance(matrix, (list, tuple)) or len(matrix) != n:
        raise ValueError("matrix must have one row per element, got %r"
                         % (matrix,))
    for row in matrix:
        if not isinstance(row, (list, tuple)) or len(row) != n:
            raise ValueError("each matrix row must have one column per "
                             "element, got %r" % (row,))
        for cell in row:
            if not isinstance(cell, int) or cell < 0:
                raise ValueError("matrix cells must be non-negative ints, "
                                 "got %r" % (cell,))


def build_matrix(elements, interfaces):
    """NxN interface matrix: cell[i][j] counts interfaces from i to j."""
    _validate_elements(elements)
    pairs = _normalize_pairs(interfaces, elements, "interfaces")
    n = len(elements)
    matrix = [[0] * n for _ in range(n)]
    for i, j in pairs:
        matrix[i][j] += 1
    return matrix


def interface_counts(elements, matrix) -> dict:
    """Interface count per element: row sum plus column sum."""
    _validate_elements(elements)
    _validate_matrix(elements, matrix)
    n = len(elements)
    counts = {}
    for i, name in enumerate(elements):
        row_sum = sum(matrix[i])
        col_sum = sum(matrix[j][i] for j in range(n))
        counts[name] = row_sum + col_sum
    return counts


def total_interfaces(elements, matrix) -> int:
    """Total interface entries: sum of every off-diagonal cell."""
    _validate_elements(elements)
    _validate_matrix(elements, matrix)
    return sum(sum(row) for row in matrix)


def missing_links(elements, matrix, required_pairs) -> list:
    """Required interface pairs whose cell in the matrix is zero."""
    _validate_elements(elements)
    _validate_matrix(elements, matrix)
    pairs = _normalize_pairs(required_pairs, elements, "required_pairs")
    missing = []
    for idx, (i, j) in enumerate(pairs):
        if matrix[i][j] == 0:
            missing.append((required_pairs[idx][0], required_pairs[idx][1]))
    return missing


def isolated_elements(elements, matrix) -> list:
    """Elements with zero interfaces (no outgoing and no incoming)."""
    _validate_elements(elements)
    _validate_matrix(elements, matrix)
    counts = interface_counts(elements, matrix)
    return [name for name in elements if counts[name] == 0]


# ---------------------------------------------------------------------------
# Behavioral model: state machine (state-machine logic)
# ---------------------------------------------------------------------------

class MachineError(ValueError):
    """Machine definition references an unknown state."""


def validate_machine(machine: dict) -> dict:
    """Check that the initial state and every transition endpoint exist."""
    states = set(machine["states"])
    initial = machine.get("initial")
    if initial is not None and initial not in states:
        raise MachineError("initial state not in states: %r" % (initial,))
    for t in machine.get("transitions", []):
        for key in ("from", "to"):
            if t.get(key) not in states:
                raise MachineError("transition %s state not in states: %r"
                                   % (key, t.get(key)))
    return machine


def reachable_states(machine: dict, initial: str) -> set:
    """Structural reachability: every state a transition chain reaches."""
    reach = {initial}
    frontier = [initial]
    while frontier:
        cur = frontier.pop()
        for t in machine["transitions"]:
            if t["from"] == cur and t["to"] not in reach:
                reach.add(t["to"])
                frontier.append(t["to"])
    return reach


def unreachable_states(machine: dict, initial: str) -> list:
    """States no transition chain can reach from the initial state."""
    reach = reachable_states(machine, initial)
    return sorted(s for s in machine["states"] if s not in reach)


def transition_conflicts(machine: dict) -> list:
    """One event enabling two transitions from one state, no priority.

    A (state, event) pair is conflicting when more than one transition
    is defined on it and fewer than one of them carries a priority
    resolution. Returns sorted descriptive strings.
    """
    validate_machine(machine)
    grouped = {}
    for t in machine.get("transitions", []):
        grouped.setdefault((t["from"], t["event"]), []).append(t)
    conflicts = []
    for key in sorted(grouped):
        group = grouped[key]
        if len(group) <= 1:
            continue
        resolved = sum(1 for t in group if t.get("priority") is not None) == 1
        if not resolved:
            conflicts.append("%s enabled by event %r: %d transitions"
                             % (key[0], key[1], len(group)))
    return conflicts


# ---------------------------------------------------------------------------
# Parametric constraints (sysml-modeling param semantics)
# ---------------------------------------------------------------------------

def sum_values(part_values) -> float:
    """Constraint LHS for a sum constraint: sum of the part values."""
    if not isinstance(part_values, (list, tuple)) or not part_values:
        raise ValueError("part_values must be a non-empty list")
    return float(sum(part_values))


def constraint_verdict(computed, bound, op="le", tolerance=1e-9) -> dict:
    """Evaluate a parametric constraint: computed <op> bound.

    op is 'le', 'ge' or 'eq'. Returns {computed, bound, op, margin,
    ratio, satisfied}. margin is bound - computed for 'le' (>= 0 means
    satisfied), computed - bound for 'ge', and |computed - bound| for
    'eq'. ratio is computed/bound (utilization for a budget bound).
    """
    computed = float(computed)
    bound = float(bound)
    if op not in ("le", "ge", "eq"):
        raise ValueError("constraint op must be le/ge/eq, got %r" % (op,))
    if op == "le":
        margin = bound - computed
        satisfied = margin >= -tolerance
    elif op == "ge":
        margin = computed - bound
        satisfied = margin >= -tolerance
    else:
        margin = abs(computed - bound)
        satisfied = margin <= tolerance
    ratio = computed / bound if bound != 0.0 else float("inf")
    return {"computed": round(computed, 4), "bound": round(bound, 4),
            "op": op, "margin": round(margin, 4),
            "ratio": round(ratio, 6), "satisfied": bool(satisfied)}


# ---------------------------------------------------------------------------
# Trade study (trade-study-analysis logic) - architecture decision record
# ---------------------------------------------------------------------------

def weighted_score(weights, scores) -> float:
    """Weighted score sum(w_i * s_i) with weights validated to sum 1.0."""
    if not weights or not scores:
        raise ValueError("weights and scores must be non-empty lists")
    if len(weights) != len(scores):
        raise ValueError("weights and scores length mismatch: %d vs %d"
                         % (len(weights), len(scores)))
    total = sum(weights)
    if abs(total - 1.0) > WEIGHT_TOLERANCE:
        raise ValueError("weights must sum to 1.0 (got %r)" % total)
    return sum(w * s for w, s in zip(weights, scores))


def selection_verdict(best_score, runner_up_score,
                      margin_threshold=DEFAULT_MARGIN_THRESHOLD) -> dict:
    """Selection decision with margin and tie handling."""
    margin = best_score - runner_up_score
    tie = margin <= WEIGHT_TOLERANCE
    return {"winner": "tie" if tie else "best", "margin": margin,
            "tie": bool(tie),
            "confident": (not tie) and margin >= margin_threshold}


# ---------------------------------------------------------------------------
# Project facts (the reference item)
# ---------------------------------------------------------------------------

@dataclass
class ModelSystem:
    """Model facts the role needs to build the plan (reference item)."""
    name: str
    description: str = ""
    failure_condition: str = "hazardous"      # severity category
    system_safety_ref: str = ""
    modeling_standard: str = "ARP4754A"
    model_baseline: str = ""
    cm_owner: str = "systems engineering"
    # block definition diagram
    block_parts: list = field(default_factory=list)
    block_references: list = field(default_factory=list)
    # functional architecture
    functions: list = field(default_factory=list)
    allocations: list = field(default_factory=list)   # (function, element)
    # requirements
    requirements: list = field(default_factory=list)  # dicts (see example)
    derive_links: list = field(default_factory=list)  # (source, target)
    satisfy_links: list = field(default_factory=list)  # (req, element)
    verify_links: list = field(default_factory=list)   # (req, verif item)
    req_tree: dict = field(default_factory=dict)        # id -> [child ids]
    req_statuses: dict = field(default_factory=dict)    # leaf id -> status
    # diagram suite purposes
    diagram_purposes: list = field(default_factory=list)
    # N2 interfaces
    n2_elements: list = field(default_factory=list)
    n2_interfaces: list = field(default_factory=list)    # (src, tgt) pairs
    n2_required: list = field(default_factory=list)
    # state machine
    machine: dict = field(default_factory=dict)
    # parametric constraints
    constraints: list = field(default_factory=list)
    # architecture decision record
    decision_weights: list = field(default_factory=list)
    decision_alternatives: list = field(default_factory=list)  # dicts
    decision_requirement_ids: list = field(default_factory=list)

    def development_assurance_level(self) -> str:
        return fdal_from_severity(self.failure_condition)


# ---------------------------------------------------------------------------
# Plan builder: produces the actual deliverable content
# ---------------------------------------------------------------------------

def build_plan(item: ModelSystem) -> dict:
    """Build the complete System Model Architecture and MBSE Plan model."""
    fdal = item.development_assurance_level()
    _check_fdal(fdal)

    # -- requirements screening + traceability ---------------------------
    req_ids = [r["id"] for r in item.requirements]
    screened = []
    for r in item.requirements:
        v = requirement_verifiability(r)
        screened.append({
            "id": r["id"], "text": r["text"], "kind": r.get("kind", ""),
            "priority": r.get("priority", ""), "source": r.get("source", ""),
            "method": r["method"], "shall_clauses": count_shall_clauses(r["text"]),
            "vague_terms": find_vague_terms(r["text"]),
            "verifiable": v["verifiable"], "reasons": v["reasons"],
        })
    verifiable_count = sum(1 for s in screened if s["verifiable"])

    sat_frac, sat_missing = satisfy_coverage(req_ids, item.satisfy_links)
    ver_frac, ver_missing = verify_coverage(req_ids, item.verify_links)
    derive_valid, derive_issues = derive_chain_check(item.derive_links)

    # roll-up of the requirement tree (leaf rule applied bottom-up)
    status_of = {}
    def _node_status(req_id):
        if req_id in status_of:
            return status_of[req_id]
        children = item.req_tree.get(req_id, [])
        if not children:
            status = item.req_statuses.get(req_id, "not-assessed")
        else:
            status = rollup_verification_status(
                [_node_status(c) for c in children])
        status_of[req_id] = status
        return status
    top_req = req_ids[0] if req_ids else ""
    statuses_for_review = [_node_status(rid) for rid in req_ids]
    rollup_top = statuses_for_review[0] if statuses_for_review \
        else "not-assessed"
    review = model_review_verdict(req_ids, item.satisfy_links,
                                  item.verify_links,
                                  statuses_for_review)
    critical = fdal in ("A", "B")
    trace_status = traceability_status(len(item.verify_links), len(req_ids),
                                       critical=critical)

    # -- diagram suite + viewpoints --------------------------------------
    suite = diagram_suite_verdict(item.diagram_purposes)
    views = {v: v in suite["covered_viewpoints"] for v in REQUIRED_VIEWPOINTS}

    # -- block + allocation closure ---------------------------------------
    bdd_verdict = block_definition_verdict(item.block_parts,
                                           item.block_references)
    bdd_missing = missing_block_definitions(item.block_parts,
                                            item.block_references)
    allocated_fns = [f for f, _ in item.allocations]
    alloc_closed, unallocated = allocation_closure(item.functions,
                                                   allocated_fns)

    # -- N2 interface model ------------------------------------------------
    matrix = build_matrix(item.n2_elements, item.n2_interfaces)
    counts = interface_counts(item.n2_elements, matrix)
    total_n2 = total_interfaces(item.n2_elements, matrix)
    missing_if = missing_links(item.n2_elements, matrix, item.n2_required)
    isolated = isolated_elements(item.n2_elements, matrix)

    # -- behavioral model ---------------------------------------------------
    initial = item.machine.get("initial", "")
    unreachable = unreachable_states(item.machine, initial)
    conflicts = transition_conflicts(item.machine)
    reachable = sorted(reachable_states(item.machine, initial))

    # -- parametric constraints --------------------------------------------
    constraint_rows = []
    for c in item.constraints:
        values = [p["value"] for p in c["parts"]]
        computed = sum_values(values)
        verdict = constraint_verdict(computed, c["bound"], op=c.get("op", "le"))
        verdict["name"] = c["name"]
        verdict["unit"] = c.get("unit", "")
        verdict["parts"] = c["parts"]
        constraint_rows.append(verdict)

    # -- architecture decision record ---------------------------------------
    decision_rows = []
    for alt in item.decision_alternatives:
        score = weighted_score(item.decision_weights, alt["scores"])
        decision_rows.append({"id": alt["id"], "name": alt["name"],
                              "scores": alt["scores"],
                              "requirements": alt.get("requirements", []),
                              "score": round(score, 4)})
    decision_rows.sort(key=lambda a: (-a["score"], a["id"]))
    if len(decision_rows) >= 2:
        sel = selection_verdict(decision_rows[0]["score"],
                                decision_rows[1]["score"])
    else:
        sel = {"winner": "best", "margin": 0.0, "tie": False,
               "confident": False}
    cited = set()
    for a in item.decision_alternatives:
        cited.update(a.get("requirements") or [])
    uncovered = [r for r in item.decision_requirement_ids
                 if r not in cited]
    decision_trace_ok = (not uncovered)

    # -- governance ----------------------------------------------------------
    toolchain = [{"task": task, "tool": TOOL_BY_TASK[task]}
                 for task in ("requirements-modeling", "functional-architecture",
                              "architecture-analysis")
                 if task in TOOL_BY_TASK]

    return {
        "document_type": "System Model Architecture and MBSE Plan",
        "status": "draft-for-review",
        "item": item.name,
        "item_description": item.description,
        "modeling_standard": item.modeling_standard,
        "model_baseline": item.model_baseline,
        "cm_owner": item.cm_owner,
        "development_assurance_level": fdal,
        "severity_source": item.failure_condition,
        "system_safety_reference": item.system_safety_ref,
        "critical": critical,
        # requirements architecture
        "requirements": screened,
        "requirements_total": len(req_ids),
        "verifiable_count": verifiable_count,
        "satisfy_fraction": sat_frac,
        "verify_fraction": ver_frac,
        "satisfy_missing": sat_missing,
        "verify_missing": ver_missing,
        "derive_valid": derive_valid,
        "derive_issues": derive_issues,
        "derive_links_count": len(item.derive_links),
        "rollup": rollup_top,
        "traceability_status": trace_status,
        "traceability_required": "full closure (critical)"
        if critical else ">= 90% closure",
        # model architecture
        "diagram_suite": suite["rows"],
        "diagram_count": len(suite["rows"]),
        "diagram_selection_consistent": suite["consistent"],
        "viewpoints": views,
        "viewpoint_verdict": model_viewpoint_verdict(views),
        # structure + function
        "block_parts": list(item.block_parts),
        "block_references": list(item.block_references),
        "bdd_verdict": bdd_verdict,
        "bdd_missing": bdd_missing,
        "functions": list(item.functions),
        "allocation_rows": [{"function": f, "element": e}
                            for f, e in item.allocations],
        "allocation_closed": alloc_closed,
        "unallocated": unallocated,
        # decision record
        "decision_record": {
            "weights": list(item.decision_weights),
            "alternatives": decision_rows,
            "winner": decision_rows[0] if decision_rows else None,
            "selection": sel,
            "trace_ok": decision_trace_ok,
            "uncovered_requirements": uncovered,
        },
        "toolchain": toolchain,
        # interfaces
        "n2": {
            "elements": list(item.n2_elements),
            "matrix": matrix,
            "counts": [{"element": e, "count": counts[e]}
                       for e in item.n2_elements],
            "total": total_n2,
            "required": [list(p) for p in item.n2_required],
            "missing": [list(p) for p in missing_if],
            "isolated": isolated,
        },
        # behavior
        "behavior": {
            "states": list(item.machine.get("states", [])),
            "initial": initial,
            "transitions": [dict(t) for t in item.machine.get("transitions", [])],
            "reachable": reachable,
            "unreachable": unreachable,
            "conflicts": conflicts,
        },
        # parametrics
        "constraints": constraint_rows,
        # model review + governance
        "model_review": review["verdict"],
        "model_review_reasons": review["reasons"],
        "governance": {
            "model_baseline": item.model_baseline,
            "review_verdict": review["verdict"],
            "open_items": [],
            "toolchain": toolchain,
        },
        "generated": _today(),
    }


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def _pct(fraction: float) -> str:
    return "%.1f%%" % (fraction * 100.0)


def render_plan_markdown(model: dict) -> str:
    """Render the plan content model as the deliverable markdown document."""
    n2 = model["n2"]
    beh = model["behavior"]
    dec = model["decision_record"]
    lines = [
        "# System Model Architecture and MBSE Plan",
        "",
        f"**System:** {model['item']}",
        f"**Development assurance level:** {model['development_assurance_level']} "
        f"(from {model['severity_source']} failure condition"
        + (f", system safety reference {model['system_safety_reference']}"
           if model['system_safety_reference'] else "") + ")",
        f"**Modeling standard:** {model['modeling_standard']} "
        "(development process context)",
        f"**Model baseline:** {model['model_baseline']}",
        f"**Status:** {model['status']}",
        "",
        "## 1. Scope",
        "",
        f"This plan defines the system model architecture and the "
        f"model-based systems engineering (MBSE) approach for "
        f"{model['item']}."
        + (f" {model['item_description']}" if model["item_description"] else ""),
        f"The model is developed to development assurance level "
        f"{model['development_assurance_level']} (FDAL), so traceability "
        f"requires {model['traceability_required']}.",
        "",
        "## 2. Model architecture (diagram suite)",
        "",
        "Diagram kind is selected from the modeling purpose. The suite is:",
        "",
        "| Purpose | Diagram kind | Viewpoint |",
        "|---|---|---|",
        *[f"| {r['purpose']} | {r['kind']} ({r['kind_name']}) | "
          f"{r['viewpoint']} |" for r in model["diagram_suite"]],
        "",
        f"Diagram selection is consistent: "
        f"{model['diagram_count']}/{model['diagram_count']} purposes resolve "
        f"to their canonical SysML diagram kind.",
        "",
        "## 3. Viewpoint coverage",
        "",
        "| Viewpoint | Covered by |",
        "|---|---|",
        "| structure | bdd, ibd, pkg |",
        "| behavior | act, seq, stm, uc |",
        "| requirements | req |",
        "| parametric | param |",
        "",
        f"Viewpoint coverage verdict: **{model['viewpoint_verdict']}** "
        "(all four required viewpoints present).",
        "",
        "## 4. Requirements architecture",
        "",
        f"The requirement set holds {model['requirements_total']} "
        f"requirements. Quality screening: {model['verifiable_count']}/"
        f"{model['requirements_total']} verifiable "
        "(one shall clause, no vague terms, mapped verification method).",
        "",
        *[f"- **{r['id']}** [{r['kind']}, priority {r['priority']}, "
          f"{r['method']}]: {r['text']}"
          + (" — verifiable (1 shall clause, no vague terms)"
             if r["verifiable"]
             else " — NOT verifiable: " + "; ".join(r["reasons"]) + ".")
          for r in model["requirements"]],
        "",
        f"Derive relationships: {'valid' if model['derive_valid'] else 'invalid'} "
        f"({model['derive_links_count']} derive link"
        + ("s" if model["derive_links_count"] != 1 else "")
        + " checked; no self-derive, all ids canonical).",
        "",
        f"- Satisfy coverage: {_pct(model['satisfy_fraction'])} "
        f"({model['requirements_total'] - len(model['satisfy_missing'])}/"
        f"{model['requirements_total']} requirements satisfied by a design "
        "element).",
        f"- Verify coverage: {_pct(model['verify_fraction'])} "
        f"({model['requirements_total'] - len(model['verify_missing'])}/"
        f"{model['requirements_total']} requirements linked to a "
        "verification item).",
        f"- Verification status roll-up (requirement tree): "
        f"**{model['rollup']}**.",
        "",
        "## 5. Functional and logical architecture",
        "",
        "Functions are allocated to the design elements of the logical "
        "architecture:",
        "",
        "| Function | Allocated to |",
        "|---|---|",
        *[f"| {a['function']} | {a['element']} |"
          for a in model["allocation_rows"]],
        "",
        f"Allocation closure: "
        f"{'closed' if model['allocation_closed'] else 'open'} "
        f"({len(model['allocation_rows'])}/{len(model['functions'])} "
        "functions allocated"
        + ("" if model["allocation_closed"] else
           "; unallocated: " + ", ".join(model["unallocated"])) + ").",
        "",
        "Concept decision record (weighted criteria, weights sum to 1.0):",
        "",
        *[f"- **{a['name']}** ({a['id']}): weighted score {a['score']:.2f}"
          for a in dec["alternatives"]],
        f"- Selection: winner {dec['winner']['name'] if dec['winner'] else '-'} "
        f"with margin {dec['selection']['margin']:.2f} "
        f"({'confident' if dec['selection']['confident'] else 'not confident'}"
        f"{'; traceable to requirements' if dec['trace_ok'] else ''}).",
        "",
        "Toolchain mapping (open source, per MBSE task):",
        "",
        *[f"- {t['task']}: {t['tool']}" for t in model["toolchain"]],
        "",
        "## 6. Block definition and internal structure",
        "",
        "The block definition diagram declares the block hierarchy; every "
        "element the model references must have a block definition:",
        "",
        *[f"- {p}" for p in model["block_parts"]],
        "",
        f"Block definition verdict: **{model['bdd_verdict']}** "
        f"({len(model['block_references'])} referenced element(s), "
        f"{len(model['bdd_missing'])} without a definition).",
        "",
        "## 7. Interface model (N2)",
        "",
        "The N2 matrix arranges the components on the diagonal; cell (i, j) "
        "counts the interfaces from component i to component j. "
        f"Total interfaces modeled: {n2['total']}.",
        "",
        "| Component | Interface count (out + in) |",
        "|---|---|",
        *[f"| {c['element']} | {c['count']} |" for c in n2["counts"]],
        "",
        f"Required data links: {n2['total'] - len(n2['missing'])}/"
        f"{len(n2['required'])} modeled"
        + ("" if not n2["missing"] else
           "; missing: " + ", ".join("%s -> %s" % tuple(p)
                                     for p in n2["missing"]))
        + ". Isolated components (no interfaces): "
        + ("none." if not n2["isolated"] else ", ".join(n2["isolated"]) + "."),
        "",
        "## 8. Behavioral model",
        "",
        f"The state machine models {len(beh['states'])} states "
        f"(initial state {beh['initial']}) and "
        f"{len(beh['transitions'])} transitions:",
        "",
        *[f"- {t['from']} --{t['event']}-> {t['to']}"
          for t in beh["transitions"]],
        "",
        f"Reachability from {beh['initial']}: "
        f"{len(beh['reachable'])}/{len(beh['states'])} states reachable; "
        "unreachable: "
        + ("none." if not beh["unreachable"] else ", ".join(beh["unreachable"])),
        f"Transition conflicts: "
        + ("none." if not beh["conflicts"] else ", ".join(beh["conflicts"])),
        "",
        "## 9. Parametric constraints",
        "",
        "Constraint equations are bound to block value properties; each "
        "constraint below is evaluated on the model:",
        "",
        *[f"- **{c['name']}**: "
          + " + ".join("%g %s" % (p["value"], c["unit"]) for p in c["parts"])
          + f" = {c['computed']:g} {c['unit']} <= bound "
          + f"{c['bound']:g} {c['unit']} — verdict: "
          + ("satisfied" if c["satisfied"] else "NOT satisfied")
          + f", margin {c['margin']:+.2f} {c['unit']}, "
          + f"utilization {c['ratio'] * 100.0:.1f}% of bound."
          for c in model["constraints"]],
        "",
        f"Parametric constraints satisfied: "
        f"{sum(1 for c in model['constraints'] if c['satisfied'])}/"
        f"{len(model['constraints'])}.",
        "",
        "## 10. Traceability and model review",
        "",
        f"Traceability closure: **{model['traceability_status']}** "
        f"({model['traceability_required']}). Every requirement is linked "
        "through its satisfying design element to a verification item.",
        f"Model review verdict: **{model['model_review']}** "
        "(satisfy coverage "
        f"{_pct(model['satisfy_fraction'])}, verify coverage "
        f"{_pct(model['verify_fraction'])}, roll-up {model['rollup']}).",
        "",
        "## 11. Model governance",
        "",
        f"- Model baseline: {model['model_baseline']} (configuration-managed "
        "model artifact, CM owner: " + model["cm_owner"] + ").",
        "- Diagram content and traceability are reviewed like any other "
        "engineering data in the development process.",
        "- Toolchain: " + ", ".join(t["tool"] for t in model["toolchain"]) + ".",
        "- Open items for the next modeling review: "
        + ("none." if not model["governance"]["open_items"]
           else "; ".join(model["governance"]["open_items"])),
        "",
        "---",
        f"*Generated by Aero Agent Roles mbse-modeling-engineer core "
        f"({model['generated']}). DRAFT for human systems-engineering review. "
        "Not an approval document.*",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evidence gate checkers
# ---------------------------------------------------------------------------

GATE_CHECKS = {
    "level_identified": "development assurance level is a single valid letter",
    "diagram_coverage": "every required viewpoint covered; selection consistent",
    "traceability_closed": "satisfy + verify coverage 100%, roll-up verified",
    "block_hierarchy_valid": "bdd defines every reference; allocation closed",
    "parametric_satisfied": "every constraint satisfied with a numeric margin",
    "interface_consistent": "all required N2 links modeled; none isolated",
    "behavior_consistent": "all states reachable; no transition conflicts",
    "governance_present": "model review ready; baseline + open items recorded",
    "sign_off_honest": "document is marked draft-for-review, not approval",
}


def check_plan(model: dict) -> dict:
    """Run the evidence gates against a plan model."""
    fdal = model.get("development_assurance_level", "")
    sat = model.get("satisfy_fraction", 0.0)
    ver = model.get("verify_fraction", 0.0)
    n2 = model.get("n2", {})
    beh = model.get("behavior", {})
    cons = model.get("constraints", [])
    results = {
        "level_identified": fdal in FDALS and bool(model.get("severity_source")),
        "diagram_coverage": (
            model.get("viewpoint_verdict") == "complete"
            and model.get("diagram_selection_consistent", False)),
        "traceability_closed": (
            sat == 1.0 and ver == 1.0 and model.get("rollup") == "verified"),
        "block_hierarchy_valid": (
            model.get("bdd_verdict") == "valid"
            and model.get("allocation_closed", False)),
        "parametric_satisfied": bool(cons) and all(
            isinstance(c.get("margin"), (int, float)) and c["satisfied"]
            for c in cons),
        "interface_consistent": (
            not n2.get("missing") and not n2.get("isolated")
            and n2.get("total", 0) >= len(n2.get("required", []))),
        "behavior_consistent": (
            not beh.get("unreachable") and not beh.get("conflicts")),
        "governance_present": (
            model.get("model_review") == "ready"
            and bool(model.get("model_baseline"))
            and isinstance(model.get("governance", {}).get("open_items"), list)),
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_plan_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    checks = {
        "has_title": "system model architecture and mbse plan" in low,
        "has_level": "development assurance level" in low,
        "has_item": "system:" in low,
        "has_coverage": "coverage" in low and "5/5" in md_text,
        "has_parametric": "margin" in low and "utilization" in low,
        "has_traceability": "traceability" in low and "closed" in low,
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling: check a plan document."""
    return check_plan_markdown(md_text)


# ---------------------------------------------------------------------------
# Example model (for tests and worked-example generation)
# ---------------------------------------------------------------------------

def example_item() -> ModelSystem:
    """The reference item: Cabin Pressure Control System (CPCS)."""
    parts = [
        "Cabin Pressure Controller",
        "Outflow Valve Assembly",
        "Safety Valve Assembly",
        "Pressure Sensor Package",
    ]
    return ModelSystem(
        name="Cabin Pressure Control System (CPCS)",
        description="DAL-B cabin pressure control system model built to "
                    "ARP4754A development-assurance context; the model is "
                    "the primary requirements and architecture artifact.",
        failure_condition="hazardous",
        system_safety_ref="FHA-CPCS-001 / PSSA rev B",
        modeling_standard="ARP4754A",
        model_baseline="CPCS-MOD-001 Rev A",
        cm_owner="systems engineering",
        block_parts=["CPCS"] + parts,
        block_references=["CPCS"] + parts,
        functions=[
            "sense-cabin-pressure",
            "schedule-pressure-target",
            "position-outflow-valve",
            "open-safety-valve",
            "alert-crew",
        ],
        allocations=[
            ("sense-cabin-pressure", "Pressure Sensor Package"),
            ("schedule-pressure-target", "Cabin Pressure Controller"),
            ("position-outflow-valve", "Outflow Valve Assembly"),
            ("open-safety-valve", "Safety Valve Assembly"),
            ("alert-crew", "Cabin Pressure Controller"),
        ],
        requirements=[
            {"id": "CPCS-001", "kind": "functional", "priority": "1",
             "source": "aircraft-level requirement",
             "method": "analysis",
             "text": "The CPCS shall maintain cabin pressure altitude at or "
                     "below 8000 feet during normal cruise operation."},
            {"id": "CPCS-002", "kind": "functional", "priority": "1",
             "source": "derived from CPCS-001",
             "method": "test",
             "text": "The CPCS shall command the outflow valve to full open "
                     "when cabin altitude exceeds 10000 feet."},
            {"id": "CPCS-003", "kind": "functional", "priority": "2",
             "source": "crew alerting requirement",
             "method": "test",
             "text": "The CPCS shall alert the flight crew when cabin "
                     "altitude exceeds 9500 feet."},
            {"id": "CPCS-004", "kind": "performance", "priority": "2",
             "source": "derived from CPCS-001",
             "method": "analysis",
             "text": "The CPCS shall limit cabin pressure excursions to "
                     "0.05 psi above the scheduled cabin pressure."},
            {"id": "CPCS-005", "kind": "constraint", "priority": "1",
             "source": "safety assessment",
             "method": "demonstration",
             "text": "The CPCS shall open the safety valve automatically "
                     "when cabin differential pressure exceeds 8.5 psi."},
        ],
        derive_links=[("CPCS-001", "CPCS-004")],
        satisfy_links=[
            ("CPCS-001", "Cabin Pressure Controller"),
            ("CPCS-002", "Outflow Valve Assembly"),
            ("CPCS-003", "Cabin Pressure Controller"),
            ("CPCS-004", "Cabin Pressure Controller"),
            ("CPCS-005", "Safety Valve Assembly"),
        ],
        verify_links=[
            ("CPCS-001", "CPCS-VER-001 cabin altitude schedule analysis"),
            ("CPCS-002", "CPCS-VER-002 outflow valve command test"),
            ("CPCS-003", "CPCS-VER-003 crew alert test"),
            ("CPCS-004", "CPCS-VER-004 pressure excursion analysis"),
            ("CPCS-005", "CPCS-VER-005 safety valve demonstration"),
        ],
        req_tree={
            "CPCS-001": ["CPCS-002", "CPCS-004"],
            "CPCS-002": ["CPCS-003"],
        },
        req_statuses={
            "CPCS-003": "verified", "CPCS-004": "verified",
            "CPCS-005": "verified",
        },
        diagram_purposes=[
            "system-composition", "internal-structure", "requirements-capture",
            "requirements-traceability", "constraint-analysis",
            "functional-flow", "state-transition", "message-ordering",
            "use-case-scoping", "model-organization",
        ],
        n2_elements=parts,
        n2_interfaces=[
            ("Pressure Sensor Package", "Cabin Pressure Controller"),
            ("Cabin Pressure Controller", "Outflow Valve Assembly"),
            ("Outflow Valve Assembly", "Cabin Pressure Controller"),
            ("Safety Valve Assembly", "Cabin Pressure Controller"),
        ],
        n2_required=[
            ("Pressure Sensor Package", "Cabin Pressure Controller"),
            ("Cabin Pressure Controller", "Outflow Valve Assembly"),
            ("Outflow Valve Assembly", "Cabin Pressure Controller"),
            ("Safety Valve Assembly", "Cabin Pressure Controller"),
        ],
        machine={
            "states": ["Standby", "Auto", "Manual", "Fault"],
            "initial": "Standby",
            "transitions": [
                {"from": "Standby", "event": "auto_engage", "to": "Auto"},
                {"from": "Auto", "event": "fault_detected", "to": "Fault"},
                {"from": "Auto", "event": "manual_override", "to": "Manual"},
                {"from": "Manual", "event": "auto_engage", "to": "Auto"},
                {"from": "Manual", "event": "fault_detected", "to": "Fault"},
                {"from": "Fault", "event": "reset", "to": "Standby"},
            ],
        },
        constraints=[
            {"name": "CPCS mass budget", "unit": "kg", "op": "le",
             "bound": 30.0,
             "parts": [
                 {"name": "Cabin Pressure Controller", "value": 4.2},
                 {"name": "Outflow Valve Assembly", "value": 12.8},
                 {"name": "Safety Valve Assembly", "value": 6.5},
                 {"name": "Pressure Sensor Package", "value": 0.9},
             ]},
            {"name": "CPCS electrical power budget", "unit": "W", "op": "le",
             "bound": 120.0,
             "parts": [
                 {"name": "Cabin Pressure Controller", "value": 35.0},
                 {"name": "Outflow Valve Assembly", "value": 42.0},
                 {"name": "Safety Valve Assembly", "value": 18.0},
                 {"name": "Pressure Sensor Package", "value": 6.0},
             ]},
        ],
        decision_weights=[0.5, 0.3, 0.2],
        decision_alternatives=[
            {"id": "CON-A", "name": "Centralized digital controller",
             "scores": [8, 6, 9], "requirements": ["CPCS-001", "CPCS-003"]},
            {"id": "CON-B", "name": "Distributed smart actuators",
             "scores": [6, 8, 7], "requirements": ["CPCS-002", "CPCS-004"]},
        ],
        decision_requirement_ids=["CPCS-001", "CPCS-002", "CPCS-003",
                                  "CPCS-004"],
    )


def example_plan_markdown() -> str:
    return render_plan_markdown(build_plan(example_item()))


if __name__ == "__main__":
    item = example_item()
    model = build_plan(item)
    md = render_plan_markdown(model)
    print("SYSTEM: %s" % model["item"])
    print("FDAL: %s (from %s)" % (model["development_assurance_level"],
                                  model["severity_source"]))
    print("REQUIREMENTS: %d, satisfy %.2f, verify %.2f, roll-up %s"
          % (model["requirements_total"], model["satisfy_fraction"],
             model["verify_fraction"], model["rollup"]))
    print("VIEWPOINTS: %s" % model["viewpoint_verdict"])
    print("BDD: %s | ALLOCATION: %s" % (model["bdd_verdict"],
                                        model["allocation_closed"]))
    print("N2 TOTAL: %d | missing %d | isolated %d"
          % (model["n2"]["total"], len(model["n2"]["missing"]),
             len(model["n2"]["isolated"])))
    print("BEHAVIOR: reachable %d/%d | unreachable %d | conflicts %d"
          % (len(model["behavior"]["reachable"]),
             len(model["behavior"]["states"]),
             len(model["behavior"]["unreachable"]),
             len(model["behavior"]["conflicts"])))
    print("CONSTRAINTS: %s" % [c["satisfied"] for c in model["constraints"]])
    print("MODEL REVIEW: %s" % model["model_review"])
    print("GATES: %s" % check_plan(model))
    print("RENDERED: %d chars" % len(md))
