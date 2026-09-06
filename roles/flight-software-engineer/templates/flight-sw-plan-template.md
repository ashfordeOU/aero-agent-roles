# Flight Software Design and Verification Plan

**Item:** Flight control computer (FCC) flight software
**System:** Fly-by-wire flight control system
**Airframe context:** Transport category airplane
**Certification basis:** DO-178C software life cycle (FAR/CS-25 program context)
**Software level (input):** A
  - Source: FCC system safety assessment - FHA condition 'loss of all rate control' (catastrophic) (this plan does not re-derive the level)
**Target platform:** cFE 6.x on a partitioned vehicle management computer (RTOS with priority ceiling protocol support)
**Status:** draft-for-review

## 1. Item and software architecture

The flight control computer application software implements the pitch/roll rate control laws of the fly-by-wire flight control system on the vehicle management computer: sensor acquisition, rate-loop control, guidance steering, health monitoring and fault response, plus telemetry of control and guidance outputs to the ground. This plan covers the software design (component model, dispatch schedule, software bus command/telemetry design, process scheduling, shared-resource access control) and the verification plan for the item.

Times are in milliseconds. The rate groups of the component model (200/100/50 Hz) drive the periodic processes analyzed in section 4, whose periods are 5/10/20 ms; the shared data stores of section 5 are the protected resources of the priority ceiling protocol analysis. Software bus message IDs follow the classic 16-bit layout: app tag in the upper byte, message number in the lower byte.

The software architecture follows the layered flight software pattern: each layer below has one responsibility, and application software never calls the real-time OS directly.

| Layer | Role |
|---|---|
| PSP | board-specific support (clock, memory, console); one PSP per target processor |
| OSAL | RTOS abstraction (tasks, semaphores, queues, mutexes); apps never call the RTOS directly |
| cFE services | executive, software bus, event, table, time and file services |
| Flight applications | ControlLaw, Guidance, HealthMon, TelemetryMux, FaultResponse |

Application inventory (each application is structured as a component and owns periodic processes):

| Application | Function | Component kind | Period (ms) |
|---|---|---|---|
| ControlLaw | rate-loop control law | active | 5 |
| Guidance | guidance steering target | active | 10 |
| HealthMon | health monitoring and fault annunciation | queued | 20 |
| TelemetryMux | telemetry multiplexing of control/guidance samples | queued | 10 |
| FaultResponse | fault response logic | passive | 20 |

## 2. Component design model and dispatch schedule

The item is decomposed into components of the supported kinds (active owns a thread and queue, queued owns a queue without a thread, passive runs inline in the caller context). Typed ports carry one payload type; commands are registered per component with unique opcodes in 0x0000..0xFFFF and require a queue, so passive components declare none and every active component declares at least one input port. Telemetry channels carry typed samples with a monotonic per-channel sequence counter.

Component inventory: **6 total** (2 active, 2 queued, 2 passive), **4 connections**, **3 rate group(s)**, **2 command opcode(s)**, **4 telemetry channel(s)**, **2 event(s)**.

Rate-group dispatch schedule: the master clock runs at the fastest declared group rate (**200 Hz** by default), and each group ticks its input ports every max(1, round(base_hz / hz)) master ticks (one tick = 5 ms at 200 Hz).

| Rate group | hz | Period (ticks) | Period (ms) |
|---|---|---|---|
| RG200 | 200 | 1 | 5 |
| RG100 | 100 | 2 | 10 |
| RG50 | 50 | 4 | 20 |

Topology validation: **clean** — 0 issues, 0 warnings. Every active/queued input port has exactly one dispatch driver (one incoming connection or one rate group); connections run output to input with matching data types and no self-loops; command opcodes are unique.

## 3. Software bus command and telemetry design

Inter-application command and telemetry traffic rides the software bus publish/subscribe model. Message IDs are 16-bit (0x0000-0xFFFF): **65536 total IDs**, with the command band 0x0000-0x0FFF (**4096 IDs**) and the telemetry band 0x1000-0xFFFF (**61440 IDs**) by convention. The upper bits carry the app tag and the lower bits the message number; the plan allocates one block per application and validates every ID against its band.

Command/telemetry catalog (per 20 ms integration frame):

| Application | Command msg ID | Telemetry msg ID | Band check | msgs/cycle | Activations/frame | msgs/frame | Seq per frame |
|---|---|---|---|---|---|---|---|
| ControlLaw | 0x0101 | 0x1101 | OK | 1 | 4 | 4 | 0..3 |
| Guidance | 0x0201 | 0x1201 | OK | 1 | 2 | 2 | 0..1 |
| HealthMon | 0x0301 | 0x1301 | OK | 1 | 1 | 1 | 0..0 |
| TelemetryMux | none | 0x1401 | OK | 2 | 2 | 4 | 0..3 |
| FaultResponse | none | 0x1501 | OK | 1 | 1 | 1 | 0..0 |

**Total software bus telemetry load: 12 messages per 20 ms integration frame (600 per second).**

Every telemetry message carries a monotonic sequence counter per message ID (the frame budget above), so the ground station can detect dropped packets from counter gaps. Event service entries carry one of the severities DEBUG, INFO, EVENT, ERROR, CRITICAL.

## 4. Process scheduling analysis

The periodic processes of the rate-group schedule form a (C, T) task set with implicit deadlines (D = T) in one time unit; shorter period means higher priority under rate-monotonic (RM) scheduling.

| Process | C (ms) | T (ms) | Utilization share |
|---|---|---|---|
| ControlLaw | 1 | 5 | 0.2 |
| Guidance | 2 | 10 | 0.2 |
| HealthMon | 3 | 20 | 0.15 |

**Processor utilization U = sum(C_i / T_i) = 0.55.** Liu-Layland sufficient bound for 3 tasks: U_rm(3) = 0.779763 (decreasing toward ln 2 ~ 0.693 as n grows).

Utilization bound test: U = 0.55 <= U_rm(3) = 0.779763 -> **RM feasibility guaranteed by the bound**.

Exact response-time analysis (fixed point of R_i = C_i + sum over higher-priority j of ceil(R_i / T_j) * C_j):

| Process | R_i (ms) | T_i (ms) | Margin (ms) | Feasible |
|---|---|---|---|---|
| ControlLaw | 1 | 5 | 4 | YES |
| Guidance | 3 | 10 | 7 | YES |
| HealthMon | 7 | 20 | 13 | YES |

**RM feasibility: YES.** EDF feasibility (implicit deadlines, U <= 1 necessary and sufficient): **YES**. Scheduling verdict: **RM-guaranteed-by-UB**.

## 5. Shared-resource access control design

Shared data stores are protected resources under the priority ceiling protocol. Each task is a {C, T, priority} model (higher number = higher priority, matching the RM order: the shortest period process has priority 3). The ceiling of a resource is the highest priority among the tasks that lock it; under the ceiling rule a task is blocked by at most one lower-priority critical section, and only on a resource whose ceiling is at least its priority.

| Resource | Protected data | Ceiling (priority) |
|---|---|---|
| attitude-state-store | attitude/rate state shared by the rate loop and the health monitor | 3 |
| command-buffer | command buffer shared by guidance and the health monitor | 2 |

| Process | C (ms) | T (ms) | Priority | Blocking B (ms) | R with blocking (ms) | Margin (ms) | Feasible |
|---|---|---|---|---|---|---|---|
| ControlLaw | 1 | 5 | 3 | 0.6 | 1.6 | 3.4 | YES |
| Guidance | 2 | 10 | 2 | 0.7 | 3.7 | 6.3 | YES |
| HealthMon | 3 | 20 | 1 | 0 | 7 | 13 | YES |

**Schedulability with blocking: FEASIBLE.** Empty-lock identity (no locks -> zero blocking and the plain response-time analysis): **holds**.

## 6. Verification plan

Verification activities are requirements-based and mapped to the design stages above; each carries a pass criterion from the design discipline it verifies (software bus routing and telemetry continuity, component and dispatch-driver rules, scheduling verdicts, blocking analysis).

| ID | Stage | Activity | Method | Pass criterion | Leaf |
|---|---|---|---|---|---|
| V-01 | Software bus routing | Software bus publish/subscribe routing verification | deterministic simulation (register, subscribe, publish, route) | every app receives only its subscribed message IDs, in publish order; publish to an unknown message ID is rejected | avionics/fsw/cfs-architecture |
| V-02 | Telemetry pipeline | Telemetry sequence-counter continuity check | stamped pipeline run per message ID | sequence counters are monotonic per message ID with no gaps, so the ground station can detect drops | avionics/fsw/cfs-architecture |
| V-03 | Event reporting | Event service severity conformance | event log audit | every event entry carries one of DEBUG, INFO, EVENT, ERROR, CRITICAL; unknown severities are rejected | avionics/fsw/cfs-architecture |
| V-04 | Component model | Component definition conformance | validate_component on every declared component | active components declare >= 1 input port; passive components declare no commands; command opcodes unique in 0x0000..0xFFFF; telemetry types and event severities from the supported sets | avionics/fsw/fprime-component |
| V-05 | Component model | Connection and dispatch-driver coverage | validate_connections + validate_rate_groups on the topology | connections run output to input with matching types (serial matches any), no self-loops; every active/queued input port has exactly one dispatch driver | avionics/fsw/fprime-component |
| V-06 | Dispatch schedule | Rate-group schedule and clocked dispatch determinism | deterministic clocked simulation over the master clock | groups tick their input ports every max(1, round(base_hz / hz)) master ticks; invocations, deliveries and telemetry samples are deterministic with monotonic per-channel sequence counters | avionics/fsw/fprime-component |
| V-07 | Scheduling analysis | Rate-monotonic schedulability verdict | utilization bound test + exact response-time analysis | U <= U_rm(n) guarantees RM feasibility; otherwise every converged response time R_i must satisfy R_i <= T_i (divergence means RM-infeasible); EDF feasible iff U <= 1 | avionics/fsw/real-time-scheduling |
| V-08 | Scheduling analysis | Scheduling analysis contract tests | run scripts/test_real_time_scheduling.py (35 cases) | all 35 contract cases pass offline: Liu-Layland anchors, worked task sets A/B/C, divergence detection, ValueError rejection of non-physical inputs | avionics/fsw/real-time-scheduling |
| V-09 | Resource access control | Priority ceiling and blocking verification | ceiling map + blocking times audit against the lock register | each resource ceiling equals the highest priority among its lockers; blocking is the longest qualifying lower-priority critical section (never a sum) | avionics/fsw/shared-resource-access-control |
| V-10 | Resource access control | Response-time-with-blocking feasibility | fixed-point analysis with the blocking term | every response time R_i = C_i + B_i + sum of higher-priority preemption load is at most T_i within 1e-9 relative slack; empty-lock identity: with no locks the analysis equals the plain response-time analysis | avionics/fsw/shared-resource-access-control |
| V-11 | Resource access control | Resource access contract tests | run scripts/test_shared_resource_access_control.py (35 cases) | all 35 contract cases pass offline: anchor ceilings, blocking truth table, fixed-point convergence, empty-lock identity, ValueError rejection of every non-physical input | avionics/fsw/shared-resource-access-control |

Deterministic contract-test baseline (stdlib unittest, offline):

| Leaf | Command | Cases |
|---|---|---|
| avionics/fsw/cfs-architecture | `python3 scripts/test_cfs_architecture.py` | 15 |
| avionics/fsw/fprime-component | `python3 scripts/test_fprime_component.py` | 35 |
| avionics/fsw/real-time-scheduling | `python3 scripts/test_real_time_scheduling.py` | 35 |
| avionics/fsw/shared-resource-access-control | `python3 scripts/test_shared_resource_access_control.py` | 35 |

The plan addresses the DO-178C life-cycle planning areas at summary level (planning of software development and verification; software development standards; software verification (reviews, analyses, requirements-based tests); configuration management and change control; software life cycle data); the certification plan itself (PSAC), structural coverage targets per level, tool qualification and the level/severity evidence trail belong to the DO-178C certification engineer role. This plan never asserts those results.

## 7. Open items and sign-off

Open items to close before the human flight software engineer reviews this draft:

- None blocking: component topology is clean, the process set is RM-feasible with margins, and the shared-resource analysis with blocking is feasible.
- Software level A is an INPUT from the system safety assessment (FCC system safety assessment - FHA condition 'loss of all rate control' (catastrophic)) and must be confirmed against the DO-178C planning flow before any certification activity.

---
*Generated by Aero Agent Roles flight-software-engineer core (2026-09-06). DRAFT for human flight software engineering review. Not an approval document, not a certification finding, and not a regulatory sign-off.*