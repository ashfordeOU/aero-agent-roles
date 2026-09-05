# Loads and Strength Report

**Item:** Example regional transport wing
**Aircraft:** Example 100,000 lb regional transport (FAR 25)
**Category / basis:** transport category, FAR 25 (Subpart C loads, Subpart D structure)
**Status:** draft-for-review

## 1. Loads

- Wing loading W/S = 100.000 psf, mean geometric chord cbar = 11.180 ft (cbar = S/b), lift-curve slope a = 5.700/rad.
- Design speeds (EAS): VS = 230.000 ft/s, VA = 363.662 ft/s, VB = 414.000 ft/s, VC = 460.000 ft/s, VD = 621.000 ft/s.
- Gust alleviation (FAR 25.341(b)(2)): mass ratio mu_g = 41.020, alleviation factor K_g = 0.779.
- Limit maneuvering load factor at VA = 2.500 (transport category, FAR 25.337); negative limit -1.000 at speeds up to VC.
- Discrete-gust limit load factors (design gust velocities U_de of FAR 25.341(a) at sea level, fps EAS):

  - VB (414.000 ft/s, U_de = 66.000 fps): n = 2.443 (positive), -0.443 (negative).
  - VC (460.000 ft/s, U_de = 50.000 fps): n = 2.215 (positive), -0.215 (negative).
  - VD (621.000 ft/s, U_de = 25.000 fps): n = 1.820 (positive), 0.180 (negative).

- Gust line vs maneuver envelope at VB/VC/VD: VB margin -0.215 (gust-critical); VC margin -0.416 (gust-critical); VD margin +1.000 (maneuver envelope governs).

- **Design limit condition: maneuver at VA, n_limit = +2.500** (negative envelope limit -1.000).
- **Ultimate loads: n_ult = 1.5 x 2.500 = 3.750 (factor of safety, FAR 25.303).**

- Root loads per wing at the design condition (elliptic span-load idealization: root shear = nW/2 and root bending M = nWb/(3 pi), the semi-ellipse lift resultant standing at 4/(3 pi) of the semi-span from the root):
  - Limit root bending moment = 28.47 M in-lb; ultimate root bending M_ult = 42.70 M in-lb (3.56 M ft-lb).
  - Ultimate root shear V_ult = 188 klb per wing.

- Ground loads - level landing at the limit vertical inertia factor 2.500 (bound landing-ground-loads leaf):
  - Nose gear reaction 62 klb; main gear reaction 188 klb (total 250 klb).
  - Braked-roll deceleration 0.60 g (braking friction 0.8 on the main gear).
- Spectra: fatigue and dynamic load spectra feed the fatigue screening (Section 6); random-vibration / shock-response-spectrum conditions for equipment-mounted structure are derived with the bound random-vibration-analysis / shock-response-spectrum leaves when that structure is in scope.

## 2. Global model

- Idealization: each wing is a cantilever box beam from the root to the tip carrying the elliptic spanwise lift distribution l(y) = l0 sqrt(1 - (2y/b)^2); root shear and bending then follow in closed form (above), which is sufficient for the screening margins of this report. A refined beam-frame/truss/CalculiX model (bound FEM leaves) confirms station-by-station internal loads and deflections in the detailed phase.
- Boundary conditions: wing root fixed at the fuselage side of body; box depth h = 40.000 in between spar cap centroids at the root section (example geometry).
- Internal loads at the root: M_ult = 42.70 M in-lb, V_ult = 188 klb - used for every margin below.

## 3. Strength/stability margins (ultimate load)

| Component | Load | Allowable | MS | Basis |
|---|---|---|---|---|
| Lower spar cap (tension, root) | P = M_ult/h = 1067611 lb | Ftu = 83.0 ksi | **+0.360** | boom couple at box depth 40 in; 7075-T6 Ftu per bound materials/lug leaf anchors (MMPDS B-basis to confirm) |
| Upper spar cap (compression, root) | P = M_ult/h = 1067611 lb | Fcy = 73.0 ksi | **+0.196** | compression material limit (yield); local stability of the stiffened panel carried by the skin/stringer rows |
| Spar web (shear, two webs) | V_ult = 187500 lb | Fsu = 48.0 ksi | **+0.557** | V_ult/(2 t h_web); 7075-T6 Fsu per bound lug leaf anchor (MMPDS to confirm) |
| Upper skin panel (compression buckling, between stringers) | sigma_app = 61.0 ksi | sigma_cr = 66.7 ksi (k=4, ssss long plate) | **+0.093** | plate buckling sigma_cr = k pi^2 E/(12(1-nu^2)) (t/b)^2 with b = stringer pitch 6.0 in, t = 0.25 in (bound plate-buckling leaf) |
| Upper stringer (column over rib pitch) | P_app = 73208 lb | Fcy*A = 87545 lb (yield-governed column) | **+0.196** | short column: lambda = 31.1 < lambda_1 = 37.5, yield governs (bound buckling leaf) |
| Wing root lug (vertical shear, one lug of pair) | P = V_ult/2 = 93750 lb | min over bearing Fbru, net-tension Ftu, tearout Fsu; governing mode tearout | **+2.259** | round-end lug: bearing, net section, tearout margins per bound lug-joint leaf (e/D = 1.50, D/t = 4.00) |

## 4. Dynamics

- First wing bending frequency f1 = 2.135 Hz (uniform cantilever idealization over the semi-span with the root box stiffness EI, wing weight fraction applied; beta1*L = 1.875, bound beam-vibration leaf).
- Frequency placement vs rotor/propeller 1P and control-surface excitation bands is confirmed against the bound modal-analysis / beam-vibration leaves in the detailed phase.

## 5. Materials

- Allowables used: 7075-T6 screening values from the bound AeroSkills anchors (material-selection leaf E/Fty/UTS, lug-joint worked example Fsu/Fbru, strain-life 7075-T6 class fatigue constants). MMPDS (licensed) is referenced, never reproduced; B-basis design allowables are confirmed by the materials group before release:
  - E = 10400 ksi; Ftu = 83.0 ksi; Fty = 73.0 ksi; Fsu = 48.0 ksi; Fbru = 152.3 ksi.
- Ramberg-Osgood / creep / fracture data: not required for the 7075-T6 screening at room temperature; the bound ramberg-osgood / creep-rupture / fracture-toughness leaves apply where those regimes are in scope.

## 6. Fatigue

- Critical location: lower spar cap at the root; 1g bending stress sigma_1g = 16.3 ksi.
- S-N basis: Basquin S = A N^b with A = 100.1 ksi, b = -0.10 (7075-T6 class fatigue strength constants, bound stress-life / strain-life leaves, reference-only). Mean stress is corrected with the modified Goodman rule Sa_eq = Sa / (1 - Sm/Ftu).
- Spectrum (per-flight cycle blocks at the lower spar cap, amplitude dn about the 1g mean):

  - 1.00 cycle(s)/flight at dn = 0.80: Sa = 6.5 ksi, Sa_eq = 8.1 ksi, N = 8.34e+10 cycles, damage per flight = 1.20e-11
  - 0.05 cycle(s)/flight at dn = 1.40: Sa = 11.4 ksi, Sa_eq = 14.2 ksi, N = 3.10e+08 cycles, damage per flight = 1.61e-10

- GAG cycle (0g to 1g, once per flight): Sa = 8.1 ksi, Sm = 8.1 ksi, Sa_eq = 9.0 ksi, N = 2.83e+10 cycles, damage per flight = 3.53e-11.
- **Palmgren-Miner cumulative damage sum per flight D = 2.09e-10** (limit 1.0): safe-life screening passes with equivalent life far beyond the design life; production fatigue refines with the counted load spectrum and detail notch factors from the bound load-spectrum-counting / notch-sensitivity / goodman-diagram leaves.

## 7. Damage tolerance

- Safe-life screening (Section 6) is the scope of this example report; the damage tolerance evaluation per FAR 25.571 (crack growth, residual strength, inspection intervals) is executed with the bound crack-growth / residual-strength / widespread-fatigue-damage leaves once the production spectrum and crack-growth data are baselined.
- Bird strike (FAR 25.631) is a design load case for the leading edge and windshield supports; the bound bird-strike leaf applies when that structure is in scope.

## 8. Composites / thermal

- The example item is metallic (7075-T6); laminate first-ply-failure and sandwich margins from the bound laminate-stiffness / laminate-first-ply-failure / failure-criteria / sandwich-panels leaves apply when composite structure enters the design.
- Thermal stress and thermal buckling margins are computed with the bound thermal-stress-analysis / thermal-buckling leaves for thermal-critical structure; no thermal-critical metallic margin is driven in this room-temperature screening.

## 9. Margin summary

| Component | MS | Status |
|---|---|---|
| Lower spar cap (tension, root) | +0.360 | PASS |
| Upper spar cap (compression, root) | +0.196 | PASS |
| Spar web (shear, two webs) | +0.557 | PASS |
| Upper skin panel (compression buckling, between stringers) | +0.093 | PASS |
| Upper stringer (column over rib pitch) | +0.196 | PASS |
| Wing root lug (vertical shear, one lug of pair) | +2.259 | PASS |

---
*Generated by Aero Agent Roles structures-loads-engineer core (2026-09-05). DRAFT for human stress lead review. Not an approval document - no certification approval is claimed, no compliance finding is declared. FEM results are as good as the model idealizations stated above.*
