# Attitude Determination and Control Subsystem Report

**Spacecraft:** Aurora-1 - sun-synchronous Earth observation microsatellite
**Orbit:** 600 km circular, 97.8 deg inclination (period 96.5 min, mean motion 0.00108474 rad/s).
**Reference frame:** ECI (J2000).
**Pointing requirement (3-sigma):** 30.0 arcsec cross-boresight (payload requirement).
**Status:** draft-for-review

## 1. Scope and reference mission

This report covers the attitude determination and control subsystem (ADCS) of Aurora-1. It assembles the pointing error budget, sizes and checks the reaction wheel control law, the momentum management (desaturation) strategy and the magnetorquer actuation, and validates the attitude determination chain on a truth-model observation set.

All numbers below come from the standard ADCS formulas listed in SOURCES.md and the bound Aero Agent Skills leaves; component specifications and mass-model values are labeled project inputs for this worked example and must be verified against mission data before release.

### Assumed project facts (inputs)

- Principal inertia (x/y, z): 60 / 35 kg m^2
- Wheel torque limit: 0.01 N m per wheel
- Wheel momentum capacity: 0.2 N m s
- Worst-case environmental torque: 1e-05 N m per axis
- Magnetic field magnitude (orbit): 2.5e-05 T
- Magnetorquer dipole limit: 20 A m^2

## 2. Pointing requirements and ADCS modes

The payload requires 30.0 arcsec (3-sigma) cross-boresight pointing. The ADCS modes are mapped to the bound skills that deepen each stage: safe hold / sun pointing, B-dot detumble, coarse and fine attitude determination, acquisition slew and fine pointing (see the workflow in ROLE.md).

## 3. Environment and disturbance assumptions

Worst-case environmental torque is assumed at 1e-05 N m per axis (project environmental assessment; method per the bound environmental-disturbance-torque-budget leaf). Over one orbit this accumulates 0.058 N m s of momentum per axis, which the momentum-management strategy in Section 6 must absorb and unload.

## 4. Attitude determination

### 4.1 Coarse estimate (TRIAD)

The TRIAD algorithm (sun sensor + magnetometer pair, 90 deg inter-observation angle) recovers the acquisition attitude. On the truth-model observation set the recovered rotation angle is 10.000000 deg against the 10 deg slew target, with orthogonality error 4.44e-16 (a perfect rotation matrix would give 0).

### 4.2 Fine estimate (QUEST, Davenport q-method)

Three weighted vector observations (star tracker, sun sensor, magnetometer) feed the optimal attitude solution:

- Optimal quaternion q (w, x, y, z): 0.996195, 0, 0, 0.0871557
- Eigenangle: 10.000000 deg (target 10 deg)
- Largest eigenvalue of K: 3.000000
- Wahba cost J(q): 1.541e-33
- Residual RMS: 2.266e-17 rad (0.0000 arcsec)

The near-zero Wahba cost and residual RMS validate the determination chain on the noiseless truth model; in flight the star tracker measurement noise (2.0 arcsec 1-sigma per axis, project input) dominates, as captured in the Section 7 budget.

## 5. Gyro noise characterization

Gyro rate samples (2 h at 1 s, sigma 1e-05 rad/s, deterministic series) are characterized by the overlapping Allan deviation:

- tau = 1 s: AD = 1.004e-05 rad/s
- tau = 2 s: AD = 7.253e-06 rad/s
- tau = 5 s: AD = 4.644e-06 rad/s
- tau = 10 s: AD = 3.186e-06 rad/s
- tau = 30 s: AD = 1.803e-06 rad/s
- tau = 60 s: AD = 1.223e-06 rad/s

- Fitted log-log slope: -0.515 -> angle-random-walk
- Angle random walk coefficient: 0.0345 deg/sqrt(h)
- 1-sigma propagation over a 1 s star tracker update gap: 2.07 arcsec (random-walk integration, feeds Section 7).

## 6. Attitude control (reaction wheels + magnetorquers)

### 6.1 Reaction wheel control law

The quaternion-error PD law tau = -kp*theta_err - kd*omega_err is sized for the z axis from the control bandwidth 0.05 rad/s and damping ratio 0.8:

- kp (z): 0.0875 N m / rad
- kd (z): 2.800 N m s / rad
- Initial torque demand: 0.0153 N m (clipped at 0.01 N m: yes)
- Torque-limited phase: 6 s
- 1% settle time: 80 s

The peak wheel momentum demand during the slew is 0.129 N m s against a capacity of 0.2 N m s per wheel -> momentum margin 1.55x, saturation not flagged.

### 6.2 Momentum management (desaturation)

Environmental torques accumulate 0.058 N m s per orbit per axis. The wheels unload whenever momentum reaches the trigger level 0.14 N m s (70% of capacity), returning to a 0.02 N m s bias: one unload every 2.1 orbits.

Unload torque over a 600 s horizon is 2.00e-04 N m; with the local field of 2.5e-05 T the magnetorquer dipole demand is 8.0 A m^2 (torque-rod limit 20 A m^2, current 1.00 A at 200 turns x 0.1 m^2). Magnetorquer torque authority is 5.00e-04 N m -> desaturation margin 2.5x. Alignment warning: no (torque demand is perpendicular to the field in this example).

### 6.3 Detumble (B-dot) and coil sizing

At separation the worst-case tip-off rate is 0.5 deg/s. The B-dot law m = gain * (omega x B) demands 19.6 A m^2, within the 20 A m^2 rod limit (19.6 A m^2 used), producing 4.9e-04 N m and a damping time of 1067 s (within one orbit).

## 7. Pointing error budget

The 3-sigma requirement is 30.0 arcsec. Independent 1-sigma contributors combine by root-sum-square:

| Contributor (1-sigma) | arcsec | Variance share |
|---|---|---|
| Star tracker determination noise (1-sigma, per axis) | 2.00 | 19.5% |
| Gyro propagation over 1 s update gap (ARW) | 2.07 | 20.9% |
| Control deadband / limit cycle | 3.00 | 43.8% |
| Reaction wheel jitter | 1.50 | 11.0% |
| Thermal / mechanical distortion | 1.00 | 4.9% |

- RSS 1-sigma error: 4.53 arcsec
- RSS 3-sigma error: 13.59 arcsec
- Requirement met: yes (margin 2.21x)
- Dominant contributor: Control deadband / limit cycle (44% of variance)
- Budget remaining for a new contributor: 8.91 arcsec 1-sigma (26.74 arcsec 3-sigma)

## 8. Conclusions and open items

The ADCS as specified meets the 30.0 arcsec (3-sigma) pointing requirement with a 2.2x margin. The determination chain, control law, momentum management and detumble sizing are mutually consistent and the magnetorquer authority supports the unload cadence.

Open items before release: confirm the assumed disturbance torque with the environmental-disturbance-torque-budget analysis, confirm component specifications with the manufacturers, and verify the mass model.

---
*Generated by Aero Agent Roles adcs-engineer core (2026-09-06). DRAFT for human ADCS lead review. Not an approval document; carries no certification or flight-readiness authority.*
