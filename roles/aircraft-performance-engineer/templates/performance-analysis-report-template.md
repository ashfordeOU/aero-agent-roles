# Aircraft Performance Analysis Report

**Workbook:** AeroSkills reference fleet performance workbook
**Fleet analysed:** Reference fleet: A-1/A-2 airplanes, H-1/H-2/H-3/H-4 rotorcraft cases
**Certification basis:** FAR-25 (airplane cases) / FAR-29 (rotorcraft cases)
**Status:** draft-for-review

## 1. Scope and aircraft register

Multi-aircraft performance analysis of a reference fleet: two FAR-25 airplanes (a twin-engine transport for the engine-out balanced field length case and a turboprop transport for the propeller cruise range case) and four FAR-29 rotorcraft cases (the light helicopter with its 5.0 m main rotor for lead-lag clearance, hover in ground effect, axial descent flow states and banked turn performance; the medium helicopter takeoff case for main rotor sizing; the blade-level flap dynamics case; and the six-tonne class helicopter for the range and endurance fuel closure).

All case inputs are the real reference cases of the bound flight-mechanics/performance leaves; the role engine recomputes every quantity from the same formulas the leaf logic modules encode and cross-checks against them when AeroSkills is present (evidence/provenance.json).

| Case | Aircraft | Bound leaf | Computes |
|---|---|---|---|
| A-1 | twin-engine transport airplane | flight-mechanics/performance/balanced-field-length | engine-out balanced field length and V1 |
| A-2 | turboprop transport airplane | flight-mechanics/performance/propeller-range | propeller Breguet cruise range |
| H-1 | light helicopter (2200 kg, 5.0 m main rotor) | rotorcraft-lead-lag-dynamics, rotorcraft-hover-ground-effect, rotorcraft-axial-descent-flow-states, rotorcraft-turn-performance | lead-lag clearance, hover IGE, axial descent, banked turn |
| H-2 | medium helicopter (4500 kg takeoff) | rotorcraft-main-rotor-sizing | main rotor sizing |
| H-3 | medium helicopter (blade-level case) | rotorcraft-blade-flapping-dynamics | Lock number, coning, flap frequency |
| H-4 | six-tonne class helicopter | rotorcraft-range-endurance | hover endurance and cruise range/endurance closure |

Airplane cases sit in the FAR-25 transport performance context; rotorcraft cases in the FAR-29 rotorcraft context. Every number below is computed by the role engine from the case inputs; each section cites the bound AeroSkills leaf whose logic the engine cross-checks against when the library is present.

## 2. Airplane A-1: engine-out balanced field length and V1

Case inputs: all-engine thrust 150000 N across 2 engines, weight 600000 N, rolling friction 0.03, brake friction 0.45, lift-off speed 80 m/s, engine-out climb gradient 0.024, obstacle height 10.668 m (35 ft), reaction 1 s, rotation 1 s.

| Quantity | Value |
|---|---|
| OEI thrust T_OEI (n-1)/n | 75000 N |
| Ground acceleration, all engines | 2.15746 m/s2 |
| Ground acceleration, engine out | 0.931632 m/s2 |
| Braking deceleration | 4.41299 m/s2 |
| Air segment over the obstacle | 444.5 m |

**Balanced V1: 77.2815 m/s (0.966019 of V_LOF).**

**Balanced field length: 2138.1 m** (ASD(V1) = AGD(V1) = 2138.1 m, balance delta 4.547e-13 m).

Bracket check (unique crossing inside [0, V_LOF]): ASD(0) = 0 m vs AGD(0) = 3959.33 m; ASD(V_LOF) = 2288.36 m vs AGD(V_LOF) = 2007.72 m.

Bound leaf: flight-mechanics/performance/balanced-field-length (FAR-25.113-style engine-out field length; summary-not-copy).

## 3. Airplane A-2: turboprop cruise range (propeller Breguet)

Case inputs: propeller efficiency 0.8, PSFC 0.55 lb/(hp h), cruise L/D 12, cruise masses 11500 kg to 10000 kg.

| Quantity | Value |
|---|---|
| PSFC converted to SI | 9.293e-08 kg/(W s) |
| Mass ratio m0/m1 | 1.15 |
| **Cruise range** | **1.47224e+06 m = 1472.2 km** |

R = (eta_p / (c_p * g0)) * (L/D) * ln(m0 / m1), the propeller branch of the Breguet range family (no cruise-speed term; the efficiency enters the numerator and the PSFC the denominator).

Bound leaf: flight-mechanics/performance/propeller-range (FAR-25 cruise fuel-planning context; summary-not-copy).

## 4. Rotorcraft H-2: main rotor sizing

Case inputs: takeoff mass 4500 kg, main-rotor-disk-loading ceiling 350 Pa, ct-over-sigma hover design point 0.12, blade count 4, rotor tip speed 210 m/s.

| Quantity | Value |
|---|---|
| Weight-borne hover thrust | 44129.9 N |
| Disk area | 126.085 m2 |
| Disk radius | 6.33516 m |
| Achieved disk loading | 350 Pa (exactly the ceiling) |
| Hover thrust coefficient CT | 0.00647878 |
| Rotor solidity sigma | 0.0539898 |
| Blade area A_b | 6.80734 m2 |
| Blade chord c | 0.268633 m (R/c = 23.5829) |
| Rotor tip Mach | 0.617103 (subcritical at sea level) |

Closure identities: CT = 0.00647878 / (rho * Vtip^2) ceiling identity holds (CT/sigma = 0.12, solidity identity b*c*R/A = 0.0539898).

Bound leaf: flight-mechanics/performance/rotorcraft-main-rotor-sizing (FAR-29 context; sizing only, no power).

## 5. Rotorcraft H-3: main-rotor blade flap dynamics

Case inputs: uniform blade mass 50 kg, radius 6 m, chord 0.5 m, collective 0.17 rad, uniform inflow ratio 0.05, flap hinge offset 0.05, lift-curve slope 5.73 /rad, rho 1.225 kg/m3.

| Quantity | Value |
|---|---|
| Flap inertia I_beta (uniform) | 600 kg m2 |
| **Lock number gamma** | **7.58079** (published band 5-12) |
| Hover coning a0 | 0.0979185 rad = 5.61032 deg (typical 3-8 deg) |
| Flap frequency ratio nu | 1.03872 per rev (1.02-1.08 band) |

Bound leaf: flight-mechanics/performance/rotorcraft-blade-flapping-dynamics (FAR-29 context; Johnson/Leishman flap model, summary-only).

## 6. Rotorcraft H-1: lead-lag dynamics and ground-resonance clearance

Case inputs: lag-hinge offset 0.05 (fraction of radius), operating rotor speed 44 rad/s, airframe lateral frequency 5 Hz.

| Quantity | Value |
|---|---|
| Lag frequency ratio nu_zeta | 0.280976 per rev (0.2-0.4 band) |
| Collective lag mode | 1.96762 Hz |
| Regressing lag mode | 5.0352 Hz |
| Advancing lag mode | 8.97044 Hz |
| Coincidence rotor speed Omega* | 43.6924 rad/s |
| Clearance fraction | -0.00698993 |
| **Verdict** | **resonance-adjacent** |

Sensitivity: with a separated airframe lateral frequency of 3.5 Hz, Omega* = 30.5847 rad/s (clearance fraction -0.304893) and the verdict is **clear**.

Bound leaf: flight-mechanics/performance/rotorcraft-lead-lag-dynamics (FAR-29 context; Coleman-diagram coincidence, summary-only).

## 7. Rotorcraft H-1: hover in ground effect

Case inputs: mass 2200 kg, rotor radius 5 m, rotor height above ground 5 m (z/R = 1), solidity 0.08, Cd0 0.012, tip speed 220 m/s, induced power factor 1.15, available power 360000 W.

| Quantity | Value |
|---|---|
| Hover thrust (weight) | 21574.6 N |
| Ideal induced velocity v_h | 10.5887 m/s |
| Ideal induced power | 228448 W |
| Profile power (unchanged IGE) | 122935 W |
| **Ground-effect factor k_ige** | **0.9375** (Cheeseman factor at z/R = 1; 0.9375 at z/R = 1) |
| IGE induced power | 214170 W |
| **IGE total hover power** | **369230 W** |
| OGE total hover power | 385650 W |
| Power margin at 360000 W available | -9230.24 W |
| **Maximum hover height** | **4.00045 m** (IGE-limited) |

Bound leaf: flight-mechanics/performance/rotorcraft-hover-ground-effect (FAR-29 context; Cheeseman-style factor on induced power only, summary-only).

## 8. Rotorcraft H-1: axial descent flow states

Case inputs: mass 2200 kg (thrust 21574.6 N), rotor radius 5 m, profile power 122935 W, induced power factor 1.15, rotor speed 44 rad/s; vortex-ring band limits (0, 21.1775) m/s.

| Descent rate (m/s) | Flow state | v_i (m/s) | Power (W) | Torque at 44 rad/s (N m) |
|---|---|---|---|---|
| 0 | hover | n/a (momentum invalid) | n/a | n/a |
| 15 | vortex-ring-band | n/a (momentum invalid) | n/a | n/a |
| 25 | windmill-brake | 5.85704 | -352018 | -8000.4 |
| 30 | windmill-brake | 4.37555 | -512829 | -11655.2 |
| 40 | windmill-brake | 3.03301 | -794247 | -18051.1 |

Torque-reversal condition: c = P_profile / (k T) = 4.95489 m/s versus v_h = 10.5887 m/s -> c < v_h, verdict **momentum-unreachable**.

Bound leaf: flight-mechanics/performance/rotorcraft-axial-descent-flow-states (FAR-29 context; NASA TP-2005-213477 public-domain empirical-inflow context, summary-only).

## 9. Rotorcraft H-1: banked turn performance

Case inputs: mass 2200 kg (weight 21574.6 N), rotor radius 5 m (disk 78.5398 m2), solidity 0.08, Cd0 0.012, tip speed 220 m/s, flat-plate area 2.2 m2, induced power factor 1.15, speed 60 m/s, analysed load factor 2, available power 600000 W.

| Quantity | Value |
|---|---|
| Turn thrust (n x W) | 43149.3 N |
| Turning induced velocity | 3.73017 m/s |
| Induced power | 185097 W |
| Profile power | 122935 W |
| Parasite power | 291060 W |
| **Turn total power** | **599092 W** |
| Level-flight total at n = 1 | 460336 W |
| Bank angle at n = 2 | 60 deg |
| Turn rate / radius | 0.283094 rad/s / 211.944 m |
| **Sustained load factor** | **2.00491** (power-limited) |
| Sustained bank angle | 60.081 deg |
| Sustained turn rate / radius | 0.28402 rad/s / 211.253 m |

Power round trip: the total power at the sustained load factor equals the 600000 W available power (bisection root, fixed 120 iterations).

Sensitivity: with 450000 W available at 40 m/s the sustained load factor falls to 1.86867 (rate 0.387015 rad/s, radius 103.355 m): the parasite V^3 growth cuts the sustained load factor as the speed rises at fixed power.

Bound leaf: flight-mechanics/performance/rotorcraft-turn-performance (FAR-29 context; uniform-inflow momentum theory, summary-only).

## 10. Rotorcraft H-4: range and endurance fuel closure

Case inputs: takeoff weight 60000 N, fuel load 1500 kg, rotor radius 8 m, figure of merit 0.75, specific fuel consumption 1.000e-07 kg/(s W); weight at burnout W1 = 45290 N.

| Quantity | Value |
|---|---|
| Hover power at W0 | 882912 W |
| Fuel flow at W0 | 0.0882912 kg/s |
| **Hover endurance** | **20927 s = 5.81 h** |
| Best-range speed (max SR) | 80 m/s |
| Best-endurance speed (min P) | 60 m/s |
| Specific range at 60 m/s | 113.302 m/kg |
| **Cruise range at 80 m/s** | **2.43344e+06 m = 2433.44 km** |
| **Cruise endurance at 60 m/s** | **33798 s = 9.39 h** |

Cruise closure scales the reference power with the average weight (W_avg/W_ref)^1.5 over the fuel burn; the power-required curve inputs are: (40 m/s, 620000 W), (50 m/s, 560000 W), (60 m/s, 540000 W), (70 m/s, 555000 W), (80 m/s, 600000 W).

Bound leaf: flight-mechanics/performance/rotorcraft-range-endurance (FAR-29 context; weight-decay integration, summary-only).

---
*Generated by Aero Agent Roles aircraft-performance-engineer core (2026-09-06). DRAFT for human flight-mechanics review. Not an approval document, not a certification finding, and no regulatory sign-off.*