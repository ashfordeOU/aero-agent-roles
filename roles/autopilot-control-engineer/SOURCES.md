# SOURCES.md - Autopilot Control Engineer

Standards and documents this role references. Summary-not-copy: see
[STANDARDS.md](../../STANDARDS.md) for the full rule and purchase links.

| Source | Role use | Gated |
|---|---|---|
| MIL-STD-1797A, Flying Qualities of Piloted Aircraft | handling-qualities framing context for the attitude loops; reference-only | true |
| Aero Agent Skills gnc-autonomy/control leaves (12) | the domain rules the core implements: state-space analysis, PID pole placement, root-locus design, frequency-response margins, observer design, L1 adaptive control, gain scheduling, digital control design, control allocation | false |

The control relations encoded in
`core/autopilot_control_engineer_core.py` are standard control-
engineering methodology as carried by the bound Aero Agent Skills logic
files:

| Rule | Formula | Bound leaf |
|---|---|---|
| Companion-form realization + eigenvalues | A = [[0,1],[-a0,-a1]]; lambda = (tr +/- sqrt(tr^2-4det))/2 | control/state-space-analysis |
| PID pole placement | match (s^2+2 zeta wn s+wn^2)(s+p3) to plant b/(s^2+a1 s+a0) | control/pid-control-design |
| Second-order bandwidth factor | w_bw = f(zeta) wn, f = sqrt(1-2z^2+sqrt(2-4z^2+4z^4)) | control/frequency-response-design |
| Type-1 loop margins | L(s) = K/(s(s+a)): PM = 90-atan(wc/a), GM = inf | control/pid-control-design, python-control-design |
| General loop margins | bisection for 0 dB / -180 deg crossings on jw | control/frequency-response-design |
| Root locus (type-1 canonical plant) | s^2+a s+K = 0; K = a^2/(4 zeta^2) for target damping | control/root-locus-design |
| Observer gain (Ackermann, 2-state) | L = phi(A) O^-1 e_2 | control/observer-design |
| L1 adaptive control (scalar sigma-only) | state predictor, projection adaptation law, low-pass filter C(s)=omega_c/(s+omega_c) | control/l1-adaptive-control, control/adaptive-control |
| Gain schedule interpolation + rate limiting | linear breakpoint interpolation; step clamp +/- max_rate*dt | control/gain-scheduling |
| ZOH discretization | A_d = exp(-a T), B_d = 1 - A_d | control/digital-control-design |
| Minimum sample-rate rule | w_s,min = 10 wb, T_max = 2 pi / w_s,min | control/digital-control-design |
| Minimum-norm pseudoinverse allocation | u = B^T (B B^T)^-1 m | control/control-allocation |

The L1 adaptive-control implementation is a direct port of the scalar
sigma-only specialization in gnc-autonomy/control/l1-adaptive-control
(same equations, same discrete Euler step ordering), which in turn
follows Cao and Hovakimyan, *L1 Adaptive Control Theory*, SIAM 2010,
chapter 2. Reference-typical plant, gain-schedule and effector
parameters are documented assumptions in the report, never vendor
data. No proprietary standard text is reproduced; summaries and
original structures only.
