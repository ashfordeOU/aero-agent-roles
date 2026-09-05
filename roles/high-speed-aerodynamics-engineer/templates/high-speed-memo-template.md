# High-Speed Aerodynamic Analysis Memo

**Vehicle:** HSX-1 supersonic cruiser (reference flight condition)
**Status:** draft-for-review (generated 2026-09-05)

## 1. Flight condition summary

- Vehicle: HSX-1 supersonic cruiser (reference flight condition) - Mach 2.0 supersonic transport configuration, subsonic-leading-edge swept wing, mixed-compression intake, high-temperature aluminium airframe
- Flight condition: cruise M 2.00 at 18288 m; transonic climb check M 0.85 at 12192 m
- ISA state at cruise: T 216.65 K, p 7172 Pa, rho 0.1153 kg/m3, a 295.07 m/s, mu 1.42e-05 kg/(m s)
- Flow state: V = M a = 590.1 m/s, q = 20081 Pa
- Configuration: swept wing (subsonic leading edge, sweep 66 deg), mixed-compression intake (ramp deflection 10.0 deg), equivalent body length 62 m

## 2. Freestream total conditions and Mach-area

- Isentropic total-to-static ratios at M 2.00: T0/T = 1.8000, p0/p = 7.8244, rho0/rho = 4.3469
- Total conditions (isentropic, no shock): p0 = 56114 Pa, T0 = 389.97 K
- Mach-area: A/A* at M 2.00 = 1.6875 (throat needed for isentropic capture); subsonic-branch root for the same ratio M = 0.3722
- Use: intake contraction and nozzle expansion sizing (isentropic-flow-relations stage).

## 3. Compressibility corrections and transonic limit

- Karman-Tsien corrected peak suction at M 0.70: Cp = -0.55 / (sqrt(1-M^2) + (M^2/(1+sqrt(1-M^2))) x Cp/2) = -0.8654 (vs Prandtl-Glauert -0.7702)
- Critical pressure coefficient at climb M 0.85: Cp* = -0.3020
- Section critical Mach from Cp0 = -0.55: M_cr = 0.7017 (Cp* crossing solve)
- Sweep effect: M_eff = M cos(Lambda): climb M 0.85 x cos(66 deg) = 0.3457; cruise M_eff = 0.8135 (subsonic leading edge)
- Korn drag-divergence Mach (t/c 0.030, cruise CL 0.12): M_DD = 0.908; transonic wave-drag penalty at climb M 0.85 = 0.0000 (0 below M_DD), parabolic rise 0.0000
- Terminating-shock strength at local M 1.30: p2/p1 = 1.8050
- Transonic similarity parameter K = (1 - M^2)/tau^(2/3) = 2.874

## 4. Shock system at the cruise Mach

- Normal shock at nose/inlet face, M1 = 2.00: M2 = 0.5774, p2/p1 = 4.5000, T2/T1 = 1.6875, rho2/rho1 = 2.6667, p02/p01 = 0.7209
- Intake ramp oblique shock, theta = 10.0 deg at M 2.00 (weak): beta = 39.31 deg, M2 = 1.641, p2/p1 = 1.7066, p02/p01 = 0.9846; theta_max = 22.97 deg
- Terminal normal shock at M2 = 1.641: p02/p01 = 0.8797
- Intake recovery: 2-shock p02/p01 = 0.8662 vs single normal shock 0.7209 (gain +0.1453)
- Regular shock reflection at (M 1.641, theta 10.0 deg): verdict mach (required reflected deflection reaches the reflected-shock detachment limit at M2 (or M2 <= 1): Mach reflection)
- Aft expansion (Prandtl-Meyer), turn 10.0 deg from M 1.641: M = 1.988, p2/p1 = 0.5875
- Detached bow shock at the nose (sphere, R = 0.050 m): standoff Delta = 0.0161 m (Billig correlation, Delta/R = 0.3215)

## 5. Supersonic section analysis and wave drag

- Shock-expansion diamond airfoil at M 2.00, alpha 2.0 deg, half-angle 2.0 deg: cl = 0.0808, cd_wave = 0.00565, cm_le = 0.0387
- Surface Cp (uf/ur/lf/lr): 0.0000 / -0.0738 / 0.0881 / 0.0000
- Zero-lift wave drag area (Sears-Haack equivalent body, L = 62 m, r_max = 1.6 m): D/q = (9 pi/2)(A_max/L)^2 = 0.2379 m2

## 6. Boundary layer and skin friction

- Station x = 6.0 m at cruise: Re = rho V x / mu = 2.872e+07 (turbulent flat-plate regime)
- Flat-plate thickness: delta = 0.07157 m, delta* = 0.00895 m, theta = 0.00696 m, H = 1.286
- Skin friction: Cf_local = 0.00191 (1/7 power), Cf_avg = 0.00239, log-law Cf = 0.00255
- Transition: Michel/Thwaites flat-plate natural transition at x_tr = 0.349 m (6% of the analysis station)
- Attachment-line (Hiemenz 2-D) layer at the nose: a = 2U/R = 23606 1/s, delta = 0.000173 m, Cf = 0.00713
- Surface roughness: k_s = 6.0e-06 m -> k+ = 0.887 (smooth; smooth retained below k+ = 5)

## 7. Aerodynamic heating screen

- Stagnation point (Sutton-Graves): q_s = C_SG sqrt(rho/Rn) V^3 = 57119 W/m2; radiation-equilibrium T = 1043 K (eps 0.85)
- Flat-plate skin: recovery factor r = Pr^(1/3) = 0.8921 (turbulent); adiabatic wall temperature T_aw = T (1 + r (g-1)/2 M^2) = 371.3 K
- Cold-wall skin flux at x = 6.0 m (Eckert reference temp, T_wall 300 K): q = 3838 W/m2, Cf = 0.00213 at Re* = 1.668e+07
- Screening margins: skin 51.7 K below the 423 K limit; nose 210 K below the 600 K limit

## 8. Margin summary

| Margin | Value | Requirement | Source (stage) |
|---|---|---|---|
| Intake total-pressure recovery (2-shock system) | 0.8662 | > single normal-shock recovery 0.7209 at M 2.00 | stage 4: ramp oblique p02/p01 0.98464 x terminal normal p02/p01 0.87972 |
| Oblique-shock attachment margin (theta_max - theta) | 12.9735 | > 0 deg (attached weak shock; detached above) | stage 4: theta_max 22.97 deg at M 2.00 (oblique-shock leaf) |
| Section drag-divergence margin at cruise (M_DD - M_eff,cruise) | 0.0945 | > 0 (supercritical section subcritical at the cruise effective Mach M_eff 0.813) | stage 7: Korn rule M_DD = 0.908 (t/c 0.030, CL 0.12, supercritical) vs swept section M_eff = M cos(Lambda) |
| Section critical-Mach margin at climb (M_cr,section - M_eff,climb) | 0.3560 | > 0 (wing section subcritical through the transonic climb leg, M_eff 0.346) | stage 3: Cp* crossing M_cr = 0.702 for Cp0 = -0.55; climb M_eff = M cos(Lambda) = 0.346 |
| Skin kinetic-heating margin (T_limit - T_aw) | 51.7291 | > 0 (skin screening limit 423 K vs recovery temp) | stage 10: T_aw = T (1 + r (g-1)/2 M^2) = 371.3 K at M 2.00, recovery r = 0.8921 |
| Nose stagnation-temperature margin (T_limit - T0) | 210.0300 | > 0 (nose screening limit 600 K vs stagnation-line recovery temperature T0) | stage 10: T0 = T (1 + (g-1)/2 M^2) = 390.0 K at M 2.00 (hot-wall ceiling; Sutton-Graves cold-wall flux 57119 W/m2 screened separately) |

---
*DRAFT - for human high-speed aerodynamics lead review. Not an approval document.*