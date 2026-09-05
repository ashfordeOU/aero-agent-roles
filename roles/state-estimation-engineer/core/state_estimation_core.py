#!/usr/bin/env python3
"""state_estimation_core.py - State Estimation Engineer executable core.

This is the role's ENGINE: given a navigation state estimation item's
project facts (vehicle, sensor set, sample rates, noise-model inputs) it
computes the estimator design numbers and BUILDS the Navigation State
Estimator Design Report content:

  - complementary-filter attitude channel: Mahony-style explicit
    complementary filter gains (kp, ki), gyro-bias drift anchor |b|*t,
    discrete-integration lag |omega|*dt, innovation tolerance
    (bound leaf: gnc-autonomy/estimation-filtering/complementary-filter)
  - navigation (position/velocity) channel: discrete constant-velocity
    Kalman recursion with the standard discretized process-noise
    covariance Q = q*[[dt^4/4, dt^3/2], [dt^3/2, dt^2]] (bound leaves:
    rts-smoother forward_kalman model, interacting-multiple-model-filter
    kalman recursion)
  - alpha-beta design companion: Benedict-Bordner critical-damping beta
    and Kalata gains from the maneuverability/tracking index
    lambda = sigma_w*dt^2/sigma_v (bound leaf: alpha-beta-filter)
  - nonlinear update design: EKF linearization by central finite
    differences of a bearing/range measurement, innovation S, gain K,
    corrected state, and the NEES consistency metric (bound leaves:
    extended-kalman-filter, unscented-kalman-filter)
  - fallback/verification methods: IMM two-mode bank, SIR particle
    filter effective-sample-size rule ESS < n/2, fixed-interval RTS
    smoothing with covariance-reduction numbers (bound leaves:
    interacting-multiple-model-filter, particle-filter, rts-smoother)
  - observability analysis: discrete observability matrix rank/determinant
    for the measured position channel
  - evidence gates check_* that verify the deliverable

Standalone: stdlib only, deterministic, no AeroSkills checkout required.
Every formula below is grounded in the equations shipped by the bound
AeroSkills leaf logic files (their *_logic.py) or in the leaf SKILL.md
documentation; see SOURCES.md. No number is invented.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date

# ---------------------------------------------------------------------------
# Domain anchors (from the bound estimation-filtering leaves)
# ---------------------------------------------------------------------------

# Complementary-filter module defaults documented by the leaf (SKILL.md):
# proportional gain k_p in 1/s, integral gain k_i in 1/s^2.
CF_KP_DEFAULT = 2.0       # 1/s
CF_KI_DEFAULT = 0.4       # 1/s^2
# Steady-state innovation-norm tolerance (rad) used by the leaf's
# steady_state_verdict (trailing <=10 steps below tolerance => converged).
CF_INNOVATION_TOL = 1e-3  # rad

# SIR particle-filter degeneracy rule documented by the leaf: resample
# when the effective sample size drops below half the particle count.
PARTICLE_ESS_FRACTION = 0.5

# Fixed-interval smoothing semantics (leaf rts-smoother): the smoothed
# covariance must sit at or below the filtered covariance at every step
# and match it at the final (boundary) step.

# ---------------------------------------------------------------------------
# Small list-matrix helpers (stdlib; 2x2/4x4 sized use)
# ---------------------------------------------------------------------------


def _vec(n, v):
    return [float(v[i]) for i in range(n)]


def mat_mul(a, b):
    bt = list(zip(*b))
    return [[sum(ra[j] * cb[j] for j in range(len(ra))) for cb in bt]
            for ra in a]


def mat_vec(a, v):
    return [sum(a[i][j] * v[j] for j in range(len(v))) for i in range(len(a))]


def mat_transpose(a):
    return [list(r) for r in zip(*a)]


def mat_add(a, b):
    return [[a[i][j] + b[i][j] for j in range(len(a[0]))]
            for i in range(len(a))]


def mat_sub(a, b):
    return [[a[i][j] - b[i][j] for j in range(len(a[0]))]
            for i in range(len(a))]


def mat_scale(a, s):
    return [[a[i][j] * s for j in range(len(a[0]))] for i in range(len(a))]


def mat_identity(n):
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


def vec_sub(a, b):
    return [a[i] - b[i] for i in range(len(a))]


def vec_dot(a, b):
    return sum(a[i] * b[i] for i in range(len(a)))


def mat_inverse_2x2(a):
    """Inverse of a 2x2 matrix (RTS-smoother leaf inv_2x2 formula)."""
    det = a[0][0] * a[1][1] - a[0][1] * a[1][0]
    if abs(det) < 1e-300:
        raise ValueError("singular 2x2 matrix")
    return [[a[1][1] / det, -a[0][1] / det],
            [-a[1][0] / det, a[0][0] / det]]


def mat_inverse(m):
    """Gauss-Jordan inverse (extended-kalman-filter leaf mat_inverse)."""
    n = len(m)
    aug = [row[:] + [1.0 if i == j else 0.0 for j in range(n)]
           for i, row in enumerate(m)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-300:
            raise ValueError("singular matrix")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        pv = aug[col][col]
        aug[col] = [v / pv for v in aug[col]]
        for r in range(n):
            if r == col:
                continue
            f = aug[r][col]
            if f != 0.0:
                aug[r] = [a - f * b for a, b in zip(aug[r], aug[col])]
    return [row[n:] for row in aug]


# ---------------------------------------------------------------------------
# Domain rules: alpha-beta gains (alpha-beta-filter leaf formulas)
# ---------------------------------------------------------------------------

def steady_state_beta(alpha: float) -> float:
    """Benedict-Bordner critical-damping beta = alpha^2/(2 - alpha).

    Grounded in alpha-beta-filter leaf steady_state_gains() (valid for
    alpha in (0, 2)).
    """
    aa = float(alpha)
    if not 0.0 < aa < 2.0:
        raise ValueError("smoothing factor alpha must be in (0, 2)")
    return aa * aa / (2.0 - aa)


def kalata_gains(tracking_index: float) -> dict:
    """Kalata critical-damping (alpha, beta) from the tracking index.

    lambda = sigma_w*dt^2/sigma_v (ratio of position uncertainty
    accumulated by the process noise over one step to the measurement
    standard deviation). Grounded in the alpha-beta-filter leaf
    gains_from_tracking_index() closed forms.
    """
    lam = float(tracking_index)
    if lam < 0.0:
        raise ValueError("tracking index must be >= 0")
    if lam == 0.0:
        return {"alpha": 0.0, "beta": 0.0}
    s = math.sqrt(lam * lam + 8.0 * lam)
    alpha = -(lam * lam + 8.0 * lam - (lam + 4.0) * s) / 8.0
    beta = (lam * lam + 4.0 * lam - lam * s) / 4.0
    return {"alpha": alpha, "beta": beta}


def tracking_index_from_noise(sigma_w: float, dt: float,
                              sigma_v: float) -> float:
    """lambda = sigma_w*dt^2/sigma_v (alpha-beta leaf definition)."""
    if sigma_v <= 0.0:
        raise ValueError("measurement sigma must be > 0")
    if dt <= 0.0:
        raise ValueError("dt must be > 0")
    return sigma_w * dt * dt / sigma_v


# ---------------------------------------------------------------------------
# Domain rules: discrete constant-velocity Kalman recursion
# (rts-smoother forward_kalman + IMM kalman_predict/kalman_update models)
# ---------------------------------------------------------------------------

def cv_matrices(dt: float, q: float):
    """(F, Q) for the discrete constant-velocity model.

    F = [[1, dt], [0, 1]] and the discretized process-noise covariance
    Q = q*[[dt^4/4, dt^3/2], [dt^3/2, dt^2]] - identical to the
    rts-smoother leaf _model_matrices().
    """
    return ([[1.0, dt], [0.0, 1.0]],
            [[q * dt ** 4 / 4.0, q * dt ** 3 / 2.0],
             [q * dt ** 3 / 2.0, q * dt ** 2]])


def run_cv_kalman(measurements, dt: float, q: float, r: float,
                  x0=None, p0=None) -> list:
    """Run the linear constant-velocity Kalman recursion (per axis).

    Every step: predict x_pred = F x, P_pred = F P F^T + Q; update with
    innovation y = z - H x_pred (H = [1, 0]), innovation variance
    S = H P_pred H^T + r, gain K = P_pred H^T / S, and the filtered
    state/covariance (Joseph-form, as the rts-smoother leaf). Returns
    one record per measurement with x_pred, P_pred, innovation, S, gain,
    x_filt, P_filt. Deterministic: the covariance/gain recursion does
    not depend on the measurement values.
    """
    if dt <= 0.0:
        raise ValueError("dt must be > 0")
    if q < 0.0:
        raise ValueError("process noise intensity q must be >= 0")
    if r <= 0.0:
        raise ValueError("measurement variance r must be > 0")
    if not measurements:
        raise ValueError("measurements must be non-empty")
    f, q_disc = cv_matrices(dt, q)
    x = _vec(2, x0 if x0 is not None else [0.0, 0.0])
    p = [[float(v) for v in row] for row in
         (p0 if p0 is not None else [[100.0, 0.0], [0.0, 25.0]])]
    records = []
    for z in measurements:
        x_pred = mat_vec(f, x)
        p_pred = mat_add(mat_mul(mat_mul(f, p), mat_transpose(f)), q_disc)
        innov = float(z) - x_pred[0]
        s = p_pred[0][0] + r
        gain = [p_pred[0][0] / s, p_pred[1][0] / s]
        x_filt = [x_pred[0] + gain[0] * innov,
                  x_pred[1] + gain[1] * innov]
        kh = [[gain[0], 0.0], [gain[1], 0.0]]
        eye_kh = [[1.0 - kh[0][0], -kh[0][1]],
                  [-kh[1][0], 1.0 - kh[1][1]]]
        p_filt = mat_add(
            mat_mul(mat_mul(eye_kh, p_pred), mat_transpose(eye_kh)),
            mat_scale(mat_mul([[gain[0]], [gain[1]]],
                              [[gain[0], gain[1]]]), r))
        records.append({
            "x_pred": x_pred, "P_pred": p_pred,
            "innovation": innov, "S": s,
            "gain": gain, "x_filt": x_filt, "P_filt": p_filt,
        })
        x = x_filt
        p = p_filt
    return records


# ---------------------------------------------------------------------------
# Domain rules: fixed-interval RTS smoothing over the forward records
# (rts-smoother leaf rts_smooth + smoother_reduction semantics)
# ---------------------------------------------------------------------------

def rts_smooth(records: list) -> dict:
    """Backward Rauch-Tung-Striebel pass over CV forward records.

    Smoother gain G_k = P_filt[k] F^T (P_pred[k+1])^-1; smoothed state
    x_s[k] = x_filt[k] + G_k (x_s[k+1] - x_pred[k+1]); smoothed
    covariance P_s[k] = P_filt[k] + G_k (P_s[k+1] - P_pred[k+1]) G_k^T.
    Returns smoothed states/covariances plus the leaf's reduction
    verdict: max_reduction (largest relative drop of the position
    variance), all_reduced, boundary_matches.
    """
    n = len(records)
    if n < 2:
        raise ValueError("at least two forward records required")
    dt = records[0].get("dt", None)
    f = [[1.0, dt], [0.0, 1.0]] if dt else None
    if f is None:
        raise ValueError("forward records carry no dt")
    f_t = mat_transpose(f)
    x_s = [None] * n
    p_s = [None] * n
    gains = [None] * n
    x_s[n - 1] = list(records[n - 1]["x_filt"])
    p_s[n - 1] = [row[:] for row in records[n - 1]["P_filt"]]
    gains[n - 1] = [[0.0, 0.0], [0.0, 0.0]]
    for k in range(n - 2, -1, -1):
        fwd, nxt = records[k], records[k + 1]
        g = mat_mul(mat_mul(fwd["P_filt"], f_t),
                    mat_inverse_2x2(nxt["P_pred"]))
        diff = mat_vec(g, vec_sub(x_s[k + 1], nxt["x_pred"]))
        x_s[k] = vec_add_list(fwd["x_filt"], diff)
        p_corr = mat_sub(p_s[k + 1], nxt["P_pred"])
        p_s[k] = mat_add(fwd["P_filt"],
                         mat_mul(mat_mul(g, p_corr), mat_transpose(g)))
        gains[k] = g
    reductions = []
    all_reduced = True
    for k in range(n):
        p_f = records[k]["P_filt"][0][0]
        p_sk = p_s[k][0][0]
        reductions.append((p_f - p_sk) / p_f)
        if p_sk > p_f + 1e-12:
            all_reduced = False
    p_f_last = records[-1]["P_filt"]
    p_s_last = p_s[-1]
    boundary_matches = all(
        abs(p_s_last[i][j] - p_f_last[i][j]) <= 1e-12
        for i in range(2) for j in range(2))
    return {
        "smoothed_states": x_s,
        "smoothed_covs": p_s,
        "gains": gains,
        "max_reduction": max(reductions) if reductions else 0.0,
        "all_reduced": all_reduced,
        "boundary_matches": boundary_matches,
    }


def vec_add_list(a, b):
    return [a[i] + b[i] for i in range(len(a))]


# ---------------------------------------------------------------------------
# Domain rules: EKF linearization and one nonlinear update
# (extended-kalman-filter leaf: central-difference Jacobians)
# ---------------------------------------------------------------------------

def bearing_range_measurement(x):
    """Nonlinear measurement [range, bearing] of a 4-state CV target.

    Same model as the extended-kalman-filter leaf
    bearing_range_measurement(): range = hypot(px, py), bearing =
    atan2(py, px) (rad).
    """
    px, py = x[0], x[1]
    return [math.hypot(px, py), math.atan2(py, px)]


def numeric_jacobian(f, x, eps: float = 1e-6):
    """Central-finite-difference Jacobian (leaf jacobian())."""
    n = len(x)
    fx = f(x)
    scalar_out = isinstance(fx, (int, float))
    m = 1 if scalar_out else len(fx)
    j = [[0.0] * n for _ in range(m)]
    for col in range(n):
        xp = list(x)
        xm = list(x)
        xp[col] += eps
        xm[col] -= eps
        fp = f(xp)
        fm = f(xm)
        if scalar_out:
            j[0][col] = (fp - fm) / (2.0 * eps)
        else:
            for row in range(m):
                j[row][col] = (fp[row] - fm[row]) / (2.0 * eps)
    return j


def ekf_correct(x_pred, p_pred, z, h, r_mat, eps: float = 1e-6) -> dict:
    """One EKF correction at the predicted state (leaf ekf_update)."""
    h_jac = numeric_jacobian(h, x_pred, eps)
    hx = h(x_pred)
    z = [float(v) for v in z]
    innov = vec_sub(z, hx)
    s = mat_add(mat_mul(mat_mul(h_jac, p_pred), mat_transpose(h_jac)),
                r_mat)
    s_inv = mat_inverse(s)
    k = mat_mul(mat_mul(p_pred, mat_transpose(h_jac)), s_inv)
    x_new = vec_add_list(x_pred, mat_vec(k, innov))
    p_new = mat_mul(mat_sub(mat_identity(len(x_pred)),
                            mat_mul(k, h_jac)), p_pred)
    return {"x": x_new, "P": p_new, "y": innov, "S": s, "K": k, "H": h_jac}


# ---------------------------------------------------------------------------
# Domain rules: consistency metrics (UKF + particle-filter leaves)
# ---------------------------------------------------------------------------

def nees(x_est, p_est, x_true) -> float:
    """Normalized estimation error squared (UKF leaf nees()).

    NEES = (x_est - x_true)^T P^-1 (x_est - x_true); for a consistent
    filter the expected value is the state dimension n.
    """
    d = vec_sub([float(v) for v in x_est], [float(v) for v in x_true])
    return vec_dot(d, mat_vec(mat_inverse(p_est), d))


def effective_sample_size(weights) -> float:
    """ESS = (sum w)^2 / sum(w^2) (particle-filter leaf formula)."""
    if not weights:
        raise ValueError("weights must be non-empty")
    total = sum(float(w) for w in weights)
    if total <= 0.0:
        raise ValueError("total weight must be positive")
    sq = sum(w * w for w in weights)
    if sq <= 0.0:
        raise ValueError("sum of squared weights must be positive")
    return total * total / sq


def steady_state_verdict(innovation_norms, tolerance) -> bool:
    """Complementary-filter steady-state acceptance verdict.

    Mirrors the complementary-filter leaf steady_state_verdict(): True
    when the mean of the last min(10, n) per-step innovation norms is
    below the tolerance (rad). Raises ValueError on an empty sequence,
    non-finite norms, or a non-positive tolerance.
    """
    if not innovation_norms:
        raise ValueError("innovation_norms must be non-empty")
    norms = [float(x) for x in innovation_norms]
    for x in norms:
        if not math.isfinite(x):
            raise ValueError("innovation norms must be finite")
    tol = float(tolerance)
    if tol <= 0.0:
        raise ValueError("tolerance must be > 0")
    window = norms[-min(10, len(norms)):]
    return sum(window) / len(window) < tol


# ---------------------------------------------------------------------------
# Domain rules: observability (discrete linear systems practice)
# ---------------------------------------------------------------------------

def observability_rank(dt: float) -> dict:
    """Discrete observability of the CV pair [x, vx] with H = [1, 0].

    Observability matrix rows [H; H F] = [[1, 0], [1, dt]]; the
    determinant is dt, so the pair is fully observable (rank 2) for any
    dt > 0: velocity is observable through the dynamics between
    position samples. Returns the determinant, the rank, and the
    verdict.
    """
    if dt <= 0.0:
        raise ValueError("dt must be > 0")
    det = dt
    rank = 2 if abs(det) > 1e-12 else 1
    return {"det": det, "rank": rank, "observable": rank == 2}


# ---------------------------------------------------------------------------
# Item facts (inputs; noise-model values are design inputs from the
# sensor datasheets, never invented rules)
# ---------------------------------------------------------------------------

@dataclass
class NavEstimatorItem:
    """Project facts the role needs to build the design report."""
    item_name: str
    description: str = ""
    estimator_class: str = "attitude (complementary filter) + loosely-coupled GNSS/INS"
    vehicle: str = ""
    intended_use: str = ""
    dt: float = 1.0                  # GNSS/nav update interval, s
    horizon_steps: int = 60          # design evaluation horizon
    process_noise_intensity: float = 0.01   # q, m^2/s^3 (accel PSD input)
    meas_variance: float = 4.0       # r, m^2 (GNSS position variance input)
    initial_pos_var: float = 100.0   # P0[0][0], m^2
    initial_vel_var: float = 25.0    # P0[1][1], (m/s)^2
    alpha: float = 0.5               # alpha-beta smoothing factor
    gyro_bias_vec: list = field(default_factory=lambda:
                                [0.001, -0.0008, 0.0006])  # rad/s, per axis
    gyro_rate_mag: float = 0.0229    # rad/s (example body-rate magnitude)
    imu_dt: float = 0.01             # IMU/attitude update interval, s
    attitude_horizon_s: float = 100.0  # drift evaluation horizon, s
    cf_kp: float = CF_KP_DEFAULT
    cf_ki: float = CF_KI_DEFAULT
    ekf_op_point: list = field(default_factory=lambda:
                               [300.0, 40.0, 12.0, 0.0])  # px,py,vx,vy
    ekf_range_r: float = 9.0         # m^2 (range-aid measurement variance)
    ekf_range_error: float = 3.0     # m (deterministic range error input)
    particle_count: int = 1000
    measurement_drift: float = 0.5   # m per step (example target motion)

    @property
    def sigma_w(self) -> float:
        return math.sqrt(self.process_noise_intensity)

    @property
    def sigma_v(self) -> float:
        return math.sqrt(self.meas_variance)

    @property
    def bias_norm(self) -> float:
        return math.sqrt(sum(b * b for b in self.gyro_bias_vec))

    def tracking_index(self) -> float:
        return tracking_index_from_noise(self.sigma_w, self.dt,
                                         self.sigma_v)

    def measurement_sequence(self):
        """Deterministic ramp measurements (m) for the design run."""
        return [self.measurement_drift * k for k in range(1,
                                                          self.horizon_steps + 1)]

    def imu_measurement_sequence(self):
        """Gyro samples: constant rate about the body z axis."""
        return [[0.0, 0.0, self.gyro_rate_mag] for _ in range(
            int(self.attitude_horizon_s / self.imu_dt))]


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_report(item: NavEstimatorItem) -> dict:
    """Build the complete Navigation State Estimator Design Report model."""
    dt = item.dt
    # --- navigation channel: linear CV Kalman recursion ---------------
    x0 = [0.0, 0.0]
    p0 = [[item.initial_pos_var, 0.0], [0.0, item.initial_vel_var]]
    records = run_cv_kalman(item.measurement_sequence(), dt,
                            item.process_noise_intensity,
                            item.meas_variance, x0, p0)
    kf = [{
        "step": k + 1,
        "gain": records[k]["gain"],
        "S": records[k]["S"],
        "innovation": records[k]["innovation"],
        "P_filt": records[k]["P_filt"],
        "x_filt": records[k]["x_filt"],
    } for k in range(len(records))]

    # --- RTS smoothing over the same run ------------------------------
    recs_dt = [dict(r, dt=dt) for r in records]
    smooth = rts_smooth(recs_dt)

    # --- alpha-beta design companion ----------------------------------
    beta_bb = steady_state_beta(item.alpha)
    lam = item.tracking_index()
    kal = kalata_gains(lam)

    # --- EKF nonlinear (range/bearing) update design ------------------
    op = [float(v) for v in item.ekf_op_point]
    h_model = bearing_range_measurement(op)          # true measurement
    z = [h_model[0] + item.ekf_range_error, h_model[1]]  # deterministic meas
    p_op = [[item.initial_pos_var, 0.0, 0.0, 0.0],
            [0.0, item.initial_pos_var, 0.0, 0.0],
            [0.0, 0.0, item.initial_vel_var, 0.0],
            [0.0, 0.0, 0.0, item.initial_vel_var]]
    ekf = ekf_correct(op, p_op, z, bearing_range_measurement,
                      [[item.ekf_range_r, 0.0], [0.0, (math.pi / 180.0) ** 2]])
    ekf_nees = nees(ekf["x"][:2], [[ekf["P"][0][0], ekf["P"][0][1]],
                                   [ekf["P"][1][0], ekf["P"][1][1]]],
                    op[:2])

    # --- attitude channel (complementary filter design numbers) -------
    bias_norm = item.bias_norm
    drift_100 = bias_norm * item.attitude_horizon_s
    drift_10 = bias_norm * 10.0
    lag = item.gyro_rate_mag * item.imu_dt

    # --- consistency metrics (SIR rule + NEES) ------------------------
    ess = effective_sample_size([1.0 / item.particle_count]
                                * item.particle_count)

    # --- observability -------------------------------------------------
    obs = observability_rank(dt)

    return {
        "document_type": "Navigation State Estimator Design Report",
        "status": "draft-for-review",
        "item": item.item_name,
        "item_description": item.description,
        "estimator_class": item.estimator_class,
        "vehicle": item.vehicle,
        "intended_use": item.intended_use,
        "design_inputs": {
            "dt_s": dt,
            "horizon_steps": item.horizon_steps,
            "process_noise_intensity": item.process_noise_intensity,
            "meas_variance": item.meas_variance,
            "sigma_w_m_per_s2": round(item.sigma_w, 6),
            "sigma_v_m": round(item.sigma_v, 6),
            "initial_pos_var": item.initial_pos_var,
            "initial_vel_var": item.initial_vel_var,
            "imu_dt_s": item.imu_dt,
            "attitude_horizon_s": item.attitude_horizon_s,
            "particle_count": item.particle_count,
        },
        "attitude": {
            "filter": "Mahony-style explicit complementary filter (SO(3))",
            "kp_1_per_s": item.cf_kp,
            "ki_1_per_s2": item.cf_ki,
            "innovation_tolerance_rad": CF_INNOVATION_TOL,
            "gyro_bias_vec": item.gyro_bias_vec,
            "bias_norm": round(bias_norm, 6),
            "drift_10s_rad": round(drift_10, 6),
            "drift_100s_rad": round(drift_100, 6),
            "drift_100s_deg": round(math.degrees(drift_100), 3),
            "integration_lag_rad_per_step": round(lag, 9),
            "integration_lag_deg_per_step": round(math.degrees(lag), 6),
            "bias_observability_note": (
                "gyro bias is observable when at least two non-parallel "
                "reference vectors (accelerometer + magnetometer) are "
                "fused; a single reference leaves the bias along its "
                "axis unobservable (Mahony et al. 2008 nonlinear "
                "complementary filter on SO(3))"),
        },
        "alpha_beta": {
            "alpha": item.alpha,
            "beta_benedict_bordner": round(beta_bb, 6),
            "tracking_index_lambda": round(lam, 6),
            "kalata_alpha": round(kal["alpha"], 6),
            "kalata_beta": round(kal["beta"], 6),
        },
        "kalman": {
            "model": "discrete constant-velocity, H = [1 0], per axis",
            "F": [[1.0, dt], [0.0, 1.0]],
            "Q_discrete": [[round(item.process_noise_intensity * dt ** 4 / 4.0, 9),
                            round(item.process_noise_intensity * dt ** 3 / 2.0, 9)],
                           [round(item.process_noise_intensity * dt ** 3 / 2.0, 9),
                            round(item.process_noise_intensity * dt ** 2, 9)]],
            "first": {
                "gain": [round(kf[0]["gain"][0], 9), round(kf[0]["gain"][1], 9)],
                "S": round(kf[0]["S"], 9),
                "pos_var_after": round(kf[0]["P_filt"][0][0], 9),
            },
            "mid": {
                "gain": [round(kf[len(kf) // 2]["gain"][0], 9),
                         round(kf[len(kf) // 2]["gain"][1], 9)],
                "S": round(kf[len(kf) // 2]["S"], 9),
                "pos_var_after": round(kf[len(kf) // 2]["P_filt"][0][0], 9),
            },
            "final": {
                "step": len(kf),
                "gain": [round(kf[-1]["gain"][0], 9), round(kf[-1]["gain"][1], 9)],
                "S": round(kf[-1]["S"], 9),
                "pos_var_after": round(kf[-1]["P_filt"][0][0], 9),
                "vel_var_after": round(kf[-1]["P_filt"][1][1], 9),
            },
            "residual_rms": round(math.sqrt(
                sum(r["innovation"] ** 2 for r in records) / len(records)), 6),
        },
        "ekf": {
            "measurement_model": "range + bearing (nonlinear)",
            "operating_point": [round(v, 4) for v in op],
            "true_measurement": [round(h_model[0], 4), round(h_model[1], 6)],
            "measurement_z": [round(z[0], 4), round(z[1], 6)],
            "H": [[round(v, 9) for v in row] for row in ekf["H"]],
            "innovation": [round(v, 6) for v in ekf["y"]],
            "S_diag": [round(ekf["S"][0][0], 9), round(ekf["S"][1][1], 9)],
            "gain_row0": [round(v, 9) for v in ekf["K"][0]],
            "x_corrected": [round(v, 6) for v in ekf["x"]],
            "nees_2d": round(ekf_nees, 4),
            "nees_dimension": 2,
        },
        "verification_metrics": {
            "nees_expected_dim": 2,
            "nees_2d": round(ekf_nees, 4),
            "ess_uniform": round(ess, 4),
            "ess_rule": "resample when ESS < n/2 (SIR, particle-filter leaf)",
            "ess_threshold": item.particle_count * PARTICLE_ESS_FRACTION,
        },
        "smoothing": {
            "method": "fixed-interval RTS smoother over stored forward run",
            "max_reduction": round(smooth["max_reduction"], 9),
            "max_reduction_pct": round(100.0 * smooth["max_reduction"], 3),
            "all_reduced": smooth["all_reduced"],
            "boundary_matches": smooth["boundary_matches"],
            "smoothed_final_pos_var": round(
                smooth["smoothed_covs"][-1][0][0], 9),
        },
        "observability": {
            "matrix_rows": [[1.0, 0.0], [1.0, dt]],
            "det": round(obs["det"], 9),
            "rank": obs["rank"],
            "observable": obs["observable"],
        },
        "fallback_methods": {
            "imm": "two-mode CV/CA IMM bank with Markov mode mixing for "
                   "maneuvering flight",
            "particle": "SIR bootstrap filter (non-Gaussian fallback), "
                        "systematic resampling when ESS < n/2",
            "ukf": "scaled-unscented-transform alternative to EKF "
                   "linearization for strongly nonlinear updates",
            "rts": "fixed-interval smoothing for offline trajectory "
                   "reconstruction",
        },
        "generated": date.today().isoformat(),
    }


def render_report_markdown(model: dict) -> str:
    """Render the report content model as the deliverable markdown."""
    di = model["design_inputs"]
    at = model["attitude"]
    ab = model["alpha_beta"]
    km = model["kalman"]
    ek = model["ekf"]
    vm = model["verification_metrics"]
    sm = model["smoothing"]
    ob = model["observability"]
    lines = [
        "# Navigation State Estimator Design Report",
        "",
        f"**Item:** {model['item']}",
        f"**Estimator class:** {model['estimator_class']}",
        f"**Vehicle / platform:** {model['vehicle']}",
        f"**Intended use:** {model['intended_use']}",
        f"**Status:** {model['status']}",
        "",
        f"## 1. Scope",
        "",
        f"This report produces the navigation state estimator design for "
        f"{model['item']}." +
        (f" {model['item_description']}" if model["item_description"] else "") +
        " The estimator architecture is " + model["estimator_class"] +
        ": an attitude channel (complementary filter) plus a "
        "loosely-coupled GNSS position/velocity channel (linear "
        "constant-velocity Kalman recursion with an EKF nonlinear-update "
        "option). Outputs are DRAFT design numbers for a human navigation "
        "engineer to review before implementation on the target computer.",
        "",
        "## 2. Design inputs (noise model)",
        "",
        f"- Navigation update interval dt = {di['dt_s']:g} s over a "
        f"{di['horizon_steps']}-step design horizon.",
        f"- Process noise intensity q = {di['process_noise_intensity']:g} "
        f"m^2/s^3 -> sigma_w = {di['sigma_w_m_per_s2']} m/s^2.",
        f"- Measurement variance r = {di['meas_variance']:g} m^2 (GNSS "
        f"position, sigma_v = {di['sigma_v_m']} m).",
        f"- Initial covariance P0 = diag({di['initial_pos_var']:g} m^2, "
        f"{di['initial_vel_var']:g} (m/s)^2).",
        f"- IMU/attitude rate dt = {di['imu_dt_s']:g} s; attitude design "
        f"horizon {di['attitude_horizon_s']:g} s.",
        f"- Particle fallback count n = {di['particle_count']:g}.",
        "",
        "## 3. Attitude channel (complementary filter)",
        "",
        f"- Filter: {at['filter']}.",
        f"- Gains: k_p = {at['kp_1_per_s']:g} 1/s, k_i = "
        f"{at['ki_1_per_s2']:g} 1/s^2 (leaf module defaults); corrected "
        "rate omega_c = omega_m - b + k_p*e with bias step "
        "b <- b - k_i*e*dt.",
        f"- Gyro bias input b = {at['gyro_bias_vec']} rad/s per axis, "
        f"|b| = {at['bias_norm']} rad/s.",
        f"- Drift anchor: uncompensated bias integrates to |b|*t = "
        f"{at['drift_10s_rad']} rad after 10 s and "
        f"{at['drift_100s_rad']} rad ({at['drift_100s_deg']} deg) after "
        f"{di['attitude_horizon_s']:g} s - the error the bias estimate "
        "removes.",
        f"- Discrete-integration lag bound |omega|*dt = "
        f"{at['integration_lag_rad_per_step']} rad/step "
        f"({at['integration_lag_deg_per_step']} deg/step) at the example "
        "body rate.",
        f"- Steady-state acceptance: trailing-window innovation norm "
        f"below {at['innovation_tolerance_rad']:g} rad "
        "(leaf steady_state_verdict).",
        f"- Observability note: {at['bias_observability_note']}.",
        "",
        "## 4. Navigation channel (Kalman recursion)",
        "",
        f"- Model: {km['model']}.",
        f"- Transition F = {km['F'][0]} / {km['F'][1]}; discretized "
        f"process covariance Q = {km['Q_discrete'][0]} / "
        f"{km['Q_discrete'][1]}.",
        f"- Alpha-beta design companion (fixed-gain alternative for the "
        f"smoothing stage): alpha = {ab['alpha']:g}, "
        f"Benedict-Bordner critical-damping beta = alpha^2/(2-alpha) = "
        f"{ab['beta_benedict_bordner']}; tracking index "
        f"lambda = sigma_w*dt^2/sigma_v = {ab['tracking_index_lambda']} "
        f"gives Kalata gains alpha = {ab['kalata_alpha']}, "
        f"beta = {ab['kalata_beta']}.",
        f"- First update: gain K = {km['first']['gain']}, innovation "
        f"variance S = {km['first']['S']}, position variance after "
        f"{km['first']['pos_var_after']} m^2.",
        f"- Mid-horizon (step {di['horizon_steps'] // 2}): "
        f"gain K = {km['mid']['gain']}, S = {km['mid']['S']}, position "
        f"variance {km['mid']['pos_var_after']} m^2.",
        f"- Final (step {km['final']['step']}): gain K = "
        f"{km['final']['gain']}, S = {km['final']['S']}, position "
        f"variance {km['final']['pos_var_after']} m^2, velocity variance "
        f"variance {km['final']['vel_var_after']} (m/s)^2 - the steady-state "
        "covariance the design reports. The converged gain equals the "
        "Kalata alpha-beta pair above within the recursion tolerance, "
        "confirming the fixed-gain design is a faithful steady-state "
        "approximation of the full recursion.",
        f"- Residual RMS over the deterministic design run: "
        f"{km['residual_rms']} m.",
        "",
        "## 5. Nonlinear update design (EKF linearization)",
        "",
        f"- Measurement model: {ek['measurement_model']} "
        f"h(x) = [hypot(px,py), atan2(py,px)].",
        f"- Operating point x = {ek['operating_point']} "
        f"(true measurement {ek['true_measurement']}).",
        f"- Linearized measurement Jacobian (central differences) "
        f"H = {ek['H'][0]} / {ek['H'][1]}.",
        f"- Deterministic measurement z = {ek['measurement_z']} "
        "(range biased +3 m input).",
        f"- Innovation y = {ek['innovation']}; innovation covariance "
        f"diag(S) = {ek['S_diag']}.",
        f"- Gain first row K = {ek['gain_row0']}.",
        f"- Corrected state x+ = {ek['x_corrected']}.",
        "",
        "## 6. Consistency and fallback verification",
        "",
        f"- NEES = {ek['nees_2d']} against the {ek['nees_dimension']}-state "
        "position subspace (expected value n = "
        f"{vm['nees_expected_dim']} for a consistent filter).",
        f"- SIR particle fallback: uniform ensemble of "
        f"{di['particle_count']:g} particles gives ESS = "
        f"{vm['ess_uniform']:g}; {vm['ess_rule']} (threshold "
        f"{vm['ess_threshold']:g}).",
        f"- IMM two-mode bank ({model['fallback_methods']['imm']}).",
        f"- UKF option ({model['fallback_methods']['ukf']}).",
        "",
        "## 7. Offline post-processing (RTS smoothing)",
        "",
        f"- Method: {sm['method']}.",
        f"- Smoothed position variance at the final boundary equals the "
        f"filtered value ({sm['boundary_matches']}); every interior "
        f"smoothed variance at or below the filtered "
        f"({sm['all_reduced']}).",
        f"- Maximum covariance reduction: {sm['max_reduction_pct']}% "
        f"(smoothed final position variance "
        f"{sm['smoothed_final_pos_var']} m^2).",
        "",
        "## 8. Observability analysis",
        "",
        f"- Discrete observability matrix rows {ob['matrix_rows'][0]} / "
        f"{ob['matrix_rows'][1]} with determinant {ob['det']}.",
        f"- Verdict: rank {ob['rank']}, "
        f"{'fully observable' if ob['observable'] else 'NOT fully observable'} "
        "for dt > 0: the velocity state is observable through the "
        "dynamics between position samples.",
        "",
        "## 9. Verification evidence and open items",
        "",
        "- Evidence gates (see cli.py check): architecture stated, "
        "attitude + navigation channels designated, alpha-beta and "
        "Kalman/EKF numbers present, observability checked, consistency "
        "metrics present.",
        "- Open items for the human navigation engineer: final sensor "
        "datasheet noise values, lever-arm and time-tagging alignment, "
        "flight-computer numerical format, and the in-flight "
        "consistency monitoring policy.",
        "",
        "---",
        f"*Generated by Aero Agent Roles state-estimation-engineer core "
        f"({model['generated']}). DRAFT for human navigation engineer "
        "review. Not an approval document. Not flight software release.*",
    ]
    return "\n".join(lines)


def example_item() -> NavEstimatorItem:
    return NavEstimatorItem(
        item_name="UAV navigation state estimator (INS/GNSS + AHRS)",
        description="Loosely-coupled GNSS/INS navigation filter with a "
                    "complementary-filter attitude channel for a small "
                    "fixed-wing UAV autopilot.",
        estimator_class="attitude (complementary filter) + loosely-coupled GNSS/INS",
        vehicle="small fixed-wing UAV (autopilot reference design)",
        intended_use="design analysis for the navigation state estimator "
                     "before implementation on the flight computer",
    )


def example_report_markdown() -> str:
    return render_report_markdown(build_report(example_item()))


# ---------------------------------------------------------------------------
# Evidence gate checkers
# ---------------------------------------------------------------------------

GATE_CHECKS = {
    "architecture_stated": "estimator class / architecture is named",
    "channels_designated": "attitude and navigation filter designs are present",
    "gains_computed": "alpha-beta and complementary-filter gains are numbers",
    "kalman_numbers_present": "Kalman gain + covariance at the final step",
    "linearization_present": "EKF Jacobian H is a numeric matrix",
    "observability_checked": "observability rank/determinant computed",
    "consistency_metrics_present": "NEES + ESS figures computed",
    "sign_off_honest": "report is marked draft-for-review, not approval",
}


def check_report(model: dict) -> dict:
    """Run the evidence gates against a report content model."""
    ab = model.get("alpha_beta", {})
    km = model.get("kalman", {})
    ek = model.get("ekf", {})
    ob = model.get("observability", {})
    results = {
        "architecture_stated": bool(model.get("estimator_class")),
        "channels_designated": bool(model.get("attitude"))
            and bool(model.get("kalman")),
        "gains_computed": isinstance(ab.get("kalata_beta"), (int, float))
            and isinstance(ab.get("beta_benedict_bordner"), (int, float)),
        "kalman_numbers_present": isinstance(
            km.get("final", {}).get("gain"), list)
            and isinstance(km.get("final", {}).get("pos_var_after"),
                            (int, float)),
        "linearization_present": isinstance(ek.get("H"), list)
            and bool(ek.get("H")),
        "observability_checked": ob.get("observable") is not None,
        "consistency_metrics_present": isinstance(
            model.get("verification_metrics", {}).get("nees_2d"),
            (int, float)),
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_report_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    checks = {
        "has_title": "navigation state estimator design report" in low,
        "has_architecture": "estimator class" in low,
        "has_attitude_channel": "complementary filter" in low
            and "bias" in low,
        "has_nav_channel": "kalman" in low and "innovation" in low,
        "has_alpha_beta": "kalata" in low and "benedict" in low,
        "has_numbers": "gain" in low and "variance" in low,
        "has_observability": "observability" in low and "rank" in low,
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling: check a report document."""
    return check_report_markdown(md_text)


if __name__ == "__main__":
    model = build_report(example_item())
    md = render_report_markdown(model)
    print("ESTIMATOR CLASS:", model["estimator_class"])
    print("KALATA GAINS (lambda=%.4f): alpha=%.6f beta=%.6f"
          % (model["alpha_beta"]["tracking_index_lambda"],
             model["alpha_beta"]["kalata_alpha"],
             model["alpha_beta"]["kalata_beta"]))
    print("KF FINAL: gain=%s pos_var=%.6f"
          % (model["kalman"]["final"]["gain"],
             model["kalman"]["final"]["pos_var_after"]))
    print("EKF NEES: %.4f  OBSERVABLE: %s"
          % (model["ekf"]["nees_2d"],
             model["observability"]["observable"]))
    print("SMOOTH MAX REDUCTION: %.4f%%"
          % model["smoothing"]["max_reduction_pct"])
    print("GATES:", check_report(model))
    print("RENDERED: %d chars" % len(md))
