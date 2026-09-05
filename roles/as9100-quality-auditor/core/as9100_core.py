#!/usr/bin/env python3
"""as9100_core.py - AS9100 Quality / Internal Auditor executable core.

This is the role's ENGINE: given a supplier audit's facts (scope,
schedule facts, record population, and the observed issues), it
classifies each nonconformity on the audit finding ladder, sizes the
record sample, computes the audit due date from the risk category,
scores each corrective-action response against the closure chain, and
BUILDS the findings report deliverable. It also gate-checks
deliverables. Standalone: no external repo needed.

Domain rules encoded here are paraphrased from the bound AeroSkills
leaves (manufacturing-quality/as9100/*), which encode AS9100D audit
practice: the finding ladder (internal-quality-audit), the corrective
action chain (corrective-action), nonconformance disposition
discipline (nonconformance-control), calibration practice (7.1.5),
and the audit focus -> clause mapping (quality). AS9100D text is never
reproduced - clause ids are identifiers and the report structure is an
original synthesis of public QMS-audit practice (ISO 19011-style
evidence discipline).
"""
from __future__ import annotations

import calendar
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime

# ---------------------------------------------------------------------------
# Domain tables (paraphrased leaf rules, summary-not-copy)
# ---------------------------------------------------------------------------

# AS9100D inherits the ISO 9001:2015 clause structure: sections 4-10 with
# aerospace additions inside them. Section names are the public ISO 9001
# structure; clause ids below are the leaf-verified AS9100D ids the audit
# criteria cite.
AS9100D_SECTIONS = [
    ("4", "Context of the organization"),
    ("5", "Leadership"),
    ("6", "Planning"),
    ("7", "Support"),
    ("8", "Operation"),
    ("9", "Performance evaluation"),
    ("10", "Improvement"),
]

# Clause ids the audit criteria may cite, with the focus each leaf maps to
# the clause. Only leaf-verified AS9100D clause ids are listed.
CLAUSE_BY_ID = {
    "6.1": "risks and opportunities",
    "7.1.5": "monitoring and measuring resources (calibration)",
    "8.1.1": "operational risk management",
    "8.1.2": "configuration management",
    "8.1.3": "product safety",
    "8.1.4": "counterfeit parts prevention",
    "8.2": "requirements for products and services (order review)",
    "8.4": "control of externally provided processes, products and services",
    "8.5.1": "control of production and service provision",
    "8.5.1.3": "control of special processes",
    "8.6": "release of products and services",
    "8.7": "control of nonconforming outputs",
    "10.2": "nonconformity and corrective action",
}

# Finding classifications used in audit reporting. The audit leaf's ladder
# returns major/minor/ofi (ofi = opportunity for improvement); audit report
# practice labels the ofi grade "observation".
NC_CLASSIFICATIONS = ("major", "minor", "observation")

# Corrective action closure chain, ordered; each stage gates the next
# (paraphrase of the corrective-action leaf STAGES tuple).
CA_STAGES = ("containment", "root-cause", "corrective-action", "effectiveness")

# Placeholder answers that do not count as a recorded action (leaf rule).
NON_ANSWERS = frozenset(("", "none", "n/a", "na", "no", "unknown",
                         "not-applicable"))

# Root cause analysis needs at least this many distinct "why" levels.
MIN_WHY_DEPTH = 3

# Audit program mechanics (leaf rules): a 12-month base interval scaled by
# process risk, and a square-root record sample scaled by confidence.
BASE_INTERVAL_MONTHS = 12.0
RISK_MULTIPLIERS = {"low": 1.5, "medium": 1.0, "high": 0.5}
CONFIDENCE_ANCHORS = ((0.90, 0.8), (0.95, 1.0), (0.99, 1.2))


def clause_focus(clause_id: str) -> str:
    """Focus name for a known AS9100D clause id."""
    if clause_id not in CLAUSE_BY_ID:
        raise ValueError("unknown AS9100D clause id: %r" % (clause_id,))
    return CLAUSE_BY_ID[clause_id]


# ---------------------------------------------------------------------------
# NC classification ladder (internal-quality-audit leaf rule)
# ---------------------------------------------------------------------------

def classify_nc(severity_impact: int, systemic: bool, detection: bool) -> str:
    """Classify a nonconformity on the 1-5 impact severity scale.

    Ladder (leaf rule): "major" when severity impact >= 4 or when the
    condition escaped normal detection so containment of suspect output
    is required; "minor" when severity impact is 2-3, with systemic
    spread escalating minor to major; "observation" when severity impact
    is 1 (the leaf's opportunity for improvement, reported as an
    observation). Raises ValueError when severity_impact is outside 1-5.

    Args:
        severity_impact: impact of the nonconformity, integer 1-5.
        systemic: whether the same condition is found across other
            records, areas, or product lines.
        detection: whether the nonconformity escaped normal detection
            so containment of suspect output is required.
    """
    if not 1 <= severity_impact <= 5:
        raise ValueError("severity_impact must be an integer in 1-5")
    if severity_impact >= 4 or detection:
        return "major"
    if severity_impact >= 2:
        return "major" if systemic else "minor"
    return "observation"


def nc_classification_reason(severity_impact: int, systemic: bool,
                             detection: bool) -> str:
    """One-line rationale for a classification (leaf ladder rules)."""
    cls = classify_nc(severity_impact, systemic, detection)
    if severity_impact >= 4:
        return ("severity impact %d is 4-5, which is a major "
                "nonconformity" % severity_impact)
    if detection:
        return ("the condition escaped normal detection and containment "
                "of suspect output is required, which is a major "
                "nonconformity")
    if severity_impact >= 2 and systemic:
        return ("severity impact %d with systemic spread, which escalates "
                "a minor to a major nonconformity" % severity_impact)
    if severity_impact >= 2:
        return ("severity impact %d is 2-3 with no systemic spread, "
                "which is a minor nonconformity" % severity_impact)
    return ("severity impact 1 is an opportunity for improvement, "
            "reported as an observation")


# ---------------------------------------------------------------------------
# Corrective action closure chain (corrective-action leaf rules)
# ---------------------------------------------------------------------------

def _clean(text) -> str:
    return (text or "").strip()


def _is_non_answer(text: str) -> bool:
    return not text or text.lower() in NON_ANSWERS


def containment_ok(containment) -> bool:
    """Containment is recorded and not a placeholder (leaf rule)."""
    return not _is_non_answer(_clean(containment))


def root_cause_chain_ok(whys, min_depth: int = MIN_WHY_DEPTH) -> bool:
    """Root cause chain is long enough and every level is distinct."""
    if not isinstance(whys, (list, tuple)):
        return False
    chain = [_clean(w) for w in whys]
    if len(chain) < min_depth:
        return False
    prev = None
    for w in chain:
        if _is_non_answer(w):
            return False
        if prev is not None and w.lower() == prev.lower():
            return False
        prev = w
    return True


def corrective_action_ok(action) -> bool:
    """Corrective action is recorded and not a placeholder (leaf rule)."""
    return not _is_non_answer(_clean(action))


def effectiveness_evidence_ok(evidence, root_cause_statement=None) -> bool:
    """Effectiveness evidence exists and is not circular (does not simply
    restate the root cause)."""
    e = _clean(evidence)
    if _is_non_answer(e):
        return False
    rc = _clean(root_cause_statement)
    return not (rc and e.lower() == rc.lower())


def corrective_action_status(record: dict) -> str:
    """Closure stage of a corrective action record (leaf rule).

    Returns one of: containment-missing, root-cause-incomplete,
    corrective-action-missing, effectiveness-pending, closed. Raises
    ValueError for a non-dict record or a missing required key.
    """
    if not isinstance(record, dict):
        raise ValueError("record must be a dict, got %r" % (record,))
    for key in ("problem", "containment", "whys", "corrective_action"):
        if key not in record:
            raise ValueError("record missing required key: %s" % key)
    if not containment_ok(record.get("containment")):
        return "containment-missing"
    if not root_cause_chain_ok(record.get("whys")):
        return "root-cause-incomplete"
    if not corrective_action_ok(record.get("corrective_action")):
        return "corrective-action-missing"
    if not effectiveness_evidence_ok(
            record.get("effectiveness_evidence"),
            record.get("root_cause_statement")):
        return "effectiveness-pending"
    return "closed"


def verify_closure(corrective_action_taken, root_cause_stated,
                   effectiveness_check) -> bool:
    """True only when all three closure evidence elements are set."""
    return bool(corrective_action_taken and root_cause_stated
                and effectiveness_check)


# ---------------------------------------------------------------------------
# Audit program numbers (internal-quality-audit leaf rules)
# ---------------------------------------------------------------------------

def _add_calendar_months(day: date, total_months: int) -> date:
    """Add whole calendar months, clamping the day to the month end."""
    month_index = day.year * 12 + (day.month - 1) + total_months
    year, zero_month = divmod(month_index, 12)
    month = zero_month + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last_day))


def audit_due_date(last_audit_date_iso: str, risk_category: str,
                   base_interval_months: float = BASE_INTERVAL_MONTHS) -> str:
    """Due date of the next audit as an ISO date string.

    The span is base_interval_months times the risk multiplier for the
    process risk category (high risk processes are audited more often),
    added as calendar months with the day clamped to the target month
    end. Raises ValueError for a malformed date or unknown category.
    """
    if risk_category not in RISK_MULTIPLIERS:
        raise ValueError("risk_category must be one of: low, medium, high")
    try:
        last_date = datetime.strptime(last_audit_date_iso,
                                      "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValueError("last_audit_date_iso must be an ISO date "
                         "string YYYY-MM-DD") from None
    span = base_interval_months * RISK_MULTIPLIERS[risk_category]
    return _add_calendar_months(last_date, int(round(span))).isoformat()


def _confidence_factor(confidence_level: float) -> float:
    """Sample factor at the confidence anchors, interpolated between."""
    for anchor, factor in CONFIDENCE_ANCHORS:
        if confidence_level == anchor:
            return factor
    if confidence_level <= 0.90:
        return 0.8
    if confidence_level <= 0.95:
        factor = 0.8 + (confidence_level - 0.90) * 4.0
    elif confidence_level <= 0.99:
        factor = 1.0 + (confidence_level - 0.95) * 5.0
    else:
        factor = 1.2
    return round(factor, 9)


def audit_sample_size(lot_size: int, confidence_level: float = 0.95) -> int:
    """Sample size for a records audit: ceil(sqrt(lot_size) * factor).

    Square-root sample scaled by the confidence factor (1.0 at 0.95,
    0.8 at 0.90, 1.2 at 0.99, interpolated between) and rounded up,
    with a floor of 1. Raises ValueError for lot_size below 1 or a
    confidence level outside [0.5, 0.999].
    """
    if lot_size < 1:
        raise ValueError("lot_size must be at least 1")
    if not 0.5 <= confidence_level <= 0.999:
        raise ValueError("confidence_level must be within [0.5, 0.999]")
    factor = _confidence_factor(confidence_level)
    size = math.ceil(round(math.sqrt(lot_size) * factor, 9))
    return max(1, size)


# ---------------------------------------------------------------------------
# Audit item + findings model
# ---------------------------------------------------------------------------

@dataclass
class AuditItem:
    """Project facts the role needs to build the findings report.

    issues is a list of observed nonconformities, each a dict with:
      clause (AS9100D id), title, objective_evidence, requirement,
      severity_impact (1-5), systemic (bool), detection (bool), and
      corrective_action (dict with problem, containment, whys,
      corrective_action, effectiveness_evidence, root_cause_statement)
      - observations carry no corrective_action entry.
    """
    supplier_name: str
    audited_processes: list = field(default_factory=list)
    audit_date: str = ""
    auditor: str = ""
    auditee_owner: str = ""            # area owner; independence is checked
    process_risk: str = "medium"
    record_population: int = 0
    confidence_level: float = 0.95
    criteria: list = field(default_factory=list)
    issues: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Findings model builder: produces the actual deliverable content
# ---------------------------------------------------------------------------

def _nc_id(index: int) -> str:
    return "NC-%02d" % index


def _classify_issues(item: AuditItem) -> list:
    """Classify every issue and attach its corrective action record."""
    findings = []
    for i, issue in enumerate(item.issues, start=1):
        clause = issue["clause"]
        if clause not in CLAUSE_BY_ID:
            raise ValueError("issue cites unknown AS9100D clause id: %r"
                             % (clause,))
        severity = issue["severity_impact"]
        systemic = bool(issue.get("systemic"))
        detection = bool(issue.get("detection"))
        classification = classify_nc(severity, systemic, detection)
        ca = issue.get("corrective_action")
        if ca is not None and not isinstance(ca, dict):
            raise ValueError("corrective_action for %s must be a dict "
                             "or None" % _nc_id(i))
        findings.append({
            "nc_id": _nc_id(i),
            "clause": clause,
            "title": issue["title"],
            "classification": classification,
            "classification_reason": nc_classification_reason(
                severity, systemic, detection),
            "severity_impact": severity,
            "systemic": systemic,
            "detection": detection,
            "objective_evidence": issue["objective_evidence"],
            "requirement": issue["requirement"],
            "corrective_action": ca,
        })
    return findings


def audit_findings(item: AuditItem) -> dict:
    """Build the complete findings-report content model from audit facts.

    Classifies each issue on the finding ladder, scores each corrective
    action record on the closure chain, sizes the record sample, and
    computes the next audit due date from the risk category.
    """
    findings = _classify_issues(item)
    counts = {"major": 0, "minor": 0, "observation": 0}
    for f in findings:
        counts[f["classification"]] += 1
    counts["total"] = len(findings)
    for f in findings:
        ca = f.get("corrective_action")
        f["ca_status"] = (corrective_action_status(ca) if ca
                          else "not-required")
    due = audit_due_date(item.audit_date, item.process_risk)
    sample = audit_sample_size(item.record_population,
                               item.confidence_level)
    return {
        "document_type": "AS9100 Internal Audit Findings Report",
        "status": "draft-for-review",
        "supplier": item.supplier_name,
        "audit": {
            "audit_date": item.audit_date,
            "auditor": item.auditor,
            "auditee_owner": item.auditee_owner,
            "auditor_independent": item.auditor.strip().lower()
                                    != item.auditee_owner.strip().lower(),
            "audited_processes": list(item.audited_processes),
            "criteria": list(item.criteria),
            "process_risk": item.process_risk,
            "next_audit_due": due,
        },
        "sampling": {
            "population": item.record_population,
            "confidence_level": item.confidence_level,
            "sample_size": sample,
            "sample_note": ("%d of %d records sampled at %.2f confidence "
                            "(square-root rule)"
                            % (sample, item.record_population,
                               item.confidence_level)),
        },
        "clauses_cited": sorted({f["clause"] for f in findings}),
        "findings": findings,
        "counts": counts,
        "closure_recommendation": (
            "PROPOSED - the QA manager signs audit closure; NC-01/02 "
            "effectiveness verification at the follow-up audit is "
            "required before any closure is recorded"),
        "generated": date.today().isoformat(),
    }


def build_findings(item: AuditItem) -> dict:
    """Synonym for audit_findings (build_ naming parity with the role
    pattern); the engine produces the identical content model."""
    return audit_findings(item)


def _table_cell(text) -> str:
    """Escape a cell for a markdown table (pipes and newlines)."""
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def nc_row(nc_id: str, clause: str, classification: str,
           objective_evidence: str, requirement: str) -> list:
    """One findings-table row as a list of cell strings."""
    return [_table_cell(nc_id), _table_cell(clause),
            _table_cell(classification), _table_cell(objective_evidence),
            _table_cell(requirement)]


def _ca_text(ca: dict, key: str) -> str:
    if not ca:
        return ""
    return _table_cell(ca.get(key, ""))


# ---------------------------------------------------------------------------
# Renderer: findings report markdown deliverable
# ---------------------------------------------------------------------------

def render_findings_markdown(model: dict) -> str:
    """Render the findings content model as the deliverable markdown."""
    a = model["audit"]
    s = model["sampling"]
    c = model["counts"]
    lines = [
        "# AS9100 Internal Audit Findings Report",
        "",
        f"**Supplier:** {model['supplier']}",
        f"**Audit date:** {a['audit_date']}",
        f"**Auditor:** {a['auditor']} "
        f"(independent of area owner {a['auditee_owner']}: "
        f"{'yes' if a['auditor_independent'] else 'NO - independence failure'})",
        f"**Status:** {model['status']}",
        "",
        "## Audit plan",
        "",
        "- Audit scope: " + ", ".join(a["audited_processes"]) + ".",
        "- Criteria: " + ", ".join(a["criteria"]) + ".",
        f"- Audit team: {a['auditor']} (lead auditor).",
        f"- Process risk category: {a['process_risk']}; next audit due "
        f"{a['next_audit_due']} (risk-scaled 12-month base interval).",
        f"- Records sampled: {s['sample_note']}.",
        "",
        "## Findings summary",
        "",
        f"- Major nonconformities: {c['major']}",
        f"- Minor nonconformities: {c['minor']}",
        f"- Observations (opportunities for improvement): {c['observation']}",
        f"- Total findings: {c['total']}",
        f"- AS9100D clauses cited: {', '.join(model['clauses_cited'])}.",
        "",
        "## Findings report",
        "",
        "### Nonconformities",
        "",
        "| NC ID | Clause | Classification | Objective evidence | Requirement |",
        "|---|---|---|---|---|",
    ]
    for f in model["findings"]:
        row = nc_row(f["nc_id"], f["clause"], f["classification"],
                     f["objective_evidence"], f["requirement"])
        lines.append("| " + " | ".join(row) + " |")
    lines += [
        "",
        "### Finding details",
        "",
    ]
    for f in model["findings"]:
        ca = f.get("corrective_action")
        lines += [
            f"#### {f['nc_id']} - {f['classification'].upper()} "
            f"(clause {f['clause']})",
            "",
            f"**Title:** {f['title']}",
            f"**Classification rationale:** {f['classification_reason']}.",
            f"**Objective evidence:** {f['objective_evidence']}",
            f"**Requirement violated:** {f['requirement']}",
        ]
        if ca:
            lines += [
                "",
                "Corrective-action record (closure chain status: "
                + f["ca_status"] + "):",
                f"- Containment: {ca.get('containment', '')}",
                f"- Root cause: {' > '.join(ca.get('whys', []))}",
                f"- Corrective action: {ca.get('corrective_action', '')}",
                f"- Effectiveness evidence: "
                f"{ca.get('effectiveness_evidence') or 'pending - not yet recorded'}",
            ]
        else:
            lines += [
                "",
                f"No corrective action required (observation, clause "
                f"{f['clause']}); improvement tracked separately.",
            ]
        lines.append("")
    lines += [
        "### Observations (no violation found, improvement note)",
        "",
    ]
    for f in model["findings"]:
        if f["classification"] == "observation":
            lines.append(
                f"- {f['nc_id']} (clause {f['clause']}): {f['title']}. "
                f"{f['objective_evidence']}")
    lines += [
        "",
        "### Corrective-action follow-up",
        "",
        "| NC ID | Root cause | Containment | Corrective action | Verification | Status |",
        "|---|---|---|---|---|---|",
    ]
    for f in model["findings"]:
        ca = f.get("corrective_action")
        if not ca:
            lines.append(
                "| " + f["nc_id"] + " | n/a - observation | n/a - "
                "observation | n/a - observation | n/a - observation | "
                "observation |")
            continue
        verification = (ca.get("effectiveness_evidence")
                        or "pending - effectiveness not yet verified")
        lines.append(
            "| " + f["nc_id"] + " | "
            + _ca_text(ca, "root_cause_statement") + " | "
            + _ca_text(ca, "containment") + " | "
            + _ca_text(ca, "corrective_action") + " | "
            + _table_cell(verification) + " | "
            + f["ca_status"] + " |")
    lines += [
        "",
        "## Closure",
        "",
        f"- Closure recommendation: {model['closure_recommendation']}.",
        f"- No finding is recorded closed: closure requires the corrective "
        f"action taken, the root cause statement and the effectiveness "
        f"check all on file (verification gate).",
        "",
        "---",
        f"*DRAFT - audit evidence report generated by Aero Agent Roles "
        f"as9100-quality-auditor core ({model['generated']}) for human QA "
        f"review. Not a certification, supplier-approval, or closure "
        f"decision; the QA manager signs closure.*",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evidence gate checkers: verify a deliverable meets the role's gates
# ---------------------------------------------------------------------------

def check_findings(model: dict) -> dict:
    """Run the evidence gates against a findings model."""
    audit = model.get("audit", {})
    findings = model.get("findings", [])
    major_minor = [f for f in findings
                   if f.get("classification") in ("major", "minor")]
    results = {
        "scope_identified": bool(model.get("supplier")) and bool(
            audit.get("audited_processes")),
        "criteria_stated": any("as9100" in str(x).lower()
                               for x in audit.get("criteria", [])),
        "clauses_real": all(f.get("clause") in CLAUSE_BY_ID
                            for f in findings),
        "nc_classified": all(f.get("classification") in NC_CLASSIFICATIONS
                             for f in findings),
        "evidence_present": all(
            f.get("clause") and f.get("objective_evidence")
            and f.get("requirement") for f in findings),
        "ca_chain_present": all(
            isinstance(f.get("corrective_action"), dict)
            and containment_ok(f["corrective_action"].get("containment"))
            and root_cause_chain_ok(f["corrective_action"].get("whys"))
            and corrective_action_ok(
                f["corrective_action"].get("corrective_action"))
            for f in major_minor),
        "no_closure_claimed": all(
            f.get("ca_status") != "closed" for f in findings),
        "closure_honest": "proposed" in str(
            model.get("closure_recommendation", "")).lower(),
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_findings_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    checks = {
        "has_title": "as9100 internal audit findings report" in low,
        "has_supplier": "**supplier:**" in low,
        "has_clause_refs": "clause" in low and "nc-01" in low,
        "has_classifications": all(k in low
                                   for k in ("major", "minor", "observation")),
        "has_evidence": "objective evidence" in low and "requirement" in low,
        "has_ca_chain": all(k in low for k in (
            "root cause", "containment", "corrective action", "verification")),
        "has_proposed_closure": "proposed" in low,
        "has_draft_marker": "draft" in low,
        "not_approval": "not a" in low and "approval" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling: check a findings report."""
    return check_findings_markdown(md_text)


# ---------------------------------------------------------------------------
# Example audit (for tests and worked-example generation)
# ---------------------------------------------------------------------------

def example_item() -> AuditItem:
    """Synthetic supplier audit: AeroForge Precision Machining, LLC.

    Five observed issues exercise the whole finding ladder: severity 5
    major (8.7), systemic minor escalated to major (10.2), two minors
    (7.1.5, 8.1.2), and one observation (6.1). All clause ids are
    leaf-verified AS9100D ids.
    """
    return AuditItem(
        supplier_name="AeroForge Precision Machining, LLC",
        audited_processes=[
            "CNC machining and production control (8.5.1)",
            "inspection and test (8.6)",
            "calibration control (7.1.5)",
            "nonconformance disposition (8.7)",
            "corrective action (10.2)",
        ],
        audit_date="2026-09-05",
        auditor="M. Reyes",
        auditee_owner="J. Torres",
        process_risk="high",
        record_population=400,
        confidence_level=0.95,
        criteria=[
            "AS9100D clauses (6.1, 7.1.5, 8.1.2, 8.6, 8.7, 10.2)",
            "customer requirements flow-down, PO-7712",
        ],
        issues=[
            {
                "clause": "8.7",
                "title": ("Use-as-is disposition on a safety-critical part "
                          "without customer approval"),
                "objective_evidence": ("NCR-2214: bracket P/N BN-4470-2 "
                    "(safety-critical, flight control linkage) dispositioned "
                    "use-as-is by the supplier MRB; no customer waiver on "
                    "file and the disposition record has no customer-approval "
                    "entry. Twelve brackets of the same lot shipped under "
                    "delivery DLV-3390."),
                "requirement": ("Nonconforming output must be identified, "
                    "segregated, and dispositioned by an authorized "
                    "authority; use-as-is outside the original specification "
                    "requires customer approval."),
                "severity_impact": 5,
                "systemic": True,
                "detection": True,
                "corrective_action": {
                    "problem": ("Use-as-is release of safety-critical "
                                "brackets without customer approval"),
                    "containment": ("Quarantine the twelve shipped brackets "
                                    "of lot 2214B at the customer site; "
                                    "suspend MRB use-as-is disposition "
                                    "until the procedure is corrected."),
                    "whys": [
                        "The MRB disposition procedure has no "
                        "customer-approval step for use-as-is",
                        "The procedure was written when the MRB handled "
                        "non-aerospace parts only",
                        "Customer approval flow was never added when the "
                        "aerospace order book opened",
                        "No checklist gate sits between the disposition "
                        "decision and product release",
                    ],
                    "corrective_action": ("Revise the disposition procedure "
                        "to require customer approval before any use-as-is "
                        "release and add a release checklist gate; retrain "
                        "the MRB board."),
                    "effectiveness_evidence": "",
                    "root_cause_statement": ("use-as-is release without "
                        "customer approval on safety-critical parts"),
                },
            },
            {
                "clause": "10.2",
                "title": ("Recurring nonconformity with no root cause or "
                          "effectiveness verification"),
                "objective_evidence": ("NCR-2210/2211/2214 record the same "
                    "oversize-bore characteristic within six months. CAPA-118 "
                    "was closed with effectiveness evidence restating the "
                    "root cause rather than an observed result."),
                "requirement": ("On nonconformity, the organization must "
                    "react, evaluate the need for action to eliminate the "
                    "cause so it does not recur, and verify the "
                    "effectiveness of the action taken."),
                "severity_impact": 3,
                "systemic": True,
                "detection": False,
                "corrective_action": {
                    "problem": ("Same oversize-bore characteristic recurs "
                                "across three NCRs in six months"),
                    "containment": ("100% bore inspection of the affected "
                                    "part numbers in stock and in work."),
                    "whys": [
                        "Tool wear compensation is not verified between "
                        "operator shifts",
                        "The compensation check is a manual step with no "
                        "scheduled trigger",
                        "The CNC program pauses at shift change but no "
                        "measurement is required before restart",
                    ],
                    "corrective_action": ("Add an in-process bore "
                        "measurement gate at every shift change, tied to "
                        "the SPC record for the characteristic."),
                    "effectiveness_evidence": "",
                    "root_cause_statement": ("oversize-bore recurrence from "
                        "unverified tool-wear compensation at shift change"),
                },
            },
            {
                "clause": "7.1.5",
                "title": ("Calibration sticker expired on a torque wrench "
                          "in the tool crib"),
                "objective_evidence": ("Torque wrench TQ-009 in the "
                    "assembly tool crib carried a calibration sticker due "
                    "2026-08-30; the crib sign-out log shows no issue "
                    "after the sticker expiry date."),
                "requirement": ("Monitoring and measuring resources must "
                    "be calibrated or verified at defined intervals; "
                    "suspect measurements must be assessed for validity."),
                "severity_impact": 2,
                "systemic": False,
                "detection": False,
                "corrective_action": {
                    "problem": ("Torque wrench TQ-009 remained in the "
                                "active tool crib after its calibration "
                                "interval expired"),
                    "containment": ("Remove TQ-009 to calibration; verify "
                                    "the sign-out log to bound the period "
                                    "of possible use."),
                    "whys": [
                        "No recall alert fired when the interval expired",
                        "Calibration due dates are tracked on a paper "
                        "log reviewed monthly",
                        "The monthly review ran two weeks late",
                    ],
                    "corrective_action": ("Move calibration due-date "
                        "tracking to the shop system with an automatic "
                        "recall alert at interval expiry."),
                    "effectiveness_evidence": "",
                    "root_cause_statement": ("expired calibration sticker "
                        "from a late monthly due-date review"),
                },
            },
            {
                "clause": "8.1.2",
                "title": ("Configuration baseline register not updated for "
                          "approved engineering change ECO-4821"),
                "objective_evidence": ("ECO-4821 (drawing BN-4470 rev A to "
                    "rev B) approved 2026-08-10; the configuration baseline "
                    "register entry for BN-4470 still shows rev A as of the "
                    "audit date. No nonconforming product resulted."),
                "requirement": ("Configuration management must establish "
                    "and maintain a configuration baseline and control "
                    "changes to it."),
                "severity_impact": 3,
                "systemic": False,
                "detection": False,
                "corrective_action": {
                    "problem": ("Configuration baseline register lagging "
                                "the approved ECO-4821"),
                    "containment": ("Update the baseline register for "
                                    "BN-4470 rev B; audit open ECOs against "
                                    "the register."),
                    "whys": [
                        "Baseline register updates are batched monthly",
                        "No trigger links ECO approval to the register "
                        "update",
                        "The register owner has no change-approval "
                        "notification",
                    ],
                    "corrective_action": ("Link ECO approval records to the "
                        "baseline register so approved changes update the "
                        "register at approval time."),
                    "effectiveness_evidence": "",
                    "root_cause_statement": ("baseline register updated "
                        "monthly instead of at ECO approval"),
                },
            },
            {
                "clause": "6.1",
                "title": ("Opportunity: risk register entries lack "
                          "post-mitigation residual scoring"),
                "objective_evidence": ("The operational risk register is "
                    "complete and current; mitigation actions for the "
                    "coating process change are recorded but no residual "
                    "RPN re-score follows the recorded reductions."),
                "requirement": ("No violation found; the register meets "
                    "clause 6.1. Re-scoring residual risk closes the "
                    "mitigation loop demonstrated elsewhere in the QMS."),
                "severity_impact": 1,
                "systemic": False,
                "detection": False,
                "corrective_action": None,
            },
        ],
    )


def example_findings_markdown() -> str:
    return render_findings_markdown(audit_findings(example_item()))


if __name__ == "__main__":
    item = example_item()
    model = audit_findings(item)
    md = render_findings_markdown(model)
    print("SUPPLIER: %s" % model["supplier"])
    print("SAMPLE SIZE: %d" % model["sampling"]["sample_size"])
    print("NEXT AUDIT DUE: %s" % model["audit"]["next_audit_due"])
    print("COUNTS: %s" % model["counts"])
    print("GATES: %s" % check_findings(model))
    print("RENDERED: %d chars" % len(md))
