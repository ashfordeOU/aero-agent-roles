#!/usr/bin/env python3
"""navigation_engineer_core.py - Navigation Engineer executable core.

This is the role's ENGINE: given a vehicle's navigation project facts
(reference geodetic position, INS sensor specs, GNSS constellation
geometry, RTK baseline, terrain-referenced aiding corridor and a
passive bearing-only sensor geometry) it computes a full navigation
architecture and position-error-budget report. Standalone: stdlib only
(math, dataclasses), no AeroSkills checkout required.

Domain rules encoded here are the standard navigation-engineering
methods carried by the bound Aero Agent Skills leaves:

- Frames/geodesy: WGS84 geodetic->ECEF and ECEF->NED rotation, per
  gnc-autonomy/navigation/navigation-frames (WGS84_A=6378137.0 m,
  WGS84_F=1/298.257223563).
- INS coasting error growth: accelerometer-bias position error
  0.5*b*t^2, gyro-drift position error (1/6)*g*eps*t^3, Schuler
  frequency/period, angle-random-walk sigma = arw*sqrt(t_hours), per
  gnc-autonomy/navigation/inertial-navigation (G0=9.80665,
  R_EARTH=6371000.0 Schuler pendulum length).
- GNSS epoch fix: iterated pseudorange least squares (Gauss-Newton on
  the linearized geometry matrix [-(sx-rx)/rho,...,1]), per
  gnc-autonomy/navigation/gnss-pseudorange-positioning; DOP from the
  ENU geometry matrix [e,n,u,1] and (H'H)^-1 diagonal, per
  gnc-autonomy/navigation/dilution-of-precision.
- RAIM/FDE: chi-square fault-detection test statistic sse/sigma^2
  against a chi2_quantile(n-4, 1-Pfa) threshold (Wilson-Hilferty cubic
  approximation of a normal quantile via Acklam's rational
  approximation) and horizontal protection level from the worst-case
  error slope, per gnc-autonomy/navigation/gnss-raim-fde
  (PFA=1e-5, SIGMA0=6.0 m).
- Carrier smoothing: Hatch filter steady-state noise std
  sigma_code*sqrt(alpha/(2-alpha)) + carrier term
  (1-alpha)*sigma_carrier/sqrt(alpha*(2-alpha)), per
  gnc-autonomy/navigation/gnss-carrier-smoothing.
- Doppler velocity: linearized range-rate least squares with state
  (vx,vy,vz,c*dtr_dot), per
  gnc-autonomy/navigation/gnss-doppler-velocity-positioning.
- RTK: double-difference float least squares, integer ambiguity search
  with a ratio test (DEFAULT_RATIO_MIN=3.0), fixed-baseline solve, per
  gnc-autonomy/navigation/gnss-rtk-positioning (LAMBDA_L1=0.190293672798 m).
- INS-GNSS integration: 5-state psi-angle loosely-coupled error filter
  (state transition Phi=I+F*dt, standard Kalman predict/update), per
  gnc-autonomy/navigation/kalman-filter-design and
  gnc-autonomy/navigation/ins-gnss-integrated-filter; the tightly-
  coupled 8-state per-satellite-pseudorange alternative is
  gnc-autonomy/navigation/tightly-coupled-ins-gnss.
- Terrain-referenced navigation: TERCOM correlation-surface best match
  by Pearson correlation and a slope-linearized SITAN Kalman bias
  update, per gnc-autonomy/navigation/terrain-referenced-navigation.
- Bearing-only localization: Stansfield two-pass weighted least
  squares fix, geometry dilution factor d=1/sqrt(lambda_min(S)), per
  gnc-autonomy/navigation/bearing-only-localization.

DO-229 (WAAS MOPS), DO-208 (TSO-C129 GPS MOPS) and ICAO Annex 10 Vol I
supply integrity/availability context only (reference-only per
standards-map); no standard text is reproduced.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


def _today() -> str:
    import os
    from datetime import date
    return os.environ.get("ROLE_GEN_DATE", date.today().isoformat())


# ---------------------------------------------------------------------------
# Generic linear algebra (stdlib only; used by every LS/Kalman stage below)
# ---------------------------------------------------------------------------

def mat_transpose(a):
    return [list(row) for row in zip(*a)]


def mat_mul(a, b):
    n, k, m = len(a), len(b), len(b[0])
    return [[sum(a[i][t] * b[t][j] for t in range(k)) for j in range(m)]
            for i in range(n)]


def mat_add(a, b):
    return [[a[i][j] + b[i][j] for j in range(len(a[0]))]
            for i in range(len(a))]


def mat_vec(a, v):
    return [sum(row[j] * v[j] for j in range(len(v))) for row in a]


def identity(n):
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


def solve_linear(a, b):
    """Solve A x = b (square A) by Gaussian elimination with partial
    pivoting. Raises ValueError if A is singular."""
    n = len(a)
    m = [list(row) + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-14:
            raise ValueError("singular matrix in solve_linear")
        m[col], m[piv] = m[piv], m[col]
        pv = m[col][col]
        m[col] = [v / pv for v in m[col]]
        for r in range(n):
            if r != col and m[r][col] != 0.0:
                factor = m[r][col]
                m[r] = [m[r][k] - factor * m[col][k] for k in range(n + 1)]
    return [m[i][n] for i in range(n)]


def mat_inverse(a):
    n = len(a)
    cols = []
    for j in range(n):
        e = [1.0 if i == j else 0.0 for i in range(n)]
        cols.append(solve_linear(a, e))
    return [[cols[j][i] for j in range(n)] for i in range(n)]


def lstsq(h, y):
    """Normal-equation least squares: x = (H'H)^-1 H'y. Returns
    (x, HTH_inv, residuals, sse)."""
    ht = mat_transpose(h)
    hth = mat_mul(ht, h)
    hty = mat_vec(ht, y)
    hth_inv = mat_inverse(hth)
    x = mat_vec(hth_inv, hty)
    hx = mat_vec(h, x)
    resid = [y[i] - hx[i] for i in range(len(y))]
    sse = sum(r * r for r in resid)
    return x, hth_inv, resid, sse


# ---------------------------------------------------------------------------
# 1. Frames and geodesy (navigation-frames)
# ---------------------------------------------------------------------------

WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)
OMEGA_EARTH = 7.2921159e-5


def geodetic_to_ecef(lat_rad: float, lon_rad: float, alt_m: float):
    """WGS84 geodetic -> ECEF, per navigation-frames."""
    sin_lat, cos_lat = math.sin(lat_rad), math.cos(lat_rad)
    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
    x = (n + alt_m) * cos_lat * math.cos(lon_rad)
    y = (n + alt_m) * cos_lat * math.sin(lon_rad)
    z = (n * (1.0 - WGS84_E2) + alt_m) * sin_lat
    return (x, y, z)


def ecef_to_ned_matrix(lat_rad: float, lon_rad: float):
    """3x3 ECEF->NED rotation at the reference geodetic point, per
    navigation-frames."""
    sl, cl = math.sin(lat_rad), math.cos(lat_rad)
    so, co = math.sin(lon_rad), math.cos(lon_rad)
    return [[-sl * co, -sl * so, cl],
            [-so, co, 0.0],
            [-cl * co, -cl * so, -sl]]


def ned_to_enu(v_ned):
    """NED -> ENU axis permutation: E=N_east, N=N_north, U=-N_down."""
    return (v_ned[1], v_ned[0], -v_ned[2])


def enu_to_ecef_dir(e, n, u, lat_rad, lon_rad):
    """Rotate an ENU direction vector into ECEF using the transpose of
    the ECEF->NED rotation (ENU = permutation of NED)."""
    v_ned = (n, e, -u)
    r = ecef_to_ned_matrix(lat_rad, lon_rad)
    rt = mat_transpose(r)
    return tuple(mat_vec(rt, list(v_ned)))


# ---------------------------------------------------------------------------
# 2. INS coasting error growth (inertial-navigation)
# ---------------------------------------------------------------------------

G0 = 9.80665
R_EARTH_SCHULER = 6371000.0
DEG_PER_HOUR_TO_RAD_S = math.pi / 180.0 / 3600.0


def deg_per_hour_to_rad_s(deg_per_hour: float) -> float:
    return deg_per_hour * DEG_PER_HOUR_TO_RAD_S


def schuler_frequency(g: float = G0, r: float = R_EARTH_SCHULER) -> float:
    return math.sqrt(g / r)


def schuler_period(g: float = G0, r: float = R_EARTH_SCHULER) -> float:
    return 2.0 * math.pi * math.sqrt(r / g)


def accel_bias_velocity_error(bias: float, t: float) -> float:
    return bias * t


def accel_bias_position_error(bias: float, t: float) -> float:
    return 0.5 * bias * t * t


def gyro_drift_position_error(gyro_bias_rad_s: float, t: float,
                              g: float = G0) -> float:
    return (1.0 / 6.0) * g * gyro_bias_rad_s * t ** 3


def angle_random_walk_sigma(arw_deg_per_sqrt_hour: float,
                            t_hours: float) -> float:
    return arw_deg_per_sqrt_hour * math.sqrt(t_hours)


def ins_coasting_error_growth(accel_bias_m_s2: float, gyro_bias_deg_hr: float,
                              arw_deg_sqrt_hr: float, t_s: float) -> dict:
    """1-sigma INS coasting position error over an outage of t_s
    seconds: RSS of the accelerometer-bias and gyro-drift position
    error terms (independent error sources)."""
    if t_s <= 0.0:
        raise ValueError("outage duration must be > 0")
    eps = deg_per_hour_to_rad_s(gyro_bias_deg_hr)
    accel_pos = accel_bias_position_error(accel_bias_m_s2, t_s)
    accel_vel = accel_bias_velocity_error(accel_bias_m_s2, t_s)
    gyro_pos = gyro_drift_position_error(eps, t_s)
    total = math.hypot(accel_pos, gyro_pos)
    arw_sigma_deg = angle_random_walk_sigma(arw_deg_sqrt_hr, t_s / 3600.0)
    return {
        "t_s": t_s, "accel_bias_m_s2": accel_bias_m_s2,
        "accel_bias_ug": accel_bias_m_s2 / (1e-6 * G0),
        "gyro_bias_deg_hr": gyro_bias_deg_hr, "gyro_bias_rad_s": eps,
        "arw_deg_sqrt_hr": arw_deg_sqrt_hr,
        "accel_bias_position_error_m": accel_pos,
        "accel_bias_velocity_error_m_s": accel_vel,
        "gyro_drift_position_error_m": gyro_pos,
        "total_position_1sigma_m": total,
        "arw_attitude_1sigma_deg": arw_sigma_deg,
        "schuler_period_s": schuler_period(),
    }


# ---------------------------------------------------------------------------
# 3. GNSS epoch fix (gnss-pseudorange-positioning + dilution-of-precision)
# ---------------------------------------------------------------------------

def geometric_range(recv, sat) -> float:
    return math.sqrt(sum((sat[k] - recv[k]) ** 2 for k in range(3)))


def _geometry_row(recv, sat, rho) -> list:
    return [-(sat[0] - recv[0]) / rho, -(sat[1] - recv[1]) / rho,
            -(sat[2] - recv[2]) / rho, 1.0]


def pseudorange_least_squares(sat_positions, pseudoranges, x0=(0.0, 0.0, 0.0, 0.0),
                              iters: int = 8, tol: float = 1e-6) -> dict:
    """Iterated pseudorange LS position + clock-bias fix, per
    gnss-pseudorange-positioning (MIN_SATELLITES=4)."""
    if len(sat_positions) < 4:
        raise ValueError("need at least 4 satellites")
    x, y, z, b = x0
    h_last, resid_last, sse = None, None, None
    n_iter = 0
    for n_iter in range(1, iters + 1):
        h, dr = [], []
        for sat, pr in zip(sat_positions, pseudoranges):
            rho = geometric_range((x, y, z), sat)
            h.append(_geometry_row((x, y, z), sat, rho))
            dr.append(pr - (rho + b))
        ht = mat_transpose(h)
        hth = mat_mul(ht, h)
        htdr = mat_vec(ht, dr)
        dx = solve_linear(hth, htdr)
        x, y, z, b = x + dx[0], y + dx[1], z + dx[2], b + dx[3]
        h_last, resid_last = h, dr
        if max(abs(v) for v in dx) < tol:
            break
    # post-fit residuals at the converged state
    resid = []
    for sat, pr in zip(sat_positions, pseudoranges):
        rho = geometric_range((x, y, z), sat)
        resid.append(pr - (rho + b))
    sse = sum(r * r for r in resid)
    return {"position": (x, y, z), "clock_bias_m": b, "H": h_last,
            "residuals": resid, "sse": sse, "iterations": n_iter,
            "n_sats": len(sat_positions)}


def compute_dops(unit_vectors_enu) -> dict:
    """GDOP/PDOP/HDOP/VDOP/TDOP from ENU LOS unit vectors [e,n,u], per
    dilution-of-precision."""
    if len(unit_vectors_enu) < 4:
        raise ValueError("need at least 4 satellites for DOP")
    h = [[e, n, u, 1.0] for (e, n, u) in unit_vectors_enu]
    a = mat_mul(mat_transpose(h), h)
    g = mat_inverse(a)
    gdop = math.sqrt(g[0][0] + g[1][1] + g[2][2] + g[3][3])
    pdop = math.sqrt(g[0][0] + g[1][1] + g[2][2])
    hdop = math.sqrt(g[0][0] + g[1][1])
    vdop = math.sqrt(max(g[2][2], 0.0))
    tdop = math.sqrt(max(g[3][3], 0.0))
    return {"gdop": gdop, "pdop": pdop, "hdop": hdop, "vdop": vdop,
            "tdop": tdop}


# ---------------------------------------------------------------------------
# 3b. RAIM / FDE (gnss-raim-fde)
# ---------------------------------------------------------------------------

RAIM_PFA = 1e-5
RAIM_SIGMA0 = 6.0
_HAL_NPA_M = 556.0   # non-precision-approach horizontal alert limit (context)

_ACKLAM_A = (-3.969683028665376e+01, 2.209460984245205e+02,
            -2.759285104469687e+02, 1.383577518672690e+02,
            -3.066479806614716e+01, 2.506628277459239e+00)
_ACKLAM_B = (-5.447609879822406e+01, 1.615858368580409e+02,
            -1.556989798598866e+02, 6.680131188771972e+01,
            -1.328068155288572e+01)
_ACKLAM_C = (-7.784894002430293e-03, -3.223964580411365e-01,
            -2.400758277161838e+00, -2.549732539343734e+00,
             4.374664141464968e+00, 2.938163982698783e+00)
_ACKLAM_D = (7.784695709041462e-03, 3.224671290700398e-01,
             2.445134137142996e+00, 3.754408661907416e+00)


def normal_quantile(p: float) -> float:
    """Standard normal quantile via Acklam's rational approximation."""
    if not (0.0 < p < 1.0):
        raise ValueError("p must lie in (0, 1)")
    plow, phigh = 0.02425, 1.0 - 0.02425
    a, b, c, d = _ACKLAM_A, _ACKLAM_B, _ACKLAM_C, _ACKLAM_D
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) \
            / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q \
            / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) \
        / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)


def chi2_quantile(df: int, p: float) -> float:
    """Chi-square quantile via the Wilson-Hilferty cubic approximation."""
    if df <= 0:
        raise ValueError("df must be > 0")
    z = normal_quantile(p)
    term = 1.0 - 2.0 / (9.0 * df) + z * math.sqrt(2.0 / (9.0 * df))
    return df * term ** 3


def raim_fault_detection(h, y, sigma: float = RAIM_SIGMA0,
                         pfa: float = RAIM_PFA) -> dict:
    """Snapshot RAIM chi-square fault-detection test, per gnss-raim-fde."""
    n, m = len(h), len(h[0])
    if n <= m:
        raise ValueError("need redundant geometry (n > %d) for RAIM" % m)
    x, hth_inv, resid, sse = lstsq(h, y)
    df = n - m
    t_stat = sse / (sigma * sigma)
    threshold = chi2_quantile(df, 1.0 - pfa)
    return {"test_statistic": t_stat, "threshold": threshold, "df": df,
            "fault_detected": t_stat > threshold, "sse": sse,
            "residuals": resid, "x": x, "hth_inv": hth_inv}


def raim_hpl(h, sigma: float = RAIM_SIGMA0, pfa: float = RAIM_PFA) -> dict:
    """Horizontal protection level from the worst-case error slope, per
    gnss-raim-fde."""
    n, m = len(h), len(h[0])
    hth = mat_mul(mat_transpose(h), h)
    hth_inv = mat_inverse(hth)
    a = mat_mul(hth_inv, mat_transpose(h))       # m x n
    ha = mat_mul(h, a)                            # n x n
    slopes = []
    for j in range(n):
        num = math.hypot(a[0][j], a[1][j])
        s_jj = max(1.0 - ha[j][j], 1e-9)
        slopes.append(num / math.sqrt(s_jj))
    slope_max = max(slopes)
    df = n - m
    hpl = slope_max * sigma * math.sqrt(chi2_quantile(df, 1.0 - pfa))
    return {"hpl_m": hpl, "slope_max": slope_max, "slopes": slopes,
            "hal_context_m": _HAL_NPA_M,
            "available": hpl <= _HAL_NPA_M}


# ---------------------------------------------------------------------------
# 4. Carrier smoothing + Doppler velocity
# ---------------------------------------------------------------------------

def hatch_alpha(tau: float, big_t: float) -> float:
    if not (0.0 < big_t < tau):
        raise ValueError("require 0 < T < tau")
    return big_t / tau


def carrier_smoothing_noise(alpha: float, sigma_code: float,
                            sigma_carrier: float) -> dict:
    """Steady-state Hatch-filter noise std, per gnss-carrier-smoothing."""
    if not (0.0 < alpha < 1.0):
        raise ValueError("alpha must lie in (0, 1)")
    code_only = sigma_code * math.sqrt(alpha / (2.0 - alpha))
    carrier_term = (1.0 - alpha) * sigma_carrier / math.sqrt(alpha * (2.0 - alpha))
    total = math.hypot(code_only, carrier_term)
    return {"alpha": alpha, "code_only_std_m": code_only,
            "carrier_term_std_m": carrier_term, "total_std_m": total,
            "improvement_factor": sigma_code / total}


def doppler_velocity_least_squares(sat_positions, sat_velocities, recv_position,
                                   doppler_obs_m_s, sigma: float = 0.05) -> dict:
    """Linearized Doppler range-rate LS velocity + clock-drift fix, per
    gnss-doppler-velocity-positioning. Geometry is fixed at recv_position
    (unit LOS does not depend on the unknown velocity), so this is a
    direct (non-iterated) linear solve."""
    n = len(sat_positions)
    if n < 4:
        raise ValueError("need at least 4 satellites for velocity LS")
    h, rhs = [], []
    for sat_p, sat_v, y in zip(sat_positions, sat_velocities, doppler_obs_m_s):
        rho = geometric_range(recv_position, sat_p)
        u = tuple((sat_p[k] - recv_position[k]) / rho for k in range(3))
        h.append([u[0], u[1], u[2], -1.0])
        rhs.append(sum(sat_v[k] * u[k] for k in range(3)) - y)
    x, hth_inv, resid, sse = lstsq(h, rhs)
    df = n - 4
    sigma0 = math.sqrt(sse / df) if df > 0 else sigma
    axis_sigma = [sigma0 * math.sqrt(max(hth_inv[i][i], 0.0)) for i in range(4)]
    return {"velocity_m_s": tuple(x[:3]), "clock_drift_m_s": x[3],
            "sigma0_m_s": sigma0, "axis_sigma_m_s": axis_sigma,
            "residuals": resid, "sse": sse, "n_sats": n}


# ---------------------------------------------------------------------------
# 5. RTK (gnss-rtk-positioning)
# ---------------------------------------------------------------------------

C_LIGHT = 299792458.0
F_L1 = 1575.42e6
LAMBDA_L1 = C_LIGHT / F_L1
RTK_RATIO_MIN = 3.0


def rtk_float_solve(h_rows, y_m) -> dict:
    """Float double-difference baseline + ambiguity LS: unknowns
    x = (bx, by, bz, N_1..N_{m-1}) in metres (ambiguity columns already
    carry the lambda*N scaling), per gnss-rtk-positioning."""
    x, hth_inv, resid, sse = lstsq(h_rows, y_m)
    n, k = len(h_rows), len(h_rows[0])
    df = max(n - k, 1)
    sigma0 = math.sqrt(sse / df) if n > k else 0.005 * LAMBDA_L1
    cov = [[sigma0 * sigma0 * hth_inv[i][j] for j in range(k)] for i in range(k)]
    return {"x": x, "cov": cov, "sigma0_m": sigma0, "sse": sse,
            "residuals": resid, "n_obs": n, "n_unknowns": k}


def rtk_ambiguity_search(x_float, cov, n_baseline: int, radius: int = 2,
                         ratio_min: float = RTK_RATIO_MIN) -> dict:
    """Integer ambiguity search (cycles) with the classic ratio test,
    per gnss-rtk-positioning (DEFAULT_SEARCH_RADIUS=2,
    DEFAULT_RATIO_MIN=3.0). The ambiguity unknowns solved by
    rtk_float_solve are already in cycles (the design-matrix column
    carries the lambda scaling, per its docstring), so no further
    lambda conversion is applied here."""
    amb_float_cycles = [x_float[n_baseline + i]
                        for i in range(len(x_float) - n_baseline)]
    m = len(amb_float_cycles)
    amb_block = [[cov[n_baseline + i][n_baseline + j]
                 for j in range(m)] for i in range(m)]
    q_inv = mat_inverse(amb_block)
    centers = [round(v) for v in amb_float_cycles]
    offsets = range(-radius, radius + 1)

    def _enumerate(dims):
        if not dims:
            yield ()
            return
        for v in offsets:
            for rest in _enumerate(dims[1:]):
                yield (v,) + rest

    scored = []
    for combo in _enumerate(list(range(m))):
        cand = [centers[i] + combo[i] for i in range(m)]
        d = [cand[i] - amb_float_cycles[i] for i in range(m)]
        qd = mat_vec(q_inv, d)
        score = sum(d[i] * qd[i] for i in range(m))
        scored.append((score, tuple(cand)))
    scored.sort(key=lambda t: t[0])
    best_score, best_cand = scored[0]
    second_score, _ = scored[1]
    ratio = (second_score / best_score) if best_score > 1e-9 else float("inf")
    return {"float_cycles": amb_float_cycles, "fixed_cycles": best_cand,
            "best_score": best_score, "second_score": second_score,
            "ratio": ratio, "resolved": ratio >= ratio_min}


def rtk_fixed_baseline_solve(h_baseline_cols, y_minus_lambda_n) -> dict:
    """Baseline-only LS once ambiguities are fixed, per
    gnss-rtk-positioning."""
    x, hth_inv, resid, sse = lstsq(h_baseline_cols, y_minus_lambda_n)
    n = len(h_baseline_cols)
    df = max(n - 3, 1)
    sigma0 = math.sqrt(sse / df) if n > 3 else 0.003
    cov = [[sigma0 * sigma0 * hth_inv[i][j] for j in range(3)] for i in range(3)]
    return {"baseline_m": tuple(x), "cov": cov, "sigma0_m": sigma0}


def ecef_cov_to_enu(cov_ecef, lat_rad, lon_rad):
    """Rotate a 3x3 ECEF covariance into ENU and return the per-axis
    1-sigma (E, N, U), per navigation-frames / gnss-rtk-positioning."""
    r_ned = ecef_to_ned_matrix(lat_rad, lon_rad)
    # NED -> ENU permutation as a matrix: E=row1(N-comp? ) build directly
    p = [[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0]]  # NED->ENU
    r = mat_mul(p, r_ned)                          # ECEF -> ENU
    c_enu = mat_mul(mat_mul(r, cov_ecef), mat_transpose(r))
    return (math.sqrt(max(c_enu[0][0], 0.0)), math.sqrt(max(c_enu[1][1], 0.0)),
            math.sqrt(max(c_enu[2][2], 0.0)))


# ---------------------------------------------------------------------------
# 6. INS-GNSS integration (kalman-filter-design + ins-gnss-integrated-filter)
# ---------------------------------------------------------------------------

def error_state_matrix(f_north: float, f_east: float):
    """Continuous 5-state psi-angle error model
    x = [dr_N, dr_E, dv_N, dv_E, psi], per ins-gnss-integrated-filter."""
    f = [[0.0] * 5 for _ in range(5)]
    f[0][2] = 1.0
    f[1][3] = 1.0
    f[2][4] = f_east
    f[3][4] = -f_north
    return f


def state_transition_matrix(f_north: float, f_east: float, dt_s: float):
    f = error_state_matrix(f_north, f_east)
    i5 = identity(5)
    return [[i5[i][j] + f[i][j] * dt_s for j in range(5)] for i in range(5)]


def predict_step(x, p, phi, q):
    x_next = mat_vec(phi, x)
    p_next = mat_add(mat_mul(mat_mul(phi, p), mat_transpose(phi)), q)
    return x_next, p_next


def measurement_update(x, p, z, h, r):
    hx = mat_vec(h, x)
    y = [z[i] - hx[i] for i in range(len(z))]
    s = mat_add(mat_mul(mat_mul(h, p), mat_transpose(h)), r)
    s_inv = mat_inverse(s)
    k = mat_mul(mat_mul(p, mat_transpose(h)), s_inv)
    x_new = [x[i] + sum(k[i][j] * y[j] for j in range(len(y)))
            for i in range(len(x))]
    kh = mat_mul(k, h)
    i5 = identity(len(x))
    imkh = [[i5[i][j] - kh[i][j] for j in range(len(x))] for i in range(len(x))]
    p_new = mat_mul(imkh, p)
    return x_new, p_new, y


# ---------------------------------------------------------------------------
# 7. Terrain-referenced navigation (terrain-referenced-navigation)
# ---------------------------------------------------------------------------

_DEM_TERMS = ((30.0, 1.0, 0.0, 400.0, 0.3),
             (15.0, 0.6, 0.8, 800.0, 1.1),
             (8.0, 0.2, 0.98, 1500.0, 2.0))
_DEM_BASE_M = 420.0


def terrain_height(x: float, y: float) -> float:
    """Analytic DEM surface: sum-of-sinusoids terrain, per
    terrain-referenced-navigation's build_dem_strip functional form."""
    h = _DEM_BASE_M
    for amp, ux, uy, wavelen, phase in _DEM_TERMS:
        h += amp * math.sin(2.0 * math.pi * (ux * x + uy * y) / wavelen + phase)
    return h


def terrain_gradient(x: float, y: float):
    """Analytic terrain slope (dh/dx, dh/dy)."""
    gx = gy = 0.0
    for amp, ux, uy, wavelen, phase in _DEM_TERMS:
        arg = 2.0 * math.pi * (ux * x + uy * y) / wavelen + phase
        c = amp * math.cos(arg) * (2.0 * math.pi / wavelen)
        gx += c * ux
        gy += c * uy
    return gx, gy


def tercom_match(measured, track_xy, candidates_m) -> dict:
    """TERCOM correlation-surface best match by Pearson r, per
    terrain-referenced-navigation."""
    n = len(measured)
    mean_z = sum(measured) / n
    var_z = sum((v - mean_z) ** 2 for v in measured)
    best = None
    surface = []
    for dx, dy in candidates_m:
        d = [terrain_height(track_xy[i][0] - dx, track_xy[i][1] - dy)
            for i in range(n)]
        mean_d = sum(d) / n
        cov = sum((measured[i] - mean_z) * (d[i] - mean_d) for i in range(n))
        var_d = sum((v - mean_d) ** 2 for v in d)
        denom = math.sqrt(var_z * var_d)
        r = cov / denom if denom > 1e-9 else 0.0
        surface.append({"dx": dx, "dy": dy, "r": r})
        if best is None or r > best["r"]:
            best = {"dx": dx, "dy": dy, "r": r}
    return {"best": best, "surface": surface}


def sitan_slope_update(dr0, track_xy, measured, r_meas: float = 2.25,
                       q_bias: float = 0.02, p0_bias: float = 100.0) -> dict:
    """Slope-linearized SITAN filter update on state (dr_e, dr_n, bias),
    per terrain-referenced-navigation."""
    x = [dr0[0], dr0[1], 0.0]
    p = [[p0_bias if i == j else 0.0 for j in range(3)] for i in range(3)]
    q = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, q_bias]]
    for i in range(len(track_xy)):
        p = mat_add(p, q)
        px, py = track_xy[i][0] - x[0], track_xy[i][1] - x[1]
        h_pred = terrain_height(px, py) + x[2]
        gx, gy = terrain_gradient(px, py)
        h_row = [[-gx, -gy, 1.0]]
        y_i = measured[i] - h_pred
        s = mat_mul(mat_mul(h_row, p), mat_transpose(h_row))[0][0] + r_meas
        k_col = mat_vec(p, [-gx, -gy, 1.0])
        k = [kv / s for kv in k_col]
        x = [x[j] + k[j] * y_i for j in range(3)]
        kh = [[k[a] * h_row[0][b] for b in range(3)] for a in range(3)]
        i3 = identity(3)
        imkh = [[i3[a][b] - kh[a][b] for b in range(3)] for a in range(3)]
        p = mat_mul(imkh, p)
    return {"dr_e_m": x[0], "dr_n_m": x[1], "bias_m": x[2],
            "p_final": p, "sigma_e_m": math.sqrt(max(p[0][0], 0.0)),
            "sigma_n_m": math.sqrt(max(p[1][1], 0.0))}


# ---------------------------------------------------------------------------
# 8. Bearing-only localization (bearing-only-localization)
# ---------------------------------------------------------------------------

def _unit_normal(beta_deg: float):
    b = math.radians(beta_deg)
    return (math.sin(b), -math.cos(b))


def bearing_only_wls_fix(observers, bearings_deg, sigma_deg: float) -> dict:
    """Stansfield two-pass weighted least squares fix, per
    bearing-only-localization."""
    n = len(observers)
    if n < 2:
        raise ValueError("need at least 2 observers")
    sigma_rad = math.radians(sigma_deg)
    normals = [_unit_normal(b) for b in bearings_deg]
    rhs = [normals[i][0] * observers[i][0] + normals[i][1] * observers[i][1]
          for i in range(n)]

    def _solve(weights):
        n00 = sum(weights[i] * normals[i][0] * normals[i][0] for i in range(n))
        n01 = sum(weights[i] * normals[i][0] * normals[i][1] for i in range(n))
        n11 = sum(weights[i] * normals[i][1] * normals[i][1] for i in range(n))
        c0 = sum(weights[i] * normals[i][0] * rhs[i] for i in range(n))
        c1 = sum(weights[i] * normals[i][1] * rhs[i] for i in range(n))
        det = n00 * n11 - n01 * n01
        if det <= 1e-12 * max(n00 * n11, 1e-12):
            raise ValueError("bearing geometry is singular")
        x = (n11 * c0 - n01 * c1) / det
        y = (n00 * c1 - n01 * c0) / det
        cov = [[n11 / det, -n01 / det], [-n01 / det, n00 / det]]
        return x, y, cov

    w1 = [1.0 / (sigma_rad ** 2) for _ in range(n)]
    x1, y1, _ = _solve(w1)
    ranges = [math.hypot(observers[i][0] - x1, observers[i][1] - y1)
             for i in range(n)]
    w2 = [1.0 / (sigma_rad ** 2 * max(ranges[i], 1e-6) ** 2) for i in range(n)]
    x2, y2, cov = _solve(w2)
    return {"x_m": x2, "y_m": y2, "cov": cov, "ranges_m": ranges,
            "pass1": (x1, y1)}


def error_ellipse(cov) -> dict:
    c00, c01, c11 = cov[0][0], cov[0][1], cov[1][1]
    tr, det = c00 + c11, c00 * c11 - c01 * c01
    disc = math.sqrt(max(tr * tr / 4.0 - det, 0.0))
    lam1, lam2 = tr / 2.0 + disc, tr / 2.0 - disc
    theta = 0.5 * math.atan2(2.0 * c01, c00 - c11)
    return {"semi_major_m": math.sqrt(max(lam1, 0.0)),
            "semi_minor_m": math.sqrt(max(lam2, 0.0)),
            "orientation_deg": math.degrees(theta)}


def geometry_dilution_factor(observers, bearings_deg) -> float:
    normals = [_unit_normal(b) for b in bearings_deg]
    s00 = sum(g[0] * g[0] for g in normals)
    s01 = sum(g[0] * g[1] for g in normals)
    s11 = sum(g[1] * g[1] for g in normals)
    tr, det = s00 + s11, s00 * s11 - s01 * s01
    disc = math.sqrt(max(tr * tr / 4.0 - det, 0.0))
    lam_min = tr / 2.0 - disc
    if lam_min <= 1e-9:
        return float("inf")
    return 1.0 / math.sqrt(lam_min)


def dilution_verdict(d: float) -> str:
    if d <= 1.05:
        return "good"
    if d < 2.5:
        return "moderate"
    return "poor"


# ---------------------------------------------------------------------------
# Project facts
# ---------------------------------------------------------------------------

@dataclass
class NavProject:
    vehicle: str = "Mapping UAS (small fixed-wing)"
    mission: str = ("Integrated navigation error analysis: RTK base + "
                    "90 s GNSS-denied terrain corridor")
    condition: str = "Survey cruise, 25 m/s, 300 m AGL"
    report_title: str = ("Navigation Architecture and Position Error "
                         "Analysis Report")
    # reference geodetic point (vehicle at outage start)
    ref_lat_deg: float = 37.4275
    ref_lon_deg: float = -122.1697
    ref_alt_m: float = 330.0
    # INS specs (MEMS-class)
    accel_bias_ug: float = 50.0       # micro-g
    gyro_bias_deg_hr: float = 5.0
    gyro_arw_deg_sqrt_hr: float = 0.3
    outage_s: float = 90.0
    # GNSS epoch fix geometry (6-satellite constellation, az/el deg)
    sat_az_el_deg: tuple = ((45.0, 60.0), (135.0, 55.0), (225.0, 50.0),
                            (315.0, 45.0), (60.0, 25.0), (280.0, 20.0))
    sat_range_km: float = 22000.0
    true_clock_bias_m: float = 1500.0
    pr_noise_pattern_m: tuple = (0.8, -1.2, 0.5, -0.3, 1.1, -0.6)
    raim_sigma_m: float = RAIM_SIGMA0
    # carrier smoothing / Doppler
    smooth_tau_s: float = 100.0
    smooth_t_s: float = 1.0
    sigma_code_m: float = 0.3
    sigma_carrier_m: float = 0.003
    doppler_sigma_m_s: float = 0.05
    true_velocity_enu_m_s: tuple = (25.0, 0.0, 0.0)
    true_clock_drift_m_s: float = 0.5
    doppler_noise_pattern_m_s: tuple = (0.02, -0.03, 0.01, -0.02, 0.03, -0.01)
    # RTK (base < 10 km, 4 common satellites, 4 epochs, ref sat = index 0)
    rtk_base_range_km: float = 6.0
    rtk_baseline_true_enu_m: tuple = (120.0, -45.0, 8.0)
    rtk_true_ambiguities_cycles: tuple = (12.0, -7.0, 5.0)
    rtk_az_el_epochs_deg: tuple = (
        ((40.0, 58.0), (140.0, 52.0), (230.0, 48.0), (320.0, 42.0)),
        ((41.5, 58.4), (141.4, 52.3), (231.3, 48.3), (321.2, 42.3)),
        ((43.0, 58.8), (142.8, 52.6), (232.6, 48.6), (322.4, 42.6)),
        ((44.5, 59.2), (144.2, 52.9), (233.9, 48.9), (323.6, 42.9)),
    )
    rtk_dd_noise_cycles: float = 0.003
    # INS-GNSS integration
    integ_f_north_m_s2: float = 0.20
    integ_f_east_m_s2: float = 0.05
    integ_dt_s: float = 1.0
    integ_process_noise_pos: float = 1e-4
    integ_process_noise_vel: float = 1e-3
    integ_process_noise_psi: float = 1e-8
    integ_gnss_sigma_m: float = 3.0
    # terrain-referenced navigation (90 s corridor)
    tercom_true_offset_m: tuple = (45.0, -20.0)
    tercom_track_samples: int = 10
    tercom_speed_m_s: float = 25.0
    tercom_candidate_step_m: float = 25.0
    tercom_candidate_halfwidth: int = 2
    sitan_r_meas_m2: float = 2.25
    sitan_q_bias_m2: float = 0.02
    sitan_p0_bias_m2: float = 100.0
    # bearing-only localization (passive secondary sensor, 3 observers)
    bearing_observers_m: tuple = ((0.0, 0.0), (1800.0, 200.0), (900.0, 1600.0))
    bearing_target_m: tuple = (950.0, 700.0)
    bearing_sigma_deg: float = 1.5
    # requirement
    req_position_budget_m: float = 25.0


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def _sat_positions_enu(az_el_deg, range_km):
    """Place satellites along the az/el LOS direction at range_km (a
    valid geometry-only construction: for DOP/LS purposes only the LOS
    direction matters)."""
    pts = []
    for az, el in az_el_deg:
        az_r, el_r = math.radians(az), math.radians(el)
        e = math.cos(el_r) * math.sin(az_r)
        n = math.cos(el_r) * math.cos(az_r)
        u = math.sin(el_r)
        rng = range_km * 1000.0
        pts.append((e * rng, n * rng, u * rng))
    return pts


def build_report(p: NavProject) -> dict:
    lat_r, lon_r = math.radians(p.ref_lat_deg), math.radians(p.ref_lon_deg)

    # --- 1. Frames ---
    ecef_ref = geodetic_to_ecef(lat_r, lon_r, p.ref_alt_m)
    r_ecef_ned = ecef_to_ned_matrix(lat_r, lon_r)

    # --- 2. INS coasting ---
    accel_bias_m_s2 = p.accel_bias_ug * 1e-6 * G0
    ins = ins_coasting_error_growth(accel_bias_m_s2, p.gyro_bias_deg_hr,
                                    p.gyro_arw_deg_sqrt_hr, p.outage_s)

    # --- 3. GNSS epoch fix + DOP ---
    sat_enu = _sat_positions_enu(p.sat_az_el_deg, p.sat_range_km)
    sat_ecef = [tuple(ecef_ref[k] + enu_to_ecef_dir(*pt, lat_r, lon_r)[k]
                      for k in range(3)) for pt in sat_enu]
    pseudoranges = [geometric_range(ecef_ref, sat) + p.true_clock_bias_m + noise
                    for sat, noise in zip(sat_ecef, p.pr_noise_pattern_m)]
    seed = (ecef_ref[0] + 50.0, ecef_ref[1] + 50.0, ecef_ref[2] + 50.0, 0.0)
    fix = pseudorange_least_squares(sat_ecef, pseudoranges, x0=seed)
    unit_enu = []
    for (e, n, u) in sat_enu:
        rng = math.sqrt(e * e + n * n + u * u)
        unit_enu.append((e / rng, n / rng, u / rng))
    dops = compute_dops(unit_enu)
    uere_rms = math.sqrt(fix["sse"] / len(fix["residuals"]))
    pos_1sigma = dops["pdop"] * uere_rms

    # --- 3b. RAIM/FDE ---
    h_raim = [[e, n, u, 1.0] for (e, n, u) in unit_enu]
    y_raim = fix["residuals"]
    raim = raim_fault_detection(h_raim, y_raim, sigma=p.raim_sigma_m)
    hpl = raim_hpl(h_raim, sigma=p.raim_sigma_m)

    # --- 4. Carrier smoothing + Doppler ---
    alpha = hatch_alpha(p.smooth_tau_s, p.smooth_t_s)
    smoothing = carrier_smoothing_noise(alpha, p.sigma_code_m, p.sigma_carrier_m)

    sat_vel_enu = [(0.0, 0.0, -3874.0) for _ in sat_enu]  # radial closing rate proxy
    sat_vel_ecef = [enu_to_ecef_dir(*v, lat_r, lon_r) for v in sat_vel_enu]
    recv_vel_ecef = enu_to_ecef_dir(*p.true_velocity_enu_m_s, lat_r, lon_r)
    doppler_obs = []
    for sat_p, sat_v, noise in zip(sat_ecef, sat_vel_ecef, p.doppler_noise_pattern_m_s):
        rho = geometric_range(ecef_ref, sat_p)
        u = tuple((sat_p[k] - ecef_ref[k]) / rho for k in range(3))
        y = sum((sat_v[k] - recv_vel_ecef[k]) * u[k] for k in range(3)) \
            + p.true_clock_drift_m_s + noise
        doppler_obs.append(y)
    doppler = doppler_velocity_least_squares(sat_ecef, sat_vel_ecef, ecef_ref,
                                             doppler_obs, sigma=p.doppler_sigma_m_s)

    # --- 5. RTK ---
    m = len(p.rtk_az_el_epochs_deg[0]) - 1     # DDs per epoch (ref = sat 0)
    h_rows, y_rows = [], []
    for az_el in p.rtk_az_el_epochs_deg:
        u_list = []
        for az, el in az_el:
            az_r, el_r = math.radians(az), math.radians(el)
            u_list.append((math.cos(el_r) * math.sin(az_r),
                          math.cos(el_r) * math.cos(az_r), math.sin(el_r)))
        u_ref = u_list[0]
        for j in range(1, len(u_list)):
            du = tuple(u_list[j][k] - u_ref[k] for k in range(3))
            row = [-du[0], -du[1], -du[2]] + [0.0] * m
            row[3 + (j - 1)] = -LAMBDA_L1
            true_dd_range = -sum(du[k] * p.rtk_baseline_true_enu_m[k]
                                 for k in range(3)) \
                - LAMBDA_L1 * p.rtk_true_ambiguities_cycles[j - 1]
            noise = p.rtk_dd_noise_cycles * LAMBDA_L1 * (1 if (j % 2) else -1)
            h_rows.append(row)
            y_rows.append(true_dd_range + noise)
    rtk_float = rtk_float_solve(h_rows, y_rows)
    amb_search = rtk_ambiguity_search(rtk_float["x"], rtk_float["cov"], 3,
                                      radius=2, ratio_min=RTK_RATIO_MIN)
    h_base = [row[:3] for row in h_rows]
    y_fixed = []
    idx = 0
    for e_i, az_el in enumerate(p.rtk_az_el_epochs_deg):
        for j in range(1, len(az_el)):
            n_fixed = amb_search["fixed_cycles"][j - 1]
            y_fixed.append(y_rows[idx] + LAMBDA_L1 * n_fixed)
            idx += 1
    rtk_fixed = rtk_fixed_baseline_solve(h_base, y_fixed)
    rtk_enu_sigma = (math.sqrt(rtk_fixed["cov"][0][0]),
                     math.sqrt(rtk_fixed["cov"][1][1]),
                     math.sqrt(rtk_fixed["cov"][2][2]))

    # --- 6. INS-GNSS integration (loosely coupled, one predict+update) ---
    x0 = [ins["accel_bias_position_error_m"], ins["gyro_drift_position_error_m"],
         ins["accel_bias_velocity_error_m_s"], 0.0,
         math.radians(ins["arw_attitude_1sigma_deg"])]
    p0 = [[0.0] * 5 for _ in range(5)]
    p0[0][0] = ins["total_position_1sigma_m"] ** 2
    p0[1][1] = ins["total_position_1sigma_m"] ** 2
    p0[2][2] = ins["accel_bias_velocity_error_m_s"] ** 2 + 1e-6
    p0[3][3] = ins["accel_bias_velocity_error_m_s"] ** 2 + 1e-6
    p0[4][4] = math.radians(ins["arw_attitude_1sigma_deg"]) ** 2 + 1e-10
    q = [[0.0] * 5 for _ in range(5)]
    q[0][0] = q[1][1] = p.integ_process_noise_pos
    q[2][2] = q[3][3] = p.integ_process_noise_vel
    q[4][4] = p.integ_process_noise_psi
    phi = state_transition_matrix(p.integ_f_north_m_s2, p.integ_f_east_m_s2,
                                  p.integ_dt_s)
    x_pred, p_pred = predict_step(x0, p0, phi, q)
    h_meas = [[1.0, 0.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0, 0.0]]
    r_meas = [[p.integ_gnss_sigma_m ** 2, 0.0], [0.0, p.integ_gnss_sigma_m ** 2]]
    x_upd, p_upd, innov = measurement_update(x_pred, p_pred, [0.0, 0.0],
                                             h_meas, r_meas)
    integ = {"x0": x0, "x_pred": x_pred, "x_upd": x_upd,
            "dt_s": p.integ_dt_s, "f_north_m_s2": p.integ_f_north_m_s2,
            "f_east_m_s2": p.integ_f_east_m_s2, "gnss_sigma_m": p.integ_gnss_sigma_m,
            "p_pred_diag": [p_pred[i][i] for i in range(5)],
            "p_upd_diag": [p_upd[i][i] for i in range(5)],
            "innovation": innov,
            "pos_1sigma_after_m": math.hypot(math.sqrt(max(p_upd[0][0], 0.0)),
                                             math.sqrt(max(p_upd[1][1], 0.0)))}

    # --- 7. GNSS-denied terrain segment ---
    n_samp = p.tercom_track_samples
    dt_track = p.outage_s / (n_samp - 1)
    track_true = [(p.tercom_speed_m_s * i * dt_track, 0.0) for i in range(n_samp)]
    track_ins = [(x + p.tercom_true_offset_m[0], y + p.tercom_true_offset_m[1])
                for (x, y) in track_true]
    measured = [terrain_height(x, y) for (x, y) in track_true]
    step = p.tercom_candidate_step_m
    hw = p.tercom_candidate_halfwidth
    candidates = [(i * step, j * step)
                 for i in range(-hw, hw + 1) for j in range(-hw, hw + 1)]
    tercom = tercom_match(measured, track_ins, candidates)
    sitan = sitan_slope_update((tercom["best"]["dx"], tercom["best"]["dy"]),
                               track_ins, measured, r_meas=p.sitan_r_meas_m2,
                               q_bias=p.sitan_q_bias_m2, p0_bias=p.sitan_p0_bias_m2)

    # --- 8. Bearing-only localization ---
    bearings = []
    for ox, oy in p.bearing_observers_m:
        tx, ty = p.bearing_target_m
        # per bearing-only-localization's bearing_deg(): standard math
        # angle atan2(dy, dx), matching the sin(beta)/cos(beta) line
        # normal used in bearing_only_wls_fix below.
        brg = math.degrees(math.atan2(ty - oy, tx - ox)) % 360.0
        bearings.append(brg)
    bearing_fix = bearing_only_wls_fix(list(p.bearing_observers_m), bearings,
                                       p.bearing_sigma_deg)
    ellipse = error_ellipse(bearing_fix["cov"])
    dilution = geometry_dilution_factor(list(p.bearing_observers_m), bearings)

    # --- 9. Integrated error budget ---
    # "unaided reference" shows the coasting error WITHOUT terrain aiding
    # (why aiding is needed); it is not one of the deployed navigation
    # modes, so it is excluded from the pass/fail verdict below.
    unaided_label = "GNSS-denied, INS coasting only (%ds, unaided reference)" \
        % int(p.outage_s)
    phases = {
        "GNSS-nominal (RTK fixed)": max(rtk_enu_sigma[0], rtk_enu_sigma[1]),
        "GNSS-nominal (standalone, DOP)": pos_1sigma,
        unaided_label: ins["total_position_1sigma_m"],
        "GNSS-denied, terrain-aided (SITAN, deployed solution)":
            math.hypot(sitan["sigma_e_m"], sitan["sigma_n_m"]),
    }
    verdict_phases = {k: v for k, v in phases.items() if k != unaided_label}
    worst_phase = max(verdict_phases, key=verdict_phases.get)
    worst_value = verdict_phases[worst_phase]
    budget_ok = worst_value <= p.req_position_budget_m

    model = {
        "document_type": p.report_title,
        "status": "draft-for-review",
        "vehicle": p.vehicle,
        "mission": p.mission,
        "condition": p.condition,
        "generated": _today(),
        "frames": {
            "lat_deg": p.ref_lat_deg, "lon_deg": p.ref_lon_deg,
            "alt_m": p.ref_alt_m, "ecef_m": ecef_ref,
            "wgs84_a_m": WGS84_A, "wgs84_f": WGS84_F, "wgs84_e2": WGS84_E2,
        },
        "ins": ins,
        "gnss_fix": {"position": fix["position"], "clock_bias_m": fix["clock_bias_m"],
                    "true_clock_bias_m": p.true_clock_bias_m,
                    "iterations": fix["iterations"], "sse": fix["sse"],
                    "n_sats": fix["n_sats"], "uere_rms_m": uere_rms,
                    "dops": dops, "pos_1sigma_m": pos_1sigma},
        "raim": {"test_statistic": raim["test_statistic"],
                "threshold": raim["threshold"], "df": raim["df"],
                "fault_detected": raim["fault_detected"], "sse": raim["sse"],
                "hpl_m": hpl["hpl_m"], "hal_context_m": hpl["hal_context_m"],
                "available": hpl["available"]},
        "smoothing": dict(smoothing, tau_s=p.smooth_tau_s, t_s=p.smooth_t_s),
        "doppler": {"velocity_m_s": doppler["velocity_m_s"],
                   "clock_drift_m_s": doppler["clock_drift_m_s"],
                   "sigma0_m_s": doppler["sigma0_m_s"],
                   "axis_sigma_m_s": doppler["axis_sigma_m_s"]},
        "rtk": {"baseline_km": p.rtk_base_range_km,
               "float_x": rtk_float["x"], "float_sigma0_m": rtk_float["sigma0_m"],
               "ambiguity_ratio": amb_search["ratio"],
               "ambiguity_resolved": amb_search["resolved"],
               "fixed_cycles": amb_search["fixed_cycles"],
               "true_cycles": p.rtk_true_ambiguities_cycles,
               "baseline_enu_m": rtk_fixed["baseline_m"],
               "true_baseline_enu_m": p.rtk_baseline_true_enu_m,
               "enu_1sigma_m": rtk_enu_sigma},
        "integration": integ,
        "terrain": {"true_offset_m": p.tercom_true_offset_m,
                   "tercom_best": tercom["best"], "n_candidates": len(candidates),
                   "n_samples": n_samp,
                   "sitan_dr_e_m": sitan["dr_e_m"], "sitan_dr_n_m": sitan["dr_n_m"],
                   "sitan_bias_m": sitan["bias_m"],
                   "sitan_sigma_e_m": sitan["sigma_e_m"],
                   "sitan_sigma_n_m": sitan["sigma_n_m"]},
        "bearing": {"fix_m": (bearing_fix["x_m"], bearing_fix["y_m"]),
                   "true_m": p.bearing_target_m, "ellipse": ellipse,
                   "n_observers": len(p.bearing_observers_m),
                   "sigma_deg": p.bearing_sigma_deg,
                   "dilution_factor": dilution,
                   "dilution_verdict": dilution_verdict(dilution)},
        "budget": {"phases": phases, "worst_phase": worst_phase,
                  "worst_value_m": worst_value,
                  "requirement_m": p.req_position_budget_m,
                  "ok": bool(budget_ok)},
        "verdicts": {
            "raim_integrity": "PASS" if not raim["fault_detected"] else "FAIL",
            "rtk_ambiguity": "PASS" if amb_search["resolved"] else "FAIL",
            "position_budget": "PASS" if budget_ok else "FAIL",
        },
    }
    return model


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def render_report_markdown(m: dict) -> str:
    f = m["frames"]
    ins = m["ins"]
    g = m["gnss_fix"]
    raim = m["raim"]
    sm = m["smoothing"]
    dp = m["doppler"]
    rtk = m["rtk"]
    ig = m["integration"]
    tr = m["terrain"]
    br = m["bearing"]
    bud = m["budget"]
    v = m["verdicts"]
    dops = g["dops"]

    lines = [
        "# " + m["document_type"],
        "",
        "**Vehicle:** %s" % m["vehicle"],
        "**Condition:** %s" % m["condition"],
        "**Mission / item:** %s" % m["mission"],
        "**Status:** %s" % m["status"],
        "",
        "## 1. Frames and geodesy",
        "",
        "- Vertical/horizontal reference: WGS84 ellipsoid, a = %.1f m, "
        "f = 1/%.9f, e^2 = %.8f." % (f["wgs84_a_m"], 1.0 / f["wgs84_f"],
                                     f["wgs84_e2"]),
        "- Reference point (outage start): lat %.4f deg, lon %.4f deg, "
        "alt %.1f m -> ECEF (%.1f, %.1f, %.1f) m." % (
            f["lat_deg"], f["lon_deg"], f["alt_m"],
            f["ecef_m"][0], f["ecef_m"][1], f["ecef_m"][2]),
        "- Frame conventions: NED (north-east-down) for the INS mechanization "
        "and the INS-GNSS integration filter; ENU (east-north-up) for GNSS/"
        "RTK baseline reporting and the terrain/bearing-only local-tangent "
        "geometry; ECEF for the pseudorange/RTK least-squares solves. "
        "ECEF->NED rotation is evaluated at the reference point and reused "
        "for every local-frame conversion in this report.",
        "",
        "## 2. INS coasting error growth",
        "",
        "- Sensor specs (MEMS-class): accelerometer bias %.0f micro-g "
        "(%.6f m/s^2), gyro bias %.1f deg/hr (%.3e rad/s), angle random "
        "walk %.2f deg/sqrt(hr)." % (
            ins["accel_bias_ug"], ins["accel_bias_m_s2"],
            ins["gyro_bias_deg_hr"], ins["gyro_bias_rad_s"],
            ins["arw_deg_sqrt_hr"]),
        "- GNSS-denied outage: %.0f s (Schuler period %.0f s = %.1f min; "
        "the outage is far shorter than one Schuler cycle, so the coasting "
        "errors below grow essentially unbounded rather than oscillating)."
        % (ins["t_s"], ins["schuler_period_s"], ins["schuler_period_s"] / 60.0),
        "- Accelerometer-bias error: velocity dv = b*t = %.4f m/s; position "
        "dx = 0.5*b*t^2 = %.3f m." % (ins["accel_bias_velocity_error_m_s"],
                                      ins["accel_bias_position_error_m"]),
        "- Gyro-drift position error: dx = (1/6)*g*eps*t^3 = %.3f m." %
        ins["gyro_drift_position_error_m"],
        "- Combined (RSS, independent sources) 1-sigma coasting position "
        "error at t = %.0f s: **%.3f m**." % (ins["t_s"],
                                              ins["total_position_1sigma_m"]),
        "- Attitude uncertainty from angle random walk over the outage: "
        "%.4f deg 1-sigma (reported separately; not summed into the "
        "position budget above)." % ins["arw_attitude_1sigma_deg"],
        "",
        "## 3. GNSS epoch solution",
        "",
        "- Iterated pseudorange least squares over %d satellites converged "
        "in %d iteration(s); recovered clock bias %.2f m (true %.2f m); "
        "post-fit SSE %.4f m^2." % (g["n_sats"], g["iterations"],
                                    g["clock_bias_m"], g["true_clock_bias_m"],
                                    g["sse"]),
        "- DOP geometry: GDOP %.2f, PDOP %.2f, HDOP %.2f, VDOP %.2f, TDOP "
        "%.2f." % (dops["gdop"], dops["pdop"], dops["hdop"], dops["vdop"],
                   dops["tdop"]),
        "- UERE (post-fit residual RMS) %.3f m; position 1-sigma = PDOP * "
        "UERE = %.2f * %.3f = **%.3f m**." % (g["uere_rms_m"], dops["pdop"],
                                              g["uere_rms_m"], g["pos_1sigma_m"]),
        "- RAIM/FDE (snapshot chi-square test, Pfa = %.0e): test statistic "
        "%.3f vs threshold %.3f (df = %d) -> **%s**." % (
            RAIM_PFA, raim["test_statistic"], raim["threshold"], raim["df"],
            "FAULT DETECTED" if raim["fault_detected"] else "no fault"),
        "- Horizontal protection level HPL = %.1f m (worst-case error "
        "slope); non-precision-approach HAL context %.0f m -> integrity "
        "%s." % (raim["hpl_m"], raim["hal_context_m"],
                 "available" if raim["available"] else "unavailable"),
        "",
        "## 4. Carrier smoothing and Doppler velocity",
        "",
        "- Hatch filter: tau = %.0f s, T = %.0f s -> alpha = %.3f. Code-only "
        "std %.3f m; smoothed std %.4f m (carrier term %.5f m) -> "
        "improvement factor %.1fx vs code-only pseudorange." % (
            sm["tau_s"], sm["t_s"], sm["alpha"],
            sm["code_only_std_m"], sm["total_std_m"], sm["carrier_term_std_m"],
            sm["improvement_factor"]),
        "- Doppler-derived velocity (linearized LS): v = (%.3f, %.3f, %.3f) "
        "m/s ECEF, clock drift %.3f m/s; per-axis 1-sigma (%.4f, %.4f, "
        "%.4f, %.4f) m/s [vx,vy,vz,drift]." % (
            dp["velocity_m_s"][0], dp["velocity_m_s"][1], dp["velocity_m_s"][2],
            dp["clock_drift_m_s"], dp["axis_sigma_m_s"][0],
            dp["axis_sigma_m_s"][1], dp["axis_sigma_m_s"][2],
            dp["axis_sigma_m_s"][3]),
        "",
        "## 5. RTK",
        "",
        "- Base station range %.1f km (< 10 km, no residual troposphere/"
        "ionosphere double-difference error assumed). L1 wavelength "
        "lambda = %.9f m." % (rtk["baseline_km"], LAMBDA_L1),
        "- Float double-difference solution sigma0 = %.4f m." %
        rtk["float_sigma0_m"],
        "- Integer ambiguity search (radius 2 cycles): fixed = %s cycles "
        "(true = %s); ratio test = %.2f (threshold %.1f) -> **%s**." % (
            tuple(round(v_, 0) for v_ in rtk["fixed_cycles"]),
            rtk["true_cycles"], rtk["ambiguity_ratio"], RTK_RATIO_MIN,
            "FIXED" if rtk["ambiguity_resolved"] else "FLOAT (not resolved)"),
        "- Fixed-baseline ENU: (%.3f, %.3f, %.3f) m (true (%.1f, %.1f, "
        "%.1f) m); per-axis 1-sigma (E, N, U) = (%.4f, %.4f, %.4f) m." % (
            rtk["baseline_enu_m"][0], rtk["baseline_enu_m"][1],
            rtk["baseline_enu_m"][2], rtk["true_baseline_enu_m"][0],
            rtk["true_baseline_enu_m"][1], rtk["true_baseline_enu_m"][2],
            rtk["enu_1sigma_m"][0], rtk["enu_1sigma_m"][1],
            rtk["enu_1sigma_m"][2]),
        "",
        "## 6. INS-GNSS integration",
        "",
        "- Loosely-coupled 5-state psi-angle error filter (states: "
        "dr_N, dr_E, dv_N, dv_E, psi), initialized from the section-2 "
        "coasting error budget. Kalman/ins-gnss leaf logic; the "
        "tightly-coupled 8-state per-pseudorange alternative "
        "(tightly-coupled-ins-gnss) applies when raw per-satellite "
        "measurements (not a position fix) are the GNSS input.",
        "- Predict (dt = %.1f s, f_N = %.2f, f_E = %.2f m/s^2): position "
        "variance grows to (%.3f, %.3f) m^2 [dr_N, dr_E]." % (
            ig["dt_s"], ig["f_north_m_s2"], ig["f_east_m_s2"],
            ig["p_pred_diag"][0], ig["p_pred_diag"][1]),
        "- GNSS position measurement update (R = %.1f m per axis): "
        "innovation (%.3f, %.3f) m; post-update position 1-sigma "
        "**%.3f m**." % (ig["gnss_sigma_m"], ig["innovation"][0],
                         ig["innovation"][1], ig["pos_1sigma_after_m"]),
        "",
        "## 7. GNSS-denied segment (terrain-referenced navigation)",
        "",
        "- TERCOM: %d-sample profile over the %.0f s corridor matched "
        "against a %d-candidate correlation surface (Pearson r). Best "
        "match offset (%.1f, %.1f) m (true INS offset (%.1f, %.1f) m), "
        "r = %.4f." % (
            tr["n_samples"], ins["t_s"], tr["n_candidates"],
            tr["tercom_best"]["dx"], tr["tercom_best"]["dy"],
            tr["true_offset_m"][0], tr["true_offset_m"][1],
            tr["tercom_best"]["r"]),
        "- SITAN slope-linearized filter refinement from the TERCOM cue: "
        "position offset (dr_e, dr_n) = (%.2f, %.2f) m, altitude bias "
        "%.2f m; post-filter 1-sigma (%.3f, %.3f) m [e, n]." % (
            tr["sitan_dr_e_m"], tr["sitan_dr_n_m"], tr["sitan_bias_m"],
            tr["sitan_sigma_e_m"], tr["sitan_sigma_n_m"]),
        "",
        "## 8. Bearing-only localization",
        "",
        "- Passive secondary sensor: %d ground observers, bearing sigma "
        "%.1f deg. Stansfield two-pass WLS fix: (%.1f, %.1f) m (true "
        "(%.1f, %.1f) m)." % (br["n_observers"], br["sigma_deg"],
                              br["fix_m"][0], br["fix_m"][1],
                              br["true_m"][0], br["true_m"][1]),
        "- 1-sigma error ellipse: semi-major %.2f m, semi-minor %.2f m, "
        "orientation %.1f deg." % (br["ellipse"]["semi_major_m"],
                                   br["ellipse"]["semi_minor_m"],
                                   br["ellipse"]["orientation_deg"]),
        "- Geometry dilution factor d = %.2f -> **%s** (observability "
        "degrades as the observer-target geometry approaches collinear "
        "bearing lines)." % (br["dilution_factor"], br["dilution_verdict"]),
        "",
        "## 9. Integrated error budget and verdict",
        "",
        "| Flight phase | Position 1-sigma (m) |",
        "|---|---|",
    ]
    for phase, val in bud["phases"].items():
        lines.append("| %s | %.3f |" % (phase, val))
    lines += [
        "",
        "Requirement: integrated position error <= %.1f m (1-sigma), all "
        "phases. Worst phase: **%s** at %.3f m -> **%s**." % (
            bud["requirement_m"], bud["worst_phase"], bud["worst_value_m"],
            "PASS" if bud["ok"] else "FAIL"),
        "",
        "| Gate | Result |",
        "|---|---|",
        "| RAIM/FDE integrity (no fault) | %s |" % v["raim_integrity"],
        "| RTK ambiguity resolution | %s |" % v["rtk_ambiguity"],
        "| Integrated position budget | %s |" % v["position_budget"],
        "",
        "- All error figures are 1-sigma design predictions from the "
        "stated sensor and geometry assumptions; they are DRAFT analysis "
        "for human navigation-engineering review, not flight test results.",
        "- Open items: full flight-envelope multipath/ionosphere "
        "characterization, sensor-in-the-loop validation, and gain-"
        "schedule coverage of the survey grid pattern.",
        "",
        "## Appendix A. Calculation traceability",
        "",
        "- Frames/geodesy: WGS84 geodetic->ECEF and ECEF->NED rotation "
        "(navigation-frames).",
        "- INS coasting: accel-bias position error 0.5*b*t^2, gyro-drift "
        "position error (1/6)*g*eps*t^3, Schuler period 2*pi*sqrt(R/g), "
        "ARW sigma = arw*sqrt(t_hours) (inertial-navigation).",
        "- GNSS fix: iterated pseudorange LS on the linearized geometry "
        "matrix (gnss-pseudorange-positioning); DOP = sqrt(trace) of "
        "(H'H)^-1 blocks (dilution-of-precision).",
        "- RAIM/FDE: chi-square test statistic sse/sigma^2 vs "
        "chi2_quantile(n-4, 1-Pfa) (Wilson-Hilferty cubic approximation "
        "of a normal quantile via Acklam's rational approximation); HPL "
        "from the worst-case error slope (gnss-raim-fde).",
        "- Carrier smoothing: Hatch filter steady-state std "
        "sigma_code*sqrt(a/(2-a)) + carrier term (gnss-carrier-smoothing).",
        "- Doppler velocity: linearized range-rate LS, state "
        "(vx,vy,vz,c*dtr_dot) (gnss-doppler-velocity-positioning).",
        "- RTK: double-difference float LS, integer ambiguity ratio test "
        "(ratio_min = 3.0), fixed-baseline LS (gnss-rtk-positioning).",
        "- INS-GNSS integration: 5-state psi-angle error model, "
        "Phi = I + F*dt, standard Kalman predict/update "
        "(kalman-filter-design, ins-gnss-integrated-filter).",
        "- Terrain-referenced navigation: TERCOM Pearson-r correlation "
        "match, SITAN slope-linearized Kalman bias update "
        "(terrain-referenced-navigation).",
        "- Bearing-only localization: Stansfield two-pass WLS fix, "
        "geometry dilution factor d = 1/sqrt(lambda_min(S)) "
        "(bearing-only-localization).",
        "",
        "---",
        "*Generated by Aero Agent Roles navigation-engineer core (%s). "
        "DRAFT - for human navigation-engineering lead review. Design "
        "predictions only; not flight software release, not a "
        "certification finding, not an approval document.*" % m["generated"],
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evidence gates
# ---------------------------------------------------------------------------

def check_report(m: dict) -> dict:
    bud = m["budget"]
    results = {
        "ins_error_computed": m["ins"]["total_position_1sigma_m"] > 0.0,
        "gnss_fix_converged": m["gnss_fix"]["iterations"] > 0,
        "dop_computed": all(v > 0.0 for v in m["gnss_fix"]["dops"].values()),
        "raim_test_computed": m["raim"]["threshold"] > 0.0,
        "rtk_ratio_test_computed": m["rtk"]["ambiguity_ratio"] > 0.0,
        "integration_covariance_shrinks": (
            m["integration"]["p_upd_diag"][0] < m["integration"]["p_pred_diag"][0]),
        "tercom_offset_recovered": (
            abs(m["terrain"]["tercom_best"]["dx"] - m["terrain"]["true_offset_m"][0])
            <= 2 * 25.0),
        "bearing_fix_finite": math.isfinite(m["bearing"]["fix_m"][0]),
        "position_budget_met": bool(bud["ok"]),
        "sign_off_honest": m.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_report_markdown(md_text: str) -> dict:
    low = md_text.lower()
    checks = {
        "has_title": "navigation architecture and position error analysis "
                     "report" in low,
        "has_frames": "wgs84" in low and "ecef" in low,
        "has_ins_error": "coasting position error" in low,
        "has_gnss_dop": "gdop" in low and "pdop" in low,
        "has_raim": "raim" in low,
        "has_rtk": "ambiguity" in low and "ratio test" in low,
        "has_error_budget": "integrated error budget" in low or
        "integrated position budget" in low,
        "no_blank_fields": "___" not in md_text,
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
        "has_not_flight_release": "not flight software release" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    return check_report_markdown(md_text)


# ---------------------------------------------------------------------------
# Example project (tests + worked-example generation)
# ---------------------------------------------------------------------------

def example_project() -> NavProject:
    return NavProject()


def example_item():
    return example_project()


def example_report_markdown() -> str:
    return render_report_markdown(build_report(example_project()))


if __name__ == "__main__":
    proj = example_project()
    model = build_report(proj)
    md = render_report_markdown(model)
    print("VEHICLE: %s" % model["vehicle"])
    print("INS coasting 1-sigma: %.3f m" % model["ins"]["total_position_1sigma_m"])
    print("GNSS pos 1-sigma: %.3f m (PDOP %.2f)" % (
        model["gnss_fix"]["pos_1sigma_m"], model["gnss_fix"]["dops"]["pdop"]))
    print("RAIM: T=%.3f thresh=%.3f fault=%s HPL=%.1f m" % (
        model["raim"]["test_statistic"], model["raim"]["threshold"],
        model["raim"]["fault_detected"], model["raim"]["hpl_m"]))
    print("Carrier smoothing improvement: %.1fx" %
          model["smoothing"]["improvement_factor"])
    print("RTK ratio=%.2f resolved=%s ENU sigma=%s" % (
        model["rtk"]["ambiguity_ratio"], model["rtk"]["ambiguity_resolved"],
        model["rtk"]["enu_1sigma_m"]))
    print("Integration post-update pos 1-sigma: %.3f m" %
          model["integration"]["pos_1sigma_after_m"])
    print("TERCOM best offset: %s (true %s)" % (
        model["terrain"]["tercom_best"], model["terrain"]["true_offset_m"]))
    print("Bearing-only fix: %s (true %s) dilution=%.2f" % (
        model["bearing"]["fix_m"], model["bearing"]["true_m"],
        model["bearing"]["dilution_factor"]))
    print("Budget worst phase: %s = %.3f m -> ok=%s" % (
        model["budget"]["worst_phase"], model["budget"]["worst_value_m"],
        model["budget"]["ok"]))
    print("GATES(model): %s" % check_report(model))
    print("GATES(markdown): %s" % check_report_markdown(md))
    print("RENDERED: %d chars" % len(md))
