# SOURCES.md - Flight Software Engineer

Standards and documents this role references. Summary-not-copy: see
[STANDARDS.md](../../STANDARDS.md) for the full rule and purchase links.

| Source | Role use | Gated |
|---|---|---|
| RTCA DO-178C / EUROCAE ED-12C | governing software life cycle for the planning vocabulary (planning, development standards, verification, CM, life cycle data); reference-only, never reproduced | true |

The DO-178C planning areas appear in the plan only as summary-level
placement of the design and verification work. The DO-178C
certification plan itself (PSAC), DAL derivation, structural coverage
targets per level, tool qualification and approval liaison belong to
the do178c-cert-engineer role; this role never claims them.

The quantitative rules the role's core encodes come from the REAL rules
of the bound AeroSkills leaves (all Apache-2.0 open-source knowledge or
public science, summary-not-copy):

| Bound leaf | Contributes | Form of rule |
|---|---|---|
| avionics/fsw/cfs-architecture | cFE/OSAL/PSP layering, classic APP_Init/APP_Execute/APP_Data life cycle, software bus publish/subscribe routing by 16-bit message ID (command band 0x0000-0x0FFF, telemetry band 0x1000-0xFFFF, app tag in the upper bits), monotonic telemetry sequence counters, EVS severities DEBUG..CRITICAL | leaf SKILL.md + scripts/cfs_architecture_logic.py |
| avionics/fsw/fprime-component | component kinds (active/queued/passive), typed ports and payload types, command opcodes unique in 0x0000..0xFFFF, active-needs-input and passive-no-commands rules, telemetry channel types, event severities FATAL..DEBUG, exactly-one dispatch driver per active/queued input port, rate-group master clock (base_hz = fastest group rate; group period = max(1, round(base_hz/hz)) ticks) | leaf SKILL.md + scripts/fprime_component_logic.py |
| avionics/fsw/real-time-scheduling | (C, T) implicit-deadline task set; U = sum(C_i/T_i); Liu-Layland bound U_rm(n) = n(2^(1/n)-1); exact response time R_i = C_i + sum_{j in hp(i)} ceil(R_i/T_j)*C_j; RM feasible iff R_i <= T_i; EDF feasible iff U <= 1 | leaf SKILL.md + scripts/real_time_scheduling_logic.py (public mathematics, Liu and Layland 1973) |
| avionics/fsw/shared-resource-access-control | priority ceiling of a resource = highest priority among its lockers; ceiling rule worst-case blocking = longest cs of any lower-priority task on a resource whose ceiling >= the task priority (at most one such section); response time with blocking R_i = C_i + B_i + sum_{j in hp(i)} ceil(R_i/T_j)*C_j; feasible iff R_i <= T_i within 1e-9 | leaf SKILL.md + scripts/shared_resource_access_control_logic.py (public priority ceiling methodology) |

The template in `templates/` is an original structure produced by the
role's core for the reference item (flight control computer flight
software); it is a filled worked example, not a form with blanks. No
proprietary RTCA/EUROCAE or framework text is reproduced.
