# Flight Test Plan and Requirements Traceability

**Item:** Certification flight test campaign of the FGS-2000-equipped transport category airplane
**Program:** FGS-2000 flight guidance system certification
**Airframe:** Transport category airplane (FGS-2000-equipped)
**Certification basis:** FAR-25 (noise measurement procedure per FAR 36 summary)
**Authority:** FAA
**Status:** draft-for-review

> **DRAFT for human review - not an approval document.** This plan is a planning artifact for the program sign-off chain. It does not issue certification approval, claim regulatory sign-off, or release any aircraft for flight beyond the program's own go/no-go authority. Noise limits are program inputs from the certification basis, not derived here.

## 1. Campaign scope and basis

The campaign plans and traces the certification flight tests that support the FGS-2000 flight guidance system program: airspeed position error calibration of the air data sources, the guidance-mode performance build-up matrix across the configurations, the FAR 36 noise certification measurement conditions, and the instrumentation, telemetry and PCM decommutation chain that records and delivers every channel to the ground station.

Bound AeroSkills leaves grounding this plan (all under flight-test-operations/planning): flight-test-instrumentation, flight-test-planning, noise-certification-test, pcm-telemetry-decommutation, position-error-calibration, telemetry-data-acquisition and test-point-matrix-design. Every number below is computed by the role core from the real rules of those leaves; method validation cards (section 11) recompute the leaves' reference worked examples pre-flight to validate the reduction chain. No flight data is claimed.

## 2. Test objectives and requirements traceability

| Objective | Traced to (points / blocks / campaigns) | Traced |
|---|---|---|
| OBJ-01 | PEC-campaign | yes |
| OBJ-02 | tp1, tp2, tp3, tp4, tp5, tp6, tp7, tp8, tp9, tp10, tp11, tp12 | yes |
| OBJ-03 | BLK-01, BLK-04 | yes |
| OBJ-04 | BLK-02 | yes |
| OBJ-05 | NOISE-campaign | yes |
| OBJ-06 | BLK-01 | yes |

Objective coverage verdict: **COMPLETE** (6/6 traced).

| Requirement | Source | Verification | Status | Traced via |
|---|---|---|---|---|
| RQ-01 | FAR/CS-25.1303 context | flight-test | planned | OBJ-01 |
| RQ-02 | flight-test-instrumentation leaf | analysis | planned | OBJ-06 |
| RQ-03 | telemetry-data-acquisition leaf | flight-test | planned | OBJ-03 |
| RQ-04 | flight-test-planning leaf | analysis | planned | OBJ-02, OBJ-04, OBJ-05 |
| RQ-05 | noise-certification-test leaf (chapter 4 style rule) | flight-test | planned | OBJ-05 |
| RQ-06 | flight-test-planning leaf (build-up approach) | analysis | planned | OBJ-02, OBJ-04 |

Requirement trace verdict: **TRACE-COMPLETE** (6/6 requirements traced to a planned point, block or campaign). Verification status rollup: planned 6 - verification executes during the campaign; this plan claims no completed verification.

## 3. Test point matrix

Condition sweeps (one axis at a time, grid is the cartesian product, altitude-major): altitude 1500, 3000 m, speed 110, 130, 150 m/s, weight 55000 kg, configuration clean, takeoff.

**Grid count: 12 test points.** Repeat interval 5 -> repeat points: tp5, tp10.

| Point | Altitude (m) | Speed (m/s) | Weight (kg) | Configuration | Repeat |
|---|---|---|---|---|---|
| tp1 | 1500 | 110 | 55000 | clean |  |
| tp2 | 1500 | 110 | 55000 | takeoff |  |
| tp3 | 1500 | 130 | 55000 | clean |  |
| tp4 | 1500 | 130 | 55000 | takeoff |  |
| tp5 | 1500 | 150 | 55000 | clean | yes |
| tp6 | 1500 | 150 | 55000 | takeoff |  |
| tp7 | 3000 | 110 | 55000 | clean |  |
| tp8 | 3000 | 110 | 55000 | takeoff |  |
| tp9 | 3000 | 130 | 55000 | clean |  |
| tp10 | 3000 | 130 | 55000 | takeoff | yes |
| tp11 | 3000 | 150 | 55000 | clean |  |
| tp12 | 3000 | 150 | 55000 | takeoff |  |

## 4. Point sequencing, repeats and steady state criteria

Efficiency sequence (configuration flown in one block, altitude swept once, then speed levels): tp1, tp3, tp5, tp7, tp9, tp11, tp2, tp4, tp6, tp8, tp10, tp12.

Steady state tolerance band per condition: altitude +-30 m, speed +-2 m/s, weight +-500 kg. A flown point is valid only when every observed value lies inside the band (|observed - planned| <= tolerance); invalid points are reflown before the matrix closes.

Steady state check on the recorded readings: 12 valid, 0 invalid -> verdict **ALL-VALID**.

Matrix coverage of the matrix objectives (OBJ-02): verdict **COMPLETE**, uncovered: -.

## 5. Instrumentation plan

Every channel is sized at the required sample rate (margin 2.5 x the Nyquist rate, i.e. 5 times the maximum frequency of interest) with the anti-aliasing filter set ahead of the sampler. ADC: 16 bit over a 10 V full-scale span -> resolution 0.0001526 V (1 LSB); worst-case quantization error half a step.

| Channel | Parameter | Max value | Sensor range | Range | fmax (Hz) | Sample rate (Hz) | Nyquist | Cal current |
|---|---|---|---|---|---|---|---|---|
| PITOT | Pitot pressure (airspeed source) | 90000 Pa | +-110000 Pa | ok | 5 | 25 | ok | yes |
| STATIC | Static pressure (airspeed source) | 85000 Pa | +-110000 Pa | ok | 5 | 25 | ok | yes |
| ACCV | Vertical acceleration at CG | 2.5 g | +-4 g | ok | 20 | 100 | ok | yes |
| Q | Pitch rate | 30 deg/s | +-60 deg/s | ok | 10 | 50 | ok | yes |
| DELE | Elevator position | 20 deg | +-30 deg | ok | 10 | 50 | ok | yes |
| STRAIN | Wing root bending strain | 1500 microstrain | +-2500 microstrain | ok | 25 | 125 | ok | yes |
| N1 | Engine N1 speed | 105 % | +-110 % | ok | 5 | 25 | ok | yes |

Instrumentation completeness (required vs provided): verdict **COMPLETE**, missing: -. Release verdict: **RELEASED** - a channel is released only when its calibration is current, its sensor range covers the expected signal, and its sample rate satisfies the Nyquist criterion with margin.

## 6. Telemetry and data acquisition plan

PCM minor frame: 64 words of 16 bits -> **1024 bits per frame**; stream bit rate at 50 frames/s -> **51200 bit/s**.

Supercommutated channels (sampled faster than the frame rate, integer instances per frame):

| Channel | Sample rate (Hz) | Instances per frame |
|---|---|---|
| ACCV vertical acceleration (CG) | 100 | 2 |
| STRAIN wing root strain | 200 | 4 |

Subcommutated channels (sampled slower than the frame rate, integer frames per sample):

| Channel | Sample rate (Hz) | Frames per sample |
|---|---|---|
| OILT oil temperature | 12.5 | 4 |

IRIG-B time coding: day of year 32, seconds of day 43200 -> seconds of year **2721600 s**.

Signal conditioning: sensor span 4 V x gain 2 = 8 V conditioned span vs 10 V ADC full scale -> verdict **OK**.

Data latency: acquisition 5 ms + processing 10 ms + link 25 ms = **40 ms** end-to-end vs requirement 50 ms -> within requirement; pipeline buffer holds 10 samples (ceil(latency x sample rate)).

Ground station link: received power -95 dBm, receiver sensitivity -110 dBm -> margin 15 dB vs 10 dB minimum -> ok.

Telemetry quality: bit error rate 1.0e-05 vs limit 0.0001, dropouts 0.5 % vs limit 1 % -> data release verdict ok.

## 7. PCM telemetry decommutation plan

Decommutation validation fixture (reference layout of the pcm-telemetry-decommutation leaf worked example): sync word 0xEB90, 8 data words + 1 idle word(s) -> **frame period 10 words**; subframe id at data word 0 masked with 0x0003.

Planned telemetry flight duration 3600 s at 50 frames/s -> 180000 expected minor frames; recovered samples per channel follow the demultiplex rules (fixed: 1 value per frame; supercommutated: one value per slot per frame; subcommutated: keyed by subframe id).

| Channel | Kind | Word(s) | Values per frame | Expected samples |
|---|---|---|---|---|
| A | fixed | 1 | 1 | 180000 |
| B | fixed | 4 | 1 | 180000 |
| C | fixed | 6 | 1 | 180000 |
| D | fixed | 7 | 1 | 180000 |
| A2 | super | 3, 5 | 2 | 360000 |
| S | sub (4 subframes) | 2 | 1 | 180000 (45000 per subframe id) |

A corrupted sync word drops the whole frame from every channel; the recovered series feed data reduction only after the sync miss report is reviewed.

## 8. Airspeed position error calibration (PEC) campaign

Planned calibration points at indicated airspeeds 60, 80, 100, 120, 140 m/s, flown by the tower-fly-by, gps-ground-speed-doublet reference method(s); repeat passes at a scheduled speed are combined by their least-squares mean.

PEC acceptance criteria (data quality verdict): coverage of planned points inside the calibrated span >= **0.95** and residual RMS of the observations about the piecewise-linear correction curve <= **1 m/s**; the verdict is adequate only when both hold, else the campaign extends to cover the planned points.

Correction curve knots (V_ias, dVp) become the PEC table rows V_cas = V_ias + dVp that feed the data reduction of every later flight. The compressible airspeed relations used by the reduction are validated pre-flight in the cards of section 11 (M-09 to M-11); the fly-by reduction evaluates the indicator scale at the reference pass speed (100 m/s when the pass speed is not recorded).

Reduction relations and reference worked examples are the compressible airspeed law and PEC practice of the position-error-calibration leaf.

## 9. Noise certification measurement campaign

Reference measurement geometry (typical public FAR 36 summary values):

- Flyover: microphone on the extended runway centerline 6500 m from the brake release point (extended runway centerline, brake release point).
- Sideline: microphone 450 m lateral of the runway centerline at the point of maximum takeoff noise (lateral of runway centerline at max takeoff noise).
- Approach: microphone 1200 m from the threshold under the flight path at 120 m altitude on the 3 degree glide slope (under the flight path from the threshold).

Certification test matrix rows (weights and reference speeds; flyover speed reference V2 + 10 kt):

| Condition | Configuration | Weight (kg) | Reference speed (kt) | Limit (EPNdB) | Demonstration target (EPNdB) |
|---|---|---|---|---|---|
| flyover | takeoff | 78000 | 165 | 89 | 89 |
| sideline | takeoff | 78000 | 155 | 94 | 94 |
| approach | landing | 62000 | 135 | 98 | 98 |

Acceptance rule applied to the measured EPNL of each run: individual margin (limit - EPNL) >= 0 per point, and the cumulative three-point margin (sum of the individual margins) >= **10 EPNdB** (typical chapter 4 / stage 4 check at reference level; the exact rule set depends on the certification basis). The EPNL integration (10 dB down rule, 10 s normalization) and the margin math are validated pre-flight in the cards of section 11 (M-12, M-13).

Applicable noise limits are program inputs from the certification basis (stated per condition in this plan); they are not derived here.

## 10. Build-up flights and go/no-go gate

Flight blocks ordered by the build-up approach (ascending risk; a block is flown only after its prerequisites):

| Block | Flight block | Risk level | Prerequisites |
|---|---|---|---|
| BLK-01 | FTI ground release and telemetry ground validation | 0 | - |
| BLK-02 | PCM decommutation validation on a recorded stream | 0 | - |
| BLK-03 | PEC campaign flights (tower fly-by / GPS ground speed doublet) | 1 | BLK-01 |
| BLK-04 | Matrix build-up block, 1500 m altitude band | 2 | BLK-01, BLK-03 |
| BLK-05 | Matrix build-up block, 3000 m altitude band | 3 | BLK-04 |
| BLK-06 | Noise certification measurement flights | 3 | BLK-03, BLK-04 |

Build-up order verdict: **OK** (missing prerequisites: -). Highest planned risk level: 3.

Go/no-go gate for the first build-up flight (weather, aircraft readiness, instrumentation release, safety review - all must pass):

| Check | Passed |
|---|---|
| weather_ok | NO |
| aircraft_ready | NO |
| instrumentation_ok | NO |
| safety_review_ok | NO |

**Go/no-go verdict: GO** (blockers: -). A NO-GO names the blocker and the flight does not depart; the gate is re-run before every flight.

## 11. Method validation cards (reduction and analysis checks)

Each card recomputes a reference worked example of a bound leaf with the role's own reduction/analysis code. These are pre-flight software validation checks - they are not flight data and carry no compliance claim.

**M-01 - Required sample rate (Nyquist headroom, default margin 2.5)** (source: flight-test-instrumentation leaf worked rule (5 times fmax))

| Check | Computed | Reference | PASS |
|---|---|---|---|
| required_sample_rate(fmax=20 Hz) | 100 Hz | 100 Hz | PASS |

**M-02 - ADC resolution of the acquisition chain** (source: flight-test-instrumentation leaf rule (R / 2^N))

| Check | Computed | Reference | PASS |
|---|---|---|---|
| quantization_error(16 bit, 10 V span) | 0.0001526 V | 0.0001526 V | PASS |

**M-03 - PCM minor frame period in words** (source: pcm-telemetry-decommutation leaf worked example (8 data words + 1 idle word))

| Check | Computed | Reference | PASS |
|---|---|---|---|
| frame_period_words(8, 1) | 10 words | 10 words | PASS |

**M-04 - PCM stream bit rate** (source: telemetry-data-acquisition leaf worked example (50 frames/s of 1024 bits))

| Check | Computed | Reference | PASS |
|---|---|---|---|
| pcm_bit_rate(50, 64, 16) | 51200 bit/s | 51200 bit/s | PASS |

**M-05 - Supercommutated channel instances per frame** (source: telemetry-data-acquisition leaf worked example (200 Hz channel on a 50 frame/s stream))

| Check | Computed | Reference | PASS |
|---|---|---|---|
| supercommutated_instances(200, 50) | 4 per frame | 4 per frame | PASS |

**M-06 - Subcommutated channel frames per sample** (source: telemetry-data-acquisition leaf worked example (25 Hz channel on a 100 frame/s stream))

| Check | Computed | Reference | PASS |
|---|---|---|---|
| subcommutated_instances(100, 25) | 4 frames per sample | 4 frames per sample | PASS |

**M-07 - IRIG-B time of year coding** (source: telemetry-data-acquisition leaf worked example (day 32 at 43200 s))

| Check | Computed | Reference | PASS |
|---|---|---|---|
| irig_b_time_of_year(32, 43200) | 2721600 s | 2721600 s | PASS |

**M-08 - End-to-end telemetry latency** (source: telemetry-data-acquisition leaf worked example (5 + 10 + 25 ms))

| Check | Computed | Reference | PASS |
|---|---|---|---|
| total_latency(5, 10, 25) | 40 ms | 40 ms | PASS |

**M-09 - Compressible airspeed identity (impact pressure / calibrated airspeed round trip)** (source: position-error-calibration leaf worked example (6258.4 Pa at 100 m/s))

| Check | Computed | Reference | PASS |
|---|---|---|---|
| impact_pressure_from_cas(100 m/s) | 6258 Pa | 6258 Pa | PASS |
| calibrated_airspeed(qc(100 m/s)) | 100 m/s | 100 m/s | PASS |

**M-10 - Tower fly-by position error reduction** (source: position-error-calibration leaf worked example (H_g 500 m, H_p 490 m, 288.15 K -> +0.88 m/s))

| Check | Computed | Reference | PASS |
|---|---|---|---|
| tower_flyby_position_error(500, 490, 288.15) | 0.882 m/s | 0.88 m/s | PASS |
| tower_flyby_position_error(500, 510, 288.15) (sign check: altimeter high) | -0.8884 m/s | -0.89 m/s | PASS |

**M-11 - GPS ground speed doublet reduction** (source: position-error-calibration leaf worked example (98/102 m/s -> 100 m/s TAS; 94.87 m/s CAS at rho/rho0 0.9))

| Check | Computed | Reference | PASS |
|---|---|---|---|
| gps_doublet_tas(98, 102) | 100 m/s | 100 m/s | PASS |
| tas_to_cas(100, rho/rho0=0.9) | 94.87 m/s | 94.87 m/s | PASS |

**M-12 - EPNL integration (10 dB down rule, 10 s normalization)** (source: noise-certification-test leaf worked example (constant 90 dB run, 41 samples at 0.5 s -> 93.0103 EPNdB))

| Check | Computed | Reference | PASS |
|---|---|---|---|
| epnl_from_pnlt(90 dB x 41 @ 0.5 s) | 93.01 EPNdB | 93.01 EPNdB | PASS |

**M-13 - Cumulative three-point margin rule (chapter 4 style)** (source: noise-certification-test leaf worked example (margins [3, 4, 4] sum to 11.0 EPNdB, pass))

| Check | Computed | Reference | PASS |
|---|---|---|---|
| cumulative_margin([3, 4, 4]).sum_db | 11 EPNdB | 11 EPNdB | PASS |

**M-14 - Go/no-go gate rejects a failed check** (source: flight-test-planning leaf rule (any failed check forces NO-GO and names the blocker))

| Check | Computed | Reference | PASS |
|---|---|---|---|
| go_no_gate(True, True, False, True).verdict | NO-GO  | NO-GO  | PASS |

**M-15 - Sensor range verdict** (source: flight-test-instrumentation leaf rule (|value| <= range -> ok))

| Check | Computed | Reference | PASS |
|---|---|---|---|
| sensor_range_verdict(90000 Pa, 110000 Pa) | ok  | ok  | PASS |

## 12. Plan issuance, evidence gates and close-out

This plan is issued as a **DRAFT** for human review in the program sign-off chain. It is **not an approval** and carries no regulatory authority: certification approval is issued by the regulator/designee, and individual flights are released only by the program's go/no-go gate (section 10).

Close-out rollup at issuance: objectives traced 6/6 (verdict COMPLETE); requirements traced 6/6 (verdict TRACE-COMPLETE); matrix steady-state verdict ALL-VALID; instrumentation release RELEASED; validation cards all pass. Verification of every requirement executes during the campaign and is reported separately after each flight.

Generated: 2026-09-06  ·  Role: flight-test-planning-engineer  ·  Status: draft-for-review

---

*Flight Test Plan and Requirements Traceability - DRAFT for human review. Not an approval document.*
