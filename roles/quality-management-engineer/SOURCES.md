# SOURCES.md - AS9100 Quality Management Engineer

Standards and documents this role references. Summary-not-copy: see
[STANDARDS.md](../../STANDARDS.md) for the full rule and purchase links.

| Source | Role use | Gated |
|---|---|---|
| AS9100D, Aerospace Quality Management System Requirements (SAE/IAQG) | audit criteria and clause structure (4.4, 7.1.5, 8.5.1, 8.6, 9.1.1), referenced summary-only | true |
| ANSI/ASQ Z1.4 (attribute sampling) | plan structure the acceptance-sampling tables paraphrase (code letters, n/Ac/Re, OC) | true |
| ANSI/ASQ Z1.9 (variables sampling, k-method) | plan structure the variables tables paraphrase (n/k/M, Q statistics) | true |
| AIAG Measurement Systems Analysis (MSA) manual | 10/30 percent-GRR acceptance bands, ndc = 1.41 PV/GRR, range-method K1/K2/K3 constants | false |
| AIAG Statistical Process Control (SPC) manual | A2/D3/D4/d2 chart constants, Western Electric rules, Cp/Cpk practice | false |

The audit-report template in `templates/` is an original synthesis with
all numbers computed by the role core from the example site datasets.
The embedded sampling tables are documented reduced reference tables
"in the style of" Z1.4/Z1.9 (summary values only, per the bound
AeroSkills leaves' own documented convention), never reproductions of
the standards. No proprietary text is reproduced anywhere; clause
numbers are factual identifiers paraphrased as audit criteria.

## Acquisition status

- AS9100D: obtain from SAE International / IAQG (sae.org, iaqg.org);
  reference-only - never quoted in role outputs.
- ANSI/ASQ Z1.4 / Z1.9: obtain from ANSI/ASQ; reduced reference tables
  only (the same documented convention the bound AeroSkills leaves
  ship).
- AIAG manuals: common published summary constants used by the bound
  leaves; no table text reproduced.

## Verification

Role computed anchors are cross-checked against the bound leaf logic
files at dispatch time (provenance.json records core value, skill
value, delta, agrees for all ten bound leaves).
