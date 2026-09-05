#!/usr/bin/env python3
"""high_speed_aero_core.py - High-Speed Aerodynamics Engineer executable core.

This is the role's ENGINE: given a high-speed (transonic/supersonic)
vehicle's flight condition it computes the compressible-flow numbers
with REAL domain formulas and BUILDS the High-Speed Aerodynamic
Analysis Memo. Standalone: no external repo needed (stdlib math only,
offline, deterministic).

Every formula below mirrors the logic of the bound Aero Agent Skills
leaves (which encode public-domain compressible-flow practice;
summaries only, never reproduced text):

- ISA atmosphere: standard lapse-rate troposphere + isothermal
  stratosphere (public domain), Sutherland viscosity.
- Isentropic flow relations
  (aerodynamics/high-speed/isentropic-flow-relations):
      T0/T = 1 + 0.5*(g-1)*M^2;  p0/p = (T0/T)^(g/(g-1));
      rho0/rho = (T0/T)^(1/(g-1))
      A/A* = (1/M) * ((2/(g+1))*(1 + 0.5*(g-1)M^2))^((g+1)/(2(g-1)))
      M from A/A* by bisection (subsonic or supersonic branch)
      choked mass flow mdot = MFP * p0 * A* / sqrt(T0),
      MFP = sqrt(g/R)*(2/(g+1))^((g+1)/(2(g-1))) = 0.0404184
- Compressibility corrections (aerodynamics/high-speed/
  transonic-similarity):
      P-G factor = 1/sqrt(1-M^2)
      Karman-Tsien: Cp = Cp0 / (sqrt(1-M^2)
                     + (M^2/(1+sqrt(1-M^2)))*Cp0/2)
      Cp* = (2/(g M^2))*(((1+0.5(g-1)M^2)/(0.5(g+1)))^(g/(g-1)) - 1)
      critical Mach solves Cp0/sqrt(1-M^2) = Cp*(M) by bisection
- Swept wing (aerodynamics/high-speed/swept-wing-aerodynamics):
      M_eff = M cos(Lambda);  M_cr,swept = M_cr0 / cos(Lambda)
- Normal shock (aerodynamics/high-speed/normal-shock):
      M2 = sqrt((1+0.5(g-1)M1^2)/(g M1^2 - 0.5(g-1)))
      p2/p1 = 1 + 2g/(g+1)(M1^2-1);  rho2/rho1 = (g+1)M1^2/(2+(g-1)M1^2)
      T2/T1 = (p2/p1)/(rho2/rho1);
      p02/p01 = (p2/p1)^(1/(1-g)) * (rho2/rho1)^(g/(g-1))
- Oblique shock (aerodynamics/high-speed/oblique-shock):
      theta-beta-M relation tan(theta) = 2 cot(beta)(M1^2 sin^2(beta)-1)
                                        /(M1^2(g+cos(2 beta))+2)
      weak/strong beta by bisection; normal ratios on M1n = M1 sin(beta);
      M2 = M2n / sin(beta - theta); theta_max by ternary search
- Regular shock reflection (aerodynamics/high-speed/
  regular-shock-reflection): incident oblique state at (M1, theta),
  reflected shock must turn the flow back parallel to the wall;
  verdict 'regular' when M2 > 1 and theta < theta_max(M2), else 'mach'
- Prandtl-Meyer (aerodynamics/high-speed/prandtl-meyer):
      nu(M) = sqrt((g+1)/(g-1)) atan(sqrt((g-1)/(g+1)(M^2-1)))
              - atan(sqrt(M^2-1))
      M2 from nu(M2) = nu(M1) + delta by bisection; p2/p1 = isentropic
- Shock-expansion airfoil (aerodynamics/high-speed/
  shock-expansion-airfoil): four-panel diamond airfoil, oblique-shock
  turn on compression corners, Prandtl-Meyer turn on expansion corners,
  surface Cp from p/p_inf, forces integrated to section cl / cd_wave /
  cm_le (chord c = 1, q_ref = 0.5 g M^2 normalization)
- Supercritical section / Korn rule
  (aerodynamics/high-speed/supercritical-airfoil):
      M_DD = 0.95 - t/c - CL/10 (supercritical), 0.90 - ... (conventional)
      terminating shock strength p2/p1 = 1 + 2g/(g+1)(M^2-1)
- Wave drag area rule (aerodynamics/high-speed/wave-drag-area-rule):
      Sears-Haack zero-lift wave drag area D/q = (9 pi/2)(A_max/L)^2
      wave drag rise Delta CDw = k (M - M_DD)^2 above drag divergence
- Boundary layer theory (aerodynamics/boundary-layer/
  boundary-layer-theory): laminar Blasius delta = 5 x/sqrt(Re_x),
  delta* = 1.7208 x/sqrt(Re_x), theta = 0.664 x/sqrt(Re_x),
  Cf = 0.664/sqrt(Re_x); turbulent 1/7-power delta = 0.37 x/Re_x^(1/5),
  delta* = delta/8, theta = 7 delta/72, Cf = 0.0592/Re_x^(1/5),
  log-law Cf = 0.455/(log10 Re_x)^2.58; regime at Re_tr = 5e5
- Boundary layer transition (aerodynamics/boundary-layer/
  boundary-layer-transition): flat-plate Michel/Thwaites closed form
  Re_theta = sqrt(0.45) sqrt(Re_x) crossing the Michel threshold
  Re_theta,tr = 1.174 (1 + 22400/Re_x) Re_x^0.46
- Rough wall skin friction (aerodynamics/boundary-layer/
  rough-wall-skin-friction): u_tau = U sqrt(Cf/2), k+ = rho u_tau k_s/mu,
  regime bands smooth k+ < 5, transitional 5-70, fully rough > 70
- Stagnation flow boundary layer (aerodynamics/boundary-layer/
  stagnation-flow-boundary-layer): Hiemenz 2-D leading edge
  a = 2 U/R, delta = 2.4 sqrt(nu/a), tau_w = mu U sqrt(a/nu) fpp(1.2326),
  Cf = tau_w/(0.5 rho U^2)
- Aerodynamic heating (aerodynamics/high-speed/aerodynamic-heating):
  Sutton-Graves q_s = C_SG sqrt(rho/Rn) V^3, C_SG = 1.83e-4,
  radiation-equilibrium T_w = (q/(eps sigma))^(1/4)
- Flat-plate skin friction heating (aerodynamics/high-speed/
  flat-plate-skin-friction-heating): recovery factor r = Pr^(1/2)
  laminar / Pr^(1/3) turbulent, adiabatic wall temperature
  T_aw = T_inf (1 + r (g-1)/2 M^2), Eckert reference temperature,
  cold-wall flux q = h_c (T_aw - T_wall), h_c = 0.5 Cf rho* U CP
- Bow shock standoff (aerodynamics/high-speed/bow-shock-standoff):
  Billig correlations sphere Delta/R = 0.143 exp(3.24/M^2),
  cylinder Delta/R = 0.386 exp(4.67/M^2)

Deliverable: the High-Speed Aerodynamic Analysis Memo
(render_memo_markdown), with evidence gates (check_memo /
check_memo_markdown) that verify the document before it leaves the
role. Every margin row in the memo traces to a stage output of the
bound workflow.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Physical / ISA constants (public domain)
# ---------------------------------------------------------------------------
ISA_T0 = 288.15            # K, sea-level temperature
ISA_P0 = 101325.0          # Pa, sea-level pressure
ISA_RHO0 = 1.225           # kg/m^3, sea-level density
ISA_LAPSE = 0.0065         # K/m, troposphere lapse rate
ISA_TROPOPAUSE = 11000.0   # m
GAMMA = 1.4                # specific-heat ratio of air
R_GAS = 287.052874         # J/(kg K), gas constant of air
G0 = 9.80665               # m/s^2
SUTHERLAND_MU0 = 1.458e-6  # Sutherland law constant (kg/(m s K^1.5))
SUTHERLAND_S = 110.4       # Sutherland reference temperature (K)
CP_AIR = 1005.0            # J/(kg K) constant-pressure specific heat
PR_AIR = 0.71              # Prandtl number of air

# Compressible-flow constants mirrored from the bound leaves.
MFP_CONST = 0.0404184199   # mass flow parameter, sqrt(g/R)*(2/(g+1))^...
PG_MACH_LIMIT = 0.99       # P-G/KT bisection upper bound on Mach
KT_MACH_LIMIT = 0.85       # documented Karman-Tsien validity ceiling
SECTION_MCR_MIN_CP = -2.0  # plausible suction-peak floor for M_cr solve
RE_TRANSITION = 5e5        # flat-plate natural transition Reynolds number
C_SG = 1.83e-4             # Sutton-Graves air correlation constant
SIGMA_SB = 5.670374419e-8  # Stefan-Boltzmann constant, W/(m2 K4)
EPS_DEFAULT = 0.85         # TPS surface emissivity
RECOVERY_TURBULENT = PR_AIR ** (1.0 / 3.0)   # Pr^(1/3), flat-plate turbulent
RECOVERY_LAMINAR = math.sqrt(PR_AIR)          # Pr^(1/2), flat-plate laminar

# Item-level screening limits (engineering design values for the memo's
# reference vehicle; inputs, never invented regulatory allowables).
SKIN_TEMP_LIMIT_K = 423.0  # aluminium-alloy skin screening limit, ~150 C
NOSE_TEMP_LIMIT_K = 600.0  # nose-cap screening limit (leading-edge alloy)

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _require_positive(name: str, value: float) -> None:
    if not (isinstance(value, (int, float)) and value > 0.0):
        raise ValueError("%s must be positive, got %r" % (name, value))


def _require_nonnegative(name: str, value: float) -> None:
    if not (isinstance(value, (int, float)) and value >= 0.0):
        raise ValueError("%s must be >= 0, got %r" % (name, value))


# ---------------------------------------------------------------------------
# ISA standard atmosphere (public-domain lapse-rate model)
# ---------------------------------------------------------------------------

def isa_temperature(altitude_m: float) -> float:
    """ISA temperature (K) at geometric altitude (m), tropo+stratosphere."""
    _require_nonnegative("altitude", altitude_m)
    if altitude_m <= ISA_TROPOPAUSE:
        return ISA_T0 - ISA_LAPSE * altitude_m
    return ISA_T0 - ISA_LAPSE * ISA_TROPOPAUSE  # 216.65 K isothermal


def isa_pressure(altitude_m: float) -> float:
    """ISA static pressure (Pa) at altitude (m)."""
    _require_nonnegative("altitude", altitude_m)
    t = isa_temperature(altitude_m)
    if altitude_m <= ISA_TROPOPAUSE:
        return ISA_P0 * (t / ISA_T0) ** (G0 / (ISA_LAPSE * R_GAS))
    p_tropo = ISA_P0 * (216.65 / ISA_T0) ** (G0 / (ISA_LAPSE * R_GAS))
    return p_tropo * math.exp(-G0 * (altitude_m - ISA_TROPOPAUSE)
                              / (R_GAS * 216.65))


def isa_density(altitude_m: float) -> float:
    """ISA air density (kg/m^3) from the perfect-gas law."""
    _require_nonnegative("altitude", altitude_m)
    return isa_pressure(altitude_m) / (R_GAS * isa_temperature(altitude_m))


def speed_of_sound(temperature_k: float) -> float:
    """Speed of sound a = sqrt(gamma*R*T) in m/s."""
    _require_positive("temperature", temperature_k)
    return math.sqrt(GAMMA * R_GAS * temperature_k)


def air_viscosity(temperature_k: float) -> float:
    """Dynamic viscosity mu (kg/(m s)) by Sutherland's law."""
    _require_positive("temperature", temperature_k)
    return (SUTHERLAND_MU0 * temperature_k ** 1.5) / (temperature_k + SUTHERLAND_S)


def atmosphere(altitude_m: float) -> Dict[str, float]:
    """ISA atmosphere state at altitude: T, p, rho, a, mu (SI units)."""
    _require_nonnegative("altitude", altitude_m)
    t = isa_temperature(altitude_m)
    p = isa_pressure(altitude_m)
    rho = isa_density(altitude_m)
    a = speed_of_sound(t)
    mu = air_viscosity(t)
    return {"temperature": t, "pressure": p, "density": rho,
            "speed_of_sound": a, "viscosity": mu}


# ---------------------------------------------------------------------------
# Isentropic flow relations (isentropic-flow-relations leaf)
# ---------------------------------------------------------------------------

def total_static_ratios(mach: float) -> Dict[str, float]:
    """Isentropic total-to-static ratios at a Mach number (air, g = 1.4)."""
    _require_nonnegative("mach", mach)
    t0_over_t = 1.0 + 0.5 * (GAMMA - 1.0) * mach * mach
    return {
        "t0_over_t": t0_over_t,
        "p0_over_p": t0_over_t ** (GAMMA / (GAMMA - 1.0)),
        "rho0_over_rho": t0_over_t ** (1.0 / (GAMMA - 1.0)),
    }


def area_ratio(mach: float) -> float:
    """Isentropic area ratio A/A* for a Mach number (Mach-area relation)."""
    if mach <= 0.0:
        raise ValueError("Mach number must be > 0 for the area ratio, got %r" % (mach,))
    base = (2.0 / (GAMMA + 1.0)) * (1.0 + 0.5 * (GAMMA - 1.0) * mach * mach)
    exponent = (GAMMA + 1.0) / (2.0 * (GAMMA - 1.0))
    return (1.0 / mach) * base ** exponent


def mach_from_area_ratio(aa: float, subsonic: bool = True) -> float:
    """Recover the Mach number for an area ratio A/A* (deterministic bisection).

    Subsonic root over [0.05, 1.0), supersonic root over (1.0, 20.0].
    Mirrors the isentropic-flow-relations leaf solver.
    """
    if aa < 1.0:
        raise ValueError("A/A* must be >= 1.0 (sonic-throat floor), got %r" % (aa,))
    if aa == 1.0:
        return 1.0
    if subsonic:
        lo, hi = 0.05, 1.0
    else:
        lo, hi = 1.0, 20.0
    f_lo = area_ratio(lo) - aa
    for _ in range(300):
        if hi - lo < 1e-12:
            break
        mid = 0.5 * (lo + hi)
        f_mid = area_ratio(mid) - aa
        if (f_mid < 0.0) == (f_lo < 0.0):
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def static_to_total(p_static: float, t_static: float, mach: float) -> Dict[str, float]:
    """Rebuild total conditions from a static state and Mach number."""
    _require_positive("static pressure", p_static)
    _require_positive("static temperature", t_static)
    ratios = total_static_ratios(mach)
    return {"p0": p_static * ratios["p0_over_p"],
            "t0": t_static * ratios["t0_over_t"]}


def choked_mass_flow(p0: float, t0: float, area_star: float) -> float:
    """Choked mass flow mdot (kg/s) through a sonic throat area A* (m2)."""
    _require_positive("total pressure", p0)
    _require_positive("total temperature", t0)
    _require_positive("throat area", area_star)
    return MFP_CONST * p0 * area_star / math.sqrt(t0)


# ---------------------------------------------------------------------------
# Compressibility corrections (transonic-similarity leaf)
# ---------------------------------------------------------------------------

def prandtl_glauert_factor(mach: float) -> float:
    """Prandtl-Glauert compressibility factor 1/sqrt(1-M^2), M < 1."""
    _require_nonnegative("mach", mach)
    if mach >= 1.0:
        raise ValueError("P-G factor is subsonic only (M < 1), got %r" % (mach,))
    return 1.0 / math.sqrt(1.0 - mach * mach)


def prandtl_glauert_correction(cp0: float, mach: float) -> float:
    """Incompressible Cp corrected by the Prandtl-Glauert rule."""
    return cp0 * prandtl_glauert_factor(mach)


def karman_tsien_correction(cp0: float, mach: float) -> float:
    """Pressure coefficient corrected by the Karman-Tsien rule.

    Cp = Cp0 / (sqrt(1-M^2) + (M^2/(1+sqrt(1-M^2))) * Cp0/2).
    """
    _require_nonnegative("mach", mach)
    if mach >= KT_MACH_LIMIT:
        raise ValueError("Karman-Tsien is documented to M ~ 0.85, got %r" % (mach,))
    root = math.sqrt(1.0 - mach * mach)
    return cp0 / (root + (mach * mach / (1.0 + root)) * cp0 / 2.0)


def critical_pressure_coefficient(mach: float) -> float:
    """Isentropic pressure coefficient at which local flow reaches M = 1.

    Cp* = (2/(g M^2)) * (((1 + 0.5(g-1)M^2)/(0.5(g+1)))^(g/(g-1)) - 1).
    """
    _require_nonnegative("mach", mach)
    if mach == 0.0:
        raise ValueError("Mach must be > 0 for Cp*, got 0")
    term = (1.0 + 0.5 * (GAMMA - 1.0) * mach * mach) / (0.5 * (GAMMA + 1.0))
    return (2.0 / (GAMMA * mach * mach)) * (term ** (GAMMA / (GAMMA - 1.0)) - 1.0)


def critical_mach_number(cp_min0: float) -> float:
    """Critical Mach number for an incompressible peak suction Cp0 < 0.

    Solves Cp0 / sqrt(1 - M^2) = Cp*(M) by bisection on M in [0.02, 0.99].
    """
    if cp_min0 >= 0.0:
        raise ValueError("peak suction cp_min0 must be negative, got %r" % (cp_min0,))
    lo, hi = 0.02, PG_MACH_LIMIT
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        lhs = cp_min0 / math.sqrt(1.0 - mid * mid)
        rhs = critical_pressure_coefficient(mid)
        if lhs - rhs > 0.0:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-10:
            break
    return 0.5 * (lo + hi)


def transonic_similarity_parameter(mach: float, tau: float) -> float:
    """Transonic similarity parameter K = (1 - M^2) / tau^(2/3)."""
    if not (0.0 <= mach <= 1.0):
        raise ValueError("Mach must be in [0, 1], got %r" % (mach,))
    if not (0.0 < tau < 1.0):
        raise ValueError("thickness ratio tau must be in (0, 1), got %r" % (tau,))
    return (1.0 - mach * mach) / (tau ** (2.0 / 3.0))


# ---------------------------------------------------------------------------
# Swept wing (swept-wing-aerodynamics leaf)
# ---------------------------------------------------------------------------

def cos_sweep(sweep_deg: float) -> float:
    """Cosine of the sweep angle (degrees)."""
    if not (0.0 <= sweep_deg < 90.0):
        raise ValueError("sweep must be in [0, 90) degrees, got %r" % (sweep_deg,))
    return math.cos(math.radians(sweep_deg))


def effective_mach(mach: float, sweep_deg: float) -> float:
    """Section (effective) Mach number of a yawed wing: M * cos(Lambda)."""
    if not (0.0 <= mach < 1.0):
        raise ValueError("effective-Mach model is subsonic (M < 1), got %r" % (mach,))
    return mach * cos_sweep(sweep_deg)


def swept_critical_mach(mcrit0: float, sweep_deg: float) -> float:
    """Critical Mach of the swept wing: mcrit0 / cos(Lambda)."""
    if not (0.0 < mcrit0 < 1.0):
        raise ValueError("unswept critical Mach must be in (0, 1), got %r" % (mcrit0,))
    mcrit = mcrit0 / cos_sweep(sweep_deg)
    if mcrit >= 1.0:
        raise ValueError("swept critical Mach reaches 1 (subsonic theory only)")
    return mcrit


# ---------------------------------------------------------------------------
# Normal shock (normal-shock leaf)
# ---------------------------------------------------------------------------

def normal_shock(m1: float) -> Dict[str, float]:
    """All normal-shock ratios at upstream Mach M1 (unitless, air)."""
    if m1 <= 1.0:
        raise ValueError("M1 must be > 1 (upstream flow supersonic), got %r" % (m1,))
    g = GAMMA
    m2 = math.sqrt((1.0 + 0.5 * (g - 1.0) * m1 * m1)
                   / (g * m1 * m1 - 0.5 * (g - 1.0)))
    p2_p1 = 1.0 + 2.0 * g / (g + 1.0) * (m1 * m1 - 1.0)
    rho2_rho1 = (g + 1.0) * m1 * m1 / (2.0 + (g - 1.0) * m1 * m1)
    p02_p01 = (p2_p1 ** (1.0 / (1.0 - g))
               * rho2_rho1 ** (g / (g - 1.0)))
    return {"m2": m2, "p2_p1": p2_p1, "t2_t1": p2_p1 / rho2_rho1,
            "rho2_rho1": rho2_rho1, "p02_p01": p02_p01}


# ---------------------------------------------------------------------------
# Oblique shock (oblique-shock leaf)
# ---------------------------------------------------------------------------

def mach_angle(m1: float) -> float:
    """Mach wave angle mu = asin(1/M1) in degrees."""
    if m1 <= 1.0:
        raise ValueError("M1 must be > 1, got %r" % (m1,))
    return math.degrees(math.asin(1.0 / m1))


def _theta_from_beta(m1: float, beta_deg: float) -> float:
    """Flow deflection theta (deg) across an oblique shock at wave angle beta."""
    b = math.radians(beta_deg)
    m1s = m1 * m1
    num = 2.0 * (1.0 / math.tan(b)) * (m1s * math.sin(b) ** 2 - 1.0)
    den = m1s * (GAMMA + math.cos(2.0 * b)) + 2.0
    return math.degrees(math.atan(num / den))


def deflection_limit(m1: float) -> float:
    """Maximum attached-shock deflection theta_max (deg) at M1.

    Apex of the shock polar, by ternary search over (mu, 90 deg].
    """
    if m1 <= 1.0:
        raise ValueError("M1 must be > 1, got %r" % (m1,))
    mu = mach_angle(m1)
    lo, hi = mu + 1e-9, 90.0
    for _ in range(200):
        a = (2.0 * lo + hi) / 3.0
        b = (lo + 2.0 * hi) / 3.0
        if _theta_from_beta(m1, a) < _theta_from_beta(m1, b):
            lo = a
        else:
            hi = b
    mid = 0.5 * (lo + hi)
    return _theta_from_beta(m1, mid)


def oblique_shock(m1: float, theta_deg: float, strong: bool = False) -> Dict[str, float]:
    """Downstream state across the oblique shock (weak or strong branch).

    Solves the theta-beta-M relation for the wave angle by bisection,
    then applies the normal-shock ratios to M1n = M1 sin(beta).
    """
    if m1 <= 1.0:
        raise ValueError("M1 must be > 1, got %r" % (m1,))
    if theta_deg < 0.0:
        raise ValueError("theta must be >= 0 (a negative deflection is an "
                         "expansion), got %r" % (theta_deg,))
    tmax = deflection_limit(m1)
    if theta_deg > tmax:
        raise ValueError("theta %g exceeds theta_max %g at M1 %g: detached"
                         % (theta_deg, tmax, m1))
    mu = mach_angle(m1)
    if theta_deg <= 1e-12:
        if strong:
            ns = normal_shock(m1)  # beta -> 90 deg collapses to the normal shock
            return {"beta_deg": 90.0, "m2": ns["m2"], "p2_p1": ns["p2_p1"],
                    "rho2_rho1": ns["rho2_rho1"], "t2_t1": ns["t2_t1"],
                    "p02_p01": ns["p02_p01"], "theta_max_deg": tmax,
                    "strong": True}
        # weak limit: the shock collapses onto the Mach wave (isentropic)
        return {"beta_deg": mu, "m2": m1, "p2_p1": 1.0, "rho2_rho1": 1.0,
                "t2_t1": 1.0, "p02_p01": 1.0, "theta_max_deg": tmax,
                "strong": False}

    def _target(beta):
        return _theta_from_beta(m1, beta) - theta_deg

    # locate the peak beta (apex) to bracket weak and strong branches
    lo, hi = mu + 1e-9, 90.0
    for _ in range(200):
        a = (2.0 * lo + hi) / 3.0
        b = (lo + 2.0 * hi) / 3.0
        if _theta_from_beta(m1, a) < _theta_from_beta(m1, b):
            lo = a
        else:
            hi = b
    bmax = 0.5 * (lo + hi)
    if strong:
        lo_b, hi_b = bmax, 90.0
    else:
        lo_b, hi_b = mu + 1e-9, bmax
    for _ in range(300):
        mid = 0.5 * (lo_b + hi_b)
        if _target(mid) < 0.0:
            lo_b = mid
        else:
            hi_b = mid
        if hi_b - lo_b < 1e-10:
            break
    beta = 0.5 * (lo_b + hi_b)
    m1n = m1 * math.sin(math.radians(beta))
    g = GAMMA
    m2n = math.sqrt((1.0 + 0.5 * (g - 1.0) * m1n * m1n)
                    / (g * m1n * m1n - 0.5 * (g - 1.0)))
    p2_p1 = 1.0 + 2.0 * g / (g + 1.0) * (m1n * m1n - 1.0)
    rho2_rho1 = (g + 1.0) * m1n * m1n / (2.0 + (g - 1.0) * m1n * m1n)
    p02_p01 = (p2_p1 ** (1.0 / (1.0 - g))
               * rho2_rho1 ** (g / (g - 1.0)))
    m2 = m2n / math.sin(math.radians(beta - theta_deg))
    return {"beta_deg": beta, "m2": m2, "p2_p1": p2_p1,
            "rho2_rho1": rho2_rho1, "t2_t1": p2_p1 / rho2_rho1,
            "p02_p01": p02_p01, "theta_max_deg": tmax, "strong": bool(strong)}


def shock_reflection_verdict(m1: float, theta_deg: float) -> Dict:
    """Two-shock regular-reflection verdict at (M1, theta) (straight wall).

    Incident oblique shock at (M1, theta); the reflected shock must turn
    the flow back parallel to the wall by the same deflection. Verdict is
    'regular' when the incident downstream Mach M2 > 1 and theta is below
    the reflected-shock detachment limit at M2; otherwise 'mach'.
    """
    incident = oblique_shock(m1, theta_deg)
    m2 = incident["m2"]
    theta_max_ref = deflection_limit(m2) if m2 and m2 > 1.0 else 0.0
    result = {
        "verdict": None, "theta_deg": theta_deg, "M2": m2,
        "theta_max_ref_deg": theta_max_ref,
        "incident": incident, "reflected": None, "reason": None,
    }
    if m2 and m2 > 1.0 and theta_deg < theta_max_ref:
        result["verdict"] = "regular"
        result["reflected"] = oblique_shock(m2, theta_deg)
        result["reason"] = ("reflected shock turns the flow back parallel "
                            "to the wall below the detachment limit")
    else:
        result["verdict"] = "mach"
        result["reason"] = ("required reflected deflection reaches the "
                            "reflected-shock detachment limit at M2 "
                            "(or M2 <= 1): Mach reflection")
    return result


# ---------------------------------------------------------------------------
# Prandtl-Meyer expansion (prandtl-meyer leaf)
# ---------------------------------------------------------------------------

def prandtl_meyer_function(mach: float) -> float:
    """Prandtl-Meyer angle nu(M) in radians (M >= 1)."""
    if mach < 1.0:
        raise ValueError("Prandtl-Meyer function undefined below M = 1, got %r"
                         % (mach,))
    term = math.sqrt((GAMMA - 1.0) / (GAMMA + 1.0) * (mach * mach - 1.0))
    return (math.sqrt((GAMMA + 1.0) / (GAMMA - 1.0)) * math.atan(term)
            - math.atan(math.sqrt(mach * mach - 1.0)))


def mach_after_expansion(m1: float, turning_angle_deg: float,
                         bracket=(1.0, 50.0)) -> float:
    """Downstream Mach number after an isentropic turn of given angle."""
    if m1 < 1.0:
        raise ValueError("upstream Mach must be >= 1, got %r" % (m1,))
    if turning_angle_deg < 0.0:
        raise ValueError("turning angle must be >= 0, got %r" % (turning_angle_deg,))
    target = prandtl_meyer_function(m1) + math.radians(turning_angle_deg)
    lo, hi = bracket
    if target > prandtl_meyer_function(hi):
        raise ValueError("turning angle too large for the Mach bracket")
    for _ in range(300):
        mid = 0.5 * (lo + hi)
        if prandtl_meyer_function(mid) < target:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-10:
            break
    return 0.5 * (lo + hi)


def expansion_properties(m1: float, turning_angle_deg: float) -> Dict[str, float]:
    """Downstream state across a Prandtl-Meyer expansion (unitless)."""
    m2 = mach_after_expansion(m1, turning_angle_deg)
    def _p_over_p0(m):
        return (1.0 + 0.5 * (GAMMA - 1.0) * m * m) ** (-GAMMA / (GAMMA - 1.0))
    return {"m2": m2, "turning_angle_deg": turning_angle_deg,
            "pressure_ratio_p2_p1": _p_over_p0(m2) / _p_over_p0(m1)}


# ---------------------------------------------------------------------------
# Shock-expansion diamond airfoil (shock-expansion-airfoil leaf)
# ---------------------------------------------------------------------------

def _pm_mach_from_angle(nu_deg: float) -> float:
    """Invert nu(M) = nu_deg (degrees) for the Mach number (bisection)."""
    target = math.radians(nu_deg)
    lo, hi = 1.0 + 1e-12, 2.0
    while prandtl_meyer_function(hi) < target:
        hi *= 2.0
    for _ in range(300):
        mid = 0.5 * (lo + hi)
        if prandtl_meyer_function(mid) < target:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-10:
            break
    return 0.5 * (lo + hi)


def _panel_turn(m: float, p_ratio_in: float, theta_deg: float):
    """State after a turn: positive theta is an oblique-shock compression,
    negative theta is a Prandtl-Meyer expansion. Returns (m_out, p_out)."""
    if theta_deg > 0.0:
        st = oblique_shock(m, theta_deg)
        return st["m2"], p_ratio_in * st["p2_p1"]
    if theta_deg < 0.0:
        m2 = _pm_mach_from_angle(math.degrees(prandtl_meyer_function(m))
                                 - theta_deg)
        p2_p1 = ((1.0 + 0.5 * (GAMMA - 1.0) * m * m)
                 / (1.0 + 0.5 * (GAMMA - 1.0) * m2 * m2)) ** (GAMMA / (GAMMA - 1.0))
        return m2, p_ratio_in * p2_p1
    return m, p_ratio_in


def shock_expansion_airfoil(m1: float, alpha_deg: float, eps_deg: float) -> Dict:
    """Shock-expansion solution for a diamond (double-wedge) airfoil.

    Returns section cl, cd_wave and cm_le (leading-edge moment, positive
    nose-up) with chord c = 1 and q_ref = 0.5 g M1^2 normalization,
    mirroring the shock-expansion-airfoil leaf panel model.
    """
    if m1 <= 1.0:
        raise ValueError("shock-expansion requires supersonic m1 > 1")
    if abs(alpha_deg) >= 90.0:
        raise ValueError("|alpha| must be below 90 deg")
    if not (0.0 <= eps_deg < 45.0):
        raise ValueError("eps (half-angle) must lie in [0, 45) deg")
    q_ref = 0.5 * GAMMA * m1 * m1

    # Panel deflections in degrees (positive = compression).
    theta_uf = eps_deg - alpha_deg
    theta_lf = eps_deg + alpha_deg
    theta_rear = -2.0 * eps_deg

    m_uf, p_uf = _panel_turn(m1, 1.0, theta_uf)
    m_lf, p_lf = _panel_turn(m1, 1.0, theta_lf)
    m_ur, p_ur = _panel_turn(m_uf, p_uf, theta_rear)
    m_lr, p_lr = _panel_turn(m_lf, p_lf, theta_rear)
    surfaces = {
        "uf": {"cp": (p_uf - 1.0) / q_ref, "p_pinf": p_uf},
        "ur": {"cp": (p_ur - 1.0) / q_ref, "p_pinf": p_ur},
        "lf": {"cp": (p_lf - 1.0) / q_ref, "p_pinf": p_lf},
        "lr": {"cp": (p_lr - 1.0) / q_ref, "p_pinf": p_lr},
    }
    alpha = math.radians(alpha_deg)
    eps = math.radians(eps_deg)
    sin_e, cos_e = math.sin(eps), math.cos(eps)
    normals = {"uf": (sin_e, -cos_e), "ur": (-sin_e, -cos_e),
               "lf": (sin_e, cos_e), "lr": (-sin_e, cos_e)}
    centers = {"uf": (0.25, 0.25 * math.tan(eps)),
               "ur": (0.75, 0.25 * math.tan(eps)),
               "lf": (0.25, -0.25 * math.tan(eps)),
               "lr": (0.75, -0.25 * math.tan(eps))}
    panel_len = 0.5 / cos_e
    fx = fy = moment = 0.0
    for key in ("uf", "ur", "lf", "lr"):
        dp = surfaces[key]["p_pinf"] - 1.0
        nx, ny = normals[key]
        cx, cy = centers[key]
        fxi = dp * panel_len * nx
        fyi = dp * panel_len * ny
        fx += fxi
        fy += fyi
        moment += cx * fyi - cy * fxi
    cos_a, sin_a = math.cos(alpha), math.sin(alpha)
    drag = fx * cos_a + fy * sin_a
    lift = -fx * sin_a + fy * cos_a
    return {"m1": m1, "alpha_deg": alpha_deg, "eps_deg": eps_deg,
            "cl": lift / q_ref, "cd_wave": drag / q_ref,
            "cm_le": moment / q_ref,
            "surface_cp": {k: v["cp"] for k, v in surfaces.items()}}


# ---------------------------------------------------------------------------
# Supercritical section / Korn rule (supercritical-airfoil leaf)
# ---------------------------------------------------------------------------

def drag_divergence_mach(t_over_c: float, cl: float,
                         supercritical: bool = True) -> float:
    """Korn-rule drag-divergence Mach number of a section."""
    if not (0.02 < t_over_c < 0.30):
        raise ValueError("t/c must be in (0.02, 0.30), got %r" % (t_over_c,))
    if not (0.0 <= cl < 1.5):
        raise ValueError("cruise lift coefficient must be in [0, 1.5)")
    base = 0.95 if supercritical else 0.90
    return base - t_over_c - cl / 10.0


def terminating_shock_strength(mach_ahead: float) -> float:
    """Static pressure ratio across the terminating shock (local M in (1,2])."""
    if not (1.0 < mach_ahead <= 2.0):
        raise ValueError("local Mach ahead must be in (1, 2], got %r"
                         % (mach_ahead,))
    return 1.0 + 2.0 * GAMMA / (GAMMA + 1.0) * (mach_ahead ** 2 - 1.0)


def wave_drag_penalty(mach: float, mdd: float) -> float:
    """Relative wave-drag penalty index: (M - M_DD)^3 above divergence."""
    if not (0.5 <= mach < 1.0):
        raise ValueError("flight Mach must be in [0.5, 1), got %r" % (mach,))
    if not (0.5 < mdd < 1.0):
        raise ValueError("drag-divergence Mach must be in (0.5, 1)")
    excess = mach - mdd
    return 0.0 if excess <= 0.0 else excess ** 3


# ---------------------------------------------------------------------------
# Wave drag area rule (wave-drag-area-rule leaf)
# ---------------------------------------------------------------------------

def sears_haack_wave_drag_area(length: float, r_max: float) -> float:
    """Zero-lift wave drag area D/q of the Sears-Haack body of revolution.

    D/q = (9 pi / 2) * (A_max / L)^2, A_max = pi * r_max^2.
    """
    _require_positive("body length", length)
    _require_positive("maximum radius", r_max)
    a_max = math.pi * r_max * r_max
    return (9.0 * math.pi / 2.0) * (a_max / length) ** 2


def wave_drag_rise_coef(mach: float, mdd: float, k: float = 20.0) -> float:
    """Parabolic wave-drag rise Delta CDw = k (M - M_DD)^2 above M_DD."""
    if not (0.0 <= mach < 1.0):
        raise ValueError("Mach must be in [0, 1)")
    if not (0.0 < mdd < 1.0):
        raise ValueError("drag-divergence Mach must be in (0, 1)")
    if k <= 0.0:
        raise ValueError("parabolic constant k must be positive")
    return 0.0 if mach <= mdd else k * (mach - mdd) ** 2


# ---------------------------------------------------------------------------
# Boundary layer theory (boundary-layer-theory leaf)
# ---------------------------------------------------------------------------

def reynolds(rho: float, v: float, l: float, mu: float) -> float:
    """Reynolds number Re = rho * V * L / mu."""
    _require_positive("rho", rho)
    _require_positive("v", v)
    _require_positive("l", l)
    _require_positive("mu", mu)
    return rho * v * l / mu


def kinematic_viscosity(mu: float, rho: float) -> float:
    """Kinematic viscosity nu = mu / rho."""
    _require_positive("mu", mu)
    _require_positive("rho", rho)
    return mu / rho


def classify_regime(re_x: float, re_tr: float = RE_TRANSITION) -> str:
    """'laminar' below the transition Reynolds number, else 'turbulent'."""
    _require_positive("re_x", re_x)
    _require_positive("transition re", re_tr)
    return "laminar" if re_x < re_tr else "turbulent"


def flat_plate_thicknesses(x: float, re_x: float,
                           re_tr: float = RE_TRANSITION) -> Dict:
    """Flat-plate boundary-layer summary at station x: regime, delta,
    delta*, theta, shape factor, local and average skin friction."""
    _require_positive("station x", x)
    _require_positive("re_x", re_x)
    regime = classify_regime(re_x, re_tr)
    if regime == "laminar":
        delta = 5.0 * x / math.sqrt(re_x)
        dstar = 1.7208 * x / math.sqrt(re_x)
        theta = 0.664 * x / math.sqrt(re_x)
        cf_local = 0.664 / math.sqrt(re_x)
        cf_avg = 1.328 / math.sqrt(re_x)
    else:
        delta = 0.37 * x / re_x ** 0.2
        dstar = delta / 8.0
        theta = 7.0 * delta / 72.0
        cf_local = 0.0592 / re_x ** 0.2
        cf_avg = 0.074 / re_x ** 0.2
    return {"regime": regime, "delta": delta, "delta_star": dstar,
            "theta": theta, "shape_factor": dstar / theta,
            "cf_local": cf_local, "cf_average": cf_avg}


def cf_turbulent_log_law(re_x: float) -> float:
    """Turbulent skin friction from the log law: 0.455/(log10 Re)^2.58."""
    if re_x <= 10.0:
        raise ValueError("Reynolds number must be > 10 for the log law")
    return 0.455 / (math.log10(re_x) ** 2.58)


# ---------------------------------------------------------------------------
# Boundary layer transition (boundary-layer-transition leaf)
# ---------------------------------------------------------------------------

def michel_threshold(re_x: float) -> float:
    """Michel transition criterion Re_theta,tr at Re_x."""
    _require_positive("re_x", re_x)
    return 1.174 * (1.0 + 22400.0 / re_x) * re_x ** 0.46


def flat_plate_transition(nu: float, ue: float, x_max: float):
    """Natural-transition location x_tr (m) on a flat plate at edge speed ue.

    Closed-form Michel check with Re_theta = sqrt(0.45) sqrt(Re_x),
    scanned from 1e-3 m to x_max; None when no crossing exists.
    """
    _require_positive("nu", nu)
    _require_positive("ue", ue)
    _require_positive("x_max", x_max)
    lo, steps = 1e-3, 500
    dx = (x_max - lo) / steps
    for i in range(steps + 1):
        x = lo + i * dx
        re_x = ue * x / nu
        re_theta = math.sqrt(0.45) * math.sqrt(re_x)
        if re_theta >= michel_threshold(re_x):
            return x
    return None


# ---------------------------------------------------------------------------
# Rough wall skin friction (rough-wall-skin-friction leaf)
# ---------------------------------------------------------------------------

def friction_velocity(u_inf: float, cf: float) -> float:
    """Friction velocity u_tau = U * sqrt(Cf/2)."""
    _require_positive("u_inf", u_inf)
    _require_positive("cf", cf)
    return u_inf * math.sqrt(cf / 2.0)


def sand_roughness_reynolds(rho: float, u_tau: float, k_s: float,
                            mu: float) -> float:
    """Roughness Reynolds number k+ = rho * u_tau * k_s / mu."""
    _require_positive("rho", rho)
    _require_positive("u_tau", u_tau)
    _require_positive("k_s", k_s)
    _require_positive("mu", mu)
    return rho * u_tau * k_s / mu


def roughness_regime(k_plus: float) -> str:
    """Surface regime: smooth k+ < 5, transitional 5-70, fully rough > 70."""
    _require_nonnegative("k+", k_plus)
    if k_plus < 5.0:
        return "smooth"
    if k_plus <= 70.0:
        return "transitional"
    return "fully-rough"


# ---------------------------------------------------------------------------
# Stagnation flow boundary layer (stagnation-flow-boundary-layer leaf)
# ---------------------------------------------------------------------------

def stagnation_velocity_gradient(flow_type: str, u_inf: float,
                                 radius: float) -> float:
    """Potential-flow stagnation velocity gradient a (1/s) at the
    attachment line: 2 U/R (2-D cylinder / Hiemenz) or 1.5 U/R (sphere)."""
    key = str(flow_type).strip().lower()
    _require_positive("u_inf", u_inf)
    _require_positive("radius", radius)
    if key in ("cylinder", "2d", "two-dimensional"):
        return 2.0 * u_inf / radius
    if key in ("sphere", "axisymmetric", "axi"):
        return 1.5 * u_inf / radius
    raise ValueError("flow_type %r not recognized (cylinder/sphere)" % (flow_type,))


def stagnation_bl_thickness(nu: float, a: float) -> float:
    """99-percent laminar BL thickness at a stagnation line: 2.4 sqrt(nu/a)."""
    _require_positive("nu", nu)
    _require_positive("velocity gradient a", a)
    return 2.4 * math.sqrt(nu / a)


def stagnation_wall_shear(mu: float, u_inf: float, a: float, nu: float,
                          fpp: float = 1.2326) -> float:
    """Stagnation-line wall shear tau_w = mu U sqrt(a/nu) fpp (Hiemenz)."""
    _require_positive("mu", mu)
    _require_positive("u_inf", u_inf)
    _require_positive("a", a)
    _require_positive("nu", nu)
    _require_positive("fpp", fpp)
    return mu * u_inf * math.sqrt(a / nu) * fpp


def stagnation_cf(rho: float, u_inf: float, tau_w: float) -> float:
    """Local skin-friction coefficient Cf = tau_w / (0.5 rho U^2)."""
    _require_positive("rho", rho)
    _require_positive("u_inf", u_inf)
    _require_positive("wall shear", tau_w)
    return tau_w / (0.5 * rho * u_inf * u_inf)


# ---------------------------------------------------------------------------
# Aerodynamic heating (aerodynamic-heating + flat-plate heating leaves)
# ---------------------------------------------------------------------------

def stagnation_heat_flux(rho: float, velocity: float, nose_radius: float) -> float:
    """Sutton-Graves stagnation heat flux q_s = C_SG sqrt(rho/Rn) V^3 (W/m2)."""
    _require_positive("rho", rho)
    _require_positive("velocity", velocity)
    _require_positive("nose radius", nose_radius)
    return C_SG * math.sqrt(rho / nose_radius) * velocity ** 3


def radiation_equilibrium_temp(heat_flux: float,
                               emissivity: float = EPS_DEFAULT) -> float:
    """Radiation-equilibrium wall temperature T = (q/(eps sigma))^(1/4), K."""
    _require_nonnegative("heat flux", heat_flux)
    if not (0.0 < emissivity <= 1.0):
        raise ValueError("emissivity must be in (0, 1]")
    return (heat_flux / (emissivity * SIGMA_SB)) ** 0.25


def recovery_factor(regime: str) -> float:
    """Flat-plate recovery factor: sqrt(Pr) laminar, Pr^(1/3) turbulent."""
    key = str(regime).strip().lower()
    if key == "laminar":
        return math.sqrt(PR_AIR)
    if key == "turbulent":
        return PR_AIR ** (1.0 / 3.0)
    raise ValueError("regime must be 'laminar' or 'turbulent'")


def adiabatic_wall_temperature(mach: float, t_inf: float,
                               regime: str) -> float:
    """Adiabatic (recovery) wall temperature T_aw (K)."""
    _require_nonnegative("mach", mach)
    _require_positive("static temperature", t_inf)
    r = recovery_factor(regime)
    return t_inf * (1.0 + r * (GAMMA - 1.0) / 2.0 * mach * mach)


def flat_plate_cold_wall_flux(mach: float, t_inf: float, p_inf: float,
                              t_wall: float, x: float,
                              regime: str) -> Dict:
    """Cold-wall convective heat flux on a flat plate (W/m2).

    Eckert reference temperature T* = T_inf (1 + 0.032 M^2
    + 0.58 (T_wall/T_inf - 1)); Cf at reference conditions (laminar
    0.664/sqrt(Re*), turbulent 0.0592/Re*^0.2); h_c = 0.5 Cf rho* U CP;
    q = h_c (T_aw - T_wall).
    """
    _require_positive("mach", mach)
    _require_positive("static temperature", t_inf)
    _require_positive("static pressure", p_inf)
    _require_positive("wall temperature", t_wall)
    _require_positive("running length x", x)
    key = str(regime).strip().lower()
    if key not in ("laminar", "turbulent"):
        raise ValueError("regime must be 'laminar' or 'turbulent'")
    t_star = t_inf * (1.0 + 0.032 * mach * mach
                      + 0.58 * (t_wall / t_inf - 1.0))
    rho_star = p_inf / (R_GAS * t_star)
    mu_star = (SUTHERLAND_MU0 * t_star ** 1.5) / (t_star + SUTHERLAND_S)
    u_e = mach * speed_of_sound(t_inf)
    re_star = rho_star * u_e * x / mu_star
    if key == "laminar":
        cf = 0.664 / math.sqrt(re_star)
    else:
        cf = 0.0592 / re_star ** 0.2
    h_c = 0.5 * cf * rho_star * u_e * CP_AIR
    t_aw = adiabatic_wall_temperature(mach, t_inf, key)
    return {"t_aw": t_aw, "t_star": t_star, "re_star": re_star,
            "cf": cf, "h_c": h_c, "q_cold_wall": h_c * (t_aw - t_wall)}


# ---------------------------------------------------------------------------
# Bow shock standoff (bow-shock-standoff leaf)
# ---------------------------------------------------------------------------

def bow_shock_standoff_ratio(mach: float, body: str = "sphere") -> float:
    """Billig-form standoff ratio Delta/R on the stagnation streamline."""
    if mach <= 1.0:
        raise ValueError("Mach must exceed 1 for a detached bow shock")
    key = str(body).strip().lower()
    if key == "sphere":
        return 0.143 * math.exp(3.24 / (mach * mach))
    if key == "cylinder":
        return 0.386 * math.exp(4.67 / (mach * mach))
    raise ValueError("body must be 'sphere' or 'cylinder'")


def bow_shock_standoff_distance(mach: float, nose_radius: float,
                                body: str = "sphere") -> float:
    """Detached bow-shock standoff distance Delta (m) ahead of the nose."""
    _require_positive("nose radius", nose_radius)
    return bow_shock_standoff_ratio(mach, body) * nose_radius


# ---------------------------------------------------------------------------
# Flight-condition item: project facts the role needs
# ---------------------------------------------------------------------------

@dataclass
class HighSpeedItem:
    """Vehicle + flight-condition facts for the analysis memo."""
    name: str
    description: str = ""
    # Flight conditions
    cruise_mach: float = 2.0              # supersonic cruise Mach number
    cruise_altitude_m: float = 18288.0    # 60 000 ft
    climb_mach: float = 0.85              # transonic climb/check Mach
    climb_altitude_m: float = 12192.0     # 40 000 ft
    # Configuration
    sweep_deg: float = 66.0               # wing leading-edge sweep (deg)
    mcrit0: float = 0.78                  # unswept-section critical Mach
    t_over_c: float = 0.03                # wing thickness ratio
    cl_cruise: float = 0.12               # cruise lift coefficient (Korn)
    supercritical: bool = True
    cp_min0: float = -0.55                # incompressible peak suction
    section_mach_ahead: float = 1.3       # local Mach ahead of term. shock
    # Geometry
    nose_radius_m: float = 0.05           # nose radius for standoff/heating
    body_length_m: float = 62.0           # equivalent-body length
    body_r_max_m: float = 1.6             # equivalent-body max radius
    intake_deflection_deg: float = 10.0   # intake ramp / wedge deflection
    bl_station_m: float = 6.0             # boundary-layer analysis station
    airfoil_mach: float = 2.0             # diamond-airfoil analysis Mach
    airfoil_alpha_deg: float = 2.0
    airfoil_eps_deg: float = 2.0
    # Surface/thermal facts
    k_s_m: float = 6.0e-6                 # equivalent sand roughness (m)
    skin_emissivity: float = EPS_DEFAULT
    # Climb-point compressibility rows (item inputs)
    karman_tsien_mach: float = 0.70       # subsonic climb leg for KT row
    generated: str = ""


def example_item() -> "HighSpeedItem":
    """Reference item: an SST-class supersonic cruiser flight condition."""
    return HighSpeedItem(
        name="HSX-1 supersonic cruiser (reference flight condition)",
        description="Mach 2.0 supersonic transport configuration, "
                    "subsonic-leading-edge swept wing, mixed-compression "
                    "intake, high-temperature aluminium airframe",
        cruise_mach=2.0, cruise_altitude_m=18288.0,
        climb_mach=0.85, climb_altitude_m=12192.0,
        sweep_deg=66.0, t_over_c=0.03, cl_cruise=0.12,
        supercritical=True, cp_min0=-0.55, section_mach_ahead=1.3,
        nose_radius_m=0.05, body_length_m=62.0, body_r_max_m=1.6,
        intake_deflection_deg=10.0, bl_station_m=6.0,
        airfoil_mach=2.0, airfoil_alpha_deg=2.0, airfoil_eps_deg=2.0,
        k_s_m=6.0e-6, skin_emissivity=EPS_DEFAULT,
        karman_tsien_mach=0.70,
    )


# ---------------------------------------------------------------------------
# Memo builder: computes every number with the formulas above
# ---------------------------------------------------------------------------

def _fmt(v: float, nd: int = 4) -> str:
    return ("%.*f" % (nd, v)).rstrip("0").rstrip(".") if nd else ("%g" % v)


def build_memo(item: HighSpeedItem) -> Dict:
    """Build the complete high-speed analysis memo content model."""
    m = item.cruise_mach
    atm = atmosphere(item.cruise_altitude_m)
    a_cruise = atm["speed_of_sound"]
    v_cruise = m * a_cruise
    q_cruise = 0.5 * atm["density"] * v_cruise ** 2
    rho = atm["density"]
    mu = atm["viscosity"]
    nu = kinematic_viscosity(mu, rho)

    # --- isentropic relations at the cruise Mach --------------------------
    ratios = total_static_ratios(m)
    total = static_to_total(atm["pressure"], atm["temperature"], m)
    aa = area_ratio(m)
    m_sub = mach_from_area_ratio(aa, subsonic=True)   # demo of inverse

    # --- compressibility corrections (climb leg) --------------------------
    kt_mach = item.karman_tsien_mach
    kt_cp = karman_tsien_correction(item.cp_min0, kt_mach)
    pg_cp = prandtl_glauert_correction(item.cp_min0, kt_mach)
    cp_star_climb = critical_pressure_coefficient(item.climb_mach)
    m_crit_section = critical_mach_number(item.cp_min0)
    m_eff_climb = effective_mach(item.climb_mach, item.sweep_deg)
    m_eff_cruise = m * cos_sweep(item.sweep_deg)  # subsonic-LE check
    # m_eff_cruise stays below 1 for a subsonic-leading-edge planform
    if m_eff_cruise >= 1.0:
        raise ValueError("example planform must keep a subsonic leading edge "
                         "(M cos Lambda < 1)")
    k_trans = transonic_similarity_parameter(item.climb_mach, item.t_over_c)
    m_dd = drag_divergence_mach(item.t_over_c, item.cl_cruise,
                                item.supercritical)
    wave_pen_climb = wave_drag_penalty(item.climb_mach, m_dd)
    wave_rise = wave_drag_rise_coef(item.climb_mach, m_dd)
    term_shock = terminating_shock_strength(item.section_mach_ahead)

    # --- shock system at cruise -------------------------------------------
    ns = normal_shock(m)                       # nose / intake normal shock
    obl = oblique_shock(m, item.intake_deflection_deg)   # ramp weak shock
    ref = shock_reflection_verdict(obl["m2"], item.intake_deflection_deg)
    pm = expansion_properties(obl["m2"], item.intake_deflection_deg)
    standoff = bow_shock_standoff_distance(m, item.nose_radius_m, "sphere")
    # intake total-pressure recovery through ramp oblique + terminal normal
    terminal = normal_shock(obl["m2"])
    recovery_total = obl["p02_p01"] * terminal["p02_p01"]
    recovery_single = ns["p02_p01"]
    recovery_gain = recovery_total - recovery_single

    # --- supersonic section + wave drag ------------------------------------
    sea = shock_expansion_airfoil(item.airfoil_mach, item.airfoil_alpha_deg,
                                  item.airfoil_eps_deg)
    dq = sears_haack_wave_drag_area(item.body_length_m, item.body_r_max_m)

    # --- boundary layer at the cruise station ------------------------------
    re_bl = reynolds(rho, v_cruise, item.bl_station_m, mu)
    bl = flat_plate_thicknesses(item.bl_station_m, re_bl)
    cf_loglaw = cf_turbulent_log_law(re_bl)
    x_tr = flat_plate_transition(nu, v_cruise, item.bl_station_m)
    a_stag = stagnation_velocity_gradient("cylinder", v_cruise,
                                          item.nose_radius_m)
    delta_stag = stagnation_bl_thickness(nu, a_stag)
    tau_stag = stagnation_wall_shear(mu, v_cruise, a_stag, nu)
    cf_stag = stagnation_cf(rho, v_cruise, tau_stag)
    u_tau = friction_velocity(v_cruise, bl["cf_local"])
    k_plus = sand_roughness_reynolds(rho, u_tau, item.k_s_m, mu)
    rough = roughness_regime(k_plus)

    # --- heating ------------------------------------------------------------
    q_stag = stagnation_heat_flux(rho, v_cruise, item.nose_radius_m)
    t_rad = radiation_equilibrium_temp(q_stag, item.skin_emissivity)
    t_aw_skin = adiabatic_wall_temperature(m, atm["temperature"], "turbulent")
    t0_stag = total["t0"]        # stagnation-line recovery temperature (r=1)
    fp_heat = flat_plate_cold_wall_flux(m, atm["temperature"],
                                        atm["pressure"], 300.0,
                                        item.bl_station_m, "turbulent")
    skin_margin = SKIN_TEMP_LIMIT_K - t_aw_skin
    # nose margin against the stagnation-line recovery temperature T0, the
    # hot-wall equilibrium ceiling (the Sutton-Graves cold-wall radiation
    # equilibrium T_rad is a conservative screening bound, not the hot wall)
    nose_margin = NOSE_TEMP_LIMIT_K - t0_stag

    margins = [
        {"margin": "Intake total-pressure recovery (2-shock system)",
         "value": recovery_total,
         "requirement": "> single normal-shock recovery %.4f at M %.2f"
                        % (recovery_single, m),
         "source": "stage 4: ramp oblique p02/p01 %.5f x terminal normal "
                   "p02/p01 %.5f" % (obl["p02_p01"], terminal["p02_p01"])},
        {"margin": "Oblique-shock attachment margin (theta_max - theta)",
         "value": obl["theta_max_deg"] - item.intake_deflection_deg,
         "requirement": "> 0 deg (attached weak shock; detached above)",
         "source": "stage 4: theta_max %.2f deg at M %.2f (oblique-shock "
                   "leaf)" % (obl["theta_max_deg"], m)},
        {"margin": "Section drag-divergence margin at cruise "
                   "(M_DD - M_eff,cruise)",
         "value": m_dd - m_eff_cruise,
         "requirement": "> 0 (supercritical section subcritical at the cruise "
                        "effective Mach M_eff %.3f)" % m_eff_cruise,
         "source": "stage 7: Korn rule M_DD = %.3f (t/c %.3f, CL %.2f, %s) "
                   "vs swept section M_eff = M cos(Lambda)"
                   % (m_dd, item.t_over_c, item.cl_cruise,
                      "supercritical" if item.supercritical else "conventional")},
        {"margin": "Section critical-Mach margin at climb "
                   "(M_cr,section - M_eff,climb)",
         "value": m_crit_section - m_eff_climb,
         "requirement": "> 0 (wing section subcritical through the transonic "
                        "climb leg, M_eff %.3f)" % m_eff_climb,
         "source": "stage 3: Cp* crossing M_cr = %.3f for Cp0 = %.2f; "
                   "climb M_eff = M cos(Lambda) = %.3f"
                   % (m_crit_section, item.cp_min0, m_eff_climb)},
        {"margin": "Skin kinetic-heating margin (T_limit - T_aw)",
         "value": skin_margin,
         "requirement": "> 0 (skin screening limit %.0f K vs recovery temp)"
                        % SKIN_TEMP_LIMIT_K,
         "source": "stage 10: T_aw = T (1 + r (g-1)/2 M^2) = %.1f K at M %.2f, "
                   "recovery r = %.4f" % (t_aw_skin, m, recovery_factor("turbulent"))},
        {"margin": "Nose stagnation-temperature margin (T_limit - T0)",
         "value": nose_margin,
         "requirement": "> 0 (nose screening limit %.0f K vs stagnation-line "
                        "recovery temperature T0)" % NOSE_TEMP_LIMIT_K,
         "source": "stage 10: T0 = T (1 + (g-1)/2 M^2) = %.1f K at M %.2f "
                   "(hot-wall ceiling; Sutton-Graves cold-wall flux %.0f "
                   "W/m2 screened separately)" % (t0_stag, m, q_stag)},
    ]

    model = {
        "document_type": "High-Speed Aerodynamic Analysis Memo",
        "status": "draft-for-review",
        "generated": item.generated or date.today().isoformat(),
        "vehicle": item.name,
        "description": item.description,
        # ---- item facts echoed into the memo (single source of truth)
        "facts": {
            "sweep_deg": item.sweep_deg,
            "t_over_c": item.t_over_c, "cl_cruise": item.cl_cruise,
            "supercritical": item.supercritical, "cp_min0": item.cp_min0,
            "section_mach_ahead": item.section_mach_ahead,
            "nose_radius_m": item.nose_radius_m,
            "body_length_m": item.body_length_m,
            "body_r_max_m": item.body_r_max_m,
            "intake_deflection_deg": item.intake_deflection_deg,
            "bl_station_m": item.bl_station_m,
            "k_s_m": item.k_s_m, "emissivity": item.skin_emissivity,
            "karman_tsien_mach": item.karman_tsien_mach,
        },
        # ---- flight condition
        "cruise_mach": m, "cruise_altitude_m": item.cruise_altitude_m,
        "atmosphere": atm, "v_cruise": v_cruise, "q_cruise": q_cruise,
        "climb_mach": item.climb_mach, "climb_altitude_m": item.climb_altitude_m,
        # ---- isentropic relations
        "total_ratios": ratios, "total_conditions": total,
        "area_ratio": aa, "area_ratio_subsonic_root": m_sub,
        # ---- compressibility corrections
        "corrections": {"kt_mach": kt_mach, "cp_min0": item.cp_min0,
                        "kt_cp": kt_cp, "pg_cp": pg_cp,
                        "cp_star_climb": cp_star_climb,
                        "m_crit_section": m_crit_section,
                        "m_eff_climb": m_eff_climb,
                        "m_eff_cruise": m_eff_cruise,
                        "k_transonic": k_trans,
                        "m_dd": m_dd, "wave_pen_climb": wave_pen_climb,
                        "wave_rise": wave_rise,
                        "term_shock_strength": term_shock},
        # ---- shock system
        "shocks": {"normal": ns, "oblique": obl, "reflection": ref,
                   "expansion": pm, "standoff_m": standoff,
                   "terminal_p02_p01": terminal["p02_p01"],
                   "recovery_total": recovery_total,
                   "recovery_single": recovery_single,
                   "recovery_gain": recovery_gain},
        # ---- supersonic section + wave drag
        "airfoil": sea, "wave_drag_area_m2": dq,
        # ---- boundary layer
        "bl": {"re": re_bl, "station_m": item.bl_station_m,
               "flat_plate": bl, "cf_loglaw": cf_loglaw,
               "x_transition_m": x_tr,
               "stagnation": {"gradient_1_per_s": a_stag,
                              "delta_m": delta_stag,
                              "tau_w": tau_stag, "cf": cf_stag},
               "roughness": {"k_plus": k_plus, "regime": rough,
                             "k_s_m": item.k_s_m}},
        # ---- heating
        "heating": {"q_stag": q_stag, "t_rad": t_rad,
                    "t0_stag": t0_stag,
                    "t_aw_skin": t_aw_skin, "flat_plate": fp_heat,
                    "skin_limit_k": SKIN_TEMP_LIMIT_K,
                    "nose_limit_k": NOSE_TEMP_LIMIT_K,
                    "skin_margin": skin_margin, "nose_margin": nose_margin},
        # ---- margins + gates
        "margins": margins,
        "margins_all_ok": all(m["value"] > 0 for m in margins),
    }
    return model


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------

def render_memo_markdown(model: Dict) -> str:
    """Render the memo content model as the deliverable markdown document."""
    atm = model["atmosphere"]
    tot = model["total_conditions"]
    rat = model["total_ratios"]
    corr = model["corrections"]
    sh = model["shocks"]
    bl = model["bl"]
    heat = model["heating"]
    sea = model["airfoil"]
    f = model["facts"]
    lines = [
        "# High-Speed Aerodynamic Analysis Memo",
        "",
        f"**Vehicle:** {model['vehicle']}",
        f"**Status:** {model['status']} (generated {model['generated']})",
        "",
        "## 1. Flight condition summary",
        "",
        (f"- Vehicle: {model['vehicle']}"
         + (f" - {model['description']}" if model.get("description") else "")),
        (f"- Flight condition: cruise M {model['cruise_mach']:.2f} at "
         f"{model['cruise_altitude_m']:.0f} m; transonic climb check M "
         f"{model['climb_mach']:.2f} at {model['climb_altitude_m']:.0f} m"),
        (f"- ISA state at cruise: T {atm['temperature']:.2f} K, p "
         f"{atm['pressure']:.0f} Pa, rho {atm['density']:.4f} kg/m3, a "
         f"{atm['speed_of_sound']:.2f} m/s, mu {atm['viscosity']:.2e} kg/(m s)"),
        (f"- Flow state: V = M a = {model['v_cruise']:.1f} m/s, q = "
         f"{model['q_cruise']:.0f} Pa"),
        (f"- Configuration: swept wing (subsonic leading edge, sweep "
         f"{f['sweep_deg']:.0f} deg), mixed-compression intake (ramp "
         f"deflection {f['intake_deflection_deg']:.1f} deg), equivalent "
         f"body length {f['body_length_m']:.0f} m"),
        "",
        "## 2. Freestream total conditions and Mach-area",
        "",
        (f"- Isentropic total-to-static ratios at M {model['cruise_mach']:.2f}: "
         f"T0/T = {rat['t0_over_t']:.4f}, p0/p = {rat['p0_over_p']:.4f}, "
         f"rho0/rho = {rat['rho0_over_rho']:.4f}"),
        (f"- Total conditions (isentropic, no shock): p0 = {tot['p0']:.0f} Pa, "
         f"T0 = {tot['t0']:.2f} K"),
        (f"- Mach-area: A/A* at M {model['cruise_mach']:.2f} = "
         f"{model['area_ratio']:.4f} (throat needed for isentropic capture); "
         f"subsonic-branch root for the same ratio M = "
         f"{model['area_ratio_subsonic_root']:.4f}"),
        "- Use: intake contraction and nozzle expansion sizing (isentropic-"
        "flow-relations stage).",
        "",
        "## 3. Compressibility corrections and transonic limit",
        "",
        (f"- Karman-Tsien corrected peak suction at M {corr['kt_mach']:.2f}: "
         f"Cp = {corr['cp_min0']:.2f} / (sqrt(1-M^2) + (M^2/(1+sqrt(1-M^2))) "
         f"x Cp/2) = {corr['kt_cp']:.4f} (vs Prandtl-Glauert "
         f"{corr['pg_cp']:.4f})"),
        (f"- Critical pressure coefficient at climb M {model['climb_mach']:.2f}: "
         f"Cp* = {corr['cp_star_climb']:.4f}"),
        (f"- Section critical Mach from Cp0 = {corr['cp_min0']:.2f}: "
         f"M_cr = {corr['m_crit_section']:.4f} (Cp* crossing solve)"),
        (f"- Sweep effect: M_eff = M cos(Lambda): climb M "
         f"{model['climb_mach']:.2f} x cos({f['sweep_deg']:.0f} deg) = "
         f"{corr['m_eff_climb']:.4f}; cruise M_eff = {corr['m_eff_cruise']:.4f} "
         f"(subsonic leading edge)"),
        (f"- Korn drag-divergence Mach (t/c {f['t_over_c']:.3f}, cruise CL "
         f"{f['cl_cruise']:.2f}): M_DD = {corr['m_dd']:.3f}; transonic wave-"
         f"drag penalty at climb M {model['climb_mach']:.2f} = "
         f"{corr['wave_pen_climb']:.4f} (0 below M_DD), parabolic rise "
         f"{corr['wave_rise']:.4f}"),
        (f"- Terminating-shock strength at local M {f['section_mach_ahead']:.2f}: "
         f"p2/p1 = {corr['term_shock_strength']:.4f}"),
        (f"- Transonic similarity parameter K = (1 - M^2)/tau^(2/3) = "
         f"{corr['k_transonic']:.3f}"),
        "",
        "## 4. Shock system at the cruise Mach",
        "",
        (f"- Normal shock at nose/inlet face, M1 = {model['cruise_mach']:.2f}: "
         f"M2 = {sh['normal']['m2']:.4f}, p2/p1 = {sh['normal']['p2_p1']:.4f}, "
         f"T2/T1 = {sh['normal']['t2_t1']:.4f}, rho2/rho1 = "
         f"{sh['normal']['rho2_rho1']:.4f}, p02/p01 = "
         f"{sh['normal']['p02_p01']:.4f}"),
        (f"- Intake ramp oblique shock, theta = {f['intake_deflection_deg']:.1f} "
         f"deg at M {model['cruise_mach']:.2f} (weak): beta = "
         f"{sh['oblique']['beta_deg']:.2f} deg, M2 = {sh['oblique']['m2']:.3f}, "
         f"p2/p1 = {sh['oblique']['p2_p1']:.4f}, p02/p01 = "
         f"{sh['oblique']['p02_p01']:.4f}; theta_max = "
         f"{sh['oblique']['theta_max_deg']:.2f} deg"),
        (f"- Terminal normal shock at M2 = {sh['oblique']['m2']:.3f}: p02/p01 "
         f"= {sh['terminal_p02_p01']:.4f}"),
        (f"- Intake recovery: 2-shock p02/p01 = {sh['recovery_total']:.4f} "
         f"vs single normal shock {sh['recovery_single']:.4f} (gain "
         f"+{sh['recovery_gain']:.4f})"),
        (f"- Regular shock reflection at (M {sh['oblique']['m2']:.3f}, "
         f"theta {f['intake_deflection_deg']:.1f} deg): verdict "
         f"{sh['reflection']['verdict']} ({sh['reflection']['reason']})"),
        (f"- Aft expansion (Prandtl-Meyer), turn "
         f"{f['intake_deflection_deg']:.1f} deg from M "
         f"{sh['oblique']['m2']:.3f}: M = {sh['expansion']['m2']:.3f}, p2/p1 = "
         f"{sh['expansion']['pressure_ratio_p2_p1']:.4f}"),
        (f"- Detached bow shock at the nose (sphere, R = "
         f"{f['nose_radius_m']:.3f} m): standoff Delta = "
         f"{sh['standoff_m']:.4f} m (Billig correlation, Delta/R = "
         f"{sh['standoff_m']/f['nose_radius_m']:.4f})"),
        "",
        "## 5. Supersonic section analysis and wave drag",
        "",
        (f"- Shock-expansion diamond airfoil at M {sea['m1']:.2f}, alpha "
         f"{sea['alpha_deg']:.1f} deg, half-angle {sea['eps_deg']:.1f} deg: "
         f"cl = {sea['cl']:.4f}, cd_wave = {sea['cd_wave']:.5f}, "
         f"cm_le = {sea['cm_le']:.4f}"),
        (f"- Surface Cp (uf/ur/lf/lr): {sea['surface_cp']['uf']:.4f} / "
         f"{sea['surface_cp']['ur']:.4f} / {sea['surface_cp']['lf']:.4f} / "
         f"{sea['surface_cp']['lr']:.4f}"),
        (f"- Zero-lift wave drag area (Sears-Haack equivalent body, L = "
         f"{f['body_length_m']:.0f} m, r_max = {f['body_r_max_m']:.1f} m): "
         f"D/q = (9 pi/2)(A_max/L)^2 = {model['wave_drag_area_m2']:.4f} m2"),
        "",
        "## 6. Boundary layer and skin friction",
        "",
        (f"- Station x = {bl['station_m']:.1f} m at cruise: Re = rho V x / mu = "
         f"{bl['re']:.3e} ({bl['flat_plate']['regime']} flat-plate regime)"),
        (f"- Flat-plate thickness: delta = {bl['flat_plate']['delta']:.5f} m, "
         f"delta* = {bl['flat_plate']['delta_star']:.5f} m, theta = "
         f"{bl['flat_plate']['theta']:.5f} m, H = "
         f"{bl['flat_plate']['shape_factor']:.3f}"),
        (f"- Skin friction: Cf_local = {bl['flat_plate']['cf_local']:.5f} "
         f"(1/7 power), Cf_avg = {bl['flat_plate']['cf_average']:.5f}, "
         f"log-law Cf = {bl['cf_loglaw']:.5f}"),
        (f"- Transition: Michel/Thwaites flat-plate natural transition at "
         f"x_tr = {_bl_x_tr(bl):.3f} m ({_bl_x_tr_frac(bl):.0f}% of the "
         f"analysis station)"),
        (f"- Attachment-line (Hiemenz 2-D) layer at the nose: a = 2U/R = "
         f"{bl['stagnation']['gradient_1_per_s']:.0f} 1/s, delta = "
         f"{bl['stagnation']['delta_m']:.6f} m, Cf = "
         f"{bl['stagnation']['cf']:.5f}"),
        (f"- Surface roughness: k_s = {bl['roughness']['k_s_m']:.1e} m -> "
         f"k+ = {bl['roughness']['k_plus']:.3f} "
         f"({bl['roughness']['regime']}; smooth retained below k+ = 5)"),
        "",
        "## 7. Aerodynamic heating screen",
        "",
        (f"- Stagnation point (Sutton-Graves): q_s = C_SG sqrt(rho/Rn) V^3 = "
         f"{heat['q_stag']:.0f} W/m2; radiation-equilibrium T = "
         f"{heat['t_rad']:.0f} K (eps {f['emissivity']:.2f})"),
        (f"- Flat-plate skin: recovery factor r = Pr^(1/3) = "
         f"{RECOVERY_TURBULENT:.4f} (turbulent); adiabatic wall temperature "
         f"T_aw = T (1 + r (g-1)/2 M^2) = {heat['t_aw_skin']:.1f} K"),
        (f"- Cold-wall skin flux at x = {bl['station_m']:.1f} m (Eckert "
         f"reference temp, T_wall 300 K): q = "
         f"{heat['flat_plate']['q_cold_wall']:.0f} W/m2, Cf = "
         f"{heat['flat_plate']['cf']:.5f} at Re* = "
         f"{heat['flat_plate']['re_star']:.3e}"),
        (f"- Screening margins: skin {heat['skin_margin']:.1f} K below the "
         f"{heat['skin_limit_k']:.0f} K limit; nose {heat['nose_margin']:.0f} K "
         f"below the {heat['nose_limit_k']:.0f} K limit"),
        "",
        "## 8. Margin summary",
        "",
        "| Margin | Value | Requirement | Source (stage) |",
        "|---|---|---|---|",
    ]
    for mr in model["margins"]:
        lines.append(f"| {mr['margin']} | {mr['value']:.4f} | "
                     f"{mr['requirement']} | {mr['source']} |")
    lines += [
        "",
        "---",
        "*DRAFT - for human high-speed aerodynamics lead review. Not an "
        "approval document.*",
    ]
    return "\n".join(lines)


# --- small renderer helpers --------------------------------------------------

def _bl_x_tr(bl: Dict) -> float:
    return bl["x_transition_m"] if bl["x_transition_m"] is not None else float("nan")


def _bl_x_tr_frac(bl: Dict) -> float:
    x = bl["x_transition_m"]
    return 100.0 * (x if x is not None else 0.0) / bl["station_m"]


# ---------------------------------------------------------------------------
# Evidence gate checkers
# ---------------------------------------------------------------------------

GATE_CHECKS = {
    "condition_identified": "vehicle name and cruise Mach/altitude present",
    "numbers_real": "computed compressible-flow numbers are finite and in domain",
    "shock_consistent": "normal shock decelerates (M2<1); oblique shock attached",
    "recovery_physical": "total-pressure recoveries in (0,1); 2-shock gain positive",
    "corrections_physical": "Cp* negative; Karman-Tsien correction exceeds P-G",
    "bl_physical": "boundary-layer thickness positive; Cf in (0, 0.01]",
    "heating_screened": "kinetic-heating margins positive against screening limits",
    "margins_traced": "every margin row names its workflow stage source",
    "sign_off_honest": "memo is marked draft-for-review, not approval",
}


def check_memo(model: Dict) -> Dict:
    """Run the evidence gates against a memo content model."""
    def _num(key):
        v = model.get(key)
        return isinstance(v, (int, float)) and math.isfinite(v)

    corr = model.get("corrections", {})
    sh = model.get("shocks", {})
    bl = model.get("bl", {})
    heat = model.get("heating", {})
    ns = sh.get("normal", {})
    obl = sh.get("oblique", {})
    margins = model.get("margins", [])
    results = {
        "condition_identified": (bool(model.get("vehicle"))
                                 and _num("cruise_mach")
                                 and model["cruise_mach"] > 1.0
                                 and _num("cruise_altitude_m")),
        "numbers_real": all([
            _num("area_ratio"), _num("v_cruise"), _num("q_cruise"),
            isinstance(model.get("total_ratios", {}).get("p0_over_p"), float),
            model["total_ratios"]["p0_over_p"] > 1.0,
            model["area_ratio"] >= 1.0,
            isinstance(corr.get("m_dd"), float) and 0.5 < corr["m_dd"] < 1.0,
            isinstance(bl.get("re"), float) and bl["re"] > 0.0,
        ]),
        "shock_consistent": (
            ns.get("m2") is not None and 0.0 < ns["m2"] < 1.0
            and ns.get("p2_p1", 0.0) > 1.0
            and obl.get("beta_deg") is not None
            and obl["beta_deg"] > mach_angle(model["cruise_mach"])
            and obl["m2"] is not None and obl["m2"] > 1.0),
        "recovery_physical": (
            0.0 < sh.get("recovery_single", 0.0) < 1.0
            and 0.0 < sh.get("recovery_total", 0.0) < 1.0
            and sh.get("recovery_gain", 0.0) > 0.0
            and sh.get("reflection", {}).get("verdict") in ("regular", "mach")),
        "corrections_physical": (
            corr.get("cp_star_climb") is not None and corr["cp_star_climb"] < 0.0
            and corr.get("kt_cp") is not None
            and abs(corr["kt_cp"]) > abs(corr.get("pg_cp", 0.0))
            and corr.get("m_eff_cruise", 1.0) < 1.0
            and corr.get("m_crit_section") is not None
            and corr["m_crit_section"] > corr.get("m_eff_climb", 0.0)
            and corr.get("m_dd", 0.0) > corr.get("m_eff_cruise", 0.0)),
        "bl_physical": (
            bl.get("flat_plate", {}).get("delta", 0.0) > 0.0
            and bl["flat_plate"]["cf_local"] > 0.0
            and bl["flat_plate"]["cf_local"] < 0.01
            and bl["flat_plate"]["shape_factor"] > 1.0
            and bl.get("stagnation", {}).get("delta_m", 0.0) > 0.0
            and bl.get("roughness", {}).get("k_plus", -1.0) >= 0.0),
        "heating_screened": (
            heat.get("q_stag", 0.0) > 0.0
            and heat.get("skin_margin", 0.0) > 0.0
            and heat.get("nose_margin", 0.0) > 0.0
            and heat.get("t_aw_skin", 0.0) > 200.0),
        "margins_traced": (len(margins) >= 4
                           and all("stage " in str(m.get("source", ""))
                                   for m in margins)),
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_memo_markdown(md_text: str) -> Dict:
    """Gate-check the rendered markdown deliverable (zero blanks allowed)."""
    low = md_text.lower().replace("_", "").replace("-", " ")
    checks = {
        "has_title": "high-speed aerodynamic analysis memo" in md_text.lower(),
        "has_vehicle": bool(re.search(r"\*\*vehicle:\*\*", md_text, re.I)),
        "has_sections": all(re.search(rf"^## {n}\. ", md_text, re.M)
                            for n in range(1, 9)),
        "has_key_numbers": all(key in low for key in (
            "total to static", "karman tsien", "normal shock",
            "total pressure recovery", "margins")),
        "has_no_blanks": not re.search(r"_{3,}|TBD|\bOPEN item\b", md_text),
        "has_draft_marker": "draft" in md_text.lower(),
        "has_not_approval": "not an approval" in md_text.lower(),
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> Dict:
    """Public entry point used by gate tooling: check a memo document."""
    return check_memo_markdown(md_text)


# ---------------------------------------------------------------------------
# Example item + worked example
# ---------------------------------------------------------------------------

def example_memo_markdown() -> str:
    return render_memo_markdown(build_memo(example_item()))


if __name__ == "__main__":
    model = build_memo(example_item())
    md = render_memo_markdown(model)
    print("VEHICLE: %s" % model["vehicle"])
    print("CRUISE M: %.2f   p0/p: %.4f   A/A*: %.4f   recovery2: %.4f"
          % (model["cruise_mach"], model["total_ratios"]["p0_over_p"],
             model["area_ratio"], model["shocks"]["recovery_total"]))
    print("M_DD: %.3f   M_cr,section: %.3f   M_eff,cruise: %.3f"
          % (model["corrections"]["m_dd"], model["corrections"]["m_crit_section"],
             model["corrections"]["m_eff_cruise"]))
    print("GATES: %s" % check_memo(model))
    print("RENDERED: %d chars" % len(md))
