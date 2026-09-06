#!/usr/bin/env python3
"""rocket_propulsion_core.py - Rocket Propulsion Engineer executable core.

This is the role's ENGINE: given a launch-vehicle propulsion program's
project facts (payload, target orbit delta-v, propellant pairs, engine
cycles, chamber pressures, nozzle area ratio) it computes the staging
and sizing budget (rocket equation, stage mass ratios, payload
fractions, structural indices), the powered-ascent gravity-loss
accounting, the engine feed-cycle balance, the thrust-chamber design
(c-star, throat, contraction, chamber volume), the nozzle expansion
(exit Mach, exit pressure, ideal thrust, expansion and
flow-separation verdicts), the regenerative-cooling thermal balance at
the throat, the injector and thrust-vector-control sizing, the
cold-gas RCS sizing, and the alternate solid and hybrid motor
ballistics for screening. It BUILDS the Rocket Propulsion System
Design Report and gate-checks deliverables. Standalone: no external
repo needed.

Every formula below is the REAL domain rule encoded in the bound Aero
Agent Skills leaves under propulsion/rocket/ (nozzle-design,
rocket-sizing, rocket-staging, rocket-engine-cycle,
combustion-chamber-design, solid-rocket-motor, thrust-chamber-cooling,
cold-gas-thruster, hybrid-rocket-motor, injector-design,
propellant-selection, rocket-gravity-loss,
rocket-nozzle-flow-separation, thrust-vector-control). Those leaves
encode standard propulsion methodology (ideal rocket equation,
isentropic area-Mach relation, Vieille burn-rate law,
Bartz/Dittus-Boelter heat transfer, pump/turbine power balance).
Representative inputs (burn-rate coefficients, coolant channel sizes)
are stated as reference-typical values in the report; no proprietary
text is reproduced.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date


def _today() -> str:
    import os
    return os.environ.get("ROLE_GEN_DATE", date.today().isoformat())


# ---------------------------------------------------------------------------
# Physical constants (SI)
# ---------------------------------------------------------------------------
G0 = 9.80665                # standard gravity, m/s^2
R_UNIV = 8314.462           # universal gas constant, J/(kmol K)
R_SPECIFIC_AIR = 287.0      # J/(kg K), reference gas constant
GAMMA_AIR = 1.4             # reference specific-heat ratio


# ---------------------------------------------------------------------------
# Domain tables (real rules / reference-typical values from bound leaves)
# ---------------------------------------------------------------------------

# Propellant pairs (rocket-engine-cycle leaf, reference-only typicals):
# (rho_ox kg/m3, rho_fuel kg/m3, mixture ratio r_m, isp_vac s).
# r_m None marks the monopropellant hydrazine (single stream).
PROPELLANTS = {
    "LOX/RP-1": (1140.0, 820.0, 2.56, 300.0),
    "LOX/LH2": (1140.0, 71.0, 5.5, 430.0),
    "N2O4/MMH": (1450.0, 880.0, 1.9, 320.0),
    "hydrazine": (1010.0, 1010.0, None, 230.0),
}

# Combustion gas properties per pair (combustion-chamber-design leaf
# convention: theoretical c* from Tc, Mw, gamma). Reference-typical
# values consistent with the leaf anchors (LOX/RP-1: Tc 3670 K, Mw 23,
# gamma 1.20 ~> theoretical c* about 1776 m/s).
GAS_PROPS = {
    "LOX/RP-1": {"tc_k": 3670.0, "mw_kg_kmol": 23.0, "gamma": 1.20},
    "LOX/LH2": {"tc_k": 3500.0, "mw_kg_kmol": 12.0, "gamma": 1.20},
    "N2O4/MMH": {"tc_k": 3400.0, "mw_kg_kmol": 21.5, "gamma": 1.24},
    "hydrazine": {"tc_k": 1600.0, "mw_kg_kmol": 10.0, "gamma": 1.25},
}

CYCLES = ("pressure-fed", "gas-generator", "staged-combustion", "expander")

# Feed-cycle constants (rocket-engine-cycle leaf, reference-only).
P_LOSSES_DEFAULT = 2.0e6        # injector plus line loss, Pa
ETA_PUMP_DEFAULT = 0.7          # pump efficiency, dimensionless
ETA_TURB_DEFAULT = 0.6          # turbine efficiency, dimensionless
PUMP_INLET_PRESSURE = 0.3e6     # feed-tank pressure seen by the pump, Pa
GG_FRACTION_DEFAULT = 0.03      # propellant fraction burned in the GG
GG_PRESSURE_FRACTION = 0.8      # GG pressure as a fraction of p_c
TURBINE_EXIT_PRESSURE = 0.2e6   # turbine exhaust pressure, Pa
GG_CP = 2000.0                  # GG gas cp, J/(kg K)
GG_T_INLET = 1200.0             # GG gas temperature, K
GG_GAMMA = 1.2                  # GG gas specific-heat ratio
STAGED_INLET_FRACTION = 1.5     # preburner discharge, fraction of p_c
EXPANDER_MAX_P_C = 10.0e6       # expander chamber-pressure bound, Pa
PRESSURE_FED_MAX_P_C = 3.0e6    # pressure-fed chamber-pressure bound, Pa
EXPANDER_CP = 12000.0           # warm hydrogen gas cp, J/(kg K)
EXPANDER_T_INLET = 500.0        # cooling-jacket outlet temperature, K
EXPANDER_GAMMA = 1.4            # warm hydrogen specific-heat ratio
EXPANDER_EXIT_FRACTION = 0.85
RHO_WALL = 4430.0               # titanium tank wall density, kg/m3
SIGMA_WALL = 880.0e6            # titanium allowable stress, Pa
REFERENCE_BURN_TIME = 60.0      # s, propellant basis for the tank trade

# Hybrid fuel regression records (hybrid-rocket-motor leaf,
# reference-only typicals).
HYBRID_FUELS = {
    "HTPB-N2O": {"a": 1.2e-4, "n": 0.55, "m": -0.20, "L_ref": 0.6,
                 "rho_f": 920.0, "c_star": 1500.0},
    "HTPB-LOX": {"a": 1.8e-4, "n": 0.50, "m": -0.15, "L_ref": 0.6,
                 "rho_f": 920.0, "c_star": 1750.0},
}

# Solid propellant reference-typical values (solid-rocket-motor leaf
# methodology): APCP-class composite, Vieille rate r = a * p^n.
SOLID_RHO_P = 1800.0            # propellant density, kg/m3
SOLID_A = 2.0e-5                # burn-rate coefficient, m/s per Pa^n
SOLID_N = 0.35                  # pressure exponent
SOLID_CSTAR = 1600.0            # characteristic velocity, m/s
SOLID_ISP = 265.0               # delivered specific impulse, s

# Cooling reference properties (thrust-chamber-cooling leaf worked
# example): hot gas and RP-1 coolant, copper wall.
MU_GAS = 8.0e-5                 # hot-gas viscosity, Pa s
CP_GAS = 2000.0                 # hot-gas cp, J/(kg K)
PR_GAS = 0.72                   # hot-gas Prandtl number
MU_COOLANT = 0.0022             # coolant (RP-1) viscosity, Pa s
CP_COOLANT = 2000.0             # coolant cp, J/(kg K)
K_COOLANT = 0.13                # coolant conductivity, W/(m K)
WALL_CONDUCTIVITY = 390.0       # copper wall conductivity, W/(m K)
WALL_THICKNESS = 0.0015         # copper wall thickness, m
WALL_LIMIT_K = 800.0            # copper wall temperature limit, K
COOLANT_TEMP_K = 300.0          # coolant inlet temperature, K

# Flow-separation constant (rocket-nozzle-flow-separation leaf).
K_SEP = 0.4                     # separation pressure ratio pe/pa
ISA_SEA_LEVEL_PRESSURE = 101325.0
ISA_SEA_LEVEL_TEMPERATURE = 288.15

# Cold-gas thruster constants (cold-gas-thruster leaf).
GAMMA_N2 = 1.4
R_N2 = 296.8

# Propellant-family screening verdicts (propellant-selection leaf).
FAMILY_VERDICT = {
    "cryogenic": {"booster": "suitable", "upper-stage": "suitable",
                  "orbit": "suitable", "deep-space": "caveat",
                  "long-duration": "caveat", "quick-response": "unsuitable"},
    "storable": {"booster": "suitable", "upper-stage": "caveat",
                 "orbit": "caveat", "deep-space": "caveat",
                 "long-duration": "suitable", "quick-response": "suitable"},
    "hypergolic": {"booster": "caveat", "upper-stage": "suitable",
                   "orbit": "suitable", "deep-space": "suitable",
                   "long-duration": "suitable",
                   "quick-response": "suitable"},
    "solid": {"booster": "suitable", "upper-stage": "caveat",
              "orbit": "caveat", "deep-space": "unsuitable",
              "long-duration": "unsuitable", "quick-response": "suitable"},
}
FAMILY_BY_NAME = {
    "lox": "cryogenic", "liquid oxygen": "cryogenic", "lh2": "cryogenic",
    "liquid hydrogen": "cryogenic", "lch4": "cryogenic", "methane": "cryogenic",
    "rp-1": "storable", "rp1": "storable", "kerosene": "storable",
    "mmh": "hypergolic", "udmh": "hypergolic", "hydrazine": "hypergolic",
    "nto": "hypergolic", "nitrogen tetroxide": "hypergolic",
    "n2o4": "hypergolic",
    "htpb": "solid", "apcp": "solid", "ammonium perchlorate": "solid",
    "double-base": "solid", "solid": "solid",
}


def _require_finite(*values) -> None:
    for v in values:
        if v is None or not math.isfinite(v):
            raise ValueError("inputs must be finite, got %r" % (v,))


def _check_positive(value, name) -> None:
    if value <= 0.0:
        raise ValueError("%s must be positive: %r" % (name, value))


# ===========================================================================
# rocket-sizing leaf: rocket equation, mass ratio, propellant mass
# ===========================================================================

def rocket_equation_delta_v(isp_s, m0_kg, mf_kg, g0=G0):
    """Ideal rocket equation delta-v, g0 * Isp * ln(m0 / mf), m/s."""
    _check_positive(isp_s, "specific impulse isp_s")
    _check_positive(m0_kg, "initial mass m0_kg")
    _check_positive(mf_kg, "final mass mf_kg")
    if mf_kg >= m0_kg:
        raise ValueError("final mass must be < initial mass")
    return g0 * isp_s * math.log(m0_kg / mf_kg)


def mass_ratio_from_delta_v(delta_v, isp_s, g0=G0):
    """Mass ratio m0/mf required for a delta-v at a given Isp."""
    if delta_v < 0:
        raise ValueError("delta-v must be >= 0")
    _check_positive(isp_s, "specific impulse isp_s")
    return math.exp(delta_v / (g0 * isp_s))


def propellant_mass(m0_kg, mf_kg):
    """Propellant mass burned, m0 - mf, kg."""
    _check_positive(m0_kg, "initial mass m0_kg")
    _check_positive(mf_kg, "final mass mf_kg")
    if mf_kg >= m0_kg:
        raise ValueError("final mass must be < initial mass")
    return m0_kg - mf_kg


def total_stage_delta_v(stage_delta_vs):
    """Total delta-v across the stages, m/s."""
    if not stage_delta_vs:
        raise ValueError("stage delta-v list must not be empty")
    total = 0.0
    for dv in stage_delta_vs:
        if dv < 0:
            raise ValueError("stage delta-v must be >= 0")
        total += dv
    return total


# ===========================================================================
# rocket-staging leaf: structural index, payload fraction, stage optimum
# ===========================================================================

def structural_index(structure_kg, propellant_kg):
    """Structural index eps = m_struct / (m_struct + m_prop)."""
    _check_positive(structure_kg, "structure mass structure_kg")
    _check_positive(propellant_kg, "propellant mass propellant_kg")
    return structure_kg / (structure_kg + propellant_kg)


def payload_fraction(payload_kg, m0_kg):
    """Payload fraction of a stage, payload mass over initial stage mass."""
    _check_positive(payload_kg, "payload mass payload_kg")
    _check_positive(m0_kg, "initial mass m0_kg")
    if payload_kg >= m0_kg:
        raise ValueError("payload must be < initial mass")
    return payload_kg / m0_kg


def mass_ratio_from_indices(eps, lam):
    """Stage mass ratio r = 1 / (lam + eps*(1 - lam))."""
    if not 0 < eps < 1:
        raise ValueError("structural index must be in (0, 1)")
    if not 0 < lam < 1:
        raise ValueError("payload fraction must be in (0, 1)")
    burnout = lam + eps * (1.0 - lam)
    if burnout <= 0:
        raise ValueError("payload fraction and structural index leave "
                         "no burnout mass")
    return 1.0 / burnout


def payload_fraction_from_mass_ratio(eps, r):
    """Payload fraction implied by a mass ratio and structural index."""
    if not 0 < eps < 1:
        raise ValueError("structural index must be in (0, 1)")
    if r <= 1:
        raise ValueError("mass ratio must be > 1")
    lam = (1.0 / r - eps) / (1.0 - eps)
    if lam <= 0:
        raise ValueError("mass ratio %r is unreachable at eps %r" % (r, eps))
    return lam


def stage_delta_v_from_indices(isp_s, eps, lam, g0=G0):
    """Ideal delta-v of one stage from Isp, eps and payload fraction, m/s."""
    _check_positive(isp_s, "specific impulse isp_s")
    return g0 * isp_s * math.log(mass_ratio_from_indices(eps, lam))


def optimal_equal_stage_split(total_delta_v, n_stages, isp_s, eps, g0=G0):
    """Optimal split of n identical stages for a total delta-v.

    Returns (r_star, lam_stage, lam_total): the per-stage mass ratio,
    the per-stage payload fraction, and the total payload fraction.
    """
    if total_delta_v <= 0:
        raise ValueError("total delta-v must be > 0")
    if n_stages < 1:
        raise ValueError("stage count must be >= 1")
    _check_positive(isp_s, "specific impulse isp_s")
    if not 0 < eps < 1:
        raise ValueError("structural index must be in (0, 1)")
    r_star = math.exp(total_delta_v / (n_stages * g0 * isp_s))
    lam_stage = payload_fraction_from_mass_ratio(eps, r_star)
    return r_star, lam_stage, lam_stage ** n_stages


def stage_count_for_delta_v(total_delta_v, isp_s, eps, target_payload_fraction,
                            g0=G0):
    """Minimum identical-stage count reaching a target total payload
    fraction. Returns (n_stages, lam_total_achieved)."""
    if total_delta_v <= 0:
        raise ValueError("total delta-v must be > 0")
    _check_positive(isp_s, "specific impulse isp_s")
    if not 0 < eps < 1:
        raise ValueError("structural index must be in (0, 1)")
    if not 0 < target_payload_fraction < 1:
        raise ValueError("target payload fraction must be in (0, 1)")
    limit = math.exp(-total_delta_v / (g0 * isp_s * (1.0 - eps)))
    if target_payload_fraction > limit:
        raise ValueError("target payload fraction exceeds the asymptotic "
                         "staging limit %r" % limit)
    n = 1
    while True:
        try:
            _, _, lam_total = optimal_equal_stage_split(
                total_delta_v, n, isp_s, eps, g0)
        except ValueError:
            n += 1
            continue
        if lam_total >= target_payload_fraction:
            return n, lam_total
        n += 1


def stage_mass_budget(dv_ms, isp_s, eps, payload_kg):
    """Mass budget of one stage for an ideal delta-v at a structural index.

    Backs the stage mass ratio out of the rocket equation, the payload
    fraction out of the structural index, then the initial, propellant
    and inert masses. Returns a dict.
    """
    _check_positive(payload_kg, "payload mass payload_kg")
    if dv_ms <= 0:
        raise ValueError("stage delta-v must be > 0")
    r = mass_ratio_from_delta_v(dv_ms, isp_s)
    lam = payload_fraction_from_mass_ratio(eps, r)
    m0 = payload_kg / lam
    m_inert = eps * (1.0 - lam) * m0
    m_prop = (1.0 - lam) * (1.0 - eps) * m0
    return {"r": r, "lam": lam, "m0_kg": m0, "m_prop_kg": m_prop,
            "m_inert_kg": m_inert, "m_burnout_kg": m_inert + payload_kg}


# ===========================================================================
# nozzle-design leaf: isentropic compressible flow for the rocket nozzle
# ===========================================================================

def _area_ratio_at_mach(m, gamma):
    """Isentropic area-Mach relation A/A* evaluated at Mach number m."""
    return ((1.0 / m)
            * (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (2.0 * (gamma - 1.0)))
            * (1.0 + (gamma - 1.0) / 2.0 * m * m)
            ** ((gamma + 1.0) / (2.0 * (gamma - 1.0))))


def exit_mach_from_area_ratio(area_ratio, gamma=GAMMA_AIR):
    """Supersonic exit Mach number for an area ratio A/A* (bisection)."""
    if area_ratio <= 1:
        raise ValueError("area ratio must be > 1 (supersonic branch)")
    if gamma <= 1:
        raise ValueError("gamma must be > 1")
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


def mass_flow(p0_pa, t0_k, a_throat_m2, gamma=GAMMA_AIR, r_j_kgk=R_SPECIFIC_AIR):
    """Choked mass flow through the nozzle throat, kg/s."""
    if p0_pa <= 0 or t0_k <= 0 or a_throat_m2 <= 0:
        raise ValueError("p0, t0 and throat area must be positive")
    if gamma <= 1 or r_j_kgk <= 0:
        raise ValueError("gamma must be > 1 and R > 0")
    return (p0_pa * a_throat_m2
            * math.sqrt(gamma / (r_j_kgk * t0_k))
            * (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (2.0 * (gamma - 1.0))))


def exit_velocity(p0_pa, t0_k, pe_pa, gamma=GAMMA_AIR, r_j_kgk=R_SPECIFIC_AIR):
    """Ideal isentropic exit velocity, m/s."""
    if p0_pa <= 0 or t0_k <= 0 or pe_pa <= 0:
        raise ValueError("p0, t0 and pe must be positive")
    if pe_pa > p0_pa:
        raise ValueError("exit pressure cannot exceed chamber pressure")
    if gamma <= 1 or r_j_kgk <= 0:
        raise ValueError("gamma must be > 1 and R > 0")
    return math.sqrt(
        (2.0 * gamma * r_j_kgk * t0_k / (gamma - 1.0))
        * (1.0 - (pe_pa / p0_pa) ** ((gamma - 1.0) / gamma)))


def ideal_thrust(mdot_kgs, ve_ms, pe_pa, pa_pa, ae_m2):
    """Ideal nozzle thrust F = mdot*ve + (Pe - Pa)*Ae, N."""
    if mdot_kgs < 0 or ve_ms < 0:
        raise ValueError("mass flow and exit velocity must be >= 0")
    if pe_pa <= 0 or pa_pa <= 0:
        raise ValueError("pressures must be positive")
    if ae_m2 < 0:
        raise ValueError("exit area must be >= 0")
    return mdot_kgs * ve_ms + (pe_pa - pa_pa) * ae_m2


def optimum_expansion(p0_pa, pe_pa, pa_pa):
    """Expansion verdict against ambient: 'over' / 'under' / 'optimum'."""
    if p0_pa <= 0 or pe_pa <= 0 or pa_pa <= 0:
        raise ValueError("pressures must be positive")
    if pe_pa > p0_pa:
        raise ValueError("exit pressure cannot exceed chamber pressure")
    if pe_pa < pa_pa:
        return "over"
    if pe_pa > pa_pa:
        return "under"
    return "optimum"


def exit_static_pressure(p0_pa, mach, gamma):
    """Isentropic static pressure at Mach M:
    P = P0 * (1 + (g-1)/2 M^2)^(-g/(g-1)), Pa."""
    if p0_pa <= 0 or mach < 0:
        raise ValueError("pressure and Mach must be positive")
    if gamma <= 1:
        raise ValueError("gamma must be > 1")
    return p0_pa * (1.0 + (gamma - 1.0) / 2.0 * mach * mach) ** (
        -gamma / (gamma - 1.0))


# ===========================================================================
# rocket-engine-cycle leaf: feed-system balance
# ===========================================================================

def propellant_pair_properties(pair_name):
    """Return (rho_ox, rho_fuel, r_m, isp_vac) for a known pair."""
    try:
        return PROPELLANTS[pair_name]
    except (KeyError, TypeError):
        raise ValueError("unknown propellant pair: %s" % (pair_name,))


def mass_flow_split(f, isp, r_m, g0=G0):
    """Return (mdot, mdot_ox, mdot_f) from thrust, Isp and mixture ratio.

    A monopropellant (r_m None) returns mdot_ox = mdot, mdot_f = 0.
    """
    _require_finite(f, isp, r_m)
    if f <= 0 or isp <= 0:
        raise ValueError("thrust and specific impulse must be positive")
    if r_m is not None and r_m <= 0:
        raise ValueError("mixture ratio must be positive")
    mdot = f / (isp * g0)
    if r_m is None:
        return mdot, mdot, 0.0
    mdot_ox = mdot * r_m / (1.0 + r_m)
    mdot_f = mdot / (1.0 + r_m)
    return mdot, mdot_ox, mdot_f


def pump_discharge_pressure(p_c, p_losses):
    """Pump discharge pressure covers chamber pressure plus losses, Pa."""
    if p_c <= 0:
        raise ValueError("chamber pressure must be positive")
    if p_losses < 0:
        raise ValueError("pressure losses must not be negative")
    return p_c + p_losses


def pump_power(mdot_prop, p_discharge, p_inlet, rho_prop, eta_pump):
    """Hydraulic pump power mdot*(p_discharge - p_inlet)/(rho*eta), W."""
    _require_finite(mdot_prop, p_discharge, p_inlet, rho_prop, eta_pump)
    if not 0.0 < eta_pump <= 1.0:
        raise ValueError("pump efficiency must lie in (0, 1]")
    if mdot_prop <= 0 or p_discharge <= 0 or rho_prop <= 0:
        raise ValueError("mass flow, discharge pressure and density must "
                         "be positive")
    if p_inlet < 0:
        raise ValueError("inlet pressure must not be negative")
    if p_discharge <= p_inlet:
        raise ValueError("discharge pressure must exceed inlet pressure")
    return mdot_prop * (p_discharge - p_inlet) / (rho_prop * eta_pump)


def turbine_power(mdot_gas, cp, t_inlet, eta_turb, gamma, p_inlet, p_exit):
    """Turbine drive power from an isentropic expansion model, W."""
    _require_finite(mdot_gas, cp, t_inlet, eta_turb, gamma, p_inlet, p_exit)
    if not 0.0 < eta_turb <= 1.0:
        raise ValueError("turbine efficiency must lie in (0, 1]")
    if mdot_gas <= 0 or cp <= 0 or t_inlet <= 0:
        raise ValueError("gas flow, cp and inlet temperature must be "
                         "positive")
    if gamma <= 1.0:
        raise ValueError("gamma must exceed 1")
    if p_inlet <= 0 or p_exit <= 0 or p_exit >= p_inlet:
        raise ValueError("turbine pressures must satisfy 0 < pexit < pinlet")
    ratio = (p_exit / p_inlet) ** ((gamma - 1.0) / gamma)
    return mdot_gas * cp * t_inlet * eta_turb * (1.0 - ratio)


def cycle_feasibility(cycle, propellant, p_c):
    """Return (feasible, reason) for one cycle at chamber pressure p_c."""
    if cycle not in CYCLES:
        raise ValueError("unknown engine cycle: %s" % (cycle,))
    _require_finite(p_c)
    if p_c <= 0:
        raise ValueError("chamber pressure must be positive")
    _, _, r_m, _ = propellant_pair_properties(propellant)
    if cycle == "pressure-fed":
        if p_c <= PRESSURE_FED_MAX_P_C:
            return True, "chamber pressure within the pressure-fed bound"
        return False, ("chamber pressure above the %d MPa pressure-fed "
                       "bound; tank mass penalty heavy"
                       % (PRESSURE_FED_MAX_P_C / 1.0e6))
    if cycle == "expander":
        if propellant != "LOX/LH2":
            return False, ("expander drive needs the high-heat-capacity "
                           "LH2 fuel; %s does not qualify" % (propellant,))
        if p_c > EXPANDER_MAX_P_C:
            return False, ("chamber pressure above the %d MPa expander "
                           "bound" % (EXPANDER_MAX_P_C / 1.0e6))
        return True, "LH2 heated in the cooling jacket drives the turbine"
    if r_m is None:
        return False, ("%s needs an oxidizer/fuel pair; monopropellant has "
                       "no turbine drive gas split" % (cycle,))
    return True, "turbine drive gas carried at part or full chamber pressure"


def mixture_bulk_density(rho_ox, rho_fuel, r_m):
    """Bulk density of the propellant pair, kg/m3."""
    _require_finite(rho_ox, rho_fuel)
    if rho_ox <= 0 or rho_fuel <= 0:
        raise ValueError("densities must be positive")
    if r_m is None:
        return rho_ox
    return (1.0 + r_m) / (r_m / rho_ox + 1.0 / rho_fuel)


def pressure_fed_tank_mass(p_tank, propellant_volume):
    """Thin-wall feed-tank mass p*V*rho_wall/(2*sigma), kg."""
    _require_finite(p_tank, propellant_volume)
    if p_tank <= 0:
        raise ValueError("tank pressure must be positive")
    if propellant_volume < 0:
        raise ValueError("propellant volume must not be negative")
    return p_tank * propellant_volume * RHO_WALL / (2.0 * SIGMA_WALL)


def engine_cycle_analysis(cycle, f, p_c, propellant, isp=None, p_losses=None,
                          eta_pump=None, eta_turb=None, gg_fraction=None,
                          p_tank_inlet=None, burn_time=None):
    """Full feed-cycle balance; returns the summary dict (see the leaf)."""
    if cycle not in CYCLES:
        raise ValueError("unknown engine cycle: %s" % (cycle,))
    _require_finite(f, p_c)
    if f <= 0 or p_c <= 0:
        raise ValueError("thrust and chamber pressure must be positive")
    rho_ox, rho_fuel, r_m, isp_vac = propellant_pair_properties(propellant)
    isp_use = isp_vac if isp is None else isp
    _require_finite(isp_use)
    if isp_use <= 0:
        raise ValueError("specific impulse must be positive")
    p_losses = P_LOSSES_DEFAULT if p_losses is None else p_losses
    eta_pump = ETA_PUMP_DEFAULT if eta_pump is None else eta_pump
    eta_turb = ETA_TURB_DEFAULT if eta_turb is None else eta_turb
    gg_fraction = GG_FRACTION_DEFAULT if gg_fraction is None else gg_fraction
    p_tank_inlet = PUMP_INLET_PRESSURE if p_tank_inlet is None else p_tank_inlet
    burn_time = REFERENCE_BURN_TIME if burn_time is None else burn_time
    _require_finite(p_losses, gg_fraction, p_tank_inlet, burn_time)
    if not (0.0 < gg_fraction < 1.0):
        raise ValueError("gas-generator fraction must lie in (0, 1)")
    if p_losses < 0 or p_tank_inlet < 0 or burn_time <= 0:
        raise ValueError("losses and tank inlet non-negative; burn time "
                         "positive")

    mdot, mdot_ox, mdot_f = mass_flow_split(f, isp_use, r_m, G0)
    feasible, reason = cycle_feasibility(cycle, propellant, p_c)
    bulk_rho = mixture_bulk_density(rho_ox, rho_fuel, r_m)
    prop_volume = burn_time * mdot / bulk_rho

    pump_discharge = pump_discharge_pressure(p_c, p_losses)
    pump_ox = pump_fuel = pump_total = turb = 0.0
    drive_fraction = 0.0
    tank_pressure = 0.0
    if cycle == "pressure-fed":
        tank_pressure = p_c + p_losses
    elif cycle == "gas-generator":
        pump_ox = pump_power(mdot_ox, pump_discharge, p_tank_inlet, rho_ox,
                             eta_pump)
        pump_fuel = pump_power(mdot_f, pump_discharge, p_tank_inlet, rho_fuel,
                               eta_pump)
        pump_total = pump_ox + pump_fuel
        if feasible:
            mdot_gg = gg_fraction * mdot
            p_gg = GG_PRESSURE_FRACTION * p_c
            turb = turbine_power(mdot_gg, GG_CP, GG_T_INLET, eta_turb,
                                 GG_GAMMA, p_gg, TURBINE_EXIT_PRESSURE)
            drive_fraction = gg_fraction
        tank_pressure = p_tank_inlet
    elif cycle == "staged-combustion":
        pump_ox = pump_power(mdot_ox, pump_discharge, p_tank_inlet, rho_ox,
                             eta_pump)
        pump_fuel = pump_power(mdot_f, pump_discharge, p_tank_inlet, rho_fuel,
                               eta_pump)
        pump_total = pump_ox + pump_fuel
        if feasible:
            p_preburner = STAGED_INLET_FRACTION * p_c
            turb = turbine_power(mdot, GG_CP, GG_T_INLET, eta_turb,
                                 GG_GAMMA, p_preburner,
                                 TURBINE_EXIT_PRESSURE)
            drive_fraction = 1.0
        tank_pressure = p_tank_inlet
    elif cycle == "expander":
        pump_ox = pump_power(mdot_ox, pump_discharge, p_tank_inlet, rho_ox,
                             eta_pump)
        pump_fuel = pump_power(mdot_f, pump_discharge, p_tank_inlet, rho_fuel,
                               eta_pump)
        pump_total = pump_ox + pump_fuel
        if feasible:
            p_exit = EXPANDER_EXIT_FRACTION * p_c
            turb = turbine_power(mdot_f, EXPANDER_CP, EXPANDER_T_INLET,
                                 eta_turb, EXPANDER_GAMMA, p_c, p_exit)
            drive_fraction = mdot_f / mdot
        tank_pressure = p_tank_inlet

    tank_penalty = pressure_fed_tank_mass(tank_pressure, prop_volume)
    power_balance = turb - pump_total
    if cycle == "pressure-fed":
        if feasible:
            verdict = ("pressure-fed cycle feasible at p_c %.2f MPa: tank "
                       "pressure %.2f MPa, tank mass penalty %.0f kg for "
                       "the %.0f s burn basis"
                       % (p_c / 1.0e6, tank_pressure / 1.0e6, tank_penalty,
                          burn_time))
        else:
            verdict = ("pressure-fed cycle rejected at p_c %.2f MPa: tank "
                       "mass penalty %.0f kg is heavy against a "
                       "low-pressure pump-fed feed"
                       % (p_c / 1.0e6, tank_penalty))
    elif not feasible:
        verdict = "cycle rejected: %s" % (reason,)
    elif power_balance >= 0.0:
        verdict = ("%s cycle feasible: total pump power %.3f MW, turbine "
                   "power %.3f MW, surplus %.3f MW, drive mass fraction "
                   "%.0f%%"
                   % (cycle, pump_total / 1.0e6, turb / 1.0e6,
                      power_balance / 1.0e6, 100.0 * drive_fraction))
    else:
        verdict = ("%s cycle feasible on the pressure bound but "
                   "underpowered: turbine power %.3f MW against %.3f MW "
                   "of pump power, deficit %.3f MW"
                   % (cycle, turb / 1.0e6, pump_total / 1.0e6,
                      -power_balance / 1.0e6))
    return {
        "cycle": cycle, "propellant": propellant, "feasible": feasible,
        "reason": reason, "isp": isp_use, "mdot": mdot, "mdot_ox": mdot_ox,
        "mdot_f": mdot_f, "pump_discharge_pressure": pump_discharge,
        "pump_power_ox": pump_ox, "pump_power_fuel": pump_fuel,
        "pump_power_total": pump_total, "turbine_power": turb,
        "power_balance": power_balance, "drive_mass_fraction": drive_fraction,
        "tank_pressure": tank_pressure, "tank_mass_penalty": tank_penalty,
        "verdict": verdict,
    }


# ===========================================================================
# combustion-chamber-design leaf: chamber upstream of the throat
# ===========================================================================

def characteristic_velocity(pc, throat_area_, mass_flow_):
    """Delivered c* = Pc * At / mdot, m/s."""
    if pc <= 0 or throat_area_ <= 0 or mass_flow_ <= 0:
        raise ValueError("pc, throat area and mass flow must be positive")
    return pc * throat_area_ / mass_flow_


def theoretical_cstar(chamber_temp, molecular_weight, gamma):
    """Ideal c* from gas properties, m/s."""
    if chamber_temp <= 0 or molecular_weight <= 0:
        raise ValueError("chamber_temp and molecular_weight must be positive")
    if not 1.0 < gamma <= 5.0 / 3.0:
        raise ValueError("gamma must be in (1, 5/3]")
    r = R_UNIV / molecular_weight
    denom = gamma * math.sqrt(
        (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (gamma - 1.0)))
    return math.sqrt(gamma * r * chamber_temp) / denom


def thrust_coefficient(thrust, pc, throat_area_):
    """Thrust coefficient Cf = F / (Pc * At), dimensionless."""
    if thrust <= 0 or pc <= 0 or throat_area_ <= 0:
        raise ValueError("thrust, pc and throat area must be positive")
    return thrust / (pc * throat_area_)


def thrust_from_cf(cf, pc, throat_area_):
    """Thrust F = Cf * Pc * At, N."""
    if cf <= 0 or pc <= 0 or throat_area_ <= 0:
        raise ValueError("cf, pc and throat area must be positive")
    return cf * pc * throat_area_


def throat_area_from_flow(mass_flow_, cstar, pc):
    """Required throat area At = mdot * c* / Pc, m2."""
    if mass_flow_ <= 0 or cstar <= 0 or pc <= 0:
        raise ValueError("mass flow, cstar and pc must be positive")
    return mass_flow_ * cstar / pc


def contraction_ratio(chamber_area, throat_area_):
    """Chamber contraction ratio eps_c = Ac / At (Ac must exceed At)."""
    if chamber_area <= 0 or throat_area_ <= 0:
        raise ValueError("chamber area and throat area must be positive")
    if chamber_area <= throat_area_:
        raise ValueError("chamber area must exceed throat area")
    return chamber_area / throat_area_


def chamber_volume(lstar, throat_area_):
    """Chamber volume Vc = L-star * At, m3."""
    if lstar <= 0 or throat_area_ <= 0:
        raise ValueError("lstar and throat area must be positive")
    return lstar * throat_area_


def nozzle_throat_radius(throat_area_):
    """Circular throat radius r = sqrt(At/pi), m."""
    if throat_area_ <= 0:
        raise ValueError("throat area must be positive")
    return math.sqrt(throat_area_ / math.pi)


def vacuum_specific_impulse(thrust, mass_flow_):
    """Vacuum Isp = F / (mdot * g0), s."""
    if thrust <= 0 or mass_flow_ <= 0:
        raise ValueError("thrust and mass flow must be positive")
    return thrust / (mass_flow_ * G0)


# ===========================================================================
# solid-rocket-motor leaf: grain ballistics
# ===========================================================================

def burn_rate(pressure, a, n):
    """Vieille/St. Robert burn rate r = a * p^n, m/s."""
    _check_positive(pressure, "pressure")
    _check_positive(a, "burn rate coefficient a")
    if not 0.0 < n < 1.0:
        raise ValueError("pressure exponent n must be in (0, 1)")
    return a * pressure ** n


def solid_characteristic_velocity(T_c, gamma, R):
    """Solid c* = sqrt(R*Tc / (gamma*(2/(gamma+1))**((gamma+1)/(gamma-1)))),
    m/s."""
    _check_positive(T_c, "chamber temperature T_c")
    _check_positive(R, "specific gas constant R")
    if gamma <= 1.0:
        raise ValueError("gamma must be > 1")
    return math.sqrt(R * T_c / (gamma
                                * (2.0 / (gamma + 1.0))
                                ** ((gamma + 1.0) / (gamma - 1.0))))


def equilibrium_chamber_pressure(rho_p, a, n, A_b, A_t, c_star):
    """Solid equilibrium chamber pressure
    p_c = (rho_p*a*Ab*c*/At)**(1/(1-n)), Pa."""
    _check_positive(rho_p, "propellant density rho_p")
    _check_positive(a, "burn rate coefficient a")
    if not 0.0 < n < 1.0:
        raise ValueError("pressure exponent n must be in (0, 1); n = 1 is "
                         "the singular limiting case")
    _check_positive(A_b, "burn area A_b")
    _check_positive(A_t, "throat area A_t")
    _check_positive(c_star, "characteristic velocity c_star")
    return (rho_p * a * A_b * c_star / A_t) ** (1.0 / (1.0 - n))


def solid_mass_flow(p_c, A_t, c_star):
    """Choked mass flow m_dot = p_c * A_t / c*, kg/s."""
    _check_positive(p_c, "chamber pressure p_c")
    _check_positive(A_t, "throat area A_t")
    _check_positive(c_star, "characteristic velocity c_star")
    return p_c * A_t / c_star


def burn_mass_flow(rho_p, A_b, rate):
    """Mass generated by the burning surface rho_p * A_b * r, kg/s."""
    _check_positive(rho_p, "propellant density rho_p")
    _check_positive(A_b, "burn area A_b")
    _check_positive(rate, "burn rate r")
    return rho_p * A_b * rate


def thrust_from_isp(Isp, m_dot, g0=G0):
    """Thrust F = Isp * g0 * m_dot, N."""
    _check_positive(Isp, "specific impulse Isp")
    _check_positive(m_dot, "mass flow m_dot")
    _check_positive(g0, "gravity g0")
    return Isp * g0 * m_dot


def total_impulse(F, burn_time_):
    """Total impulse I_t = F * t_b, N s."""
    _check_positive(F, "thrust F")
    _check_positive(burn_time_, "burn time t_b")
    return F * burn_time_


def web_burn_time(web, rate):
    """Burn time for a web thickness t_b = web / r, s."""
    _check_positive(web, "web thickness web")
    _check_positive(rate, "burn rate r")
    return web / rate


def tubular_grain_burn_area(D_inner, L):
    """Inner-bore burn area of a tubular grain pi*D*L, m2."""
    _check_positive(D_inner, "inner bore diameter D_inner")
    _check_positive(L, "grain length L")
    return math.pi * D_inner * L


def burn_area_verdict(initial_area, final_area):
    """Grain progression verdict: progressive / neutral / regressive."""
    _check_positive(initial_area, "initial burn area")
    _check_positive(final_area, "final burn area")
    if abs(final_area - initial_area) <= 1e-9 * initial_area:
        return "neutral"
    return "progressive" if final_area > initial_area else "regressive"


# ===========================================================================
# thrust-chamber-cooling leaf: throat thermal balance (Bartz / D-B)
# ===========================================================================

def throat_area(diameter_m):
    """Throat cross-section area pi*d^2/4, m2."""
    if diameter_m <= 0:
        raise ValueError("throat diameter must be positive")
    return math.pi * diameter_m ** 2 / 4.0


def chamber_mass_flow(chamber_pressure_pa, throat_area_m2, cstar_m_s):
    """Propellant mass flow Pc*At/c*, kg/s."""
    if chamber_pressure_pa <= 0 or throat_area_m2 <= 0 or cstar_m_s <= 0:
        raise ValueError("chamber pressure, throat area and c-star must be "
                         "positive")
    return chamber_pressure_pa * throat_area_m2 / cstar_m_s


def adiabatic_wall_temperature(chamber_temp_k, gamma, prandtl=0.72):
    """Recovery temperature at the throat for M = 1 hot-gas flow.
    Returns {throat_static_temp_k, recovery_temp_k}."""
    if chamber_temp_k <= 0 or prandtl <= 0:
        raise ValueError("chamber temperature and Prandtl must be positive")
    if gamma <= 1:
        raise ValueError("gamma must be > 1")
    half = (gamma - 1.0) / 2.0
    throat_static = chamber_temp_k / (1.0 + half)
    recovery = throat_static * (1.0 + prandtl ** (1.0 / 3.0) * half)
    return {"throat_static_temp_k": throat_static,
            "recovery_temp_k": recovery}


def bartz_hot_gas_coefficient(chamber_pressure_pa, cstar_m_s,
                              throat_diameter_m, mu_gas, cp_gas,
                              prandtl_gas, sigma=1.0):
    """Bartz hot-gas convective coefficient at the throat, W/(m2 K)."""
    if chamber_pressure_pa <= 0 or cstar_m_s <= 0 or throat_diameter_m <= 0:
        raise ValueError("chamber pressure, c-star and throat diameter must "
                         "be positive")
    if mu_gas <= 0 or cp_gas <= 0 or prandtl_gas <= 0 or sigma <= 0:
        raise ValueError("gas properties and sigma must be positive")
    property_term = mu_gas ** 0.2 * cp_gas / prandtl_gas ** 0.6
    pressure_term = (chamber_pressure_pa / cstar_m_s) ** 0.8
    diameter_term = throat_diameter_m ** 0.2
    return 0.026 * property_term * pressure_term / diameter_term * sigma


def coolant_side_coefficient(mass_flux, hydraulic_diameter_m, mu_c, cp_c, k_c):
    """Coolant-side coefficient (Dittus-Boelter).
    Returns {h_c, reynolds, nusselt, prandtl}."""
    if mass_flux <= 0 or hydraulic_diameter_m <= 0:
        raise ValueError("mass flux and hydraulic diameter must be positive")
    if mu_c <= 0 or cp_c <= 0 or k_c <= 0:
        raise ValueError("coolant properties must be positive")
    reynolds = mass_flux * hydraulic_diameter_m / mu_c
    prandtl = cp_c * mu_c / k_c
    nusselt = 0.023 * reynolds ** 0.8 * prandtl ** 0.4
    h_c = nusselt * k_c / hydraulic_diameter_m
    return {"h_c": h_c, "reynolds": reynolds, "nusselt": nusselt,
            "prandtl": prandtl}


def wall_heat_flux(hot_coeff, cold_coeff, wall_thickness_m, wall_conductivity,
                   recovery_temp_k, coolant_temp_k):
    """Series wall resistance network.
    Returns {heat_flux_wm2, hot_wall_temp_k, cold_wall_temp_k,
    wall_delta_temp_k}."""
    if hot_coeff <= 0 or cold_coeff <= 0 or wall_thickness_m <= 0:
        raise ValueError("coefficients and wall thickness must be positive")
    if wall_conductivity <= 0 or recovery_temp_k <= 0 or coolant_temp_k <= 0:
        raise ValueError("conductivity and temperatures must be positive")
    resistance = (1.0 / hot_coeff + wall_thickness_m / wall_conductivity
                  + 1.0 / cold_coeff)
    q = (recovery_temp_k - coolant_temp_k) / resistance
    return {"heat_flux_wm2": q,
            "hot_wall_temp_k": recovery_temp_k - q / hot_coeff,
            "cold_wall_temp_k": coolant_temp_k + q / cold_coeff,
            "wall_delta_temp_k": q * wall_thickness_m / wall_conductivity}


def coolant_mass_flux_for_wall_limit(hot_coeff, wall_thickness_m,
                                     wall_conductivity, recovery_temp_k,
                                     coolant_temp_k, wall_limit_k,
                                     coolant_props):
    """Coolant mass flux holding the hot wall at the limit.
    Returns {required_h_c, required_reynolds, required_mass_flux}."""
    if hot_coeff <= 0 or wall_thickness_m <= 0 or wall_conductivity <= 0:
        raise ValueError("hot coefficient, thickness and conductivity must "
                         "be positive")
    if recovery_temp_k <= 0 or coolant_temp_k <= 0 or wall_limit_k <= 0:
        raise ValueError("temperatures and limit must be positive")
    if wall_limit_k >= recovery_temp_k:
        raise ValueError("wall limit must be below the recovery temperature")
    d_h = coolant_props["hydraulic_diameter_m"]
    mu_c = coolant_props["mu_c"]
    cp_c = coolant_props["cp_c"]
    k_c = coolant_props["k_c"]
    if d_h <= 0 or mu_c <= 0 or cp_c <= 0 or k_c <= 0:
        raise ValueError("coolant properties must be positive")
    q_lim = hot_coeff * (recovery_temp_k - wall_limit_k)
    resistance_lim = (recovery_temp_k - coolant_temp_k) / q_lim
    conduction = 1.0 / hot_coeff + wall_thickness_m / wall_conductivity
    required_h_c = 1.0 / (resistance_lim - conduction)
    if required_h_c <= 0:
        raise ValueError("wall limit is below what infinite coolant "
                         "convection could hold")
    prandtl = cp_c * mu_c / k_c
    required_reynolds = (required_h_c * d_h
                         / (0.023 * prandtl ** 0.4 * k_c)) ** (1.0 / 0.8)
    required_mass_flux = required_reynolds * mu_c / d_h
    return {"required_h_c": required_h_c,
            "required_reynolds": required_reynolds,
            "required_mass_flux": required_mass_flux}


def film_cooling_handoff(hot_wall_temp_k, wall_limit_k):
    """True when plain regenerative flow cannot hold the wall limit."""
    if hot_wall_temp_k <= 0 or wall_limit_k <= 0:
        raise ValueError("temperatures must be positive")
    return hot_wall_temp_k > wall_limit_k


def chamber_cooling_summary(chamber_pressure_pa, cstar_m_s, chamber_temp_k,
                            gamma, throat_diameter_m, coolant_mass_flux,
                            wall_thickness_m=WALL_THICKNESS,
                            wall_conductivity=WALL_CONDUCTIVITY,
                            wall_limit_k=WALL_LIMIT_K,
                            coolant_temp_k=COOLANT_TEMP_K,
                            prandtl_gas=PR_GAS, mu_gas=MU_GAS,
                            cp_gas=CP_GAS,
                            hydraulic_diameter_m=0.002, mu_c=MU_COOLANT,
                            cp_c=CP_COOLANT, k_c=K_COOLANT, sigma=1.0):
    """One-call cooling summary for a chamber operating point. Dict."""
    at = throat_area(throat_diameter_m)
    mdot = chamber_mass_flow(chamber_pressure_pa, at, cstar_m_s)
    aw = adiabatic_wall_temperature(chamber_temp_k, gamma, prandtl_gas)
    h_g = bartz_hot_gas_coefficient(chamber_pressure_pa, cstar_m_s,
                                    throat_diameter_m, mu_gas, cp_gas,
                                    prandtl_gas, sigma)
    coolant = coolant_side_coefficient(coolant_mass_flux,
                                       hydraulic_diameter_m, mu_c, cp_c, k_c)
    wall = wall_heat_flux(h_g, coolant["h_c"], wall_thickness_m,
                          wall_conductivity, aw["recovery_temp_k"],
                          coolant_temp_k)
    handoff = film_cooling_handoff(wall["hot_wall_temp_k"], wall_limit_k)
    required = coolant_mass_flux_for_wall_limit(
        h_g, wall_thickness_m, wall_conductivity, aw["recovery_temp_k"],
        coolant_temp_k, wall_limit_k,
        {"hydraulic_diameter_m": hydraulic_diameter_m, "mu_c": mu_c,
         "cp_c": cp_c, "k_c": k_c})
    return {
        "throat_area_m2": at, "chamber_mass_flow_kg_s": mdot,
        "throat_static_temp_k": aw["throat_static_temp_k"],
        "recovery_temp_k": aw["recovery_temp_k"], "h_g": h_g,
        "h_c": coolant["h_c"], "reynolds": coolant["reynolds"],
        "nusselt": coolant["nusselt"], "prandtl": coolant["prandtl"],
        "heat_flux_wm2": wall["heat_flux_wm2"],
        "hot_wall_temp_k": wall["hot_wall_temp_k"],
        "cold_wall_temp_k": wall["cold_wall_temp_k"],
        "wall_delta_temp_k": wall["wall_delta_temp_k"],
        "film_cooling_handoff": handoff,
        "required_h_c": required["required_h_c"],
        "required_reynolds": required["required_reynolds"],
        "required_mass_flux": required["required_mass_flux"],
    }


# ===========================================================================
# rocket-gravity-loss leaf: powered-ascent loss accounting
# ===========================================================================

def burn_time(propellant_mass_kg, mass_flow_kgs):
    """Powered-ascent burn time t_b = m_prop / m_dot, s."""
    if propellant_mass_kg <= 0 or mass_flow_kgs <= 0:
        raise ValueError("propellant mass and mass flow must be positive")
    return propellant_mass_kg / mass_flow_kgs


def thrust_to_weight(thrust, initial_mass):
    """Launch thrust-to-weight ratio TWR = T / (m0 * g0)."""
    if thrust <= 0 or initial_mass <= 0:
        raise ValueError("thrust and initial mass must be positive")
    return thrust / (initial_mass * G0)


def gravity_loss_pitched(burn_time_s, mean_path_angle_deg):
    """Pitched-ascent gravity loss g0 * t_b * sin(gamma), m/s."""
    if burn_time_s < 0:
        raise ValueError("burn time must not be negative")
    if not 0.0 <= mean_path_angle_deg <= 90.0:
        raise ValueError("mean flight-path angle must lie in [0, 90] deg")
    return G0 * burn_time_s * math.sin(math.radians(mean_path_angle_deg))


def effective_delta_v(ideal_delta_v, gravity_loss, drag_loss=0.0):
    """Effective ascent delta-v: ideal budget minus the losses, m/s."""
    if gravity_loss < 0 or drag_loss < 0:
        raise ValueError("losses must not be negative")
    if gravity_loss + drag_loss > ideal_delta_v:
        raise ValueError("losses sum to more than the ideal delta-v")
    return ideal_delta_v - gravity_loss - drag_loss


def required_ideal_delta_v(target_delta_v, gravity_loss, drag_loss=0.0):
    """Ideal delta-v required for a net target: target plus losses, m/s."""
    if gravity_loss < 0 or drag_loss < 0:
        raise ValueError("losses must not be negative")
    return target_delta_v + gravity_loss + drag_loss


# ===========================================================================
# rocket-nozzle-flow-separation leaf
# ===========================================================================

def separation_pressure_ratio(pa, k_sep=K_SEP):
    """Separation pressure p_sep = k_sep * pa, Pa."""
    if pa <= 0 or k_sep <= 0:
        raise ValueError("pa and k_sep must be positive")
    return k_sep * pa


def separation_mach(pc, p_sep, gamma):
    """Isentropic Mach number at the pressure ratio pc / p_sep."""
    if pc <= 0 or p_sep <= 0:
        raise ValueError("pressures must be positive")
    if gamma <= 1.0:
        raise ValueError("gamma must be > 1")
    if pc <= p_sep:
        raise ValueError("pc must exceed the separation pressure")
    term = (pc / p_sep) ** ((gamma - 1.0) / gamma)
    return ((term - 1.0) * 2.0 / (gamma - 1.0)) ** 0.5


def area_ratio_from_mach(M, gamma):
    """Isentropic area ratio A/A* for a Mach number M."""
    if M <= 0.0:
        raise ValueError("Mach number M must be positive")
    if gamma <= 1.0:
        raise ValueError("gamma must be > 1")
    exponent = (gamma + 1.0) / (2.0 * (gamma - 1.0))
    core = (2.0 / (gamma + 1.0)) * (1.0 + 0.5 * (gamma - 1.0) * M * M)
    return (1.0 / M) * core ** exponent


def separation_station_area_ratio(pc, pa, gamma):
    """Nozzle area ratio A_sep/At at the separation station."""
    p_sep = separation_pressure_ratio(pa)
    m_sep = separation_mach(pc, p_sep, gamma)
    return area_ratio_from_mach(m_sep, gamma)


def separated_verdict(Ae_At, A_sep_At):
    """True (separated) when Ae_At > A_sep_At, else False (attached)."""
    if Ae_At <= 1.0 or A_sep_At < 1.0:
        raise ValueError("area ratios must be >= 1 (throat)")
    return Ae_At > A_sep_At


def side_load_flag(separated, pc, pa, pe_design=None):
    """Side-load advisory for a nozzle at an ambient pressure.

    Separated nozzles carry a side-load risk during start/transient
    operation; nozzles at or below the separation station area ratio
    stay attached.
    """
    if pc <= 0 or pa <= 0:
        raise ValueError("pressures must be positive")
    if separated:
        return ("separated at this ambient pressure: side loads possible "
                "during start/transient operation")
    return "attached at this ambient pressure: no separation side-load flag"


# ===========================================================================
# injector-design leaf
# ===========================================================================

def orifice_area(diameter_m):
    """Round orifice area pi*d^2/4, m2."""
    if diameter_m <= 0:
        raise ValueError("diameter_m must be positive")
    return math.pi * diameter_m * diameter_m / 4.0


def injection_velocity(discharge_coefficient, pressure_drop_pa, density):
    """Injection velocity Cd*sqrt(2*dP/rho), m/s."""
    if discharge_coefficient <= 0 or pressure_drop_pa <= 0 or density <= 0:
        raise ValueError("Cd, dP and density must be positive")
    return discharge_coefficient * math.sqrt(2.0 * pressure_drop_pa / density)


def momentum_flux_ratio(oxidizer_density, oxidizer_velocity, fuel_density,
                        fuel_velocity):
    """Momentum flux ratio J = (rho_o*v_o^2)/(rho_f*v_f^2)."""
    if oxidizer_density <= 0 or fuel_density <= 0:
        raise ValueError("densities must be positive")
    if oxidizer_velocity <= 0 or fuel_velocity <= 0:
        raise ValueError("velocities must be positive")
    return (oxidizer_density * oxidizer_velocity * oxidizer_velocity
            / (fuel_density * fuel_velocity * fuel_velocity))


def orifice_count(total_mass_flow_kgs, per_orifice_mass_flow_kgs):
    """Orifice count: ceil(total / per_orifice)."""
    if per_orifice_mass_flow_kgs <= 0:
        raise ValueError("per_orifice_mass_flow_kgs must be positive")
    if total_mass_flow_kgs < 0:
        raise ValueError("total_mass_flow_kgs must be non-negative")
    return int(math.ceil(total_mass_flow_kgs / per_orifice_mass_flow_kgs))


def injector_layout_summary(chamber_mass_flow_kgs, mixture_ratio_of,
                            fuel_density, oxidizer_density,
                            fuel_pressure_drop_pa, oxidizer_pressure_drop_pa,
                            discharge_coefficient, fuel_orifice_diam,
                            oxidizer_orifice_diam, fuel_orifices_per_element,
                            oxidizer_orifices_per_element):
    """Full injector face summary for a chamber operating point. Dict."""
    if chamber_mass_flow_kgs <= 0 or mixture_ratio_of <= 0:
        raise ValueError("chamber flow and mixture ratio must be positive")
    if discharge_coefficient <= 0:
        raise ValueError("discharge coefficient must be positive")
    if fuel_orifice_diam <= 0 or oxidizer_orifice_diam <= 0:
        raise ValueError("orifice diameters must be positive")
    if fuel_orifices_per_element < 1 or oxidizer_orifices_per_element < 1:
        raise ValueError("orifice counts per element must be at least 1")

    fuel_mdot = chamber_mass_flow_kgs / (1.0 + mixture_ratio_of)
    ox_mdot = chamber_mass_flow_kgs - fuel_mdot
    f_area = orifice_area(fuel_orifice_diam)
    o_area = orifice_area(oxidizer_orifice_diam)
    f_vel = injection_velocity(discharge_coefficient, fuel_pressure_drop_pa,
                               fuel_density)
    o_vel = injection_velocity(discharge_coefficient,
                               oxidizer_pressure_drop_pa, oxidizer_density)
    f_per = fuel_density * f_area * f_vel
    o_per = oxidizer_density * o_area * o_vel
    n_f = orifice_count(fuel_mdot, f_per)
    n_o = orifice_count(ox_mdot, o_per)
    n_el = max(int(math.ceil(n_f / fuel_orifices_per_element)),
               int(math.ceil(n_o / oxidizer_orifices_per_element)))
    return {
        "fuel_mass_flow_kgs": fuel_mdot, "oxidizer_mass_flow_kgs": ox_mdot,
        "fuel_area_m2": f_area, "oxidizer_area_m2": o_area,
        "fuel_injection_velocity_m_s": f_vel,
        "oxidizer_injection_velocity_m_s": o_vel,
        "fuel_per_orifice_mass_flow_kgs": f_per,
        "oxidizer_per_orifice_mass_flow_kgs": o_per,
        "momentum_flux_ratio": momentum_flux_ratio(
            oxidizer_density, o_vel, fuel_density, f_vel),
        "fuel_orifice_count": n_f, "oxidizer_orifice_count": n_o,
        "element_count": n_el,
        "per_element_fuel_kgs": fuel_orifices_per_element * f_per,
        "per_element_oxidizer_kgs": oxidizer_orifices_per_element * o_per,
        "per_element_total_kgs": (fuel_orifices_per_element * f_per
                                  + oxidizer_orifices_per_element * o_per),
    }


# ===========================================================================
# propellant-selection leaf
# ===========================================================================

def density_impulse(isp_s, bulk_density_kg_m3):
    """Density impulse Isp * bulk density, kg s/m3."""
    if isp_s <= 0 or bulk_density_kg_m3 <= 0:
        raise ValueError("isp and bulk density must be positive")
    return isp_s * bulk_density_kg_m3


def bulk_density(mixture_ratio, rho_fuel_kg_m3, rho_oxidizer_kg_m3):
    """Bulk density of the propellant mixture at an O/F ratio, kg/m3."""
    if mixture_ratio < 0:
        raise ValueError("mixture ratio must be >= 0")
    if rho_fuel_kg_m3 <= 0 or rho_oxidizer_kg_m3 <= 0:
        raise ValueError("densities must be positive")
    return ((1.0 + mixture_ratio) * rho_fuel_kg_m3 * rho_oxidizer_kg_m3
            / (rho_oxidizer_kg_m3 + mixture_ratio * rho_fuel_kg_m3))


def required_mass_fraction(delta_v, isp_s, g0=G0):
    """Propellant mass fraction for a delta-v: 1 - exp(-dv/(g0*Isp))."""
    if delta_v < 0 or isp_s <= 0:
        raise ValueError("delta-v must be >= 0 and isp positive")
    return 1.0 - math.exp(-delta_v / (g0 * isp_s))


def propellant_family(name):
    """Propellant family for a propellant name (or the name itself)."""
    key = name.strip().lower()
    return FAMILY_BY_NAME.get(key, key)


def propellant_verdict(propellant_class, mission):
    """Screening verdict suitable/caveat/unsuitable for class + mission."""
    fam = propellant_family(propellant_class)
    return FAMILY_VERDICT.get(fam, {}).get(mission, "caveat")


# ===========================================================================
# cold-gas-thruster leaf
# ===========================================================================

def _cf_const(gamma, gas_const):
    return math.sqrt(gamma / gas_const
                     * (2.0 / (gamma + 1.0))
                     ** ((gamma + 1.0) / (gamma - 1.0)))


def choked_mass_flow(pressure, temperature, throat_area,
                     gamma=GAMMA_N2, gas_const=R_N2):
    """Choked mass flow through a cold-gas thruster throat, kg/s."""
    if pressure <= 0 or temperature <= 0 or throat_area <= 0:
        raise ValueError("pressure, temperature and area must be positive")
    return (pressure * throat_area / math.sqrt(temperature)
            * _cf_const(gamma, gas_const))


def cold_gas_thrust(mass_flow_, isp):
    """Thrust F = mass_flow * isp * g0, N."""
    if mass_flow_ < 0 or isp <= 0:
        raise ValueError("mass flow non-negative and isp positive")
    return mass_flow_ * isp * G0


def tank_gas_mass(pressure, volume, temperature, gas_const=R_N2):
    """Gas mass in the plenum tank (ideal gas), kg."""
    if pressure <= 0 or volume <= 0 or temperature <= 0:
        raise ValueError("pressure, volume and temperature must be positive")
    return pressure * volume / (gas_const * temperature)


def blowdown_time_constant(tank_mass_kg, mass_flow0):
    """Isothermal blowdown time constant tau = m / mdot0, s."""
    if tank_mass_kg <= 0 or mass_flow0 <= 0:
        raise ValueError("tank mass and initial flow must be positive")
    return tank_mass_kg / mass_flow0


def pressure_at_time(p0, t, tau):
    """Plenum pressure under isothermal blowdown p0*exp(-t/tau), Pa."""
    if tau <= 0 or t < 0:
        raise ValueError("tau positive, time non-negative")
    return p0 * math.exp(-t / tau)


def operating_time(p0, p_min, tau):
    """Operating time to the minimum usable pressure, s."""
    if p0 <= 0 or p_min <= 0:
        raise ValueError("pressures must be positive")
    if p_min >= p0:
        raise ValueError("p_min must be below p0")
    return tau * math.log(p0 / p_min)


def cold_gas_total_impulse(isp, tank_mass0, tank_mass_final):
    """Total impulse over the blowdown, N s."""
    if isp <= 0 or tank_mass_final > tank_mass0:
        raise ValueError("isp positive; final mass <= initial mass")
    return isp * G0 * (tank_mass0 - tank_mass_final)


# ===========================================================================
# hybrid-rocket-motor leaf
# ===========================================================================

def fuel_properties(fuel):
    """Reference-only property dict for a named hybrid fuel pair."""
    try:
        props = HYBRID_FUELS[fuel]
    except (KeyError, TypeError):
        raise ValueError("unknown fuel: %s; known fuels: %s"
                         % (fuel, ", ".join(sorted(HYBRID_FUELS))))
    if not 0.0 < props["n"] < 1.0:
        raise ValueError("regression exponent n must lie in (0, 1)")
    if not math.isfinite(props["a"]) or props["a"] <= 0.0:
        raise ValueError("regression coefficient a must be positive")
    return props


def regression_rate(g_o, fuel):
    """Hybrid regression rate r = a * G_o^n at the reference length, m/s."""
    _require_finite(g_o)
    if g_o <= 0.0:
        raise ValueError("oxidizer mass flux must be positive")
    props = fuel_properties(fuel)
    return props["a"] * g_o ** props["n"]


def regression_rate_at_length(g_o, fuel, length):
    """Hybrid regression rate scaled to an actual grain length, m/s."""
    _require_finite(length)
    if length <= 0.0:
        raise ValueError("grain length must be positive")
    props = fuel_properties(fuel)
    return regression_rate(g_o, fuel) * (length / props["L_ref"]) ** props["m"]


def oxidizer_mass_flux(m_dot_o, port_area):
    """Oxidizer mass flux through the port G_o = mdot_o / A_port,
    kg/(m2 s)."""
    _require_finite(m_dot_o, port_area)
    if m_dot_o <= 0.0 or port_area <= 0.0:
        raise ValueError("oxidizer flow and port area must be positive")
    return m_dot_o / port_area


def port_area_circular(radius):
    """Circular port area pi*r^2, m2."""
    if radius <= 0:
        raise ValueError("radius must be positive")
    return math.pi * radius * radius


def fuel_mass_flow(rho_f, r_dot, burn_area):
    """Fuel mass flow rho_f * r_dot * A_b, kg/s."""
    if rho_f <= 0 or r_dot <= 0 or burn_area <= 0:
        raise ValueError("density, regression rate and burn area must be "
                         "positive")
    return rho_f * r_dot * burn_area


def of_ratio(m_dot_o, m_dot_f):
    """O/F mixture ratio of the motor."""
    if m_dot_o <= 0 or m_dot_f <= 0:
        raise ValueError("mass flows must be positive")
    return m_dot_o / m_dot_f


def hybrid_chamber_pressure(m_dot, c_star, area_throat):
    """Chamber pressure p_c = m_dot * c* / A_t, Pa."""
    if m_dot <= 0 or c_star <= 0 or area_throat <= 0:
        raise ValueError("flow, c-star and throat area must be positive")
    return m_dot * c_star / area_throat


def hybrid_thrust(thrust_coeff, p_c, area_throat):
    """Thrust F = Cf * p_c * A_t, N."""
    if thrust_coeff <= 0 or p_c <= 0 or area_throat <= 0:
        raise ValueError("Cf, p_c and throat area must be positive")
    return thrust_coeff * p_c * area_throat


# ===========================================================================
# thrust-vector-control leaf
# ===========================================================================

def side_force(thrust, deflection_rad):
    """Lateral control force F_side = T * sin(delta), N."""
    if thrust < 0:
        raise ValueError("thrust must be >= 0")
    if not (-math.pi / 2.0 <= deflection_rad <= math.pi / 2.0):
        raise ValueError("deflection must be within +/-90 deg")
    return thrust * math.sin(deflection_rad)


def control_torque(thrust, deflection_rad, moment_arm):
    """Control torque about the vehicle CG, N m."""
    if thrust < 0 or moment_arm < 0:
        raise ValueError("thrust and moment arm must be non-negative")
    if not (-math.pi / 2.0 <= deflection_rad <= math.pi / 2.0):
        raise ValueError("deflection must be within +/-90 deg")
    return thrust * math.sin(deflection_rad) * moment_arm


def axial_thrust_ratio(deflection_rad):
    """Fraction of thrust retained along the axis, cos(delta)."""
    if not (-math.pi / 2.0 <= deflection_rad <= math.pi / 2.0):
        raise ValueError("deflection must be within +/-90 deg")
    return math.cos(deflection_rad)


def deflection_angle_for_side_force(side_force_required, thrust):
    """Gimbal deflection (rad) producing the required side force."""
    if thrust <= 0:
        raise ValueError("thrust must be > 0 to deflect")
    ratio = side_force_required / thrust
    if abs(ratio) > 1.0:
        raise ValueError("side force exceeds the thrust; cannot be met by "
                         "deflection")
    return math.asin(ratio)


def actuator_authority_required(required_torque, moment_arm):
    """Side force the TVC actuator must deliver, N: F = M / L."""
    if required_torque < 0 or moment_arm <= 0:
        raise ValueError("torque non-negative and moment arm positive")
    return required_torque / moment_arm


# ===========================================================================
# Project facts + report builder
# ===========================================================================

@dataclass
class RocketProgram:
    """Project facts the role needs to build the design report.

    Reference-typical values are labeled as such in the report; every
    number in the deliverable is computed from these stated inputs.
    """
    program_name: str = "Meridian-9 medium launch vehicle"
    item_name: str = "Meridian-9 two-stage liquid propulsion system"
    description: str = ("Two-stage LOX/RP-1 + LOX/LH2 launch vehicle "
                        "delivering 5000 kg to low Earth orbit.")
    payload_kg: float = 5000.0
    orbit_net_dv_ms: float = 7800.0      # net insertion delta-v target, m/s
    ideal_dv_budget_ms: float = 9600.0   # total ideal budget incl. losses
    booster_dv_ms: float = 5700.0        # stage-1 ideal delta-v share
    upper_dv_ms: float = 3900.0          # stage-2 ideal delta-v share
    booster_pair: str = "LOX/RP-1"
    booster_cycle: str = "gas-generator"
    booster_pc_pa: float = 10.0e6        # chamber pressure, Pa
    booster_thrust_n: float = 4105.0e3   # nominal vacuum thrust, N
    booster_eps: float = 0.10            # structural index
    booster_area_ratio: float = 16.0     # exit/throat area ratio
    booster_lstar_m: float = 1.0         # characteristic chamber length
    booster_contraction: float = 3.5     # chamber contraction ratio Ac/At
    booster_cstar_efficiency: float = 0.985
    booster_mean_path_angle_deg: float = 45.0
    booster_drag_loss_ms: float = 150.0
    upper_pair: str = "LOX/LH2"
    upper_cycle: str = "staged-combustion"
    upper_pc_pa: float = 12.0e6
    upper_thrust_n: float = 300.0e3
    upper_eps: float = 0.10
    # injector facts (booster)
    injector_cd: float = 0.80
    injector_ox_drop_pa: float = 4.0e6
    injector_fuel_drop_pa: float = 4.0e6
    injector_ox_diam_m: float = 0.0022
    injector_fuel_diam_m: float = 0.0024
    injector_ox_per_element: int = 2
    injector_fuel_per_element: int = 1
    # TVC facts (booster)
    tvc_deflection_deg: float = 5.0
    tvc_moment_arm_m: float = 3.0
    # cooling facts (booster throat; reference channel geometry)
    coolant_mass_flux: float = 12000.0   # kg/(m2 s), reference channel flow
    channel_dh_m: float = 0.002          # coolant channel hydraulic diameter
    # solid / hybrid screening facts
    solid_isp: float = SOLID_ISP
    solid_kn: float = 500.0              # burn-area / throat-area ratio
    hybrid_fuel: str = "HTPB-N2O"
    hybrid_grain_length_m: float = 1.8
    hybrid_port_radius_m: float = 0.25
    # cold-gas RCS facts (upper stage)
    rcs_pressure_pa: float = 25.0e6
    rcs_volume_m3: float = 0.12
    rcs_temperature_k: float = 300.0
    rcs_throat_diam_m: float = 0.0010
    rcs_isp: float = 60.0
    rcs_p_min_pa: float = 1.0e6
    rcs_t_query_s: float = 600.0
    certification_basis: str = ("ECSS space-systems standards "
                                "(reference-only)")


def _pair_props(pair: str):
    """Full propellant property record: densities, r_m, isp, gas props."""
    rho_ox, rho_fuel, r_m, isp_vac = propellant_pair_properties(pair)
    gas = GAS_PROPS[pair]
    return {"pair": pair, "rho_ox": rho_ox, "rho_fuel": rho_fuel,
            "r_m": r_m, "isp_vac": isp_vac, "tc_k": gas["tc_k"],
            "mw_kg_kmol": gas["mw_kg_kmol"], "gamma": gas["gamma"],
            "r_gas": R_UNIV / gas["mw_kg_kmol"]}


def _stage_model(dv_ms, pair_props, eps, payload_kg, role_label):
    """Stage sizing model for one stage."""
    budget = stage_mass_budget(dv_ms, pair_props["isp_vac"], eps, payload_kg)
    bulk = mixture_bulk_density(pair_props["rho_ox"], pair_props["rho_fuel"],
                                pair_props["r_m"])
    return {"role": role_label, "pair": pair_props["pair"],
            "isp_vac_s": pair_props["isp_vac"], "eps": eps,
            "dv_ms": dv_ms, "mass_ratio": budget["r"],
            "payload_fraction": budget["lam"],
            "m0_kg": budget["m0_kg"], "m_prop_kg": budget["m_prop_kg"],
            "m_inert_kg": budget["m_inert_kg"],
            "m_burnout_kg": budget["m_burnout_kg"],
            "bulk_density_kg_m3": bulk,
            "propellant_volume_m3": budget["m_prop_kg"] / bulk}


def build_report(item: RocketProgram) -> dict:
    """Build the complete Rocket Propulsion System Design Report model."""
    booster_props = _pair_props(item.booster_pair)
    upper_props = _pair_props(item.upper_pair)
    n2o4_props = _pair_props("N2O4/MMH")

    def di_row(props):
        bulk = mixture_bulk_density(props["rho_ox"], props["rho_fuel"],
                                    props["r_m"])
        return {"pair": props["pair"], "isp_vac": props["isp_vac"],
                "bulk_density_kg_m3": bulk,
                "density_impulse": density_impulse(props["isp_vac"], bulk)}

    # ---- staging / sizing ----------------------------------------------
    bench = optimal_equal_stage_split(item.ideal_dv_budget_ms, 2, 300.0, 0.1)
    n_stage_req, lam_req = stage_count_for_delta_v(
        item.ideal_dv_budget_ms, 300.0, 0.1, 0.010)
    upper = _stage_model(item.upper_dv_ms, upper_props, item.upper_eps,
                         item.payload_kg, "upper")
    booster = _stage_model(item.booster_dv_ms, booster_props, item.booster_eps,
                           upper["m0_kg"], "booster")

    # ---- booster engine operating point + ascent ------------------------
    # Nominal engine: mdot = F/(Isp*g0). Burn time from stage propellant.
    isp_vac_boost = booster_props["isp_vac"]
    mdot_eng = item.booster_thrust_n / (isp_vac_boost * G0)
    t_b = burn_time(booster["m_prop_kg"], mdot_eng)

    cycle = engine_cycle_analysis(item.booster_cycle, item.booster_thrust_n,
                                  item.booster_pc_pa, item.booster_pair,
                                  burn_time=t_b)
    pf = engine_cycle_analysis("pressure-fed", item.booster_thrust_n,
                               min(item.booster_pc_pa, 3.0e6),
                               item.booster_pair, burn_time=t_b)

    # Ascent accounting: gravity loss from the pitched model; the vehicle
    # effective total = ideal budget - booster losses.
    grav = gravity_loss_pitched(t_b, item.booster_mean_path_angle_deg)
    drag = item.booster_drag_loss_ms
    booster_eff = effective_delta_v(item.booster_dv_ms, grav, drag)
    required_total_ideal = required_ideal_delta_v(item.orbit_net_dv_ms, grav,
                                                  drag)
    effective_total = item.ideal_dv_budget_ms - grav - drag
    ascent = {
        "burn_time_s": t_b, "mass_flow_kg_s": mdot_eng,
        "thrust_to_weight": 0.0, "gravity_loss_ms": grav,
        "drag_loss_ms": drag, "booster_effective_ms": booster_eff,
        "effective_total_ms": effective_total,
        "required_total_ideal_ms": required_total_ideal,
        "margin_ms": item.ideal_dv_budget_ms - required_total_ideal,
        "mean_path_angle_deg": item.booster_mean_path_angle_deg,
        "liftoff_thrust_n": item.booster_thrust_n,
    }
    # Liftoff TWR is recomputed after the nozzle section once the nominal
    # sea-level thrust (with the ambient pressure term) is known.

    # ---- booster chamber + nozzle ---------------------------------------
    tc = booster_props["tc_k"]
    gamma = booster_props["gamma"]
    mw = booster_props["mw_kg_kmol"]
    r_gas = booster_props["r_gas"]
    cstar_theo = theoretical_cstar(tc, mw, gamma)
    cstar_del = item.booster_cstar_efficiency * cstar_theo
    at = throat_area_from_flow(mdot_eng, cstar_del, item.booster_pc_pa)
    dt = 2.0 * nozzle_throat_radius(at)
    ac = item.booster_contraction * at
    dc = 2.0 * math.sqrt(ac / math.pi)
    vc = chamber_volume(item.booster_lstar_m, at)
    chamber = {"cstar_theoretical_ms": cstar_theo,
               "cstar_delivered_ms": cstar_del,
               "cstar_efficiency": item.booster_cstar_efficiency,
               "throat_area_m2": at, "throat_diameter_m": dt,
               "chamber_area_m2": ac, "chamber_diameter_m": dc,
               "contraction_ratio": item.booster_contraction,
               "chamber_volume_m3": vc, "lstar_m": item.booster_lstar_m,
               "chamber_temp_k": tc, "molecular_weight": mw, "gamma": gamma}

    me = exit_mach_from_area_ratio(item.booster_area_ratio, gamma)
    pe = exit_static_pressure(item.booster_pc_pa, me, gamma)
    ae = item.booster_area_ratio * at
    ve = exit_velocity(item.booster_pc_pa, tc, pe, gamma, r_gas)
    pa_sl = ISA_SEA_LEVEL_PRESSURE
    # Ideal vacuum thrust (ambient -> 0): F = mdot*ve + pe*Ae.
    f_ideal_vac = mdot_eng * ve + pe * ae
    f_ideal_sl = ideal_thrust(mdot_eng, ve, pe, pa_sl, ae)
    eff_nozzle = item.booster_thrust_n / f_ideal_vac
    f_nom_sl = mdot_eng * ve * eff_nozzle + (pe - pa_sl) * ae
    exp_sl = optimum_expansion(item.booster_pc_pa, pe, pa_sl)
    a_sep = separation_station_area_ratio(item.booster_pc_pa, pa_sl, gamma)
    separated = separated_verdict(item.booster_area_ratio, a_sep)
    nozzle = {
        "area_ratio": item.booster_area_ratio, "exit_mach": me,
        "exit_pressure_pa": pe, "exit_area_m2": ae,
        "exit_velocity_ms": ve, "chamber_gas_r": r_gas,
        "ideal_thrust_vac_n": f_ideal_vac, "ideal_thrust_sl_n": f_ideal_sl,
        "nominal_thrust_vac_n": item.booster_thrust_n,
        "nominal_thrust_sl_n": f_nom_sl,
        "nozzle_efficiency": eff_nozzle,
        "expansion_sea_level": exp_sl,
        "nominal_isp_vac_s": isp_vac_boost,
        "nominal_isp_sl_s": f_nom_sl / (mdot_eng * G0),
        "separation_station_area_ratio": a_sep,
        "separated_at_ignition": separated,
        "side_load_verdict": side_load_flag(separated, item.booster_pc_pa,
                                            pa_sl, pe_design=pe),
    }
    # liftoff TWR uses the nominal sea-level thrust
    twr = thrust_to_weight(f_nom_sl, booster["m0_kg"])
    ascent["thrust_to_weight"] = twr
    ascent["liftoff_thrust_n"] = f_nom_sl

    # ---- booster throat cooling ------------------------------------------
    cool = chamber_cooling_summary(
        item.booster_pc_pa, cstar_del, tc, gamma, dt,
        item.coolant_mass_flux, hydraulic_diameter_m=item.channel_dh_m)

    # ---- injector + TVC ---------------------------------------------------
    inj = injector_layout_summary(
        mdot_eng, booster_props["r_m"], booster_props["rho_fuel"],
        booster_props["rho_ox"], item.injector_fuel_drop_pa,
        item.injector_ox_drop_pa, item.injector_cd,
        item.injector_fuel_diam_m, item.injector_ox_diam_m,
        item.injector_fuel_per_element, item.injector_ox_per_element)
    delta_rad = math.radians(item.tvc_deflection_deg)
    tvc_moment = control_torque(item.booster_thrust_n, delta_rad,
                                item.tvc_moment_arm_m)
    tvc = {
        "deflection_deg": item.tvc_deflection_deg,
        "side_force_n": side_force(item.booster_thrust_n, delta_rad),
        "control_torque_nm": tvc_moment,
        "axial_ratio": axial_thrust_ratio(delta_rad),
        "actuator_authority_n": actuator_authority_required(
            tvc_moment, item.tvc_moment_arm_m),
        "moment_arm_m": item.tvc_moment_arm_m,
    }

    # ---- upper stage cycle ------------------------------------------------
    upper_burn_s = 360.0
    upper_cycle = engine_cycle_analysis(item.upper_cycle, item.upper_thrust_n,
                                        item.upper_pc_pa, item.upper_pair,
                                        burn_time=upper_burn_s)

    # ---- alternate booster concept: solid (same duty) ---------------------
    mdot_solid_duty = item.booster_thrust_n / (item.solid_isp * G0)
    at_solid = mdot_solid_duty * SOLID_CSTAR / 7.0e6   # nominal 7 MPa sizing
    ab_solid = item.solid_kn * at_solid
    pc_solid = equilibrium_chamber_pressure(SOLID_RHO_P, SOLID_A, SOLID_N,
                                            ab_solid, at_solid, SOLID_CSTAR)
    rate_solid = burn_rate(pc_solid, SOLID_A, SOLID_N)
    mdot_solid = solid_mass_flow(pc_solid, at_solid, SOLID_CSTAR)
    mdot_solid_burn = burn_mass_flow(SOLID_RHO_P, ab_solid, rate_solid)
    f_solid = thrust_from_isp(item.solid_isp, mdot_solid)
    solid = {
        "burn_rate_coeff": SOLID_A, "pressure_exponent": SOLID_N,
        "rho_p": SOLID_RHO_P, "cstar": SOLID_CSTAR, "isp": item.solid_isp,
        "kn": item.solid_kn, "throat_area_m2": at_solid,
        "burn_area_m2": ab_solid, "chamber_pressure_pa": pc_solid,
        "burn_rate_ms": rate_solid, "mass_flow_kg_s": mdot_solid,
        "generated_mass_flow_kg_s": mdot_solid_burn,
        "thrust_n": f_solid, "propellant_mass_kg": mdot_solid * t_b,
        "web_m": rate_solid * t_b,
        "total_impulse_ns": total_impulse(f_solid, t_b),
        "burn_area_verdict": burn_area_verdict(ab_solid, ab_solid),
        "balance_closed": abs(mdot_solid - mdot_solid_burn) / mdot_solid
        < 1e-3,
    }

    # ---- alternate upper concept: hybrid (same burn duty) -----------------
    mdot_upper_eng = item.upper_thrust_n / (upper_props["isp_vac"] * G0)
    mdot_o_h = 0.60 * mdot_upper_eng
    port_area = port_area_circular(item.hybrid_port_radius_m)
    g_o = oxidizer_mass_flux(mdot_o_h, port_area)
    props_h = fuel_properties(item.hybrid_fuel)
    rdot_h = regression_rate_at_length(g_o, item.hybrid_fuel,
                                       item.hybrid_grain_length_m)
    burn_area_h = (2.0 * math.pi * item.hybrid_port_radius_m
                   * item.hybrid_grain_length_m)
    mdot_f_h = fuel_mass_flow(props_h["rho_f"], rdot_h, burn_area_h)
    of_h = of_ratio(mdot_o_h, mdot_f_h)
    at_h = (mdot_o_h + mdot_f_h) * props_h["c_star"] / 5.0e6
    pc_h = hybrid_chamber_pressure(mdot_o_h + mdot_f_h, props_h["c_star"],
                                   at_h)
    hybrid = {
        "fuel": item.hybrid_fuel, "oxidizer_mass_flow_kg_s": mdot_o_h,
        "oxidizer_mass_flux_kg_m2s": g_o,
        "port_radius_m": item.hybrid_port_radius_m,
        "grain_length_m": item.hybrid_grain_length_m,
        "burn_area_m2": burn_area_h,
        "regression_rate_mm_s": rdot_h * 1000.0,
        "fuel_mass_flow_kg_s": mdot_f_h, "of_ratio": of_h,
        "chamber_pressure_pa": pc_h,
        "thrust_n": hybrid_thrust(1.4, pc_h, at_h),
    }

    # ---- cold-gas RCS (upper stage) ----------------------------------------
    rcs_at = throat_area(item.rcs_throat_diam_m)
    rcs_mdot0 = choked_mass_flow(item.rcs_pressure_pa, item.rcs_temperature_k,
                                 rcs_at)
    rcs_F = cold_gas_thrust(rcs_mdot0, item.rcs_isp)
    rcs_m_tank = tank_gas_mass(item.rcs_pressure_pa, item.rcs_volume_m3,
                               item.rcs_temperature_k)
    rcs_tau = blowdown_time_constant(rcs_m_tank, rcs_mdot0)
    rcs_m_final = tank_gas_mass(item.rcs_p_min_pa, item.rcs_volume_m3,
                                item.rcs_temperature_k)
    rcs = {
        "pressure_pa": item.rcs_pressure_pa,
        "temperature_k": item.rcs_temperature_k,
        "throat_diameter_m": item.rcs_throat_diam_m,
        "throat_area_m2": rcs_at, "mass_flow0_kg_s": rcs_mdot0,
        "thrust_n": rcs_F, "tank_mass_kg": rcs_m_tank,
        "time_constant_s": rcs_tau,
        "pressure_at_600s_pa": pressure_at_time(item.rcs_pressure_pa,
                                                item.rcs_t_query_s, rcs_tau),
        "operating_time_s": operating_time(item.rcs_pressure_pa,
                                           item.rcs_p_min_pa, rcs_tau),
        "total_impulse_ns": cold_gas_total_impulse(item.rcs_isp, rcs_m_tank,
                                                   rcs_m_final),
        "p_min_pa": item.rcs_p_min_pa, "isp_s": item.rcs_isp,
    }

    staging_bench = {
        "dv_stage_ms": item.ideal_dv_budget_ms / 2.0,
        "r_star": bench[0], "lam_stage": bench[1], "lam_total": bench[2],
        "n_stage_req": n_stage_req, "lam_total_req": lam_req,
        "upper_payload_kg": upper["m0_kg"],
    }

    return {
        "document_type": "Rocket Propulsion System Design Report",
        "status": "draft-for-review",
        "item": item.item_name,
        "program": item.program_name,
        "item_description": item.description,
        "certification_basis": item.certification_basis,
        "generated": _today(),
        "inputs": {
            "payload_kg": item.payload_kg,
            "orbit_net_dv_ms": item.orbit_net_dv_ms,
            "ideal_dv_budget_ms": item.ideal_dv_budget_ms,
            "booster_pc_pa": item.booster_pc_pa,
            "upper_pc_pa": item.upper_pc_pa,
            "booster_thrust_n": item.booster_thrust_n,
            "upper_thrust_n": item.upper_thrust_n,
            "upper_burn_time_s": upper_burn_s,
            "wall_limit_k": WALL_LIMIT_K,
            "coolant_mass_flux_ref": item.coolant_mass_flux,
            "channel_dh_m": item.channel_dh_m,
            "mean_path_angle_deg": item.booster_mean_path_angle_deg,
            "solid_kn": item.solid_kn,
        },
        "propellant_screening": {
            "rows": [di_row(booster_props), di_row(upper_props),
                     di_row(n2o4_props)],
            "booster_pair": item.booster_pair,
            "upper_pair": item.upper_pair,
            "lox_family": propellant_family("lox"),
            "rp1_family": propellant_family("rp-1"),
            "booster_verdict": propellant_verdict("lox", "booster"),
            "upper_verdict": propellant_verdict("lox", "upper-stage"),
        },
        "staging": {
            "benchmark": staging_bench,
            "booster": booster, "upper": upper,
        },
        "ascent": ascent,
        "booster_cycle": cycle,
        "pressure_fed_trade": pf,
        "chamber": chamber,
        "nozzle": nozzle,
        "cooling": cool,
        "injector": inj,
        "tvc": tvc,
        "upper_cycle": upper_cycle,
        "solid": solid,
        "hybrid": hybrid,
        "rcs": rcs,
        "performance": {
            "payload_kg": item.payload_kg,
            "liftoff_mass_kg": booster["m0_kg"],
            "total_ideal_dv_ms": item.ideal_dv_budget_ms,
            "orbit_net_dv_ms": item.orbit_net_dv_ms,
            "booster_mass_ratio": booster["mass_ratio"],
            "upper_mass_ratio": upper["mass_ratio"],
            "upper_stage_m0_kg": upper["m0_kg"],
            "booster_total_impulse_ns": total_impulse(
                item.booster_thrust_n, t_b),
            "upper_total_impulse_ns": total_impulse(item.upper_thrust_n,
                                                    upper_burn_s),
            "booster_mdot_kg_s": mdot_eng,
            "upper_mdot_kg_s": mdot_upper_eng,
        },
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _fmt(x, spec=".6g"):
    if x is None:
        return "TBD"
    if isinstance(x, float):
        return format(x, spec)
    return str(x)


def _mpa(p):
    return "%.2f MPa" % (p / 1.0e6)


def _kn(n):
    return "%.0f kN" % (n / 1.0e3)


def render_report_markdown(model: dict) -> str:
    """Render the report content model as the deliverable markdown."""
    i = model["inputs"]
    ps = model["propellant_screening"]
    st = model["staging"]
    asc = model["ascent"]
    cyc = model["booster_cycle"]
    pf = model["pressure_fed_trade"]
    ch = model["chamber"]
    nz = model["nozzle"]
    cool = model["cooling"]
    inj = model["injector"]
    tvc = model["tvc"]
    ucyc = model["upper_cycle"]
    sol = model["solid"]
    hyb = model["hybrid"]
    rcs = model["rcs"]
    perf = model["performance"]
    boost = st["booster"]
    upper = st["upper"]
    bench = st["benchmark"]

    lines = [
        "# Rocket Propulsion System Design Report",
        "",
        f"**Item:** {model['item']}",
        f"**Program:** {model['program']}",
        f"**Certification basis:** {model['certification_basis']}",
        f"**Status:** {model['status']}",
        "",
        "## 1. Mission requirements",
        "",
        model["item_description"],
        f"- Payload to low Earth orbit: {_fmt(i['payload_kg'], '.0f')} kg.",
        f"- Net orbit-insertion delta-v target: "
        f"{_fmt(i['orbit_net_dv_ms'], '.0f')} m/s.",
        f"- Total ideal delta-v budget (incl. first-stage ascent losses): "
        f"{_fmt(i['ideal_dv_budget_ms'], '.0f')} m/s.",
        "",
        "## 2. Propellant screening",
        "",
        "Reference-typical density impulse (Isp x bulk density, kg s/m3) "
        "ranks the candidate pairs on tank volume:",
        "",
        "| Pair | Isp vac (s) | Bulk density (kg/m3) | Density impulse (kg s/m3) |",
        "|---|---|---|---|",
    ]
    for r in ps["rows"]:
        lines.append(f"| {r['pair']} | {r['isp_vac']:.0f} | "
                     f"{r['bulk_density_kg_m3']:.0f} | "
                     f"{r['density_impulse']:.0f} |")
    lines += [
        "",
        f"- LOX family on a booster mission: **{ps['booster_verdict']}**; "
        f"LOX family on upper-stage duty: **{ps['upper_verdict']}**.",
        f"- RP-1 (kerosene) family: **{ps['rp1_family']}** - dense, "
        "storable at ambient temperature.",
        f"- Selection: {cyc['propellant']} booster + {ucyc['propellant']} "
        "upper stage (detailed in sections 5, 6, 10).",
        "",
        "## 3. Staging and sizing",
        "",
        f"The ideal budget {_fmt(i['ideal_dv_budget_ms'], '.0f')} m/s is "
        f"split {_fmt(boost['dv_ms'], '.0f')} m/s (booster) / "
        f"{_fmt(upper['dv_ms'], '.0f')} m/s (upper). Equal-stage "
        "benchmark (identical stages, Isp 300 s, structural index 0.10): "
        f"optimal per-stage mass ratio {bench['r_star']:.4f}, per-stage "
        f"payload fraction {bench['lam_stage']:.5f}, total payload "
        f"fraction {bench['lam_total']:.5f}; minimum identical-stage "
        f"count for a 1% total payload fraction: "
        f"{bench['n_stage_req']} stage(s).",
        "",
        "| Quantity | Booster (S1) | Upper (S2) |",
        "|---|---|---|",
        f"| Propellant pair | {boost['pair']} | {upper['pair']} |",
        f"| Vacuum Isp (s) | {boost['isp_vac_s']:.0f} | "
        f"{upper['isp_vac_s']:.0f} |",
        f"| Ideal delta-v (m/s) | {boost['dv_ms']:.0f} | "
        f"{upper['dv_ms']:.0f} |",
        f"| Stage mass ratio | {boost['mass_ratio']:.3f} | "
        f"{upper['mass_ratio']:.3f} |",
        f"| Payload fraction | {boost['payload_fraction']:.4f} | "
        f"{upper['payload_fraction']:.4f} |",
        f"| Stage initial mass (kg) | {boost['m0_kg']:.0f} | "
        f"{upper['m0_kg']:.0f} |",
        f"| Propellant mass (kg) | {boost['m_prop_kg']:.0f} | "
        f"{upper['m_prop_kg']:.0f} |",
        f"| Inert mass (kg) | {boost['m_inert_kg']:.0f} | "
        f"{upper['m_inert_kg']:.0f} |",
        f"| Structural index | {boost['eps']:.2f} | {upper['eps']:.2f} |",
        "",
        f"Upper-stage initial mass {upper['m0_kg']:.0f} kg (incl. the "
        f"{i['payload_kg']:.0f} kg payload) is the booster's payload; "
        f"booster initial (liftoff) mass is {boost['m0_kg']:.0f} kg.",
        "",
        "## 4. Powered-ascent gravity-loss accounting (booster)",
        "",
        f"- Engine burn time: {asc['burn_time_s']:.1f} s (propellant "
        f"{boost['m_prop_kg']:.0f} kg at {asc['mass_flow_kg_s']:.1f} "
        "kg/s).",
        f"- Liftoff thrust-to-weight: {asc['thrust_to_weight']:.2f} "
        f"(nominal sea-level thrust {_kn(asc['liftoff_thrust_n'])}).",
        f"- Gravity loss (pitched ascent, mean flight-path angle "
        f"{asc['mean_path_angle_deg']:.0f} deg): "
        f"{asc['gravity_loss_ms']:.1f} m/s.",
        f"- Drag loss (reference): {asc['drag_loss_ms']:.0f} m/s.",
        f"- Booster effective delta-v: {asc['booster_effective_ms']:.1f} "
        "m/s.",
        f"- Required total ideal delta-v for the "
        f"{_fmt(i['orbit_net_dv_ms'], '.0f')} m/s net target: "
        f"{asc['required_total_ideal_ms']:.1f} m/s; allocated "
        f"{_fmt(i['ideal_dv_budget_ms'], '.0f')} m/s "
        f"(margin {asc['margin_ms']:.1f} m/s).",
        "",
        "## 5. Booster engine feed cycle",
        "",
        f"Cycle: **{cyc['cycle']}** on {cyc['propellant']} at chamber "
        f"pressure {_mpa(i['booster_pc_pa'])}.",
        f"- Mass flow: {cyc['mdot']:.1f} kg/s total "
        f"({cyc['mdot_ox']:.1f} kg/s oxidizer, {cyc['mdot_f']:.1f} kg/s "
        "fuel).",
        f"- Pump discharge pressure: {_mpa(cyc['pump_discharge_pressure'])}; "
        f"pump power {cyc['pump_power_ox'] / 1e6:.2f} MW (ox) + "
        f"{cyc['pump_power_fuel'] / 1e6:.2f} MW (fuel) = "
        f"{cyc['pump_power_total'] / 1e6:.2f} MW.",
        f"- Turbine drive power: {cyc['turbine_power'] / 1e6:.2f} MW "
        f"(drive mass fraction {cyc['drive_mass_fraction'] * 100.0:.0f}%).",
        f"- Power balance: {cyc['power_balance'] / 1e6:.2f} MW "
        f"({'surplus' if cyc['power_balance'] >= 0 else 'deficit'}).",
        f"- Verdict: {cyc['verdict']}",
        "",
        f"Pressure-fed trade at the same thrust and burn time: tank mass "
        f"penalty {pf['tank_mass_penalty']:.0f} kg at tank pressure "
        f"{_mpa(pf['tank_pressure'])} - {pf['verdict']}.",
        "",
        "## 6. Booster thrust chamber design",
        "",
        f"- Theoretical c*: {ch['cstar_theoretical_ms']:.1f} m/s "
        f"(Tc {ch['chamber_temp_k']:.0f} K, Mw {ch['molecular_weight']:.0f} "
        f"kg/kmol, gamma {ch['gamma']:.2f}).",
        f"- Delivered c*: {ch['cstar_delivered_ms']:.1f} m/s "
        f"(efficiency {ch['cstar_efficiency']:.3f}).",
        f"- Throat area: {ch['throat_area_m2'] * 1e4:.1f} cm2 "
        f"(diameter {ch['throat_diameter_m'] * 1000.0:.0f} mm).",
        f"- Chamber area: {ch['chamber_area_m2'] * 1e4:.0f} cm2 "
        f"(diameter {ch['chamber_diameter_m']:.2f} m), contraction ratio "
        f"{ch['contraction_ratio']:.1f}.",
        f"- Chamber volume (L* = {ch['lstar_m']:.1f} m): "
        f"{ch['chamber_volume_m3']:.3f} m3.",
        "",
        "## 7. Booster nozzle design and flow separation",
        "",
        f"- Exit/throat area ratio: {nz['area_ratio']:.0f} "
        f"(exit Mach {nz['exit_mach']:.2f}).",
        f"- Exit static pressure: {nz['exit_pressure_pa'] / 1e3:.1f} kPa; "
        f"exit area {nz['exit_area_m2']:.2f} m2.",
        f"- Ideal exit velocity: {nz['exit_velocity_ms']:.0f} m/s.",
        f"- Ideal thrust: {_kn(nz['ideal_thrust_vac_n'])} vacuum / "
        f"{_kn(nz['ideal_thrust_sl_n'])} sea level; nominal design "
        f"{_kn(nz['nominal_thrust_vac_n'])} (nozzle efficiency "
        f"{nz['nozzle_efficiency']:.3f}).",
        f"- Nominal Isp: {nz['nominal_isp_vac_s']:.1f} s vacuum / "
        f"{nz['nominal_isp_sl_s']:.1f} s sea level.",
        f"- Expansion at sea level: **{nz['expansion_sea_level']}** "
        f"(exit pressure "
        f"{'below' if nz['expansion_sea_level'] == 'over' else 'above'} "
        "ambient).",
        f"- Flow-separation station area ratio at sea level: "
        f"{nz['separation_station_area_ratio']:.1f} vs design "
        f"{nz['area_ratio']:.0f} -> "
        f"{'SEPARATED' if nz['separated_at_ignition'] else 'attached'} "
        "at ignition.",
        f"- Side-load advisory: {nz['side_load_verdict']}",
        "",
        "## 8. Booster thrust-chamber cooling",
        "",
        "Throat thermal balance (Bartz hot-gas side, Dittus-Boelter "
        "coolant side, series copper wall):",
        f"- Recovery temperature: {cool['recovery_temp_k']:.1f} K "
        f"(throat static {cool['throat_static_temp_k']:.1f} K).",
        f"- Hot-gas coefficient h_g: {cool['h_g']:.0f} W/(m2 K); coolant "
        f"coefficient h_c: {cool['h_c']:.0f} W/(m2 K) "
        f"(Re {cool['reynolds']:.0f}, Nu {cool['nusselt']:.1f}).",
        f"- Heat flux: {cool['heat_flux_wm2'] / 1e6:.2f} MW/m2; hot wall "
        f"{cool['hot_wall_temp_k']:.0f} K, cold wall "
        f"{cool['cold_wall_temp_k']:.0f} K, wall drop "
        f"{cool['wall_delta_temp_k']:.1f} K.",
        f"- Copper wall limit {_fmt(i['wall_limit_k'], '.0f')} K: "
        f"film-cooling handoff "
        f"**{'REQUIRED' if cool['film_cooling_handoff'] else 'not required'}**.",
        f"- Coolant mass flux to hold the limit: "
        f"{cool['required_mass_flux']:.0f} kg/(m2 s) vs the "
        f"{_fmt(i['coolant_mass_flux_ref'], '.0f')} kg/(m2 s) reference "
        "channel flow.",
        "",
        "## 9. Injector and thrust-vector control",
        "",
        f"Injector (unlike-doublet elements): layout of "
        f"{inj['element_count']} elements, injection velocity "
        f"{inj['fuel_injection_velocity_m_s']:.1f} m/s (fuel) / "
        f"{inj['oxidizer_injection_velocity_m_s']:.1f} m/s (oxidizer), "
        f"momentum flux ratio {inj['momentum_flux_ratio']:.2f}, "
        f"{inj['fuel_orifice_count']} fuel orifices, "
        f"{inj['oxidizer_orifice_count']} oxidizer orifices.",
        "",
        f"TVC: gimbal deflection {tvc['deflection_deg']:.0f} deg at "
        f"{_kn(i['booster_thrust_n'])} nominal thrust gives side force "
        f"{_kn(tvc['side_force_n'])} and control torque "
        f"{tvc['control_torque_nm'] / 1e3:.0f} kN m (moment arm "
        f"{tvc['moment_arm_m']:.1f} m); actuator authority "
        f"{_kn(tvc['actuator_authority_n'])}; axial thrust retained "
        f"{tvc['axial_ratio'] * 100.0:.1f}%.",
        "",
        "## 10. Upper-stage propulsion",
        "",
        f"Cycle: **{ucyc['cycle']}** on {ucyc['propellant']} at chamber "
        f"pressure {_mpa(i['upper_pc_pa'])}.",
        f"- Mass flow: {ucyc['mdot']:.1f} kg/s total "
        f"({ucyc['mdot_ox']:.1f} kg/s oxidizer, {ucyc['mdot_f']:.1f} kg/s "
        f"fuel); nominal vacuum thrust {_kn(i['upper_thrust_n'])}.",
        f"- Pump power {ucyc['pump_power_total'] / 1e6:.2f} MW, turbine "
        f"power {ucyc['turbine_power'] / 1e6:.2f} MW, balance "
        f"{ucyc['power_balance'] / 1e6:.2f} MW.",
        f"- Verdict: {ucyc['verdict']}",
        "",
        f"Cold-gas RCS (nitrogen, {_mpa(rcs['pressure_pa'])} plenum, "
        f"{rcs['throat_diameter_m'] * 1000.0:.2f} mm throat, "
        f"{rcs['isp_s']:.0f} s): per-thruster thrust {rcs['thrust_n']:.1f} "
        f"N, initial flow {rcs['mass_flow0_kg_s'] * 1000.0:.1f} g/s, tank "
        f"gas {rcs['tank_mass_kg']:.2f} kg, blowdown time constant "
        f"{rcs['time_constant_s']:.0f} s, operating time to "
        f"{_mpa(rcs['p_min_pa'])}: {rcs['operating_time_s']:.0f} s, total "
        f"impulse {rcs['total_impulse_ns']:.0f} N s.",
        "",
        "## 11. Alternate booster concepts (solid and hybrid screening)",
        "",
        f"Solid booster for the same booster duty (Isp {sol['isp']:.0f} s, "
        "Vieille burn rate r = a p^n with a = "
        f"{sol['burn_rate_coeff']:.1e} m/s per Pa^n, n = "
        f"{sol['pressure_exponent']:.2f}):",
        f"- Equilibrium chamber pressure: {_mpa(sol['chamber_pressure_pa'])} "
        f"at Kn = {sol['kn']:.0f} (burn area {sol['burn_area_m2']:.1f} m2, "
        f"throat {sol['throat_area_m2'] * 1e4:.0f} cm2).",
        f"- Burn rate: {sol['burn_rate_ms'] * 1000.0:.2f} mm/s; mass flow "
        f"{sol['mass_flow_kg_s']:.1f} kg/s (choked-flow / surface "
        f"generation balance "
        f"{'closed' if sol['balance_closed'] else 'open'}).",
        f"- Thrust {_kn(sol['thrust_n'])}, propellant "
        f"{sol['propellant_mass_kg']:.0f} kg, web "
        f"{sol['web_m'] * 1000.0:.0f} mm, total impulse "
        f"{sol['total_impulse_ns'] / 1e6:.1f} MN s.",
        "",
        f"Hybrid ({hyb['fuel']}) screened on the upper-stage burn duty: "
        f"oxidizer flow {hyb['oxidizer_mass_flow_kg_s']:.1f} kg/s through "
        f"a {hyb['port_radius_m']:.2f} m port "
        f"(flux {hyb['oxidizer_mass_flux_kg_m2s']:.0f} kg/(m2 s)), "
        f"regression rate {hyb['regression_rate_mm_s']:.2f} mm/s, fuel "
        f"flow {hyb['fuel_mass_flow_kg_s']:.1f} kg/s, O/F "
        f"{hyb['of_ratio']:.2f}, chamber pressure "
        f"{_mpa(hyb['chamber_pressure_pa'])}.",
        "",
        "## 12. Performance summary",
        "",
        "| Quantity | Value |",
        "|---|---|",
        f"| Payload to LEO | {perf['payload_kg']:.0f} kg |",
        f"| Liftoff mass | {perf['liftoff_mass_kg']:.0f} kg |",
        f"| Total ideal delta-v | {perf['total_ideal_dv_ms']:.0f} m/s |",
        f"| Net insertion delta-v target | {perf['orbit_net_dv_ms']:.0f} m/s |",
        f"| Booster mass ratio | {perf['booster_mass_ratio']:.3f} |",
        f"| Upper-stage mass ratio | {perf['upper_mass_ratio']:.3f} |",
        f"| Booster propellant flow | {perf['booster_mdot_kg_s']:.1f} kg/s |",
        f"| Upper propellant flow | {perf['upper_mdot_kg_s']:.1f} kg/s |",
        f"| Booster total impulse | "
        f"{perf['booster_total_impulse_ns'] / 1e6:.1f} MN s |",
        f"| Upper total impulse | "
        f"{perf['upper_total_impulse_ns'] / 1e6:.1f} MN s |",
        "",
        "## 13. Open items for human review",
        "",
        "- Booster chamber and nozzle hot-side properties are "
        "reference-typical values; confirm with the program combustion "
        "model before release.",
        "- Staging split and ascent-loss inputs (mean flight-path angle, "
        "drag loss) are stated design assumptions for the reference "
        "trajectory.",
        f"- The {ucyc['cycle']} balance above uses reference-typical "
        "drive-gas properties (gas-generator table values) for the "
        "turbine model; re-derive the upper-stage preburner outlet state "
        "with the program cycle code before release.",
        "",
        "---",
        f"*Generated by Aero Agent Roles rocket-propulsion-engineer core "
        f"({model['generated']}). DRAFT for human rocket propulsion "
        "engineering review. Not an approval document and not a launch "
        "readiness decision.*",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evidence gates
# ---------------------------------------------------------------------------

def check_report(model: dict) -> dict:
    """Run the evidence gates against the report model."""
    asc = model.get("ascent", {})
    nz = model.get("nozzle", {})
    results = {
        "item_identified": bool(model.get("item")),
        "propellant_screened": model.get("propellant_screening", {}).get(
            "booster_verdict") in ("suitable", "caveat"),
        "staging_complete": (model.get("staging", {}).get("booster", {}).get(
            "m0_kg", 0) > 0 and model.get("staging", {}).get("upper", {}).get(
            "m0_kg", 0) > 0),
        "ascent_accounted": asc.get("booster_effective_ms", 0) > 0,
        "ascent_closes": asc.get("margin_ms", -1e9) >= 0,
        "engine_cycle_feasible": model.get("booster_cycle", {}).get(
            "feasible") is True,
        "nozzle_geometry_present": (nz.get("exit_mach", 0) > 1
                                    and nz.get("ideal_thrust_vac_n", 0) > 0),
        "cooling_verdict_present": "film_cooling_handoff" in model.get(
            "cooling", {}),
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_report_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    checks = {
        "has_title": "rocket propulsion system design report" in low,
        "has_numbers": "m/s" in low and "kg" in low and "mpa" in low,
        "has_cycle": "gas-generator" in low and "staged-combustion" in low,
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
        "has_no_launch_claim": "not a launch readiness decision" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling."""
    return check_report_markdown(md_text)


# ---------------------------------------------------------------------------
# Example program (for tests and worked-example generation)
# ---------------------------------------------------------------------------

def example_item() -> RocketProgram:
    return RocketProgram()


def example_report_markdown() -> str:
    item = example_item()
    model = build_report(item)
    return render_report_markdown(model)


if __name__ == "__main__":
    item = example_item()
    model = build_report(item)
    md = render_report_markdown(model)
    print("VEHICLE: %s" % model["item"])
    print("LIFTOFF MASS: %.0f kg" % model["performance"]["liftoff_mass_kg"])
    print("EFFECTIVE TOTAL: %.1f m/s (margin %.1f m/s)"
          % (model["ascent"]["effective_total_ms"],
             model["ascent"]["margin_ms"]))
    print("CYCLE: %s feasible=%s" % (model["booster_cycle"]["cycle"],
                                     model["booster_cycle"]["feasible"]))
    print("GATES: %s" % check_report(model))
    print("RENDERED: %d chars" % len(md))
