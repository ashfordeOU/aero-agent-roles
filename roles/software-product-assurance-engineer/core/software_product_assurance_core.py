#!/usr/bin/env python3
"""software_product_assurance_core.py - the engine of the Software Product
Assurance Engineer role.

Turns a space project's software product assurance evidence into a
clause-by-clause compliance matrix against ECSS-Q-ST-80C Rev.2 (30 April
2025), and stops at a human sign-off. Standalone: stdlib only, no Aero
Agent Skills checkout needed. When the skills library is present the role
CLI dispatches the bound q80 leaves and cross-checks this engine against
them (a second, independent implementation of the same rules).

What the engine does
--------------------
1. Software criticality category: taken as given (A to D) or derived from
   the highest severity of the functions the software serves (I to IV)
   and the compensating provisions at system level.
2. Tailoring: every requirement of the standard resolved for the category
   (applicable, reduced, not applicable; the security clauses follow the
   security sensitivity instead of the category).
3. Compliance matrix: the clause list joined to the evidence index
   (clause, document, section, status, justification). One row per
   clause; several evidence rows combine to the weakest status; silence
   is never compliance; a claim with no document reference is downgraded;
   a not-applicable claim the tailoring keeps is a gap.
4. Document trace: every document the evidence cites is looked up in the
   project's document folder; a citation that resolves to no file is a
   gap, and a compliant claim that rests only on missing files is
   downgraded, so every clause traces to a real file.
5. Milestone evidence: the documents a review (SRR, PDR, CDR, QR, AR...)
   owes for the category and scope, each with the clauses that drive it
   and the state of their evidence; a submitted review pack graded for
   missing and immature items; the SPAP maturity owed; the milestone
   report (SPAMR) skeleton with the sections the evidence can fill.
6. Product metrics: a measurement set graded against the category
   thresholds (illustrative defaults; the project's agreed values win).
7. Gates: the deliverable is checked for its DRAFT status, the stop line,
   one row per clause, a coverage summary that matches the rows, and an
   honest sign-off state. The engine never marks a matrix approved.

The standard is referenced, never reproduced: clause identifiers are
factual identifiers, and every topic label and rule below is our own
paraphrase. Author: ashfordeOU.
"""
from __future__ import annotations

import csv
import io
import os
import re

__version__ = "0.1.0"

STANDARD = "ECSS-Q-ST-80C Rev.2 (30 April 2025)"
TITLE = ("Software Product Assurance Compliance Matrix "
         "(ECSS-Q-ST-80C Rev.2)")

CATEGORIES = ("A", "B", "C", "D")
SEVERITIES = ("I", "II", "III", "IV")
STATUSES = ("compliant", "partially-compliant", "not-compliant",
            "not-applicable")
REVIEWS = ("srr", "pdr", "cdr", "trr", "qr", "ar", "orr")
REVIEW_NAMES = {
    "srr": "system requirements review (SRR)",
    "pdr": "preliminary design review (PDR)",
    "cdr": "critical design review (CDR)",
    "trr": "test readiness review (TRR)",
    "qr": "qualification review (QR)",
    "ar": "acceptance review (AR)",
    "orr": "operational readiness review (ORR)",
}
SCOPE_FLAGS = ("suppliers", "procured", "reuse", "security", "operations")
PROVISION_KINDS = ("hardware", "software", "operational-procedure")

DRAFT_BANNER = ("DRAFT - prepared by an agent for review. Not a statement of "
                "compliance until signed off by the responsible human.")
STOP_LINE = "STOP: human sign-off required before submission."
NOT_SIGNED = "Sign-off: none recorded."

# Sign-off block a HUMAN appends to the Markdown matrix (never the engine).
SIGN_OFF_KEYS = ("Signed-off-by", "Sign-off-role", "Sign-off-date",
                 "Sign-off-decision", "Accepted-open-gaps")

STATUS_ALIASES = {
    "c": "compliant", "compliant": "compliant", "yes": "compliant",
    "y": "compliant", "full": "compliant", "fc": "compliant",
    "pc": "partially-compliant", "partial": "partially-compliant",
    "partially": "partially-compliant",
    "partially compliant": "partially-compliant",
    "partially-compliant": "partially-compliant",
    "nc": "not-compliant", "no": "not-compliant", "n": "not-compliant",
    "not compliant": "not-compliant", "not-compliant": "not-compliant",
    "non-compliant": "not-compliant", "noncompliant": "not-compliant",
    "na": "not-applicable", "n/a": "not-applicable",
    "not applicable": "not-applicable", "not-applicable": "not-applicable",
}

_SEVERITY_ALIASES = {
    "1": "I", "2": "II", "3": "III", "4": "IV",
    "i": "I", "ii": "II", "iii": "III", "iv": "IV",
    "catastrophic": "I", "critical": "II", "major": "III",
    "minor": "IV", "negligible": "IV",
}

_PROVISION_ALIASES = {
    "hw": "hardware", "hardware": "hardware",
    "sw": "software", "software": "software",
    "procedure": "operational-procedure",
    "operational": "operational-procedure",
    "operational-procedure": "operational-procedure",
    "ops-procedure": "operational-procedure",
}

_REVIEW_ALIASES = {
    "system-requirements-review": "srr",
    "preliminary-design-review": "pdr",
    "critical-design-review": "cdr",
    "test-readiness-review": "trr",
    "qualification-review": "qr",
    "acceptance-review": "ar",
    "operational-readiness-review": "orr",
}

# Plan (SPAP) maturity owed at each review (Annex B practice, paraphrased).
PLAN_MATURITY_BY_REVIEW = {
    "srr": "issued", "pdr": "updated", "cdr": "updated",
    "qr": "maintained", "ar": "maintained", "orr": "maintained",
}

_MATURITY = {"draft": 0, "issued": 1, "approved": 2}

# Which clause groups feed each input of the milestone report skeleton.
# A SPAMR input counts as available when at least one applicable clause of
# its groups carries evidence that resolves to a real document.
SPAMR_INPUT_CLAUSES = {
    "verification_activities": ("6.2.6",),
    "methods_tools": ("5.6",),
    "standards_adherence": ("6.3.3", "6.3.4"),
    "metrics": ("7.1", "6.2.5"),
    "testing": ("6.3.5",),
    "problems": ("5.2.5", "5.2.6"),
    "progress_reports": ("5.2.2",),
}

# Where a gap goes next: the bound skill that resolves it.
_LEAF = "space-systems/ecss/"
GAP_ROUTES_BY_KIND = {
    "na-conflicts-with-tailoring": _LEAF + "q80-software-criticality-tailoring",
    "evidence-for-tailored-out-clause": _LEAF + "q80-software-criticality-tailoring",
    "evidence-for-unlisted-clause": _LEAF + "q80-compliance-matrix",
    "conflicting-status": _LEAF + "q80-compliance-matrix",
}
GAP_ROUTES_BY_CLAUSE = (
    ("7.1.", _LEAF + "q80-software-product-quality-metrics"),
    ("7.4.", _LEAF + "q80-software-product-assurance-plan"),
    ("7.5.", _LEAF + "q80-software-product-assurance-plan"),
    ("5.", _LEAF + "q80-software-product-assurance-plan"),
    ("6.", _LEAF + "q80-software-process-assurance"),
    ("7.", _LEAF + "q80-software-process-assurance"),
)

TOLERANCE = 1e-9

# ---------------------------------------------------------------------------
# Clause and applicability data. Derived from the clause structure of the
# standard: identifiers are facts; the topic labels are our own wording and
# no requirement or heading text is reproduced. Applicability codes per
# requirement in category order A B C D: Y applicable, N not applicable,
# R reduced, S set by security sensitivity. Default YYYY.
# ---------------------------------------------------------------------------

TOPICS = {'5': 'assurance programme',
 '5.1': 'organisation',
 '5.1.1': 'assurance organisation set-up',
 '5.1.2': 'who answers for what',
 '5.1.3': 'staff and means',
 '5.1.4': 'the assurance lead',
 '5.1.5': 'skills and training',
 '5.2': 'programme management',
 '5.2.1': 'planning and control of the programme',
 '5.2.2': 'assurance reporting',
 '5.2.3': 'audit programme',
 '5.2.4': 'alert handling',
 '5.2.5': 'problem reporting',
 '5.2.6': 'nonconformance handling',
 '5.2.7': 'quality model',
 '5.3': 'risks and critical items',
 '5.3.1': 'risk handling',
 '5.3.2': 'critical items',
 '5.4': 'suppliers',
 '5.4.1': 'choosing suppliers',
 '5.4.2': 'what suppliers are held to',
 '5.4.3': 'watching suppliers',
 '5.4.4': 'category flow-down to suppliers',
 '5.4.5': 'security flow-down to suppliers',
 '5.5': 'buying software',
 '5.5.1': 'purchase documents',
 '5.5.2': 'bought-in component list',
 '5.5.3': 'purchase data',
 '5.5.4': 'marking of bought items',
 '5.5.5': 'incoming checks',
 '5.5.6': 'export constraints',
 '5.6': 'tools and environment',
 '5.6.1': 'methods and tools chosen',
 '5.6.2': 'choice of development environment',
 '5.7': 'process capability',
 '5.7.1': 'capability assessment',
 '5.7.2': 'how assessments are run',
 '5.7.3': 'improving the process',
 '6': 'process assurance',
 '6.1': 'life cycle',
 '6.1.1': 'defining the life cycle',
 '6.1.2': 'process targets',
 '6.1.3': 'reviewing the life cycle',
 '6.1.4': 'means for the life cycle',
 '6.1.5': 'validation timing',
 '6.2': 'cross-process obligations',
 '6.2.1': 'process documentation',
 '6.2.2': 'dependability and safety of software',
 '6.2.3': 'critical software',
 '6.2.4': 'configuration management',
 '6.2.5': 'process measurement',
 '6.2.6': 'verification',
 '6.2.7': 'reusing existing software',
 '6.2.8': 'generated code',
 '6.2.9': 'security',
 '6.2.10': 'security-sensitive software',
 '6.3': 'per-process obligations',
 '6.3.1': 'system-level software requirements',
 '6.3.2': 'requirements analysis',
 '6.3.3': 'architecture and design',
 '6.3.4': 'coding',
 '6.3.5': 'testing and validation',
 '6.3.6': 'delivery and installation',
 '6.3.7': 'acceptance',
 '6.3.8': 'operations',
 '6.3.9': 'maintenance',
 '7': 'product quality assurance',
 '7.1': 'quality targets and measurement',
 '7.1.1': 'deriving quality requirements',
 '7.1.2': 'quality requirements as numbers',
 '7.1.3': 'checking quality requirements',
 '7.1.4': 'product measures',
 '7.1.5': 'basic measures',
 '7.1.6': 'reporting measures',
 '7.1.7': 'numerical accuracy',
 '7.1.8': 'maturity analysis',
 '7.2': 'product quality obligations',
 '7.2.1': 'requirement documents',
 '7.2.2': 'design documents',
 '7.2.3': 'test and validation documents',
 '7.3': 'software built for reuse',
 '7.3.1': 'what the customer asks for',
 '7.3.2': 'own documentation set',
 '7.3.3': 'standalone information',
 '7.3.4': 'reuse requirements',
 '7.3.5': 'configuration of reusable items',
 '7.3.6': 'multi-platform testing',
 '7.3.7': 'conformance certificate',
 '7.4': 'ground hardware and services',
 '7.4.1': 'buying ground hardware',
 '7.4.2': 'buying services',
 '7.4.3': 'limits',
 '7.4.4': 'choice',
 '7.4.5': 'upkeep',
 '7.5': 'programmable devices',
 '7.5.1': 'programming devices',
 '7.5.2': 'device marking',
 '7.5.3': 'device calibration'}

REQUIREMENT_IDS = (
    '5.1.1', '5.1.2.1', '5.1.2.2', '5.1.2.3', '5.1.3.1', '5.1.3.2', '5.1.4.1', '5.1.4.2',
    '5.1.5.1', '5.1.5.2', '5.1.5.3', '5.1.5.4', '5.2.1.1', '5.2.1.2', '5.2.1.3', '5.2.1.4',
    '5.2.1.5', '5.2.2.1', '5.2.2.2', '5.2.2.3', '5.2.3', '5.2.4', '5.2.5.1', '5.2.5.2',
    '5.2.5.3', '5.2.5.4', '5.2.6.1', '5.2.6.2', '5.2.7.1', '5.2.7.2', '5.3.1', '5.3.2.1',
    '5.3.2.2', '5.4.1.1', '5.4.1.2', '5.4.2.1', '5.4.2.2', '5.4.3.1', '5.4.3.2', '5.4.3.3',
    '5.4.3.4', '5.4.4', '5.4.5', '5.5.1', '5.5.2', '5.5.3', '5.5.4', '5.5.5',
    '5.5.6', '5.6.1.1', '5.6.1.2', '5.6.1.3', '5.6.2.1', '5.6.2.2', '5.6.2.3', '5.7.1',
    '5.7.2.1', '5.7.2.2', '5.7.2.3', '5.7.2.4', '5.7.3.1', '5.7.3.2', '5.7.3.3', '6.1.1',
    '6.1.2', '6.1.3', '6.1.4', '6.1.5', '6.2.1.1', '6.2.1.2', '6.2.1.3', '6.2.1.4',
    '6.2.1.5', '6.2.1.6', '6.2.1.7', '6.2.1.8', '6.2.1.9', '6.2.2.1', '6.2.2.2', '6.2.2.3',
    '6.2.2.4', '6.2.2.5', '6.2.2.6', '6.2.2.7', '6.2.2.8', '6.2.2.9', '6.2.2.10', '6.2.3.2',
    '6.2.3.3', '6.2.3.4', '6.2.3.5', '6.2.3.6', '6.2.3.7', '6.2.3.8', '6.2.4.1', '6.2.4.2',
    '6.2.4.3', '6.2.4.4', '6.2.4.5', '6.2.4.6', '6.2.4.7', '6.2.4.8', '6.2.4.9', '6.2.4.10',
    '6.2.4.11', '6.2.4.12', '6.2.5.1', '6.2.5.2', '6.2.5.3', '6.2.5.4', '6.2.5.5', '6.2.6.1',
    '6.2.6.2', '6.2.6.3', '6.2.6.4', '6.2.6.5', '6.2.6.6', '6.2.6.7', '6.2.6.8', '6.2.6.9',
    '6.2.6.10', '6.2.6.11', '6.2.6.12', '6.2.6.13', '6.2.7.1', '6.2.7.2', '6.2.7.3', '6.2.7.4',
    '6.2.7.5', '6.2.7.6', '6.2.7.7', '6.2.7.8', '6.2.7.9', '6.2.7.10', '6.2.7.11', '6.2.8.1',
    '6.2.8.2', '6.2.8.3', '6.2.8.4', '6.2.8.5', '6.2.8.6', '6.2.8.7', '6.2.9.1', '6.2.9.2',
    '6.2.9.3', '6.2.9.4', '6.2.9.5', '6.2.9.6', '6.2.9.7', '6.2.10.1', '6.2.10.2', '6.2.10.3',
    '6.2.10.4', '6.3.1.1', '6.3.1.2', '6.3.1.3', '6.3.2.1', '6.3.2.2', '6.3.2.3', '6.3.2.4',
    '6.3.2.5', '6.3.3.1', '6.3.3.2', '6.3.3.3', '6.3.3.4', '6.3.3.5', '6.3.3.6', '6.3.3.7',
    '6.3.4.1', '6.3.4.2', '6.3.4.3', '6.3.4.4', '6.3.4.5', '6.3.4.6', '6.3.4.7', '6.3.4.8',
    '6.3.5.1', '6.3.5.2', '6.3.5.3', '6.3.5.4', '6.3.5.5', '6.3.5.6', '6.3.5.7', '6.3.5.8',
    '6.3.5.9', '6.3.5.10', '6.3.5.11', '6.3.5.12', '6.3.5.13', '6.3.5.14', '6.3.5.15', '6.3.5.16',
    '6.3.5.17', '6.3.5.18', '6.3.5.19', '6.3.5.20', '6.3.5.21', '6.3.5.22', '6.3.5.23', '6.3.5.24',
    '6.3.5.25', '6.3.5.26', '6.3.5.27', '6.3.5.28', '6.3.5.29', '6.3.5.30', '6.3.5.31', '6.3.5.32',
    '6.3.5.33', '6.3.6.1', '6.3.6.2', '6.3.6.3', '6.3.6.4', '6.3.7.1', '6.3.7.2', '6.3.7.3',
    '6.3.7.5', '6.3.7.6', '6.3.7.7', '6.3.8.1', '6.3.8.2', '6.3.8.3', '6.3.9.1', '6.3.9.2',
    '6.3.9.3', '6.3.9.4', '6.3.9.5', '6.3.9.6', '6.3.9.7', '7.1.1', '7.1.2', '7.1.3',
    '7.1.4', '7.1.5', '7.1.6', '7.1.7', '7.1.8', '7.2.1.1', '7.2.1.2', '7.2.1.3',
    '7.2.2.1', '7.2.2.2', '7.2.2.3', '7.2.3.1', '7.2.3.2', '7.2.3.3', '7.2.3.4', '7.2.3.5',
    '7.2.3.6', '7.3.1', '7.3.2', '7.3.3', '7.3.4', '7.3.5', '7.3.6', '7.3.7',
    '7.4.1', '7.4.2', '7.4.3', '7.4.4', '7.4.5', '7.5.1', '7.5.2', '7.5.3',
)

APPLICABILITY = {'5.1.3.2': 'YYYN',
 '5.1.5.1': 'YYYR',
 '5.1.5.2': 'YYYN',
 '5.2.3': 'YYYR',
 '5.2.7.2': 'YYYR',
 '5.4.1.1': 'YYYR',
 '5.4.2.2': 'YYYN',
 '5.4.3.4': 'YYYN',
 '5.6.1.1': 'YYYR',
 '5.6.1.2': 'YYYR',
 '5.6.1.3': 'YYYR',
 '5.6.2.1': 'YYYR',
 '5.6.2.2': 'YYYR',
 '5.7.1': 'YYYN',
 '5.7.2.1': 'YYYN',
 '5.7.2.2': 'YYYN',
 '5.7.2.3': 'YYYN',
 '5.7.2.4': 'YYYN',
 '5.7.3.1': 'YYYN',
 '5.7.3.2': 'YYYN',
 '5.7.3.3': 'YYYN',
 '6.2.1.9': 'YYYN',
 '6.2.2.2': 'YYYN',
 '6.2.2.3': 'YYYN',
 '6.2.2.4': 'YYYN',
 '6.2.2.5': 'YYYN',
 '6.2.2.6': 'YYYN',
 '6.2.2.7': 'YYYN',
 '6.2.3.2': 'YYYN',
 '6.2.3.3': 'YYYN',
 '6.2.3.4': 'YYYN',
 '6.2.3.5': 'YYYN',
 '6.2.3.6': 'YYYN',
 '6.2.3.7': 'YYNN',
 '6.2.3.8': 'YYYN',
 '6.2.5.4': 'YYYR',
 '6.2.6.5': 'YYYN',
 '6.2.6.6': 'YYYN',
 '6.2.6.13': 'YYNN',
 '6.2.7.4': 'YYYR',
 '6.2.7.7': 'YYYR',
 '6.2.7.8': 'YYYR',
 '6.2.9.1': 'SSSS',
 '6.2.9.2': 'SSSS',
 '6.2.9.3': 'SSSS',
 '6.2.9.4': 'SSSS',
 '6.2.9.5': 'SSSS',
 '6.2.9.6': 'SSSS',
 '6.2.9.7': 'SSSS',
 '6.2.10.1': 'SSSS',
 '6.2.10.2': 'SSSS',
 '6.2.10.3': 'SSSS',
 '6.2.10.4': 'SSSS',
 '6.3.3.1': 'YYYR',
 '6.3.3.2': 'YYYR',
 '6.3.3.3': 'YYYN',
 '6.3.3.4': 'YYYR',
 '6.3.3.5': 'YYYN',
 '6.3.3.6': 'YYYN',
 '6.3.4.3': 'YYYN',
 '6.3.4.4': 'YYYR',
 '6.3.4.8': 'YYYR',
 '6.3.5.1': 'YYYR',
 '6.3.5.2': 'YYYR',
 '6.3.5.3': 'YYYR',
 '6.3.5.4': 'YYYR',
 '6.3.5.9': 'YYYN',
 '6.3.5.10': 'YYYN',
 '6.3.5.14': 'YYYR',
 '6.3.5.19': 'YYYN',
 '6.3.5.28': 'YYNN',
 '6.3.5.30': 'YYYN',
 '6.3.5.31': 'YYYN',
 '6.3.8.2': 'YYRR',
 '6.3.9.7': 'YYYR',
 '7.1.4': 'YYYR',
 '7.1.5': 'YYYR',
 '7.1.8': 'YYYN'}

REDUCTION_NOTES = {'5.1.5.1': 'training need still met; the formal training output is not demanded',
 '5.2.3': 'audits held only where a need is identified, not on a fixed plan',
 '5.2.7.2': 'only the quality characteristics that matter for this software are kept',
 '5.4.1.1': 'supplier selection still done; the formal output is not demanded',
 '5.6.1.1': 'methods and tools must have a prior successful use, any domain',
 '5.6.1.2': 'the activity stays; the formal output is not demanded',
 '5.6.1.3': 'the activity stays; the formal output is not demanded',
 '5.6.2.1': 'the activity stays; the formal output is not demanded',
 '5.6.2.2': 'the activity stays; the formal output is not demanded',
 '6.2.5.4': 'process metrics limited to problems found during validation',
 '6.2.7.4': 'reuse analysis trimmed to a subset of its items, design scope limited',
 '6.2.7.7': 'kept only as far as maintainability of the software needs it',
 '6.2.7.8': 'kept only as far as maintainability of the software needs it',
 '6.3.3.1': 'only document control is asked of the design',
 '6.3.3.2': 'design standards become a recommendation',
 '6.3.3.4': 'applies only if design standards were adopted',
 '6.3.4.4': 'not asked unless the software is security sensitive',
 '6.3.4.8': 'code enters configuration control no later than validation start',
 '6.3.5.1': 'no formal unit and integration test activity is demanded',
 '6.3.5.2': 'no formal unit and integration test activity is demanded',
 '6.3.5.3': 'test procedures and data are verified by sampling',
 '6.3.5.4': 'held for validation and acceptance testing only',
 '6.3.5.14': 'held for validation and acceptance testing only',
 '6.3.8.2': 'the safety-feature item of the clause drops out',
 '6.3.9.7': 'statistical data need not be collected',
 '7.1.4': 'one product metric item drops out',
 '7.1.5': 'design and fault-density or failure-intensity metrics not demanded'}

DOCUMENT_TITLES = {'acceptance-documentation': 'acceptance test plan, report and joint review',
 'alerts': 'alert information raised and received',
 'audit-plan': 'audit plan and schedule',
 'coding-standards': 'coding standards and their tools',
 'criticality-classification': 'criticality classification of software products and '
                               'components',
 'dependability-safety-analysis': 'software dependability and safety analysis report',
 'design-justification': 'justification of design choices',
 'design-standards': 'design and modelling standards',
 'isvv-plan': 'independent software verification and validation plan',
 'isvv-report': 'independent software verification and validation report',
 'maintenance': 'maintenance plan and records',
 'nonconformance-reports': 'nonconformance reports and review board records',
 'operations': 'operations support and ground equipment selection',
 'problem-reports': 'software problem reports and their closure',
 'procedures-standards': 'procedures and standards in force',
 'process-assessment': 'process assessment and improvement records',
 'procurement': 'procurement data and receiving inspection',
 'requirements-baseline': 'quality requirements in the requirements baseline',
 'review-inspection-records': 'review and inspection plans and reports',
 'scm-plan': 'software configuration management plan',
 'sdp': 'software development plan and project plans',
 'security-analysis': 'software security analysis report',
 'security-management-plan': 'software security management plan',
 'software-configuration-file': 'software configuration file and release data',
 'software-reuse-file': 'software reuse file',
 'software-verification-plan': 'software verification plan',
 'software-verification-report': 'software verification report',
 'spa-reports': 'periodic software product assurance reports',
 'spamr': 'software product assurance milestone report (SPAMR)',
 'spap': 'software product assurance plan (SPAP)',
 'supplier-control': 'supplier selection, requirements flow-down and monitoring',
 'technical-specification': 'quality requirements in the technical specification',
 'test-readiness': 'test readiness confirmation and test compliance statement',
 'training': 'training plan and records',
 'validation-documentation': 'test and validation plans, specifications and reports'}

DOCUMENT_CONDITIONS = {'software-reuse-file': 'reuse',
 'security-analysis': 'security',
 'security-management-plan': 'security',
 'supplier-control': 'suppliers',
 'procurement': 'procured',
 'operations': 'operations',
 'maintenance': 'operations'}

DOCUMENT_CLAUSE_REVIEWS = {'acceptance-documentation': {'6.3.7.1': ('qr', 'ar'),
                              '6.3.7.6': ('ar',),
                              '6.3.7.7': ('ar',)},
 'alerts': {'5.2.4': ()},
 'audit-plan': {'5.2.3': ('srr',)},
 'coding-standards': {'6.3.4.1': ('pdr',), '6.3.4.2': ('pdr',), '6.3.4.4': ('pdr',)},
 'criticality-classification': {'6.2.2.1': ('srr', 'pdr'), '6.2.2.3': ('pdr',)},
 'dependability-safety-analysis': {'6.2.2.2': ('pdr',),
                                   '6.2.2.5': ('cdr', 'qr', 'ar'),
                                   '6.2.2.6': ('cdr', 'qr', 'ar'),
                                   '6.2.2.7': ('pdr', 'cdr'),
                                   '6.2.2.10': ('pdr', 'cdr', 'qr', 'ar'),
                                   '6.2.10.1': ('pdr', 'cdr', 'qr', 'ar')},
 'design-justification': {'7.2.2.3': ('pdr', 'cdr')},
 'design-standards': {'6.2.8.4': ('srr', 'pdr'), '6.3.3.2': ('srr', 'pdr')},
 'isvv-plan': {'6.2.6.13': ('srr', 'pdr'), '6.3.5.28': ('srr', 'pdr')},
 'isvv-report': {'6.2.6.13': ('pdr', 'cdr', 'qr', 'ar'),
                 '6.3.5.28': ('pdr', 'cdr', 'qr', 'ar')},
 'maintenance': {'6.3.9.1': ('qr', 'ar', 'orr'),
                 '6.3.9.2': ('qr', 'ar', 'orr'),
                 '6.3.9.4': ('qr', 'ar', 'orr'),
                 '6.3.9.5': ('qr', 'ar', 'orr'),
                 '6.3.9.6': (),
                 '6.3.9.7': ()},
 'nonconformance-reports': {'5.2.6.1': ('srr',), '6.3.7.5': ('ar',)},
 'operations': {'6.3.8.1': ('orr',),
                '6.3.8.2': ('orr',),
                '7.4.1': ('srr', 'pdr'),
                '7.4.2': ('srr', 'pdr'),
                '7.4.3': ('srr', 'pdr'),
                '7.4.4': ('srr', 'pdr')},
 'problem-reports': {'5.2.5.1': ('pdr',),
                     '5.2.5.2': ('pdr',),
                     '5.2.5.3': ('pdr',),
                     '6.2.6.4': ('srr', 'pdr', 'cdr', 'qr', 'ar', 'orr'),
                     '6.3.5.6': ('cdr', 'qr', 'ar', 'orr'),
                     '6.3.5.8': ('srr', 'pdr', 'cdr', 'qr', 'ar', 'orr')},
 'procedures-standards': {'6.2.1.6': ('pdr',), '6.2.1.7': ('pdr',)},
 'process-assessment': {'5.7.1': (),
                        '5.7.2.1': (),
                        '5.7.2.2': (),
                        '5.7.2.3': (),
                        '5.7.2.4': (),
                        '5.7.3.1': (),
                        '5.7.3.2': (),
                        '5.7.3.3': ()},
 'procurement': {'5.5.3': ('srr', 'pdr'),
                 '5.5.5': ('pdr', 'cdr', 'qr'),
                 '7.4.1': ('srr', 'pdr')},
 'requirements-baseline': {'7.1.1': ('srr',),
                           '7.1.2': ('srr',),
                           '7.2.1.1': ('srr',),
                           '7.2.1.3': ('srr',)},
 'review-inspection-records': {'6.2.6.9': (), '6.2.6.10': (), '6.2.6.11': ()},
 'scm-plan': {'6.2.4.2': ('srr', 'pdr'),
              '6.2.4.5': ('srr', 'pdr'),
              '6.2.4.12': ('srr', 'pdr'),
              '7.3.5': ('srr', 'pdr')},
 'sdp': {'5.5.2': ('srr', 'pdr'),
         '5.6.2.1': ('srr', 'pdr'),
         '5.6.2.2': ('srr', 'pdr'),
         '6.2.1.1': (),
         '6.2.1.2': (),
         '6.2.1.3': (),
         '6.3.4.5': ('pdr',)},
 'security-analysis': {'5.4.5': ('srr',),
                       '6.2.9.2': ('pdr',),
                       '6.2.9.5': ('cdr', 'qr', 'ar'),
                       '6.2.9.6': ('cdr', 'qr', 'ar'),
                       '6.2.9.7': ('pdr', 'cdr'),
                       '6.2.10.1': ('pdr', 'cdr', 'qr', 'ar')},
 'security-management-plan': {'6.2.4.8': ('srr', 'pdr'),
                              '6.2.4.9': ('srr',),
                              '6.2.4.11': ('srr',),
                              '6.2.10.2': ('pdr', 'cdr', 'qr', 'ar'),
                              '6.2.10.3': ('pdr', 'cdr'),
                              '6.2.10.4': ('pdr', 'cdr')},
 'software-configuration-file': {'6.2.4.3': (),
                                 '6.2.4.4': ('cdr', 'qr', 'ar', 'orr'),
                                 '6.2.4.5': ('cdr', 'qr', 'ar', 'orr'),
                                 '6.2.4.6': ('cdr', 'qr', 'ar', 'orr'),
                                 '6.2.4.8': ('cdr', 'qr', 'ar', 'orr'),
                                 '6.2.4.10': (),
                                 '6.2.4.11': (),
                                 '6.3.6.2': ('ar',)},
 'software-reuse-file': {'6.2.7.2': ('srr', 'pdr'),
                         '6.2.7.3': ('srr', 'pdr'),
                         '6.2.7.4': ('srr', 'pdr'),
                         '6.2.7.5': ('srr', 'pdr'),
                         '6.2.7.6': ('srr', 'pdr'),
                         '6.2.7.7': ('srr', 'pdr'),
                         '6.2.7.8': ('srr', 'pdr'),
                         '6.2.7.9': ('cdr', 'qr', 'ar'),
                         '6.2.7.11': ('srr', 'pdr', 'cdr', 'qr', 'ar'),
                         '7.3.6': ('cdr',),
                         '7.3.7': ('cdr',)},
 'software-verification-plan': {'6.2.6.1': ('srr', 'pdr')},
 'software-verification-report': {'6.2.6.5': ('cdr', 'qr', 'ar'),
                                  '6.2.6.6': ('cdr', 'qr', 'ar'),
                                  '7.1.7': ('pdr', 'cdr', 'qr'),
                                  '7.2.3.6': ('cdr', 'qr', 'ar')},
 'spa-reports': {'5.2.2.1': (),
                 '5.2.2.2': (),
                 '5.6.1.3': (),
                 '6.2.5.4': (),
                 '6.2.5.5': (),
                 '6.2.6.2': (),
                 '6.2.6.3': (),
                 '6.2.6.7': (),
                 '6.2.8.5': (),
                 '6.3.3.4': (),
                 '6.3.3.6': (),
                 '6.3.3.7': (),
                 '6.3.4.7': (),
                 '6.3.5.3': (),
                 '6.3.5.5': (),
                 '6.3.5.12': (),
                 '7.1.6': (),
                 '7.1.8': ()},
 'spamr': {'5.2.2.3': ('srr', 'pdr', 'cdr', 'qr', 'ar', 'orr'),
           '5.6.1.2': ('srr', 'pdr'),
           '6.2.3.3': ('pdr', 'cdr', 'qr', 'ar'),
           '6.2.6.12': ('srr', 'pdr', 'cdr', 'qr', 'ar', 'orr')},
 'spap': {'5.1.2.1': ('srr',),
          '5.1.2.2': ('srr',),
          '5.1.2.3': ('srr',),
          '5.1.3.1': ('srr',),
          '5.1.4.1': ('srr',),
          '5.2.1.1': ('srr', 'pdr'),
          '5.2.1.3': ('cdr', 'qr', 'ar', 'orr'),
          '5.2.1.4': ('ar',),
          '5.2.1.5': ('srr', 'pdr'),
          '5.2.6.1': ('srr',),
          '5.2.6.2': ('srr', 'pdr'),
          '5.2.7.1': ('pdr',),
          '5.2.7.2': ('pdr',),
          '5.4.3.3': ('pdr',),
          '5.4.3.4': ('pdr',),
          '5.6.1.1': ('srr', 'pdr'),
          '6.1.1': ('srr', 'pdr'),
          '6.2.1.4': ('srr', 'pdr'),
          '6.2.2.10': ('pdr', 'cdr'),
          '6.2.3.2': ('pdr', 'cdr'),
          '6.2.3.4': ('pdr', 'cdr'),
          '6.2.3.5': ('pdr', 'cdr'),
          '6.2.4.8': ('srr', 'pdr'),
          '6.2.4.9': ('srr', 'pdr'),
          '6.2.4.11': ('srr', 'pdr'),
          '6.2.5.1': ('srr', 'pdr'),
          '6.2.5.2': ('srr', 'pdr'),
          '6.2.7.2': ('srr', 'pdr'),
          '6.2.7.3': ('srr', 'pdr'),
          '6.2.7.4': ('srr', 'pdr'),
          '6.2.7.5': ('srr', 'pdr'),
          '6.2.9.1': ('srr', 'pdr', 'cdr'),
          '6.2.10.3': ('pdr', 'cdr'),
          '6.2.10.4': ('pdr', 'cdr'),
          '6.3.3.3': ('pdr',),
          '6.3.3.5': ('pdr',),
          '6.3.3.7': ('pdr',),
          '6.3.4.3': ('pdr',),
          '6.3.4.6': ('pdr',),
          '6.3.5.1': ('pdr', 'cdr'),
          '6.3.5.2': ('pdr', 'cdr'),
          '6.3.8.3': ('orr',),
          '7.1.3': ('srr', 'pdr'),
          '7.1.4': ('srr', 'pdr'),
          '7.1.5': ('srr', 'pdr'),
          '7.2.2.3': ('srr', 'pdr'),
          '7.5.1': ('pdr',),
          '7.5.2': ('pdr',)},
 'supplier-control': {'5.4.1.1': (),
                      '5.4.2.1': ('srr',),
                      '5.4.2.2': ('srr',),
                      '5.4.4': ('srr',)},
 'technical-specification': {'6.3.2.4': ('pdr',),
                             '7.1.1': ('pdr',),
                             '7.1.2': ('pdr',),
                             '7.2.1.1': ('pdr',),
                             '7.2.1.3': ('pdr',),
                             '7.3.4': ('pdr',)},
 'test-readiness': {'6.1.5': ('trr',),
                    '6.3.5.4': ('trr',),
                    '6.3.5.7': ('cdr', 'qr', 'ar', 'orr'),
                    '6.3.5.11': ('cdr', 'qr', 'ar', 'orr')},
 'training': {'5.1.5.1': ('srr',), '5.1.5.2': ()},
 'validation-documentation': {'6.2.8.2': ('pdr', 'cdr', 'qr', 'ar'),
                              '6.2.8.7': ('pdr', 'cdr', 'qr', 'ar'),
                              '6.3.5.13': ('cdr', 'qr', 'ar', 'orr'),
                              '6.3.5.16': ('cdr', 'qr', 'ar', 'orr'),
                              '6.3.5.17': ('cdr', 'qr', 'ar', 'orr'),
                              '6.3.5.18': ('cdr', 'qr', 'ar', 'orr'),
                              '6.3.5.22': ('pdr', 'cdr'),
                              '6.3.5.23': ('pdr', 'cdr'),
                              '6.3.5.24': ('pdr', 'cdr'),
                              '6.3.5.25': ('pdr', 'cdr', 'qr', 'ar'),
                              '6.3.5.27': ('ar',),
                              '6.3.5.29': ('pdr', 'cdr', 'qr', 'ar'),
                              '6.3.5.30': ('cdr', 'qr', 'ar'),
                              '6.3.5.31': ('cdr', 'qr', 'ar'),
                              '6.3.5.32': ('cdr', 'qr', 'ar'),
                              '6.3.5.33': ('cdr', 'qr', 'ar')}}

SPAMR_SECTIONS = (('1', 'purpose and scope of this milestone report', None),
 ('2', 'applicable and reference documents', None),
 ('3', 'terms and abbreviations', None),
 ('4',
  'verification activities performed by product assurance',
  'verification_activities'),
 ('5', 'suitability of methods and tools', 'methods_tools'),
 ('6', 'adherence to design and coding standards', 'standards_adherence'),
 ('7', 'product and process metrics against their targets', 'metrics'),
 ('8', 'testing and validation status and coverage', 'testing'),
 ('9', 'status of software problem reports and nonconformances', 'problems'),
 ('10', 'references to progress reports', 'progress_reports'))

METRICS = {'cyclomatic_complexity': ('product', 'per function', 'max', '7.1.5'),
 'nesting_depth': ('product', 'levels', 'max', '7.1.4'),
 'function_size_loc': ('product', 'lines', 'max', '7.1.4'),
 'comment_density': ('product', 'ratio', 'min', '7.1.4'),
 'requirement_coverage': ('product', 'ratio', 'min', '7.2.1'),
 'requirement_test_coverage': ('product', 'ratio', 'min', '6.3.5.2'),
 'statement_coverage': ('product', 'ratio', 'min', '6.3.5.2'),
 'decision_coverage': ('product', 'ratio', 'min', '6.3.5.2'),
 'mcdc_coverage': ('product', 'ratio', 'min', '6.3.5.2'),
 'open_major_nonconformances': ('process', 'count', 'max', '5.2.6'),
 'open_problem_reports': ('process', 'count', 'max', '5.2.5'),
 'coding_standard_violations': ('product', 'count', 'max', '6.3.4')}

DEFAULT_THRESHOLDS = {'A': {'cyclomatic_complexity': 10,
       'nesting_depth': 4,
       'function_size_loc': 60,
       'comment_density': 0.25,
       'requirement_coverage': 1.0,
       'requirement_test_coverage': 1.0,
       'statement_coverage': 1.0,
       'decision_coverage': 1.0,
       'mcdc_coverage': 1.0,
       'open_major_nonconformances': 0,
       'open_problem_reports': None,
       'coding_standard_violations': 0},
 'B': {'cyclomatic_complexity': 10,
       'nesting_depth': 4,
       'function_size_loc': 80,
       'comment_density': 0.2,
       'requirement_coverage': 1.0,
       'requirement_test_coverage': 1.0,
       'statement_coverage': 1.0,
       'decision_coverage': 1.0,
       'mcdc_coverage': None,
       'open_major_nonconformances': 0,
       'open_problem_reports': None,
       'coding_standard_violations': 0},
 'C': {'cyclomatic_complexity': 15,
       'nesting_depth': 5,
       'function_size_loc': 100,
       'comment_density': 0.15,
       'requirement_coverage': 1.0,
       'requirement_test_coverage': 1.0,
       'statement_coverage': None,
       'decision_coverage': None,
       'mcdc_coverage': None,
       'open_major_nonconformances': 0,
       'open_problem_reports': None,
       'coding_standard_violations': None},
 'D': {'cyclomatic_complexity': 20,
       'nesting_depth': 6,
       'function_size_loc': 150,
       'comment_density': 0.1,
       'requirement_coverage': 1.0,
       'requirement_test_coverage': 0.9,
       'statement_coverage': None,
       'decision_coverage': None,
       'mcdc_coverage': None,
       'open_major_nonconformances': 0,
       'open_problem_reports': None,
       'coding_standard_violations': None}}

_REQUIREMENT_SET = frozenset(REQUIREMENT_IDS)

# Worst first: several evidence rows on one clause combine to the weakest.
_SEVERITY_RANK = {"not-compliant": 0, "partially-compliant": 1,
                  "compliant": 2}


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def normalise_category(value):
    """Return the category letter A to D ('b', 'cat-B', ' B ' accepted)."""
    text = str(value if value is not None else "").strip().upper()
    for prefix in ("CATEGORY", "CAT-", "CAT"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip(" -")
    if text not in CATEGORIES:
        raise ValueError("unknown software criticality category %r "
                         "(use A, B, C or D)" % (value,))
    return text


def normalise_severity(value):
    """Return the function severity I to IV (numeral, digit or name)."""
    key = str(value if value is not None else "").strip()
    if key.upper() in SEVERITIES:
        return key.upper()
    if key.lower() in _SEVERITY_ALIASES:
        return _SEVERITY_ALIASES[key.lower()]
    raise ValueError("unknown function severity %r (use I, II, III, IV or "
                     "catastrophic, critical, major, minor)" % (value,))


def normalise_provision(value):
    key = str(value).strip().lower()
    if key not in _PROVISION_ALIASES:
        raise ValueError("unknown compensating provision %r (use hardware, "
                         "software or operational-procedure)" % (value,))
    return _PROVISION_ALIASES[key]


def normalise_clause_id(value):
    """Return a clause id such as '6.2.3.4'.

    A 'clause' / 'cl.' / section-sign prefix, a trailing dot and a trailing
    item letter are cut: '6.2.3.4a', '6.2.3.4.a' and 'cl. 6.2.3.4' all give
    '6.2.3.4'. Leading zeros in a part are dropped.
    """
    if not isinstance(value, str):
        raise ValueError("clause id must be text, got %r" % (value,))
    text = value.strip().rstrip(".")
    low = text.lower()
    for prefix in ("clause", "cl.", "§"):
        if low.startswith(prefix):
            text = text[len(prefix):].strip()
            low = text.lower()
    while text and text[-1].isalpha():
        text = text[:-1].rstrip(".")
    parts = text.split(".")
    if not text or not all(p.isdigit() for p in parts):
        raise ValueError("not a clause identifier: %r" % (value,))
    return ".".join(str(int(p)) for p in parts)


def normalise_status(value):
    """Map a status spelling to one of the four statuses; refuse the rest."""
    key = str(value or "").strip().lower().replace("_", " ")
    if key in STATUS_ALIASES:
        return STATUS_ALIASES[key]
    dashed = key.replace(" ", "-")
    if dashed in STATUS_ALIASES:
        return STATUS_ALIASES[dashed]
    raise ValueError("unknown compliance status %r (use compliant, "
                     "partially-compliant, not-compliant or not-applicable)"
                     % (value,))


def normalise_review(value):
    """Return the short review name (srr, pdr, cdr, trr, qr, ar, orr)."""
    key = str(value).strip().lower().replace(" ", "-")
    key = _REVIEW_ALIASES.get(key, key)
    if key not in REVIEWS:
        raise ValueError("unknown review %r (use SRR, PDR, CDR, TRR, QR, AR "
                         "or ORR)" % (value,))
    return key


def normalise_scope(flags):
    """Return the scope flags as a sorted tuple; refuse unknown flags."""
    out = set()
    for flag in flags or ():
        key = str(flag).strip().lower()
        if not key:
            continue
        if key not in SCOPE_FLAGS:
            raise ValueError("unknown scope flag %r (use %s)"
                             % (flag, ", ".join(SCOPE_FLAGS)))
        out.add(key)
    return tuple(sorted(out))


def _clause_key(cid):
    return [int(p) for p in cid.split(".")]


def topic_of(clause):
    """Our topic label for the heading a clause sits under, or ''."""
    parts = normalise_clause_id(clause).split(".")
    for depth in range(min(3, len(parts)), 0, -1):
        key = ".".join(parts[:depth])
        if key in TOPICS:
            return TOPICS[key]
    return ""


def _in_group(cid, group):
    return cid == group or cid.startswith(group + ".")


# ---------------------------------------------------------------------------
# Stage 1-2: category and tailoring
# ---------------------------------------------------------------------------

def derive_category(severity, provisions=(), provides_provision_for=None):
    """Derive the software criticality category.

    The base category follows the highest severity of the functions the
    software takes part in (I -> A ... IV -> D). A compensating provision
    at system level (hardware, software, operational procedure) lowers it
    by one step. Software that IS the compensating provision for functions
    of some severity takes that severity's category with no credit.

    Returns category, base_category, lowered_by_provision, rationale lines
    and the constraints the assignment places on other items.
    """
    sev = normalise_severity(severity)
    base = CATEGORIES[SEVERITIES.index(sev)]
    rationale = ["highest function severity %s gives base category %s"
                 % (sev, base)]
    constraints = []
    if provides_provision_for:
        prov = normalise_severity(provides_provision_for)
        prov_base = CATEGORIES[SEVERITIES.index(prov)]
        category = min(base, prov_base)     # 'A' sorts before 'B': stricter
        rationale.append("the software is itself a compensating provision "
                         "for severity %s functions, so it takes category "
                         "%s without credit" % (prov, prov_base))
        return {"severity": sev, "category": category, "base_category": base,
                "lowered_by_provision": False, "provisions": [],
                "rationale": rationale, "constraints": constraints}
    kinds = sorted(set(normalise_provision(k) for k in (provisions or ())))
    lowered = bool(kinds) and base != "D"
    if lowered:
        category = CATEGORIES[CATEGORIES.index(base) + 1]
        rationale.append("compensating provision(s) %s lower %s to %s"
                         % (", ".join(kinds), base, category))
        if "software" in kinds:
            constraints.append("the software implementing the provision must "
                               "itself be category %s" % base)
        constraints.append("each provision must meet the system dependability "
                           "and safety requirements before the lower category "
                           "is claimed")
    else:
        category = base
        if kinds:
            rationale.append("severity IV software is already category D; "
                             "no credit to take")
    return {"severity": sev, "category": category, "base_category": base,
            "lowered_by_provision": lowered, "provisions": kinds,
            "rationale": rationale, "constraints": constraints}


def tailored_status(clause, category, security_sensitive=False):
    """'applicable', 'reduced', 'not-applicable', or 'unknown'.

    'unknown' = the id is not a requirement of this revision (a heading,
    a typo, or an id from an older list); the matrix treats it as
    applicable and says so.
    """
    cid = normalise_clause_id(clause)
    if cid not in _REQUIREMENT_SET:
        return "unknown"
    code = APPLICABILITY.get(cid, "YYYY")[
        CATEGORIES.index(normalise_category(category))]
    if code == "S":
        return "applicable" if security_sensitive else "not-applicable"
    return {"Y": "applicable", "R": "reduced", "N": "not-applicable"}[code]


def tailoring_summary(category, security_sensitive=False):
    """Tailoring for one category, per clause group and in total."""
    cat = normalise_category(category)
    groups, order = {}, []
    totals = {"applicable": 0, "reduced": 0, "not-applicable": 0}
    reduced = []
    for rid in REQUIREMENT_IDS:
        status = tailored_status(rid, cat, security_sensitive)
        group = ".".join(rid.split(".")[:2])
        if group not in groups:
            groups[group] = {"group": group, "topic": TOPICS.get(group, ""),
                             "applicable": 0, "reduced": 0,
                             "not-applicable": 0}
            order.append(group)
        groups[group][status] += 1
        totals[status] += 1
        if status == "reduced":
            reduced.append({"clause": rid,
                            "note": REDUCTION_NOTES.get(
                                rid, "reduced scope for this category")})
    return {"category": cat, "security_sensitive": bool(security_sensitive),
            "groups": [groups[g] for g in order], "totals": totals,
            "reduced": reduced}


def default_clauses():
    """The requirement list of the standard as (id, topic) pairs."""
    return [(rid, topic_of(rid)) for rid in REQUIREMENT_IDS]


def parse_clause_list(text):
    """Parse a customer clause list: one id per line, or CSV with id[,title].

    Blank lines and lines starting with '#' are skipped; a header row whose
    first cell is not a clause id is skipped. Duplicates are refused.
    """
    out, seen = [], set()
    for n, raw in enumerate(csv.reader(io.StringIO(str(text))), 1):
        if not raw or not raw[0].strip() or raw[0].strip().startswith("#"):
            continue
        try:
            cid = normalise_clause_id(raw[0])
        except ValueError:
            if n == 1:
                continue            # header row
            raise
        if cid in seen:
            raise ValueError("clause %s listed twice" % cid)
        seen.add(cid)
        title = raw[1].strip() if len(raw) > 1 and raw[1].strip() else ""
        out.append((cid, title or topic_of(cid)))
    if not out:
        raise ValueError("clause list is empty")
    return out


# ---------------------------------------------------------------------------
# Stage 3: evidence index and compliance matrix
# ---------------------------------------------------------------------------

_FIELD_ALIASES = {
    "clause": "clause", "clause_id": "clause", "requirement": "clause",
    "id": "clause",
    "document": "document", "doc": "document", "evidence": "document",
    "section": "section", "sect": "section", "paragraph": "section",
    "status": "status", "compliance": "status",
    "justification": "justification", "comment": "justification",
    "rationale": "justification",
}


def parse_evidence_csv(text):
    """Parse the evidence index from CSV text.

    Needs a clause column and a status column; document, section and
    justification are optional. Header spellings are matched loosely
    (clause/requirement/id, document/doc/evidence, section/paragraph,
    justification/comment/rationale). Blank rows are skipped.
    """
    reader = csv.DictReader(io.StringIO(str(text)))
    if not reader.fieldnames:
        raise ValueError("evidence CSV has no header row")
    mapping = {}
    for name in reader.fieldnames:
        key = _FIELD_ALIASES.get(str(name).strip().lower())
        if key and key not in mapping.values():
            mapping[name] = key
    if "clause" not in mapping.values() or "status" not in mapping.values():
        raise ValueError("evidence CSV needs a clause column and a status "
                         "column (optional: document, section, "
                         "justification)")
    rows = []
    for raw in reader:
        row = {mapping[k]: (v or "").strip() for k, v in raw.items()
               if k in mapping}
        if not any(row.values()):
            continue
        rows.append(row)
    return rows


def index_evidence(rows):
    """{clause id: [entries]} with normalised status and stripped fields."""
    index = {}
    for n, row in enumerate(rows, 1):
        if not str(row.get("clause") or "").strip():
            raise ValueError("evidence row %d has no clause" % n)
        cid = normalise_clause_id(str(row["clause"]))
        try:
            status = normalise_status(row.get("status"))
        except ValueError as exc:
            raise ValueError("evidence row %d (clause %s): %s" % (n, cid, exc))
        index.setdefault(cid, []).append({
            "status": status,
            "document": str(row.get("document") or "").strip(),
            "section": str(row.get("section") or "").strip(),
            "justification": str(row.get("justification") or "").strip(),
        })
    return index


def route_gap(kind, clause):
    """The bound skill that resolves a gap of this kind on this clause."""
    if kind in GAP_ROUTES_BY_KIND:
        return GAP_ROUTES_BY_KIND[kind]
    for prefix, leaf in GAP_ROUTES_BY_CLAUSE:
        if clause.startswith(prefix):
            return leaf
    return _LEAF + "q80-compliance-matrix"


def _matrix_row(cid, title, entries, category, security_sensitive):
    gaps = []
    tailoring = (tailored_status(cid, category, security_sensitive)
                 if category else "unknown")
    refs, docs = [], []
    for e in entries:
        if e["document"]:
            refs.append(e["document"] + (" " + e["section"]
                                         if e["section"] else ""))
            if e["document"] not in docs:
                docs.append(e["document"])
    justification = "; ".join(e["justification"] for e in entries
                              if e["justification"])
    if not entries:
        if tailoring == "not-applicable":
            status = "not-applicable"
            justification = ("tailored out for software category %s"
                             % category)
        else:
            status = "not-compliant"
            gaps.append("no-evidence")
            justification = "no evidence mapped; open until assessed"
    else:
        stated = [e["status"] for e in entries]
        graded = [s for s in stated if s != "not-applicable"]
        if graded:
            status = min(graded, key=_SEVERITY_RANK.get)
            if "not-applicable" in stated:
                gaps.append("conflicting-status")
        else:
            status = "not-applicable"
        if status == "not-applicable":
            if tailoring in ("applicable", "reduced"):
                gaps.append("na-conflicts-with-tailoring")
            if not justification:
                gaps.append("na-without-justification")
        else:
            if not refs:
                gaps.append("no-evidence-reference")
                if status == "compliant":
                    status = "partially-compliant"
            elif any(e["document"] and not e["section"] for e in entries):
                gaps.append("reference-without-section")
            if (status in ("partially-compliant", "not-compliant")
                    and not justification):
                gaps.append("deviation-without-justification")
            if tailoring == "not-applicable":
                gaps.append("evidence-for-tailored-out-clause")
    return {"clause": cid, "title": title, "status": status,
            "tailoring": tailoring, "justification": justification,
            "evidence": refs, "documents": docs,
            "evidence_rows": len(entries), "gaps": gaps, "notes": [],
            "trace": None}


def build_matrix(clauses, evidence_rows, category, security_sensitive=False):
    """Build the compliance matrix. The result is ALWAYS a draft.

    clauses: list of (id, topic) pairs (default_clauses() for the whole
        standard) or plain ids.
    evidence_rows: rows from parse_evidence_csv (or dicts of that shape).
    category: software criticality category A to D.
    """
    cat = normalise_category(category)
    index = index_evidence(evidence_rows)
    listed, seen = [], set()
    for item in clauses:
        if isinstance(item, (tuple, list)):
            cid, title = normalise_clause_id(str(item[0])), str(item[1] or "")
        else:
            cid, title = normalise_clause_id(str(item)), ""
        if cid in seen:
            raise ValueError("clause %s listed twice" % cid)
        seen.add(cid)
        listed.append((cid, title or topic_of(cid)))
    rows = [_matrix_row(cid, title, index.get(cid, []), cat,
                        security_sensitive) for cid, title in listed]
    orphans = sorted((cid for cid in index if cid not in seen),
                     key=_clause_key)
    matrix = {"standard": STANDARD, "category": cat, "status": "DRAFT",
              "requires_human_sign_off": True, "rows": rows,
              "orphan_evidence": orphans,
              "orphan_documents": {cid: [e["document"] for e in index[cid]
                                         if e["document"]]
                                   for cid in orphans},
              "trace": {"ran": False}}
    _refresh(matrix)
    return matrix


def coverage_summary(rows, trace_ran=False):
    """Counts per status and the three coverage fractions.

    compliant fraction = compliant / applicable; evidenced fraction =
    applicable clauses carrying a document reference / applicable; traced
    fraction = applicable clauses with at least one reference that resolves
    to a real file / applicable (None when no document folder was given).
    """
    counts = {s: 0 for s in STATUSES}
    with_ref = traced = gapped = 0
    for row in rows:
        counts[row["status"]] += 1
        applicable = row["status"] != "not-applicable"
        if applicable and row["evidence"]:
            with_ref += 1
        if applicable and row.get("trace") and row["trace"]["found"]:
            traced += 1
        if row["gaps"]:
            gapped += 1
    applicable = len(rows) - counts["not-applicable"]

    def frac(n):
        return round(n / applicable, 4) if applicable else 1.0
    return {"clauses": len(rows), "counts": counts, "applicable": applicable,
            "compliant_fraction": frac(counts["compliant"]),
            "evidenced_fraction": frac(with_ref),
            "traced_fraction": frac(traced) if trace_ran else None,
            "rows_with_gaps": gapped}


def find_gaps(matrix):
    """One entry per (clause, gap kind), with the skill that resolves it.

    Every row gap; every clause not fully compliant (unless it already
    carries no-evidence); one entry per clause that has evidence but is not
    in the clause list.
    """
    out = []
    for row in matrix["rows"]:
        for kind in row["gaps"]:
            out.append({"clause": row["clause"], "kind": kind,
                        "status": row["status"],
                        "next_skill": route_gap(kind, row["clause"])})
        if (row["status"] in ("partially-compliant", "not-compliant")
                and "no-evidence" not in row["gaps"]):
            out.append({"clause": row["clause"], "kind": row["status"],
                        "status": row["status"],
                        "next_skill": route_gap(row["status"],
                                                row["clause"])})
    for cid in matrix.get("orphan_evidence", []):
        out.append({"clause": cid, "kind": "evidence-for-unlisted-clause",
                    "status": None,
                    "next_skill": route_gap("evidence-for-unlisted-clause",
                                            cid)})
    return out


def _refresh(matrix):
    matrix["coverage"] = coverage_summary(matrix["rows"],
                                          matrix["trace"]["ran"])
    matrix["gaps"] = find_gaps(matrix)


# ---------------------------------------------------------------------------
# Stage 4: document trace
# ---------------------------------------------------------------------------

def list_documents(folder):
    """Every file under a folder, as sorted relative paths ('/' separated)."""
    if not os.path.isdir(folder):
        raise ValueError("document folder not found: %s" % folder)
    out = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for f in sorted(files):
            if f.startswith("."):
                continue
            rel = os.path.relpath(os.path.join(root, f), folder)
            out.append(rel.replace(os.sep, "/"))
    return sorted(out)


def _doc_keys(name):
    base = str(name).replace("\\", "/").rsplit("/", 1)[-1].strip().lower()
    stem = base.rsplit(".", 1)[0] if "." in base else base
    return base, stem


def resolve_document(document, files):
    """The file a cited document resolves to, or None.

    A citation resolves when a file in the folder has the same name, or the
    same name without its extension ('EX-SPAP-001' -> 'EX-SPAP-001.md').
    Matching ignores case and the folder a file sits in.
    """
    base, stem = _doc_keys(document)
    for rel in files:
        fbase, fstem = _doc_keys(rel)
        if base in (fbase, fstem) or stem == fbase:
            return rel
    return None


def apply_document_trace(matrix, files, folder_label="docs/"):
    """Trace every cited document to a file; raise gaps for the misses.

    A clause whose cited document is missing gets a document-not-found
    gap; a compliant clause whose every citation is missing is downgraded
    to partially compliant (a claim resting on no file is not evidence).
    """
    files = list(files)
    cited, missing = {}, {}
    for row in matrix["rows"]:
        found, lost = [], []
        for doc in row["documents"]:
            rel = resolve_document(doc, files)
            cited.setdefault(doc, rel)
            if rel is None:
                lost.append(doc)
                missing.setdefault(doc, []).append(row["clause"])
            else:
                found.append(doc)
        row["trace"] = {"found": found, "missing": lost}
        if lost and "document-not-found" not in row["gaps"]:
            row["gaps"].append("document-not-found")
        if row["status"] == "compliant" and row["documents"] and not found:
            row["status"] = "partially-compliant"
            row["notes"].append("downgraded from compliant: no cited "
                                "document was found in the folder")
    for cid, docs in matrix.get("orphan_documents", {}).items():
        for doc in docs:
            rel = resolve_document(doc, files)
            cited.setdefault(doc, rel)
            if rel is None:
                missing.setdefault(doc, []).append(cid)
    used = set(r for r in cited.values() if r)
    matrix["trace"] = {
        "ran": True, "folder": folder_label, "files": len(files),
        "cited": len(cited),
        "found": sorted(d for d, r in cited.items() if r),
        "resolved": {d: r for d, r in sorted(cited.items()) if r},
        "missing": {d: sorted(set(c), key=_clause_key)
                    for d, c in sorted(missing.items())},
        "uncited_files": [f for f in files if f not in used],
    }
    _refresh(matrix)
    return matrix


# ---------------------------------------------------------------------------
# Stage 5: milestone evidence
# ---------------------------------------------------------------------------

def clause_applies(clause, category, security_sensitive=False):
    """True when a clause applies (fully or reduced) for a category."""
    return tailored_status(clause, category, security_sensitive) in (
        "applicable", "reduced")


def evidence_due(review, category, scope=()):
    """Documents a review owes for a category and scope, with their clauses.

    A document kind is owed when at least one of its driving clauses
    expects it at this review and applies to the category; kinds tied to a
    scope (suppliers, procured items, reuse, security, operations) are owed
    only when the project has that scope.
    """
    rev = normalise_review(review)
    cat = normalise_category(category)
    flags = set(normalise_scope(scope))
    out = []
    for doc in sorted(DOCUMENT_CLAUSE_REVIEWS):
        cond = DOCUMENT_CONDITIONS.get(doc)
        if cond is not None and cond not in flags:
            continue
        clauses = [c for c, revs in DOCUMENT_CLAUSE_REVIEWS[doc].items()
                   if rev in revs and clause_applies(c, cat,
                                                     "security" in flags)]
        if clauses:
            out.append({"document": doc, "title": DOCUMENT_TITLES[doc],
                        "clauses": clauses})
    return out


def parse_pack_csv(text):
    """Parse a review pack: CSV with document (a document kind) + maturity."""
    reader = csv.DictReader(io.StringIO(str(text)))
    fields = [str(f).strip().lower() for f in (reader.fieldnames or [])]
    if "document" not in fields or "maturity" not in fields:
        raise ValueError("review pack CSV needs 'document' and 'maturity' "
                         "columns (document = a document kind such as spap, "
                         "sdp, scm-plan)")
    out = []
    for raw in reader:
        row = {str(k).strip().lower(): (v or "").strip()
               for k, v in raw.items() if k is not None}
        if not row.get("document"):
            continue
        out.append({"document": row["document"],
                    "maturity": row.get("maturity", ""),
                    "file": row.get("file", "")})
    return out


def assess_review_pack(review, category, submitted, scope=(),
                       required_maturity="issued"):
    """Grade a submitted pack against what the review owes.

    Returns owed, missing, immature (below required maturity), unplanned
    (submitted but not owed at this review) and complete.
    """
    if required_maturity not in _MATURITY:
        raise ValueError("unknown maturity %r" % (required_maturity,))
    owed = [d["document"] for d in evidence_due(review, category, scope)]
    got = {}
    for item in submitted:
        doc = str(item.get("document") or "").strip()
        if doc not in DOCUMENT_TITLES:
            raise ValueError("unknown document kind %r in the review pack "
                             "(known kinds: %s)"
                             % (doc, ", ".join(sorted(DOCUMENT_TITLES))))
        if doc in got:
            raise ValueError("document %s submitted twice" % doc)
        mat = str(item.get("maturity") or "").strip().lower()
        if mat not in _MATURITY:
            raise ValueError("unknown maturity %r for %s (use draft, issued "
                             "or approved)" % (mat, doc))
        got[doc] = mat
    missing = [d for d in owed if d not in got]
    immature = [d for d in owed if d in got
                and _MATURITY[got[d]] < _MATURITY[required_maturity]]
    unplanned = sorted(d for d in got if d not in owed)
    return {"review": normalise_review(review), "owed": owed,
            "missing": missing, "immature": immature,
            "unplanned": unplanned,
            "complete": not missing and not immature}


def milestone_check(matrix, review, category, scope=(), pack=None):
    """What the review owes, traced to the matrix rows that evidence it."""
    rev = normalise_review(review)
    by_clause = {r["clause"]: r for r in matrix["rows"]}
    trace_ran = matrix["trace"]["ran"]
    owed = []
    for item in evidence_due(rev, category, scope):
        rows = [by_clause.get(c) for c in item["clauses"]]
        listed = [r for r in rows if r is not None]
        docs = []
        for r in listed:
            for d in (r["trace"]["found"] if trace_ran and r["trace"]
                      else r["documents"]):
                if d not in docs:
                    docs.append(d)
        if not listed:
            state = "not-in-clause-list"
        elif len(listed) == len(rows) and all(
                r["status"] == "compliant"
                and (not trace_ran or r["trace"]["found"]) for r in listed):
            state = "evidenced"
        elif any(r["evidence"] for r in listed):
            state = "partial"
        else:
            state = "no-evidence"
        owed.append(dict(item, state=state, cited=docs))
    return {"review": rev, "review_name": REVIEW_NAMES[rev],
            "spap_maturity_due": PLAN_MATURITY_BY_REVIEW.get(rev),
            "owed": owed,
            "pack": (assess_review_pack(rev, category, pack, scope)
                     if pack is not None else None)}


def spamr_inputs(matrix, metrics=None):
    """Which milestone-report inputs the evidence can supply, and from what.

    An input is available when an applicable clause of its groups carries
    evidence that resolves to a real document (or, with no folder given,
    that cites one). The metrics input is also fed by a graded measurement
    set.
    """
    trace_ran = matrix["trace"]["ran"]
    out = {}
    for key, groups in SPAMR_INPUT_CLAUSES.items():
        docs = []
        for r in matrix["rows"]:
            if r["status"] == "not-applicable":
                continue
            if not any(_in_group(r["clause"], g) for g in groups):
                continue
            for d in (r["trace"]["found"] if trace_ran and r["trace"]
                      else r["documents"]):
                if d not in docs:
                    docs.append(d)
        if key == "metrics" and metrics is not None:
            docs.append("graded measurement set")
        out[key] = sorted(docs)
    return out


def spamr_skeleton(review, inputs):
    """Milestone report (SPAMR) skeleton: section status per available input.

    Status is 'boilerplate' (no project input needed), 'filled' (input
    available) or 'missing-input'. Always a draft for human review.
    """
    rev = normalise_review(review)
    sections, missing = [], []
    for sid, topic, key in SPAMR_SECTIONS:
        if key is None:
            status = "boilerplate"
        elif inputs.get(key):
            status = "filled"
        else:
            status = "missing-input"
            missing.append(key)
        sections.append({"id": sid, "topic": topic, "status": status,
                         "input": key,
                         "draws_on": list(inputs.get(key) or [])
                         if key else []})
    return {"review": rev, "sections": sections, "missing_inputs": missing,
            "status": "DRAFT - requires human review and sign-off"}


# ---------------------------------------------------------------------------
# Stage 6: product quality metrics
# ---------------------------------------------------------------------------

def parse_metrics_csv(text):
    """Parse a measurement set: CSV with metric,value (blank = not measured)."""
    reader = csv.DictReader(io.StringIO(str(text)))
    fields = [str(f).strip().lower() for f in (reader.fieldnames or [])]
    if "metric" not in fields or "value" not in fields:
        raise ValueError("metrics CSV needs 'metric' and 'value' columns")
    out = {}
    for raw in reader:
        row = {str(k).strip().lower(): (v or "").strip()
               for k, v in raw.items() if k is not None}
        name = row.get("metric", "")
        if not name:
            continue
        value = row.get("value", "")
        try:
            out[name] = float(value) if value != "" else None
        except ValueError:
            raise ValueError("metric %s has a non-numeric value %r"
                             % (name, value))
    return out


def thresholds_for(category, overrides=None):
    """{metric: (threshold, source)}; source 'project' for an override."""
    cat = normalise_category(category)
    out = {n: (v, "default") for n, v in DEFAULT_THRESHOLDS[cat].items()
           if v is not None}
    for name, value in dict(overrides or {}).items():
        if name not in METRICS:
            raise ValueError("unknown metric %r" % (name,))
        if value is None:
            out.pop(name, None)
        else:
            out[name] = (value, "project")
    return out


def evaluate_metrics(measurements, category, overrides=None):
    """Grade a measurement set: pass / fail / missing, with the margin."""
    limits = thresholds_for(category, overrides)
    unknown = sorted(n for n in measurements if n not in METRICS)
    rows, failing, missing = [], [], []
    for name in sorted(limits):
        threshold, source = limits[name]
        direction = METRICS[name][2]
        value = measurements.get(name)
        if value is None:
            rows.append({"metric": name, "value": None,
                         "threshold": threshold, "source": source,
                         "direction": direction, "status": "missing",
                         "margin": None})
            missing.append(name)
            continue
        if direction == "max":
            ok, margin = value <= threshold + TOLERANCE, threshold - value
        else:
            ok, margin = value + TOLERANCE >= threshold, value - threshold
        rows.append({"metric": name, "value": value, "threshold": threshold,
                     "source": source, "direction": direction,
                     "status": "pass" if ok else "fail",
                     "margin": round(margin, 4)})
        if not ok:
            failing.append(name)
    return {"category": normalise_category(category), "rows": rows,
            "failing": failing, "missing": missing, "unknown": unknown,
            "verdict": "pass" if not failing and not missing else "fail"}


# ---------------------------------------------------------------------------
# The deliverable
# ---------------------------------------------------------------------------

class ProjectInputs(object):
    """Everything the role is given for one project."""

    def __init__(self, project="", category=None, severity=None,
                 provisions=(), provides_provision_for=None,
                 security_sensitive=False, scope=(), review=None,
                 clauses=None, clause_label="", evidence_text="",
                 evidence_label="evidence.csv", docs_files=None,
                 docs_label="", pack_text=None, pack_label="",
                 metrics_text=None, metrics_label="", example=False):
        self.project = project
        self.category = category
        self.severity = severity
        self.provisions = list(provisions or ())
        self.provides_provision_for = provides_provision_for
        self.security_sensitive = bool(security_sensitive)
        self.scope = list(scope or ())
        self.review = review
        self.clauses = clauses
        self.clause_label = clause_label
        self.evidence_text = evidence_text
        self.evidence_label = evidence_label
        self.docs_files = docs_files
        self.docs_label = docs_label
        self.pack_text = pack_text
        self.pack_label = pack_label
        self.metrics_text = metrics_text
        self.metrics_label = metrics_label
        self.example = example


EXAMPLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "example")
EXAMPLE_PROJECT = ("EXAMPLE-SAT on-board software (worked example, "
                   "not a real project)")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def example_item(example_dir=None):
    """The bundled worked example: a category-B on-board software at PDR.

    Severity I functions with a hardware compensating provision (so the
    category derives to B), reuse in scope, an evidence index, a document
    folder of stub files (one cited document deliberately absent), a PDR
    review pack and a measurement set.
    """
    d = os.path.normpath(example_dir or EXAMPLE_DIR)
    return ProjectInputs(
        project=EXAMPLE_PROJECT, severity="I", provisions=["hardware"],
        scope=["reuse"], review="pdr",
        evidence_text=_read(os.path.join(d, "evidence.csv")),
        evidence_label="example/evidence.csv",
        docs_files=list_documents(os.path.join(d, "docs")),
        docs_label="example/docs/",
        pack_text=_read(os.path.join(d, "pdr-pack.csv")),
        pack_label="example/pdr-pack.csv",
        metrics_text=_read(os.path.join(d, "metrics.csv")),
        metrics_label="example/metrics.csv", example=True)


def resolve_category(item):
    """(category, derivation or None, notes) from the inputs."""
    notes = []
    derivation = None
    if item.severity:
        derivation = derive_category(item.severity, item.provisions,
                                     item.provides_provision_for)
    if item.category:
        cat = normalise_category(item.category)
        if derivation and derivation["category"] != cat:
            notes.append("the category given (%s) differs from the one the "
                          "severity derives (%s): the human must settle it "
                          "before the matrix is used" % (
                              cat, derivation["category"]))
        return cat, derivation, notes
    if derivation:
        return derivation["category"], derivation, notes
    raise ValueError("give the software criticality category (--category "
                     "A-D) or the function severity to derive it from "
                     "(--severity I-IV)")


def build_report(item):
    """Build the full deliverable model from the project inputs."""
    cat, derivation, notes = resolve_category(item)
    scope = set(normalise_scope(item.scope))
    security = bool(item.security_sensitive) or "security" in scope
    if security:
        scope.add("security")
    scope = tuple(sorted(scope))
    clauses = item.clauses if item.clauses is not None else default_clauses()
    evidence_rows = parse_evidence_csv(item.evidence_text)
    matrix = build_matrix(clauses, evidence_rows, cat, security)
    if item.docs_files is not None:
        apply_document_trace(matrix, item.docs_files,
                             item.docs_label or "docs/")
    metrics = None
    if item.metrics_text is not None:
        metrics = evaluate_metrics(parse_metrics_csv(item.metrics_text), cat)
    review = normalise_review(item.review) if item.review else None
    milestone = spamr = None
    if review:
        pack = (parse_pack_csv(item.pack_text)
                if item.pack_text is not None else None)
        milestone = milestone_check(matrix, review, cat, scope, pack)
        spamr = spamr_skeleton(review, spamr_inputs(matrix, metrics))
    return {
        "role": "software-product-assurance-engineer",
        "title": TITLE, "standard": STANDARD,
        "project": item.project or "unnamed project",
        "example": bool(item.example),
        "status": "DRAFT", "requires_human_sign_off": True,
        "banner": DRAFT_BANNER, "stop_line": STOP_LINE,
        "category": cat, "category_derivation": derivation,
        "category_notes": notes,
        "security_sensitive": security, "scope": list(scope),
        "review": review,
        "inputs": {
            "clause_list": item.clause_label or (
                "the full requirement list of the standard"
                if item.clauses is None else "customer clause list"),
            "evidence": item.evidence_label,
            "evidence_rows": len(evidence_rows),
            "docs": item.docs_label if item.docs_files is not None else None,
            "pack": item.pack_label if item.pack_text is not None else None,
            "metrics": (item.metrics_label
                        if item.metrics_text is not None else None),
        },
        "matrix": matrix,
        "tailoring": tailoring_summary(cat, security),
        "milestone": milestone, "spamr": spamr, "metrics": metrics,
        "sign_off": {"signed": False, "signatory": None, "role": None,
                     "date": None, "decision": None},
        "disclaimer": ("DRAFT for human review. Not an approval, not a "
                       "certification, not a statement of compliance."),
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _cell(text):
    return str(text).replace("|", "/").replace("\n", " ").strip()


def _frac(x):
    return "not run" if x is None else "%.4f" % x


def coverage_line(cov):
    c = cov["counts"]
    return ("Coverage: %d clauses, %d applicable; compliant %d, partially %d, "
            "not compliant %d, not applicable %d; compliant fraction %s; "
            "evidenced fraction %s; traced fraction %s." % (
                cov["clauses"], cov["applicable"], c["compliant"],
                c["partially-compliant"], c["not-compliant"],
                c["not-applicable"], _frac(cov["compliant_fraction"]),
                _frac(cov["evidenced_fraction"]),
                _frac(cov["traced_fraction"])))


def render_report_markdown(model):
    """Render the deliverable: banner, scope, coverage, matrix, gaps, trace,
    tailoring, milestone, SPAMR skeleton, metrics, boundaries, stop line."""
    m = model["matrix"]
    cov = m["coverage"]
    L = ["# " + model["title"], "", "> " + model["banner"], "",
         "Status: %s. Human sign-off required." % model["status"], ""]

    # 1. scope
    L += ["## 1. Scope and basis", ""]
    L.append("- Project: %s" % model["project"])
    L.append("- Standard: %s, referenced summary-only (clause identifiers "
             "with topic labels of our own wording)" % model["standard"])
    L.append("- Software criticality category: **%s**" % model["category"])
    der = model["category_derivation"]
    if der:
        L.append("- Category derivation: %s" % "; ".join(der["rationale"]))
        for c in der["constraints"]:
            L.append("- Constraint: %s" % c)
    for n in model["category_notes"]:
        L.append("- Open point: %s" % n)
    L.append("- Security sensitive: %s" % (
        "yes" if model["security_sensitive"] else "no"))
    L.append("- Project scope: %s" % (", ".join(model["scope"]) or
                                      "no conditional scope"))
    L.append("- Target review: %s" % (
        REVIEW_NAMES[model["review"]] if model["review"] else "none given"))
    inp = model["inputs"]
    L.append("- Clause list: %s (%d clauses)" % (inp["clause_list"],
                                                 cov["clauses"]))
    L.append("- Evidence index: %s (%d rows)" % (inp["evidence"],
                                                 inp["evidence_rows"]))
    L.append("- Document folder: %s" % (
        "%s (%d files)" % (inp["docs"], m["trace"]["files"])
        if inp["docs"] else "not given, so no citation was traced to a file"))
    L.append("- Review pack: %s" % (inp["pack"] or "not given"))
    L.append("- Measurement set: %s" % (inp["metrics"] or "not given"))
    L.append("")

    # 2. coverage
    c = cov["counts"]
    L += ["## 2. Coverage summary", "", coverage_line(cov), "",
          "| Measure | Value |", "|---|---|",
          "| Clauses in the matrix | %d |" % cov["clauses"],
          "| Applicable clauses | %d |" % cov["applicable"],
          "| Compliant | %d |" % c["compliant"],
          "| Partially compliant | %d |" % c["partially-compliant"],
          "| Not compliant (including no evidence) | %d |" % c["not-compliant"],
          "| Not applicable | %d |" % c["not-applicable"],
          "| Compliant fraction of applicable clauses | %s |"
          % _frac(cov["compliant_fraction"]),
          "| Applicable clauses with a document reference | %s |"
          % _frac(cov["evidenced_fraction"]),
          "| Applicable clauses traced to a real file | %s |"
          % _frac(cov["traced_fraction"]),
          "| Rows with at least one gap | %d |" % cov["rows_with_gaps"],
          "", "Open gaps: %d." % len(m["gaps"]), ""]

    # 3. matrix
    L += ["## 3. Compliance matrix", "",
          "| Clause | Topic | Tailoring | Status | Justification | Evidence "
          "| Gaps |", "|---|---|---|---|---|---|---|"]
    for r in m["rows"]:
        just = r["justification"]
        if r["notes"]:
            just = "; ".join([just] + r["notes"]) if just else "; ".join(
                r["notes"])
        L.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            r["clause"], _cell(r["title"]), r["tailoring"], r["status"],
            _cell(just), _cell("; ".join(r["evidence"])),
            _cell(", ".join(r["gaps"]))))
    L.append("")

    # 4. gaps
    L += ["## 4. Gaps", ""]
    if m["gaps"]:
        L += ["Each gap names the bound skill that resolves it.", "",
              "| # | Clause | Gap | Status | Next skill |",
              "|---|---|---|---|---|"]
        for i, g in enumerate(m["gaps"], 1):
            L.append("| %d | %s | %s | %s | %s |" % (
                i, g["clause"], g["kind"], g["status"] or "not in list",
                g["next_skill"].rsplit("/", 1)[-1]))
    else:
        L.append("No open gaps.")
    if m["orphan_evidence"]:
        L += ["", "Evidence was given for clauses that are not in the clause "
              "list (a mistyped id, or an id from an older revision): %s."
              % ", ".join(m["orphan_evidence"])]
    L.append("")

    # 5. trace
    L += ["## 5. Document trace", ""]
    t = m["trace"]
    if t["ran"]:
        L.append("Folder %s holds %d files; the evidence cites %d documents, "
                 "%d of which resolve to a file." % (
                     t["folder"], t["files"], t["cited"], len(t["found"])))
        L.append("")
        if t["missing"]:
            L += ["| Cited document not found | Cited by clauses |",
                  "|---|---|"]
            for doc, cl in t["missing"].items():
                L.append("| %s | %s |" % (_cell(doc), ", ".join(cl)))
            L.append("")
        else:
            L += ["Every cited document resolves to a file.", ""]
        if t["resolved"]:
            L += ["| Cited document | File |", "|---|---|"]
            for doc, rel in t["resolved"].items():
                L.append("| %s | %s |" % (_cell(doc), _cell(rel)))
            L.append("")
        if t["uncited_files"]:
            L += ["Files no evidence row cites: %s." % ", ".join(
                t["uncited_files"]), ""]
    else:
        L += ["Not run: no document folder was given, so the references in "
              "the matrix are claims that have not been traced to files. "
              "Run the build again with the project's document folder.", ""]

    # 6. tailoring
    tl = model["tailoring"]
    L += ["## 6. Tailoring for category %s" % tl["category"], "",
          "| Group | Topic | Applicable | Reduced | Not applicable |",
          "|---|---|---|---|---|"]
    for g in tl["groups"]:
        L.append("| %s | %s | %d | %d | %d |" % (
            g["group"], _cell(g["topic"]), g["applicable"], g["reduced"],
            g["not-applicable"]))
    tt = tl["totals"]
    L += ["", "Total: %d applicable, %d reduced, %d not applicable. The "
          "security clauses follow the security sensitivity (%s), not the "
          "category." % (tt["applicable"], tt["reduced"],
                         tt["not-applicable"],
                         "yes" if tl["security_sensitive"] else "no"), ""]
    if tl["reduced"]:
        L += ["Reduced for this category:", ""]
        for r in tl["reduced"]:
            L.append("- %s: %s" % (r["clause"], r["note"]))
        L.append("")

    # 7. milestone
    ms = model["milestone"]
    L += ["## 7. Milestone evidence check", ""]
    if ms:
        L.append("Review: %s. Software product assurance plan (SPAP) "
                 "maturity owed: %s." % (
                     ms["review_name"],
                     ms["spap_maturity_due"] or "not set for this review"))
        L += ["", "| Document owed | Driving clauses | Evidence state | "
              "Documents cited |", "|---|---|---|---|"]
        for o in ms["owed"]:
            L.append("| %s | %s | %s | %s |" % (
                _cell(o["title"]), ", ".join(o["clauses"]), o["state"],
                _cell(", ".join(o["cited"]) or "none")))
        L.append("")
        pk = ms["pack"]
        if pk:
            L += ["Review pack against what is owed: %d owed; missing: %s; "
                  "below issued maturity: %s; submitted but not owed at this "
                  "review: %s; pack complete: %s." % (
                      len(pk["owed"]), ", ".join(pk["missing"]) or "none",
                      ", ".join(pk["immature"]) or "none",
                      ", ".join(pk["unplanned"]) or "none",
                      "yes" if pk["complete"] else "no"), ""]
        else:
            L += ["No review pack was given, so only the clause evidence was "
                  "checked.", ""]
    else:
        L += ["No target review was given.", ""]

    # 8. SPAMR
    sp = model["spamr"]
    L += ["## 8. Milestone report skeleton (SPAMR)", ""]
    if sp:
        L += ["Software product assurance milestone report (SPAMR) for the "
              "%s, %s." % (REVIEW_NAMES[sp["review"]], sp["status"]), "",
              "| Section | Topic | Status | Draws on |", "|---|---|---|---|"]
        for s in sp["sections"]:
            L.append("| %s | %s | %s | %s |" % (
                s["id"], _cell(s["topic"]), s["status"],
                _cell(", ".join(s["draws_on"])) or "-"))
        L += ["", "Inputs still missing: %s." % (
            ", ".join(sp["missing_inputs"]) or "none"), ""]
    else:
        L += ["No target review was given.", ""]

    # 9. metrics
    mt = model["metrics"]
    L += ["## 9. Product quality metrics", ""]
    if mt:
        L += ["| Metric | Value | Threshold | Source | Direction | Status | "
              "Margin |", "|---|---|---|---|---|---|---|"]
        for r in mt["rows"]:
            L.append("| %s | %s | %s | %s | %s | %s | %s |" % (
                r["metric"], "-" if r["value"] is None else "%g" % r["value"],
                "%g" % r["threshold"], r["source"], r["direction"],
                r["status"],
                "-" if r["margin"] is None else "%g" % r["margin"]))
        L += ["", "Verdict: %s (failing: %s; not measured: %s). The standard "
              "fixes no threshold values: the defaults are illustrative and "
              "the values agreed in the contract and the plan replace them."
              % (mt["verdict"], ", ".join(mt["failing"]) or "none",
                 ", ".join(mt["missing"]) or "none"), ""]
        if mt["unknown"]:
            L += ["Metrics not in the catalogue (not graded): %s."
                  % ", ".join(mt["unknown"]), ""]
    else:
        L += ["No measurement set was given.", ""]

    # 10. boundaries
    L += ["## 10. Limitations and boundaries", "",
          "- This matrix is a DRAFT prepared by an agent. It is not an "
          "approval, not a certification and not a statement of compliance.",
          "- Statuses are those the evidence index claims, combined to the "
          "weakest per clause and downgraded where a reference is missing. "
          "The role checks that each cited document exists; it does not "
          "judge what the document says.",
          "- A not-applicable claim on a clause the tailoring keeps is a "
          "deviation and needs the customer's agreement.",
          "- The standard is referenced, never reproduced: clause "
          "identifiers are facts, topic labels are our own wording."]
    if model["example"]:
        L += ["- Worked example: the project, documents and evidence are "
              "invented to show the deliverable. Nothing here describes a "
              "real mission."]
    L.append("")

    # 11. sign-off
    L += ["## 11. Human sign-off", "", NOT_SIGNED,
          "The responsible human records the decision (see ROLE.md, "
          "Human sign-off). Approving over open gaps has to list them as "
          "accepted.", "", model["stop_line"]]
    return "\n".join(L) + "\n"


def render_matrix_csv(model):
    """The matrix as CSV: DRAFT on every row, the stop line as the last row."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["clause", "topic", "tailoring", "status", "justification",
                "evidence", "documents_found", "documents_missing", "gaps",
                "next_skill", "matrix_status"])
    for r in model["matrix"]["rows"]:
        tr = r["trace"] or {}
        just = "; ".join(([r["justification"]] if r["justification"] else [])
                         + r["notes"])
        w.writerow([r["clause"], r["title"], r["tailoring"], r["status"],
                    just, "; ".join(r["evidence"]),
                    "; ".join(tr.get("found", [])),
                    "; ".join(tr.get("missing", [])),
                    ", ".join(r["gaps"]),
                    route_gap(r["gaps"][0], r["clause"]).rsplit("/", 1)[-1]
                    if r["gaps"] else "",
                    model["status"]])
    w.writerow(["STOP", model["stop_line"], "", "", "", "", "", "", "", "",
                model["status"]])
    return buf.getvalue()


def example_report_markdown():
    return render_report_markdown(build_report(example_item()))


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

def check_report(model):
    """Evidence gates on the content model. True = pass."""
    m = model["matrix"]
    rows = m["rows"]
    ids = [r["clause"] for r in rows]
    gates = {}
    gates["draft_status"] = (model["status"] == "DRAFT"
                             and model["requires_human_sign_off"] is True
                             and m["status"] == "DRAFT"
                             and not model["sign_off"]["signed"])
    gates["category_resolved"] = model["category"] in CATEGORIES
    gates["one_row_per_clause"] = (bool(rows) and len(set(ids)) == len(ids)
                                   and all(r["status"] in STATUSES
                                           for r in rows))
    gates["no_silent_compliance"] = all(
        r["evidence_rows"] > 0
        or (r["status"] == "not-applicable"
            and r["tailoring"] == "not-applicable")
        or (r["status"] == "not-compliant" and "no-evidence" in r["gaps"])
        for r in rows)
    gates["compliant_rows_referenced"] = all(
        r["evidence"] and (not m["trace"]["ran"] or r["trace"]["found"])
        for r in rows if r["status"] == "compliant")
    gates["coverage_consistent"] = (
        m["coverage"] == coverage_summary(rows, m["trace"]["ran"]))
    gates["gaps_consistent"] = m["gaps"] == find_gaps(m)
    if m["trace"]["ran"]:
        flagged = set(c for r in rows if "document-not-found" in r["gaps"]
                      for c in [r["clause"]])
        gates["trace_honest"] = all(
            c in flagged or c in m["orphan_evidence"]
            for cl in m["trace"]["missing"].values() for c in cl)
    else:
        gates["trace_honest"] = m["coverage"]["traced_fraction"] is None
    ms = model["milestone"]
    gates["milestone_consistent"] = (ms is None) or (
        bool(ms["owed"]) and all(o["state"] in (
            "evidenced", "partial", "no-evidence", "not-in-clause-list")
            for o in ms["owed"]))
    gates["all_pass"] = all(gates.values())
    return gates


_COVERAGE_RE = re.compile(
    r"^Coverage: (\d+) clauses, (\d+) applicable; compliant (\d+), "
    r"partially (\d+), not compliant (\d+), not applicable (\d+);", re.M)
_ROW_RE = re.compile(r"^\| (\d+(?:\.\d+)*) \| [^|]* \| ([a-z-]+) \| "
                     r"([a-z-]+) \|", re.M)
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def read_sign_off(md):
    """Parse the human sign-off block, if one was appended.

    Returns {'state': 'unsigned'} or {'state': 'signed', fields..., 'errors'}.
    """
    found = {}
    for line in md.splitlines():
        for key in SIGN_OFF_KEYS:
            if line.startswith(key + ":"):
                found[key] = line[len(key) + 1:].strip()
    if not found:
        return {"state": "unsigned"}
    errors = []
    for key in SIGN_OFF_KEYS[:4]:
        if not found.get(key):
            errors.append("%s is missing or empty" % key)
    if found.get("Sign-off-date") and not _ISO_DATE.match(
            found["Sign-off-date"]):
        errors.append("Sign-off-date must be YYYY-MM-DD")
    decision = found.get("Sign-off-decision", "").lower()
    if decision and decision not in ("approved", "rejected"):
        errors.append("Sign-off-decision must be approved or rejected")
    return {"state": "signed", "signatory": found.get("Signed-off-by"),
            "role": found.get("Sign-off-role"),
            "date": found.get("Sign-off-date"), "decision": decision,
            "accepted_open_gaps": found.get("Accepted-open-gaps"),
            "errors": errors}


def _section(md, heading):
    """The text of one '## ' section of the Markdown, or ''."""
    if heading not in md:
        return ""
    return md.split(heading, 1)[1].split("\n## ", 1)[0]


def check_report_markdown(md):
    """Gate-check a rendered (or human-signed) matrix. True = pass."""
    gates = {}
    low = md.lower()
    gates["title_present"] = TITLE in md
    gates["draft_marked"] = DRAFT_BANNER in md and "not an approval" in low
    gates["category_stated"] = bool(re.search(
        r"Software criticality category: \*\*[ABCD]\*\*", md))
    rows = _ROW_RE.findall(_section(md, "## 3. Compliance matrix"))
    gates["matrix_present"] = bool(rows) and all(
        s in STATUSES for _, _, s in rows)
    counts = {s: 0 for s in STATUSES}
    for _, _, s in rows:
        if s in counts:
            counts[s] += 1
    cov = _COVERAGE_RE.search(md)
    gates["coverage_matches_rows"] = bool(cov) and [
        int(x) for x in cov.groups()] == [
        len(rows), len(rows) - counts["not-applicable"], counts["compliant"],
        counts["partially-compliant"], counts["not-compliant"],
        counts["not-applicable"]]
    gap_sec = _section(md, "## 4. Gaps")
    gap_rows = len(re.findall(r"^\| \d+ \| ", gap_sec, re.M))
    og = re.search(r"^Open gaps: (\d+)\.", md, re.M)
    open_gaps = int(og.group(1)) if og else None
    gates["open_gaps_match"] = og is not None and open_gaps == gap_rows
    so = read_sign_off(md)
    if so["state"] == "unsigned":
        gates["sign_off_honest"] = (STOP_LINE in md and NOT_SIGNED in md
                                    and "Status: DRAFT." in md)
    else:
        ok = not so["errors"]
        if ok and so["decision"] == "approved" and open_gaps:
            acc = so.get("accepted_open_gaps") or ""
            ok = acc.isdigit() and int(acc) == open_gaps
            if not ok:
                so["errors"].append(
                    "approved over %d open gaps without Accepted-open-gaps: "
                    "%d" % (open_gaps, open_gaps))
        gates["sign_off_honest"] = ok
    gates["all_pass"] = all(gates.values())
    gates["sign_off"] = so
    return gates
