# AS9100 Quality Management System Audit Report

**Site:** Meridian Aerospace Components (Fab plant 2)
**Standard:** AS9100D (referenced summary-only; no standard text reproduced)
**Audit period:** 2026-08-04 to 2026-09-04
**Audit lead:** Q. Nguyen (quality engineer, audit lead)
**Status:** draft-for-review

## 1. Scope and audit basis

This report audits the numerical quality evidence behind the site's quality management system: measurement systems analysis records, statistical process control records, and acceptance-sampling release evidence for the audit period. Every result below is computed by the role engine from the raw datasets listed; nothing is asserted without a computed number.

- Criteria: AS9100D clauses as summarized in the site audit matrix; Cpk >= 1.33 for key characteristics (per PO-7712 clause 4.2).
- Measurement-system acceptance criteria: <10% acceptable, 10-30% conditional, >30% unacceptable (AIAG-style practice); site procedure QP-7.1.5: 10% max for key-characteristic gages.
- Inspector agreement bands: kappa >= 0.75 good, 0.40-0.75 marginal, < 0.40 poor.
- Records reviewed: all 41 active gage master/calibration records reviewed (100% census).
- Datasets analyzed:

  - gage R&R ANOVA study: 3 inspectors x 10 parts x 3 trials on KC-001 bore micrometer G-077
  - gage R&R range-method re-analysis of the same 90 readings
  - gage bias/linearity: 5 reference levels, micrometer G-112
  - attribute agreement: 3 inspectors x 30 go/no-go parts
  - SPC X-bar/R: 20 subgroups of 5, KC-002 pin diameter
  - SPC I-MR: 30 lot coating-thickness values
  - small-shift CUSUM/EWMA: 25 bore-deviation observations
  - attribute p-chart: 20 lots x 200 units
  - acceptance records: attribute lot 500 and variables lot 1500 release records

## 2. Executive summary

| Clause | Audit area | Result |
|---|---|---|
| 4.4 | QMS and its processes | conforming |
| 7.1.5.1 | Monitoring and measuring resources (general) | minor nonconformity |
| 7.1.5.2 | Measurement traceability | minor nonconformity |
| 8.5.1 | Control of production and service provision | minor nonconformity |
| 8.6 | Release of products and services | conforming |
| 9.1.1 | Monitoring, measurement, analysis and evaluation | conforming |

Findings: 3 minor nonconformity(ies), 2 observation(s)/opportunities for improvement; 0 major.

## 3. Measurement systems analysis audit

### 3.1 Gage R&R - ANOVA (KC-001 bore micrometer G-077)

Study layout: 3 inspectors x 10 parts x 3 trials. Two-way random-effects ANOVA on 90 readings.

| Quantity | Value |
|---|---|
| %GRR (ANOVA) | 11.05% |
| Verdict (10/30 band) | conditional |
| Number of distinct categories (ndc) | 12 |
| Repeatability EV / Reproducibility AV / Interaction IV | 0.0044 / 0.0022 / 0.0018 mm |
| Part variation PV / Total variation TV | 0.0468 / 0.0471 mm |

### 3.2 Gage R&R - independent range-method estimator

The same 90 readings re-analyzed with the AIAG range method (5.15-sigma constants) as an independent estimator:

| Quantity | Value |
|---|---|
| %GRR (range method) | 10.68% |
| Verdict (10/30 band) | conditional |
| ndc | 13 |
| EV / AV / GRR | 0.0219 / 0.0122 / 0.0251 mm |
| Dual-method agreement | 0.37 percentage points |

### 3.3 Gage bias and linearity (micrometer G-112)

| Reference (mm) | Bias (mm) | Bias % of reference |
|---|---|---|

| Statistic | Value |
|---|---|
| Mean bias | +0.0218 mm |
| Linearity slope (bias vs reference) | +0.00188 mm/mm |
| Regression R-squared | 0.9941 |
| Bias significance t (df 4) | 3.27 vs t crit 2.78 -> significant |
| Worst per-level | 0.168% at 25.0 mm (band 10%) |
| Overall verdict | REVIEW |

### 3.4 Attribute agreement analysis

Layout: 3 inspectors x 30 go/no-go parts.

| Statistic | Value |
|---|---|
| Fleiss kappa | 0.33 |
| Observed agreement (P-bar) | 84.4% |
| Chance agreement (P-e) | 76.9% |
| Verdict | poor |
| Pairwise inspector A-B re-check | agreement 80.0%, kappa 0.14 |

## 4. Statistical process control audit

### 4.1 X-bar/R and capability (KC-002 pin diameter 6.000 mm)

| Statistic | Value |
|---|---|
| Subgroups (n=5) | 20 |
| Center line x-bar / R-bar | 6.0007 mm / 0.00875 mm |
| X-bar UCL / LCL | 6.00575 / 5.99566 mm |
| R UCL / LCL | 0.01850 / 0.00000 mm |
| Process sigma (R-bar/d2) | 0.00376 mm |
| Cp / Cpu / Cpl / Cpk | 1.33 / 1.27 / 1.39 / 1.27 |
| Western Electric rule violations | none |
| Chart verdict | in-control |

### 4.2 I-MR chart (coating thickness per lot)

| Statistic | Value |
|---|---|
| Lots plotted | 30 |
| Mean / average moving range | 120.90 / 1.59 um |
| Individuals UCL / LCL | 125.14 / 116.67 um |
| Moving-range UCL | 5.20 um |
| Flagged lots (individuals) | 17 |
| Chart verdict | out-of-control |

### 4.3 CUSUM / EWMA small-shift surveillance

| Statistic | Value |
|---|---|
| Observations reviewed | 25 |
| CUSUM signal | no |
| EWMA signal | no |
| First signal (1-based sample) | none |

### 4.4 p-chart (final-lot nonconforming fraction)

| Statistic | Value |
|---|---|
| Subgroups (n=200) | 20 |
| p-bar | 0.0123 |
| UCL / LCL | 0.0356 / 0.0000 |
| Flagged subgroups | none |
| Verdict | in-control |

## 5. Acceptance sampling audit

### 5.1 Attribute plan (release lots)

Basis: reduced reference table in the style of ANSI/ASQ Z1.4, single sampling, normal inspection, level II.

| Plan element | Value |
|---|---|
| Lot size / inspection level / AQL | 500 / II / 1.0 |
| Sample size code letter | J |
| Plan (n, Ac, Re) | (80, 2, 3) |
| Nonconforming found in sample | 1 |
| Lot decision | accept |
| OC probability at AQL | 0.9534 |
| Producer risk (1 - Pa at AQL) | 4.66% |
| OC probability at 4% nonconforming | 0.3748 |

### 5.2 Variables plan (k-method, single USL)

Basis: reduced k-method reference table in the style of ANSI/ASQ Z1.9, single specification limit, sigma unknown.

| Plan element | Value |
|---|---|
| Lot size / AQL / USL | 1500 / 1.0 / 25.150 mm |
| Code letter / sample n | J / 35 |
| Acceptability constant k / max % nonconforming M | 1.62 / 3.33 |
| Sample mean / standard deviation | 25.1020 / 0.0098 mm |
| Q = (USL - x-bar)/s | 4.90 |
| Estimated % nonconforming above USL | 4.84e-05% |
| k-method decision (Q >= k) | accept |

## 6. Findings

### NC-01 - MINOR (clause 7.1.5.2)

**Title:** Significant mean bias on inspection micrometer G-112 not addressed in calibration records
**Objective evidence:** bias/linearity study over 5 reference levels 5.000-25.000 mm: mean bias +0.0218 mm, t = 3.27 vs two-sided 95% t critical 2.78 (df 4), overall verdict REVIEW; per-level |bias| <= 0.17% of reference (band 10%), so linearity itself is inside the band but the consistent offset is statistically significant
**Requirement reference (summary):** Monitoring and measuring resources must be calibrated or verified at defined intervals; a statistically significant measurement bias makes measurement results suspect and must be corrected or its validity assessed before the gage supports acceptance decisions.
**Objective evidence reference:** bias/linearity study BL-2026-07, gage G-112
**Disposition status:** open - corrective action is the site's responsibility; this report does not close findings.

### NC-02 - MINOR (clause 7.1.5.1)

**Title:** Poor inspector agreement on attribute (go/no-go) acceptance judgments
**Objective evidence:** Fleiss kappa 0.33 (poor band < 0.40) across 3 inspectors x 30 parts; observed agreement 84.4%, chance agreement 76.9%; pairwise inspector A-B re-check: observed agreement 80.0%, kappa 0.14
**Requirement reference (summary):** The inspection/verification activity that supports product acceptance must be reliable; attribute acceptance decisions made by inspectors who agree only at chance level do not provide objective evidence of conformance.
**Objective evidence reference:** attribute agreement study AA-2026-08
**Disposition status:** open - corrective action is the site's responsibility; this report does not close findings.

### NC-03 - MINOR (clause 8.5.1)

**Title:** Out-of-control coating lot released with no recorded reaction
**Objective evidence:** I-MR chart over 30 lots: lot 17 at 134.8 um exceeds the individuals UCL 125.1 um (mean 120.90 um, average moving range 1.59 um, MR UCL 5.20 um); chart verdict out-of-control and no reaction/disposition record was found in the SPC log for the flagged lot(s) 17
**Requirement reference (summary):** Production must be carried out under controlled conditions; when process control charts signal an out-of-control condition the organization must react and determine whether the output remains conforming before release.
**Objective evidence reference:** SPC log CL-2026-08, anodize line 2
**Disposition status:** open - corrective action is the site's responsibility; this report does not close findings.

### OFI-01 - OBSERVATION (clause 8.5.1)

**Title:** KC-002 key-characteristic capability below the flow-down Cpk requirement
**Objective evidence:** X-bar/R chart in control (no Western Electric rule violations over 20 subgroups of 5) with Cp 1.33 but Cpk 1.27 (Cpu 1.27, Cpl 1.39) against 6.000 +/- 0.015 mm; the flow-down requires Cpk >= 1.33 - the chart is stable but the process center is off-nominal, so the acceptance margin is eroded
**Requirement reference (summary):** No requirement breach: the process is stable and in spec. Opportunity: recenter the process or review the flow-down acceptance evidence for KC-002 before the next release lot.
**Objective evidence reference:** SPC log KC-002, 2026-08
**Disposition status:** open - corrective action is the site's responsibility; this report does not close findings.

### OFI-02 - OBSERVATION (clause 7.1.5.1)

**Title:** Bore micrometer G-077 measurement error on the conditional band for a key-characteristic gage
**Objective evidence:** ANOVA gage R&R: %GRR 11.05% (ndc 12) and independent range-method estimate 10.68% (ndc 13) both fall in the conditional 10-30% band; the two estimators agree to 0.37 percentage points, so the estimate is robust, but the site procedure QP-7.1.5 allows <= 10% for key-characteristic gages and no application justification was found in the MSA records
**Requirement reference (summary):** No requirement breach beyond the procedure criterion. Opportunity: improve the measurement method (fixturing, resolution, training) or document the specific-application justification for the conditional system.
**Objective evidence reference:** MSA study GRR-2026-06, gage G-077
**Disposition status:** open - corrective action is the site's responsibility; this report does not close findings.

## 7. Clause conformance summary

| Clause | Audit area | Status | Evidence (computed) |
|---|---|---|---|
| 4.4 | QMS and its processes | conforming | All 41 active gage master/calibration records reviewed (100% census): records current, revision-controlled, and traceable to the gage register; no record-level gaps found |
| 7.1.5.1 | Monitoring and measuring resources (general) | minor nonconformity | Attribute agreement study poor (kappa 0.33); bore micrometer %GRR 11.05% conditional (range method 10.68%) |
| 7.1.5.2 | Measurement traceability | minor nonconformity | Calibration records complete; micrometer G-112 bias significant (mean bias +0.0218 mm, overall REVIEW) |
| 8.5.1 | Control of production and service provision | minor nonconformity | I-MR chart out of control at coating lot 17 with no reaction record; KC-002 X-bar/R stable with Cpk 1.27 below the 1.33 flow-down |
| 8.6 | Release of products and services | conforming | Attribute plan (n=80, Ac=2, Re=3) at AQL 1.0 executed correctly: 1 nonconforming found -> accept; OC probability 0.9534 at AQL (producer risk 4.66%); variables k-method plan (n=35, k=1.62): Q=4.90 >= k -> accept, estimated nonconforming 4.84e-05% vs max M=3.33% |
| 9.1.1 | Monitoring, measurement, analysis and evaluation | conforming | Small-shift surveillance active: CUSUM and EWMA charts on 25 bore-deviation observations produced no signal; p-chart over 20 lots in control (pbar 0.0123) |

## 8. Limitations and boundaries

- Datasets are the site's own records; conclusions hold only for the samples and periods listed in section 1.
- Classification criteria are summarized from the site's audit procedure; severity reflects released-product and systemic impact evidence only.
- Findings remain open pending the site's corrective action; this report does not issue, close, or waive any finding.

---
*Generated by Aero Agent Roles quality-management-engineer core (2026-09-06). DRAFT for human quality-management review. Not an approval document. This report is not a certification decision and does not constitute AS9100 certification or a registrar finding.*
