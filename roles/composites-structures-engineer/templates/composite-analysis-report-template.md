# Composite Structure Analysis and Certification Report

**Item:** Vertical stabilizer skin panel, bay P2 (between stringers S3 and S4)
**Part number:** VS-SK-0201
**Structure class:** primary structure
**Certification basis:** FAR/CS-25 (14 CFR Part 25 / EASA CS-25)
**Status:** draft-for-review

## 1. Scope

This report documents the analysis of the composite structural item listed above: laminate stiffness, ply-level stresses and failure indices, hygrothermal response, and panel stability. It is prepared as a DRAFT input for the human certification chain. It is not an approval and is not a certification.

- Item description: Stabilizer torque-box skin bay in the vertical tail, compression- and shear-loaded at the ultimate condition..

- Structure class: primary structure.
- Regulatory basis: FAR/CS-25 (14 CFR Part 25 / EASA CS-25); relevant rules: FAR 25.305 strength, FAR 25.307 proof of structure, FAR 25.571 damage tolerance.
- Analysis status: draft-for-review (generated 2026-09-06).

## 2. Materials and design allowables

- Material: T300/5208-style carbon/epoxy (unidirectional lamina).
- Lamina stiffness: E1 = 181.0 GPa, E2 = 10.3 GPa, G12 = 7.17 GPa, nu12 = 0.28.
- Allowable basis: B (B-basis: 95% confidence that at least 90% of the population exceeds the value).
- Knockdown factors applied to lamina allowables: environment 0.9, BVID 0.85, open hole 1.0 (product = 0.765).

## 3. Laminate definition and stiffness

- Stacking sequence: [45, -45, 0, 90, 90, 0, -45, 45, 45, -45, 0, 90, 90, 0, -45, 45] (16 plies), balanced and symmetric.
- Cured ply thickness: 0.125 mm; total laminate thickness: 2.000 mm.
- In-plane stiffness (CLT A matrix, N/m): A11 = 152.74e6, A12 = 45.21e6, A22 = 152.74e6, A66 = 53.76e6. A16/A26 vanish (balanced symmetric).
- Flexural stiffness (CLT D matrix, N*m): D11 = 49.79, D12 = 17.54, D22 = 47.11, D66 = 20.38.
- Effective engineering constants: Ex = 69.7 GPa, Ey = 69.7 GPa, Gxy = 26.9 GPa, nu_xy = 0.296.

## 4. Stress analysis and failure indices

- Ultimate load case (resultants N/mm): Nx = -75.0, Ny = -15.0, Nxy = 20.0.
- Mid-plane strains: ex = -5.0634e-04, ey = 5.1685e-05, gxy = 3.7202e-04.

Per-ply material-axis stresses (MPa) and failure indices (Tsai-Wu and max-stress; index >= 1.0 marks failure):

| Ply (deg) | s1 (MPa) | s2 (MPa) | t12 (MPa) | Tsai-Wu | Max-stress |
|---|---|---|---|---|---|
|  45 |     -8.71 |     -4.40 |      4.00 |   -0.0868 |    0.0588 |
| -45 |    -75.27 |     -1.62 |     -4.00 |   -0.0286 |    0.0588 |
|   0 |    -91.91 |     -0.93 |      2.67 |   -0.0147 |    0.0613 |
|  90 |      7.93 |     -5.09 |     -2.67 |   -0.1021 |    0.0392 |
|  90 |      7.93 |     -5.09 |     -2.67 |   -0.1021 |    0.0392 |
|   0 |    -91.91 |     -0.93 |      2.67 |   -0.0147 |    0.0613 |
| -45 |    -75.27 |     -1.62 |     -4.00 |   -0.0286 |    0.0588 |
|  45 |     -8.71 |     -4.40 |      4.00 |   -0.0868 |    0.0588 |
|  45 |     -8.71 |     -4.40 |      4.00 |   -0.0868 |    0.0588 |
| -45 |    -75.27 |     -1.62 |     -4.00 |   -0.0286 |    0.0588 |
|   0 |    -91.91 |     -0.93 |      2.67 |   -0.0147 |    0.0613 |
|  90 |      7.93 |     -5.09 |     -2.67 |   -0.1021 |    0.0392 |
|  90 |      7.93 |     -5.09 |     -2.67 |   -0.1021 |    0.0392 |
|   0 |    -91.91 |     -0.93 |      2.67 |   -0.0147 |    0.0613 |
| -45 |    -75.27 |     -1.62 |     -4.00 |   -0.0286 |    0.0588 |
|  45 |     -8.71 |     -4.40 |      4.00 |   -0.0868 |    0.0588 |

- Governing criterion: **max-stress** at the 0-deg plies (index 0.0613).
- Reserve factor to first-ply failure (un-knockdowned basis): **16.32**.
- Design allowables with knockdowns (MPa): Xt = 1147.5, Xc = 1147.5, Yt = 30.6, Yc = 188.2, S = 52.0.
- Reserve factor against knockdowned B-basis allowables: **12.49** (>= 1.0 required).
- Note: under compression-dominated states the Tsai-Wu index may be non-positive inside the failure surface; max-stress is then the governing conservative check.

## 5. Hygrothermal response

- Environment: RH = 0.60, temperature change delta_T = -156 K (room 21 C to cure 177 C reference), saturation moisture m_sat = 0.015.
- Equilibrium moisture content: M = 0.0090 (0.9% mass fraction).
- Laminate CTE (exact CLT): alpha_x = 7.750 ppm/K, alpha_y = 7.750 ppm/K.
- Laminate CME: beta_x = 0.1701, beta_y = 0.1701 (per unit moisture fraction).
- Hygrothermal strain (delta_m = 0.0090): eps_x = 3.2163e-04, eps_y = 3.2163e-04.
- Cure-cooldown residual strain: eps_x = -1.2090e-03.

## 6. Stability (plate buckling)

- Panel: a = 190 mm (load direction), b = 150 mm, simply supported edges, uniaxial compression Nx = 75 N/mm.
- Critical load (min over modes): N_x_cr = 97.92 N/mm, mode (1, 1).
- Buckling margin: **1.31** (>= 1.0 = no predicted buckling at the applied load).

## 7. Conclusions and certification readiness

- Governing condition: stability (plate buckling) with margin 1.31 at ultimate.
- Static strength is not critical for this load case; the reserve factor against knockdowned B-basis allowables is 12.49.
- Evidence required before the human certification engineer signs: coupon test results establishing the B-basis allowables used here, environmental conditioning data, BVID thresholds, and a damage-tolerance evaluation per the certification plan. Joint-level and repair analyses (bonded and bolted joints, sandwich details) follow the bound composite leaves.

---
*Generated by Aero Agent Roles composites-structures-engineer core (2026-09-06). DRAFT for human review by the certification chain. Not an approval. Not a certification.*
