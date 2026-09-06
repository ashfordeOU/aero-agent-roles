# Stability and Control Flight Test Report

**Item:** Reference transport airplane - stability & control flight test (worked example)
**Airframe:** Reference transport-category airplane (worked example)
**Configuration:** clean, flaps up, test CG 25 % MAC
**Certification basis:** FAR/CS-25 (context only; summary-not-copy)
**Status:** draft-for-review

## 1. Test item and conditions

This report reduces the measured stability and control records of the reference transport-category airplane flight test campaign: the static longitudinal trim sweep, the dynamic mode excitations, the steady-heading sideslip sweep and the longitudinal control force records. All flight data below are the SIMULATED worked-example datasets of the bound AeroSkills leaves and must be replaced by recorded flight data before any program use.

Every number in this report is computed by the role core from the bound leaf formulas: trim curve reduction and neutral point relations (CL = 2 W/(rho V^2 S), h_n = h + b Cm_delta_e pi/180), log decrement mode identification (delta = (1/n) ln(A0/An), zeta = delta/sqrt(delta^2 + 4 pi^2)), the SHS signed estimates (Cn_beta = -cn_dr s_r, Cl_beta = -cl_da s_a) and the control force least squares fits. Practice bands are typical flight test practice; FAR/CS certification criteria take precedence.

## 2. Static longitudinal stability

Trim curve fit (elevator angle vs lift coefficient, delta_e = a + b CL):

| Speed (m/s) | CL | Elevator (deg) |
|---|---|---|
| 115.58 | 0.500 | +0.000 |
| 105.51 | 0.600 | -0.600 |
| 97.68 | 0.700 | -1.200 |
| 91.372 | 0.800 | -1.800 |
| 86.146 | 0.900 | -2.400 |

- Trim curve slope b = d(delta_e)/dCL = **-6 deg per CL** (negative slope = statically stable), intercept 3 deg, R^2 = 1, n = 5.
- CG position for the demonstrated margin h = **0.25 MAC** (trim sweep measured at trim CG 0.25 MAC). Stick fixed neutral point from the slope, h_n = h_trim + b Cm_delta_e (pi/180) = **0.3024 MAC** (absolute); static margin SM = h_n - h = **0.05236 MAC** -> **Stable**.
- Stick free neutral point (free elevator hinge model, shift (Cm_delta_e Ch_alpha)/(CL_alpha Ch_delta_e) = 0.01875 MAC) = **0.2836 MAC**; stick free static margin **0.03361 MAC** -> **Stable**.
- Elevator angle per g: d(delta_e)/dn = (180/pi) CL SM / Cm_delta_e = **-4.2 deg/g** (magnitude 4.2 deg/g). elevator moves trailing-edge-up with increasing load factor, consistent with a statically stable aircraft.

## 3. Dynamic stability (mode identification and verdicts)

| Mode | Excitation | Damping ratio | Damped freq (Hz) | t half (s) | Band | Verdict |
|---|---|---|---|---|---|---|
| Short Period | elevator doublet (push-pull-push) | 0.41 | 1.111 | 0.2209 | 0.3 to 2 | **Acceptable** |
| Phugoid | elevator pulse | 0.05997 | 0.05 | 36.72 | 0.04 to 2 | **Acceptable** |
| Dutch Roll | rudder pulse | 0.1483 | 0.3333 | 2.208 | 0.08 to 2 | **Acceptable** |
| Spiral | rudder step, hold a small bank angle | 0.05 | aperiodic | n/a (aperiodic) | 0 to 2 | **Acceptable** |

- **Short Period**: log decrement over 2 cycle(s) of the decaying record; acceptable.
- **Phugoid**: log decrement over 2 cycle(s) of the decaying record; acceptable.
- **Dutch Roll**: log decrement over 2 cycle(s) of the decaying record; acceptable.
- **Spiral**: aperiodic; damping-ratio estimate from the 20-30 s rudder-step convergence record; acceptable.

## 4. Static lateral-directional stability (steady-heading sideslip)

Sideslip sweep at constant CAS 80 m/s, altitude 3000 m, commanded beta inside +-15 deg (left slip positive). Declared control powers: cn_dr = -0.9 /rad, cl_da = -0.35 /rad.

| Beta (deg) | Rudder (deg) | Aileron (deg) | Rudder-free pedal force (N) |
|---|---|---|---|
| 2 | +0.240 | -0.350 | 0 |
| 5 | +0.580 | -0.800 | -95 |
| 8 | +0.960 | -1.300 | -185 |
| 11 | +1.340 | -1.800 | -275 |
| 14 | +1.700 | -2.300 | -360 |

- Rudder gradient s_r = d(delta_r)/d(beta) = **0.12267 deg/deg** (positive = pilot pushes rudder into the slip).
- Aileron gradient s_a = d(delta_a)/d(beta) = **-0.16333 deg/deg** (negative = aileron holds the slip against the dihedral roll).
- Pedal-force gradient (rudder free) g_p = **-30 N/deg**.
- Directional estimate Cn_beta = -cn_dr * s_r = **0.1104 /rad** -> weathercock verdict **Stable**.
- Lateral estimate Cl_beta = -cl_da * s_a = **-0.05717 /rad** -> dihedral verdict **Stable**.

## 5. Longitudinal control forces

Force transducer calibration (applied lbf vs recorded counts): slope **0.019802 lbf/count**, intercept **-4.3564 lbf**; calibrated force at 2100 counts = **37.228 lbf**.

- Stick force gradient vs calibrated airspeed: slope **0.222 lbf/kt** (pull positive), R^2 0.99927 -> **Stable Gradient**.
- Stick force per g from the pull-ups: **13.14 lbf/g**, R^2 0.99962.
- Breakout force from the push-pull hysteresis: hysteresis width **10.6 lbf**, breakout **5.3 lbf**.
- Control centering check: residual **0.42 deg** against limit **0.5 deg**, margin **0.08 deg** -> **Centered**.

## 6. Demonstration rollup

| Subject | Measured value | Verdict | Pass |
|---|---|---|---|
| Static longitudinal stability, stick fixed | static margin 0.05236 MAC (neutral point 0.3024 MAC) | Stable | YES |
| Static longitudinal stability, stick free | static margin 0.03361 MAC (neutral point 0.2836 MAC) | Stable | YES |
| Elevator angle per g | -4.2 deg/g (magnitude 4.2 deg/g) | Stable | YES |
| Dynamic stability, short period | damping ratio 0.41 | Acceptable | YES |
| Dynamic stability, phugoid | damping ratio 0.05997 | Acceptable | YES |
| Dynamic stability, dutch roll | damping ratio 0.1483 | Acceptable | YES |
| Dynamic stability, spiral | damping ratio 0.05 | Acceptable | YES |
| Directional (weathercock) stability | Cn_beta estimate 0.1104 /rad | Stable | YES |
| Lateral (dihedral) stability | Cl_beta estimate -0.05717 /rad | Stable | YES |
| Stick force gradient vs speed | 0.222 lbf/kt | Stable Gradient | YES |
| Control centering (residual vs limit) | residual 0.42 deg, limit 0.5 deg, margin 0.08 deg | Centered | YES |

**Rollup gate: CLOSED** (11/11 checks pass).

Requirement/finding verification: 5/5 verified (CLOSED).

## 7. Sign-off status

This report is a **DRAFT** prepared for the human flight test engineer and the stability and control specialist to review before the demonstration is presented to the certification authority. It documents measured data reductions and verdicts only.

---
*Generated by Aero Agent Roles stability-control-flight-test-engineer core (2026-09-06). DRAFT for human flight test engineering review. Not an approval document and not a certification finding - the authority/regulator signs.*