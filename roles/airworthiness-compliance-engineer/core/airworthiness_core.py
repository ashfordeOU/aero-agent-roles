#!/usr/bin/env python3
"""airworthiness_core.py - Airworthiness Compliance Engineer executable core.

This is the role's ENGINE: given a certification item's project facts it
determines the applicable FAR-25 / CS-25 regulations, selects the means of
compliance per regulation, assigns the compliance document and an honest
proposed status, and BUILDS the airworthiness compliance matrix (the
certification matrix / compliance checklist deliverable). It also
gate-checks deliverables. Standalone: no external repo needed.

Domain rules encoded here are public process knowledge:
- Regulation numbers, section titles and subpart placement of 14 CFR
  Part 25 (FAR-25) are public-domain (US government work, quotable with
  citation; verified against eCFR). CS-25 mirrors FAR-25 with EU
  amendments; referenced at rule level only.
- The means-of-compliance selection rules are a deterministic summary of
  public certification practice (the six-class MOC scheme and the
  analysis / test / inspection / similarity vocabulary). No verbatim AMC
  or regulatory body text is reproduced.

Author: ashfordeOU
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date

# ---------------------------------------------------------------------------
# Domain tables (public-domain FAR-25 / CS-25 structure and practice)
# ---------------------------------------------------------------------------

# Severity of a failure condition -> development assurance level context
# (standard 25.1309 practice, as used in certification programs).
SEVERITY_TO_DAL = {
    "catastrophic": "A",
    "hazardous": "B",
    "major": "C",
    "minor": "D",
    "no-safety-effect": "E",
    "n/a": "n/a",
}
DALS = ("A", "B", "C", "D", "E", "n/a")

# Failure-condition severities that trigger the 25.1309 safety assessment
# (systems whose failure conditions are catastrophic, hazardous, or major).
SAFETY_SIGNIFICANT = ("catastrophic", "hazardous", "major")

# Means-of-compliance vocabulary, six-class scheme used in certification
# practice (summary of public EASA/FAA style MOC categories).
MOC_NAMES = {
    1: "engineering/analysis",
    2: "ground test",
    3: "flight test",
    4: "simulation/analysis tool",
    5: "certification by similarity",
    6: "safety assessment",
}
MOC_IDS = tuple(sorted(MOC_NAMES))

# Coarse method words accepted in a compliance matrix (FAA-style vocabulary
# per public airworthiness practice: analysis, test, inspection, similarity).
MOC_WORDS = (
    "analysis",
    "test",
    "ground test",
    "flight test",
    "inspection",
    "similarity",
    "safety assessment",
    "engineering/analysis",
    "simulation/analysis tool",
    "certification program demonstration",
)

# Item kinds a certification item can be (per-item MOC suitability rules).
ITEM_KINDS = (
    "structure",
    "systems",
    "powerplant",
    "equipment",
    "software",
    "hardware",
    "performance",
    "handling",
)

# FAR-25 subpart placement for the regulations this role routes on.
# Letters/names are the public FAR-25 structure (A General, C Structure,
# D Design and Construction, F Equipment, ...).
SUBPARTS = {
    "A": "General",
    "B": "Flight",
    "C": "Structure",
    "D": "Design and Construction",
    "E": "Powerplant",
    "F": "Equipment",
    "G": "Operating Limitations and Information",
    "H": "Electrical Wiring Interconnection Systems (EWIS)",
}

# Representative area mapping (which product area a paragraph belongs to),
# transport-airplane oriented per public FAR-25 structure.
AREA_PARAGRAPHS = {
    "systems": ["25.1309", "25.1310", "25.1329"],
    "flight-controls": ["25.671", "25.672", "25.675", "25.677", "25.679", "25.683"],
    "structure": ["25.301", "25.303", "25.305", "25.307", "25.571", "25.629"],
    "design-and-construction": ["25.601", "25.603", "25.605", "25.607", "25.609"],
    "powerplant": ["25.901", "25.903", "25.933", "25.943", "25.1101"],
    "equipment": ["25.1301", "25.1303", "25.1305", "25.1309", "25.1316"],
    "operating-limitations": ["25.1501", "25.1503", "25.1511", "25.1521"],
    "ewis": ["25.1701", "25.1703", "25.1707", "25.1709", "25.1711", "25.1713", "25.1717"],
}

# Regulation register: real FAR-25 paragraphs used by this role. Fields:
#   subpart      - public FAR-25 subpart letter
#   area         - product area key from AREA_PARAGRAPHS
#   item_kind    - item kind for MOC suitability
#   severity     - context severity of the paragraph in a typical systems
#                  installation (structure rows carry "n/a")
#   novel_by_default - True when a retrofit of this kind is typically a new
#                  feature screened against the existing basis
# Section titles are the public eCFR titles (public domain, quotable).
REGS = {
    "25.1301": {
        "title": "Function and installation",
        "subpart": "F",
        "area": "equipment",
        "item_kind": "equipment",
        "severity": "n/a",
        "compliance_document": "Equipment installation inspection records and "
                               "qualification test report (installation conformity)",
    },
    "25.1303": {
        "title": "Flight and navigation instruments",
        "subpart": "F",
        "area": "equipment",
        "item_kind": "equipment",
        "severity": "n/a",
        "compliance_document": "Instrument installation conformity records",
    },
    "25.1309": {
        "title": "Equipment, systems, and installations",
        "subpart": "F",
        "area": "systems",
        "item_kind": "systems",
        "severity": "hazardous",
        "compliance_document": "System safety assessment (SSA) per 25.1309 "
                               "with failure condition classification",
    },
    "25.1310": {
        "title": "Power source capacity and distribution",
        "subpart": "F",
        "area": "systems",
        "item_kind": "systems",
        "severity": "major",
        "compliance_document": "Electrical load analysis and power source "
                               "capacity report",
    },
    "25.1329": {
        "title": "Flight guidance system (autopilot)",
        "subpart": "F",
        "area": "systems",
        "item_kind": "systems",
        "severity": "hazardous",
        "compliance_document": "Autopilot ground/flight test report and SSA "
                               "input for the flight guidance system",
    },
    "25.671": {
        "title": "General (flight control systems)",
        "subpart": "D",
        "area": "flight-controls",
        "item_kind": "systems",
        "severity": "hazardous",
        "compliance_document": "Flight control integration analysis and test "
                               "report (control system failure assessment)",
    },
    "25.683": {
        "title": "Operation tests",
        "subpart": "D",
        "area": "flight-controls",
        "item_kind": "systems",
        "severity": "n/a",
        "compliance_document": "Control system operation test report",
    },
    "25.301": {
        "title": "Loads",
        "subpart": "C",
        "area": "structure",
        "item_kind": "structure",
        "severity": "n/a",
        "compliance_document": "Loads analysis report (change-effect "
                               "assessment on the affected structure)",
    },
    "25.571": {
        "title": "Damage tolerance and fatigue evaluation of structure",
        "subpart": "C",
        "area": "structure",
        "item_kind": "structure",
        "severity": "n/a",
        "compliance_document": "Damage tolerance / fatigue evaluation and "
                               "inspection program for affected structure",
    },
    "25.607": {
        "title": "Fasteners",
        "subpart": "D",
        "area": "design-and-construction",
        "item_kind": "structure",
        "severity": "n/a",
        "compliance_document": "Fastener standards compliance record",
    },
    "25.629": {
        "title": "Aeroelastic stability requirements",
        "subpart": "C",
        "area": "structure",
        "item_kind": "structure",
        "severity": "n/a",
        "compliance_document": "Flutter / aeroelastic stability analysis and "
                               "flight test clearance report",
    },
}

# Per-regulation extra methods of compliance that real demonstration
# practice requires on top of the item-kind suitability set (original
# routing summary, e.g. flight test for autopilot operation tests).
REG_EXTRA_MOC = {
    "25.1329": ["flight test"],
    "25.683": ["ground test"],
    "25.629": ["flight test"],
}

# Certification basis by aircraft type (public regulation mapping).
# Product airplane: transport -> Part 25 (FAR-25/CS-25); normal/utility/
# acrobatic/commuter -> Part 23; rotorcraft -> Part 27/29; engines Part 33;
# propellers Part 35. This role routes on transport-category airplanes
# (FAR-25 / CS-25) but keeps the full public mapping for screening.
AIRCRAFT_REGULATION = {
    ("airplane", "transport"): "25",
    ("airplane", "normal"): "23",
    ("airplane", "utility"): "23",
    ("airplane", "acrobatic"): "23",
    ("airplane", "commuter"): "23",
    ("rotorcraft", "normal"): "27",
    ("rotorcraft", "transport"): "29",
    ("engine", "n/a"): "33",
    ("propeller", "n/a"): "35",
}
AIRCRAFT_ALIASES = {
    "transport": ("airplane", "transport"),
    "transport-category": ("airplane", "transport"),
    "transport airplane": ("airplane", "transport"),
    "large airplane": ("airplane", "transport"),
    "normal": ("airplane", "normal"),
    "normal-category": ("airplane", "normal"),
    "rotorcraft": ("rotorcraft", "normal"),
    "rotorcraft transport": ("rotorcraft", "transport"),
    "engine": ("engine", "n/a"),
    "propeller": ("propeller", "n/a"),
}

# Owners by product area (original role assignment table).
AREA_OWNER = {
    "systems": "systems safety engineer",
    "flight-controls": "flight controls engineer",
    "structure": "structures engineer",
    "design-and-construction": "design engineer",
    "powerplant": "powerplant engineer",
    "equipment": "equipment engineer",
    "operating-limitations": "flight test engineer",
    "ewis": "EWIS engineer",
}

# Statuses this role may write. A finding ("compliant") is NEVER written:
# that is the certification authority's call.
STATUS_PROPOSED = "proposed"
STATUS_VOCABULARY = ("proposed", "open", "in-work", "evidence-available")
FORBIDDEN_STATUS = ("compliant", "found", "approved", "issued")

# ---------------------------------------------------------------------------
# Core computations
# ---------------------------------------------------------------------------


def _canonical_aircraft(aircraft_type: str) -> tuple[str, str]:
    """Map an aircraft_type string to (product_type, category)."""
    key = (aircraft_type or "").strip().lower()
    if key in AIRCRAFT_ALIASES:
        return AIRCRAFT_ALIASES[key]
    raise ValueError(
        "unknown aircraft_type %r; expected one of %s"
        % (aircraft_type, ", ".join(sorted(AIRCRAFT_ALIASES)))
    )


def reg_number(reg) -> str:
    """Normalize a regulation reference to a bare number (e.g. 25.1309)."""
    if isinstance(reg, dict):
        reg = reg.get("number") or reg.get("reg") or ""
    text = str(reg or "").strip()
    text = text.replace("FAR ", "").replace("CS-", "").replace("CS ", "")
    match = re.fullmatch(r"(\d{2}\.\d{3,4})", text)
    if match is None:
        raise ValueError("invalid regulation reference %r" % (reg,))
    return match.group(1)


def determine_applicability(reg, aircraft_type: str,
                           change_scope=None) -> dict:
    """Determine whether a regulation applies to a change on an aircraft.

    Returns a verdict dict {reg, aircraft_type, product, category,
    applicable, part, reason}. Two gates:
    1. Aircraft-type gate: a FAR-25/CS-25 paragraph applies to
       transport-category airplanes only; other categories screen to
       their governing part (public regulation mapping).
    2. Change-scope gate (when ``change_scope`` is given): the reg's
       product area must be inside the change scope (e.g. an autopilot
       STC that touches systems/flight-controls/equipment screens out
       pure-structure paragraphs such as 25.571).
    """
    number = reg_number(reg)
    if number not in REGS:
        raise ValueError(
            "unknown regulation %r - not in the role's FAR-25 register"
            % (number,)
        )
    product, category = _canonical_aircraft(aircraft_type)
    governing = AIRCRAFT_REGULATION.get((product, category))
    if governing is None:
        raise ValueError(
            "no governing airworthiness part for %s %s"
            % (product, category)
        )
    if not number.startswith(governing + "."):
        return {
            "reg": number,
            "aircraft_type": aircraft_type,
            "product": product,
            "category": category,
            "applicable": False,
            "part": governing,
            "reason": (
                "not applicable: %s is a Part 25 paragraph but a %s category "
                "%s certifies under Part %s/CS-%s (the equivalent paragraph, "
                "where one exists, lives in that part)"
                % (number, category, product, governing, governing)
            ),
        }
    # Part matches the aircraft type: now screen against the change scope.
    if change_scope is not None:
        area = REGS[number]["area"]
        if area not in change_scope:
            return {
                "reg": number,
                "aircraft_type": aircraft_type,
                "product": product,
                "category": category,
                "applicable": False,
                "part": governing,
                "reason": (
                    "not applicable to this change: %s covers the %s area "
                    "but the change scope is limited to %s; screened out "
                    "unless the change also touches the %s area - confirm "
                    "with the certification authority"
                    % (number, area, ", ".join(sorted(change_scope)), area)
                ),
            }
    return {
        "reg": number,
        "aircraft_type": aircraft_type,
        "product": product,
        "category": category,
        "applicable": True,
        "part": governing,
        "reason": (
            "applies: %s is a %s airworthiness paragraph and the product "
            "is a %s category %s"
            % (number, "FAR-25/CS-25" if governing == "25"
                else "FAR-%s/CS-%s" % (governing, governing),
               category, product)
        ),
    }


def _validate_kind_severity_dal(item_kind, severity, dal) -> None:
    if item_kind not in ITEM_KINDS:
        raise ValueError(
            "unknown item_kind %r; expected one of %s"
            % (item_kind, ", ".join(ITEM_KINDS))
        )
    if severity not in SEVERITY_TO_DAL:
        raise ValueError(
            "unknown severity %r; expected one of %s"
            % (severity, ", ".join(sorted(SEVERITY_TO_DAL)))
        )
    if dal not in DALS:
        raise ValueError(
            "unknown development_assurance_level %r; expected one of %s"
            % (dal, ", ".join(DALS))
        )


def _dedupe(seq) -> list:
    seen = []
    for entry in seq:
        if entry not in seen:
            seen.append(entry)
    return seen


def moc_suitability(item_kind: str, severity: str = "n/a",
                    dal: str = "n/a", novel: bool = False) -> list:
    """Recommended MOC ids (ordered, primary first) for an item kind.

    Deterministic routing summary of public certification practice:
    structure - analysis primary with static/ground test evidence (novel
    items add flight test); systems - analysis plus the MOC 6 safety
    assessment for catastrophic/hazardous failures (simulation acceptable
    for DAL C-E, a test MOC is added for novel items); powerplant - bench/
    ground and flight test with supporting analysis; equipment -
    environmental qualification test (DO-160 style) with analysis support;
    software - DO-178C lifecycle data; hardware - DO-254 style analysis
    plus verification test.
    """
    _validate_kind_severity_dal(item_kind, severity, dal)
    if item_kind == "structure":
        return [1, 2, 3] if novel else [1, 2]
    if item_kind == "systems":
        rec = [1]
        if severity in ("catastrophic", "hazardous"):
            rec.append(6)
        elif dal in ("C", "D", "E"):
            rec.append(4)
        if novel:
            rec.append(2)
        return _dedupe(rec)
    if item_kind == "powerplant":
        return [2, 3, 1]
    if item_kind == "equipment":
        return [2, 1]
    if item_kind == "software":
        return [1, 4]
    if item_kind == "hardware":
        return [1, 2]
    return [3, 1, 4]  # performance, handling


def safety_assessment_required(severity: str) -> bool:
    """25.1309 practice: catastrophic/hazardous/major failure conditions
    require the safety assessment."""
    if severity not in SEVERITY_TO_DAL:
        raise ValueError("unknown failure-condition severity %r" % (severity,))
    return severity in SAFETY_SIGNIFICANT


def severity_to_dal(severity: str) -> str:
    if severity not in SEVERITY_TO_DAL:
        raise ValueError("unknown severity %r" % (severity,))
    return SEVERITY_TO_DAL[severity]


def select_moc(reg, cert_basis: str = "FAR-25",
               severity: str | None = None,
               dal: str | None = None,
               novel: bool = False) -> dict:
    """Select the means of compliance for a regulation.

    Returns a dict {reg, item_kind, severity, dal, moc_ids, methods,
    moc_display, safety_assessment}. ``methods`` are coarse method words
    (analysis/test/inspection vocabulary); ``moc_display`` renders the
    six-class MOC scheme when the basis is CS-25 (per AMC practice) and
    the coarse vocabulary for FAR-25.
    """
    number = reg_number(reg)
    if number not in REGS:
        raise ValueError(
            "unknown regulation %r - not in the role's FAR-25 register"
            % (number,)
        )
    record = REGS[number]
    item_kind = record["item_kind"]
    resolved_severity = severity or record["severity"]
    resolved_dal = dal or severity_to_dal(resolved_severity)
    ids = moc_suitability(item_kind, resolved_severity, resolved_dal, novel)
    ids = _dedupe(ids + [moc_id(m) for m in REG_EXTRA_MOC.get(number, [])
                         if moc_id(m) not in ids])
    methods = [moc_name(i) for i in ids]
    basis = str(cert_basis or "FAR-25").upper()
    if "CS" in basis:
        display = " + ".join(
            "MOC %d %s" % (i, MOC_NAMES[i]) for i in ids
        ) + " (per AMC-25 style acceptable means of compliance)"
    else:
        display = " + ".join(methods)
    return {
        "reg": number,
        "item_kind": item_kind,
        "severity": resolved_severity,
        "dal": resolved_dal,
        "moc_ids": ids,
        "methods": methods,
        "moc_display": display,
        "safety_assessment": safety_assessment_required(resolved_severity),
    }


def moc_id(word: str) -> int:
    """Map a coarse method word to its MOC class id."""
    mapping = {
        "analysis": 1,
        "engineering/analysis": 1,
        "ground test": 2,
        "test": 2,
        "flight test": 3,
        "simulation": 4,
        "simulation/analysis tool": 4,
        "similarity": 5,
        "safety assessment": 6,
    }
    key = word.strip().lower()
    if key not in mapping:
        raise ValueError("unknown means of compliance %r" % (word,))
    return mapping[key]


def moc_name(moc_id_val: int) -> str:
    if moc_id_val not in MOC_NAMES:
        raise ValueError("unknown MOC id %r" % (moc_id_val,))
    return MOC_NAMES[moc_id_val]


def moc_is_valid(method: str) -> bool:
    return method.strip().lower() in MOC_WORDS


def methods_are_valid(methods) -> bool:
    return all(moc_is_valid(m) for m in methods)


def basis_name(aircraft_type: str, jurisdiction: str) -> str:
    """Certification basis regulation id for a transport airplane."""
    product, category = _canonical_aircraft(aircraft_type)
    governing = AIRCRAFT_REGULATION.get((product, category))
    if governing != "25":
        raise ValueError(
            "role routes FAR-25/CS-25 transport work; %r certifies under "
            "Part %s" % (aircraft_type, governing)
        )
    if jurisdiction not in ("FAA", "EASA"):
        raise ValueError("jurisdiction must be FAA or EASA, got %r" % (jurisdiction,))
    return "FAR-25" if jurisdiction == "FAA" else "CS-25"


# ---------------------------------------------------------------------------
# Compliance matrix builder: produces the actual deliverable content
# ---------------------------------------------------------------------------


@dataclass
class AirworthinessItem:
    """Project facts the role needs to build the compliance matrix."""
    item_name: str
    description: str = ""
    aircraft_type: str = "transport"
    jurisdiction: str = "FAA"
    certification_path: str = "STC"  # type certificate / STC / amended TC / TSO
    regulation_ids: list = field(default_factory=list)
    change_scope: list = field(default_factory=list)  # areas the change touches
    severity_overrides: dict = field(default_factory=dict)
    novel_regs: list = field(default_factory=list)
    special_conditions: list = field(default_factory=list)   # list[str]
    elos_items: list = field(default_factory=list)           # list[str]

    def basis(self) -> str:
        return basis_name(self.aircraft_type, self.jurisdiction)


def compliance_row(reg, item: AirworthinessItem) -> dict:
    """Build one matrix row: reg -> applicability -> MoC -> document ->
    proposed status."""
    number = reg_number(reg)
    if number not in REGS:
        raise ValueError(
            "unknown regulation %r - not in the role's FAR-25 register"
            % (number,)
        )
    record = REGS[number]
    verdict = determine_applicability(
        number, item.aircraft_type, change_scope=item.change_scope or None
    )
    severity = item.severity_overrides.get(number, record["severity"])
    novel = number in (item.novel_regs or [])
    moc = select_moc(number, item.basis(), severity=severity, novel=novel)
    dal = moc["dal"]
    if not verdict["applicable"]:
        return {
            "reg": number,
            "title": record["title"],
            "subpart": record["subpart"],
            "area": record["area"],
            "applicable": False,
            "reason": verdict["reason"],
            "item_kind": record["item_kind"],
            "severity": severity,
            "dal": dal,
            "moc_ids": [],
            "methods": [],
            "moc_display": "not applicable - screened out",
            "safety_assessment": False,
            "compliance_document": "not required (not applicable)",
            "status": STATUS_PROPOSED,
            "owner": "-",
        }
    return {
        "reg": number,
        "title": record["title"],
        "subpart": record["subpart"],
        "area": record["area"],
        "applicable": True,
        "reason": verdict["reason"],
        "item_kind": record["item_kind"],
        "severity": severity,
        "dal": dal,
        "moc_ids": moc["moc_ids"],
        "methods": moc["methods"],
        "moc_display": moc["moc_display"],
        "safety_assessment": moc["safety_assessment"],
        "compliance_document": record["compliance_document"],
        "status": STATUS_PROPOSED,
        "owner": AREA_OWNER.get(record["area"], "compliance engineer"),
    }


def _row_matches_item(row: dict, item: AirworthinessItem) -> bool:
    """Gate helper: is the row's applicability determination consistent
    with the item scope? (all rows built from the same item are)."""
    if row["reg"] not in REGS:
        return False
    return True


def build_matrix(item: AirworthinessItem) -> dict:
    """Build the full compliance matrix content model."""
    rows = [compliance_row(r, item) for r in item.regulation_ids]
    applicable = [r for r in rows if r["applicable"]]
    covered = [r for r in applicable if r["methods"] and r["compliance_document"]]
    coverage = (len(covered) / len(applicable)) if applicable else 0.0
    issues = [
        "%s: no accepted means of compliance yet" % r["reg"]
        for r in applicable
        if not r["methods"]
    ]
    special = item.special_conditions or []
    elos = item.elos_items or []
    return {
        "document_type": "Airworthiness compliance checklist / certification matrix",
        "status": "draft-for-review",
        "item": item.item_name,
        "item_description": item.description,
        "aircraft_type": item.aircraft_type,
        "jurisdiction": item.jurisdiction,
        "certification_basis": item.basis(),
        "certification_path": item.certification_path,
        "special_conditions": special,
        "elos_items": elos,
        "rows": rows,
        "applicable_count": len(applicable),
        "row_count": len(rows),
        "coverage": coverage,
        "issues": issues,
        "generated": date.today().isoformat(),
    }


def render_matrix_markdown(model: dict) -> str:
    """Render the compliance matrix content model as markdown."""
    basis = model["certification_basis"]
    regs_applicable = ", ".join(
        r["reg"] for r in model["rows"] if r["applicable"]
    ) or "none"
    sc = ", ".join(model["special_conditions"]) or "none identified"
    elos = ", ".join(model["elos_items"]) or "none proposed"
    lines = [
        "# Airworthiness Compliance Matrix",
        "",
        f"**Item:** {model['item']}",
        f"**Aircraft type:** {model['aircraft_type']} (jurisdiction "
        f"{model['jurisdiction']})",
        f"**Certification basis:** {basis}",
        f"**Certification path:** {model['certification_path']}",
        f"**Applicable regulations (proposed):** {regs_applicable}",
        f"**Special conditions:** {sc}",
        f"**Equivalent level of safety (ELOS) findings:** {elos}",
        f"**Status:** {model['status']}",
        f"**Coverage:** {model['coverage']:.0%} of applicable regulations "
        "have a proposed means of compliance and compliance document",
        "",
        "## Certification basis",
        "",
        f"- Aircraft/system: {model['item']}",
        f"- Certification basis reference (TC/STC/amendment level): "
        f"{basis}, {model['certification_path']}",
        f"- Applicable regulations (list with amendment): "
        f"{regs_applicable} (amendment level per the basis)",
        f"- Special conditions: {sc}",
        f"- Equivalent level of safety findings: {elos}",
        "",
        "## Compliance matrix",
        "",
        "| Reg | Applicable? | Means of compliance | Compliance document | "
        "Status (proposed/open) | Owner |",
        "|---|---|---|---|---|---|",
    ]
    for row in model["rows"]:
        reg_cell = "%s (Subpart %s - %s)" % (
            row["reg"], row["subpart"], SUBPARTS[row["subpart"]]
        )
        if row["applicable"]:
            app_cell = "YES"
            moc_cell = row["moc_display"]
            if row["safety_assessment"]:
                moc_cell += " (safety assessment required)"
            doc_cell = row["compliance_document"]
            dal_cell = "proposed (severity %s / DAL %s)" % (
                row["severity"], row["dal"]
            )
            owner_cell = row["owner"]
        else:
            app_cell = "NO"
            moc_cell = "n/a"
            doc_cell = "not required (screened out: %s)" % row["reason"]
            dal_cell = "proposed (n/a)"
            owner_cell = row["owner"]
        lines.append(
            "| %s | %s | %s | %s | %s | %s |"
            % (reg_cell, app_cell, moc_cell, doc_cell, dal_cell, owner_cell)
        )
    lines += [
        "",
        "## Notes",
        "",
        "- Status vocabulary: proposed | open | in-work | evidence-available.",
        "- Every row above is a PROPOSED determination by the compliance "
        "engineer (this role). The certification authority makes the binding "
        "applicability and compliance findings.",
        "- NEVER mark a row \"compliant/found\" without evidence - that is "
        "the authority's finding, not ours.",
        "- Severity and DAL context are proposed inputs to the 25.1309 "
        "safety assessment, subject to the system safety process.",
        "",
        "## Open items (gap report)",
        "",
    ]
    if model["issues"]:
        lines += ["- " + issue for issue in model["issues"]]
    else:
        lines.append("- No open gaps in this draft; confirm every row with "
                     "the certification authority before submission.")
    lines += [
        "",
        "---",
        f"*Generated by Aero Agent Roles airworthiness-compliance-engineer "
        f"core ({model['generated']}). DRAFT - for human compliance engineer "
        "review. Not a compliance finding or an approval.*",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evidence gate checkers: verify a deliverable meets the role's gates
# ---------------------------------------------------------------------------

GATE_CHECKS = {
    "basis_identified": "certification basis (FAR-25/CS-25) is identified",
    "rows_present": "at least one matrix row exists",
    "regs_real": "every row references a real FAR-25 paragraph",
    "all_applicable_have_moc": "every applicable row has a means of compliance",
    "all_applicable_have_doc": "every applicable row has a compliance document",
    "moc_vocabulary_valid": "means of compliance use the real vocabulary",
    "statuses_honest": "no row claims a compliant/found finding",
    "sign_off_honest": "document is marked draft-for-review, not approval",
}


def check_matrix(model: dict) -> dict:
    """Run the evidence gates against a compliance matrix model."""
    rows = model.get("rows", [])
    applicable = [r for r in rows if r.get("applicable")]
    results = {
        "basis_identified": bool(model.get("certification_basis")),
        "rows_present": bool(rows),
        "regs_real": all(
            r.get("reg") in REGS and r.get("reg") in _REAL_POOL
            for r in rows
        ),
        "all_applicable_have_moc": all(
            bool(r.get("methods")) for r in applicable
        ),
        "all_applicable_have_doc": all(
            bool(r.get("compliance_document")) for r in applicable
        ),
        "moc_vocabulary_valid": all(
            methods_are_valid(r["methods"]) for r in applicable
        ),
        "statuses_honest": all(
            (r.get("status") or "").lower() not in FORBIDDEN_STATUS
            for r in rows
        ),
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


# All real paragraphs any reg row may reference (routing check pool).
_REAL_POOL = [p for area in AREA_PARAGRAPHS.values() for p in area]


def check_matrix_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    has_reg = bool(re.search(r"\b25\.\d{3,4}\b", md_text))
    checks = {
        "has_title": "airworthiness compliance matrix" in low,
        "has_basis": "certification basis" in low,
        "has_reg_numbers": has_reg,
        "has_table_header": ("| reg |" in low and "means of compliance" in low),
        "has_status_word": "proposed" in low,
        "no_blank_fields": "___" not in md_text,
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not a compliance finding or an approval" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling: check a matrix document."""
    return check_matrix_markdown(md_text)


# ---------------------------------------------------------------------------
# Example project (for tests and worked-example generation)
# ---------------------------------------------------------------------------


def example_item() -> AirworthinessItem:
    return AirworthinessItem(
        item_name="Autopilot flight guidance system retrofit (STC)",
        description="Supplemental type certificate for a digital autopilot / "
                    "flight guidance system on a transport-category airplane: "
                    "autopilot computer, mode selector, servo actuators on "
                    "the flight controls, and annunciators. The change is a "
                    "major change by someone other than the type certificate "
                    "holder, so it takes the supplemental type certificate "
                    "(STC) path against the existing FAR-25 basis. The STC "
                    "delta touches the systems, flight-controls and equipment "
                    "areas; no primary structure is modified.",
        aircraft_type="transport",
        jurisdiction="FAA",
        certification_path="STC",
        change_scope=["systems", "flight-controls", "equipment"],
        regulation_ids=[
            # applicable to the STC delta:
            "25.1301", "25.1309", "25.1329", "25.671", "25.683",
            # screened-out candidates that exercise the applicability logic:
            "25.301", "25.571", "25.607",
        ],
        severity_overrides={},      # use the register context severities
        novel_regs=["25.1329"],     # new flight guidance feature on the type
        special_conditions=[],
        elos_items=[],
    )


def example_matrix_markdown() -> str:
    return render_matrix_markdown(build_matrix(example_item()))


if __name__ == "__main__":
    item = example_item()
    model = build_matrix(item)
    md = render_matrix_markdown(model)
    print("CERTIFICATION BASIS: %s" % model["certification_basis"])
    print("APPLICABLE REGS: %d/%d" % (model["applicable_count"], model["row_count"]))
    print("COVERAGE: %.2f" % model["coverage"])
    print("GATES: %s" % check_matrix(model))
    print("RENDERED: %d chars" % len(md))
