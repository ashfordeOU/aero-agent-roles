# SOURCES.md - Stability and Control Flight Test Engineer

Standards and documents this role references. Summary-not-copy: see
[STANDARDS.md](../../STANDARDS.md) for the full rule and purchase links.

| Source | Role use | Gated |
|---|---|---|
| 14 CFR Part 25 (FAR-25) | demonstration context the bound leaves paraphrase: static longitudinal stability (trim, neutral point, static margin over the approved CG range), static lateral-directional stability (weathercock/dihedral criteria), dynamic stability (short period and Dutch roll oscillations damped, phugoid not divergent), control force characteristics. Public regulation, cited by name and section only, never reproduced. | true |
| EASA CS-25 | EASA mirror of the Part 25 stability and control demonstration context, cited reference-only. | true |

## Grounding in the bound AeroSkills leaves

Every formula, practice band and reduction convention in the role core
comes from the four bound leaves under `flight-test-operations/
stability/` in the Aero Agent Skills repo (pinned skills_release
v1.3.0+, read from `~/AeroSkills` when present):

| Leaf | Real rule it contributes (summary) |
|---|---|
| static-stability-flight-test | trim curve reduction delta_e = a + b CL by least squares (CL = 2 W / (rho V^2 S)); stick fixed neutral point h_n = h + b Cm_delta_e (pi/180) with static margin h_n - h (positive stable); stick free neutral point shifted by (Cm_delta_e Ch_alpha)/(CL_alpha Ch_delta_e); elevator angle per g (180/pi) CL SM / Cm_delta_e |
| dynamic-stability-flight-test | excitation per mode (elevator doublet short period, elevator pulse phugoid, rudder pulse Dutch roll, rudder step spiral); log decrement delta = (1/n) ln(A0/An); damping ratio zeta = delta/sqrt(delta^2 + 4 pi^2); w_d = 2 pi/T_d; w_n = w_d/sqrt(1 - zeta^2); t_half = ln 2/(zeta w_n); N = ln 2/(2 pi zeta); practice verdict bands (short period 0.3-2.0 acceptable ..., spiral convergent) |
| lateral-directional-stability-flight-test | steady-heading sideslip sweep matrix (constant CAS, beta inside +-15 deg); rudder/aileron/pedal-force gradients d(delta_r)/d(beta), d(delta_a)/d(beta), d(F_pedal)/d(beta) by least squares; signed estimates Cn_beta = -cn_dr s_r and Cl_beta = -cl_da s_a with declared control powers (inputs, never measured); weathercock stable when Cn_beta > 0, dihedral stable when Cl_beta < 0 |
| control-force-flight-test | force transducer calibration by closed-form least squares (applied load vs counts); stick force gradient vs KCAS with stable-gradient verdict when slope > 0 (pull positive); stick force per g from pull-ups; breakout force = (pull - push)/2 hysteresis half-width; centering margin = limit - residual |

The report template in `templates/` is an original structure generated
by the role core. The practice band values (e.g. short period
0.3-2.0 acceptable) are typical flight test practice as encoded by the
leaves - the certification criteria in the cited standards take
precedence. No proprietary or copyrighted text is reproduced; FAR/CS
public text is referenced by name and section only (summary-not-copy).

## Acquisition / verification status

- far-25: public regulation (ecfr.gov); referenced context only.
- cs-25: EASA public certification specification (easa.europa.eu);
  referenced context only.
- Leaf formulas verified against each leaf's own contract test file
  (`scripts/test_<leaf>.py`) values and re-verified by the role's
  skill-dispatch cross-checks (provenance.json delta 0 on the worked
  example) when AeroSkills is present.
