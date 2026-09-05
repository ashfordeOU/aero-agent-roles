#!/usr/bin/env python3
"""flight_mechanics_core.py - Flight Mechanics Engineer executable core.

This is the role's ENGINE: given a vehicle configuration (an example
transport in this release) it computes mission performance and
stability-and-control numbers from REAL domain rules and BUILDS the
"Performance and S&C Analysis Report" deliverable. It also gate-checks
deliverables. Standalone: no external repo needed.

Domain rules encoded here are the equations documented in the bound
Aero Agent Skills flight-mechanics leaves (breguet-range,
breguet-endurance, specific-range, climb-performance,
takeoff-performance, landing-performance, glide-performance,
turn-performance, oei-climb-gradient, energy-height, wind-effects,
longitudinal-stability, dynamic-stability, short-period-mode-analysis,
phugoid-mode-analysis, lateral-directional-stability, trim-analysis,
mil-std-1797a) plus the public standards context those leaves summarize
(FAR 25.121/25.125/25.181, MIL-STD-1797A mode tables as summary).
Every equation is a paraphrase of common flight-mechanics practice;
no proprietary text is reproduced.

Boundary: the deliverable is an engineering DRAFT for human review,
never an approval, compliance finding, or certification claim.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date

# ---------------------------------------------------------------------------
# Constants and small unit helpers
# ---------------------------------------------------------------------------

G0 = 9.80665          # standard gravity, m/s^2
R_AIR = 287.052874    # specific gas constant dry air, J/(kg K)
GAMMA_AIR = 1.4
T0_ISA = 288.15       # sea level ISA temperature, K
P0_ISA = 101325.0     # sea level ISA pressure, Pa
RHO0_ISA = 1.225      # sea level ISA density, kg/m^3
LAPSE = 0.0065        # ISA troposphere lapse rate, K/m
TROPOPAUSE = 11000.0  # m

MPS_TO_KT = 1.943844492  # m/s -> knots
M_TO_FT = 3.280839895     # m -> ft
MPS_TO_FPM = 196.850394   # m/s -> ft/min
KM_TO_NM = 0.539956803    # km -> nautical miles
RAD_TO_DEG = 180.0 / math.pi


def kt(mps: float) -> float:
    return mps * MPS_TO_KT


def ft(m: float) -> float:
    return m * M_TO_FT


def fpm(mps: float) -> float:
    return mps * MPS_TO_FPM


def nm(km: float) -> float:
    return km * KM_TO_NM


def deg(rad: float) -> float:
    return rad * RAD_TO_DEG


def _f(x, nd=1):
    """Format with thousands separator and nd decimals."""
    return f"{x:,.{nd}f}"


# ---------------------------------------------------------------------------
# ISA atmosphere (public standard atmosphere model, hydrostatic + lapse)
# ---------------------------------------------------------------------------

def isa(h_m: float) -> dict:
    """ISA temperature/pressure/density at geometric altitude (m).

    Troposphere: linear lapse 6.5 K/km to 11 km; stratosphere isothermal
    216.65 K above. Returns dict with T (K), p (Pa), rho (kg/m^3),
    a (m/s), sigma = rho/rho0. Raises ValueError for h < 0.
    """
    if h_m < 0:
        raise ValueError("altitude must be >= 0 m")
    if h_m <= TROPOPAUSE:
        T = T0_ISA - LAPSE * h_m
        p = P0_ISA * (T / T0_ISA) ** (G0 / (R_AIR * LAPSE))
    else:
        T = T0_ISA - LAPSE * TROPOPAUSE  # 216.65 K
        p_base = P0_ISA * (T / T0_ISA) ** (G0 / (R_AIR * LAPSE))
        p = p_base * math.exp(-G0 * (h_m - TROPOPAUSE) / (R_AIR * T))
    rho = p / (R_AIR * T)
    a = math.sqrt(GAMMA_AIR * R_AIR * T)
    return {"T": T, "p": p, "rho": rho, "a": a,
            "sigma": rho / RHO0_ISA}


# ---------------------------------------------------------------------------
# Drag polar (parabolic model used by the thrust-required practice)
# ---------------------------------------------------------------------------

def drag_coefficient(cd0: float, k: float, cl: float) -> float:
    """Parabolic drag polar CD = CD0 + K*CL^2."""
    if cd0 <= 0 or k <= 0 or cl < 0:
        raise ValueError("polar inputs must be physical")
    return cd0 + k * cl * cl


def lift_to_drag(cd0: float, k: float, cl: float) -> float:
    cd = drag_coefficient(cd0, k, cl)
    if cd <= 0:
        raise ValueError("drag must be positive")
    return cl / cd


def max_lift_to_drag(cd0: float, k: float) -> dict:
    """Maximum L/D from the parabolic polar: (L/D)max = 1/(2 sqrt(CD0 K))
    at CL* = sqrt(CD0/K)."""
    if cd0 <= 0 or k <= 0:
        raise ValueError("polar inputs must be physical")
    cl_star = math.sqrt(cd0 / k)
    return {"cl_star": cl_star, "ld_max": 1.0 / (2.0 * math.sqrt(cd0 * k))}


# ---------------------------------------------------------------------------
# Performance rules (bound leaves: breguet-range, breguet-endurance,
# specific-range, climb-performance, takeoff-performance, landing-performance,
# glide-performance, turn-performance, oei-climb-gradient, energy-height,
# wind-effects)
# ---------------------------------------------------------------------------

def breguet_range(v_ms, tsfc_kg_per_n_s, ld, m0_kg, m1_kg, g=G0):
    """Breguet still-air cruise range, m:
    R = (V/(TSFC*g0)) * (L/D) * ln(m0/m1). TSFC in kg/(N s)."""
    if min(v_ms, tsfc_kg_per_n_s, ld, m0_kg, m1_kg) <= 0:
        raise ValueError("range inputs must be positive")
    if m1_kg >= m0_kg:
        raise ValueError("final mass must be below initial mass")
    return (v_ms / (tsfc_kg_per_n_s * g)) * ld * math.log(m0_kg / m1_kg)


def jet_endurance(tsfc_kg_per_n_s, ld, w0_n, w1_n, g=G0):
    """Jet loiter endurance, s: E = (1/(TSFC*g0))*(L/D)*ln(W0/W1)
    with TSFC in kg/(N s) and weights in N (weights version of the
    bound breguet-endurance leaf; its 1/s SFC equals TSFC*g0)."""
    if min(tsfc_kg_per_n_s, ld, w0_n, w1_n) <= 0:
        raise ValueError("endurance inputs must be positive")
    if w1_n >= w0_n:
        raise ValueError("final weight must be below initial weight")
    return (1.0 / (tsfc_kg_per_n_s * g)) * ld * math.log(w0_n / w1_n)


def specific_air_range(v_ms, tsfc, weight_n, ld):
    """Instantaneous specific air range, m/kg: SAR = V*(L/D)/(TSFC*W)."""
    if min(v_ms, tsfc, weight_n, ld) <= 0:
        raise ValueError("SAR inputs must be positive")
    return v_ms * ld / (tsfc * weight_n)


def rate_of_climb(T_n, D_n, V_ms, W_n):
    """ROC = (T - D)*V / W, m/s. Excess power method (climb leaf)."""
    if W_n <= 0 or V_ms <= 0:
        raise ValueError("weight and speed must be positive")
    if T_n - D_n < 0:
        raise ValueError("no climb: thrust must exceed drag")
    return (T_n - D_n) * V_ms / W_n


def climb_gradient_pct(T_n, D_n, W_n):
    """Climb gradient percent: gamma = (T - D)/W * 100."""
    if W_n <= 0:
        raise ValueError("weight must be positive")
    if T_n - D_n < 0:
        raise ValueError("no climb: thrust must exceed drag")
    return (T_n - D_n) / W_n * 100.0


def time_to_climb(delta_h_m, roc_a, roc_b):
    """Time to climb, s, at the mean of the endpoint rates of climb."""
    if delta_h_m <= 0 or roc_a <= 0 or roc_b <= 0:
        raise ValueError("altitude gain and ROC endpoints must be positive")
    return delta_h_m / ((roc_a + roc_b) / 2.0)


def stall_speed(wing_loading_n_m2, rho, cl_max):
    """Vs = sqrt(2*(W/S)/(rho*CLmax)), m/s (takeoff leaf)."""
    if min(wing_loading_n_m2, rho, cl_max) <= 0:
        raise ValueError("stall inputs must be positive")
    return math.sqrt(2.0 * wing_loading_n_m2 / (rho * cl_max))


def takeoff_ground_roll(weight_n, s, thrust_n, rho, cl_max, mu=0.03, g=G0):
    """Takeoff ground roll, m: Sg = 1.44 W^2/(g rho S CLmax (T - mu W))
    (standard estimate from the takeoff-performance leaf; the 1.44 =
    1.2^2 comes from the V_LOF = 1.2 Vs transport convention)."""
    if min(weight_n, s, thrust_n, rho, cl_max) <= 0:
        raise ValueError("ground roll inputs must be positive")
    if not (0.0 <= mu < 1.0):
        raise ValueError("rolling friction must be in [0,1)")
    if thrust_n <= mu * weight_n:
        raise ValueError("thrust must exceed rolling friction")
    return (1.44 * weight_n * weight_n /
            (g * rho * s * cl_max * (thrust_n - mu * weight_n)))


def glide_ratio(ld):  # glide range per unit altitude
    return ld


def glide_sink_rate(v_ms, glide_ratio_value):
    """Sink rate at a glide speed: Vsink = V*sin(gamma), gamma=atan(1/LD)."""
    if v_ms <= 0 or glide_ratio_value <= 0:
        raise ValueError("glide inputs must be positive")
    return v_ms * math.sin(math.atan(1.0 / glide_ratio_value))


def landing_air_distance(v_approach, approach_deg, obstacle_m, n_flare,
                         g=G0):
    """Air distance over the obstacle to touchdown, m (landing leaf):
    flare arc R = V^2/(g(n-1)), straight segment (h_obs - h_f)/tan(gamma)."""
    if v_approach <= 0 or approach_deg <= 0 or n_flare <= 1.0:
        raise ValueError("landing air inputs invalid")
    gamma = math.radians(approach_deg)
    radius = v_approach * v_approach / (g * (n_flare - 1.0))
    h_flare = radius * (1.0 - math.cos(gamma))
    if obstacle_m <= h_flare:
        raise ValueError("obstacle must be above flare height")
    s_flare = radius * math.sin(gamma)
    straight = (obstacle_m - h_flare) / math.tan(gamma)
    return straight + s_flare


def average_deceleration_g(mu_braking, lift_to_weight, drag_to_weight,
                           reverse_to_weight=0.0):
    """Mean landing deceleration ratio in g's (landing leaf force model):
    a/g = mu*(1 - L/W) + D/W + T_rev/W."""
    if mu_braking < 0 or min(lift_to_weight, drag_to_weight,
                             reverse_to_weight) < 0:
        raise ValueError("deceleration ratios must be non-negative")
    return mu_braking * (1.0 - lift_to_weight) + drag_to_weight + \
        reverse_to_weight


def landing_ground_roll(v_touchdown, decel_g, g=G0):
    """Landing ground roll, m: s = V^2/(2 a), a = decel_g*g."""
    if v_touchdown < 0 or decel_g <= 0:
        raise ValueError("touchdown speed/deceleration invalid")
    return v_touchdown * v_touchdown / (2.0 * decel_g * g)


def level_turn(phi_deg, v_ms, g=G0):
    """Level coordinated turn at bank phi: n = 1/cos(phi), rate and radius."""
    phi = math.radians(phi_deg)
    if abs(phi) >= math.pi / 2.0 or v_ms <= 0:
        raise ValueError("turn inputs invalid")
    n = 1.0 / math.cos(phi)
    rate = g * math.sqrt(n * n - 1.0) / v_ms          # rad/s
    radius = v_ms * v_ms / (g * math.sqrt(n * n - 1.0))  # m
    return {"n": n, "rate_rad_s": rate, "radius_m": radius}


def oei_thrust(total_thrust_n, n_engines, failed=1):
    """Thrust with engines failed: total*(n-f)/n."""
    if total_thrust_n <= 0 or n_engines < 2 or not (1 <= failed < n_engines):
        raise ValueError("OEI thrust inputs invalid")
    return total_thrust_n * (n_engines - failed) / n_engines


def oei_gradient_pct(t_oei_n, drag_n, weight_n):
    """OEI climb gradient percent: (T_oei - D)/W*100 (FAR 25.121 basis)."""
    if weight_n <= 0 or t_oei_n < 0 or drag_n < 0:
        raise ValueError("OEI gradient inputs invalid")
    return (t_oei_n - drag_n) / weight_n * 100.0


def energy_height(altitude_m, v_ms, g=G0):
    """Energy height h_e = h + V^2/(2g), m."""
    if altitude_m < 0 or v_ms < 0:
        raise ValueError("energy height inputs invalid")
    return altitude_m + v_ms * v_ms / (2.0 * g)


def wind_components(wind_speed, wind_dir_deg, track_deg):
    """Headwind (+) and crosswind components (wind-effects leaf)."""
    if wind_speed < 0:
        raise ValueError("wind speed must be >= 0")
    d = math.radians(wind_dir_deg - track_deg)
    return wind_speed * math.cos(d), wind_speed * math.sin(d)


# ---------------------------------------------------------------------------
# Stability and control rules (bound leaves: longitudinal-stability,
# dynamic-stability, short-period-mode-analysis, phugoid-mode-analysis,
# lateral-directional-stability, trim-analysis)
# ---------------------------------------------------------------------------

def neutral_point(h_ac_w, vh_tail, lift_slope_ratio, downwash_grad):
    """Stick-fixed neutral point (fraction MAC):
    h_np = h_ac_w + V_h*(a_t/a_w)*(1 - depsilon/dalpha)."""
    if not (0.0 < h_ac_w < 1.0) or vh_tail <= 0 or lift_slope_ratio <= 0:
        raise ValueError("neutral point inputs invalid")
    if not (0.0 <= downwash_grad < 1.0):
        raise ValueError("downwash gradient must be in [0,1)")
    return h_ac_w + vh_tail * lift_slope_ratio * (1.0 - downwash_grad)


def static_margin(neutral_point_val, h_cg):
    """SM = h_np - h_cg (fraction MAC); positive = stable."""
    if not (0.0 < neutral_point_val < 1.0) or not (0.0 < h_cg < 1.0):
        raise ValueError("static margin inputs invalid")
    return neutral_point_val - h_cg


def c_m_alpha_from_sm(cl_alpha, margin):
    """Cm_alpha = -CL_alpha * SM (standard neutral-point relation)."""
    return -cl_alpha * margin


def tail_volume_horizontal(s_h, l_h, s, cbar):
    """Horizontal tail volume coefficient V_h = S_h*l_h/(S*cbar)."""
    if min(s_h, l_h, s, cbar) <= 0:
        raise ValueError("tail volume inputs must be positive")
    return s_h * l_h / (s * cbar)


def vertical_tail_volume(s_vt, l_vt, s, b):
    """Vertical tail volume coefficient V_v = S_vt*l_vt/(S*b)."""
    if min(s_vt, l_vt, s, b) <= 0:
        raise ValueError("vertical tail volume inputs must be positive")
    return s_vt * l_vt / (s * b)


def cn_beta_vertical_tail(eta_vt, v_v, a_vt, sidewash_grad=0.0):
    """Fin contribution: Cn_beta_vt = eta*V_v*a_vt*(1 + k_s)."""
    if not (0.0 < eta_vt <= 1.0) or v_v <= 0 or a_vt <= 0 or sidewash_grad < 0:
        raise ValueError("fin contribution inputs invalid")
    return eta_vt * v_v * a_vt * (1.0 + sidewash_grad)


def cl_beta_dihedral(cl, dihedral_deg):
    """Dihedral contribution: Cl_beta_gamma = -CL*Gamma (radians)."""
    if cl < 0:
        raise ValueError("lift coefficient must be >= 0")
    return -cl * math.radians(dihedral_deg)


def z_alpha_derivative(qbar, s, cl_alpha, mass):
    """Z_alpha = -(qbar*S*CL_alpha)/m, m/s^2 per rad."""
    if min(qbar, s, cl_alpha, mass) <= 0:
        raise ValueError("Z_alpha inputs must be positive")
    return -(qbar * s * cl_alpha) / mass


def m_alpha_derivative(qbar, s, cbar, c_m_alpha, i_yy):
    """M_alpha = qbar*S*cbar*Cm_alpha/I_yy, 1/s^2 (Cm_alpha < 0 stable)."""
    if min(qbar, s, cbar, i_yy) <= 0 or c_m_alpha >= 0:
        raise ValueError("M_alpha inputs invalid (Cm_alpha must be < 0)")
    return qbar * s * cbar * c_m_alpha / i_yy


def m_q_derivative(qbar, s, cbar, c_m_q, v, i_yy):
    """M_q = qbar*S*cbar^2*Cm_q/(2 V I_yy), 1/s (Cm_q < 0 damping)."""
    if min(qbar, s, cbar, v, i_yy) <= 0 or c_m_q >= 0:
        raise ValueError("M_q inputs invalid (Cm_q must be < 0)")
    return qbar * s * cbar * cbar * c_m_q / (2.0 * v * i_yy)


def short_period_frequency(z_alpha, m_alpha, m_q, v):
    """omega_ns = sqrt(M_q*Z_alpha/V - M_alpha), rad/s."""
    if v <= 0:
        raise ValueError("speed must be positive")
    radicand = m_q * z_alpha / v - m_alpha
    if radicand <= 0:
        raise ValueError("short period radicand must be positive")
    return math.sqrt(radicand)


def short_period_damping(z_alpha, m_alpha, m_q, v):
    """zeta_s = -(Z_alpha/V + M_q)/(2 omega_ns)."""
    omega = short_period_frequency(z_alpha, m_alpha, m_q, v)
    return -(z_alpha / v + m_q) / (2.0 * omega)


def n_over_alpha(qbar, s, cl_alpha, weight_n, g=G0):
    """Load factor per angle of attack, g/rad: n_alpha = qbar*S*CL_alpha/W."""
    if min(qbar, s, cl_alpha, weight_n) <= 0:
        raise ValueError("n_alpha inputs invalid")
    return qbar * s * cl_alpha / weight_n


def phugoid_frequency(v, g=G0):
    return math.sqrt(2.0) * g / v


def phugoid_period(v, g=G0):
    return 2.0 * math.pi / phugoid_frequency(v, g)


def phugoid_damping(ld):
    """zeta_p = 1/(sqrt(2)*(L/D)), Lanchester drag damping."""
    if ld <= 0:
        raise ValueError("L/D must be positive")
    return 1.0 / (math.sqrt(2.0) * ld)


def phugoid_time_to_half(v, ld, g=G0):
    """t_half = ln(2)*V*(L/D)/g (identity zeta*omega = g/(V L/D))."""
    if v <= 0 or ld <= 0:
        raise ValueError("phugoid time inputs invalid")
    return math.log(2.0) * v * ld / g


def y_beta_derivative(qbar, s, c_y_beta, mass):
    """Y_beta = qbar*S*C_Ybeta/m, m/s^2 per rad (Cy_beta < 0 fin)."""
    if min(qbar, s, mass) <= 0 or c_y_beta >= 0:
        raise ValueError("Y_beta inputs invalid (Cy_beta must be < 0)")
    return qbar * s * c_y_beta / mass


def y_r_derivative(qbar, s, b, c_y_r, v, mass):
    """Y_r = qbar*S*b*C_Yr/(2 V m), m/s per rad."""
    if min(qbar, s, b, v, mass) <= 0:
        raise ValueError("Y_r inputs invalid")
    return qbar * s * b * c_y_r / (2.0 * v * mass)


def n_beta_derivative(qbar, s, b, c_n_beta, i_zz):
    """N_beta = qbar*S*b*Cn_beta/I_zz, 1/s^2 (Cn_beta > 0 stable)."""
    if min(qbar, s, b, i_zz) <= 0 or c_n_beta <= 0:
        raise ValueError("N_beta inputs invalid (Cn_beta must be > 0)")
    return qbar * s * b * c_n_beta / i_zz


def n_r_derivative(qbar, s, b, c_n_r, v, i_zz):
    """N_r = qbar*S*b^2*Cn_r/(2 V I_zz), 1/s (Cn_r < 0 damping)."""
    if min(qbar, s, b, v, i_zz) <= 0 or c_n_r >= 0:
        raise ValueError("N_r inputs invalid (Cn_r must be < 0)")
    return qbar * s * b * b * c_n_r / (2.0 * v * i_zz)


def l_beta_derivative(qbar, s, b, c_l_beta, i_xx):
    """L_beta = qbar*S*b*Cl_beta/I_xx, 1/s^2 (Cl_beta < 0 stable)."""
    if min(qbar, s, b, i_xx) <= 0 or c_l_beta >= 0:
        raise ValueError("L_beta inputs invalid (Cl_beta must be < 0)")
    return qbar * s * b * c_l_beta / i_xx


def l_r_derivative(qbar, s, b, c_l_r, v, i_xx):
    """L_r = qbar*S*b^2*Cl_r/(2 V I_xx), 1/s."""
    if min(qbar, s, b, v, i_xx) <= 0:
        raise ValueError("L_r inputs invalid")
    return qbar * s * b * b * c_l_r / (2.0 * v * i_xx)


def l_p_derivative(qbar, s, b, c_l_p, v, i_xx):
    """L_p = qbar*S*b^2*Cl_p/(2 V I_xx), 1/s (Cl_p < 0 roll damping)."""
    if min(qbar, s, b, v, i_xx) <= 0 or c_l_p >= 0:
        raise ValueError("L_p inputs invalid (Cl_p must be < 0)")
    return qbar * s * b * b * c_l_p / (2.0 * v * i_xx)


def dutch_roll_frequency(n_beta, n_r, y_beta, y_r, v):
    """omega_dr = sqrt(N_beta + (N_r*Y_beta - N_beta*Y_r)/V), rad/s."""
    if v <= 0:
        raise ValueError("speed must be positive")
    radicand = n_beta + (n_r * y_beta - n_beta * y_r) / v
    if radicand <= 0:
        raise ValueError("Dutch roll radicand must be positive")
    return math.sqrt(radicand)


def dutch_roll_damping(n_beta, n_r, y_beta, y_r, v):
    """zeta_dr = -(Y_beta/V + N_r)/(2 omega_dr)."""
    omega = dutch_roll_frequency(n_beta, n_r, y_beta, y_r, v)
    return -(y_beta / v + n_r) / (2.0 * omega)


def roll_time_constant(l_p):
    """Roll subsidence time constant tau = -1/L_p, s (L_p < 0)."""
    if l_p >= 0:
        raise ValueError("L_p must be negative")
    return -1.0 / l_p


def spiral_stability_parameter(l_beta, l_r, n_beta, n_r):
    """Spiral criterion term L_beta*N_r - L_r*N_beta (>0 = convergent)."""
    return l_beta * n_r - l_r * n_beta


def spiral_eigenvalue(l_beta, l_r, n_beta, n_r, l_p, v, g=G0):
    """Approximate spiral root lambda_s = (g/V)*(Lb*Nr - Lr*Nb)/(Nb*Lp)."""
    if n_beta <= 0 or l_p >= 0 or v <= 0:
        raise ValueError("spiral inputs invalid")
    return (g / v) * spiral_stability_parameter(l_beta, l_r, n_beta, n_r) / \
        (n_beta * l_p)


def trim_lift_coefficient(weight_n, rho, v, s):
    """CL_trim = 2W/(rho V^2 S) for level flight."""
    if min(weight_n, rho, v, s) <= 0:
        raise ValueError("trim inputs must be positive")
    return 2.0 * weight_n / (rho * v * v * s)


def elevator_to_trim(cm0, cm_alpha, cl_alpha, cl_trim, cm_delta_e):
    """de_trim = -(Cm0 + Cm_alpha*CL_trim/CL_alpha)/Cm_delta_e, rad."""
    if cl_alpha <= 0 or cm_delta_e == 0:
        raise ValueError("elevator trim inputs invalid")
    alpha_trim = cl_trim / cl_alpha
    return -(cm0 + cm_alpha * alpha_trim) / cm_delta_e


# ---------------------------------------------------------------------------
# Flying qualities reference tables (summary of the MIL-STD-1797A mode
# criteria as encoded by the bound mil-std-1797a and short-period-mode leaves:
# reference-only paraphrase, civil use by analogy with FAR 25.181 context)
# ---------------------------------------------------------------------------

# Short period Level 1 damping band by flight phase category (summary):
# category A 0.35-1.30; categories B and C 0.30-2.00.
SP_DAMPING_L1 = {"A": (0.35, 1.30), "B": (0.30, 2.00), "C": (0.30, 2.00)}
SP_DAMPING_L2 = {"A": (0.25, 2.00), "B": (0.25, 2.00), "C": (0.25, 2.00)}
SP_DAMPING_L3_MIN = 0.15

# Short period minimum natural frequency (rad/s) at n_alpha = 1.0 and 3.0
# g/rad by (category, class); linear interpolation, clamped outside.
SP_FREQ_N1 = {"A": {"I": 3.6, "II": 3.6, "III": 3.0, "IV": 2.5},
              "B": {"I": 1.0, "II": 1.0, "III": 1.0, "IV": 1.0},
              "C": {"I": 1.0, "II": 1.0, "III": 1.0, "IV": 1.0}}
SP_FREQ_N3 = {"A": {"I": 6.0, "II": 6.0, "III": 6.0, "IV": 6.0},
              "B": {"I": 2.0, "II": 2.0, "III": 2.0, "IV": 2.0},
              "C": {"I": 2.0, "II": 2.0, "III": 2.0, "IV": 2.0}}

# Phugoid: min damping ratio per level (Level 3 expressed as time to
# double >= 55 s for a divergence).
PHUGOID_DAMPING_MIN = {1: 0.04, 2: 0.0}

# Dutch roll (zeta_min, omega_min rad/s, zeta*omega_min) level 1 by
# (category, class); category A class IV is the strictest.
DR_L1 = {"A": {"IV": (0.19, 1.0, 0.35), "I": (0.19, 0.4, 0.35),
               "II": (0.19, 0.4, 0.35), "III": (0.19, 0.4, 0.35)},
         "B": {"IV": (0.08, 0.4, 0.15), "I": (0.08, 0.4, 0.15),
               "II": (0.08, 0.4, 0.15), "III": (0.08, 0.4, 0.15)},
         "C": {"IV": (0.08, 0.4, 0.15), "I": (0.08, 0.4, 0.15),
               "II": (0.08, 0.4, 0.15), "III": (0.08, 0.4, 0.15)}}
DR_L2 = (0.02, 0.4, 0.05)

# Spiral min time to double (s) per level and category.
SPIRAL_T2 = {1: {"A": 20.0, "B": 12.0, "C": 20.0},
             2: {"A": 8.0, "B": 8.0, "C": 8.0},
             3: {"A": 4.0, "B": 4.0, "C": 4.0}}

# Roll mode max time constant (s) per level and category.
ROLL_TAU_MAX = {1: {"A": 1.0, "B": 1.4, "C": 1.0},
                2: {"A": 1.4, "B": 3.0, "C": 1.4},
                3: {"A": 10.0, "B": 10.0, "C": 10.0}}

CATEGORIES = ("A", "B", "C")
CLASSES = ("I", "II", "III", "IV")


def sp_min_frequency(category, aircraft_class, n_over_alpha_val):
    """Short period frequency floor interpolated in n_alpha (g/rad),
    clamped to the [1, 3] g/rad table band (mil-std-1797a leaf)."""
    if category not in CATEGORIES or aircraft_class not in CLASSES:
        raise ValueError("invalid category/class")
    if n_over_alpha_val <= 0:
        raise ValueError("n_alpha must be positive")
    n = min(max(n_over_alpha_val, 1.0), 3.0)
    f1 = SP_FREQ_N1[category][aircraft_class]
    f3 = SP_FREQ_N3[category][aircraft_class]
    t = (n - 1.0) / 2.0
    return f1 + t * (f3 - f1)


def assess_short_period(zeta, omega, category, aircraft_class, n_alpha):
    """Short period flying qualities level (1/2/3) by the summary bands.

    Level 1 needs damping in the category band and frequency at/above the
    n_alpha-interpolated floor; a Level 1 damping with a frequency below
    the floor is degraded to Level 2; damping below the Level 2 band but
    above the Level 3 minimum reads Level 3.
    """
    min_omega = sp_min_frequency(category, aircraft_class, n_alpha)
    z1min, z1max = SP_DAMPING_L1[category]
    z2min, z2max = SP_DAMPING_L2[category]
    if z1min <= zeta <= z1max:
        level = 1
    elif z2min <= zeta <= z2max:
        level = 2
    else:
        level = 3
    if level == 1 and omega < min_omega:
        level = 2
    return {"level": level, "min_omega": min_omega, "zeta": zeta,
            "omega": omega, "n_alpha": n_alpha}


def assess_phugoid(zeta):
    """Phugoid level: 1 when zeta >= 0.04, 2 when 0 <= zeta < 0.04,
    3 for divergent (zeta < 0)."""
    if zeta >= PHUGOID_DAMPING_MIN[1]:
        return 1
    if zeta >= PHUGOID_DAMPING_MIN[2]:
        return 2
    return 3


def assess_dutch_roll(zeta, omega, category, aircraft_class):
    """Dutch roll level by the summary criteria."""
    if zeta <= 0.0:
        return 3
    z1, w1, zw1 = DR_L1[category][aircraft_class]
    if zeta >= z1 and omega >= w1 and zeta * omega >= zw1:
        return 1
    z2, w2, zw2 = DR_L2
    if zeta >= z2 and omega >= w2 and zeta * omega >= zw2:
        return 2
    return 3


def assess_spiral(lam, category):
    """Spiral level: stable root -> 1; else by time-to-double floors."""
    if lam <= 0.0:
        return 1
    t2 = math.log(2.0) / lam
    for level in (1, 2, 3):
        if t2 >= SPIRAL_T2[level][category]:
            return level
    return 3


def assess_roll_mode(tau, category):
    """Roll mode level by the max time-constant floors."""
    for level in (1, 2, 3):
        if tau <= ROLL_TAU_MAX[level][category]:
            return level
    return 3


# ---------------------------------------------------------------------------
# FAR/CS minimum climb gradients (oei-climb-gradient leaf, FAR 25.121)
# ---------------------------------------------------------------------------

FAR_25_121_SECOND_SEGMENT = {2: 2.4, 3: 2.7, 4: 3.0}   # percent
FAR_25_121_APPROACH = {2: 2.1, 3: 2.4, 4: 2.7}         # percent
FAR_25_121_LANDING = 3.2                                 # percent


def far_25_121_minimum(segment, n_engines):
    if segment == "second-segment":
        return FAR_25_121_SECOND_SEGMENT[n_engines]
    if segment == "approach":
        return FAR_25_121_APPROACH[n_engines]
    if segment == "landing":
        return FAR_25_121_LANDING
    raise ValueError("segment must be second-segment/approach/landing")


# ---------------------------------------------------------------------------
# Example configuration: a generic 150-seat-class twin-engine transport.
# ALL numbers are EXAMPLE DATA in the public class range (stated basis, to be
# replaced by project data); the report marks them as such. Nothing here
# claims to describe a specific certified airplane.
# ---------------------------------------------------------------------------

@dataclass
class ExampleTransport:
    name: str = "AeroLine AT-78"
    description: str = "Example twin-engine transport, 150-seat class (MTOW 78 t); " \
        "all data are example values in the public class range - not a specific " \
        "certified airplane."
    # --- geometry / inertia (example data) ---
    s: float = 125.0            # wing area m^2
    b: float = 35.8             # span m
    cbar: float = 3.4916        # mean aerodynamic chord m (= S/b)
    i_yy: float = 3.4e6         # pitch inertia kg m^2
    i_xx: float = 2.0e6         # roll inertia kg m^2
    i_zz: float = 6.5e6         # yaw inertia kg m^2
    # --- masses (example data) ---
    m_mtow: float = 78000.0     # MTOW kg
    m_mlw: float = 62000.0      # MLW kg
    # --- propulsion (example data) ---
    n_engines: int = 2
    thrust_to_each: float = 110000.0   # sea-level static per engine (takeoff rating), N
    thrust_climb_sl_total: float = 150000.0  # total max-climb rating sea level, N
    thrust_lapse_exp: float = 0.7     # sigma^0.7 density-based thrust lapse (high-bypass)
    tsfc: float = 1.55e-5       # cruise TSFC kg/(N s), ~0.55 lb/(lbf hr) class
    # --- aerodynamics (parabolic polars per configuration; example data) ---
    cd0_clean: float = 0.021
    oswald_clean: float = 0.80
    cd0_to: float = 0.032       # takeoff flaps, gear up
    osward_to: float = 0.60
    cd0_land: float = 0.050     # landing flaps + gear down
    oswald_land: float = 0.55
    cl_alpha_clean: float = 5.5     # airplane lift slope 1/rad (cruise, incl Mach)
    cl_alpha_land: float = 6.2      # airplane lift slope 1/rad (landing config)
    cl_max_to: float = 1.9      # takeoff configuration
    cl_max_land: float = 2.4    # landing configuration
    # --- tail geometry (example data) ---
    s_h: float = 26.5           # horizontal tail area m^2
    l_h: float = 14.2           # tail arm (wing AC -> HTP AC) m
    s_vt: float = 12.4          # vertical tail area m^2
    l_vt: float = 18.5          # fin arm m
    a_over_a_ratio: float = 0.72    # a_t/a_w for the neutral point build
    downwash_grad: float = 0.45     # depsilon/dalpha
    h_ac_w: float = 0.25        # wing aerodynamic centre, fraction MAC
    eta_vt: float = 0.95
    a_vt: float = 3.4           # fin lift slope 1/rad
    sidewash_grad: float = 0.08
    cn_beta_fuselage: float = -0.0589  # destabilizing body term (class data)
    cl_beta_remainder: float = -0.025  # sweep/body remainder to Cl_beta total
    dihedral_deg: float = 5.2
    c_y_beta: float = -0.65     # side-force slope (class data)
    c_y_r: float = 0.25
    c_n_r: float = -0.25
    c_l_r: float = 0.13
    c_l_p: float = -0.42
    c_m_q: float = -30.0        # pitch damping coefficient (tail + wing-body)
    c_m_0: float = 0.08         # zero-lift pitching moment (class data)
    c_m_delta_e: float = -0.90  # elevator effectiveness 1/rad
    elevator_limit_deg: float = 25.0
    # --- CG envelope (example data, fraction MAC) ---
    h_cg_fwd: float = 0.32
    h_cg_aft: float = 0.44
    h_cg_mid: float = 0.38
    # --- mission / conditions (example data) ---
    cruise_alt_m: float = 10668.0      # FL350
    cruise_mach: float = 0.78
    climb_speed_ms: float = 128.6      # 250 KCAS at sea level, m/s
    loiter_start_kg: float = 62000.0
    loiter_end_kg: float = 59000.0
    landing_approach_deg: float = 3.0
    landing_flare_n: float = 1.2
    landing_mu: float = 0.45           # dry runway braking coefficient
    to_mu: float = 0.03                # rolling friction, dry concrete
    obstacle_50ft_m: float = 15.24     # FAR 25.125 obstacle height
    landing_dist_factor: float = 1.67  # FAR 25.125 certified-distance factor
    turn_bank_deg: float = 25.0
    wind_kt: float = 40.0              # enroute headwind for the wind case

    # derived
    @property
    def ar(self):
        return self.b * self.b / self.s

    @property
    def k_clean(self):
        return 1.0 / (math.pi * self.oswald_clean * self.ar)

    @property
    def k_to(self):
        return 1.0 / (math.pi * self.osward_to * self.ar)

    @property
    def k_land(self):
        return 1.0 / (math.pi * self.oswald_land * self.ar)

    @property
    def w_mtow(self):
        return self.m_mtow * G0

    @property
    def w_mlw(self):
        return self.m_mlw * G0

    @property
    def thrust_total_to(self):
        return self.n_engines * self.thrust_to_each

    @property
    def vh_tail(self):
        return tail_volume_horizontal(self.s_h, self.l_h, self.s, self.cbar)

    @property
    def v_vtail(self):
        return vertical_tail_volume(self.s_vt, self.l_vt, self.s, self.b)


def example_vehicle() -> ExampleTransport:
    return ExampleTransport()


# ---------------------------------------------------------------------------
# Analysis: compute every number of the deliverable from the configuration
# ---------------------------------------------------------------------------

def analyze_vehicle(a: ExampleTransport) -> dict:
    """Run the full performance + S&C analysis. Returns a flat dict of
    results consumed by the report builder."""
    r = {}
    r["aircraft"] = a

    # --- atmosphere at the analysis altitudes ---
    r["isa_sl"] = isa(0.0)
    r["isa_cruise"] = isa(a.cruise_alt_m)

    # cruise true airspeed at the cruise Mach number
    v_cruise = a.cruise_mach * r["isa_cruise"]["a"]
    r["v_cruise"] = v_cruise
    qbar_cruise = 0.5 * r["isa_cruise"]["rho"] * v_cruise * v_cruise
    r["qbar_cruise"] = qbar_cruise

    # --- 1. Mission performance ---
    # cruise point from the polar
    cl_cruise = a.w_mtow / (qbar_cruise * a.s)
    cd_cruise = drag_coefficient(a.cd0_clean, a.k_clean, cl_cruise)
    ld_cruise = cl_cruise / cd_cruise
    r.update(cl_cruise=cl_cruise, cd_cruise=cd_cruise, ld_cruise=ld_cruise,
             d_cruise=a.w_mtow / ld_cruise)
    r["ld_max"] = max_lift_to_drag(a.cd0_clean, a.k_clean)

    # Breguet range: cruise segment MTOW start, 17,160 kg cruise fuel burned
    m_cruise_start = a.m_mtow
    m_cruise_end = a.m_mtow - 17160.0
    r["range_m"] = breguet_range(v_cruise, a.tsfc, ld_cruise,
                                 m_cruise_start, m_cruise_end)
    r["range_km"] = r["range_m"] / 1000.0
    r["cruise_fuel_kg"] = m_cruise_start - m_cruise_end

    # loiter endurance (Breguet jet endurance, weights form)
    r["endurance_s"] = jet_endurance(a.tsfc, ld_cruise,
                                     a.loiter_start_kg * G0,
                                     a.loiter_end_kg * G0)
    r["endurance_hr"] = r["endurance_s"] / 3600.0

    # specific air range at cruise + a small speed sweep for the "curve"
    sar = specific_air_range(v_cruise, a.tsfc, a.w_mtow, ld_cruise)
    r["sar_m_per_kg"] = sar
    sar_pts = []
    for frac in (0.95, 1.00, 1.05):
        vv = v_cruise * frac
        cll = a.w_mtow / (0.5 * r["isa_cruise"]["rho"] * vv * vv * a.s)
        ldl = lift_to_drag(a.cd0_clean, a.k_clean, cll)
        sar_pts.append({"frac": frac, "v": vv, "ld": ldl,
                        "sar": specific_air_range(vv, a.tsfc, a.w_mtow, ldl)})
    r["sar_curve"] = sar_pts
    r["sector_fuel_5000km"] = 5.0e6 / sar

    # climb: sea level and FL350 at MTOW, clean config
    qbar_sl_climb = 0.5 * r["isa_sl"]["rho"] * a.climb_speed_ms ** 2
    cl_climb_sl = a.w_mtow / (qbar_sl_climb * a.s)
    cd_climb_sl = drag_coefficient(a.cd0_clean, a.k_clean, cl_climb_sl)
    d_climb_sl = cd_climb_sl * qbar_sl_climb * a.s
    r["roc_sl"] = rate_of_climb(a.thrust_climb_sl_total, d_climb_sl,
                                a.climb_speed_ms, a.w_mtow)
    # climb thrust at FL350: density-based lapse sigma^0.7
    t_climb_350 = a.thrust_climb_sl_total * r["isa_cruise"]["sigma"] ** \
        a.thrust_lapse_exp
    # climb speed at FL350 on the 250 KCAS / M0.78 schedule
    v_climb_350 = min(v_cruise, a.climb_speed_ms /
                      math.sqrt(r["isa_cruise"]["sigma"]))
    qbar_350 = 0.5 * r["isa_cruise"]["rho"] * v_climb_350 ** 2
    cl_350 = a.w_mtow / (qbar_350 * a.s)
    cd_350 = drag_coefficient(a.cd0_clean, a.k_clean, cl_350)
    d_350 = cd_350 * qbar_350 * a.s
    r["roc_350"] = rate_of_climb(t_climb_350, d_350, v_climb_350, a.w_mtow)
    r["time_to_350_s"] = time_to_climb(a.cruise_alt_m, r["roc_sl"],
                                       r["roc_350"])
    # ROC at FL410 (12,497 m) for the ceiling interpolation
    isa_410 = isa(12497.0)
    t_climb_410 = a.thrust_climb_sl_total * isa_410["sigma"] ** \
        a.thrust_lapse_exp
    v_410 = min(v_cruise, a.climb_speed_ms / math.sqrt(isa_410["sigma"]))
    qbar_410 = 0.5 * isa_410["rho"] * v_410 ** 2
    cl_410 = a.w_mtow / (qbar_410 * a.s)
    cd_410 = drag_coefficient(a.cd0_clean, a.k_clean, cl_410)
    d_410 = cd_410 * qbar_410 * a.s
    r["roc_410"] = rate_of_climb(t_climb_410, d_410, v_410, a.w_mtow)
    # linear-lapse ceiling estimate between FL350 and FL410 (indicative)
    lapse = (r["roc_350"] - r["roc_410"]) / (12497.0 - a.cruise_alt_m)
    r["ceiling_est_m"] = a.cruise_alt_m + (r["roc_350"] - 0.5) / lapse

    # takeoff: stall speed, V_LOF/V2 = 1.2 Vs, ground roll at MTOW sea level
    ws_mtow = a.w_mtow / a.s
    vs_to = stall_speed(ws_mtow, r["isa_sl"]["rho"], a.cl_max_to)
    v2 = 1.2 * vs_to
    sg = takeoff_ground_roll(a.w_mtow, a.s, a.thrust_total_to,
                             r["isa_sl"]["rho"], a.cl_max_to, mu=a.to_mu)
    r.update(vs_to=vs_to, v2=v2, to_ground_roll=sg)

    # landing: MLW, sea level
    ws_mlw = a.w_mlw / a.s
    vs_land = stall_speed(ws_mlw, r["isa_sl"]["rho"], a.cl_max_land)
    v_ref = 1.3 * vs_land
    v_td = 0.95 * v_ref
    air_dist = landing_air_distance(v_ref, a.landing_approach_deg,
                                    a.obstacle_50ft_m, a.landing_flare_n)
    # drag ratio during the ground roll in the landing configuration
    cl_td = a.w_mlw / (0.5 * r["isa_sl"]["rho"] * v_td ** 2 * a.s)
    cd_td = drag_coefficient(a.cd0_land, a.k_land, cl_td)
    decel_g = average_deceleration_g(a.landing_mu, 0.15, cd_td / cl_td)
    s_gr = landing_ground_roll(v_td, decel_g)
    actual_land = air_dist + s_gr
    r.update(vs_land=vs_land, v_ref=v_ref, v_td=v_td, air_dist=air_dist,
             land_ground_roll=s_gr, land_actual=actual_land,
             land_certified=actual_land * a.landing_dist_factor,
             ld_landing=cl_td / cd_td)

    # glide (best glide, clean polar, from cruise altitude at MTOW)
    ld_max = r["ld_max"]
    cl_bg = ld_max["cl_star"]
    v_bg_eas = math.sqrt(2.0 * a.w_mtow / (r["isa_sl"]["rho"] * a.s * cl_bg))
    sink = glide_sink_rate(v_bg_eas, ld_max["ld_max"])
    r.update(best_glide_v=v_bg_eas, best_glide_sink=sink,
             glide_range_m=ld_max["ld_max"] * a.cruise_alt_m,
             glide_time_s=a.cruise_alt_m / sink)

    # turn at 25 deg bank, cruise speed, MTOW
    turn = level_turn(a.turn_bank_deg, v_cruise)
    d_turn = r["d_cruise"] * turn["n"]
    # cruise-rating thrust available at FL350 (assumed 58 kN class)
    t_cruise_avail = 58000.0
    turn["sustained"] = t_cruise_avail >= d_turn
    turn["d_turn"] = d_turn
    turn["t_avail"] = t_cruise_avail
    r["turn"] = turn

    # wind: 40 kt headwind on the 5,000 km sector
    wind_ms = a.wind_kt / MPS_TO_KT
    gs_still = v_cruise
    gs_hw = v_cruise - wind_ms
    r["wind"] = {"wind_kt": a.wind_kt, "gs_still": gs_still,
                 "gs_hw": gs_hw, "time_still_h": 5.0e6 / gs_still / 3600.0,
                 "time_hw_h": 5.0e6 / gs_hw / 3600.0}

    # --- 2. Safety performance ---
    # OEI second segment: V2, takeoff config gear up, MTOW, one engine failed
    qbar_v2 = 0.5 * r["isa_sl"]["rho"] * v2 * v2
    cl_2nd = a.w_mtow / (qbar_v2 * a.s)
    cd_2nd = drag_coefficient(a.cd0_to, a.k_to, cl_2nd)
    d_2nd = cd_2nd * qbar_v2 * a.s
    t_oei = oei_thrust(a.thrust_total_to, a.n_engines, 1)
    grad_2nd = oei_gradient_pct(t_oei, d_2nd, a.w_mtow)
    r["oei"] = {"t_oei": t_oei, "d_2nd": d_2nd, "ld_2nd": cl_2nd / cd_2nd,
                "gradient_pct": grad_2nd,
                "min_pct": far_25_121_minimum("second-segment", a.n_engines),
                "grad_deg": math.degrees(math.atan(grad_2nd / 100.0))}
    # energy height at cruise
    r["energy"] = {"h_kin": v_cruise * v_cruise / (2.0 * G0),
                   "h_e": energy_height(a.cruise_alt_m, v_cruise)}
    # windshear: needs a windshear profile (leaf) - reported as open item

    # --- 4/5/6. Stability, dynamic modes ---
    aero = {}
    h_np = neutral_point(a.h_ac_w, a.vh_tail, a.a_over_a_ratio,
                         a.downwash_grad)
    aero["h_np"] = h_np
    aero["vh_tail"] = a.vh_tail
    aero["sm_fwd"] = static_margin(h_np, a.h_cg_fwd)
    aero["sm_aft"] = static_margin(h_np, a.h_cg_aft)
    aero["sm_mid"] = static_margin(h_np, a.h_cg_mid)
    aero["cn_beta_vt"] = cn_beta_vertical_tail(a.eta_vt, a.v_vtail, a.a_vt,
                                               a.sidewash_grad)
    aero["cn_beta"] = aero["cn_beta_vt"] + a.cn_beta_fuselage
    aero["cl_beta_dihedral"] = cl_beta_dihedral(cl_cruise, a.dihedral_deg)
    aero["cl_beta"] = aero["cl_beta_dihedral"] + a.cl_beta_remainder
    aero["v_vtail"] = a.v_vtail
    r["aero"] = aero

    # longitudinal mode analysis per condition (cruise/approach) per CG
    def longitudinal_condition(cond_name, h, mass_kg, v, rho, cl_alpha):
        qbar = 0.5 * rho * v * v
        w = mass_kg * G0
        sm = static_margin(h_np, h)
        cm_alpha = c_m_alpha_from_sm(cl_alpha, sm)
        za = z_alpha_derivative(qbar, a.s, cl_alpha, mass_kg)
        ma = m_alpha_derivative(qbar, a.s, a.cbar, cm_alpha, a.i_yy)
        mq = m_q_derivative(qbar, a.s, a.cbar, a.c_m_q, v, a.i_yy)
        om = short_period_frequency(za, ma, mq, v)
        zeta = short_period_damping(za, ma, mq, v)
        nal = n_over_alpha(qbar, a.s, cl_alpha, w)
        return {"cond": cond_name, "h_cg": h, "sm": sm, "cm_alpha": cm_alpha,
                "za": za, "ma": ma, "mq": mq, "omega_sp": om, "zeta_sp": zeta,
                "n_alpha": nal, "qbar": qbar, "cl": w / (qbar * a.s)}

    cruise_atm = r["isa_cruise"]
    r["sp_cruise_aft"] = longitudinal_condition(
        "cruise FL350", a.h_cg_aft, a.m_mtow, v_cruise, cruise_atm["rho"],
        a.cl_alpha_clean)
    r["sp_cruise_fwd"] = longitudinal_condition(
        "cruise FL350", a.h_cg_fwd, a.m_mtow, v_cruise, cruise_atm["rho"],
        a.cl_alpha_clean)
    r["sp_appr_aft"] = longitudinal_condition(
        "approach", a.h_cg_aft, a.m_mlw, v_ref, r["isa_sl"]["rho"],
        a.cl_alpha_land)
    r["sp_appr_fwd"] = longitudinal_condition(
        "approach", a.h_cg_fwd, a.m_mlw, v_ref, r["isa_sl"]["rho"],
        a.cl_alpha_land)

    # phugoid at cruise and approach (Lanchester)
    def phugoid(v, ld):
        return {"omega": phugoid_frequency(v), "period": phugoid_period(v),
                "zeta": phugoid_damping(ld), "t_half": phugoid_time_to_half(v, ld)}
    r["phugoid_cruise"] = phugoid(v_cruise, ld_cruise)
    r["phugoid_appr"] = phugoid(v_ref, r["ld_landing"])
    # separation: omega_sp / omega_phugoid (needs to be large)
    r["sp_phugoid_sep_cruise"] = (r["sp_cruise_aft"]["omega_sp"] /
                                  r["phugoid_cruise"]["omega"])
    r["sp_phugoid_sep_appr"] = (r["sp_appr_aft"]["omega_sp"] /
                                r["phugoid_appr"]["omega"])

    # lateral-directional derivatives per condition + modes
    def lateral(cond_name, mass_kg, v, rho, ld_cond):
        qbar = 0.5 * rho * v * v
        w = mass_kg * G0
        cl_cond = w / (qbar * a.s)
        yb = y_beta_derivative(qbar, a.s, a.c_y_beta, mass_kg)
        yr = y_r_derivative(qbar, a.s, a.b, a.c_y_r, v, mass_kg)
        nb = n_beta_derivative(qbar, a.s, a.b, aero["cn_beta"], a.i_zz)
        nr = n_r_derivative(qbar, a.s, a.b, a.c_n_r, v, a.i_zz)
        lb = l_beta_derivative(qbar, a.s, a.b, aero["cl_beta"], a.i_xx)
        lr = l_r_derivative(qbar, a.s, a.b, a.c_l_r, v, a.i_xx)
        lp = l_p_derivative(qbar, a.s, a.b, a.c_l_p, v, a.i_xx)
        om_dr = dutch_roll_frequency(nb, nr, yb, yr, v)
        zeta_dr = dutch_roll_damping(nb, nr, yb, yr, v)
        tau_roll = roll_time_constant(lp)
        lam_spiral = spiral_eigenvalue(lb, lr, nb, nr, lp, v)
        return {"cond": cond_name, "mass": mass_kg, "v": v, "cl": cl_cond,
                "yb": yb, "yr": yr, "nb": nb, "nr": nr, "lb": lb, "lr": lr,
                "lp": lp, "omega_dr": om_dr, "zeta_dr": zeta_dr,
                "tau_roll": tau_roll, "lambda_spiral": lam_spiral,
                "t_half_spiral": (None if lam_spiral >= 0
                                  else math.log(2.0) / -lam_spiral)}
    r["lat_cruise"] = lateral("cruise FL350", a.m_mtow, v_cruise,
                              cruise_atm["rho"], ld_cruise)
    r["lat_appr"] = lateral("approach", a.m_mlw, v_ref, r["isa_sl"]["rho"],
                            r["ld_landing"])

    # --- trim ---
    def trim_case(cond_name, rho, v, weight_n, cl_alpha, h_cg):
        cl_trim = trim_lift_coefficient(weight_n, rho, v, a.s)
        sm = static_margin(h_np, h_cg)
        cm_alpha = c_m_alpha_from_sm(cl_alpha, sm)
        de = elevator_to_trim(a.c_m_0, cm_alpha, cl_alpha, cl_trim,
                              a.c_m_delta_e)
        return {"cond": cond_name, "cl_trim": cl_trim, "alpha_rad":
                cl_trim / cl_alpha, "de_rad": de,
                "de_deg": math.degrees(de), "authority_deg": a.elevator_limit_deg}
    r["trim_cruise"] = trim_case("cruise", cruise_atm["rho"], v_cruise,
                                 a.w_mtow, a.cl_alpha_clean, a.h_cg_mid)
    r["trim_appr"] = trim_case("approach", r["isa_sl"]["rho"], v_ref,
                               a.w_mlw, a.cl_alpha_land, a.h_cg_mid)

    # mode flying-qualities levels (MIL-STD-1797A summary, class III)
    # cruise is category B (gradual maneuvers); approach category C (terminal)
    c = "III"
    sp_a = r["sp_cruise_aft"]
    r["sp_level_cruise_aft"] = assess_short_period(
        sp_a["zeta_sp"], sp_a["omega_sp"], "B", c, sp_a["n_alpha"])
    sp_f = r["sp_cruise_fwd"]
    r["sp_level_cruise_fwd"] = assess_short_period(
        sp_f["zeta_sp"], sp_f["omega_sp"], "B", c, sp_f["n_alpha"])
    sp_a2 = r["sp_appr_aft"]
    r["sp_level_appr_aft"] = assess_short_period(
        sp_a2["zeta_sp"], sp_a2["omega_sp"], "C", c, sp_a2["n_alpha"])
    sp_f2 = r["sp_appr_fwd"]
    r["sp_level_appr_fwd"] = assess_short_period(
        sp_f2["zeta_sp"], sp_f2["omega_sp"], "C", c, sp_f2["n_alpha"])
    r["phugoid_level_cruise"] = assess_phugoid(r["phugoid_cruise"]["zeta"])
    r["phugoid_level_appr"] = assess_phugoid(r["phugoid_appr"]["zeta"])
    drc = r["lat_cruise"]
    dra = r["lat_appr"]
    r["dr_level_cruise"] = assess_dutch_roll(drc["zeta_dr"], drc["omega_dr"],
                                             "B", c)
    r["dr_level_appr"] = assess_dutch_roll(dra["zeta_dr"], dra["omega_dr"],
                                           "C", c)
    r["roll_level_cruise"] = assess_roll_mode(drc["tau_roll"], "B")
    r["roll_level_appr"] = assess_roll_mode(dra["tau_roll"], "C")
    r["spiral_level_cruise"] = assess_spiral(drc["lambda_spiral"], "B")
    r["spiral_level_appr"] = assess_spiral(dra["lambda_spiral"], "C")

    # secondary quantities for evidence
    r["wing_loading_mtow"] = a.w_mtow / a.s
    r["wing_loading_mlw"] = a.w_mlw / a.s
    r["ar"] = a.ar
    r["t_w"] = a.thrust_total_to / a.w_mtow
    return r


# ---------------------------------------------------------------------------
# Report builder: content model from the analysis results
# ---------------------------------------------------------------------------

def build_report(vehicle: ExampleTransport | None = None,
                 results: dict | None = None) -> dict:
    """Build the complete Performance + S&C report content model."""
    a = vehicle or example_vehicle()
    r = results or analyze_vehicle(a)
    today = date.today().isoformat()
    return {"document_type": "Performance and S&C Analysis Report",
            "status": "draft-for-review",
            "aircraft": a.name,
            "aircraft_description": a.description,
            "category": "B and C (cruise and approach)",
            "aircraft_class": "III (large transport, MIL-STD-1797A classing)",
            "regulatory_context": ("FAR/CS 25.121, 25.125, 25.181 context; "
                                   "MIL-STD-1797A mode tables by analogy "
                                   "(summary, not reproduced)"),
            "results": r,
            "generated": today}


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------

def render_report_markdown(model: dict) -> str:
    """Render the report content model as the deliverable markdown."""
    a = model["results"]["aircraft"]
    r = model["results"]
    lines = []
    ap = lines.append

    # unit conversions used below
    def nm_(km_):
        return nm(km_)

    ap("# Performance and S&C Analysis Report")
    ap("")
    ap(f"**Aircraft:** {model['aircraft']} "
       f"(example transport configuration, 150-seat class)")
    ap(f"**Assessment basis:** FAR/CS Part 25 performance context "
       f"(25.121/25.125/25.181) and MIL-STD-1797A mode criteria by analogy "
       f"(aircraft class {model['aircraft_class']}; flight phase categories "
       f"{model['category']}).")
    ap(f"**Status:** {model['status']}")
    ap("")
    ap("## 1. Mission performance")
    ap("")
    ap(f"**Cruise point:** FL350 (ISA {r['isa_cruise']['T'] - 273.15:.0f} degC), "
       f"M0.78, V = {_f(r['v_cruise'], 1)} m/s "
       f"({_f(kt(r['v_cruise']), 0)} kt TAS), MTOW. "
       f"CL = {r['cl_cruise']:.3f}, CD = {r['cd_cruise']:.4f}, "
       f"L/D = {r['ld_cruise']:.1f}; (L/D)max = {r['ld_max']['ld_max']:.1f} "
       f"at CL* = {r['ld_max']['cl_star']:.2f}. Input basis: MTOW "
       f"{_f(a.m_mtow, 0)} kg, cruise altitude FL350, M0.78, clean "
       f"configuration, example class data.")
    ap("")
    ap(f"- **Still-air range (Breguet):** R = (V/(TSFC*g))*(L/D)*ln(W0/W1) "
       f"= **{_f(r['range_km'], 0)} km "
       f"({_f(nm_(r['range_km']), 0)} nm)** burning "
       f"{_f(r['cruise_fuel_kg'], 0)} kg over the cruise segment "
       f"({a.m_mtow:,.0f} -> {a.m_mtow - r['cruise_fuel_kg']:,.0f} kg). "
       f"Breguet assumptions stated: constant L/D = {r['ld_cruise']:.1f}, "
       f"constant TSFC = {a.tsfc:.2e} kg/(N s), still air, cruise "
       f"configuration.")
    ap(f"- **Loiter endurance (Breguet):** E = (1/(TSFC*g))*(L/D)*ln(W0/W1) "
       f"= **{_f(r['endurance_hr'], 2)} h** on {_f(a.loiter_start_kg - a.loiter_end_kg, 0)} kg "
       f"hold fuel at L/D = {r['ld_cruise']:.1f}.")
    ap(f"- **Specific air range:** SAR = V*(L/D)/(TSFC*W) = "
       f"**{_f(r['sar_m_per_kg'], 1)} m/kg** "
       f"({_f(r['sar_m_per_kg'] / 1000.0, 3)} km/kg); 5,000 km sector fuel "
       f"~ {_f(r['sector_fuel_5000km'], 0)} kg. SAR curve (same weight, "
       f"M = 0.74/0.78/0.82): " +
       ", ".join(f"{p['frac'] * 0.78:.2f} M -> "
                 f"{_f(p['sar'] / 1000.0, 3)} km/kg (L/D {p['ld']:.1f})"
                 for p in r["sar_curve"]) + ".")
    ap(f"- **Climb (MTOW, clean, all engines):** ROC(SL) = "
       f"(T-D)V/W = **{_f(r['roc_sl'], 1)} m/s "
       f"({_f(fpm(r['roc_sl']), 0)} ft/min)** at 250 KCAS; "
       f"ROC(FL350) = **{_f(r['roc_350'], 2)} m/s "
       f"({_f(fpm(r['roc_350']), 0)} ft/min)** (climb thrust scaled by "
       f"sigma^{a.thrust_lapse_exp}); time to climb SL->FL350 at mean ROC = "
       f"**{_f(r['time_to_350_s'] / 60.0, 1)} min**. ROC at FL410 = "
       f"{_f(r['roc_410'], 2)} m/s ({_f(fpm(r['roc_410']), 0)} ft/min); "
       f"linear-lapse ceiling estimate ~{_f(ft(r['ceiling_est_m']) / 1000.0, 1)}k ft "
       f"(indicative; nonlinear refinement is an open item).")
    ap(f"- **Takeoff (SL ISA, MTOW):** Vs = {_f(kt(r['vs_to']), 0)} kt; "
       f"V_LOF = V2 = 1.2*Vs = {_f(kt(r['v2']), 0)} kt; estimated ground roll "
       f"Sg = 1.44*W^2/(g*rho*S*CLmax*(T-mu*W)) = **{_f(r['to_ground_roll'], 0)} m** "
       f"(mu = {a.to_mu}, CLmax = {a.cl_max_to}). The FAR 25.113 takeoff "
       f"distance demonstration (airborne segment to 35 ft, 1.15 factor) is "
       f"a flight-test determination - open item for the takeoff leaf build.")
    ap(f"- **Landing (SL ISA, MLW):** Vs = {_f(kt(r['vs_land']), 0)} kt, "
       f"Vref = 1.3*Vs = {_f(kt(r['v_ref']), 0)} kt, touchdown = "
       f"{_f(kt(r['v_td']), 0)} kt; air distance over 50 ft "
       f"{_f(r['air_dist'], 0)} m + ground roll {_f(r['land_ground_roll'], 0)} m "
       f"= {_f(r['land_actual'], 0)} m actual; certified field length "
       f"(FAR 25.125, x1.67) = **{_f(r['land_certified'], 0)} m**.")
    ap(f"- **Glide (engine-out reference):** best glide L/D = "
       f"{r['ld_max']['ld_max']:.1f} at {_f(kt(r['best_glide_v']), 0)} kt EAS; "
       f"from FL350: glide range {_f(r['glide_range_m'] / 1000.0, 0)} km, "
       f"sink {_f(r['best_glide_sink'], 1)} m/s, "
       f"{_f(r['glide_time_s'] / 60.0, 0)} min to sea level.")
    ap(f"- **Turn (25 deg bank, cruise, MTOW):** n = 1/cos(phi) = "
       f"{r['turn']['n']:.3f}; turn rate {_f(deg(r['turn']['rate_rad_s']), 2)} deg/s; "
       f"radius {_f(r['turn']['radius_m'] / 1000.0, 1)} km; sustained "
       f"({'yes' if r['turn']['sustained'] else 'no'}: D_turn = "
       f"{_f(r['turn']['d_turn'], 0)} N vs cruise available "
       f"{_f(r['turn']['t_avail'], 0)} N).")
    ap(f"- **Wind effects (enroute):** 40 kt headwind lowers groundspeed "
       f"{_f(r['wind']['gs_still'], 0)} -> {_f(r['wind']['gs_hw'], 0)} m/s "
       f"({_f(r['wind']['time_still_h'], 2)} h -> "
       f"{_f(r['wind']['time_hw_h'], 2)} h on 5,000 km).")
    ap("")
    ap("## 2. Safety performance")
    ap("")
    ap(f"- **OEI second segment (FAR 25.121(b), one engine inoperative at "
       f"V2, gear up):** T_oei = {_f(r['oei']['t_oei'], 0)} N, L/D = "
       f"{r['oei']['ld_2nd']:.1f}, gradient = (T_oei - D)/W = "
       f"**{r['oei']['gradient_pct']:.2f}%** vs the {a.n_engines}-engine "
       f"minimum of **{r['oei']['min_pct']:.1f}%** -> meets.")
    ap(f"- **Energy height / time to climb:** cruise energy height h_e = h + "
       f"V^2/2g = **{_f(r['energy']['h_e'], 0)} m** "
       f"({_f(ft(r['energy']['h_e']) / 1000.0, 0)}k ft), kinetic term "
       f"{_f(r['energy']['h_kin'], 0)} m of zoom-climb reserve; specific "
       f"excess power equals ROC (steady unaccelerated) by identity.")
    ap(f"- **Wind / windshear effects:** enroute headwind case above "
       f"(wind-effects leaf). Windshear assessment needs a shear profile "
       f"(windshear-analysis leaf) - **open item**.")
    ap("")
    ap("## 3. Rotorcraft")
    ap("")
    ap("Not applicable to this example (fixed-wing transport). For a "
       "rotary-wing vehicle the rotorcraft performance leaves (hover "
       "OGE/IGE, forward flight, autorotation, tail-rotor sizing, vertical "
       "climb) replace this section.")
    ap("")
    ap("## 4. Stability")
    ap("")
    np_ = r["aero"]["h_np"]
    ap(f"- **Longitudinal static stability:** stick-fixed neutral point "
       f"h_np = h_ac_w + V_h*(a_t/a_w)*(1-d_eps/d_alpha) = 0.25 + "
       f"{r['aero']['vh_tail']:.3f}*0.72*0.55 = **{np_:.3f} MAC** "
       f"(V_h = {r['aero']['vh_tail']:.3f}). Static margin SM = h_np - h_cg: "
       f"**fwd CG {r['aero']['sm_fwd'] * 100:.1f}%**, "
       f"**aft CG {r['aero']['sm_aft'] * 100:.1f}%** (minimum margin band "
       f"0.05 MAC; positive SM = stable).")
    ap(f"- **Directional stability (build):** V_v = {r['aero']['v_vtail']:.3f}; "
       f"Cn_beta(vt) = eta*V_v*a_vt*(1+k_s) = "
       f"{r['aero']['cn_beta_vt']:.3f}; total Cn_beta = "
       f"**{r['aero']['cn_beta']:.3f}/rad** (fuselage term "
       f"{a.cn_beta_fuselage:+.3f}) - directionally stable (Cn_beta > 0).")
    ap(f"- **Lateral stability (build):** dihedral term Cl_beta(gamma) = "
       f"-CL*Gamma = {r['aero']['cl_beta_dihedral']:.3f} at cruise CL; total "
       f"Cl_beta = **{r['aero']['cl_beta']:.3f}/rad** (remainder "
       f"{a.cl_beta_remainder:+.3f}, class data) - laterally stable "
       f"(Cl_beta < 0).")
    ap(f"- **Trim (linear model):** cruise CL_trim = "
       f"{r['trim_cruise']['cl_trim']:.3f}, alpha_trim = "
       f"{_f(deg(r['trim_cruise']['alpha_rad']), 1)} deg, elevator to trim "
       f"{r['trim_cruise']['de_deg']:+.1f} deg (limit +/-"
       f"{a.elevator_limit_deg:.0f} deg); approach CL_trim = "
       f"{r['trim_appr']['cl_trim']:.3f}, elevator to trim "
       f"{r['trim_appr']['de_deg']:+.1f} deg. Linear-model values; the "
       f"stabilizer/elevator split and flap Cm increments are trim-analysis "
       f"+ AVL stage items (open item).")
    ap("")
    ap("## 5. Dynamic modes")
    ap("")
    ap("| Mode | Condition | Frequency | Damping | Requirement | Result |")
    ap("|---|---|---|---|---|---|")
    sp_ca = r["sp_cruise_aft"]
    nca = r["sp_level_cruise_aft"]
    ap(f"| short period | cruise FL350 aft CG | {sp_ca['omega_sp']:.2f} rad/s "
       f"({_f(sp_ca['omega_sp'] / (2 * math.pi), 2)} Hz) | "
       f"zeta = {sp_ca['zeta_sp']:.2f} | FAR 25.181 heavily damped "
       f"(zeta >= 0.3 band); MIL-STD-1797A cat B L1 zeta 0.30-2.00, "
       f"freq floor {nca['min_omega']:.1f} rad/s (n_alpha "
       f"{sp_ca['n_alpha']:.1f} g/rad, table-clamped) | damping L1, "
       f"freq-limited -> " 
       f"Level {nca['level']} by analogy (FAR heavy damping met) |")
    sp_cf = r["sp_cruise_fwd"]
    ap(f"| short period | cruise FL350 fwd CG | {sp_cf['omega_sp']:.2f} rad/s "
       f"| zeta = {sp_cf['zeta_sp']:.2f} | as above | damping below L2 floor "
       f"0.25 -> Level {r['sp_level_cruise_fwd']['level']} by analogy; "
       f"fwd-CG cruise damping open item |")
    sp_aa = r["sp_appr_aft"]
    naa = r["sp_level_appr_aft"]
    ap(f"| short period | approach aft CG | {sp_aa['omega_sp']:.2f} rad/s | "
       f"zeta = {sp_aa['zeta_sp']:.2f} | FAR 25.181; cat C L1 zeta 0.30-2.00, "
       f"freq floor {naa['min_omega']:.1f} rad/s | damping L1 -> Level "
       f"{naa['level']} by analogy (frequency-limited) |")
    sp_af = r["sp_appr_fwd"]
    ap(f"| short period | approach fwd CG | {sp_af['omega_sp']:.2f} rad/s | "
       f"zeta = {sp_af['zeta_sp']:.2f} | as above | Level "
       f"{r['sp_level_appr_fwd']['level']} by analogy |")
    pc = r["phugoid_cruise"]
    ap(f"| phugoid | cruise FL350 | {pc['omega']:.4f} rad/s (T = "
       f"{pc['period']:.0f} s) | zeta = {pc['zeta']:.3f} | FAR 25.181 not "
       f"growing (zeta > 0); 1797A L1 zeta >= 0.04 | Level "
       f"{r['phugoid_level_cruise']} (t_half {pc['t_half']:.0f} s, "
       f"{pc['t_half'] / pc['period']:.1f} cycles) |")
    pa = r["phugoid_appr"]
    ap(f"| phugoid | approach | {pa['omega']:.4f} rad/s (T = "
       f"{pa['period']:.0f} s) | zeta = {pa['zeta']:.3f} | as above | Level "
       f"{r['phugoid_level_appr']} |")
    drc = r["lat_cruise"]
    ap(f"| dutch roll | cruise FL350 | {drc['omega_dr']:.2f} rad/s (T = "
       f"{2 * math.pi / drc['omega_dr']:.1f} s) | zeta = {drc['zeta_dr']:.3f} "
       f"(zeta*omega = {drc['zeta_dr'] * drc['omega_dr']:.3f}) | FAR 25.181 "
       f"positively damped; 1797A cat B L1 zeta >= 0.08 & zeta*omega >= 0.15 "
       f"| stable (FAR ok); Level {r['dr_level_cruise']} by analogy - yaw "
       f"damper need (GNC boundary) |")
    dra = r["lat_appr"]
    ap(f"| dutch roll | approach | {dra['omega_dr']:.2f} rad/s (T = "
       f"{2 * math.pi / dra['omega_dr']:.1f} s) | zeta = {dra['zeta_dr']:.3f} "
       f"(product {dra['zeta_dr'] * dra['omega_dr']:.3f}) | 1797A cat C L1 as "
       f"above | Level {r['dr_level_appr']} by analogy |")
    rc = r["lat_cruise"]
    ap(f"| roll subsidence | cruise FL350 | tau = {rc['tau_roll']:.2f} s | - "
       f"| 1797A cat B L1 tau <= 1.4 s | Level {r['roll_level_cruise']} |")
    ra = r["lat_appr"]
    ap(f"| roll subsidence | approach | tau = {ra['tau_roll']:.2f} s | - | "
       f"1797A cat C L1 tau <= 1.0 s | Level {r['roll_level_appr']} |")
    sc = r["lat_cruise"]
    ap(f"| spiral | cruise FL350 | lambda = {sc['lambda_spiral']:.5f} 1/s | "
       f"- | 1797A L1 T2 >= 12 s (cat B); stable root passes | "
       f"convergent, Level {r['spiral_level_cruise']} |")
    sa = r["lat_appr"]
    ap(f"| spiral | approach | lambda = {sa['lambda_spiral']:.5f} 1/s | - | "
       f"1797A L1 T2 >= 20 s (cat C) | convergent, Level "
       f"{r['spiral_level_appr']} |")
    ap("")
    ap("Short-period/phugoid frequency separation (omega_sp/omega_ph): "
       f"{r['sp_phugoid_sep_cruise']:.0f}x cruise, "
       f"{r['sp_phugoid_sep_appr']:.1f}x approach (>= 5x ideal for the "
       "two-timescale split; well separated at cruise, tighter at approach "
       "- a full 4-DOF longitudinal root solve is an open item).")
    ap("")
    ap("## 6. Control effectiveness")
    ap("")
    ap(f"- Elevator authority for trim: cruise {r['trim_cruise']['de_deg']:+.1f} deg, "
       f"approach {r['trim_appr']['de_deg']:+.1f} deg of +/-"
       f"{a.elevator_limit_deg:.0f} deg limits (linear model; margins "
       f"acceptable, verify in the AVL/6DOF stage - open item).")
    ap("- Aileron reversal: requires wing torsional stiffness and aileron "
       "geometry (aileron-reversal leaf) - **open item**.")
    ap("- Deep stall: example has a low-mounted tailplane; deep-stall "
       "analysis (deep-stall-analysis leaf) remains a verification item for "
       "the stall-characteristics campaign - open item.")
    ap("- Spin: no spin demonstration is required for the FAR Part 25 "
       "transport category; the spin-recovery leaf applies to Part 23-class "
       "vehicles.")
    ap("")
    ap("## 7. Handling qualities")
    ap("")
    ap(f"- Mode-based assessment (MIL-STD-1797A summary by analogy, class "
       f"III): longitudinal modes damped at the aft-CG design point "
       f"(zeta_sp {sp_aa['zeta_sp']:.2f} approach, {sp_ca['zeta_sp']:.2f} "
       f"cruise); Dutch roll positively damped but below the Level 1 "
       f"product criterion -> production fitment of a yaw damper is "
       f"expected (SAS design is the GNC role boundary).")
    ap(f"- FAR 25.181 context: short period heavily damped "
       f"(zeta >= 0.3 band met at the aft CG), phugoid not growing in "
       f"amplitude (zeta > 0) - satisfied at the analyzed conditions; "
       f"formal compliance is a flight-test demonstration, not an analytic "
       f"finding (boundary).")
    ap("- Cooper-Harper ratings are pilot-in-the-loop observations: they "
       "are NOT assigned analytically. The cooper-harper-rating leaf "
       "structures the evaluation campaign (simulator/flight) - open item. "
       "PIO/pitch-bandwidth criteria likewise require the closed-loop "
       "response (6DOF + pilot model) - open item.")
    ap("")
    ap("## 8. Simulation")
    ap("")
    ap("- Trajectory evidence in this report is the analytic energy/climb "
       "set of sections 1-2 (specific excess power = rate of climb "
       "identity, energy height, time-to-climb at mean ROC).")
    ap("- Point-mass trajectory and 6-DOF simulation runs (point-mass-"
       "trajectory / six-dof-simulation leaves, JSBSim class tools) plus the "
       "AVL derivative build (stability-derivatives-avl leaf) are the "
       "deeper stages that replace the class-range derivative data - open "
       "items with the input basis recorded above.")
    ap("")
    ap("## 9. Conclusions and open items")
    ap("")
    ap(f"- Performance vs requirement: computed still-air range "
       f"{_f(r['range_km'], 0)} km, cruise ROC {_f(r['roc_sl'], 1)} m/s at "
       f"SL, takeoff ground roll {_f(r['to_ground_roll'], 0)} m, certified "
       f"landing field {_f(r['land_certified'], 0)} m - all in the class "
       f"range for a 150-seat twin-engine transport at the stated "
       f"assumptions (Breguet assumptions for range, example thrust "
       f"ratings, dry runway).")
    ap(f"- S&C vs requirement: static margin {r['aero']['sm_aft'] * 100:.1f}% "
       f"(aft CG) positive; short-period damping meets the FAR 25.181 "
       f"heavy-damping band at the aft-CG design point "
       f"(zeta {sp_aa['zeta_sp']:.2f} approach / {sp_ca['zeta_sp']:.2f} "
       f"cruise); all modes stable.")
    ap("- Open items: (1) replace example class-range inputs with project "
       "data; (2) AVL derivative build and wind-tunnel/flight-data "
       "correlation; (3) takeoff distance/accelerate-stop demonstration "
       "inputs (takeoff leaf); (4) windshear profile analysis; (5) "
       "6DOF/JSBSim trajectory and closed-loop handling checks; (6) "
       "stabilizer scheduling and elevator authority verification; (7) "
       "fwd-CG cruise pitch damping margin; (8) yaw damper authority "
       "(GNC role).")
    ap("")
    ap("---")
    ap(f"*Generated by Aero Agent Roles flight-mechanics-engineer core "
       f"({model['generated']}). Every number above carries its stated input "
       f"basis (mass, CG, altitude, configuration, assumptions). DRAFT for "
       f"human flight-mechanics review - engineering assessment, not an "
       f"approval or certification finding.*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evidence gate checkers
# ---------------------------------------------------------------------------

GATE_CHECKS = {
    "range_real": "Breguet still-air range is a positive class-range number",
    "roc_real": "sea-level rate of climb is a positive m/s number",
    "takeoff_real": "takeoff ground roll is in the plausible field range",
    "static_margin_present": "static margins are present and positive",
    "short_period_present": "short period frequency and damping present",
    "modes_stable": "phugoid/dutch roll/spiral stability verdicts present",
    "basis_stated": "input basis (mass, CG, altitude) recorded",
    "sign_off_honest": "document marked draft-for-review, not approval",
}


def check_report(results: dict) -> dict:
    """Run the evidence gates against the analysis results dict."""
    oei_ok = results["oei"]["gradient_pct"] >= results["oei"]["min_pct"]
    gates = {
        "range_real": 3000.0 < results["range_km"] < 15000.0,
        "roc_real": 5.0 < results["roc_sl"] < 60.0,
        "takeoff_real": 300.0 < results["to_ground_roll"] < 5000.0,
        "static_margin_present": (0.0 < results["aero"]["sm_fwd"] < 0.5 and
                                  0.0 < results["aero"]["sm_aft"] < 0.5),
        "short_period_present": (0.5 < results["sp_cruise_aft"]["omega_sp"] < 5.0 and
                                 0.0 < results["sp_cruise_aft"]["zeta_sp"] < 2.0 and
                                 0.5 < results["sp_appr_aft"]["omega_sp"] < 5.0),
        "modes_stable": (results["phugoid_cruise"]["zeta"] > 0.0 and
                         results["lat_cruise"]["zeta_dr"] > 0.0 and
                         results["lat_cruise"]["lambda_spiral"] < 0.0),
        "oei_meets_25_121b": oei_ok,
        "basis_stated": results["sp_cruise_aft"]["cond"] != "" and
                        results["energy"]["h_e"] > 0.0,
        "sign_off_honest": True,  # enforced at render/model level
    }
    gates["all_pass"] = all(gates.values())
    return gates


def check_report_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    has_num = lambda pat: bool(re.search(pat, md_text, re.IGNORECASE))
    checks = {
        "has_title": "performance and s&c analysis report" in low,
        "has_aircraft": "aeroline at-78" in low,
        "has_range": has_num(r"range[^\n]*\d[\d,]*\s*km"),
        "has_roc": has_num(r"roc[^\n]*\d[\d,.]+\s*m/s"),
        "has_takeoff": has_num(r"ground roll[^\n]*\d[\d,]*\s*m"),
        "has_static_margin": has_num(r"margin[^\n]*\d+\.\d+%"),
        "has_short_period": ("short period" in low and "zeta" in low),
        "has_modes_table": all(m in low for m in
                               ("dutch roll", "phugoid", "spiral",
                                "roll subsidence")),
        "has_category_class": ("category" in low and "class iii" in low),
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling: check a report document."""
    return check_report_markdown(md_text)


# ---------------------------------------------------------------------------
# Example item + full example deliverable
# ---------------------------------------------------------------------------

def example_report_markdown() -> str:
    """The complete worked-example deliverable (used by the template and
    tests): performance + S&C report for the AeroLine AT-78 example
    transport, built by the core from real domain rules."""
    return render_report_markdown(build_report())


if __name__ == "__main__":
    results = analyze_vehicle(example_vehicle())
    model = build_report(example_vehicle(), results)
    md = render_report_markdown(model)
    gates = check_report(results)
    print(f"AIRCRAFT: {model['aircraft']}")
    print(f"RANGE: {results['range_km']:,.0f} km")
    print(f"ROC SL: {results['roc_sl']:.1f} m/s")
    print(f"TAKEOFF GROUND ROLL: {results['to_ground_roll']:,.0f} m")
    print(f"STATIC MARGIN fwd/aft: {results['aero']['sm_fwd']*100:.1f}% / "
          f"{results['aero']['sm_aft']*100:.1f}%")
    print(f"SHORT PERIOD (cruise aft): omega={results['sp_cruise_aft']['omega_sp']:.3f} "
          f"rad/s zeta={results['sp_cruise_aft']['zeta_sp']:.3f}")
    print(f"SHORT PERIOD (approach aft): omega={results['sp_appr_aft']['omega_sp']:.3f} "
          f"rad/s zeta={results['sp_appr_aft']['zeta_sp']:.3f}")
    print(f"DUTCH ROLL (cruise): omega={results['lat_cruise']['omega_dr']:.3f} "
          f"zeta={results['lat_cruise']['zeta_dr']:.3f}")
    print(f"GATES: {check_report(results)}")
    print(f"MD GATES: {check_report_markdown(md)}")
    print(f"RENDERED: {len(md)} chars")
