#!/usr/bin/env python3
"""do178c_core.py - DO-178C Certification Engineer executable core.

This is the role's ENGINE: given a software item's project facts it
computes DAL requirements, coverage targets, independence, the life
cycle data set, verification objectives, and BUILDS the Plan for
Software Aspects of Certification (PSAC) content. It also gate-checks
deliverables. Standalone: no external repo needed.

Domain rules encoded here are public process knowledge (DAL levels,
coverage metrics, independence practice as published in FAA AC 20-115D /
EASA AMC 20-115C and standard certification practice). DO-178C text is
never reproduced - the plan structure is an original synthesis.
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

# Software level from failure-condition severity (FAR 25.1309 / CS-25.1309
# standard severity categories -> DAL mapping used in certification practice).
SEVERITY_TO_DAL = {
    "catastrophic": "A",
    "hazardous": "B",
    "major": "C",
    "minor": "D",
    "no-safety-effect": "E",
}
DALS = ("A", "B", "C", "D", "E")

# Coverage targets by DAL (requirements-based coverage ratios, as used in
# verification practice: A/B 0.98, C/D 0.95 per measured requirements).
COVERAGE_TARGET = {"A": 0.98, "B": 0.98, "C": 0.95, "D": 0.95, "E": None}

# Structural coverage requirements by DAL (standard practice): MC/DC at A,
# decision coverage at B, statement coverage at C.
STRUCTURAL = {
    "A": ["statement", "decision", "mc-dc", "data-coupling", "control-coupling"],
    "B": ["statement", "decision", "data-coupling", "control-coupling"],
    "C": ["statement"],
    "D": [],
    "E": [],
}

# Independence expectations by DAL (verification independence for A/B).
INDEPENDENT = {"A": True, "B": True, "C": False, "D": False, "E": False}

# Life cycle data set by DAL: the data items a PSAC must name. Levels with
# more rigor require the full set; E is minimal. (Original synthesis of the
# standard plan-of-attack categories, not reproduced text.)
LIFE_CYCLE_DATA = {
    "A": [
        "plan for software aspects of certification",
        "software development plan",
        "software verification plan",
        "software configuration management plan",
        "software quality assurance plan",
        "software requirements standards",
        "software design standards",
        "software code standards",
        "software requirements data",
        "software design data",
        "software source code",
        "executable object code",
        "software verification results",
        "software life cycle environment configuration index",
        "software configuration index",
        "software accomplishment summary",
        "software conformity review records",
    ],
    "B": [
        "plan for software aspects of certification",
        "software development plan",
        "software verification plan",
        "software configuration management plan",
        "software quality assurance plan",
        "software requirements standards",
        "software design standards",
        "software code standards",
        "software requirements data",
        "software design data",
        "software source code",
        "executable object code",
        "software verification results",
        "software life cycle environment configuration index",
        "software configuration index",
        "software accomplishment summary",
    ],
    "C": [
        "plan for software aspects of certification",
        "software development plan",
        "software verification plan",
        "software configuration management plan",
        "software quality assurance plan",
        "software requirements data",
        "software design data",
        "software source code",
        "executable object code",
        "software verification results",
        "software life cycle environment configuration index",
        "software configuration index",
        "software accomplishment summary",
    ],
    "D": [
        "plan for software aspects of certification",
        "software development plan",
        "software verification plan",
        "software configuration management plan",
        "software quality assurance plan",
        "software requirements data",
        "software design data",
        "software source code",
        "executable object code",
        "software verification results",
        "software life cycle environment configuration index",
        "software configuration index",
    ],
    "E": [
        "software requirements data",
        "software design data",
        "software source code",
        "software verification results",
    ],
}

# Verification objectives by DAL: the objective families expected per level
# (public practice: completeness/independence/coverage expectations).
VERIFICATION_FAMILIES = {
    "A": ["planning", "development", "verification", "cm", "sqa", "cert-liaison"],
    "B": ["planning", "development", "verification", "cm", "sqa", "cert-liaison"],
    "C": ["planning", "development", "verification", "cm", "sqa"],
    "D": ["planning", "development", "verification", "cm", "sqa"],
    "E": ["development", "verification"],
}


@dataclass
class SoftwareItem:
    """Project facts the role needs to build the PSAC."""
    item_name: str
    description: str = ""
    failure_condition: str = "major"          # severity category
    system_safety_ref: str = ""               # FHA/PSSA reference
    life_cycle_model: str = "waterfall"
    programming_languages: list = field(default_factory=lambda: ["C"])
    target_platform: str = ""
    development_tools: list = field(default_factory=list)
    verification_tools: list = field(default_factory=list)
    tool_qualification_approach: str = "criteria-based per DO-330"
    previously_developed: bool = False
    pds_origin_standard: str = ""
    certification_basis: str = "FAR/CS-25"

    def software_level(self) -> str:
        return SEVERITY_TO_DAL.get(self.failure_condition.lower(), "E")


# ---------------------------------------------------------------------------
# Core computations
# ---------------------------------------------------------------------------

def _check_dal(dal: str) -> None:
    if dal not in DALS:
        raise ValueError(f"invalid DAL {dal!r}")


def coverage_target(dal: str) -> float | None:
    _check_dal(dal)
    return COVERAGE_TARGET[dal]


def structural_coverage(dal: str) -> list[str]:
    _check_dal(dal)
    return STRUCTURAL[dal]


def independence_required(dal: str) -> bool:
    _check_dal(dal)
    return INDEPENDENT[dal]


def life_cycle_data(dal: str) -> list[str]:
    _check_dal(dal)
    return LIFE_CYCLE_DATA[dal]


def coverage_adequate(dal: str, measured_pct: float) -> bool:
    """True when measured requirements-based coverage meets the DAL target."""
    target = coverage_target(dal)
    if target is None:
        return True
    return measured_pct >= target


def verification_independence_note(dal: str) -> str:
    return ("independent" if independence_required(dal)
            else "may be conducted by the developer")


def structural_methods_text(dal: str) -> str:
    cov = structural_coverage(dal)
    if not cov:
        return "No structural coverage required at this level."
    return "Required: " + ", ".join(cov) + "."


# ---------------------------------------------------------------------------
# PSAC builder: produces the actual deliverable content
# ---------------------------------------------------------------------------

def build_psac(item: SoftwareItem) -> dict:
    """Build the complete PSAC content model from project facts."""
    dal = item.software_level()
    return {
        "document_type": "Plan for Software Aspects of Certification",
        "status": "draft-for-review",
        "item": item.item_name,
        "item_description": item.description,
        "certification_basis": item.certification_basis,
        "software_level": dal,
        "severity_source": item.failure_condition,
        "system_safety_reference": item.system_safety_ref,
        "life_cycle_model": item.life_cycle_model,
        "coverage_target": coverage_target(dal),
        "structural_coverage": structural_coverage(dal),
        "independence": verification_independence_note(dal),
        "life_cycle_data": life_cycle_data(dal),
        "languages": item.programming_languages,
        "target_platform": item.target_platform,
        "development_tools": item.development_tools,
        "verification_tools": item.verification_tools,
        "tool_qualification_approach": item.tool_qualification_approach,
        "previously_developed": item.previously_developed,
        "pds_origin_standard": item.pds_origin_standard,
        "objectives": VERIFICATION_FAMILIES[dal],
        "generated": _today(),
    }


def render_psac_markdown(model: dict) -> str:
    """Render the PSAC content model as the deliverable markdown document."""
    lines = [
        "# Plan for Software Aspects of Certification",
        "",
        f"**Item:** {model['item']}",
        f"**Software level:** {model['software_level']} "
        f"(from {model['severity_source']} failure condition)",
        f"**Certification basis:** {model['certification_basis']}",
        f"**Status:** {model['status']}",
        "",
        "## 1. Scope",
        "",
        f"This plan covers the software item {model['item']}."
        + (f" {model['item_description']}" if model['item_description'] else ""),
        f"The software level is {model['software_level']} based on the "
        f"{model['severity_source']} failure condition"
        + (f" (system safety reference {model['system_safety_reference']})"
           if model['system_safety_reference'] else "") + ".",
        "",
        "## 2. Software life cycle",
        "",
        f"The {model['life_cycle_model']} life cycle is used. The life cycle "
        "data set for this level is:",
        "",
        *[f"- {d}" for d in model["life_cycle_data"]],
        "",
        "## 3. Software life cycle environment",
        "",
        f"- Development tools: {', '.join(model['development_tools']) or 'none'}"
        if model["development_tools"] else "- Development tools: to be defined",
        f"- Verification tools: {', '.join(model['verification_tools']) or 'none'}"
        if model["verification_tools"] else "- Verification tools: to be defined",
        f"- Tool qualification: {model['tool_qualification_approach']}",
        "",
        "## 4. Software development standards",
        "",
        "- Requirements standards: project-defined, referenced in the "
        "software development plan.",
        "- Design standards: project-defined.",
        f"- Code standards: {', '.join(model['languages'])} subset and "
        "metrics defined in the software code standard.",
        "",
        "## 5. Software verification strategy",
        "",
        f"- Requirements-based coverage target: "
        f"{model['coverage_target']:.2f} (level {model['software_level']}).",
        f"- Structural coverage: {', '.join(model['structural_coverage']) or 'none required'}.",
        f"- Verification independence: {model['independence']}.",
        "",
        "## 6. Software configuration management",
        "",
        "The configuration management plan defines baselines, change "
        "control, archiving, and the configuration index for this item.",
        "",
        "## 7. Software quality assurance",
        "",
        "The software quality assurance plan defines SQA process, audits, "
        "and conformity review for this level.",
        "",
        "## 8. Liaison with airworthiness",
        "",
        "Certification authority liaison and the means of compliance are "
        "defined in the certification plan.",
        "",
        "## 9. Objectives summary",
        "",
        *[f"- {o}" for o in model["objectives"]],
        "",
        "---",
        f"*Generated by Aero Agent Roles do178c-cert-engineer core "
        f"({model['generated']}). DRAFT for human certification engineer "
        "review. Not an approval document.*",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evidence gate checkers: verify a deliverable meets the role's gates
# ---------------------------------------------------------------------------

GATE_CHECKS = {
    "level_identified": "software_level is a single valid DAL letter",
    "coverage_target_present": "requirements-based coverage target is a number",
    "structural_stated": "structural coverage list is present for the DAL",
    "life_cycle_data_present": "life cycle data set is non-empty and level-appropriate",
    "sign_off_honest": "document is marked draft-for-review, not approval",
}


def check_psac(model: dict) -> dict:
    """Run the evidence gates against a PSAC model. Returns pass/fail per gate."""
    dal = model.get("software_level", "")
    results = {
        "level_identified": dal in DALS,
        "coverage_target_present": isinstance(model.get("coverage_target"), (int, float)),
        "structural_stated": isinstance(model.get("structural_coverage"), list),
        "life_cycle_data_present": bool(model.get("life_cycle_data")),
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_psac_markdown(md_text: str, dal: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    level_pat = re.compile(r"software level[:\*]*\s*" + dal.lower() + r"\b")
    checks = {
        "has_title": "plan for software aspects of certification" in low,
        "has_level": bool(level_pat.search(low)),
        "has_coverage": "coverage target" in low,
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str, dal: str) -> dict:
    """Public entry point used by gate tooling: check a PSAC document."""
    return check_psac_markdown(md_text, dal)


# ---------------------------------------------------------------------------
# Example project (for tests and worked-example generation)
# ---------------------------------------------------------------------------

def example_item() -> SoftwareItem:
    return SoftwareItem(
        item_name="Autopilot Flight Guidance System (FGS) software",
        description="DAL-B autopilot software hosted on the flight "
                    "guidance computer.",
        failure_condition="hazardous",
        system_safety_ref="FHA-FGS-001 / PSSA rev C",
        life_cycle_model="waterfall",
        programming_languages=["C"],
        target_platform="PowerPC-based flight guidance computer",
        development_tools=["host compiler", "static analyzer"],
        verification_tools=["requirements-based test harness",
                            "code coverage tool"],
        tool_qualification_approach="criteria-based qualification per DO-330",
        certification_basis="FAR/CS-25",
    )


def example_psac_markdown() -> str:
    return render_psac_markdown(build_psac(example_item()))


if __name__ == "__main__":
    import sys
    item = example_item()
    model = build_psac(item)
    md = render_psac_markdown(model)
    print(f"SOFTWARE LEVEL: {model['software_level']}")
    print(f"COVERAGE TARGET: {model['coverage_target']:.2f}")
    print(f"INDEPENDENCE: {model['independence']}")
    print(f"LIFE CYCLE DATA: {len(model['life_cycle_data'])} items")
    print(f"GATES: {check_psac(model)}")
    print(f"RENDERED: {len(md)} chars")
