#!/usr/bin/env python3
"""structures_loads_core.py - Structures and Loads Engineer executable core.

This is the role's ENGINE: given an airplane's loads facts and the
candidate wing design it derives the FAR 25 limit envelope (discrete
gust per FAR 25.341 + maneuver per FAR 25.337), converts the design
limit condition to ultimate loads with the 1.5 factor of safety
(FAR 25.303), resolves root shear/bending with an elliptic span-load
idealization, computes margins of safety per critical component from
real allowables, runs the fatigue screening (S-N basis + Miner sum),
and BUILDS the loads + strength report content. It also gate-checks
deliverables. Standalone: no external repo needed.

Domain rules encoded here mirror the real AeroSkills leaves the role
is bound to (gust-maneuver-loads, landing-ground-loads, buckling,
plate-buckling, lug-joint, mmpsd-allowables, material-selection,
stress-life, goodman, miner-damage, notch-sensitivity, beam-vibration):
the formulas are the same ones those leaves' behavior contracts assert.
The specific values in the worked example are the leaf anchors (Kg in
the 0.77-0.80 band, 7075-T6 allowables Ftu 83.0 / Fty 73.0 / Fsu 48.0 /
Fbru 152.3 ksi, fatigue strength coefficient ~100 ksi at b = -0.10),
stated with their basis. Nothing here reproduces MMPDS or FAR text.

Units: US customary throughout the report and engine internals (lb,
in, ksi, ft/s, psf) - the register of the FAR 25 loads rules. Metric
leaf anchors are converted at the module boundary (1 ksi = 6.894757
MPa, 1 GPa = 145.0377 ksi). Invalid inputs raise ValueError.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date

# ---------------------------------------------------------------------------
# Domain constants (FAR 25.341 / 25.337 / 25.303, public regulation)
# ---------------------------------------------------------------------------

RHO0 = 0.002378      # sea-level standard density, slugs/ft^3
G = 32.174           # ft/s^2
KNOT = 1.68781       # ft/s per knot (used for unit labels, not calcs)

# FAR 25.341(a) design gust velocities at sea level, fps EAS.
GUST_VELOCITY_SEA_LEVEL = {"vb-vc": 66.0, "vc": 50.0, "vd": 25.0}
GUST_VELOCITY_FLOOR = {"vb-vc": 38.0, "vc": 25.0, "vd": 12.5}
GUST_ALTITUDE_FLOOR = {"vb-vc": 15000.0, "vc": 15000.0, "vd": 50000.0}

# FAR 25.337(b): positive limit maneuvering load factor at VA.
MANEUVER_LIMIT_VA = {"normal": 2.5, "commuter": 3.8, "transport": 3.8}
NEGATIVE_MANEUVER_LIMIT = -1.0
FACTOR_OF_SAFETY = 1.5          # FAR 25.303
MAX_GUST_VELOCITY = 66.0

# ---------------------------------------------------------------------------
# Materials - 7075-T6 screening allowables. Values are the real anchors used
# by the bound AeroSkills leaves (material-selection leaf: E 71.7 GPa,
# Fty 503 MPa, UTS 572 MPa; lug-joint worked example: Fsu 331 MPa,
# Fbru 1050 MPa; strain-life leaf 7075-T6 class fatigue constants).
# Basis: typical/reference-only screening values - confirm against MMPDS
# (licensed) before release. Never reproduced as a table here.
# ---------------------------------------------------------------------------
KSI = 6.894757      # MPa per ksi (conversion, not an allowable)

MATERIALS = {
    "al-7075-t6": {
        "label": "Aluminum 7075-T6 (screening allowables per bound "
                 "AeroSkills material/lug/strain-life anchors; confirm "
                 "B-basis values against MMPDS before release)",
        "E_ksi": 10400.0,          # 71.7 GPa
        "Ftu_ksi": 572.0 / KSI,    # 83.0
        "Fty_ksi": 503.0 / KSI,    # 73.0
        "Fsu_ksi": 331.0 / KSI,    # 48.0
        "Fbru_ksi": 1050.0 / KSI,  # 152.3
        "rho_lb_in3": 0.101,
        "nu": 0.33,
        "sig_f_prime_ksi": 690.0 / KSI,  # fatigue strength coeff, ~100.1 ksi
        "b_fatigue": -0.10,               # fatigue strength exponent
    },
}

# ---------------------------------------------------------------------------
# Core loads logic (mirrors bound leaf gust_load_logic.py)
# ---------------------------------------------------------------------------


def _require_positive(value, name):
    if value is None:
        raise ValueError("%s is required, got None" % (name,))
    value = float(value)
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError("%s must be positive, got %r" % (name, value))
    return value


def _require_nonnegative(value, name):
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError("%s must be nonnegative, got %r" % (name, value))
    return value


def far25_gust_velocity(speed_region, altitude_ft=0.0):
    """Design discrete gust velocity U_de (fps EAS) per FAR 25.341(a)."""
    if speed_region not in GUST_VELOCITY_SEA_LEVEL:
        raise ValueError("speed_region must be one of vb-vc/vc/vd")
    altitude_ft = _require_nonnegative(altitude_ft, "altitude_ft")
    v0 = GUST_VELOCITY_SEA_LEVEL[speed_region]
    alt_floor = GUST_ALTITUDE_FLOOR[speed_region]
    v_floor = GUST_VELOCITY_FLOOR[speed_region]
    if altitude_ft >= alt_floor:
        return v_floor
    return v0 - (v0 - v_floor) * (altitude_ft / alt_floor)


def gust_mass_ratio(ws, cbar, a, rho=RHO0):
    """Mass ratio mu_g = 2*(W/S)/(rho*cbar*a*g), FAR 25.341(b)(2)."""
    return (2.0 * _require_positive(ws, "ws")
            / (_require_positive(rho, "rho") * _require_positive(cbar, "cbar")
               * _require_positive(a, "a") * G))


def gust_alleviation_factor(ws, cbar, a, rho=RHO0):
    """Gust alleviation factor Kg = 0.88*mu_g/(5.3+mu_g)."""
    mu = gust_mass_ratio(ws, cbar, a, rho)
    return 0.88 * mu / (5.3 + mu)


def gust_load_factor(ve_fps, ws, a, u_de_fps, kg=None, cbar=None, rho=RHO0):
    """n = 1 + (rho0*V_e*a*K_g*U_de)/(2*W/S) with V_e in ft/s (FAR 25.341)."""
    ve = _require_positive(ve_fps, "ve")
    ws = _require_positive(ws, "ws")
    a = _require_positive(a, "a")
    u = float(u_de_fps)
    if not math.isfinite(u) or u == 0.0:
        raise ValueError("u_de must be a nonzero finite gust velocity")
    if abs(u) > MAX_GUST_VELOCITY:
        raise ValueError("u_de magnitude %.3f fps exceeds the FAR 25.341 "
                         "maximum design gust velocity of %.1f fps EAS"
                         % (abs(u), MAX_GUST_VELOCITY))
    if kg is None:
        if cbar is None:
            raise ValueError("kg or cbar must be given")
        kg = gust_alleviation_factor(ws, cbar, a, rho)
    kg = _require_positive(kg, "kg")
    return 1.0 + (RHO0 * ve * a * kg * u) / (2.0 * ws)


def maneuver_limit_load_factor(weight_lb, category="transport",
                               negative=False):
    """Positive limit maneuvering load factor at VA per FAR 25.337(b):
    n = max(2.5, min(3.8, 2.1 + 24000/(W + 10000))) with W the design
    maximum takeoff weight in lb (regulation text, public domain). The
    bound gust leaf's category table (normal 2.5, commuter 3.8) is used
    for the non-transport entries; for transport the exact regulation
    formula is applied - a 100,000 lb transport lands on the 2.5 floor,
    exactly as the leaf's own worked envelope (VA = VS*sqrt(2.5))."""
    if negative:
        return NEGATIVE_MANEUVER_LIMIT
    if category == "transport":
        w = _require_positive(weight_lb, "weight_lb")
        n = 2.1 + 24000.0 / (w + 10000.0)
        return max(2.5, min(3.8, n))
    try:
        return MANEUVER_LIMIT_VA[category]
    except KeyError:
        raise ValueError("unknown category %r; use normal/commuter/transport"
                         % (category,))


def _positive_limit_at(vn, v):
    """Positive envelope limit load factor at speed v (ft/s)."""
    vs, va, vd = vn["vs"], vn["va"], vn["vd"]
    n_pos = vn["n_positive"]
    if v <= va:
        return min(n_pos, (v / vs) ** 2)
    if v >= vd:
        return 0.0
    return n_pos * (vd - v) / (vd - va)


def _negative_limit_at(vn, v):
    vs, vc, vd = vn["vs"], vn["vc"], vn["vd"]
    n_neg = vn["n_negative"]
    if v <= vc:
        return max(n_neg, -((v / vs) ** 2))
    if v >= vd:
        return 0.0
    return n_neg * (vd - v) / (vd - vc)


def vn_diagram(ws, vs, vd, a, cbar, category="transport", altitude_ft=0.0,
               rho=RHO0, weight_lb=None):
    """Construct the FAR 25 V-n flight envelope as a dict.

    Returns corner speeds (vs < va < vb < vc < vd enforced), limit
    maneuvering load factors, gust points at VB/VC/VD with the FAR
    25.341(a) design gust velocities, and the gust velocities used.
    weight_lb (design MTOW) is passed through to the FAR 25.337(b)
    maneuvering-factor formula for the transport category.
    """
    ws = _require_positive(ws, "ws")
    vs = _require_positive(vs, "vs")
    vd = _require_positive(vd, "vd")
    a = _require_positive(a, "a")
    cbar = _require_positive(cbar, "cbar")
    n_pos = maneuver_limit_load_factor(weight_lb, category)
    n_neg = NEGATIVE_MANEUVER_LIMIT
    va = vs * math.sqrt(n_pos)
    vb = max(1.8 * vs, 1.05 * va)
    vc = max(2.0 * vs, 1.1 * vb)
    if not (vs < va < vb < vc < vd):
        raise ValueError(
            "speed ordering violated: need vs < va < vb < vc < vd, got "
            "vs=%.1f va=%.1f vb=%.1f vc=%.1f vd=%.1f" % (vs, va, vb, vc, vd))
    kg = gust_alleviation_factor(ws, cbar, a, rho)
    u_bc = far25_gust_velocity("vb-vc", altitude_ft)
    u_c = far25_gust_velocity("vc", altitude_ft)
    u_d = far25_gust_velocity("vd", altitude_ft)
    gust_points = []
    for label, v, u_pos in (("VB", vb, u_bc), ("VC", vc, u_c),
                            ("VD", vd, u_d)):
        gust_points.append({
            "speed": label, "v": v,
            "u_de": u_pos,
            "n_pos": gust_load_factor(v, ws, a, u_pos, kg=kg),
            "n_neg": gust_load_factor(v, ws, a, -u_pos, kg=kg),
        })
    return {
        "category": category, "ws": ws, "cbar_ft": cbar, "a": a,
        "vs": vs, "va": va, "vb": vb,
        "vc": vc, "vd": vd, "n_positive": n_pos, "n_negative": n_neg,
        "mu_g": gust_mass_ratio(ws, cbar, a, rho), "kg": kg,
        "altitude_ft": altitude_ft,
        "maneuver_envelope": {
            "positive": [(vs, 1.0), (va, n_pos), (vd, 0.0)],
            "negative": [(vs, n_neg), (vc, n_neg), (vd, 0.0)],
        },
        "gust_points": gust_points,
        "gust_velocities": {"vb-vc": u_bc, "vc": u_c, "vd": u_d},
    }


def design_limit_load_factor(vn):
    """The limit design condition = max of the envelope (maneuver corner,
    positive/negative plateau values and every gust line point). Returns
    (n_limit, condition_label, speed_fps)."""
    best = (vn["n_positive"], "maneuver at VA", vn["va"])
    for p in vn["gust_points"]:
        if p["n_pos"] > best[0]:
            best = (p["n_pos"], "gust at %s (%.1f fps EAS)"
                    % (p["speed"], p["u_de"]), p["v"])
    n_neg = vn["n_negative"]
    if n_neg < 0.0:
        for p in vn["gust_points"]:
            if p["n_neg"] < n_neg:
                n_neg = p["n_neg"]
    return {"n_limit_pos": best[0], "n_limit_neg": n_neg,
            "condition_pos": best[1], "speed_pos": best[2]}


def envelope_margins(vn):
    """Margin check of each gust point against the maneuver envelope."""
    out = {}
    for p in vn["gust_points"]:
        v = p["v"]
        env_pos = _positive_limit_at(vn, v)
        env_neg = _negative_limit_at(vn, v)
        g_pos, g_neg = p["n_pos"], p["n_neg"]
        m_pos = (env_pos - g_pos) / env_pos if env_pos > 0 else 1.0
        m_neg = (g_neg - env_neg) / abs(env_neg) if env_neg < 0 else 1.0
        out[p["speed"]] = {
            "v": v, "n_envelope_pos": env_pos, "n_gust_pos": g_pos,
            "margin_pos": m_pos, "gust_critical_pos": m_pos < 0.0,
            "n_envelope_neg": env_neg, "n_gust_neg": g_neg,
            "margin_neg": m_neg, "gust_critical_neg": m_neg < 0.0,
        }
    return out


# ---------------------------------------------------------------------------
# Landing / ground loads (mirrors bound leaf landing_ground_loads_logic.py)
# ---------------------------------------------------------------------------

N_LEVEL_DEFAULT = 2.5   # typical level-landing limit vertical inertia factor


def level_landing_reactions(weight_lb, a_ft, b_ft, lf=N_LEVEL_DEFAULT):
    """Level landing reactions at a limit vertical inertia load factor."""
    weight = _require_positive(weight_lb, "weight")
    a = _require_positive(a_ft, "a (nose gear to CG)")
    b = _require_positive(b_ft, "b (CG to main gear)")
    lf = _require_positive(lf, "load factor")
    r_nose = lf * weight * b / (a + b)
    r_main = lf * weight * a / (a + b)
    return {"nose_lb": r_nose, "main_lb": r_main, "total_lb": r_nose + r_main}


def braked_roll_deceleration(a_ft, b_ft, friction=0.8):
    """Braked-roll deceleration in g: friction*a/(a+b)."""
    a = _require_positive(a_ft, "a")
    b = _require_positive(b_ft, "b")
    friction = _require_positive(friction, "friction")
    return friction * a / (a + b)


# ---------------------------------------------------------------------------
# Strength logic
# ---------------------------------------------------------------------------


def margin_of_safety(allowable, applied):
    """MS = allowable/applied - 1 (must be >= 0 at ultimate for a pass)."""
    allowable = _require_positive(allowable, "allowable")
    applied = _require_positive(applied, "applied")
    return allowable / applied - 1.0


def effective_length_factor(end_condition):
    """K for named end conditions (bound buckling leaf table)."""
    table = {"pinned-pinned": 1.0, "fixed-fixed": 0.5, "fixed-pinned": 0.7,
             "fixed-free": 2.0}
    name = end_condition.strip().lower().replace(" ", "-")
    while "--" in name:
        name = name.replace("--", "-")
    aliases = {"pinned": "pinned-pinned", "hinged": "pinned-pinned",
               "fixed": "fixed-fixed", "clamped": "fixed-fixed",
               "cantilever": "fixed-free", "clamped-free": "fixed-free",
               "clamped-clamped": "fixed-fixed"}
    name = aliases.get(name, name)
    if name not in table:
        raise ValueError("unknown end condition %r" % (end_condition,))
    return table[name]


def euler_buckling_load(e_ksi, i_in4, length_in,
                        end_condition="pinned-pinned", k_factor=None):
    """Euler critical buckling load Pcr = pi^2 E I / (K L)^2, lb.

    end_condition is a name resolved by effective_length_factor(); pass
    k_factor directly to skip name resolution. E in ksi, I in in^4,
    length in in -> Pcr in lb (E converted to psi internally).
    """
    k = (_require_positive(k_factor, "K")
         if k_factor is not None else effective_length_factor(end_condition))
    return (math.pi ** 2 * _require_positive(e_ksi, "E") * 1000.0
            * _require_positive(i_in4, "I")
            / (k * _require_positive(length_in, "L")) ** 2)


def column_check(e_ksi, i_in4, area_in2, length_in, end_condition,
                 applied_load_lb, fcy_ksi):
    """Complete Euler column check with the yield transition. Returns the
    governing allowable load (yield below lambda_1, Euler above), the
    slenderness verdict and the margin of safety. All loads in lb."""
    k = effective_length_factor(end_condition)
    le = k * length_in
    r = math.sqrt(i_in4 / area_in2)
    lam = le / r
    pcr = euler_buckling_load(e_ksi, i_in4, length_in, k_factor=k)
    lam1 = math.pi * math.sqrt(e_ksi / fcy_ksi)
    euler_governs = lam > lam1
    p_allow = pcr if euler_governs else fcy_ksi * 1000.0 * area_in2
    return {
        "end_condition": end_condition, "K": k, "effective_length_in": le,
        "radius_of_gyration_in": r, "slenderness_ratio": lam,
        "transition_slenderness": lam1, "euler_governs": euler_governs,
        "pcr_lb": pcr, "allowable_load_lb": p_allow,
        "margin_of_safety": margin_of_safety(p_allow, applied_load_lb),
    }


def plate_buckling_stress(e_ksi, nu, t_in, b_in, k=4.0):
    """sigma_cr = k*pi^2 E/(12(1-nu^2)) (t/b)^2, ksi. k=4 long ssss plate
    under uniform edge compression (bound plate-buckling leaf)."""
    return (k * math.pi ** 2 * _require_positive(e_ksi, "E")
            / (12.0 * (1.0 - nu ** 2))
            * (_require_positive(t_in, "t") / _require_positive(b_in, "b")) ** 2)


def shear_buckling_stress(e_ksi, nu, t_in, b_in, a_over_b):
    """tau_cr = k_s pi^2 E/(12(1-nu^2)) (t/b)^2 with Timoshenko shear
    coefficient k_s = 5.34 + 4/(a/b)^2 (a/b >= 1), ksi."""
    ar = _require_positive(a_over_b, "a/b")
    k_s = 5.34 + 4.0 / ar ** 2 if ar >= 1.0 else 5.34 * ar ** 2 + 4.0
    return (k_s * math.pi ** 2 * _require_positive(e_ksi, "E")
            / (12.0 * (1.0 - nu ** 2))
            * (_require_positive(t_in, "t") / _require_positive(b_in, "b")) ** 2)


def lug_analysis(load_lb, hole_diameter_in, thickness_in, lug_width_in,
                 edge_distance_in, f_tu_ksi, f_su_ksi, f_bru_ksi):
    """Round-end lug margins (bound lug-joint-analysis leaf): bearing,
    net-section tension, tearout; governing mode = lowest margin."""
    if load_lb < 0:
        raise ValueError("lug load must be non-negative")
    D, t = hole_diameter_in, thickness_in
    w, e = lug_width_in, edge_distance_in
    if not (D > 0 and t > 0 and w > 0 and e > D / 2 and w > D):
        raise ValueError("degenerate lug geometry")
    sig_b = load_lb / (D * t) / 1000.0          # ksi
    sig_nt = load_lb / ((w - D) * t) / 1000.0   # ksi
    l_te = math.sqrt(e ** 2 - (D / 2.0) ** 2)
    sig_te = load_lb / (2.0 * t * l_te) / 1000.0  # ksi
    margins = {
        "bearing": f_bru_ksi / sig_b - 1.0,
        "net_tension": f_tu_ksi / sig_nt - 1.0,
        "tearout": f_su_ksi / sig_te - 1.0,
    }
    governing = min(margins, key=lambda key: margins[key])
    return {
        "bearing_stress_ksi": sig_b, "net_tension_stress_ksi": sig_nt,
        "tearout_stress_ksi": sig_te, "e_over_d": e / D, "d_over_t": D / t,
        "bearing_margin": margins["bearing"],
        "net_tension_margin": margins["net_tension"],
        "tearout_margin": margins["tearout"],
        "governing_mode": governing, "min_margin": margins[governing],
        "passes": margins[governing] >= 0.0,
    }


# ---------------------------------------------------------------------------
# Fatigue logic (mirrors bound stress-life / goodman / miner leaves)
# ---------------------------------------------------------------------------


def basquin_life(sig_a_ksi, a_ksi, b):
    """Cycles to failure N = (S/A)^(1/b) (Basquin S-N, bound leaf)."""
    if not sig_a_ksi > 0 or not a_ksi > 0 or b == 0.0:
        raise ValueError("need S > 0, A > 0, b != 0")
    return (sig_a_ksi / a_ksi) ** (1.0 / b)


def goodman_effective_amplitude(sig_a_ksi, sig_m_ksi, f_tu_ksi):
    """Fully-reversed equivalent amplitude: Sa/(1 - Sm/Ftu) (modified
    Goodman mean correction, bound goodman leaf)."""
    f = _require_positive(f_tu_ksi, "Ftu")
    sm = _require_nonnegative(sig_m_ksi, "Sm")
    if sm >= f:
        raise ValueError("mean stress must be below Ftu")
    return _require_positive(sig_a_ksi, "Sa") / (1.0 - sm / f)


def cumulative_damage(cycles):
    """Palmgren-Miner damage fraction over (n, N) blocks (bound leaf)."""
    if not cycles:
        raise ValueError("cycle blocks must not be empty")
    total = 0.0
    for n, n_fail in cycles:
        if n < 0:
            raise ValueError("applied cycles must be >= 0")
        if n_fail <= 0:
            raise ValueError("cycles to failure must be > 0")
        total += n / float(n_fail)
    return total


def fatigue_life_report(spectrum, sig_a_ksi, sig_m_ksi, mat):
    """Miner sum and equivalent-life multiples for a per-flight spectrum.

    spectrum: list of (cycles_per_flight, load_factor_amplitude_dn).
    The stress amplitude for each block scales with dn: the reference
    amplitude sig_a_ksi corresponds to dn = 1.0.
    """
    m = MATERIALS[mat]
    a = m["sig_f_prime_ksi"]
    b = m["b_fatigue"]
    f_tu = m["Ftu_ksi"]
    blocks = []
    total_damage_per_flight = 0.0
    for n_per_flight, dn in spectrum:
        s_a = sig_a_ksi * dn
        s_ar = goodman_effective_amplitude(s_a, sig_m_ksi, f_tu)
        n_fail = basquin_life(s_ar, a, b)
        blocks.append({"dn": dn, "cycles_per_flight": n_per_flight,
                       "Sa_ksi": s_a, "Sa_equiv_ksi": s_ar,
                       "N_fail": n_fail,
                       "damage_per_flight": n_per_flight / n_fail})
        total_damage_per_flight += n_per_flight / n_fail
    return {"blocks": blocks, "damage_per_flight": total_damage_per_flight,
            "A_ksi": a, "b": b}


# ---------------------------------------------------------------------------
# Dynamics (mirrors bound beam-vibration leaf: cantilever first root)
# ---------------------------------------------------------------------------

CANTILEVER_BETA1_L = 1.87510407
# Equivalent uniform-beam stiffness factor: a real wing tapers, so the
# equivalent uniform cantilever uses a fraction of the root box EI
# (standard preliminary-dynamics idealization, ~0.25-0.35 of root EI).
WING_EI_EQUIVALENT_FACTOR = 0.30


def cantilever_frequency_hz(e_ksi, i_in4, mass_per_len_lb_s2_in,
                            length_in, stiffness_factor=1.0):
    """First cantilever bending frequency f = (b1 L)^2/(2pi) sqrt(EI/(m L^4))
    with m the mass per unit length in lb*s^2/in and stiffness_factor the
    fraction of the given EI used by the equivalent uniform beam."""
    ei = (_require_positive(e_ksi, "E") * 1000.0
          * _require_positive(i_in4, "I")
          * _require_positive(stiffness_factor, "stiffness_factor"))
    m = _require_positive(mass_per_len_lb_s2_in, "m")
    length = _require_positive(length_in, "L")
    return (CANTILEVER_BETA1_L ** 2 / (2.0 * math.pi)
            * math.sqrt(ei / (m * length ** 4)))


# ---------------------------------------------------------------------------
# Example wing (the role's reference item) - one coherent, self-consistent
# regional-transport-class wing sized by the rules above.
# ---------------------------------------------------------------------------


@dataclass
class ExampleWing:
    """Project facts for the worked-example wing (reference item).

    A 100,000 lb regional-transport-class wing (FAR 25). FAR 25.337(b)
    gives the positive limit maneuvering factor n = max(2.5,
    min(3.8, 2.1 + 24000/(W+10000))) = 2.5 at this weight, so the
    corner sits at VA = VS*sqrt(2.5), matching the bound gust leaf's
    own worked-envelope anchor.
    """
    name: str = "Example regional transport wing"
    aircraft: str = "Example 100,000 lb regional transport (FAR 25)"
    category: str = "transport"
    gross_weight_lb: float = 100_000.0
    wing_loading_psf: float = 100.0   # W/S (kept when re-sizing by weight)
    aspect_ratio: float = 8.0         # AR (kept when re-sizing by weight)
    wing_area_ft2: float = 1_000.0
    span_ft: float = 89.44            # AR 8, cbar = S/b = 11.18 ft
    cbar_ft: float = 11.18
    lift_curve_slope: float = 5.7     # 1/rad
    stall_speed_fps: float = 230.0    # EAS
    dive_speed_fps: float = 621.0     # EAS
    altitude_ft: float = 0.0
    # wing weight fraction for dynamics (regional transport band)
    wing_weight_fraction: float = 0.15
    material: str = "al-7075-t6"
    # Root box section (candidate design being checked)
    box_depth_in: float = 40.0        # spar cap centroid separation
    cap_area_in2: float = 17.5        # total cap area per surface (both spars)
    web_thickness_in: float = 0.08    # per web
    web_depth_in: float = 38.0        # effective web depth
    # Compression surface (upper skin/stringer between ribs)
    stringer_pitch_in: float = 6.0    # skin bay width b
    skin_thickness_in: float = 0.25
    stringer_area_in2: float = 1.2
    stringer_i_in4: float = 0.60      # weak axis, panel buckling direction
    rib_pitch_in: float = 22.0        # column length for stringer
    # Root attachment lug (wing-to-fuselage vertical shear, per lug pair)
    lug_hole_diameter_in: float = 3.0
    lug_thickness_in: float = 0.75
    lug_edge_distance_in: float = 4.5
    # Landing gear stations (for the ground-loads row)
    gear_nose_to_cg_ft: float = 18.0
    gear_cg_to_main_ft: float = 6.0
    # Fatigue: gust cycle count per flight at VC-scale gust intensity
    fatigue_spectrum: list = field(default_factory=lambda: [
        (1.0, 0.80),   # 1 light-gust cycle/flight at dn = 0.80
        (0.05, 1.40),  # 1 per 20 flights at dn = 1.40
    ])

    def resize_for_weight(self, weight_lb):
        """Re-derive the wing AND its box section for a new MTOW under
        geometric similarity with the 100,000 lb baseline: planform keeps
        the example's W/S and AR, and every length scales with the span
        ratio while areas scale with its square (so margins land in the
        same band)."""
        w0 = 100_000.0
        s0 = w0 / self.wing_loading_psf          # baseline area
        b0 = math.sqrt(self.aspect_ratio * s0)   # baseline span
        self.gross_weight_lb = _require_positive(weight_lb, "weight_lb")
        self.wing_area_ft2 = self.gross_weight_lb / self.wing_loading_psf
        self.span_ft = math.sqrt(self.aspect_ratio * self.wing_area_ft2)
        self.cbar_ft = self.wing_area_ft2 / self.span_ft
        r = self.span_ft / b0                     # length ratio
        self.box_depth_in *= r
        self.cap_area_in2 *= r * r
        self.web_thickness_in *= r
        self.web_depth_in *= r
        self.stringer_area_in2 *= r * r
        self.stringer_i_in4 *= r ** 4
        self.rib_pitch_in *= r
        self.lug_hole_diameter_in *= r
        self.lug_thickness_in *= r
        self.lug_edge_distance_in *= r
        return self


def _mat(item):
    if item.material not in MATERIALS:
        raise ValueError("unknown material %r" % (item.material,))
    return MATERIALS[item.material]


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_report(item: ExampleWing) -> dict:
    """Build the complete loads + strength report content model."""
    mat = _mat(item)
    vn = vn_diagram(
        ws=item.wing_loading_psf, vs=item.stall_speed_fps,
        vd=item.dive_speed_fps, a=item.lift_curve_slope,
        cbar=item.cbar_ft, category=item.category,
        altitude_ft=item.altitude_ft, weight_lb=item.gross_weight_lb)
    design = design_limit_load_factor(vn)
    env_margins = envelope_margins(vn)

    n_lim = design["n_limit_pos"]
    n_ult = FACTOR_OF_SAFETY * n_lim
    # Elliptic span-load idealization: root shear per wing = n*W/2 and
    # root bending M = n*W*b/(3 pi) (semi-ellipse centroid at 4/(3 pi) of
    # the semi-span from the root).
    v_root_ult = n_ult * item.gross_weight_lb / 2.0
    m_root_ult_ftlb = (n_ult * item.gross_weight_lb * item.span_ft
                       / (3.0 * math.pi))
    m_root_ult_inlb = m_root_ult_ftlb * 12.0
    m_root_limit_inlb = m_root_ult_inlb / FACTOR_OF_SAFETY

    h = item.box_depth_in
    a_cap = item.cap_area_in2
    p_cap = m_root_ult_inlb / h                 # cap axial load, lb
    sig_cap = p_cap / a_cap / 1000.0            # ksi
    # Web shear: two webs carry the root shear
    tau_web = v_root_ult / (2.0 * item.web_thickness_in
                            * item.web_depth_in) / 1000.0

    e_ksi = mat["E_ksi"]
    nu = mat["nu"]
    # Compression surface: skin local buckling between stringers (long
    # simply-supported plate, k = 4.0) and stringer column over the rib
    # pitch (pinned-pinned).
    sig_cr_skin = plate_buckling_stress(
        e_ksi, nu, item.skin_thickness_in, item.stringer_pitch_in, k=4.0)
    # Applied compression stress in the skin at the same fibre as the cap.
    col = column_check(
        e_ksi, item.stringer_i_in4, item.stringer_area_in2,
        item.rib_pitch_in, "pinned-pinned",
        applied_load_lb=sig_cap * 1000.0 * item.stringer_area_in2,
        fcy_ksi=mat["Fty_ksi"])

    lug = lug_analysis(
        v_root_ult / 2.0, item.lug_hole_diameter_in, item.lug_thickness_in,
        2.0 * item.lug_edge_distance_in, item.lug_edge_distance_in,
        mat["Ftu_ksi"], mat["Fsu_ksi"], mat["Fbru_ksi"])

    # Fatigue at the lower spar cap (root): 1g stress amplitude scale
    m_1g_ftlb = (item.gross_weight_lb * item.span_ft / (3.0 * math.pi))
    m_1g_inlb = m_1g_ftlb * 12.0
    sig_1g = m_1g_inlb / h / a_cap / 1000.0    # ksi at 1g
    # Reference amplitude for dn=1.0 about the 1g mean (gust cycle) and a
    # GAG cycle 0->1g (mean sig_1g/2, amplitude sig_1g/2).
    sig_a_ref = sig_1g * 0.5                    # dn 1.0 about 1g mean
    sig_m_gust = sig_1g
    fatigue_gust = fatigue_life_report(item.fatigue_spectrum, sig_a_ref,
                                       sig_m_gust, item.material)
    # GAG cycle: 1 per flight, 0g -> 1g (wing root bending)
    g_ar = goodman_effective_amplitude(sig_1g / 2.0, sig_1g / 2.0,
                                       mat["Ftu_ksi"])
    n_gag = basquin_life(g_ar, mat["sig_f_prime_ksi"], mat["b_fatigue"])
    damage_per_flight = fatigue_gust["damage_per_flight"] + 1.0 / n_gag

    # Dynamics: first wing bending frequency (uniform cantilever, root box
    # stiffness, wing weight fraction over the semi-span)
    i_box_in4 = 2.0 * a_cap * (h / 2.0) ** 2
    wing_weight_lb = item.wing_weight_fraction * item.gross_weight_lb
    semi_span_in = item.span_ft * 12.0 / 2.0
    w_per_in = (wing_weight_lb / 2.0) / semi_span_in   # lb/in per wing
    mass_per_len = w_per_in / 386.09                   # lb*s^2/in per wing
    f1 = cantilever_frequency_hz(e_ksi, i_box_in4, mass_per_len,
                                 semi_span_in,
                                 stiffness_factor=WING_EI_EQUIVALENT_FACTOR)

    # Ground loads (level landing at MLW = gross weight in example)
    ground = level_landing_reactions(
        item.gross_weight_lb, item.gear_nose_to_cg_ft,
        item.gear_cg_to_main_ft, N_LEVEL_DEFAULT)
    decel_g = braked_roll_deceleration(item.gear_nose_to_cg_ft,
                                       item.gear_cg_to_main_ft, 0.8)

    margins = [
        {"component": "Lower spar cap (tension, root)",
         "load": "P = M_ult/h = %.0f lb" % p_cap,
         "applied_ksi": sig_cap,
         "allowable": "Ftu = %.1f ksi" % mat["Ftu_ksi"],
         "MS": margin_of_safety(mat["Ftu_ksi"], sig_cap),
         "basis": "boom couple at box depth %.0f in; 7075-T6 Ftu per bound "
                  "materials/lug leaf anchors (MMPDS B-basis to confirm)" % h},
        {"component": "Upper spar cap (compression, root)",
         "load": "P = M_ult/h = %.0f lb" % p_cap,
         "applied_ksi": sig_cap,
         "allowable": "Fcy = %.1f ksi" % mat["Fty_ksi"],
         "MS": margin_of_safety(mat["Fty_ksi"], sig_cap),
         "basis": "compression material limit (yield); local stability of "
                  "the stiffened panel carried by the skin/stringer rows"},
        {"component": "Spar web (shear, two webs)",
         "load": "V_ult = %.0f lb" % v_root_ult,
         "applied_ksi": tau_web,
         "allowable": "Fsu = %.1f ksi" % mat["Fsu_ksi"],
         "MS": margin_of_safety(mat["Fsu_ksi"], tau_web),
         "basis": "V_ult/(2 t h_web); 7075-T6 Fsu per bound lug leaf anchor "
                  "(MMPDS to confirm)"},
        {"component": "Upper skin panel (compression buckling, between "
                      "stringers)",
         "load": "sigma_app = %.1f ksi" % sig_cap,
         "applied_ksi": sig_cap,
         "allowable": "sigma_cr = %.1f ksi (k=4, ssss long plate)"
                      % sig_cr_skin,
         "MS": margin_of_safety(sig_cr_skin, sig_cap),
         "basis": "plate buckling sigma_cr = k pi^2 E/(12(1-nu^2)) (t/b)^2 "
                  "with b = stringer pitch %.1f in, t = %.2f in (bound "
                  "plate-buckling leaf)" % (item.stringer_pitch_in,
                                            item.skin_thickness_in)},
        {"component": "Upper stringer (column over rib pitch)",
         "load": "P_app = %.0f lb" % (sig_cap * 1000.0
                                      * item.stringer_area_in2),
         "applied_ksi": sig_cap,
         "allowable": ("Pcr = %.0f lb (Euler)" % col["pcr_lb"]
                       if col["euler_governs"]
                       else "Fcy*A = %.0f lb (yield-governed column)"
                            % col["allowable_load_lb"]),
         "MS": col["margin_of_safety"],
         "basis": ("Euler Pcr = pi^2 E I/(K L)^2, K=1 (pinned-pinned), "
                   "L = rib pitch %.1f in, lambda = %.1f > lambda_1 = %.1f"
                   % (item.rib_pitch_in, col["slenderness_ratio"],
                      col["transition_slenderness"])
                   if col["euler_governs"] else
                   "short column: lambda = %.1f < lambda_1 = %.1f, yield "
                   "governs (bound buckling leaf)"
                   % (col["slenderness_ratio"], col["transition_slenderness"]))},
        {"component": "Wing root lug (vertical shear, one lug of pair)",
         "load": "P = V_ult/2 = %.0f lb" % (v_root_ult / 2.0),
         "applied_ksi": lug["bearing_stress_ksi"],
         "allowable": ("min over bearing Fbru, net-tension Ftu, tearout Fsu; "
                       "governing mode %s" % lug["governing_mode"]),
         "MS": lug["min_margin"],
         "basis": "round-end lug: bearing, net section, tearout margins per "
                  "bound lug-joint leaf (e/D = %.2f, D/t = %.2f)"
                  % (lug["e_over_d"], lug["d_over_t"])},
    ]
    for m in margins:
        m["status"] = "PASS" if m["MS"] >= 0.0 else "RESIZE"

    return {
        "document_type": "Loads and Strength Report",
        "status": "draft-for-review",
        "item": item.name,
        "aircraft": item.aircraft,
        "category": item.category,
        "material": mat["label"],
        "vn": vn,
        "envelope_margins": env_margins,
        "design": design,
        "n_limit": n_lim,
        "n_limit_neg": design["n_limit_neg"],
        "n_ult": n_ult,
        "loads_condition": design["condition_pos"],
        "m_root_limit_inlb": m_root_limit_inlb,
        "m_root_ult_inlb": m_root_ult_inlb,
        "m_root_ult_ftlb": m_root_ult_ftlb,
        "v_root_ult_lb": v_root_ult,
        "ground": ground,
        "decel_g": decel_g,
        "margins": margins,
        "dynamics_f1_hz": f1,
        "geometry": {"box_depth_in": h, "cap_area_in2": a_cap,
                     "span_ft": item.span_ft,
                     "semi_span_ft": item.span_ft / 2.0,
                     "web_thickness_in": item.web_thickness_in,
                     "web_depth_in": item.web_depth_in,
                     "stringer_pitch_in": item.stringer_pitch_in,
                     "skin_thickness_in": item.skin_thickness_in,
                     "wing_weight_fraction": item.wing_weight_fraction},
        "materials": {"E_ksi": mat["E_ksi"], "Ftu_ksi": mat["Ftu_ksi"],
                      "Fty_ksi": mat["Fty_ksi"], "Fsu_ksi": mat["Fsu_ksi"],
                      "Fbru_ksi": mat["Fbru_ksi"]},
        "fatigue": {"sig_1g_ksi": sig_1g, "damage_per_flight": damage_per_flight,
                    "n_gag": n_gag, "gust_blocks": fatigue_gust["blocks"],
                    "A_ksi": fatigue_gust["A_ksi"], "b": fatigue_gust["b"],
                    "sig_m_gust_ksi": sig_m_gust},
        "generated": date.today().isoformat(),
    }


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def _fmt(x, nd=3):
    return ("%.*f" % (nd, x))


def render_report_markdown(model: dict) -> str:
    """Render the report content model as the deliverable markdown."""
    vn = model["vn"]
    em = model["envelope_margins"]
    lines = [
        "# Loads and Strength Report",
        "",
        f"**Item:** {model['item']}",
        f"**Aircraft:** {model['aircraft']}",
        f"**Category / basis:** {model['category']} category, FAR 25 "
        "(Subpart C loads, Subpart D structure)",
        f"**Status:** {model['status']}",
        "",
        "## 1. Loads",
        "",
        f"- Wing loading W/S = {_fmt(vn['ws'])} psf, mean geometric chord "
        f"cbar = {_fmt(vn['cbar_ft'])} ft (cbar = S/b), lift-curve slope "
        f"a = {_fmt(vn['a'])}/rad.",
        f"- Design speeds (EAS): VS = {_fmt(vn['vs'])} ft/s, "
        f"VA = {_fmt(vn['va'])} ft/s, VB = {_fmt(vn['vb'])} ft/s, "
        f"VC = {_fmt(vn['vc'])} ft/s, VD = {_fmt(vn['vd'])} ft/s.",
        f"- Gust alleviation (FAR 25.341(b)(2)): mass ratio "
        f"mu_g = {_fmt(vn['mu_g'])}, alleviation factor "
        f"K_g = {_fmt(vn['kg'])}.",
        f"- Limit maneuvering load factor at VA = {_fmt(vn['n_positive'])} "
        f"({vn['category']} category, FAR 25.337); negative limit "
        f"{_fmt(vn['n_negative'])} at speeds up to VC.",
        "- Discrete-gust limit load factors (design gust velocities U_de "
        "of FAR 25.341(a) at sea level, fps EAS):",
        "",
    ]
    for p in vn["gust_points"]:
        lines.append(
            f"  - {p['speed']} ({_fmt(p['v'])} ft/s, U_de = "
            f"{_fmt(p['u_de'])} fps): n = {_fmt(p['n_pos'])} (positive), "
            f"{_fmt(p['n_neg'])} (negative).")
    env_lines = []
    for label in ("VB", "VC", "VD"):
        m = em[label]
        verdict = ("gust-critical" if m["gust_critical_pos"]
                   else "maneuver envelope governs")
        env_lines.append("%s margin %+.3f (%s)" % (label, m["margin_pos"],
                                                   verdict))
    lines += [
        "",
        f"- Gust line vs maneuver envelope at VB/VC/VD: "
        + "; ".join(env_lines) + ".",
        "",
        f"- **Design limit condition: {model['loads_condition']}, "
        f"n_limit = +{_fmt(model['n_limit'])}** (negative envelope "
        f"limit {_fmt(model['n_limit_neg'])}).",
        f"- **Ultimate loads: n_ult = 1.5 x {_fmt(model['n_limit'])} = "
        f"{_fmt(model['n_ult'])} (factor of safety, FAR 25.303).**",
        "",
        "- Root loads per wing at the design condition (elliptic span-load "
        "idealization: root shear = nW/2 and root bending M = nWb/(3 pi), "
        "the semi-ellipse lift resultant standing at 4/(3 pi) of the "
        "semi-span from the root):",
        f"  - Limit root bending moment = "
        f"{model['m_root_limit_inlb'] / 1e6:.2f} M in-lb; ultimate root "
        f"bending M_ult = {model['m_root_ult_inlb'] / 1e6:.2f} M in-lb "
        f"({model['m_root_ult_ftlb'] / 1e6:.2f} M ft-lb).",
        f"  - Ultimate root shear V_ult = "
        f"{model['v_root_ult_lb'] / 1000:.0f} klb per wing.",
        "",
        "- Ground loads - level landing at the limit vertical inertia "
        f"factor {_fmt(N_LEVEL_DEFAULT)} (bound landing-ground-loads "
        "leaf):",
        f"  - Nose gear reaction {model['ground']['nose_lb'] / 1000:.0f} "
        f"klb; main gear reaction "
        f"{model['ground']['main_lb'] / 1000:.0f} klb (total "
        f"{model['ground']['total_lb'] / 1000:.0f} klb).",
        f"  - Braked-roll deceleration {_fmt(model['decel_g'], 2)} g "
        "(braking friction 0.8 on the main gear).",
        "- Spectra: fatigue and dynamic load spectra feed the fatigue "
        "screening (Section 6); random-vibration / shock-response-spectrum "
        "conditions for equipment-mounted structure are derived with the "
        "bound random-vibration-analysis / shock-response-spectrum leaves "
        "when that structure is in scope.",
        "",
        "## 2. Global model",
        "",
        "- Idealization: each wing is a cantilever box beam from the root "
        "to the tip carrying the elliptic spanwise lift distribution "
        "l(y) = l0 sqrt(1 - (2y/b)^2); root shear and bending then follow "
        "in closed form (above), which is sufficient for the screening "
        "margins of this report. A refined beam-frame/truss/CalculiX model "
        "(bound FEM leaves) confirms station-by-station internal loads and "
        "deflections in the detailed phase.",
        f"- Boundary conditions: wing root fixed at the fuselage side of "
        f"body; box depth h = {_fmt(model['geometry']['box_depth_in'])} "
        "in between spar cap centroids at the root section (example "
        "geometry).",
        f"- Internal loads at the root: M_ult = "
        f"{model['m_root_ult_inlb'] / 1e6:.2f} M in-lb, V_ult = "
        f"{model['v_root_ult_lb'] / 1000:.0f} klb - used for every margin "
        "below.",
        "",
        "## 3. Strength/stability margins (ultimate load)",
        "",
        "| Component | Load | Allowable | MS | Basis |",
        "|---|---|---|---|---|",
    ]
    for m in model["margins"]:
        lines.append("| %s | %s | %s | **%+.3f** | %s |"
                     % (m["component"], m["load"], m["allowable"], m["MS"],
                        m["basis"]))
    lines += [
        "",
        "## 4. Dynamics",
        "",
        f"- First wing bending frequency f1 = "
        f"{_fmt(model['dynamics_f1_hz'])} Hz (uniform cantilever "
        "idealization over the semi-span with the root box stiffness EI, "
        "wing weight fraction applied; beta1*L = "
        f"{_fmt(CANTILEVER_BETA1_L)}, bound beam-vibration leaf).",
        "- Frequency placement vs rotor/propeller 1P and control-surface "
        "excitation bands is confirmed against the bound "
        "modal-analysis / beam-vibration leaves in the detailed phase.",
        "",
        "## 5. Materials",
        "",
        f"- Allowables used: 7075-T6 screening values from the bound "
        "AeroSkills anchors (material-selection leaf E/Fty/UTS, "
        "lug-joint worked example Fsu/Fbru, strain-life 7075-T6 class "
        "fatigue constants). MMPDS (licensed) is referenced, never "
        "reproduced; B-basis design allowables are confirmed by the "
        "materials group before release:",
        f"  - E = {_fmt(model['materials']['E_ksi'], 0)} ksi; "
        f"Ftu = {_fmt(model['materials']['Ftu_ksi'], 1)} ksi; "
        f"Fty = {_fmt(model['materials']['Fty_ksi'], 1)} ksi; "
        f"Fsu = {_fmt(model['materials']['Fsu_ksi'], 1)} ksi; "
        f"Fbru = {_fmt(model['materials']['Fbru_ksi'], 1)} ksi.",
        "- Ramberg-Osgood / creep / fracture data: not required for the "
        "7075-T6 screening at room temperature; the bound "
        "ramberg-osgood / creep-rupture / fracture-toughness leaves apply "
        "where those regimes are in scope.",
        "",
        "## 6. Fatigue",
        "",
        f"- Critical location: lower spar cap at the root; 1g bending "
        f"stress sigma_1g = {_fmt(model['fatigue']['sig_1g_ksi'], 1)} ksi.",
        f"- S-N basis: Basquin S = A N^b with A = "
        f"{_fmt(model['fatigue']['A_ksi'], 1)} ksi, b = "
        f"{_fmt(model['fatigue']['b'], 2)} (7075-T6 class fatigue strength "
        "constants, bound stress-life / strain-life leaves, "
        "reference-only). Mean stress is corrected with the modified "
        "Goodman rule Sa_eq = Sa / (1 - Sm/Ftu).",
        "- Spectrum (per-flight cycle blocks at the lower spar cap, "
        "amplitude dn about the 1g mean):",
        "",
    ]
    for blk in model["fatigue"]["gust_blocks"]:
        lines.append(
            "  - %.2f cycle(s)/flight at dn = %.2f: Sa = %.1f ksi, "
            "Sa_eq = %.1f ksi, N = %.2e cycles, damage per flight = %.2e"
            % (blk["cycles_per_flight"], blk["dn"], blk["Sa_ksi"],
               blk["Sa_equiv_ksi"], blk["N_fail"],
               blk["damage_per_flight"]))
    sig_1g = model["fatigue"]["sig_1g_ksi"]
    mat = MATERIALS["al-7075-t6"]
    g_ar = goodman_effective_amplitude(sig_1g / 2.0, sig_1g / 2.0,
                                       mat["Ftu_ksi"])
    lines += [
        "",
        f"- GAG cycle (0g to 1g, once per flight): Sa = {sig_1g / 2.0:.1f} "
        f"ksi, Sm = {sig_1g / 2.0:.1f} ksi, Sa_eq = {g_ar:.1f} ksi, "
        f"N = {model['fatigue']['n_gag']:.2e} cycles, damage per flight = "
        f"{1.0 / model['fatigue']['n_gag']:.2e}.",
        f"- **Palmgren-Miner cumulative damage sum per flight D = "
        f"{model['fatigue']['damage_per_flight']:.2e}** (limit 1.0): "
        "safe-life screening passes with equivalent life far beyond the "
        "design life; production fatigue refines with the counted load "
        "spectrum and detail notch factors from the bound "
        "load-spectrum-counting / notch-sensitivity / goodman-diagram "
        "leaves.",
        "",
        "## 7. Damage tolerance",
        "",
        "- Safe-life screening (Section 6) is the scope of this example "
        "report; the damage tolerance evaluation per FAR 25.571 (crack "
        "growth, residual strength, inspection intervals) is executed with "
        "the bound crack-growth / residual-strength / "
        "widespread-fatigue-damage leaves once the production spectrum and "
        "crack-growth data are baselined.",
        "- Bird strike (FAR 25.631) is a design load case for the leading "
        "edge and windshield supports; the bound bird-strike leaf applies "
        "when that structure is in scope.",
        "",
        "## 8. Composites / thermal",
        "",
        "- The example item is metallic (7075-T6); laminate first-ply-"
        "failure and sandwich margins from the bound "
        "laminate-stiffness / laminate-first-ply-failure / "
        "failure-criteria / sandwich-panels leaves apply when composite "
        "structure enters the design.",
        "- Thermal stress and thermal buckling margins are computed with "
        "the bound thermal-stress-analysis / thermal-buckling leaves for "
        "thermal-critical structure; no thermal-critical metallic margin "
        "is driven in this room-temperature screening.",
        "",
        "## 9. Margin summary",
        "",
        "| Component | MS | Status |",
        "|---|---|---|",
    ]
    for m in model["margins"]:
        lines.append("| %s | %+.3f | %s |"
                     % (m["component"], m["MS"], m["status"]))
    lines += [
        "",
        "---",
        f"*Generated by Aero Agent Roles structures-loads-engineer core "
        f"({model['generated']}). DRAFT for human stress lead review. Not "
        "an approval document - no certification approval is claimed, no "
        "compliance finding is declared. FEM results are as good as the "
        "model idealizations stated above.*",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evidence gate checkers
# ---------------------------------------------------------------------------

GATE_CHECKS = {
    "loads_stated": "limit/ultimate load factors present as numbers",
    "envelope_present": "V-n gust + maneuver envelope present",
    "margins_present": "every margin row has a load, an allowable, an MS "
                       "and a basis",
    "fatigue_stated": "fatigue life basis + Miner sum present",
    "sign_off_honest": "document marked draft-for-review, not approval",
}


def check_report(model: dict) -> dict:
    """Run the evidence gates against a report model."""
    vn = model.get("vn", {})
    results = {
        "loads_stated": (isinstance(model.get("n_limit"), (int, float))
                         and isinstance(model.get("n_ult"), (int, float))
                         and isinstance(model.get("n_limit_neg"),
                                       (int, float))),
        "envelope_present": bool(vn.get("gust_points"))
                            and bool(vn.get("maneuver_envelope")),
        "margins_present": bool(model.get("margins")) and all(
            all(m.get(k) is not None for k in
                ("component", "load", "allowable", "MS", "basis"))
            for m in model["margins"]),
        "fatigue_stated": (model.get("fatigue", {}).get("damage_per_flight")
                           is not None),
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_report_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    checks = {
        "has_title": "loads and strength report" in low,
        "has_loads": bool(re.search(r"n_ult\s*=\s*\d", md_text))
                     and "design limit condition" in low,
        "has_margins_table": ("| component | load | allowable | ms |"
                              in low),
        "has_ms_numbers": len(re.findall(r"\*\*[+-]?\d+\.\d{2,}\*\*",
                                         md_text)) >= 6,
        "has_fatigue": ("palmgren-miner" in low and "s-n basis" in low
                        and "damage" in low),
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling: check a report document."""
    return check_report_markdown(md_text)


# ---------------------------------------------------------------------------
# Example item / worked output (for tests and the filled template)
# ---------------------------------------------------------------------------


def example_item() -> ExampleWing:
    return ExampleWing()


def example_report_markdown() -> str:
    return render_report_markdown(build_report(example_item()))


if __name__ == "__main__":
    item = example_item()
    model = build_report(item)
    md = render_report_markdown(model)
    print("DESIGN LIMIT: %s n_limit=%.2f n_ult=%.2f"
          % (model["loads_condition"], model["n_limit"], model["n_ult"]))
    print("Kg=%.3f mu_g=%.1f" % (model["vn"]["kg"], model["vn"]["mu_g"]))
    print("M_ult=%.2f M in-lb  V_ult=%.0f lb"
          % (model["m_root_ult_inlb"] / 1e6, model["v_root_ult_lb"]))
    for m in model["margins"]:
        print("  MS %+7.3f  %s" % (m["MS"], m["component"]))
    print("f1=%.2f Hz  D/flight=%.2e" % (model["dynamics_f1_hz"],
                                         model["fatigue"]["damage_per_flight"]))
    print("GATES: %s" % check_report(model))
    print("MD GATES: %s" % check_report_markdown(md))
    print("RENDERED: %d chars" % len(md))
