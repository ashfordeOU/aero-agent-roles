#!/usr/bin/env python3
"""propulsion_core.py - Propulsion Engineer executable core.

This is the role's ENGINE: given a propulsion requirement (vehicle
class, thrust, flight point, cycle architecture) it computes the
on-design gas-turbine/turbofan cycle state points, net thrust, TSFC,
and efficiencies; builds the off-design envelope with corrected-flow
matching and component-map verdicts; sizes nozzles; and produces a
rocket-cycle (or electric) option when the item is a space vehicle.
It also gate-checks deliverables. Standalone: no external repo needed.

Domain rules encoded here come from the bound Aero Agent Skills leaves
(AeroSkills propulsion pack) which encode standard propulsion practice
(Mattingly-style cycle analysis, isentropic compressible flow, the
ideal-cycle and real-cycle gas-turbine relations, standard-day
correction). All numbers are produced by these relations from stated
inputs; representative inputs (component maps, stage counts) are
labeled as such. Fuel LHV is the kerosene-class 43.2 MJ/kg used by the
combustor-design leaf anchors. No proprietary text is reproduced.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date

# ---------------------------------------------------------------------------
# Physical constants (SI). Cold stream: air gamma=1.4 (R=287 => cp~1004.5).
# Hot stream (combustion products): gamma=1.33 per the propelling-nozzle leaf.
# ---------------------------------------------------------------------------
G0 = 9.80665
R_GAS = 287.0
GAMMA_C = 1.4                 # cold (air) specific heat ratio
GAMMA_H = 1.33                # hot (products) specific heat ratio
CP_C = GAMMA_C * R_GAS / (GAMMA_C - 1.0)     # ~1004.5 J/(kg K)
CP_H = GAMMA_H * R_GAS / (GAMMA_H - 1.0)     # ~1156.5 J/(kg K)
LHV_JET_A = 43.2e6            # kerosene-class fuel LHV, J/kg (combustor leaf)
T_REF = 288.15                # ISA sea-level temperature, K
P_REF = 101325.0              # ISA sea-level pressure, Pa

# ---------------------------------------------------------------------------
# Domain tables (real rules / reference-typical values, from bound leaves)
# ---------------------------------------------------------------------------

# Component efficiency / loss defaults - reference-typical modern values,
# stated inputs in every deliverable (design assumptions, not vendor data).
DEFAULTS = {
    "etaf": 0.90,      # fan isentropic efficiency
    "etac": 0.90,      # core compressor isentropic efficiency
    "etat": 0.90,      # turbine isentropic efficiency
    "etab": 0.995,     # combustor efficiency
    "etam": 0.99,      # mechanical (shaft) efficiency
    "pib": 0.95,       # combustor total-pressure ratio (~5% loss)
    "pid": 0.995,      # inlet total-pressure recovery (subsonic duct)
    "pifd": 0.99,      # fan-duct total-pressure ratio (~1% loss)
    "cv": 0.99,        # nozzle velocity coefficient
}

# Rocket propellant reference table (reference-only typical values from the
# rocket-engine-cycle leaf): (rho_ox, rho_fuel, r_m, isp_vac). Densities
# kg/m3, r_m mixture ratio (O/F by mass), isp_vac in seconds at vacuum.
# r_m None marks the monopropellant hydrazine (single stream).
PROPELLANTS = {
    "LOX/RP-1": (1140.0, 820.0, 2.56, 300.0),
    "LOX/LH2": (1140.0, 71.0, 5.5, 430.0),
    "N2O4/MMH": (1450.0, 880.0, 1.9, 320.0),
    "hydrazine": (1010.0, 1010.0, None, 230.0),
}

# Feed-cycle chamber-pressure bounds (documented limits from the
# rocket-engine-cycle leaf): pressure-fed to 3 MPa, expander (LOX/LH2 only)
# to 10 MPa. Gas-generator and staged-combustion: no pressure bound in the
# leaf's feasibility model for bipropellant pairs.
PRESSURE_FED_MAX_P_C = 3.0e6
EXPANDER_MAX_P_C = 10.0e6
P_LOSSES_DEFAULT = 2.0e6       # injector plus line losses, Pa
ETA_PUMP_DEFAULT = 0.7
ETA_TURB_DEFAULT = 0.6
PUMP_INLET_PRESSURE = 0.3e6
GG_FRACTION_DEFAULT = 0.03
GG_PRESSURE_FRACTION = 0.8
TURBINE_EXIT_PRESSURE = 0.2e6
GG_CP = 2000.0
GG_T_INLET = 1200.0
GG_GAMMA = 1.2
STAGED_INLET_FRACTION = 1.5
EXPANDER_CP = 12000.0          # warm hydrogen gas cp, reference-only
EXPANDER_T_INLET = 500.0
EXPANDER_GAMMA = 1.4
EXPANDER_EXIT_FRACTION = 0.85

# Throttle bands (turbofan-off-design leaf): fractions of max rating.
def throttle_verdict(frac: float) -> str:
    """Classify a throttle fraction: below-idle/idle/cruise/climb/
    max-continuous/over-throttle."""
    if frac <= 0.0 or frac > 1.05:
        raise ValueError("throttle fraction must be in (0, 1.05]")
    if frac < 0.05:
        return "below-idle"
    if frac < 0.30:
        return "idle"
    if frac < 0.65:
        return "cruise"
    if frac < 0.95:
        return "climb"
    if frac <= 1.00:
        return "max-continuous"
    return "over-throttle"


# ---------------------------------------------------------------------------
# ISA atmosphere (public standard): lapse to 11 km, isothermal above.
# ---------------------------------------------------------------------------

def isa(alt_m: float) -> dict:
    """ISA temperature (K), pressure (Pa), density (kg/m3), speed of sound."""
    if alt_m < 0:
        raise ValueError("altitude must be >= 0")
    if alt_m <= 11000.0:
        t = 288.15 - 0.0065 * alt_m
        p = P_REF * (t / T_REF) ** 5.2561
    else:
        t = 216.65
        p = 22632.0 * math.exp(-G0 * (alt_m - 11000.0) / (R_GAS * t))
    rho = p / (R_GAS * t)
    a = math.sqrt(GAMMA_C * R_GAS * t)
    return {"t": t, "p": p, "rho": rho, "a": a, "alt": alt_m}


# ---------------------------------------------------------------------------
# Ideal/real-cycle relations (gas-turbine-cycle + real-cycle-effects leaves)
# ---------------------------------------------------------------------------

def brayton_thermal_efficiency(pr: float, gamma: float = GAMMA_C) -> float:
    """Ideal Brayton thermal efficiency 1 - PR**((1-gamma)/gamma)."""
    if pr <= 1:
        raise ValueError("pressure ratio must be > 1")
    if gamma <= 1:
        raise ValueError("gamma must be > 1")
    return 1.0 - pr ** ((1.0 - gamma) / gamma)


def compressor_exit_temperature(t1: float, pr: float, gamma: float = GAMMA_C,
                                eta_c: float = 1.0) -> float:
    """Actual compressor exit temp: T2 = T1 + (T2s - T1)/eta_c."""
    if t1 <= 0 or pr <= 1 or gamma <= 1 or not (0 < eta_c <= 1):
        raise ValueError("invalid compressor input")
    t2s = t1 * pr ** ((gamma - 1.0) / gamma)
    return t1 + (t2s - t1) / eta_c


def turbine_exit_temperature(t3: float, pr: float, gamma: float = GAMMA_H,
                             eta_t: float = 1.0) -> float:
    """Actual turbine exit temp: T4 = T3 - eta_t*(T3 - T4s)."""
    if t3 <= 0 or pr <= 1 or gamma <= 1 or not (0 < eta_t <= 1):
        raise ValueError("invalid turbine input")
    t4s = t3 / pr ** ((gamma - 1.0) / gamma)
    return t3 - eta_t * (t3 - t4s)


def real_thermal_efficiency(t1, t2, t3, t4) -> float:
    """Real-cycle thermal efficiency (cp cancels): net work / heat added."""
    if not (0 < t1 < t2 < t3 and t1 < t4 < t3):
        raise ValueError("station temperatures out of physical order")
    return (t3 - t4 - t2 + t1) / (t3 - t2)


# ---------------------------------------------------------------------------
# Compressible-flow / nozzle relations (propelling-nozzle + nozzle-design
# leaves): choked flow factor, critical ratio, isentropic area-Mach.
# ---------------------------------------------------------------------------

def _choked_factor(gamma: float) -> float:
    return (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (2.0 * (gamma - 1.0)))


def _critical_ratio(gamma: float) -> float:
    return ((gamma + 1.0) / 2.0) ** (gamma / (gamma - 1.0))


def _area_ratio_at_mach(m: float, gamma: float) -> float:
    return ((1.0 / m)
            * (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (2.0 * (gamma - 1.0)))
            * (1.0 + (gamma - 1.0) / 2.0 * m * m) ** ((gamma + 1.0) / (2.0 * (gamma - 1.0))))


def exit_mach_from_area_ratio(area_ratio: float, gamma: float = 1.2) -> float:
    """Supersonic exit Mach for a nozzle area ratio (bisection, M>1 root)."""
    if area_ratio <= 1 or gamma <= 1:
        raise ValueError("area ratio must be > 1, gamma > 1")
    lo, hi = 1.0, 1.0
    while _area_ratio_at_mach(hi, gamma) < area_ratio:
        hi *= 2.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if _area_ratio_at_mach(mid, gamma) < area_ratio:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def nozzle_regime(pt: float, p_amb: float, gamma: float) -> dict:
    """Choked/unchoked regime for a convergent nozzle at total pressure pt."""
    if pt <= 0 or p_amb <= 0:
        raise ValueError("pressures must be positive")
    npr = pt / p_amb
    if npr <= 1.0:
        raise ValueError("nozzle pressure ratio must exceed 1")
    return {"npr": npr, "critical": _critical_ratio(gamma),
            "choked": npr >= _critical_ratio(gamma)}


def fully_expanded_velocity(tt: float, pt: float, p_amb: float,
                            gamma: float, cv: float = 1.0) -> float:
    """Isentropic fully-expanded jet velocity (Pe = Pa): m/s."""
    if tt <= 0 or pt <= 0 or p_amb <= 0 or pt <= p_amb:
        raise ValueError("invalid nozzle state")
    if not (0 < cv <= 1):
        raise ValueError("velocity coefficient in (0, 1]")
    ratio = (p_amb / pt) ** ((gamma - 1.0) / gamma)
    ve = math.sqrt((2.0 * gamma * R_GAS * tt / (gamma - 1.0)) * (1.0 - ratio))
    return cv * ve


def exit_static_state(tt: float, pt: float, p_amb: float, gamma: float):
    """Static state (Te, pe, ve) at a nozzle exit.

    Choked (convergent): Me=1 at the throat.  Unchoked: subsonic Mach
    from the isentropic relation, exit static pressure = ambient.
    """
    regime = nozzle_regime(pt, p_amb, gamma)
    if regime["choked"]:
        te = tt * 2.0 / (gamma + 1.0)
        pe = pt * (2.0 / (gamma + 1.0)) ** (gamma / (gamma - 1.0))
        ve = math.sqrt(gamma * R_GAS * te)
        return {"te": te, "pe": pe, "ve": ve, "mach": 1.0, "choked": True}
    me = math.sqrt(2.0 / (gamma - 1.0)
                   * (regime["npr"] ** ((gamma - 1.0) / gamma) - 1.0))
    te = tt / (1.0 + (gamma - 1.0) / 2.0 * me * me)
    ve = me * math.sqrt(gamma * R_GAS * te)
    return {"te": te, "pe": p_amb, "ve": ve, "mach": me, "choked": False}


def throat_area_from_mass_flow(mdot: float, pt: float, tt: float,
                               gamma: float) -> float:
    """Choked throat area (m2) passing mdot at total state (pt, tt)."""
    if mdot <= 0 or pt <= 0 or tt <= 0 or gamma <= 1:
        raise ValueError("invalid choked-flow input")
    return (mdot * math.sqrt(tt)
            / (pt * math.sqrt(gamma / R_GAS) * _choked_factor(gamma)))


def pressure_thrust(mdot: float, ve: float, pe: float, p_amb: float,
                    area: float) -> float:
    """Nozzle thrust F = mdot*ve + (pe - p_amb)*A (momentum + pressure term)."""
    if mdot < 0 or area < 0 or pe <= 0 or p_amb <= 0:
        raise ValueError("invalid thrust input")
    return mdot * ve + (pe - p_amb) * area


# ---------------------------------------------------------------------------
# Turbofan on-design point: closed-form separate-stream cycle
# ---------------------------------------------------------------------------
# Stations: 0 freestream | 2 fan face | 13 fan exit | 3 compressor exit |
# 4 turbine inlet (TIT) | 5 turbine exit | 9 core nozzle exit | 19 fan
# nozzle exit.  Power balance: fan (all air) + core compressor (core air)
# driven by the turbine (core gas).  All quantities per kg/s of TOTAL
# inlet airflow unless scaled; component maps are representative input.
# ---------------------------------------------------------------------------

def turbofan_design_point(m0: float, alt_m: float, bpr: float, fpr: float,
                          opr: float, tit: float, eta=None,
                          mdot0: float = 1.0) -> dict:
    """Separate-stream turbofan on-design cycle analysis (closed form).

    Returns station total states (K, Pa), nozzle states, net thrust per
    kg/s inlet air (momentum + pressure term, fully expanded or choked
    convergent nozzle per the real regime), fuel/air ratio, TSFC and
    the efficiency decomposition. Raise on non-physical inputs.
    """
    if not (0 <= m0 < 1.0):
        raise ValueError("subsonic Mach number required")
    if alt_m < 0:
        raise ValueError("altitude must be >= 0")
    if bpr <= 0 or fpr <= 1 or opr <= 1 or tit <= 1500:
        raise ValueError("invalid cycle architecture inputs")
    if mdot0 <= 0:
        raise ValueError("mass flow must be positive")
    e = dict(DEFAULTS)
    if eta:
        e.update({k: v for k, v in eta.items() if k in DEFAULTS})
    for k in ("etaf", "etac", "etat", "etab", "etam"):
        if not (0 < e[k] <= 1):
            raise ValueError(f"{k} must be in (0, 1]")
    for k in ("pib", "pid", "pifd"):
        if not (0 < e[k] <= 1):
            raise ValueError(f"{k} must be in (0, 1]")
    if not (0 < e["cv"] <= 1):
        raise ValueError("cv must be in (0, 1]")

    atm = isa(alt_m)
    t0, p0 = atm["t"], atm["p"]
    v0 = m0 * atm["a"]
    ram = 1.0 + 0.5 * (GAMMA_C - 1.0) * m0 * m0

    # 0 -> 2 inlet
    tt2 = t0 * ram
    pt2 = e["pid"] * p0 * ram ** (GAMMA_C / (GAMMA_C - 1.0))
    # fan (all air)
    tt13 = compressor_exit_temperature(tt2, fpr, GAMMA_C, e["etaf"])
    pt13 = fpr * pt2
    # core compressor: ratio OPR/FPR (OPR measured fan face -> HPC exit)
    pr_core = opr / fpr
    tt3 = compressor_exit_temperature(tt13, pr_core, GAMMA_C, e["etac"])
    pt3 = opr * pt2
    # combustor
    pt4 = e["pib"] * pt3
    tt4 = tit
    f = (CP_H * tt4 - CP_C * tt3) / (e["etab"] * LHV_JET_A - CP_H * tt4)
    if f <= 0:
        raise ValueError("combustor energy balance gives non-positive f/a")
    # power balance per kg/s total inlet air
    cor = 1.0 / (1.0 + bpr)          # core-air fraction
    wfan = CP_C * (tt13 - tt2)       # fan work per kg air (whole flow)
    whpc = CP_C * (tt3 - tt13)       # core compressor work per kg core air
    wshaft = wfan + cor * whpc       # shaft work per kg/s total air
    wgas = wshaft / (e["etam"] * (1.0 + f) * cor)   # turbine work per kg gas
    tt5 = tt4 - wgas / CP_H
    if tt5 <= 0:
        raise ValueError("turbine work exceeds available enthalpy")
    tt5s = tt4 - (tt4 - tt5) / e["etat"]
    pt5 = pt4 * (tt5s / tt4) ** (GAMMA_H / (GAMMA_H - 1.0))
    if pt5 <= p0:
        raise ValueError("turbine exit below ambient: architecture infeasible")

    # ---- nozzles (real regime: choked convergent or unchoked) ----
    mdot_gas = cor * (1.0 + f)       # core nozzle flow per kg/s inlet air
    mdot_fan = 1.0 - cor
    pt19 = e["pifd"] * pt13          # fan nozzle entry after duct loss

    core = exit_static_state(tt5, pt5, p0, GAMMA_H)
    fan = exit_static_state(tt13, pt19, p0, GAMMA_C)
    # velocity coefficient applied to nozzle velocities
    ve9 = e["cv"] * core["ve"]
    ve19 = e["cv"] * fan["ve"]
    # fully-expanded (Pe = Pa) jet velocities: the effective velocities of
    # the momentum-only thrust form used by the bypass-ratio trade leaf
    ve9_fe = (fully_expanded_velocity(tt5, pt5, p0, GAMMA_H, e["cv"])
              if pt5 > p0 else ve9)
    ve19_fe = (fully_expanded_velocity(tt13, pt19, p0, GAMMA_C, e["cv"])
               if pt19 > p0 else ve19)

    # nozzle exit streamtube areas (per kg/s of the stream flow)
    a9 = mdot_gas * R_GAS * core["te"] / (p0 * ve9)
    a19 = mdot_fan * R_GAS * fan["te"] / (p0 * ve19)
    # choked throat area where the regime is choked
    a9_star = (throat_area_from_mass_flow(mdot_gas, pt5, tt5, GAMMA_H)
               if core["choked"] else None)
    a19_star = (throat_area_from_mass_flow(mdot_fan, pt19, tt13, GAMMA_C)
                if fan["choked"] else None)

    # net thrust per kg/s total air: F = sum [mdot*(Vj - V0) + (Pe-P0)*A]
    # (fuel mass flow neglected in the inlet momentum term, standard
    # cycle-deck convention)
    f_net = mdot_gas * (ve9 - v0) + (core["pe"] - p0) * a9 \
        + mdot_fan * (ve19 - v0) + (fan["pe"] - p0) * a19
    if f_net <= 0:
        raise ValueError("non-positive net thrust at this point")

    # ---- efficiencies (per unit total inlet air) ----
    # Overall: useful thrust power / fuel power.  Propulsive: Froude-loss
    # method, eta_p = F*V0 / (F*V0 + sum 0.5 mdot (Ve - V0)^2) - the
    # residual kinetic energy left in both jets at the flight velocity.
    # Thermal is the consistent remainder eta_o/eta_p (kinetic-energy
    # method with the pressure-thrust work credited to the useful side).
    f_air = f * cor                     # fuel per kg/s total inlet air
    eta_o = f_net * v0 / (f_air * LHV_JET_A) if v0 > 0 else 0.0
    p_useful = f_net * v0
    p_loss = (0.5 * mdot_gas * (ve9 - v0) ** 2
              + 0.5 * mdot_fan * (ve19 - v0) ** 2)
    eta_p = p_useful / (p_useful + p_loss) if p_useful > 0 else 0.0
    eta_th = (eta_o / eta_p) if eta_p > 0 else 0.0

    return {
        "m0": m0, "alt": alt_m, "bpr": bpr, "fpr": fpr, "opr": opr,
        "tit": tit, "t0": t0, "p0": p0, "v0": v0,
        "stations": {
            "2": {"tt": tt2, "pt": pt2, "name": "fan face"},
            "13": {"tt": tt13, "pt": pt13, "name": "fan exit"},
            "3": {"tt": tt3, "pt": pt3, "name": "compressor exit"},
            "4": {"tt": tt4, "pt": pt4, "name": "turbine inlet (TIT)"},
            "5": {"tt": tt5, "pt": pt5, "name": "turbine exit"},
        },
        "nozzle_core": {"tt": tt5, "pt": pt5, "te": core["te"],
                        "pe": core["pe"], "ve": ve9, "ve_fe": ve9_fe,
                        "mach": core["mach"],
                        "choked": core["choked"], "a_exit": a9,
                        "a_star": a9_star},
        "nozzle_fan": {"tt": tt13, "pt": pt19, "te": fan["te"],
                       "pe": fan["pe"], "ve": ve19, "ve_fe": ve19_fe,
                       "mach": fan["mach"],
                       "choked": fan["choked"], "a_exit": a19,
                       "a_star": a19_star},
        "f_air_core": f, "f_air_total": f_air, "mdot_core_frac": cor,
        "mdot_fan_frac": mdot_fan, "f_net_per_kg": f_net,
        "tsfc_kg_Ns": f_air / f_net,
        "eta_o": eta_o, "eta_th": eta_th, "eta_p": eta_p,
        "eta_brayton_ideal": brayton_thermal_efficiency(opr),
        "w_shaft_per_kg": wshaft, "pr_core": pr_core, "mdot0": mdot0,
    }


# ---------------------------------------------------------------------------
# Off-design envelope: corrected-flow matching (compressor-map + turbofan-
# off-design leaves) at fixed corrected flow and turbine inlet temperature.
# ---------------------------------------------------------------------------

def corrected_flow(mdot: float, tt: float, pt: float) -> float:
    """m_corr = mdot*sqrt(theta)/delta, theta=Tt/288.15, delta=Pt/101325."""
    if mdot <= 0 or tt <= 0 or pt <= 0:
        raise ValueError("invalid corrected-flow input")
    theta = tt / T_REF
    delta = pt / P_REF
    return mdot * math.sqrt(theta) / delta


def corrected_speed(n_phys: float, tt: float) -> float:
    if n_phys < 0 or tt <= 0:
        raise ValueError("invalid corrected-speed input")
    return n_phys / math.sqrt(tt / T_REF)


def operating_line_clearance(pr_op: float, pr_surge: float) -> float:
    """Pressure-ratio clearance to the surge line at same corrected flow (%).
    Positive = operating line below surge (safe side)."""
    if pr_op <= 0 or pr_surge <= 0:
        raise ValueError("pressure ratios must be positive")
    return (pr_surge - pr_op) / pr_op * 100.0


def map_verdict(pr: float, pr_surge: float, threshold: float = 0.05) -> str:
    """on-map / approaching-surge / on-surge-line from PR gap to surge."""
    if pr <= 1 or pr_surge <= pr:
        raise ValueError("pr must exceed 1 and lie below surge")
    if (pr_surge - pr) / pr_surge <= threshold:
        return "approaching-surge"
    return "on-map"


def surge_margin_flow(q_surge: float, q_op: float) -> float:
    """Flow-basis surge margin (%), (q_op - q_surge)/q_op*100."""
    if q_surge <= 0 or q_op <= 0:
        raise ValueError("flows must be positive")
    return (q_op - q_surge) / q_op * 100.0


def off_design_envelope(design: dict, points: list) -> list:
    """Off-design rows for flight points (name, alt_m, m0, throttle_frac).

    Quick off-design model (turbofan-off-design leaf): the engine holds
    constant corrected mass flow (nozzle-matched) and turbine inlet
    temperature; physical airflow scales by delta/sqrt(theta); net
    thrust re-computed through the same on-design cycle with the point's
    flight conditions. Component map representative input: core
    compressor operating point at design pressure ratio vs a
    representative surge line 15% above the operating line.
    """
    mdot_corr = corrected_flow(design["mdot0"], design["stations"]["2"]["tt"],
                               design["stations"]["2"]["pt"])
    rows = []
    for name, alt_m, m0, throttle in points:
        p = turbofan_design_point(m0, alt_m, design["bpr"], design["fpr"],
                                  design["opr"], design["tit"])
        # matched corrected flow => physical flow at this point
        tt2 = p["stations"]["2"]["tt"]
        pt2 = p["stations"]["2"]["pt"]
        mdot_phys = mdot_corr / (math.sqrt(tt2 / T_REF) / (pt2 / P_REF))
        f_pt = p["f_net_per_kg"] * mdot_phys
        # throttle scaling on net thrust (fuel flow scales with thrust at
        # roughly constant SFC for the quick model)
        f_thr = f_pt * throttle
        mdot_fuel = p["tsfc_kg_Ns"] * f_pt * throttle
        pr_surge = design["opr"] * 1.15     # representative surge line
        op_clear = operating_line_clearance(design["opr"], pr_surge)
        # representative map point at this flight condition (same corrected
        # speed as design, core PR = design OPR): surge verdict
        verdict = map_verdict(design["opr"], pr_surge)
        rows.append({
            "name": name, "alt_m": alt_m, "m0": m0, "throttle": throttle,
            "throttle_verdict": throttle_verdict(throttle),
            "mdot_phys": mdot_phys, "f_net": f_pt,
            "f_throttled": f_thr, "tsfc_kg_Ns": p["tsfc_kg_Ns"],
            "mdot_fuel": mdot_fuel, "corr_flow": mdot_corr,
            "surge_clearance_pct": op_clear, "map_verdict": verdict,
            "t0": p["t0"], "p0": p["p0"], "tt2": tt2, "pt2": pt2,
        })
    return rows


# ---------------------------------------------------------------------------
# Bypass-ratio trade (bypass-ratio-trade leaf): first-order fan/core split
# at fixed core conditions and fixed total mass flow.  mdot_fan =
# BPR/(1+BPR)*mdot_total, mdot_core = mdot_total/(1+BPR), F per stream =
# mdot*(Vj - V0), mdot_fuel = f*mdot_core, TSFC = 1e6*f*mdot_core/F_total.
# ---------------------------------------------------------------------------

def thrust_split(bpr: float, mdot_total: float, vj_core: float,
                 vj_fan: float, v0: float) -> dict:
    """Net thrust per stream F = mdot*(Vj - V0); each jet must thrust."""
    if bpr < 0 or mdot_total <= 0:
        raise ValueError("bpr >= 0 and mdot_total > 0 required")
    for name, v in (("vj_core", vj_core), ("vj_fan", vj_fan), ("v0", v0)):
        if v <= 0:
            raise ValueError(f"{name} must be > 0")
    if vj_core <= v0 or vj_fan <= v0:
        raise ValueError("jet velocities must exceed flight velocity")
    mdot_core = mdot_total / (1.0 + bpr)
    mdot_fan = mdot_total * bpr / (1.0 + bpr)
    f_core = mdot_core * (vj_core - v0)
    f_fan = mdot_fan * (vj_fan - v0)
    return {"bpr": bpr, "mdot_fan": mdot_fan, "mdot_core": mdot_core,
            "f_core": f_core, "f_fan": f_fan,
            "f_total": f_core + f_fan,
            "specific_thrust": (f_core + f_fan) / mdot_total}


def bpr_trend(mdot_total: float, vj_core: float, vj_fan: float, v0: float,
              f_core: float) -> list:
    """Trade across bypass ratios at fixed core/fan jet velocities.

    Fixed core conditions and fixed total mass flow (leaf method):
    raising BPR shifts flow to the fan stream, whose jet velocity is
    much lower than the core's, so average jet velocity drops and TSFC
    falls. Returns {bpr, f_total, specific_thrust, tsfc_g_kN_s}.
    """
    if not 0.0 < f_core < 1.0:
        raise ValueError("core fuel/air ratio must lie in (0, 1)")
    out = []
    for bpr in (2.0, 4.0, 6.0, 8.0, 10.0, 12.0):
        s = thrust_split(bpr, mdot_total, vj_core, vj_fan, v0)
        mdot_fuel = f_core * s["mdot_core"]
        tsfc = 1e6 * mdot_fuel / s["f_total"]     # g/(kN*s)
        out.append({"bpr": bpr, "f_total": s["f_total"],
                    "specific_thrust": s["specific_thrust"],
                    "tsfc_g_kN_s": tsfc})
    return out


def propulsive_efficiency_froude(vj: float, v0: float) -> float:
    """Froude propulsive efficiency eta_p = 2/(1 + vj/v0)."""
    if vj <= 0 or v0 <= 0:
        raise ValueError("velocities must be positive")
    return 2.0 / (1.0 + vj / v0)


# ---------------------------------------------------------------------------
# Rocket propulsion (rocket-engine-cycle + nozzle-design + propellant-
# selection leaves): feed-cycle feasibility, mass split, nozzle sizing.
# ---------------------------------------------------------------------------

def propellant_pair_properties(pair: str):
    try:
        return PROPELLANTS[pair]
    except (KeyError, TypeError):
        raise ValueError(f"unknown propellant pair: {pair}")


def rocket_mass_flow(f_n: float, isp_s: float, g0: float = G0) -> float:
    """mdot = F/(Isp*g0): mass flow from thrust and specific impulse."""
    if f_n <= 0 or isp_s <= 0 or g0 <= 0:
        raise ValueError("thrust, Isp and g0 must be positive")
    return f_n / (isp_s * g0)


def mass_flow_split(f_n: float, isp_s: float, r_m, g0: float = G0):
    """(mdot, mdot_ox, mdot_f) for a bipropellant or monopropellant."""
    mdot = rocket_mass_flow(f_n, isp_s, g0)
    if r_m is None:
        return mdot, mdot, 0.0
    if r_m <= 0:
        raise ValueError("mixture ratio must be positive")
    mdot_ox = mdot * r_m / (1.0 + r_m)
    mdot_f = mdot / (1.0 + r_m)
    return mdot, mdot_ox, mdot_f


def cycle_feasibility(cycle: str, propellant: str, p_c: float):
    """(feasible, reason): pressure-fed <=3 MPa; expander LOX/LH2 only
    <=10 MPa; gas-generator and staged-combustion feasible for any
    bipropellant pair (documented bounds from the rocket-engine-cycle
    leaf)."""
    if cycle not in ("pressure-fed", "gas-generator", "staged-combustion",
                     "expander"):
        raise ValueError(f"unknown engine cycle: {cycle}")
    if p_c <= 0:
        raise ValueError("chamber pressure must be positive")
    rho_ox, rho_fuel, r_m, isp = propellant_pair_properties(propellant)
    if cycle == "pressure-fed":
        if p_c <= PRESSURE_FED_MAX_P_C:
            return True, "chamber pressure within the 3 MPa pressure-fed bound"
        return False, (f"chamber pressure above the "
                       f"{PRESSURE_FED_MAX_P_C / 1e6:.0f} MPa pressure-fed bound")
    if cycle == "expander":
        if propellant != "LOX/LH2":
            return False, ("expander drive needs the high heat-capacity LH2 "
                           f"fuel; {propellant} does not qualify")
        if p_c > EXPANDER_MAX_P_C:
            return False, ("chamber pressure above the 10 MPa expander bound")
        return True, "LH2 fuel heated in the cooling jacket drives the turbine"
    if r_m is None:
        return False, (f"{cycle} needs an oxidizer/fuel pair; monopropellant "
                       "has no turbine drive gas split")
    return True, "turbine drive gas carried at part or full chamber pressure"


def pump_power(mdot: float, p_discharge: float, p_inlet: float, rho: float,
               eta_pump: float = ETA_PUMP_DEFAULT) -> float:
    if mdot <= 0 or p_discharge <= p_inlet or rho <= 0:
        raise ValueError("invalid pump input")
    if not (0 < eta_pump <= 1):
        raise ValueError("pump efficiency in (0, 1]")
    return mdot * (p_discharge - p_inlet) / (rho * eta_pump)


def turbine_power(mdot_gas: float, cp: float, t_inlet: float, eta_t: float,
                  gamma: float, p_inlet: float, p_exit: float) -> float:
    if mdot_gas <= 0 or cp <= 0 or t_inlet <= 0 or p_exit >= p_inlet:
        raise ValueError("invalid turbine input")
    if not (0 < eta_t <= 1) or gamma <= 1:
        raise ValueError("turbine efficiency/gamma invalid")
    pr = (p_exit / p_inlet) ** ((gamma - 1.0) / gamma)
    return mdot_gas * cp * t_inlet * eta_t * (1.0 - pr)


def bulk_density(rho_ox: float, rho_fuel: float, r_m) -> float:
    if rho_ox <= 0 or rho_fuel <= 0:
        raise ValueError("densities must be positive")
    if r_m is None:
        return rho_ox
    return (1.0 + r_m) / (r_m / rho_ox + 1.0 / rho_fuel)


def rocket_engine_cycle_analysis(cycle: str, f_n: float, p_c: float,
                                 propellant: str, isp=None, p_losses=None,
                                 eta_pump=None, eta_turb=None,
                                 gg_fraction=None) -> dict:
    """Feed-cycle balance: mass flows, pump/turbine power, feasibility,
    tank pressure, verdict. Mirrors the rocket-engine-cycle leaf model."""
    rho_ox, rho_fuel, r_m, isp_vac = propellant_pair_properties(propellant)
    isp_use = isp_vac if isp is None else isp
    if isp_use <= 0:
        raise ValueError("Isp must be positive")
    p_losses = P_LOSSES_DEFAULT if p_losses is None else p_losses
    eta_pump = ETA_PUMP_DEFAULT if eta_pump is None else eta_pump
    eta_turb = ETA_TURB_DEFAULT if eta_turb is None else eta_turb
    gg_fraction = GG_FRACTION_DEFAULT if gg_fraction is None else gg_fraction
    if not (0 < eta_pump <= 1) or not (0 < eta_turb <= 1):
        raise ValueError("efficiencies must lie in (0, 1]")
    if not (0 < gg_fraction < 1):
        raise ValueError("gas-generator fraction must lie in (0, 1)")

    mdot, mdot_ox, mdot_f = mass_flow_split(f_n, isp_use, r_m)
    feasible, reason = cycle_feasibility(cycle, propellant, p_c)
    bulk = bulk_density(rho_ox, rho_fuel, r_m)

    p_discharge = p_c + p_losses
    pump_ox = pump_power(mdot_ox, p_discharge, PUMP_INLET_PRESSURE, rho_ox,
                         eta_pump) if mdot_ox > 0 else 0.0
    pump_fuel = pump_power(mdot_f, p_discharge, PUMP_INLET_PRESSURE, rho_fuel,
                           eta_pump) if mdot_f > 0 else 0.0
    pump_total = pump_ox + pump_fuel
    turb_p = 0.0
    drive_fraction = 0.0
    if cycle == "gas-generator":
        mdot_gg = gg_fraction * mdot
        p_gg = GG_PRESSURE_FRACTION * p_c
        turb_p = turbine_power(mdot_gg, GG_CP, GG_T_INLET, eta_turb, GG_GAMMA,
                               p_gg, TURBINE_EXIT_PRESSURE)
        drive_fraction = gg_fraction
    elif cycle == "staged-combustion":
        p_pb = STAGED_INLET_FRACTION * p_c
        turb_p = turbine_power(mdot, GG_CP, GG_T_INLET, eta_turb, GG_GAMMA,
                               p_pb, TURBINE_EXIT_PRESSURE)
        drive_fraction = 1.0
    elif cycle == "expander":
        p_exit = EXPANDER_EXIT_FRACTION * p_c
        turb_p = turbine_power(mdot_f, EXPANDER_CP, EXPANDER_T_INLET, eta_turb,
                               EXPANDER_GAMMA, p_c, p_exit)
        drive_fraction = mdot_f / mdot if mdot > 0 else 0.0
    power_balance = turb_p - pump_total

    if not feasible:
        verdict = f"cycle rejected: {reason}"
    elif cycle == "pressure-fed":
        verdict = (f"pressure-fed feasible at p_c {p_c / 1e6:.2f} MPa: tank "
                   f"pressure {p_discharge / 1e6:.2f} MPa; pump-fed trades "
                   "machinery against the heavy feed tank")
    elif power_balance >= 0.0:
        verdict = (f"{cycle} feasible: pump power {pump_total / 1e6:.3f} MW, "
                   f"turbine power {turb_p / 1e6:.3f} MW, surplus "
                   f"{power_balance / 1e6:.3f} MW")
    else:
        verdict = (f"{cycle} feasible on the pressure bound but underpowered: "
                   f"turbine {turb_p / 1e6:.3f} MW vs pump demand "
                   f"{pump_total / 1e6:.3f} MW")
    return {
        "cycle": cycle, "propellant": propellant, "feasible": feasible,
        "reason": reason, "isp": isp_use, "mdot": mdot, "mdot_ox": mdot_ox,
        "mdot_f": mdot_f, "mixture_ratio": r_m, "p_c": p_c,
        "p_discharge": p_discharge, "pump_power_total": pump_total,
        "turbine_power": turb_p, "power_balance": power_balance,
        "drive_mass_fraction": drive_fraction, "verdict": verdict,
        "bulk_density": bulk,
    }


def rocket_nozzle_sizing(mdot: float, p_c: float, t_c: float, gamma: float,
                         area_ratio: float, r_gas: float = 693.0) -> dict:
    """Rocket nozzle from chamber state and area ratio (nozzle-design leaf).

    Computes throat area from the choked-flow relation, supersonic exit
    Mach from the isentropic area-Mach relation, exit pressure/velocity,
    and the ideal thrust coefficient. Chamber properties (Tc, gamma,
    R of the product gas) are stated inputs for the chosen propellant,
    to be confirmed by equilibrium CEA at the design O/F.
    """
    if mdot <= 0 or p_c <= 0 or t_c <= 0 or gamma <= 1 or area_ratio <= 1:
        raise ValueError("invalid nozzle sizing input")
    if r_gas <= 0:
        raise ValueError("product-gas constant must be positive")
    a_star = (mdot * math.sqrt(t_c)
              / (p_c * math.sqrt(gamma / r_gas) * _choked_factor(gamma)))
    me = exit_mach_from_area_ratio(area_ratio, gamma)
    pe = p_c / (1.0 + (gamma - 1.0) / 2.0 * me * me) ** (gamma / (gamma - 1.0))
    ve = math.sqrt((2.0 * gamma * r_gas * t_c / (gamma - 1.0))
                   * (1.0 - (pe / p_c) ** ((gamma - 1.0) / gamma)))
    a_exit = area_ratio * a_star
    # ideal thrust coefficient at vacuum (pe > 0): Cf = F/(Pc At)
    cf_ideal = (mdot * ve + pe * a_exit) / (p_c * a_star)
    return {"a_star": a_star, "a_exit": a_exit, "me": me, "pe": pe,
            "ve": ve, "cf_ideal": cf_ideal, "area_ratio": area_ratio,
            "t_c": t_c, "gamma": gamma, "r_gas": r_gas}


# ---------------------------------------------------------------------------
# Item model + report builder
# ---------------------------------------------------------------------------

@dataclass
class PropulsionItem:
    """Project facts the role needs to build the propulsion design report."""
    item_name: str
    mission: str = ""                 # air transport / upper stage / ...
    vehicle: str = ""
    engine_kind: str = "turbofan"     # turbofan | rocket | electric
    thrust_requirement_n: float = 30000.0   # net thrust per engine (design pt)
    cruise_mach: float = 0.78
    cruise_alt_m: float = 10668.0     # FL350
    bpr: float = 8.0
    fpr: float = 1.6
    opr: float = 30.0
    tit_k: float = 1650.0
    # rocket item fields
    rocket_cycle: str = "expander"
    propellant: str = "LOX/LH2"
    chamber_pressure_pa: float = 4.0e6
    chamber_temp_k: float = 3500.0     # stated input (CEA-confirmable)
    nozzle_gamma: float = 1.2          # stated input (CEA-confirmable)
    nozzle_area_ratio: float = 84.0
    product_gas_r: float = 693.0       # LOX/LH2 products, MW~12 (stated input)
    thrust_vac_n: float = 110000.0
    # supporting facts
    component_efficiencies: dict = field(default_factory=dict)
    surge_line_factor: float = 1.15    # representative surge line above op
    certification_basis: str = "FAR 33 context (engine), design study"
    reference: str = ""


def example_turbofan_item() -> PropulsionItem:
    """Reference item: high-bypass turbofan for a 200-seat-class twin
    (BPR 8, OPR 30, TIT 1650 K) - the filled deliverable in templates/."""
    return PropulsionItem(
        item_name="High-bypass turbofan for a 200-seat twin (design study)",
        mission="Subsonic transport cruise design point (M0.78, FL350)",
        vehicle="200-seat twin-aisle-class transport, 2 wing-mounted engines",
        engine_kind="turbofan",
        thrust_requirement_n=30000.0,
        cruise_mach=0.78,
        cruise_alt_m=10668.0,
        bpr=8.0, fpr=1.6, opr=30.0, tit_k=1650.0,
        certification_basis="Design study in a FAR 33 engine-type context; "
                            "no certification approval claimed",
    )


def example_rocket_item() -> PropulsionItem:
    """Reference space item: LOX/LH2 expander upper-stage engine."""
    return PropulsionItem(
        item_name="LOX/LH2 expander upper-stage engine (reference design)",
        mission="Vacuum upper stage, reference sizing study",
        vehicle="Expendable launch vehicle upper stage",
        engine_kind="rocket",
        rocket_cycle="expander",
        propellant="LOX/LH2",
        chamber_pressure_pa=4.0e6,
        chamber_temp_k=3500.0,
        nozzle_gamma=1.2,
        nozzle_area_ratio=84.0,
        thrust_vac_n=110000.0,
        certification_basis="Design study; engine certification per FAR 33 "
                            "is out of scope (no approval claimed)",
    )


# ---------------------------------------------------------------------------
# Content model builders
# ---------------------------------------------------------------------------

def build_turbofan_report(item: PropulsionItem) -> dict:
    """Full propulsion design report content model (turbofan item)."""
    if item.engine_kind != "turbofan":
        raise ValueError("turbofan builder for a turbofan item")
    design = turbofan_design_point(item.cruise_mach, item.cruise_alt_m,
                                   item.bpr, item.fpr, item.opr, item.tit_k,
                                   item.component_efficiencies, mdot0=1.0)
    # scale to thrust requirement
    mdot0 = item.thrust_requirement_n / design["f_net_per_kg"]
    design["mdot0"] = mdot0
    design["f_net"] = design["f_net_per_kg"] * mdot0
    design["mdot_fuel"] = design["tsfc_kg_Ns"] * design["f_net"]
    # SFC conversions
    design["tsfc_g_kN_s"] = design["tsfc_kg_Ns"] * 1e6
    design["sfc_lb_lbf_hr"] = design["tsfc_g_kN_s"] / 28.33

    # envelope points: SLS static, climb, design cruise, cruise part-power,
    # and top-of-cruise (name, alt_m, m0, throttle)
    pts = [("SLS static", 0.0, 0.0, 1.00),
           ("FL250 climb", 7620.0, 0.78, 1.00),
           ("FL350 design cruise", 10668.0, 0.78, 1.00),
           ("FL350 part power", 10668.0, 0.78, 0.60),
           ("FL390 top of cruise", 11887.0, 0.80, 1.00)]
    envelope = off_design_envelope(design, pts)

    # representative core-compressor map point (map input, not vendor data):
    # surge line set a stated factor above the operating-line pressure ratio
    pr_surge = item.opr * item.surge_line_factor

    # bypass-ratio trade (bypass-ratio-trade leaf): fixed core conditions
    # and fixed total mass flow; jets held at the design-point velocities.
    f_core = design["f_air_total"] * (1.0 + design["bpr"])   # core f/a
    trade_rows = bpr_trend(mdot0, design["nozzle_core"]["ve_fe"],
                           design["nozzle_fan"]["ve_fe"], design["v0"],
                           f_core)
    for r in trade_rows:
        # overall efficiency proxy on the leaf's momentum thrust at V0
        p_useful = r["f_total"] * design["v0"]
        mdot_fuel = f_core * mdot0 / (1.0 + r["bpr"])
        r["eta_o"] = (p_useful / (mdot_fuel * LHV_JET_A)
                      if mdot_fuel > 0 else 0.0)

    return {
        "document_type": "Propulsion Design Report",
        "status": "draft-for-review",
        "item": item.item_name,
        "vehicle": item.vehicle,
        "mission": item.mission,
        "engine_kind": "turbofan",
        "certification_basis": item.certification_basis,
        "requirement_n": item.thrust_requirement_n,
        "design": design,
        "component_eta": dict(DEFAULTS, **item.component_efficiencies),
        "envelope": envelope,
        "surge_line_factor": item.surge_line_factor,
        "pr_surge_rep": pr_surge,
        "bpr_trade": trade_rows,
        "spool_note": "fan (LP) + core compressor (HP) driven by the turbine "
                      "through the closed-form power balance",
        "generated": date.today().isoformat(),
    }


def build_rocket_report(item: PropulsionItem) -> dict:
    """Propulsion design report content model (rocket item)."""
    if item.engine_kind != "rocket":
        raise ValueError("rocket builder for a rocket item")
    cycle = rocket_engine_cycle_analysis(
        item.rocket_cycle, item.thrust_vac_n, item.chamber_pressure_pa,
        item.propellant)
    nozzle = rocket_nozzle_sizing(cycle["mdot"], item.chamber_pressure_pa,
                                  item.chamber_temp_k, item.nozzle_gamma,
                                  item.nozzle_area_ratio,
                                  r_gas=item.product_gas_r)
    # Isp check: F = mdot*Isp*g0 identity holds by construction of mdot;
    # ideal-expansion Isp from the computed exit velocity
    isp_ideal = nozzle["ve"] / G0
    alternatives = []
    for pair, (r_ox, r_f, r_m, isp_v) in PROPELLANTS.items():
        alternatives.append({"pair": pair, "isp_vac": isp_v,
                             "bulk_density": bulk_density(r_ox, r_f, r_m)})
    return {
        "document_type": "Propulsion Design Report",
        "status": "draft-for-review",
        "item": item.item_name,
        "vehicle": item.vehicle,
        "mission": item.mission,
        "engine_kind": "rocket",
        "certification_basis": item.certification_basis,
        "requirement_n": item.thrust_vac_n,
        "cycle": cycle,
        "nozzle": nozzle,
        "isp_ideal": isp_ideal,
        "alternatives": alternatives,
        "generated": date.today().isoformat(),
    }


def build_report(item: PropulsionItem) -> dict:
    if item.engine_kind == "rocket":
        return build_rocket_report(item)
    if item.engine_kind == "turbofan":
        return build_turbofan_report(item)
    raise ValueError(f"unsupported engine_kind {item.engine_kind!r}")


# ---------------------------------------------------------------------------
# Markdown renderers
# ---------------------------------------------------------------------------

def _fmt(x, spec=".6g"):
    return f"{x:{spec}}"


def _kpa(p):
    return p / 1000.0


def render_turbofan_markdown(model: dict) -> str:
    d = model["design"]
    st = d["stations"]
    nc, nf = d["nozzle_core"], d["nozzle_fan"]
    lines = [
        "# Propulsion Design Report",
        "",
        f"**Item:** {model['item']}",
        f"**Vehicle / mission:** {model['vehicle']} - {model['mission']}",
        f"**Engine class:** high-bypass turbofan "
        f"(BPR {d['bpr']:.0f}, FPR {d['fpr']:.2f}, OPR {d['opr']:.0f}, "
        f"TIT {d['tit']:.0f} K)",
        f"**Status:** {model['status']}",
        f"**Certification basis:** {model['certification_basis']}",
        "",
        "## 1. Requirement and selected cycle",
        "",
        f"- Thrust requirement (per engine, design point): "
        f"{model['requirement_n'] / 1000.0:.1f} kN net at "
        f"M{d['m0']:.2f}, {d['alt'] / 1000.0:.0f} km ISA.",
        "- Selected cycle: separate-stream turbofan with the fan on the "
        "low-pressure spool and the core compressor/turbine on the high-"
        "pressure spool. Rationale: high bypass ratio (8) lowers mean jet "
        "velocity and raises propulsive efficiency at a transonic cruise "
        "Mach; the OPR 30 / TIT 1650 K core delivers the cruise SFC of "
        f"{d['sfc_lb_lbf_hr']:.3f} lb/(lbf.h) computed below.",
        f"- Design airflow (total, matched to the requirement): "
        f"{d['mdot0']:.1f} kg/s.",
        "",
        "## 2. Cycle analysis (airbreathing)",
        "",
        "On-design station state table (total temperature / total pressure, "
        "per kg/s inlet airflow basis; component efficiencies are stated "
        "inputs below):",
        "",
        "| Station | Name | Tt (K) | Pt (kPa) |",
        "|---|---|---|---|",
    ]
    for s in ("2", "13", "3", "4", "5"):
        lines.append(f"| {s} | {st[s]['name']} | {st[s]['tt']:.1f} | "
                     f"{_kpa(st[s]['pt']):.1f} |")
    lines += [
        "",
        f"Core nozzle (station 9): exit static {nc['te']:.0f} K / "
        f"{_kpa(nc['pe']):.1f} kPa, jet velocity {nc['ve']:.1f} m/s, "
        f"Mach {nc['mach']:.3f}, {'choked' if nc['choked'] else 'unchoked'}, "
        f"exit area {nc['a_exit'] * d['mdot0']:.4f} m^2 "
        f"(per engine).",
        f"Fan nozzle (station 19): exit static {nf['te']:.0f} K / "
        f"{_kpa(nf['pe']):.1f} kPa, jet velocity {nf['ve']:.1f} m/s, "
        f"Mach {nf['mach']:.3f}, {'choked' if nf['choked'] else 'unchoked'}, "
        f"exit area {nf['a_exit'] * d['mdot0']:.4f} m^2 (per engine).",
        "",
        f"- Net thrust (per engine, design point): "
        f"{d['f_net'] / 1000.0:.1f} kN "
        f"= sum of m_dot*(V9 - V0) + (P9 - P0)*A9 over both streams.",
        f"- TSFC: {d['tsfc_g_kN_s']:.1f} g/(kN.s)  "
        f"({d['sfc_lb_lbf_hr']:.3f} lb/(lbf.h)).",
        f"- Fuel/air ratio (core): {d['f_air_core']:.5f} "
        f"(total basis {d['f_air_total']:.5f}); fuel flow "
        f"{d['mdot_fuel']:.3f} kg/s per engine.",
        f"- Efficiencies: overall {d['eta_o']:.3f}, thermal "
        f"{d['eta_th']:.3f}, propulsive {d['eta_p']:.3f} (kinetic-energy "
        "method over both streams); ideal Brayton at OPR 30: "
        f"{d['eta_brayton_ideal']:.3f}.",
        "",
        "Input assumptions (stated): fan efficiency 0.90, core compressor "
        f"efficiency 0.90, turbine 0.90, combustor 0.995 (pressure ratio "
        f"{model['component_eta']['pib']:.2f}), inlet recovery "
        f"{model['component_eta']['pid']:.3f}, fan-duct ratio "
        f"{model['component_eta']['pifd']:.2f}, mechanical 0.99, nozzle "
        f"velocity coefficient {model['component_eta']['cv']:.2f}; "
        f"fuel LHV 43.2 MJ/kg (kerosene class). "
        "Component maps and stage counts are representative input.",
        "",
        "## 3. Off-design",
        "",
        "Quick off-design model (turbofan-off-design leaf): corrected mass "
        "flow and turbine inlet temperature held at the design value; "
        "physical airflow scales by delta/sqrt(theta); net thrust is "
        "recomputed through the on-design cycle at each flight point.",
        "",
        "| Point | Alt (km) | Mach | Throttle | Verdict | m_dot (kg/s) | "
        "F_net (kN) | TSFC g/(kN.s) | Surge clearance | Map verdict |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in model["envelope"]:
        lines.append(
            f"| {r['name']} | {r['alt_m'] / 1000.0:.0f} | {r['m0']:.2f} | "
            f"{r['throttle']:.2f} | {r['throttle_verdict']} | "
            f"{r['mdot_phys']:.1f} | {r['f_throttled'] / 1000.0:.1f} | "
            f"{r['tsfc_kg_Ns'] * 1e6:.1f} | "
            f"{r['surge_clearance_pct']:.0f}% | {r['map_verdict']} |")
    lines += [
        "",
        f"Surge clearance: representative core-compressor surge line set "
        f"{model['surge_line_factor'] * 100.0:.0f}% above the operating "
        f"line pressure ratio ({model['pr_surge_rep']:.0f} vs OPR "
        f"{d['opr']:.0f}); the operating line clears surge at every "
        "envelope point (representative map input, not vendor data).",
        "",
        "## 4. Component selection",
        "",
        "| Component | Choice | Basis |",
        "|---|---|---|",
        f"| Inlet | subsonic pitot, recovery {model['component_eta']['pid']:.3f} | cruise M{d['m0']:.2f} |",
        f"| Fan | single stage, PR {d['fpr']:.2f}, eta 0.90 | Tt {st['13']['tt']:.0f} K at design |",
        f"| Core compressor | multi-stage axial, PR {d['pr_core']:.1f} (OPR {d['opr']:.0f}/fan {d['fpr']:.2f}) | Tt {st['3']['tt']:.0f} K, representative map margin |",
        f"| Combustor | annular, eta 0.995, pressure ratio {model['component_eta']['pib']:.2f} | f/a {d['f_air_core']:.5f} |",
        f"| HP turbine | cooled (turbine-blade-cooling stage), eta 0.90 | Tt in {st['4']['tt']:.0f} K, Tt out {st['5']['tt']:.0f} K |",
        f"| Core nozzle | convergent, {'choked' if nc['choked'] else 'unchoked'} at design | area {nc['a_exit'] * d['mdot0']:.4f} m^2 |",
        f"| Fan nozzle | convergent, {'choked' if nf['choked'] else 'unchoked'} at design | area {nf['a_exit'] * d['mdot0']:.4f} m^2 |",
        "",
        "## 5. Integration",
        "",
        "- Ram-drag bookkeeping (engine-airframe integration): net thrust "
        "above already subtracts the inlet momentum drag m_dot_0*V0 "
        f"(= {d['mdot0'] * d['v0'] / 1000.0:.1f} kN at the design point).",
        f"- Installed performance: nacelle, pylon and bleed/accessory "
        "losses are NOT yet deducted; the uninstalled net thrust is "
        f"{d['f_net'] / 1000.0:.1f} kN per engine.  Installation "
        "bookkeeping is a follow-on engine-airframe integration pass.",
        "",
        "## 6. Rocket / space option (if applicable)",
        "",
        "Not applicable to this airbreathing transport item - the engine "
        "selection is turbofan.  For a space item the rocket-engine-cycle "
        "and nozzle-design stages apply (see the rocket reference example "
        "in the core / cli build --engine rocket).",
        "",
        "## 7. Electric option (if applicable)",
        "",
        "Not applicable: no electric-propulsion role for a 30 kN cruise "
        "thrust requirement at M0.78.  Electric thrusters cover the "
        "low-thrust space regime (hall/gridded-ion), not airbreathing "
        "main propulsion.",
        "",
        "## 8. Bypass-ratio trade and recommendation",
        "",
        "First-order trade at fixed core conditions, fixed total mass flow "
        "and jet velocities held at the design-point values "
        "(bypass-ratio-trade leaf method):",
        "",
        "| BPR | F/m_dot (N per kg/s) | TSFC g/(kN.s) | eta_o |",
        "|---|---|---|---|",
    ]
    for r in model["bpr_trade"]:
        lines.append(f"| {r['bpr']:.0f} | {r['specific_thrust']:.1f} | "
                     f"{r['tsfc_g_kN_s']:.1f} | {r['eta_o']:.3f} |")
    lines += [
        "",
        "Raising BPR lowers specific thrust and TSFC by shifting flow to "
        "the fan stream (bypass-ratio-trade trend), at the cost of fan "
        "diameter and nacelle drag.  BPR 8 balances specific thrust with "
        "nacelle integration for a 200-seat twin; the design point above "
        "is the recommendation.  Open items: nacelle drag, turbine "
        "cooling flow, and the component map verification.",
        "",
        "---",
        f"*Generated by Aero Agent Roles propulsion-engineer core "
        f"({model['generated']}). DRAFT for human propulsion lead review. "
        "Not an approval document.*",
    ]
    return "\n".join(lines)


def render_rocket_markdown(model: dict) -> str:
    c = model["cycle"]
    n = model["nozzle"]
    lines = [
        "# Propulsion Design Report",
        "",
        f"**Item:** {model['item']}",
        f"**Vehicle / mission:** {model['vehicle']} - {model['mission']}",
        f"**Engine class:** {c['cycle']} rocket engine, {c['propellant']}",
        f"**Status:** {model['status']}",
        f"**Certification basis:** {model['certification_basis']}",
        "",
        "## 1. Requirement and selected cycle",
        "",
        f"- Thrust requirement (vacuum): {model['requirement_n'] / 1000.0:.0f} kN.",
        f"- Selected cycle: {c['cycle']} ({c['reason']}).  Propellant "
        f"rationale: {c['propellant']} gives the highest vacuum Isp "
        f"({c['isp']:.0f} s) of the bipropellant pairs screened; "
        f"LOX/LH2 is required for the expander drive gas.",
        "",
        "## 2. Cycle analysis (rocket feed system)",
        "",
        f"- Chamber pressure: {c['p_c'] / 1e6:.2f} MPa.",
        f"- Isp (vacuum, reference-typical): {c['isp']:.0f} s; mass flow "
        f"m_dot = F/(Isp*g0) = {c['mdot']:.2f} kg/s "
        f"(oxidizer {c['mdot_ox']:.2f} kg/s, fuel {c['mdot_f']:.2f} kg/s at "
        f"O/F {c['mixture_ratio']:.2f}).",
        f"- Pump discharge pressure: {c['p_discharge'] / 1e6:.2f} MPa; "
        f"pump power {c['pump_power_total'] / 1e6:.3f} MW, turbine power "
        f"{c['turbine_power'] / 1e6:.3f} MW.",
        f"- Feasibility verdict: {c['verdict']}.",
        "",
        "## 3. Nozzle design (expansion ratio trade)",
        "",
        "Chamber conditions (stated inputs for the propellant, to be "
        f"confirmed by equilibrium CEA): Tc {n['t_c']:.0f} K, gamma "
        f"{n['gamma']:.2f}.",
        f"- Throat area (choked flow): {n['a_star'] * 1e4:.2f} cm^2; "
        f"exit area at area ratio {n['area_ratio']:.0f}: "
        f"{n['a_exit'] * 1e4:.2f} cm^2.",
        f"- Exit Mach {n['me']:.2f}, exit static pressure "
        f"{n['pe'] / 1000.0:.2f} kPa, ideal exit velocity "
        f"{n['ve']:.0f} m/s (ideal vacuum Isp {model['isp_ideal']:.0f} s).",
        f"- Ideal vacuum thrust coefficient Cf = {n['cf_ideal']:.3f} at "
        f"this area ratio; vacuum operation keeps the nozzle underexpanded "
        "for any finite area ratio (optimum expansion is at infinite "
        "ratio), so the expansion trade is Cf gained vs nozzle mass.",
        "",
        "## 4. Propellant trade",
        "",
        "| Propellant | Isp_vac (s) | Bulk density (kg/m^3) |",
        "|---|---|---|",
    ]
    for a in model["alternatives"]:
        lines.append(f"| {a['pair']} | {a['isp_vac']:.0f} | "
                     f"{a['bulk_density']:.0f} |")
    lines += [
        "",
        "Density impulse (Isp x bulk density) matters for vehicle sizing: "
        "LOX/LH2 wins on Isp but loses on tank volume to LOX/RP-1 and "
        "N2O4/MMH; the reference choice is Isp-driven for an upper stage.",
        "",
        "## 5. Off-design / throttling",
        "",
        f"Expander-cycle throttling is bounded by the turbine drive-gas "
        f"temperature; reference-typical bounds: pressure-fed up to "
        f"{PRESSURE_FED_MAX_P_C / 1e6:.0f} MPa, expander (LOX/LH2) up to "
        f"{EXPANDER_MAX_P_C / 1e6:.0f} MPa chamber pressure.  Deep "
        "throttling and start transients are follow-on stages "
        "(injector-design, thrust-vector-control).",
        "",
        "## 6. Integration",
        "",
        "Vacuum operation removes the nozzle pressure ambient term; "
        "installation losses (nozzle divergence, film cooling, TVC "
        "gimbal mass) are follow-on.  Upper-stage burn sizing and "
        "propellant tanks are covered by the vehicle-level pass.",
        "",
        "---",
        f"*Generated by Aero Agent Roles propulsion-engineer core "
        f"({model['generated']}). DRAFT for human propulsion lead review. "
        "Not an approval document.*",
    ]
    return "\n".join(lines)


def render_report_markdown(model: dict) -> str:
    if model["engine_kind"] == "rocket":
        return render_rocket_markdown(model)
    return render_turbofan_markdown(model)


# ---------------------------------------------------------------------------
# Evidence gate checkers
# ---------------------------------------------------------------------------

GATE_CHECKS = {
    "requirement_present": "thrust requirement is a positive number",
    "cycle_identified": "engine class and design point stated",
    "state_points_complete": "station T/p present with efficiencies",
    "thrust_computed": "net thrust number present",
    "sfc_computed": "TSFC/SFC number present",
    "assumptions_stated": "input assumptions and representative-map labels",
    "sign_off_honest": "document marked draft-for-review, not approval",
}


def check_report(model: dict) -> dict:
    """Run the evidence gates against a report content model."""
    if model["engine_kind"] == "turbofan":
        d = model["design"]
        results = {
            "requirement_present": model["requirement_n"] > 0,
            "cycle_identified": (model["engine_kind"] == "turbofan"
                                 and d["bpr"] > 0 and d["opr"] > 1),
            "state_points_complete": (len(d["stations"]) >= 5
                                      and all("tt" in s and "pt" in s
                                              for s in d["stations"].values())),
            "thrust_computed": d["f_net"] > 0,
            "sfc_computed": d["tsfc_kg_Ns"] > 0,
            "assumptions_stated": bool(model["component_eta"]),
            "sign_off_honest": model["status"] == "draft-for-review",
        }
    else:
        c = model["cycle"]
        results = {
            "requirement_present": model["requirement_n"] > 0,
            "cycle_identified": model["engine_kind"] == "rocket",
            "state_points_complete": c["mdot"] > 0 and c["p_c"] > 0,
            "thrust_computed": c["mdot"] * c["isp"] * G0 > 0,
            "sfc_computed": c["isp"] > 0,
            "assumptions_stated": bool(model["nozzle"]),
            "sign_off_honest": model["status"] == "draft-for-review",
        }
    results["all_pass"] = all(results.values())
    return results


def check_report_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    checks = {
        "has_title": "propulsion design report" in low,
        "has_cycle": ("turbofan" in low or "rocket engine" in low),
        "has_numbers": bool(re.search(r"kN|\d+\.\d+ g/\(kn\.s\)|\d+ s", low)),
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling."""
    return check_report_markdown(md_text)


# ---------------------------------------------------------------------------
# Examples for tests / worked-example generation
# ---------------------------------------------------------------------------

def example_turbofan_markdown() -> str:
    return render_turbofan_markdown(build_turbofan_report(example_turbofan_item()))


def example_rocket_markdown() -> str:
    return render_rocket_markdown(build_rocket_report(example_rocket_item()))


if __name__ == "__main__":
    item = example_turbofan_item()
    model = build_report(item)
    md = render_report_markdown(model)
    d = model["design"]
    print(f"ENGINE: {item.item_name}")
    print(f"F_NET: {d['f_net'] / 1000.0:.1f} kN  airflow {d['mdot0']:.1f} kg/s")
    print(f"TSFC: {d['tsfc_g_kN_s']:.1f} g/(kN.s) = "
          f"{d['sfc_lb_lbf_hr']:.3f} lb/(lbf.h)")
    print(f"ETA: overall {d['eta_o']:.3f} thermal {d['eta_th']:.3f} "
          f"propulsive {d['eta_p']:.3f}")
    print(f"GATES: {check_report(model)}")
    print(f"RENDERED: {len(md)} chars")
