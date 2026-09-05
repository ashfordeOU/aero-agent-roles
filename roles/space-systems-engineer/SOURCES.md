# SOURCES.md - Space Systems Engineer

Standards and documents this role references. Summary-not-copy: see
[STANDARDS.md](../../STANDARDS.md) for the full rule and purchase links.

## Standards / references

| Source | Role use | Gated |
|---|---|---|
| ECSS-E-ST-10, E-ST-32, E-ST-33, E-ST-40, Q-ST-80 | systems/software engineering + product assurance context | true |
| Wertz et al., Space Mission Analysis and Design (SMAD) | mission design, margin policy, disturbance model (book) | true |
| Vallado, Fundamentals of Astrodynamics and Applications | astrodynamics methods: vis-viva, Hohmann, Kepler (book) | true |
| Larson & Wertz, Space Mission Analysis and Design | subsystem sizing conventions (book) | true |
| NASA GEVS / NPR | environment and test practice (informational) | false |

## Domain rules encoded in core/space_systems_core.py

Every number the engine produces follows a REAL relation exercised by
the bound AeroSkills space-systems leaves (same formulas, reimplemented
stdlib-only so the role is standalone). Anchor values in
tests/test_space_systems_engineer_core.py are the leaves' own worked
examples.

| Rule | Formula | Source leaf |
|---|---|---|
| Circular orbit velocity | v = sqrt(mu/r) | space-systems/orbit-mechanics/hohmann-transfer |
| Orbit period | T = 2*pi*sqrt(r^3/mu) | hohmann-transfer / kepler-orbit-propagation |
| Hohmann transfer delta-v | dv = dv1 + dv2 (two burns, vis-viva) | hohmann-transfer |
| Disposal perigee-lowering burn | single retrograde burn, vis-viva | hohmann-transfer pattern, ECSS-E-ST-33 disposal practice |
| Delta-v budget + margin | sum contributions; dv*(1+margin) | mission-design/mission-delta-v-budget |
| Propellant mass (rocket equation) | m_prop = m_dry*(exp(dv/(Isp*g0)) - 1) | mission-delta-v-budget |
| Eclipse fraction/time (beta = 0) | f = asin(Re/r)/pi; t = f*T | orbit-mechanics/eclipse-time |
| Battery capacity | C = P*T_ecl/(DoD*efficiency) | subsystems/power-thermal-budget, spacecraft-battery-sizing |
| Solar array daylight power | P/(eff*(1-f))*(1+margin) | power-thermal-budget |
| Array EOL specific power + area | p_eol = G*eta*PF*(1-r)^n; A = P/p_eol | subsystems/solar-array-sizing |
| Radiator area | A = Q/(eps*sigma*(T^4 - T_sink^4)) | subsystems/thermal-design |
| Reaction wheel momentum sizing | h_slew = J*omega; h_wheel = J_w*omega_max | adcs/reaction-wheel-control, attitude-control-sizing |
| Pointing error budget | RSS of 3-sigma contributors vs requirement | adcs/pointing-error-budget |
| Link budget (Friis) | L_fs, EIRP, C/N0, Eb/N0 margin | subsystems/communication-link-budget |
| Tank sizing | V = m/rho, ullage, t = p*r/(2*sigma) | subsystems/propellant-tank-sizing |

Conservative stated inputs (margin 15% on delta-v, 20% array margin, 30%
battery DoD, 3 dB link requirement, 0.1 deg 3-sigma pointing) follow SMAD
margin practice and are cited as design inputs in the report; the engine
does not invent an allowable or a factor.

The template in `templates/space-systems-template.md` is the generated
worked example (Aurora-1, 600 km SSO): REAL delta-v, propellant, wheel,
array, battery, radiator, and link numbers - zero blanks.
