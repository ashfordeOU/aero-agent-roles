# AS9100 Internal Audit Findings Report

**Supplier:** AeroForge Precision Machining, LLC
**Audit date:** 2026-09-05
**Auditor:** M. Reyes (independent of area owner J. Torres: yes)
**Status:** draft-for-review

## Audit plan

- Audit scope: CNC machining and production control (8.5.1), inspection and test (8.6), calibration control (7.1.5), nonconformance disposition (8.7), corrective action (10.2).
- Criteria: AS9100D clauses (6.1, 7.1.5, 8.1.2, 8.6, 8.7, 10.2), customer requirements flow-down, PO-7712.
- Audit team: M. Reyes (lead auditor).
- Process risk category: high; next audit due 2027-03-05 (risk-scaled 12-month base interval).
- Records sampled: 20 of 400 records sampled at 0.95 confidence (square-root rule).

## Findings summary

- Major nonconformities: 2
- Minor nonconformities: 2
- Observations (opportunities for improvement): 1
- Total findings: 5
- AS9100D clauses cited: 10.2, 6.1, 7.1.5, 8.1.2, 8.7.

## Findings report

### Nonconformities

| NC ID | Clause | Classification | Objective evidence | Requirement |
|---|---|---|---|---|
| NC-01 | 8.7 | major | NCR-2214: bracket P/N BN-4470-2 (safety-critical, flight control linkage) dispositioned use-as-is by the supplier MRB; no customer waiver on file and the disposition record has no customer-approval entry. Twelve brackets of the same lot shipped under delivery DLV-3390. | Nonconforming output must be identified, segregated, and dispositioned by an authorized authority; use-as-is outside the original specification requires customer approval. |
| NC-02 | 10.2 | major | NCR-2210/2211/2214 record the same oversize-bore characteristic within six months. CAPA-118 was closed with effectiveness evidence restating the root cause rather than an observed result. | On nonconformity, the organization must react, evaluate the need for action to eliminate the cause so it does not recur, and verify the effectiveness of the action taken. |
| NC-03 | 7.1.5 | minor | Torque wrench TQ-009 in the assembly tool crib carried a calibration sticker due 2026-08-30; the crib sign-out log shows no issue after the sticker expiry date. | Monitoring and measuring resources must be calibrated or verified at defined intervals; suspect measurements must be assessed for validity. |
| NC-04 | 8.1.2 | minor | ECO-4821 (drawing BN-4470 rev A to rev B) approved 2026-08-10; the configuration baseline register entry for BN-4470 still shows rev A as of the audit date. No nonconforming product resulted. | Configuration management must establish and maintain a configuration baseline and control changes to it. |
| NC-05 | 6.1 | observation | The operational risk register is complete and current; mitigation actions for the coating process change are recorded but no residual RPN re-score follows the recorded reductions. | No violation found; the register meets clause 6.1. Re-scoring residual risk closes the mitigation loop demonstrated elsewhere in the QMS. |

### Finding details

#### NC-01 - MAJOR (clause 8.7)

**Title:** Use-as-is disposition on a safety-critical part without customer approval
**Classification rationale:** severity impact 5 is 4-5, which is a major nonconformity.
**Objective evidence:** NCR-2214: bracket P/N BN-4470-2 (safety-critical, flight control linkage) dispositioned use-as-is by the supplier MRB; no customer waiver on file and the disposition record has no customer-approval entry. Twelve brackets of the same lot shipped under delivery DLV-3390.
**Requirement violated:** Nonconforming output must be identified, segregated, and dispositioned by an authorized authority; use-as-is outside the original specification requires customer approval.

Corrective-action record (closure chain status: effectiveness-pending):
- Containment: Quarantine the twelve shipped brackets of lot 2214B at the customer site; suspend MRB use-as-is disposition until the procedure is corrected.
- Root cause: The MRB disposition procedure has no customer-approval step for use-as-is > The procedure was written when the MRB handled non-aerospace parts only > Customer approval flow was never added when the aerospace order book opened > No checklist gate sits between the disposition decision and product release
- Corrective action: Revise the disposition procedure to require customer approval before any use-as-is release and add a release checklist gate; retrain the MRB board.
- Effectiveness evidence: pending - not yet recorded

#### NC-02 - MAJOR (clause 10.2)

**Title:** Recurring nonconformity with no root cause or effectiveness verification
**Classification rationale:** severity impact 3 with systemic spread, which escalates a minor to a major nonconformity.
**Objective evidence:** NCR-2210/2211/2214 record the same oversize-bore characteristic within six months. CAPA-118 was closed with effectiveness evidence restating the root cause rather than an observed result.
**Requirement violated:** On nonconformity, the organization must react, evaluate the need for action to eliminate the cause so it does not recur, and verify the effectiveness of the action taken.

Corrective-action record (closure chain status: effectiveness-pending):
- Containment: 100% bore inspection of the affected part numbers in stock and in work.
- Root cause: Tool wear compensation is not verified between operator shifts > The compensation check is a manual step with no scheduled trigger > The CNC program pauses at shift change but no measurement is required before restart
- Corrective action: Add an in-process bore measurement gate at every shift change, tied to the SPC record for the characteristic.
- Effectiveness evidence: pending - not yet recorded

#### NC-03 - MINOR (clause 7.1.5)

**Title:** Calibration sticker expired on a torque wrench in the tool crib
**Classification rationale:** severity impact 2 is 2-3 with no systemic spread, which is a minor nonconformity.
**Objective evidence:** Torque wrench TQ-009 in the assembly tool crib carried a calibration sticker due 2026-08-30; the crib sign-out log shows no issue after the sticker expiry date.
**Requirement violated:** Monitoring and measuring resources must be calibrated or verified at defined intervals; suspect measurements must be assessed for validity.

Corrective-action record (closure chain status: effectiveness-pending):
- Containment: Remove TQ-009 to calibration; verify the sign-out log to bound the period of possible use.
- Root cause: No recall alert fired when the interval expired > Calibration due dates are tracked on a paper log reviewed monthly > The monthly review ran two weeks late
- Corrective action: Move calibration due-date tracking to the shop system with an automatic recall alert at interval expiry.
- Effectiveness evidence: pending - not yet recorded

#### NC-04 - MINOR (clause 8.1.2)

**Title:** Configuration baseline register not updated for approved engineering change ECO-4821
**Classification rationale:** severity impact 3 is 2-3 with no systemic spread, which is a minor nonconformity.
**Objective evidence:** ECO-4821 (drawing BN-4470 rev A to rev B) approved 2026-08-10; the configuration baseline register entry for BN-4470 still shows rev A as of the audit date. No nonconforming product resulted.
**Requirement violated:** Configuration management must establish and maintain a configuration baseline and control changes to it.

Corrective-action record (closure chain status: effectiveness-pending):
- Containment: Update the baseline register for BN-4470 rev B; audit open ECOs against the register.
- Root cause: Baseline register updates are batched monthly > No trigger links ECO approval to the register update > The register owner has no change-approval notification
- Corrective action: Link ECO approval records to the baseline register so approved changes update the register at approval time.
- Effectiveness evidence: pending - not yet recorded

#### NC-05 - OBSERVATION (clause 6.1)

**Title:** Opportunity: risk register entries lack post-mitigation residual scoring
**Classification rationale:** severity impact 1 is an opportunity for improvement, reported as an observation.
**Objective evidence:** The operational risk register is complete and current; mitigation actions for the coating process change are recorded but no residual RPN re-score follows the recorded reductions.
**Requirement violated:** No violation found; the register meets clause 6.1. Re-scoring residual risk closes the mitigation loop demonstrated elsewhere in the QMS.

No corrective action required (observation, clause 6.1); improvement tracked separately.

### Observations (no violation found, improvement note)

- NC-05 (clause 6.1): Opportunity: risk register entries lack post-mitigation residual scoring. The operational risk register is complete and current; mitigation actions for the coating process change are recorded but no residual RPN re-score follows the recorded reductions.

### Corrective-action follow-up

| NC ID | Root cause | Containment | Corrective action | Verification | Status |
|---|---|---|---|---|---|
| NC-01 | use-as-is release without customer approval on safety-critical parts | Quarantine the twelve shipped brackets of lot 2214B at the customer site; suspend MRB use-as-is disposition until the procedure is corrected. | Revise the disposition procedure to require customer approval before any use-as-is release and add a release checklist gate; retrain the MRB board. | pending - effectiveness not yet verified | effectiveness-pending |
| NC-02 | oversize-bore recurrence from unverified tool-wear compensation at shift change | 100% bore inspection of the affected part numbers in stock and in work. | Add an in-process bore measurement gate at every shift change, tied to the SPC record for the characteristic. | pending - effectiveness not yet verified | effectiveness-pending |
| NC-03 | expired calibration sticker from a late monthly due-date review | Remove TQ-009 to calibration; verify the sign-out log to bound the period of possible use. | Move calibration due-date tracking to the shop system with an automatic recall alert at interval expiry. | pending - effectiveness not yet verified | effectiveness-pending |
| NC-04 | baseline register updated monthly instead of at ECO approval | Update the baseline register for BN-4470 rev B; audit open ECOs against the register. | Link ECO approval records to the baseline register so approved changes update the register at approval time. | pending - effectiveness not yet verified | effectiveness-pending |
| NC-05 | n/a - observation | n/a - observation | n/a - observation | n/a - observation | observation |

## Closure

- Closure recommendation: PROPOSED - the QA manager signs audit closure; NC-01/02 effectiveness verification at the follow-up audit is required before any closure is recorded.
- No finding is recorded closed: closure requires the corrective action taken, the root cause statement and the effectiveness check all on file (verification gate).

---
*DRAFT - audit evidence report generated by Aero Agent Roles as9100-quality-auditor core (2026-09-05) for human QA review. Not a certification, supplier-approval, or closure decision; the QA manager signs closure.*