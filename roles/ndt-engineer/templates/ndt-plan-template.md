# Nondestructive Test Plan and Method Selection Report

**Item:** Main Gearbox Housing (investment casting)  (PN 7450-103)
**Material:** A356 aluminum alloy casting (non-ferromagnetic, 30 pct IACS)  **Route:** investment cast + T6
**Drawing:** DWG 7450-103 rev C
**Certification basis:** AS9100D special-process control; NAS 410 personnel qualification practice
**Status:** draft-for-review

Scope: Critical cast aluminum gearbox housing; the casting is fully machined after NDT and holds oil under pressure in service.

## 1. Candidate defect population and method selection

Method selection follows the bound ndt-method-selection decision logic: defect class (surface / near-surface / internal) x material class (non-ferromagnetic) defines the applicable set, and sensitivity rank (UT 5, RT/ET 4, MT/PT 3) picks the method (cost is reporting only).

### 1.1  Fatigue crack at oil-feed boss

- Zone / note: surface-breaking crack zone on the machined boss face (non-ferromagnetic aluminum)
- Defect class: surface  ·  material class: non-ferromagnetic
- Applicable methods: eddy current testing (ET) (sensitivity 4), liquid penetrant testing (PT) (sensitivity 3)
- **Selected method: eddy current testing (ET)** — surface defect in non-ferromagnetic material: ET is the highest-sensitivity applicable method.
- Alternates: liquid penetrant testing (PT)

### 1.2  Subsurface gas porosity under machined skin

- Zone / note: near-surface gas porosity band beneath the machined skin
- Defect class: near-surface  ·  material class: non-ferromagnetic
- Applicable methods: eddy current testing (ET) (sensitivity 4), ultrasonic testing (UT) (sensitivity 5)
- **Selected method: ultrasonic testing (UT)** — near-surface defect in non-ferromagnetic material: UT is the highest-sensitivity applicable method.
- Alternates: eddy current testing (ET)

### 1.3  Internal shrinkage porosity in lug section

- Zone / note: internal shrinkage/gas porosity population in the thick lug section
- Defect class: internal  ·  material class: non-ferromagnetic
- Applicable methods: radiography (RT) (sensitivity 4), ultrasonic testing (UT) (sensitivity 5)
- **Selected method: ultrasonic testing (UT)** — internal defect in non-ferromagnetic material: UT is the highest-sensitivity applicable method.
- Alternates: radiography (RT)

## 2. Inspection parameters per selected method

_Parameter rows below are computed by the role core mirroring the bound method leaf logic. The qualified procedure and the engineering specification govern the actual inspection settings._

### 2.1 Eddy current (ET) — surface zone
- Flaw depth: 0.001 m; conductivity 30 pct IACS (1.74e+07 S/m)
- Test frequency (penetration factor 0.5): **58231 Hz**; standard depth of penetration **0.0005 m**
- Current density at the flaw depth: 0.135 of surface; phase lag 114.59 deg

### 2.2 Eddy current (ET) — near-surface zone
- Subsurface flaw depth 0.001 m: frequency **3639 Hz**, standard depth of penetration 0.002 m keeps the flaw at half a delta (density ratio 0.607, phase lag 28.65 deg)

### 2.3 Liquid penetrant (PT) — surface-breaking crack zone
- Penetrant: gamma 0.032 N/m, contact angle 5 deg, viscosity 0.008 Pa.s; crack opening 4e-06 m -> effective capillary radius 2e-06 m
- Capillary pressure across the meniscus: **3.19e+04 Pa**
- Washburn model: penetration depth 0.03458 m at the 300 s reference dwell; computed time to fill the 0.001 m-deep reference crack 0.251 s (dwell scales with depth squared and inversely with crack radius)
- Indication sizing: bleed-out width 1.6e-05 m for the 4e-06 m opening (ratio 4.0); developer 0.075 kg at 0.15 kg/m2 over 0.50 m2; fluorescent contrast vs background 0.938
- Dwell: procedure-qualified penetrant dwell governs; the model numbers above are sizing inputs, not settings.

### 2.4 Radiography (RT) — internal volumetric zone
- Setup: focal spot 3.0 mm, SOD 500 mm, ODD 30 mm -> geometric unsharpness **0.18 mm** (limit 0.25 mm)
- Exposure (inverse-square): **1.39 min** at the working distance
- IQI sensitivity: 2.00 pct (0.6 mm visible on 30 mm section; limit 2.0 pct)
- Film density 2.50 in band 2.0-4.0 (acceptable); technique verdict: **acceptable**
- Expected discontinuity class from image geometry: porosity (acceptance criteria per class)

### 2.5 Computed tomography (CT) — supplemental volumetric sizing
- Magnification 2.00, voxel size 0.0001 m; required flaw 0.0005 m
- Resolution: PASS: smallest detectable feature 3.000e-04 m (3 voxels) is at or below the required 5.000e-04 m flaw size
- Scan plan: 1609 projections at 350 kV (161 s), material aluminum thickness 50 mm
- Porosity ROI: 0.8 pct void fraction, equivalent spherical void diameter 0.00496 m; CT number +400 HU -> light-alloy

### 2.6 Magnetic particle (MT) — ferromagnetic parts
- Not applicable to this non-ferromagnetic part; retained in the method library for ferromagnetic parts (forgings, steel castings).

### 2.7 Leak test (LT) — sealed assembly
- Method recommendation: **pressure-decay** — only one side accessible and the part holds pressure, so a decay test on the sealed internal volume fits
- Pressure decay: 5 L at dP 0.02 bar over 600 s -> leak rate **0.1645 scc/s**; allowable 0.2 scc/s -> disposition **accept** (margin 0.85 dB)
- Gauge adequacy: 0.0005 bar resolution needs >= 12.3 s to catch the allowable leak; test time 600 s is adequate

## 3. NDT personnel qualification

- Operator level: Level II (supervisor Level III)
- Certification status as of 2026-09-05: **current** (recert due 2027-09-05; near-vision due 2027-03-05)
- Supervision pairing: valid (Level I operators work under Level II/III)
- Upgrade evaluation (toward Level III): eligible when hours, months and examination are met
- Per-method certification check (interpretation of results requires the level shown):
  - PT: Level II to interpret, Level I to perform — operator meets
  - ET: Level II to interpret, Level I to perform — operator meets
  - UT: Level II to interpret, Level I to perform — operator meets
  - RT: Level II to interpret, Level I to perform — operator meets
  - CT: Level II to interpret, Level II to perform — operator meets
  - LT: Level II to interpret, Level II to perform — operator meets

## 4. Acceptance and disposition framing

All dispositions in this plan are INPUTS for the responsible engineering authority; the customer acceptance document and the qualified procedure govern.

- **ET:** signal amplitude and phase vs the calibrated reference standard gate sizing; indications are evaluated against the acceptance document for the zone (crack-like vs volumetric responses)
- **PT:** rounded indications (pores) and linear indications (cracks, laps) are sized from the bleed-out image and evaluated against their class limits; excessive background is a process failure, not an indication
- **RT:** the discontinuity class (porosity / crack / inclusion / slag) gates the applicable acceptance criteria; the technique verdict (unsharpness, IQI sensitivity, film density) must be acceptable before any disposition is made
- **CT:** segmented void fraction and equivalent void diameter are disposition inputs against the casting acceptance standard; resolution must first pass the required-flaw check
- **LT:** measured leak rate is accepted when at or below the maximum allowable, rejected when above 1.25x the allowable, reviewed in between (margin band)

## 5. Open items for the responsible authority

- Confirm the acceptance limits and the qualified procedure revisions named in the drawing and the program plan.
- Confirm operator certification records and intervals match the employer's written practice.

---
*Generated by Aero Agent Roles ndt-engineer core (2026-09-05). DRAFT for human NDT engineering review. Not an approval document; carries no acceptance or certification authority.*
