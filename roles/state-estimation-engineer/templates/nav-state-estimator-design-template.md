# Navigation State Estimator Design Report

**Item:** UAV navigation state estimator (INS/GNSS + AHRS)
**Estimator class:** attitude (complementary filter) + loosely-coupled GNSS/INS
**Vehicle / platform:** small fixed-wing UAV (autopilot reference design)
**Intended use:** design analysis for the navigation state estimator before implementation on the flight computer
**Status:** draft-for-review

## 1. Scope

This report produces the navigation state estimator design for UAV navigation state estimator (INS/GNSS + AHRS). Loosely-coupled GNSS/INS navigation filter with a complementary-filter attitude channel for a small fixed-wing UAV autopilot. The estimator architecture is attitude (complementary filter) + loosely-coupled GNSS/INS: an attitude channel (complementary filter) plus a loosely-coupled GNSS position/velocity channel (linear constant-velocity Kalman recursion with an EKF nonlinear-update option). Outputs are DRAFT design numbers for a human navigation engineer to review before implementation on the target computer.

## 2. Design inputs (noise model)

- Navigation update interval dt = 1 s over a 60-step design horizon.
- Process noise intensity q = 0.01 m^2/s^3 -> sigma_w = 0.1 m/s^2.
- Measurement variance r = 4 m^2 (GNSS position, sigma_v = 2.0 m).
- Initial covariance P0 = diag(100 m^2, 25 (m/s)^2).
- IMU/attitude rate dt = 0.01 s; attitude design horizon 100 s.
- Particle fallback count n = 1000.

## 3. Attitude channel (complementary filter)

- Filter: Mahony-style explicit complementary filter (SO(3)).
- Gains: k_p = 2 1/s, k_i = 0.4 1/s^2 (leaf module defaults); corrected rate omega_c = omega_m - b + k_p*e with bias step b <- b - k_i*e*dt.
- Gyro bias input b = [0.001, -0.0008, 0.0006] rad/s per axis, |b| = 0.001414 rad/s.
- Drift anchor: uncompensated bias integrates to |b|*t = 0.014142 rad after 10 s and 0.141421 rad (8.103 deg) after 100 s - the error the bias estimate removes.
- Discrete-integration lag bound |omega|*dt = 0.000229 rad/step (0.013121 deg/step) at the example body rate.
- Steady-state acceptance: trailing-window innovation norm below 0.001 rad (leaf steady_state_verdict).
- Observability note: gyro bias is observable when at least two non-parallel reference vectors (accelerometer + magnetometer) are fused; a single reference leaves the bias along its axis unobservable (Mahony et al. 2008 nonlinear complementary filter on SO(3)).

## 4. Navigation channel (Kalman recursion)

- Model: discrete constant-velocity, H = [1 0], per axis.
- Transition F = [1.0, 1.0] / [0.0, 1.0]; discretized process covariance Q = [0.0025, 0.005] / [0.005, 0.01].
- Alpha-beta design companion (fixed-gain alternative for the smoothing stage): alpha = 0.5, Benedict-Bordner critical-damping beta = alpha^2/(2-alpha) = 0.166667; tracking index lambda = sigma_w*dt^2/sigma_v = 0.05 gives Kalata gains alpha = 0.270867, beta = 0.042695.
- First update: gain K = [0.968992849, 0.193833453], innovation variance S = 129.0025, position variance after 3.875971396 m^2.
- Mid-horizon (step 30): gain K = [0.270963014, 0.042713764], S = 5.486690082, position variance 1.083852057 m^2.
- Final (step 60): gain K = [0.270867122, 0.042694639], S = 5.4859685, position variance 1.083468489 m^2, velocity variance variance 0.058442889 (m/s)^2 - the steady-state covariance the design reports. The converged gain equals the Kalata alpha-beta pair above within the recursion tolerance, confirming the fixed-gain design is a faithful steady-state approximation of the full recursion.
- Residual RMS over the deterministic design run: 0.087482 m.

## 5. Nonlinear update design (EKF linearization)

- Measurement model: range + bearing (nonlinear) h(x) = [hypot(px,py), atan2(py,px)].
- Operating point x = [300.0, 40.0, 12.0, 0.0] (true measurement [302.6549, 0.132552]).
- Linearized measurement Jacobian (central differences) H = [0.991227893, 0.132163706, 0.0, 0.0] / [-0.000436681, 0.003275109, 0.0, 0.0].
- Deterministic measurement z = [305.6549, 0.132552] (range biased +3 m input).
- Innovation y = [3.0, 0.0]; innovation covariance diag(S) = [108.99999803, 0.00139632].
- Gain first row K = [0.909383403, -31.273707682].
- Corrected state x+ = [302.72815, 40.363753, 12.0, 0.0].

## 6. Consistency and fallback verification

- NEES = 0.9174 against the 2-state position subspace (expected value n = 2 for a consistent filter).
- SIR particle fallback: uniform ensemble of 1000 particles gives ESS = 1000; resample when ESS < n/2 (SIR, particle-filter leaf) (threshold 500).
- IMM two-mode bank (two-mode CV/CA IMM bank with Markov mode mixing for maneuvering flight).
- UKF option (scaled-unscented-transform alternative to EKF linearization for strongly nonlinear updates).

## 7. Offline post-processing (RTS smoothing)

- Method: fixed-interval RTS smoother over stored forward run.
- Smoothed position variance at the final boundary equals the filtered value (True); every interior smoothed variance at or below the filtered (True).
- Maximum covariance reduction: 82.946% (smoothed final position variance 1.083468489 m^2).

## 8. Observability analysis

- Discrete observability matrix rows [1.0, 0.0] / [1.0, 1.0] with determinant 1.0.
- Verdict: rank 2, fully observable for dt > 0: the velocity state is observable through the dynamics between position samples.

## 9. Verification evidence and open items

- Evidence gates (see cli.py check): architecture stated, attitude + navigation channels designated, alpha-beta and Kalman/EKF numbers present, observability checked, consistency metrics present.
- Open items for the human navigation engineer: final sensor datasheet noise values, lever-arm and time-tagging alignment, flight-computer numerical format, and the in-flight consistency monitoring policy.

---
*Generated by Aero Agent Roles state-estimation-engineer core (2026-09-05). DRAFT for human navigation engineer review. Not an approval document. Not flight software release.*
