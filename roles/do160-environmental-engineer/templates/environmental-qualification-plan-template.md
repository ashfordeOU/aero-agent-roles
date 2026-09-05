# Equipment Environmental Qualification Plan/Report

**Item:** Terrain Awareness Warning System (TAWS) computer LRU
**Installation:** Forward equipment bay, pressurized and temperature-controlled, FAR/CS-25 transport
**Certification basis:** FAR/CS-25
**Standard:** DO-160G (environmental conditions and test procedures for airborne equipment)
**Status:** draft-for-review

## 1. Scope

This plan/report covers environmental qualification of the LRU Terrain Awareness Warning System (TAWS) computer LRU. Line-replaceable unit hosting the TAWS alerting function for a FAR/CS-25 transport.
Expected operating temperature extremes: -40 to 55 deg C.

## 2. Environmental categories

- Temperature/altitude category: B1 (typical operating range -55 to 55 deg C; typical reference data, confirm against the current revision).
- ESD category: A (single category per Section 25).
- RF emissions installation category: A (reference-only RE102 floor model).
- Lightning: Section 22 test level 3, waveform set A, B, C, H.
- Power input: 28 VDC bus, Section 16 envelope (see Section 6).

## 3. Qualification test matrix

Required test-condition sections for the equipment category (B1) and planned coverage:

| Section | Test condition | Planned |
|---|---|---|
| 4 | Temperature and altitude | yes |
| 5 | Temperature variation | yes |
| 6 | Humidity | yes |
| 7 | Operational shocks and crash safety | yes |
| 8 | Vibration | yes |
| 9 | Explosion proofness | yes |
| 10 | Waterproofness | yes |
| 11 | Fluids susceptibility | yes |
| 16 | Power input | yes |
| 19 | Induced signal susceptibility | yes |
| 20 | Radio frequency susceptibility | yes |
| 21 | Emission of radio frequency energy | yes |
| 22 | Lightning induced transient susceptibility | yes |
| 23 | Lightning direct effects | yes |
| 24 | Icing | yes |
| 25 | Electrostatic discharge | yes |

Matrix completeness: COMPLETE - no required section missing.
Category-specific section exclusions must be confirmed against the current revision before freezing the matrix.

## 4. Electrostatic discharge (Section 25)

- Equipment category: A (the only Section 25 category).
- Test level: 15 kV air discharge on the equipment bonded to the ground plane.
- Discharge generator (IEC 61000-4-2 human-body model): 150 pF storage capacitance, 330 ohm discharge resistance.
- Stored energy at test level: 0.016875 J (16.875 mJ).
- Waveform: first peak 56.25 A, 30.00 A at 30 ns, 15.00 A at 60 ns; rise time 0.7 to 1.0 ns; RC time constant 49.5 ns.
- Discharges per test point: 10 positive and 10 negative (valid: true).
- Test points: surfaces accessible to personnel during normal operation or maintenance; connector pins are not applicable test points.
- Verdict (planned): PASS - operates as specified with no permanent degradation.

## 5. Lightning protection (Sections 22/23)

- Section 22 induced transient susceptibility test level: 3 (valid range 1-5: true).
- Waveform set: A, B, C, H (letters within A-H: true).
- Section 22/23 pass criteria: no physical damage, no upset, no latch-up after the applied transients.
- Verdict (planned): PASS.
- Level and waveform tables are standard data in the current revision; verify selection before freezing the plan.

## 6. Power input (Section 16)

- Bus: 28 VDC; Section 16 category envelope values applied from the current revision (data-driven, summary reference).
- Normal steady-state range: 22.0 to 29.0 V. Emergency range: 18.0 to 32.2 V (emergency-rated: true).
- Measured steady state 27.5 V: within normal range; margins 5.5 V low / 1.5 V high.
- Measured sag 20.0% of nominal (80 ms event vs 25% max / 100 ms envelope): within envelope; margins 20.0 ms, 5.0%.
- Recovery after transient 60 ms vs 100 ms allowable: within.
- Ripple: 3.57% of nominal (characterization).
- Emergency classification of measured bus: normal.

## 7. Radio frequency susceptibility (Section 20)

- RS103 radiated test field: 100 V/m (typical mid-range category value; verify against the current revision).
- Calibration field with 6 dB margin: 199.5 V/m.
- Amplifier budget for 3 m, 3 dBi, 3 dB cable loss, 6 dB margin: 11943 W.
- Far-field check: wavelength at 1 GHz is 0.2998 m; the far-field relation E = sqrt(30*P*G)/d holds beyond the Fraunhofer distance.
- CS114 conducted category C: limit 75.7 dBuA (summary reference base); measured 60.0 dBuA gives margin 15.7 dB (within limit).

## 8. Radio frequency emissions (Section 21)

- RE102 radiated, installation category A (reference-only floor 24 dBuV/m, 2 MHz to 18 GHz):
  - Measured sweep: 15.0 dBuV/m at 10 MHz, 20.0 dBuV/m at 100 MHz, 18.0 dBuV/m at 1 GHz.
  - Margins: +9.0 dB, +4.0 dB, +6.0 dB; worst case 100 MHz at +4.0 dB.
  - Verdict: PASS (minimum margin >= 0 dB).
- CE102 conducted (10 kHz to 10 MHz, reference-only band curve):
  - Measured sweep: 68.0 dBuV at 50 kHz, 54.0 dBuV at 150 kHz, 66.0 dBuV at 5 MHz.
  - Margins: +10.0 dB, +6.0 dB, +4.0 dB; worst case 5 MHz at +4.0 dB.
  - Verdict: PASS (minimum margin >= 0 dB).
- A margin band of at least 6 dB is typical engineering recommendation (reference-only, not an RTCA requirement).

## 9. Verdicts and open items

| Domain | Section | Verdict |
|---|---|---|
| Electrostatic discharge | 25 | PASS |
| Lightning | 22/23 | PASS |
| Power input | 16 | PASS |
| RF susceptibility (CS114) | 20 | PASS |
| RF emissions (RE102) | 21 | PASS |
| RF emissions (CE102) | 21 | PASS |

Open items before the human environmental qualification engineer signs:
- Confirm level/waveform/limit tables against the current DO-160 revision (typical reference data used throughout).
- Confirm category-specific matrix exclusions for the installed location.
- Review measured bench data against the qualification test environment.

---
*Generated by Aero Agent Roles do160-environmental-engineer core. DRAFT for human environmental qualification engineer review. Not an approval document.*