#!/usr/bin/env python3
"""flight_software_core.py - Flight Software Engineer executable core.

This is the role's ENGINE: given a flight software item (a software item
of an airborne system, planned under the DO-178C software life cycle) it
runs the flight software DESIGN and VERIFICATION analysis - the cFS-style
software-bus command/telemetry message design (16-bit message IDs,
command band 0x0000-0x0FFF, telemetry band 0x1000-0xFFFF, monotonic
telemetry sequence counters, event severities), the F Prime style
component design model (component kinds, typed ports, command opcodes,
telemetry channels, rate-group dispatch schedule on a master clock), the
real-time scheduling analysis of the periodic process set (utilization,
Liu-Layland bound, exact iterative response-time analysis, EDF check),
and the shared-resource access-control design under the priority ceiling
protocol (resource ceilings, worst-case blocking, response-time analysis
with the blocking term) - and BUILDS the Flight Software Design and
Verification Plan content model. It also gate-checks deliverables.
Standalone: no external repo needed.

Domain rules encoded here come from the REAL rules of the bound
AeroSkills leaves (avionics/fsw/cfs-architecture, avionics/fsw/
fprime-component, avionics/fsw/real-time-scheduling, avionics/fsw/
shared-resource-access-control) or public science they encode: the
cFS/F Prime framework facts (NASA open-source, Apache-2.0) and the
Liu-Layland (1973) and priority-ceiling methodology (Sha/Rajkumar/
Lehoczky) are paraphrased, never copied from proprietary text. DO-178C
(RTCA/EUROCAE) is referenced only as the governing software life-cycle
standard for the planning vocabulary; no DO-178C text is reproduced.

Author: ashfordeOU (Aero Agent Roles role build, wave R6).
"""
from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass, field
from datetime import date


def _today() -> str:
    return os.environ.get("ROLE_GEN_DATE", date.today().isoformat())


# ---------------------------------------------------------------------------
# cFS-style software bus message design (avionics/fsw/cfs-architecture)
# ---------------------------------------------------------------------------
# Classic cFS facts encoded by the cfs-architecture leaf: message IDs are
# 16-bit (0x0000-0xFFFF); by convention command traffic occupies
# 0x0000-0x0FFF and telemetry 0x1000-0xFFFF; the upper bits carry an app
# tag and the lower bits the message number (0x1900 = app 0x19,
# message 0x00). Telemetry messages carry a monotonic sequence counter
# (CFE_SB_TlmHdr.SeqCnt) so the ground station can detect dropped
# packets. Event severities are DEBUG, INFO, EVENT, ERROR, CRITICAL.
MSG_ID_MIN = 0x0000
MSG_ID_MAX = 0xFFFF
CMD_MSG_ID_MAX = 0x0FFF      # command traffic occupies 0x0000-0x0FFF
TLM_MSG_ID_MIN = 0x1000      # telemetry traffic occupies 0x1000-0xFFFF
MSG_TAG_SHIFT = 8            # upper bits = app tag, lower bits = message no.
CFS_SEVERITIES = ("DEBUG", "INFO", "EVENT", "ERROR", "CRITICAL")
CFS_APP_LIFECYCLE = ("APP_Init", "APP_Execute", "APP_Data")


def msg_id_space_size() -> int:
    """Total 16-bit message ID space: 0x0000-0xFFFF inclusive."""
    return MSG_ID_MAX - MSG_ID_MIN + 1


def command_band_size() -> int:
    """Command band 0x0000-0x0FFF: 4096 message IDs."""
    return CMD_MSG_ID_MAX - MSG_ID_MIN + 1


def telemetry_band_size() -> int:
    """Telemetry band 0x1000-0xFFFF: 61440 message IDs."""
    return MSG_ID_MAX - CMD_MSG_ID_MAX


def msg_id_band(msg_id) -> str:
    """'command' for 0x0000-0x0FFF, 'telemetry' for 0x1000-0xFFFF.

    Rejects non-integer or out-of-range (non-16-bit) IDs, mirroring the
    cfs-architecture leaf's _check_msg_id rule.
    """
    if isinstance(msg_id, bool) or not isinstance(msg_id, int):
        raise ValueError("message id must be an integer, got %r" % (msg_id,))
    if not (MSG_ID_MIN <= msg_id <= MSG_ID_MAX):
        raise ValueError("message id 0x%X out of 16-bit range 0x0000-0xFFFF"
                         % msg_id)
    return "command" if msg_id <= CMD_MSG_ID_MAX else "telemetry"


def allocate_msg_id(app_tag: int, message_number: int, band: str) -> int:
    """Compose a 16-bit message ID: (app_tag << 8) | message_number.

    The classic cFS layout packs the app tag in the upper bits and the
    message number below (0x1900 = app 0x19, message 0x00). The result
    must land in the requested band: command tags keep the ID <= 0x0FFF,
    telemetry tags keep it >= 0x1000. Raises ValueError otherwise.
    """
    if isinstance(app_tag, bool) or not isinstance(app_tag, int) \
            or not (0 <= app_tag <= 0xFF):
        raise ValueError("app tag must be an integer in 0x00..0xFF")
    if isinstance(message_number, bool) \
            or not isinstance(message_number, int) \
            or not (0 <= message_number <= 0xFF):
        raise ValueError("message number must be an integer in 0x00..0xFF")
    if band not in ("command", "telemetry"):
        raise ValueError("band must be 'command' or 'telemetry'")
    mid = (app_tag << MSG_TAG_SHIFT) | message_number
    if msg_id_band(mid) != band:
        raise ValueError(
            "message id 0x%04X (app tag 0x%02X, message 0x%02X) does not "
            "lie in the %s band 0x%04X-0x%04X"
            % (mid, app_tag, message_number, band,
               MSG_ID_MIN if band == "command" else TLM_MSG_ID_MIN,
               CMD_MSG_ID_MAX if band == "command" else MSG_ID_MAX))
    return mid


def telemetry_seq_run(msgs_per_cycle: int, cycles: int,
                      start_seq: int = 0) -> dict:
    """Sequence budget for one telemetry message ID over `cycles`.

    Every telemetry message on a message ID carries an incrementing
    sequence counter, one per message (telemetry_pipeline stamps
    start_seq + i). Returns count, first_seq, last_seq and the
    monotonic verdict.
    """
    if not isinstance(msgs_per_cycle, int) or msgs_per_cycle < 1:
        raise ValueError("msgs_per_cycle must be an integer >= 1")
    if not isinstance(cycles, int) or cycles < 1:
        raise ValueError("cycles must be an integer >= 1")
    if not isinstance(start_seq, int) or start_seq < 0:
        raise ValueError("start_seq must be a non-negative integer")
    count = msgs_per_cycle * cycles
    seqs = [start_seq + i for i in range(count)]
    return {"count": count, "first_seq": seqs[0], "last_seq": seqs[-1],
            "monotonic": all(b == a + 1 for a, b in zip(seqs, seqs[1:]))}


def cfs_telemetry_stamp(bus, app_name, tlm_msg_id, payloads,
                        start_seq: int = 0) -> dict:
    """Plan-side model of the cfs leaf's telemetry_pipeline stamping.

    Mirrors the leaf formula seq = start_seq + i for the i-th payload of
    one pipeline run on a message ID (the bus argument carries the leaf
    run when dispatched; the core models the same stamping rule).
    Returns count, seqs, first/last and the monotonic verdict.
    """
    if not isinstance(payloads, (list, tuple)) or not payloads:
        raise ValueError("payloads must be a non-empty list")
    msg_id_band(tlm_msg_id)   # validates 16-bit ID (raises ValueError)
    if not isinstance(app_name, str) or not app_name:
        raise ValueError("app name must be a non-empty string")
    seqs = [start_seq + i for i in range(len(payloads))]
    return {"msg_id": tlm_msg_id, "app": app_name,
            "count": len(seqs), "seqs": seqs,
            "first_seq": seqs[0], "last_seq": seqs[-1],
            "monotonic": all(b == a + 1 for a, b in zip(seqs, seqs[1:]))}


# ---------------------------------------------------------------------------
# F Prime style component model (avionics/fsw/fprime-component)
# ---------------------------------------------------------------------------
# F Prime facts encoded by the fprime-component leaf: component kinds
# active (owns a thread + queue) / queued (queue, no thread) / passive
# (runs inline); typed ports carry one of U8/U16/U32/I32/F32/F64/string
# (serial matches any partner); commands carry unique opcodes in
# 0x0000..0xFFFF and need a queue (passive components declare none);
# an active component must declare at least one input port; telemetry
# channels carry typed samples with per-channel monotonic sequence
# counters; event severities are FATAL/HIGH/LOW/INFO/DEBUG; every
# active/queued input port needs exactly one dispatch driver (one
# incoming connection or one rate group); a rate group ticks its input
# ports every max(1, round(base_hz / hz)) master ticks and the master
# clock runs at the fastest declared group rate by default.
COMPONENT_KINDS = ("active", "queued", "passive")
TLM_TYPES = ("U8", "U16", "U32", "I32", "F32", "F64", "string")
PORT_TYPES = TLM_TYPES + ("serial",)
FPRIME_SEVERITIES = ("FATAL", "HIGH", "LOW", "INFO", "DEBUG")
OPCODE_MIN = 0
OPCODE_MAX = 0xFFFF


def validate_component(defn) -> list:
    """Issue strings for one F Prime component definition.

    Enforces the leaf rules: required name, supported kind, unique port
    names with input/output direction and supported data types, unique
    command names and opcodes in 0x0000..0xFFFF, unique telemetry
    channel names of supported types, event severities from
    FATAL/HIGH/LOW/INFO/DEBUG, active components declare at least one
    input port, passive components declare no commands.
    """
    issues = []
    name = defn.get("name")
    if not isinstance(name, str) or not name.strip():
        return ["component missing name"]
    name = name.strip()
    kind = defn.get("kind")
    if kind not in COMPONENT_KINDS:
        issues.append("component '%s': unsupported kind %r"
                      % (name, kind))
    ports = defn.get("ports") or []
    seen_ports, input_ports = [], []
    for p in ports:
        pname = p.get("name")
        if not isinstance(pname, str) or not pname.strip():
            issues.append("component '%s': port missing name" % name)
            continue
        pname = pname.strip()
        if pname in seen_ports:
            issues.append("component '%s': duplicate port name '%s'"
                          % (name, pname))
        seen_ports.append(pname)
        if p.get("direction") not in ("input", "output"):
            issues.append("component '%s': port '%s' direction must be "
                          "input or output" % (name, pname))
        if p.get("data_type") not in PORT_TYPES:
            issues.append("component '%s': port '%s' unsupported data "
                          "type %r" % (name, pname, p.get("data_type")))
        if p.get("direction") == "input":
            input_ports.append(pname)
    commands = defn.get("commands") or []
    cmd_names, cmd_opcodes = [], {}
    for c in commands:
        cname = c.get("name")
        opcode = c.get("opcode")
        if not isinstance(cname, str) or not cname.strip():
            issues.append("component '%s': command missing name" % name)
        else:
            cname = cname.strip()
            if cname in cmd_names:
                issues.append("component '%s': duplicate command name '%s'"
                              % (name, cname))
            cmd_names.append(cname)
        if (isinstance(opcode, bool) or not isinstance(opcode, int)
                or not (OPCODE_MIN <= opcode <= OPCODE_MAX)):
            issues.append("component '%s': command '%s' opcode %r out of "
                          "range 0x0000..0xFFFF"
                          % (name, cname, opcode))
        else:
            if opcode in cmd_opcodes:
                issues.append("component '%s': duplicate command opcode "
                              "0x%04X (commands '%s' and '%s')"
                              % (name, opcode, cmd_opcodes[opcode], cname))
            cmd_opcodes[opcode] = cname
    telemetry = defn.get("telemetry") or []
    tlm_names = []
    for ch in telemetry:
        chname = ch.get("name")
        if not isinstance(chname, str) or not chname.strip():
            issues.append("component '%s': telemetry channel missing name"
                          % name)
            continue
        chname = chname.strip()
        if chname in tlm_names:
            issues.append("component '%s': duplicate telemetry channel "
                          "name '%s'" % (name, chname))
        tlm_names.append(chname)
        if ch.get("type") not in TLM_TYPES:
            issues.append("component '%s': telemetry channel '%s' "
                          "unsupported type %r"
                          % (name, chname, ch.get("type")))
    events = defn.get("events") or []
    event_names = []
    for e in events:
        ename = e.get("name")
        if not isinstance(ename, str) or not ename.strip():
            issues.append("component '%s': event missing name" % name)
            continue
        ename = ename.strip()
        if ename in event_names:
            issues.append("component '%s': duplicate event name '%s'"
                          % (name, ename))
        event_names.append(ename)
        if e.get("severity") not in FPRIME_SEVERITIES:
            issues.append("component '%s': event '%s' unsupported "
                          "severity %r"
                          % (name, ename, e.get("severity")))
    if kind == "active" and not input_ports:
        issues.append("component '%s': active components must declare at "
                      "least one input port (the framework dispatches "
                      "them)" % name)
    if kind == "passive" and commands:
        issues.append("component '%s': passive components must not declare "
                      "commands; commands arrive asynchronously and "
                      "require a queue (%d declared)"
                      % (name, len(commands)))
    return issues


def _defs_index(defs):
    index = {}
    for d in defs:
        dname = d.get("name")
        if isinstance(dname, str) and dname.strip():
            index[dname.strip()] = d
    return index


def _port_lookup(defn, pname):
    for p in defn.get("ports") or []:
        if p.get("name") == pname:
            return p
    return None


def validate_connections(defs, connections) -> list:
    """Issue strings for typed output->input connections.

    Enforces the leaf rules: both ends exist and are declared ports,
    the source is an output and the destination an input, data types
    match unless one side is a serial interface, no self-loops.
    """
    issues = []
    index = _defs_index(defs)
    for c in connections:
        (cfrom, pfrom), (cto, pto) = c["from"], c["to"]
        if cfrom not in index:
            issues.append("connection from unknown component '%s'" % cfrom)
            continue
        if cto not in index:
            issues.append("connection to unknown component '%s'" % cto)
            continue
        fport = _port_lookup(index[cfrom], pfrom)
        tport = _port_lookup(index[cto], pto)
        if fport is None:
            issues.append("connection from '%s': port '%s' not declared"
                          % (cfrom, pfrom))
            continue
        if tport is None:
            issues.append("connection to '%s': port '%s' not declared"
                          % (cto, pto))
            continue
        if fport.get("direction") != "output":
            issues.append("connection from '%s.%s': source port must be an "
                          "output" % (cfrom, pfrom))
        if tport.get("direction") != "input":
            issues.append("connection to '%s.%s': destination port must be "
                          "an input" % (cto, pto))
        if cfrom == cto:
            issues.append("self-loop connection '%s.%s' -> '%s.%s' is not "
                          "allowed" % (cfrom, pfrom, cto, pto))
        ftype, ttype = fport.get("data_type"), tport.get("data_type")
        if ftype != ttype and "serial" not in (ftype, ttype):
            issues.append("connection type mismatch '%s.%s' (%s) -> "
                          "'%s.%s' (%s)"
                          % (cfrom, pfrom, ftype, cto, pto, ttype))
    return issues


def _incoming_connections(connections):
    incoming = {}
    for c in connections:
        (cfrom, _pfrom), (cto, pto) = c["from"], c["to"]
        incoming.setdefault((cto, pto), []).append(cfrom)
    return incoming


def validate_rate_groups(defs, connections, rate_groups):
    """(issues, warnings) for rate-group dispatch schedules.

    Enforces the leaf rules: unique group names, positive group hz, each
    listed entry is a declared input port, and every input port of an
    active or queued component is dispatched by exactly one driver (one
    incoming connection or one rate group); passive input ports in two
    or more groups, or in none, only warn.
    """
    issues, warnings = [], []
    index = _defs_index(defs)
    names = []
    for g in rate_groups:
        gname = g.get("name")
        if not isinstance(gname, str) or not gname.strip():
            issues.append("rate group missing name")
            continue
        gname = gname.strip()
        if gname in names:
            issues.append("duplicate rate group name '%s'" % gname)
        names.append(gname)
        hz = g.get("hz")
        if isinstance(hz, bool) or not isinstance(hz, (int, float)) \
                or not hz > 0:
            issues.append("rate group '%s': hz must be a positive number"
                          % (gname,))
        for (comp, port) in g.get("ports") or []:
            if comp not in index:
                issues.append("rate group '%s': unknown component '%s'"
                              % (gname, comp))
                continue
            p = _port_lookup(index[comp], port)
            if p is None:
                issues.append("rate group '%s': component '%s' has no port "
                              "'%s'" % (gname, comp, port))
                continue
            if p.get("direction") != "input":
                issues.append("rate group '%s': '%s.%s' is not an input "
                              "port" % (gname, comp, port))
    group_membership = {}
    for g in rate_groups:
        gname = g.get("name")
        for (comp, port) in (g.get("ports") or []):
            if isinstance(gname, str) and gname.strip() \
                    and comp in index \
                    and _port_lookup(index[comp], port) is not None:
                group_membership.setdefault((comp, port), []).append(
                    gname.strip())
    incoming = _incoming_connections(connections)
    for d in defs:
        dname = d.get("name")
        if not isinstance(dname, str):
            continue
        kind = d.get("kind")
        for p in d.get("ports") or []:
            if p.get("direction") != "input":
                continue
            pname = p.get("name")
            if not isinstance(pname, str):
                continue
            key = (dname, pname)
            n_groups = len(group_membership.get(key, ()))
            n_conns = len(incoming.get(key, ()))
            if kind in ("active", "queued"):
                drivers = n_groups + n_conns
                if drivers == 0:
                    issues.append("input port '%s.%s' has no dispatch "
                                  "driver: add it to one rate group or "
                                  "connect one output to it" % (dname, pname))
                elif drivers > 1:
                    issues.append("input port '%s.%s' has %d dispatch "
                                  "drivers (%d rate group(s), %d "
                                  "connection(s)); exactly one is allowed"
                                  % (dname, pname, drivers, n_groups,
                                     n_conns))
            else:  # passive input ports run inline in the caller context
                if n_groups > 1:
                    warnings.append("passive input port '%s.%s' is invoked "
                                    "by %d rate groups; its handler runs in "
                                    "multiple timing contexts"
                                    % (dname, pname, n_groups))
                if n_groups == 0 and n_conns == 0:
                    warnings.append("passive input port '%s.%s' has no "
                                    "dispatch driver (dead port)"
                                    % (dname, pname))
    return issues, warnings


def validate_topology(defs, connections, rate_groups) -> dict:
    """Umbrella validator: component + connection + rate group rules."""
    issues = []
    for i, d in enumerate(defs):
        for msg in validate_component(d):
            issues.append("component %d: %s" % (i, msg))
    issues.extend(validate_connections(defs, connections))
    rg_issues, warnings = validate_rate_groups(defs, connections,
                                               rate_groups)
    issues.extend(rg_issues)
    return {"issues": issues, "warnings": warnings}


def component_counts(defs) -> dict:
    """Counts of components by kind (F Prime component inventory)."""
    counts = {"active": 0, "queued": 0, "passive": 0}
    for d in defs:
        kind = d.get("kind")
        if kind in counts:
            counts[kind] += 1
    counts["total"] = sum(counts.values())
    return counts


def rate_group_schedule(rate_groups, base_hz=None) -> dict:
    """Master-clock dispatch schedule for a rate group list.

    Mirrors the fprime leaf Simulation clock math: the master clock runs
    at the fastest declared group rate by default (base_hz = max hz) and
    each group ticks its input ports every max(1, round(base_hz / hz))
    master ticks; groups are ordered by (period, name).
    """
    if not rate_groups:
        raise ValueError("rate_groups must not be empty")
    hzs = []
    for g in rate_groups:
        hz = g.get("hz")
        if isinstance(hz, bool) or not isinstance(hz, (int, float)) \
                or not hz > 0:
            raise ValueError("rate group hz must be a positive number")
        hzs.append(float(hz))
    if base_hz is None:
        base_hz = max(hzs)
    if isinstance(base_hz, bool) or not isinstance(base_hz, (int, float)) \
            or base_hz <= 0:
        raise ValueError("base_hz must be a positive number")
    schedule = []
    for g in rate_groups:
        period = max(1, int(round(float(base_hz) / float(g["hz"]))))
        schedule.append({"name": g["name"], "hz": float(g["hz"]),
                         "period_ticks": period,
                         "period_ms": None,
                         "ports": list(g.get("ports") or [])})
    schedule.sort(key=lambda s: (s["period_ticks"], s["name"]))
    return {"base_hz": float(base_hz), "groups": schedule}


def opcode_inventory(defs) -> list:
    """Declared command opcodes per component (validated unique)."""
    rows = []
    for d in defs:
        for c in d.get("commands") or []:
            if isinstance(c.get("opcode"), int) \
                    and not isinstance(c.get("opcode"), bool):
                rows.append({"component": d.get("name"),
                             "opcode": c["opcode"],
                             "name": c.get("name")})
    rows.sort(key=lambda r: (r["component"], r["opcode"]))
    return rows


# ---------------------------------------------------------------------------
# Real-time scheduling analysis (avionics/fsw/real-time-scheduling)
# ---------------------------------------------------------------------------
# Public feasibility mathematics encoded by the real-time-scheduling
# leaf (Liu and Layland 1973, summary-only): task set = (C, T) pairs
# with implicit deadline D = T in one time unit; shorter period means
# higher priority under RM (equal periods broken by list index);
# U = sum(C_i / T_i); the sufficient Liu-Layland bound is
# U_rm(n) = n * (2**(1/n) - 1); the exact RM response time of task i is
# the fixed point of R_i = C_i + sum_{j in hp(i)} ceil(R_i / T_j) * C_j
# iterated from R_i = C_i (divergence when an iterate passes the period
# or the 1000 * max(T) cap); RM is feasible iff every converged R_i is
# at most T_i; EDF is feasible iff U <= 1 (implicit deadlines).
DIVERGENCE_CAP_FACTOR = 1000.0
MAX_RTA_ITERATIONS = 10000
_RM_EPS = 1e-9


def _validate_task_pairs(tasks):
    if not isinstance(tasks, (list, tuple)):
        raise ValueError("task set must be a list or tuple of (C, T) pairs")
    if len(tasks) == 0:
        raise ValueError("task set must not be empty")
    validated = []
    for item in tasks:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError("each task must be a (C, T) pair")
        c, t = item
        if isinstance(c, bool) or isinstance(t, bool) \
                or not isinstance(c, (int, float)) \
                or not isinstance(t, (int, float)):
            raise ValueError("C and T must be real numbers, not booleans")
        c, t = float(c), float(t)
        if not math.isfinite(c) or not math.isfinite(t):
            raise ValueError("C and T must be finite numbers")
        if c <= 0.0 or t <= 0.0:
            raise ValueError("execution time C and period T must be "
                             "positive")
        validated.append((c, t))
    return validated


def utilization(tasks) -> float:
    """Total processor utilization U = sum(C_i / T_i)."""
    return sum(c / t for c, t in _validate_task_pairs(tasks))


def liu_layland_bound(n) -> float:
    """Liu-Layland sufficient bound U_rm(n) = n * (2**(1/n) - 1).

    Anchors: U_rm(1) = 1, U_rm(2) = 0.828427, U_rm(3) = 0.779763,
    U_rm(4) = 0.756828; the bound decreases toward ln 2 ~ 0.693.
    """
    if isinstance(n, bool) or not isinstance(n, (int, float)):
        raise ValueError("n must be a positive integer number of tasks")
    if isinstance(n, float):
        if n.is_integer():
            n = int(n)
        else:
            raise ValueError("n must be an integer task count")
    if n < 1:
        raise ValueError("n must be >= 1 (a task set has at least one task)")
    return n * (2.0 ** (1.0 / n) - 1.0)


def _hp_indices(periods, i):
    hp = []
    for j in range(len(periods)):
        if j == i:
            continue
        if periods[j] < periods[i] or (periods[j] == periods[i] and j < i):
            hp.append(j)
    return hp


def _rta_single(c_i, t_i, hp_tasks):
    cap = DIVERGENCE_CAP_FACTOR * t_i
    r = c_i
    for _ in range(MAX_RTA_ITERATIONS):
        r_next = c_i + sum(math.ceil(r / t_j) * c_j
                           for c_j, t_j in hp_tasks)
        if r_next > t_i + _RM_EPS or r_next > cap:
            return None
        if abs(r_next - r) <= _RM_EPS:
            return float(r_next)
        r = r_next
    return None


def rm_response_times(tasks):
    """Exact RM response times R_i for every task, or None on divergence.

    R_i = C_i + sum_{j in hp(i)} ceil(R_i / T_j) * C_j, iterated from
    R_i = C_i to a fixed point. Divergence (None) means RM-infeasible.
    """
    validated = _validate_task_pairs(tasks)
    periods = [t for _, t in validated]
    result = []
    for i, (c_i, t_i) in enumerate(validated):
        hp = [(validated[j][0], validated[j][1])
              for j in _hp_indices(periods, i)]
        r_i = _rta_single(c_i, t_i, hp)
        if r_i is None:
            return None
        result.append(r_i)
    return result


def rm_ub_feasible(tasks) -> bool:
    """True when U <= U_rm(n): the Liu-Layland sufficient test.

    A True verdict guarantees RM feasibility; False is inconclusive
    (use rm_feasible for the exact answer).
    """
    validated = _validate_task_pairs(tasks)
    return utilization(validated) <= liu_layland_bound(len(validated))


def rm_feasible(tasks) -> bool:
    """Exact RM verdict: every converged response time is at most its
    period (divergence means infeasible)."""
    response_times = rm_response_times(tasks)
    if response_times is None:
        return False
    validated = _validate_task_pairs(tasks)
    return all(r <= t + _RM_EPS for r, (_, t) in
               zip(response_times, validated))


def edf_feasible(tasks) -> bool:
    """True when EDF can schedule the set: U <= 1 (necessary and
    sufficient for implicit-deadline periodic tasks on one processor)."""
    return utilization(tasks) <= 1.0 + _RM_EPS


def scheduling_summary(tasks) -> dict:
    """Convenience verdict dict for a task set.

    Keys: utilization, n_tasks, liu_layland_bound, rm_ub_verdict,
    rm_exact_response_times, rm_exact_feasible, edf_feasible, verdict.
    Verdict strings match the real-time-scheduling leaf exactly:
    "RM-guaranteed-by-UB", "RM-exact-feasible (UB inconclusive)",
    "EDF-feasible-only", "RM-infeasible".
    """
    validated = _validate_task_pairs(tasks)
    u = utilization(validated)
    n = len(validated)
    ll_bound = liu_layland_bound(n)
    ub_verdict = u <= ll_bound
    response_times = rm_response_times(validated)
    exact_feasible = (
        response_times is not None
        and all(r <= t + _RM_EPS
                for r, (_, t) in zip(response_times, validated)))
    edf_ok = u <= 1.0 + _RM_EPS
    if exact_feasible:
        verdict = ("RM-guaranteed-by-UB" if ub_verdict
                   else "RM-exact-feasible (UB inconclusive)")
    elif edf_ok:
        verdict = "EDF-feasible-only"
    else:
        verdict = "RM-infeasible"
    return {"utilization": u, "n_tasks": n, "liu_layland_bound": ll_bound,
            "rm_ub_verdict": ub_verdict,
            "rm_exact_response_times": response_times,
            "rm_exact_feasible": exact_feasible,
            "edf_feasible": edf_ok, "verdict": verdict}


# ---------------------------------------------------------------------------
# Shared-resource access control (avionics/fsw/shared-resource-access-control)
# ---------------------------------------------------------------------------
# Public priority-ceiling methodology encoded by the leaf (Sha, Rajkumar
# and Lehoczky, summary-only): a task is a {name, C, T, priority} dict
# with implicit deadline D = T (higher number = higher priority); the
# ceiling of a resource is the highest priority among the tasks that
# lock it; under the ceiling rule a task is blocked by at most one
# lower-priority task's critical section, and only on a resource whose
# ceiling is at least the task's priority - so worst-case blocking is
# the longest qualifying cs, never a sum; the response time with
# blocking is the fixed point of R_i = C_i + B_i + sum_{j in hp(i)}
# ceil(R_i / T_j) * C_j, iterated from C_i + B_i (cap 100 iterations);
# feasible iff every response time is at most its period.
SR_MAX_RTA_ITERATIONS = 100
_SR_EPS = 1e-9


def _task_registry(tasks):
    if isinstance(tasks, dict):
        items = list(tasks.items())
    elif isinstance(tasks, (list, tuple)):
        items = []
        for entry in tasks:
            if not isinstance(entry, dict) or "name" not in entry:
                raise ValueError("each task in a list must be a dict with "
                                 "a name key")
            items.append((entry["name"], entry))
    else:
        raise ValueError("task set must be a dict or a list of task dicts")
    if len(items) == 0:
        raise ValueError("task set must not be empty")
    registry = {}
    for name, record in items:
        if not isinstance(name, str) or name == "":
            raise ValueError("task name must be a non-empty string")
        if name in registry:
            raise ValueError("duplicate task name: %s" % name)
        if not isinstance(record, dict):
            raise ValueError("task %s must be a dict" % name)
        missing = set(("C", "T", "priority")) - set(record)
        if missing:
            raise ValueError("task %s lacks keys %s"
                             % (name, sorted(missing)))
        c, t, p = record["C"], record["T"], record["priority"]
        for label, value in (("C", c), ("T", t), ("priority", p)):
            if isinstance(value, bool) or not isinstance(value,
                                                         (int, float)):
                raise ValueError("%s of task %s must be a real number"
                                 % (label, name))
            if not math.isfinite(float(value)):
                raise ValueError("%s of task %s must be finite"
                                 % (label, name))
        if c <= 0.0 or t <= 0.0:
            raise ValueError("execution time C and period T of task %s "
                             "must be positive" % name)
        if c > t:
            raise ValueError("execution time C of task %s exceeds its "
                             "period T" % name)
        registry[name] = {"C": float(c), "T": float(t),
                          "priority": float(p)}
    return registry


def _validate_locks(registry, locks, allow_empty):
    if not isinstance(locks, (list, tuple)):
        raise ValueError("locks must be a list of lock dicts")
    if len(locks) == 0:
        if not allow_empty:
            raise ValueError("lock list must not be empty")
        return []
    normalized = []
    for lock in locks:
        if not isinstance(lock, dict):
            raise ValueError("each lock must be a dict")
        missing = set(("resource", "task", "cs")) - set(lock)
        if missing:
            raise ValueError("lock lacks keys %s" % sorted(missing))
        resource, task, cs = lock["resource"], lock["task"], lock["cs"]
        if not isinstance(resource, str) or resource == "":
            raise ValueError("resource name must be a non-empty string")
        if task not in registry:
            raise ValueError("lock references unknown task %r" % (task,))
        if isinstance(cs, bool) or not isinstance(cs, (int, float)):
            raise ValueError("cs of a lock must be a real number")
        if not math.isfinite(float(cs)):
            raise ValueError("cs of a lock must be finite")
        if cs < 0.0:
            raise ValueError("critical section cs must not be negative")
        normalized.append((resource, task, float(cs)))
    return normalized


def _ceiling_map(registry, locks):
    ceiling = {}
    for resource, task, _cs in locks:
        priority = registry[task]["priority"]
        if resource not in ceiling or priority > ceiling[resource]:
            ceiling[resource] = priority
    return ceiling


def priority_ceiling(tasks, locks) -> dict:
    """Per-resource ceiling: the highest priority among the tasks that
    lock the resource. Raises ValueError on an empty lock list."""
    registry = _task_registry(tasks)
    normalized = _validate_locks(registry, locks, allow_empty=False)
    return _ceiling_map(registry, normalized)


def resource_ceiling(tasks, locks, resource) -> float:
    """Ceiling priority of one resource (ValueError when unlocked)."""
    registry = _task_registry(tasks)
    normalized = _validate_locks(registry, locks, allow_empty=False)
    if not isinstance(resource, str) or resource == "":
        raise ValueError("resource name must be a non-empty string")
    ceiling = _ceiling_map(registry, normalized)
    if resource not in ceiling:
        raise ValueError("resource %r is not locked by any task" % resource)
    return ceiling[resource]


def worst_case_blocking(task, tasks, locks) -> float:
    """Worst-case blocking of one task under the ceiling rule.

    The longest cs of any strictly lower-priority task that locks a
    resource whose ceiling is at least the task's priority; zero when no
    such section exists (a task is blocked by at most one lower-priority
    critical section under PCP).
    """
    registry = _task_registry(tasks)
    normalized = _validate_locks(registry, locks, allow_empty=True)
    if task not in registry:
        raise ValueError("unknown task %r" % (task,))
    priority = registry[task]["priority"]
    ceiling = _ceiling_map(registry, normalized)
    best = 0.0
    for lock_task, record in registry.items():
        if record["priority"] >= priority:
            continue  # only strictly lower-priority tasks can block
        for resource, lock_task_name, cs in normalized:
            if lock_task_name != lock_task:
                continue
            if ceiling.get(resource, -math.inf) >= priority:
                best = max(best, cs)
    return best


def blocking_times(tasks, locks) -> dict:
    """{task name: worst-case blocking time} for every task."""
    registry = _task_registry(tasks)
    _validate_locks(registry, locks, allow_empty=True)
    return {name: worst_case_blocking(name, registry, locks)
            for name in registry}


def response_time_with_blocking(task, tasks, locks) -> float:
    """Response time including the blocking term: fixed point of
    R_i = C_i + B_i + sum_{j in hp(i)} ceil(R_i / T_j) * C_j, iterated
    from C_i + B_i (cap 100 iterations)."""
    registry = _task_registry(tasks)
    _validate_locks(registry, locks, allow_empty=True)
    if task not in registry:
        raise ValueError("unknown task %r" % (task,))
    record = registry[task]
    c, t, priority = record["C"], record["T"], record["priority"]
    hp = [(registry[name]["C"], registry[name]["T"])
          for name in registry if registry[name]["priority"] > priority]
    blocking = worst_case_blocking(task, registry, locks)
    response = c + blocking
    for _ in range(SR_MAX_RTA_ITERATIONS):
        total = blocking + sum(math.ceil(response / period) * exec_time
                               for exec_time, period in hp)
        updated = c + total
        if updated == response:
            break
        response = updated
    return response


def rta_with_blocking_feasibility(tasks, locks) -> dict:
    """{blocking, response_times, feasible}: schedulability verdict with
    the blocking term (feasible iff every response time is at most its
    task period within 1e-9 relative slack). An empty lock list gives
    zero blocking, so the response times then equal the plain analysis."""
    registry = _task_registry(tasks)
    _validate_locks(registry, locks, allow_empty=True)
    blocking = {name: worst_case_blocking(name, registry, locks)
                for name in registry}
    response_times = {name: response_time_with_blocking(name, registry,
                                                        locks)
                      for name in registry}
    feasible = all(response_times[name] <= registry[name]["T"]
                   * (1.0 + _SR_EPS) for name in registry)
    return {"blocking": blocking, "response_times": response_times,
            "feasible": feasible}


# ---------------------------------------------------------------------------
# Verification planning tables (grounded in the bound leaves)
# ---------------------------------------------------------------------------
# Verification activities planned per design stage. Each row's pass
# criteria are properties the bound leaves' own verification checklists
# and contract tests state (publish-order routing, monotonic telemetry
# sequence counters, exactly-one dispatch driver, response-time
# convergence within every period, the empty-lock identity, the 1e-9
# feasibility slack). Contract test case counts are the real counts the
# leaves' SKILL.md files state (15 / 35 / 35 / 35).
VERIFICATION_ACTIVITIES = [
    {"id": "V-01", "stage": "Software bus routing",
     "activity": "Software bus publish/subscribe routing verification",
     "method": "deterministic simulation (register, subscribe, publish, "
               "route)",
     "pass_criteria": "every app receives only its subscribed message IDs, "
                      "in publish order; publish to an unknown message ID "
                      "is rejected",
     "leaf": "avionics/fsw/cfs-architecture"},
    {"id": "V-02", "stage": "Telemetry pipeline",
     "activity": "Telemetry sequence-counter continuity check",
     "method": "stamped pipeline run per message ID",
     "pass_criteria": "sequence counters are monotonic per message ID with "
                      "no gaps, so the ground station can detect drops",
     "leaf": "avionics/fsw/cfs-architecture"},
    {"id": "V-03", "stage": "Event reporting",
     "activity": "Event service severity conformance",
     "method": "event log audit",
     "pass_criteria": "every event entry carries one of DEBUG, INFO, "
                      "EVENT, ERROR, CRITICAL; unknown severities are "
                      "rejected",
     "leaf": "avionics/fsw/cfs-architecture"},
    {"id": "V-04", "stage": "Component model",
     "activity": "Component definition conformance",
     "method": "validate_component on every declared component",
     "pass_criteria": "active components declare >= 1 input port; passive "
                      "components declare no commands; command opcodes "
                      "unique in 0x0000..0xFFFF; telemetry types and event "
                      "severities from the supported sets",
     "leaf": "avionics/fsw/fprime-component"},
    {"id": "V-05", "stage": "Component model",
     "activity": "Connection and dispatch-driver coverage",
     "method": "validate_connections + validate_rate_groups on the "
               "topology",
     "pass_criteria": "connections run output to input with matching "
                      "types (serial matches any), no self-loops; every "
                      "active/queued input port has exactly one dispatch "
                      "driver",
     "leaf": "avionics/fsw/fprime-component"},
    {"id": "V-06", "stage": "Dispatch schedule",
     "activity": "Rate-group schedule and clocked dispatch determinism",
     "method": "deterministic clocked simulation over the master clock",
     "pass_criteria": "groups tick their input ports every "
                      "max(1, round(base_hz / hz)) master ticks; "
                      "invocations, deliveries and telemetry samples are "
                      "deterministic with monotonic per-channel sequence "
                      "counters",
     "leaf": "avionics/fsw/fprime-component"},
    {"id": "V-07", "stage": "Scheduling analysis",
     "activity": "Rate-monotonic schedulability verdict",
     "method": "utilization bound test + exact response-time analysis",
     "pass_criteria": "U <= U_rm(n) guarantees RM feasibility; otherwise "
                      "every converged response time R_i must satisfy "
                      "R_i <= T_i (divergence means RM-infeasible); EDF "
                      "feasible iff U <= 1",
     "leaf": "avionics/fsw/real-time-scheduling"},
    {"id": "V-08", "stage": "Scheduling analysis",
     "activity": "Scheduling analysis contract tests",
     "method": "run scripts/test_real_time_scheduling.py (35 cases)",
     "pass_criteria": "all 35 contract cases pass offline: Liu-Layland "
                      "anchors, worked task sets A/B/C, divergence "
                      "detection, ValueError rejection of non-physical "
                      "inputs",
     "leaf": "avionics/fsw/real-time-scheduling"},
    {"id": "V-09", "stage": "Resource access control",
     "activity": "Priority ceiling and blocking verification",
     "method": "ceiling map + blocking times audit against the lock "
               "register",
     "pass_criteria": "each resource ceiling equals the highest priority "
                      "among its lockers; blocking is the longest "
                      "qualifying lower-priority critical section (never a "
                      "sum)",
     "leaf": "avionics/fsw/shared-resource-access-control"},
    {"id": "V-10", "stage": "Resource access control",
     "activity": "Response-time-with-blocking feasibility",
     "method": "fixed-point analysis with the blocking term",
     "pass_criteria": "every response time R_i = C_i + B_i + sum of "
                      "higher-priority preemption load is at most T_i "
                      "within 1e-9 relative slack; empty-lock identity: "
                      "with no locks the analysis equals the plain "
                      "response-time analysis",
     "leaf": "avionics/fsw/shared-resource-access-control"},
    {"id": "V-11", "stage": "Resource access control",
     "activity": "Resource access contract tests",
     "method": "run scripts/test_shared_resource_access_control.py "
               "(35 cases)",
     "pass_criteria": "all 35 contract cases pass offline: anchor "
                      "ceilings, blocking truth table, fixed-point "
                      "convergence, empty-lock identity, ValueError "
                      "rejection of every non-physical input",
     "leaf": "avionics/fsw/shared-resource-access-control"},
]

# DO-178C life-cycle planning vocabulary used to place the design and
# verification work in the software life cycle (summary-not-copy; the
# do178c-cert-engineer role owns the certification plan itself).
DO178C_PLANNING_AREAS = (
    "planning of software development and verification",
    "software development standards",
    "software verification (reviews, analyses, requirements-based tests)",
    "configuration management and change control",
    "software life cycle data",
)

# ---------------------------------------------------------------------------
# Flight Software Design and Verification Plan builder
# ---------------------------------------------------------------------------


@dataclass
class FlightSoftwareItem:
    """Project facts the role needs to build the design/verification plan.

    The reference item is a flight software item of an airborne system
    (FAR/CS-25 program context; software life cycle per DO-178C). The
    architecture is described with the cFS layering vocabulary; the
    component model with the F Prime vocabulary; the process set and
    protected data stores feed the scheduling and access-control
    analyses.
    """
    item_name: str
    description: str = ""
    system: str = ""
    airframe: str = ""
    certification_basis: str = "DO-178C software life cycle (FAR/CS-25 program context)"
    software_level: str = "A"          # INPUT from the system safety assessment
    software_level_source: str = ""
    platform: str = ""
    # cFS-style layered architecture (bottom to top)
    layers: list = field(default_factory=list)
    # application / component inventory:
    # {name, function, kind, period_ms}
    applications: list = field(default_factory=list)
    # software bus command/telemetry catalog:
    # {app, cmd_tag, cmd_num, tlm_tag, tlm_num, msgs_per_cycle}
    # (cmd_tag/cmd_num None when the app declares no command interface)
    bus_catalog: list = field(default_factory=list)
    major_cycle_ms: float = 20.0
    # process set for scheduling: {name, C_ms, T_ms}
    processes: list = field(default_factory=list)
    # PCP task model: {name: {C, T, priority}} (higher number = higher priority)
    pcp_tasks: dict = field(default_factory=dict)
    # protected resources: {resource, task, cs}
    locks: list = field(default_factory=list)
    # human-readable protected-data descriptions: {resource: description}
    lock_descriptions: dict = field(default_factory=dict)
    # F Prime component model: defs / connections / rate groups
    components: list = field(default_factory=list)
    connections: list = field(default_factory=list)
    rate_groups: list = field(default_factory=list)
    base_hz: float = 0.0              # 0 -> fastest declared group rate
    supporting_note: str = ""


def _fmt(x, nd=4) -> str:
    if isinstance(x, float):
        if x == 0.0:
            return "0"
        if 1e-4 <= abs(x) < 1e6:
            return "%.*g" % (nd, x)
        return "%.1e" % x
    return str(x)


def build_design_verification_plan(item: FlightSoftwareItem) -> dict:
    """Build the complete Flight Software Design and Verification Plan
    content model: every number below is computed by this core from the
    real rules of the bound leaves (message ID bands and sequence
    counters, rate-group clock math, Liu-Layland/RTA feasibility,
    priority-ceiling blocking)."""
    # --- architecture (cFS layering + app inventory) ---
    layers = list(item.layers)
    apps = [dict(a) for a in item.applications]

    # --- software bus command/telemetry design (cfs-architecture) ---
    catalog, cmd_ids, tlm_ids = [], [], []
    for row in item.bus_catalog:
        entry = {"app": row["app"],
                 "cmd_msg_id": None, "tlm_msg_id": None,
                 "msgs_per_cycle": row.get("msgs_per_cycle", 1)}
        if row.get("cmd_tag") is not None:
            entry["cmd_msg_id"] = allocate_msg_id(row["cmd_tag"],
                                                  row["cmd_num"],
                                                  "command")
            cmd_ids.append(entry["cmd_msg_id"])
        if row.get("tlm_tag") is not None:
            entry["tlm_msg_id"] = allocate_msg_id(row["tlm_tag"],
                                                  row["tlm_num"],
                                                  "telemetry")
            tlm_ids.append(entry["tlm_msg_id"])
        entry["band_ok"] = (
            (entry["cmd_msg_id"] is None
             or msg_id_band(entry["cmd_msg_id"]) == "command")
            and (entry["tlm_msg_id"] is None
                 or msg_id_band(entry["tlm_msg_id"]) == "telemetry"))
        period = next((a["period_ms"] for a in apps
                       if a["name"] == row["app"]),
                      item.major_cycle_ms)
        acts = max(1, int(math.ceil(item.major_cycle_ms / float(period))))
        entry["period_ms"] = float(period)
        entry["activations_per_frame"] = acts
        entry["msgs_per_frame"] = acts * entry["msgs_per_cycle"]
        seq = telemetry_seq_run(entry["msgs_per_cycle"], acts)
        entry["seq_per_frame"] = {"first_seq": seq["first_seq"],
                                  "last_seq": seq["last_seq"]}
        catalog.append(entry)
    total_msgs_per_frame = sum(e["msgs_per_frame"] for e in catalog)
    bus_design = {
        "msg_id_min": MSG_ID_MIN, "msg_id_max": MSG_ID_MAX,
        "space_size": msg_id_space_size(),
        "command_band": (MSG_ID_MIN, CMD_MSG_ID_MAX),
        "telemetry_band": (TLM_MSG_ID_MIN, MSG_ID_MAX),
        "command_band_size": command_band_size(),
        "telemetry_band_size": telemetry_band_size(),
        "catalog": catalog,
        "distinct_command_ids": len(cmd_ids),
        "distinct_telemetry_ids": len(tlm_ids),
        "total_msgs_per_frame": total_msgs_per_frame,
        "major_cycle_ms": item.major_cycle_ms,
    }

    # --- component model (fprime-component) ---
    verdict = validate_topology(item.components, item.connections,
                                item.rate_groups)
    counts = component_counts(item.components)
    base = item.base_hz if item.base_hz > 0.0 else None
    schedule = rate_group_schedule(item.rate_groups, base_hz=base)
    # map master ticks to wall time when every group period divides the
    # frame (1 tick = major_cycle / ticks_per_frame); compute from the
    # fastest group: ticks_per_frame = round(base_hz * frame / 1000)
    tick_ms = item.major_cycle_ms / max(
        1.0, round(schedule["base_hz"] * item.major_cycle_ms / 1000.0))
    for g in schedule["groups"]:
        g["period_ms"] = round(g["period_ticks"] * tick_ms, 4)
    opcodes = opcode_inventory(item.components)
    tlm_channels = []
    n_events = 0
    for d in item.components:
        for ch in d.get("telemetry") or []:
            tlm_channels.append({"component": d.get("name"),
                                 "channel": ch.get("name"),
                                 "type": ch.get("type")})
        n_events += len(d.get("events") or [])
    component_model = {
        "kinds": counts,
        "components": len(item.components),
        "connections": len(item.connections),
        "rate_groups": len(item.rate_groups),
        "events": n_events,
        "schedule": schedule,
        "tick_ms": tick_ms,
        "topology_issues": len(verdict["issues"]),
        "topology_warnings": len(verdict["warnings"]),
        "topology_verdict": "clean" if not verdict["issues"]
        else "issues",
        "opcodes": opcodes,
        "telemetry_channels": tlm_channels,
    }

    # --- real-time scheduling analysis (real-time-scheduling) ---
    task_pairs = [(p["C_ms"], p["T_ms"]) for p in item.processes]
    sched = scheduling_summary(task_pairs)
    margins = [round(t - r, 4) for r, (_, t)
               in zip(sched["rm_exact_response_times"], task_pairs)] \
        if sched["rm_exact_response_times"] else []
    scheduling = {
        "processes": [dict(p) for p in item.processes],
        "task_pairs": [(p["C_ms"], p["T_ms"]) for p in item.processes],
        "utilization": sched["utilization"],
        "n_tasks": sched["n_tasks"],
        "liu_layland_bound": sched["liu_layland_bound"],
        "rm_ub_verdict": sched["rm_ub_verdict"],
        "rm_exact_response_times": sched["rm_exact_response_times"],
        "rm_exact_feasible": sched["rm_exact_feasible"],
        "edf_feasible": sched["edf_feasible"],
        "verdict": sched["verdict"],
        "deadline_margins_ms": margins,
    }

    # --- shared-resource access control (shared-resource-access-control) ---
    res = rta_with_blocking_feasibility(item.pcp_tasks, item.locks)
    ceilings = priority_ceiling(item.pcp_tasks, item.locks)
    margins_r = {name: round(item.pcp_tasks[name]["T"]
                             - res["response_times"][name], 4)
                 for name in item.pcp_tasks}
    lock_names = {}
    for lock in item.locks:
        resource = lock["resource"]
        if resource not in lock_names:
            lock_names[resource] = (item.lock_descriptions.get(resource)
                                    or resource)
    resources = {
        "tasks": {name: dict(rec)
                  for name, rec in item.pcp_tasks.items()},
        "locks": [dict(l) for l in item.locks],
        "lock_names": lock_names,
        "ceilings": ceilings,
        "blocking": res["blocking"],
        "response_times": res["response_times"],
        "feasible": res["feasible"],
        "deadline_margins_ms": margins_r,
        "empty_lock_identity": blocking_times(item.pcp_tasks, []) ==
        {n: 0.0 for n in item.pcp_tasks},
    }

    # --- verification plan (activities + contract test baseline) ---
    verification = {
        "activities": [dict(v) for v in VERIFICATION_ACTIVITIES],
        "activities_by_stage": {},
        "contract_tests": [
            {"leaf": "avionics/fsw/cfs-architecture",
             "command": "python3 scripts/test_cfs_architecture.py",
             "cases": 15},
            {"leaf": "avionics/fsw/fprime-component",
             "command": "python3 scripts/test_fprime_component.py",
             "cases": 35},
            {"leaf": "avionics/fsw/real-time-scheduling",
             "command": "python3 scripts/test_real_time_scheduling.py",
             "cases": 35},
            {"leaf": "avionics/fsw/shared-resource-access-control",
             "command": "python3 scripts/test_shared_resource_access_control.py",
             "cases": 35},
        ],
        "do178c_planning_areas": list(DO178C_PLANNING_AREAS),
    }
    by_stage = {}
    for v in VERIFICATION_ACTIVITIES:
        by_stage.setdefault(v["stage"], []).append(v["id"])
    verification["activities_by_stage"] = by_stage

    return {
        "document_type": "Flight Software Design and Verification Plan",
        "status": "draft-for-review",
        "item": item.item_name,
        "item_description": item.description,
        "system": item.system,
        "airframe": item.airframe,
        "certification_basis": item.certification_basis,
        "software_level": item.software_level,
        "software_level_source": item.software_level_source,
        "platform": item.platform,
        "layers": layers,
        "applications": apps,
        "bus_design": bus_design,
        "component_model": component_model,
        "scheduling": scheduling,
        "resources": resources,
        "verification": verification,
        "supporting_note": item.supporting_note,
        "generated": _today(),
    }


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def render_design_verification_plan_markdown(model: dict) -> str:
    """Render the plan content model as the deliverable markdown."""
    L = []
    A = L.append
    A("# Flight Software Design and Verification Plan")
    A("")
    A("**Item:** %s" % model["item"])
    if model.get("system"):
        A("**System:** %s" % model["system"])
    if model.get("airframe"):
        A("**Airframe context:** %s" % model["airframe"])
    A("**Certification basis:** %s" % model["certification_basis"])
    A("**Software level (input):** %s" % model["software_level"])
    if model.get("software_level_source"):
        A("  - Source: %s (this plan does not re-derive the level)" %
          model["software_level_source"])
    if model.get("platform"):
        A("**Target platform:** %s" % model["platform"])
    A("**Status:** %s" % model["status"])
    A("")
    A("## 1. Item and software architecture")
    A("")
    A(model["item_description"])
    if model.get("supporting_note"):
        A("")
        A(model["supporting_note"])
    A("")
    A("The software architecture follows the layered flight software "
      "pattern: each layer below has one responsibility, and application "
      "software never calls the real-time OS directly.")
    A("")
    A("| Layer | Role |")
    A("|---|---|")
    for layer in model["layers"]:
        A("| %s | %s |" % (layer["name"], layer["role"]))
    A("")
    A("Application inventory (each application is structured as a "
      "component and owns periodic processes):")
    A("")
    A("| Application | Function | Component kind | Period (ms) |")
    A("|---|---|---|---|")
    for a in model["applications"]:
        A("| %s | %s | %s | %s |"
          % (a["name"], a.get("function", ""), a.get("kind", ""),
             _fmt(a.get("period_ms"))))
    A("")
    A("## 2. Component design model and dispatch schedule")
    A("")
    A("The item is decomposed into components of the supported kinds "
      "(active owns a thread and queue, queued owns a queue without a "
      "thread, passive runs inline in the caller context). Typed ports "
      "carry one payload type; commands are registered per component "
      "with unique opcodes in 0x0000..0xFFFF and require a queue, so "
      "passive components declare none and every active component "
      "declares at least one input port. Telemetry channels carry typed "
      "samples with a monotonic per-channel sequence counter.")
    A("")
    A("Component inventory: **%d total** (%d active, %d queued, %d "
      "passive), **%d connections**, **%d rate group(s)**, "
      "**%d command opcode(s)**, **%d telemetry channel(s)**, "
      "**%d event(s)**."
      % (model["component_model"]["components"],
         model["component_model"]["kinds"]["active"],
         model["component_model"]["kinds"]["queued"],
         model["component_model"]["kinds"]["passive"],
         model["component_model"]["connections"],
         model["component_model"]["rate_groups"],
         len(model["component_model"]["opcodes"]),
         len(model["component_model"]["telemetry_channels"]),
         model["component_model"]["events"]))
    A("")
    sched_m = model["component_model"]["schedule"]
    A("Rate-group dispatch schedule: the master clock runs at the "
      "fastest declared group rate (**%s Hz** by default), and each "
      "group ticks its input ports every max(1, round(base_hz / hz)) "
      "master ticks (one tick = %s ms at %s Hz)."
      % (_fmt(sched_m["base_hz"]), _fmt(model["component_model"]["tick_ms"]),
         _fmt(sched_m["base_hz"])))
    A("")
    A("| Rate group | hz | Period (ticks) | Period (ms) |")
    A("|---|---|---|---|")
    for g in sched_m["groups"]:
        A("| %s | %s | %s | %s |"
          % (g["name"], _fmt(g["hz"]), g["period_ticks"],
             _fmt(g["period_ms"])))
    A("")
    if model["component_model"]["topology_issues"] == 0:
        A("Topology validation: **clean** — 0 issues, 0 warnings. Every "
          "active/queued input port has exactly one dispatch driver "
          "(one incoming connection or one rate group); connections run "
          "output to input with matching data types and no self-loops; "
          "command opcodes are unique.")
    else:
        A("Topology validation: **%d issue(s), %d warning(s)** — see the "
          "open items." % (model["component_model"]["topology_issues"],
                           model["component_model"]["topology_warnings"]))
    A("")
    A("## 3. Software bus command and telemetry design")
    A("")
    bus = model["bus_design"]
    A("Inter-application command and telemetry traffic rides the "
      "software bus publish/subscribe model. Message IDs are 16-bit "
      "(0x0000-0xFFFF): **%d total IDs**, with the command band "
      "0x0000-0x0FFF (**%d IDs**) and the telemetry band 0x1000-0xFFFF "
      "(**%d IDs**) by convention. The upper bits carry the app tag and "
      "the lower bits the message number; the plan allocates one block "
      "per application and validates every ID against its band."
      % (bus["space_size"], bus["command_band_size"],
         bus["telemetry_band_size"]))
    A("")
    A("Command/telemetry catalog (per 20 ms integration frame):")
    A("")
    A("| Application | Command msg ID | Telemetry msg ID | Band check | "
      "msgs/cycle | Activations/frame | msgs/frame | Seq per frame |")
    A("|---|---|---|---|---|---|---|---|")
    for e in bus["catalog"]:
        A("| %s | %s | %s | %s | %s | %s | %s | %s..%s |"
          % (e["app"],
             ("0x%04X" % e["cmd_msg_id"]) if e["cmd_msg_id"] is not None
             else "none",
             ("0x%04X" % e["tlm_msg_id"]) if e["tlm_msg_id"] is not None
             else "none",
             "OK" if e["band_ok"] else "CHECK",
             e["msgs_per_cycle"], e["activations_per_frame"],
             e["msgs_per_frame"], e["seq_per_frame"]["first_seq"],
             e["seq_per_frame"]["last_seq"]))
    A("")
    A("**Total software bus telemetry load: %d messages per %s ms "
      "integration frame (%d per second).**"
      % (bus["total_msgs_per_frame"], _fmt(bus["major_cycle_ms"]),
         int(bus["total_msgs_per_frame"]
             / bus["major_cycle_ms"] * 1000.0)))
    A("")
    A("Every telemetry message carries a monotonic sequence counter per "
      "message ID (the frame budget above), so the ground station can "
      "detect dropped packets from counter gaps. Event service entries "
      "carry one of the severities DEBUG, INFO, EVENT, ERROR, CRITICAL.")
    A("")
    A("## 4. Process scheduling analysis")
    A("")
    sc = model["scheduling"]
    A("The periodic processes of the rate-group schedule form a "
      "(C, T) task set with implicit deadlines (D = T) in one time unit; "
      "shorter period means higher priority under rate-monotonic (RM) "
      "scheduling.")
    A("")
    A("| Process | C (ms) | T (ms) | Utilization share |")
    A("|---|---|---|---|")
    for p, (c, t) in zip(sc["processes"], sc["task_pairs"]):
        A("| %s | %s | %s | %s |" % (p["name"], _fmt(c), _fmt(t),
                                     _fmt(c / t)))
    A("")
    A("**Processor utilization U = sum(C_i / T_i) = %s.** "
      "Liu-Layland sufficient bound for %d tasks: U_rm(%d) = %s "
      "(decreasing toward ln 2 ~ 0.693 as n grows)."
      % (_fmt(sc["utilization"]), sc["n_tasks"], sc["n_tasks"],
         _fmt(sc["liu_layland_bound"], 6)))
    A("")
    if sc["rm_ub_verdict"]:
        A("Utilization bound test: U = %s <= U_rm(%d) = %s -> **RM "
          "feasibility guaranteed by the bound**."
          % (_fmt(sc["utilization"]), sc["n_tasks"],
             _fmt(sc["liu_layland_bound"], 6)))
    else:
        A("Utilization bound test: U = %s > U_rm(%d) = %s -> bound "
          "inconclusive; the exact response-time analysis below decides."
          % (_fmt(sc["utilization"]), sc["n_tasks"],
             _fmt(sc["liu_layland_bound"], 6)))
    A("")
    A("Exact response-time analysis (fixed point of R_i = C_i + sum over "
      "higher-priority j of ceil(R_i / T_j) * C_j):")
    A("")
    A("| Process | R_i (ms) | T_i (ms) | Margin (ms) | Feasible |")
    A("|---|---|---|---|---|")
    for p, r, (_, t), margin in zip(sc["processes"],
                                    sc["rm_exact_response_times"],
                                    sc["task_pairs"],
                                    sc["deadline_margins_ms"]):
        A("| %s | %s | %s | %s | %s |"
          % (p["name"], _fmt(r), _fmt(t), _fmt(margin),
             "YES" if r <= t else "NO"))
    A("")
    A("**RM feasibility: %s.** EDF feasibility (implicit deadlines, "
      "U <= 1 necessary and sufficient): **%s**. Scheduling verdict: "
      "**%s**."
      % ("YES" if sc["rm_exact_feasible"] else "NO",
         "YES" if sc["edf_feasible"] else "NO", sc["verdict"]))
    A("")
    A("## 5. Shared-resource access control design")
    A("")
    rc = model["resources"]
    A("Shared data stores are protected resources under the priority "
      "ceiling protocol. Each task is a {C, T, priority} model (higher "
      "number = higher priority, matching the RM order: the shortest "
      "period process has priority %d). The ceiling of a resource is "
      "the highest priority among the tasks that lock it; under the "
      "ceiling rule a task is blocked by at most one lower-priority "
      "critical section, and only on a resource whose ceiling is at "
      "least its priority."
      % int(max(rc["tasks"][t]["priority"] for t in rc["tasks"])))
    A("")
    A("| Resource | Protected data | Ceiling (priority) |")
    A("|---|---|---|")
    for res, name in rc["lock_names"].items():
        A("| %s | %s | %d |" % (res, name, int(rc["ceilings"][res])))
    A("")
    A("| Process | C (ms) | T (ms) | Priority | Blocking B (ms) | "
      "R with blocking (ms) | Margin (ms) | Feasible |")
    A("|---|---|---|---|---|---|---|---|")
    for name in sorted(rc["tasks"], key=lambda n: -rc["tasks"][n]["priority"]):
        t = rc["tasks"][name]
        A("| %s | %s | %s | %s | %s | %s | %s | %s |"
          % (name, _fmt(t["C"]), _fmt(t["T"]), _fmt(t["priority"]),
             _fmt(rc["blocking"][name]), _fmt(rc["response_times"][name]),
             _fmt(rc["deadline_margins_ms"][name]),
             "YES" if rc["response_times"][name] <= t["T"] else "NO"))
    A("")
    A("**Schedulability with blocking: %s.** Empty-lock identity (no "
      "locks -> zero blocking and the plain response-time analysis): "
      "**%s**."
      % ("FEASIBLE" if rc["feasible"] else "INFEASIBLE",
         "holds" if rc["empty_lock_identity"] else "check"))
    A("")
    A("## 6. Verification plan")
    A("")
    A("Verification activities are requirements-based and mapped to the "
      "design stages above; each carries a pass criterion from the "
      "design discipline it verifies (software bus routing and "
      "telemetry continuity, component and dispatch-driver rules, "
      "scheduling verdicts, blocking analysis).")
    A("")
    A("| ID | Stage | Activity | Method | Pass criterion | Leaf |")
    A("|---|---|---|---|---|---|")
    for v in model["verification"]["activities"]:
        A("| %s | %s | %s | %s | %s | %s |"
          % (v["id"], v["stage"], v["activity"], v["method"],
             v["pass_criteria"], v["leaf"]))
    A("")
    A("Deterministic contract-test baseline (stdlib unittest, offline):")
    A("")
    A("| Leaf | Command | Cases |")
    A("|---|---|---|")
    for ct in model["verification"]["contract_tests"]:
        A("| %s | `%s` | %d |"
          % (ct["leaf"], ct["command"], ct["cases"]))
    A("")
    A("The plan addresses the DO-178C life-cycle planning areas at "
      "summary level (%s); the certification plan itself (PSAC), "
      "structural coverage targets per level, tool qualification and "
      "the level/severity evidence trail belong to the DO-178C "
      "certification engineer role. This plan never asserts those "
      "results."
      % "; ".join(model["verification"]["do178c_planning_areas"]))
    A("")
    A("## 7. Open items and sign-off")
    A("")
    A("Open items to close before the human flight software engineer "
      "reviews this draft:")
    A("")
    if model["component_model"]["topology_issues"] == 0 \
            and model["scheduling"]["rm_exact_feasible"] \
            and model["resources"]["feasible"]:
        A("- None blocking: component topology is clean, the process set "
          "is RM-feasible with margins, and the shared-resource analysis "
          "with blocking is feasible.")
    else:
        A("- Component topology: %d issue(s), %d warning(s) open."
          % (model["component_model"]["topology_issues"],
             model["component_model"]["topology_warnings"]))
        A("- Scheduling: RM feasible = %s; resources with blocking "
          "feasible = %s."
          % (model["scheduling"]["rm_exact_feasible"],
             model["resources"]["feasible"]))
    A("- Software level %s is an INPUT from the system safety assessment "
      "(%s) and must be confirmed against the DO-178C planning flow "
      "before any certification activity." % (model["software_level"],
                                              model["software_level_source"]))
    A("")
    A("---")
    A("*Generated by Aero Agent Roles flight-software-engineer core "
      "(%s). DRAFT for human flight software engineering review. Not an "
      "approval document, not a certification finding, and not a "
      "regulatory sign-off.*" % model["generated"])
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Evidence gate checkers
# ---------------------------------------------------------------------------

GATE_CHECKS = {
    "architecture_stated": "layered architecture and application "
                           "inventory are present",
    "component_model_clean": "component topology validates with zero "
                             "issues and a computed rate-group schedule",
    "bus_numbers_present": "software bus message ID bands, catalog and "
                           "frame loads are computed",
    "scheduling_numbers_present": "utilization, Liu-Layland bound, "
                                  "response times and verdict are computed",
    "resource_numbers_present": "ceilings, blocking and "
                                "response-times-with-blocking are computed",
    "verification_planned": "verification activities carry pass criteria",
    "sign_off_honest": "document is marked draft-for-review, not approval",
}


def check_design_verification_plan(model: dict) -> dict:
    """Run the evidence gates against a plan model."""
    arch = model.get("layers", [])
    comp = model.get("component_model", {})
    bus = model.get("bus_design", {})
    sc = model.get("scheduling", {})
    rc = model.get("resources", {})
    ver = model.get("verification", {})
    results = {
        "architecture_stated": bool(arch) and bool(model.get("applications")),
        "component_model_clean": bool(
            comp.get("topology_issues") == 0
            and comp.get("topology_warnings") == 0
            and bool(comp.get("schedule"))
            and comp["schedule"].get("groups")),
        "bus_numbers_present": (bus.get("space_size") == 65536
                                and bus.get("command_band_size") == 4096
                                and bus.get("telemetry_band_size") == 61440
                                and bool(bus.get("catalog"))),
        "scheduling_numbers_present": (
            isinstance(sc.get("utilization"), float)
            and isinstance(sc.get("liu_layland_bound"), float)
            and sc.get("rm_exact_response_times")
            and sc.get("verdict") in ("RM-guaranteed-by-UB",
                                      "RM-exact-feasible (UB inconclusive)",
                                      "EDF-feasible-only", "RM-infeasible")),
        "resource_numbers_present": (
            bool(rc.get("ceilings")) and bool(rc.get("blocking"))
            and bool(rc.get("response_times"))
            and rc.get("feasible") in (True, False)),
        "verification_planned": bool(ver.get("activities")) and all(
            v.get("pass_criteria") for v in ver["activities"]),
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_design_verification_plan_markdown(md_text: str,
                                            level: str = "") -> dict:
    """Gate-check the rendered markdown deliverable.

    level (optional): when given, the plan must carry that software
    level letter.
    """
    low = md_text.lower()
    checks = {
        "has_title": "flight software design and verification plan" in low,
        "has_item": "item:" in low,
        "has_level": bool(re.search(r"software level \(input\)[:*\s]*"
                                    r"[abcde]\b", low)),
        "has_bus_numbers": "message id" in low and "4096" in low,
        "has_scheduling_number": "processor utilization" in low
                                 and "liu-layland" in low,
        "has_resource_numbers": "priority ceiling" in low
                                and "blocking" in low,
        "has_verification": "verification plan" in low
                            and "pass criterion" in low,
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
    }
    if level:
        checks["level_matches"] = bool(
            re.search(r"software level \(input\)[:*\s]*" + re.escape(level)
                      + r"\b", md_text, re.IGNORECASE))
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str, level: str = "") -> dict:
    """Public entry point used by gate tooling."""
    return check_design_verification_plan_markdown(md_text, level)


# ---------------------------------------------------------------------------
# Example project (worked example: FCC flight software)
# ---------------------------------------------------------------------------

def _component(name, kind, ports=None, commands=None, telemetry=None,
               events=None):
    return {"name": name, "kind": kind, "ports": list(ports or []),
            "commands": list(commands or []),
            "telemetry": list(telemetry or []),
            "events": list(events or [])}


def _conn(comp_from, port_from, comp_to, port_to):
    return {"from": (comp_from, port_from), "to": (comp_to, port_to)}


def _rate_group(name, hz, ports):
    return {"name": name, "hz": float(hz), "ports": list(ports)}


def example_item() -> FlightSoftwareItem:
    """Reference item: the flight control computer (FCC) flight software
    of a transport category airplane, planned under DO-178C. The worked
    numbers are the real anchor values of the bound leaves: the process
    set (1, 5), (2, 10), (3, 20) ms with utilization 0.55 below the
    Liu-Layland bound U_rm(3) = 0.779763; the shared-resource anchor
    ceilings R1 = 3 / R2 = 2, blocking 0.6 / 0.7 / 0.0 and response
    times with blocking 1.6 / 3.7 / 7.0 ms (all feasible)."""
    components = [
        _component("Sensors", "passive",
                   ports=[{"direction": "output", "name": "dataOut",
                           "data_type": "F32"}]),
        _component("ControlLaw", "active",
                   ports=[{"direction": "input", "name": "cycle",
                           "data_type": "U32"},
                          {"direction": "input", "name": "sensorIn",
                           "data_type": "F32"},
                          {"direction": "output", "name": "cmdOut",
                           "data_type": "F32"}],
                   commands=[{"name": "reset", "opcode": 0x01}],
                   events=[{"name": "ctrlFault", "severity": "HIGH"}]),
        _component("Guidance", "active",
                   ports=[{"direction": "input", "name": "cycle",
                           "data_type": "U32"},
                          {"direction": "output", "name": "tgtOut",
                           "data_type": "F32"}],
                   commands=[{"name": "setMode", "opcode": 0x02}],
                   telemetry=[{"name": "guidTgt", "type": "F32"}]),
        _component("HealthMon", "queued",
                   ports=[{"direction": "input", "name": "eventIn",
                           "data_type": "U32"},
                          {"direction": "output", "name": "faultOut",
                           "data_type": "U8"}],
                   telemetry=[{"name": "healthStatus", "type": "U32"}],
                   events=[{"name": "fault", "severity": "FATAL"}]),
        _component("TelemetryMux", "queued",
                   ports=[{"direction": "input", "name": "tlmCtrlIn",
                           "data_type": "F32"},
                          {"direction": "input", "name": "tlmGuidIn",
                           "data_type": "F32"}],
                   telemetry=[{"name": "tlmCtrlIn", "type": "F32"},
                              {"name": "tlmGuidIn", "type": "F32"}]),
        _component("FaultResponse", "passive",
                   ports=[{"direction": "input", "name": "faultIn",
                           "data_type": "U8"}]),
    ]
    connections = [
        _conn("Sensors", "dataOut", "ControlLaw", "sensorIn"),
        _conn("ControlLaw", "cmdOut", "TelemetryMux", "tlmCtrlIn"),
        _conn("Guidance", "tgtOut", "TelemetryMux", "tlmGuidIn"),
        _conn("HealthMon", "faultOut", "FaultResponse", "faultIn"),
    ]
    rate_groups = [
        _rate_group("RG200", 200.0, [("ControlLaw", "cycle")]),
        _rate_group("RG100", 100.0, [("Guidance", "cycle")]),
        _rate_group("RG50", 50.0, [("HealthMon", "eventIn")]),
    ]
    return FlightSoftwareItem(
        item_name="Flight control computer (FCC) flight software",
        description="The flight control computer application software "
                    "implements the pitch/roll rate control laws of the "
                    "fly-by-wire flight control system on the vehicle "
                    "management computer: sensor acquisition, rate-loop "
                    "control, guidance steering, health monitoring and "
                    "fault response, plus telemetry of control and "
                    "guidance outputs to the ground. This plan covers "
                    "the software design (component model, dispatch "
                    "schedule, software bus command/telemetry design, "
                    "process scheduling, shared-resource access control) "
                    "and the verification plan for the item.",
        system="Fly-by-wire flight control system",
        airframe="Transport category airplane",
        certification_basis="DO-178C software life cycle (FAR/CS-25 "
                            "program context)",
        software_level="A",
        software_level_source="FCC system safety assessment - FHA "
                              "condition 'loss of all rate control' "
                              "(catastrophic)",
        platform="cFE 6.x on a partitioned vehicle management computer "
                 "(RTOS with priority ceiling protocol support)",
        layers=[
            {"name": "PSP", "role": "board-specific support (clock, "
             "memory, console); one PSP per target processor"},
            {"name": "OSAL", "role": "RTOS abstraction (tasks, "
             "semaphores, queues, mutexes); apps never call the RTOS "
             "directly"},
            {"name": "cFE services", "role": "executive, software bus, "
             "event, table, time and file services"},
            {"name": "Flight applications", "role": "ControlLaw, "
             "Guidance, HealthMon, TelemetryMux, FaultResponse"},
        ],
        applications=[
            {"name": "ControlLaw", "function": "rate-loop control law",
             "kind": "active", "period_ms": 5.0},
            {"name": "Guidance", "function": "guidance steering target",
             "kind": "active", "period_ms": 10.0},
            {"name": "HealthMon", "function": "health monitoring and "
             "fault annunciation", "kind": "queued", "period_ms": 20.0},
            {"name": "TelemetryMux", "function": "telemetry multiplexing "
             "of control/guidance samples", "kind": "queued",
             "period_ms": 10.0},
            {"name": "FaultResponse", "function": "fault response logic",
             "kind": "passive", "period_ms": 20.0},
        ],
        bus_catalog=[
            {"app": "ControlLaw", "cmd_tag": 0x01, "cmd_num": 0x01,
             "tlm_tag": 0x11, "tlm_num": 0x01, "msgs_per_cycle": 1},
            {"app": "Guidance", "cmd_tag": 0x02, "cmd_num": 0x01,
             "tlm_tag": 0x12, "tlm_num": 0x01, "msgs_per_cycle": 1},
            {"app": "HealthMon", "cmd_tag": 0x03, "cmd_num": 0x01,
             "tlm_tag": 0x13, "tlm_num": 0x01, "msgs_per_cycle": 1},
            {"app": "TelemetryMux", "cmd_tag": None, "cmd_num": None,
             "tlm_tag": 0x14, "tlm_num": 0x01, "msgs_per_cycle": 2},
            {"app": "FaultResponse", "cmd_tag": None, "cmd_num": None,
             "tlm_tag": 0x15, "tlm_num": 0x01, "msgs_per_cycle": 1},
        ],
        major_cycle_ms=20.0,
        processes=[
            {"name": "ControlLaw", "C_ms": 1.0, "T_ms": 5.0},
            {"name": "Guidance", "C_ms": 2.0, "T_ms": 10.0},
            {"name": "HealthMon", "C_ms": 3.0, "T_ms": 20.0},
        ],
        pcp_tasks={
            "ControlLaw": {"C": 1.0, "T": 5.0, "priority": 3.0},
            "Guidance": {"C": 2.0, "T": 10.0, "priority": 2.0},
            "HealthMon": {"C": 3.0, "T": 20.0, "priority": 1.0},
        },
        locks=[
            {"resource": "attitude-state-store", "task": "ControlLaw",
             "cs": 0.5},
            {"resource": "attitude-state-store", "task": "HealthMon",
             "cs": 0.6},
            {"resource": "command-buffer", "task": "Guidance", "cs": 0.8},
            {"resource": "command-buffer", "task": "HealthMon", "cs": 0.7},
        ],
        lock_descriptions={
            "attitude-state-store": "attitude/rate state shared by the "
                                    "rate loop and the health monitor",
            "command-buffer": "command buffer shared by guidance and the "
                              "health monitor",
        },
        components=components,
        connections=connections,
        rate_groups=rate_groups,
        base_hz=0.0,
        supporting_note="Times are in milliseconds. The rate groups of "
                        "the component model (200/100/50 Hz) drive the "
                        "periodic processes analyzed in section 4, whose "
                        "periods are 5/10/20 ms; the shared data stores "
                        "of section 5 are the protected resources of the "
                        "priority ceiling protocol analysis. Software "
                        "bus message IDs follow the classic 16-bit "
                        "layout: app tag in the upper byte, message "
                        "number in the lower byte.",
    )


def example_plan_markdown() -> str:
    return render_design_verification_plan_markdown(
        build_design_verification_plan(example_item()))


def example_plan_model() -> dict:
    return build_design_verification_plan(example_item())


if __name__ == "__main__":
    model = example_plan_model()
    print("ITEM:", model["item"])
    print("BUS SPACE:", model["bus_design"]["space_size"],
          "CMD BAND:", model["bus_design"]["command_band_size"],
          "TLM BAND:", model["bus_design"]["telemetry_band_size"])
    print("TLM MSGS/FRAME:", model["bus_design"]["total_msgs_per_frame"])
    print("TOPOLOGY:", model["component_model"]["topology_issues"],
          "issues /", model["component_model"]["topology_warnings"],
          "warnings; base_hz", model["component_model"]["schedule"]["base_hz"])
    print("UTILIZATION:", model["scheduling"]["utilization"],
          "LL:", model["scheduling"]["liu_layland_bound"],
          "RT:", model["scheduling"]["rm_exact_response_times"],
          "VERDICT:", model["scheduling"]["verdict"])
    print("CEILINGS:", model["resources"]["ceilings"])
    print("BLOCKING:", model["resources"]["blocking"])
    print("RT W/ BLOCKING:", model["resources"]["response_times"],
          "FEASIBLE:", model["resources"]["feasible"])
    print("GATES:", check_design_verification_plan(model))
    print("RENDERED:", len(example_plan_markdown()), "chars")
