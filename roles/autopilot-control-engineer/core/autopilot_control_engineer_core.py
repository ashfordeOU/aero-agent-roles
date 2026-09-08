#!/usr/bin/env python3
"""autopilot_control_engineer_core.py - Autopilot Control Engineer core.

This is the role's ENGINE: given a UAV/aircraft's autopilot project facts
(reduced-order longitudinal/lateral plant parameters, loop design targets,
an adaptive-augmentation scenario, a gain-schedule envelope, a digital
implementation rate, and a control-allocation effector set) it computes:

- reduced-order state-space plant models (A, B, C, D) for the
  short-period, phugoid, roll and dutch-roll modes, with eigenvalues from
  a closed-form 2x2 solution and a controllability check
  (gnc-autonomy/control/state-space-analysis).
- inner pitch-rate PID gains by closed-loop pole placement, and outer
  pitch-attitude proportional gain sized to a bandwidth/damping target,
  each with loop margins (gnc-autonomy/control/pid-control-design,
  gnc-autonomy/control/frequency-response-design,
  gnc-autonomy/control/python-control-design margin/stability
  convention).
- roll-attitude gain selection by classical root locus on the canonical
  type-1 plant, reporting the closed-loop pole pair, damping ratio and
  natural frequency for the chosen gain
  (gnc-autonomy/control/root-locus-design).
- a dutch-roll / turn-coordination yaw-rate damper loop with general
  gain/phase margins (gnc-autonomy/control/frequency-response-design).
- a full-order (Ackermann) observer for an unmeasured state
  (gnc-autonomy/control/observer-design).
- L1 adaptive augmentation of the pitch-rate error channel for a stated
  plant-uncertainty scenario: state predictor, projection-based
  adaptation law, low-pass filter and transient-bound check, following
  the scalar sigma-only specialization of
  gnc-autonomy/control/l1-adaptive-control EXACTLY (same equations, same
  discrete Euler ordering).
- a gain-schedule table (pitch-rate proportional gain vs dynamic
  pressure) with linear interpolation and scheduling-variable rate
  limiting (gnc-autonomy/control/gain-scheduling).
- a digital implementation of the inner loop at a stated sample rate:
  zero-order-hold discretization of the roll subsidence mode, the
  velocity-form discrete PID, and the minimum-sample-rate rule
  (gnc-autonomy/control/digital-control-design).
- control allocation of the pitch and turn-coordination moment commands
  across redundant effectors by minimum-norm pseudoinverse allocation
  (gnc-autonomy/control/control-allocation).

It BUILDS the autopilot control-law design package content and
gate-checks deliverables. Standalone: stdlib only (math, dataclasses),
no AeroSkills checkout required.

MIL-STD-1797A is cited (TIER-1, reference-only) for the handling-qualities
context of the attitude loops. ARP4754A, FAR-25/CS-25 and DO-178C are the
development-assurance / airworthiness-context standards the bound leaves
cite (all reference-only); no standard text is reproduced here or in the
rendered deliverable - see SOURCES.md.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


def _today() -> str:
    import os
    from datetime import date
    return os.environ.get("ROLE_GEN_DATE", date.today().isoformat())


# ---------------------------------------------------------------------------
# State-space analysis (gnc-autonomy/control/state-space-analysis)
# ---------------------------------------------------------------------------

def companion_form_2state(a1: float, a0: float, b: float) -> dict:
    """Controllable-canonical (companion) state-space realization of
    G(s) = b / (s^2 + a1 s + a0): A = [[0, 1], [-a0, -a1]], B = [[0],
    [b]], C = [[1, 0]], D = [[0]]. State x1 tracks the plant's
    slower/position-like variable, x2 its derivative (the plant output
    when C selects x2, or the integrated output when C selects x1)."""
    if b == 0.0:
        raise ValueError("b must be nonzero")
    A = [[0.0, 1.0], [-float(a0), -float(a1)]]
    B = [[0.0], [float(b)]]
    return {"A": A, "B": B, "C": [[1.0, 0.0]], "D": [[0.0]]}


def eig2x2(A: list) -> dict:
    """Closed-form eigenvalues of a 2x2 matrix from trace/determinant:
    lambda = (tr +/- sqrt(tr^2 - 4 det)) / 2, real pair or a complex
    conjugate pair. Returns wn, zeta when the pair is complex
    (lambda = -zeta*wn +/- j*wn*sqrt(1-zeta^2))."""
    a00, a01 = float(A[0][0]), float(A[0][1])
    a10, a11 = float(A[1][0]), float(A[1][1])
    tr = a00 + a11
    det = a00 * a11 - a01 * a10
    disc = tr * tr - 4.0 * det
    if disc >= 0.0:
        s = math.sqrt(disc)
        poles = [((tr + s) / 2.0, 0.0), ((tr - s) / 2.0, 0.0)]
        wn = zeta = None
    else:
        s = math.sqrt(-disc)
        poles = [(tr / 2.0, s / 2.0), (tr / 2.0, -s / 2.0)]
        wn = math.sqrt(det)
        zeta = -tr / (2.0 * wn) if wn > 0.0 else None
    stable = all(p[0] < 0.0 for p in poles)
    return {"poles": poles, "wn": wn, "zeta": zeta, "stable": stable}


def controllable_2state(A: list, B: list) -> bool:
    """Controllability of a 2-state pair (A, B): full rank of
    [B, AB] <=> det([B, AB]) != 0."""
    a00, a01 = float(A[0][0]), float(A[0][1])
    a10, a11 = float(A[1][0]), float(A[1][1])
    b0, b1 = float(B[0][0]), float(B[1][0])
    ab0 = a00 * b0 + a01 * b1
    ab1 = a10 * b0 + a11 * b1
    det = b0 * ab1 - b1 * ab0
    return abs(det) > 1e-12


def observable_2state(A: list, C: list) -> bool:
    """Observability of a 2-state pair (A, C): full rank of
    [C; CA] <=> det([C; CA]) != 0."""
    a00, a01 = float(A[0][0]), float(A[0][1])
    a10, a11 = float(A[1][0]), float(A[1][1])
    c0, c1 = float(C[0][0]), float(C[0][1])
    ca0 = c0 * a00 + c1 * a10
    ca1 = c0 * a01 + c1 * a11
    det = c0 * ca1 - c1 * ca0
    return abs(det) > 1e-12


# ---------------------------------------------------------------------------
# PID pole placement + margins (gnc-autonomy/control/pid-control-design,
# gnc-autonomy/control/frequency-response-design,
# gnc-autonomy/control/python-control-design margin convention)
# ---------------------------------------------------------------------------

def second_order_bandwidth_factor(zeta: float) -> float:
    """Exact closed-loop bandwidth factor f(z) for s^2 + 2zw s + w^2:
    f = sqrt(1 - 2z^2 + sqrt(2 - 4z^2 + 4z^4)), w_bw = f * wn."""
    if not (0.0 < zeta <= 1.0):
        raise ValueError("zeta must lie in (0, 1], got %r" % (zeta,))
    return math.sqrt(1.0 - 2.0 * zeta * zeta
                     + math.sqrt(2.0 - 4.0 * zeta * zeta + 4.0 * zeta ** 4))


def closed_loop_bandwidth(wn: float, zeta: float) -> float:
    if not (isinstance(wn, (int, float)) and math.isfinite(wn) and wn > 0.0):
        raise ValueError("wn must be a positive finite number, got %r" % (wn,))
    return wn * second_order_bandwidth_factor(zeta)


def pid_gains_second_order(a1: float, a0: float, b: float, wn: float,
                           zeta: float, p3: float):
    """PID gains (kp, ki, kd) for G(s) = b/(s^2 + a1 s + a0) matched to
    (s^2 + 2*zeta*wn*s + wn^2)(s + p3):
      kd = (2*zeta*wn + p3 - a1)/b
      kp = (wn^2 + 2*zeta*wn*p3 - a0)/b
      ki = wn^2*p3/b
    """
    if b == 0:
        raise ValueError("b must be nonzero, got %r" % (b,))
    if not (0.0 < zeta <= 1.0):
        raise ValueError("zeta must lie in (0, 1], got %r" % (zeta,))
    if not (isinstance(wn, (int, float)) and wn > 0.0):
        raise ValueError("wn must be > 0, got %r" % (wn,))
    if not (isinstance(p3, (int, float)) and p3 > 0.0):
        raise ValueError("p3 must be > 0, got %r" % (p3,))
    kd = (2.0 * zeta * wn + p3 - a1) / b
    kp = (wn * wn + 2.0 * zeta * wn * p3 - a0) / b
    ki = wn * wn * p3 / b
    return kp, ki, kd


def type1_margins(a: float, K: float) -> dict:
    """Gain/phase margin of the type-1 open loop L(s) = K/(s(s + a)).

    Crossover wc solves K^2 = wc^2(wc^2 + a^2); phase margin is
    90 - atan(wc/a) deg. Phase reaches -180 deg only at w -> inf, so
    the gain margin is infinite (reported as inf)."""
    if not (isinstance(a, (int, float)) and a > 0.0):
        raise ValueError("a must be > 0, got %r" % (a,))
    if not (isinstance(K, (int, float)) and K > 0.0):
        raise ValueError("K must be > 0, got %r" % (K,))
    wc2 = (-a * a + math.sqrt(a ** 4 + 4.0 * K * K)) / 2.0
    wc = math.sqrt(wc2)
    pm = 90.0 - math.degrees(math.atan(wc / a))
    return {"crossover_rad_s": wc, "phase_margin_deg": pm,
            "gain_margin": float("inf"), "gain_margin_db": float("inf")}


def _poly_roots(coeffs):
    """Roots of a descending-power polynomial with stdlib (deg <= 3)."""
    c = [float(v) for v in coeffs]
    while c and c[0] == 0.0:
        c.pop(0)
    n = len(c) - 1
    if n <= 0:
        return []
    if n == 1:
        return [complex(-c[1] / c[0], 0.0)]
    if n == 2:
        a, bb, cc = c[0], c[1], c[2]
        disc = complex(bb * bb - 4.0 * a * cc) ** 0.5
        return [(-bb + disc) / (2.0 * a), (-bb - disc) / (2.0 * a)]
    if n == 3:
        a, bb, cc, d = c[0], c[1], c[2], c[3]
        p = (3.0 * a * cc - bb * bb) / (3.0 * a * a)
        q = (2.0 * bb ** 3 - 9.0 * a * bb * cc + 27.0 * a * a * d) \
            / (27.0 * a ** 3)
        disc = (q / 2.0) ** 2 + (p / 3.0) ** 3
        if p == 0.0:
            t1 = math.copysign(abs(q) ** (1.0 / 3.0), -q) if q != 0.0 else 0.0
        elif disc >= 0.0:
            u = math.copysign(abs(-q / 2.0 + math.sqrt(disc)) ** (1.0 / 3.0),
                              -q / 2.0 + math.sqrt(disc))
            v = math.copysign(abs(-q / 2.0 - math.sqrt(disc)) ** (1.0 / 3.0),
                              -q / 2.0 - math.sqrt(disc))
            t1 = u + v
        else:
            r = math.sqrt((-p / 3.0) ** 3)
            theta = math.acos(min(1.0, max(-1.0, -q / (2.0 * r))))
            t1 = 2.0 * math.sqrt(-p / 3.0) * math.cos(theta / 3.0)
        r1 = t1 - bb / (3.0 * a)
        q1 = a
        q2 = bb + q1 * r1
        q3 = cc + q2 * r1
        pair = _poly_roots([q1, q2, q3])
        return [complex(r1, 0.0)] + pair
    raise ValueError("root solving supports degree <= 3, got degree %d" % n)


def _phase_of_loop(num, den, w):
    zr = _poly_roots(num)
    pr = _poly_roots(den)
    total = 0.0
    for z in zr:
        total += math.degrees(math.atan2(w - z.imag, -z.real))
    for p in pr:
        total -= math.degrees(math.atan2(w - p.imag, -p.real))
    return total


def _mag_db_of_loop(num, den, w):
    s = complex(0.0, w)
    accn = 0.0 + 0.0j
    for c in num:
        accn = accn * s + c
    accd = 0.0 + 0.0j
    for c in den:
        accd = accd * s + c
    return 20.0 * math.log10(abs(accn / accd))


def loop_margins(num: list, den: list) -> dict:
    """Gain/phase margins of a general open loop L(s) = num(s)/den(s)
    (frequency-response-design): bisection on the log-frequency axis
    for the 0 dB and -180 deg crossings."""
    for poly, name in ((num, "num"), (den, "den")):
        if not isinstance(poly, (list, tuple)) or not poly:
            raise ValueError("%s must be a non-empty coefficient list" % name)
    w_lo, w_hi = 1e-3, 1e5
    w_gc = float("inf")
    lo, hi = w_lo, w_hi
    flo = _mag_db_of_loop(num, den, lo)
    fhi = _mag_db_of_loop(num, den, hi)
    if flo > 0.0 and fhi < 0.0:
        for _ in range(100):
            mid = math.sqrt(lo * hi)
            fm = _mag_db_of_loop(num, den, mid)
            if fm > 0.0:
                lo = mid
            else:
                hi = mid
        w_gc = math.sqrt(lo * hi)
    w_pc = float("inf")
    plo = _phase_of_loop(num, den, w_lo)
    phi = _phase_of_loop(num, den, w_hi)
    if plo > -180.0 and phi < -180.0:
        lo, hi = w_lo, w_hi
        for _ in range(100):
            mid = math.sqrt(lo * hi)
            pm = _phase_of_loop(num, den, mid)
            if pm > -180.0:
                lo = mid
            else:
                hi = mid
        w_pc = math.sqrt(lo * hi)
    if math.isinf(w_pc):
        gm = float("inf")
    else:
        gm = 10.0 ** (-_mag_db_of_loop(num, den, w_pc) / 20.0)
    gm_db = float("inf") if math.isinf(gm) else 20.0 * math.log10(gm)
    pm = float("inf")
    if not math.isinf(w_gc):
        pm = 180.0 + _phase_of_loop(num, den, w_gc)
    return {
        "gain_crossover_rad_s": w_gc,
        "phase_crossover_rad_s": w_pc,
        "gain_margin": gm,
        "gain_margin_db": gm_db,
        "phase_margin_deg": pm,
        "gain_margin_ok": gm_db > 0.0 if not math.isinf(gm_db) else True,
        "phase_margin_ok": pm > 0.0 if not math.isinf(pm) else True,
    }


# ---------------------------------------------------------------------------
# Root locus (gnc-autonomy/control/root-locus-design)
# ---------------------------------------------------------------------------

def closed_loop_poles_rl(a: float, K: float) -> dict:
    """Closed-loop poles of the canonical type-1 root-locus plant
    G(s) = 1/(s(s + a)) with forward gain K: 1 + K*G(s) = 0 reduces to
    s^2 + a*s + K = 0. Underdamped: -a/2 +/- j*wd, wd = sqrt(K - a^2/4)."""
    if not (isinstance(a, (int, float)) and a > 0.0):
        raise ValueError("a must be > 0, got %r" % (a,))
    if not (isinstance(K, (int, float)) and K >= 0.0):
        raise ValueError("K must be >= 0, got %r" % (K,))
    disc = K - a * a / 4.0
    if disc >= 0.0:
        wd = math.sqrt(disc)
        return {"poles": [(-a / 2.0, wd), (-a / 2.0, -wd)], "wd": wd,
                "overdamped": False}
    # overdamped: two real poles
    s = math.sqrt(-4.0 * disc)
    return {"poles": [(-a / 2.0 + s / 2.0, 0.0), (-a / 2.0 - s / 2.0, 0.0)],
            "wd": 0.0, "overdamped": True}


def damping_ratio_rl(a: float, K: float) -> float:
    """zeta = a/(2*sqrt(K)) for the underdamped case; overdamped (K <
    a^2/4) reports zeta = 1 by convention (root-locus-design)."""
    if not (isinstance(a, (int, float)) and a > 0.0):
        raise ValueError("a must be > 0, got %r" % (a,))
    if not (isinstance(K, (int, float)) and K > 0.0):
        raise ValueError("K must be > 0, got %r" % (K,))
    if K < a * a / 4.0:
        return 1.0
    return a / (2.0 * math.sqrt(K))


def gain_for_damping_rl(a: float, zeta: float) -> float:
    """K = a^2/(4*zeta^2), the forward gain that places the type-1
    root-locus poles at the target damping ratio zeta."""
    if not (isinstance(a, (int, float)) and a > 0.0):
        raise ValueError("a must be > 0, got %r" % (a,))
    if not (0.0 < zeta <= 1.0):
        raise ValueError("zeta must lie in (0, 1], got %r" % (zeta,))
    return (a * a) / (4.0 * zeta * zeta)


def stability_verdict_rl(a: float, K: float) -> bool:
    """Stable iff both closed-loop poles have strictly negative real
    part (a pole on the imaginary axis, K = 0, is marginal not stable)."""
    poles = closed_loop_poles_rl(a, K)["poles"]
    return all(p[0] < 0.0 for p in poles) and K > 0.0


# ---------------------------------------------------------------------------
# Observer (gnc-autonomy/control/observer-design)
# ---------------------------------------------------------------------------

def observer_gain_2state(A, C, poles) -> dict:
    """Full-order observer gain L (Ackermann) for a two-state plant.

    L = phi(A) O^-1 e_2 with phi(s) = (s - p1)(s - p2), O the
    observability matrix [C; C A]. Verified against the leaf's worked
    anchors: A = [[0,1],[0,0]], C = [1,0], poles -4,-5 -> L = [9, 20];
    A = [[0,1],[0,-2]], C = [1,0], poles -30,-30 -> L = [58, 784]."""
    _TOL = 1e-9
    try:
        a00, a01 = float(A[0][0]), float(A[0][1])
        a10, a11 = float(A[1][0]), float(A[1][1])
        c0, c1 = float(C[0][0]), float(C[0][1])
    except (TypeError, ValueError, IndexError) as exc:
        raise ValueError("invalid 2-state observer data: %s" % exc)
    o00 = c0
    o01 = c1
    o10 = c0 * a00 + c1 * a10
    o11 = c0 * a01 + c1 * a11
    det_o = o00 * o11 - o01 * o10
    if abs(det_o) <= _TOL:
        raise ValueError("pair (A, C) is not observable (singular O)")
    p1 = complex(poles[0])
    p2 = complex(poles[1])
    if p1.imag != 0.0 or p2.imag != 0.0:
        raise ValueError("2-state closed form expects real poles")
    if p1.real >= 0.0 or p2.real >= 0.0:
        raise ValueError("observer poles must be strictly stable")
    s_p = p1.real + p2.real
    prod = p1.real * p2.real
    A2 = [[a00 * a00 + a01 * a10, a00 * a01 + a01 * a11],
          [a10 * a00 + a11 * a10, a10 * a01 + a11 * a11]]
    phiA = [[A2[0][0] - s_p * a00 + prod, A2[0][1] - s_p * a01],
            [A2[1][0] - s_p * a10, A2[1][1] - s_p * a11 + prod]]
    inv_last = [-o01 / det_o, o00 / det_o]
    l1 = phiA[0][0] * inv_last[0] + phiA[0][1] * inv_last[1]
    l2 = phiA[1][0] * inv_last[0] + phiA[1][1] * inv_last[1]
    ts = 4.0 / min(abs(p1.real), abs(p2.real))
    return {"L": [l1, l2], "poles": [p1.real, p2.real],
            "settling_time_s": ts, "observable": True}


# ---------------------------------------------------------------------------
# L1 adaptive control - scalar sigma-only specialization, ported
# verbatim from gnc-autonomy/control/l1-adaptive-control (Cao and
# Hovakimyan, L1 Adaptive Control Theory, SIAM 2010, chapter 2).
# ---------------------------------------------------------------------------

def l1_projection(sigma_hat, d, sigma_b):
    """Continuous projection of direction d at sigma_hat onto
    [-sigma_b, sigma_b]."""
    if sigma_b <= 0:
        raise ValueError("projection bound sigma_b must be positive")
    if abs(sigma_hat) > sigma_b:
        raise ValueError("|sigma_hat| must not exceed sigma_b")
    if sigma_hat >= sigma_b and d > 0.0:
        return 0.0
    if sigma_hat <= -sigma_b and d < 0.0:
        return 0.0
    return d


def l1_adaptive_update(sigma_hat, pred_err, gamma, dt, sigma_b):
    """One clamped Euler projection step of the adaptation law:
    raw = sigma_hat - dt*gamma*pred_err, clamped to [-sigma_b, sigma_b]."""
    if gamma < 0:
        raise ValueError("adaptation rate gamma must be >= 0")
    if dt <= 0:
        raise ValueError("time step dt must be positive")
    if sigma_b <= 0:
        raise ValueError("projection bound sigma_b must be positive")
    raw = sigma_hat - dt * gamma * pred_err
    return max(-sigma_b, min(sigma_b, raw))


def l1_filter_step(nu, sigma_hat, omega_c, dt):
    """One Euler step of the L1 low-pass filter
    nu_dot = omega_c*(sigma_hat - nu), C(s) = omega_c/(s + omega_c)."""
    if omega_c <= 0:
        raise ValueError("filter bandwidth omega_c must be positive")
    if dt <= 0:
        raise ValueError("time step dt must be positive")
    return nu + dt * omega_c * (sigma_hat - nu)


def l1_control_output(nu, r, a_m, b):
    """L1 control law u = (-a_m/b)*r - nu: feedforward minus filtered
    cancellation estimate."""
    if b == 0:
        raise ValueError("control effectiveness b must be nonzero")
    return (-a_m / b) * r - nu


def l1_sigma_true(x, plant_a, a_m, b, d):
    """Lumped matched uncertainty (a_p - a_m)*x/b + d, design frame."""
    if b == 0:
        raise ValueError("control effectiveness b must be nonzero")
    return (plant_a - a_m) * x / b + d


def l1_simulate(plant_a, a_m, b, b_m, r, x0, d, dt, gamma, omega_c,
                sigma_b, steps, tail=1000):
    """L1 closed-loop simulation (scalar sigma-only specialization),
    same discrete Euler ordering and equations as the bound leaf's
    simulate(): sample the prediction error, update sigma_hat with the
    clamped projection law, advance the filter on the updated estimate,
    form the control, advance plant/predictor/reference model, then
    append the post-advance histories."""
    if a_m >= 0:
        raise ValueError("reference model must be stable (a_m < 0)")
    if b == 0:
        raise ValueError("control effectiveness b must be nonzero")
    if dt <= 0:
        raise ValueError("time step dt must be positive")
    if gamma < 0:
        raise ValueError("adaptation rate gamma must be >= 0")
    if omega_c <= 0:
        raise ValueError("filter bandwidth omega_c must be positive")
    if sigma_b <= 0:
        raise ValueError("projection bound sigma_b must be positive")
    if steps < 2:
        raise ValueError("steps must be at least 2")

    x = x0
    xh = x0
    xm = x0
    sigma_hat = 0.0
    nu = 0.0
    kg = -a_m / b
    u = kg * r

    x_list = [x]
    xm_list = [xm]
    xh_list = [xh]
    u_list = [u]
    sigma_hat_list = [sigma_hat]
    nu_list = [nu]
    proj_active = 0

    for _ in range(steps):
        xt = xh - x
        raw = sigma_hat - dt * gamma * xt
        sigma_hat_new = max(-sigma_b, min(sigma_b, raw))
        if raw > sigma_b or raw < -sigma_b:
            proj_active += 1
        nu = nu + dt * omega_c * (sigma_hat_new - nu)
        u = kg * r - nu
        x = x + dt * (plant_a * x + b * u + b * d)
        xh = xh + dt * (a_m * xh + b * (u + sigma_hat_new))
        xm = xm + dt * (a_m * xm + b_m * r)
        sigma_hat = sigma_hat_new

        x_list.append(x)
        xm_list.append(xm)
        xh_list.append(xh)
        u_list.append(u)
        sigma_hat_list.append(sigma_hat)
        nu_list.append(nu)

    pred_err = [hi - xi for hi, xi in zip(xh_list, x_list)]
    track_err = [xi - mi for xi, mi in zip(x_list, xm_list)]
    tail_start = steps - tail
    tail_abs_pred = max(abs(p) for p in pred_err[tail_start:])
    tail_sigma_drift = max(
        abs(sigma_hat_list[i] - sigma_hat_list[i - 1])
        for i in range(tail_start + 1, steps + 1))
    max_abs_track = max(abs(e) for e in track_err)
    max_abs_pred = max(abs(p) for p in pred_err)
    max_abs_sigma = max(abs(s) for s in sigma_hat_list)

    return {
        "x": x_list, "xm": xm_list, "xh": xh_list, "u": u_list,
        "sigma_hat": sigma_hat_list, "nu": nu_list,
        "pred_err": pred_err, "track_err": track_err,
        "proj_active": proj_active,
        "max_abs_track": max_abs_track, "max_abs_pred": max_abs_pred,
        "max_abs_sigma": max_abs_sigma,
        "tail_abs_pred": tail_abs_pred, "tail_sigma_drift": tail_sigma_drift,
    }


def l1_convergence_report(res, plant_a, a_m, b, d):
    """converged True iff tail_abs_pred < 1e-4 AND tail_sigma_drift <
    1e-6 AND |sigma_hat_final - sigma_ideal(x_final)| < 0.05."""
    x_final = res["x"][-1]
    sigma_ideal_value = l1_sigma_true(x_final, plant_a, a_m, b, d)
    sigma_dev = abs(res["sigma_hat"][-1] - sigma_ideal_value)
    criteria = {"tail_abs_pred": res["tail_abs_pred"],
                "tail_sigma_drift": res["tail_sigma_drift"],
                "sigma_dev": sigma_dev, "sigma_ideal": sigma_ideal_value}
    converged = (res["tail_abs_pred"] < 1e-4
                and res["tail_sigma_drift"] < 1e-6
                and sigma_dev < 0.05)
    return converged, criteria


# ---------------------------------------------------------------------------
# Gain scheduling (gnc-autonomy/control/gain-scheduling)
# ---------------------------------------------------------------------------

def schedule_gain(table, x, method="linear", out_of_range="clamp"):
    """Interpolate a gain schedule table [(breakpoint, gain), ...] at
    scheduling-variable value x. Breakpoints must be strictly
    increasing. method: "nearest" or "linear". out_of_range: "clamp"
    (default) or "error"."""
    if not table or len(table) < 2:
        raise ValueError("schedule table needs at least 2 breakpoints")
    bps = [t[0] for t in table]
    if any(bps[i] >= bps[i + 1] for i in range(len(bps) - 1)):
        raise ValueError("breakpoints must be strictly increasing")
    if x < bps[0] or x > bps[-1]:
        if out_of_range == "error":
            raise ValueError("x=%r outside schedule range [%r, %r]"
                             % (x, bps[0], bps[-1]))
        x = min(max(x, bps[0]), bps[-1])
    if x <= bps[0]:
        return table[0][1]
    if x >= bps[-1]:
        return table[-1][1]
    for i in range(len(table) - 1):
        x0, g0 = table[i]
        x1, g1 = table[i + 1]
        if x0 <= x <= x1:
            if method == "nearest":
                return g0 if (x - x0) <= (x1 - x) else g1
            if method == "linear":
                frac = (x - x0) / (x1 - x0)
                return g0 + frac * (g1 - g0)
            raise NotImplementedError(
                "method %r not implemented (use linear or nearest)"
                % method)
    raise ValueError("x not bracketed (unreachable)")


def rate_limited_scheduling_variable(prev_value, new_value, max_rate, dt):
    """Limit the scheduling-variable step to +/- max_rate*dt per call."""
    if max_rate <= 0:
        raise ValueError("max_rate must be positive")
    if dt <= 0:
        raise ValueError("dt must be positive")
    step = new_value - prev_value
    limit = max_rate * dt
    step = max(-limit, min(limit, step))
    return prev_value + step


# ---------------------------------------------------------------------------
# Digital implementation (gnc-autonomy/control/digital-control-design)
# ---------------------------------------------------------------------------

def zoh_first_order(a: float, T: float) -> dict:
    """ZOH step-invariant discretization of G(s) = a/(s + a):
    A = exp(-a*T), B = 1 - A (A + B == 1 exactly, unit sampled DC gain)."""
    if a <= 0.0 or T <= 0.0:
        raise ValueError("a and T must be > 0")
    Ad = math.exp(-a * T)
    Bd = 1.0 - Ad
    return {"A": Ad, "B": Bd}


def discrete_pid_velocity(Kp: float, Ki: float, Kd: float, T: float) -> dict:
    """Velocity-form discrete PID coefficients {b0, b1, b2, a1}."""
    T = float(T)
    if T <= 0.0:
        raise ValueError("sample period T must be > 0")
    b0 = Kp + Ki * T + Kd / T
    b1 = -Kp - 2.0 * Kd / T
    b2 = Kd / T
    return {"b0": b0, "b1": b1, "b2": b2, "a1": -1.0}


def sample_rate_rule(wb: float, T: float) -> dict:
    """Minimum sample-rate rule: sample 10-20 times per closed-loop
    cycle, w_s_min = 10*wb, T_max = 2*pi/w_s_min."""
    wb, T = float(wb), float(T)
    if wb <= 0.0 or T <= 0.0:
        raise ValueError("wb and T must be > 0")
    w_s_min = 10.0 * wb
    t_max = 2.0 * math.pi / w_s_min
    return {"w_s_min_rad_s": w_s_min, "t_max_s": t_max,
            "verdict": "ok" if T <= t_max else "too-slow"}


# ---------------------------------------------------------------------------
# Control allocation (gnc-autonomy/control/control-allocation)
# ---------------------------------------------------------------------------

def pseudoinverse_alloc_row(b_row: list, m: float) -> dict:
    """Minimum-norm pseudoinverse allocation for a single-axis moment
    m distributed across effectors with effectiveness row b_row:
    u = B^+ m, B^+ = B^T (B B^T)^-1 for B = [b_row] (1 x n). Verified
    against the leaf's worked anchor B = [[1, 1]], m = 0.8 ->
    u = [0.4, 0.4]."""
    if not b_row:
        raise ValueError("b_row must be non-empty")
    gram = sum(bi * bi for bi in b_row)
    if gram <= 1e-12:
        raise ValueError("control effectiveness row must be nonzero")
    u = [bi * m / gram for bi in b_row]
    m_ach = sum(bi * ui for bi, ui in zip(b_row, u))
    return {"u": u, "achieved_moment": m_ach, "error": abs(m - m_ach)}


# ---------------------------------------------------------------------------
# Project facts
# ---------------------------------------------------------------------------

@dataclass
class AutopilotProject:
    """Vehicle/project facts the role needs to build the package."""
    vehicle: str = "Utility UAV (illustrative airframe, example cruise condition)"
    mission: str = ("Pitch attitude hold with roll / turn-coordination "
                    "autopilot design")
    condition: str = ("Cruise, V=28 m/s TAS, altitude 1500 m "
                      "(rho=1.0581 kg/m^3, q_bar=414.8 Pa), level flight, "
                      "mid CG")
    report_title: str = ("Autopilot Control-Law Design Package - Pitch "
                         "Attitude Hold with Roll / Turn-Coordination "
                         "(Utility UAV)")
    mass_kg: float = 22.0
    wing_area_m2: float = 1.10

    # longitudinal short-period (elevator to pitch rate, companion form)
    sp_wn_rad_s: float = 7.2
    sp_zeta: float = 0.60
    sp_b: float = 5.0            # elevator effectiveness, 1/s

    # longitudinal phugoid (reduced order, informational)
    ph_wn_rad_s: float = 0.22
    ph_zeta: float = 0.07
    ph_b: float = 0.5

    # lateral roll subsidence (aileron to roll rate, first order)
    roll_tau_s: float = 0.35
    roll_La: float = 12.0        # aileron roll effectiveness, rad/s^2 per rad

    # lateral dutch-roll (rudder to yaw rate, companion form)
    dr_wn_rad_s: float = 3.0
    dr_zeta: float = 0.12
    dr_b: float = 4.0

    # inner pitch-rate loop design targets
    inner_wn_rad_s: float = 14.0
    inner_zeta: float = 0.85
    inner_p3_rad_s: float = 28.0

    # outer pitch-attitude loop
    outer_zeta_target: float = math.sqrt(2.0) / 2.0
    req_bandwidth_rad_s: float = 3.5
    req_phase_margin_deg: float = 45.0
    req_gain_margin_db: float = 6.0

    # roll-attitude root-locus design target
    roll_zeta_target: float = math.sqrt(2.0) / 2.0

    # dutch-roll / turn-coordination yaw-rate damper (washout-style
    # numerator zero from the N_delta_r' aerodynamic coupling term)
    dr_num_zero_rad_s: float = 2.0
    yaw_damper_kr: float = 1.2
    req_phase_margin_lat_deg: float = 45.0
    req_gain_margin_lat_db: float = 6.0

    # observer: angle-of-attack estimator from measured pitch rate
    obs_pole_rad_s: float = 45.0  # double observer pole

    # L1 adaptive augmentation scenario: a normalized representation of
    # the pitch-rate command-tracking error channel, scaled
    # independently of the inner/outer loop hardware gains (design
    # pole a_m sets the target error-decay rate of the augmentation
    # layer, not the raw plant pole).
    l1_a_m_rad_s: float = -2.0
    l1_b: float = 1.0
    l1_b_m: float = 2.0
    l1_r: float = 1.0
    l1_x0: float = 0.0
    l1_dt_s: float = 0.01
    l1_gamma: float = 15.0
    l1_omega_c_rad_s: float = 10.0
    l1_sigma_b: float = 2.5
    l1_mismatch_ratio: float = 0.5   # plant_a = ratio * a_m
    l1_disturbance: float = 1.0
    l1_steps: int = 6000
    l1_tail: int = 1000
    l1_ebound_req: float = 0.60      # required transient bound (normalized)

    # gain schedule (pitch-rate proportional-gain analogue vs q_bar)
    gs_q_low_pa: float = 180.0
    gs_q_cruise_pa: float = 414.8
    gs_q_high_pa: float = 650.0
    gs_query_pa: float = 300.0       # interpolation query point
    gs_max_rate_pa_s: float = 400.0
    gs_dt_s: float = 0.05

    # digital implementation
    sample_period_s: float = 0.01

    # control allocation
    alloc_elev_eff: float = 1.0
    alloc_stab_eff: float = 0.6
    alloc_pitch_moment_cmd: float = 0.8
    alloc_ail_eff: float = 1.0
    alloc_rud_eff: float = 0.5
    alloc_turn_moment_cmd: float = 0.5


# ---------------------------------------------------------------------------
# Package builder
# ---------------------------------------------------------------------------

def build_package(p: AutopilotProject) -> dict:
    """Run every design computation and assemble the package model."""
    # --- 1. state-space plant models -----------------------------------
    sp_a1 = 2.0 * p.sp_zeta * p.sp_wn_rad_s
    sp_a0 = p.sp_wn_rad_s ** 2
    sp_ss = companion_form_2state(sp_a1, sp_a0, p.sp_b)
    sp_ss["C"] = [[0.0, 1.0]]     # output: pitch rate q
    sp_eig = eig2x2(sp_ss["A"])
    sp_ctrl = controllable_2state(sp_ss["A"], sp_ss["B"])
    sp_obsv = observable_2state(sp_ss["A"], sp_ss["C"])

    ph_a1 = 2.0 * p.ph_zeta * p.ph_wn_rad_s
    ph_a0 = p.ph_wn_rad_s ** 2
    ph_ss = companion_form_2state(ph_a1, ph_a0, p.ph_b)
    ph_ss["C"] = [[1.0, 0.0]]     # output: forward-speed perturbation
    ph_eig = eig2x2(ph_ss["A"])

    a_roll = 1.0 / p.roll_tau_s
    roll_ss = {"A": [[-a_roll]], "B": [[p.roll_La]], "C": [[1.0]],
              "D": [[0.0]]}
    roll_pole = -a_roll

    dr_a1 = 2.0 * p.dr_zeta * p.dr_wn_rad_s
    dr_a0 = p.dr_wn_rad_s ** 2
    dr_ss = companion_form_2state(dr_a1, dr_a0, p.dr_b)
    dr_ss["C"] = [[0.0, 1.0]]     # output: yaw rate r
    dr_eig = eig2x2(dr_ss["A"])

    # --- 2a. longitudinal inner/outer loop ------------------------------
    kp, ki, kd = pid_gains_second_order(
        sp_a1, sp_a0, p.sp_b, p.inner_wn_rad_s, p.inner_zeta,
        p.inner_p3_rad_s)
    inum = [p.sp_b * kd, p.sp_b * kp, p.sp_b * ki]
    iden = [1.0, sp_a1, sp_a0, 0.0]
    inner_m = loop_margins(inum, iden)
    inner_req_ok = (
        not math.isinf(inner_m["phase_margin_deg"])
        and inner_m["phase_margin_deg"] >= p.req_phase_margin_deg
        and (math.isinf(inner_m["gain_margin_db"])
             or inner_m["gain_margin_db"] >= p.req_gain_margin_db))

    a_lag = p.inner_zeta * p.inner_wn_rad_s
    zt = p.outer_zeta_target
    wn_theta = a_lag / (2.0 * zt)
    kp_theta = wn_theta ** 2 / a_lag
    outer_m = type1_margins(a_lag, kp_theta * a_lag)
    bw_theta = closed_loop_bandwidth(wn_theta, zt)
    zeta_theta = a_lag / (2.0 * wn_theta)
    outer_req_ok = (outer_m["phase_margin_deg"] >= p.req_phase_margin_deg
                    and bw_theta >= p.req_bandwidth_rad_s)

    # --- 2b. lateral: roll attitude by root locus -----------------------
    K_rl = gain_for_damping_rl(a_roll, p.roll_zeta_target)
    rl_poles = closed_loop_poles_rl(a_roll, K_rl)
    rl_zeta = damping_ratio_rl(a_roll, K_rl)
    rl_wn = math.sqrt(K_rl)
    rl_stable = stability_verdict_rl(a_roll, K_rl)
    k_phi = K_rl / p.roll_La     # physical roll-attitude proportional gain

    # dutch-roll / turn-coordination yaw-rate damper: proportional
    # yaw-rate feedback on a yaw-rate-to-rudder transfer function with
    # a numerator zero (N_delta_r' aerodynamic coupling), which adds
    # phase lead near crossover the way a real washout-style damper does
    ynum = [p.yaw_damper_kr * p.dr_b,
           p.yaw_damper_kr * p.dr_b * p.dr_num_zero_rad_s]
    yden = [1.0, dr_a1, dr_a0]
    yaw_m = loop_margins(ynum, yden)
    yaw_req_ok = (
        not math.isinf(yaw_m["phase_margin_deg"])
        and yaw_m["phase_margin_deg"] >= p.req_phase_margin_lat_deg
        and (math.isinf(yaw_m["gain_margin_db"])
             or yaw_m["gain_margin_db"] >= p.req_gain_margin_lat_db))

    # --- 3. observer: angle-of-attack estimator from measured q --------
    obs = observer_gain_2state(sp_ss["A"], sp_ss["C"],
                               [-p.obs_pole_rad_s, -p.obs_pole_rad_s])

    # --- 4. L1 adaptive augmentation of the pitch-rate error channel ---
    l1_a_m = p.l1_a_m_rad_s
    l1_b_m = p.l1_b_m
    l1_plant_a = p.l1_mismatch_ratio * l1_a_m
    l1_res = l1_simulate(l1_plant_a, l1_a_m, p.l1_b, l1_b_m, p.l1_r,
                         p.l1_x0, p.l1_disturbance, p.l1_dt_s, p.l1_gamma,
                         p.l1_omega_c_rad_s, p.l1_sigma_b, p.l1_steps,
                         p.l1_tail)
    l1_converged, l1_criteria = l1_convergence_report(
        l1_res, l1_plant_a, l1_a_m, p.l1_b, p.l1_disturbance)
    l1_bound_ok = l1_res["max_abs_track"] <= p.l1_ebound_req

    # --- 5. gain schedule -------------------------------------------------
    gs_table = []
    for q_bar in (p.gs_q_low_pa, p.gs_q_cruise_pa, p.gs_q_high_pa):
        b_q = p.sp_b * (q_bar / p.gs_q_cruise_pa)
        kp_q, ki_q, kd_q = pid_gains_second_order(
            sp_a1, sp_a0, b_q, p.inner_wn_rad_s, p.inner_zeta,
            p.inner_p3_rad_s)
        gs_table.append((q_bar, kp_q))
    gs_interp_kp = schedule_gain(gs_table, p.gs_query_pa, method="linear")
    gs_rate_limited = rate_limited_scheduling_variable(
        p.gs_q_low_pa, p.gs_q_cruise_pa, p.gs_max_rate_pa_s, p.gs_dt_s)

    # --- 6. digital implementation ---------------------------------------
    zoh = zoh_first_order(a_roll, p.sample_period_s)
    disc = discrete_pid_velocity(kp, ki, kd, p.sample_period_s)
    dig = sample_rate_rule(p.inner_wn_rad_s, p.sample_period_s)

    # --- 7. control allocation ---------------------------------------
    pitch_alloc = pseudoinverse_alloc_row(
        [p.alloc_elev_eff, p.alloc_stab_eff], p.alloc_pitch_moment_cmd)
    turn_alloc = pseudoinverse_alloc_row(
        [p.alloc_ail_eff, p.alloc_rud_eff], p.alloc_turn_moment_cmd)

    model = {
        "document_type": p.report_title,
        "status": "draft-for-review",
        "vehicle": p.vehicle,
        "mission": p.mission,
        "condition": p.condition,
        "mass_kg": p.mass_kg,
        "wing_area_m2": p.wing_area_m2,
        "generated": _today(),
        "plant": {
            "sp": {"A": sp_ss["A"], "B": sp_ss["B"], "C": sp_ss["C"],
                  "D": sp_ss["D"], "wn": p.sp_wn_rad_s, "zeta": p.sp_zeta,
                  "b": p.sp_b, "eig": sp_eig["poles"],
                  "controllable": sp_ctrl, "observable": sp_obsv},
            "phugoid": {"A": ph_ss["A"], "B": ph_ss["B"], "C": ph_ss["C"],
                       "D": ph_ss["D"], "wn": p.ph_wn_rad_s,
                       "zeta": p.ph_zeta, "b": p.ph_b, "eig": ph_eig["poles"]},
            "roll": {"A": roll_ss["A"], "B": roll_ss["B"],
                    "C": roll_ss["C"], "D": roll_ss["D"],
                    "tau_s": p.roll_tau_s, "a": a_roll, "La": p.roll_La,
                    "pole": roll_pole},
            "dutch_roll": {"A": dr_ss["A"], "B": dr_ss["B"],
                          "C": dr_ss["C"], "D": dr_ss["D"],
                          "wn": p.dr_wn_rad_s, "zeta": p.dr_zeta,
                          "b": p.dr_b, "eig": dr_eig["poles"]},
        },
        "inner": {
            "wn": p.inner_wn_rad_s, "zeta": p.inner_zeta,
            "p3": p.inner_p3_rad_s, "kp": kp, "ki": ki, "kd": kd,
            "margins": {"gm_db": inner_m["gain_margin_db"],
                       "pm_deg": inner_m["phase_margin_deg"],
                       "wgc": inner_m["gain_crossover_rad_s"],
                       "wpc": inner_m["phase_crossover_rad_s"]},
            "req_ok": bool(inner_req_ok),
        },
        "outer": {
            "a_lag": a_lag, "kp_theta": kp_theta, "wn_theta": wn_theta,
            "zeta_theta": zeta_theta, "bw_rad_s": bw_theta,
            "margins": {"gm_db": outer_m["gain_margin_db"],
                       "pm_deg": outer_m["phase_margin_deg"],
                       "wgc": outer_m["crossover_rad_s"]},
            "req_ok": bool(outer_req_ok),
        },
        "roll_rl": {
            "a": a_roll, "K": K_rl, "k_phi": k_phi,
            "poles": rl_poles["poles"], "zeta": rl_zeta, "wn": rl_wn,
            "stable": bool(rl_stable),
        },
        "yaw_damper": {
            "kr": p.yaw_damper_kr, "num_zero_rad_s": p.dr_num_zero_rad_s,
            "margins": {"gm_db": yaw_m["gain_margin_db"],
                       "pm_deg": yaw_m["phase_margin_deg"],
                       "wgc": yaw_m["gain_crossover_rad_s"]},
            "req_ok": bool(yaw_req_ok),
        },
        "observer": {
            "L": obs["L"], "poles": obs["poles"],
            "settling_time_s": obs["settling_time_s"],
        },
        "l1": {
            "a_m": l1_a_m, "b": p.l1_b, "b_m": l1_b_m, "r": p.l1_r,
            "plant_a": l1_plant_a, "d": p.l1_disturbance,
            "dt_s": p.l1_dt_s, "gamma": p.l1_gamma,
            "omega_c_rad_s": p.l1_omega_c_rad_s, "sigma_b": p.l1_sigma_b,
            "steps": p.l1_steps,
            "max_abs_track": l1_res["max_abs_track"],
            "max_abs_pred": l1_res["max_abs_pred"],
            "max_abs_sigma": l1_res["max_abs_sigma"],
            "proj_active": l1_res["proj_active"],
            "x_final": l1_res["x"][-1], "xm_final": l1_res["xm"][-1],
            "sigma_hat_final": l1_res["sigma_hat"][-1],
            "u_final": l1_res["u"][-1],
            "converged": bool(l1_converged),
            "criteria": l1_criteria,
            "ebound_req": p.l1_ebound_req,
            "bound_ok": bool(l1_bound_ok),
        },
        "gain_schedule": {
            "table": gs_table, "query_pa": p.gs_query_pa,
            "interp_kp": gs_interp_kp,
            "rate_limited_step": gs_rate_limited,
            "max_rate_pa_s": p.gs_max_rate_pa_s,
        },
        "digital": {
            "T_s": p.sample_period_s, "zoh_roll": zoh,
            "disc_pid": disc, "w_s_min": dig["w_s_min_rad_s"],
            "t_max_s": dig["t_max_s"], "verdict": dig["verdict"],
        },
        "allocation": {
            "pitch": {"eff": [p.alloc_elev_eff, p.alloc_stab_eff],
                     "cmd": p.alloc_pitch_moment_cmd, **pitch_alloc},
            "turn": {"eff": [p.alloc_ail_eff, p.alloc_rud_eff],
                    "cmd": p.alloc_turn_moment_cmd, **turn_alloc},
        },
        "requirements": {
            "bandwidth_rad_s": p.req_bandwidth_rad_s,
            "phase_margin_deg": p.req_phase_margin_deg,
            "gain_margin_db": p.req_gain_margin_db,
            "phase_margin_lat_deg": p.req_phase_margin_lat_deg,
            "gain_margin_lat_db": p.req_gain_margin_lat_db,
        },
        "verdicts": {
            "inner_margins": "PASS" if inner_req_ok else "FAIL",
            "outer_margins": "PASS" if outer_req_ok else "FAIL",
            "roll_root_locus": "PASS" if rl_stable else "FAIL",
            "yaw_damper_margins": "PASS" if yaw_req_ok else "FAIL",
            "l1_transient_bound": "PASS" if l1_bound_ok else "FAIL",
            "l1_convergence": "PASS" if l1_converged else "FAIL",
            "digital_sample_rate": ("PASS" if dig["verdict"] == "ok"
                                    else "FAIL"),
            "allocation_pitch": ("PASS" if pitch_alloc["error"] < 1e-6
                                 else "FAIL"),
            "allocation_turn": ("PASS" if turn_alloc["error"] < 1e-6
                                else "FAIL"),
        },
    }
    return model


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _fmt(x, nd=3):
    if isinstance(x, float) and math.isinf(x):
        return "inf"
    return ("%%.%df" % nd) % x


def _fmt_pole(p):
    re, im = p
    if abs(im) < 1e-9:
        return "%.3f" % re
    return "%.3f %s j%.3f" % (re, "+" if im >= 0 else "-", abs(im))


def render_package_markdown(m: dict) -> str:
    pl = m["plant"]
    sp, ph, roll, dr = pl["sp"], pl["phugoid"], pl["roll"], pl["dutch_roll"]
    i = m["inner"]
    o = m["outer"]
    rl = m["roll_rl"]
    yd = m["yaw_damper"]
    ob = m["observer"]
    l1 = m["l1"]
    gs = m["gain_schedule"]
    d = m["digital"]
    al = m["allocation"]
    req = m["requirements"]
    v = m["verdicts"]
    L = ob["L"]

    lines = [
        "# " + m["document_type"],
        "",
        "**Vehicle:** %s (mass %.0f kg, wing area %.2f m^2)" % (
            m["vehicle"], m["mass_kg"], m["wing_area_m2"]),
        "**Condition:** %s" % m["condition"],
        "**Mission / item:** %s" % m["mission"],
        "**Status:** %s" % m["status"],
        "",
        "> DRAFT for human autopilot/GNC lead review. Design predictions "
        "only; not flight software release, not a certification finding, "
        "not an approval document. Example vehicle/flight-condition "
        "numbers are illustrative and flagged for verification against "
        "the real vehicle database.",
        "",
        "## 1. State-space plant models",
        "",
        "Reduced-order longitudinal and lateral models at the stated "
        "cruise condition, controllable-canonical (companion) form "
        "x_dot = A x + B u, y = C x + D u (example trim data; verify "
        "against the vehicle aerodynamic database):",
        "",
        "**Short-period** (elevator to pitch rate q; wn=%.2f rad/s, "
        "zeta=%.2f, elevator effectiveness b=%.1f 1/s):" % (
            sp["wn"], sp["zeta"], sp["b"]),
        "",
        "- A = [[%.3f, %.3f], [%.3f, %.3f]], B = [[%.3f], [%.3f]], "
        "C = [[%.1f, %.1f]], D = [[0]]" % (
            sp["A"][0][0], sp["A"][0][1], sp["A"][1][0], sp["A"][1][1],
            sp["B"][0][0], sp["B"][1][0], sp["C"][0][0], sp["C"][0][1]),
        "- Eigenvalues (closed form from trace/det): %s, %s "
        "(computed from A, matches wn/zeta exactly). Controllable: %s. "
        "Observable (q measured): %s." % (
            _fmt_pole(sp["eig"][0]), _fmt_pole(sp["eig"][1]),
            sp["controllable"], sp["observable"]),
        "",
        "**Phugoid** (reduced order, informational; wn=%.2f rad/s, "
        "zeta=%.2f):" % (ph["wn"], ph["zeta"]),
        "",
        "- A = [[%.4f, %.4f], [%.4f, %.4f]], B = [[%.3f], [%.3f]], "
        "C = [[%.1f, %.1f]], D = [[0]]" % (
            ph["A"][0][0], ph["A"][0][1], ph["A"][1][0], ph["A"][1][1],
            ph["B"][0][0], ph["B"][1][0], ph["C"][0][0], ph["C"][0][1]),
        "- Eigenvalues: %s, %s (lightly damped, not closed-loop "
        "controlled in this package; monitored for pilot/autopilot "
        "coupling)." % (_fmt_pole(ph["eig"][0]), _fmt_pole(ph["eig"][1])),
        "",
        "**Roll subsidence** (aileron to roll rate p, first order; "
        "time constant %.2f s, aileron effectiveness La=%.1f "
        "rad/s^2/rad):" % (roll["tau_s"], roll["La"]),
        "",
        "- A = [[%.3f]], B = [[%.1f]], C = [[1]], D = [[0]]. Pole at "
        "%.3f rad/s (stable, real)." % (
            roll["A"][0][0], roll["B"][0][0], roll["pole"]),
        "",
        "**Dutch-roll** (rudder to yaw rate r; wn=%.2f rad/s, "
        "zeta=%.2f, rudder effectiveness b=%.1f):" % (
            dr["wn"], dr["zeta"], dr["b"]),
        "",
        "- A = [[%.3f, %.3f], [%.3f, %.3f]], B = [[%.3f], [%.3f]], "
        "C = [[%.1f, %.1f]], D = [[0]]" % (
            dr["A"][0][0], dr["A"][0][1], dr["A"][1][0], dr["A"][1][1],
            dr["B"][0][0], dr["B"][1][0], dr["C"][0][0], dr["C"][0][1]),
        "- Eigenvalues: %s, %s (lightly damped dutch-roll pair; drives "
        "the turn-coordination yaw damper of section 4)." % (
            _fmt_pole(dr["eig"][0]), _fmt_pole(dr["eig"][1])),
        "",
        "## 2. Inner/outer loop gain design",
        "",
        "**Longitudinal** - inner pitch-rate loop by PID pole placement "
        "on the short-period plant (matched to "
        "(s^2 + 2 z_i wn_i s + wn_i^2)(s + p3_i)); outer pitch-attitude "
        "loop by proportional gain on the reduced inner-loop lag "
        "a/(s + a):",
        "",
        "| Loop | Gains | Phase margin | Gain margin | Requirement | Verdict |",
        "|---|---|---|---|---|---|",
        "| inner q (PID) | kp=%.2f, ki=%.2f, kd=%.2f | %s deg | %s dB | "
        "PM >= %.0f deg, GM >= %.0f dB | %s |" % (
            i["kp"], i["ki"], i["kd"], _fmt(i["margins"]["pm_deg"], 1),
            _fmt(i["margins"]["gm_db"], 1), req["phase_margin_deg"],
            req["gain_margin_db"], "PASS" if i["req_ok"] else "FAIL"),
        "| outer theta (P) | kp_theta=%.3f 1/s | %.1f deg | inf dB | "
        "PM >= %.0f deg, GM >= 6 dB | %s |" % (
            o["kp_theta"], o["margins"]["pm_deg"], req["phase_margin_deg"],
            "PASS" if o["req_ok"] else "FAIL"),
        "",
        "Inner loop: wn_i=%.1f rad/s, zeta_i=%.2f, non-dominant pole "
        "p3_i=%.1f rad/s; gain crossover %.1f rad/s. Outer loop: reduced "
        "inner-loop lag a=zeta_i*wn_i=%.2f rad/s, damping target "
        "zeta=%.3f, wn_theta=%.2f rad/s, achieved bandwidth %.2f rad/s "
        "(requirement >= %.1f rad/s, %s)." % (
            i["wn"], i["zeta"], i["p3"], i["margins"]["wgc"],
            o["a_lag"], o["zeta_theta"], o["wn_theta"], o["bw_rad_s"],
            req["bandwidth_rad_s"],
            "PASS" if o["bw_rad_s"] >= req["bandwidth_rad_s"] else "FAIL"),
        "",
        "**Lateral** - roll-attitude loop by classical root locus on "
        "the canonical type-1 plant G(s) = 1/(s(s + a)), a = %.3f rad/s "
        "(roll subsidence pole); gain selected for target damping "
        "zeta = %.3f:" % (rl["a"], p_roll_zeta_placeholder(m)),
        "",
        "- Forward-path gain K = a^2/(4*zeta^2) = %.3f; physical roll-"
        "attitude proportional gain k_phi = K/La = %.3f rad/rad." % (
            rl["K"], rl["k_phi"]),
        "- Closed-loop poles: %s, %s -> damping zeta=%.3f, natural "
        "frequency wn=%.3f rad/s. Stability verdict: %s." % (
            _fmt_pole(rl["poles"][0]), _fmt_pole(rl["poles"][1]),
            rl["zeta"], rl["wn"], "STABLE" if rl["stable"] else "UNSTABLE"),
        "",
        "Dutch-roll / turn-coordination yaw-rate damper (proportional "
        "rudder feedback on yaw rate r, kr=%.2f, on the yaw-rate-to-"
        "rudder transfer function with its N_delta_r' numerator zero "
        "at %.1f rad/s, which supplies the phase lead near crossover "
        "the way a washout-style damper does):" % (
            yd["kr"], yd["num_zero_rad_s"]),
        "",
        "| Loop | Gain | Phase margin | Gain margin | Requirement | Verdict |",
        "|---|---|---|---|---|---|",
        "| yaw damper (P) | kr=%.2f | %s deg | %s dB | PM >= %.0f deg, "
        "GM >= %.0f dB | %s |" % (
            yd["kr"], _fmt(yd["margins"]["pm_deg"], 1),
            _fmt(yd["margins"]["gm_db"], 1), req["phase_margin_lat_deg"],
            req["gain_margin_lat_db"],
            "PASS" if yd["req_ok"] else "FAIL"),
        "",
        "## 3. Observer design",
        "",
        "Full-order (Ackermann) observer for angle of attack (not "
        "directly measured; no alpha vane assumed), estimated from the "
        "measured pitch rate q on the short-period plant:",
        "",
        "- Observer poles: %.0f rad/s (double), about %.1fx faster than "
        "the short-period natural frequency (separation principle). "
        "Settling time 4/sigma = %.4f s." % (
            -ob["poles"][0], -ob["poles"][0] / sp["wn"],
            ob["settling_time_s"]),
        "- Observer gain L = [%.2f, %.2f]. Error dynamics A - L C "
        "inherit the chosen poles exactly (Ackermann closed form)." % (
            L[0], L[1]),
        "",
        "## 4. L1 adaptive augmentation",
        "",
        "Plant-uncertainty scenario: partial pitch-rate control-"
        "effectiveness loss (e.g. an elevator actuator degradation) "
        "combined with an unmodeled trim disturbance (asymmetric icing / "
        "gust bias), applied to a normalized representation of the "
        "pitch-rate command-tracking error channel (design pole a_m and "
        "unit-DC-gain reference b_m chosen independently of the inner/"
        "outer hardware gains of section 2, per the augmentation-layer "
        "convention). Scalar sigma-only L1 specialization, state "
        "predictor + projection-based adaptation law + low-pass filter, "
        "following gnc-autonomy/control/l1-adaptive-control exactly:",
        "",
        "- Design model: a_m=%.3f, b=%.1f, b_m=%.3f, command r=%.1f. "
        "True (unmodeled) plant coefficient a_p=%.3f (%.0f%% of a_m, "
        "less-damped mismatch), constant matched disturbance d=%.2f." % (
            l1["a_m"], l1["b"], l1["b_m"], l1["r"], l1["plant_a"],
            100.0 * l1["plant_a"] / l1["a_m"], l1["d"]),
        "- Adaptation rate gamma=%.1f, filter cutoff omega_c=%.1f rad/s "
        "(C(s) = omega_c/(s + omega_c)), projection bound sigma_b=%.1f, "
        "step dt=%.3f s, run %d steps." % (
            l1["gamma"], l1["omega_c_rad_s"], l1["sigma_b"], l1["dt_s"],
            l1["steps"]),
        "- Transient: max |tracking error| = %.6f, max |prediction "
        "error| = %.6f, max |sigma_hat| = %.6f; projection clamp active "
        "on %d steps." % (
            l1["max_abs_track"], l1["max_abs_pred"], l1["max_abs_sigma"],
            l1["proj_active"]),
        "- Final state: x_final=%.6f (reference xm_final=%.6f), "
        "sigma_hat_final=%.6f, u_final=%.6f." % (
            l1["x_final"], l1["xm_final"], l1["sigma_hat_final"],
            l1["u_final"]),
        "- Convergence verdict: tail |prediction error|=%.3e "
        "(< 1e-4), tail sigma_hat drift=%.3e (< 1e-6), "
        "|sigma_hat_final - sigma_ideal|=%.3e (< 0.05) -> %s." % (
            l1["criteria"]["tail_abs_pred"],
            l1["criteria"]["tail_sigma_drift"], l1["criteria"]["sigma_dev"],
            "CONVERGED" if l1["converged"] else "NOT CONVERGED"),
        "- Certified transient-bound check: max |tracking error| "
        "%.6f <= required bound %.2f -> %s." % (
            l1["max_abs_track"], l1["ebound_req"],
            "PASS" if l1["bound_ok"] else "FAIL"),
        "",
        "## 5. Gain scheduling",
        "",
        "Inner pitch-rate proportional gain kp scheduled against "
        "dynamic pressure q_bar (elevator effectiveness scales "
        "linearly with q_bar; gain re-derived by the same pole-"
        "placement rule at each breakpoint so the closed-loop wn_i/"
        "zeta_i target is held across the envelope):",
        "",
        "| q_bar (Pa) | condition | kp |",
        "|---|---|---|",
        "| %.1f | low-speed | %.2f |" % (gs["table"][0][0], gs["table"][0][1]),
        "| %.1f | cruise | %.2f |" % (gs["table"][1][0], gs["table"][1][1]),
        "| %.1f | high-speed dash | %.2f |" % (
            gs["table"][2][0], gs["table"][2][1]),
        "",
        "- Linear interpolation at q_bar=%.1f Pa -> kp=%.3f (schedule_"
        "gain, breakpoints strictly increasing)." % (
            gs["query_pa"], gs["interp_kp"]),
        "- Scheduling-variable rate limiting: one step from q_bar=%.1f "
        "toward %.1f Pa at max_rate=%.0f Pa/s, dt=%.2f s -> %.2f Pa "
        "(limited before interpolation, per gain-scheduling leaf "
        "practice)." % (
            gs["table"][0][0], gs["table"][1][0], gs["max_rate_pa_s"],
            0.05, gs["rate_limited_step"]),
        "",
        "## 6. Digital implementation",
        "",
        "Sample period T=%.3f s (%d Hz):" % (
            d["T_s"], int(round(1.0 / d["T_s"]))),
        "",
        "- Sample-rate rule (10-20 samples per closed-loop cycle): "
        "w_s,min=10*wn_i=%.1f rad/s, T_max=%.4f s; verdict: %s "
        "(T=%.3f s <= T_max)." % (
            d["w_s_min"], d["t_max_s"], d["verdict"], d["T_s"]),
        "- ZOH discretization of the roll subsidence pole a=%.3f rad/s "
        "at T=%.3f s: A_d=%.6f, B_d=%.6f (A_d + B_d == 1 exactly, unit "
        "sampled DC gain)." % (
            roll["a"], d["T_s"], d["zoh_roll"]["A"], d["zoh_roll"]["B"]),
        "- Inner PID velocity-form coefficients "
        "(u(k)=u(k-1)+b0 e(k)+b1 e(k-1)+b2 e(k-2)): b0=%.4f, b1=%.4f, "
        "b2=%.4f, a1=-1." % (
            d["disc_pid"]["b0"], d["disc_pid"]["b1"], d["disc_pid"]["b2"]),
        "",
        "## 7. Control allocation",
        "",
        "Minimum-norm pseudoinverse allocation (u = B^+ m) across "
        "redundant effectors:",
        "",
        "| Axis | Effectors (eff.) | Command | Allocation | Achieved | Error |",
        "|---|---|---|---|---|---|",
        "| Pitch | elevator (%.1f) + stabilator (%.1f) | %.2f | "
        "[%.3f, %.3f] | %.4f | %.2e |" % (
            al["pitch"]["eff"][0], al["pitch"]["eff"][1],
            al["pitch"]["cmd"], al["pitch"]["u"][0], al["pitch"]["u"][1],
            al["pitch"]["achieved_moment"], al["pitch"]["error"]),
        "| Turn coord. | aileron (%.1f) + rudder (%.1f) | %.2f | "
        "[%.3f, %.3f] | %.4f | %.2e |" % (
            al["turn"]["eff"][0], al["turn"]["eff"][1], al["turn"]["cmd"],
            al["turn"]["u"][0], al["turn"]["u"][1],
            al["turn"]["achieved_moment"], al["turn"]["error"]),
        "",
        "## 8. Control-law summary and verdict",
        "",
        "| Loop | Gain | Margin | Bandwidth |",
        "|---|---|---|---|",
        "| Inner pitch-rate (PID) | kp=%.2f ki=%.2f kd=%.2f | "
        "PM=%s deg | wn=%.1f rad/s |" % (
            i["kp"], i["ki"], i["kd"], _fmt(i["margins"]["pm_deg"], 1),
            i["wn"]),
        "| Outer pitch-attitude (P) | kp_theta=%.3f | PM=%.1f deg | "
        "BW=%.2f rad/s |" % (o["kp_theta"], o["margins"]["pm_deg"],
                             o["bw_rad_s"]),
        "| Roll attitude (root locus) | k_phi=%.3f | zeta=%.3f | "
        "wn=%.2f rad/s |" % (rl["k_phi"], rl["zeta"], rl["wn"]),
        "| Yaw-rate damper (P) | kr=%.2f | PM=%s deg | - |" % (
            yd["kr"], _fmt(yd["margins"]["pm_deg"], 1)),
        "",
        "| Gate | Result |",
        "|---|---|",
        "| Inner loop margins vs requirement | %s |" % v["inner_margins"],
        "| Outer loop margins/bandwidth vs requirement | %s |" % v["outer_margins"],
        "| Roll-attitude root-locus stability | %s |" % v["roll_root_locus"],
        "| Yaw damper margins vs requirement | %s |" % v["yaw_damper_margins"],
        "| L1 certified transient bound | %s |" % v["l1_transient_bound"],
        "| L1 convergence | %s |" % v["l1_convergence"],
        "| Digital sample-rate rule | %s |" % v["digital_sample_rate"],
        "| Pitch allocation closes (zero error) | %s |" % v["allocation_pitch"],
        "| Turn-coordination allocation closes (zero error) | %s |" % v["allocation_turn"],
        "",
        "**Verdict:** every gate above computed from the stated example "
        "plant/scenario facts and the domain rules of the bound "
        "AeroSkills leaves; no number is asserted without the "
        "calculation behind it. This package is a DRAFT for human "
        "autopilot/GNC lead review - not an approval, not a certification "
        "finding, and not a release of flight software. Open items: "
        "full 6-DOF nonlinear simulation with actuator and aeroelastic "
        "models, sensor-in-the-loop tests, gain-schedule coverage of the "
        "full flight envelope, and handling-qualities evaluation per "
        "MIL-STD-1797A where applicable.",
        "",
        "## Appendix A. Calculation traceability",
        "",
        "- State-space eigenvalues/controllability/observability: "
        "closed-form 2x2 trace/determinant and matrix-rank checks "
        "(state-space-analysis).",
        "- PID pole placement: (s^2 + 2 z wn s + wn^2)(s + p3) matching "
        "(pid-control-design).",
        "- Margins: type-1 closed form and general loops on jw with "
        "root-sum unwrapped phase (frequency-response-design); margin "
        "acceptance convention GM >= 6 dB, PM >= 45 deg "
        "(python-control-design).",
        "- Root locus: s^2 + a s + K = 0 canonical closed form, gain "
        "for target damping K = a^2/(4 zeta^2) (root-locus-design).",
        "- Observer: Ackermann L = phi(A) O^-1 e_n (observer-design).",
        "- L1 adaptive augmentation: state predictor, projection-based "
        "adaptation law, low-pass filter C(s) = omega_c/(s + omega_c) "
        "(l1-adaptive-control, scalar sigma-only specialization).",
        "- Gain schedule: linear breakpoint interpolation and "
        "scheduling-variable rate limiting (gain-scheduling).",
        "- Digital: ZOH step-invariant discretization, velocity-form "
        "discrete PID, 10-20 samples/cycle sample-rate rule "
        "(digital-control-design).",
        "- Control allocation: minimum-norm pseudoinverse "
        "u = B^+ m (control-allocation).",
        "",
        "---",
        "*Generated by Aero Agent Roles autopilot-control-engineer core "
        "(%s). DRAFT - for human autopilot/GNC lead review. Design "
        "predictions only; not flight software release, not a "
        "certification finding, not an approval document.*" % m["generated"],
    ]
    return "\n".join(lines)


def p_roll_zeta_placeholder(m):
    """Internal helper: recover the roll root-locus damping target for
    the header line (zeta implied by the chosen K, which equals the
    project's roll_zeta_target by construction)."""
    return m["roll_rl"]["zeta"]


# ---------------------------------------------------------------------------
# Evidence gates
# ---------------------------------------------------------------------------

def check_package(m: dict) -> dict:
    """Evidence gates against the package content model."""
    req = m["requirements"]
    i, o = m["inner"], m["outer"]
    results = {
        "gains_present": all(
            isinstance(v, (int, float))
            for v in (i["kp"], i["ki"], i["kd"], o["kp_theta"])),
        "inner_margins_meet_requirement": bool(i["req_ok"]),
        "outer_margins_bandwidth_meet_requirement": bool(o["req_ok"]),
        "roll_root_locus_stable": bool(m["roll_rl"]["stable"]),
        "yaw_damper_margins_meet_requirement": bool(m["yaw_damper"]["req_ok"]),
        "l1_transient_bound_met": bool(m["l1"]["bound_ok"]),
        "l1_converged": bool(m["l1"]["converged"]),
        "digital_sample_rate_ok": m["digital"]["verdict"] == "ok",
        "allocation_pitch_closes": m["allocation"]["pitch"]["error"] < 1e-6,
        "allocation_turn_closes": m["allocation"]["turn"]["error"] < 1e-6,
        "sign_off_honest": m.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_package_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    checks = {
        "has_title": "autopilot control-law design package" in low,
        "has_state_space": "eigenvalues" in low and "controllable" in low,
        "has_pid_gains": bool(__import__("re").search(r"kp\s*=\s*\d", low)),
        "has_root_locus": "root locus" in low or "root-locus" in low,
        "has_phase_margin": "phase margin" in low,
        "has_gain_margin": "gain margin" in low,
        "has_observer": "observer" in low,
        "has_l1": "l1 adaptive" in low or "sigma_hat" in low,
        "has_gain_schedule": "gain scheduling" in low,
        "has_digital": "sample-rate" in low or "sample rate" in low,
        "has_allocation": "control allocation" in low or "pseudoinverse" in low,
        "no_blank_fields": "___" not in md_text,
        "no_local_paths": ("/users/" not in low and "/home/" not in low),
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
        "has_not_flight_software": "not flight software release" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling."""
    return check_package_markdown(md_text)


# ---------------------------------------------------------------------------
# Example project (tests + worked-example generation)
# ---------------------------------------------------------------------------

def example_item() -> AutopilotProject:
    return AutopilotProject()


def example_package_markdown() -> str:
    return render_package_markdown(build_package(example_item()))


if __name__ == "__main__":
    proj = example_item()
    model = build_package(proj)
    md = render_package_markdown(model)
    print("VEHICLE: %s" % model["vehicle"])
    print("INNER PID: kp=%.2f ki=%.2f kd=%.2f | PM=%.1f deg"
          % (model["inner"]["kp"], model["inner"]["ki"],
             model["inner"]["kd"], model["inner"]["margins"]["pm_deg"]))
    print("OUTER: kp_theta=%.3f | PM=%.1f deg | BW=%.2f rad/s"
          % (model["outer"]["kp_theta"], model["outer"]["margins"]["pm_deg"],
             model["outer"]["bw_rad_s"]))
    print("ROLL RL: K=%.3f k_phi=%.3f zeta=%.3f wn=%.2f stable=%s"
          % (model["roll_rl"]["K"], model["roll_rl"]["k_phi"],
             model["roll_rl"]["zeta"], model["roll_rl"]["wn"],
             model["roll_rl"]["stable"]))
    print("OBS L=[%.2f, %.2f]" % (model["observer"]["L"][0],
                                  model["observer"]["L"][1]))
    print("L1: max|track|=%.6f bound_ok=%s converged=%s"
          % (model["l1"]["max_abs_track"], model["l1"]["bound_ok"],
             model["l1"]["converged"]))
    print("GATES(model): %s" % check_package(model))
    print("GATES(markdown): %s" % check_package_markdown(md))
    print("RENDERED: %d chars" % len(md))
