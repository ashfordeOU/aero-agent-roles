# SOURCES.md - ADCS Engineer

Standards and reference documents this role builds on. Summary-not-copy:
see [STANDARDS.md](../../STANDARDS.md) for the full rule and purchase
links.

| Source | Role use | Gated |
|---|---|---|
| ECSS engineering standards (E-ST-10 system engineering, E-ST-60 spacecraft control / ADCS, E-ST-32/33/40, Q-ST-80) | mission/ADCS context and engineering-process framing | true |
| Aero Agent Skills space-systems/adcs leaves (14) | per-stage domain methods: TRIAD/QUEST determination, Allan-variance gyro noise, reaction wheel / magnetorquer control laws, pointing error budget assembly, disturbance torques, CMG/RCS/gravity-gradient screens | n/a (repo skill content) |
| IEEE Std 952 (IEEE standard specification format for gyro tests) | overlapping Allan deviation method and angle random walk convention (paraphrased method, no text reproduced) | n/a (method reference) |
| Wertz, "Spacecraft Attitude Determination and Control" (public-practice summary knowledge) | vector-observation attitude determination, control law and momentum management conventions | n/a (book reference) |

The ADCS report template in `templates/` is an original structure
synthesized from the standard engineering workflow above; every formula
it renders (orbit mean motion, TRIAD/QUEST, Allan deviation, PD control
law, torque = m x B dipole projection, RSS error budget) is the same
public engineering rule encoded in the bound AeroSkills leaves, which
the CLI dispatches for cross-checking when the library is present.
ECSS text is never reproduced. All worked-example inputs (inertia,
wheel limits, component error specs, disturbance torque) are labeled
project facts/assumptions in the deliverable itself.
