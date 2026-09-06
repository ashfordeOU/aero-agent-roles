#!/usr/bin/env python3
"""aircraft_performance_core.py - Aircraft Performance Engineer executable core.

This is the role's ENGINE: given a multi-aircraft performance analysis
case set it runs the flight-mechanics computations of the nine bound
AeroSkills flight-mechanics/performance leaves - the FAR-25.113-style
engine-out balanced field length and V1 decision-speed balance of a
twin-engine transport, the propeller Breguet cruise range of a
turboprop transport, and the FAR-29 rotorcraft checks of a helicopter
family (main-rotor sizing from the takeoff weight and disk-loading
ceiling, blade flap dynamics, lead-lag dynamics with ground-resonance
clearance, hover in ground effect, axial-descent flow states with the
windmill-brake momentum model, banked-turn performance, and the
range/endurance fuel closure) - and BUILDS the Aircraft Performance
Analysis Report content. It also gate-checks deliverables.

Domain rules encoded here are standard engineering methodology
(summary-only) as implemented by the bound AeroSkills leaves and named
there to the public standards FAR-25 and FAR-29 (US government work);
the worked-example numbers each section prints are the REAL numbers the
leaves' own logic modules produce for their reference cases. This core
reimplements the same public-domain formulas with identical signatures
so a dispatched cross-check (cli.py --bundle) yields core_value ==
skill_value (delta 0 or within recorded tolerance). No proprietary
standard text is reproduced. Standalone: no external repo needed.
"""
from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass, field
from datetime import date

PI = math.pi
G0 = 9.80665             # standard gravity, m/s^2 (FAR/CS practice constant)
RHO_SL = 1.225           # sea-level air density, kg/m^3 (default only)
A0_SL = 340.3            # sea-level speed of sound, m/s


def _today() -> str:
    return os.environ.get("ROLE_GEN_DATE", date.today().isoformat())


# ---------------------------------------------------------------------------
# Airplane case 1: engine-out balanced field length + V1 (FAR-25.113-style)
# ---------------------------------------------------------------------------
# Method (paraphrase of the balanced-field-length leaf, which encodes the
# FAR-25 multi-engine takeoff practice): accelerate on all engines to the
# decision speed V1, then balance the accelerate-stop distance (react +
# brake to a full stop) against the accelerate-go distance (continue on
# the remaining engines to lift-off, rotate, climb over the 35-ft obstacle
# on the engine-out climb gradient). The balanced V1 is where the two
# distances are equal; the balanced field length is that common distance.
# Module constants: reaction 1 s, rotation 1 s, obstacle 10.668 m (35 ft).
REACTION_TIME_S = 1.0
ROTATION_TIME_S = 1.0
OBSTACLE_HEIGHT_M = 10.668  # 35 ft, the FAR-25.113 obstacle height


def oei_thrust(thrust_all_n, engine_count):
    """One-engine-inoperative thrust (N): T_OEI = T_all * (n-1)/n."""
    if thrust_all_n <= 0:
        raise ValueError("all-engine thrust must be > 0, got %r" % (thrust_all_n,))
    if engine_count < 2:
        raise ValueError("engine_count must be >= 2, got %r" % (engine_count,))
    return thrust_all_n * (engine_count - 1) / engine_count


def ground_acceleration(thrust_n, weight_n, mu_roll, g0=G0):
    """Constant ground-roll acceleration a = g0*(T - mu*W)/W (m/s^2)."""
    if weight_n <= 0:
        raise ValueError("weight must be > 0, got %r" % (weight_n,))
    if thrust_n <= 0:
        raise ValueError("thrust must be > 0, got %r" % (thrust_n,))
    if not (0.0 <= mu_roll < 1.0):
        raise ValueError("rolling friction mu_roll must be in [0, 1), got %r"
                         % (mu_roll,))
    if thrust_n <= mu_roll * weight_n:
        raise ValueError("thrust %r must exceed rolling friction %r"
                         % (thrust_n, mu_roll * weight_n))
    return g0 * (thrust_n - mu_roll * weight_n) / weight_n


def braking_deceleration(mu_brake, g0=G0):
    """Braking deceleration magnitude a_brake = g0 * mu_brake (m/s^2)."""
    if not (0.0 < mu_brake < 1.0):
        raise ValueError("brake friction mu_brake must be in (0, 1), got %r"
                         % (mu_brake,))
    return g0 * mu_brake


def accelerate_distance(v_from_ms, v_to_ms, accel_m_s2):
    """Distance to accelerate between two speeds: s = (v2^2 - v1^2)/(2 a)."""
    if v_from_ms < 0:
        raise ValueError("v_from must be >= 0, got %r" % (v_from_ms,))
    if v_to_ms <= v_from_ms:
        raise ValueError("v_to must exceed v_from, got %r to %r"
                         % (v_from_ms, v_to_ms))
    if accel_m_s2 <= 0:
        raise ValueError("acceleration must be > 0, got %r" % (accel_m_s2,))
    return (v_to_ms ** 2 - v_from_ms ** 2) / (2.0 * accel_m_s2)


def stop_distance(v_ms, decel_m_s2):
    """Braking distance to a full stop from a speed: s = v^2/(2 decel)."""
    if v_ms < 0:
        raise ValueError("speed must be >= 0, got %r" % (v_ms,))
    if decel_m_s2 <= 0:
        raise ValueError("deceleration must be > 0, got %r" % (decel_m_s2,))
    return v_ms ** 2 / (2.0 * decel_m_s2)


def accelerate_stop_distance(v1_ms, thrust_all_n, weight_n, mu_roll,
                             mu_brake, reaction_time_s=REACTION_TIME_S,
                             g0=G0):
    """Accelerate-stop distance (m): roll to V1 on all engines, react,
    brake to a full stop. ASD(0) = 0."""
    if reaction_time_s < 0:
        raise ValueError("reaction time must be >= 0, got %r"
                         % (reaction_time_s,))
    if v1_ms < 0:
        raise ValueError("V1 decision speed must be >= 0, got %r" % (v1_ms,))
    if v1_ms == 0:
        return 0.0
    a_all = ground_acceleration(thrust_all_n, weight_n, mu_roll, g0)
    s_roll = accelerate_distance(0.0, v1_ms, a_all)
    s_react = v1_ms * reaction_time_s
    s_stop = stop_distance(v1_ms, braking_deceleration(mu_brake, g0))
    return s_roll + s_react + s_stop


def accelerate_go_distance(v1_ms, thrust_all_n, engine_count, weight_n,
                           mu_roll, v_lof_ms, oei_climb_gradient,
                           obstacle_height_m=OBSTACLE_HEIGHT_M,
                           rotation_time_s=ROTATION_TIME_S, g0=G0):
    """Accelerate-go distance (m): all-engine roll to V1, engine-out roll
    V1 -> V_LOF, rotate at V_LOF, climb over the 35-ft obstacle on the
    engine-out gradient."""
    if v1_ms < 0:
        raise ValueError("V1 decision speed must be >= 0, got %r" % (v1_ms,))
    if v_lof_ms <= 0:
        raise ValueError("lift-off speed must be > 0, got %r" % (v_lof_ms,))
    if v_lof_ms < v1_ms:
        raise ValueError("lift-off speed %r must not be below decision "
                         "speed %r" % (v_lof_ms, v1_ms))
    if oei_climb_gradient <= 0:
        raise ValueError("OEI climb gradient must be > 0, got %r"
                         % (oei_climb_gradient,))
    if obstacle_height_m <= 0:
        raise ValueError("obstacle height must be > 0, got %r"
                         % (obstacle_height_m,))
    if rotation_time_s < 0:
        raise ValueError("rotation time must be >= 0, got %r"
                         % (rotation_time_s,))
    t_oei = oei_thrust(thrust_all_n, engine_count)
    a_all = ground_acceleration(thrust_all_n, weight_n, mu_roll, g0)
    a_oei = ground_acceleration(t_oei, weight_n, mu_roll, g0)
    s_roll_all = (0.0 if v1_ms == 0
                  else accelerate_distance(0.0, v1_ms, a_all))
    s_roll_oei = (0.0 if v1_ms == v_lof_ms
                  else accelerate_distance(v1_ms, v_lof_ms, a_oei))
    s_air = obstacle_height_m / oei_climb_gradient
    return s_roll_all + s_roll_oei + v_lof_ms * rotation_time_s + s_air


def balanced_v1(thrust_all_n, engine_count, weight_n, mu_roll, mu_brake,
                v_lof_ms, oei_climb_gradient,
                reaction_time_s=REACTION_TIME_S,
                obstacle_height_m=OBSTACLE_HEIGHT_M,
                rotation_time_s=ROTATION_TIME_S, g0=G0):
    """Balanced decision speed V1 where ASD = AGD (m/s): the positive root
    of A V1^2 + B V1 + C = 0 with A = 1/(2 a_brake) + 1/(2 a_oei),
    B = reaction time, C = -(V_LOF^2/(2 a_oei) + V_LOF * t_rotation +
    obstacle/gradient). Raises ValueError when the root falls outside
    [0, V_LOF] (no balanced decision exists for the case)."""
    if v_lof_ms <= 0:
        raise ValueError("lift-off speed must be > 0, got %r" % (v_lof_ms,))
    if reaction_time_s < 0:
        raise ValueError("reaction time must be >= 0, got %r"
                         % (reaction_time_s,))
    if rotation_time_s < 0:
        raise ValueError("rotation time must be >= 0, got %r"
                         % (rotation_time_s,))
    if obstacle_height_m <= 0:
        raise ValueError("obstacle height must be > 0, got %r"
                         % (obstacle_height_m,))
    t_oei = oei_thrust(thrust_all_n, engine_count)
    a_oei = ground_acceleration(t_oei, weight_n, mu_roll, g0)
    a_brake = braking_deceleration(mu_brake, g0)
    a_coeff = 1.0 / (2.0 * a_brake) + 1.0 / (2.0 * a_oei)
    b_coeff = reaction_time_s
    c_coeff = -(v_lof_ms ** 2 / (2.0 * a_oei)
                + v_lof_ms * rotation_time_s
                + obstacle_height_m / oei_climb_gradient)
    discriminant = b_coeff ** 2 - 4.0 * a_coeff * c_coeff
    v1 = (-b_coeff + math.sqrt(discriminant)) / (2.0 * a_coeff)
    if not (0.0 <= v1 <= v_lof_ms):
        raise ValueError("balanced V1 %r falls outside the physical bracket "
                         "[0, %r]; no balanced decision exists for this case"
                         % (v1, v_lof_ms))
    return v1


def balanced_field_length(v1_ms, thrust_all_n, engine_count, weight_n,
                          mu_roll, mu_brake, v_lof_ms, oei_climb_gradient,
                          reaction_time_s=REACTION_TIME_S,
                          obstacle_height_m=OBSTACLE_HEIGHT_M,
                          rotation_time_s=ROTATION_TIME_S, g0=G0):
    """Balanced field length (m): the common ASD(V1) = AGD(V1) distance at
    the balanced decision speed (accelerate-stop distance at balance)."""
    if v_lof_ms <= 0:
        raise ValueError("lift-off speed must be > 0, got %r" % (v_lof_ms,))
    if oei_climb_gradient <= 0:
        raise ValueError("OEI climb gradient must be > 0, got %r"
                         % (oei_climb_gradient,))
    if obstacle_height_m <= 0:
        raise ValueError("obstacle height must be > 0, got %r"
                         % (obstacle_height_m,))
    if rotation_time_s < 0:
        raise ValueError("rotation time must be >= 0, got %r"
                         % (rotation_time_s,))
    return accelerate_stop_distance(
        v1_ms, thrust_all_n, weight_n, mu_roll, mu_brake,
        reaction_time_s, g0)


# ---------------------------------------------------------------------------
# Airplane case 2: turboprop cruise range (propeller Breguet equation)
# ---------------------------------------------------------------------------
# R = (eta_p / (c_p * g0)) * (L/D) * ln(m0 / m1) with eta_p the propeller
# efficiency, c_p the power specific fuel consumption in kg/(W s), L/D the
# cruise lift-to-drag ratio, m0 the initial and m1 the final cruise mass.
# 1 lb/(hp h) = 0.45359237 / (745.6999 * 3600) kg/(W s).
LB_PER_HP_H_TO_KG_PER_W_S = 0.45359237 / (745.6999 * 3600.0)


def psfc_lb_per_hp_h_to_kg_per_w_s(value):
    """Convert a PSFC in lb/(hp h) into SI kg/(W s)."""
    if value < 0.0:
        raise ValueError("psfc must be non-negative")
    return value * LB_PER_HP_H_TO_KG_PER_W_S


def final_mass_from_fuel_fraction(initial_mass, fuel_fraction):
    """Final cruise mass from a fuel fraction: m1 = m0 * (1 - f)."""
    if initial_mass <= 0.0:
        raise ValueError("initial_mass must be positive")
    if not (0.0 <= fuel_fraction < 1.0):
        raise ValueError("fuel_fraction must be in [0, 1)")
    return initial_mass * (1.0 - fuel_fraction)


def propeller_range(propeller_efficiency, psfc_kg_per_w_s, ld,
                    initial_mass, final_mass):
    """Propeller Breguet cruise range R in meters."""
    if not (0.0 < propeller_efficiency <= 1.0):
        raise ValueError("propeller_efficiency must be in (0, 1]")
    if psfc_kg_per_w_s <= 0.0:
        raise ValueError("psfc_kg_per_w_s must be positive")
    if ld <= 0.0:
        raise ValueError("ld must be positive")
    if initial_mass <= 0.0:
        raise ValueError("initial_mass must be positive")
    if final_mass <= 0.0:
        raise ValueError("final_mass must be positive")
    if final_mass >= initial_mass:
        raise ValueError("final_mass must be below initial_mass")
    return ((propeller_efficiency / (psfc_kg_per_w_s * G0)) * ld
            * math.log(initial_mass / final_mass))


def propeller_range_km(propeller_efficiency, psfc_kg_per_w_s, ld,
                       initial_mass, final_mass):
    """Propeller Breguet cruise range in kilometers."""
    return propeller_range(propeller_efficiency, psfc_kg_per_w_s, ld,
                           initial_mass, final_mass) / 1000.0


def range_report(propeller_efficiency, psfc_kg_per_w_s, ld,
                 initial_mass, final_mass):
    """Range package dict with exactly the keys range_m and range_km."""
    range_m = propeller_range(propeller_efficiency, psfc_kg_per_w_s, ld,
                              initial_mass, final_mass)
    return {"range_m": range_m, "range_km": range_m / 1000.0}


# ---------------------------------------------------------------------------
# Rotorcraft case A: main rotor sizing (weight-borne hover, FAR-29 context)
# ---------------------------------------------------------------------------
# Disk area A = T / DL_max at the main-rotor-disk-loading ceiling,
# R = sqrt(A/pi); hover thrust coefficient CT = T / (rho*A*Vtip^2);
# solidity sigma = CT / (CT/sigma)_design; blade area A_b = sigma*A and
# chord c = A_b / (b*R); tip Mach M = Vtip / a.
def disk_area_and_radius(thrust, disk_loading_max):
    """Disk area A = thrust / disk_loading_max (m2) and radius
    R = sqrt(A / PI) (m), the disk sized exactly at the ceiling."""
    if thrust <= 0:
        raise ValueError("thrust must be > 0")
    if disk_loading_max <= 0:
        raise ValueError("disk_loading_max must be > 0")
    area = thrust / disk_loading_max
    radius = math.sqrt(area / PI)
    return area, radius


def hover_thrust_coefficient(thrust, rho, radius, tip_speed):
    """Hover thrust coefficient CT = T / (rho * A * Vtip^2), dimensionless."""
    if thrust <= 0:
        raise ValueError("thrust must be > 0")
    if rho <= 0:
        raise ValueError("rho must be > 0")
    if radius <= 0:
        raise ValueError("radius must be > 0")
    if tip_speed <= 0:
        raise ValueError("tip_speed must be > 0")
    area = PI * radius ** 2
    return thrust / (rho * area * tip_speed ** 2)


def solidity_closure(thrust_coefficient, ct_over_sigma_design):
    """Rotor solidity sigma = CT / (CT/sigma)_design, dimensionless."""
    if thrust_coefficient <= 0:
        raise ValueError("thrust_coefficient must be > 0")
    if ct_over_sigma_design <= 0:
        raise ValueError("ct_over_sigma_design must be > 0")
    return thrust_coefficient / ct_over_sigma_design


def blade_area_chord(solidity, area, blade_count, radius):
    """Total blade area A_b = sigma * A (m2) and constant chord
    c = A_b / (b * R) (m) on rectangular blades."""
    if solidity <= 0:
        raise ValueError("solidity must be > 0")
    if area <= 0:
        raise ValueError("area must be > 0")
    if radius <= 0:
        raise ValueError("radius must be > 0")
    if blade_count < 1 or not float(blade_count).is_integer():
        raise ValueError("blade_count must be a positive integer")
    blade_area = solidity * area
    chord = blade_area / (blade_count * radius)
    return blade_area, chord


def tip_mach(tip_speed, speed_of_sound):
    """Rotor tip Mach number M_tip = Vtip / a, dimensionless."""
    if tip_speed < 0:
        raise ValueError("tip_speed must be >= 0")
    if speed_of_sound <= 0:
        raise ValueError("speed_of_sound must be > 0")
    return tip_speed / speed_of_sound


# ---------------------------------------------------------------------------
# Rotorcraft case B: blade flap dynamics (Lock number, coning, flap freq)
# ---------------------------------------------------------------------------
# I_beta = m_b R^2 / 3 (uniform blade about the rotation axis); Lock number
# gamma = rho a c R^4 / I_beta (published band 5-12); hover coning
# a0 = 0.5 gamma (theta0/4 - lambda/3); flap frequency ratio
# nu = sqrt(1 + 1.5 e / (1 - e)), e = 0 gives exactly 1.0 (1/rev).
A_LIFT_DEFAULT = 5.73  # 1/rad typical section lift-curve slope


def blade_flap_inertia_uniform(blade_mass_kg, radius_m):
    """Moment of inertia of a uniform blade about the rotation axis."""
    if blade_mass_kg <= 0:
        raise ValueError("blade_mass_kg must be positive")
    if radius_m <= 0:
        raise ValueError("radius_m must be positive")
    return blade_mass_kg * radius_m ** 2 / 3.0


def lock_number(rho, lift_slope, chord_m, radius_m, flap_inertia):
    """Blade Lock number gamma = rho * a * c * R^4 / I_beta."""
    if rho <= 0:
        raise ValueError("rho must be positive")
    if lift_slope <= 0:
        raise ValueError("lift_slope must be positive")
    if chord_m <= 0:
        raise ValueError("chord_m must be positive")
    if radius_m <= 0:
        raise ValueError("radius_m must be positive")
    if flap_inertia <= 0:
        raise ValueError("flap_inertia must be positive")
    return rho * lift_slope * chord_m * radius_m ** 4 / flap_inertia


def hover_coning_angle(gamma, theta0_rad, inflow_ratio):
    """Steady hover coning angle a0 = 0.5 gamma (theta0/4 - lambda/3) rad."""
    if gamma <= 0:
        raise ValueError("gamma must be positive")
    if theta0_rad < 0:
        raise ValueError("theta0_rad must be non-negative")
    if inflow_ratio < 0:
        raise ValueError("inflow_ratio must be non-negative")
    return 0.5 * gamma * (theta0_rad / 4.0 - inflow_ratio / 3.0)


def flap_frequency_ratio(hinge_offset_fraction):
    """Rotating flap frequency ratio nu = sqrt(1 + 1.5 e / (1 - e))."""
    if hinge_offset_fraction < 0:
        raise ValueError("hinge_offset_fraction must be non-negative")
    if hinge_offset_fraction >= 1:
        raise ValueError("hinge_offset_fraction must be below 1")
    return math.sqrt(1.0 + 1.5 * hinge_offset_fraction
                     / (1.0 - hinge_offset_fraction))


def blade_flapping_summary(blade_mass_kg, radius_m, chord_m, theta0_rad,
                           inflow_ratio, hinge_offset_fraction,
                           lift_slope=A_LIFT_DEFAULT, rho=RHO_SL):
    """One-call blade flapping assessment dict: lock_number,
    flap_inertia_kg_m2, coning_angle_rad, coning_angle_deg,
    flap_frequency_ratio, flap_frequency_per_rev."""
    inertia = blade_flap_inertia_uniform(blade_mass_kg, radius_m)
    gamma = lock_number(rho, lift_slope, chord_m, radius_m, inertia)
    a0_rad = hover_coning_angle(gamma, theta0_rad, inflow_ratio)
    nu = flap_frequency_ratio(hinge_offset_fraction)
    return {
        "lock_number": gamma,
        "flap_inertia_kg_m2": inertia,
        "coning_angle_rad": a0_rad,
        "coning_angle_deg": a0_rad * 180.0 / PI,
        "flap_frequency_ratio": nu,
        "flap_frequency_per_rev": nu,
    }


# ---------------------------------------------------------------------------
# Rotorcraft case C: lead-lag dynamics + ground-resonance clearance
# ---------------------------------------------------------------------------
# Rotating lead-lag frequency ratio nu_zeta = sqrt(1.5 e / (1 - e)) (e = 0
# is exactly 0, lag has no 1/rev term); fixed-frame multiblade modes at nu
# per rev: collective nu*Omega/2pi, regressing |1-nu|*Omega/2pi, advancing
# (1+nu)*Omega/2pi; coincidence rotor speed Omega* = 2 pi omega_F / |1-nu|;
# clearance verdict within a margin of the operating speed.
def lag_frequency_ratio_hinge_offset(hinge_offset_fraction):
    """Rotating lead-lag frequency ratio nu_zeta = sqrt(1.5 e / (1 - e))."""
    if hinge_offset_fraction < 0:
        raise ValueError("hinge_offset_fraction must be non-negative")
    if hinge_offset_fraction >= 1:
        raise ValueError("hinge_offset_fraction must be below 1")
    return math.sqrt(1.5 * hinge_offset_fraction / (1.0 - hinge_offset_fraction))


def _hz(omega_rad_s, factor):
    return factor * omega_rad_s / (2.0 * PI)


def _check_nu_omega(nu, omega_rad_s):
    if nu < 0:
        raise ValueError("nu must be non-negative")
    if omega_rad_s <= 0:
        raise ValueError("omega_rad_s must be positive")


def fixed_frame_lag_modes(nu, omega_rad_s):
    """Fixed-frame multiblade lag modes (Hz): collective, regressing,
    advancing for a 3+ bladed rotor."""
    _check_nu_omega(nu, omega_rad_s)
    return {
        "collective_hz": _hz(omega_rad_s, nu),
        "regressing_hz": _hz(omega_rad_s, abs(1.0 - nu)),
        "advancing_hz": _hz(omega_rad_s, 1.0 + nu),
    }


def regressing_lag_frequency(nu, omega_rad_s):
    """Regressing lag mode frequency |1 - nu| * Omega / 2pi in Hz."""
    _check_nu_omega(nu, omega_rad_s)
    return _hz(omega_rad_s, abs(1.0 - nu))


def coincidence_rotor_speed(nu, airframe_frequency_hz):
    """Coincidence rotor speed Omega* = 2 pi omega_F / |1 - nu| in rad/s."""
    if nu < 0:
        raise ValueError("nu must be non-negative")
    if airframe_frequency_hz <= 0:
        raise ValueError("airframe_frequency_hz must be positive")
    if abs(1.0 - nu) == 0.0:
        raise ValueError("|1 - nu| must be non-zero (nu = 1 is not physical "
                         "for lag)")
    return 2.0 * PI * airframe_frequency_hz / abs(1.0 - nu)


def ground_resonance_clearance(nu, operating_omega_rad_s,
                               airframe_frequency_hz, margin=0.20):
    """Ground-resonance clearance verdict dict (coincidence_omega,
    operating_omega, clearance_fraction, verdict clear|resonance-adjacent)."""
    coincidence = coincidence_rotor_speed(nu, airframe_frequency_hz)
    if operating_omega_rad_s <= 0:
        raise ValueError("operating_omega_rad_s must be positive")
    if margin < 0:
        raise ValueError("margin must be non-negative")
    clearance = (coincidence - operating_omega_rad_s) / operating_omega_rad_s
    verdict = "clear" if abs(clearance) > margin else "resonance-adjacent"
    return {
        "coincidence_omega": coincidence,
        "operating_omega": operating_omega_rad_s,
        "clearance_fraction": clearance,
        "verdict": verdict,
    }


def _resolve_lag_frequency_ratio(hinge_offset_or_nu):
    """Summary convention: below 1 is a hinge offset e (converted), 1 or
    more is a direct lag frequency ratio nu (stiff-inplane practice)."""
    if hinge_offset_or_nu < 0:
        raise ValueError("hinge_offset_or_nu must be non-negative")
    if hinge_offset_or_nu < 1.0:
        return lag_frequency_ratio_hinge_offset(hinge_offset_or_nu)
    return hinge_offset_or_nu


def lead_lag_summary(hinge_offset_or_nu, omega_rad_s, airframe_frequency_hz,
                     margin=0.20):
    """One-call lead-lag dict: lag_frequency_ratio, collective_hz,
    regressing_hz, advancing_hz, coincidence_omega, operating_omega,
    clearance_fraction, verdict."""
    nu = _resolve_lag_frequency_ratio(hinge_offset_or_nu)
    modes = fixed_frame_lag_modes(nu, omega_rad_s)
    clearance = ground_resonance_clearance(nu, omega_rad_s,
                                           airframe_frequency_hz, margin)
    summary = {"lag_frequency_ratio": nu}
    summary.update(modes)
    summary.update(clearance)
    return summary


# ---------------------------------------------------------------------------
# Rotorcraft case D: hover in ground effect (Cheeseman-style factor)
# ---------------------------------------------------------------------------
# T = m g0; v_h = sqrt(T / (2 rho A)); P_ideal = T v_h; profile power
# P_profile = (1/8) rho sigma Cd0 A Vtip^3 (unchanged in ground effect);
# ground-effect factor k_ige = 1 - (R / (4 z))^2 valid for z/R >= 0.5
# (0.9375 at z = R, 0.75 at z = 0.5 R); P_i_ige = P_ideal k_ige;
# P_total_ige = k P_ideal k_ige + P_profile; P_total_oge = k P_ideal +
# P_profile; margin = P_available - P_total_ige; ceiling by bisection over
# [0.5 R, 50 R] when the available power cannot cover OGE hover.
K_DEFAULT = 1.15        # induced power factor (hover/fwd-flight convention)
MIN_Z_RATIO = 0.5       # validity floor for height / radius
DEFAULT_SOLIDITY = 0.08
DEFAULT_DRAG_COEFFICIENT = 0.012
DEFAULT_TIP_SPEED = 220.0


def disk_area(radius):
    """Rotor disk area A = PI * radius^2 in m2."""
    if radius <= 0:
        raise ValueError("radius must be positive")
    return PI * radius ** 2


def hover_induced_velocity(thrust, area, rho=RHO_SL):
    """Momentum-theory ideal induced velocity v_h = sqrt(T / (2 rho A))."""
    if thrust <= 0:
        raise ValueError("thrust must be positive")
    if area <= 0:
        raise ValueError("area must be positive")
    if rho <= 0:
        raise ValueError("rho must be positive")
    return math.sqrt(thrust / (2.0 * rho * area))


def ground_effect_factor(height, radius):
    """Cheeseman-style ground-effect factor k_ige = 1 - (R / (4 z))^2."""
    if radius <= 0:
        raise ValueError("radius must be positive")
    if height / radius < MIN_Z_RATIO:
        raise ValueError("height / radius must be >= %s for the "
                         "ground-effect model" % MIN_Z_RATIO)
    return 1.0 - (radius / (4.0 * height)) ** 2


def ige_induced_power(ideal_induced_power, ground_effect_factor):
    """Induced power in ground effect P_i_ige = P_ideal * factor (W)."""
    if ideal_induced_power < 0:
        raise ValueError("ideal induced power must be >= 0")
    if ground_effect_factor <= 0 or ground_effect_factor > 1:
        raise ValueError("ground effect factor must lie in (0, 1]")
    return ideal_induced_power * ground_effect_factor


def ige_total_power(ideal_induced_power, profile_power, ground_effect_factor,
                    k=K_DEFAULT):
    """Total hover power in ground effect k*P_ideal*factor + P_profile (W)."""
    if ideal_induced_power < 0:
        raise ValueError("ideal induced power must be >= 0")
    if profile_power < 0:
        raise ValueError("profile power must be >= 0")
    if ground_effect_factor <= 0 or ground_effect_factor > 1:
        raise ValueError("ground effect factor must lie in (0, 1]")
    if k <= 0:
        raise ValueError("induced power factor k must be positive")
    return k * ideal_induced_power * ground_effect_factor + profile_power


def power_margin(available_power, required_power):
    """Hover power margin = available - required (W)."""
    if available_power < 0:
        raise ValueError("available power must be >= 0")
    if required_power < 0:
        raise ValueError("required power must be >= 0")
    return available_power - required_power


def oge_total_power(ideal_induced_power, profile_power, k=K_DEFAULT):
    """Out-of-ground-effect total hover power k*P_ideal + P_profile (W)."""
    if ideal_induced_power < 0:
        raise ValueError("ideal induced power must be >= 0")
    if profile_power < 0:
        raise ValueError("profile power must be >= 0")
    if k <= 0:
        raise ValueError("induced power factor k must be positive")
    return k * ideal_induced_power + profile_power


def _profile_power(rho, area, solidity, drag_coefficient, tip_speed):
    """Average-section profile power (1/8) rho sigma Cd0 A Vtip^3 (W)."""
    return ((1.0 / 8.0) * rho * solidity * drag_coefficient * area
            * tip_speed ** 3)


def max_hover_height(weight_kg, radius, available_power, rho=RHO_SL,
                     solidity=DEFAULT_SOLIDITY,
                     drag_coefficient=DEFAULT_DRAG_COEFFICIENT,
                     tip_speed=DEFAULT_TIP_SPEED, k=K_DEFAULT):
    """Largest rotor height z (m) with IGE total power <= available power.

    Returns None when the available power covers the OGE total (hover at
    any height); bisects z over [0.5 R, 50 R] otherwise; raises ValueError
    when the power cannot even hover in full ground effect."""
    if weight_kg <= 0:
        raise ValueError("weight_kg must be positive")
    if radius <= 0:
        raise ValueError("radius must be positive")
    if available_power < 0:
        raise ValueError("available power must be >= 0")
    if rho <= 0:
        raise ValueError("rho must be positive")
    if solidity <= 0:
        raise ValueError("solidity must be positive")
    if drag_coefficient <= 0:
        raise ValueError("drag coefficient must be positive")
    if tip_speed <= 0:
        raise ValueError("tip speed must be positive")
    if k <= 0:
        raise ValueError("induced power factor k must be positive")

    thrust = weight_kg * G0
    area = disk_area(radius)
    v_h = hover_induced_velocity(thrust, area, rho)
    ideal_power = thrust * v_h
    prof_power = _profile_power(rho, area, solidity, drag_coefficient,
                                tip_speed)
    oge_total = oge_total_power(ideal_power, prof_power, k)
    if available_power >= oge_total:
        return None

    z_low = MIN_Z_RATIO * radius
    power_low = ige_total_power(ideal_power, prof_power,
                                ground_effect_factor(z_low, radius), k)
    if available_power < power_low:
        raise ValueError("available power below the IGE total power at the "
                         "lowest valid height; hover impossible even in "
                         "full ground effect")

    z_high = 50.0 * radius
    power_high = ige_total_power(ideal_power, prof_power,
                                 ground_effect_factor(z_high, radius), k)
    if available_power >= power_high:
        return z_high

    lo, hi = z_low, z_high
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        power_mid = ige_total_power(ideal_power, prof_power,
                                    ground_effect_factor(mid, radius), k)
        if power_mid <= available_power:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def hover_ground_effect(weight_kg, radius, height, rho=RHO_SL,
                        solidity=DEFAULT_SOLIDITY,
                        drag_coefficient=DEFAULT_DRAG_COEFFICIENT,
                        tip_speed=DEFAULT_TIP_SPEED, k=K_DEFAULT,
                        available_power=None):
    """One-call hover-in-ground-effect result dict."""
    if weight_kg <= 0:
        raise ValueError("weight_kg must be positive")
    if radius <= 0:
        raise ValueError("radius must be positive")
    if height / radius < MIN_Z_RATIO:
        raise ValueError("height / radius must be >= %s for the "
                         "ground-effect model" % MIN_Z_RATIO)
    if rho <= 0:
        raise ValueError("rho must be positive")
    if solidity <= 0:
        raise ValueError("solidity must be positive")
    if drag_coefficient <= 0:
        raise ValueError("drag coefficient must be positive")
    if tip_speed <= 0:
        raise ValueError("tip speed must be positive")
    if k <= 0:
        raise ValueError("induced power factor k must be positive")

    thrust = weight_kg * G0
    area = disk_area(radius)
    v_h = hover_induced_velocity(thrust, area, rho)
    ideal_power = thrust * v_h
    prof_power = _profile_power(rho, area, solidity, drag_coefficient,
                                tip_speed)
    factor = ground_effect_factor(height, radius)
    ige_induced = ige_induced_power(ideal_power, factor)
    ige_total = ige_total_power(ideal_power, prof_power, factor, k)
    oge_total = oge_total_power(ideal_power, prof_power, k)

    if available_power is not None:
        margin = power_margin(available_power, ige_total)
        ceiling = max_hover_height(weight_kg, radius, available_power, rho,
                                   solidity, drag_coefficient, tip_speed, k)
    else:
        margin = None
        ceiling = None

    return {
        "thrust_N": thrust,
        "area_m2": area,
        "hover_induced_velocity": v_h,
        "ideal_induced_power_W": ideal_power,
        "profile_power_W": prof_power,
        "ground_effect_factor": factor,
        "ige_induced_power_W": ige_induced,
        "ige_total_power_W": ige_total,
        "oge_total_power_W": oge_total,
        "power_margin_W": margin,
        "max_hover_height": ceiling,
    }


# ---------------------------------------------------------------------------
# Rotorcraft case E: axial descent flow states (windmill-brake momentum)
# ---------------------------------------------------------------------------
# Flow states by the descent-rate ratio w = Vd / v_h: Vd = 0 hover, 0 < w < 2
# vortex-ring band (momentum-invalid, empirical inflow, NASA TP-2005-213477
# public-domain context), w >= 2 windmill-brake state where momentum theory
# applies: v_i = Vd/2 - sqrt((Vd/2)^2 - v_h^2); signed power
# P = k T (-Vd + v_i) + P_profile (negative = rotor absorbs power from the
# airstream); torque Q = P / Omega; torque-reversal condition
# c = P_profile / (k T) vs v_h decides zero-shaft-power reachability
# (momentum root Vd = c + v_h^2/c only physical when c >= v_h).
def _require_positive(name, value):
    if value <= 0:
        raise ValueError("%s must be positive" % name)


def _require_non_negative(name, value):
    if value < 0:
        raise ValueError("%s must be non-negative" % name)


def _require_descent(name, value):
    if value < 0:
        raise ValueError("%s is negative; climb is not a descent state" % name)


def axial_flow_state(descent_rate, hover_induced_velocity):
    """Categorize the axial flow state: hover | vortex-ring-band |
    windmill-brake by the Vd / 2 v_h boundaries."""
    _require_positive("hover_induced_velocity", hover_induced_velocity)
    _require_descent("descent_rate", descent_rate)
    if descent_rate == 0.0:
        return "hover"
    if descent_rate < 2.0 * hover_induced_velocity:
        return "vortex-ring-band"
    return "windmill-brake"


def vortex_ring_band_limits(hover_induced_velocity):
    """Descent-rate limits of the vortex-ring band (0, 2 v_h) in m/s."""
    _require_positive("hover_induced_velocity", hover_induced_velocity)
    return (0.0, 2.0 * hover_induced_velocity)


def windmill_brake_induced_velocity(descent_rate, hover_induced_velocity):
    """Windmill-brake induced velocity v_i = Vd/2 - sqrt((Vd/2)^2 - v_h^2),
    valid only for Vd >= 2 v_h (physical branch, v_i never exceeds v_h)."""
    _require_positive("hover_induced_velocity", hover_induced_velocity)
    _require_descent("descent_rate", descent_rate)
    if descent_rate < 2.0 * hover_induced_velocity:
        raise ValueError("descent_rate below 2 * v_h lies inside the "
                         "vortex-ring band, momentum theory does not apply")
    half = descent_rate / 2.0
    return half - math.sqrt(half * half - hover_induced_velocity ** 2)


def rotor_descent_power(thrust_N, descent_rate, induced_velocity,
                        profile_power_W, k=K_DEFAULT):
    """Signed rotor shaft power in descent P = k T (-Vd + v_i) + P_profile."""
    _require_positive("thrust_N", thrust_N)
    _require_positive("k", k)
    _require_non_negative("profile_power_W", profile_power_W)
    _require_non_negative("induced_velocity", induced_velocity)
    _require_descent("descent_rate", descent_rate)
    return k * thrust_N * (-descent_rate + induced_velocity) + profile_power_W


def rotor_descent_torque(power_W, rotor_speed_rad_s):
    """Signed rotor torque in descent Q = P / Omega (N m)."""
    _require_positive("rotor_speed_rad_s", rotor_speed_rad_s)
    return power_W / rotor_speed_rad_s


def torque_reversal_condition(profile_power_W, thrust_N, k, v_h):
    """Zero-shaft-power reachability on the momentum windmill-brake branch:
    c = P_profile / (k T); the root Vd = c + v_h^2/c is physical only when
    c >= v_h (else momentum-unreachable, root None)."""
    _require_non_negative("profile_power_W", profile_power_W)
    _require_positive("thrust_N", thrust_N)
    _require_positive("k", k)
    _require_positive("v_h", v_h)
    c = profile_power_W / (k * thrust_N)
    c_less_than_vh = c < v_h
    if c_less_than_vh:
        verdict = ("momentum-unreachable: the autorotative equilibrium lies "
                   "in the empirical vortex-ring/turbulent-wake regime")
        root = None
    else:
        root = c + v_h * v_h / c
        verdict = ("momentum-reachable: zero-shaft-power root at "
                   "Vd = c + v_h^2 / c on the windmill-brake branch")
    return {
        "c": c,
        "v_h": v_h,
        "c_less_than_vh": c_less_than_vh,
        "verdict": verdict,
        "momentum_root_Vd": root,
    }


def descent_summary(thrust_N, rotor_radius, profile_power_W, descent_rate,
                    rho=RHO_SL, k=K_DEFAULT, rotor_speed_rad_s=None):
    """One-call axial-descent dict (flow_state, v_h, band_limits,
    induced_velocity, power_W, torque_Nm, momentum_root_reachable)."""
    _require_positive("thrust_N", thrust_N)
    _require_positive("rotor_radius", rotor_radius)
    _require_positive("rho", rho)
    _require_positive("k", k)
    _require_non_negative("profile_power_W", profile_power_W)
    _require_descent("descent_rate", descent_rate)
    if rotor_speed_rad_s is not None:
        _require_positive("rotor_speed_rad_s", rotor_speed_rad_s)

    area = PI * rotor_radius ** 2
    v_h = math.sqrt(thrust_N / (2.0 * rho * area))
    state = axial_flow_state(descent_rate, v_h)
    band = vortex_ring_band_limits(v_h)
    reachable = not torque_reversal_condition(
        profile_power_W, thrust_N, k, v_h)["c_less_than_vh"]

    if state == "windmill-brake":
        v_i = windmill_brake_induced_velocity(descent_rate, v_h)
        power = rotor_descent_power(thrust_N, descent_rate, v_i,
                                    profile_power_W, k)
        torque = None
        if rotor_speed_rad_s is not None:
            torque = rotor_descent_torque(power, rotor_speed_rad_s)
    else:
        v_i = None
        power = None
        torque = None

    return {
        "flow_state": state,
        "v_h": v_h,
        "band_limits": band,
        "induced_velocity": v_i,
        "power_W": power,
        "torque_Nm": torque,
        "momentum_root_reachable": reachable,
    }


# ---------------------------------------------------------------------------
# Rotorcraft case F: banked turn performance (turning-flight momentum theory)
# ---------------------------------------------------------------------------
# T = n W; the turning inflow n W = 2 rho A v_i sqrt(V^2 + v_i^2) is solved
# by a FIXED-COUNT bisection (BISECT_ITER = 120) on [0, sqrt(nW/(2 rho A))];
# P_i = k n W v_i; P_prof = (1/8) rho sigma Cd0 A Vtip^3; P_par = 0.5 rho V^3
# f; sustained load factor inverts the strictly increasing total power by
# bisection on [1, N_CEILING]; bank = acos(1/n), rate = g sqrt(n^2-1)/V,
# radius = V^2 / (g sqrt(n^2 - 1)).
CD0_DEFAULT = 0.012
N_CEILING = 10.0
BISECT_ITER = 120


def _bisect_root(low, high, excess):
    """Fixed-count bisection root of a strictly increasing excess function."""
    lo, hi = low, high
    for _ in range(BISECT_ITER):
        mid = 0.5 * (lo + hi)
        if excess(mid) < 0.0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def thrust_for_turn(load_factor, weight):
    """Turn rotor thrust T = n * W (N)."""
    if load_factor < 1.0:
        raise ValueError("load_factor must be >= 1.0 for a level turn")
    if weight <= 0:
        raise ValueError("weight must be positive (N)")
    return load_factor * weight


def generalized_induced_velocity(load_factor, weight, area, rho, speed):
    """Turning induced velocity v_i (m/s): fixed-count bisection root of
    2 rho A v_i sqrt(V^2 + v_i^2) = n W on v_i >= 0."""
    if load_factor < 1.0:
        raise ValueError("load_factor must be >= 1.0 for a level turn")
    if weight <= 0:
        raise ValueError("weight must be positive (N)")
    if area <= 0:
        raise ValueError("area must be positive (m2)")
    if rho <= 0:
        raise ValueError("rho must be positive (kg/m3)")
    if speed < 0:
        raise ValueError("speed must be non-negative (m/s)")
    target = load_factor * weight
    hi = math.sqrt(target / (2.0 * rho * area))

    def _excess(v):
        return (2.0 * rho * area * v
                * math.sqrt(speed * speed + v * v)) - target

    return _bisect_root(0.0, hi, _excess)


def induced_power(load_factor, weight, induced_velocity, k=K_DEFAULT):
    """Turn induced power P_i = k n W v_i (W)."""
    if k <= 0:
        raise ValueError("induced power factor k must be positive")
    if load_factor < 1.0:
        raise ValueError("load_factor must be >= 1.0 for a level turn")
    if weight <= 0:
        raise ValueError("weight must be positive (N)")
    if induced_velocity < 0:
        raise ValueError("induced velocity must be non-negative (m/s)")
    return k * load_factor * weight * induced_velocity


def profile_power(rho, area, solidity, drag_coefficient=CD0_DEFAULT,
                  tip_speed=DEFAULT_TIP_SPEED):
    """Rotor profile power (1/8) rho sigma Cd0 A Vtip^3 (W)."""
    if rho <= 0:
        raise ValueError("rho must be positive (kg/m3)")
    if area <= 0:
        raise ValueError("area must be positive (m2)")
    if solidity <= 0:
        raise ValueError("solidity must be positive")
    if drag_coefficient <= 0:
        raise ValueError("drag coefficient must be positive")
    if tip_speed <= 0:
        raise ValueError("tip speed must be positive (m/s)")
    return (1.0 / 8.0) * rho * solidity * drag_coefficient * area \
        * tip_speed ** 3


def parasite_power(rho, speed, flat_plate_area):
    """Parasite power P_par = 0.5 rho V^3 f (W)."""
    if rho <= 0:
        raise ValueError("rho must be positive (kg/m3)")
    if speed < 0:
        raise ValueError("speed must be non-negative (m/s)")
    if flat_plate_area < 0:
        raise ValueError("flat-plate area must be non-negative (m2)")
    return 0.5 * rho * speed ** 3 * flat_plate_area


def turn_power(load_factor, weight, area, rho, speed, solidity,
               drag_coefficient, tip_speed, flat_plate_area, k=K_DEFAULT):
    """Turn power breakdown dict (load_factor, thrust, induced_velocity,
    induced_power, profile_power, parasite_power, total_power)."""
    thrust = thrust_for_turn(load_factor, weight)
    v_i = generalized_induced_velocity(load_factor, weight, area, rho,
                                       speed)
    p_ind = induced_power(load_factor, weight, v_i, k)
    p_prof = profile_power(rho, area, solidity, drag_coefficient,
                           tip_speed)
    p_par = parasite_power(rho, speed, flat_plate_area)
    return {
        "load_factor": load_factor,
        "thrust": thrust,
        "induced_velocity": v_i,
        "induced_power": p_ind,
        "profile_power": p_prof,
        "parasite_power": p_par,
        "total_power": p_ind + p_prof + p_par,
    }


def sustained_load_factor(available_power, weight, area, rho, speed,
                          solidity, drag_coefficient, tip_speed,
                          flat_plate_area, k=K_DEFAULT, ceiling=N_CEILING):
    """Power-sustained load factor of the banked turn (fixed-count
    bisection on [1, ceiling]); note 'power-limited' or
    'power-excess above ceiling'."""
    if available_power <= 0:
        raise ValueError("available power must be positive (W)")
    if ceiling <= 1.0:
        raise ValueError("ceiling must be above 1.0")
    p_prof = profile_power(rho, area, solidity, drag_coefficient,
                           tip_speed)
    p_par = parasite_power(rho, speed, flat_plate_area)

    def _turn_total(n):
        v_i = generalized_induced_velocity(n, weight, area, rho, speed)
        return induced_power(n, weight, v_i, k) + p_prof + p_par

    level_total = _turn_total(1.0)
    if level_total > available_power:
        raise ValueError("available power cannot sustain level flight at "
                         "this speed")
    ceiling_total = _turn_total(ceiling)
    if ceiling_total < available_power:
        n_s = ceiling
        note = "power-excess above ceiling"
    else:
        n_s = _bisect_root(1.0, ceiling,
                           lambda n: _turn_total(n) - available_power)
        note = "power-limited"
    v_i = generalized_induced_velocity(n_s, weight, area, rho, speed)
    p_ind = induced_power(n_s, weight, v_i, k)
    return {
        "load_factor": n_s,
        "bank_angle": math.acos(1.0 / n_s),
        "induced_velocity": v_i,
        "induced_power": p_ind,
        "profile_power": p_prof,
        "parasite_power": p_par,
        "total_power": p_ind + p_prof + p_par,
        "note": note,
    }


def bank_from_load_factor(load_factor):
    """Bank angle of the level turn acos(1 / n) in rad."""
    if load_factor < 1.0:
        raise ValueError("load_factor must be >= 1.0 for a level turn")
    return math.acos(1.0 / load_factor)


def turn_rate(load_factor, speed):
    """Turn rate omega = G0 sqrt(n^2 - 1) / V in rad/s."""
    if load_factor < 1.0:
        raise ValueError("load_factor must be >= 1.0 for a level turn")
    if speed <= 0:
        raise ValueError("speed must be positive (m/s)")
    return G0 * math.sqrt(load_factor ** 2 - 1.0) / speed


def turn_radius(load_factor, speed):
    """Turn radius R = V^2 / (G0 sqrt(n^2 - 1)) in m."""
    if load_factor < 1.0:
        raise ValueError("load_factor must be >= 1.0 for a level turn")
    if speed <= 0:
        raise ValueError("speed must be positive (m/s)")
    return speed ** 2 / (G0 * math.sqrt(load_factor ** 2 - 1.0))


def max_bank_from_power(available_power, weight, area, rho, speed,
                        solidity, drag_coefficient, tip_speed,
                        flat_plate_area, k=K_DEFAULT, ceiling=N_CEILING):
    """Maximum bank angle (rad) from one sustained_load_factor solve."""
    result = sustained_load_factor(available_power, weight, area, rho,
                                   speed, solidity, drag_coefficient,
                                   tip_speed, flat_plate_area, k, ceiling)
    return result["bank_angle"]


# ---------------------------------------------------------------------------
# Rotorcraft case G: range and endurance fuel closure
# ---------------------------------------------------------------------------
# Hover power P = k_h W^1.5 with k_h = 1 / (FM sqrt(2 rho A)); weight decay
# dW/dt = -g0 c P integrates to hover endurance t = (2/(g0 c k_h)) *
# (1/sqrt(W1) - 1/sqrt(W0)) with W1 = W0 - g0 m_f; cruise closure scales the
# reference power with (W_avg / W_ref)^1.5: R = V (W0 - W1)/(g0 c P_avg),
# E = (W0 - W1)/(g0 c P_avg); specific range SR = V / (g0 c P); best-range
# speed maximizes SR, best-endurance speed minimizes P over the curve.
C_SPEC_DEFAULT = 1.0e-7   # kg/(s W), about 0.36 kg/kWh
FM_DEFAULT = 0.75         # rotor figure of merit


def hover_power_constant(radius, rho=RHO_SL, figure_of_merit=FM_DEFAULT):
    """Hover power law constant k_h = 1 / (FM sqrt(2 rho A))."""
    if radius <= 0:
        raise ValueError("radius must be positive")
    if rho <= 0:
        raise ValueError("density must be positive")
    if figure_of_merit <= 0 or figure_of_merit > 1:
        raise ValueError("figure of merit must be in (0, 1]")
    return 1.0 / (figure_of_merit * math.sqrt(2.0 * rho * disk_area(radius)))


def hover_power(weight_n, radius, rho=RHO_SL, figure_of_merit=FM_DEFAULT):
    """Hover power P = k_h W^1.5 (W) at a given rotorcraft weight."""
    if weight_n <= 0:
        raise ValueError("weight must be positive")
    k_h = hover_power_constant(radius, rho, figure_of_merit)
    return k_h * weight_n ** 1.5


def hover_endurance(weight_initial_n, fuel_mass_kg, radius, rho=RHO_SL,
                    figure_of_merit=FM_DEFAULT, c_specific=C_SPEC_DEFAULT,
                    g0=G0):
    """Hover endurance (s) from the exact weight-decay integral."""
    if weight_initial_n <= 0:
        raise ValueError("initial weight must be positive")
    if fuel_mass_kg < 0:
        raise ValueError("fuel mass must not be negative")
    if c_specific <= 0:
        raise ValueError("specific fuel consumption must be positive")
    w0 = weight_initial_n
    w1 = w0 - g0 * fuel_mass_kg
    if w1 <= 0:
        raise ValueError("fuel mass must leave a positive final weight")
    if fuel_mass_kg == 0.0:
        return 0.0
    k_h = hover_power_constant(radius, rho, figure_of_merit)
    return (2.0 / (g0 * c_specific * k_h)) * (1.0 / math.sqrt(w1)
                                              - 1.0 / math.sqrt(w0))


def fuel_flow(weight_n, radius, rho=RHO_SL, figure_of_merit=FM_DEFAULT,
              c_specific=C_SPEC_DEFAULT):
    """Fuel flow mdot = c * P(weight) in kg/s."""
    return c_specific * hover_power(weight_n, radius, rho, figure_of_merit)


def specific_range(v_ms, power_w, c_specific=C_SPEC_DEFAULT, g0=G0):
    """Specific range V / (g0 c P), m of cruise range per kg of fuel."""
    if v_ms <= 0:
        raise ValueError("speed must be positive")
    if power_w <= 0:
        raise ValueError("power must be positive")
    if c_specific <= 0:
        raise ValueError("specific fuel consumption must be positive")
    return v_ms / (g0 * c_specific * power_w)


def _validate_power_curve(power_curve):
    if not power_curve:
        raise ValueError("power curve must not be empty")
    for v_ms, power_w in power_curve:
        if v_ms <= 0 or power_w <= 0:
            raise ValueError("power curve pairs must have positive speed "
                             "and power")


def best_range_speed(power_curve):
    """Best-range speed (m/s): maximizes specific range over the curve."""
    _validate_power_curve(power_curve)
    return max(power_curve,
               key=lambda pair: specific_range(pair[0], pair[1]))[0]


def best_endurance_speed(power_curve):
    """Best-endurance speed (m/s): minimizes power over the curve."""
    _validate_power_curve(power_curve)
    return min(power_curve, key=lambda pair: pair[1])[0]


def _average_power(power_at_ref_w, weight_initial_n, fuel_mass_kg,
                   weight_ref_n, g0):
    """Average cruise power P_avg = P_ref (W_avg / W_ref)^1.5 (W)."""
    if power_at_ref_w <= 0:
        raise ValueError("reference power must be positive")
    if weight_ref_n <= 0:
        raise ValueError("reference weight must be positive")
    w0 = weight_initial_n
    w1 = w0 - g0 * fuel_mass_kg
    if w1 <= 0:
        raise ValueError("fuel mass must leave a positive final weight")
    w_avg = (w0 + w1) / 2.0
    return power_at_ref_w * (w_avg / weight_ref_n) ** 1.5


def cruise_range(v_ms, weight_initial_n, fuel_mass_kg, power_at_ref_w,
                 weight_ref_n, c_specific=C_SPEC_DEFAULT, g0=G0):
    """Cruise range R = V (W0 - W1) / (g0 c P_avg) in m at speed V."""
    if v_ms <= 0:
        raise ValueError("speed must be positive")
    if weight_initial_n <= 0:
        raise ValueError("initial weight must be positive")
    if fuel_mass_kg < 0:
        raise ValueError("fuel mass must not be negative")
    if c_specific <= 0:
        raise ValueError("specific fuel consumption must be positive")
    p_avg = _average_power(power_at_ref_w, weight_initial_n, fuel_mass_kg,
                           weight_ref_n, g0)
    w0 = weight_initial_n
    w1 = w0 - g0 * fuel_mass_kg
    return v_ms * (w0 - w1) / (g0 * c_specific * p_avg)


def cruise_endurance(v_ms, weight_initial_n, fuel_mass_kg, power_at_ref_w,
                     weight_ref_n, c_specific=C_SPEC_DEFAULT, g0=G0):
    """Cruise endurance E = (W0 - W1) / (g0 c P_avg) in s."""
    if v_ms <= 0:
        raise ValueError("speed must be positive")
    if weight_initial_n <= 0:
        raise ValueError("initial weight must be positive")
    if fuel_mass_kg < 0:
        raise ValueError("fuel mass must not be negative")
    if c_specific <= 0:
        raise ValueError("specific fuel consumption must be positive")
    p_avg = _average_power(power_at_ref_w, weight_initial_n, fuel_mass_kg,
                           weight_ref_n, g0)
    w0 = weight_initial_n
    w1 = w0 - g0 * fuel_mass_kg
    return (w0 - w1) / (g0 * c_specific * p_avg)


# ---------------------------------------------------------------------------
# Performance analysis report builder
# ---------------------------------------------------------------------------


@dataclass
class PerformanceItem:
    """Project facts the role needs to build the aircraft performance
    analysis report. Each case set mirrors the reference case of one bound
    AeroSkills leaf (real worked inputs; outputs reproduced by this core).
    """
    workbook_name: str
    description: str = ""
    certification_basis: str = "FAR-25 (airplane cases) / FAR-29 (rotorcraft cases)"
    airframe: str = ""
    # --- Airplane A-1: engine-out balanced field length case ---
    bfl_thrust_all_n: float = 0.0
    bfl_engine_count: int = 2
    bfl_weight_n: float = 0.0
    bfl_mu_roll: float = 0.03
    bfl_mu_brake: float = 0.45
    bfl_v_lof_ms: float = 0.0
    bfl_gradient: float = 0.0
    bfl_obstacle_m: float = OBSTACLE_HEIGHT_M
    bfl_reaction_s: float = REACTION_TIME_S
    bfl_rotation_s: float = ROTATION_TIME_S
    # --- Airplane A-2: turboprop cruise range case ---
    pr_eta_p: float = 0.0
    pr_psfc_lb_per_hp_h: float = 0.0
    pr_ld: float = 0.0
    pr_m0_kg: float = 0.0
    pr_m1_kg: float = 0.0
    # --- Rotorcraft H-2: main rotor sizing case ---
    sz_mass_kg: float = 0.0
    sz_dl_max_pa: float = 0.0
    sz_ct_over_sigma: float = 0.0
    sz_blade_count: int = 4
    sz_tip_speed_ms: float = 0.0
    sz_rho: float = RHO_SL
    sz_speed_of_sound: float = A0_SL
    # --- Rotorcraft blade flap dynamics case ---
    bf_blade_mass_kg: float = 0.0
    bf_radius_m: float = 0.0
    bf_chord_m: float = 0.0
    bf_theta0_rad: float = 0.0
    bf_inflow_ratio: float = 0.0
    bf_hinge_offset: float = 0.0
    bf_lift_slope: float = A_LIFT_DEFAULT
    bf_rho: float = RHO_SL
    # --- Rotorcraft H-1: lead-lag dynamics case ---
    ll_hinge_offset: float = 0.05
    ll_omega_rad_s: float = 0.0
    ll_airframe_hz: float = 0.0
    ll_margin: float = 0.20
    ll_alt_airframe_hz: float = 0.0   # sensitivity airframe frequency
    # --- Rotorcraft H-1: hover in ground effect case ---
    ge_mass_kg: float = 0.0
    ge_radius_m: float = 0.0
    ge_height_m: float = 0.0
    ge_rho: float = RHO_SL
    ge_solidity: float = DEFAULT_SOLIDITY
    ge_cd0: float = DEFAULT_DRAG_COEFFICIENT
    ge_tip_speed_ms: float = DEFAULT_TIP_SPEED
    ge_k: float = K_DEFAULT
    ge_available_power_w: float = 0.0
    # --- Rotorcraft H-1: axial descent flow states case ---
    ad_mass_kg: float = 0.0
    ad_radius_m: float = 0.0
    ad_profile_power_w: float = 0.0
    ad_rho: float = RHO_SL
    ad_k: float = K_DEFAULT
    ad_rotor_speed_rad_s: float = 44.0
    ad_descent_cases: list = field(default_factory=list)  # Vd values (m/s)
    # --- Rotorcraft H-1: banked turn performance case ---
    tp_mass_kg: float = 0.0
    tp_radius_m: float = 0.0
    tp_rho: float = RHO_SL
    tp_solidity: float = DEFAULT_SOLIDITY
    tp_cd0: float = CD0_DEFAULT
    tp_tip_speed_ms: float = DEFAULT_TIP_SPEED
    tp_flat_plate_m2: float = 0.0
    tp_k: float = K_DEFAULT
    tp_speed_ms: float = 0.0
    tp_load_factor: float = 2.0
    tp_available_power_w: float = 0.0
    tp_alt_power_w: float = 0.0        # sensitivity: 450 kW @ 40 m/s case
    tp_alt_speed_ms: float = 40.0
    # --- Rotorcraft H-4: range and endurance fuel closure case ---
    re_weight0_n: float = 0.0
    re_fuel_kg: float = 0.0
    re_radius_m: float = 0.0
    re_rho: float = RHO_SL
    re_figure_of_merit: float = FM_DEFAULT
    re_c_specific: float = C_SPEC_DEFAULT
    re_power_curve: list = field(default_factory=list)  # [(V m/s, P W)]
    re_range_speed_ms: float = 0.0
    re_range_power_w: float = 0.0
    re_endurance_speed_ms: float = 0.0
    re_endurance_power_w: float = 0.0
    supporting_note: str = ""


def _fmt(x, nd=6) -> str:
    if isinstance(x, float):
        if x == 0.0:
            return "0"
        if 1e-4 <= abs(x) < 1e7:
            return "%.*g" % (nd, x)
        return "%.3e" % x
    return str(x)


def _hms(seconds) -> str:
    """Hours string for an endurance in seconds."""
    return "%.2f h" % (seconds / 3600.0)


def _rad_to_deg(rad) -> float:
    return rad * 180.0 / PI


def build_performance_report(item: PerformanceItem) -> dict:
    """Build the complete Aircraft Performance Analysis content model.

    Each bound leaf's section is computed by the same formulas the leaf
    logic encodes; the numbers are REAL outputs of this engine for the
    reference cases carried by the item.
    """
    # --- Section 2: balanced field length (Airplane A-1) ---
    v1 = balanced_v1(item.bfl_thrust_all_n, item.bfl_engine_count,
                     item.bfl_weight_n, item.bfl_mu_roll, item.bfl_mu_brake,
                     item.bfl_v_lof_ms, item.bfl_gradient,
                     item.bfl_reaction_s, item.bfl_obstacle_m,
                     item.bfl_rotation_s)
    bfl_m = balanced_field_length(v1, item.bfl_thrust_all_n,
                                  item.bfl_engine_count, item.bfl_weight_n,
                                  item.bfl_mu_roll, item.bfl_mu_brake,
                                  item.bfl_v_lof_ms, item.bfl_gradient,
                                  item.bfl_reaction_s, item.bfl_obstacle_m,
                                  item.bfl_rotation_s)
    agd = accelerate_go_distance(v1, item.bfl_thrust_all_n,
                                 item.bfl_engine_count, item.bfl_weight_n,
                                 item.bfl_mu_roll, item.bfl_v_lof_ms,
                                 item.bfl_gradient, item.bfl_obstacle_m,
                                 item.bfl_rotation_s)
    t_oei = oei_thrust(item.bfl_thrust_all_n, item.bfl_engine_count)
    a_all = ground_acceleration(item.bfl_thrust_all_n, item.bfl_weight_n,
                                item.bfl_mu_roll)
    a_oei = ground_acceleration(t_oei, item.bfl_weight_n, item.bfl_mu_roll)
    a_brake = braking_deceleration(item.bfl_mu_brake)
    asd_0 = accelerate_stop_distance(0.0, item.bfl_thrust_all_n,
                                     item.bfl_weight_n, item.bfl_mu_roll,
                                     item.bfl_mu_brake)
    agd_0 = accelerate_go_distance(0.0, item.bfl_thrust_all_n,
                                   item.bfl_engine_count, item.bfl_weight_n,
                                   item.bfl_mu_roll, item.bfl_v_lof_ms,
                                   item.bfl_gradient)
    asd_vlof = accelerate_stop_distance(item.bfl_v_lof_ms,
                                        item.bfl_thrust_all_n,
                                        item.bfl_weight_n, item.bfl_mu_roll,
                                        item.bfl_mu_brake)
    agd_vlof = accelerate_go_distance(item.bfl_v_lof_ms,
                                      item.bfl_thrust_all_n,
                                      item.bfl_engine_count,
                                      item.bfl_weight_n, item.bfl_mu_roll,
                                      item.bfl_v_lof_ms, item.bfl_gradient)
    bfl = {
        "aircraft": "A-1 twin-engine transport airplane",
        "thrust_all_N": item.bfl_thrust_all_n,
        "engine_count": item.bfl_engine_count,
        "weight_N": item.bfl_weight_n,
        "mu_roll": item.bfl_mu_roll,
        "mu_brake": item.bfl_mu_brake,
        "reaction_s": item.bfl_reaction_s,
        "rotation_s": item.bfl_rotation_s,
        "oei_thrust_N": t_oei,
        "a_all_m_s2": a_all,
        "a_oei_m_s2": a_oei,
        "a_brake_m_s2": a_brake,
        "air_segment_m": item.bfl_obstacle_m / item.bfl_gradient,
        "v1_ms": v1,
        "v1_over_vlof": v1 / item.bfl_v_lof_ms,
        "balanced_field_length_m": bfl_m,
        "asd_at_v1_m": bfl_m,
        "agd_at_v1_m": agd,
        "asd_0_m": asd_0,
        "agd_0_m": agd_0,
        "asd_vlof_m": asd_vlof,
        "agd_vlof_m": agd_vlof,
        "balance_delta_m": abs(bfl_m - agd),
        "v_lof_ms": item.bfl_v_lof_ms,
        "gradient": item.bfl_gradient,
        "obstacle_m": item.bfl_obstacle_m,
    }

    # --- Section 3: turboprop cruise range (Airplane A-2) ---
    psfc_si = psfc_lb_per_hp_h_to_kg_per_w_s(item.pr_psfc_lb_per_hp_h)
    pr_m = propeller_range(item.pr_eta_p, psfc_si, item.pr_ld,
                           item.pr_m0_kg, item.pr_m1_kg)
    pr_km = pr_m / 1000.0
    propeller = {
        "aircraft": "A-2 turboprop transport airplane",
        "eta_p": item.pr_eta_p,
        "psfc_lb_per_hp_h": item.pr_psfc_lb_per_hp_h,
        "psfc_kg_per_w_s": psfc_si,
        "ld": item.pr_ld,
        "m0_kg": item.pr_m0_kg,
        "m1_kg": item.pr_m1_kg,
        "mass_ratio": item.pr_m0_kg / item.pr_m1_kg,
        "range_m": pr_m,
        "range_km": pr_km,
    }

    # --- Section 4: main rotor sizing (Rotorcraft H-2) ---
    sz_thrust = item.sz_mass_kg * G0
    sz_area, sz_radius = disk_area_and_radius(sz_thrust, item.sz_dl_max_pa)
    sz_ct = hover_thrust_coefficient(sz_thrust, item.sz_rho, sz_radius,
                                     item.sz_tip_speed_ms)
    sz_sigma = solidity_closure(sz_ct, item.sz_ct_over_sigma)
    sz_blade_area, sz_chord = blade_area_chord(sz_sigma, sz_area,
                                               item.sz_blade_count,
                                               sz_radius)
    sz_mach = tip_mach(item.sz_tip_speed_ms, item.sz_speed_of_sound)
    sizing = {
        "aircraft": "H-2 medium helicopter (takeoff sizing case)",
        "mass_kg": item.sz_mass_kg,
        "dl_max_pa": item.sz_dl_max_pa,
        "ct_over_sigma_design": item.sz_ct_over_sigma,
        "blade_count": item.sz_blade_count,
        "tip_speed_ms": item.sz_tip_speed_ms,
        "thrust_N": sz_thrust,
        "disk_area_m2": sz_area,
        "disk_radius_m": sz_radius,
        "achieved_disk_loading_pa": sz_thrust / sz_area,
        "thrust_coefficient": sz_ct,
        "solidity": sz_sigma,
        "ct_over_sigma_check": sz_ct / sz_sigma,
        "blade_area_m2": sz_blade_area,
        "blade_chord_m": sz_chord,
        "blade_aspect_ratio": sz_radius / sz_chord,
        "tip_mach": sz_mach,
        "solidity_identity": (item.sz_blade_count * sz_chord * sz_radius
                              / sz_area),
    }

    # --- Section 5: blade flap dynamics (blade reference case) ---
    flap = blade_flapping_summary(item.bf_blade_mass_kg, item.bf_radius_m,
                                  item.bf_chord_m, item.bf_theta0_rad,
                                  item.bf_inflow_ratio, item.bf_hinge_offset,
                                  item.bf_lift_slope, item.bf_rho)
    flap["aircraft"] = "H-3 medium helicopter (blade-level case)"
    flap["blade_mass_kg"] = item.bf_blade_mass_kg
    flap["radius_m"] = item.bf_radius_m
    flap["chord_m"] = item.bf_chord_m
    flap["theta0_rad"] = item.bf_theta0_rad
    flap["inflow_ratio"] = item.bf_inflow_ratio
    flap["hinge_offset"] = item.bf_hinge_offset
    flap["lift_slope"] = item.bf_lift_slope
    flap["rho"] = item.bf_rho

    # --- Section 6: lead-lag dynamics (Rotorcraft H-1) ---
    lag = lead_lag_summary(item.ll_hinge_offset, item.ll_omega_rad_s,
                           item.ll_airframe_hz, item.ll_margin)
    lag["aircraft"] = "H-1 light helicopter"
    lag["hinge_offset"] = item.ll_hinge_offset
    lag["airframe_frequency_hz"] = item.ll_airframe_hz
    lag_alt = None
    if item.ll_alt_airframe_hz > 0.0:
        lag_alt = lead_lag_summary(item.ll_hinge_offset,
                                   item.ll_omega_rad_s,
                                   item.ll_alt_airframe_hz, item.ll_margin)
        lag_alt["airframe_frequency_hz"] = item.ll_alt_airframe_hz

    # --- Section 7: hover in ground effect (Rotorcraft H-1) ---
    ge = hover_ground_effect(item.ge_mass_kg, item.ge_radius_m,
                             item.ge_height_m, item.ge_rho, item.ge_solidity,
                             item.ge_cd0, item.ge_tip_speed_ms, item.ge_k,
                             item.ge_available_power_w)
    ge["mass_kg"] = item.ge_mass_kg
    ge["radius_m"] = item.ge_radius_m
    ge["height_m"] = item.ge_height_m
    ge["solidity"] = item.ge_solidity
    ge["cd0"] = item.ge_cd0
    ge["tip_speed_ms"] = item.ge_tip_speed_ms
    ge["k"] = item.ge_k
    ge["available_power_W"] = item.ge_available_power_w

    # --- Section 8: axial descent flow states (Rotorcraft H-1) ---
    ad_thrust = item.ad_mass_kg * G0
    ad_area = PI * item.ad_radius_m ** 2
    ad_vh = math.sqrt(ad_thrust / (2.0 * item.ad_rho * ad_area))
    ad_rows = []
    for vd in item.ad_descent_cases:
        summary = descent_summary(ad_thrust, item.ad_radius_m,
                                  item.ad_profile_power_w, vd, item.ad_rho,
                                  item.ad_k, item.ad_rotor_speed_rad_s)
        ad_rows.append({"vd_ms": vd, **summary})
    ad_reversal = torque_reversal_condition(item.ad_profile_power_w,
                                            ad_thrust, item.ad_k, ad_vh)
    descent = {
        "aircraft": "H-1 light helicopter",
        "mass_kg": item.ad_mass_kg,
        "radius_m": item.ad_radius_m,
        "k": item.ad_k,
        "thrust_N": ad_thrust,
        "disk_area_m2": ad_area,
        "v_h_ms": ad_vh,
        "band_limits": (0.0, 2.0 * ad_vh),
        "profile_power_W": item.ad_profile_power_w,
        "rotor_speed_rad_s": item.ad_rotor_speed_rad_s,
        "cases": ad_rows,
        "torque_reversal": ad_reversal,
    }

    # --- Section 9: banked turn performance (Rotorcraft H-1) ---
    tp_weight = item.tp_mass_kg * G0
    tp_area = PI * item.tp_radius_m ** 2
    tp_breakdown = turn_power(item.tp_load_factor, tp_weight, tp_area,
                              item.tp_rho, item.tp_speed_ms,
                              item.tp_solidity, item.tp_cd0,
                              item.tp_tip_speed_ms, item.tp_flat_plate_m2,
                              item.tp_k)
    tp_level = turn_power(1.0, tp_weight, tp_area, item.tp_rho,
                          item.tp_speed_ms, item.tp_solidity, item.tp_cd0,
                          item.tp_tip_speed_ms, item.tp_flat_plate_m2,
                          item.tp_k)
    tp_sustained = sustained_load_factor(item.tp_available_power_w,
                                         tp_weight, tp_area, item.tp_rho,
                                         item.tp_speed_ms, item.tp_solidity,
                                         item.tp_cd0, item.tp_tip_speed_ms,
                                         item.tp_flat_plate_m2, item.tp_k)
    tp_alt = None
    if item.tp_alt_power_w > 0.0:
        tp_alt = sustained_load_factor(item.tp_alt_power_w, tp_weight,
                                       tp_area, item.tp_rho,
                                       item.tp_alt_speed_ms,
                                       item.tp_solidity, item.tp_cd0,
                                       item.tp_tip_speed_ms,
                                       item.tp_flat_plate_m2, item.tp_k)
        tp_alt["speed_ms"] = item.tp_alt_speed_ms
    turn = {
        "aircraft": "H-1 light helicopter",
        "mass_kg": item.tp_mass_kg,
        "radius_m": item.tp_radius_m,
        "rho": item.tp_rho,
        "solidity": item.tp_solidity,
        "cd0": item.tp_cd0,
        "tip_speed_ms": item.tp_tip_speed_ms,
        "flat_plate_m2": item.tp_flat_plate_m2,
        "k": item.tp_k,
        "weight_N": tp_weight,
        "disk_area_m2": tp_area,
        "v_h_ref_ms": math.sqrt(tp_weight / (2.0 * item.tp_rho * tp_area)),
        "speed_ms": item.tp_speed_ms,
        "load_factor": item.tp_load_factor,
        "breakdown": tp_breakdown,
        "level_total_power_W": tp_level["total_power"],
        "bank_deg": _rad_to_deg(bank_from_load_factor(item.tp_load_factor)),
        "rate_rad_s": turn_rate(item.tp_load_factor, item.tp_speed_ms),
        "turn_radius_m": turn_radius(item.tp_load_factor, item.tp_speed_ms),
        "sustained": tp_sustained,
        "sustained_bank_deg": _rad_to_deg(tp_sustained["bank_angle"]),
        "sustained_rate_rad_s": turn_rate(tp_sustained["load_factor"],
                                          item.tp_speed_ms),
        "sustained_radius_m": turn_radius(tp_sustained["load_factor"],
                                          item.tp_speed_ms),
        "alt_power_case": tp_alt,
        "available_power_W": item.tp_available_power_w,
    }

    # --- Section 10: range and endurance fuel closure (Rotorcraft H-4) ---
    re_area = disk_area(item.re_radius_m)
    re_kh = hover_power_constant(item.re_radius_m, item.re_rho,
                                 item.re_figure_of_merit)
    re_hover_p = hover_power(item.re_weight0_n, item.re_radius_m,
                             item.re_rho, item.re_figure_of_merit)
    re_ff = fuel_flow(item.re_weight0_n, item.re_radius_m, item.re_rho,
                      item.re_figure_of_merit, item.re_c_specific)
    re_w1 = item.re_weight0_n - G0 * item.re_fuel_kg
    re_hover_t = hover_endurance(item.re_weight0_n, item.re_fuel_kg,
                                 item.re_radius_m, item.re_rho,
                                 item.re_figure_of_merit,
                                 item.re_c_specific)
    re_brs = best_range_speed(item.re_power_curve)
    re_bes = best_endurance_speed(item.re_power_curve)
    re_sr = specific_range(item.re_endurance_speed_ms,
                           item.re_endurance_power_w, item.re_c_specific)
    re_range = cruise_range(item.re_range_speed_ms, item.re_weight0_n,
                            item.re_fuel_kg, item.re_range_power_w,
                            item.re_weight0_n, item.re_c_specific)
    re_endurance = cruise_endurance(item.re_endurance_speed_ms,
                                    item.re_weight0_n, item.re_fuel_kg,
                                    item.re_endurance_power_w,
                                    item.re_weight0_n, item.re_c_specific)
    fuel = {
        "aircraft": "H-4 six-tonne class helicopter",
        "radius_m": item.re_radius_m,
        "figure_of_merit": item.re_figure_of_merit,
        "c_specific": item.re_c_specific,
        "weight0_N": item.re_weight0_n,
        "fuel_mass_kg": item.re_fuel_kg,
        "weight1_N": re_w1,
        "disk_area_m2": re_area,
        "hover_power_constant": re_kh,
        "hover_power_W": re_hover_p,
        "fuel_flow_kg_s": re_ff,
        "hover_endurance_s": re_hover_t,
        "hover_endurance_h": re_hover_t / 3600.0,
        "power_curve": [{"speed_ms": v, "power_W": p}
                        for v, p in item.re_power_curve],
        "best_range_speed_ms": re_brs,
        "best_endurance_speed_ms": re_bes,
        "specific_range_m_per_kg": re_sr,
        "cruise_range_m": re_range,
        "cruise_range_km": re_range / 1000.0,
        "cruise_endurance_s": re_endurance,
        "cruise_endurance_h": re_endurance / 3600.0,
        "range_speed_ms": item.re_range_speed_ms,
        "endurance_speed_ms": item.re_endurance_speed_ms,
    }

    return {
        "document_type": "Aircraft Performance Analysis Report",
        "status": "draft-for-review",
        "item": item.workbook_name,
        "item_description": item.description,
        "airframe": item.airframe,
        "certification_basis": item.certification_basis,
        "airplane_cases": ["A-1 balanced field length",
                           "A-2 turboprop cruise range"],
        "rotorcraft_cases": ["H-1 lead-lag / hover IGE / axial descent / "
                             "banked turn",
                             "H-2 main rotor sizing",
                             "H-3 blade flap dynamics",
                             "H-4 range and endurance"],
        "bfl": bfl,
        "propeller": propeller,
        "sizing": sizing,
        "flap": flap,
        "leadlag": lag,
        "leadlag_alt": lag_alt,
        "hover_ige": ge,
        "descent": descent,
        "turn": turn,
        "fuel": fuel,
        "supporting_note": item.supporting_note,
        "generated": _today(),
    }


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


def render_report_markdown(model: dict) -> str:
    """Render the performance content model as the deliverable markdown."""
    L = []
    A = L.append
    A("# Aircraft Performance Analysis Report")
    A("")
    A("**Workbook:** %s" % model["item"])
    if model.get("airframe"):
        A("**Fleet analysed:** %s" % model["airframe"])
    A("**Certification basis:** %s" % model["certification_basis"])
    A("**Status:** %s" % model["status"])
    A("")
    A("## 1. Scope and aircraft register")
    A("")
    A(model["item_description"])
    if model.get("supporting_note"):
        A("")
        A(model["supporting_note"])
    A("")
    A("| Case | Aircraft | Bound leaf | Computes |")
    A("|---|---|---|---|")
    A("| A-1 | twin-engine transport airplane | flight-mechanics/performance/"
      "balanced-field-length | engine-out balanced field length and V1 |")
    A("| A-2 | turboprop transport airplane | flight-mechanics/performance/"
      "propeller-range | propeller Breguet cruise range |")
    A("| H-1 | light helicopter (2200 kg, 5.0 m main rotor) | "
      "rotorcraft-lead-lag-dynamics, rotorcraft-hover-ground-effect, "
      "rotorcraft-axial-descent-flow-states, rotorcraft-turn-performance | "
      "lead-lag clearance, hover IGE, axial descent, banked turn |")
    A("| H-2 | medium helicopter (4500 kg takeoff) | "
      "rotorcraft-main-rotor-sizing | main rotor sizing |")
    A("| H-3 | medium helicopter (blade-level case) | "
      "rotorcraft-blade-flapping-dynamics | Lock number, coning, flap "
      "frequency |")
    A("| H-4 | six-tonne class helicopter | rotorcraft-range-endurance | "
      "hover endurance and cruise range/endurance closure |")
    A("")
    A("Airplane cases sit in the FAR-25 transport performance context; "
      "rotorcraft cases in the FAR-29 rotorcraft context. Every number "
      "below is computed by the role engine from the case inputs; each "
      "section cites the bound AeroSkills leaf whose logic the engine "
      "cross-checks against when the library is present.")
    A("")

    # --- Section 2: balanced field length ---
    b = model["bfl"]
    A("## 2. Airplane A-1: engine-out balanced field length and V1")
    A("")
    A("Case inputs: all-engine thrust %s N across %d engines, weight %s N, "
      "rolling friction %s, brake friction %s, lift-off speed %s m/s, "
      "engine-out climb gradient %s, obstacle height %s m (35 ft), "
      "reaction %s s, rotation %s s."
      % (_fmt(b["thrust_all_N"]), b["engine_count"], _fmt(b["weight_N"]),
         _fmt(b["mu_roll"]), _fmt(b["mu_brake"]), _fmt(b["v_lof_ms"]),
         _fmt(b["gradient"]), _fmt(b["obstacle_m"]), _fmt(b["reaction_s"]),
         _fmt(b["rotation_s"])))
    A("")
    A("| Quantity | Value |")
    A("|---|---|")
    A("| OEI thrust T_OEI (n-1)/n | %s N |" % _fmt(b["oei_thrust_N"]))
    A("| Ground acceleration, all engines | %s m/s2 |"
      % _fmt(b["a_all_m_s2"]))
    A("| Ground acceleration, engine out | %s m/s2 |" % _fmt(b["a_oei_m_s2"]))
    A("| Braking deceleration | %s m/s2 |" % _fmt(b["a_brake_m_s2"]))
    A("| Air segment over the obstacle | %s m |" % _fmt(b["air_segment_m"]))
    A("")
    A("**Balanced V1: %s m/s (%s of V_LOF).**"
      % (_fmt(b["v1_ms"]), _fmt(b["v1_over_vlof"])))
    A("")
    A("**Balanced field length: %s m** (ASD(V1) = AGD(V1) = %s m, "
      "balance delta %s m)."
      % (_fmt(b["balanced_field_length_m"]), _fmt(b["agd_at_v1_m"]),
         _fmt(b["balance_delta_m"])))
    A("")
    A("Bracket check (unique crossing inside [0, V_LOF]): ASD(0) = %s m vs "
      "AGD(0) = %s m; ASD(V_LOF) = %s m vs AGD(V_LOF) = %s m."
      % (_fmt(b["asd_0_m"]), _fmt(b["agd_0_m"]), _fmt(b["asd_vlof_m"]),
         _fmt(b["agd_vlof_m"])))
    A("")
    A("Bound leaf: flight-mechanics/performance/balanced-field-length "
      "(FAR-25.113-style engine-out field length; summary-not-copy).")
    A("")

    # --- Section 3: propeller range ---
    p = model["propeller"]
    A("## 3. Airplane A-2: turboprop cruise range (propeller Breguet)")
    A("")
    A("Case inputs: propeller efficiency %s, PSFC %s lb/(hp h), cruise "
      "L/D %s, cruise masses %s kg to %s kg."
      % (_fmt(p["eta_p"]), _fmt(p["psfc_lb_per_hp_h"]), _fmt(p["ld"]),
         _fmt(p["m0_kg"], 5), _fmt(p["m1_kg"], 5)))
    A("")
    A("| Quantity | Value |")
    A("|---|---|")
    A("| PSFC converted to SI | %s kg/(W s) |" % _fmt(p["psfc_kg_per_w_s"]))
    A("| Mass ratio m0/m1 | %s |" % _fmt(p["mass_ratio"]))
    A("| **Cruise range** | **%s m = %s km** |"
      % (_fmt(p["range_m"], 6), _fmt(p["range_km"], 5)))
    A("")
    A("R = (eta_p / (c_p * g0)) * (L/D) * ln(m0 / m1), the propeller "
      "branch of the Breguet range family (no cruise-speed term; the "
      "efficiency enters the numerator and the PSFC the denominator).")
    A("")
    A("Bound leaf: flight-mechanics/performance/propeller-range (FAR-25 "
      "cruise fuel-planning context; summary-not-copy).")
    A("")

    # --- Section 4: main rotor sizing ---
    s = model["sizing"]
    A("## 4. Rotorcraft H-2: main rotor sizing")
    A("")
    A("Case inputs: takeoff mass %s kg, main-rotor-disk-loading ceiling "
      "%s Pa, ct-over-sigma hover design point %s, blade count %d, rotor "
      "tip speed %s m/s."
      % (_fmt(s["mass_kg"]), _fmt(s["dl_max_pa"]),
         _fmt(s["ct_over_sigma_design"]), s["blade_count"],
         _fmt(s["tip_speed_ms"])))
    A("")
    A("| Quantity | Value |")
    A("|---|---|")
    A("| Weight-borne hover thrust | %s N |" % _fmt(s["thrust_N"]))
    A("| Disk area | %s m2 |" % _fmt(s["disk_area_m2"]))
    A("| Disk radius | %s m |" % _fmt(s["disk_radius_m"]))
    A("| Achieved disk loading | %s Pa (exactly the ceiling) |"
      % _fmt(s["achieved_disk_loading_pa"]))
    A("| Hover thrust coefficient CT | %s |" % _fmt(s["thrust_coefficient"]))
    A("| Rotor solidity sigma | %s |" % _fmt(s["solidity"]))
    A("| Blade area A_b | %s m2 |" % _fmt(s["blade_area_m2"]))
    A("| Blade chord c | %s m (R/c = %s) |"
      % (_fmt(s["blade_chord_m"]), _fmt(s["blade_aspect_ratio"])))
    A("| Rotor tip Mach | %s (subcritical at sea level) |"
      % _fmt(s["tip_mach"]))
    A("")
    A("Closure identities: CT = %s / (rho * Vtip^2) ceiling identity holds "
      "(CT/sigma = %s, solidity identity b*c*R/A = %s)."
      % (_fmt(s["thrust_coefficient"]), _fmt(s["ct_over_sigma_check"]),
         _fmt(s["solidity_identity"])))
    A("")
    A("Bound leaf: flight-mechanics/performance/rotorcraft-main-rotor-"
      "sizing (FAR-29 context; sizing only, no power).")
    A("")

    # --- Section 5: blade flap dynamics ---
    f = model["flap"]
    A("## 5. Rotorcraft H-3: main-rotor blade flap dynamics")
    A("")
    A("Case inputs: uniform blade mass %s kg, radius %s m, chord %s m, "
      "collective %s rad, uniform inflow ratio %s, flap hinge offset %s, "
      "lift-curve slope %s /rad, rho %s kg/m3."
      % (_fmt(f["blade_mass_kg"]), _fmt(f["radius_m"]), _fmt(f["chord_m"]),
         _fmt(f["theta0_rad"]), _fmt(f["inflow_ratio"]),
         _fmt(f["hinge_offset"]), _fmt(f["lift_slope"]), _fmt(f["rho"])))
    A("")
    A("| Quantity | Value |")
    A("|---|---|")
    A("| Flap inertia I_beta (uniform) | %s kg m2 |"
      % _fmt(f["flap_inertia_kg_m2"]))
    A("| **Lock number gamma** | **%s** (published band 5-12) |"
      % _fmt(f["lock_number"]))
    A("| Hover coning a0 | %s rad = %s deg (typical 3-8 deg) |"
      % (_fmt(f["coning_angle_rad"]), _fmt(f["coning_angle_deg"])))
    A("| Flap frequency ratio nu | %s per rev (1.02-1.08 band) |"
      % _fmt(f["flap_frequency_ratio"]))
    A("")
    A("Bound leaf: flight-mechanics/performance/rotorcraft-blade-flapping-"
      "dynamics (FAR-29 context; Johnson/Leishman flap model, "
      "summary-only).")
    A("")

    # --- Section 6: lead-lag ---
    ll = model["leadlag"]
    A("## 6. Rotorcraft H-1: lead-lag dynamics and ground-resonance "
      "clearance")
    A("")
    A("Case inputs: lag-hinge offset %s (fraction of radius), operating "
      "rotor speed %s rad/s, airframe lateral frequency %s Hz."
      % (_fmt(ll["hinge_offset"]), _fmt(ll["operating_omega"]),
         _fmt(ll["airframe_frequency_hz"])))
    A("")
    A("| Quantity | Value |")
    A("|---|---|")
    A("| Lag frequency ratio nu_zeta | %s per rev (0.2-0.4 band) |"
      % _fmt(ll["lag_frequency_ratio"]))
    A("| Collective lag mode | %s Hz |" % _fmt(ll["collective_hz"]))
    A("| Regressing lag mode | %s Hz |" % _fmt(ll["regressing_hz"]))
    A("| Advancing lag mode | %s Hz |" % _fmt(ll["advancing_hz"]))
    A("| Coincidence rotor speed Omega* | %s rad/s |"
      % _fmt(ll["coincidence_omega"]))
    A("| Clearance fraction | %s |" % _fmt(ll["clearance_fraction"]))
    A("| **Verdict** | **%s** |" % ll["verdict"])
    A("")
    if model.get("leadlag_alt"):
        alt = model["leadlag_alt"]
        A("Sensitivity: with a separated airframe lateral frequency of %s "
          "Hz, Omega* = %s rad/s (clearance fraction %s) and the verdict "
          "is **%s**."
          % (_fmt(alt["airframe_frequency_hz"]), _fmt(alt["coincidence_omega"]),
             _fmt(alt["clearance_fraction"]), alt["verdict"]))
        A("")
    A("Bound leaf: flight-mechanics/performance/rotorcraft-lead-lag-"
      "dynamics (FAR-29 context; Coleman-diagram coincidence, "
      "summary-only).")
    A("")

    # --- Section 7: hover in ground effect ---
    g = model["hover_ige"]
    A("## 7. Rotorcraft H-1: hover in ground effect")
    A("")
    A("Case inputs: mass %s kg, rotor radius %s m, rotor height above "
      "ground %s m (z/R = %s), solidity %s, Cd0 %s, tip speed %s m/s, "
      "induced power factor %s, available power %s W."
      % (_fmt(g["mass_kg"]), _fmt(g["radius_m"]), _fmt(g["height_m"]),
         _fmt(g["height_m"] / g["radius_m"]), _fmt(g["solidity"]),
         _fmt(g["cd0"]), _fmt(g["tip_speed_ms"]), _fmt(g["k"]),
         _fmt(g["available_power_W"])))
    A("")
    A("| Quantity | Value |")
    A("|---|---|")
    A("| Hover thrust (weight) | %s N |" % _fmt(g["thrust_N"]))
    A("| Ideal induced velocity v_h | %s m/s |"
      % _fmt(g["hover_induced_velocity"]))
    A("| Ideal induced power | %s W |" % _fmt(g["ideal_induced_power_W"]))
    A("| Profile power (unchanged IGE) | %s W |"
      % _fmt(g["profile_power_W"]))
    A("| **Ground-effect factor k_ige** | **%s** (Cheeseman factor at "
      "z/R = %s; 0.9375 at z/R = 1) |"
      % (_fmt(g["ground_effect_factor"]),
         _fmt(g["height_m"] / g["radius_m"])))
    A("| IGE induced power | %s W |" % _fmt(g["ige_induced_power_W"]))
    A("| **IGE total hover power** | **%s W** |"
      % _fmt(g["ige_total_power_W"]))
    A("| OGE total hover power | %s W |" % _fmt(g["oge_total_power_W"]))
    if g.get("power_margin_W") is not None:
        A("| Power margin at %s W available | %s W |"
          % (_fmt(g["power_margin_W"] + g["ige_total_power_W"]),
             _fmt(g["power_margin_W"])))
        if g.get("max_hover_height") is not None:
            A("| **Maximum hover height** | **%s m** (IGE-limited) |"
              % _fmt(g["max_hover_height"]))
        else:
            A("| Maximum hover height | none - available power covers OGE "
              "hover at any height |")
    A("")
    A("Bound leaf: flight-mechanics/performance/rotorcraft-hover-ground-"
      "effect (FAR-29 context; Cheeseman-style factor on induced power "
      "only, summary-only).")
    A("")

    # --- Section 8: axial descent ---
    d = model["descent"]
    A("## 8. Rotorcraft H-1: axial descent flow states")
    A("")
    A("Case inputs: mass %s kg (thrust %s N), rotor radius %s m, profile "
      "power %s W, induced power factor %s, rotor speed %s rad/s; "
      "vortex-ring band limits (0, %s) m/s."
      % (_fmt(d["mass_kg"]), _fmt(d["thrust_N"]), _fmt(d["radius_m"]),
         _fmt(d["profile_power_W"]), _fmt(d["k"]),
         _fmt(d["rotor_speed_rad_s"]), _fmt(d["band_limits"][1])))
    A("")
    A("| Descent rate (m/s) | Flow state | v_i (m/s) | Power (W) | "
      "Torque at %s rad/s (N m) |" % _fmt(d["rotor_speed_rad_s"]))
    A("|---|---|---|---|---|")
    for row in d["cases"]:
        vi = _fmt(row["induced_velocity"]) if row["induced_velocity"] \
            is not None else "n/a (momentum invalid)"
        pw = _fmt(row["power_W"]) if row["power_W"] is not None else "n/a"
        tq = _fmt(row["torque_Nm"]) if row["torque_Nm"] is not None else "n/a"
        A("| %s | %s | %s | %s | %s |"
          % (_fmt(row["vd_ms"]), row["flow_state"], vi, pw, tq))
    A("")
    tr = d["torque_reversal"]
    A("Torque-reversal condition: c = P_profile / (k T) = %s m/s versus "
      "v_h = %s m/s -> c < v_h, verdict **%s**."
      % (_fmt(tr["c"]), _fmt(tr["v_h"]),
         "momentum-unreachable" if tr["c_less_than_vh"]
         else "momentum-reachable"))
    A("")
    A("Bound leaf: flight-mechanics/performance/rotorcraft-axial-descent-"
      "flow-states (FAR-29 context; NASA TP-2005-213477 public-domain "
      "empirical-inflow context, summary-only).")
    A("")

    # --- Section 9: turn ---
    t = model["turn"]
    bk = t["breakdown"]
    A("## 9. Rotorcraft H-1: banked turn performance")
    A("")
    A("Case inputs: mass %s kg (weight %s N), rotor radius %s m (disk %s "
      "m2), solidity %s, Cd0 %s, tip speed %s m/s, flat-plate area %s m2, "
      "induced power factor %s, speed %s m/s, analysed load factor %s, "
      "available power %s W."
      % (_fmt(t["mass_kg"]), _fmt(t["weight_N"]), _fmt(t["radius_m"]),
         _fmt(t["disk_area_m2"]), _fmt(t["solidity"]), _fmt(t["cd0"]),
         _fmt(t["tip_speed_ms"]), _fmt(t["flat_plate_m2"]), _fmt(t["k"]),
         _fmt(t["speed_ms"]), _fmt(t["load_factor"]),
         _fmt(t["available_power_W"])))
    A("")
    A("| Quantity | Value |")
    A("|---|---|")
    A("| Turn thrust (n x W) | %s N |" % _fmt(bk["thrust"]))
    A("| Turning induced velocity | %s m/s |" % _fmt(bk["induced_velocity"]))
    A("| Induced power | %s W |" % _fmt(bk["induced_power"]))
    A("| Profile power | %s W |" % _fmt(bk["profile_power"]))
    A("| Parasite power | %s W |" % _fmt(bk["parasite_power"]))
    A("| **Turn total power** | **%s W** |" % _fmt(bk["total_power"]))
    A("| Level-flight total at n = 1 | %s W |"
      % _fmt(t["level_total_power_W"]))
    A("| Bank angle at n = %s | %s deg |"
      % (_fmt(t["load_factor"]), _fmt(t["bank_deg"])))
    A("| Turn rate / radius | %s rad/s / %s m |"
      % (_fmt(t["rate_rad_s"]), _fmt(t["turn_radius_m"])))
    su = t["sustained"]
    A("| **Sustained load factor** | **%s** (%s) |"
      % (_fmt(su["load_factor"]), su["note"]))
    A("| Sustained bank angle | %s deg |" % _fmt(t["sustained_bank_deg"]))
    A("| Sustained turn rate / radius | %s rad/s / %s m |"
      % (_fmt(t["sustained_rate_rad_s"]), _fmt(t["sustained_radius_m"])))
    A("")
    A("Power round trip: the total power at the sustained load factor "
      "equals the %s W available power (bisection root, fixed 120 "
      "iterations)." % _fmt(t["available_power_W"]))
    A("")
    if t.get("alt_power_case"):
        alt = t["alt_power_case"]
        A("Sensitivity: with %s W available at %s m/s the sustained load "
          "factor falls to %s (rate %s rad/s, radius %s m): the parasite "
          "V^3 growth cuts the sustained load factor as the speed rises at "
          "fixed power."
          % (_fmt(alt["total_power"]), _fmt(alt["speed_ms"]),
             _fmt(alt["load_factor"]),
             _fmt(turn_rate(alt["load_factor"], alt["speed_ms"])),
             _fmt(turn_radius(alt["load_factor"], alt["speed_ms"]))))
        A("")
    A("Bound leaf: flight-mechanics/performance/rotorcraft-turn-"
      "performance (FAR-29 context; uniform-inflow momentum theory, "
      "summary-only).")
    A("")

    # --- Section 10: range and endurance ---
    fu = model["fuel"]
    A("## 10. Rotorcraft H-4: range and endurance fuel closure")
    A("")
    A("Case inputs: takeoff weight %s N, fuel load %s kg, rotor radius %s "
      "m, figure of merit %s, specific fuel consumption %s kg/(s W); "
      "weight at burnout W1 = %s N."
      % (_fmt(fu["weight0_N"]), _fmt(fu["fuel_mass_kg"]),
         _fmt(fu["radius_m"]), _fmt(fu["figure_of_merit"]),
         _fmt(fu["c_specific"]), _fmt(fu["weight1_N"])))
    A("")
    A("| Quantity | Value |")
    A("|---|---|")
    A("| Hover power at W0 | %s W |" % _fmt(fu["hover_power_W"]))
    A("| Fuel flow at W0 | %s kg/s |" % _fmt(fu["fuel_flow_kg_s"]))
    A("| **Hover endurance** | **%s s = %s** |"
      % (_fmt(fu["hover_endurance_s"], 5), _hms(fu["hover_endurance_s"])))
    A("| Best-range speed (max SR) | %s m/s |"
      % _fmt(fu["best_range_speed_ms"]))
    A("| Best-endurance speed (min P) | %s m/s |"
      % _fmt(fu["best_endurance_speed_ms"]))
    A("| Specific range at %s m/s | %s m/kg |"
      % (_fmt(fu["endurance_speed_ms"]), _fmt(fu["specific_range_m_per_kg"])))
    A("| **Cruise range at %s m/s** | **%s m = %s km** |"
      % (_fmt(fu["range_speed_ms"]), _fmt(fu["cruise_range_m"], 6),
         _fmt(fu["cruise_range_km"])))
    A("| **Cruise endurance at %s m/s** | **%s s = %s** |"
      % (_fmt(fu["endurance_speed_ms"]), _fmt(fu["cruise_endurance_s"], 5),
         _hms(fu["cruise_endurance_s"])))
    A("")
    A("Cruise closure scales the reference power with the average weight "
      "(W_avg/W_ref)^1.5 over the fuel burn; the power-required curve "
      "inputs are: %s."
      % ", ".join("(%s m/s, %s W)" % (_fmt(r["speed_ms"]),
                                      _fmt(r["power_W"]))
                  for r in fu["power_curve"]))
    A("")
    A("Bound leaf: flight-mechanics/performance/rotorcraft-range-endurance "
      "(FAR-29 context; weight-decay integration, summary-only).")
    A("")
    A("---")
    A("*Generated by Aero Agent Roles aircraft-performance-engineer core "
      "(%s). DRAFT for human flight-mechanics review. Not an approval "
      "document, not a certification finding, and no regulatory "
      "sign-off.*" % model["generated"])
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Evidence gate checkers
# ---------------------------------------------------------------------------

GATE_CHECKS = {
    "bfl_balance_present": "balanced V1 inside [0, V_LOF] with ASD = AGD "
                           "at balance",
    "propeller_range_present": "propeller Breguet range computed with the "
                               "SI PSFC conversion",
    "sizing_closed": "rotor disk sized at the loading ceiling with "
                     "solidity closure and tip Mach",
    "flap_dynamics_present": "Lock number in the published band with "
                             "coning angle and flap frequency ratio",
    "leadlag_verdict_present": "lag modes, coincidence rotor speed and a "
                               "clear/resonance-adjacent verdict",
    "ige_numbers_present": "ground-effect factor, IGE/OGE power terms and "
                           "hover-height verdict present",
    "descent_verdict_present": "axial flow states classified with the "
                               "windmill-brake momentum power",
    "turn_numbers_present": "turn power breakdown and a power-sustained "
                            "load factor with round trip",
    "fuel_closure_present": "hover endurance and cruise range/endurance "
                            "closed over the fuel load",
    "sign_off_honest": "document is marked draft-for-review, not approval",
}


def check_report(model: dict) -> dict:
    """Run the evidence gates against a performance model."""
    b = model.get("bfl", {})
    p = model.get("propeller", {})
    s = model.get("sizing", {})
    f = model.get("flap", {})
    ll = model.get("leadlag", {})
    g = model.get("hover_ige", {})
    d = model.get("descent", {})
    t = model.get("turn", {})
    fu = model.get("fuel", {})
    v1 = b.get("v1_ms", -1.0)
    results = {
        "bfl_balance_present": bool(b) and 0.0 <= v1 <= b.get("v_lof_ms",
                                                              0.0) and
            isinstance(b.get("balanced_field_length_m"), (int, float)) and
            b["balanced_field_length_m"] > 0.0 and
            b.get("balance_delta_m", float("inf")) < 1e-6,
        "propeller_range_present": bool(p) and
            isinstance(p.get("range_m"), (int, float)) and
            p["range_m"] > 0.0 and
            abs(p.get("range_km", 0.0) - p["range_m"] / 1000.0) < 1e-9 and
            p.get("psfc_kg_per_w_s", 0.0) > 0.0,
        "sizing_closed": bool(s) and s.get("disk_radius_m", 0.0) > 0.0 and
            s.get("solidity", 0.0) > 0.0 and
            s.get("blade_chord_m", 0.0) > 0.0 and
            0.0 < s.get("tip_mach", 1.0) < 1.0 and
            abs(s.get("achieved_disk_loading_pa", 0.0)
                - s.get("dl_max_pa", 0.0)) < 1e-9,
        "flap_dynamics_present": bool(f) and
            5.0 <= f.get("lock_number", 0.0) <= 12.0 and
            isinstance(f.get("coning_angle_deg"), (int, float)) and
            f.get("flap_frequency_ratio", 0.0) >= 1.0,
        "leadlag_verdict_present": bool(ll) and
            ll.get("verdict") in ("clear", "resonance-adjacent") and
            ll.get("coincidence_omega", 0.0) > 0.0 and
            isinstance(ll.get("regressing_hz"), (int, float)),
        "ige_numbers_present": bool(g) and
            0.0 < g.get("ground_effect_factor", 0.0) <= 1.0 and
            g.get("ige_total_power_W", 0.0) < g.get("oge_total_power_W",
                                                    float("inf")),
        "descent_verdict_present": bool(d) and
            d.get("band_limits") is not None and
            all(r.get("flow_state") in ("hover", "vortex-ring-band",
                                        "windmill-brake")
                for r in d.get("cases", [])) and
            d.get("torque_reversal", {}).get("c_less_than_vh") is not None,
        "turn_numbers_present": bool(t) and
            t.get("sustained", {}).get("load_factor", 0.0) >= 1.0 and
            isinstance(t.get("level_total_power_W"), (int, float)) and
            isinstance(t.get("sustained_radius_m"), (int, float)),
        "fuel_closure_present": bool(fu) and
            fu.get("hover_endurance_s", 0.0) > 0.0 and
            fu.get("cruise_range_m", 0.0) > 0.0 and
            fu.get("cruise_endurance_s", 0.0) > 0.0 and
            fu.get("best_range_speed_ms", 0.0) > 0.0,
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_report_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    checks = {
        "has_title": "aircraft performance analysis report" in low,
        "has_scope_register": "scope and aircraft register" in low,
        "has_v1_bfl_numbers": "balanced v1" in low and
                              "balanced field length" in low,
        "has_propeller_range_number": "propeller breguet" in low and
                                      "km" in low,
        "has_sizing_numbers": "disk radius" in low and "solidity" in low
                              and "tip mach" in low,
        "has_flap_number": "lock number" in low,
        "has_leadlag_verdict": "lead-lag" in low and
                               "resonance-adjacent" in low,
        "has_ige_numbers": "ground-effect factor" in low and
                           "in ground effect" in low,
        "has_descent_number": "windmill-brake" in low and
                              "flow state" in low,
        "has_turn_number": "sustained load factor" in low and
                           "turn total power" in low,
        "has_fuel_numbers": "hover endurance" in low and
                            "cruise endurance" in low,
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling."""
    return check_report_markdown(md_text)


# ---------------------------------------------------------------------------
# Example project (worked deliverable: the AeroSkills reference fleet)
# ---------------------------------------------------------------------------

def example_item() -> PerformanceItem:
    """Reference item: the multi-aircraft performance workbook whose nine
    case sets ARE the real reference cases of the nine bound leaves (the
    numbers the leaves' own logic modules produce)."""
    return PerformanceItem(
        workbook_name="AeroSkills reference fleet performance workbook",
        description="Multi-aircraft performance analysis of a reference "
                    "fleet: two FAR-25 airplanes (a twin-engine transport "
                    "for the engine-out balanced field length case and a "
                    "turboprop transport for the propeller cruise range "
                    "case) and four FAR-29 rotorcraft cases (the light "
                    "helicopter with its 5.0 m main rotor for lead-lag "
                    "clearance, hover in ground effect, axial descent "
                    "flow states and banked turn performance; the medium "
                    "helicopter takeoff case for main rotor sizing; the "
                    "blade-level flap dynamics case; and the six-tonne "
                    "class helicopter for the range and endurance fuel "
                    "closure).",
        airframe="Reference fleet: A-1/A-2 airplanes, H-1/H-2/H-3/H-4 "
                 "rotorcraft cases",
        certification_basis="FAR-25 (airplane cases) / FAR-29 (rotorcraft "
                            "cases)",
        # A-1: twin-engine transport, FAR-25.113-style balanced field
        # length (balanced-field-length leaf worked case)
        bfl_thrust_all_n=150000.0,
        bfl_engine_count=2,
        bfl_weight_n=600000.0,
        bfl_mu_roll=0.03,
        bfl_mu_brake=0.45,
        bfl_v_lof_ms=80.0,
        bfl_gradient=0.024,
        # A-2: turboprop transport, propeller Breguet range
        # (propeller-range leaf worked case)
        pr_eta_p=0.80,
        pr_psfc_lb_per_hp_h=0.55,
        pr_ld=12.0,
        pr_m0_kg=11500.0,
        pr_m1_kg=10000.0,
        # H-2: 4500 kg medium helicopter, 350 Pa ceiling, 0.12 CT/sigma,
        # 4 blades at 210 m/s (main-rotor-sizing leaf worked case)
        sz_mass_kg=4500.0,
        sz_dl_max_pa=350.0,
        sz_ct_over_sigma=0.12,
        sz_blade_count=4,
        sz_tip_speed_ms=210.0,
        # H-3: blade flap dynamics reference case (blade-flapping leaf
        # worked case: R = 6.0 m, m_b = 50 kg, chord 0.5 m)
        bf_blade_mass_kg=50.0,
        bf_radius_m=6.0,
        bf_chord_m=0.5,
        bf_theta0_rad=0.170,
        bf_inflow_ratio=0.050,
        bf_hinge_offset=0.05,
        # H-1: articulated rotor at 44 rad/s with a 5.0 Hz airframe
        # (lead-lag leaf worked case)
        ll_hinge_offset=0.05,
        ll_omega_rad_s=44.0,
        ll_airframe_hz=5.0,
        ll_alt_airframe_hz=3.5,
        # H-1: 2200 kg helicopter hovering at z = 5.0 m with a 5.0 m rotor
        # and 360 kW available (hover-ground-effect leaf worked case)
        ge_mass_kg=2200.0,
        ge_radius_m=5.0,
        ge_height_m=5.0,
        ge_available_power_w=360000.0,
        # H-1: axial descent states over the reference rotor with
        # P_profile = 122935 W and Omega = 44 rad/s (axial-descent leaf
        # worked cases at Vd = 0/15/25/30/40 m/s)
        ad_mass_kg=2200.0,
        ad_radius_m=5.0,
        ad_profile_power_w=122935.0,
        ad_rotor_speed_rad_s=44.0,
        ad_descent_cases=[0.0, 15.0, 25.0, 30.0, 40.0],
        # H-1: banked turn at n = 2, 60 m/s with 600 kW available
        # (turn-performance leaf worked case)
        tp_mass_kg=2200.0,
        tp_radius_m=5.0,
        tp_solidity=0.08,
        tp_cd0=0.012,
        tp_tip_speed_ms=220.0,
        tp_flat_plate_m2=2.2,
        tp_speed_ms=60.0,
        tp_load_factor=2.0,
        tp_available_power_w=600000.0,
        tp_alt_power_w=450000.0,
        tp_alt_speed_ms=40.0,
        # H-4: six-tonne class helicopter fuel closure (range-endurance
        # leaf worked case: W0 = 60000 N, 1500 kg fuel, R = 8 m, FM 0.75)
        re_weight0_n=60000.0,
        re_fuel_kg=1500.0,
        re_radius_m=8.0,
        re_figure_of_merit=0.75,
        re_power_curve=[(40.0, 620000.0), (50.0, 560000.0),
                        (60.0, 540000.0), (70.0, 555000.0),
                        (80.0, 600000.0)],
        re_range_speed_ms=80.0,
        re_range_power_w=600000.0,
        re_endurance_speed_ms=60.0,
        re_endurance_power_w=540000.0,
        supporting_note="All case inputs are the real reference cases of "
                        "the bound flight-mechanics/performance leaves; "
                        "the role engine recomputes every quantity from "
                        "the same formulas the leaf logic modules encode "
                        "and cross-checks against them when AeroSkills is "
                        "present (evidence/provenance.json).",
    )


def example_report_markdown() -> str:
    return render_report_markdown(build_performance_report(example_item()))


if __name__ == "__main__":
    item = example_item()
    model = build_performance_report(item)
    md = render_report_markdown(model)
    print("BALANCED V1:", model["bfl"]["v1_ms"])
    print("BALANCED FIELD LENGTH:", model["bfl"]["balanced_field_length_m"])
    print("PROPELLER RANGE KM:", model["propeller"]["range_km"])
    print("DISK RADIUS:", model["sizing"]["disk_radius_m"])
    print("LOCK NUMBER:", model["flap"]["lock_number"])
    print("LEAD-LAG VERDICT:", model["leadlag"]["verdict"])
    print("IGE TOTAL POWER:", model["hover_ige"]["ige_total_power_W"])
    print("SUSTAINED LOAD FACTOR:", model["turn"]["sustained"]["load_factor"])
    print("HOVER ENDURANCE S:", model["fuel"]["hover_endurance_s"])
    print("GATES:", check_report(model))
    print("RENDERED:", len(md), "chars")
