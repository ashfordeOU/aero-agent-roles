#!/usr/bin/env python3
"""do254_hardware_core.py - DO-254 Airborne Electronic Hardware Engineer core.

This is the role's ENGINE: given an airborne electronic hardware item's
project facts it determines the hardware design assurance level (DAL A-E
from the function failure condition), classifies the item simple vs
complex AEH, computes verification expectations (methods, coverage
ratios, independence), configuration management depth, requirement
traceability health, and BUILDS the Plan for Hardware Aspects of
Certification (PHAC) content. It also gate-checks deliverables.
Standalone: no external repo needed.

Domain rules encoded here are public process knowledge as practiced in
the bound AeroSkills do254 leaves (hardware-planning, verification,
configuration-management, requirements-capture) and standard
certification practice summarized in FAA AC 20-152A. DO-254 text is
never reproduced - the PHAC structure is an original synthesis.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date

def _today() -> str:
    import os
    from datetime import date
    return os.environ.get("ROLE_GEN_DATE", date.today().isoformat())

# ---------------------------------------------------------------------------
# Domain tables (public process knowledge)
# ---------------------------------------------------------------------------

# Hardware design assurance level from failure-condition severity
# (FAR 25.1309 / CS-25.1309 severity categories -> DAL mapping used in
# DO-254 certification practice; identical severity-to-level logic as
# the software side).
SEVERITY_TO_DAL = {
    "catastrophic": "A",
    "hazardous": "B",
    "major": "C",
    "minor": "D",
    "no-safety-effect": "E",
}
DALS = ("A", "B", "C", "D", "E")

# DO-254 verification logic: requirements-based test coverage ratio by
# level: 0.98 at levels A/B, 0.95 at levels C/D (as encoded in the bound
# avionics/do254/verification leaf). Level E (no safety effect) is
# typically outside DO-254 scope: no coverage target.
COVERAGE_RATIO = {"A": 0.98, "B": 0.98, "C": 0.95, "D": 0.95, "E": None}

# Verification independence by DAL: independent verification expected at
# the higher hardware design assurance levels (A/B) per the bound
# avionics/do254/verification leaf.
INDEPENDENT = {"A": True, "B": True, "C": False, "D": False, "E": False}

# Life cycle data set by DAL: the hardware life cycle data items a PHAC
# must name. Levels with more rigor require the full set; E (no safety
# effect) is a documented exclusion. Original synthesis of the standard
# plan-of-attack categories, not reproduced text.
LIFE_CYCLE_DATA = {
    "A": [
        "plan for hardware aspects of certification (PHAC)",
        "hardware requirements standards",
        "hardware design standards",
        "hardware validation plan",
        "hardware verification plan",
        "hardware configuration management plan",
        "hardware process assurance plan",
        "hardware requirements data",
        "hardware design data",
        "hardware verification data and results",
        "hardware life cycle environment configuration index",
        "hardware configuration index (HCI)",
        "hardware process assurance records",
        "hardware accomplishment summary (HAS)",
    ],
    "B": [
        "plan for hardware aspects of certification (PHAC)",
        "hardware requirements standards",
        "hardware design standards",
        "hardware validation plan",
        "hardware verification plan",
        "hardware configuration management plan",
        "hardware process assurance plan",
        "hardware requirements data",
        "hardware design data",
        "hardware verification data and results",
        "hardware life cycle environment configuration index",
        "hardware configuration index (HCI)",
        "hardware process assurance records",
        "hardware accomplishment summary (HAS)",
    ],
    "C": [
        "plan for hardware aspects of certification (PHAC)",
        "hardware requirements standards",
        "hardware design standards",
        "hardware verification plan",
        "hardware configuration management plan",
        "hardware requirements data",
        "hardware design data",
        "hardware verification data and results",
        "hardware configuration index (HCI)",
        "hardware process assurance records",
    ],
    "D": [
        "plan for hardware aspects of certification (PHAC)",
        "hardware requirements data",
        "hardware design data",
        "hardware verification plan",
        "hardware verification data and results",
        "hardware configuration index (HCI)",
        "hardware process assurance records",
    ],
    "E": [
        "hardware requirements data",
        "hardware design data",
        "hardware verification data and results",
    ],
}

# Verification objectives by DAL: objective families expected per level
# (public practice: planning/verification/CM/process assurance scale with
# the level; A/B add independence and certification liaison).
VERIFICATION_FAMILIES = {
    "A": ["planning", "requirements", "design", "verification", "cm",
          "process-assurance", "cert-liaison"],
    "B": ["planning", "requirements", "design", "verification", "cm",
          "process-assurance", "cert-liaison"],
    "C": ["planning", "requirements", "design", "verification", "cm",
          "process-assurance"],
    "D": ["planning", "requirements", "design", "verification", "cm"],
    "E": [],
}

# Hardware change classes (DO-254 CM practice, bound
# configuration-management leaf): class 1 = formal ECR/ECO with baseline
# update + reverification + independent review; class 2 = documented
# lighter review.
CHANGE_CLASS_1_RATIONALE = ("form/fit/function change or safety effect "
                            "present or complex hardware")
CHANGE_CLASS_2_RATIONALE = ("no form/fit/function change, no safety effect, "
                            "simple hardware")


@dataclass
class HardwareItem:
    """Project facts the role needs to build the PHAC."""
    item_name: str
    description: str = ""
    failure_condition: str = "major"          # severity category
    system_safety_ref: str = ""               # FHA/PSSA reference
    # AEH classification inputs (bound hardware-planning leaf semantics):
    has_programmable_logic: bool = False
    has_internal_state: bool = False
    fully_verifiable_from_top_data: bool = True
    safety_significant: bool = False
    technology: str = ""                      # CPLD / FPGA / ASIC / ...
    life_cycle_model: str = "waterfall"
    hdl_languages: list = field(default_factory=lambda: ["VHDL"])
    target_device: str = ""
    development_tools: list = field(default_factory=list)
    verification_tools: list = field(default_factory=list)
    tool_qualification_approach: str = "criteria-based per DO-254"
    previously_developed: bool = False
    pds_origin_standard: str = ""
    certification_basis: str = "FAR/CS-25"
    requirements: list = field(default_factory=list)

    def assurance_level(self) -> str:
        return SEVERITY_TO_DAL.get(self.failure_condition.lower(), "E")

    def aeh_class(self) -> str:
        return classify_aeh(
            has_programmable_logic=self.has_programmable_logic,
            has_internal_state=self.has_internal_state,
            fully_verifiable_from_top_data=self.fully_verifiable_from_top_data,
            safety_significant=self.safety_significant)


# ---------------------------------------------------------------------------
# AEH classification (grounded in avionics/do254/hardware-planning leaf)
# ---------------------------------------------------------------------------

_COMPLEX_ARTIFACTS = ("phac", "requirements-capture", "conceptual-design",
                      "detailed-design", "verification", "configuration-management",
                      "process-assurance")
_SIMPLE_ARTIFACTS = ("hardware-plan", "verification", "configuration-management")


def classify_aeh(has_programmable_logic, has_internal_state,
                 fully_verifiable_from_top_data, safety_significant) -> str:
    """Return 'complex' or 'simple' for a DO-254 AEH item.

    Conservative planning default: when in doubt, treat the item as
    complex so the full design assurance process applies (programmable
    logic, internal state, or inability to verify behavior from top-level
    data alone, or safety-significant items).
    """
    if has_programmable_logic or has_internal_state:
        return "complex"
    if not fully_verifiable_from_top_data:
        return "complex"
    if safety_significant:
        return "complex"
    return "simple"


def planning_artifacts(classification: str) -> list:
    """Planning artifact set per AEH class; unknown class -> ValueError."""
    if classification == "complex":
        return list(_COMPLEX_ARTIFACTS)
    if classification == "simple":
        return list(_SIMPLE_ARTIFACTS)
    raise ValueError("unknown AEH classification: %r" % (classification,))


# ---------------------------------------------------------------------------
# Verification rules (grounded in avionics/do254/verification leaf)
# ---------------------------------------------------------------------------

def _check_dal(dal: str) -> None:
    if dal not in DALS:
        raise ValueError("invalid DAL %r" % (dal,))


def verification_methods_for(aeh_class: str, dal: str) -> set:
    """Verification methods for a DO-254 hardware item: complex AEH uses
    test, analysis, and review; simple AEH uses reduced verification
    (review). Unknown classes or levels outside A-D raise ValueError."""
    if aeh_class not in ("simple", "complex"):
        raise ValueError("unknown AEH class: %r" % (aeh_class,))
    if dal not in ("A", "B", "C", "D"):
        raise ValueError("invalid hardware design assurance level: %r" % (dal,))
    if aeh_class == "complex":
        return {"test", "analysis", "review"}
    return {"review"}


def independence_required(dal: str) -> bool:
    """Independent verification is expected at the higher hardware design
    assurance levels (A/B)."""
    _check_dal(dal)
    return INDEPENDENT[dal]


def coverage_ratio(dal: str) -> float | None:
    """Requirements-based test coverage ratio by level (None at E)."""
    _check_dal(dal)
    return COVERAGE_RATIO[dal]


def coverage_adequate(dal: str, measured_pct: float) -> bool:
    """True when measured requirements-based coverage meets the level ratio."""
    ratio = coverage_ratio(dal)
    if ratio is None:
        return True
    return measured_pct >= ratio


def verification_complete(methods_used, required_methods) -> bool:
    """True when every required verification method is present in the
    methods used (extra methods do not fail the check)."""
    return set(required_methods).issubset(set(methods_used))


def hwsw_integration_evidence(present: bool) -> bool:
    """Whether hardware/software integration evidence is available for the
    item (plain boolean pass-through)."""
    return bool(present)


def structural_methods_text(dal: str) -> str:
    """Plain-language verification expectation for the level."""
    cov = coverage_ratio(dal)
    indep = independence_required(dal)
    indep_txt = "independent" if indep else "may be conducted by the developer"
    if cov is None:
        return "No requirements-based coverage target (no safety effect)."
    return ("Requirements-based coverage ratio %.2f; verification %s."
            % (cov, indep_txt))


# ---------------------------------------------------------------------------
# Configuration management (grounded in avionics/do254/configuration-management)
# ---------------------------------------------------------------------------

VALID_HARDWARE_CLASSES = ("simple", "complex")
VALID_SAFETY_EFFECTS = ("none", "minor", "major", "hazardous", "catastrophic")


def hw_change_class(change: dict) -> dict:
    """Classify a DO-254 hardware change as class 1 or class 2.

    change: dict with keys hardware_class ('simple'/'complex'),
    safety_effect ('none'/'minor'/'major'/'hazardous'/'catastrophic'),
    functional_change (bool). Class 1 when form/fit/function changes,
    safety effect present, or hardware is complex.
    """
    if not isinstance(change, dict):
        raise ValueError("change must be a dict")
    hw = change.get("hardware_class")
    se = change.get("safety_effect")
    fc = change.get("functional_change")
    if hw not in VALID_HARDWARE_CLASSES:
        raise ValueError("hardware_class must be simple or complex, got %r" % hw)
    if se not in VALID_SAFETY_EFFECTS:
        raise ValueError("safety_effect must be one of %s, got %r"
                         % (", ".join(VALID_SAFETY_EFFECTS), se))
    if not isinstance(fc, bool):
        raise ValueError("functional_change must be a bool, got %r" % fc)
    if fc or se != "none" or hw == "complex":
        return {"class": 1, "rationale": CHANGE_CLASS_1_RATIONALE}
    return {"class": 2, "rationale": CHANGE_CLASS_2_RATIONALE}


def cm_actions(change_class_num: int) -> dict:
    """Map a change class to required configuration management actions."""
    if change_class_num == 1:
        return {"baseline_update": True, "ecr_required": True,
                "reverification_required": True, "independent_review": True}
    if change_class_num == 2:
        return {"baseline_update": True, "ecr_required": True,
                "reverification_required": False, "independent_review": False}
    raise ValueError("change class must be 1 or 2, got %r" % (change_class_num,))


def hci_entry(item: str, revision: str, baseline: str) -> str:
    """Format one hardware configuration index line: 'item rev baseline'."""
    if not isinstance(item, str) or not item.strip():
        raise ValueError("item must be a non-empty string")
    if not isinstance(revision, str) or not revision.strip():
        raise ValueError("revision must be a non-empty string")
    if not isinstance(baseline, str) or not baseline.strip():
        raise ValueError("baseline must be a non-empty string")
    return "%s %s %s" % (item.strip(), revision.strip(), baseline.strip())


# ---------------------------------------------------------------------------
# Requirements capture (grounded in avionics/do254/requirements-capture)
# ---------------------------------------------------------------------------

VAGUE_TERMS = ("suitable", "adequate", "approximately", "etc", "as required",
               "or better", "and so on", "reasonable")


def req_issues(requirement: dict) -> list:
    """List of issue flags for one requirement mapping.

    Recognized flags: missing-id, empty-text, vague, not-traceable."""
    if not isinstance(requirement, dict):
        raise ValueError("requirement must be a mapping")
    issues = []
    rid = requirement.get("id") or ""
    text = requirement.get("text") or ""
    if not str(rid).strip():
        issues.append("missing-id")
    if not str(text).strip():
        issues.append("empty-text")
    lower = str(text).lower()
    if any(term in lower for term in VAGUE_TERMS):
        issues.append("vague")
    if not requirement.get("traceable"):
        issues.append("not-traceable")
    return issues


def classify_derived(has_higher_level_source: bool) -> str:
    """'derived' when there is no direct higher-level source, else 'allocated'."""
    return "allocated" if has_higher_level_source else "derived"


def capture_readiness(requirements: list) -> tuple:
    """(ready, score) fraction of requirements with no issues.

    Raises ValueError on an empty list. Ready means score >= 0.7
    (project-defined threshold)."""
    if not requirements:
        raise ValueError("requirements list must not be empty")
    clean = sum(1 for req in requirements if not req_issues(req))
    score = clean / float(len(requirements))
    return (score >= 0.7, score)


def traceability_summary(requirements: list) -> dict:
    """Traceability health of a hardware requirements set.

    Returns counts of allocated (upward-traced) vs derived requirements,
    derived requirements lacking a justification, and a per-requirement
    issue list for the design review. Derived requirements are added
    during design or safety analysis with no direct higher-level source;
    they must be identified and justified and they count for verification.
    """
    allocated = 0
    allocated_traced = 0
    derived = 0
    derived_justified = 0
    issues_by_id = {}
    for req in requirements:
        issues = req_issues(req)
        if classify_derived(bool(req.get("source"))) == "allocated":
            allocated += 1
            if req.get("traceable"):
                allocated_traced += 1
        else:
            derived += 1
            if req.get("justification"):
                derived_justified += 1
        if issues:
            issues_by_id[req.get("id", "?")] = issues
    total = len(requirements)
    readiness = capture_readiness(requirements)
    return {
        "total": total,
        "allocated": allocated,
        "allocated_traced": allocated_traced,
        "derived": derived,
        "derived_justified": derived_justified,
        "issue_count": sum(len(v) for v in issues_by_id.values()),
        "issues_by_id": issues_by_id,
        "readiness_score": round(readiness[1], 4),
        "ready": readiness[0],
        "allocated_traced_complete": (allocated > 0 and
                                      allocated_traced == allocated),
        "derived_justified_complete": derived == 0 or derived_justified == derived,
    }


# ---------------------------------------------------------------------------
# PHAC builder: produces the actual deliverable content
# ---------------------------------------------------------------------------

def build_phac(item: HardwareItem) -> dict:
    """Build the complete PHAC content model from project facts."""
    dal = item.assurance_level()
    aeh_class = item.aeh_class()
    methods = sorted(verification_methods_for(aeh_class, dal)
                     if dal in ("A", "B", "C", "D") else [])
    return {
        "document_type": "Plan for Hardware Aspects of Certification",
        "status": "draft-for-review",
        "item": item.item_name,
        "item_description": item.description,
        "certification_basis": item.certification_basis,
        "assurance_level": dal,
        "severity_source": item.failure_condition,
        "system_safety_reference": item.system_safety_ref,
        "aeh_class": aeh_class,
        "life_cycle_model": item.life_cycle_model,
        "technology": item.technology,
        "life_cycle_data": life_cycle_data(dal),
        "coverage_ratio": coverage_ratio(dal),
        "verification_methods": methods,
        "independence": independence_required(dal),
        "independence_text": ("independent" if independence_required(dal)
                              else "may be conducted by the developer"),
        "hwsw_integration": hwsw_integration_evidence(True),
        "planning_artifacts": planning_artifacts(aeh_class),
        "hdl_languages": item.hdl_languages,
        "target_device": item.target_device,
        "development_tools": item.development_tools,
        "verification_tools": item.verification_tools,
        "tool_qualification_approach": item.tool_qualification_approach,
        "previously_developed": item.previously_developed,
        "pds_origin_standard": item.pds_origin_standard,
        "objectives": VERIFICATION_FAMILIES[dal],
        "traceability": traceability_summary(item.requirements or []),
        "generated": _today(),
    }


def life_cycle_data(dal: str) -> list:
    _check_dal(dal)
    return LIFE_CYCLE_DATA[dal]


def render_phac_markdown(model: dict) -> str:
    """Render the PHAC content model as the deliverable markdown document."""
    t = model["traceability"]
    if model["coverage_ratio"] is not None:
        coverage_line = ("- Requirements-based coverage ratio: "
                         f"{model['coverage_ratio']:.2f} "
                         f"(level {model['assurance_level']}).")
    else:
        coverage_line = ("- Requirements-based coverage ratio: none "
                         "(no safety effect).")
    objectives = model["objectives"] or ["none (no safety effect)"]
    lines = [
        "# Plan for Hardware Aspects of Certification",
        "",
        f"**Item:** {model['item']}",
        f"**Design assurance level:** {model['assurance_level']} "
        f"(from {model['severity_source']} failure condition)",
        f"**AEH class:** {model['aeh_class']}",
        f"**Certification basis:** {model['certification_basis']}",
        f"**Status:** {model['status']}",
        "",
        "## 1. Scope",
        "",
        f"This plan covers the airborne electronic hardware item "
        f"{model['item']}."
        + (f" {model['item_description']}" if model['item_description'] else ""),
        f"The item is {model['aeh_class']} AEH per DO-254, technology "
        f"{model['technology'] or 'to be defined'}.",
        "",
        "## 2. Design assurance level and failure-condition basis",
        "",
        f"The hardware design assurance level is {model['assurance_level']} "
        f"based on the {model['severity_source']} failure condition"
        + (f" (system safety reference {model['system_safety_reference']})"
           if model['system_safety_reference'] else "") + ".",
        "",
        "## 3. Hardware life cycle and life cycle data",
        "",
        f"The {model['life_cycle_model']} life cycle is used. The hardware "
        "life cycle data set for this level is:",
        "",
        *[f"- {d}" for d in model["life_cycle_data"]],
        "",
        "## 4. Hardware design assurance environment",
        "",
        f"- Development tools: {', '.join(model['development_tools']) or 'to be defined'}",
        f"- Verification tools: {', '.join(model['verification_tools']) or 'to be defined'}",
        f"- Tool qualification: {model['tool_qualification_approach']}",
        "",
        "## 5. Requirements capture and traceability",
        "",
        f"- Requirements under review: {t['total']} "
        f"(allocated {t['allocated']}, derived {t['derived']}).",
        f"- Allocated requirements traced upward: "
        f"{t['allocated_traced']} of {t['allocated']} "
        f"({'complete' if t['allocated_traced_complete'] else 'INCOMPLETE'}).",
        f"- Derived requirements justified: {t['derived_justified']} of "
        f"{t['derived']} "
        f"({'complete' if t['derived_justified_complete'] else 'INCOMPLETE'}).",
        f"- Capture readiness score: {t['readiness_score']:.2f} "
        f"({'ready' if t['ready'] else 'NOT READY'}).",
        "- Hardware requirements are reviewed for completeness, "
        "correctness, and verifiability with unique identifiers and "
        "trace links; vague wording fails the review.",
        "",
        "## 6. Design and implementation",
        "",
        f"- HDL languages: {', '.join(model['hdl_languages']) or 'to be defined'}.",
        f"- Target device: {model['target_device'] or 'to be defined'}.",
        "- Conceptual design and detailed design data are produced for "
        "complex AEH and reviewed against the requirements.",
        "",
        "## 7. Verification strategy",
        "",
        f"- Verification methods: {', '.join(model['verification_methods']) or 'reduced (level E)'}.",
        coverage_line,
        f"- Verification independence: {model['independence_text']}.",
        "- Hardware/software integration evidence ties the item to the "
        "software it hosts.",
        "",
        "## 8. Configuration management",
        "",
        "The hardware configuration management plan defines baselines, "
        "change control (ECR/ECO), and the hardware configuration index "
        "(HCI). Class 1 changes (form/fit/function, safety effect, or "
        "complex hardware) require baseline update, reverification, and "
        "independent review.",
        "",
        "## 9. Process assurance",
        "",
        "Hardware process assurance monitors conformity of the life cycle "
        "data and records objective evidence of process compliance.",
        "",
        "## 10. Certification liaison and compliance",
        "",
        "Certification authority liaison, means of compliance, and the "
        "acceptance basis (AC 20-152A) are addressed with the airworthiness "
        "authority. Previously developed hardware, when used, is assessed "
        "under the PDS process.",
        "",
        "## 11. Objectives summary",
        "",
        *[f"- {o}" for o in objectives],
        "",
        "---",
        f"*Generated by Aero Agent Roles do254-hardware-engineer core "
        f"({model['generated']}). DRAFT for human hardware certification "
        "engineer review. Not an approval document.*",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evidence gate checkers: verify a deliverable meets the role's gates
# ---------------------------------------------------------------------------

GATE_CHECKS = {
    "level_identified": "assurance_level is a single valid DAL letter",
    "aeh_classified": "item classified simple or complex AEH",
    "life_cycle_data_present": "life cycle data set is non-empty and "
                               "level-appropriate",
    "coverage_stated": "requirements-based coverage ratio present",
    "methods_stated": "verification methods stated for the class/level",
    "traceability_ready": "allocated traced, derived justified, readiness "
                          "score at or above 0.7",
    "sign_off_honest": "document is marked draft-for-review, not approval",
}


def check_phac(model: dict) -> dict:
    """Run the evidence gates against a PHAC model. Pass/fail per gate."""
    dal = model.get("assurance_level", "")
    t = model.get("traceability", {})
    results = {
        "level_identified": dal in DALS,
        "aeh_classified": model.get("aeh_class") in ("simple", "complex"),
        "life_cycle_data_present": bool(model.get("life_cycle_data")),
        "coverage_stated": isinstance(model.get("coverage_ratio"), (int, float))
                           or model.get("coverage_ratio") is None,
        "methods_stated": isinstance(model.get("verification_methods"), list),
        "traceability_ready": (bool(t.get("allocated_traced_complete"))
                               and bool(t.get("derived_justified_complete"))
                               and bool(t.get("ready"))),
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_phac_markdown(md_text: str, dal: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    level_pat = re.compile(r"design assurance level[:*\s]*" + dal.lower() + r"\b")
    checks = {
        "has_title": "plan for hardware aspects of certification" in low,
        "has_level": bool(level_pat.search(low)),
        "has_class": ("aeh class" in low),
        "has_coverage": "coverage ratio" in low,
        "has_independence": "independence" in low,
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str, dal: str) -> dict:
    """Public entry point used by gate tooling: check a PHAC document."""
    return check_phac_markdown(md_text, dal)


# ---------------------------------------------------------------------------
# Example project (for tests and worked-example generation)
# ---------------------------------------------------------------------------

def example_requirements() -> list:
    """A realistic requirements set for a CPLD/FPGA-based LRU function."""
    return [
        {"id": "HR-001",
         "text": "The autopilot mode logic FPGA shall select the active "
                 "flight mode from the mode-select discretes within 50 ms "
                 "of the mode change command.",
         "traceable": True, "source": "SYS-REQ-112"},
        {"id": "HR-002",
         "text": "The FPGA shall assert the autopilot engage output only "
                 "when all engage interlocks are satisfied.",
         "traceable": True, "source": "SYS-REQ-113"},
        {"id": "HR-003",
         "text": "The FPGA shall de-assert the engage output within 20 ms "
                 "of any disengage interlock opening.",
         "traceable": True, "source": "SYS-REQ-114"},
        {"id": "HR-004",
         "text": "The FPGA shall latch the last valid mode state across a "
                 "power interruption of up to 10 ms.",
         "traceable": True, "source": "SYS-REQ-115"},
        {"id": "HR-005",
         "text": "The FPGA shall present the active mode on the ARINC 429 "
                 "output bus within one output frame.",
         "traceable": True, "source": "SYS-REQ-116"},
        {"id": "HR-006",
         "text": "The FPGA shall ignore mode-select inputs while the "
                 "engage interlock is open.",
         "traceable": True, "source": "SYS-REQ-113"},
        {"id": "HR-007",
         "text": "The FPGA shall drive the watchdog output with a pulse "
                 "train of period 10 ms plus-or-minus 1 ms while the "
                 "internal sequencer is running.",
         "traceable": True, "source": "SYS-REQ-117"},
        {"id": "HR-008",
         "text": "The FPGA shall reset to the disengaged state on power-up "
                 "or on watchdog time-out.",
         "traceable": True, "source": "SYS-REQ-114"},
        {"id": "HR-009",
         "text": "The FPGA shall debounce the mode-select discretes over "
                 "a 5 ms window before accepting a state change.",
         "traceable": True, "source": "SYS-REQ-112"},
        {"id": "HR-010",
         "text": "The FPGA shall report internal status on the built-in "
                 "test output word every 100 ms.",
         "traceable": True, "source": "SYS-REQ-118"},
        # Derived requirement: added during detailed design, justified.
        {"id": "HR-011",
         "text": "The FPGA shall implement a one-hot state encoding for "
                 "the mode sequencer to prevent multiple-mode lockup.",
         "traceable": False, "source": "",
         "justification": "One-hot encoding chosen during detailed design "
                          "to guarantee single-mode arbitration (safety "
                          "analysis of mode lockup)."},
        # Derived requirement: added from safety analysis, justified.
        {"id": "HR-012",
         "text": "The FPGA shall provide a hardware mode-select voting "
                 "scheme across the two mode-select discretes.",
         "traceable": False, "source": "",
         "justification": "Dual-discrete voting added following the "
                          "FPGA-level FMEA to protect against a stuck "
                          "discrete failure."},
    ]


def example_item() -> HardwareItem:
    """Reference item: a complex CPLD/FPGA-based LRU function."""
    return HardwareItem(
        item_name="Autopilot Mode Logic FPGA (complex CPLD/FPGA-based "
                  "LRU function)",
        description="FPGA implementation of the autopilot flight mode "
                    "selection and engage logic hosted in the flight "
                    "guidance computer LRU.",
        failure_condition="hazardous",
        system_safety_ref="FHA-FGS-001 / PSSA rev C",
        has_programmable_logic=True,
        has_internal_state=True,
        fully_verifiable_from_top_data=False,
        safety_significant=True,
        technology="CPLD/FPGA programmable logic",
        life_cycle_model="waterfall",
        hdl_languages=["VHDL"],
        target_device="FPGA, flight guidance computer LRU",
        development_tools=["HDL synthesis tool", "static timing analyzer"],
        verification_tools=["HDL simulator", "requirements-based test "
                            "harness", "code coverage tool"],
        tool_qualification_approach="criteria-based per DO-254 tool "
                                    "assessment",
        certification_basis="FAR/CS-25",
        requirements=example_requirements(),
    )


def example_phac_markdown() -> str:
    return render_phac_markdown(build_phac(example_item()))


if __name__ == "__main__":
    item = example_item()
    model = build_phac(item)
    md = render_phac_markdown(model)
    print(f"ASSURANCE LEVEL: {model['assurance_level']}")
    print(f"AEH CLASS: {model['aeh_class']}")
    print(f"COVERAGE RATIO: {model['coverage_ratio']:.2f}")
    print(f"INDEPENDENCE: {model['independence_text']}")
    print(f"LIFE CYCLE DATA: {len(model['life_cycle_data'])} items")
    print(f"TRACEABILITY: {model['traceability']}")
    print(f"GATES: {check_phac(model)}")
    print(f"RENDERED: {len(md)} chars")
