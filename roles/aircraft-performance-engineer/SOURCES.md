# SOURCES.md - Aircraft Performance Engineer

Standards and documents this role references. Summary-not-copy: see
[STANDARDS.md](../../STANDARDS.md) for the full rule. FAR-25 and FAR-29
are US government work in the public domain, but the repo treats every
mapped standard reference-only: only names, paraphrases and short
attributed quotes appear, never reproduced text.

| Source | Role use | Gated |
|---|---|---|
| 14 CFR Part 25 (FAR-25) | airplane performance context for the engine-out balanced field length method (the FAR-25.113 35-ft obstacle convention) and the turboprop cruise fuel-planning context | true |
| 14 CFR Part 29 (FAR-29) | transport-category rotorcraft certification context for the seven rotorcraft leaves (sizing, flap/lag dynamics, hover IGE, descent, turn, fuel closure) | true |
| NASA TP-2005-213477 | public-domain empirical-inflow context marking the vortex-ring band momentum-invalid in axial descent (named, not reproduced) | false |

## Bound AeroSkills leaves (flight-mechanics/performance) and the real rule each contributes

Every number in the report comes from the same formulas the bound
leaf logic modules encode for their reference cases (each leaf is
Apache-2.0; the formulas are standard engineering methodology,
summary-only). The role engine recomputes the leaf formulas
independently and the CLI dispatches each leaf logic module to
cross-check (evidence/provenance.json records core_value vs
skill_value and delta).

| Report section | Bound leaf | Real rule the leaf contributes (summary) |
|---|---|---|
| 2. Balanced field length (A-1) | balanced-field-length | T_OEI = T_all (n-1)/n; a = g0 (T - mu_roll W)/W; a_brake = g0 mu_brake; ASD = V1^2/(2 a_all) + V1 t_reaction + V1^2/(2 a_brake); AGD = V1^2/(2 a_all) + (V_LOF^2 - V1^2)/(2 a_oei) + V_LOF t_rotation + h_obs/gradient; balanced V1 = the quadratic root of ASD = AGD inside [0, V_LOF]; BFL = ASD(V1) = AGD(V1). Real anchors: balanced V1 77.2815 m/s, BFL 2138.10 m (35-ft obstacle = 10.668 m, 1 s reaction/rotation). |
| 3. Propeller cruise range (A-2) | propeller-range | R = (eta_p / (c_p g0)) (L/D) ln(m0/m1); 1 lb/(hp h) = 0.45359237/(745.6999*3600) kg/(W s); m1 = m0 (1 - f). Real anchor: 0.55 lb/hp/h, eta 0.80, L/D 12, 11500 to 10000 kg gives 1472.24 km. |
| 4. Main rotor sizing (H-2) | rotorcraft-main-rotor-sizing | T = m g0; A = T/DL_max; R = sqrt(A/pi); CT = T/(rho A Vtip^2) (= DL_max/(rho Vtip^2) at the ceiling); sigma = CT/(CT/sigma)_design; A_b = sigma A; c = A_b/(b R); M_tip = Vtip/a. Real anchor: 4500 kg at 350 Pa, 0.12 design point, 4 blades, 210 m/s gives R 6.3352 m, CT 0.006479, sigma 0.053990, c 0.2686 m, M 0.6171. |
| 5. Blade flap dynamics (H-3) | rotorcraft-blade-flapping-dynamics | I_beta = m_b R^2/3; gamma = rho a c R^4/I_beta (5-12 band); a0 = 0.5 gamma (theta0/4 - lambda/3); nu = sqrt(1 + 1.5 e/(1 - e)). Real anchor: 50 kg/6.0 m/0.5 m blade at theta0 0.170, lambda 0.050, e 0.05 gives gamma 7.58079, coning 0.09792 rad = 5.6103 deg, nu 1.03872. |
| 6. Lead-lag clearance (H-1) | rotorcraft-lead-lag-dynamics | nu_zeta = sqrt(1.5 e/(1 - e)) (e = 0 gives exactly 0); modes nu Omega/2pi, |1 - nu| Omega/2pi, (1 + nu) Omega/2pi; Omega* = 2 pi omega_F/|1 - nu|; clear/resonance-adjacent verdict on the clearance fraction vs margin 0.20. Real anchor: e 0.05, Omega 44 rad/s, 5.0 Hz airframe gives coincidence 43.6924 rad/s, verdict resonance-adjacent; 3.5 Hz airframe is clear. |
| 7. Hover in ground effect (H-1) | rotorcraft-hover-ground-effect | k_ige = 1 - (R/(4 z))^2 (z/R >= 0.5; 0.9375 at z/R = 1, 0.75 at 0.5); P_ideal = T v_h; P_profile = (1/8) rho sigma Cd0 A Vtip^3 unchanged; P_total_ige = k P_ideal k_ige + P_profile; OGE reference; margin; hover ceiling by bisection. Real anchor: 2200 kg, R 5.0 m, z 5.0 m gives k_ige 0.9375, IGE total 369230 W, OGE 385650 W, margin -9230 W at 360 kW, ceiling ~4.0 m. |
| 8. Axial descent states (H-1) | rotorcraft-axial-descent-flow-states | v_h = sqrt(T/(2 rho A)); states by w = Vd/v_h (0 hover, 0 < w < 2 vortex-ring band, w >= 2 windmill-brake); v_i = Vd/2 - sqrt((Vd/2)^2 - v_h^2); P = k T (-Vd + v_i) + P_profile (negative = rotor absorbs power); Q = P/Omega; torque-reversal c = P_profile/(k T) vs v_h. Real anchors: R 5.0 m/2200 kg gives v_h 10.5887 m/s; at Vd = 25 m/s v_i 5.8570 m/s, P -352017.6 W; at 30 m/s P -512828.7 W, Q -11655.2 N m at 44 rad/s; c 4.955 < v_h -> momentum-unreachable. |
| 9. Banked turn performance (H-1) | rotorcraft-turn-performance | T = n W; inflow n W = 2 rho A v_i sqrt(V^2 + v_i^2) (fixed-count bisection); P_i = k n W v_i; P_prof = (1/8) rho sigma Cd0 A Vtip^3; P_par = 0.5 rho V^3 f; sustained n_s inverts the total power vs available power; phi = acos(1/n); omega = g sqrt(n^2 - 1)/V; R_t = V^2/(g sqrt(n^2 - 1)). Real anchors: n = 2, 60 m/s total 599092 W (level total 460336 W); 600 kW sustains 2.00491 g at 60 m/s. |
| 10. Range/endurance closure (H-4) | rotorcraft-range-endurance | P = k_h W^1.5, k_h = 1/(FM sqrt(2 rho A)); hover endurance t = (2/(g0 c k_h)) (1/sqrt(W1) - 1/sqrt(W0)); SR = V/(g0 c P); cruise closure with P_avg = P_ref (W_avg/W_ref)^1.5: R = V (W0 - W1)/(g0 c P_avg), E = (W0 - W1)/(g0 c P_avg). Real anchors: 60000 N, 1500 kg fuel, R 8 m, FM 0.75 gives hover endurance 20927.3 s, cruise range 2433442 m at 80 m/s, endurance 33797.8 s at 60 m/s. |

Acquisition/extraction status: FAR-25 and FAR-29 are read directly
from eCFR (ecfr.gov, public). NASA TP-2005-213477 is public domain.
No proprietary publication text is reproduced anywhere in this role;
the methodology above is paraphrase-level standard practice as encoded
by the Apache-2.0 AeroSkills leaves.
