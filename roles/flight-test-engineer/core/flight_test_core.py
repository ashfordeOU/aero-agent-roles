#!/usr/bin/env python3
"""flight_test_core.py - Flight Test Engineer executable core.

This is the role's ENGINE: given an aircraft's project facts and the
flight-recorded (or worked-example simulated) data it plans a safe
build-up flight test campaign and produces the flight test plan plus
envelope expansion report: build-up blocks at fractions of the design
limits, V-speed margins, stall/VS1g checks, flutter point progression
with the damping requirement, load factor checks, an altitude/Mach
grid, and per-block PASS/FAIL criteria. It also gate-checks
deliverables. Standalone: no external repo needed.

Domain rules encoded here are public process knowledge as bound in the
Aero Agent Skills flight-test-operations leaves and in the public
FAR-25 / CS-25 context those leaves reference (vref/v2/vr factors, the
VA = VS*sqrt(n_max) maneuvering speed, the FAR 25.629 flutter margin
factor of 1.2 and the 0.03 minimum damping at the maximum test speed,
the FAR 25.207/25.203 stall warning and recovery criteria, equal-step
envelope expansion with the load factor checked at every point, and
ISA atmosphere physics for the altitude/Mach grid). No proprietary text
is reproduced; regulations are paraphrased context only.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date

# ---------------------------------------------------------------------------
# Domain tables (public practice / FAR-25 & CS-25 context, summary-only)
# ---------------------------------------------------------------------------

# Certification V-speed factors (FAR-25.107/25.125 context as encoded in the
# v-speeds AeroSkills leaf): vref = 1.3*vs0, v2 = 1.2*vs1, vr = 1.1*vs1.
VREF_FACTOR = 1.3
V2_FACTOR = 1.2
VR_FACTOR = 1.1

# Maneuvering speed VA = VS * sqrt(n_max) (FAR-25.335 context).
# Stall warning must begin at 1.05 * VS1g, or VS1g + 3 kt, whichever is
# greater (FAR-25.207 / CS-25.207 context, as in the stall leaf).
STALL_WARNING_MARGIN = 0.05
STALL_WARNING_KNOT_FLOOR = 3.0

# Flutter: required demonstration speed = 1.2 * V_D and minimum damping
# 0.03 at the maximum test speed (FAR-25.629 context, flutter-testing leaf).
FLUTTER_MARGIN_FACTOR = 1.2
MIN_DAMPING = 0.03
MIN_FREQ_SEPARATION = 0.10

# Load factor / safety: severity x likelihood risk index; >= 15 is high
# risk and must be mitigated before the flight (flight-test-safety leaf).
HIGH_RISK_INDEX = 15

# ISA constants (public physics) for the altitude/Mach grid.
GAMMA = 1.4
R_AIR = 287.05287          # J/(kg K)
T0_K = 288.15              # ISA sea level temperature
LAPSE_K_PER_M = 0.0065     # troposphere lapse
H_TROPO_M = 11000.0
ISA_EXP = 9.80665 / (R_AIR * LAPSE_K_PER_M) - 1.0   # 4.25588 (density)

MPS_TO_KTS = 1.0 / 0.514444
FT_PER_M = 3.280839895

# Default build-up speed blocks as fractions of the design limit V_D:
# equal increments from 0.85 V_D to 1.00 V_D (dive build-up convention
# in the FAR-25.629 context - clearance is progressive, point by point).
DEFAULT_SPEED_BLOCK_FRACTIONS = (0.85, 0.90, 0.95, 1.00)

# Load factor build-up for the maneuver envelope: fractions of n_max.
DEFAULT_LOAD_FACTOR_BLOCKS = (0.5, 0.75, 1.0)

# Planned test altitudes for the altitude/Mach grid, meters pressure alt.
DEFAULT_ALTITUDES_M = (0.0, 7620.0, 10668.0)   # SL / FL250 / FL350


# ---------------------------------------------------------------------------
# Project facts
# ---------------------------------------------------------------------------

@dataclass
class TestAircraft:
    """Aircraft project facts the role needs to plan and reduce the test."""
    name: str
    description: str = ""
    gross_weight_kg: float = 0.0
    n_max: float = 2.5                    # positive limit load factor
    vs_eas_ms: float = 0.0                # clean 1g stalling speed VS1g, m/s EAS
    vs1_eas_ms: float = 0.0               # takeoff-config stalling speed, m/s EAS
    vs0_eas_ms: float = 0.0               # landing-config stalling speed, m/s EAS
    vfe_eas_ms: float = 0.0               # flaps-extended limit speed
    vno_eas_ms: float = 0.0               # normal operating limit speed
    vne_eas_ms: float = 0.0               # never-exceed speed
    vd_eas_ms: float = 0.0                # design dive speed
    mmo: float = 0.78                     # maximum operating Mach
    certification_basis: str = "FAR/CS-25 (context only)"
    recovery_alt_loss_limit_m: float = 30.0
    recovery_pitch_up_limit_deg: float = 8.0
    recovery_roll_off_limit_deg: float = 20.0


# ---------------------------------------------------------------------------
# Core computations (real rules, real numbers)
# ---------------------------------------------------------------------------

def _require_positive(value, name):
    if value <= 0:
        raise ValueError("%s must be positive, got %r" % (name, value))


def _require_ordered_placards(ac: TestAircraft) -> None:
    """Placard ordering 0 < vfe < va < vno < vne < vd (design context)."""
    va = corner_speed(ac.vs_eas_ms, ac.n_max)
    order = (ac.vfe_eas_ms, va, ac.vno_eas_ms, ac.vne_eas_ms, ac.vd_eas_ms)
    if not (0 < order[0] < order[1] < order[2] < order[3] < order[4]):
        raise ValueError(
            "placard order must be 0 < vfe < va < vno < vne < vd, got %r"
            % (order,))


def corner_speed(vs_ms, n_max):
    """Maneuvering speed VA = VS * sqrt(n_max), speeds in m/s.

    Raises ValueError when vs_ms <= 0 or n_max <= 1."""
    if vs_ms <= 0:
        raise ValueError("stall speed must be > 0, got %r" % (vs_ms,))
    if n_max <= 1:
        raise ValueError("limit load factor must be > 1, got %r" % (n_max,))
    return vs_ms * math.sqrt(n_max)


def v_speeds(ac: TestAircraft) -> dict:
    """Assemble the validated V-speed set from the stall speeds (m/s EAS).

    vref = 1.3*vs0, v2 = 1.2*vs1, vr = 1.1*vs1 plus VA = vs*sqrt(n_max)."""
    for name, value in (("vs", ac.vs_eas_ms), ("vs1", ac.vs1_eas_ms),
                        ("vs0", ac.vs0_eas_ms)):
        _require_positive(value, name)
    if not (ac.vs0_eas_ms <= ac.vs1_eas_ms <= ac.vs_eas_ms):
        raise ValueError(
            "stall speeds must satisfy vs0 <= vs1 <= vs (clean), got "
            "vs0=%r vs1=%r vs=%r" % (ac.vs0_eas_ms, ac.vs1_eas_ms,
                                     ac.vs_eas_ms))
    va = corner_speed(ac.vs_eas_ms, ac.n_max)
    return {
        "vs": ac.vs_eas_ms,
        "vs1": ac.vs1_eas_ms,
        "vs0": ac.vs0_eas_ms,
        "vref": VREF_FACTOR * ac.vs0_eas_ms,
        "v2": V2_FACTOR * ac.vs1_eas_ms,
        "vr": VR_FACTOR * ac.vs1_eas_ms,
        "va": va,
    }


def classify_airspeed(v_ms, vfe, va, vno, vne):
    """Classify a test speed into a flight test category.

    Half-open boundaries: v < vfe -> below-vfe; vfe <= v < va ->
    vfe-to-va; va <= v < vno -> va-to-vno; vno <= v < vne ->
    vno-to-vne; v >= vne -> at-or-above-vne. Raises ValueError when
    v_ms < 0 or the bound order 0 < vfe < va < vno < vne is violated."""
    if v_ms < 0:
        raise ValueError("airspeed must be >= 0, got %r" % (v_ms,))
    if not (0 < vfe < va < vno < vne):
        raise ValueError(
            "bound order must be 0 < vfe < va < vno < vne, got %r"
            % ((vfe, va, vno, vne),))
    if v_ms < vfe:
        return "below-vfe"
    if v_ms < va:
        return "vfe-to-va"
    if v_ms < vno:
        return "va-to-vno"
    if v_ms < vne:
        return "vno-to-vne"
    return "at-or-above-vne"


def speed_block_targets(limit_ms, fractions=DEFAULT_SPEED_BLOCK_FRACTIONS):
    """Build-up block speeds = fraction * limit (m/s EAS).

    Validates equal fraction increments and that the top block reaches
    the limit (>= 0.99*limit). Returns a list of block dicts."""
    if len(fractions) < 2:
        raise ValueError("need at least two block fractions")
    steps = [round(b - a, 6) for a, b in zip(fractions, fractions[1:])]
    if len(set(steps)) != 1 or steps[0] <= 0:
        raise ValueError("fractions must increase in equal steps, got %r"
                         % (fractions,))
    if fractions[-1] < 0.99:
        raise ValueError("top block must reach the limit, got %r"
                         % (fractions[-1],))
    blocks = []
    for i, frac in enumerate(fractions, start=1):
        blocks.append({
            "id": "S%d" % i,
            "fraction": frac,
            "target_eas_ms": limit_ms * frac,
        })
    return blocks


def flutter_required_speed(vd_ms, margin_factor=FLUTTER_MARGIN_FACTOR):
    """Required flutter demonstration speed V_F = margin_factor * V_D."""
    _require_positive(vd_ms, "vd")
    _require_positive(margin_factor, "margin_factor")
    return margin_factor * vd_ms


def damping_margin(damping_at_v_test, min_damping=MIN_DAMPING):
    """Damping margin verdict at the maximum test speed."""
    _require_positive(min_damping, "min_damping")
    return {"damping": damping_at_v_test, "min_required": min_damping,
            "pass": damping_at_v_test >= min_damping}


def frequency_separation(f1, f2, min_frac=MIN_FREQ_SEPARATION):
    """Mode frequency separation |f1-f2| / mean(f1,f2) vs min_frac."""
    _require_positive(f1, "f1")
    _require_positive(f2, "f2")
    _require_positive(min_frac, "min_frac")
    separation = abs(f1 - f2) / ((f1 + f2) / 2.0)
    return {"f1": f1, "f2": f2, "separation": separation,
            "min_frac": min_frac, "pass": separation >= min_frac}


def flutter_speed_from_damping(speeds, dampings):
    """Extrapolated flutter speed from the damping vs test speed trend.

    Least squares line damping = m*speed + b; V_F = -b/m at zero
    crossing. Speeds strictly increasing, >= 2 points, decreasing
    trend (slope < 0). Raises ValueError otherwise."""
    n = len(speeds)
    if n == 0 or len(dampings) == 0:
        raise ValueError("speeds and dampings must not be empty")
    if n != len(dampings):
        raise ValueError("speeds and dampings lengths differ")
    if n < 2:
        raise ValueError("at least two damping points are required")
    if any(speeds[i] >= speeds[i + 1] for i in range(n - 1)):
        raise ValueError("speeds must be strictly increasing")
    sx = sum(speeds)
    sy = sum(dampings)
    sxx = sum(x * x for x in speeds)
    sxy = sum(x * y for x, y in zip(speeds, dampings))
    denom = n * sxx - sx * sx
    if denom == 0:
        raise ValueError("degenerate speed set")
    m = (n * sxy - sx * sy) / denom
    b = (sy - m * sx) / n
    if m >= 0:
        raise ValueError("damping trend is not decreasing; no zero crossing")
    return -b / m


def flutter_margin_ratio(vf_measured, vd, required_ratio=FLUTTER_MARGIN_FACTOR):
    """Flutter margin verdict ratio = V_F_measured / V_D >= 1.2."""
    _require_positive(vf_measured, "vf_measured")
    _require_positive(vd, "vd")
    _require_positive(required_ratio, "required_ratio")
    ratio = vf_measured / vd
    return {"ratio": ratio, "required_ratio": required_ratio,
            "pass": ratio >= required_ratio}


def stall_warning_required(vs1g_ms):
    """Warning onset speed required: 1.05*VS1g or VS1g + 3 kt, greater."""
    _require_positive(vs1g_ms, "vs1g")
    knot_floor_ms = STALL_WARNING_KNOT_FLOOR * 0.514444
    return max(vs1g_ms * (1.0 + STALL_WARNING_MARGIN), vs1g_ms + knot_floor_ms)


def stall_warning_verdict(vs1g_ms, observed_warning_ms):
    """Verdict that the observed stall warning onset meets the margin."""
    required = stall_warning_required(vs1g_ms)
    ok = observed_warning_ms >= required
    return {"required_ms": required, "observed_ms": observed_warning_ms,
            "ok": ok}


def accelerated_stall_speed(vs1g_ms, load_factor):
    """Stall speed at an elevated entry load factor V = vs1g*sqrt(n)."""
    _require_positive(vs1g_ms, "vs1g")
    if load_factor < 1:
        raise ValueError("entry load factor must be >= 1")
    return vs1g_ms * math.sqrt(load_factor)


def level_turn_load_factor(bank_deg):
    """Load factor n = 1/cos(bank) of a coordinated level turn."""
    if abs(bank_deg) >= 90.0:
        raise ValueError("bank must be strictly between -90 and 90 deg")
    return 1.0 / math.cos(math.radians(bank_deg))


def stall_recovery_verdict(ac: TestAircraft, altitude_loss_m, pitch_up_deg,
                           roll_off_deg):
    """Recovery characteristics verdict against the program limits."""
    if altitude_loss_m < 0 or pitch_up_deg < 0 or roll_off_deg < 0:
        raise ValueError("observed recovery values must be >= 0")
    alt_ok = altitude_loss_m <= ac.recovery_alt_loss_limit_m
    pitch_ok = pitch_up_deg <= ac.recovery_pitch_up_limit_deg
    roll_ok = roll_off_deg <= ac.recovery_roll_off_limit_deg
    return {"altitude_loss_ok": alt_ok, "pitch_up_ok": pitch_ok,
            "roll_off_ok": roll_ok,
            "ok": alt_ok and pitch_ok and roll_ok}


def risk_index(severity, likelihood):
    """Risk index = severity * likelihood (both 1..5, ints)."""
    if not (1 <= severity <= 5 and 1 <= likelihood <= 5):
        raise ValueError("severity and likelihood must be in 1..5")
    return severity * likelihood


def load_factor_within_limit(n, n_max):
    """True when the applied load factor is within the positive limit."""
    if n < 0:
        raise ValueError("load factor must be >= 0")
    _require_positive(n_max, "n_max")
    return n <= n_max


# ---------------------------------------------------------------------------
# ISA atmosphere for the altitude / Mach grid (public physics)
# ---------------------------------------------------------------------------

def isa_temperature_k(h_m):
    """ISA static temperature at geopotential altitude h_m."""
    if h_m < 0 or h_m > 20000.0:
        raise ValueError("altitude out of ISA model range")
    if h_m <= H_TROPO_M:
        return T0_K - LAPSE_K_PER_M * h_m
    return T0_K - LAPSE_K_PER_M * H_TROPO_M


def isa_density_ratio(h_m):
    """ISA density ratio sigma at geopotential altitude h_m."""
    if h_m <= H_TROPO_M:
        return (1.0 - LAPSE_K_PER_M * h_m / T0_K) ** ISA_EXP
    sigma_t = (1.0 - LAPSE_K_PER_M * H_TROPO_M / T0_K) ** ISA_EXP
    t_tropo = isa_temperature_k(H_TROPO_M)
    h_iso = R_AIR * t_tropo / 9.80665
    return sigma_t * math.exp(-(h_m - H_TROPO_M) / h_iso)


def mach_grid_row(ac: TestAircraft, h_m, eas_ms):
    """Reduce a test EAS at altitude to TAS and Mach (ISA).

    Returns dict with sigma, temperature, speed of sound, TAS, Mach,
    and the limiting factor against MMO."""
    if h_m < 0:
        raise ValueError("altitude must be >= 0")
    _require_positive(eas_ms, "eas_ms")
    sigma = isa_density_ratio(h_m)
    t_k = isa_temperature_k(h_m)
    a_ms = math.sqrt(GAMMA * R_AIR * t_k)
    tas_ms = eas_ms / math.sqrt(sigma)
    mach = tas_ms / a_ms
    return {"h_m": h_m, "h_ft": h_m * FT_PER_M, "sigma": sigma,
            "t_k": t_k, "a_ms": a_ms, "tas_ms": tas_ms, "mach": mach,
            "mmo": ac.mmo,
            "limiting": ("mach-limited" if mach >= ac.mmo else "eas-limited")}


# ---------------------------------------------------------------------------
# Deliverable builder: plan + envelope expansion report content model
# ---------------------------------------------------------------------------

def build_flight_test_deliverable(ac: TestAircraft, data: dict | None = None) -> dict:
    """Build the flight test plan + envelope report content model.

    data is the flight-recorded (or worked-example simulated) data dict;
    when None the example simulated data is used. The model carries every
    computed number and verdict; nothing is asserted without a check."""
    if data is None:
        data = example_flight_data()
    speeds = v_speeds(ac)
    _require_ordered_placards(ac)
    va = speeds["va"]

    # --- Build-up speed blocks (fractions of V_D) ---------------------------
    speed_blocks = speed_block_targets(ac.vd_eas_ms)
    for blk in speed_blocks:
        blk["category"] = classify_airspeed(
            blk["target_eas_ms"], ac.vfe_eas_ms, va, ac.vno_eas_ms,
            ac.vne_eas_ms)
        blk["abort"] = ("immediate pull-up + throttle reduction if buffet, "
                        "LCO, or control anomaly")
        blk["criteria"] = ("PASS: damping >= 0.03 at point, no LCO, load "
                           "factor within %.1f g; FAIL otherwise" % ac.n_max)

    # --- Flutter build-up / point progression -------------------------------
    flutter_pts = data["flutter_points"]
    if len(flutter_pts["speeds"]) != len(speed_blocks):
        raise ValueError("flutter data must cover every speed block")
    vf_req = flutter_required_speed(ac.vd_eas_ms)
    damp_verdicts = []
    for blk, dmp in zip(speed_blocks, flutter_pts["dampings"]):
        damp_verdicts.append(damping_margin(dmp))
    vf_meas = flutter_speed_from_damping(list(flutter_pts["speeds"]),
                                         list(flutter_pts["dampings"]))
    margin = flutter_margin_ratio(vf_meas, ac.vd_eas_ms)
    mode_pairs = [frequency_separation(f1, f2) for f1, f2 in
                  data["gvt_modes"]]
    flutter = {
        "required_speed_ms": vf_req,
        "points": [{"block": blk["id"], "speed_ms": sp, "damping": dmp,
                    "damping_pass": dv["pass"]}
                   for blk, sp, dmp, dv in zip(speed_blocks,
                                               flutter_pts["speeds"],
                                               flutter_pts["dampings"],
                                               damp_verdicts)],
        "vf_extrapolated_ms": vf_meas,
        "margin": margin,
        "mode_pairs": mode_pairs,
        "min_separation": min(p["separation"] for p in mode_pairs),
        "pass": margin["pass"] and all(dv["pass"] for dv in damp_verdicts)
                and min(p["separation"] for p in mode_pairs)
                >= MIN_FREQ_SEPARATION,
    }

    # --- Altitude / Mach grid ------------------------------------------------
    mach_grid = [mach_grid_row(ac, h, ac.vd_eas_ms)
                 for h in DEFAULT_ALTITUDES_M]

    # --- Stall / VS1g matrix --------------------------------------------------
    stall_rows = []
    stall_all_ok = True
    for row in data["stall_rows"]:
        req = stall_warning_required(row["vs_measured"])
        wv = stall_warning_verdict(row["vs_measured"], row["warning_onset"])
        rec = None
        if row.get("recovery"):
            rec = stall_recovery_verdict(ac, row["recovery"]["alt_loss_m"],
                                         row["recovery"]["pitch_up_deg"],
                                         row["recovery"]["roll_off_deg"])
            rec["altitude_loss_m"] = row["recovery"]["alt_loss_m"]
            rec["pitch_up_deg"] = row["recovery"]["pitch_up_deg"]
            rec["roll_off_deg"] = row["recovery"]["roll_off_deg"]
            row_ok = wv["ok"] and rec["ok"]
        else:
            row_ok = wv["ok"]
        stall_all_ok = stall_all_ok and row_ok
        stall_rows.append({
            "config": row["config"],
            "vs1g_measured": row["vs_measured"],
            "warning_required": req,
            "warning_onset": row["warning_onset"],
            "warning_ok": wv["ok"],
            "recovery": rec,
            "ok": row_ok,
        })

    # --- Envelope / load factor blocks ----------------------------------------
    n_blocks = []
    for i, frac in enumerate(DEFAULT_LOAD_FACTOR_BLOCKS, start=1):
        target_n = frac * ac.n_max
        achieved = data["maneuver_n"][i - 1]
        n_blocks.append({
            "id": "L%d" % i, "fraction": frac, "target_n": target_n,
            "achieved_n": achieved, "ok": load_factor_within_limit(
                achieved, ac.n_max),
        })

    # --- Climb performance check ----------------------------------------------
    climb = {
        "roc_fpm": data["climb_roc_fpm"],
        "gradient_pct": data["climb_gradient_pct"],
        "required_gradient_pct": 2.4,   # FAR-25.121 context, two-engine
        "margin_pct": data["climb_gradient_pct"] - 2.4,
        "pass": data["climb_gradient_pct"] >= 2.4,
    }

    # --- Safety register --------------------------------------------------------
    safety_rows = []
    for r in data["risk_rows"]:
        idx = risk_index(r["severity"], r["likelihood"])
        safety_rows.append({
            "hazard": r["hazard"],
            "severity": r["severity"],
            "likelihood": r["likelihood"],
            "index": idx,
            "high": idx >= HIGH_RISK_INDEX,
            "mitigation": r["mitigation"],
        })
    go_no_go = {"checks": data["go_no_go"],
                "go": all(data["go_no_go"].values())}

    # --- Limit changes traced to data points -------------------------------------
    limit_changes = data["limit_changes"]

    objectives = [
        "Determine VS1g and the V-speed set (vref/v2/vr/VA) with "
        "warning-margin evidence in every configuration",
        "Demonstrate freedom from flutter to V_D with damping >= 0.03 at "
        "the maximum test speed and an extrapolated margin >= 1.2*V_D",
        "Expand the speed and load factor envelope in build-up blocks to "
        "V_D / n_max with a load factor check at every point",
        "Verify stall recovery characteristics within the program limits",
        "Measure climb performance and check the gradient requirement",
    ]

    model = {
        "document_type": "Flight Test Plan and Envelope Expansion Report",
        "status": "draft-for-review",
        "aircraft": ac.name,
        "aircraft_description": ac.description,
        "certification_basis": ac.certification_basis,
        "generated": date.today().isoformat(),
        "objectives": objectives,
        "v_speeds": speeds,
        "n_max": ac.n_max,
        "placards": {"vfe": ac.vfe_eas_ms, "vno": ac.vno_eas_ms,
                     "vne": ac.vne_eas_ms, "vd": ac.vd_eas_ms,
                     "mmo": ac.mmo},
        "recovery_limits": {"alt_loss_m": ac.recovery_alt_loss_limit_m,
                            "pitch_up_deg": ac.recovery_pitch_up_limit_deg,
                            "roll_off_deg": ac.recovery_roll_off_limit_deg},
        "speed_blocks": speed_blocks,
        "flutter": flutter,
        "mach_grid": mach_grid,
        "stall_rows": stall_rows,
        "stall_all_ok": stall_all_ok,
        "n_blocks": n_blocks,
        "climb": climb,
        "safety_rows": safety_rows,
        "safety_no_unmitigated": not any(r["high"] for r in safety_rows),
        "go_no_go": go_no_go,
        "limit_changes": limit_changes,
        "example_data_note": data.get("note", ""),
    }
    return model


# ---------------------------------------------------------------------------
# Renderer: the actual deliverable markdown document
# ---------------------------------------------------------------------------

def _fmt_ms(v):
    return "%.1f" % v


def _kt(v):
    return "%.0f" % (v * MPS_TO_KTS)


def _verdict(ok):
    return "PASS" if ok else "FAIL"


def render_flight_test_markdown(model: dict) -> str:
    """Render the content model as the deliverable markdown document."""
    vs = model["v_speeds"]
    pl = model["placards"]
    L = []
    L += [
        "# Flight Test Plan and Envelope Expansion Report",
        "",
        f"**Aircraft:** {model['aircraft']}",
        f"**Basis:** {model['certification_basis']}",
        f"**Status:** {model['status']}",
        "",
    ]
    if model.get("example_data_note"):
        L += ["_%s_" % model["example_data_note"], ""]

    # 1. Objectives and configuration
    L += ["## 1. Objectives and configuration", "",
          *[f"- {o}" for o in model["objectives"]], "",
          f"- Limit load factor: n_max = {model['n_max']:.1f} g positive. "
          f"Stall speeds (EAS): VS1g = {_fmt_ms(vs['vs'])} m/s "
          f"({_kt(vs['vs'])} kt), VS1 = {_fmt_ms(vs['vs1'])} m/s "
          f"({_kt(vs['vs1'])} kt), VS0 = {_fmt_ms(vs['vs0'])} m/s "
          f"({_kt(vs['vs0'])} kt).",
          f"- Placards (EAS): VFE = {_fmt_ms(pl['vfe'])} m/s, "
          f"VNO = {_fmt_ms(pl['vno'])} m/s, VNE = {_fmt_ms(pl['vne'])} m/s, "
          f"V_D = {_fmt_ms(pl['vd'])} m/s, MMO = {pl['mmo']:.2f}.",
          f"- Derived: VA = {_fmt_ms(vs['va'])} m/s "
          f"({_kt(vs['va'])} kt), vref = {_fmt_ms(vs['vref'])} m/s "
          f"({_kt(vs['vref'])} kt), v2 = {_fmt_ms(vs['v2'])} m/s "
          f"({_kt(vs['v2'])} kt), vr = {_fmt_ms(vs['vr'])} m/s "
          f"({_kt(vs['vr'])} kt).",
          f"- Crew: test pilot + flight test engineer console; "
          f"airspace: restricted area; instrumentation: calibrated "
          f"pitot-static, accelerometers, strain gauges on wing/elevator, "
          f"flutter excitation vanes, telemetry with real-time damping.",
          "",
    ]

    # 2. Safety
    L += ["## 2. Safety", "",
          "| Hazard | Sev | Lik | Risk | High (>=15) | Mitigation |",
          "|---|---|---|---|---|---|"]
    for r in model["safety_rows"]:
        L.append("| %s | %d | %d | %d | %s | %s |" % (
            r["hazard"], r["severity"], r["likelihood"], r["index"],
            "yes" if r["high"] else "no", r["mitigation"]))
    unmit = "true" if model["safety_no_unmitigated"] else "FALSE - blocked"
    L += ["", "Every high-risk item is mitigated before the flight: %s."
          % unmit,
          "",
          "| Go/no-go criterion | Value |",
          "|---|---|"]
    for name, ok in model["go_no_go"]["checks"].items():
        L.append("| %s | %s |" % (name, "GO" if ok else "NO-GO"))
    L += ["", "Flight release: %s." % (
        "GO" if model["go_no_go"]["go"] else "NO-GO - blocked"), ""]

    # 3. Build-up plan
    L += ["## 3. Build-up plan", "",
          "Build-up order: GVT -> flutter build-up (blocks S1..S4) -> "
          "stall matrix -> load factor envelope -> climb performance. "
          "Each block clears before the next is flown; every block states "
          "its limit, abort criteria, and PASS/FAIL criteria.",
          "",
          "### 3.1 Flutter build-up (speed blocks as fractions of V_D)", ""]
    L += ["| Block | V_D fraction | Target (EAS) | Category | Abort | "
          "PASS/FAIL criteria |",
          "|---|---|---|---|---|---|"]
    for blk in model["speed_blocks"]:
        L.append("| %s | %.2f | %s m/s (%s kt) | %s | %s | %s |" % (
            blk["id"], blk["fraction"], _fmt_ms(blk["target_eas_ms"]),
            _kt(blk["target_eas_ms"]), blk["category"], blk["abort"],
            blk["criteria"]))
    fl = model["flutter"]
    L += ["",
          f"Required flutter demonstration speed: V_F = "
          f"{_fmt_ms(fl['required_speed_ms'])} m/s "
          f"({FLUTTER_MARGIN_FACTOR:.1f} x V_D). Damping >= 0.03 required "
          f"at the maximum test speed; structural mode frequency "
          f"separation >= {MIN_FREQ_SEPARATION:.2f} at every point.",
          "",
          "### 3.2 Altitude / Mach grid (V_D tested per altitude, ISA)", ""]
    L += ["| Altitude | Density ratio | Speed of sound | TAS at V_D | "
          "Mach at V_D | MMO | Limit |",
          "|---|---|---|---|---|---|---|"]
    for g in model["mach_grid"]:
        L.append("| %d ft | %.3f | %.1f m/s | %.1f m/s | %.3f | %.2f | %s |"
                 % (round(g["h_ft"]), g["sigma"], g["a_ms"], g["tas_ms"],
                    g["mach"], g["mmo"], g["limiting"]))
    L += ["",
          "### 3.3 Stall matrix (VS1g and warning onset per configuration)",
          ""]
    L += ["| Config | Measured VS1g (EAS) | Warning required | Warning "
          "onset | Recovery limits |",
          "|---|---|---|---|---|"]
    for row in model["stall_rows"]:
        L.append("| %s | %s m/s | %s m/s | %s m/s | alt <= %.0f m, pitch "
                 "<= %.0f deg, roll <= %.0f deg |" % (
                     row["config"], _fmt_ms(row["vs1g_measured"]),
                     _fmt_ms(row["warning_required"]),
                     _fmt_ms(row["warning_onset"]),
                     model["recovery_limits"]["alt_loss_m"],
                     model["recovery_limits"]["pitch_up_deg"],
                     model["recovery_limits"]["roll_off_deg"]))
    L += ["",
          "### 3.4 Load factor envelope (pull blocks at VA or above)", ""]
    L += ["| Block | n_max fraction | Target n | PASS/FAIL |",
          "|---|---|---|---|"]
    for b in model["n_blocks"]:
        L.append("| %s | %.2f | %.2f g | PASS if n <= %.1f g at point, "
                 "with no buffet/LCO |" % (b["id"], b["fraction"],
                                           b["target_n"], model["n_max"]))
    L += ["",
          "### 3.5 Climb performance",
          "",
          "Sawtooth climb segments at constant indicated airspeed; "
          f"gradient check against {model['climb']['required_gradient_pct']}"
          " % (two-engine context).",
          "",
    ]

    # 4. Results
    L += ["## 4. Results", "", "### 4.1 Flutter build-up points", ""]
    L += ["| Block | Speed (EAS) | Damping | Min damping | Verdict |",
          "|---|---|---|---|---|"]
    for p in fl["points"]:
        L.append("| %s | %s m/s | %.3f | %.3f | %s |" % (
            p["block"], _fmt_ms(p["speed_ms"]), p["damping"],
            MIN_DAMPING, _verdict(p["damping_pass"])))
    L += ["",
          f"Extrapolated flutter speed from the damping trend: "
          f"{_fmt_ms(fl['vf_extrapolated_ms'])} m/s; margin ratio "
          f"{fl['margin']['ratio']:.2f} vs required "
          f"{fl['margin']['required_ratio']:.1f} -> "
          f"{_verdict(fl['margin']['pass'])}.",
          "",
          "Structural mode frequency separation (GVT pairs):"]
    for p in fl["mode_pairs"]:
        L.append(f"- mode pair {p['f1']:.1f} Hz / {p['f2']:.1f} Hz: "
                 f"separation {p['separation']:.2f} >= "
                 f"{p['min_frac']:.2f} -> {_verdict(p['pass'])}")
    L += ["", "### 4.2 Stall results", ""]
    L += ["| Config | VS1g (EAS) | Warning onset | Warning margin | "
          "Recovery | Verdict |",
          "|---|---|---|---|---|---|"]
    for row in model["stall_rows"]:
        if row["recovery"]:
            rec = "alt %.0f m / pitch %.0f deg / roll %.0f deg" % (
                row["recovery"]["altitude_loss_m"],
                row["recovery"]["pitch_up_deg"],
                row["recovery"]["roll_off_deg"])
        else:
            rec = "-"
        L.append("| %s | %s m/s | %s m/s | %+.2f m/s | %s | %s |" % (
            row["config"], _fmt_ms(row["vs1g_measured"]),
            _fmt_ms(row["warning_onset"]),
            row["warning_onset"] - row["vs1g_measured"], rec,
            _verdict(row["ok"])))
    L += ["", "### 4.3 Load factor envelope results", ""]
    L += ["| Block | Target n | Achieved n | Limit | Verdict |",
          "|---|---|---|---|---|"]
    for b in model["n_blocks"]:
        L.append("| %s | %.2f g | %.2f g | %.1f g | %s |" % (
            b["id"], b["target_n"], b["achieved_n"], model["n_max"],
            _verdict(b["ok"])))
    L += ["", "### 4.4 Climb performance results", "",
          f"- Rate of climb: {model['climb']['roc_fpm']:.0f} ft/min "
          f"(segment reduction, corrected to reference weight).",
          f"- Gradient: {model['climb']['gradient_pct']:.2f} % vs "
          f"{model['climb']['required_gradient_pct']:.1f} % required -> "
          f"margin {model['climb']['margin_pct']:+.2f} % "
          f"({_verdict(model['climb']['pass'])}).",
          "",
    ]

    # 5. Limit changes and findings
    L += ["## 5. Findings, limit changes, and recommendations", ""]
    L += ["| Envelope limit change | Traced to data point | Verdict |",
          "|---|---|---|"]
    for ch in model["limit_changes"]:
        L.append("| %s | %s | %s |" % (ch["limit"], ch["data_point"],
                                       _verdict(ch["ok"])))
    L += ["",
          "Recommendations: (1) expand to the top block only after the "
          "damping and separation verdicts above; (2) repeat the "
          "configuration whose stall warning onset is marginal before "
          "envelope use; (3) confirm flutter clearance per point with the "
          "flight test conductor.",
          "",
    ]

    # 6. Sign-off
    L += ["## 6. Sign-off", "",
          "This plan/report states that the recorded data support "
          "expanding to the listed limits PENDING human flight test "
          "conductor review. It is a draft deliverable, not a clearance.",
          "",
          "---",
          f"*Generated by Aero Agent Roles flight-test-engineer core "
          f"({model['generated']}). DRAFT for human flight test conductor "
          f"review. Not a clearance and not an approval of the envelope "
          f"or of flight.*",
    ]
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Evidence gate checkers
# ---------------------------------------------------------------------------

GATE_CHECKS = {
    "objectives_stated": "test objectives are present",
    "blocks_buildup": "speed blocks rise to >= 0.99 of V_D in equal steps",
    "limits_stated": "VNO/VNE/V_D/n_max and flutter margin numbers present",
    "criteria_stated": "every block carries PASS/FAIL criteria",
    "flutter_damping_gate": "damping >= 0.03 verdict present at top speed",
    "sign_off_honest": "deliverable is draft, not a clearance",
}


def check_flight_test_deliverable(model: dict) -> dict:
    """Run the evidence gates against the content model."""
    blocks = model.get("speed_blocks", [])
    fl = model.get("flutter", {})
    results = {
        "objectives_stated": bool(model.get("objectives")),
        "blocks_buildup": bool(blocks) and blocks[-1]["fraction"] >= 0.99,
        "limits_stated": ("vd" in model.get("placards", {})
                          and model.get("n_max") is not None),
        "criteria_stated": all(b.get("criteria") for b in blocks),
        "flutter_damping_gate": bool(fl.get("points")) and all(
            p["damping_pass"] for p in fl.get("points", [])),
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_flight_test_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    checks = {
        "has_title": ("flight test plan" in low
                      and "envelope expansion report" in low),
        "has_limits": bool(re.search(r"vne|v_d|vno", low)),
        "has_blocks": bool(re.search(r"\bs[1-4]\b|\bs%d\b", low))
                      or "0.85" in low,
        "has_pass_fail": "pass" in low and "fail" in low,
        "has_draft_marker": "draft" in low,
        "has_not_clearance": "not a clearance" in low,
        "has_numbers": bool(re.search(r"\d+\.\d+", low)),
        "no_blank_blanks": "___" not in md_text,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling: check a plan/report doc."""
    return check_flight_test_markdown(md_text)


# ---------------------------------------------------------------------------
# Example aircraft and simulated flight data (worked example for tests)
# ---------------------------------------------------------------------------

def example_aircraft() -> TestAircraft:
    """The worked-example reference aircraft (a synthetic light jet)."""
    return TestAircraft(
        name="FT-1 Worked-Example Light Jet",
        description="Synthetic light jet used to demonstrate the flight "
                    "test engineer deliverable. Numbers are for planning "
                    "practice only, not a real vehicle.",
        gross_weight_kg=5900.0,
        n_max=2.5,
        vs_eas_ms=44.0,
        vs1_eas_ms=40.0,
        vs0_eas_ms=36.0,
        vfe_eas_ms=62.0,
        vno_eas_ms=85.0,
        vne_eas_ms=94.0,
        vd_eas_ms=106.0,
        mmo=0.78,
        certification_basis="FAR/CS-25 context (worked example)",
        recovery_alt_loss_limit_m=30.0,
        recovery_pitch_up_limit_deg=8.0,
        recovery_roll_off_limit_deg=20.0,
    )


def example_flight_data() -> dict:
    """Worked-example simulated flight data (clearly labeled; not real)."""
    return {
        "note": "Flight data below are SIMULATED for the worked example "
                "and must be replaced by recorded flight data.",
        "gvt_modes": [(4.2, 11.6), (9.1, 14.8), (11.6, 14.8), (4.2, 9.1)],
        "flutter_points": {
            "speeds": [90.1, 95.4, 100.7, 106.0],
            "dampings": [0.120, 0.115, 0.108, 0.100],
        },
        "stall_rows": [
            {"config": "clean", "vs_measured": 44.1, "warning_onset": 46.8,
             "recovery": {"alt_loss_m": 18.0, "pitch_up_deg": 3.0,
                          "roll_off_deg": 6.0}},
            {"config": "takeoff (flaps)", "vs_measured": 40.4,
             "warning_onset": 42.5,
             "recovery": {"alt_loss_m": 21.0, "pitch_up_deg": 4.0,
                          "roll_off_deg": 8.0}},
            {"config": "landing (flaps/gear)", "vs_measured": 36.3,
             "warning_onset": 38.2,
             "recovery": {"alt_loss_m": 24.0, "pitch_up_deg": 5.0,
                          "roll_off_deg": 9.0}},
        ],
        "maneuver_n": [1.26, 1.88, 2.48],
        "climb_roc_fpm": 1450.0,
        "climb_gradient_pct": 2.70,
        "risk_rows": [
            {"hazard": "Flutter onset at high speed", "severity": 5,
             "likelihood": 2,
             "mitigation": "GVT + build-up blocks, damping gate 0.03, "
                           "excitation vanes, real-time monitoring"},
            {"hazard": "Stall departure at aft CG", "severity": 4,
             "likelihood": 3,
             "mitigation": "entry technique, altitude floor, recovery "
                           "demonstration, spin chute installed"},
            {"hazard": "Overspeed control upset", "severity": 4,
             "likelihood": 2,
             "mitigation": "abort criteria at every block, test pilot "
                           "briefing, VMO/VNE marking"},
            {"hazard": "Engine failure during climb segment", "severity": 3,
             "likelihood": 2,
             "mitigation": "single-engine drills, field/landing options, "
                           "engine instruments monitored"},
            {"hazard": "Telemetry data loss", "severity": 2,
             "likelihood": 3,
             "mitigation": "onboard recording backup, link checked "
                           "pre-flight"},
        ],
        "go_no_go": {"weather": True, "aircraft_ready": True,
                     "instrumentation_ok": True, "safety_review_ok": True,
                     "airspace_ok": True},
        "limit_changes": [
            {"limit": "Speed envelope to 0.85 V_D", "data_point": "S1",
             "ok": True},
            {"limit": "Speed envelope to 0.90 V_D", "data_point": "S2",
             "ok": True},
            {"limit": "Speed envelope to 0.95 V_D", "data_point": "S3",
             "ok": True},
            {"limit": "Speed envelope to 1.00 V_D", "data_point": "S4",
             "ok": True},
        ],
    }


def example_deliverable_markdown() -> str:
    return render_flight_test_markdown(
        build_flight_test_deliverable(example_aircraft()))


if __name__ == "__main__":
    ac = example_aircraft()
    model = build_flight_test_deliverable(ac)
    md = render_flight_test_markdown(model)
    print("AIRCRAFT:", model["aircraft"])
    print("V-SPEEDS:", {k: round(v, 2) for k, v in model["v_speeds"].items()})
    print("FLUTTER REQUIRED: %.1f m/s" % model["flutter"]["required_speed_ms"])
    print("FLUTTER EXTRAPOLATED: %.1f m/s" %
          model["flutter"]["vf_extrapolated_ms"])
    print("FLUTTER MARGIN RATIO: %.3f" % model["flutter"]["margin"]["ratio"])
    print("GATES:", check_flight_test_deliverable(model))
    print("RENDERED:", len(md), "chars")
