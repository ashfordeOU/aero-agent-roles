# Finite Element Analysis Report

**Item:** Flap actuator support bracket assembly, LH rear spar (FAB-036)
**Structure:** Wing rear spar attachment, flap actuation load path
**Material:** 7075-T7351 (wrought, plate) (E = 71.7 GPa)
**Analysis basis:** component-level finite element idealizations (truss, frame, beam-column, buckling, vibration, modal, shear center, lug) per the bound Aero Agent Skills FEM family.
**Status:** draft-for-review

> This report is a DRAFT engineering analysis for human review within the stress sign-off chain. It is **not an approval** and carries no regulatory authority. Allowables are analysis inputs referenced to MMPDS chapter 9 (see SOURCES.md) and must be verified against the governing issue before release use.

## 1. Scope and models

The bracket carries the flap actuator ultimate reaction of 36.0 kN (upward into the bracket lug) into the wing rear spar. The report verifies the load path with eight independent FE / closed-form idealizations, each recorded with its model and results below.

- Load case A (ultimate): Actuator ultimate reaction, upward into the bracket lug (limit x 1.5 included upstream).
- Load case B (lateral): bracket and actuator lateral inertia, 3.0 kN at the lug tab (frame model only).
- Excitation for dynamics clearance: 35 Hz (structure-borne hydraulic actuator pulsation band 30-40 Hz (vendor data)).

## 2. Stage 1 - Truss idealization (load frame)

The bracket load frame (arm, compression brace, spar segment) is idealized as a 3-bar pin-jointed truss: nodes (0,0), (0.30,0) and (0,0.30) m; support at node 0 (x,y) and node 2 (x); 36.0 kN applied at the lug node 1.

| Member | Axial force (kN) | Sense |
|---|---|---|
| arm | 36.0 | tension |
| brace | -50.9 | compression |
| spar segment | 36.0 | tension |

Apex (lug node) deflection: 0.99 mm along the load direction.
Reactions: 0-x = -36.0 kN, 0-y = -36.0 kN, 2-x = 36.0 kN.

## 3. Stage 2 - Beam-frame idealization (arm + lug tab)

The arm and lug tab are modeled as a rigid-jointed 2D frame (Euler-Bernoulli elements, fixed at the spar attach) under the 3000 N lateral inertia case.

- Tip (lug tab) deflection: 0.996 mm.
- Fixed-end moment: 360 N m.
- Bending stress at the fixed end: 43.2 MPa; axial stress 3.0 MPa; combined 46.2 MPa.
- Margin of safety (combined, vs F_tu input): 9.15.
- Global equilibrium check: PASS.

## 4. Stage 3 - Beam-column (compression brace)

The compression brace (round 28 mm, L = 0.424 m) carries 50.9 kN from the truss solve with a 2.0 mm load eccentricity at the lug end.

- Euler load P_E: 118.6 kN.
- Moment amplification factor: 1.489.
- Applied moment (P x e): 101.8 N m; section moment capacity (F_tu x Z): 1010.8 N m.
- Interaction ratio: 0.606; margin of safety: 0.65; verdict: PASS.
- Secant-formula peak compressive stress: 174.3 MPa (below the yield-based limit input of 441.0 MPa).

## 5. Stage 4 - Column buckling check (compression brace)

- Critical (Euler) buckling load: 118.6 kN.
- Slenderness ratio: 60.6; transition slenderness: 40.1; Euler buckling governs: yes.
- Margin of safety (Pcr / applied - 1): 1.33.

## 6. Stage 5 - Beam vibration (continuous members)

- Actuator rod (steel, d = 10 mm, L = 0.45 m, pinned at both clevises): f1 = 100.3 Hz, f2 = 401.2 Hz, f3 = 902.7 Hz.
- Bracket arm first cantilever mode: 453.3 Hz.
- Separation from the 35 Hz excitation: rod f1 / f_exc = 2.87 (>= 2.0 criterion met).

## 7. Stage 6 - Modal analysis (2-DOF lumped assembly)

Lumped model of the actuation load path: actuator mass 4.5 kg on the arm-tip stiffness 1.660e+06 N/m (3EI/L^3), rod mass 0.28 kg on the rod axial stiffness 3.665e+07 N/m.

- Natural frequencies: w1 = 589.4 rad/s (93.8 Hz), w2 = 11843.7 rad/s (1885.0 Hz).
- Mode shapes (phi2/phi1): mode 1 = 1.000, 1.003, mode 2 = 1.000, -16.177.
- Resonance check at 35 Hz excitation (219.9 rad/s, +/- 10% band): resonance = no; nearest mode w = 589.4 rad/s.

## 8. Stage 7 - Shear center (channel rear spar)

The rear spar web is a thin-walled channel 100 x 50 x 4 mm (web x flanges x t). The V*Q/I shear-flow walk places the shear center 18.75 mm behind the web centerline (classical thin-channel formula: 18.75 mm; wall-flow integration: 18.75 mm).

- Shear introduced on the web centerline is therefore eccentric to the shear center by 18.75 mm, producing a torque of 675 N m per 36 kN of web shear.
- The 4-bolt bracket attach (120 mm pitch) reacts this torque as a couple of 5.6 kN per bolt pair; the bolt/joint check is part of the follow-on joint verification.

## 9. Stage 8 - Lug joint (actuator clevis)

Round-end lug, hole D = 12.7 mm, thickness t = 6.35 mm, width w = 2e = 38.1 mm (e/D = 1.50, D/t = 2.0), axial load 36.0 kN.

| Mode | Applied stress (MPa) | Allowable input (MPa) | Margin |
|---|---|---|---|
| bearing | 446.4 | 552.0 (F_bru) | 0.237 |
| net tension | 223.2 | 469.0 (F_tu) | 1.101 |
| tearout | 157.8 | 296.0 (F_su) | 0.875 |

- Governing mode: bearing; minimum margin of safety: 0.237; verdict: PASS.
- Limiting allowable capacity: 44.5 kN (bearing governs).

## 10. Margin summary

| Stage | Analysis | Key quantity | Value | Margin | Status |
|---|---|---|---|---|---|
| 1 | Truss idealization (load frame) | brace compression force | 50.9 kN | - | PASS |
| 2 | Beam-frame idealization (lateral case) | combined bending + axial stress | 46.2 MPa | 9.15 | PASS |
| 3 | Beam-column (brace, combined loading) | interaction ratio | 0.606 | 0.65 | PASS |
| 4 | Column buckling (brace, pinned-pinned) | critical buckling load | 118.6 kN | 1.33 | PASS |
| 5 | Beam vibration (actuator rod) | rod fundamental frequency | 100.3 Hz | 1.87 | PASS |
| 6 | 2-DOF modal (actuator + rod) | first assembly mode | 93.8 Hz | 1.68 | PASS |
| 7 | Shear center (channel rear spar) | shear-center offset | 18.75 mm | - | PASS |
| 8 | Lug joint (actuator clevis) | governing margin (bearing) | 0.237 | 0.24 | PASS |

## 11. Findings, notes and open items

1. All eight stages close with positive margins; the lug bearing mode is the sizing driver (margin +0.24) - confirm the F_bru input against the governing MMPDS issue at e/D = 1.5 and D/t = 2.0.
2. The channel web shear introduces a 675 N m torque through the shear-center offset; the bracket bolt-pattern couple reaction is documented and the joint check is a follow-on item.
3. Dynamics: no resonance of the actuation load path within +/- 10% of the 35 Hz excitation band.
4. Material allowables used as inputs (MMPDS chapter 9 family, 7075-T7351) must be re-verified against the governing issue before this analysis supports any release action.
5. This DRAFT requires human stress review and disposition before any further use. It is not an approval document.

---
*Generated by Aero Agent Roles fem-analysis-engineer core (2026-09-06). DRAFT for human review. Not an approval document.*