# SOURCES.md - Software Product Assurance Engineer (ECSS-Q-ST-80C)

Standards and documents this role references. Summary-not-copy: see
[STANDARDS.md](../../STANDARDS.md) for the full rule.

| Source | Role use | Gated |
|---|---|---|
| ECSS-Q-ST-80C Rev.2, Space product assurance: Software product assurance (30 April 2025) | clause identifiers of the requirement list, the applicability of each requirement per software criticality category and its security-driven clauses, the outputs each requirement expects and the reviews they are expected at, the outline of the milestone report and the plan maturity per review, all paraphrased into data and rules | false |
| ECSS-Q-ST-80C Rev.2, Annex D (criticality categories and tailoring) | category from function severity and compensating provisions; per-category applicability codes; reduced-scope notes in our own words | false |
| ECSS-Q-ST-80C Rev.2, Annexes B, C and F (plan, milestone report, outputs per review) | SPAP maturity owed per review, the SPAMR section outline as topics of our own wording, the documents owed per review | false |
| ECSS-E-ST-40C Rev.1, Space engineering: Software | engineering and verification context of the bound software-engineering and software-verification leaves | false |

ECSS standards are freely downloadable from the ECSS website
(ecss.nl) after registration. They are cited as the source and
paraphrased; no requirement, heading or annex text is reproduced. Clause
identifiers are factual identifiers. The topic labels in the matrix are
our own wording, the same labels the bound q80 leaves use.

The metric thresholds in the metrics stage are illustrative project
defaults carried by the bound q80-software-product-quality-metrics leaf:
the standard fixes no threshold values, and the contract and the plan
replace them.

The deliverable template in `templates/` is the generated output of the
role core for the bundled worked example (`example/`), an invented
project. It is an original synthesis; nothing in it describes a real
mission or reproduces the standard.

## Acquisition status

- ECSS-Q-ST-80C Rev.2 and ECSS-E-ST-40C Rev.1: obtain from ecss.nl;
  referenced summary-only, never quoted in role outputs.

## Verification

The engine's category derivation, tailoring, matrix rows, coverage, gap
list, owed documents, pack grading, SPAMR skeleton, SPAP maturity and
metrics grading are cross-checked against the bound q80 leaf logic at
build time when the skills library is present (provenance.json records
each comparison: core value, skill value, agrees).
