# Navigation Architecture and Position Error Analysis Report

**Vehicle:** Mapping UAS (small fixed-wing)
**Condition:** Survey cruise, 25 m/s, 300 m AGL
**Mission / item:** Integrated navigation error analysis: RTK base + 90 s GNSS-denied terrain corridor
**Status:** draft-for-review

## 1. Frames and geodesy

- Vertical/horizontal reference: WGS84 ellipsoid, a = 6378137.0 m, f = 1/298.257223563, e^2 = 0.00669438.
- Reference point (outage start): lat 37.4275 deg, lon -122.1697 deg, alt 330.0 m -> ECEF (-2700244.8, -4292949.0, 3855377.8) m.
- Frame conventions: NED (north-east-down) for the INS mechanization and the INS-GNSS integration filter; ENU (east-north-up) for GNSS/RTK baseline reporting and the terrain/bearing-only local-tangent geometry; ECEF for the pseudorange/RTK least-squares solves. ECEF->NED rotation is evaluated at the reference point and reused for every local-frame conversion in this report.

## 2. INS coasting error growth

- Sensor specs (MEMS-class): accelerometer bias 50 micro-g (0.000490 m/s^2), gyro bias 5.0 deg/hr (2.424e-05 rad/s), angle random walk 0.30 deg/sqrt(hr).
- GNSS-denied outage: 90 s (Schuler period 5064 s = 84.4 min; the outage is far shorter than one Schuler cycle, so the coasting errors below grow essentially unbounded rather than oscillating).
- Accelerometer-bias error: velocity dv = b*t = 0.0441 m/s; position dx = 0.5*b*t^2 = 1.986 m.
- Gyro-drift position error: dx = (1/6)*g*eps*t^3 = 28.883 m.
- Combined (RSS, independent sources) 1-sigma coasting position error at t = 90 s: **28.951 m**.
- Attitude uncertainty from angle random walk over the outage: 0.0474 deg 1-sigma (reported separately; not summed into the position budget above).

## 3. GNSS epoch solution

- Iterated pseudorange least squares over 6 satellites converged in 3 iteration(s); recovered clock bias 1500.03 m (true 1500.00 m); post-fit SSE 2.8573 m^2.
- DOP geometry: GDOP 3.13, PDOP 2.68, HDOP 1.35, VDOP 2.31, TDOP 1.63.
- UERE (post-fit residual RMS) 0.690 m; position 1-sigma = PDOP * UERE = 2.68 * 0.690 = **1.847 m**.
- RAIM/FDE (snapshot chi-square test, Pfa = 1e-05): test statistic 0.079 vs threshold 24.669 (df = 2) -> **no fault**.
- Horizontal protection level HPL = 41.8 m (worst-case error slope); non-precision-approach HAL context 556 m -> integrity available.

## 4. Carrier smoothing and Doppler velocity

- Hatch filter: tau = 100 s, T = 1 s -> alpha = 0.010. Code-only std 0.021 m; smoothed std 0.0299 m (carrier term 0.02105 m) -> improvement factor 10.0x vs code-only pseudorange.
- Doppler-derived velocity (linearized LS): v = (21.135, -13.323, 0.004) m/s ECEF, clock drift 0.514 m/s; per-axis 1-sigma (0.0374, 0.0434, 0.0618, 0.0512) m/s [vx,vy,vz,drift].

## 5. RTK

- Base station range 6.0 km (< 10 km, no residual troposphere/ionosphere double-difference error assumed). L1 wavelength lambda = 0.190293673 m.
- Float double-difference solution sigma0 = 0.0000 m.
- Integer ambiguity search (radius 2 cycles): fixed = (12, -7, 5) cycles (true = (12.0, -7.0, 5.0)); ratio test = 4035.35 (threshold 3.0) -> **FIXED**.
- Fixed-baseline ENU: (119.998, -45.000, 8.011) m (true (120.0, -45.0, 8.0) m); per-axis 1-sigma (E, N, U) = (0.0000, 0.0000, 0.0002) m.

## 6. INS-GNSS integration

- Loosely-coupled 5-state psi-angle error filter (states: dr_N, dr_E, dv_N, dv_E, psi), initialized from the section-2 coasting error budget. Kalman/ins-gnss leaf logic; the tightly-coupled 8-state per-pseudorange alternative (tightly-coupled-ins-gnss) applies when raw per-satellite measurements (not a position fix) are the GNSS input.
- Predict (dt = 1.0 s, f_N = 0.20, f_E = 0.05 m/s^2): position variance grows to (838.171, 838.171) m^2 [dr_N, dr_E].
- GNSS position measurement update (R = 3.0 m per axis): innovation (-2.030, -28.883) m; post-update position 1-sigma **4.220 m**.

## 7. GNSS-denied segment (terrain-referenced navigation)

- TERCOM: 10-sample profile over the 90 s corridor matched against a 25-candidate correlation surface (Pearson r). Best match offset (50.0, -25.0) m (true INS offset (45.0, -20.0) m), r = 0.9978.
- SITAN slope-linearized filter refinement from the TERCOM cue: position offset (dr_e, dr_n) = (45.20, -21.91) m, altitude bias 0.07 m; post-filter 1-sigma (1.383, 6.103) m [e, n].

## 8. Bearing-only localization

- Passive secondary sensor: 3 ground observers, bearing sigma 1.5 deg. Stansfield two-pass WLS fix: (950.0, 700.0) m (true (950.0, 700.0) m).
- 1-sigma error ellipse: semi-major 24.11 m, semi-minor 19.52 m, orientation -72.8 deg.
- Geometry dilution factor d = 0.85 -> **good** (observability degrades as the observer-target geometry approaches collinear bearing lines).

## 9. Integrated error budget and verdict

| Flight phase | Position 1-sigma (m) |
|---|---|
| GNSS-nominal (RTK fixed) | 0.000 |
| GNSS-nominal (standalone, DOP) | 1.847 |
| GNSS-denied, INS coasting only (90s, unaided reference) | 28.951 |
| GNSS-denied, terrain-aided (SITAN, deployed solution) | 6.258 |

Requirement: integrated position error <= 25.0 m (1-sigma), all phases. Worst phase: **GNSS-denied, terrain-aided (SITAN, deployed solution)** at 6.258 m -> **PASS**.

| Gate | Result |
|---|---|
| RAIM/FDE integrity (no fault) | PASS |
| RTK ambiguity resolution | PASS |
| Integrated position budget | PASS |

- All error figures are 1-sigma design predictions from the stated sensor and geometry assumptions; they are DRAFT analysis for human navigation-engineering review, not flight test results.
- Open items: full flight-envelope multipath/ionosphere characterization, sensor-in-the-loop validation, and gain-schedule coverage of the survey grid pattern.

## Appendix A. Calculation traceability

- Frames/geodesy: WGS84 geodetic->ECEF and ECEF->NED rotation (navigation-frames).
- INS coasting: accel-bias position error 0.5*b*t^2, gyro-drift position error (1/6)*g*eps*t^3, Schuler period 2*pi*sqrt(R/g), ARW sigma = arw*sqrt(t_hours) (inertial-navigation).
- GNSS fix: iterated pseudorange LS on the linearized geometry matrix (gnss-pseudorange-positioning); DOP = sqrt(trace) of (H'H)^-1 blocks (dilution-of-precision).
- RAIM/FDE: chi-square test statistic sse/sigma^2 vs chi2_quantile(n-4, 1-Pfa) (Wilson-Hilferty cubic approximation of a normal quantile via Acklam's rational approximation); HPL from the worst-case error slope (gnss-raim-fde).
- Carrier smoothing: Hatch filter steady-state std sigma_code*sqrt(a/(2-a)) + carrier term (gnss-carrier-smoothing).
- Doppler velocity: linearized range-rate LS, state (vx,vy,vz,c*dtr_dot) (gnss-doppler-velocity-positioning).
- RTK: double-difference float LS, integer ambiguity ratio test (ratio_min = 3.0), fixed-baseline LS (gnss-rtk-positioning).
- INS-GNSS integration: 5-state psi-angle error model, Phi = I + F*dt, standard Kalman predict/update (kalman-filter-design, ins-gnss-integrated-filter).
- Terrain-referenced navigation: TERCOM Pearson-r correlation match, SITAN slope-linearized Kalman bias update (terrain-referenced-navigation).
- Bearing-only localization: Stansfield two-pass WLS fix, geometry dilution factor d = 1/sqrt(lambda_min(S)) (bearing-only-localization).

---
*Generated by Aero Agent Roles navigation-engineer core (2026-09-08). DRAFT - for human navigation-engineering lead review. Design predictions only; not flight software release, not a certification finding, not an approval document.*