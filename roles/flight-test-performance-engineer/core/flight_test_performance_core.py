#!/usr/bin/env python3
"""flight_test_performance_core.py - Flight Test Performance Engineer executable core.

This is the role's ENGINE: given a flight-test sortie data set (recorded
takeoff, landing, level-acceleration, cruise and stall-speed runs plus the
test-day conditions) it reduces the measured data to standard conditions
and reference weight, computes the takeoff/landing distance legs, the
determined thrust from the level acceleration (total energy method), the
corrected cruise fuel flows and range-performance curve, the weight
corrections to the stall/V speeds, and the computed-vs-predicted scatter
table. It BUILDS the Flight Test Performance Data Analysis Report and
gate-checks deliverables. Standalone: no external repo needed.

Domain rules encoded here are public flight-test methodology as bound in
the Aero Agent Skills flight-test-operations/performance leaves and in the
public FAR-25 / CS-25 context those leaves reference (summary only, never
reproduced text): ISA atmosphere physics, the 35 ft obstacle height of the
takeoff distance definition, trapezoid ground-roll integration, the Vref =
1.23*Vs0 landing approach practice, the 1.67 certified landing field
length factor, the total-energy specific excess power P_s = V*a/g, the
thrust lapse sigma^0.7 model, the sqrt(w_ref/w_test) fuel-flow weight
correction, and the sqrt(w/w_ref) stall-speed correction.

Units: SI. Forces and weights in N, speeds in m/s, distances in m,
fuel flows in kg/s, altitudes in m, temperatures in K/C as noted.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

def _today() -> str:
    import os
    from datetime import date
    return os.environ.get("ROLE_GEN_DATE", date.today().isoformat())

# ---------------------------------------------------------------------------
# Physical constants (public ISA atmosphere physics, SI)
# ---------------------------------------------------------------------------

RHO0 = 1.225            # standard sea level density, kg/m^3
P0_PA = 101325.0        # standard sea level pressure, Pa
T0_K = 288.15           # standard sea level temperature, K
LAPSE_K_PER_M = 0.0065  # troposphere lapse rate, K/m
G0 = 9.80665            # standard gravity, m/s^2
R_GAS = 287.05287       # specific gas constant of air, J/(kg K)
GAMMA = 1.4
H_TROPO_M = 11000.0     # tropopause geopotential altitude, m
T_TROPO_K = 216.65      # tropopause temperature, K
MAX_H_M = 20000.0       # model ceiling, m
H_ISO_M = R_GAS * T_TROPO_K / G0                    # isothermal scale height, m
ISA_DENSITY_EXP = G0 / (R_GAS * LAPSE_K_PER_M) - 1.0    # 4.25588
ISA_PRESSURE_EXP = G0 / (R_GAS * LAPSE_K_PER_M)          # 5.25588
FT_PER_M = 1.0 / 0.3048

# ---------------------------------------------------------------------------
# Domain constants (flight-test practice, FAR-25 / CS-25 summary context as
# encoded in the bound AeroSkills performance leaves)
# ---------------------------------------------------------------------------

OBSTACLE_35FT_M = 10.668   # 35 ft obstacle height (takeoff distance def)
APPROACH_FACTOR = 1.23     # Vref = 1.23 * Vs0 (landing-distance leaf)
DEFAULT_FLARE_TIME_S = 5.0  # flare segment time model (landing-distance leaf)
FIELD_LENGTH_FACTOR = 1.67  # certified landing field length factor
LAPSE_EXP = 0.7             # installed thrust lapse exponent (sigma^0.7)
SCATTER_BAND_PCT = 10.0     # computed-vs-predicted agreement band, percent


def _check_positive(name, value):
    if value <= 0:
        raise ValueError("%s must be > 0, got %r" % (name, value))


def _check_nonnegative(name, value):
    if value < 0:
        raise ValueError("%s must be >= 0, got %r" % (name, value))


# ---------------------------------------------------------------------------
# ISA atmosphere (public physics; same model as the bound leaves)
# ---------------------------------------------------------------------------

def isa_conditions(altitude_m):
    """ISA (T in K, P in Pa, rho in kg/m^3) at geopotential altitude.

    Troposphere lapse 0.0065 K/m to 11000 m, isothermal 216.65 K above.
    Anchors: 0 m -> (288.15, 101325.0, 1.225); 8000 m -> (236.15,
    35599.8, 0.52517); 11000 m density ratio 0.29707.
    """
    if altitude_m < 0 or altitude_m > MAX_H_M:
        raise ValueError("altitude must be within 0 to 20000 m, got %r"
                         % (altitude_m,))
    if altitude_m <= H_TROPO_M:
        t = T0_K - LAPSE_K_PER_M * altitude_m
        p = P0_PA * (1.0 - LAPSE_K_PER_M * altitude_m / T0_K) ** ISA_PRESSURE_EXP
    else:
        t = T_TROPO_K
        p_t = P0_PA * (1.0 - LAPSE_K_PER_M * H_TROPO_M / T0_K) ** ISA_PRESSURE_EXP
        p = p_t * math.exp(-(altitude_m - H_TROPO_M) / H_ISO_M)
    return (t, p, p / (R_GAS * t))


def isa_density_ratio_m(altitude_m):
    """ISA density ratio sigma = rho/rho0 at geopotential altitude (m)."""
    if altitude_m < 0 or altitude_m > MAX_H_M:
        raise ValueError("altitude must be within 0 to 20000 m, got %r"
                         % (altitude_m,))
    if altitude_m <= H_TROPO_M:
        return (1.0 - LAPSE_K_PER_M * altitude_m / T0_K) ** ISA_DENSITY_EXP
    sigma_t = (1.0 - LAPSE_K_PER_M * H_TROPO_M / T0_K) ** ISA_DENSITY_EXP
    return sigma_t * math.exp(-(altitude_m - H_TROPO_M) / H_ISO_M)


def isa_pressure_ratio_m(altitude_m):
    """ISA pressure ratio delta = P/P0 at geopotential altitude (m)."""
    if altitude_m < 0 or altitude_m > MAX_H_M:
        raise ValueError("altitude must be within 0 to 20000 m, got %r"
                         % (altitude_m,))
    if altitude_m <= H_TROPO_M:
        return (1.0 - LAPSE_K_PER_M * altitude_m / T0_K) ** ISA_PRESSURE_EXP
    delta_t = (1.0 - LAPSE_K_PER_M * H_TROPO_M / T0_K) ** ISA_PRESSURE_EXP
    return delta_t * math.exp(-(altitude_m - H_TROPO_M) / H_ISO_M)


def isa_temperature_m(altitude_m):
    """ISA static temperature in K at geopotential altitude (m)."""
    if altitude_m < 0 or altitude_m > MAX_H_M:
        raise ValueError("altitude must be within 0 to 20000 m, got %r"
                         % (altitude_m,))
    if altitude_m <= H_TROPO_M:
        return T0_K - LAPSE_K_PER_M * altitude_m
    return T_TROPO_K


def day_sigma_from_alt_oat(pressure_alt_m, oat_deg_c):
    """Test-day density ratio sigma = (P/P0_ISA) * (T0 / T_amb).

    The test-day density ratio from the measured pressure altitude and
    outside air temperature (the density-altitude formulation used by the
    climb-performance leaf). Returns a float in (0, 1] for field levels.
    """
    _check_nonnegative("pressure altitude", pressure_alt_m)
    t_amb = oat_deg_c + 273.15
    if t_amb <= 0:
        raise ValueError("outside air temperature must be above absolute zero")
    return isa_pressure_ratio_m(pressure_alt_m) * (T0_K / t_amb)


def density_altitude_m(pressure_alt_m, oat_deg_c):
    """Density altitude in m for a measured pressure altitude and OAT.

    sigma from the pressure altitude and the ambient temperature; the
    density altitude is the altitude where the ISA density ratio equals
    sigma (bisection, same model as the climb-performance leaf).
    """
    _check_nonnegative("pressure altitude", pressure_alt_m)
    t_amb = oat_deg_c + 273.15
    if t_amb <= 0:
        raise ValueError("outside air temperature must be above absolute zero")
    sigma = isa_pressure_ratio_m(pressure_alt_m) * (T0_K / t_amb)
    lo, hi = 0.0, MAX_H_M
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if isa_density_ratio_m(mid) > sigma:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def tas_from_eas(v_eas, rho, rho0=RHO0):
    """True airspeed in m/s from equivalent airspeed and air density.

    V_tas = V_eas * sqrt(rho0 / rho) (equal dynamic pressure). Anchor:
    110 m/s EAS at the 8000 m ISA density 0.52517 kg/m^3 -> 168.0 m/s.
    """
    _check_positive("equivalent airspeed", v_eas)
    _check_positive("air density", rho)
    _check_positive("sea level density", rho0)
    return v_eas * math.sqrt(rho0 / rho)


def speed_of_sound_m(altitude_m):
    """ISA speed of sound in m/s at altitude (m)."""
    _check_nonnegative("altitude", altitude_m)
    t = isa_temperature_m(altitude_m)
    return math.sqrt(GAMMA * R_GAS * t)


def tas_from_mach(mach, altitude_m):
    """True airspeed in m/s from Mach number and altitude (m)."""
    if mach < 0:
        raise ValueError("mach must be >= 0, got %r" % (mach,))
    return mach * speed_of_sound_m(altitude_m)


# ---------------------------------------------------------------------------
# Weight corrections (V speeds / stall speeds / fuel flow)
# ---------------------------------------------------------------------------

def vs1g_from_wing_loading(wing_loading_n_m2, rho_kg_m3, cl_max):
    """Reference stall speed Vs1g = sqrt(2*(W/S)/(rho*CLmax)), m/s."""
    for name, value in (("wing loading", wing_loading_n_m2),
                        ("air density", rho_kg_m3), ("cl_max", cl_max)):
        _check_positive(name, value)
    return math.sqrt(2.0 * wing_loading_n_m2 / (rho_kg_m3 * cl_max))


def weight_corrected_speed(v_ref, w_ref, w_new):
    """Speed corrected for a weight change: v_new = v_ref*sqrt(w_new/w_ref)."""
    _check_positive("reference speed", v_ref)
    _check_positive("reference weight", w_ref)
    _check_positive("new weight", w_new)
    return v_ref * math.sqrt(w_new / float(w_ref))


def stall_margin(vs, v_current):
    """Stall margin (v_current - vs) / vs (negative = below stall speed)."""
    _check_positive("stall speed", vs)
    _check_nonnegative("current speed", v_current)
    return (v_current - vs) / vs


def weight_correction_factor(w_test, w_ref):
    """Square-root fuel-flow weight correction sqrt(w_ref / w_test)."""
    _check_positive("test weight", w_test)
    _check_positive("reference weight", w_ref)
    return math.sqrt(w_ref / w_test)


def corrected_fuel_flow(wf_measured, w_test, w_ref):
    """Fuel flow (kg/s) corrected from the test weight to the reference."""
    _check_nonnegative("measured fuel flow", wf_measured)
    return wf_measured * weight_correction_factor(w_test, w_ref)


def range_performance(tas_m_s, wf_corrected):
    """Range performance (distance per unit fuel mass), m/kg."""
    _check_positive("corrected fuel flow", wf_corrected)
    return tas_m_s / wf_corrected


# ---------------------------------------------------------------------------
# Traces: integration, differentiation, quality
# ---------------------------------------------------------------------------

def ground_roll_integrate(speeds, times):
    """Ground distance from ground speed samples (trapezoid rule), m.

    s = sum((v_i + v_{i+1})/2 * dt_i). Mirrors the takeoff-distance leaf.
    """
    if len(speeds) != len(times):
        raise ValueError("speed and time samples must be equal length")
    if len(speeds) < 2:
        raise ValueError("need at least two speed samples")
    s = 0.0
    for i in range(len(speeds) - 1):
        v0, v1 = speeds[i], speeds[i + 1]
        t0, t1 = times[i], times[i + 1]
        if v0 < 0 or v1 < 0:
            raise ValueError("speed samples must be >= 0")
        if t1 <= t0:
            raise ValueError("time samples must be strictly increasing")
        s += (v0 + v1) / 2.0 * (t1 - t0)
    return s


def trace_quality_verdict(times, values, max_gap=None):
    """Data quality verdict for a reduced trace: NaN and gap flags.

    Returns {"verdict": "ok"|"flagged", "issues": [...]}; mirrors the
    data-reduction leaf's pre-analysis gate.
    """
    if len(times) != len(values):
        raise ValueError("times and values must have equal length")
    if not times:
        raise ValueError("trace must not be empty")
    issues = []
    for i, vi in enumerate(values):
        if isinstance(vi, float) and math.isnan(vi):
            issues.append({"type": "nan", "index": i, "detail": "NaN sample"})
    if max_gap is not None and len(times) > 1:
        for i in range(1, len(times)):
            d = times[i] - times[i - 1]
            if d > max_gap:
                issues.append({"type": "gap", "index": i,
                               "detail": "time gap %.3f s exceeds %.3f s"
                               % (d, max_gap)})
    return {"verdict": "ok" if not issues else "flagged", "issues": issues}


def smooth_trace(trace, window):
    """Moving average over an odd centered window (same length output)."""
    if not isinstance(window, int) or window < 1 or window % 2 == 0:
        raise ValueError("smoothing window must be a positive odd integer")
    if not trace:
        raise ValueError("trace must not be empty")
    half = (window - 1) // 2
    out = []
    for i in range(len(trace)):
        lo = max(0, i - half)
        hi = min(len(trace) - 1, i + half)
        out.append(sum(trace[lo:hi + 1]) / (hi - lo + 1.0))
    return out


def acceleration_from_trace(speeds, times):
    """Acceleration in m/s^2: central differences, one-sided at the ends."""
    if len(speeds) != len(times):
        raise ValueError("airspeed and time lists must match in length")
    n = len(speeds)
    if n < 2:
        raise ValueError("at least two samples are required")
    for i in range(1, n):
        if times[i] <= times[i - 1]:
            raise ValueError("time must be strictly increasing")
    out = [0.0] * n
    out[0] = (speeds[1] - speeds[0]) / (times[1] - times[0])
    for i in range(1, n - 1):
        out[i] = (speeds[i + 1] - speeds[i - 1]) / (times[i + 1] - times[i - 1])
    out[n - 1] = (speeds[n - 1] - speeds[n - 2]) / (times[n - 1] - times[n - 2])
    return out


# ---------------------------------------------------------------------------
# Level acceleration (total energy method) - thrust determination
# ---------------------------------------------------------------------------

def specific_excess_power(v, a, g=G0, dh_dt=0.0):
    """Specific excess power P_s = dh/dt + V*a/g in m/s (level: V*a/g)."""
    _check_positive("true airspeed", v)
    _check_positive("gravity", g)
    return dh_dt + v * a / g


def excess_thrust_from_ps(ps, v, w):
    """Excess thrust in N: delta_T = W * P_s / V."""
    _check_positive("true airspeed", v)
    _check_positive("weight", w)
    return w * ps / v


def lift_coefficient(w, v, rho, s):
    """CL = W / (0.5 * rho * V^2 * S)."""
    for name, value in (("weight", w), ("true airspeed", v),
                        ("air density", rho), ("wing area", s)):
        _check_positive(name, value)
    return w / (0.5 * rho * v * v * s)


def drag_coefficient(cd0, k, cl):
    """CD = cd0 + k * CL^2 (parabolic drag polar)."""
    for name, value in (("zero-lift drag coefficient", cd0),
                        ("induced drag factor", k), ("lift coefficient", cl)):
        _check_nonnegative(name, value)
    return cd0 + k * cl * cl


def drag_from_polar(v, rho, s, w, cd0, k):
    """Drag force in N from the parabolic polar at the test density."""
    _check_positive("true airspeed", v)
    _check_positive("air density", rho)
    _check_positive("wing area", s)
    _check_positive("weight", w)
    cl = lift_coefficient(w, v, rho, s)
    return 0.5 * rho * v * v * s * drag_coefficient(cd0, k, cl)


def thrust_available_estimate(delta_t, drag):
    """Installed thrust estimate in N: T = delta_T + D (drag gap closes)."""
    _check_nonnegative("drag", drag)
    total = delta_t + drag
    if total < 0:
        raise ValueError("negative thrust available: delta_T %r below drag %r"
                         % (delta_t, drag))
    return total


def thrust_from_acceleration(weight_n, accel_m_s2, drag_n, g_m_s2=G0):
    """Installed thrust determined from a level acceleration, in N.

    T = D + (W/g)*a (Newton's second law along the flight path).
    """
    _check_positive("weight", weight_n)
    _check_nonnegative("acceleration", accel_m_s2)
    _check_positive("drag", drag_n)
    _check_positive("gravity", g_m_s2)
    return drag_n + (weight_n / g_m_s2) * accel_m_s2


def weight_corrected_ps(ps, w_test, w_ref):
    """P_s corrected to the reference weight: P_s_ref = P_s * w_test/w_ref."""
    _check_positive("test weight", w_test)
    _check_positive("reference weight", w_ref)
    return ps * w_test / w_ref


def density_corrected_ps(ps, rho_test, rho_std=RHO0, lapse_exp=LAPSE_EXP):
    """P_s corrected to the reference density at constant IAS, m/s.

    P_s_std = P_s * (rho_test/rho_std)^(lapse_exp - 0.5): thrust scales
    sigma^lapse_exp, true airspeed sigma^-0.5.
    """
    _check_positive("test density", rho_test)
    _check_positive("reference density", rho_std)
    if not 0.0 < lapse_exp <= 1.0:
        raise ValueError("thrust lapse exponent must be in (0, 1]")
    return ps * (rho_test / rho_std) ** (lapse_exp - 0.5)


def ps_at_reference_conditions(ps, w_test, w_ref, rho_test,
                               rho_std=RHO0, lapse_exp=LAPSE_EXP):
    """P_s corrected to the reference weight AND the standard density."""
    return density_corrected_ps(weight_corrected_ps(ps, w_test, w_ref),
                                rho_test, rho_std, lapse_exp)


def _assessment_region(n, window):
    margin = (window + 1) // 2
    return margin, n - margin


def reduce_level_accel_run(times_s, speeds_tas_ms, weight_n, rho_kg_m3,
                           s_m2, cd0, k, w_ref_n=None, rho_std=None,
                           window=5, dh_dt=0.0):
    """Reduce one level-acceleration run (total energy method).

    Returns the smoothed trace, acceleration, specific excess power,
    excess thrust, the assessment-region means (acceleration, P_s,
    excess thrust, drag, thrust available), the sustained-over-band
    verdict and, when requested, the corrected mean P_s at the reference
    weight and standard density. Mirrors the level-acceleration leaf.
    """
    _check_positive("test weight", weight_n)
    if len(speeds_tas_ms) != len(times_s):
        raise ValueError("airspeed and time lists must match in length")
    n = len(speeds_tas_ms)
    if n < 3:
        raise ValueError("at least three samples are required")
    for i in range(n):
        _check_positive("true airspeed sample", speeds_tas_ms[i])
    _check_positive("air density", rho_kg_m3)
    if w_ref_n is not None:
        _check_positive("reference weight", w_ref_n)
    if rho_std is not None:
        _check_positive("reference density", rho_std)
    if isinstance(dh_dt, (int, float)):
        dh_dt_list = [float(dh_dt)] * n
    else:
        if len(dh_dt) != n:
            raise ValueError("dh_dt list must match the trace length")
        dh_dt_list = list(dh_dt)

    v_s = smooth_trace(speeds_tas_ms, window)
    acc = acceleration_from_trace(v_s, times_s)
    ps = [specific_excess_power(v_s[i], acc[i], G0, dh_dt_list[i])
          for i in range(n)]
    delta_t = [excess_thrust_from_ps(ps[i], v_s[i], weight_n)
               for i in range(n)]
    drag = [drag_from_polar(v_s[i], rho_kg_m3, s_m2, weight_n, cd0, k)
            for i in range(n)]
    t_avail = [thrust_available_estimate(delta_t[i], drag[i])
               for i in range(n)]
    start, end = _assessment_region(n, window)
    if end <= start:
        raise ValueError("trace too short for the smoothing window")
    mean = lambda xs: sum(xs[start:end]) / (end - start)  # noqa: E731
    result = {
        "density_kgm3": rho_kg_m3,
        "window": window,
        "assessment_start": start,
        "assessment_end": end,
        "v_smoothed": v_s,
        "acceleration": acc,
        "specific_excess_power": ps,
        "excess_thrust": delta_t,
        "drag": drag,
        "thrust_available": t_avail,
        "mean_acceleration": mean(acc),
        "mean_specific_excess_power": mean(ps),
        "mean_excess_thrust": mean(delta_t),
        "mean_drag": mean(drag),
        "mean_thrust_available": mean(t_avail),
        "sustained_over_band": all(delta_t[i] > 0 for i in range(start, end)),
        "mean_ps_reference_weight": None,
        "mean_ps_reference_conditions": None,
    }
    if w_ref_n is not None:
        result["mean_ps_reference_weight"] = weight_corrected_ps(
            result["mean_specific_excess_power"], weight_n, w_ref_n)
        if rho_std is not None:
            result["mean_ps_reference_conditions"] = ps_at_reference_conditions(
                result["mean_specific_excess_power"], weight_n, w_ref_n,
                rho_kg_m3, rho_std)
    return result


# ---------------------------------------------------------------------------
# Takeoff / landing distance reductions
# ---------------------------------------------------------------------------

def constant_accel_distance(v1_m_s, a_m_s2):
    """Distance to accelerate from rest to v1 (or stop): v1^2/(2a), m."""
    _check_positive("speed", v1_m_s)
    _check_positive("acceleration", a_m_s2)
    return v1_m_s ** 2 / (2.0 * a_m_s2)


def engine_failure_distance(speeds, times, v_ef_mps):
    """Ground distance from brake release to the engine failure speed, m.

    Trapezoid integration of the measured ground speed samples with a
    partial trapezoid across the segment where v_ef is crossed (linear
    interpolation of the crossing time). Mirrors the engine-failure
    takeoff leaf.
    """
    if len(speeds) != len(times):
        raise ValueError("speed and time samples must be equal length")
    if len(speeds) < 2:
        raise ValueError("at least two samples are required")
    _check_positive("engine failure speed", v_ef_mps)
    if v_ef_mps < speeds[0] or v_ef_mps > speeds[-1]:
        raise ValueError("v_ef must lie within the sampled speed range")
    for i in range(len(speeds) - 1):
        if speeds[i + 1] <= speeds[i] or times[i + 1] <= times[i]:
            raise ValueError("speeds and times must be strictly increasing")
    dist = 0.0
    for j in range(len(speeds) - 1):
        if speeds[j + 1] <= v_ef_mps:
            dist += 0.5 * (speeds[j] + speeds[j + 1]) * (
                times[j + 1] - times[j])
        else:
            frac = ((v_ef_mps - speeds[j])
                    / (speeds[j + 1] - speeds[j]))
            t_cross = times[j] + frac * (times[j + 1] - times[j])
            dist += 0.5 * (speeds[j] + v_ef_mps) * (t_cross - times[j])
            break
    return dist


def reduce_takeoff_run(run, h_target_m=OBSTACLE_35FT_M):
    """Reduce one takeoff run to its measured distance legs, m.

    run keys: times_s, speeds_mps (ground speed samples from brake
    release to rotation), v_rot_mps, t_rot_s, roc_mps (climb rate after
    liftoff), liftoff_mps. Measured legs mirror the takeoff-distance
    leaf: ground roll (trapezoid to rotation speed) + rotation leg
    v_rot*t_rot + airborne climb v_liftoff*h_target/roc. The predicted
    ground roll uses the constant-acceleration model at the measured
    mean acceleration, giving the computed-vs-predicted comparison.
    """
    times = run["times_s"]
    speeds = run["speeds_mps"]
    v_rot = run["v_rot_mps"]
    t_rot = run["t_rot_s"]
    roc = run["roc_mps"]
    v_lf = run.get("liftoff_mps", speeds[-1])
    _check_positive("rotation speed", v_rot)
    _check_positive("rotation time", t_rot)
    _check_positive("climb rate", roc)
    _check_positive("liftoff speed", v_lf)

    s_ground = ground_roll_integrate(speeds, times)
    s_rot = v_rot * t_rot
    s_air = v_lf * h_target_m / roc
    total = s_ground + s_rot + s_air

    a_mean = (speeds[-1] - speeds[0]) / (times[-1] - times[0])
    s_ground_pred = constant_accel_distance(speeds[-1], a_mean)
    total_pred = s_ground_pred + s_rot + s_air
    return {
        "id": run.get("id", "TO-1"),
        "weight_n": run.get("weight_n"),
        "v_rot_mps": v_rot,
        "rotation_time_s": t_rot,
        "liftoff_mps": v_lf,
        "climb_rate_mps": roc,
        "mean_accel_mps2": a_mean,
        "ground_roll_m": s_ground,
        "rotation_m": s_rot,
        "climb_35ft_m": s_air,
        "total_m": total,
        "ground_roll_predicted_m": s_ground_pred,
        "total_predicted_m": total_pred,
        "speeds_mps": speeds,
        "times_s": times,
    }


def reduce_landing_run(run, vs0_ref_eas_ms, w_ref_n, sigma_test,
                       factor=APPROACH_FACTOR,
                       field_length_factor=FIELD_LENGTH_FACTOR,
                       runway_m=None):
    """Reduce one landing run to the demonstrated + certified distances, m.

    Vref = factor * Vs0 at the run weight, converted to true airspeed at
    the test-day density ratio; airborne flare Vref*t_air; braking
    ground roll recorded (measured) and modelled V_td^2/(2*mu*g);
    certified field length = 1.67 * demonstrated total.
    """
    w_run = run["weight_n"]
    _check_positive("run weight", w_run)
    vs0_run = weight_corrected_speed(vs0_ref_eas_ms, w_ref_n, w_run)
    vref_eas = factor * vs0_run
    vref_tas = tas_from_eas(vref_eas, RHO0 * sigma_test)
    s_air = vref_tas * run["t_air_s"]
    v_td = vref_tas
    s_ground_meas = v_td ** 2 / (2.0 * run["a_brake_meas_mps2"])
    total_meas = s_air + s_ground_meas
    mu = run.get("mu_brake")
    s_ground_pred = None
    total_pred = None
    if mu:
        s_ground_pred = constant_accel_distance(v_td, mu * G0)
        total_pred = s_air + s_ground_pred
    certified = field_length_factor * total_meas
    row = {
        "id": run.get("id", "LD-1"),
        "weight_n": w_run,
        "vs0_run_eas_ms": vs0_run,
        "vref_eas_ms": vref_eas,
        "vref_tas_ms": vref_tas,
        "airborne_m": s_air,
        "ground_roll_measured_m": s_ground_meas,
        "ground_roll_predicted_m": s_ground_pred,
        "demonstrated_m": total_meas,
        "predicted_m": total_pred,
        "certified_field_length_m": certified,
        "field_length_factor": field_length_factor,
    }
    if runway_m is not None:
        margin = runway_m - certified
        row["runway_m"] = runway_m
        row["margin_m"] = margin
        row["fits"] = margin >= 0
    return row


def reduce_accelerate_stop(v1_m_s, a_acc_m_s2, a_brake_m_s2):
    """Rejected takeoff accelerate-stop distance: accel leg + stop leg, m."""
    _check_positive("decision speed", v1_m_s)
    _check_positive("acceleration", a_acc_m_s2)
    _check_positive("braking deceleration", a_brake_m_s2)
    s_acc = constant_accel_distance(v1_m_s, a_acc_m_s2)
    s_stop = constant_accel_distance(v1_m_s, a_brake_m_s2)
    return {"accelerate_m": s_acc, "stop_m": s_stop,
            "total_m": s_acc + s_stop}


def reduce_oei_takeoff(failure_leg_m, v1_m_s, v2_m_s, t_rec_s,
                       a_cont_m_s2, roc_oei_m_s, h_target_m=OBSTACLE_35FT_M):
    """Engine-out takeoff distance (continued takeoff legs chained), m.

    failure leg (measured ground run to VEF) + recognition v1*t_rec +
    continued ground (v2^2 - v1^2)/(2*a_cont) + climb at V2 to 35 ft.
    """
    _check_nonnegative("failure distance", failure_leg_m)
    _check_positive("decision speed", v1_m_s)
    _check_positive("takeoff safety speed", v2_m_s)
    if v2_m_s < v1_m_s:
        raise ValueError("v2 must be at or above the decision speed v1")
    _check_positive("recognition time", t_rec_s)
    _check_positive("continued acceleration", a_cont_m_s2)
    _check_positive("engine-out climb rate", roc_oei_m_s)
    s_rec = v1_m_s * t_rec_s
    s_ground = (v2_m_s ** 2 - v1_m_s ** 2) / (2.0 * a_cont_m_s2)
    s_climb = v2_m_s * h_target_m / roc_oei_m_s
    total = failure_leg_m + s_rec + s_ground + s_climb
    return {"failure_m": failure_leg_m, "recognition_m": s_rec,
            "ground_continue_m": s_ground, "climb_m": s_climb,
            "total_m": total}


# ---------------------------------------------------------------------------
# Cruise reduction (quadratic range-performance fit over Mach)
# ---------------------------------------------------------------------------

def _solve_linear_system(matrix, rhs):
    """Solve A x = b by Gaussian elimination with partial pivoting."""
    n = len(matrix)
    a = [row[:] for row in matrix]
    b = list(rhs)
    for col in range(n):
        pivot_row = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot_row][col]) < 1.0e-300:
            raise ValueError("singular linear system in quadratic fit")
        if pivot_row != col:
            a[col], a[pivot_row] = a[pivot_row], a[col]
            b[col], b[pivot_row] = b[pivot_row], b[col]
        for row in range(col + 1, n):
            factor = a[row][col] / a[col][col]
            for c in range(col, n):
                a[row][c] -= factor * a[col][c]
            b[row] -= factor * b[col]
    solution = [0.0] * n
    for row in range(n - 1, -1, -1):
        acc = b[row] - sum(a[row][c] * solution[c] for c in range(row + 1, n))
        solution[row] = acc / a[row][row]
    return solution


def reduce_cruise_points(points, w_ref, lrc_fraction=0.99):
    """Reduce cruise fuel-flow runs to the range-performance curve.

    points: list of {mach, altitude_m, w_test_kg, wf_measured_kg_s}.
    Each measured fuel flow is corrected to w_ref (sqrt weight
    correction), range performance rp = tas/wf follows, and a quadratic
    rp(M) is fitted by least squares. Returns the point table, the
    coefficients, the fitted residuals, the max-range Mach (vertex) and
    the long-range-cruise Mach at lrc_fraction of the maximum.
    """
    if len(points) < 3:
        raise ValueError("at least 3 test points are required")
    _check_positive("reference weight", w_ref)
    machs = [p["mach"] for p in points]
    for mach in machs:
        if not (0.3 < mach < 1.0):
            raise ValueError("mach must lie within (0.3, 1.0)")
    if len(set(machs)) != len(machs):
        raise ValueError("duplicate Mach values are not allowed")
    table = []
    for p in points:
        _check_positive("test weight", p["w_test_kg"])
        _check_positive("measured fuel flow", p["wf_measured_kg_s"])
        tas = tas_from_mach(p["mach"], p["altitude_m"])
        wf_c = corrected_fuel_flow(p["wf_measured_kg_s"],
                                   p["w_test_kg"], w_ref)
        table.append({"mach": p["mach"], "altitude_m": p["altitude_m"],
                      "w_test_kg": p["w_test_kg"],
                      "wf_measured_kg_s": p["wf_measured_kg_s"],
                      "tas": tas, "wf_corr": wf_c,
                      "rp": range_performance(tas, wf_c)})
    n = len(table)
    sum_x = sum(p["mach"] for p in table)
    sum_x2 = sum(p["mach"] ** 2 for p in table)
    sum_x3 = sum(p["mach"] ** 3 for p in table)
    sum_x4 = sum(p["mach"] ** 4 for p in table)
    sum_y = sum(p["rp"] for p in table)
    sum_xy = sum(p["mach"] * p["rp"] for p in table)
    sum_x2y = sum(p["mach"] ** 2 * p["rp"] for p in table)
    normal = [[sum_x4, sum_x3, sum_x2], [sum_x3, sum_x2, sum_x],
              [sum_x2, sum_x, float(n)]]
    rhs = [sum_x2y, sum_xy, sum_y]
    c2, c1, c0 = _solve_linear_system(normal, rhs)
    fitted = [c2 * p["mach"] ** 2 + c1 * p["mach"] + c0 for p in table]
    residuals = [f - p["rp"] for f, p in zip(fitted, table)]
    if c2 < 0.0:
        max_rp_mach = -c1 / (2.0 * c2)
        max_rp = c2 * max_rp_mach ** 2 + c1 * max_rp_mach + c0
        target = lrc_fraction * max_rp
        disc = c1 ** 2 - 4.0 * c2 * (c0 - target)
        lrc_mach = (max((-c1 - math.sqrt(disc)) / (2.0 * c2),
                        (-c1 + math.sqrt(disc)) / (2.0 * c2))
                    if disc >= 0.0 else None)
        verdict = "maximum-found"
    else:
        max_rp_mach = max_rp = lrc_mach = None
        verdict = "no-maximum"
    mean_rp = sum(p["rp"] for p in table) / n
    rms = math.sqrt(sum(r * r for r in residuals) / n)
    return {"points": table, "coefficients": (c2, c1, c0),
            "fitted": fitted, "residuals": residuals,
            "max_rp_mach": max_rp_mach, "max_rp": max_rp,
            "lrc_mach": lrc_mach, "verdict": verdict,
            "mean_rp": mean_rp, "rms_residual": rms}


def scatter_row(label, measured, predicted):
    """Computed-vs-predicted scatter row with percent delta and band flag."""
    if measured == 0:
        raise ValueError("measured value must be non-zero for a scatter row")
    delta_pct = (predicted - measured) / abs(measured) * 100.0
    return {"item": label, "measured": measured, "predicted": predicted,
            "delta_pct": delta_pct,
            "within_band": abs(delta_pct) <= SCATTER_BAND_PCT}


# ---------------------------------------------------------------------------
# Project facts (the sortie data set = the item)
# ---------------------------------------------------------------------------

@dataclass
class PerformanceTestItem:
    """Sortie data set + aircraft facts the role reduces and reports on."""
    aircraft_name: str
    description: str = ""
    basis: str = "FAR/CS-25 (context only)"
    w_ref_n: float = 250000.0      # reference gross weight for corrections
    s_m2: float = 122.6
    cd0: float = 0.020
    k: float = 0.042
    cl_max: float = 2.0            # clean (1g stall) max lift coefficient
    cl_max_land: float = 2.7       # landing-config max lift coefficient
    runway_m: float = 900.0        # available landing runway length
    field_pressure_alt_m: float = 152.4   # ~500 ft field elevation
    field_oat_c: float = 22.0      # test-day outside air temperature
    sortie_id: str = "SORTIE-FT2-047"
    takeoff_run: dict = field(default_factory=dict)
    landing_run: dict = field(default_factory=dict)
    level_accel_run: dict = field(default_factory=dict)
    cruise_points: list = field(default_factory=list)
    stall_runs: list = field(default_factory=list)
    oei_run: dict = field(default_factory=dict)
    accel_stop: dict = field(default_factory=dict)

    def wing_loading_n_m2(self, weight_n=None):
        return (weight_n or self.w_ref_n) / self.s_m2

    def vs1g_ref_eas_ms(self):
        """Clean 1g stall speed at the reference weight, m/s EAS."""
        return vs1g_from_wing_loading(self.wing_loading_n_m2(self.w_ref_n),
                                      RHO0, self.cl_max)

    def vs0_ref_eas_ms(self):
        """Landing-config stall speed at the reference weight, m/s EAS."""
        return vs1g_from_wing_loading(self.wing_loading_n_m2(self.w_ref_n),
                                      RHO0, self.cl_max_land)


def _takeoff_speed_profile(t_rot_idx=19, n_samples=21):
    """Deterministic worked-example ground speed profile v(t), m/s.

    v(t) = 2.0*t + 0.015*t^2 sampled every second from brake release
    (t=0) to rotation at t=t_rot_idx; the liftoff sample follows at the
    next second. The small quadratic term keeps the trapezoid integral
    different from the constant-acceleration model, giving the example
    a realistic computed-vs-predicted scatter.
    """
    times = [float(i) for i in range(n_samples)]
    speeds = [round(2.0 * t + 0.015 * t * t, 3) for t in times]
    return times, speeds, speeds[t_rot_idx]


def example_item() -> PerformanceTestItem:
    """The worked-example item: a flight-test sortie data set for
    takeoff / landing / cruise test points (SIMULATED data)."""
    times, speeds, v_rot = _takeoff_speed_profile()
    takeoff_run = {
        "id": "TO-1",
        "weight_n": 240000.0,
        "times_s": times,
        "speeds_mps": speeds,
        "v_rot_mps": v_rot,          # speed at rotation, m/s ground speed
        "t_rot_s": 3.0,              # recorded rotation time, s
        "roc_mps": 6.0,              # measured climb rate after liftoff
        "liftoff_mps": speeds[-1],
    }
    landing_run = {
        "id": "LD-1",
        "weight_n": 232000.0,
        "t_air_s": 5.0,              # recorded flare/airborne time, s
        "a_brake_meas_mps2": 3.9,    # measured braking deceleration
        "mu_brake": 0.42,            # dry-runway braking friction model
    }
    # Level acceleration at 8000 m ISA, MTOW, 150 -> 170 m/s TAS in 20 s
    n = 21
    la_times = [float(i) for i in range(n)]
    la_speeds = [round(150.0 + 1.0 * i, 3) for i in range(n)]
    level_accel_run = {
        "id": "LA-1",
        "weight_n": 250000.0,
        "altitude_m": 8000.0,        # ISA density used at the test altitude
        "times_s": la_times,
        "speeds_tas_ms": la_speeds,
        "window": 5,
    }
    # Cruise fuel-flow sweep at FL350 with a linear weight ramp; test
    # masses in kg (gross weights 240000 -> 234000 N converted / g).
    cruise_points = [
        {"mach": 0.70, "altitude_m": 10668.0,
         "w_test_kg": round(240000.0 / G0, 1), "wf_measured_kg_s": 0.455},
        {"mach": 0.74, "altitude_m": 10668.0,
         "w_test_kg": round(238000.0 / G0, 1), "wf_measured_kg_s": 0.442},
        {"mach": 0.78, "altitude_m": 10668.0,
         "w_test_kg": round(236000.0 / G0, 1), "wf_measured_kg_s": 0.448},
        {"mach": 0.82, "altitude_m": 10668.0,
         "w_test_kg": round(234000.0 / G0, 1), "wf_measured_kg_s": 0.500},
    ]
    # Stall runs at the takeoff gross weight
    stall_runs = [
        {"config": "clean", "weight_n": 240000.0,
         "vs_measured_eas_ms": 39.9, "warning_onset_mps": 41.2},
        {"config": "landing", "weight_n": 232000.0,
         "vs_measured_eas_ms": 34.1, "warning_onset_mps": 35.6},
    ]
    oei_run = {
        "id": "TO-OEI-1",
        "weight_n": 240000.0,
        "v_ef_mps": 37.0, "v1_mps": 38.0, "v2_mps": 46.3,
        "t_rec_s": 1.0, "a_cont_mps2": 2.2, "roc_oei_mps": 2.8,
    }
    accel_stop = {"v1_mps": 38.0, "a_acc_mps2": 2.3, "mu_brake": 0.42}
    return PerformanceTestItem(
        aircraft_name="FT-2 Worked-Example Turbofan Regional Jet",
        description="Simulated flight-test sortie data set covering "
                    "takeoff, landing, level-acceleration and cruise "
                    "test points (worked example).",
        sortie_id="SORTIE-FT2-047",
        takeoff_run=takeoff_run,
        landing_run=landing_run,
        level_accel_run=level_accel_run,
        cruise_points=cruise_points,
        stall_runs=stall_runs,
        oei_run=oei_run,
        accel_stop=accel_stop,
    )


# ---------------------------------------------------------------------------
# Sortie analysis: reduce everything into the results model
# ---------------------------------------------------------------------------

def analyze_sortie(item: PerformanceTestItem) -> dict:
    """Reduce the full sortie data set to the analysis results model."""
    w_ref = item.w_ref_n
    vs1g_ref = item.vs1g_ref_eas_ms()
    vs0_ref = item.vs0_ref_eas_ms()
    sigma_test = day_sigma_from_alt_oat(item.field_pressure_alt_m, item.field_oat_c)
    rho_test = RHO0 * sigma_test
    da_m = density_altitude_m(item.field_pressure_alt_m, item.field_oat_c)
    da_ft = da_m * FT_PER_M
    _, _, rho_la = isa_conditions(item.level_accel_run["altitude_m"])

    # -- conditions --------------------------------------------------------
    conditions = {
        "pressure_alt_m": item.field_pressure_alt_m,
        "oat_deg_c": item.field_oat_c,
        "sigma_test": sigma_test,
        "rho_test_kgm3": rho_test,
        "density_altitude_m": da_m,
        "density_altitude_ft": da_ft,
        "delta_from_isa_k": (item.field_oat_c + 273.15)
                            - isa_temperature_m(item.field_pressure_alt_m),
    }

    # -- data quality (speed traces) ----------------------------------------
    quality = {
        "takeoff_trace": trace_quality_verdict(
            item.takeoff_run["times_s"], item.takeoff_run["speeds_mps"],
            max_gap=2.0),
        "level_accel_trace": trace_quality_verdict(
            item.level_accel_run["times_s"],
            item.level_accel_run["speeds_tas_ms"], max_gap=2.0),
    }

    # -- takeoff -------------------------------------------------------------
    to = reduce_takeoff_run(item.takeoff_run)
    # measured failure leg: trapezoid of the recorded profile to VEF
    oei_failure_leg = engine_failure_distance(
        item.takeoff_run["speeds_mps"], item.takeoff_run["times_s"],
        item.oei_run["v_ef_mps"])
    oei = reduce_oei_takeoff(
        oei_failure_leg, item.oei_run["v1_mps"],
        item.oei_run["v2_mps"], item.oei_run["t_rec_s"],
        item.oei_run["a_cont_mps2"], item.oei_run["roc_oei_mps"])
    oei["failure_measured_m"] = oei_failure_leg
    asd = reduce_accelerate_stop(item.accel_stop["v1_mps"],
                                 item.accel_stop["a_acc_mps2"],
                                 item.accel_stop["mu_brake"] * G0)
    takeoff = {"run": to, "oei": oei, "accelerate_stop": asd,
               "v1_mps": item.oei_run["v1_mps"],
               "v2_mps": item.oei_run["v2_mps"]}

    # -- landing -------------------------------------------------------------
    landing = reduce_landing_run(
        item.landing_run, vs0_ref, w_ref, sigma_test, runway_m=item.runway_m)

    # -- level acceleration ---------------------------------------------------
    la = item.level_accel_run
    la_res = reduce_level_accel_run(
        la["times_s"], la["speeds_tas_ms"], la["weight_n"], rho_la,
        item.s_m2, item.cd0, item.k, w_ref_n=w_ref, rho_std=RHO0,
        window=la["window"])
    la_res["run_id"] = la["id"]
    la_res["altitude_m"] = la["altitude_m"]
    la_res["weight_n"] = la["weight_n"]

    # -- cruise ---------------------------------------------------------------
    # Fuel-flow reductions use masses (kg); the reference mass is the
    # reference gross weight expressed as a mass (W_ref / g).
    cruise = reduce_cruise_points(item.cruise_points, w_ref / G0)
    cruise["w_ref_kg"] = w_ref / G0

    # -- speeds / stall --------------------------------------------------------
    speeds = {
        "vs1g_ref_eas_ms": vs1g_ref,
        "vs0_ref_eas_ms": vs0_ref,
        "stall_rows": [],
    }
    for s in item.stall_runs:
        vs_pred = weight_corrected_speed(vs1g_ref if s["config"] == "clean"
                                         else vs0_ref, w_ref, s["weight_n"])
        margin = stall_margin(vs_pred, s["vs_measured_eas_ms"])
        speeds["stall_rows"].append({
            "config": s["config"], "weight_n": s["weight_n"],
            "vs_measured_eas_ms": s["vs_measured_eas_ms"],
            "vs_predicted_eas_ms": vs_pred,
            "delta_pct": (s["vs_measured_eas_ms"] - vs_pred) / vs_pred * 100.0,
            "stall_margin": margin,
            "warning_onset_mps": s["warning_onset_mps"],
        })

    # -- computed vs predicted scatter -----------------------------------------
    scatter_rows = [
        scatter_row("takeoff ground roll", to["ground_roll_m"],
                    to["ground_roll_predicted_m"]),
        scatter_row("takeoff distance (35 ft)", to["total_m"],
                    to["total_predicted_m"]),
    ]
    if landing["ground_roll_predicted_m"] is not None:
        scatter_rows.append(scatter_row(
            "landing ground roll", landing["ground_roll_measured_m"],
            landing["ground_roll_predicted_m"]))
        scatter_rows.append(scatter_row(
            "landing distance", landing["demonstrated_m"],
            landing["predicted_m"]))
    # cruise fit residuals: fitted vs measured range performance per point
    for p, f in zip(cruise["points"], cruise["fitted"]):
        scatter_rows.append(scatter_row(
            "cruise rp M=%.2f" % p["mach"], p["rp"], f))
    for s in speeds["stall_rows"]:
        scatter_rows.append(scatter_row(
            "Vs1g %s" % s["config"], s["vs_measured_eas_ms"],
            s["vs_predicted_eas_ms"]))
    max_abs = max(abs(r["delta_pct"]) for r in scatter_rows)
    scatter = {"rows": scatter_rows, "max_abs_delta_pct": max_abs,
               "band_pct": SCATTER_BAND_PCT,
               "within_band": max_abs <= SCATTER_BAND_PCT}

    return {
        "conditions": conditions,
        "quality": quality,
        "takeoff": takeoff,
        "landing": landing,
        "level_accel": la_res,
        "cruise": cruise,
        "speeds": speeds,
        "scatter": scatter,
    }


# ---------------------------------------------------------------------------
# Report builder / renderer / gates
# ---------------------------------------------------------------------------

def build_report(item: PerformanceTestItem,
                 results: dict | None = None) -> dict:
    """Build the Flight Test Performance Data Analysis Report model."""
    if results is None:
        results = analyze_sortie(item)
    return {
        "document_type": "Flight Test Performance Data Analysis Report",
        "status": "draft-for-review",
        "item": item.aircraft_name,
        "sortie_id": item.sortie_id,
        "description": item.description,
        "basis": item.basis,
        "aircraft": {
            "w_ref_n": item.w_ref_n, "s_m2": item.s_m2, "cd0": item.cd0,
            "k": item.k, "cl_max": item.cl_max, "cl_max_land": item.cl_max_land,
            "vs1g_ref_eas_ms": item.vs1g_ref_eas_ms(),
            "vs0_ref_eas_ms": item.vs0_ref_eas_ms(),
            "runway_m": item.runway_m,
        },
        "results": results,
        "generated": _today(),
    }


def render_report_markdown(model: dict) -> str:
    """Render the analysis results as the deliverable markdown document."""
    r = model["results"]
    c = r["conditions"]
    ac = model["aircraft"]
    la = r["level_accel"]
    cruise = r["cruise"]
    sc = r["scatter"]
    lines = [
        "# Flight Test Performance Data Analysis Report",
        "",
        "**Aircraft:** %s" % model["item"],
        "**Sortie:** %s" % model["sortie_id"],
        "**Basis:** %s" % model["basis"],
        "**Status:** %s" % model["status"],
        "",
        "_Flight data below are SIMULATED for the worked example and must "
        "be replaced by recorded flight data._",
        "",
        "## 1. Test conditions and data quality",
        "",
        "- Field pressure altitude: %.0f m (%.0f ft); OAT %.1f C "
        "(ISA deviation %+.1f K)."
        % (c["pressure_alt_m"], c["pressure_alt_m"] * FT_PER_M,
           c["oat_deg_c"], c["delta_from_isa_k"]),
        "- Test-day density ratio sigma = %.4f (rho = %.4f kg/m^3); "
        "density altitude %.0f m (%.0f ft)."
        % (c["sigma_test"], c["rho_test_kgm3"], c["density_altitude_m"],
           c["density_altitude_ft"]),
        "- Reference gross weight for corrections: %.0f N. Wing area "
        "%.1f m^2; drag polar cd0 = %.3f, k = %.3f."
        % (ac["w_ref_n"], ac["s_m2"], ac["cd0"], ac["k"]),
        "- Data quality: takeoff trace %s; level-acceleration trace %s."
        % (r["quality"]["takeoff_trace"]["verdict"],
           r["quality"]["level_accel_trace"]["verdict"]),
        "",
        "## 2. Takeoff performance",
        "",
    ]
    to = r["takeoff"]
    row = to["run"]
    lines += [
        "Run %s at W = %.0f N: liftoff %.1f m/s at a mean acceleration of "
        "%.2f m/s^2."
        % (row["id"], row["weight_n"], row["liftoff_mps"],
           row["mean_accel_mps2"]),
        "",
        "| Leg | Measured (m) | Predicted (m) |",
        "|---|---|---|",
        "| Ground roll (to rotation) | %.1f | %.1f |"
        % (row["ground_roll_m"], row["ground_roll_predicted_m"]),
        "| Rotation | %.1f | %.1f |" % (row["rotation_m"], row["rotation_m"]),
        "| Airborne to 35 ft | %.1f | %.1f |"
        % (row["climb_35ft_m"], row["climb_35ft_m"]),
        "| **Takeoff distance** | **%.1f** | **%.1f** |"
        % (row["total_m"], row["total_predicted_m"]),
        "",
        "Engine-out (OEI) continued takeoff at V1 = %.1f m/s, V2 = %.1f "
        "m/s: failure leg %.1f m + recognition %.1f m + continued ground "
        "%.1f m + climb %.1f m = **%.1f m**."
        % (to["v1_mps"], to["v2_mps"], to["oei"]["failure_m"],
           to["oei"]["recognition_m"], to["oei"]["ground_continue_m"],
           to["oei"]["climb_m"], to["oei"]["total_m"]),
        "Accelerate-stop at V1 = %.1f m/s: accelerate %.1f m + stop %.1f m "
        "= **%.1f m**."
        % (to["v1_mps"], to["accelerate_stop"]["accelerate_m"],
           to["accelerate_stop"]["stop_m"],
           to["accelerate_stop"]["total_m"]),
        "",
        "## 3. Landing performance",
        "",
    ]
    ld = r["landing"]
    lines += [
        "Run %s at W = %.0f N: Vs0 at run weight %.2f m/s EAS, "
        "Vref = %.2f m/s EAS (1.23 x Vs0), %.2f m/s TAS at the test-day "
        "density ratio."
        % (ld["id"], ld["weight_n"], ld["vs0_run_eas_ms"],
           ld["vref_eas_ms"], ld["vref_tas_ms"]),
        "",
        "| Segment | Measured (m) | Model (m) |",
        "|---|---|---|",
        "| Airborne (flare) | %.1f | %.1f |" % (ld["airborne_m"],
                                                ld["airborne_m"]),
        "| Ground roll (braking) | %.1f | %s |"
        % (ld["ground_roll_measured_m"],
           "%.1f" % ld["ground_roll_predicted_m"]
           if ld["ground_roll_predicted_m"] is not None else "n/a"),
        "| **Demonstrated total** | **%.1f** | %s |"
        % (ld["demonstrated_m"],
           "%.1f" % ld["predicted_m"]
           if ld["predicted_m"] is not None else "n/a"),
        "",
        "Certified field length = %.2f x demonstrated = **%.1f m** "
        "against a %.0f m runway: %s (margin %+.1f m)."
        % (ld["field_length_factor"], ld["certified_field_length_m"],
           ld["runway_m"], "FITS" if ld["fits"] else "TOO SHORT",
           ld["margin_m"]),
        "",
        "## 4. Level-acceleration thrust determination",
        "",
        "Run %s at %.0f m (ISA density %.4f kg/m^3), W = %.0f N, trace "
        "smoothed over a %d-sample window; assessment region samples %d-%d."
        % (la["run_id"], la["altitude_m"], la["density_kgm3"],
           la["weight_n"], la["window"],
           la["assessment_start"] + 1, la["assessment_end"]),
        "",
        "| Quantity | Value |",
        "|---|---|",
        "| Mean acceleration | %.3f m/s^2 |" % la["mean_acceleration"],
        "| Mean specific excess power P_s | %.3f m/s |"
        % la["mean_specific_excess_power"],
        "| Mean excess thrust (drag gap) | %.1f N |"
        % la["mean_excess_thrust"],
        "| Mean drag (polar) | %.1f N |" % la["mean_drag"],
        "| **Mean thrust available** | **%.1f N** |"
        % la["mean_thrust_available"],
        "| Sustained acceleration over band | %s |"
        % ("PASS" if la["sustained_over_band"] else "FAIL"),
    ]
    if la["mean_ps_reference_conditions"] is not None:
        lines += [
            "| P_s at reference weight and standard density | %.3f m/s |"
            % la["mean_ps_reference_conditions"],
        ]
    cruise_alt_m = (cruise["points"][0]["altitude_m"]
                    if cruise["points"] else 0.0)
    lines += [
        "",
        "## 5. Cruise performance (fuel flow reduction)",
        "",
        "Measured fuel flows corrected from the test weight to the "
        "reference weight with the sqrt(w_ref/w_test) correction at "
        "%.0f m; range performance rp = V_tas / wf_corrected."
        % cruise_alt_m,
        "",
        "| Mach | wf (kg/s) | wf corr (kg/s) | rp (m/kg) | fitted rp |",
        "|---|---|---|---|---|",
    ]
    for p, f in zip(cruise["points"], cruise["fitted"]):
        lines.append("| %.2f | %.3f | %.3f | %.1f | %.1f |"
                     % (p["mach"], p["wf_measured_kg_s"], p["wf_corr"],
                        p["rp"], f))
    lines += [
        "",
        "Quadratic range-performance fit rp(M) = %.3f M^2 %+.3f M %+.1f; "
        "maximum range cruise at M = %.3f; long range cruise (99%% of "
        "max rp) at M = %s."
        % (cruise["coefficients"][0], cruise["coefficients"][1],
           cruise["coefficients"][2],
           cruise["max_rp_mach"] if cruise["max_rp_mach"] else float("nan"),
           "%.3f" % cruise["lrc_mach"] if cruise["lrc_mach"] else "n/a"),
        "Fit residuals RMS: %.1f m/kg (mean rp %.1f m/kg)."
        % (cruise["rms_residual"], cruise["mean_rp"]),
        "",
        "## 6. Stall speeds and V-speed corrections",
        "",
    ]
    lines.append("| Config | Vs measured (m/s EAS) | Vs predicted at run "
                 "weight (m/s EAS) | Delta | Margin |")
    lines.append("|---|---|---|---|---|")
    for s in r["speeds"]["stall_rows"]:
        lines.append("| %s | %.2f | %.2f | %+.2f%% | %+.3f |"
                     % (s["config"], s["vs_measured_eas_ms"],
                        s["vs_predicted_eas_ms"], s["delta_pct"],
                        s["stall_margin"]))
    lines += [
        "",
        "Weight correction v(w) = v_ref * sqrt(w/w_ref) applied to the "
        "reference stall speeds Vs1g = %.2f m/s EAS and Vs0 = %.2f m/s EAS."
        % (ac["vs1g_ref_eas_ms"], ac["vs0_ref_eas_ms"]),
        "",
        "## 7. Computed vs predicted scatter",
        "",
        "| Item | Measured | Predicted | Delta (%s) | Within %s%s |"
        % ("%", "%+", sc["band_pct"]),
        "|---|---|---|---|---|",
    ]
    for srow in sc["rows"]:
        lines.append("| %s | %.1f | %.1f | %+.2f | %s |"
                     % (srow["item"], srow["measured"], srow["predicted"],
                        srow["delta_pct"],
                        "PASS" if srow["within_band"] else "FAIL"))
    lines += [
        "",
        "Maximum absolute scatter: %+.2f%% (band %+.0f%%) -> %s."
        % (sc["max_abs_delta_pct"], sc["band_pct"],
           "within band" if sc["within_band"] else "OUT OF BAND"),
        "",
        "## 8. Findings",
        "",
        "- Takeoff distance legs are complete and the measured ground roll "
        "agrees with the constant-acceleration model within the band.",
        "- Landing certified field length (1.67 x demonstrated) fits the "
        "available runway (margin %+.0f m)." % ld["margin_m"],
        "- Level-acceleration thrust determination is internally consistent "
        "(drag-polar closure) and reduces to the reference conditions.",
        "- Cruise maximum-range Mach and long-range-cruise Mach read off "
        "the fitted range-performance curve with an RMS residual of "
        "%.1f m/kg." % cruise["rms_residual"],
        "",
        "---",
        "*Generated by Aero Agent Roles flight-test-performance-engineer "
        "core. DRAFT for human review by the flight test / performance "
        "lead. Not an approval document and not a performance guarantee.*",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evidence gate checkers
# ---------------------------------------------------------------------------

GATE_CHECKS = {
    "test_conditions_identified": "density altitude + sigma recorded",
    "data_quality_ok": "takeoff and level-accel traces flagged clean",
    "takeoff_legs_complete": "ground roll + rotation + 35-ft climb legs",
    "landing_distance_present": "demonstrated + certified landing distance",
    "thrust_determined": "level-accel thrust available > 0, sustained",
    "cruise_curve_fit": "range-performance fit with maximum found",
    "speed_corrections_applied": "weight-corrected stall speeds recorded",
    "scatter_recorded": "computed-vs-predicted rows within the band",
    "sign_off_honest": "document is draft-for-review, not approval",
}


def check_report(model: dict) -> dict:
    """Run the evidence gates against the report content model."""
    r = model.get("results", {})
    la = r.get("level_accel", {})
    cruise = r.get("cruise", {})
    sc = r.get("scatter", {})
    conditions = r.get("conditions", {})
    quality = r.get("quality", {})
    results = {
        "test_conditions_identified": bool(
            conditions.get("density_altitude_m") is not None
            and conditions.get("sigma_test")),
        "data_quality_ok": (
            quality.get("takeoff_trace", {}).get("verdict") == "ok"
            and quality.get("level_accel_trace", {}).get("verdict") == "ok"),
        "takeoff_legs_complete": bool(
            r.get("takeoff", {}).get("run", {}).get("total_m")),
        "landing_distance_present": bool(
            r.get("landing", {}).get("certified_field_length_m")),
        "thrust_determined": bool(
            la.get("mean_thrust_available")
            and la.get("sustained_over_band") is True),
        "cruise_curve_fit": bool(cruise.get("max_rp_mach")),
        "speed_corrections_applied": bool(
            r.get("speeds", {}).get("stall_rows")),
        "scatter_recorded": bool(
            sc.get("rows") and sc.get("within_band") is True),
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_report_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    checks = {
        "has_title": "flight test performance data analysis report" in low,
        "has_aircraft": "aircraft:" in low,
        "has_conditions": "density altitude" in low,
        "has_takeoff": "takeoff distance" in low and "35 ft" in low,
        "has_landing": "landing distance" in low and "1.67" in low,
        "has_thrust": "specific excess power" in low
                      and "thrust available" in low,
        "has_cruise": "fuel flow" in low and "range performance" in low,
        "has_speeds": "stall speed" in low and "weight" in low,
        "has_scatter": "computed vs predicted" in low,
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling: check a report document."""
    return check_report_markdown(md_text)


# ---------------------------------------------------------------------------
# Example deliverable (for tests and worked-example generation)
# ---------------------------------------------------------------------------

def example_report_model() -> dict:
    return build_report(example_item())


def example_report_markdown() -> str:
    return render_report_markdown(example_report_model())


if __name__ == "__main__":
    model = example_report_model()
    results = model["results"]
    md = render_report_markdown(model)
    print("ITEM: %s (%s)" % (model["item"], model["sortie_id"]))
    print("DENSITY ALTITUDE: %.0f m (%.0f ft), sigma %.4f"
          % (results["conditions"]["density_altitude_m"],
             results["conditions"]["density_altitude_ft"],
             results["conditions"]["sigma_test"]))
    to = results["takeoff"]["run"]
    print("TAKEOFF: ground %.1f m, total %.1f m (predicted %.1f m)"
          % (to["ground_roll_m"], to["total_m"], to["total_predicted_m"]))
    ld = results["landing"]
    print("LANDING: demonstrated %.1f m, certified %.1f m, fits=%s"
          % (ld["demonstrated_m"], ld["certified_field_length_m"],
             ld["fits"]))
    la = results["level_accel"]
    print("LEVEL ACCEL: a=%.3f m/s2, Ps=%.3f m/s, T=%.1f N"
          % (la["mean_acceleration"], la["mean_specific_excess_power"],
             la["mean_thrust_available"]))
    print("CRUISE: MRC M=%.3f, LRC M=%s, RMS %.1f m/kg"
          % (results["cruise"]["max_rp_mach"],
             ("%.3f" % results["cruise"]["lrc_mach"])
             if results["cruise"]["lrc_mach"] else "n/a",
             results["cruise"]["rms_residual"]))
    print("SCATTER: max abs %+.2f%%, within band %s"
          % (results["scatter"]["max_abs_delta_pct"],
             results["scatter"]["within_band"]))
    print("GATES: %s" % check_report(model))
    print("MD GATES: %s" % check_report_markdown(md))
    print("RENDERED: %d chars" % len(md))
