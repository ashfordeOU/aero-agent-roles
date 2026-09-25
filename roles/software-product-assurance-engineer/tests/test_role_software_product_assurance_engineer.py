#!/usr/bin/env python3
"""Role test: Software Product Assurance Engineer (ECSS-Q-ST-80C).

Verifies (offline, no network):
1. Every skill bound in ROLE.md frontmatter RESOLVES to a real leaf in the
   aero-agent-skills repo, and every bound leaf ships a logic file the
   role can dispatch.
2. The workflow stage order is deterministic and complete.
3. The filled deliverable template carries no blanks, the draft and
   no-approval markers, ends at the stop line, and is byte-identical to a
   fresh build of the bundled worked example (no stale template).
4. The role ships the 100% anatomy (core engine, cli, SOURCES, example),
   spells out its abbreviations, carries no machine paths, and the author
   is ashfordeOU.
"""
import os
import re
import sys
import unittest

ROLES_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))          # repo root (4 up from tests/)
# Bound-skill resolution is a cross-repo dev check: it runs when
# AEROSKILLS_DEV points at an aero-agent-skills checkout, and skips
# otherwise (role-lint resolves the same list against the pinned ledger).
AEROSKILLS = os.environ.get("AEROSKILLS_DEV", "")
HAS_SKILLS = bool(AEROSKILLS) and os.path.isdir(os.path.join(AEROSKILLS,
                                                             "skills"))
ROLE_DIR = os.path.join(ROLES_REPO, "roles",
                        "software-product-assurance-engineer")
TEMPLATE = os.path.join(ROLE_DIR, "templates",
                        "q80-compliance-matrix-template.md")
sys.path.insert(0, os.path.join(ROLE_DIR, "core"))

EXPECTED_BOUND = [
    "space-systems/ecss/q80-software-criticality-tailoring",
    "space-systems/ecss/q80-compliance-matrix",
    "space-systems/ecss/q80-milestone-assurance-evidence",
    "space-systems/ecss/q80-software-product-assurance-plan",
    "space-systems/ecss/q80-software-process-assurance",
    "space-systems/ecss/q80-software-product-quality-metrics",
    "space-systems/ecss/software-engineering",
    "space-systems/ecss/software-verification",
]

EXPECTED_STAGES = [
    "1. Category", "2. Tailoring", "3. Evidence index",
    "4. Compliance matrix", "5. Document trace", "6. Gap routing",
    "7. Milestone evidence", "8. Milestone report skeleton",
    "9. Product metrics", "10. Engineering context", "11. Stop gate",
]

ABBREVIATIONS = {
    "PA": "product assurance",
    "ECSS": "European Cooperation for Space Standardization",
    "SRR": "system requirements review",
    "PDR": "preliminary design review",
    "CDR": "critical design review",
    "QR": "qualification review",
    "AR": "acceptance review",
    "TRR": "test readiness review",
    "ORR": "operational readiness review",
    "SPAP": "software product assurance plan",
    "SPAMR": "software product assurance milestone report",
    "CSV": "comma-separated values",
}


def read_role_md():
    with open(os.path.join(ROLE_DIR, "ROLE.md")) as f:
        return f.read()


def body_of(text):
    """The ROLE.md body with line wraps folded to single spaces."""
    return re.sub(r"\s+", " ", text.split("\n---\n", 1)[1])


class TestSoftwareProductAssuranceRole(unittest.TestCase):

    def test_bound_skills_resolve_in_aeroskills(self):
        if not HAS_SKILLS:
            self.skipTest("Aero Agent Skills checkout not present "
                          "(cross-repo dev check)")
        for leaf in EXPECTED_BOUND:
            sk = os.path.join(AEROSKILLS, "skills", leaf, "SKILL.md")
            self.assertTrue(os.path.exists(sk),
                            "bound skill not found: %s" % leaf)
            scripts = os.path.join(AEROSKILLS, "skills", leaf, "scripts")
            logic = [f for f in os.listdir(scripts)
                     if f.endswith("_logic.py") and not f.startswith("test_")]
            self.assertTrue(logic, "bound leaf has no logic: %s" % leaf)

    def test_bound_skills_are_exactly_the_frontmatter_list(self):
        fm = read_role_md().split("\n---\n", 1)[0]
        block = fm.split("skills_bound:", 1)[1].split("\ntools_allowed:")[0]
        listed = re.findall(r"^\s+-\s+(\S+)\s*$", block, re.M)
        self.assertEqual(listed, EXPECTED_BOUND)

    def test_workflow_stages_deterministic(self):
        role = read_role_md()
        wf = role.split("## Workflow", 1)[1].split("\n## ", 1)[0]
        idx = [wf.find("| " + stage + " |") for stage in EXPECTED_STAGES]
        self.assertTrue(all(i >= 0 for i in idx),
                        "a stage is missing: %s" % idx)
        self.assertEqual(idx, sorted(idx), "stage order not deterministic")

    def test_every_bound_leaf_has_a_stage(self):
        wf = read_role_md().split("## Workflow", 1)[1].split("\n## ", 1)[0]
        for leaf in EXPECTED_BOUND:
            self.assertIn(leaf.rsplit("/", 1)[-1], wf,
                          "no workflow stage loads %s" % leaf)

    def test_deliverable_template_complete(self):
        with open(TEMPLATE) as f:
            text = f.read()
        for n in range(1, 12):
            self.assertTrue(re.search(r"^## %d\. " % n, text, re.M),
                            "section %d missing" % n)
        self.assertEqual(len(re.findall(r"___|TODO|TBD", text)), 0,
                         "template must be a FILLED deliverable (0 blanks)")
        low = text.lower()
        for marker in ("draft", "not an approval", "not a certification",
                       "not a statement of compliance", "ecss-q-st-80c rev.2"):
            self.assertIn(marker, low)
        self.assertEqual(text.rstrip().splitlines()[-1],
                         "STOP: human sign-off required before submission.")

    def test_template_is_a_fresh_build_of_the_example(self):
        import software_product_assurance_core as core
        with open(TEMPLATE) as f:
            self.assertEqual(f.read(), core.example_report_markdown(),
                             "template is stale: regenerate it with "
                             "python3 cli.py build --no-dispatch > "
                             "templates/q80-compliance-matrix-template.md")

    def test_forbidden_lines_present(self):
        role = read_role_md()
        for phrase in ["mark a compliance matrix approved or signed",
                       "issue a statement of compliance",
                       "sign_off_required: true",
                       "reproduce proprietary standard text"]:
            self.assertIn(phrase, role, "missing boundary: %s" % phrase)

    def test_abbreviations_spelled_out_on_first_use(self):
        body = body_of(read_role_md())
        for abbr, words in ABBREVIATIONS.items():
            # a standard's designation (ECSS-Q-ST-80C) is a name, not a use
            first = re.search(r"\b%s\b(?!-)" % abbr, body)
            self.assertIsNotNone(first, "%s not used" % abbr)
            spelled = body.lower().find(words.lower())
            self.assertGreaterEqual(spelled, 0, "%s never spelled out" % abbr)
            self.assertLess(spelled, first.start(),
                            "%s used before it is spelled out" % abbr)

    def test_sources_register_exists(self):
        with open(os.path.join(ROLE_DIR, "SOURCES.md")) as f:
            text = f.read()
        self.assertIn("ECSS-Q-ST-80C Rev.2", text)
        self.assertIn("paraphrased", text)

    def test_core_engine_and_example_exist(self):
        for f in ["core/software_product_assurance_core.py", "cli.py",
                  "templates", "example/evidence.csv", "example/docs",
                  "example/pdr-pack.csv", "example/metrics.csv"]:
            self.assertTrue(os.path.exists(os.path.join(ROLE_DIR, f)),
                            "%s missing" % f)

    def test_example_files_are_marked(self):
        docs = os.path.join(ROLE_DIR, "example", "docs")
        for name in os.listdir(docs):
            self.assertTrue(name.startswith("EX-"), name)
            with open(os.path.join(docs, name)) as f:
                self.assertIn("EXAMPLE STUB", f.read())

    def test_no_machine_paths_shipped(self):
        # built from pieces so this file does not match its own pattern
        pat = re.compile("|".join(["/" + "Users/", "/" + "home/[a-z]",
                                   "/" + "Volumes/"]))
        for root, _dirs, files in os.walk(ROLE_DIR):
            if "__pycache__" in root:
                continue
            for name in files:
                if name.endswith((".md", ".csv", ".py")):
                    with open(os.path.join(root, name)) as f:
                        self.assertIsNone(pat.search(f.read()),
                                          "machine path in %s" % name)

    def test_author_ashfordeou(self):
        self.assertIn("author: ashfordeOU", read_role_md())

    def test_no_approval_claims_in_template(self):
        with open(TEMPLATE) as f:
            low = f.read().lower()
        for phrase in ["signed-off-by", "status: approved", "status: signed",
                       "is compliant with ecss"]:
            self.assertNotIn(phrase, low,
                             "template must not claim approval: %s" % phrase)


if __name__ == "__main__":
    unittest.main()
