# SOURCES.md - GNC Engineer

| Source | Role use | Gated |
|---|---|---|
| MIL-STD-1797A | handling qualities context (Level-1 margins/bandwidth context where HQ applies) | false |
| Stevens & Lewis, Aircraft Control and Simulation | control methods (book) | true |
| Tewari, Modern Control Design | control reference (book) | true |
| Groves, Principles of GNSS, Inertial, and Multisensor Navigation | navigation reference (book) | true |
| Vallado, Fundamentals of Astrodynamics | orbit methods (book) | true |

Summary-not-copy per STANDARDS.md.

## Encoded domain rules (computed by core/gnc_core.py)

The engine's numbers come from the textbook methods carried by the
bound Aero Agent Skills leaves (which encode the books above as
practice); no standard text is reproduced:

| Rule | Formula | Bound leaf |
|---|---|---|
| Second-order bandwidth | w_bw = f(z) wn, f(z) = sqrt(1-2z^2+sqrt(2-4z^2+4z^4)) | control/frequency-response-design |
| PID pole placement | match (s^2+2zwn s+wn^2)(s+p3) to plant b/(s^2+a1 s+a0) | control/pid-control-design |
| Type-1 loop margins | L = K/(s(s+a)): PM = 90-atan(wc/a), GM = inf | control/pid-control-design |
| Loop margins (general) | |L(jw)| and root-sum unwrapped phase on jw | control/frequency-response-design |
| LQR | K = R^-1 B' P from the ARE closed form | optimal-control/lqr-design |
| Kalman steady state | P = Riccati root, K = hP/(h^2P+r) | navigation/kalman-filter-design |
| Observer | L = phi(A) O^-1 e_n (Ackermann, 2-state) | control/observer-design |
| Guidance | a_c = N Vc lam_dot | guidance/pursuit-guidance |
| Digital | 10-20 samples per closed-loop cycle; velocity-form PID | control/digital-control-design |

Margins requirements (PM >= 45 deg, GM >= 6 dB) are the conventional
flight-control design targets recorded as project requirements in the
example; MIL-STD-1797A adds handling-qualities context where the
program requires it. All example plant/sensor numbers are stated
project facts (verify against the vehicle data).
