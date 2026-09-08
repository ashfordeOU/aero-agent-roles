# Autopilot Control-Law Design Package - Pitch Attitude Hold with Roll / Turn-Coordination (Utility UAV)

**Vehicle:** Utility UAV (illustrative airframe, example cruise condition) (mass 22 kg, wing area 1.10 m^2)
**Condition:** Cruise, V=28 m/s TAS, altitude 1500 m (rho=1.0581 kg/m^3, q_bar=414.8 Pa), level flight, mid CG
**Mission / item:** Pitch attitude hold with roll / turn-coordination autopilot design
**Status:** draft-for-review

> DRAFT for human autopilot/GNC lead review. Design predictions only; not flight software release, not a certification finding, not an approval document. Example vehicle/flight-condition numbers are illustrative and flagged for verification against the real vehicle database.

## 1. State-space plant models

Reduced-order longitudinal and lateral models at the stated cruise condition, controllable-canonical (companion) form x_dot = A x + B u, y = C x + D u (example trim data; verify against the vehicle aerodynamic database):

**Short-period** (elevator to pitch rate q; wn=7.20 rad/s, zeta=0.60, elevator effectiveness b=5.0 1/s):

- A = [[0.000, 1.000], [-51.840, -8.640]], B = [[0.000], [5.000]], C = [[0.0, 1.0]], D = [[0]]
- Eigenvalues (closed form from trace/det): -4.320 + j5.760, -4.320 - j5.760 (computed from A, matches wn/zeta exactly). Controllable: True. Observable (q measured): True.

**Phugoid** (reduced order, informational; wn=0.22 rad/s, zeta=0.07):

- A = [[0.0000, 1.0000], [-0.0484, -0.0308]], B = [[0.000], [0.500]], C = [[1.0, 0.0]], D = [[0]]
- Eigenvalues: -0.015 + j0.219, -0.015 - j0.219 (lightly damped, not closed-loop controlled in this package; monitored for pilot/autopilot coupling).

**Roll subsidence** (aileron to roll rate p, first order; time constant 0.35 s, aileron effectiveness La=12.0 rad/s^2/rad):

- A = [[-2.857]], B = [[12.0]], C = [[1]], D = [[0]]. Pole at -2.857 rad/s (stable, real).

**Dutch-roll** (rudder to yaw rate r; wn=3.00 rad/s, zeta=0.12, rudder effectiveness b=4.0):

- A = [[0.000, 1.000], [-9.000, -0.720]], B = [[0.000], [4.000]], C = [[0.0, 1.0]], D = [[0]]
- Eigenvalues: -0.360 + j2.978, -0.360 - j2.978 (lightly damped dutch-roll pair; drives the turn-coordination yaw damper of section 4).

## 2. Inner/outer loop gain design

**Longitudinal** - inner pitch-rate loop by PID pole placement on the short-period plant (matched to (s^2 + 2 z_i wn_i s + wn_i^2)(s + p3_i)); outer pitch-attitude loop by proportional gain on the reduced inner-loop lag a/(s + a):

| Loop | Gains | Phase margin | Gain margin | Requirement | Verdict |
|---|---|---|---|---|---|
| inner q (PID) | kp=162.11, ki=1097.60, kd=8.63 | 77.0 deg | inf dB | PM >= 45 deg, GM >= 6 dB | PASS |
| outer theta (P) | kp_theta=5.950 1/s | 65.5 deg | inf dB | PM >= 45 deg, GM >= 6 dB | PASS |

Inner loop: wn_i=14.0 rad/s, zeta_i=0.85, non-dominant pole p3_i=28.0 rad/s; gain crossover 44.6 rad/s. Outer loop: reduced inner-loop lag a=zeta_i*wn_i=11.90 rad/s, damping target zeta=0.707, wn_theta=8.41 rad/s, achieved bandwidth 8.41 rad/s (requirement >= 3.5 rad/s, PASS).

**Lateral** - roll-attitude loop by classical root locus on the canonical type-1 plant G(s) = 1/(s(s + a)), a = 2.857 rad/s (roll subsidence pole); gain selected for target damping zeta = 0.707:

- Forward-path gain K = a^2/(4*zeta^2) = 4.082; physical roll-attitude proportional gain k_phi = K/La = 0.340 rad/rad.
- Closed-loop poles: -1.429 + j1.429, -1.429 - j1.429 -> damping zeta=0.707, natural frequency wn=2.020 rad/s. Stability verdict: STABLE.

Dutch-roll / turn-coordination yaw-rate damper (proportional rudder feedback on yaw rate r, kr=1.20, on the yaw-rate-to-rudder transfer function with its N_delta_r' numerator zero at 2.0 rad/s, which supplies the phase lead near crossover the way a washout-style damper does):

| Loop | Gain | Phase margin | Gain margin | Requirement | Verdict |
|---|---|---|---|---|---|
| yaw damper (P) | kr=1.20 | 80.8 deg | inf dB | PM >= 45 deg, GM >= 6 dB | PASS |

## 3. Observer design

Full-order (Ackermann) observer for angle of attack (not directly measured; no alpha vane assumed), estimated from the measured pitch rate q on the short-period plant:

- Observer poles: 45 rad/s (double), about 6.2x faster than the short-period natural frequency (separation principle). Settling time 4/sigma = 0.0889 s.
- Observer gain L = [-38.06, 81.36]. Error dynamics A - L C inherit the chosen poles exactly (Ackermann closed form).

## 4. L1 adaptive augmentation

Plant-uncertainty scenario: partial pitch-rate control-effectiveness loss (e.g. an elevator actuator degradation) combined with an unmodeled trim disturbance (asymmetric icing / gust bias), applied to a normalized representation of the pitch-rate command-tracking error channel (design pole a_m and unit-DC-gain reference b_m chosen independently of the inner/outer hardware gains of section 2, per the augmentation-layer convention). Scalar sigma-only L1 specialization, state predictor + projection-based adaptation law + low-pass filter, following gnc-autonomy/control/l1-adaptive-control exactly:

- Design model: a_m=-2.000, b=1.0, b_m=2.000, command r=1.0. True (unmodeled) plant coefficient a_p=-1.000 (50% of a_m, less-damped mismatch), constant matched disturbance d=1.00.
- Adaptation rate gamma=15.0, filter cutoff omega_c=10.0 rad/s (C(s) = omega_c/(s + omega_c)), projection bound sigma_b=2.5, step dt=0.010 s, run 6000 steps.
- Transient: max |tracking error| = 0.386343, max |prediction error| = 0.311635, max |sigma_hat| = 2.500000; projection clamp active on 28 steps.
- Final state: x_final=1.000000 (reference xm_final=1.000000), sigma_hat_final=2.000000, u_final=0.000000.
- Convergence verdict: tail |prediction error|=1.067e-11 (< 1e-4), tail sigma_hat drift=1.601e-12 (< 1e-6), |sigma_hat_final - sigma_ideal|=3.524e-13 (< 0.05) -> CONVERGED.
- Certified transient-bound check: max |tracking error| 0.386343 <= required bound 0.60 -> PASS.

## 5. Gain scheduling

Inner pitch-rate proportional gain kp scheduled against dynamic pressure q_bar (elevator effectiveness scales linearly with q_bar; gain re-derived by the same pole-placement rule at each breakpoint so the closed-loop wn_i/zeta_i target is held across the envelope):

| q_bar (Pa) | condition | kp |
|---|---|---|
| 180.0 | low-speed | 373.58 |
| 414.8 | cruise | 162.11 |
| 650.0 | high-speed dash | 103.45 |

- Linear interpolation at q_bar=300.0 Pa -> kp=265.503 (schedule_gain, breakpoints strictly increasing).
- Scheduling-variable rate limiting: one step from q_bar=180.0 toward 414.8 Pa at max_rate=400 Pa/s, dt=0.05 s -> 200.00 Pa (limited before interpolation, per gain-scheduling leaf practice).

## 6. Digital implementation

Sample period T=0.010 s (100 Hz):

- Sample-rate rule (10-20 samples per closed-loop cycle): w_s,min=10*wn_i=140.0 rad/s, T_max=0.0449 s; verdict: ok (T=0.010 s <= T_max).
- ZOH discretization of the roll subsidence pole a=2.857 rad/s at T=0.010 s: A_d=0.971833, B_d=0.028167 (A_d + B_d == 1 exactly, unit sampled DC gain).
- Inner PID velocity-form coefficients (u(k)=u(k-1)+b0 e(k)+b1 e(k-1)+b2 e(k-2)): b0=1036.2880, b1=-1888.5120, b2=863.2000, a1=-1.

## 7. Control allocation

Minimum-norm pseudoinverse allocation (u = B^+ m) across redundant effectors:

| Axis | Effectors (eff.) | Command | Allocation | Achieved | Error |
|---|---|---|---|---|---|
| Pitch | elevator (1.0) + stabilator (0.6) | 0.80 | [0.588, 0.353] | 0.8000 | 1.11e-16 |
| Turn coord. | aileron (1.0) + rudder (0.5) | 0.50 | [0.400, 0.200] | 0.5000 | 0.00e+00 |

## 8. Control-law summary and verdict

| Loop | Gain | Margin | Bandwidth |
|---|---|---|---|
| Inner pitch-rate (PID) | kp=162.11 ki=1097.60 kd=8.63 | PM=77.0 deg | wn=14.0 rad/s |
| Outer pitch-attitude (P) | kp_theta=5.950 | PM=65.5 deg | BW=8.41 rad/s |
| Roll attitude (root locus) | k_phi=0.340 | zeta=0.707 | wn=2.02 rad/s |
| Yaw-rate damper (P) | kr=1.20 | PM=80.8 deg | - |

| Gate | Result |
|---|---|
| Inner loop margins vs requirement | PASS |
| Outer loop margins/bandwidth vs requirement | PASS |
| Roll-attitude root-locus stability | PASS |
| Yaw damper margins vs requirement | PASS |
| L1 certified transient bound | PASS |
| L1 convergence | PASS |
| Digital sample-rate rule | PASS |
| Pitch allocation closes (zero error) | PASS |
| Turn-coordination allocation closes (zero error) | PASS |

**Verdict:** every gate above computed from the stated example plant/scenario facts and the domain rules of the bound AeroSkills leaves; no number is asserted without the calculation behind it. This package is a DRAFT for human autopilot/GNC lead review - not an approval, not a certification finding, and not a release of flight software. Open items: full 6-DOF nonlinear simulation with actuator and aeroelastic models, sensor-in-the-loop tests, gain-schedule coverage of the full flight envelope, and handling-qualities evaluation per MIL-STD-1797A where applicable.

## Appendix A. Calculation traceability

- State-space eigenvalues/controllability/observability: closed-form 2x2 trace/determinant and matrix-rank checks (state-space-analysis).
- PID pole placement: (s^2 + 2 z wn s + wn^2)(s + p3) matching (pid-control-design).
- Margins: type-1 closed form and general loops on jw with root-sum unwrapped phase (frequency-response-design); margin acceptance convention GM >= 6 dB, PM >= 45 deg (python-control-design).
- Root locus: s^2 + a s + K = 0 canonical closed form, gain for target damping K = a^2/(4 zeta^2) (root-locus-design).
- Observer: Ackermann L = phi(A) O^-1 e_n (observer-design).
- L1 adaptive augmentation: state predictor, projection-based adaptation law, low-pass filter C(s) = omega_c/(s + omega_c) (l1-adaptive-control, scalar sigma-only specialization).
- Gain schedule: linear breakpoint interpolation and scheduling-variable rate limiting (gain-scheduling).
- Digital: ZOH step-invariant discretization, velocity-form discrete PID, 10-20 samples/cycle sample-rate rule (digital-control-design).
- Control allocation: minimum-norm pseudoinverse u = B^+ m (control-allocation).

---
*Generated by Aero Agent Roles autopilot-control-engineer core (2026-09-08). DRAFT - for human autopilot/GNC lead review. Design predictions only; not flight software release, not a certification finding, not an approval document.*
