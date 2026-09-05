# SOURCES.md - Structures and Loads Engineer

| Source | Role use | Gated |
|---|---|---|
| 14 CFR Part 25 (subpart C/D) | loads and structure requirements | false |
| 14 CFR 25.341 / 25.337 / 25.303 | discrete gust load factor, alleviation factor, limit maneuvering load factor n = max(2.5, min(3.8, 2.1 + 24000/(W+10000))), 1.5 factor of safety | false |
| MMPDS | metallic allowables (licensed; never reproduced - screening values cited from bound leaf anchors with basis) | true |
| CMH-17 | composite allowables (licensed) | true |
| Bruhn, Analysis and Design of Flight Vehicle Structures | analysis methods (book); elliptic span-load / box-beam idealizations | true |
| Niu, Airframe Structural Design | airframe methods (book) | true |
| CalculiX documentation | FEM tooling | false |

Summary-not-copy per STANDARDS.md. Allowables cited with source, never
reproduced.

## Domain-rule provenance (core/structures_loads_core.py)

Every computation in the executable core mirrors a REAL rule from the
bound AeroSkills leaves or a quotable public regulation:

- Gust envelope, K_g, mass ratio, V-n diagram, gust-critical margins:
  bound leaf structures/loads/gust-maneuver-loads (gust_load_logic.py)
  and FAR 25.341 / 25.337 / 25.333.
- Landing reactions, braked-roll deceleration: bound leaf
  structures/loads/landing-ground-loads (level-landing statics, limit
  vertical inertia factor 2.5 default).
- Euler column + yield transition (lambda_1), plate buckling (k=4 ssss
  long plate; k_s shear coefficient): bound leaves
  structures/fem/buckling-analysis and structures/fem/plate-buckling.
- Lug bearing / net-section / tearout margins, governing mode: bound
  leaf structures/fem/lug-joint-analysis (worked example reproduced:
  7075-T6 Ftu 572 / Fsu 331 / Fbru 1050 MPa -> margins +1.800 / +1.135
  / +0.926, tearout governs).
- Fatigue: Basquin S-N (bound stress-life-curve leaf), modified Goodman
  mean correction (bound goodman-diagram leaf), Palmgren-Miner damage
  sum (bound miner-damage leaf); 7075-T6 class fatigue constants
  (sigma_f' ~ 690 MPa, b = -0.10) from the bound strain-life leaf
  (representative typical, reference-only).
- First wing bending frequency: bound leaf
  structures/fem/beam-vibration (cantilever root beta1*L = 1.8751).

Example wing geometry (reference item) is a self-consistent candidate
design; all margins of safety in the filled template are computed, not
stated.
