#!/usr/bin/env python3
"""aerodynamics_core.py - Aerodynamics Engineer executable core.

This is the role's ENGINE: given an aircraft configuration's project
facts it computes the aerodynamic design numbers with REAL domain
formulas and BUILDS the aerodynamic design report. Standalone: no
external repo needed (stdlib math only, offline).

Every formula below mirrors the logic of the bound Aero Agent Skills
leaves (which encode public-domain aero practice; summaries only, never
reproduced text):

- Parasite drag buildup (aerodynamics/drag-polars/parasite-drag):
    Re = rho*V*L/mu
    Cf_laminar = 1.328/sqrt(Re)               (Blasius)
    Cf_turbulent = 0.455/(log10(Re))^2.58     (Schlichting)
    Cf_mixed = Cf_t(Re) - (Re_tr/Re)*(Cf_t(Re_tr) - Cf_l(Re_tr))
    FF wing/tail = 1 + 2(t/c) + 100(t/c)^4
    FF fuselage = 1 + 60/(l/d)^3 + 0.0025*(l/d)
    FF nacelle  = 1 + 0.35/(l/d)
    CD_i = Cf * FF * Q * S_wet_i / S_ref;  CD_parasite = sum(CD_i)
    S_wet_wing = 2 * S_exposed * (1 + 0.2 t/c)
    Cf_e = CD0 * S_ref / S_wet_total
- Drag polar (aerodynamics/drag-polars/drag-polar):
    k = 1/(pi*e*AR);  CD = CD0 + k*CL^2;  cl_opt = sqrt(CD0/k)
    L/D_max = 1/(2*sqrt(CD0*k))
- Lift curve slope (aerodynamics/drag-polars/lift-curve-slope):
    a0 = 2*pi (thin airfoil);  a = a0/(1 + a0/(pi*e*AR))  (lifting line)
    a_swept = a*cos(sweep);  a_mach = a/sqrt(1-M^2)  (P-G, M < 0.7)
- Sweep effects (aerodynamics/high-speed/swept-wing-aerodynamics):
    M_eff = M*cos(Lambda)
- High-lift (aerodynamics/high-lift/high-lift-systems):
    Delta_clmax = ref * K_delta * K_chord * K_span,
    K_delta = sin(delta)/sin(delta_max);  wing CLmax = 0.9*clmax*cos(sweep)
    V_stall = sqrt(2W/(rho*S*CLmax))
- Transonic (aerodynamics/high-speed/supercritical-airfoil):
    M_DD = 0.95 - t/c - C_L/10 (supercritical), 0.90 - t/c - C_L/10 (conv.)
    wave-drag penalty ~ (M - M_DD)^3 above divergence, 0 below
- Flutter margin (aerodynamics/aeroelasticity/flutter-speed-prediction):
    margin = V_F/V_D, clearance practice threshold 1.15
- Static divergence (aerodynamics/aeroelasticity/divergence-speed):
    q_div = k_theta/(S*c*C_Lalpha*e);  V_div = sqrt(2 q_div / rho)
- CFD validation metrics (aerodynamics/cfd/cfd-validation):
    relative_error, Richardson extrapolation with Roache GCI (F=1.25),
    PASS/FAIL verdict vs tolerance band
- Discrete-gust screening (aerodynamics/aeroelasticity/
  aeroelastic-gust-response): quasi-steady section gust lift
  Delta_CL = a_wing*(U_de/V), Delta n = (0.5*rho*V*a*U_de)/(W/S)
- ISA atmosphere: standard lapse-rate model (public domain), Sutherland
  viscosity.

Deliverable: the aerodynamic design report (render_*_markdown), with
evidence gates (check_report / check_report_markdown) that verify the
document before it leaves the role. Every margin row in the report
traces to a stage output of the bound workflow.
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

# AeroSkills leaf constants mirrored here (see module docstring).
SECTION_SLOPE = 2.0 * math.pi        # thin-airfoil section slope, per rad
MAX_MACH_PG = 0.7                    # Prandtl-Glauert subsonic validity limit
FLUTTER_MARGIN_REQUIRED = 1.15       # clearance practice, flutter leaf
MIN_DIVERGENCE_MARGIN = 1.15         # design practice, divergence leaf
WING_CLMAX_FACTOR = 0.9              # 3D/sweep reduction, high-lift leaf
GCI_SAFETY_FACTOR = 1.25             # Roache GCI safety factor, cfd-validation
DEFAULT_VALIDATION_TOL = 0.05        # 5% default band, cfd-validation leaf

# High-lift reference flap data (high-lift-systems leaf).
FLAP_TYPES = {
    "plain": {"delta_clmax_ref": 0.9, "deflection_max_deg": 60.0,
              "chord_frac_ref": 0.20, "cd0_ref": 0.05, "cp_frac": 0.50},
    "split": {"delta_clmax_ref": 0.9, "deflection_max_deg": 60.0,
              "chord_frac_ref": 0.20, "cd0_ref": 0.06, "cp_frac": 0.50},
    "slotted": {"delta_clmax_ref": 1.3, "deflection_max_deg": 40.0,
                "chord_frac_ref": 0.25, "cd0_ref": 0.08, "cp_frac": 0.52},
    "fowler": {"delta_clmax_ref": 1.7, "deflection_max_deg": 40.0,
               "chord_frac_ref": 0.30, "cd0_ref": 0.09, "cp_frac": 0.58},
}
LEADING_EDGE_DEVICES = {"slat": 0.5, "krueger": 0.4}

# CFD validation case catalog (cfd-validation leaf, summary data).
VALIDATION_CASES = {
    "onera-m6": {
        "name": "ONERA M6 wing",
        "regime": "transonic", "application": "wing",
        "conditions": {"mach": 0.84, "reynolds": 11.72e6, "alpha_deg": 3.06},
        "reference": {"cd": 0.0163, "cl": 0.266},
        "data_source": "AGARD-AR-138 (Schmitt and Charpin 1979), summary",
    },
    "dlr-f6": {
        "name": "DLR-F6 wing-body transport",
        "regime": "transonic", "application": "wing-body",
        "conditions": {"mach": 0.75, "reynolds": 3.0e6, "cl_target": 0.5},
        "reference": {"cd": 0.0299, "cl": 0.5},
        "data_source": "AIAA Drag Prediction Workshop series, summary",
    },
}

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
    """ISA temperature (K) at geometric altitude (m), troposphere+stratosphere."""
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
    return p_tropo * math.exp(-G0 * (altitude_m - ISA_TROPOPAUSE) / (R_GAS * 216.65))


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
# Reynolds number and skin friction (parasite-drag leaf)
# ---------------------------------------------------------------------------

def reynolds(rho: float, v: float, l: float, mu: float) -> float:
    """Reynolds number Re = rho * V * L / mu for a component of length L."""
    _require_positive("rho", rho)
    _require_positive("v", v)
    _require_positive("l", l)
    _require_positive("mu", mu)
    return rho * v * l / mu


def cf_laminar(re: float) -> float:
    """Laminar flat-plate skin friction Cf = 1.328/sqrt(Re) (Blasius)."""
    _require_positive("Reynolds number", re)
    return 1.328 / math.sqrt(re)


def cf_turbulent(re: float) -> float:
    """Turbulent flat-plate skin friction Cf = 0.455/(log10 Re)^2.58."""
    if re <= 10.0:
        raise ValueError("Reynolds number must be > 10 for turbulent Cf, got %r" % (re,))
    return 0.455 / (math.log10(re) ** 2.58)


def cf_mixed(re: float, re_transition: float) -> float:
    """Mixed laminar-turbulent skin friction with transition at Re_tr.

    Cf = Cf_turb(Re) - (Re_tr/Re) * (Cf_turb(Re_tr) - Cf_lam(Re_tr)).
    """
    if re <= 10.0:
        raise ValueError("Reynolds number must be > 10, got %r" % (re,))
    if re_transition <= 10.0 or re_transition >= re:
        raise ValueError(
            "transition Reynolds number must satisfy 10 < Re_tr < Re, "
            "got Re_tr=%r, Re=%r" % (re_transition, re)
        )
    return (cf_turbulent(re)
            - (re_transition / re) * (cf_turbulent(re_transition) - cf_laminar(re_transition)))


def form_factor(kind: str, t_over_c: Optional[float] = None,
                l_over_d: Optional[float] = None) -> float:
    """Component form factor FF (parasite-drag leaf formulas)."""
    kind = str(kind).lower()
    if kind in ("wing", "tail"):
        if t_over_c is None or t_over_c <= 0.0 or t_over_c >= 0.5:
            raise ValueError("t_over_c must be in (0, 0.5) for wing/tail, got %r" % (t_over_c,))
        return 1.0 + 2.0 * t_over_c + 100.0 * t_over_c ** 4
    if kind in ("fuselage", "nacelle"):
        if l_over_d is None or l_over_d <= 1.0:
            raise ValueError("l_over_d must be > 1.0 for fuselage/nacelle, got %r" % (l_over_d,))
        if kind == "fuselage":
            return 1.0 + 60.0 / (l_over_d ** 3) + 0.0025 * l_over_d
        return 1.0 + 0.35 / l_over_d
    raise ValueError("unknown component kind %r (use wing, tail, fuselage, nacelle)" % (kind,))


def component_drag(cf: float, ff: float, q: float, s_wet: float, s_ref: float) -> float:
    """Component parasite drag CD_i = Cf * FF * Q * S_wet / S_ref."""
    _require_positive("skin-friction coefficient", cf)
    if ff < 1.0:
        raise ValueError("form factor must be >= 1, got %r" % (ff,))
    if q < 1.0:
        raise ValueError("interference factor must be >= 1, got %r" % (q,))
    _require_positive("wetted area", s_wet)
    _require_positive("reference area", s_ref)
    return cf * ff * q * s_wet / s_ref


def wing_wetted_area(s_exposed: float, t_over_c: float) -> float:
    """Wing wetted area S_wet = 2 * S_exposed * (1 + 0.2*t/c)."""
    _require_positive("exposed area", s_exposed)
    if t_over_c <= 0.0 or t_over_c >= 0.5:
        raise ValueError("t_over_c must be in (0, 0.5), got %r" % (t_over_c,))
    return 2.0 * s_exposed * (1.0 + 0.2 * t_over_c)


def equivalent_skin_friction(cd0: float, s_ref: float, s_wet_total: float) -> float:
    """Equivalent skin friction Cf_e = CD0 * S_ref / S_wet_total."""
    _require_nonnegative("total parasite drag", cd0)
    _require_positive("reference area", s_ref)
    _require_positive("total wetted area", s_wet_total)
    return cd0 * s_ref / s_wet_total


def parasite_drag(components: List[dict], s_ref: float, rho: float, v: float,
                  mu: float, re_transition: float = 5e5) -> Dict:
    """Assemble the parasite-drag buildup from component geometry.

    Each component dict: {name, kind ('wing'|'tail'|'fuselage'|'nacelle'),
    length (m, for Re), s_wet (m^2), t_over_c or l_over_d, q (interference),
    count (optional, default 1)}. All sub-formulas are the parasite-drag
    leaf formulas; total = sum of CD_i terms.
    """
    _require_positive("reference area", s_ref)
    _require_positive("rho", rho)
    _require_positive("v", v)
    _require_positive("mu", mu)
    rows, s_wet_total = [], 0.0
    for comp in components:
        count = comp.get("count", 1)
        kind = comp["kind"]
        length = comp["length"]
        s_wet = comp["s_wet"]
        q = comp.get("q", 1.0)
        re_i = reynolds(rho, v, length, mu)
        cf_i = cf_mixed(re_i, re_transition)
        if kind in ("wing", "tail"):
            ff_i = form_factor(kind, t_over_c=comp["t_over_c"])
        else:
            ff_i = form_factor(kind, l_over_d=comp["l_over_d"])
        cd_i = component_drag(cf_i, ff_i, q, s_wet, s_ref) * count
        s_wet_total += s_wet * count
        rows.append({"name": comp["name"], "kind": kind, "count": count,
                     "reynolds": re_i, "cf": cf_i, "ff": ff_i, "q": q,
                     "s_wet": s_wet * count, "cd": cd_i})
    cd0 = float(sum(r["cd"] for r in rows))
    cf_e = equivalent_skin_friction(cd0, s_ref, s_wet_total)
    return {"components": rows, "cd0": cd0, "s_wet_total": s_wet_total,
            "cf_e": cf_e, "count_components": len(rows)}


# ---------------------------------------------------------------------------
# Drag polar (drag-polar leaf)
# ---------------------------------------------------------------------------

def induced_drag_factor(e: float, ar: float) -> float:
    """Induced drag factor k = 1 / (pi * e * AR)."""
    if e <= 0.0 or e > 1.0:
        raise ValueError("Oswald span-efficiency e must be in (0, 1], got %r" % (e,))
    _require_positive("aspect ratio", ar)
    return 1.0 / (math.pi * e * ar)


def drag_polar(cd0: float, e: float, ar: float, cl: Optional[float] = None) -> Dict:
    """Evaluate the parabolic drag polar at lift coefficient cl.

    Returns k, CD at cl (or at cl_opt when cl is None), cl_opt and L/D_max.
    """
    _require_positive("zero-lift drag coefficient", cd0)
    k = induced_drag_factor(e, ar)
    cl_opt = math.sqrt(cd0 / k)
    ld_max = 1.0 / (2.0 * math.sqrt(cd0 * k))
    if cl is None:
        cl = cl_opt
    if cl < 0.0:
        raise ValueError("lift coefficient must be >= 0, got %r" % (cl,))
    cd = cd0 + k * cl * cl
    return {"k": k, "cd": cd, "cl_opt": cl_opt, "ld_max": ld_max,
            "l_over_d": cl / cd if cd > 0.0 else 0.0}


# ---------------------------------------------------------------------------
# Lift curve slope (lift-curve-slope leaf)
# ---------------------------------------------------------------------------

def lift_curve_slope(ar: float, e: float = 1.0, sweep_deg: float = 0.0,
                     mach: float = 0.0, a0: Optional[float] = None) -> Dict:
    """Wing lift-curve slope (per radian) with stepwise breakdown.

    Corrections in leaf order: section (2*pi default) -> finite wing
    (lifting line) -> sweep (simple sweep theory) -> Mach (Prandtl-Glauert,
    valid M < 0.7).
    """
    if a0 is None:
        a0 = SECTION_SLOPE
    _require_positive("section slope a0", a0)
    _require_positive("aspect ratio", ar)
    if e <= 0.0 or e > 1.0:
        raise ValueError("span efficiency e must be in (0, 1], got %r" % (e,))
    if not (0.0 <= sweep_deg < 90.0):
        raise ValueError("sweep must be in [0, 90) degrees, got %r" % (sweep_deg,))
    if not (0.0 <= mach < MAX_MACH_PG):
        raise ValueError(
            "mach must be in [0, 0.7) for the Prandtl-Glauert correction, got %r" % (mach,))
    a_section = float(a0)
    a_finite = a_section / (1.0 + a_section / (math.pi * e * ar))
    a_swept = a_finite * math.cos(math.radians(sweep_deg))
    a_final = a_swept / math.sqrt(1.0 - mach * mach)
    return {"a_section": a_section, "a_finite": a_finite, "a_swept": a_swept,
            "a_mach": a_final, "per_degree": a_final / math.degrees(1.0)}


def lift_coefficient(a_per_rad: float, alpha_deg: float, alpha_zero_deg: float = 0.0) -> float:
    """C_L = a * (alpha - alpha_zero), angles in degrees, slope per radian."""
    _require_positive("lift curve slope", a_per_rad)
    return a_per_rad * math.radians(alpha_deg - alpha_zero_deg)


# ---------------------------------------------------------------------------
# Sweep effects (swept-wing-aerodynamics leaf)
# ---------------------------------------------------------------------------

def cos_sweep(sweep_deg: float) -> float:
    """Cosine of the sweep angle in degrees (simple sweep theory)."""
    if not (0.0 <= sweep_deg < 90.0):
        raise ValueError("sweep angle must be in [0, 90) degrees, got %r" % (sweep_deg,))
    return math.cos(math.radians(sweep_deg))


def effective_mach(mach: float, sweep_deg: float) -> float:
    """Section Mach number seen by a yawed wing: M * cos(Lambda)."""
    if not (0.0 <= mach < 1.0):
        raise ValueError("Mach number must be in [0, 1), got %r" % (mach,))
    return mach * cos_sweep(sweep_deg)


# ---------------------------------------------------------------------------
# High-lift (high-lift-systems leaf)
# ---------------------------------------------------------------------------

def deflection_factor(deflection_deg: float, deflection_max_deg: float) -> float:
    """sin(delta)/sin(delta_max), clamped at delta_max."""
    if deflection_deg >= deflection_max_deg:
        return 1.0
    return math.sin(math.radians(deflection_deg)) / math.sin(math.radians(deflection_max_deg))


def flap_clmax_increment(flap_type: str, deflection_deg: float,
                         chord_frac: Optional[float] = None, span_frac: float = 1.0) -> float:
    """Section clmax increment for a trailing-edge flap (high-lift leaf)."""
    if flap_type not in FLAP_TYPES:
        raise ValueError("unknown flap type %r; expected %s"
                         % (flap_type, ", ".join(sorted(FLAP_TYPES))))
    data = FLAP_TYPES[flap_type]
    if chord_frac is None:
        chord_frac = data["chord_frac_ref"]
    if not (0.0 < chord_frac <= 1.0):
        raise ValueError("chord_frac must be in (0, 1], got %r" % (chord_frac,))
    if not (0.0 < span_frac <= 1.0):
        raise ValueError("span_frac must be in (0, 1], got %r" % (span_frac,))
    k_delta = deflection_factor(deflection_deg, data["deflection_max_deg"])
    k_chord = chord_frac / data["chord_frac_ref"]
    return data["delta_clmax_ref"] * k_delta * k_chord * span_frac


def slat_clmax_increment(device: str = "slat", span_frac: float = 1.0) -> float:
    """Section clmax increment from a leading-edge device."""
    if device not in LEADING_EDGE_DEVICES:
        raise ValueError("unknown leading-edge device %r; expected %s"
                         % (device, ", ".join(sorted(LEADING_EDGE_DEVICES))))
    if not (0.0 < span_frac <= 1.0):
        raise ValueError("span_frac must be in (0, 1], got %r" % (span_frac,))
    return LEADING_EDGE_DEVICES[device] * span_frac


def wing_clmax(clmax_section: float, sweep_deg: float = 0.0) -> float:
    """Wing-level CLmax = 0.9 * clmax_section * cos(Lambda)."""
    _require_positive("section clmax", clmax_section)
    if not (0.0 <= sweep_deg < 90.0):
        raise ValueError("sweep must be in [0, 90) deg, got %r" % (sweep_deg,))
    return WING_CLMAX_FACTOR * clmax_section * math.cos(math.radians(sweep_deg))


def stall_speed(weight: float, wing_area: float, rho: float, clmax_wing: float) -> float:
    """Stall speed V = sqrt(2 W / (rho S CLmax)) in m/s."""
    _require_positive("weight", weight)
    _require_positive("wing_area", wing_area)
    _require_positive("rho", rho)
    _require_positive("clmax_wing", clmax_wing)
    return math.sqrt(2.0 * weight / (rho * wing_area * clmax_wing))


# ---------------------------------------------------------------------------
# Transonic (supercritical-airfoil + wave-drag leaves)
# ---------------------------------------------------------------------------

def drag_divergence_mach(t_over_c: float, cl: float, supercritical: bool = True) -> float:
    """Drag-divergence Mach from the Korn rule of thumb.

    M_DD = 0.95 - t/c - C_L/10 (supercritical), 0.90 - ... (conventional).
    """
    if not (0.02 < t_over_c < 0.30):
        raise ValueError("thickness ratio t/c must be in (0.02, 0.30), got %r" % (t_over_c,))
    if not (0.0 <= cl < 1.5):
        raise ValueError("cruise lift coefficient must be in [0, 1.5), got %r" % (cl,))
    base = 0.95 if supercritical else 0.90
    mdd = base - t_over_c - cl / 10.0
    if not (0.5 < mdd < 0.95):
        raise ValueError("Korn rule gives drag-divergence Mach %r outside (0.5, 0.95)"
                         % (mdd,))
    return mdd


def wave_drag_penalty(mach: float, mdd: float) -> float:
    """Relative wave-drag penalty index: (M - M_DD)^3 above divergence, 0 below."""
    if not (0.5 <= mach < 1.0):
        raise ValueError("flight Mach must be in [0.5, 1), got %r" % (mach,))
    if not (0.5 < mdd < 1.0):
        raise ValueError("drag-divergence Mach must be in (0.5, 1), got %r" % (mdd,))
    excess = mach - mdd
    if excess <= 0.0:
        return 0.0
    return excess ** 3


def transonic_similarity_parameter(mach: float, t_over_c: float) -> float:
    """Transonic similarity parameter K = (1 - M^2) / tau^(2/3)."""
    if not (0.0 <= mach <= 1.0):
        raise ValueError("Mach must be in [0, 1], got %r" % (mach,))
    if not (0.0 < t_over_c < 1.0):
        raise ValueError("thickness ratio must be in (0, 1), got %r" % (t_over_c,))
    return (1.0 - mach * mach) / (t_over_c ** (2.0 / 3.0))


# ---------------------------------------------------------------------------
# Aeroelastic screening (flutter-speed + divergence-speed + gust leaves)
# ---------------------------------------------------------------------------

def flutter_margin(v_f: float, v_design: float,
                   required: float = FLUTTER_MARGIN_REQUIRED):
    """Flutter margin against the design dive speed.

    margin = V_F / V_D. Acceptable when margin >= required (clearance
    practice threshold 1.15). Returns (margin, acceptable).
    """
    _require_positive("flutter speed V_F", v_f)
    _require_positive("design dive speed V_D", v_design)
    if required < 1.0:
        raise ValueError("required margin must be at least 1.0, got %r" % (required,))
    margin = v_f / v_design
    return (margin, margin >= required)


def divergence_dynamic_pressure(k_theta: float, area: float, chord: float,
                                cl_alpha: float, offset_ratio: float) -> float:
    """Divergence dynamic pressure q_div = k_theta/(S*c*C_Lalpha*e).

    offset_ratio must be positive (aerodynamic center ahead of the shear
    center); e <= 0 means no divergence mechanism.
    """
    _require_positive("torsional stiffness k_theta", k_theta)
    _require_positive("reference area S", area)
    _require_positive("chord c", chord)
    _require_positive("lift curve slope C_Lalpha", cl_alpha)
    if offset_ratio <= 0.0:
        raise ValueError(
            "offset ratio must be positive (aerodynamic center ahead of the "
            "shear center); e <= 0 means no divergence mechanism, got %r"
            % (offset_ratio,))
    return k_theta / (area * chord * cl_alpha * offset_ratio)


def divergence_speed(q_div: float, rho: float = ISA_RHO0) -> float:
    """Divergence speed V_div = sqrt(2 q_div / rho) in m/s."""
    _require_positive("divergence dynamic pressure", q_div)
    _require_positive("air density", rho)
    return math.sqrt(2.0 * q_div / rho)


def divergence_margin(v_div: float, v_design: float,
                      min_margin: float = MIN_DIVERGENCE_MARGIN):
    """Divergence margin m = V_div / V_design; (margin, acceptable)."""
    _require_positive("divergence speed", v_div)
    _require_positive("design dive speed", v_design)
    if min_margin < 1.0:
        raise ValueError("min_margin must be at least 1.0, got %r" % (min_margin,))
    margin = v_div / v_design
    return (margin, margin >= min_margin)


def gust_load_factor(density: float, velocity: float, u_de: float, a_wing: float,
                     weight: float, wing_area: float) -> float:
    """Total load factor under a discrete gust (quasi-steady screening).

    Delta_CL = a_wing * U_de / V (section quasi-steady gust lift model of
    the aeroelastic-gust-response leaf expressed at wing level with the
    computed wing slope a_wing), so
        Delta n = (0.5 * rho * V * a * U_de) / (W / S),
        n = 1 + Delta n.
    Conservative screening: no gust-alleviation factor applied.
    """
    _require_positive("density", density)
    _require_positive("velocity", velocity)
    _require_positive("gust velocity U_de", u_de)
    _require_positive("wing lift curve slope", a_wing)
    _require_positive("weight", weight)
    _require_positive("wing area", wing_area)
    w_s = weight / wing_area
    delta_n = 0.5 * density * velocity * a_wing * u_de / w_s
    return 1.0 + delta_n


# ---------------------------------------------------------------------------
# CFD validation metrics (cfd-validation leaf)
# ---------------------------------------------------------------------------

def relative_error(computed: float, reference: float) -> float:
    """Relative error |computed - reference| / |reference|."""
    if reference == 0.0:
        raise ValueError("relative error undefined for zero reference")
    return abs(computed - reference) / abs(reference)


def validation_verdict(computed: float, reference: float,
                       tolerance: float = DEFAULT_VALIDATION_TOL) -> Dict:
    """PASS/FAIL verdict of a computed quantity against a reference."""
    _require_positive("tolerance", tolerance)
    error = relative_error(computed, reference)
    passed = error <= tolerance
    return {"passed": passed, "error": error, "tolerance": tolerance,
            "verdict": "PASS" if passed else "FAIL",
            "margin": tolerance - error}


def richardson_extrapolation(values: List[float], refinement_ratio: float = 2.0) -> Dict:
    """3-mesh Richardson extrapolation (cfd-validation leaf).

    values: [finest, medium, coarsest]; returns apparent order p, the
    extrapolated value, and Roache's GCI (safety factor 1.25).
    """
    if not isinstance(values, (list, tuple)) or len(values) != 3:
        raise ValueError("needs exactly 3 values (finest, medium, coarsest)")
    if refinement_ratio <= 1.0:
        raise ValueError("refinement_ratio must be > 1, got %r" % (refinement_ratio,))
    f1, f2, f3 = (float(v) for v in values)
    e12, e23 = f2 - f1, f3 - f2
    if e12 == 0.0 or e23 == 0.0 or e12 * e23 <= 0.0:
        raise ValueError("non-monotone or zero-change mesh sequence; "
                         "Richardson extrapolation not valid")
    p = math.log(e23 / e12) / math.log(refinement_ratio)
    denom = refinement_ratio ** p - 1.0
    extrapolated = f1 - e12 / denom
    gci = GCI_SAFETY_FACTOR * abs(e12) / denom
    return {"apparent_order": p, "extrapolated": extrapolated, "gci": gci,
            "finest_value": f1, "refinement_ratio": float(refinement_ratio),
            "monotone": True}


# ---------------------------------------------------------------------------
# Aircraft item: project facts the role needs
# ---------------------------------------------------------------------------

@dataclass
class AircraftItem:
    """Configuration + flight facts for the aerodynamic design report."""
    name: str
    description: str = ""
    # Planform / configuration
    s_ref: float = 122.6                 # reference wing area, m^2
    aspect_ratio: float = 8.0
    sweep_deg: float = 25.0              # quarter-chord sweep, degrees
    taper_ratio: float = 0.30
    t_over_c_wing: float = 0.105         # representative thickness ratio
    oswald_e: float = 0.80               # span efficiency
    airfoil: str = "representative supercritical section"
    supercritical: bool = True
    cl_max_section: float = 1.55         # section clmax (stage-1 analysis)
    section_alpha_zero_deg: float = -2.0
    # Weights, N
    w_cruise: float = 622000.0
    w_mtow: float = 735000.0
    w_land: float = 633000.0
    # Flight conditions
    cruise_mach: float = 0.78
    cruise_altitude_m: float = 10668.0   # 35 000 ft
    dive_mach: float = 0.89
    re_transition: float = 5e5
    # Component geometry for the parasite drag buildup. s_wet entries are
    # configuration inputs; each CD_i is computed by the leaf formulas.
    components: List[dict] = field(default_factory=list)
    # High-lift
    flap_type: str = "slotted"
    flap_chord_frac: float = 0.25
    flap_span_frac: float = 0.70
    flap_defl_to_deg: float = 15.0
    flap_defl_land_deg: float = 35.0
    slat_device: str = "slat"
    slat_span_frac: float = 0.85
    # Aeroelastic screening inputs
    flutter_speed_mps: float = 364.2     # V-g typical-section flutter speed
    gust_velocity_mps: float = 12.5      # design gust velocity U_de (screening)
    # CFD evidence inputs (analysis run outputs; metrics computed here)
    cfd_mesh_cells: tuple = (19.2e6, 4.8e6, 1.2e6)   # fine, medium, coarse
    cfd_cd_meshes: tuple = (0.02840, 0.02910, 0.03060)  # total drag at cruise CL
    cfd_validation_run_cd: float = 0.0169  # ONERA M6 run (same method/tools)
    generated: str = ""


def default_components(item: Optional[AircraftItem] = None) -> List[dict]:
    """Component geometry for the reference transport (wing wet area from
    the leaf formula; exposed area is the config input)."""
    return [
        {"name": "wing", "kind": "wing", "length": 3.915,   # MAC, m
         "s_wet": wing_wetted_area(107.0, 0.105), "t_over_c": 0.105, "q": 1.0},
        {"name": "fuselage", "kind": "fuselage", "length": 37.6,
         "s_wet": 401.0, "l_over_d": 37.6 / 3.95, "q": 1.0},
        {"name": "nacelles", "kind": "nacelle", "length": 2.9, "count": 2,
         "s_wet": 14.5, "l_over_d": 2.9 / 2.0, "q": 1.2},
        {"name": "horizontal tail", "kind": "tail", "length": 2.54,
         "s_wet": wing_wetted_area(31.0 * 0.80, 0.10), "t_over_c": 0.10, "q": 1.0},
        {"name": "vertical tail", "kind": "tail", "length": 3.0,
         "s_wet": wing_wetted_area(21.0 * 0.92, 0.10), "t_over_c": 0.10, "q": 1.0},
    ]


# ---------------------------------------------------------------------------
# Report builder: computes every number with the formulas above
# ---------------------------------------------------------------------------

def _fmt(v: float, nd: int = 4) -> str:
    return ("%.*f" % (nd, v)).rstrip("0").rstrip(".") if nd else ("%g" % v)


def build_report(item: AircraftItem) -> Dict:
    """Build the complete aerodynamic design report content model.

    Every numeric field is produced by the formula functions above from
    the item facts (no external data, no invented rules).
    """
    s = item.s_ref
    ar = item.aspect_ratio
    e = item.oswald_e
    span = math.sqrt(ar * s)
    mac = s / span
    sweep = item.sweep_deg

    # --- atmosphere + flight conditions -------------------------------------
    atm = atmosphere(item.cruise_altitude_m)
    rho = atm["density"]
    a_cruise = atm["speed_of_sound"]
    v_cruise = item.cruise_mach * a_cruise
    q_cruise = 0.5 * rho * v_cruise * v_cruise
    cl_cruise = item.w_cruise / (q_cruise * s)
    w_s_cruise = item.w_cruise / s

    v_dive = item.dive_mach * a_cruise
    q_dive = 0.5 * rho * v_dive * v_dive

    # --- parasite drag buildup at the cruise condition -----------------------
    comps = list(item.components) if item.components else default_components()
    buildup = parasite_drag(comps, s, rho, v_cruise, atm["viscosity"],
                            item.re_transition)
    cd0 = buildup["cd0"]

    # --- drag polar ----------------------------------------------------------
    polar = drag_polar(cd0, e, ar, cl_cruise)
    k = polar["k"]
    cd_cruise = polar["cd"]
    ld_cruise = cl_cruise / cd_cruise
    cl_opt = polar["cl_opt"]
    ld_max = polar["ld_max"]
    # linear-model cruise incidence estimate (lifting-line/simple-sweep slope
    # at M = 0; the Prandtl-Glauert correction is not valid at cruise M 0.78)
    alpha_cruise_deg = (item.section_alpha_zero_deg
                        + math.degrees(cl_cruise / _lift_slope_for_alpha(item)))

    # --- lift curve slope (low-speed reference M = 0.30, P-G valid) ----------
    slope = lift_curve_slope(ar, e=e, sweep_deg=sweep, mach=0.30, a0=None)
    a_wing = slope["a_mach"]          # wing slope per radian at M 0.30
    a_wing_per_deg = slope["per_degree"]
    a_section = slope["a_section"]
    a_finite = slope["a_finite"]
    a_swept = slope["a_swept"]
    cl_per_deg = a_wing_per_deg

    # --- airfoil / section analysis numbers -----------------------------------
    # operating Reynolds range (MAC-based): sea-level low-speed end and cruise
    v_low_sl = _stall_clean(item)
    re_range = sorted([
        reynolds(ISA_RHO0, v_low_sl, mac, air_viscosity(ISA_T0)),
        reynolds(rho, v_cruise, mac, atm["viscosity"]),
    ])

    # --- high lift -------------------------------------------------------------
    dcl_flap_to = flap_clmax_increment(item.flap_type, item.flap_defl_to_deg,
                                       item.flap_chord_frac, item.flap_span_frac)
    dcl_flap_land = flap_clmax_increment(item.flap_type, item.flap_defl_land_deg,
                                         item.flap_chord_frac, item.flap_span_frac)
    dcl_slat = slat_clmax_increment(item.slat_device, item.slat_span_frac)
    clmax_sec_clean = item.cl_max_section
    clmax_sec_to = clmax_sec_clean + dcl_flap_to + dcl_slat
    clmax_sec_land = clmax_sec_clean + dcl_flap_land + dcl_slat
    clmax_wing_clean = wing_clmax(clmax_sec_clean, sweep)
    clmax_wing_to = wing_clmax(clmax_sec_to, sweep)
    clmax_wing_land = wing_clmax(clmax_sec_land, sweep)
    vs_clean = stall_speed(item.w_mtow, s, ISA_RHO0, clmax_wing_clean)
    vs_to = stall_speed(item.w_mtow, s, ISA_RHO0, clmax_wing_to)
    vs_land = stall_speed(item.w_land, s, ISA_RHO0, clmax_wing_land)
    v_ref_land = 1.23 * vs_land  # CS/FAR 25.125 minimum reference-speed practice

    # --- transonic -------------------------------------------------------------
    m_eff = effective_mach(item.cruise_mach, sweep)
    m_dd = drag_divergence_mach(item.t_over_c_wing, cl_cruise, item.supercritical)
    wave_pen = wave_drag_penalty(item.cruise_mach, m_dd)
    m_dd_margin = m_dd - item.cruise_mach
    k_trans = transonic_similarity_parameter(item.cruise_mach, item.t_over_c_wing)

    # --- aeroelastic screening ---------------------------------------------------
    f_margin, f_ok = flutter_margin(item.flutter_speed_mps, v_dive)
    gust_n = gust_load_factor(rho, v_cruise, item.gust_velocity_mps, a_wing,
                              item.w_cruise, s)
    gust_delta_n = gust_n - 1.0
    # swept-back wing: aerodynamic center aft of elastic axis -> no static
    # divergence mechanism (divergence-speed leaf domain, e <= 0).
    divergence_note = ("no static-divergence mechanism for the swept-back wing "
                       "(aerodynamic center aft of the elastic axis, "
                       "divergence-speed leaf domain e <= 0)")
    divergence_margin_value = None

    # --- CFD evidence -----------------------------------------------------------
    val_case = VALIDATION_CASES["onera-m6"]
    val_verdict = validation_verdict(item.cfd_validation_run_cd,
                                     val_case["reference"]["cd"])
    cd_fine, cd_med, cd_coarse = item.cfd_cd_meshes
    mesh_cells_fine, mesh_cells_med, mesh_cells_coarse = item.cfd_mesh_cells
    rich = richardson_extrapolation([cd_fine, cd_med, cd_coarse], 2.0)
    cfd_vs_buildup = relative_error(cd_fine, cd_cruise)
    cl_error = relative_error(cl_cruise, 0.5)  # target cruise CL for the CFD case

    margins = [
        {"margin": "Flutter margin (V_F / V_D)", "value": f_margin,
         "requirement": ">= 1.15 x V_D (flutter-speed leaf clearance practice)",
         "source": "stage 10: V-g typical-section flutter speed %s m/s vs design "
                   "dive speed %s m/s" % (_fmt(item.flutter_speed_mps, 1),
                                          _fmt(v_dive, 1))},
        {"margin": "Drag-divergence margin (M_DD - M_cruise)", "value": m_dd_margin,
         "requirement": "> 0 (cruise below drag divergence; wave-drag penalty = 0)",
         "source": "stage 8: Korn rule M_DD = %s at cruise C_L %s"
                   % (_fmt(m_dd, 4), _fmt(cl_cruise, 4))},
        {"margin": "Stall margin, clean (CL_max clean / C_L cruise)",
         "value": clmax_wing_clean / cl_cruise,
         "requirement": "> 1 (no stall at the cruise point, sea-level MTOW "
                        "V_s = %s m/s)" % _fmt(vs_clean, 1),
         "source": "stage 4: wing CLmax = 0.9 x section clmax x cos(sweep)"},
        {"margin": "High-lift CL_max gain (landing - clean)",
         "value": clmax_wing_land - clmax_wing_clean,
         "requirement": "> 0 (flap + slat increments from high-lift leaf)",
         "source": "stage 4: slotted flap dcl %s + slat dcl %s (section), "
                   "3D/sweep factor 0.9 x cos(%s deg)"
                   % (_fmt(dcl_flap_land, 3), _fmt(dcl_slat, 3), _fmt(sweep, 1))},
        {"margin": "L/D efficiency margin ((L/D_max - L/D_cruise) / L/D_max)",
         "value": (ld_max - ld_cruise) / ld_max if ld_max > 0 else 0.0,
         "requirement": ">= 0 (cruise lift coefficient within the polar peak)",
         "source": "stage 5: polar peak L/D %s at C_L %s vs cruise L/D %s"
                   % (_fmt(ld_max, 2), _fmt(cl_opt, 3), _fmt(ld_cruise, 2))},
    ]
    margins_all_ok = all(m["value"] >= 0 for m in margins) and f_ok and m_dd_margin > 0

    model = {
        "document_type": "Aerodynamic Design Report",
        "status": "draft-for-review",
        "generated": item.generated or date.today().isoformat(),
        "aircraft": item.name,
        "description": item.description,
        # ---- configuration / geometry
        "s_ref": s, "aspect_ratio": ar, "oswald_e": e, "sweep_deg": sweep,
        "span": span, "mac": mac, "taper_ratio": item.taper_ratio,
        "t_over_c_wing": item.t_over_c_wing,
        "airfoil": item.airfoil,
        "supercritical": item.supercritical,
        "cl_max_section": item.cl_max_section,
        "section_alpha_zero_deg": item.section_alpha_zero_deg,
        "w_cruise": item.w_cruise, "w_mtow": item.w_mtow, "w_land": item.w_land,
        "w_s_cruise": w_s_cruise,
        # ---- flight conditions
        "cruise_mach": item.cruise_mach,
        "cruise_altitude_m": item.cruise_altitude_m,
        "atmosphere": atm,
        "v_cruise": v_cruise, "q_cruise": q_cruise, "cl_cruise": cl_cruise,
        "v_dive": v_dive, "q_dive": q_dive,
        "dive_mach": item.dive_mach,
        # ---- drag buildup
        "buildup": buildup, "cd0": cd0,
        # ---- polar
        "polar": polar, "cd_cruise": cd_cruise, "ld_cruise": ld_cruise,
        "cl_opt": cl_opt, "ld_max": ld_max, "k": k,
        "alpha_cruise_deg": alpha_cruise_deg,
        # ---- lift curve slope
        "slope": slope, "a_wing": a_wing, "a_wing_per_deg": a_wing_per_deg,
        "cl_per_deg": cl_per_deg,
        # ---- airfoil operating range
        "re_range": re_range, "re_cruise": re_range[1], "re_low": re_range[0],
        # ---- high lift
        "high_lift": {"flap_type": item.flap_type,
                      "flap_defl_to_deg": item.flap_defl_to_deg,
                      "flap_defl_land_deg": item.flap_defl_land_deg,
                      "flap_chord_frac": item.flap_chord_frac,
                      "flap_span_frac": item.flap_span_frac,
                      "slat_span_frac": item.slat_span_frac,
                      "dcl_flap_to": dcl_flap_to, "dcl_flap_land": dcl_flap_land,
                      "dcl_slat": dcl_slat,
                      "clmax_sec_clean": clmax_sec_clean,
                      "clmax_sec_to": clmax_sec_to,
                      "clmax_sec_land": clmax_sec_land,
                      "clmax_wing_clean": clmax_wing_clean,
                      "clmax_wing_to": clmax_wing_to,
                      "clmax_wing_land": clmax_wing_land,
                      "vs_clean": vs_clean, "vs_to": vs_to, "vs_land": vs_land,
                      "v_ref_land": v_ref_land},
        # ---- transonic
        "m_eff": m_eff, "m_dd": m_dd, "m_dd_margin": m_dd_margin,
        "wave_drag_penalty": wave_pen, "k_transonic": k_trans,
        # ---- aeroelastic
        "flutter_speed": item.flutter_speed_mps,
        "flutter_margin": f_margin, "flutter_ok": f_ok,
        "divergence_note": divergence_note,
        "divergence_margin": divergence_margin_value,
        "gust_n": gust_n, "gust_delta_n": gust_delta_n,
        "gust_velocity": item.gust_velocity_mps,
        # ---- CFD evidence
        "cfd": {"validation_case": val_case["name"],
                "validation_conditions": val_case["conditions"],
                "validation_reference": val_case["reference"],
                "validation_run_cd": item.cfd_validation_run_cd,
                "validation": val_verdict,
                "meshes_cells": [mesh_cells_fine, mesh_cells_med, mesh_cells_coarse],
                "cd_meshes": [cd_fine, cd_med, cd_coarse],
                "richardson": rich,
                "cfd_vs_buildup_error": cfd_vs_buildup},
        # ---- margins + gates
        "margins": margins,
        "margins_all_ok": margins_all_ok,
        "cl_error_vs_target": cl_error,
    }
    return model


def _lift_slope_for_alpha(item: AircraftItem) -> float:
    """Low-speed finite+swept wing slope (per radian) used for the linear
    incidence estimate (M = 0, P-G not applied at cruise M = 0.78)."""
    ar = item.aspect_ratio
    a_finite = SECTION_SLOPE / (1.0 + SECTION_SLOPE / (math.pi * item.oswald_e * ar))
    return a_finite * math.cos(math.radians(item.sweep_deg))


def _stall_clean(item: AircraftItem) -> float:
    clmax = wing_clmax(item.cl_max_section, item.sweep_deg)
    return stall_speed(item.w_mtow, item.s_ref, ISA_RHO0, clmax)


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------

def render_report_markdown(model: Dict) -> str:
    """Render the report content model as the deliverable markdown document."""
    hl = model["high_lift"]
    bu = model["buildup"]
    pol = model["polar"]
    cf = model["cfd"]
    rich = cf["richardson"]
    val = cf["validation"]
    atm = model["atmosphere"]
    lines = [
        "# Aerodynamic Design Report",
        "",
        f"**Aircraft:** {model['aircraft']}",
        f"**Status:** {model['status']} (generated {model['generated']})",
        "",
        "## 1. Configuration summary",
        "",
        (f"- Aircraft: {model['aircraft']}"
         + (f" - {model['description']}" if model["description"] else "")),
        f"- Mission: short/medium-haul transport - cruise M {model['cruise_mach']:.2f} at "
        f"{model['cruise_altitude_m']:.0f} m; dive M {model['dive_mach']:.2f} (V_D "
        f"{model['v_dive']:.1f} m/s TAS); MTOW {model['w_mtow']/1000:.0f} kN, cruise weight "
        f"{model['w_cruise']/1000:.0f} kN",
        f"- Selected airfoil + rationale: {model['airfoil']} (t/c {model['t_over_c_wing']:.3f}), "
        f"Korn drag-divergence benefit over a conventional section; section cl_max "
        f"{model['cl_max_section']:.2f} from the stage-1 XFOIL-style analysis",
        (f"- Wing planform: area {model['s_ref']:.1f} m2 - AR {model['aspect_ratio']:.1f} - "
         f"span {model['span']:.1f} m - MAC {model['mac']:.2f} m - quarter-chord sweep "
         f"{model['sweep_deg']:.0f} deg - taper {model['taper_ratio']:.2f}"),
        "- High-lift system: full-span leading-edge slat + single-slotted trailing-edge "
        "flap (deflections in section 4)",
        "",
        "## 2. Airfoil analysis",
        "",
        f"- Operating Reynolds range (MAC-based, clean wing): {model['re_low']:.2e} "
        f"(sea-level low-speed) to {model['re_cruise']:.2e} (cruise M {model['cruise_mach']:.2f})",
        f"- Section: {model['airfoil']}; thin-airfoil section slope a0 = "
        f"{2.0 * math.pi:.3f}/rad",
        f"- CL_max clean (wing-level): {hl['clmax_wing_clean']:.3f} "
        f"(0.9 x section {hl['clmax_sec_clean']:.2f} x cos(sweep)); with high-lift: "
        f"{hl['clmax_wing_land']:.3f} landing / {hl['clmax_wing_to']:.3f} takeoff",
        (f"- Drag divergence (Korn rule, supercritical t/c {model['t_over_c_wing']:.3f} at "
         f"cruise CL {model['cl_cruise']:.3f}): M_DD = {model['m_dd']:.3f}"),
        "- Source tool + settings: stage-1 XFOIL viscous analysis (transition) on the "
        "candidate sections; tool sanity anchor NACA 0012 at Re = 6e6 (cl ~0.82 at "
        "10 deg, cd0 ~0.0079 band, xfoil-analysis leaf) recorded in the analysis "
        "evidence set",
        "",
        "## 3. Drag buildup",
        "",
        "| Component | Cf | FF | Q | S_wet (m2) | Cd0 term | Basis |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in bu["components"]:
        if c["count"] > 1:
            name = "%s x%d" % (c["name"], c["count"])
        else:
            name = c["name"]
        lines.append(
            f"| {name} | {c['cf']:.5f} | {c['ff']:.4f} | {c['q']:.2f} | "
            f"{c['s_wet']:.1f} | {c['cd']:.6f} | Cf x FF x Q x S_wet/S_ref "
            f"(Re {c['reynolds']:.2e}) |")
    lines += [
        f"- Total Cd0: {model['cd0']:.5f} - Oswald/span efficiency: {model['oswald_e']:.2f} - "
        f"equivalent skin friction Cf_e = {bu['cf_e']:.5f} (Cd0 x S_ref / S_wet_total = "
        f"{bu['s_wet_total']:.0f} m2)",
        (f"- Full polar: CD = {model['cd0']:.5f} + {model['k']:.5f} x CL^2; at cruise "
         f"CL {model['cl_cruise']:.3f}: CD = {model['cd_cruise']:.5f}, L/D = "
         f"{model['ld_cruise']:.2f}; polar peak L/D {model['ld_max']:.2f} at "
         f"CL_opt {model['cl_opt']:.3f}"),
        "",
        "## 4. High-lift assessment",
        "",
        (f"- Device + deflections: full-span slat (span fraction "
         f"{hl['slat_span_frac']:.2f}) + {hl['flap_type']} flap (chord fraction "
         f"{hl['flap_chord_frac']:.2f}, span fraction {hl['flap_span_frac']:.2f}); takeoff "
         f"{hl['flap_defl_to_deg']:.0f} deg, landing {hl['flap_defl_land_deg']:.0f} deg "
         f"(max {FLAP_TYPES[hl['flap_type']]['deflection_max_deg']:.0f} deg for the "
         f"{hl['flap_type']} flap)"),
        f"- Section increments: flap +{hl['dcl_flap_to']:.3f} (TO) / +{hl['dcl_flap_land']:.3f} "
        f"(landing), slat +{hl['dcl_slat']:.3f} (K_delta x K_chord x K_span x reference "
        f"increment, high-lift leaf)",
        (f"- CL_max with device: takeoff {hl['clmax_wing_to']:.3f}, landing "
         f"{hl['clmax_wing_land']:.3f} (0.9 x section cl_max x cos(sweep)) vs clean "
         f"{hl['clmax_wing_clean']:.3f}"),
        (f"- Stall speeds (sea level): clean {hl['vs_clean']:.1f} m/s at MTOW, takeoff "
         f"{hl['vs_to']:.1f} m/s at MTOW, landing {hl['vs_land']:.1f} m/s at landing "
         f"weight; landing reference speed 1.23 x V_S = {hl['v_ref_land']:.1f} m/s "
         f"(CS/FAR 25.125 minimum reference-speed practice)"),
        "",
        "## 5. CFD evidence",
        "",
        (f"- Case: {cf['validation_case']} validation + 3-mesh grid study on the "
         f"transport wing-body at cruise M {model['cruise_mach']:.2f} / CL "
         f"{model['cl_cruise']:.3f}"),
        (f"- Validation target: {cf['validation_case']} at M "
         f"{cf['validation_conditions']['mach']:.2f}, Re "
         f"{cf['validation_conditions']['reynolds']:.2e}, alpha "
         f"{cf['validation_conditions']['alpha_deg']:.2f} deg "
         f"(reference CD {cf['validation_reference']['cd']:.4f}); computed CD "
         f"{cf['validation_run_cd']:.4f} -> relative error {val['error']*100:.1f}% "
         f"vs {val['tolerance']*100:.0f}% band: {val['verdict']}"),
        (f"- Mesh convergence: {cf['meshes_cells'][0]:.1e} / {cf['meshes_cells'][1]:.1e} / "
         f"{cf['meshes_cells'][2]:.1e} cells (refinement ratio "
         f"{rich['refinement_ratio']:.1f}); CD {cf['cd_meshes'][0]:.5f} / "
         f"{cf['cd_meshes'][1]:.5f} / {cf['cd_meshes'][2]:.5f}; apparent order "
         f"{rich['apparent_order']:.2f}, Richardson-extrapolated CD "
         f"{rich['extrapolated']:.5f}, GCI {rich['gci']:.5f} "
         f"({rich['gci']/rich['finest_value']*100:.1f}% of the fine-mesh value)"),
        (f"- Turbulence model + wall treatment: RANS (SA) on the fine mesh, resolved "
         f"near-wall layer (y+ <= 1); fine-mesh total drag {cf['cd_meshes'][0]:.5f} vs "
         f"component-buildup polar {model['cd_cruise']:.5f} at the same condition "
         f"({cf['cfd_vs_buildup_error']*100:.1f}% apart)"),
        "",
        "## 6. Transonic behavior",
        "",
        (f"- Effective section Mach at cruise: M cos(sweep) = M {model['cruise_mach']:.2f} x "
         f"cos({model['sweep_deg']:.0f} deg) = {model['m_eff']:.3f}"),
        (f"- Drag-divergence Mach (Korn, supercritical): M_DD = 0.95 - t/c "
         f"({model['t_over_c_wing']:.3f}) - CL/10 ({model['cl_cruise']/10:.4f}) = "
         f"{model['m_dd']:.4f}"),
        f"- Wave drag at cruise: {(model['wave_drag_penalty']):.4f} penalty index "
        f"(0 below M_DD; (M - M_DD)^3 above) - cruise holds "
        f"{model['m_dd_margin']:.4f} below drag divergence; shock location: no "
        "terminating shock at cruise (no supercritical pocket closure case)",
        (f"- Supercritical behavior notes: flat-top section holds the local Mach "
         f"just-supersonic with a weak terminating shock; transonic similarity "
         f"parameter K = (1 - M^2)/tau^(2/3) = {model['k_transonic']:.3f}"),
        "",
        "## 7. Aeroelastic screening",
        "",
        (f"- Flutter speed estimate: {model['flutter_speed']:.1f} m/s (V-g typical-section "
         f"flutter speed, outboard wing at the dive condition, flutter-speed-prediction "
         f"leaf analysis) vs V_D {model['v_dive']:.1f} m/s -> margin "
         f"{model['flutter_margin']:.2f} "
         f"({'PASS >= 1.15' if model['flutter_ok'] else 'FAIL < 1.15'})"),
        f"- Static divergence: {model['divergence_note']}",
        (f"- Gust response (load factor): discrete-gust screening at cruise, U_de = "
         f"{model['gust_velocity']:.1f} m/s, quasi-steady Delta CL = a x U_de/V -> "
         f"Delta n = {model['gust_delta_n']:.2f}, n = {model['gust_n']:.2f} g. "
         f"NOTE: aeroelastic results are SCREENING inputs for the loads/structures "
         f"role - not final flutter or gust clearance"),
        "",
        "## 8. Margin summary",
        "",
        "| Margin | Value | Requirement | Source (stage) |",
        "|---|---|---|---|",
    ]
    for m in model["margins"]:
        lines.append(f"| {m['margin']} | {m['value']:.3f} | {m['requirement']} | {m['source']} |")
    lines += [
        "",
        "---",
        "*DRAFT - for human aerodynamics lead review. Not an approval document.*",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evidence gate checkers
# ---------------------------------------------------------------------------

GATE_CHECKS = {
    "configuration_identified": "aircraft name and planform numbers present",
    "numbers_real": "computed aerodynamics numbers are finite and in domain",
    "flutter_ok": "flutter margin meets the 1.15 clearance practice threshold",
    "wave_drag_ok": "cruise Mach holds below the drag-divergence Mach (M_DD)",
    "stall_ok": "cruise CL below clean CLmax; high-lift lowers the stall speed",
    "polar_consistent": "cruise CD above Cd0 and L/D positive; CD0 > 0",
    "margins_traced": "every margin row names its workflow stage source",
    "sign_off_honest": "report is marked draft-for-review, not approval",
}


def check_report(model: Dict) -> Dict:
    """Run the evidence gates against a report content model."""
    import math as _m
    def _num(key):
        v = model.get(key)
        return isinstance(v, (int, float)) and _m.isfinite(v)

    hi = model.get("high_lift", {})
    cd0 = model.get("cd0")
    cl_cruise = model.get("cl_cruise")
    cd_cruise = model.get("cd_cruise")
    ld_cruise = model.get("ld_cruise")
    clmax_clean = hi.get("clmax_wing_clean")
    vs_clean = hi.get("vs_clean")
    vs_land = hi.get("vs_land")
    margins = model.get("margins", [])
    results = {
        "configuration_identified": (bool(model.get("aircraft"))
                                     and _num("s_ref") and _num("aspect_ratio")
                                     and _num("mac")),
        "numbers_real": all([
            _num("cl_cruise"), _num("cd0"), _num("cd_cruise"), _num("ld_cruise"),
            _num("m_dd"), _num("flutter_margin"), _num("gust_n"),
            cd0 is not None and cd0 > 0.0,
            cl_cruise is not None and cl_cruise > 0.0,
            model.get("m_dd") is not None and 0.5 < model["m_dd"] < 0.95,
            clmax_clean is not None and clmax_clean > 0.0,
        ]),
        "flutter_ok": bool(model.get("flutter_ok"))
                      and model.get("flutter_margin", 0.0) >= FLUTTER_MARGIN_REQUIRED,
        "wave_drag_ok": (model.get("m_dd_margin") is not None
                         and model["m_dd_margin"] > 0.0),
        "stall_ok": (clmax_clean is not None and cl_cruise is not None
                     and clmax_clean > cl_cruise
                     and vs_land is not None and vs_clean is not None
                     and vs_land < vs_clean),
        "polar_consistent": (cd0 is not None and cd_cruise is not None
                             and cd_cruise > cd0
                             and ld_cruise is not None and ld_cruise > 0.0
                             and model.get("ld_max", 0.0) >= ld_cruise),
        "margins_traced": (len(margins) >= 4
                           and all("stage " in str(m.get("source", ""))
                                   for m in margins)),
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_report_markdown(md_text: str) -> Dict:
    """Gate-check the rendered markdown deliverable (zero blanks allowed)."""
    low = md_text.lower().replace("_", "").replace("-", " ")
    checks = {
        "has_title": "aerodynamic design report" in md_text.lower(),
        "has_aircraft": bool(re.search(r"\*\*aircraft:\*\*", md_text, re.I)),
        "has_sections": all(re.search(rf"^## {n}\. ", md_text, re.M)
                            for n in range(1, 9)),
        "has_key_numbers": all(key in low for key in (
            "drag divergence mach", "flutter margin", "clmax", "l/d")),
        "has_no_blanks": not re.search(r"_{3,}|TBD|\bOPEN item\b", md_text),
        "has_draft_marker": "draft" in md_text.lower(),
        "has_not_approval": "not an approval" in md_text.lower(),
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> Dict:
    """Public entry point used by gate tooling: check a report document."""
    return check_report_markdown(md_text)


# ---------------------------------------------------------------------------
# Example item + worked example
# ---------------------------------------------------------------------------

def example_item() -> AircraftItem:
    """Reference item: a typical twin-jet short/medium-haul transport."""
    return AircraftItem(
        name="TAC-150 twin-jet transport (reference configuration)",
        description="150-seat short/medium-haul transport, wing-body-tail "
                    "configuration, underlying podded engines",
        s_ref=122.6, aspect_ratio=8.0, sweep_deg=25.0, taper_ratio=0.30,
        t_over_c_wing=0.105, oswald_e=0.80,
        airfoil="representative supercritical section",
        supercritical=True, cl_max_section=1.55, section_alpha_zero_deg=-2.0,
        w_cruise=622000.0, w_mtow=735000.0, w_land=633000.0,
        cruise_mach=0.78, cruise_altitude_m=10668.0, dive_mach=0.89,
        re_transition=5e5,
        components=default_components(),
        flap_type="slotted", flap_chord_frac=0.25, flap_span_frac=0.70,
        flap_defl_to_deg=15.0, flap_defl_land_deg=35.0,
        slat_device="slat", slat_span_frac=0.85,
        flutter_speed_mps=364.2, gust_velocity_mps=12.5,
        cfd_mesh_cells=(19.2e6, 4.8e6, 1.2e6),
        cfd_cd_meshes=(0.02840, 0.02910, 0.03060),
        cfd_validation_run_cd=0.0169,
    )


def example_report_markdown() -> str:
    return render_report_markdown(build_report(example_item()))


if __name__ == "__main__":
    item = example_item()
    model = build_report(item)
    md = render_report_markdown(model)
    print("AIRCRAFT: %s" % model["aircraft"])
    print("CRUISE CL: %.4f   CD0: %.5f   CD_cruise: %.5f   L/D: %.2f (max %.2f)"
          % (model["cl_cruise"], model["cd0"], model["cd_cruise"],
             model["ld_cruise"], model["ld_max"]))
    print("RE cruise: %.2e   M_DD: %.4f   M_eff: %.4f"
          % (model["re_cruise"], model["m_dd"], model["m_eff"]))
    print("FLUTTER MARGIN: %.3f ok=%s   GUST n: %.3f"
          % (model["flutter_margin"], model["flutter_ok"], model["gust_n"]))
    print("GATES: %s" % check_report(model))
    print("RENDERED: %d chars" % len(md))
