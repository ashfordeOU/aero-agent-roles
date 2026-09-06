# System Development Assurance and Integration Plan (ARP4754A)

**System:** Primary Flight Control System (PFCS)
**Certification basis:** FAR/CS-25
**Status:** draft-for-review

## 1. Scope and integration context

This plan covers the system Primary Flight Control System (PFCS).
The worked-example PFCS integrates the pitch, roll, yaw damping and trim functions on a FAR/CS-25 transport; function and item development assurance planning follows ARP4754A.
The maximum development assurance level driven by the functions of this system is A; the ARP4754A severity-to-DAL assignment is applied: Catastrophic -> A, Hazardous -> B, Major -> C, Minor -> D, No safety effect -> E.

## 2. Development planning and certification interface

Planning artifacts in scope: certification-plan, system-development-plan, safety-assessment-plan.
Safety assessment depth: full (FHA-PSSA-SSA chain at A/B/C).
The certification plan identifies the applicable certification basis (FAR/CS-25) and the means of compliance for each area; the system development plan drives function and item development; the safety assessment plan interfaces with the ARP4761A process.

## 3. Function development assurance matrix (FDAL)

Each function takes the FDAL of its most severe failure condition (severity rated by effect on the aircraft and occupants, never by failure rate):

| Function | Most severe failure condition | Severity | FDAL |
|---|---|---|---|
| Pitch control | Loss of all pitch control capability | Catastrophic | A |
| Roll control | Loss of all roll control capability | Catastrophic | A |
| Yaw damping | Loss of yaw damping capability | Major | C |
| Trim control | Uncommanded trim motion | Hazardous | B |

The most severe function of this system is assured at FDAL A (Pitch control, Roll control).

## 4. Item development assurance matrix (IDAL)

Each item takes the IDAL of the highest (strictest) FDAL among the functions it implements; no item IDAL is lower than the FDAL of a function it implements without an approved justification:

| Item | Implements functions | IDAL |
|---|---|---|
| Primary Flight Control Computer (PFCC) | Pitch control, Roll control | A (from A, A) |
| Control surface actuation (elevator, aileron) | Pitch control, Roll control | A (from A, A) |
| Yaw damper unit | Yaw damping | C (from C) |
| Trim control unit | Trim control | B (from B) |

The highest item assurance in this system is IDAL A (Primary Flight Control Computer (PFCC), Control surface actuation (elevator, aileron)).

## 5. Function development lifecycle stages

| Stage | Gate | Result |
|---|---|---|
| assurance-assignment | FDAL assigned to each function from its most severe failure condition; item IDAL not lower than the FDAL of the functions it implements | PASS |
| requirements-allocation | every system requirement allocated to one item (no unallocated, no double allocation) | PASS |
| requirements-validation | requirements validated by a recognized method with closure at or above the project threshold (independent at A/B) | PASS |
| traceability-closure | bidirectional traceability srats-hlr-llr-code/test closed with every traced pair verified | PASS |
| integration-verification | every requirement assigned an acceptable verification method for its level, with evidence planned before release | PASS |
| configuration-baselined | requirements, design, verification and analysis data under a versioned baseline with change control recorded | PASS |

## 6. Requirements allocation register

- Total system requirements: 60
- Allocated to items: 60
- Unallocated: 0
- Allocation coverage: 100.0%

Every requirement maps to exactly one item; the grouped register per item supports the item development handoff.

## 7. Requirements traceability matrix

Level inventory: srats=15, hlr=22, llr=23, code=0, test=0.
- Trace links: 68; verified ratio: 1.000
- Trace status: closed
- Derived requirements flagged: 2

Bidirectional closure per level (srats to hlr, hlr to llr, llr to code/test, every traced pair verified) keeps the matrix closed.

## 8. Requirements validation and derived requirements

- Validation entries: 60; closure score: 1.000 (threshold 0.95); ready: True
- Independent validation required at levels A and B.

Derived requirements (no direct parent or source trace) carry a derivation source, rationale and impact analysis and join validation, verification and the trace matrix:

| Derived requirement | Source |
|---|---|
| LLR-FCS-DERIVED-08 | no parent/source trace: derivation source, rationale and impact analysis recorded in requirements data |
| LLR-FCS-DERIVED-17 | no parent/source trace: derivation source, rationale and impact analysis recorded in requirements data |

## 9. Integration verification plan

Verification demonstrates that the implementation satisfies the requirements (built right), separate from validation. Acceptable methods per development assurance level:

| Level | Acceptable methods | Verification independence |
|---|---|---|
| A | test, analysis | independent |
| B | test, analysis | independent |
| C | test, analysis, demonstration | developer OK |
| D | test, analysis, demonstration, inspection | developer OK |
| E | test, analysis, demonstration, inspection | developer OK |

- Verification methods planned for 60 requirement(s); 60 with an acceptable method and evidence obligation recorded.
- Coverage closure: every requirement, allocated or derived, verified by at least one acceptable method before the verification results release.

## 10. Configuration management and change control

Configuration item categories: requirement, design, verification, analysis.
Configuration items under baseline: 71 (requirements, design, verification, analysis data are versioned and frozen).

| Change | Classification | Status |
|---|---|---|
| CR-014 | minor | VERIFIED |
| CR-021 | major | APPROVED |

A change is MAJOR when it touches safety-relevant requirements, interfaces, or certification data; otherwise MINOR. All changes run request -> impact analysis -> classification -> approval -> implementation -> verification and are recorded on the log.

## 11. ARP4754A process objectives coverage

| Objective | Title | Gate in this plan | Status |
|---|---|---|---|
| development-planning | development planning and certification basis established | assurance-assignment | covered |
| assurance-assignment | FDAL/IDAL development assurance assigned from failure-condition severity with propagation justified | assurance-assignment | covered |
| requirements-allocation | system requirements allocated to items and functions | requirements-allocation | covered |
| requirements-validation | requirements validated - the right requirements captured | requirements-validation | covered |
| traceability | bidirectional requirements traceability maintained and verified | traceability-closure | covered |
| derived-requirements | derived requirements identified, sourced and impact-analyzed | requirements-validation | covered |
| integration-verification | implementation verified against requirements by acceptable methods | integration-verification | covered |
| configuration-management | configuration baseline and change control in place | configuration-baselined | covered |

Objective coverage: 8/8 (100.0%).

## 12. Status and sign-off

This plan is a DRAFT for review by the human systems integration engineer and the program sign-off chain. It is not an approval document and carries no regulatory or certification authority.

---
*Generated by Aero Agent Roles systems-integration-engineer core (2026-09-06). DRAFT for human systems integration engineer review. Not an approval document.*
