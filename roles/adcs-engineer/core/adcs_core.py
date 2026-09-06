#!/usr/bin/env python3
"""adcs_core.py - Attitude Determination and Control (ADCS) engineer core.

This is the role's ENGINE. Given a spacecraft's project facts it computes
real ADCS numbers and BUILDS the Attitude Determination and Control
Subsystem Report:

- orbit mean motion / period / per-orbit disturbance momentum
- attitude determination: TRIAD (two-vector, sun sensor + magnetometer)
  coarse estimate and QUEST (Davenport q-method, weighted vector
  observations) optimal estimate, with eigenangle, Wahba cost,
  per-observation residuals and orthogonality error
- gyro noise characterization: overlapping Allan deviation over a
  correlation-time grid, log-log noise slope, noise-process
  classification and the angle random walk coefficient in deg/sqrt(h)
- reaction wheel control: PD gains sized from the axis inertia and the
  control bandwidth, the quaternion-error feedback torque law, torque
  saturation, wheel momentum demand during a slew, momentum margin and
  the momentum-unload (desaturation) cadence
- magnetorquer actuation: dipole-from-torque projection, B-dot
  detumble dipole, torque authority, coil current and the
  underdetermined-axis warning
- pointing error budget: root-sum-square assembly of independent 1-sigma
  contributors, 3-sigma requirement verdict, margin, dominant source and
  remaining-budget allocation

The role also gate-checks deliverables (evidence gates) and runs fully
standalone: no external repository is required. When the Aero Agent
Skills library is present, cli.py dispatches the bound ADCS leaf logic
on identical inputs and records core-vs-skill agreement in the evidence
bundle (docs/PROTOCOL.md cross-check semantics).

Domain rules encoded here are the standard ADCS engineering formulas in
public practice (paraphrased summaries of the same body of knowledge the
bound AeroSkills leaves encode - see SOURCES.md). ECSS text is never
reproduced. Angles are degrees at the report boundary, radians in the
vector math, SI units throughout (N m, N m s, rad/s, kg m^2, s, T,
A m^2, arcsec for pointing errors).
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from datetime import date


def _today() -> str:
    return os.environ.get("ROLE_GEN_DATE", date.today().isoformat())


# ---------------------------------------------------------------------------
# Physical constants (public knowledge)
# ---------------------------------------------------------------------------

MU_EARTH = 3.986004418e14      # m^3/s^2, Earth gravitational parameter
R_EARTH_M = 6371.0e3           # m, mean Earth radius (round figure)
DEG_PER_RAD = 57.2958          # radians to degrees (leaf convention)
ARCSEC_PER_DEG = 3600.0
SECONDS_PER_HOUR = 3600.0


# ---------------------------------------------------------------------------
# Vector / quaternion math (body-frame = measured, reference = model)
# ---------------------------------------------------------------------------

def dot3(u, v):
    return u[0] * v[0] + u[1] * v[1] + u[2] * v[2]


def cross3(u, v):
    return (
        u[1] * v[2] - u[2] * v[1],
        u[2] * v[0] - u[0] * v[2],
        u[0] * v[1] - u[1] * v[0],
    )


def norm3(v):
    return math.sqrt(dot3(v, v))


def normalize3(v):
    n = norm3(v)
    if n <= 0.0:
        raise ValueError("cannot normalize a zero vector")
    return (v[0] / n, v[1] / n, v[2] / n)


def qmul(p, q):
    """Hamilton product of scalar-first quaternions (w, x, y, z)."""
    p0, p1, p2, p3 = p
    q0, q1, q2, q3 = q
    return (
        p0 * q0 - p1 * q1 - p2 * q2 - p3 * q3,
        p0 * q1 + p1 * q0 + p2 * q3 - p3 * q2,
        p0 * q2 - p1 * q3 + p2 * q0 + p3 * q1,
        p0 * q3 + p1 * q2 - p2 * q1 + p3 * q0,
    )


def qconj(q):
    return (q[0], -q[1], -q[2], -q[3])


def qnorm(q):
    return math.sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3])


def qnormalize(q):
    n = qnorm(q)
    if n == 0.0:
        raise ValueError("zero quaternion cannot be normalized")
    return tuple(c / n for c in q)


def qrot(q, v):
    """Active rotation A(q) v = q (x) (0, v) (x) q*; returns the 3-vector."""
    lifted = (0.0, v[0], v[1], v[2])
    out = qmul(qmul(q, lifted), qconj(q))
    return (out[1], out[2], out[3])


def axis_angle_quat(axis, angle_deg):
    """Unit quaternion for a rotation of angle_deg about a unit axis."""
    ax = normalize3(axis)
    half = math.radians(angle_deg) / 2.0
    s = math.sin(half)
    return (math.cos(half), s * ax[0], s * ax[1], s * ax[2])


def quat_eigenangle_deg(q):
    """Rotation angle of the unit quaternion: 2 * atan2(|v|, w)."""
    n = math.sqrt(q[1] * q[1] + q[2] * q[2] + q[3] * q[3])
    return 2.0 * math.degrees(math.atan2(n, abs(q[0])))


def vector_angle_deg(a, b):
    """Angle in degrees between two non-zero vectors (0..180)."""
    na = norm3(a)
    nb = norm3(b)
    if na <= 0.0 or nb <= 0.0:
        raise ValueError("angle needs two non-zero vectors")
    cos_theta = max(-1.0, min(1.0, dot3(a, b) / (na * nb)))
    return math.degrees(math.acos(cos_theta))


# ---------------------------------------------------------------------------
# Orbit
# ---------------------------------------------------------------------------

def orbit_mean_motion(altitude_m):
    """Circular-orbit mean motion n = sqrt(mu / (R + h)^3), rad/s."""
    if altitude_m < 0.0:
        raise ValueError("altitude must be non-negative")
    a = R_EARTH_M + altitude_m
    return math.sqrt(MU_EARTH / a ** 3)


def orbit_period_min(altitude_m):
    """Circular orbit period T = 2*pi/n in minutes."""
    return 2.0 * math.pi / orbit_mean_motion(altitude_m) / 60.0


# ---------------------------------------------------------------------------
# Attitude determination: TRIAD (two vector observations)
# ---------------------------------------------------------------------------

def orthonormal_triad(v1, v2):
    """t1 = v1-hat, t2 = (v1 x v2)-hat, t3 = t1 x t2 (TRIAD construction)."""
    t1 = normalize3(v1)
    c = cross3(v1, v2)
    nc = norm3(c)
    if nc <= 1e-12:
        raise ValueError("parallel or zero observations give no triad")
    t2 = (c[0] / nc, c[1] / nc, c[2] / nc)
    t3 = cross3(t1, t2)
    return t1, t2, t3


def triad_matrix(b1, b2, r1, r2, angle_tol_deg=1e-6):
    """TRIAD attitude matrix A with v_body = A * v_ref.

    b1/b2 are the measured (body) directions, r1/r2 the matching model
    (reference) directions. The angle between the body pair must agree
    with the angle between the reference pair (observation consistency).
    """
    b_angle = vector_angle_deg(b1, b2)
    r_angle = vector_angle_deg(r1, r2)
    if abs(b_angle - r_angle) > angle_tol_deg:
        raise ValueError(
            "observation angles disagree: body %.6f deg vs reference %.6f deg"
            % (b_angle, r_angle)
        )
    bt = orthonormal_triad(b1, b2)
    rt = orthonormal_triad(r1, r2)
    return [
        [sum(bt[k][i] * rt[k][j] for k in range(3)) for j in range(3)]
        for i in range(3)
    ]


def rotation_angle_deg(a):
    """Rotation angle of a 3x3 proper rotation matrix A, in degrees."""
    trace = a[0][0] + a[1][1] + a[2][2]
    cos_theta = max(-1.0, min(1.0, (trace - 1.0) / 2.0))
    return math.degrees(math.acos(cos_theta))


def orthogonality_error(a):
    """Largest |A A^T - I| element; ~0 for a proper rotation matrix."""
    worst = 0.0
    for i in range(3):
        for j in range(3):
            prod = sum(a[i][k] * a[j][k] for k in range(3))
            target = 1.0 if i == j else 0.0
            worst = max(worst, abs(prod - target))
    return worst


# ---------------------------------------------------------------------------
# Attitude determination: QUEST / Davenport q-method (N >= 2 observations)
# ---------------------------------------------------------------------------

def attitude_profile(observations, references, weights=None):
    """Wahba profile matrix B = sum_i w_i b_i r_i^T."""
    nobs = len(observations)
    if nobs < 2:
        raise ValueError("at least 2 observations are required")
    if len(references) != nobs:
        raise ValueError("observation and reference counts differ")
    if weights is None:
        weights = [1.0] * nobs
    if len(weights) != nobs:
        raise ValueError("weights length differs from observation count")
    b = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
    for i in range(nobs):
        if weights[i] <= 0.0:
            raise ValueError("weights must be strictly positive")
        w = weights[i]
        for row in range(3):
            for col in range(3):
                b[row][col] += w * observations[i][row] * references[i][col]
    return b


def davenport_k_matrix(b):
    """Symmetric 4x4 Davenport K from the profile matrix B (scalar-last)."""
    sigma = b[0][0] + b[1][1] + b[2][2]
    z = (b[2][1] - b[1][2], b[0][2] - b[2][0], b[1][0] - b[0][1])
    k = [[0.0] * 4 for _ in range(4)]
    for i in range(3):
        for j in range(3):
            k[i][j] = b[i][j] + b[j][i] - (sigma if i == j else 0.0)
    for i in range(3):
        k[i][3] = z[i]
        k[3][i] = z[i]
    k[3][3] = sigma
    return k


def _jacobi_eigen_sym4(k, max_sweeps=60, tol=1e-13):
    """Fixed-sweep Jacobi eigen-decomposition of a symmetric 4x4 matrix.

    Returns (eigenvalues, eigenvectors) with the eigenvector columns of V
    matching the diagonal eigenvalue order. Deterministic: always zeroes
    the largest off-diagonal entry until it falls below tol.
    """
    a = [row[:] for row in k]
    v = [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]
    for _ in range(max_sweeps):
        p = 0
        q = 1
        largest = 0.0
        for i in range(4):
            for j in range(i + 1, 4):
                if abs(a[i][j]) > largest:
                    largest = abs(a[i][j])
                    p, q = i, j
        if largest < tol:
            break
        theta = 0.5 * math.atan2(2.0 * a[p][q], a[q][q] - a[p][p])
        c = math.cos(theta)
        s = math.sin(theta)
        for kk in range(4):
            if kk == p or kk == q:
                continue
            akp = a[kk][p]
            akq = a[kk][q]
            a[kk][p] = a[p][kk] = c * akp - s * akq
            a[kk][q] = a[q][kk] = s * akp + c * akq
        app = a[p][p]
        aqq = a[q][q]
        apq = a[p][q]
        a[p][p] = c * c * app - 2.0 * c * s * apq + s * s * aqq
        a[q][q] = s * s * app + 2.0 * c * s * apq + c * c * aqq
        a[p][q] = a[q][p] = 0.0
        for i in range(4):
            vip = v[i][p]
            viq = v[i][q]
            v[i][p] = c * vip - s * viq
            v[i][q] = s * vip + c * viq
    return [a[i][i] for i in range(4)], v


def wahba_cost(q, observations, references, weights=None):
    """Wahba cost J(q) = sum_i w_i |b_i - A(q) r_i|^2."""
    if weights is None:
        weights = [1.0] * len(observations)
    total = 0.0
    for i in range(len(observations)):
        av = qrot(q, references[i])
        dx = observations[i][0] - av[0]
        dy = observations[i][1] - av[1]
        dz = observations[i][2] - av[2]
        total += weights[i] * (dx * dx + dy * dy + dz * dz)
    return total


def quest_solution(observations, references, weights=None):
    """Optimal attitude by the Davenport q-method (QUEST).

    Returns {q_optimal (w,x,y,z), lambda_max, residuals (per-observation
    Euclidean norms), wahba_cost, eigenangle_deg}. The optimal quaternion
    is the unit eigenvector of K for the largest eigenvalue, read
    scalar-last; the sign is canonicalized to w >= 0.
    """
    b = attitude_profile(observations, references, weights)
    k = davenport_k_matrix(b)
    eigenvalues, vecs = _jacobi_eigen_sym4(k)
    imax = max(range(4), key=lambda i: eigenvalues[i])
    lambda_max = eigenvalues[imax]
    q_raw = (vecs[3][imax], vecs[0][imax], vecs[1][imax], vecs[2][imax])
    q = qnormalize(q_raw)
    if q[0] < 0.0:
        q = tuple(-c for c in q)
    if weights is None:
        wts = [1.0] * len(observations)
    else:
        wts = weights
    residuals = []
    for i in range(len(observations)):
        av = qrot(q, references[i])
        dx = observations[i][0] - av[0]
        dy = observations[i][1] - av[1]
        dz = observations[i][2] - av[2]
        residuals.append(math.sqrt(dx * dx + dy * dy + dz * dz))
    cost = sum(wts[i] * residuals[i] * residuals[i]
               for i in range(len(observations)))
    return {
        "q_optimal": q,
        "lambda_max": lambda_max,
        "residuals": residuals,
        "wahba_cost": cost,
        "eigenangle_deg": quat_eigenangle_deg(q),
    }


# ---------------------------------------------------------------------------
# Gyro noise: overlapping Allan deviation -> angle random walk
# ---------------------------------------------------------------------------

def _deterministic_white_series(n_samples, sigma_rad_s, seed=20260904):
    """Deterministic zero-mean pseudo-white Gaussian rate series (rad/s).

    Linear congruential generator (integer arithmetic, fixed seed) mapped
    to unit uniforms, Box-Muller transform to Gaussian pairs. Output is
    bit-identical on every run and every platform - no external RNG state.
    """
    x = seed & 0x7FFFFFFF
    out = []
    while len(out) < n_samples:
        x = (1103515245 * x + 12345) & 0x7FFFFFFF
        u1 = x / 2147483648.0
        x = (1103515245 * x + 12345) & 0x7FFFFFFF
        u2 = x / 2147483648.0
        u1 = max(u1, 1e-12)
        r = math.sqrt(-2.0 * math.log(u1))
        out.append(r * math.cos(2.0 * math.pi * u2) * sigma_rad_s)
        if len(out) < n_samples:
            out.append(r * math.sin(2.0 * math.pi * u2) * sigma_rad_s)
    return out[:n_samples]


def overlapping_allan_deviation(rate_samples, tau0_s, taus):
    """Overlapping Allan deviation AD(tau) in rad/s (IEEE-952 style).

    AD(tau) = sqrt( 1/(2(N-2m)) * sum_{k=0}^{N-2m-1}
                    (mean(s[k+m:k+2m]) - mean(s[k:k+m]))^2 )
    computed with cumulative sums for stability on long series.
    """
    n_samples = len(rate_samples)
    if n_samples < 3:
        raise ValueError("at least 3 rate samples are required")
    if tau0_s <= 0.0:
        raise ValueError("tau0_s must be positive")
    sums = [0.0] * (n_samples + 1)
    acc = 0.0
    for i, value in enumerate(rate_samples):
        acc += value
        sums[i + 1] = acc
    ads = []
    for tau in taus:
        if tau < tau0_s:
            raise ValueError("cluster time below the sample period")
        m_float = tau / tau0_s
        m = int(round(m_float))
        if m < 1 or abs(m_float - m) > 1e-9 * max(1.0, abs(m_float)):
            raise ValueError("cluster time must be a whole multiple of tau0_s")
        if m > (n_samples - 1) / 2.0:
            raise ValueError("cluster time exceeds half the sample length")
        limit = n_samples - 2 * m
        inv_m = 1.0 / m
        total = 0.0
        for k in range(limit):
            diff = (sums[k + 2 * m] - 2.0 * sums[k + m] + sums[k]) * inv_m
            total += diff * diff
        ads.append(math.sqrt(total / (2.0 * limit)))
    return ads


def noise_slope(log_taus, log_ads):
    """Least-squares slope of log(AD) against log(tau)."""
    if len(log_taus) < 2 or len(log_taus) != len(log_ads):
        raise ValueError("slope fit needs >= 2 matching points")
    n = len(log_taus)
    mean_x = sum(log_taus) / n
    mean_y = sum(log_ads) / n
    cov = 0.0
    var_x = 0.0
    for x, y in zip(log_taus, log_ads):
        cov += (x - mean_x) * (y - mean_y)
        var_x += (x - mean_x) * (x - mean_x)
    if var_x == 0.0:
        raise ValueError("log-tau grid has zero variance")
    return cov / var_x


def classify_noise(slope):
    """Noise process from the log-log Allan slope band.

    Slope ~= -1 quantization, ~= -1/2 angle random walk, ~= 0 bias
    instability, ~= +1/2 rate random walk (standard Allan taxonomy).
    """
    if slope <= -0.85:
        return "quantization-noise"
    if -0.75 <= slope <= -0.25:
        return "angle-random-walk"
    if 0.25 <= slope <= 0.75:
        return "rate-random-walk"
    if abs(slope) < 0.15:
        return "bias-instability"
    return "mixed"


def angle_random_walk_coeff(ad_at_tau1, tau0_s=1.0):
    """ARW coefficient N in deg/sqrt(h) = AD(1 s) * 57.2958 * sqrt(3600*tau0)."""
    if ad_at_tau1 <= 0.0:
        raise ValueError("ad_at_tau1 must be positive")
    if tau0_s <= 0.0:
        raise ValueError("tau0_s must be positive")
    return ad_at_tau1 * DEG_PER_RAD * math.sqrt(SECONDS_PER_HOUR * tau0_s)


def gyro_noise_characterization(rate_samples, tau0_s=1.0,
                                taus=(1.0, 2.0, 5.0, 10.0, 30.0, 60.0)):
    """Full gyro characterization over a tau grid (rad/s samples).

    Returns taus, allan_deviations, fitted_slope, noise_class,
    arw_deg_per_sqrt_h and ad_at_1s.
    """
    ads = overlapping_allan_deviation(rate_samples, tau0_s, taus)
    tau_list = list(taus)
    slope = noise_slope([math.log(t) for t in tau_list],
                        [math.log(a) for a in ads])
    ad_at_1s = overlapping_allan_deviation(rate_samples, tau0_s, [1.0])[0]
    return {
        "taus": tau_list,
        "allan_deviations": ads,
        "fitted_slope": slope,
        "noise_class": classify_noise(slope),
        "arw_deg_per_sqrt_h": angle_random_walk_coeff(ad_at_1s, tau0_s),
        "ad_at_1s": ad_at_1s,
    }


# ---------------------------------------------------------------------------
# Reaction wheel control
# ---------------------------------------------------------------------------

def quaternion_error(q_current, q_ref):
    """q_err = q_current (x) q_ref^-1: identity when the bus is at q_ref."""
    return qnormalize(qmul(q_current, qconj(q_ref)))


def attitude_error_vector(q_err):
    """Small-angle attitude error vector theta_err = 2 * q_err_vec (rad)."""
    return (2.0 * q_err[1], 2.0 * q_err[2], 2.0 * q_err[3])


def pd_gains(inertia, wn_rad_s, zeta):
    """PD gains for the quaternion-error law tau = -kp*theta - kd*omega.

    With I * theta_ddot = tau: kp = I*wn^2 (N m / rad) and
    kd = 2*zeta*wn*I (N m s / rad), i.e. wn the undamped natural
    frequency and zeta the damping ratio of the closed loop.
    """
    if inertia <= 0.0 or wn_rad_s <= 0.0 or zeta <= 0.0:
        raise ValueError("inertia, wn and zeta must be positive")
    return inertia * wn_rad_s * wn_rad_s, 2.0 * zeta * wn_rad_s * inertia


def pd_wheel_torque(kp, kd, theta_err_vec, omega_err):
    """Wheel torque command tau = -kp*theta_err - kd*omega_err (N m)."""
    if kp <= 0.0 or kd <= 0.0:
        raise ValueError("kp and kd must be positive")
    return (
        -kp * theta_err_vec[0] - kd * omega_err[0],
        -kp * theta_err_vec[1] - kd * omega_err[1],
        -kp * theta_err_vec[2] - kd * omega_err[2],
    )


def torque_saturation(tau_cmd, tau_max):
    """Per-axis clip of a torque command at +-tau_max.

    Returns (tau_clipped, saturated) where saturated is True when any
    axis was clipped. tau_max may be scalar (applied to every axis) or
    a per-axis sequence (N m). The clipped tuple keeps the length of
    tau_cmd (1 axis for the scalar slew demo, 3 axes otherwise).
    """
    n = len(tau_cmd)
    limits = (tau_max,) * n if isinstance(tau_max, (int, float)) \
        else tuple(tau_max)
    if len(limits) != n:
        raise ValueError("tau_max length must match tau_cmd")
    clipped = []
    flagged = False
    for c, lim in zip(tau_cmd, limits):
        if lim <= 0.0:
            raise ValueError("tau_max must be positive")
        clipped.append(max(-lim, min(lim, c)))
        if abs(c) > lim:
            flagged = True
    return tuple(clipped), flagged


def momentum_saturation(h_w, h_max):
    """Per-axis wheel momentum vs the limit h_max.

    Returns (excess, flag): excess is the amount above the limit per
    axis and flag is True when any axis exceeds it (desat needed).
    """
    limits = (h_max, h_max, h_max) if isinstance(h_max, (int, float)) \
        else tuple(h_max)
    excess = []
    flagged = False
    for c, lim in zip(h_w, limits):
        if lim <= 0.0:
            raise ValueError("h_max must be positive")
        over = abs(c) - lim
        excess.append(max(0.0, over))
        if over > 0.0:
            flagged = True
    return (excess[0], excess[1], excess[2]), flagged


def desaturation_torque(h_w, h_target, t_desat):
    """Unload torque tau = -(h_w - h_target) / t_desat over horizon (s)."""
    if t_desat <= 0.0:
        raise ValueError("t_desat must be positive")
    return (
        -(h_w[0] - h_target[0]) / t_desat,
        -(h_w[1] - h_target[1]) / t_desat,
        -(h_w[2] - h_target[2]) / t_desat,
    )


def wheel_slew_run_z(inertia, theta0_rad, wn_rad_s, zeta, tau_max,
                     h_max, dt=0.1, t_max=500.0, settle_frac=0.01):
    """Scalar z-axis acquisition run: PD law + torque clip + momentum.

    Returns measured closed-loop metrics: the initial torque demand
    before clipping, whether it clipped and for how long, the 1% settle
    time, the peak wheel momentum demand, the final momentum and the
    momentum-saturation flag. The wheel cluster absorbs the bus momentum
    change, so the per-axis wheel momentum demand is |I * omega|.
    """
    kp, kd = pd_gains(inertia, wn_rad_s, zeta)
    theta = theta0_rad
    omega = 0.0
    t = 0.0
    tau0_demand = kp * theta0_rad
    last_clipped_t = None
    settle_time = None
    h_peak = 0.0
    while t < t_max:
        tau_d = -(kp * theta + kd * omega)
        tau, was_clipped = torque_saturation((tau_d,), tau_max)
        tau = tau[0]
        omega += (tau / inertia) * dt
        theta += omega * dt
        h_wheel = abs(inertia * omega)
        h_peak = max(h_peak, h_wheel)
        if was_clipped:
            last_clipped_t = t  # torque-limited phase is still active
        if settle_time is None and abs(theta) <= settle_frac * theta0_rad:
            settle_time = t
        t += dt
    return {
        "kp": kp,
        "kd": kd,
        "tau0_demand": tau0_demand,
        "tau0_demand_clipped": tau0_demand > tau_max,
        "clipped_until_s": last_clipped_t if last_clipped_t is not None else 0.0,
        "settle_time_1pct_s": settle_time if settle_time is not None else t_max,
        "h_peak_nms": h_peak,
        "final_momentum_nms": abs(inertia * omega),
        "momentum_saturation": h_peak > h_max,
    }


# ---------------------------------------------------------------------------
# Magnetorquer actuation
# ---------------------------------------------------------------------------

def dipole_from_torque(torque, b_field):
    """Dipole solving torque = m x B: m = (B x torque) / |B|^2.

    Returns (m, along_b) with along_b the unachievable torque component
    along B (any dipole torque is perpendicular to B).
    """
    bnorm = norm3(b_field)
    if bnorm == 0.0:
        raise ValueError("zero magnetic field: dipole undefined")
    bx = cross3(b_field, torque)
    scale = 1.0 / (bnorm * bnorm)
    m = (bx[0] * scale, bx[1] * scale, bx[2] * scale)
    bhat = (b_field[0] / bnorm, b_field[1] / bnorm, b_field[2] / bnorm)
    along = dot3(torque, bhat)
    along_b = (along * bhat[0], along * bhat[1], along * bhat[2])
    return m, along_b


def bdot_dipole(rate, b_field, gain):
    """B-dot detumble dipole m = gain * (omega x B) (A m^2)."""
    if norm3(b_field) == 0.0:
        raise ValueError("zero magnetic field: B-dot dipole undefined")
    cx = cross3(rate, b_field)
    return (gain * cx[0], gain * cx[1], gain * cx[2])


def achievable_torque(m, b_field):
    """|m x B|, the torque magnitude a dipole m exerts in field B."""
    return norm3(cross3(m, b_field))


def torque_authority(m_max, b_field):
    """Largest magnetorquer torque: m_max * |B| (perpendicular geometry)."""
    return m_max * norm3(b_field)


def coil_current_for_dipole(dipole, turns, area):
    """Coil current I = m / (N * A) producing dipole m (A)."""
    denominator = turns * area
    if denominator == 0.0:
        raise ValueError("coil turns * area must be nonzero")
    return dipole / denominator


def bdot_detumble_assessment(tipoff_rad_s, b_field, m_max, gain,
                             inertia):
    """B-dot detumble: dipole demand, achievable torque, damping time.

    Uses the perpendicular worst geometry |omega x B| = |omega| |B| and
    the damping time tau = |omega| * I / (m_max * |B|) when the demand
    clips at the torque-rod limit.
    """
    bmag = norm3(b_field)
    m_demand = gain * tipoff_rad_s * bmag
    m_used = min(m_demand, m_max)
    torque = m_used * bmag
    damping_s = tipoff_rad_s * inertia / torque if torque > 0.0 else float("inf")
    return {
        "tipoff_rad_s": tipoff_rad_s,
        "dipole_demand_a_m2": m_demand,
        "dipole_used_a_m2": m_used,
        "clipped_at_m_max": m_demand > m_max,
        "achievable_torque_nm": torque,
        "damping_time_s": damping_s,
    }


# ---------------------------------------------------------------------------
# Pointing error budget (RSS assembly, arcsec)
# ---------------------------------------------------------------------------

def rss_pointing_error(components_1sigma):
    """Root-sum-square of independent 1-sigma contributors."""
    items = list(components_1sigma.items())
    if not items:
        raise ValueError("components_1sigma must not be empty")
    variance = sum(v * v for _, v in items)
    return math.sqrt(variance)


def three_sigma_error(components_1sigma):
    """3-sigma pointing error: 3 * RSS of the 1-sigma contributors."""
    return 3.0 * rss_pointing_error(components_1sigma)


def three_sigma_verdict(components_1sigma, requirement_3sigma):
    """True when the RSS 3-sigma error meets the 3-sigma requirement."""
    if requirement_3sigma <= 0.0:
        raise ValueError("requirement_3sigma must be positive")
    return three_sigma_error(components_1sigma) <= requirement_3sigma


def dominant_error_source(components_1sigma):
    """(name, variance_share) of the largest-variance contributor."""
    items = list(components_1sigma.items())
    variance = sum(v * v for _, v in items)
    if variance == 0.0:
        raise ValueError("components must not be all zero")
    name, value = max(items, key=lambda kv: kv[1] * kv[1])
    return name, value * value / variance


def allocate_error_budget(requirement_3sigma, fixed_components_1sigma):
    """1-sigma budget left for one new contributor:
    sqrt((req/3)^2 - sum(fixed^2))."""
    if requirement_3sigma <= 0.0:
        raise ValueError("requirement_3sigma must be positive")
    one_sigma_budget = requirement_3sigma / 3.0
    fixed_variance = sum(v * v for _, v in fixed_components_1sigma.items())
    radicand = one_sigma_budget * one_sigma_budget - fixed_variance
    if radicand < 0.0:
        raise ValueError("fixed contributors exceed the 1-sigma budget")
    return math.sqrt(radicand)


def pointing_error_budget(components_1sigma, requirement_3sigma):
    """Full budget assembly: RSS, verdict, margin, dominant, allocation."""
    rss_1 = rss_pointing_error(components_1sigma)
    rss_3 = 3.0 * rss_1
    variance = sum(v * v for v in components_1sigma.values())
    shares = {k: v * v / variance for k, v in components_1sigma.items()}
    dom_name, dom_share = dominant_error_source(components_1sigma)
    try:
        alloc = allocate_error_budget(requirement_3sigma, components_1sigma)
    except ValueError:
        # Fixed contributors already exceed the 1-sigma budget: no
        # allocation is possible. The report still records the verdict
        # (requirement_met False) rather than failing to build.
        alloc = None
    return {
        "rss_1sigma": rss_1,
        "rss_3sigma": rss_3,
        "requirement_met": three_sigma_verdict(components_1sigma,
                                               requirement_3sigma),
        "margin": requirement_3sigma / rss_3 if rss_3 > 0.0 else float("inf"),
        "dominant": dom_name,
        "dominant_variance_share": dom_share,
        "variance_shares": shares,
        "allocation_1sigma": alloc,
        "allocation_3sigma": 3.0 * alloc if alloc is not None else None,
    }


# ---------------------------------------------------------------------------
# Reference spacecraft (project facts for the worked example)
# ---------------------------------------------------------------------------

@dataclass
class Spacecraft:
    """Project facts the role needs. Inputs are labeled assumptions.

    Defaults instantiate the reference item: Aurora-1, a 3-axis
    stabilized 600 km sun-synchronous Earth-observation microsatellite.
    """
    name: str = "Aurora-1"
    mission: str = "sun-synchronous Earth observation microsatellite"
    orbit_altitude_km: float = 600.0
    orbit_inclination_deg: float = 97.8
    inertia_xy_kg_m2: float = 60.0          # assumed principal moments,
    inertia_z_kg_m2: float = 35.0           # from the project mass model
    slew_target_deg: float = 10.0           # z-axis acquisition slew
    wn_rad_s: float = 0.05                  # control bandwidth
    zeta: float = 0.8                       # closed-loop damping ratio
    wheel_tau_max_nm: float = 0.01          # per-wheel torque limit
    wheel_h_max_nms: float = 0.2            # per-wheel momentum capacity
    wheel_h_bias_nms: float = 0.02          # momentum kept after unload
    wheel_unload_fraction: float = 0.70     # unload trigger, fraction of h_max
    desat_horizon_s: float = 600.0
    env_torque_nm_per_axis: float = 1.0e-5  # worst-case env. disturbance
    b_field_t: float = 2.5e-5               # field magnitude at 600 km SSO
    mag_m_max_a_m2: float = 20.0            # magnetorquer dipole limit
    mag_gain: float = 9.0e7                 # B-dot loop gain
    mag_turns: int = 200
    mag_coil_area_m2: float = 0.1
    tipoff_deg_s: float = 0.5               # worst-case separation rate
    requirement_arcsec_3sigma: float = 30.0  # payload pointing requirement
    tracker_noise_arcsec_1sigma: float = 2.0   # component specs below are
    control_deadband_arcsec_1sigma: float = 3.0  # project input facts
    wheel_jitter_arcsec_1sigma: float = 1.5
    thermal_arcsec_1sigma: float = 1.0
    reference_frame: str = "ECI (J2000)"


def example_item() -> Spacecraft:
    return Spacecraft()


def example_observation_set(slew_deg=10.0):
    """Deterministic vector-observation set for the example report.

    Truth model: a rotation of slew_deg about +z (body z = nadir roll
    axis convention of the worked example). TRIAD uses the sun-sensor /
    magnetometer pair; QUEST uses three weighted observations (star
    tracker, sun sensor, magnetometer). Observations are noiseless so
    the report presents a truth-model validation of the estimator chain
    (recovered eigenangle, Wahba cost ~ 0, residual RMS ~ 0).
    """
    axis = (0.0, 0.0, 1.0)
    q_true = axis_angle_quat(axis, slew_deg)
    r1 = (1.0, 0.0, 0.0)      # sun direction, reference frame
    r2 = (0.0, 0.0, 1.0)      # nadir direction, reference frame
    r3 = (0.0, 1.0, 0.0)      # cross-track star direction
    b1 = qrot(q_true, r1)     # measured sun direction, body frame
    b2 = qrot(q_true, r2)     # measured nadir direction, body frame
    b3 = qrot(q_true, r3)     # measured star direction, body frame
    weights = (1.0, 1.0, 1.0)
    return {
        "q_true": q_true,
        "triad": {"b1": b1, "b2": b2, "r1": r1, "r2": r2},
        "quest": {"observations": (b1, b3, b2),
                  "references": (r1, r3, r2),
                  "weights": weights},
        "slew_deg": slew_deg,
    }


def example_gyro_samples():
    """Deterministic gyro rate series for the example (see gyro section).

    2 h of 1 s samples of white rate noise at sigma = 1e-5 rad/s - a
    tactical fiber-optic gyro class input. Deterministic across runs.
    """
    return _deterministic_white_series(7200, 1.0e-5)


def _gyro_propagation_arcsec(arw_deg_per_sqrt_h, gap_s):
    """1-sigma angle error over gap_s: ARW integrates as a random walk.

    sigma_deg = N * sqrt(gap/3600) with N in deg/sqrt(h).
    """
    return arw_deg_per_sqrt_h * math.sqrt(gap_s / SECONDS_PER_HOUR) \
        * ARCSEC_PER_DEG


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_report(item: Spacecraft) -> dict:
    """Build the ADCS report content model from the project facts."""
    # orbit
    n_rad_s = orbit_mean_motion(item.orbit_altitude_km * 1000.0)
    period_min = orbit_period_min(item.orbit_altitude_km * 1000.0)
    period_s = period_min * 60.0
    per_orbit_impulse = item.env_torque_nm_per_axis * period_s

    # determination (truth-model observation set)
    obs_set = example_observation_set(item.slew_target_deg)
    tr = obs_set["triad"]
    a_triad = triad_matrix(tr["b1"], tr["b2"], tr["r1"], tr["r2"])
    triad_angle = rotation_angle_deg(a_triad)
    triad_ortho = orthogonality_error(a_triad)
    qs = obs_set["quest"]
    quest = quest_solution(qs["observations"], qs["references"],
                           qs["weights"])
    residual_rms = math.sqrt(sum(r * r for r in quest["residuals"])
                             / len(quest["residuals"])) \
        if quest["residuals"] else 0.0

    # gyro
    samples = example_gyro_samples()
    gyro = gyro_noise_characterization(samples)
    # 1-sigma propagation over the star tracker update gap (1 s)
    gyro_prop_arcsec = _gyro_propagation_arcsec(
        gyro["arw_deg_per_sqrt_h"], 1.0)

    # reaction wheel control (z-axis acquisition slew)
    run = wheel_slew_run_z(item.inertia_z_kg_m2,
                           math.radians(item.slew_target_deg),
                           item.wn_rad_s, item.zeta,
                           item.wheel_tau_max_nm, item.wheel_h_max_nms)
    h_unload = item.wheel_unload_fraction * item.wheel_h_max_nms
    h_avail = h_unload - item.wheel_h_bias_nms
    orbits_per_unload = h_avail / per_orbit_impulse if per_orbit_impulse > 0 \
        else float("inf")
    # unload demand at the trigger level, over the desat horizon
    tau_desat = desaturation_torque(
        (0.0, 0.0, h_unload), (0.0, 0.0, item.wheel_h_bias_nms),
        item.desat_horizon_s)
    # favorable geometry: B transverse, desat torque perpendicular to B
    b_vec = (0.0, item.b_field_t, 0.0)
    m_desat, along_b = dipole_from_torque(tau_desat, b_vec)
    m_desat_mag = norm3(m_desat)
    along_b_mag = norm3(along_b)
    authority = torque_authority(item.mag_m_max_a_m2, b_vec)
    coil_current = coil_current_for_dipole(
        item.mag_m_max_a_m2, item.mag_turns, item.mag_coil_area_m2)

    # B-dot detumble
    bdot = bdot_detumble_assessment(
        math.radians(item.tipoff_deg_s), b_vec, item.mag_m_max_a_m2,
        item.mag_gain, item.inertia_xy_kg_m2)

    # pointing error budget
    contributors = {
        "Star tracker determination noise (1-sigma, per axis)":
            item.tracker_noise_arcsec_1sigma,
        "Gyro propagation over 1 s update gap (ARW)":
            round(gyro_prop_arcsec, 4),
        "Control deadband / limit cycle":
            item.control_deadband_arcsec_1sigma,
        "Reaction wheel jitter":
            item.wheel_jitter_arcsec_1sigma,
        "Thermal / mechanical distortion":
            item.thermal_arcsec_1sigma,
    }
    budget = pointing_error_budget(contributors,
                                   item.requirement_arcsec_3sigma)

    q_opt = quest["q_optimal"]
    model = {
        "document_type": "Attitude Determination and Control Subsystem "
                         "Report",
        "status": "draft-for-review",
        "item": {
            "name": item.name,
            "mission": item.mission,
            "reference_frame": item.reference_frame,
            "orbit_altitude_km": item.orbit_altitude_km,
            "orbit_inclination_deg": item.orbit_inclination_deg,
            "orbit_semi_major_km": (R_EARTH_M / 1000.0)
                                   + item.orbit_altitude_km,
            "orbit_mean_motion_rad_s": n_rad_s,
            "orbit_period_min": period_min,
            "inertia_xy_kg_m2": item.inertia_xy_kg_m2,
            "inertia_z_kg_m2": item.inertia_z_kg_m2,
        },
        "requirement_arcsec_3sigma": item.requirement_arcsec_3sigma,
        "environment": {
            "disturbance_torque_nm_per_axis": item.env_torque_nm_per_axis,
            "field_magnitude_t": item.b_field_t,
            "per_orbit_impulse_nms": per_orbit_impulse,
        },
        "determination": {
            "coarse_method": "TRIAD (sun sensor + magnetometer pair)",
            "fine_method": "QUEST (Davenport q-method, weighted vector "
                           "observations)",
            "slew_target_deg": item.slew_target_deg,
            "triad_rotation_angle_deg": triad_angle,
            "triad_orthogonality_error": triad_ortho,
            "triad_obs_consistency_deg": 90.0,
            "q_optimal": [round(q_opt[0], 9), round(q_opt[1], 9),
                          round(q_opt[2], 9), round(q_opt[3], 9)],
            "quest_eigenangle_deg": quest["eigenangle_deg"],
            "quest_lambda_max": quest["lambda_max"],
            "quest_wahba_cost": quest["wahba_cost"],
            "quest_residual_rms": residual_rms,
            "quest_residual_rms_arcsec": residual_rms * DEG_PER_RAD
                                         * ARCSEC_PER_DEG,
        },
        "gyro": {
            "sample_period_s": 1.0,
            "n_samples": len(samples),
            "noise_sigma_rad_s": 1.0e-5,
            "taus_s": gyro["taus"],
            "allan_deviations_rad_s": gyro["allan_deviations"],
            "fitted_slope": gyro["fitted_slope"],
            "noise_class": gyro["noise_class"],
            "ad_at_1s_rad_s": gyro["ad_at_1s"],
            "arw_deg_per_sqrt_h": gyro["arw_deg_per_sqrt_h"],
            "propagation_1s_arcsec_1sigma": gyro_prop_arcsec,
        },
        "control": {
            "bandwidth_rad_s": item.wn_rad_s,
            "damping_ratio": item.zeta,
            "kp_z_nm_per_rad": run["kp"],
            "kd_z_nm_s_per_rad": run["kd"],
            "tau_max_nm": item.wheel_tau_max_nm,
            "tau0_demand_nm": run["tau0_demand"],
            "tau0_demand_clipped": run["tau0_demand_clipped"],
            "clipped_until_s": run["clipped_until_s"],
            "settle_time_1pct_s": run["settle_time_1pct_s"],
            "h_peak_nms": run["h_peak_nms"],
            "h_max_nms": item.wheel_h_max_nms,
            "momentum_margin": item.wheel_h_max_nms / run["h_peak_nms"]
                               if run["h_peak_nms"] > 0 else float("inf"),
            "momentum_saturation": run["momentum_saturation"],
            "h_bias_nms": item.wheel_h_bias_nms,
            "h_unload_trigger_nms": h_unload,
            "per_orbit_momentum_nms": per_orbit_impulse,
            "orbits_per_unload": orbits_per_unload,
            "desat_horizon_s": item.desat_horizon_s,
            "desat_torque_nm": norm3(tau_desat),
            "desat_dipole_a_m2": m_desat_mag,
            "desat_alignment_warning": along_b_mag > 1e-12,
            "mag_torque_authority_nm": authority,
            "desat_margin": authority / norm3(tau_desat)
                            if norm3(tau_desat) > 0 else float("inf"),
            "mag_m_max_a_m2": item.mag_m_max_a_m2,
            "mag_turns": item.mag_turns,
            "mag_coil_area_m2": item.mag_coil_area_m2,
            "mag_coil_current_a": coil_current,
            "bdot": bdot,
        },
        "pointing_budget": {
            "contributors_arcsec_1sigma": contributors,
            "rss_1sigma_arcsec": budget["rss_1sigma"],
            "rss_3sigma_arcsec": budget["rss_3sigma"],
            "requirement_met": budget["requirement_met"],
            "margin": budget["margin"],
            "dominant": budget["dominant"],
            "dominant_variance_share": budget["dominant_variance_share"],
            "variance_shares": budget["variance_shares"],
            "allocation_1sigma_arcsec": budget["allocation_1sigma"],
            "allocation_3sigma_arcsec": budget["allocation_3sigma"],
        },
        "generated": _today(),
    }
    return model


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------

def _md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "|" + "---|" * len(headers)]
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return out


def render_report_markdown(model: dict) -> str:
    """Render the ADCS content model as the deliverable markdown report."""
    it = model["item"]
    env = model["environment"]
    det = model["determination"]
    gy = model["gyro"]
    ct = model["control"]
    pb = model["pointing_budget"]
    req = model["requirement_arcsec_3sigma"]

    allan_rows = [[f"{t:g} s", f"{a:.3e} rad/s"]
                  for t, a in zip(gy["taus_s"], gy["allan_deviations_rad_s"])]

    contrib_rows = []
    for name, val in pb["contributors_arcsec_1sigma"].items():
        share = pb["variance_shares"].get(
            name, pb.get("dominant_variance_share", 0.0))
        contrib_rows.append([name, f"{val:.2f}", f"{share * 100.0:.1f}%"])

    if pb["allocation_1sigma_arcsec"] is None:
        alloc_line = "- Budget remaining for a new contributor: none - " \
                     "fixed contributors already exceed the 1-sigma budget"
    else:
        alloc_line = (f"- Budget remaining for a new contributor: "
                      f"{pb['allocation_1sigma_arcsec']:.2f} arcsec 1-sigma "
                      f"({pb['allocation_3sigma_arcsec']:.2f} arcsec "
                      f"3-sigma)")
    lines = [
        "# Attitude Determination and Control Subsystem Report",
        "",
        f"**Spacecraft:** {it['name']} - {it['mission']}",
        f"**Orbit:** {it['orbit_altitude_km']:g} km circular, "
        f"{it['orbit_inclination_deg']:g} deg inclination "
        f"(period {it['orbit_period_min']:.1f} min, mean motion "
        f"{it['orbit_mean_motion_rad_s']:.6g} rad/s).",
        f"**Reference frame:** {it['reference_frame']}.",
        f"**Pointing requirement (3-sigma):** {req:.1f} arcsec "
        "cross-boresight (payload requirement).",
        f"**Status:** {model['status']}",
        "",
        "## 1. Scope and reference mission",
        "",
        f"This report covers the attitude determination and control "
        f"subsystem (ADCS) of {it['name']}. It assembles the pointing "
        "error budget, sizes and checks the reaction wheel control law, "
        "the momentum management (desaturation) strategy and the "
        "magnetorquer actuation, and validates the attitude "
        "determination chain on a truth-model observation set.",
        "",
        "All numbers below come from the standard ADCS formulas listed in "
        "SOURCES.md and the bound Aero Agent Skills leaves; component "
        "specifications and mass-model values are labeled project "
        "inputs for this worked example and must be verified against "
        "mission data before release.",
        "",
        "### Assumed project facts (inputs)",
        "",
        *[
            f"- {k}: {v}"
            for k, v in {
                "Principal inertia (x/y, z)":
                    f"{it['inertia_xy_kg_m2']:g} / {it['inertia_z_kg_m2']:g} "
                    "kg m^2",
                "Wheel torque limit": f"{ct['tau_max_nm']:g} N m per wheel",
                "Wheel momentum capacity": f"{ct['h_max_nms']:g} N m s",
                "Worst-case environmental torque":
                    f"{env['disturbance_torque_nm_per_axis']:g} N m per "
                    "axis",
                "Magnetic field magnitude (orbit)":
                    f"{env['field_magnitude_t']:.2g} T",
                "Magnetorquer dipole limit":
                    f"{ct['mag_m_max_a_m2']:g} A m^2",
            }.items()
        ],
        "",
        "## 2. Pointing requirements and ADCS modes",
        "",
        f"The payload requires {req:.1f} arcsec (3-sigma) cross-boresight "
        "pointing. The ADCS modes are mapped to the bound skills that "
        "deepen each stage: safe hold / sun pointing, B-dot detumble, "
        "coarse and fine attitude determination, acquisition slew and "
        "fine pointing (see the workflow in ROLE.md).",
        "",
        "## 3. Environment and disturbance assumptions",
        "",
        f"Worst-case environmental torque is assumed at "
        f"{env['disturbance_torque_nm_per_axis']:.1g} N m per axis "
        "(project environmental assessment; method per the bound "
        "environmental-disturbance-torque-budget leaf). Over one orbit "
        f"this accumulates {env['per_orbit_impulse_nms']:.3f} N m s of "
        f"momentum per axis, which the momentum-management strategy in "
        "Section 6 must absorb and unload.",
        "",
        "## 4. Attitude determination",
        "",
        "### 4.1 Coarse estimate (TRIAD)",
        "",
        f"The TRIAD algorithm (sun sensor + magnetometer pair, "
        f"{det['triad_obs_consistency_deg']:g} deg inter-observation "
        "angle) recovers the acquisition attitude. On the truth-model "
        f"observation set the recovered rotation angle is "
        f"{det['triad_rotation_angle_deg']:.6f} deg against the "
        f"{det['slew_target_deg']:g} deg slew target, with orthogonality "
        f"error {det['triad_orthogonality_error']:.2e} (a perfect "
        "rotation matrix would give 0).",
        "",
        "### 4.2 Fine estimate (QUEST, Davenport q-method)",
        "",
        f"Three weighted vector observations (star tracker, sun sensor, "
        "magnetometer) feed the optimal attitude solution:",
        "",
        *[f"- {k}: {v}"
          for k, v in {
              "Optimal quaternion q (w, x, y, z)":
                  ", ".join(f"{c:g}" for c in det["q_optimal"]),
              "Eigenangle": f"{det['quest_eigenangle_deg']:.6f} deg "
                            f"(target {det['slew_target_deg']:g} deg)",
              "Largest eigenvalue of K":
                  f"{det['quest_lambda_max']:.6f}",
              "Wahba cost J(q)":
                  f"{det['quest_wahba_cost']:.3e}",
              "Residual RMS":
                  f"{det['quest_residual_rms']:.3e} rad "
                  f"({det['quest_residual_rms_arcsec']:.4f} arcsec)",
          }.items()],
        "",
        "The near-zero Wahba cost and residual RMS validate the "
        "determination chain on the noiseless truth model; in flight the "
        "star tracker measurement noise (2.0 arcsec 1-sigma per axis, "
        "project input) dominates, as captured in the Section 7 budget.",
        "",
        "## 5. Gyro noise characterization",
        "",
        f"Gyro rate samples (2 h at {gy['sample_period_s']:g} s, "
        f"sigma {gy['noise_sigma_rad_s']:.0e} rad/s, deterministic "
        "series) are characterized by the overlapping Allan deviation:",
        "",
        *[f"- tau = {t:g} s: AD = {a:.3e} rad/s"
          for t, a in zip(gy["taus_s"], gy["allan_deviations_rad_s"])],
        "",
        f"- Fitted log-log slope: {gy['fitted_slope']:.3f} "
        f"-> {gy['noise_class']}",
        f"- Angle random walk coefficient: "
        f"{gy['arw_deg_per_sqrt_h']:.4f} deg/sqrt(h)",
        f"- 1-sigma propagation over a {1:g} s star tracker update gap: "
        f"{gy['propagation_1s_arcsec_1sigma']:.2f} arcsec "
        "(random-walk integration, feeds Section 7).",
        "",
        "## 6. Attitude control (reaction wheels + magnetorquers)",
        "",
        "### 6.1 Reaction wheel control law",
        "",
        f"The quaternion-error PD law tau = -kp*theta_err - kd*omega_err "
        f"is sized for the z axis from the control bandwidth "
        f"{ct['bandwidth_rad_s']:g} rad/s and damping ratio "
        f"{ct['damping_ratio']:g}:",
        "",
        *[f"- {k}: {v}"
          for k, v in {
              "kp (z)": f"{ct['kp_z_nm_per_rad']:.4f} N m / rad",
              "kd (z)": f"{ct['kd_z_nm_s_per_rad']:.3f} N m s / rad",
              "Initial torque demand":
                  f"{ct['tau0_demand_nm']:.4f} N m "
                  f"(clipped at {ct['tau_max_nm']:g} N m: "
                  f"{'yes' if ct['tau0_demand_clipped'] else 'no'})",
              "Torque-limited phase": f"{ct['clipped_until_s']:.0f} s",
              "1% settle time": f"{ct['settle_time_1pct_s']:.0f} s",
          }.items()],
        "",
        f"The peak wheel momentum demand during the slew is "
        f"{ct['h_peak_nms']:.3f} N m s against a capacity of "
        f"{ct['h_max_nms']:g} N m s per wheel -> momentum margin "
        f"{ct['momentum_margin']:.2f}x, saturation "
        f"{'flagged' if ct['momentum_saturation'] else 'not flagged'}.",
        "",
        "### 6.2 Momentum management (desaturation)",
        "",
        f"Environmental torques accumulate "
        f"{ct['per_orbit_momentum_nms']:.3f} N m s per orbit per axis. "
        f"The wheels unload whenever momentum reaches the trigger level "
        f"{ct['h_unload_trigger_nms']:g} N m s (70% of capacity), "
        f"returning to a {ct['h_bias_nms']:g} N m s bias: one unload "
        f"every {ct['orbits_per_unload']:.1f} orbits.",
        "",
        f"Unload torque over a {ct['desat_horizon_s']:g} s horizon is "
        f"{ct['desat_torque_nm']:.2e} N m; with the local field of "
        f"{env['field_magnitude_t']:.2g} T the magnetorquer dipole "
        f"demand is {ct['desat_dipole_a_m2']:.1f} A m^2 (torque-rod "
        f"limit {ct['mag_m_max_a_m2']:g} A m^2, current "
        f"{ct['mag_coil_current_a']:.2f} A at "
        f"{ct['mag_turns']:g} turns x {ct['mag_coil_area_m2']:g} m^2). "
        f"Magnetorquer torque authority is "
        f"{ct['mag_torque_authority_nm']:.2e} N m -> desaturation margin "
        f"{ct['desat_margin']:.1f}x. Alignment warning: "
        f"{'yes' if ct['desat_alignment_warning'] else 'no'} "
        "(torque demand is perpendicular to the field in this example).",
        "",
        "### 6.3 Detumble (B-dot) and coil sizing",
        "",
        f"At separation the worst-case tip-off rate is "
        f"{math.degrees(ct['bdot']['tipoff_rad_s']):.1f} deg/s. The "
        "B-dot law m = gain * (omega x B) demands "
        f"{ct['bdot']['dipole_demand_a_m2']:.1f} A m^2, "
        f"{'clipped at' if ct['bdot']['clipped_at_m_max'] else 'within'} "
        f"the {ct['mag_m_max_a_m2']:g} A m^2 rod limit "
        f"({ct['bdot']['dipole_used_a_m2']:.1f} A m^2 used), producing "
        f"{ct['bdot']['achievable_torque_nm']:.1e} N m and a damping "
        f"time of {ct['bdot']['damping_time_s']:.0f} s "
        "(within one orbit).",
        "",
        "## 7. Pointing error budget",
        "",
        f"The 3-sigma requirement is {req:.1f} arcsec. Independent "
        "1-sigma contributors combine by root-sum-square:",
        "",
        *_md_table(["Contributor (1-sigma)", "arcsec", "Variance share"],
                   contrib_rows),
        "",
        f"- RSS 1-sigma error: {pb['rss_1sigma_arcsec']:.2f} arcsec",
        f"- RSS 3-sigma error: {pb['rss_3sigma_arcsec']:.2f} arcsec",
        f"- Requirement met: {'yes' if pb['requirement_met'] else 'no'} "
        f"(margin {pb['margin']:.2f}x)",
        f"- Dominant contributor: {pb['dominant']} "
        f"({pb['dominant_variance_share'] * 100.0:.0f}% of variance)",
        alloc_line,
        "",
        "## 8. Conclusions and open items",
        "",
        f"The ADCS as specified meets the {req:.1f} arcsec (3-sigma) "
        f"pointing requirement with a {pb['margin']:.1f}x margin. The "
        "determination chain, control law, momentum management and "
        "detumble sizing are mutually consistent and the magnetorquer "
        "authority supports the unload cadence.",
        "",
        "Open items before release: confirm the assumed disturbance "
        "torque with the environmental-disturbance-torque-budget "
        "analysis, confirm component specifications with the "
        "manufacturers, and verify the mass model.",
        "",
        "---",
        f"*Generated by Aero Agent Roles adcs-engineer core "
        f"({model['generated']}). DRAFT for human ADCS lead review. "
        "Not an approval document; carries no certification or "
        "flight-readiness authority.*",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evidence gates
# ---------------------------------------------------------------------------

GATE_CHECKS = {
    "requirement_identified": "3-sigma pointing requirement is a number",
    "determination_computed": "attitude estimate (TRIAD/QUEST) computed",
    "control_computed": "control law + momentum + desat numbers present",
    "budget_numbers_present": "RSS pointing error and margin are numbers",
    "sign_off_honest": "document is marked draft-for-review, not approval",
}


def check_report(model: dict) -> dict:
    """Run the evidence gates against the report content model."""
    det = model.get("determination", {})
    ct = model.get("control", {})
    pb = model.get("pointing_budget", {})
    results = {
        "requirement_identified":
            isinstance(model.get("requirement_arcsec_3sigma"), (int, float)),
        "determination_computed":
            isinstance(det.get("q_optimal"), list)
            and len(det.get("q_optimal", [])) == 4
            and isinstance(det.get("triad_rotation_angle_deg"), (int, float)),
        "control_computed":
            isinstance(ct.get("kp_z_nm_per_rad"), (int, float))
            and isinstance(ct.get("h_peak_nms"), (int, float))
            and isinstance(ct.get("desat_dipole_a_m2"), (int, float)),
        "budget_numbers_present":
            isinstance(pb.get("rss_3sigma_arcsec"), (int, float))
            and isinstance(pb.get("margin"), (int, float))
            and bool(pb.get("contributors_arcsec_1sigma")),
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_report_markdown(md_text: str, requirement_arcsec: float = 0.0) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    req = requirement_arcsec if requirement_arcsec > 0 else None
    if req is None:
        m = re.search(r"pointing requirement \(3-sigma\)[:*]*\s*([0-9.]+)",
                      low)
        if m:
            req = float(m.group(1))
    checks = {
        "has_title": "attitude determination and control subsystem report"
                     in low,
        "has_requirement": bool(req) and "pointing requirement" in low
                          and "arcsec" in low,
        "has_budget_numbers": "rss 3-sigma error" in low
                              and "arcsec" in low and "margin" in low,
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str, requirement_arcsec: float = 0.0) -> dict:
    """Public entry point used by gate tooling."""
    return check_report_markdown(md_text, requirement_arcsec)


# ---------------------------------------------------------------------------
# Worked example (tests + template generation)
# ---------------------------------------------------------------------------

def example_report_markdown() -> str:
    return render_report_markdown(build_report(example_item()))


if __name__ == "__main__":
    model = build_report(example_item())
    md = render_report_markdown(model)
    print("REQUIREMENT (3-sigma): %.1f arcsec"
          % model["requirement_arcsec_3sigma"])
    print("TRIAD ANGLE: %.6f deg" % model["determination"][
        "triad_rotation_angle_deg"])
    print("QUEST EIGENANGLE: %.6f deg" % model["determination"][
        "quest_eigenangle_deg"])
    print("ARW: %.4f deg/sqrt(h)  CLASS: %s"
          % (model["gyro"]["arw_deg_per_sqrt_h"],
             model["gyro"]["noise_class"]))
    print("RSS 3-SIGMA: %.2f arcsec  MARGIN: %.2fx"
          % (model["pointing_budget"]["rss_3sigma_arcsec"],
             model["pointing_budget"]["margin"]))
    print("GATES: %s" % (check_report(model),))
    print("RENDERED: %d chars" % len(md))
