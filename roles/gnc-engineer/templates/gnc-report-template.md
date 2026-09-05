# GNC Design Report - Pitch Attitude Hold Autopilot

**Vehicle:** Utility UAV (example cruise condition)
**Condition:** Cruise, 60 m/s, altitude 3000 m, level flight
**Mission / item:** Pitch attitude hold autopilot design
**Status:** draft-for-review

## 1. Architecture and plant

- Control architecture: cascade pitch attitude hold - inner pitch rate (q) loop with PID; outer pitch attitude (theta) loop (proportional). Guidance and navigation layers analyzed in sections 2 and 6.
- Frames: body-fixed axes (x forward, z down) for the short-period model; stability axes for the longitudinal modes; inertial NED for the guidance geometry.
- Plant (reduced-order short-period, elevator to pitch rate, at the stated cruise condition):

  G_q(s) = 4.0 / (s^2 + 6.6 s + 36.0)

  with short-period natural frequency 6.0 rad/s, damping 0.55 and elevator effectiveness 4.0 1/s (example trim data; verify against the vehicle aerodynamic database).
- States: pitch rate q (plant state; the short-period model implicitly includes angle of attack). Input: elevator deflection. Output: pitch rate q. Pitch attitude theta = q/s for the outer loop.
- Assumptions: rigid airframe (no aeroelastic modes in this band), actuator modeled at >= 40 rad/s in the follow-up stage.

## 2. Navigation

- Sensor suite: rate gyro (pitch axis) and accelerometer-derived pitch measurement; scalar attitude Kalman filter at 100 Hz.
- Noise models: process noise q = 0.0009 deg^2 per step (integrated gyro drift), measurement noise r = 1.00 deg^2 (accel-derived pitch, non-accelerated-flight assumption).
- Filter: constant model f = 1, h = 1. Steady-state predicted covariance P = 0.0305 deg^2; steady-state gain K = 0.0296; post-update covariance P+ = 0.0296 deg^2.
- Attitude (pitch) error budget: 1-sigma = 0.172 deg against a budget of 0.5 deg - MET.
- Innovation monitor: 1-sigma innovation = 1.015 deg.
- GNSS/RAIM: not part of this attitude channel; the gnss-pseudorange-positioning / gnss-raim-fde / dilution-of-precision leaves apply when a full position navigation solution is in scope.

## 3. Control design

Inner pitch-rate loop (PID by pole placement on the short-period plant, matched to (s^2 + 2 z_i wn_i s + wn_i^2)(s + p3_i)):

| Loop | Gains | Phase margin | Gain margin | Requirement | Verdict |
|---|---|---|---|---|---|
| inner q (PID) | kp=156.60, ki=864.00, kd=9.75 | 76.7 deg | inf dB | PM >= 45 deg, GM >= 6 dB | PASS |
| outer theta (P) | kp_theta=5.400 1/s | 65.5 deg | inf dB | PM >= 45 deg, GM >= 6 dB | PASS |

Inner loop design: wn_i = 12.0 rad/s (>= 3x the attitude bandwidth requirement of 3.0 rad/s), zeta_i = 0.90, non-dominant pole p3_i = 24.0 rad/s. Inner open loop L(s) = C(s) G_q(s): gain crossover 40.4 rad/s, phase crossover none, phase margin 76.7 deg, gain margin inf dB (type-1 loop, phase recovers above -180 deg so the gain margin is infinite).

Outer loop: the closed inner loop is reduced to the lag a/(s + a) with a = zeta_i * wn_i = 10.8 rad/s, so the outer attitude plant is a/(s(s + a)) (type-1). The proportional gain kp_theta is sized for damping zeta = 0.71 (f(z) = 1 at z = 0.707, so bandwidth = natural frequency):

- Natural frequency from the bandwidth requirement: wn,req = w_bw / f(zeta) = 3.0 / 1.000 = 3.0 rad/s. The natural frequency implied by the damping target (wn = a / (2 zeta)) is 7.64 rad/s and exceeds the requirement.
- Achieved: wn_theta = 7.64 rad/s, zeta_theta = 0.71, bandwidth w_bw = 7.64 rad/s >= 3.0 rad/s requirement (PASS), phase margin 65.5 deg >= 45 deg (PASS), gain margin inf dB >= 6 dB (PASS).

## 4. Digital implementation

- Sample period T = 0.010 s (100 Hz); closed-loop characteristic frequency wn_i = 12.0 rad/s.
- Sample-rate rule (10-20 samples per closed-loop cycle): w_s,min = 10 * wn_i = 120.0 rad/s, T_max = 0.0524 s; verdict: ok (T = 0.010 s <= T_max).
- Inner PID velocity-form coefficients at T = 0.010 s (u(k) = u(k-1) + b0 e(k) + b1 e(k-1) + b2 e(k-2)): b0 = 1140.2400, b1 = -2106.6000, b2 = 975.0000, a1 = -1.

## 5. State estimation (observer)

- Full-order observer (Luenberger/Ackermann) for the comparison state-feedback design; plant theta_ddot = -2 q + u (normalized elevator pitch acceleration), measured state theta (C = [1, 0]).
- Observer poles: -30 rad/s (double) - about 10x faster than the controller poles (separation principle), settling time 4/sigma = 0.133 s.
- Observer gain L = [58.0, 784.0].

## 6. Guidance and optimal control

Guidance (terminal approach example, proportional navigation comparison; relative state from the nav estimate):

- Geometry: range r = 2061.6 m, line-of-sight 14.04 deg; heading error 2.58 deg; closing speed Vc = 181.90 m/s; line-of-sight rate 0.00706 rad/s.
- Commanded lateral acceleration a_c = N * Vc * lam_dot = 4.0 * 181.9 * 0.00706 = 5.14 m/s^2 (0.52 g) with N = 4.0; pure pursuit capture possible (V_i = 182.5 m/s > V_t = 0), tail-chase intercept time ~11.3 s.

Optimal control (LQR comparison on the normalized pitch-axis model x = [theta, q], x_dot = A x + B u with A = [[0,1],[0,-2]], B = [0,1], u = normalized elevator pitch acceleration):

- Weights: Q = diag(10, 1) (state error), R = 0.1 (control effort).
- Riccati solution P = [[5.831, 1.000],[1.000, 0.383]]; gain K = R^-1 B' P = [10.00, 3.83].
- Closed loop A - B K stable: yes (poles at -2.92 +/- j1.22 rad/s, wn = 3.16 rad/s, zeta = 0.32). The LQR result is a comparison design on the same axis; the PID cascade of section 3 is the baseline.

## 7. Space GNC

- Not applicable for this aircraft example. The space leaves (attitude-dynamics, orbit-dynamics, orbit-determination, rendezvous-phasing) load when the vehicle is a spacecraft.

## 8. Monte Carlo / robustness

- Monte Carlo on the outer loop (400 draws, seed 7): lag a and gain kp_theta varied uniformly over +/- 15% (a, inner-loop uncertainty) and +/- 10% (kp_theta, implementation tolerance).
- Result: phase margin min 60.9 deg / mean 65.4 deg / max 69.6 deg; all 400 draws >= 45 deg (PASS); zeta_theta range 0.63-0.79; minimum bandwidth 6.83 rad/s (still >= 3.0 rad/s requirement).
- Disturbance response: the rate-loop integral gives zero steady-state attitude error to constant pitch disturbances (type-1 loop); transient response and gust loads verified in the full 6-DOF simulation (open item).

## 9. Conclusions

| Gate | Result |
|---|---|
| Inner loop margins vs requirement | PASS |
| Outer loop margins vs requirement | PASS |
| Attitude bandwidth >= 3.0 rad/s | PASS |
| Nav error budget (1-sigma <= 0.5 deg) | PASS |
| Monte Carlo robustness (PM >= 45 deg) | PASS |

- Margins are design predictions from the stated reduced-order model and sensor assumptions.
- Open items for flight test / formal verification: full 6-DOF nonlinear simulation with actuator and aeroelastic models, sensor-in-the-loop tests, gain-schedule coverage of the flight envelope, and handling-qualities evaluation per MIL-STD-1797A where applicable.

## Appendix A. Calculation traceability

- PID gains: pole placement matching (s^2 + 2 z wn s + wn^2)(s + p3) (pid-control-design).
- Bandwidth/natural frequency: w_bw = f(z) wn with f(z) = sqrt(1 - 2z^2 + sqrt(2 - 4z^2 + 4z^4)); f(0.707) = 1.
- Margins: type-1 loop L = K/(s(s + a)) closed form; general loops evaluated on jw with root-sum unwrapped phase (frequency-response-design).
- LQR: K = R^-1 B' P, ARE closed form (lqr-design).
- Kalman: steady-state covariance = scalar Riccati root; K = h P/(h^2 P + r) (kalman-filter-design).
- Observer: Ackermann L = phi(A) O^-1 e_n (observer-design).
- Guidance: a_c = N Vc lam_dot (pursuit-guidance).
- Digital: 10-20 samples per closed-loop cycle; velocity-form discrete PID (digital-control-design).

---
*Generated by Aero Agent Roles gnc-engineer core (2026-09-05). DRAFT - for human GNC lead review. Design predictions only; not flight software release, not a certification finding, not an approval document.*