#!/usr/bin/env python3
"""Role test: AS9100 Quality / Internal Auditor.

Offline verification: bound skills resolve, workflow order, findings
template fields, boundaries, sources register.
"""
import os
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles", "as9100-quality-auditor")
FINDINGS = os.path.join(ROLE_DIR, "templates", "findings-report-template.md")

EXPECTED_BOUND = [
    "manufacturing-quality/as9100/internal-quality-audit",
    "manufacturing-quality/as9100/document-control",
    "manufacturing-quality/as9100/management-review",
    "manufacturing-quality/as9100/nonconformance-control",
    "manufacturing-quality/as9100/corrective-action",
    "manufacturing-quality/as9100/risk-management",
    "manufacturing-quality/as9100/supplier-control",
    "manufacturing-quality/as9100/order-requirements-review",
    "manufacturing-quality/as9100/calibration-control",
    "manufacturing-quality/as9100/counterfeit-prevention",
    "manufacturing-quality/as9100/fod-control",
    "manufacturing-quality/as9100/quality",
    "manufacturing-quality/as9102/first-article-inspection",
    "manufacturing-quality/as9102/delta-fai",
    "manufacturing-quality/as9102/fai-revalidation",
]

STAGES = ["Audit planning", "Document control check", "Management review check",
          "Risk + ops review", "Nonconformance + corrective action",
          "Supplier + purchasing", "Calibration + counterfeit + FOD",
          "FAI (AS9102)", "Findings + report"]


def role_text():
    p = os.path.join(ROLE_DIR, "ROLE.md")
    return open(p).read() if os.path.exists(p) else None


class TestAs9100Role(unittest.TestCase):

    def test_bound_skills_resolve(self):
        for leaf in EXPECTED_BOUND:
            self.assertTrue(
                os.path.exists(os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")),
                f"bound skill missing: {leaf}")

    def test_stages_ordered(self):
        role = role_text()
        self.assertIsNotNone(role)
        idx = [role.find(s) for s in STAGES]
        self.assertTrue(all(i >= 0 for i in idx))
        self.assertEqual(idx, sorted(idx), "stage order not deterministic")

    def test_findings_fields_present(self):
        if not os.path.exists(FINDINGS):
            self.fail("findings-report-template.md missing")
        text = open(FINDINGS).read()
        for field in ["NC ID", "Clause", "Classification", "Objective evidence",
                      "Root cause", "Corrective action", "Verification"]:
            self.assertIn(field, text, f"field missing: {field}")
        low = text.lower()
        self.assertIn("proposed", low)
        self.assertIn("not a", low)

    def test_boundaries(self):
        role = role_text()
        self.assertIsNotNone(role)
        for phrase in ["issue certification", "claim audit closure",
                       "recommend supplier approval", "sign_off_required: true"]:
            self.assertIn(phrase, role)

    def test_sources_register(self):
        self.assertTrue(
            os.path.exists(os.path.join(ROLE_DIR, "SOURCES.md")),
            "SOURCES.md missing")


if __name__ == "__main__":
    unittest.main()
