# SOURCES.md - DO-160G Environmental Qualification Engineer

Standards and documents this role references. Summary-not-copy: see
[STANDARDS.md](../../STANDARDS.md) for the full rule and purchase links.

| Source | Role use | Gated |
|---|---|---|
| RTCA DO-160G / EUROCAE ED-14G | environmental test conditions and procedures for airborne equipment (sections 4-11, 16, 19-25); category and level selection | true |
| IEC 61000-4-2 | electrostatic discharge human-body model (150 pF / 330 ohm) referenced by DO-160 Section 25 practice | true |

## Grounding notes

- The role's executable core mirrors the domain rules encoded in the
  bound AeroSkills leaves under `avionics/do160/`
  (environmental-qualification, lightning-protection,
  electrostatic-discharge, power-input, radio-frequency-susceptibility,
  radio-frequency-emissions), which encode summary reference practice
  only. Their `scripts/*_logic.py` files are the arithmetic contracts
  the core mirrors; every worked anchor (15 kV air discharge, 56.25 A
  first peak, 49.5 ns RC constant, 25% sag / 15% surge anchors, CS114
  10 dBuA category steps, CE102/RE102 reference floors) is checked
  against those files in the role tests when the skills checkout is
  present.
- DO-160G section level/waveform/limit TABLES are standard data in the
  current revision and are NOT reproduced here; typical reference
  values are flagged as such and must be verified against the current
  revision before a plan is frozen.
- The qualification report template in `templates/` is an original
  structure informed by public summary process knowledge. No
  proprietary text is reproduced.
