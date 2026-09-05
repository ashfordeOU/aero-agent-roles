# Aerodynamic Design Report

**Aircraft:** TAC-150 twin-jet transport (reference configuration)
**Status:** draft-for-review (generated 2026-09-05)

## 1. Configuration summary

- Aircraft: TAC-150 twin-jet transport (reference configuration) - 150-seat short/medium-haul transport, wing-body-tail configuration, underlying podded engines
- Mission: short/medium-haul transport - cruise M 0.78 at 10668 m; dive M 0.89 (V_D 263.9 m/s TAS); MTOW 735 kN, cruise weight 622 kN
- Selected airfoil + rationale: representative supercritical section (t/c 0.105), Korn drag-divergence benefit over a conventional section; section cl_max 1.55 from the stage-1 XFOIL-style analysis
- Wing planform: area 122.6 m2 - AR 8.0 - span 31.3 m - MAC 3.91 m - quarter-chord sweep 25 deg - taper 0.30
- High-lift system: full-span leading-edge slat + single-slotted trailing-edge flap (deflections in section 4)

## 2. Airfoil analysis

- Operating Reynolds range (MAC-based, clean wing): 2.36e+07 (sea-level low-speed) to 2.40e+07 (cruise M 0.78)
- Section: representative supercritical section; thin-airfoil section slope a0 = 6.283/rad
- CL_max clean (wing-level): 1.264 (0.9 x section 1.55 x cos(sweep)); with high-lift: 2.273 landing / 1.910 takeoff
- Drag divergence (Korn rule, supercritical t/c 0.105 at cruise CL 0.500): M_DD = 0.795
- Source tool + settings: stage-1 XFOIL viscous analysis (transition) on the candidate sections; tool sanity anchor NACA 0012 at Re = 6e6 (cl ~0.82 at 10 deg, cd0 ~0.0079 band, xfoil-analysis leaf) recorded in the analysis evidence set

## 3. Drag buildup

| Component | Cf | FF | Q | S_wet (m2) | Cd0 term | Basis |
|---|---|---|---|---|---|---|
| wing | 0.00255 | 1.2222 | 1.00 | 218.5 | 0.005562 | Cf x FF x Q x S_wet/S_ref (Re 2.40e+07) |
| fuselage | 0.00189 | 1.0934 | 1.00 | 401.0 | 0.006764 | Cf x FF x Q x S_wet/S_ref (Re 2.30e+08) |
| nacelles x2 | 0.00265 | 1.2414 | 1.20 | 29.0 | 0.000935 | Cf x FF x Q x S_wet/S_ref (Re 1.78e+07) |
| horizontal tail | 0.00270 | 1.2100 | 1.00 | 50.6 | 0.001347 | Cf x FF x Q x S_wet/S_ref (Re 1.56e+07) |
| vertical tail | 0.00264 | 1.2100 | 1.00 | 39.4 | 0.001028 | Cf x FF x Q x S_wet/S_ref (Re 1.84e+07) |
- Total Cd0: 0.01564 - Oswald/span efficiency: 0.80 - equivalent skin friction Cf_e = 0.00260 (Cd0 x S_ref / S_wet_total = 738 m2)
- Full polar: CD = 0.01564 + 0.04974 x CL^2; at cruise CL 0.500: CD = 0.02805, L/D = 17.81; polar peak L/D 17.93 at CL_opt 0.561

## 4. High-lift assessment

- Device + deflections: full-span slat (span fraction 0.85) + slotted flap (chord fraction 0.25, span fraction 0.70); takeoff 15 deg, landing 35 deg (max 40 deg for the slotted flap)
- Section increments: flap +0.366 (TO) / +0.812 (landing), slat +0.425 (K_delta x K_chord x K_span x reference increment, high-lift leaf)
- CL_max with device: takeoff 1.910, landing 2.273 (0.9 x section cl_max x cos(sweep)) vs clean 1.264
- Stall speeds (sea level): clean 88.0 m/s at MTOW, takeoff 71.6 m/s at MTOW, landing 60.9 m/s at landing weight; landing reference speed 1.23 x V_S = 74.9 m/s (CS/FAR 25.125 minimum reference-speed practice)

## 5. CFD evidence

- Case: ONERA M6 wing validation + 3-mesh grid study on the transport wing-body at cruise M 0.78 / CL 0.500
- Validation target: ONERA M6 wing at M 0.84, Re 1.17e+07, alpha 3.06 deg (reference CD 0.0163); computed CD 0.0169 -> relative error 3.7% vs 5% band: PASS
- Mesh convergence: 1.9e+07 / 4.8e+06 / 1.2e+06 cells (refinement ratio 2.0); CD 0.02840 / 0.02910 / 0.03060; apparent order 1.10, Richardson-extrapolated CD 0.02779, GCI 0.00077 (2.7% of the fine-mesh value)
- Turbulence model + wall treatment: RANS (SA) on the fine mesh, resolved near-wall layer (y+ <= 1); fine-mesh total drag 0.02840 vs component-buildup polar 0.02805 at the same condition (1.2% apart)

## 6. Transonic behavior

- Effective section Mach at cruise: M cos(sweep) = M 0.78 x cos(25 deg) = 0.707
- Drag-divergence Mach (Korn, supercritical): M_DD = 0.95 - t/c (0.105) - CL/10 (0.0500) = 0.7950
- Wave drag at cruise: 0.0000 penalty index (0 below M_DD; (M - M_DD)^3 above) - cruise holds 0.0150 below drag divergence; shock location: no terminating shock at cruise (no supercritical pocket closure case)
- Supercritical behavior notes: flat-top section holds the local Mach just-supersonic with a weak terminating shock; transonic similarity parameter K = (1 - M^2)/tau^(2/3) = 1.759

## 7. Aeroelastic screening

- Flutter speed estimate: 364.2 m/s (V-g typical-section flutter speed, outboard wing at the dive condition, flutter-speed-prediction leaf analysis) vs V_D 263.9 m/s -> margin 1.38 (PASS >= 1.15)
- Static divergence: no static-divergence mechanism for the swept-back wing (aerodynamic center aft of the elastic axis, divergence-speed leaf domain e <= 0)
- Gust response (load factor): discrete-gust screening at cruise, U_de = 12.5 m/s, quasi-steady Delta CL = a x U_de/V -> Delta n = 0.49, n = 1.49 g. NOTE: aeroelastic results are SCREENING inputs for the loads/structures role - not final flutter or gust clearance

## 8. Margin summary

| Margin | Value | Requirement | Source (stage) |
|---|---|---|---|
| Flutter margin (V_F / V_D) | 1.380 | >= 1.15 x V_D (flutter-speed leaf clearance practice) | stage 10: V-g typical-section flutter speed 364.2 m/s vs design dive speed 263.9 m/s |
| Drag-divergence margin (M_DD - M_cruise) | 0.015 | > 0 (cruise below drag divergence; wave-drag penalty = 0) | stage 8: Korn rule M_DD = 0.795 at cruise C_L 0.4996 |
| Stall margin, clean (CL_max clean / C_L cruise) | 2.530 | > 1 (no stall at the cruise point, sea-level MTOW V_s = 88 m/s) | stage 4: wing CLmax = 0.9 x section clmax x cos(sweep) |
| High-lift CL_max gain (landing - clean) | 1.009 | > 0 (flap + slat increments from high-lift leaf) | stage 4: slotted flap dcl 0.812 + slat dcl 0.425 (section), 3D/sweep factor 0.9 x cos(25 deg) |
| L/D efficiency margin ((L/D_max - L/D_cruise) / L/D_max) | 0.007 | >= 0 (cruise lift coefficient within the polar peak) | stage 5: polar peak L/D 17.93 at C_L 0.561 vs cruise L/D 17.81 |

---
*DRAFT - for human aerodynamics lead review. Not an approval document.*