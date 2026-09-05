# SOURCES.md - Guidance Engineer

| Source | Role use | Gated |
|---|---|---|
| ARP4754A | development-assurance context framing the guidance cluster leaves (reference only) | true |
| FAR-25 / CS-25 | airworthiness context where guided-vehicle development touches civil certification (reference only) | false |
| Zarchan, Tactical and Strategic Missile Guidance (AIAA) | classical PN/APN/ZEM guidance-law context (book, summarized via leaves) | true |
| Siouris, Missile Guidance and Control Systems | pursuit/CLOS/guidance-loop context (book, summarized via leaves) | true |

Summary-not-copy per STANDARDS.md. The guidance laws themselves are
common knowledge encoded by the bound Aero Agent Skills leaves; no
standard or book text is reproduced.

## Encoded domain rules (computed by core/guidance_core.py)

The engine's numbers come from the laws carried by the bound
gnc-autonomy/guidance leaves (each leaf is a paraphrase of common
guidance knowledge); anchors are asserted in the leaf gate-3 contract
tests and reproduced here:

| Rule | Formula | Bound leaf | Anchor |
|---|---|---|---|
| Closing velocity | vc = -(rx*vx + ry*vy) / r | guidance/proportional-navigation | 199.007 m/s |
| LOS rate | lam_dot = (rx*vy - ry*vx) / r^2 | guidance/proportional-navigation | 0.019802 rad/s |
| PN command | a_c = N * vc * lam_dot | guidance/proportional-navigation | 15.762965 m/s^2 (N=4) |
| APN command | a_apn = N' * (Vc*lam_dot + a_T/2), N' = 4 default | guidance/augmented-proportional-navigation | 55.763 m/s^2 |
| Acceleration in g | a / g0, g0 = 9.80665 | guidance/augmented-proportional-navigation | 1.607 g |
| Pursuit heading error | eta = wrap(lam - psi) | guidance/pursuit-guidance | 5.711 deg |
| Pursuit lead angle | asin((Vt/Vi) sin(beta)) | guidance/pursuit-guidance | -1.901 deg |
| Capture condition | Vi > Vt | guidance/pursuit-guidance | satisfied |
| Tail-chase intercept | t_i = r / (Vi - Vt) | guidance/pursuit-guidance | 5.025 s |
| Desired course (waypoint) | psi_d = atan2(wy - py, wx - px) | guidance/midcourse-guidance | 26.565 deg |
| Turn-rate-limited steering | psi_c = psi + clamp(e, +/-omega*dt) | guidance/midcourse-guidance | 5 deg per step |
| Velocity to be gained | vgo = max(0, V_target - V cos(e)) | guidance/midcourse-guidance | 65.08 m/s |
| Zero-effort miss | ZEM = \|rho + v_rel t_go\|, t_go = max(0, -(rho.v_rel)/\|v_rel\|^2) | guidance/midcourse-guidance | 150 m at t_go 20 s |
| Miss requirement check | ZEM <= required miss distance | guidance/midcourse-guidance | 10 m req (example) |
| Acceleration limit | utilization = \|a_c\| / (limit_g * g0) | guidance/augmented-proportional-navigation | 5.4% PN / 19.0% APN |

All example engagement numbers (speeds, ranges, limits, requirements)
are stated project facts for the reference item — verify against the
vehicle and target data before use. Navigation constant band 3-5 with
4 as the common baseline is the leaf-encoded practice note; the
selected N remains a project decision recorded in the report.
