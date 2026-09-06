#!/usr/bin/env python3
"""stability_control_flight_test_core.py - Stability and Control Flight
Test Engineer executable core.

This is the role's ENGINE: given the measured stability and control
flight test records of an airplane it reduces them into the Stability
and Control Flight Test Report content - static longitudinal stability
(trim curve slope, stick fixed/free neutral points, static margin,
elevator angle per g), dynamic stability (mode excitation, log
decrement, damping ratio, damped/undamped frequencies, time to half
amplitude, handling-qualities verdicts per band), static
lateral-directional stability from the steady-heading sideslip sweep
(rudder/aileron/pedal-force gradients, signed Cn_beta and Cl_beta
estimates, weathercock/dihedral verdicts), and longitudinal control
forces (transducer calibration, stick force gradient, stick force per
g, breakout force, control centering) - and BUILDS the report. It also
gate-checks deliverables. Standalone: no external repo needed.

Every number produced here comes from a REAL rule in the bound
AeroSkills leaves under /skills/flight-test-operations/stability/
(static-stability-flight-test, dynamic-stability-flight-test,
lateral-directional-stability-flight-test, control-force-flight-test)
or from the public FAR-25/CS-25 demonstration context those leaves
paraphrase (summary-not-copy; no regulation text is reproduced):
  CL = 2 W / (rho V^2 S); trim curve delta_e = a + b CL by least
  squares; h_n = h + b Cm_delta_e (pi/180), SM = h_n - h; stick free
  shift (Cm_delta_e Ch_alpha)/(CL_alpha Ch_delta_e); elevator angle
  per g d(delta_e)/dn = (180/pi) CL SM / Cm_delta_e; log decrement
  delta = (1/n) ln(A0/An); zeta = delta/sqrt(delta^2 + 4 pi^2);
  w_d = 2 pi / T_d; w_n = w_d/sqrt(1 - zeta^2); t_half = ln(2)/(zeta
  w_n); Cn_beta_est = -cn_dr s_r; Cl_beta_est = -cl_da s_a;
  breakout = (pull - push)/2; margin = limit - residual. Practice band
  values (short period 0.3-2.0 acceptable ... spiral convergent) are
  typical flight test practice per the leaves; certification criteria
  in the cited standards take precedence.
"""
from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass, field
from datetime import date

DEG_PER_RAD = 180.0 / math.pi
RAD_PER_DEG = math.pi / 180.0
TWO_PI = 2.0 * math.pi
LN2 = math.log(2.0)
NEUTRAL_TOL = 1e-9


def _today() -> str:
    return os.environ.get("ROLE_GEN_DATE", date.today().isoformat())


# ---------------------------------------------------------------------------
# Domain tables (real rules from the bound flight-test-operations/stability
# leaves; practice bands - certification values in FAR/CS take precedence)
# ---------------------------------------------------------------------------

# Dynamic stability: mode -> recommended excitation (leaf EXCITATION_TECHNIQUES).
EXCITATION_TECHNIQUES = {
    "short-period": {
        "control": "elevator",
        "technique": "elevator doublet (push-pull-push) or pulse",
        "amplitude": "small, 1 to 2 degrees",
        "notes": "excite the pitch short period without engaging the phugoid; "
                 "release and record the decaying oscillation",
    },
    "phugoid": {
        "control": "elevator",
        "technique": "elevator pulse or push-pull step",
        "amplitude": "small speed change, 5 to 10 knots",
        "notes": "hold a small pitch disturbance, then hands-off; the phugoid "
                 "period is long, record 2 to 3 full cycles",
    },
    "dutch-roll": {
        "control": "rudder",
        "technique": "rudder pulse or rudder doublet",
        "amplitude": "1 to 2 degrees rudder",
        "notes": "wings level, excite yaw; record the coupled roll-yaw "
                 "oscillation until it damps",
    },
    "roll-subsidence": {
        "control": "aileron",
        "technique": "aileron step input",
        "amplitude": "small step, one third to one half aileron",
        "notes": "step, hold, release; the roll mode is aperiodic, estimate "
                 "the time constant from the exponential decay",
    },
    "spiral": {
        "control": "rudder",
        "technique": "rudder step, hold a small bank angle",
        "amplitude": "small step",
        "notes": "establish a small bank angle, release controls; observe "
                 "convergence or divergence over 20 to 30 seconds",
    },
}

# Dynamic stability: mode -> handling-qualities verdict bands by damping
# ratio (typical flight test practice per the leaf VERDICT_BANDS).
VERDICT_BANDS = {
    "short-period": (
        (2.0, 2.0, "acceptable", "aperiodic, heavily damped, no oscillation"),
        (0.3, 2.0, "acceptable", "well damped"),
        (0.08, 0.3, "marginal", "lightly damped, review the band"),
        (None, 0.08, "inadequate", "poorly damped"),
    ),
    "phugoid": (
        (0.04, 2.0, "acceptable", "positively damped"),
        (0.0, 0.04, "marginal", "near neutral, review the band"),
        (None, 0.0, "inadequate", "neutral or divergent"),
    ),
    "dutch-roll": (
        (0.08, 2.0, "acceptable", "positively damped"),
        (0.02, 0.08, "marginal", "lightly damped, review the band"),
        (None, 0.02, "inadequate", "near neutral or divergent"),
    ),
    "roll-subsidence": (
        (1.0, 2.0, "acceptable", "aperiodic convergence as expected"),
        (None, 1.0, "marginal", "oscillatory roll mode, investigate"),
    ),
    "spiral": (
        (0.0, 2.0, "acceptable", "convergent"),
        (None, 0.0, "inadequate", "divergent, time to double applies"),
    ),
}

# Static lateral-directional stability: declared sideslip test envelope.
BETA_SWEEP_MIN = 2
BETA_SWEEP_MAX = 40
SIDESLIP_LIMIT_DEG = 15.0

# Longitudinal control force verdict strings (pull forces positive).
STABLE_GRADIENT = "stable-gradient"
UNSTABLE_GRADIENT = "unstable-gradient"
CENTERED = "centered"
EXCEEDS_LIMIT = "exceeds-limit"


# ---------------------------------------------------------------------------
# Static longitudinal stability (leaf: static-stability-flight-test)
# ---------------------------------------------------------------------------


def _require_positive(value, name):
    if value <= 0:
        raise ValueError("%s must be > 0, got %r" % (name, value))


def _require_finite(value, name):
    if not math.isfinite(value):
        raise ValueError("%s must be finite, got %r" % (name, value))


def lift_coefficients(speeds_m_s, weight_n, wing_area_m2, rho_kg_m3):
    """Lift coefficient CL = 2 W / (rho V^2 S) per trimmed speed, list."""
    _require_positive(weight_n, "weight")
    _require_positive(wing_area_m2, "wing area")
    _require_positive(rho_kg_m3, "density")
    if not isinstance(speeds_m_s, (list, tuple)) or len(speeds_m_s) == 0:
        raise ValueError("speeds must be a non-empty list or tuple")
    cl = []
    for v in speeds_m_s:
        _require_finite(v, "speed")
        _require_positive(v, "speed")
        cl.append(2.0 * weight_n / (rho_kg_m3 * wing_area_m2 * v * v))
    return cl


def least_squares_fit(xs, ys):
    """Least squares line y = a + b x over paired samples, dict.

    Identical closed-form math to the leaf logic (slope = Sxy/Sxx,
    intercept = y_mean - slope*x_mean, r_squared = 1 - SSres/SStot).
    """
    if not isinstance(xs, (list, tuple)) or not isinstance(ys, (list, tuple)):
        raise ValueError("xs and ys must be lists or tuples")
    if len(xs) != len(ys):
        raise ValueError("xs length %d != ys length %d" % (len(xs), len(ys)))
    if len(xs) < 2:
        raise ValueError("need at least 2 points, got %d" % len(xs))
    for x, y in zip(xs, ys):
        _require_finite(x, "x")
        _require_finite(y, "y")
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    s_xx = sum((x - mean_x) ** 2 for x in xs)
    if s_xx == 0.0:
        raise ValueError("zero x variance: cannot fit a slope")
    s_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = s_xy / s_xx
    intercept = mean_y - slope * mean_x
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    if ss_tot == 0.0:
        r_squared = 1.0 if ss_res == 0.0 else 0.0
    else:
        r_squared = 1.0 - ss_res / ss_tot
    return {"slope": slope, "intercept": intercept,
            "r_squared": r_squared, "n": n}


def trim_curve_fit(elevator_deg, speeds_m_s, weight_n, wing_area_m2,
                   rho_kg_m3):
    """Fit the trim curve elevator angle versus lift coefficient, dict.

    Converts each trimmed speed to CL and fits delta_e = a + b CL.
    A negative slope b = d(delta_e)/dCL is the signature of a
    statically stable aircraft (less up elevator as speed increases).
    """
    if not isinstance(elevator_deg, (list, tuple)):
        raise ValueError("elevator_deg must be a list or tuple")
    cl = lift_coefficients(speeds_m_s, weight_n, wing_area_m2, rho_kg_m3)
    if len(cl) != len(elevator_deg):
        raise ValueError("elevator_deg length %d != speeds length %d"
                         % (len(elevator_deg), len(cl)))
    for e in elevator_deg:
        _require_finite(e, "elevator angle")
    fit = least_squares_fit(cl, elevator_deg)
    return {
        "speeds_m_s": list(speeds_m_s),
        "lift_coefficients": cl,
        "elevator_deg": list(elevator_deg),
        "slope_deg_per_cl": fit["slope"],
        "intercept_deg": fit["intercept"],
        "r_squared": fit["r_squared"],
        "n": fit["n"],
        "mean_cl": sum(cl) / len(cl),
        "mean_speed_m_s": sum(speeds_m_s) / len(speeds_m_s),
    }


def stick_fixed_neutral_point(slope_deg_per_cl, cg_fraction_mac,
                              cm_delta_e_per_rad):
    """Stick fixed neutral point and static margin from the slope, dict.

    h_n = h + b Cm_delta_e (pi/180) and SM = h_n - h. Positive margin
    stable, negative unstable (flag), zero neutral. Cm_delta_e is the
    elevator control power per radian (negative for a conventional
    elevator).
    """
    if cm_delta_e_per_rad == 0:
        raise ValueError("cm_delta_e must be non-zero, got 0")
    if not (0.0 < cg_fraction_mac < 1.0):
        raise ValueError("cg_fraction_mac must be in (0, 1), got %r"
                         % (cg_fraction_mac,))
    shift = slope_deg_per_cl * RAD_PER_DEG * cm_delta_e_per_rad
    neutral_point = cg_fraction_mac + shift
    margin = neutral_point - cg_fraction_mac
    if margin > NEUTRAL_TOL:
        verdict = "stable"
        note = "positive static margin, statically stable stick fixed"
    elif margin < -NEUTRAL_TOL:
        verdict = "unstable"
        note = "negative static margin, statically unstable stick fixed, flag"
    else:
        verdict = "neutral"
        note = "static margin near zero, neutrally stable stick fixed"
    return {"neutral_point_fraction_mac": neutral_point,
            "static_margin_fraction_mac": margin,
            "shift_fraction_mac": shift,
            "verdict": verdict,
            "note": note}


def stick_free_neutral_point(neutral_point_fixed_fraction_mac,
                             cg_fraction_mac, cm_delta_e_per_rad,
                             ch_alpha_per_rad, ch_delta_e_per_rad,
                             cl_alpha_per_rad):
    """Stick free neutral point from the free elevator hinge model, dict.

    With the elevator free the neutral point shifts forward of the
    stick fixed value by (Cm_delta_e Ch_alpha)/(CL_alpha Ch_delta_e).
    """
    if ch_delta_e_per_rad == 0:
        raise ValueError("ch_delta_e must be non-zero, got 0")
    if cl_alpha_per_rad <= 0:
        raise ValueError("cl_alpha must be > 0, got %r" % (cl_alpha_per_rad,))
    shift = (cm_delta_e_per_rad * ch_alpha_per_rad) / (
        cl_alpha_per_rad * ch_delta_e_per_rad)
    neutral_point = neutral_point_fixed_fraction_mac - shift
    margin = neutral_point - cg_fraction_mac
    if margin > NEUTRAL_TOL:
        verdict = "stable"
    elif margin < -NEUTRAL_TOL:
        verdict = "unstable"
    else:
        verdict = "neutral"
    return {"neutral_point_fraction_mac": neutral_point,
            "static_margin_fraction_mac": margin,
            "shift_fraction_mac": shift,
            "verdict": verdict}


def elevator_angle_per_g(cl_1g, static_margin_fraction_mac,
                         cm_delta_e_per_rad):
    """Elevator angle per g from the linear trim model, dict.

    d(delta_e)/dn = (180/pi) CL SM / Cm_delta_e in deg per g. The
    value is negative (trailing-edge-up elevator with increasing load
    factor) for a statically stable aircraft.
    """
    _require_positive(cl_1g, "cl_1g")
    if cm_delta_e_per_rad == 0:
        raise ValueError("cm_delta_e must be non-zero, got 0")
    value = (DEG_PER_RAD * cl_1g * static_margin_fraction_mac) \
        / cm_delta_e_per_rad
    magnitude = abs(value)
    if value < -NEUTRAL_TOL:
        assessment = ("elevator moves trailing-edge-up with increasing load "
                      "factor, consistent with a statically stable aircraft")
    elif value > NEUTRAL_TOL:
        assessment = ("elevator moves trailing-edge-down with increasing load "
                      "factor, review the static stability verdict")
    else:
        assessment = "no elevator movement per g, neutrally stable"
    return {"value_deg_per_g": value,
            "magnitude_deg_per_g": magnitude,
            "assessment": assessment}


def static_stability_report(elevator_deg, speeds_m_s, weight_n,
                            wing_area_m2, rho_kg_m3, cg_fraction_mac,
                            cm_delta_e_per_rad, ch_alpha_per_rad=None,
                            ch_delta_e_per_rad=None, cl_alpha_per_rad=None,
                            cl_1g=None):
    """Full static longitudinal stability reduction, dict.

    Chains trim_curve_fit, stick_fixed_neutral_point and, when the
    hinge-moment coefficients are supplied, stick_free_neutral_point,
    plus elevator_angle_per_g when cl_1g is supplied. Returns the fit,
    the stick fixed result, optional stick free / elevator-per-g
    results, and the stick fixed verdict.
    """
    fit = trim_curve_fit(elevator_deg, speeds_m_s, weight_n, wing_area_m2,
                         rho_kg_m3)
    fixed = stick_fixed_neutral_point(fit["slope_deg_per_cl"],
                                      cg_fraction_mac, cm_delta_e_per_rad)
    report = {"fit": fit, "stick_fixed": fixed, "stick_free": None,
              "elevator_angle_per_g": None, "verdict": fixed["verdict"]}
    if (ch_alpha_per_rad is not None and ch_delta_e_per_rad is not None
            and cl_alpha_per_rad is not None):
        report["stick_free"] = stick_free_neutral_point(
            fixed["neutral_point_fraction_mac"], cg_fraction_mac,
            cm_delta_e_per_rad, ch_alpha_per_rad, ch_delta_e_per_rad,
            cl_alpha_per_rad)
    if cl_1g is not None:
        report["elevator_angle_per_g"] = elevator_angle_per_g(
            cl_1g, fixed["static_margin_fraction_mac"], cm_delta_e_per_rad)
    return report


# ---------------------------------------------------------------------------
# Dynamic stability (leaf: dynamic-stability-flight-test)
# ---------------------------------------------------------------------------


def log_decrement(first_amplitude, last_amplitude, cycles):
    """Log decrement delta = (1/n) ln(A0/An), dimensionless.

    A0 and An are same-sign peak amplitudes n whole cycles apart.
    """
    if cycles < 1:
        raise ValueError("cycles must be >= 1, got %r" % (cycles,))
    if first_amplitude <= 0:
        raise ValueError("first amplitude must be > 0, got %r"
                         % (first_amplitude,))
    if last_amplitude <= 0:
        raise ValueError("last amplitude must be > 0, got %r"
                         % (last_amplitude,))
    if last_amplitude >= first_amplitude:
        if last_amplitude == first_amplitude:
            raise ValueError("amplitudes equal: no decay measured")
        raise ValueError("last amplitude exceeds first: mode is not decaying")
    return math.log(first_amplitude / last_amplitude) / cycles


def damping_ratio_from_decrement(delta):
    """Damping ratio zeta = delta / sqrt(delta^2 + 4 pi^2), dimensionless."""
    if delta < 0:
        raise ValueError("log decrement must be >= 0, got %r" % (delta,))
    return delta / math.sqrt(delta * delta + TWO_PI * TWO_PI)


def damped_frequency_from_period(period_seconds):
    """Damped natural frequency, rad/s and Hz, from the peak period T_d."""
    if period_seconds <= 0:
        raise ValueError("peak period must be > 0, got %r" % (period_seconds,))
    rad = TWO_PI / period_seconds
    return {"damped_frequency_rad_s": rad,
            "damped_frequency_hz": rad / TWO_PI}


def undamped_natural_frequency(damped_frequency_rad_s, damping_ratio):
    """Undamped natural frequency w_n = w_d / sqrt(1 - zeta^2), rad/s."""
    if damped_frequency_rad_s <= 0:
        raise ValueError("damped frequency must be > 0, got %r"
                         % (damped_frequency_rad_s,))
    if damping_ratio >= 1.0:
        raise ValueError("damping ratio must be < 1 for an oscillatory mode, "
                         "got %r" % (damping_ratio,))
    return damped_frequency_rad_s \
        / math.sqrt(1.0 - damping_ratio * damping_ratio)


def time_to_half_amplitude(damping_ratio, undamped_frequency_rad_s):
    """Time to half amplitude t_half = ln(2) / (zeta w_n), seconds."""
    if damping_ratio <= 0:
        raise ValueError("damping ratio must be > 0, got %r"
                         % (damping_ratio,))
    if undamped_frequency_rad_s <= 0:
        raise ValueError("undamped frequency must be > 0, got %r"
                         % (undamped_frequency_rad_s,))
    return LN2 / (damping_ratio * undamped_frequency_rad_s)


def time_to_double_amplitude(damping_ratio, undamped_frequency_rad_s):
    """Time to double amplitude t_double = ln(2) / (|zeta| w_n), seconds."""
    if damping_ratio >= 0:
        raise ValueError("damping ratio must be < 0 for a divergent mode, "
                         "got %r" % (damping_ratio,))
    if undamped_frequency_rad_s <= 0:
        raise ValueError("undamped frequency must be > 0, got %r"
                         % (undamped_frequency_rad_s,))
    return LN2 / (abs(damping_ratio) * undamped_frequency_rad_s)


def cycles_to_half_amplitude(damping_ratio):
    """Cycles to half amplitude N = ln(2) / (2 pi zeta), dimensionless."""
    if damping_ratio <= 0:
        raise ValueError("damping ratio must be > 0, got %r"
                         % (damping_ratio,))
    return LN2 / (TWO_PI * damping_ratio)


def mode_identification(peak_values, peak_times):
    """Identify a mode from the decaying same-sign peak sequence, dict.

    n = len(peak_values) - 1 cycles; log decrement, damping ratio and
    mean peak period feed the damped/undamped frequencies and the time
    to half amplitude.
    """
    if len(peak_values) < 2:
        raise ValueError("need at least 2 peaks, got %d" % len(peak_values))
    if len(peak_times) != len(peak_values):
        raise ValueError("peak_times length %d != peak_values length %d"
                         % (len(peak_times), len(peak_values)))
    times = list(peak_times)
    if any(t2 <= t1 for t1, t2 in zip(times, times[1:])):
        raise ValueError("peak times must be strictly ascending")
    cycles = len(peak_values) - 1
    delta = log_decrement(peak_values[0], peak_values[-1], cycles)
    zeta = damping_ratio_from_decrement(delta)
    period = (times[-1] - times[0]) / cycles
    damped = damped_frequency_from_period(period)
    undamped = None
    t_half = None
    if zeta < 1.0:
        undamped = undamped_natural_frequency(
            damped["damped_frequency_rad_s"], zeta)
        t_half = time_to_half_amplitude(zeta, undamped)
    return {
        "decrement": delta,
        "damping_ratio": zeta,
        "period_s": period,
        "damped_frequency_hz": damped["damped_frequency_hz"],
        "damped_frequency_rad_s": damped["damped_frequency_rad_s"],
        "undamped_frequency_rad_s": undamped,
        "time_to_half_s": t_half,
        "cycles_used": cycles,
    }


def excitation_technique(mode):
    """Recommended excitation for a mode (control, technique, amplitude)."""
    try:
        return dict(EXCITATION_TECHNIQUES[mode])
    except KeyError:
        raise ValueError("unknown mode %r; expected one of %s"
                         % (mode, ", ".join(sorted(EXCITATION_TECHNIQUES))))


def handling_qualities_verdict(mode, damping_ratio):
    """Handling qualities verdict for a measured mode damping, dict."""
    if mode not in VERDICT_BANDS:
        raise ValueError("unknown mode %r; expected one of %s"
                         % (mode, ", ".join(sorted(VERDICT_BANDS))))
    for low, high, verdict, note in VERDICT_BANDS[mode]:
        if low is None:
            if damping_ratio < high:
                return {"mode": mode, "damping_ratio": damping_ratio,
                        "band": "below %g" % high, "verdict": verdict,
                        "note": note}
        elif high == low:
            if damping_ratio > low:
                return {"mode": mode, "damping_ratio": damping_ratio,
                        "band": "above %g" % low, "verdict": verdict,
                        "note": note}
        elif low <= damping_ratio <= high:
            return {"mode": mode, "damping_ratio": damping_ratio,
                    "band": "%g to %g" % (low, high), "verdict": verdict,
                    "note": note}
    top_verdict = VERDICT_BANDS[mode][0]
    return {"mode": mode, "damping_ratio": damping_ratio,
            "band": "above %g" % top_verdict[1],
            "verdict": top_verdict[2], "note": top_verdict[3]}


# ---------------------------------------------------------------------------
# Static lateral-directional stability (leaf:
# lateral-directional-stability-flight-test) - steady-heading sideslip
# ---------------------------------------------------------------------------

# Sign convention (documented in the leaf): beta positive = nose LEFT of
# the velocity vector; delta_r positive = right pedal; delta_a positive =
# right aileron (left roll). A directionally stable aircraft shows a
# POSITIVE rudder gradient s_r; a laterally stable aircraft (dihedral
# effect) a NEGATIVE aileron gradient s_a. The deg/deg gradient ratios
# are unitless and numerically equal to rad/rad, so the signed estimates
# Cn_beta_est = -cn_dr * s_r and Cl_beta_est = -cl_da * s_a come out in
# /rad directly.


def fit_slope(xs, ys):
    """Return dy/dx from a two-parameter (offset + slope) least squares fit."""
    if len(xs) != len(ys):
        raise ValueError("xs and ys must have equal length")
    if len(xs) < BETA_SWEEP_MIN:
        raise ValueError("need at least %d points for a slope fit"
                         % BETA_SWEEP_MIN)
    n = len(xs)
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    s_xy = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    s_xx = sum((x - x_mean) ** 2 for x in xs)
    if s_xx == 0.0:
        raise ValueError("zero x variance: cannot fit a slope to vertical "
                         "points")
    return s_xy / s_xx


def rudder_gradient(beta_deg, delta_r_deg):
    """Fit the rudder deflection gradient s_r = d(delta_r)/d(beta), deg/deg."""
    return fit_slope(beta_deg, delta_r_deg)


def aileron_gradient(beta_deg, delta_a_deg):
    """Fit the aileron deflection gradient s_a = d(delta_a)/d(beta), deg/deg."""
    return fit_slope(beta_deg, delta_a_deg)


def pedal_force_gradient(beta_deg, pedal_force_N):
    """Fit the pedal-force gradient g_p = d(F_pedal)/d(beta), N/deg.

    Taken from the rudder-free run: the force the pilot must apply to
    hold each sideslip angle.
    """
    return fit_slope(beta_deg, pedal_force_N)


def signed_directional_estimate(cn_dr_per_rad, rudder_gradient_per_deg):
    """Directional stability estimate Cn_beta = -cn_dr * s_r, /rad."""
    if cn_dr_per_rad == 0.0:
        raise ValueError("rudder control power cn_dr must be non-zero")
    return -cn_dr_per_rad * rudder_gradient_per_deg


def signed_lateral_estimate(cl_da_per_rad, aileron_gradient_per_deg):
    """Lateral stability estimate Cl_beta = -cl_da * s_a, /rad."""
    if cl_da_per_rad == 0.0:
        raise ValueError("aileron control power cl_da must be non-zero")
    return -cl_da_per_rad * aileron_gradient_per_deg


def weathercock_verdict(cn_beta_est_per_rad):
    """Directional (weathercock) stability verdict: stable when > 0."""
    return "stable" if cn_beta_est_per_rad > 0.0 else "unstable"


def dihedral_verdict(cl_beta_est_per_rad):
    """Lateral (dihedral) stability verdict: stable when < 0."""
    return "stable" if cl_beta_est_per_rad < 0.0 else "unstable"


def build_sideslip_matrix(beta_targets_deg, cas_ms, altitude_m):
    """Build the sideslip sweep test matrix rows inside the +-15 deg limit."""
    if cas_ms <= 0.0:
        raise ValueError("calibrated airspeed must be positive")
    rows = []
    for target in beta_targets_deg:
        if target < -SIDESLIP_LIMIT_DEG or target > SIDESLIP_LIMIT_DEG:
            raise ValueError(
                "beta target %.3f deg outside declared +-%.1f deg limit"
                % (target, SIDESLIP_LIMIT_DEG))
        rows.append({"beta_target_deg": float(target),
                     "cas_ms": float(cas_ms),
                     "altitude_m": float(altitude_m)})
    return rows


def reduce_sideslip_sweep(beta_deg, delta_r_deg, delta_a_deg,
                          pedal_force_N=None, cn_dr_per_rad=None,
                          cl_da_per_rad=None):
    """Reduce a full steady-heading sideslip sweep in one call, dict."""
    result = {
        "rudder_gradient_per_deg": rudder_gradient(beta_deg, delta_r_deg),
        "aileron_gradient_per_deg": aileron_gradient(beta_deg, delta_a_deg),
        "pedal_force_gradient_N_per_deg": None,
        "cn_beta_estimate_per_rad": None,
        "cl_beta_estimate_per_rad": None,
        "weathercock_verdict": None,
        "dihedral_verdict": None,
        "point_count": len(list(beta_deg)),
    }
    if pedal_force_N is not None:
        result["pedal_force_gradient_N_per_deg"] = pedal_force_gradient(
            beta_deg, pedal_force_N)
    if cn_dr_per_rad is not None:
        cn_est = signed_directional_estimate(cn_dr_per_rad,
                                             result["rudder_gradient_per_deg"])
        result["cn_beta_estimate_per_rad"] = cn_est
        result["weathercock_verdict"] = weathercock_verdict(cn_est)
    if cl_da_per_rad is not None:
        cl_est = signed_lateral_estimate(cl_da_per_rad,
                                         result["aileron_gradient_per_deg"])
        result["cl_beta_estimate_per_rad"] = cl_est
        result["dihedral_verdict"] = dihedral_verdict(cl_est)
    return result


# ---------------------------------------------------------------------------
# Longitudinal control forces (leaf: control-force-flight-test)
# ---------------------------------------------------------------------------

# Conventions: pull (aft) forces POSITIVE, push negative; speeds in KCAS;
# load factors in g; all fits ordinary least squares closed-form sums.


def _require_min_points(values, name, minimum):
    if len(values) < minimum:
        raise ValueError("%s needs at least %d points, got %d"
                         % (name, minimum, len(values)))


def _require_equal_length(xs, ys):
    if len(xs) != len(ys):
        raise ValueError("length mismatch: %d x values vs %d y values"
                         % (len(xs), len(ys)))


def _least_squares(xs, ys):
    """OLS fit y = slope*x + intercept with r2, closed-form sums."""
    n = len(xs)
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    sxx = sum((x - x_mean) ** 2 for x in xs)
    if sxx == 0.0:
        raise ValueError("x values are all identical, cannot fit a gradient")
    sxy = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = y_mean - slope * x_mean
    sst = sum((y - y_mean) ** 2 for y in ys)
    if sst == 0.0:
        r2 = 1.0
    else:
        sse = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
        r2 = 1.0 - sse / sst
    return slope, intercept, r2


def calibrate_force_transducer(known_lbf, counts):
    """Least-squares calibration of applied load (lbf) vs counts, dict."""
    _require_min_points(known_lbf, "calibration", 2)
    _require_min_points(counts, "calibration", 2)
    _require_equal_length(known_lbf, counts)
    if any(c < 0 for c in counts):
        raise ValueError("counts must be non-negative")
    slope, intercept, _ = _least_squares(counts, known_lbf)
    predicted = [slope * c + intercept for c in counts]
    return {"slope_lbf_per_count": slope,
            "intercept_lbf": intercept,
            "predicted_lbf": predicted}


def stick_force_gradient(speeds_kts, forces_lbf):
    """Stick force gradient vs calibrated airspeed from a speed sweep, dict.

    Verdict is stable-gradient when slope > 0 (pull force increases with
    speed) else unstable-gradient.
    """
    _require_min_points(speeds_kts, "speed sweep", 3)
    _require_min_points(forces_lbf, "speed sweep", 3)
    _require_equal_length(speeds_kts, forces_lbf)
    if any(v <= 0 for v in speeds_kts):
        raise ValueError("calibrated airspeeds must be positive")
    slope, intercept, r2 = _least_squares(speeds_kts, forces_lbf)
    verdict = STABLE_GRADIENT if slope > 0 else UNSTABLE_GRADIENT
    return {"slope_lbf_per_kt": slope,
            "intercept_lbf": intercept,
            "r2": r2,
            "verdict": verdict}


def force_per_g(load_factors, forces_lbf):
    """Stick force per g from pull-up maneuver load factor sweeps, dict."""
    _require_min_points(load_factors, "pull-up sweep", 3)
    _require_min_points(forces_lbf, "pull-up sweep", 3)
    _require_equal_length(load_factors, forces_lbf)
    slope, intercept, r2 = _least_squares(load_factors, forces_lbf)
    return {"slope_lbf_per_g": slope,
            "intercept_lbf": intercept,
            "r2": r2}


def breakout_force(push_lbf, pull_lbf):
    """Breakout force from the push-pull hysteresis of the control, dict.

    width = pull - push; breakout = width / 2 (the half-width force that
    must be overcome before the control moves).
    """
    if pull_lbf <= push_lbf:
        raise ValueError("pull force %.3f must exceed push force %.3f"
                         % (pull_lbf, push_lbf))
    width = pull_lbf - push_lbf
    return {"hysteresis_width_lbf": width,
            "breakout_lbf": width / 2.0}


def centering_check(residual_deg, limit_deg):
    """Centering check of the residual control position against limit, dict.

    margin = limit - residual; verdict centered when margin >= 0 else
    exceeds-limit.
    """
    if residual_deg < 0:
        raise ValueError("residual position must be non-negative")
    if limit_deg <= 0:
        raise ValueError("centering limit must be positive")
    margin = limit_deg - residual_deg
    verdict = CENTERED if margin >= 0 else EXCEEDS_LIMIT
    return {"residual_deg": residual_deg,
            "limit_deg": limit_deg,
            "margin_deg": margin,
            "verdict": verdict}


def control_force_report(known_lbf, counts, predict_count, speeds_kts,
                         sweep_forces_lbf, load_factors, pullup_forces_lbf,
                         push_lbf, pull_lbf, residual_deg, limit_deg):
    """Combine the full control force flight test reduction in one dict."""
    if predict_count < 0:
        raise ValueError("predict count must be non-negative")
    cal = calibrate_force_transducer(known_lbf, counts)
    grad = stick_force_gradient(speeds_kts, sweep_forces_lbf)
    per_g = force_per_g(load_factors, pullup_forces_lbf)
    breakout = breakout_force(push_lbf, pull_lbf)
    centering = centering_check(residual_deg, limit_deg)
    predicted = cal["slope_lbf_per_count"] * predict_count \
        + cal["intercept_lbf"]
    return {"calibration": cal,
            "stick_force_gradient": grad,
            "force_per_g": per_g,
            "breakout": breakout,
            "centering": centering,
            "predicted_force_lbf": predicted}


# ---------------------------------------------------------------------------
# Demonstration rollup: every measured verdict -> pass/fail -> gate
# ---------------------------------------------------------------------------

# Verdict vocabulary that PASSES the demonstration (measured quantities,
# per the leaves' demonstration criteria). Anything else is flagged.
PASSING_VERDICTS = {
    "stable", "acceptable", STABLE_GRADIENT, CENTERED,
}


def verdict_pass(verdict: str) -> bool:
    """Map a measured verdict onto the demonstration pass criterion.

    stable / acceptable / stable-gradient / centered pass; unstable,
    unstable-gradient, exceeds-limit, inadequate, marginal and neutral
    margins do not (each stays honestly OPEN in the rollup).
    """
    return verdict in PASSING_VERDICTS


def rollup_verdicts(rows) -> dict:
    """Rollup of subject verdict rows into an overall demonstration gate.

    rows: list of {subject, value, verdict, basis}. Returns pass_count,
    total, failed list and overall_gate CLOSED when every subject passes.
    """
    out = []
    for row in rows:
        ok = verdict_pass(row["verdict"])
        out.append({"subject": row["subject"], "value": row["value"],
                    "verdict": row["verdict"], "basis": row["basis"],
                    "pass": ok})
    failed = [r["subject"] for r in out if not r["pass"]]
    total = len(out)
    passed = total - len(failed)
    return {"checks": out, "pass_count": passed, "total": total,
            "failed_subjects": failed,
            "overall_gate": "CLOSED" if total and not failed else "OPEN"}


# ---------------------------------------------------------------------------
# Test item + builder
# ---------------------------------------------------------------------------


@dataclass
class StabilityControlTestItem:
    """Project facts the role needs to build the stability and control
    flight test report.

    The four bound leaves each own one reduction; the item carries the
    measured records for each: static longitudinal trim sweep
    (static-stability-flight-test), per-mode decaying response records
    (dynamic-stability-flight-test), the steady-heading sideslip sweep
    (lateral-directional-stability-flight-test), and the longitudinal
    control force records (control-force-flight-test).
    """
    item_name: str
    description: str = ""
    airframe: str = ""
    certification_basis: str = "FAR/CS-25 (context only)"
    test_date: str = ""
    configuration: str = ""
    # --- static longitudinal (trim curve + neutral points) ---
    elevator_deg: list = field(default_factory=list)
    speeds_m_s: list = field(default_factory=list)
    weight_n: float = 0.0
    wing_area_m2: float = 0.0
    rho_kg_m3: float = 0.0
    # trim_cg_fraction_mac: CG at which the trim sweep was measured (the
    # neutral point located from the slope is absolute); cg_fraction_mac:
    # CG at which the demonstration margin is quoted (default = trim CG).
    trim_cg_fraction_mac: float = 0.0
    cg_fraction_mac: float = 0.0
    cm_delta_e_per_rad: float = 0.0
    ch_alpha_per_rad: float = 0.0
    ch_delta_e_per_rad: float = 0.0
    cl_alpha_per_rad: float = 0.0
    cl_1g: float = 0.0
    # --- dynamic modes: (mode, peak_values, peak_times) for decaying
    # oscillatory records; spiral (aperiodic) carries estimated zeta ---
    dynamic_modes: list = field(default_factory=list)
    # --- lateral-directional steady-heading sideslip ---
    beta_deg: list = field(default_factory=list)
    delta_r_deg: list = field(default_factory=list)
    delta_a_deg: list = field(default_factory=list)
    pedal_force_N: list = field(default_factory=list)
    cn_dr_per_rad: float = 0.0
    cl_da_per_rad: float = 0.0
    shs_cas_ms: float = 0.0
    shs_altitude_m: float = 0.0
    # --- longitudinal control forces ---
    cf_known_lbf: list = field(default_factory=list)
    cf_counts: list = field(default_factory=list)
    cf_predict_count: float = 0.0
    cf_speeds_kts: list = field(default_factory=list)
    cf_sweep_forces_lbf: list = field(default_factory=list)
    cf_load_factors: list = field(default_factory=list)
    cf_pullup_forces_lbf: list = field(default_factory=list)
    cf_push_lbf: float = 0.0
    cf_pull_lbf: float = 0.0
    cf_residual_deg: float = 0.0
    cf_limit_deg: float = 0.0
    # --- requirements/findings rollup for the report ---
    requirements: list = field(default_factory=list)
    supporting_note: str = ""


def _fmt(x, nd=4) -> str:
    if isinstance(x, float):
        if x == 0.0:
            return "0"
        if 1e-4 <= abs(x) < 1e6:
            return "%.*g" % (nd, x)
        return "%.1e" % x
    return str(x)


def _fmt_deg(x, nd=3) -> str:
    return ("%+.3f" % x) if isinstance(x, float) else str(x)


def _margin_verdict(margin: float) -> str:
    """Verdict for a static margin at the demonstrated CG: positive
    stable, negative unstable (flag), zero neutral (leaf thresholds)."""
    if margin > NEUTRAL_TOL:
        return "stable"
    if margin < -NEUTRAL_TOL:
        return "unstable"
    return "neutral"


def _label(verdict: str) -> str:
    return verdict.replace("-", " ").title()


def build_stability_control_report(item: StabilityControlTestItem) -> dict:
    """Build the complete Stability and Control Flight Test Report model."""
    # --- static longitudinal stability ---
    # The trim slope locates an ABSOLUTE stick fixed neutral point (leaf
    # formula evaluated at the CG the trim was measured at); the
    # demonstrated static margin is then quoted at the assessment CG
    # (SM = h_n - h_cg), so an aft-CG override honestly reduces margin.
    static = {"fit": {}, "stick_fixed": {}, "stick_free": None,
              "elevator_angle_per_g": None, "verdict": "n/a"}
    if item.elevator_deg and item.speeds_m_s:
        fit = trim_curve_fit(item.elevator_deg, item.speeds_m_s,
                             item.weight_n, item.wing_area_m2,
                             item.rho_kg_m3)
        trim_cg = item.trim_cg_fraction_mac or item.cg_fraction_mac
        demo_cg = item.cg_fraction_mac
        fixed0 = stick_fixed_neutral_point(fit["slope_deg_per_cl"], trim_cg,
                                           item.cm_delta_e_per_rad)
        np_abs = fixed0["neutral_point_fraction_mac"]
        sm_fixed = np_abs - demo_cg
        fixed = {"neutral_point_fraction_mac": np_abs,
                 "static_margin_fraction_mac": sm_fixed,
                 "shift_fraction_mac": fixed0["shift_fraction_mac"],
                 "verdict": _margin_verdict(sm_fixed),
                 "note": fixed0["note"]}
        free = None
        if (item.ch_alpha_per_rad and item.ch_delta_e_per_rad
                and item.cl_alpha_per_rad):
            free0 = stick_free_neutral_point(np_abs, trim_cg,
                                             item.cm_delta_e_per_rad,
                                             item.ch_alpha_per_rad,
                                             item.ch_delta_e_per_rad,
                                             item.cl_alpha_per_rad)
            np_free_abs = free0["neutral_point_fraction_mac"]
            sm_free = np_free_abs - demo_cg
            free = {"neutral_point_fraction_mac": np_free_abs,
                    "static_margin_fraction_mac": sm_free,
                    "shift_fraction_mac": free0["shift_fraction_mac"],
                    "verdict": _margin_verdict(sm_free)}
        epg = elevator_angle_per_g(item.cl_1g, sm_fixed,
                                   item.cm_delta_e_per_rad) \
            if item.cl_1g else None
        static = {"fit": fit, "stick_fixed": fixed, "stick_free": free,
                  "elevator_angle_per_g": epg,
                  "verdict": fixed["verdict"]}

    # --- dynamic stability: reduce each configured mode record ---
    dynamic_rows = []
    for entry in item.dynamic_modes:
        mode = entry["mode"]
        tech = excitation_technique(mode)
        if entry.get("spiral_zeta") is not None:
            # aperiodic spiral: damping ratio input from the rudder-step
            # convergence record (leaf verdict band applies)
            ident = {"damping_ratio": entry["spiral_zeta"], "decrement": None,
                     "period_s": None, "damped_frequency_hz": None,
                     "undamped_frequency_rad_s": None, "time_to_half_s": None,
                     "cycles_used": None}
            note = "aperiodic; damping-ratio estimate from the 20-30 s " \
                   "rudder-step convergence record"
        else:
            ident = mode_identification(entry["peaks"], entry["times"])
            note = ("log decrement over %d cycle(s) of the decaying "
                    "record" % ident["cycles_used"])
        verdict = handling_qualities_verdict(mode, ident["damping_ratio"])
        dynamic_rows.append({
            "mode": mode,
            "excitation": tech["technique"],
            "control": tech["control"],
            "decrement": ident["decrement"],
            "damping_ratio": ident["damping_ratio"],
            "period_s": ident["period_s"],
            "damped_frequency_hz": ident["damped_frequency_hz"],
            "undamped_frequency_rad_s": ident["undamped_frequency_rad_s"],
            "time_to_half_s": ident["time_to_half_s"],
            "cycles_to_half": (cycles_to_half_amplitude(
                ident["damping_ratio"])
                if ident["damping_ratio"] and ident["damping_ratio"] > 0
                else None),
            "band": verdict["band"],
            "verdict": verdict["verdict"],
            "note": note,
        })

    # --- lateral-directional static stability (SHS sweep) ---
    lateral = reduce_sideslip_sweep(
        item.beta_deg, item.delta_r_deg, item.delta_a_deg,
        pedal_force_N=item.pedal_force_N,
        cn_dr_per_rad=item.cn_dr_per_rad,
        cl_da_per_rad=item.cl_da_per_rad) \
        if item.beta_deg and item.delta_r_deg and item.delta_a_deg else {}
    shs_matrix = build_sideslip_matrix(item.beta_deg, item.shs_cas_ms,
                                       item.shs_altitude_m) \
        if item.beta_deg and item.shs_cas_ms else []

    # --- longitudinal control forces ---
    control = control_force_report(
        item.cf_known_lbf, item.cf_counts, item.cf_predict_count,
        item.cf_speeds_kts, item.cf_sweep_forces_lbf, item.cf_load_factors,
        item.cf_pullup_forces_lbf, item.cf_push_lbf, item.cf_pull_lbf,
        item.cf_residual_deg, item.cf_limit_deg) \
        if item.cf_known_lbf and item.cf_counts else {}

    # --- demonstration rollup ---
    rows = []
    fixed = static.get("stick_fixed") or {}
    if fixed:
        rows.append({"subject": "Static longitudinal stability, stick fixed",
                     "value": "static margin %s MAC (neutral point %s MAC)"
                     % (_fmt(fixed.get("static_margin_fraction_mac"), 4),
                        _fmt(fixed.get("neutral_point_fraction_mac"), 4)),
                     "verdict": fixed.get("verdict", "n/a"),
                     "basis": "trim curve slope + Cm_delta_e (leaf "
                              "static-stability-flight-test)"})
    free = static.get("stick_free")
    if free:
        rows.append({"subject": "Static longitudinal stability, stick free",
                     "value": "static margin %s MAC (neutral point %s MAC)"
                     % (_fmt(free.get("static_margin_fraction_mac"), 4),
                        _fmt(free.get("neutral_point_fraction_mac"), 4)),
                     "verdict": free.get("verdict", "n/a"),
                     "basis": "free-elevator hinge model (leaf "
                              "static-stability-flight-test)"})
    epg = static.get("elevator_angle_per_g")
    if epg:
        rows.append({"subject": "Elevator angle per g",
                     "value": "%s deg/g (magnitude %s deg/g)"
                     % (_fmt(epg.get("value_deg_per_g"), 4),
                        _fmt(epg.get("magnitude_deg_per_g"), 4)),
                     "verdict": "stable" if epg.get("value_deg_per_g", 0) < 0
                     else "unstable",
                     "basis": "d(delta_e)/dn = (180/pi) CL SM / Cm_delta_e "
                              "(leaf static-stability-flight-test)"})
    for row in dynamic_rows:
        rows.append({"subject": "Dynamic stability, %s"
                     % row["mode"].replace("-", " "),
                     "value": "damping ratio %s" % _fmt(row["damping_ratio"], 4),
                     "verdict": row["verdict"],
                     "basis": "band table (%s) per leaf "
                              "dynamic-stability-flight-test" % row["band"]})
    if lateral:
        rows.append({"subject": "Directional (weathercock) stability",
                     "value": "Cn_beta estimate %s /rad"
                     % _fmt(lateral.get("cn_beta_estimate_per_rad"), 4),
                     "verdict": lateral.get("weathercock_verdict", "n/a"),
                     "basis": "Cn_beta = -cn_dr * s_r from the SHS rudder "
                              "gradient (leaf "
                              "lateral-directional-stability-flight-test)"})
        rows.append({"subject": "Lateral (dihedral) stability",
                     "value": "Cl_beta estimate %s /rad"
                     % _fmt(lateral.get("cl_beta_estimate_per_rad"), 4),
                     "verdict": lateral.get("dihedral_verdict", "n/a"),
                     "basis": "Cl_beta = -cl_da * s_a from the SHS aileron "
                              "gradient (leaf "
                              "lateral-directional-stability-flight-test)"})
    grad = control.get("stick_force_gradient") or {}
    if grad:
        rows.append({"subject": "Stick force gradient vs speed",
                     "value": "%s lbf/kt" % _fmt(grad.get("slope_lbf_per_kt"), 4),
                     "verdict": grad.get("verdict", "n/a"),
                     "basis": "level speed sweep, pull positive (leaf "
                              "control-force-flight-test)"})
    centering = control.get("centering") or {}
    if centering:
        rows.append({"subject": "Control centering (residual vs limit)",
                     "value": "residual %s deg, limit %s deg, margin %s deg"
                     % (_fmt(centering.get("residual_deg"), 4),
                        _fmt(centering.get("limit_deg"), 4),
                        _fmt(centering.get("margin_deg"), 4)),
                     "verdict": centering.get("verdict", "n/a"),
                     "basis": "margin = limit - residual after release (leaf "
                              "control-force-flight-test)"})
    rollup = rollup_verdicts(rows)

    # --- requirement/finding verification rollup ---
    req_rollup = {"verified": 0, "open": 0, "total": 0,
                  "open_items": []}
    if item.requirements:
        verified = [r for r in item.requirements
                    if str(r.get("status", "")).lower() == "verified"]
        open_items = [r["id"] for r in item.requirements
                      if str(r.get("status", "")).lower() != "verified"]
        req_rollup = {"verified": len(verified),
                      "open": len(open_items),
                      "total": len(item.requirements),
                      "open_items": open_items}

    return {
        "document_type": "Stability and Control Flight Test Report",
        "status": "draft-for-review",
        "item": item.item_name,
        "item_description": item.description,
        "airframe": item.airframe,
        "certification_basis": item.certification_basis,
        "configuration": item.configuration,
        "test_date": item.test_date,
        "static_longitudinal": {
            "cg_fraction_mac": item.cg_fraction_mac,
            "trim_cg_fraction_mac": item.trim_cg_fraction_mac,
            "cm_delta_e_per_rad": item.cm_delta_e_per_rad,
            "fit": static.get("fit", {}),
            "stick_fixed": fixed,
            "stick_free": free,
            "elevator_angle_per_g": epg,
            "verdict": static.get("verdict", "n/a"),
        },
        "dynamic_modes": dynamic_rows,
        "lateral_directional": {
            "cas_ms": item.shs_cas_ms,
            "altitude_m": item.shs_altitude_m,
            "cn_dr_per_rad": item.cn_dr_per_rad,
            "cl_da_per_rad": item.cl_da_per_rad,
            "sideslip_limit_deg": SIDESLIP_LIMIT_DEG,
            "sweep_matrix": shs_matrix,
            "beta_deg": list(item.beta_deg),
            "delta_r_deg": list(item.delta_r_deg),
            "delta_a_deg": list(item.delta_a_deg),
            "pedal_force_N": list(item.pedal_force_N),
            "gradients": lateral,
        },
        "control_forces": control,
        "cf_predict_count": item.cf_predict_count,
        "rollup": rollup,
        "requirement_rollup": req_rollup,
        "requirements": item.requirements,
        "supporting_note": item.supporting_note,
        "generated": _today(),
    }


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


def render_report_markdown(model: dict) -> str:
    """Render the stability & control content model as the deliverable."""
    L = []
    A = L.append
    A("# Stability and Control Flight Test Report")
    A("")
    A("**Item:** %s" % model["item"])
    A("**Airframe:** %s" % model["airframe"])
    A("**Configuration:** %s" % model["configuration"])
    A("**Certification basis:** %s" % model["certification_basis"])
    A("**Status:** %s" % model["status"])
    A("")
    A("## 1. Test item and conditions")
    A("")
    A(model["item_description"])
    if model.get("supporting_note"):
        A("")
        A(model["supporting_note"])
    A("")
    A("## 2. Static longitudinal stability")
    A("")
    static = model["static_longitudinal"]
    fit = static.get("fit", {})
    if fit:
        A("Trim curve fit (elevator angle vs lift coefficient, "
          "delta_e = a + b CL):")
        A("")
        A("| Speed (m/s) | CL | Elevator (deg) |")
        A("|---|---|---|")
        for v, cl, e in zip(fit["speeds_m_s"], fit["lift_coefficients"],
                            fit["elevator_deg"]):
            A("| %s | %.3f | %s |" % (_fmt(v, 5), cl, _fmt_deg(e)))
        A("")
        A("- Trim curve slope b = d(delta_e)/dCL = **%s deg per CL** "
          "(negative slope = statically stable), intercept %s deg, "
          "R^2 = %s, n = %d."
          % (_fmt(fit["slope_deg_per_cl"]), _fmt(fit["intercept_deg"]),
             _fmt(fit["r_squared"], 5), fit["n"]))
    fixed = static.get("stick_fixed") or {}
    if fixed:
        trim_cg = static.get("trim_cg_fraction_mac") or \
            static.get("cg_fraction_mac")
        A("- CG position for the demonstrated margin h = **%s MAC** "
          "(trim sweep measured at trim CG %s MAC). Stick fixed neutral "
          "point from the slope, h_n = h_trim + b Cm_delta_e (pi/180) = "
          "**%s MAC** (absolute); static margin SM = h_n - h = "
          "**%s MAC** -> **%s**."
          % (_fmt(static.get("cg_fraction_mac")), _fmt(trim_cg),
             _fmt(fixed.get("neutral_point_fraction_mac")),
             _fmt(fixed.get("static_margin_fraction_mac")),
             _label(fixed.get("verdict", "n/a"))))
    free = static.get("stick_free")
    if free:
        A("- Stick free neutral point (free elevator hinge model, shift "
          "(Cm_delta_e Ch_alpha)/(CL_alpha Ch_delta_e) = %s MAC) = "
          "**%s MAC**; stick free static margin **%s MAC** -> **%s**."
          % (_fmt(free.get("shift_fraction_mac")),
             _fmt(free.get("neutral_point_fraction_mac")),
             _fmt(free.get("static_margin_fraction_mac")),
             _label(free.get("verdict", "n/a"))))
    epg = static.get("elevator_angle_per_g")
    if epg:
        A("- Elevator angle per g: d(delta_e)/dn = (180/pi) CL SM / "
          "Cm_delta_e = **%s deg/g** (magnitude %s deg/g). %s."
          % (_fmt(epg.get("value_deg_per_g")),
             _fmt(epg.get("magnitude_deg_per_g")),
             epg.get("assessment", "")))
    A("")
    A("## 3. Dynamic stability (mode identification and verdicts)")
    A("")
    A("| Mode | Excitation | Damping ratio | Damped freq (Hz) | t half (s) "
      "| Band | Verdict |")
    A("|---|---|---|---|---|---|---|")
    for m in model["dynamic_modes"]:
        A("| %s | %s | %s | %s | %s | %s | **%s** |"
          % (m["mode"].replace("-", " ").title(),
             m["excitation"].split(" or ")[0],
             _fmt(m["damping_ratio"], 4),
             _fmt(m["damped_frequency_hz"], 4) if
             m["damped_frequency_hz"] is not None else "aperiodic",
             _fmt(m["time_to_half_s"], 4) if m["time_to_half_s"] is not None
             else "n/a (aperiodic)",
             m["band"], _label(m["verdict"])))
    A("")
    for m in model["dynamic_modes"]:
        A("- **%s**: %s; %s." % (m["mode"].replace("-", " ").title(),
                                 m["note"], m["verdict"]))
    A("")
    A("## 4. Static lateral-directional stability (steady-heading sideslip)")
    A("")
    A("Sideslip sweep at constant CAS %s m/s, altitude %s m, commanded "
      "beta inside +-%s deg (left slip positive). Declared control "
      "powers: cn_dr = %s /rad, cl_da = %s /rad."
      % (_fmt(model["lateral_directional"]["cas_ms"], 5),
         _fmt(model["lateral_directional"]["altitude_m"], 5),
         _fmt(model["lateral_directional"]["sideslip_limit_deg"]),
         _fmt(model["lateral_directional"]["cn_dr_per_rad"]),
         _fmt(model["lateral_directional"]["cl_da_per_rad"])))
    A("")
    lat = model["lateral_directional"]["gradients"] or {}
    ldir = model["lateral_directional"]
    if lat:
        A("| Beta (deg) | Rudder (deg) | Aileron (deg) | Rudder-free pedal "
          "force (N) |")
        A("|---|---|---|---|")
        for b, dr, da, fp in zip(
                ldir.get("beta_deg", []), ldir.get("delta_r_deg", []),
                ldir.get("delta_a_deg", []),
                ldir.get("pedal_force_N", [])):
            A("| %s | %s | %s | %s |" % (_fmt(b, 4), _fmt_deg(dr),
                                         _fmt_deg(da), _fmt(fp, 5)))
        A("")
        A("- Rudder gradient s_r = d(delta_r)/d(beta) = **%s deg/deg** "
          "(positive = pilot pushes rudder into the slip)."
          % _fmt(lat.get("rudder_gradient_per_deg"), 5))
        A("- Aileron gradient s_a = d(delta_a)/d(beta) = **%s deg/deg** "
          "(negative = aileron holds the slip against the dihedral roll)."
          % _fmt(lat.get("aileron_gradient_per_deg"), 5))
        A("- Pedal-force gradient (rudder free) g_p = **%s N/deg**."
          % _fmt(lat.get("pedal_force_gradient_N_per_deg"), 5))
        if lat.get("cn_beta_estimate_per_rad") is not None:
            A("- Directional estimate Cn_beta = -cn_dr * s_r = **%s /rad** "
              "-> weathercock verdict **%s**."
              % (_fmt(lat.get("cn_beta_estimate_per_rad")),
                 _label(lat.get("weathercock_verdict", "n/a"))))
        if lat.get("cl_beta_estimate_per_rad") is not None:
            A("- Lateral estimate Cl_beta = -cl_da * s_a = **%s /rad** "
              "-> dihedral verdict **%s**."
              % (_fmt(lat.get("cl_beta_estimate_per_rad")),
                 _label(lat.get("dihedral_verdict", "n/a"))))
    A("")
    A("## 5. Longitudinal control forces")
    A("")
    cf = model["control_forces"] or {}
    cal = cf.get("calibration") or {}
    if cal:
        A("Force transducer calibration (applied lbf vs recorded counts): "
          "slope **%s lbf/count**, intercept **%s lbf**; calibrated force "
          "at %s counts = **%s lbf**."
          % (_fmt(cal.get("slope_lbf_per_count"), 5),
             _fmt(cal.get("intercept_lbf"), 5),
             _fmt(model.get("cf_predict_count", "")),
             _fmt(cf.get("predicted_force_lbf"), 5)))
        A("")
    grad = cf.get("stick_force_gradient") or {}
    if grad:
        A("- Stick force gradient vs calibrated airspeed: slope **%s lbf/kt** "
          "(pull positive), R^2 %s -> **%s**."
          % (_fmt(grad.get("slope_lbf_per_kt"), 5),
             _fmt(grad.get("r2"), 5), _label(grad.get("verdict", "n/a"))))
    pg = cf.get("force_per_g") or {}
    if pg:
        A("- Stick force per g from the pull-ups: **%s lbf/g**, R^2 %s."
          % (_fmt(pg.get("slope_lbf_per_g"), 5), _fmt(pg.get("r2"), 5)))
    bo = cf.get("breakout") or {}
    if bo:
        A("- Breakout force from the push-pull hysteresis: hysteresis width "
          "**%s lbf**, breakout **%s lbf**."
          % (_fmt(bo.get("hysteresis_width_lbf"), 5),
             _fmt(bo.get("breakout_lbf"), 5)))
    ce = cf.get("centering") or {}
    if ce:
        A("- Control centering check: residual **%s deg** against limit "
          "**%s deg**, margin **%s deg** -> **%s**."
          % (_fmt(ce.get("residual_deg"), 4), _fmt(ce.get("limit_deg"), 4),
             _fmt(ce.get("margin_deg"), 4),
             _label(ce.get("verdict", "n/a"))))
    A("")
    A("## 6. Demonstration rollup")
    A("")
    rollup = model["rollup"]
    A("| Subject | Measured value | Verdict | Pass |")
    A("|---|---|---|---|")
    for chk in rollup["checks"]:
        A("| %s | %s | %s | %s |"
          % (chk["subject"], chk["value"], _label(chk["verdict"]),
             "YES" if chk["pass"] else "NO"))
    A("")
    A("**Rollup gate: %s** (%d/%d checks pass)."
      % (rollup["overall_gate"], rollup["pass_count"], rollup["total"]))
    if rollup["failed_subjects"]:
        A("")
        A("Open checks: %s" % ", ".join(rollup["failed_subjects"]))
    rr = model["requirement_rollup"]
    A("")
    A("Requirement/finding verification: %d/%d verified (%s)."
      % (rr["verified"], rr["total"],
         "CLOSED" if not rr["open_items"] else
         "OPEN: " + ", ".join(rr["open_items"])))
    A("")
    A("## 7. Sign-off status")
    A("")
    A("This report is a **DRAFT** prepared for the human flight test "
      "engineer and the stability and control specialist to review "
      "before the demonstration is presented to the certification "
      "authority. It documents measured data reductions and verdicts "
      "only.")
    A("")
    A("---")
    A("*Generated by Aero Agent Roles stability-control-flight-test-engineer "
      "core (%s). DRAFT for human flight test engineering review. Not an "
      "approval document and not a certification finding - the "
      "authority/regulator signs.*" % model["generated"])
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Evidence gate checkers
# ---------------------------------------------------------------------------

GATE_CHECKS = {
    "static_numbers_present": "trim curve fit yields a slope, neutral "
                              "points and static margins with a verdict",
    "dynamic_modes_present": "every configured mode has a damping ratio "
                             "and a band verdict",
    "lateral_directional_present": "SHS sweep yields the rudder/aileron/"
                                   "pedal gradients and signed Cn_beta/"
                                   "Cl_beta estimates with verdicts",
    "control_forces_present": "calibration, stick force gradient, force "
                              "per g, breakout and centering are reduced",
    "closure_gate_checked": "rollup gate is CLOSED or OPEN with per-check "
                            "verdicts",
    "sign_off_honest": "document is marked draft-for-review, not approval",
}


def check_report(model: dict) -> dict:
    """Run the evidence gates against a stability & control model."""
    static = model.get("static_longitudinal", {})
    fit = static.get("fit", {})
    fixed = static.get("stick_fixed") or {}
    dyn_rows = model.get("dynamic_modes", [])
    lat = model.get("lateral_directional", {}).get("gradients", {}) or {}
    cf = model.get("control_forces", {}) or {}
    rollup = model.get("rollup", {})
    results = {
        "static_numbers_present": bool(fit) and isinstance(
            fit.get("slope_deg_per_cl"), (int, float)) and bool(fixed)
            and isinstance(fixed.get("static_margin_fraction_mac"),
                           (int, float))
            and fixed.get("verdict") in ("stable", "unstable", "neutral"),
        "dynamic_modes_present": bool(dyn_rows) and all(
            isinstance(m.get("damping_ratio"), (int, float))
            and m.get("verdict") in
            ("acceptable", "marginal", "inadequate")
            for m in dyn_rows),
        "lateral_directional_present": lat.get("rudder_gradient_per_deg")
            is not None and lat.get("aileron_gradient_per_deg") is not None
            and lat.get("weathercock_verdict") in ("stable", "unstable")
            and lat.get("dihedral_verdict") in ("stable", "unstable"),
        "control_forces_present": bool(cf.get("calibration"))
            and bool(cf.get("stick_force_gradient"))
            and bool(cf.get("force_per_g")) and bool(cf.get("breakout"))
            and bool(cf.get("centering")),
        "closure_gate_checked": rollup.get("overall_gate") in
            ("CLOSED", "OPEN") and "checks" in rollup,
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_report_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    checks = {
        "has_title": "stability and control flight test report" in low,
        "has_item": "item:" in low and "airframe:" in low,
        "has_static_number": "static margin" in low
                             and "neutral point" in low,
        "has_dynamic_number": "damping ratio" in low
                              and "verdict" in low,
        "has_lateral_number": "cn_beta" in low and "cl_beta" in low,
        "has_control_force_number": "stick force gradient" in low
                                    and "lbf/kt" in low,
        "has_rollup_gate": "rollup gate" in low
                           and ("closed" in low or "open" in low),
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling."""
    return check_report_markdown(md_text)


# ---------------------------------------------------------------------------
# Example project (worked example: the reference transport)
# ---------------------------------------------------------------------------

def example_item() -> StabilityControlTestItem:
    """Reference item: a transport-category airplane stability & control
    flight test campaign whose measured records are the worked-example
    datasets of the four bound leaves (contract values of the bound
    leaves' own reductions), reduced by the leaf formulas the core
    encodes."""
    # Static longitudinal trim sweep: CL = 2 W / (rho V^2 S) with
    # W = 450000 N, S = 110 m^2 at sea level (rho = 1.225 kg/m^3),
    # speeds chosen on CL = 0.50 .. 0.90; elevator trims on the line
    # delta_e = 3 - 6 CL deg (slope -6 deg/CL, stable).
    weight_n = 450000.0
    wing_area_m2 = 110.0
    rho_kg_m3 = 1.225
    cl_targets = [0.50, 0.60, 0.70, 0.80, 0.90]
    k_cl = 2.0 * weight_n / (rho_kg_m3 * wing_area_m2)
    speeds_m_s = [math.sqrt(k_cl / cl) for cl in cl_targets]
    elevator_deg = [3.0 - 6.0 * cl for cl in cl_targets]

    # Dynamic stability: decaying same-sign peak records per mode
    # (peak units: deg/s pitch/yaw rate as recorded; times in seconds).
    dynamic_modes = [
        # short period from an elevator doublet: zeta ~ 0.41
        {"mode": "short-period",
         "peaks": [5.00, 0.296, 0.0176],
         "times": [0.0, 0.9, 1.8]},
        # phugoid from an elevator pulse: zeta ~ 0.06, period ~ 20 s
        {"mode": "phugoid",
         "peaks": [5.00, 3.42, 2.35],
         "times": [0.0, 20.0, 40.0]},
        # dutch roll from a rudder pulse: zeta ~ 0.15, period ~ 3 s
        {"mode": "dutch-roll",
         "peaks": [5.00, 1.95, 0.76],
         "times": [0.0, 3.0, 6.0]},
        # spiral from a rudder step: convergent (aperiodic)
        {"mode": "spiral", "spiral_zeta": 0.05},
    ]

    requirements = [
        {"id": "SR-01", "text": "Aircraft shall be statically stable "
         "(positive stick fixed static margin) at the test CG",
         "status": "verified"},
        {"id": "SR-02", "text": "Short period and Dutch roll oscillations "
         "shall be damped (practice bands; FAR/CS criteria take "
         "precedence)", "status": "verified"},
        {"id": "SR-03", "text": "Phugoid shall not be divergent",
         "status": "verified"},
        {"id": "SR-04", "text": "Aircraft shall be weathercock (Cn_beta "
         "positive) and dihedrally (Cl_beta negative) stable",
         "status": "verified"},
        {"id": "SR-05", "text": "Stick force shall increase with speed "
         "(stable gradient) and control shall center within its limit",
         "status": "verified"},
    ]

    return StabilityControlTestItem(
        item_name="Reference transport airplane - stability & control "
                  "flight test (worked example)",
        description="This report reduces the measured stability and "
                    "control records of the reference transport-category "
                    "airplane flight test campaign: the static "
                    "longitudinal trim sweep, the dynamic mode "
                    "excitations, the steady-heading sideslip sweep and "
                    "the longitudinal control force records. All flight "
                    "data below are the SIMULATED worked-example datasets "
                    "of the bound AeroSkills leaves and must be replaced "
                    "by recorded flight data before any program use.",
        airframe="Reference transport-category airplane (worked example)",
        certification_basis="FAR/CS-25 (context only; summary-not-copy)",
        test_date="notional test campaign",
        configuration="clean, flaps up, test CG 25 % MAC",
        elevator_deg=elevator_deg,
        speeds_m_s=speeds_m_s,
        weight_n=weight_n,
        wing_area_m2=wing_area_m2,
        rho_kg_m3=rho_kg_m3,
        trim_cg_fraction_mac=0.25,
        cg_fraction_mac=0.25,
        cm_delta_e_per_rad=-0.5,
        ch_alpha_per_rad=0.15,
        ch_delta_e_per_rad=-0.8,
        cl_alpha_per_rad=5.0,
        cl_1g=0.7,
        dynamic_modes=dynamic_modes,
        # steady-heading sideslip sweep (leaf worked example: transport
        # at constant CAS 80 m/s, altitude 3000 m)
        beta_deg=[2.0, 5.0, 8.0, 11.0, 14.0],
        delta_r_deg=[0.24, 0.58, 0.96, 1.34, 1.70],
        delta_a_deg=[-0.35, -0.80, -1.30, -1.80, -2.30],
        pedal_force_N=[0.0, -95.0, -185.0, -275.0, -360.0],
        cn_dr_per_rad=-0.90,
        cl_da_per_rad=-0.35,
        shs_cas_ms=80.0,
        shs_altitude_m=3000.0,
        # longitudinal control forces (leaf worked example)
        cf_known_lbf=[20.0, 60.0],
        cf_counts=[1230.0, 3250.0],
        cf_predict_count=2100.0,
        cf_speeds_kts=[120.0, 130.0, 140.0, 150.0],
        cf_sweep_forces_lbf=[-3.8, -1.6, 0.5, 2.9],
        cf_load_factors=[1.0, 1.5, 2.0, 2.5],
        cf_pullup_forces_lbf=[1.2, 7.4, 14.3, 20.8],
        cf_push_lbf=-4.2,
        cf_pull_lbf=6.4,
        cf_residual_deg=0.42,
        cf_limit_deg=0.50,
        requirements=requirements,
        supporting_note="Every number in this report is computed by the "
                        "role core from the bound leaf formulas: trim "
                        "curve reduction and neutral point relations "
                        "(CL = 2 W/(rho V^2 S), h_n = h + b Cm_delta_e "
                        "pi/180), log decrement mode identification "
                        "(delta = (1/n) ln(A0/An), zeta = delta/"
                        "sqrt(delta^2 + 4 pi^2)), the SHS signed "
                        "estimates (Cn_beta = -cn_dr s_r, Cl_beta = "
                        "-cl_da s_a) and the control force least squares "
                        "fits. Practice bands are typical flight test "
                        "practice; FAR/CS certification criteria take "
                        "precedence.",
    )


def example_report_markdown() -> str:
    return render_report_markdown(build_stability_control_report(
        example_item()))


if __name__ == "__main__":
    item = example_item()
    model = build_stability_control_report(item)
    md = render_report_markdown(model)
    s = model["static_longitudinal"]
    print("CG:", s["cg_fraction_mac"])
    print("FIT SLOPE:", s["fit"].get("slope_deg_per_cl"))
    print("NP FIXED:", s["stick_fixed"]["neutral_point_fraction_mac"])
    print("SM FIXED:", s["stick_fixed"]["static_margin_fraction_mac"])
    print("NP FREE:", s["stick_free"]["neutral_point_fraction_mac"])
    print("SM FREE:", s["stick_free"]["static_margin_fraction_mac"])
    print("EPG:", s["elevator_angle_per_g"]["value_deg_per_g"])
    for m in model["dynamic_modes"]:
        print("MODE", m["mode"], "zeta", m["damping_ratio"],
              "wd_hz", m["damped_frequency_hz"],
              "t_half", m["time_to_half_s"],
              "verdict", m["verdict"], "band", m["band"])
    lat = model["lateral_directional"]["gradients"]
    print("S_R:", lat["rudder_gradient_per_deg"],
          "S_A:", lat["aileron_gradient_per_deg"],
          "G_P:", lat["pedal_force_gradient_N_per_deg"])
    print("CN_BETA:", lat["cn_beta_estimate_per_rad"],
          "CL_BETA:", lat["cl_beta_estimate_per_rad"])
    cf = model["control_forces"]
    print("CAL:", cf["calibration"]["slope_lbf_per_count"],
          cf["calibration"]["intercept_lbf"],
          cf["predicted_force_lbf"])
    print("GRAD:", cf["stick_force_gradient"]["slope_lbf_per_kt"],
          cf["stick_force_gradient"]["verdict"])
    print("PER_G:", cf["force_per_g"]["slope_lbf_per_g"])
    print("BREAKOUT:", cf["breakout"]["breakout_lbf"])
    print("CENTER:", cf["centering"]["margin_deg"], cf["centering"]["verdict"])
    print("ROLLUP:", model["rollup"]["overall_gate"],
          model["rollup"]["pass_count"], "/", model["rollup"]["total"])
    print("GATES:", check_report(model))
    print("RENDERED:", len(md), "chars")
