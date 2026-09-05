# Performance and S&C Analysis Report

**Aircraft:** AeroLine AT-78 (example transport configuration, 150-seat class)
**Assessment basis:** FAR/CS Part 25 performance context (25.121/25.125/25.181) and MIL-STD-1797A mode criteria by analogy (aircraft class III (large transport, MIL-STD-1797A classing); flight phase categories B and C (cruise and approach)).
**Status:** draft-for-review

## 1. Mission performance

**Cruise point:** FL350 (ISA -54 degC), M0.78, V = 231.3 m/s (450 kt TAS), MTOW. CL = 0.603, CD = 0.0351, L/D = 17.2; (L/D)max = 17.5 at CL* = 0.74. Input basis: MTOW 78,000 kg, cruise altitude FL350, M0.78, clean configuration, example class data.

- **Still-air range (Breguet):** R = (V/(TSFC*g))*(L/D)*ln(W0/W1) = **6,492 km (3,506 nm)** burning 17,160 kg over the cruise segment (78,000 -> 60,840 kg). Breguet assumptions stated: constant L/D = 17.2, constant TSFC = 1.55e-05 kg/(N s), still air, cruise configuration.
- **Loiter endurance (Breguet):** E = (1/(TSFC*g))*(L/D)*ln(W0/W1) = **1.56 h** on 3,000 kg hold fuel at L/D = 17.2.
- **Specific air range:** SAR = V*(L/D)/(TSFC*W) = **335.0 m/kg** (0.335 km/kg); 5,000 km sector fuel ~ 14,925 kg. SAR curve (same weight, M = 0.74/0.78/0.82): 0.74 M -> 0.323 km/kg (L/D 17.4), 0.78 M -> 0.335 km/kg (L/D 17.2), 0.82 M -> 0.344 km/kg (L/D 16.8).
- **Climb (MTOW, clean, all engines):** ROC(SL) = (T-D)V/W = **17.7 m/s (3,491 ft/min)** at 250 KCAS; ROC(FL350) = **6.50 m/s (1,280 ft/min)** (climb thrust scaled by sigma^0.7); time to climb SL->FL350 at mean ROC = **14.7 min**. ROC at FL410 = 3.19 m/s (628 ft/min); linear-lapse ceiling estimate ~45.9k ft (indicative; nonlinear refinement is an open item).
- **Takeoff (SL ISA, MTOW):** Vs = 141 kt; V_LOF = V2 = 1.2*Vs = 169 kt; estimated ground roll Sg = 1.44*W^2/(g*rho*S*CLmax*(T-mu*W)) = **1,499 m** (mu = 0.03, CLmax = 1.9). The FAR 25.113 takeoff distance demonstration (airborne segment to 35 ft, 1.15 factor) is a flight-test determination - open item for the takeoff leaf build.
- **Landing (SL ISA, MLW):** Vs = 112 kt, Vref = 1.3*Vs = 145 kt, touchdown = 138 kt; air distance over 50 ft 365 m + ground roll 511 m = 877 m actual; certified field length (FAR 25.125, x1.67) = **1,464 m**.
- **Glide (engine-out reference):** best glide L/D = 17.5 at 227 kt EAS; from FL350: glide range 187 km, sink 6.6 m/s, 27 min to sea level.
- **Turn (25 deg bank, cruise, MTOW):** n = 1/cos(phi) = 1.103; turn rate 1.13 deg/s; radius 11.7 km; sustained (yes: D_turn = 49,148 N vs cruise available 58,000 N).
- **Wind effects (enroute):** 40 kt headwind lowers groundspeed 231 -> 211 m/s (6.00 h -> 6.59 h on 5,000 km).

## 2. Safety performance

- **OEI second segment (FAR 25.121(b), one engine inoperative at V2, gear up):** T_oei = 110,000 N, L/D = 10.8, gradient = (T_oei - D)/W = **5.13%** vs the 2-engine minimum of **2.4%** -> meets.
- **Energy height / time to climb:** cruise energy height h_e = h + V^2/2g = **13,396 m** (44k ft), kinetic term 2,728 m of zoom-climb reserve; specific excess power equals ROC (steady unaccelerated) by identity.
- **Wind / windshear effects:** enroute headwind case above (wind-effects leaf). Windshear assessment needs a shear profile (windshear-analysis leaf) - **open item**.

## 3. Rotorcraft

Not applicable to this example (fixed-wing transport). For a rotary-wing vehicle the rotorcraft performance leaves (hover OGE/IGE, forward flight, autorotation, tail-rotor sizing, vertical climb) replace this section.

## 4. Stability

- **Longitudinal static stability:** stick-fixed neutral point h_np = h_ac_w + V_h*(a_t/a_w)*(1-d_eps/d_alpha) = 0.25 + 0.862*0.72*0.55 = **0.591 MAC** (V_h = 0.862). Static margin SM = h_np - h_cg: **fwd CG 27.1%**, **aft CG 15.1%** (minimum margin band 0.05 MAC; positive SM = stable).
- **Directional stability (build):** V_v = 0.051; Cn_beta(vt) = eta*V_v*a_vt*(1+k_s) = 0.179; total Cn_beta = **0.120/rad** (fuselage term -0.059) - directionally stable (Cn_beta > 0).
- **Lateral stability (build):** dihedral term Cl_beta(gamma) = -CL*Gamma = -0.055 at cruise CL; total Cl_beta = **-0.080/rad** (remainder -0.025, class data) - laterally stable (Cl_beta < 0).
- **Trim (linear model):** cruise CL_trim = 0.603, alpha_trim = 6.3 deg, elevator to trim -3.0 deg (limit +/-25 deg); approach CL_trim = 1.420, elevator to trim -14.0 deg. Linear-model values; the stabilizer/elevator split and flap Cm increments are trim-analysis + AVL stage items (open item).

## 5. Dynamic modes

| Mode | Condition | Frequency | Damping | Requirement | Result |
|---|---|---|---|---|---|
| short period | cruise FL350 aft CG | 1.10 rad/s (0.17 Hz) | zeta = 0.31 | FAR 25.181 heavily damped (zeta >= 0.3 band); MIL-STD-1797A cat B L1 zeta 0.30-2.00, freq floor 2.0 rad/s (n_alpha 9.1 g/rad, table-clamped) | damping L1, freq-limited -> Level 2 by analogy (FAR heavy damping met) |
| short period | cruise FL350 fwd CG | 1.44 rad/s | zeta = 0.24 | as above | damping below L2 floor 0.25 -> Level 3 by analogy; fwd-CG cruise damping open item |
| short period | approach aft CG | 0.77 rad/s | zeta = 0.57 | FAR 25.181; cat C L1 zeta 0.30-2.00, freq floor 2.0 rad/s | damping L1 -> Level 2 by analogy (frequency-limited) |
| short period | approach fwd CG | 0.96 rad/s | zeta = 0.46 | as above | Level 2 by analogy |
| phugoid | cruise FL350 | 0.0600 rad/s (T = 105 s) | zeta = 0.041 | FAR 25.181 not growing (zeta > 0); 1797A L1 zeta >= 0.04 | Level 1 (t_half 281 s, 2.7 cycles) |
| phugoid | approach | 0.1855 rad/s (T = 34 s) | zeta = 0.085 | as above | Level 1 |
| dutch roll | cruise FL350 | 0.92 rad/s (T = 6.8 s) | zeta = 0.099 (zeta*omega = 0.090) | FAR 25.181 positively damped; 1797A cat B L1 zeta >= 0.08 & zeta*omega >= 0.15 | stable (FAR ok); Level 2 by analogy - yaw damper need (GNC boundary) |
| dutch roll | approach | 0.54 rad/s (T = 11.7 s) | zeta = 0.187 (product 0.101) | 1797A cat C L1 as above | Level 2 by analogy |
| roll subsidence | cruise FL350 | tau = 1.35 s | - | 1797A cat B L1 tau <= 1.4 s | Level 1 |
| roll subsidence | approach | tau = 1.30 s | - | 1797A cat C L1 tau <= 1.0 s | Level 2 |
| spiral | cruise FL350 | lambda = -0.00365 1/s | - | 1797A L1 T2 >= 12 s (cat B); stable root passes | convergent, Level 1 |
| spiral | approach | lambda = -0.01128 1/s | - | 1797A L1 T2 >= 20 s (cat C) | convergent, Level 1 |

Short-period/phugoid frequency separation (omega_sp/omega_ph): 18x cruise, 4.1x approach (>= 5x ideal for the two-timescale split; well separated at cruise, tighter at approach - a full 4-DOF longitudinal root solve is an open item).

## 6. Control effectiveness

- Elevator authority for trim: cruise -3.0 deg, approach -14.0 deg of +/-25 deg limits (linear model; margins acceptable, verify in the AVL/6DOF stage - open item).
- Aileron reversal: requires wing torsional stiffness and aileron geometry (aileron-reversal leaf) - **open item**.
- Deep stall: example has a low-mounted tailplane; deep-stall analysis (deep-stall-analysis leaf) remains a verification item for the stall-characteristics campaign - open item.
- Spin: no spin demonstration is required for the FAR Part 25 transport category; the spin-recovery leaf applies to Part 23-class vehicles.

## 7. Handling qualities

- Mode-based assessment (MIL-STD-1797A summary by analogy, class III): longitudinal modes damped at the aft-CG design point (zeta_sp 0.57 approach, 0.31 cruise); Dutch roll positively damped but below the Level 1 product criterion -> production fitment of a yaw damper is expected (SAS design is the GNC role boundary).
- FAR 25.181 context: short period heavily damped (zeta >= 0.3 band met at the aft CG), phugoid not growing in amplitude (zeta > 0) - satisfied at the analyzed conditions; formal compliance is a flight-test demonstration, not an analytic finding (boundary).
- Cooper-Harper ratings are pilot-in-the-loop observations: they are NOT assigned analytically. The cooper-harper-rating leaf structures the evaluation campaign (simulator/flight) - open item. PIO/pitch-bandwidth criteria likewise require the closed-loop response (6DOF + pilot model) - open item.

## 8. Simulation

- Trajectory evidence in this report is the analytic energy/climb set of sections 1-2 (specific excess power = rate of climb identity, energy height, time-to-climb at mean ROC).
- Point-mass trajectory and 6-DOF simulation runs (point-mass-trajectory / six-dof-simulation leaves, JSBSim class tools) plus the AVL derivative build (stability-derivatives-avl leaf) are the deeper stages that replace the class-range derivative data - open items with the input basis recorded above.

## 9. Conclusions and open items

- Performance vs requirement: computed still-air range 6,492 km, cruise ROC 17.7 m/s at SL, takeoff ground roll 1,499 m, certified landing field 1,464 m - all in the class range for a 150-seat twin-engine transport at the stated assumptions (Breguet assumptions for range, example thrust ratings, dry runway).
- S&C vs requirement: static margin 15.1% (aft CG) positive; short-period damping meets the FAR 25.181 heavy-damping band at the aft-CG design point (zeta 0.57 approach / 0.31 cruise); all modes stable.
- Open items: (1) replace example class-range inputs with project data; (2) AVL derivative build and wind-tunnel/flight-data correlation; (3) takeoff distance/accelerate-stop demonstration inputs (takeoff leaf); (4) windshear profile analysis; (5) 6DOF/JSBSim trajectory and closed-loop handling checks; (6) stabilizer scheduling and elevator authority verification; (7) fwd-CG cruise pitch damping margin; (8) yaw damper authority (GNC role).

---
*Generated by Aero Agent Roles flight-mechanics-engineer core (2026-09-05). Every number above carries its stated input basis (mass, CG, altitude, configuration, assumptions). DRAFT for human flight-mechanics review - engineering assessment, not an approval or certification finding.*