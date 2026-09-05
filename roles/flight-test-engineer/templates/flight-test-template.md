# Flight Test Plan and Envelope Expansion Report

**Aircraft:** FT-1 Worked-Example Light Jet
**Basis:** FAR/CS-25 context (worked example)
**Status:** draft-for-review

_Flight data below are SIMULATED for the worked example and must be replaced by recorded flight data._

## 1. Objectives and configuration

- Determine VS1g and the V-speed set (vref/v2/vr/VA) with warning-margin evidence in every configuration
- Demonstrate freedom from flutter to V_D with damping >= 0.03 at the maximum test speed and an extrapolated margin >= 1.2*V_D
- Expand the speed and load factor envelope in build-up blocks to V_D / n_max with a load factor check at every point
- Verify stall recovery characteristics within the program limits
- Measure climb performance and check the gradient requirement

- Limit load factor: n_max = 2.5 g positive. Stall speeds (EAS): VS1g = 44.0 m/s (86 kt), VS1 = 40.0 m/s (78 kt), VS0 = 36.0 m/s (70 kt).
- Placards (EAS): VFE = 62.0 m/s, VNO = 85.0 m/s, VNE = 94.0 m/s, V_D = 106.0 m/s, MMO = 0.78.
- Derived: VA = 69.6 m/s (135 kt), vref = 46.8 m/s (91 kt), v2 = 48.0 m/s (93 kt), vr = 44.0 m/s (86 kt).
- Crew: test pilot + flight test engineer console; airspace: restricted area; instrumentation: calibrated pitot-static, accelerometers, strain gauges on wing/elevator, flutter excitation vanes, telemetry with real-time damping.

## 2. Safety

| Hazard | Sev | Lik | Risk | High (>=15) | Mitigation |
|---|---|---|---|---|---|
| Flutter onset at high speed | 5 | 2 | 10 | no | GVT + build-up blocks, damping gate 0.03, excitation vanes, real-time monitoring |
| Stall departure at aft CG | 4 | 3 | 12 | no | entry technique, altitude floor, recovery demonstration, spin chute installed |
| Overspeed control upset | 4 | 2 | 8 | no | abort criteria at every block, test pilot briefing, VMO/VNE marking |
| Engine failure during climb segment | 3 | 2 | 6 | no | single-engine drills, field/landing options, engine instruments monitored |
| Telemetry data loss | 2 | 3 | 6 | no | onboard recording backup, link checked pre-flight |

Every high-risk item is mitigated before the flight: true.

| Go/no-go criterion | Value |
|---|---|
| weather | GO |
| aircraft_ready | GO |
| instrumentation_ok | GO |
| safety_review_ok | GO |
| airspace_ok | GO |

Flight release: GO.

## 3. Build-up plan

Build-up order: GVT -> flutter build-up (blocks S1..S4) -> stall matrix -> load factor envelope -> climb performance. Each block clears before the next is flown; every block states its limit, abort criteria, and PASS/FAIL criteria.

### 3.1 Flutter build-up (speed blocks as fractions of V_D)

| Block | V_D fraction | Target (EAS) | Category | Abort | PASS/FAIL criteria |
|---|---|---|---|---|---|
| S1 | 0.85 | 90.1 m/s (175 kt) | vno-to-vne | immediate pull-up + throttle reduction if buffet, LCO, or control anomaly | PASS: damping >= 0.03 at point, no LCO, load factor within 2.5 g; FAIL otherwise |
| S2 | 0.90 | 95.4 m/s (185 kt) | at-or-above-vne | immediate pull-up + throttle reduction if buffet, LCO, or control anomaly | PASS: damping >= 0.03 at point, no LCO, load factor within 2.5 g; FAIL otherwise |
| S3 | 0.95 | 100.7 m/s (196 kt) | at-or-above-vne | immediate pull-up + throttle reduction if buffet, LCO, or control anomaly | PASS: damping >= 0.03 at point, no LCO, load factor within 2.5 g; FAIL otherwise |
| S4 | 1.00 | 106.0 m/s (206 kt) | at-or-above-vne | immediate pull-up + throttle reduction if buffet, LCO, or control anomaly | PASS: damping >= 0.03 at point, no LCO, load factor within 2.5 g; FAIL otherwise |

Required flutter demonstration speed: V_F = 127.2 m/s (1.2 x V_D). Damping >= 0.03 required at the maximum test speed; structural mode frequency separation >= 0.10 at every point.

### 3.2 Altitude / Mach grid (V_D tested per altitude, ISA)

| Altitude | Density ratio | Speed of sound | TAS at V_D | Mach at V_D | MMO | Limit |
|---|---|---|---|---|---|---|
| 0 ft | 1.000 | 340.3 m/s | 106.0 m/s | 0.311 | 0.78 | eas-limited |
| 25000 ft | 0.448 | 309.7 m/s | 158.3 m/s | 0.511 | 0.78 | eas-limited |
| 35000 ft | 0.310 | 296.5 m/s | 190.4 m/s | 0.642 | 0.78 | eas-limited |

### 3.3 Stall matrix (VS1g and warning onset per configuration)

| Config | Measured VS1g (EAS) | Warning required | Warning onset | Recovery limits |
|---|---|---|---|---|
| clean | 44.1 m/s | 46.3 m/s | 46.8 m/s | alt <= 30 m, pitch <= 8 deg, roll <= 20 deg |
| takeoff (flaps) | 40.4 m/s | 42.4 m/s | 42.5 m/s | alt <= 30 m, pitch <= 8 deg, roll <= 20 deg |
| landing (flaps/gear) | 36.3 m/s | 38.1 m/s | 38.2 m/s | alt <= 30 m, pitch <= 8 deg, roll <= 20 deg |

### 3.4 Load factor envelope (pull blocks at VA or above)

| Block | n_max fraction | Target n | PASS/FAIL |
|---|---|---|---|
| L1 | 0.50 | 1.25 g | PASS if n <= 2.5 g at point, with no buffet/LCO |
| L2 | 0.75 | 1.88 g | PASS if n <= 2.5 g at point, with no buffet/LCO |
| L3 | 1.00 | 2.50 g | PASS if n <= 2.5 g at point, with no buffet/LCO |

### 3.5 Climb performance

Sawtooth climb segments at constant indicated airspeed; gradient check against 2.4 % (two-engine context).

## 4. Results

### 4.1 Flutter build-up points

| Block | Speed (EAS) | Damping | Min damping | Verdict |
|---|---|---|---|---|
| S1 | 90.1 m/s | 0.120 | 0.030 | PASS |
| S2 | 95.4 m/s | 0.115 | 0.030 | PASS |
| S3 | 100.7 m/s | 0.108 | 0.030 | PASS |
| S4 | 106.0 m/s | 0.100 | 0.030 | PASS |

Extrapolated flutter speed from the damping trend: 185.7 m/s; margin ratio 1.75 vs required 1.2 -> PASS.

Structural mode frequency separation (GVT pairs):
- mode pair 4.2 Hz / 11.6 Hz: separation 0.94 >= 0.10 -> PASS
- mode pair 9.1 Hz / 14.8 Hz: separation 0.48 >= 0.10 -> PASS
- mode pair 11.6 Hz / 14.8 Hz: separation 0.24 >= 0.10 -> PASS
- mode pair 4.2 Hz / 9.1 Hz: separation 0.74 >= 0.10 -> PASS

### 4.2 Stall results

| Config | VS1g (EAS) | Warning onset | Warning margin | Recovery | Verdict |
|---|---|---|---|---|---|
| clean | 44.1 m/s | 46.8 m/s | +2.70 m/s | alt 18 m / pitch 3 deg / roll 6 deg | PASS |
| takeoff (flaps) | 40.4 m/s | 42.5 m/s | +2.10 m/s | alt 21 m / pitch 4 deg / roll 8 deg | PASS |
| landing (flaps/gear) | 36.3 m/s | 38.2 m/s | +1.90 m/s | alt 24 m / pitch 5 deg / roll 9 deg | PASS |

### 4.3 Load factor envelope results

| Block | Target n | Achieved n | Limit | Verdict |
|---|---|---|---|---|
| L1 | 1.25 g | 1.26 g | 2.5 g | PASS |
| L2 | 1.88 g | 1.88 g | 2.5 g | PASS |
| L3 | 2.50 g | 2.48 g | 2.5 g | PASS |

### 4.4 Climb performance results

- Rate of climb: 1450 ft/min (segment reduction, corrected to reference weight).
- Gradient: 2.70 % vs 2.4 % required -> margin +0.30 % (PASS).

## 5. Findings, limit changes, and recommendations

| Envelope limit change | Traced to data point | Verdict |
|---|---|---|
| Speed envelope to 0.85 V_D | S1 | PASS |
| Speed envelope to 0.90 V_D | S2 | PASS |
| Speed envelope to 0.95 V_D | S3 | PASS |
| Speed envelope to 1.00 V_D | S4 | PASS |

Recommendations: (1) expand to the top block only after the damping and separation verdicts above; (2) repeat the configuration whose stall warning onset is marginal before envelope use; (3) confirm flutter clearance per point with the flight test conductor.

## 6. Sign-off

This plan/report states that the recorded data support expanding to the listed limits PENDING human flight test conductor review. It is a draft deliverable, not a clearance.

---
*Generated by Aero Agent Roles flight-test-engineer core (2026-09-05). DRAFT for human flight test conductor review. Not a clearance and not an approval of the envelope or of flight.*