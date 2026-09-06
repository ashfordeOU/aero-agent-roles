# System Model Architecture and MBSE Plan

**System:** Cabin Pressure Control System (CPCS)
**Development assurance level:** B (from hazardous failure condition, system safety reference FHA-CPCS-001 / PSSA rev B)
**Modeling standard:** ARP4754A (development process context)
**Model baseline:** CPCS-MOD-001 Rev A
**Status:** draft-for-review

## 1. Scope

This plan defines the system model architecture and the model-based systems engineering (MBSE) approach for Cabin Pressure Control System (CPCS). DAL-B cabin pressure control system model built to ARP4754A development-assurance context; the model is the primary requirements and architecture artifact.
The model is developed to development assurance level B (FDAL), so traceability requires full closure (critical).

## 2. Model architecture (diagram suite)

Diagram kind is selected from the modeling purpose. The suite is:

| Purpose | Diagram kind | Viewpoint |
|---|---|---|
| system-composition | bdd (block definition diagram) | structure |
| internal-structure | ibd (internal block diagram) | structure |
| requirements-capture | req (requirements diagram) | requirements |
| requirements-traceability | req (requirements diagram) | requirements |
| constraint-analysis | param (parametric diagram) | parametric |
| functional-flow | act (activity diagram) | behavior |
| state-transition | stm (state machine diagram) | behavior |
| message-ordering | seq (sequence diagram) | behavior |
| use-case-scoping | uc (use case diagram) | behavior |
| model-organization | pkg (package diagram) | structure |

Diagram selection is consistent: 10/10 purposes resolve to their canonical SysML diagram kind.

## 3. Viewpoint coverage

| Viewpoint | Covered by |
|---|---|
| structure | bdd, ibd, pkg |
| behavior | act, seq, stm, uc |
| requirements | req |
| parametric | param |

Viewpoint coverage verdict: **complete** (all four required viewpoints present).

## 4. Requirements architecture

The requirement set holds 5 requirements. Quality screening: 5/5 verifiable (one shall clause, no vague terms, mapped verification method).

- **CPCS-001** [functional, priority 1, analysis]: The CPCS shall maintain cabin pressure altitude at or below 8000 feet during normal cruise operation. — verifiable (1 shall clause, no vague terms)
- **CPCS-002** [functional, priority 1, test]: The CPCS shall command the outflow valve to full open when cabin altitude exceeds 10000 feet. — verifiable (1 shall clause, no vague terms)
- **CPCS-003** [functional, priority 2, test]: The CPCS shall alert the flight crew when cabin altitude exceeds 9500 feet. — verifiable (1 shall clause, no vague terms)
- **CPCS-004** [performance, priority 2, analysis]: The CPCS shall limit cabin pressure excursions to 0.05 psi above the scheduled cabin pressure. — verifiable (1 shall clause, no vague terms)
- **CPCS-005** [constraint, priority 1, demonstration]: The CPCS shall open the safety valve automatically when cabin differential pressure exceeds 8.5 psi. — verifiable (1 shall clause, no vague terms)

Derive relationships: valid (1 derive link checked; no self-derive, all ids canonical).

- Satisfy coverage: 100.0% (5/5 requirements satisfied by a design element).
- Verify coverage: 100.0% (5/5 requirements linked to a verification item).
- Verification status roll-up (requirement tree): **verified**.

## 5. Functional and logical architecture

Functions are allocated to the design elements of the logical architecture:

| Function | Allocated to |
|---|---|
| sense-cabin-pressure | Pressure Sensor Package |
| schedule-pressure-target | Cabin Pressure Controller |
| position-outflow-valve | Outflow Valve Assembly |
| open-safety-valve | Safety Valve Assembly |
| alert-crew | Cabin Pressure Controller |

Allocation closure: closed (5/5 functions allocated).

Concept decision record (weighted criteria, weights sum to 1.0):

- **Centralized digital controller** (CON-A): weighted score 7.60
- **Distributed smart actuators** (CON-B): weighted score 6.80
- Selection: winner Centralized digital controller with margin 0.80 (confident; traceable to requirements).

Toolchain mapping (open source, per MBSE task):

- requirements-modeling: papyrus
- functional-architecture: capella
- architecture-analysis: osate

## 6. Block definition and internal structure

The block definition diagram declares the block hierarchy; every element the model references must have a block definition:

- CPCS
- Cabin Pressure Controller
- Outflow Valve Assembly
- Safety Valve Assembly
- Pressure Sensor Package

Block definition verdict: **valid** (5 referenced element(s), 0 without a definition).

## 7. Interface model (N2)

The N2 matrix arranges the components on the diagonal; cell (i, j) counts the interfaces from component i to component j. Total interfaces modeled: 4.

| Component | Interface count (out + in) |
|---|---|
| Cabin Pressure Controller | 4 |
| Outflow Valve Assembly | 2 |
| Safety Valve Assembly | 1 |
| Pressure Sensor Package | 1 |

Required data links: 4/4 modeled. Isolated components (no interfaces): none.

## 8. Behavioral model

The state machine models 4 states (initial state Standby) and 6 transitions:

- Standby --auto_engage-> Auto
- Auto --fault_detected-> Fault
- Auto --manual_override-> Manual
- Manual --auto_engage-> Auto
- Manual --fault_detected-> Fault
- Fault --reset-> Standby

Reachability from Standby: 4/4 states reachable; unreachable: none.
Transition conflicts: none.

## 9. Parametric constraints

Constraint equations are bound to block value properties; each constraint below is evaluated on the model:

- **CPCS mass budget**: 4.2 kg + 12.8 kg + 6.5 kg + 0.9 kg = 24.4 kg <= bound 30 kg — verdict: satisfied, margin +5.60 kg, utilization 81.3% of bound.
- **CPCS electrical power budget**: 35 W + 42 W + 18 W + 6 W = 101 W <= bound 120 W — verdict: satisfied, margin +19.00 W, utilization 84.2% of bound.

Parametric constraints satisfied: 2/2.

## 10. Traceability and model review

Traceability closure: **closed** (full closure (critical)). Every requirement is linked through its satisfying design element to a verification item.
Model review verdict: **ready** (satisfy coverage 100.0%, verify coverage 100.0%, roll-up verified).

## 11. Model governance

- Model baseline: CPCS-MOD-001 Rev A (configuration-managed model artifact, CM owner: systems engineering).
- Diagram content and traceability are reviewed like any other engineering data in the development process.
- Toolchain: papyrus, capella, osate.
- Open items for the next modeling review: none.

---
*Generated by Aero Agent Roles mbse-modeling-engineer core (2026-09-06). DRAFT for human systems-engineering review. Not an approval document.*
