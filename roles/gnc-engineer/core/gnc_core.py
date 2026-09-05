#!/usr/bin/env python3
"""gnc_core.py - GNC Engineer executable core.

This is the role's ENGINE: given a vehicle's GNC project facts (plant
model, sensor noise assumptions, design targets) it computes controller
gains (PID pole placement, LQR Riccati solution, observer gains),
stability margins (phase/gain margin from the loop gain), navigation
filter steady state (Kalman covariance and gain), guidance commands
(proportional navigation lateral acceleration), digital design checks
(sample-rate rule, discrete PID coefficients), and a seeded Monte Carlo
robustness pass. It BUILDS the GNC design report content and
gate-checks deliverables. Standalone: stdlib only, no AeroSkills
checkout required.

Domain rules encoded here are the standard textbook methods carried by
the bound Aero Agent Skills leaves (which encode aircraft flight
control / estimation / guidance practice):

- PID design: closed-loop pole placement matching the plant to
  s^2 + 2*zeta*wn*s + wn^2 (and an extra real pole at -p3), from
  gnc-autonomy/control/pid-control-design. Natural frequency wn is
  sized from the required bandwidth via the exact second-order
  bandwidth relation wn_bw = wn*sqrt(1 - 2z^2 + sqrt(2 - 4z^2 + 4z^4)).
- Margins: type-1 open loop L(s) = K/(s(s + a)) closed-form phase
  margin (finite) and gain margin (infinite); general loop margins
  evaluated on the imaginary axis with root-sum unwrapped phase, per
  gnc-autonomy/control/frequency-response-design.
- LQR: K = R^-1 B' P from the algebraic Riccati equation closed form
  for the canonical two-state plant, per gnc-autonomy/optimal-control/
  lqr-design.
- Kalman: steady-state predicted covariance (scalar Riccati root) and
  gain K = h P/(h^2 P + r), per gnc-autonomy/navigation/
  kalman-filter-design.
- Observer: full-order Ackermann gain for the two-state plant, per
  gnc-autonomy/control/observer-design.
- Guidance: proportional navigation lateral acceleration
  a_c = N*Vc*lam_dot with Vc and lam_dot from the relative state, per
  gnc-autonomy/guidance/pursuit-guidance.
- Digital: 10-20 samples per closed-loop cycle rule and discrete PID
  velocity-form coefficients, per gnc-autonomy/control/
  digital-control-design.

MIL-STD-1797A (TIER-1, reference-only=false per standards-map) supplies
handling-qualities context only; no standard text is reproduced.
"""
from __future__ import annotations

import cmath
import math
import random
from dataclasses import dataclass, field
from datetime import date

def _today() -> str:
    import os
    from datetime import date
    return os.environ.get("ROLE_GEN_DATE", date.today().isoformat())

# ---------------------------------------------------------------------------
# Domain rules (textbook formulas carried by the bound leaves)
# ---------------------------------------------------------------------------

_SQRT2 = math.sqrt(2.0)


def second_order_bandwidth_factor(zeta: float) -> float:
    """Exact closed-loop bandwidth factor f(z) for s^2 + 2zw s + w^2:

    f = sqrt(1 - 2z^2 + sqrt(2 - 4z^2 + 4z^4)),  w_bw = f * wn.
    f(0.7071) == 1 exactly (bandwidth equals natural frequency at the
    classic 0.707 damping). Requires 0 < zeta <= 1.
    """
    if not (0.0 < zeta <= 1.0):
        raise ValueError("zeta must lie in (0, 1], got %r" % (zeta,))
    return math.sqrt(1.0 - 2.0 * zeta * zeta
                     + math.sqrt(2.0 - 4.0 * zeta * zeta + 4.0 * zeta ** 4))


def natural_frequency_from_bandwidth(w_bw: float, zeta: float) -> float:
    """Size the natural frequency wn so the closed loop reaches the
    required bandwidth w_bw at damping zeta: wn = w_bw / f(zeta)."""
    if not (isinstance(w_bw, (int, float)) and math.isfinite(w_bw)
            and w_bw > 0.0):
        raise ValueError("w_bw must be a positive finite number, got %r"
                         % (w_bw,))
    return w_bw / second_order_bandwidth_factor(zeta)


def closed_loop_bandwidth(wn: float, zeta: float) -> float:
    """Bandwidth achieved by a second-order loop with wn, zeta."""
    if not (isinstance(wn, (int, float)) and math.isfinite(wn) and wn > 0.0):
        raise ValueError("wn must be a positive finite number, got %r" % (wn,))
    return wn * second_order_bandwidth_factor(zeta)


def pid_gains_first_order(a: float, b: float, wn: float, zeta: float):
    """PI gains (kp, ki) for G(s) = b/(s + a) matched to
    s^2 + 2*zeta*wn*s + wn^2: kp = (2*zeta*wn - a)/b, ki = wn^2/b."""
    if b == 0:
        raise ValueError("b must be nonzero, got %r" % (b,))
    if not (0.0 < zeta <= 1.0):
        raise ValueError("zeta must lie in (0, 1], got %r" % (zeta,))
    if not (isinstance(wn, (int, float)) and wn > 0.0):
        raise ValueError("wn must be > 0, got %r" % (wn,))
    kp = (2.0 * zeta * wn - a) / b
    ki = wn * wn / b
    return kp, ki


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
    # strip leading zeros
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
        disc = cmath.sqrt(bb * bb - 4.0 * a * cc)
        return [(-bb + disc) / (2.0 * a), (-bb - disc) / (2.0 * a)]
    if n == 3:
        # one real root by the trigonometric/Vieta closed form, then
        # synthetic-division deflation to a quadratic
        a, bb, cc, d = c[0], c[1], c[2], c[3]
        p = (3.0 * a * cc - bb * bb) / (3.0 * a * a)
        q = (2.0 * bb ** 3 - 9.0 * a * bb * cc + 27.0 * a * a * d) \
            / (27.0 * a ** 3)
        disc = (q / 2.0) ** 2 + (p / 3.0) ** 3
        if p == 0.0:                       # triply-degenerate case
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
        # synthetic division of c by (s - r1): quotient q1 s^2 + q2 s + q3
        q1 = a
        q2 = bb + q1 * r1
        q3 = cc + q2 * r1
        pair = _poly_roots([q1, q2, q3])
        return [complex(r1, 0.0)] + pair
    raise ValueError("root solving supports degree <= 3, got degree %d" % n)


def _phase_of_loop(num, den, w):
    """Unwrapped phase in degrees of L(jw) = num(jw)/den(jw) at w > 0.

    Computed as a root sum: arg L = sum over zeros of arg(jw - z)
    minus sum over poles of arg(jw - p), exact and continuous for w > 0
    when no root lies on the imaginary axis (a pole at the origin
    contributes a constant +90 deg)."""
    zr = _poly_roots(num)
    pr = _poly_roots(den)
    total = 0.0
    for z in zr:
        total += math.degrees(math.atan2(w - z.imag, -z.real))
    for p in pr:
        total -= math.degrees(math.atan2(w - p.imag, -p.real))
    return total


def _mag_db_of_loop(num, den, w):
    """20*log10 |L(jw)| with exact complex evaluation."""
    s = complex(0.0, w)
    accn = 0.0 + 0.0j
    for c in num:
        accn = accn * s + c
    accd = 0.0 + 0.0j
    for c in den:
        accd = accd * s + c
    return 20.0 * math.log10(abs(accn / accd))


def loop_margins(num: list, den: list) -> dict:
    """Gain/phase margins of an open loop L(s) = num(s)/den(s).

    num/den are descending-power coefficient lists. Returns gain
    crossover w_gc, phase crossover w_pc, gain margin (linear and dB,
    inf when the phase never reaches -180 deg), phase margin (deg, at
    w_gc), and the classic verdict booleans (GM > 0 dB, PM > 0 deg).
    Bisection on the log-frequency axis; deterministic."""
    for poly, name in ((num, "num"), (den, "den")):
        if not isinstance(poly, (list, tuple)) or not poly:
            raise ValueError("%s must be a non-empty coefficient list" % name)
    w_lo, w_hi = 1e-3, 1e5
    # gain crossover: |L| = 1 falls monotonically near crossover for the
    # type-1/type-0 loops used here; bracket then bisect
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
    # phase crossover: unwrapped phase == -180 deg
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


def riccati_solution(A, B, Q, R) -> dict:
    """LQR: algebraic Riccati solution P and gain K = R^-1 B' P for the
    canonical plant A = [[0, 1], [0, -a]] (a >= 0), B = [0, 1],
    Q = diag(q1, q2), R > 0. Closed form (common control theory)."""
    _TOL = 1e-9
    try:
        a = -float(A[1][1])
        if abs(A[0][0]) > _TOL or abs(A[0][1] - 1.0) > _TOL \
                or abs(A[1][0]) > _TOL or abs(B[0]) > _TOL \
                or abs(B[1] - 1.0) > _TOL or a < -_TOL:
            raise ValueError("A/B must be canonical [[0,1],[0,-a]], [0,1]")
        q1, q2 = max(float(Q[0][0]), 0.0), max(float(Q[1][1]), 0.0)
        r = float(R)
    except (TypeError, ValueError, IndexError) as exc:
        raise ValueError("invalid canonical LQR data: %s" % exc)
    if r <= 0.0:
        raise ValueError("R must be > 0, got %r" % (R,))
    a = max(a, 0.0)
    p2 = math.sqrt(r * q1)
    p3 = r * (-a + math.sqrt(a * a + (2.0 * p2 + q2) / r))
    p1 = a * p2 + p2 * p3 / r
    P = [[p1, p2], [p2, p3]]
    K = [p2 / r, p3 / r]
    # closed loop A - B K = [[0, 1], [-k1, -a - k2]]: stable iff
    # trace < 0 and det > 0
    trace = -a - K[1]
    det = K[0]
    disc = trace * trace - 4.0 * det
    if disc >= 0.0:
        s = math.sqrt(disc)
        poles = [((trace + s) / 2.0, 0.0), ((trace - s) / 2.0, 0.0)]
    else:
        s = math.sqrt(-disc)
        poles = [(trace / 2.0, s / 2.0), (trace / 2.0, -s / 2.0)]
    return {"P": P, "K": K, "stable": trace < 0.0 and det > 0.0,
            "poles": poles, "damping_a": a}


def kalman_steady_state(f: float, h: float, q: float, r: float) -> dict:
    """Steady-state scalar Kalman quantities (f, h, q, r constant model).

    P_inf is the positive root of the scalar Riccati equation
    P = f^2 P - f^2 P h^2 P / (h^2 P + r) + q (predicted covariance);
    K = h P/(h^2 P + r) is the steady gain; P_apost = (1 - K h) P is
    the corrected covariance after the update."""
    ff, hh, qq, rr = float(f), float(h), float(q), float(r)
    if hh == 0.0:
        raise ValueError("measurement matrix h must be nonzero")
    if qq < 0.0:
        raise ValueError("process noise q must be >= 0")
    if rr <= 0.0:
        raise ValueError("measurement noise r must be > 0")
    b = rr * (1.0 - ff * ff) - qq * hh * hh
    disc = b * b + 4.0 * hh * hh * qq * rr
    p_inf = (-b + math.sqrt(disc)) / (2.0 * hh * hh)
    k_gain = hh * p_inf / (hh * hh * p_inf + rr)
    p_apost = (1.0 - k_gain * hh) * p_inf
    innov_var = hh * hh * p_inf + rr
    return {"p_pred": p_inf, "gain": k_gain, "p_apost": p_apost,
            "innovation_variance": innov_var}


def observer_gain_2state(A, C, poles) -> dict:
    """Full-order observer gain L (Ackermann) for a two-state plant.

    L = phi(A) O^-1 e_2 with phi(s) = (s - p1)(s - p2), O the
    observability matrix [C; C A]. Closed form for the 2x2 case.
    Observer poles must be strictly stable (negative real part).
    """
    _TOL = 1e-9
    try:
        a00, a01 = float(A[0][0]), float(A[0][1])
        a10, a11 = float(A[1][0]), float(A[1][1])
        c0, c1 = float(C[0][0]), float(C[0][1])
    except (TypeError, ValueError, IndexError) as exc:
        raise ValueError("invalid 2-state observer data: %s" % exc)
    # observability matrix O = [[c0, c1], [c0*a00+c1*a10, c0*a01+c1*a11]]
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
    # phi(A) = A^2 - (p1+p2) A + p1 p2 I
    s_p = p1.real + p2.real
    prod = p1.real * p2.real
    A2 = [[a00 * a00 + a01 * a10, a00 * a01 + a01 * a11],
          [a10 * a00 + a11 * a10, a10 * a01 + a11 * a11]]
    phiA = [[A2[0][0] - s_p * a00 + prod, A2[0][1] - s_p * a01],
            [A2[1][0] - s_p * a10, A2[1][1] - s_p * a11 + prod]]
    # O^-1 e2 = last column of O^-1
    inv_last = [-o01 / det_o, o00 / det_o]
    l1 = phiA[0][0] * inv_last[0] + phiA[0][1] * inv_last[1]
    l2 = phiA[1][0] * inv_last[0] + phiA[1][1] * inv_last[1]
    ts = 4.0 / min(abs(p1.real), abs(p2.real))
    return {"L": [l1, l2], "poles": [p1.real, p2.real],
            "settling_time_s": ts, "observable": True}


def pn_acceleration(rx: float, ry: float, vx: float, vy: float,
                    n_nav: float) -> dict:
    """Proportional navigation command a_c = N * Vc * lam_dot (m/s^2).

    Vc = -(rx vx + ry vy)/r (m/s), lam_dot = (rx vy - ry vx)/r^2
    (rad/s), r = sqrt(rx^2 + ry^2)."""
    rx, ry, vx, vy = (float(v) for v in (rx, ry, vx, vy))
    n = float(n_nav)
    rng = math.hypot(rx, ry)
    if rng <= 1e-12:
        raise ValueError("range must be > 0")
    if n <= 0.0:
        raise ValueError("n_nav must be > 0 (typical N between 3 and 5)")
    vc = -(rx * vx + ry * vy) / rng
    lam_dot = (rx * vy - ry * vx) / (rng * rng)
    return {"range_m": rng, "closing_speed_m_s": vc,
            "los_rate_rad_s": lam_dot, "n_nav": n,
            "accel_cmd_m_s2": n * vc * lam_dot}


def discrete_pid_velocity(Kp: float, Ki: float, Kd: float, T: float) -> dict:
    """Velocity-form discrete PID coefficients {b0, b1, b2, a1}:
    u(k) = u(k-1) + b0 e(k) + b1 e(k-1) + b2 e(k-2), with
    b0 = Kp + Ki*T + Kd/T, b1 = -Kp - 2*Kd/T, b2 = Kd/T, a1 = -1."""
    T = float(T)
    if T <= 0.0:
        raise ValueError("sample period T must be > 0")
    b0 = Kp + Ki * T + Kd / T
    b1 = -Kp - 2.0 * Kd / T
    b2 = Kd / T
    return {"b0": b0, "b1": b1, "b2": b2, "a1": -1.0}


def sample_rate_rule(wb: float, T: float) -> dict:
    """Minimum sample-rate rule: sample 10-20 times per closed-loop
    cycle, w_s_min = 10*wb, T_max = 2*pi/w_s_min. Verdict 'ok' when
    T <= T_max."""
    wb, T = float(wb), float(T)
    if wb <= 0.0 or T <= 0.0:
        raise ValueError("wb and T must be > 0")
    w_s_min = 10.0 * wb
    t_max = 2.0 * math.pi / w_s_min
    return {"w_s_min_rad_s": w_s_min, "t_max_s": t_max,
            "verdict": "ok" if T <= t_max else "too-slow"}


def monte_carlo_outer_margins(a_nom: float, kp_nom: float, draws: int,
                              seed: int, a_tol: float = 0.15,
                              kp_tol: float = 0.10) -> dict:
    """Seeded Monte Carlo of the outer (type-1) loop margins.

    Draws a in [a_nom(1-tol), a_nom(1+tol)] and kp in
    [kp_nom(1-tol), kp_nom(1+tol)] uniformly and evaluates the closed
    form margins and damping each draw. Deterministic (fixed seed)."""
    rng = random.Random(seed)
    pm_min, pm_sum, pm_max = float("inf"), 0.0, float("-inf")
    bw_min = float("inf")
    z_min, z_max = float("inf"), float("-inf")
    n_pass = 0
    for _ in range(int(draws)):
        a = a_nom * (1.0 + a_tol * (2.0 * rng.random() - 1.0))
        kp = kp_nom * (1.0 + kp_tol * (2.0 * rng.random() - 1.0))
        K = kp * a
        m = type1_margins(a, K)
        pm = m["phase_margin_deg"]
        wn = math.sqrt(K)
        z = a / (2.0 * wn)
        pm_min = min(pm_min, pm)
        pm_max = max(pm_max, pm)
        pm_sum += pm
        bw = closed_loop_bandwidth(wn, min(z, 1.0))
        bw_min = min(bw_min, bw)
        z_min, z_max = min(z_min, z), max(z_max, z)
        if pm >= 45.0:
            n_pass += 1
    return {"draws": int(draws), "seed": int(seed),
            "a_tol_pct": 100.0 * a_tol, "kp_tol_pct": 100.0 * kp_tol,
            "pm_min_deg": pm_min, "pm_mean_deg": pm_sum / int(draws),
            "pm_max_deg": pm_max, "bandwidth_min_rad_s": bw_min,
            "zeta_min": z_min, "zeta_max": z_max,
            "passes_ge_45": n_pass,
            "all_pass": n_pass == int(draws)}


# ---------------------------------------------------------------------------
# Project facts
# ---------------------------------------------------------------------------

@dataclass
class GncProject:
    """Vehicle/project facts the role needs to build the report."""
    vehicle: str = "Utility UAV (example cruise condition)"
    mission: str = "Pitch attitude hold autopilot design"
    condition: str = "Cruise, 60 m/s, altitude 3000 m, level flight"
    report_title: str = "GNC Design Report - Pitch Attitude Hold Autopilot"
    # plant (short-period reduced order, elevator to pitch rate)
    short_period_wn_rad_s: float = 6.0
    short_period_zeta: float = 0.55
    elevator_effectiveness: float = 4.0     # b_q, 1/s
    # inner loop design targets
    inner_wn_rad_s: float = 12.0
    inner_zeta: float = 0.9
    inner_p3_rad_s: float = 24.0            # non-dominant closed pole
    # outer loop design target
    outer_zeta_target: float = _SQRT2 / 2.0  # 0.707 -> f(z)=1
    # requirements
    req_bandwidth_rad_s: float = 3.0
    req_phase_margin_deg: float = 45.0
    req_gain_margin_db: float = 6.0
    # navigation facts (attitude estimation filter, 100 Hz)
    nav_dt_s: float = 0.01
    nav_process_var: float = 0.0009          # deg^2 per step (gyro drift)
    nav_meas_var: float = 1.0                # deg^2 (accel-derived pitch)
    nav_budget_deg: float = 0.5              # 1-sigma position budget
    # observer (comparison state feedback) facts
    obs_plant_damping: float = 2.0           # theta_ddot = -2 q + u model
    obs_pole_rad_s: float = 30.0             # double observer pole
    # lqr facts (canonical normalized model)
    lqr_damping_a: float = 2.0
    lqr_q1: float = 10.0
    lqr_q2: float = 1.0
    lqr_r: float = 0.1
    # guidance example facts (terminal approach geometry)
    guide_rx_m: float = 2000.0
    guide_ry_m: float = 500.0
    guide_vx_m_s: float = -180.0
    guide_vy_m_s: float = -30.0
    guide_n_nav: float = 4.0
    guide_heading_rad: float = 0.20
    guide_target_speed_m_s: float = 0.0
    # digital implementation
    sample_period_s: float = 0.01
    # Monte Carlo
    mc_draws: int = 400
    mc_seed: int = 7
    mc_a_tol: float = 0.15
    mc_kp_tol: float = 0.10


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_gnc_report(p: GncProject) -> dict:
    """Run every design computation and assemble the report model."""
    # plant coefficients: G_q(s) = b/(s^2 + a1 s + a0)
    a1 = 2.0 * p.short_period_zeta * p.short_period_wn_rad_s
    a0 = p.short_period_wn_rad_s ** 2
    b = p.elevator_effectiveness

    # inner rate loop: PID pole placement
    kp, ki, kd = pid_gains_second_order(
        a1, a0, b, p.inner_wn_rad_s, p.inner_zeta, p.inner_p3_rad_s)
    # inner open loop L(s) = b (kd s^2 + kp s + ki) / (s(s^2 + a1 s + a0))
    inum = [b * kd, b * kp, b * ki]
    iden = [1.0, a1, a0, 0.0]
    inner_m = loop_margins(inum, iden)
    inner_gm_ok = (inner_m["gain_margin_db"] > 0.0
                   if not math.isinf(inner_m["gain_margin_db"]) else True)
    inner_pm_ok = (inner_m["phase_margin_deg"] > 0.0
                   if not math.isinf(inner_m["phase_margin_deg"]) else True)
    inner_req_ok = (inner_m["phase_margin_deg"] >= p.req_phase_margin_deg
                    and inner_gm_ok
                    and (inner_m["gain_margin_db"] >= p.req_gain_margin_db
                         or math.isinf(inner_m["gain_margin_db"])))

    # outer attitude loop: reduced inner loop ~ lag a/(s+a), a = zeta_i wn_i
    a_lag = p.inner_zeta * p.inner_wn_rad_s
    zt = p.outer_zeta_target
    wn_theta = a_lag / (2.0 * zt)                 # from damping target
    kp_theta = wn_theta ** 2 / a_lag              # omega_n^2 = kp * a_lag
    outer_m = type1_margins(a_lag, kp_theta * a_lag)
    bw_theta = closed_loop_bandwidth(wn_theta, zt)
    zeta_theta = a_lag / (2.0 * wn_theta)
    outer_req_ok = (outer_m["phase_margin_deg"] >= p.req_phase_margin_deg
                    and bw_theta >= p.req_bandwidth_rad_s)

    # digital
    dig = sample_rate_rule(p.inner_wn_rad_s, p.sample_period_s)
    disc = discrete_pid_velocity(kp, ki, kd, p.sample_period_s)

    # nav (attitude estimation Kalman, f = h = 1 model)
    nav = kalman_steady_state(1.0, 1.0, p.nav_process_var, p.nav_meas_var)
    nav_sigma_deg = math.sqrt(nav["p_apost"])
    nav_ok = nav_sigma_deg <= p.nav_budget_deg

    # observer (comparison state-feedback inner design)
    obs_A = [[0.0, 1.0], [0.0, -p.obs_plant_damping]]
    obs_C = [[1.0, 0.0]]
    obs = observer_gain_2state(obs_A, obs_C,
                               [-p.obs_pole_rad_s, -p.obs_pole_rad_s])

    # LQR comparison
    lqr_A = [[0.0, 1.0], [0.0, -p.lqr_damping_a]]
    lqr_B = [0.0, 1.0]
    lqr_Q = [[p.lqr_q1, 0.0], [0.0, p.lqr_q2]]
    lqr = riccati_solution(lqr_A, lqr_B, lqr_Q, p.lqr_r)

    # guidance (PN comparison for the same geometry)
    guide = pn_acceleration(p.guide_rx_m, p.guide_ry_m, p.guide_vx_m_s,
                            p.guide_vy_m_s, p.guide_n_nav)
    los_deg = math.degrees(math.atan2(p.guide_ry_m, p.guide_rx_m))
    heading_error_deg = math.degrees(
        math.atan2(math.sin(los_deg * math.pi / 180.0 - p.guide_heading_rad),
                   math.cos(los_deg * math.pi / 180.0 - p.guide_heading_rad)))
    vi = math.hypot(p.guide_vx_m_s, p.guide_vy_m_s)
    vt = p.guide_target_speed_m_s
    capture = vi > vt
    t_i = guide["range_m"] / (vi - vt) if capture else None

    # Monte Carlo robustness on the outer loop
    mc = monte_carlo_outer_margins(a_lag, kp_theta, p.mc_draws, p.mc_seed,
                                   p.mc_a_tol, p.mc_kp_tol)
    mc_ok = mc["all_pass"]

    model = {
        "document_type": p.report_title,
        "status": "draft-for-review",
        "vehicle": p.vehicle,
        "mission": p.mission,
        "condition": p.condition,
        "generated": _today(),
        # plant
        "plant": {
            "wn_sp": p.short_period_wn_rad_s,
            "zeta_sp": p.short_period_zeta,
            "a1": a1, "a0": a0, "b": b,
            "model": "%.1f / (s^2 + %.1f s + %.1f)"
                     % (b, a1, a0),
        },
        # inner loop
        "inner": {
            "wn": p.inner_wn_rad_s, "zeta": p.inner_zeta,
            "p3": p.inner_p3_rad_s,
            "kp": kp, "ki": ki, "kd": kd,
            "margins": {
                "gm_db": inner_m["gain_margin_db"],
                "pm_deg": inner_m["phase_margin_deg"],
                "wgc": inner_m["gain_crossover_rad_s"],
                "wpc": inner_m["phase_crossover_rad_s"],
            },
            "req_ok": bool(inner_req_ok),
        },
        # outer loop
        "outer": {
            "a_lag": a_lag, "kp_theta": kp_theta,
            "wn_theta": wn_theta, "zeta_theta": zeta_theta,
            "bw_rad_s": bw_theta,
            "margins": {"gm_db": outer_m["gain_margin_db"],
                        "pm_deg": outer_m["phase_margin_deg"],
                        "wgc": outer_m["crossover_rad_s"]},
            "req_ok": bool(outer_req_ok),
        },
        "digital": {
            "T_s": p.sample_period_s,
            "w_s_min": dig["w_s_min_rad_s"],
            "t_max_s": dig["t_max_s"],
            "verdict": dig["verdict"],
            "disc": disc,
        },
        "nav": {
            "dt_s": p.nav_dt_s,
            "q_deg2": p.nav_process_var,
            "r_deg2": p.nav_meas_var,
            "p_pred": nav["p_pred"],
            "gain": nav["gain"],
            "p_apost": nav["p_apost"],
            "sigma_deg": nav_sigma_deg,
            "budget_deg": p.nav_budget_deg,
            "innovation_sigma_deg": math.sqrt(nav["innovation_variance"]),
            "ok": bool(nav_ok),
        },
        "observer": {
            "plant_note": "theta_ddot = -%g q + u (normalized elevator "
                          "pitch acceleration)" % p.obs_plant_damping,
            "L": obs["L"], "poles": obs["poles"],
            "settling_time_s": obs["settling_time_s"],
        },
        "lqr": {
            "a_d": p.lqr_damping_a, "q1": p.lqr_q1, "q2": p.lqr_q2,
            "r": p.lqr_r,
            "P": lqr["P"], "K": lqr["K"], "stable": lqr["stable"],
            "poles": lqr["poles"],
        },
        "guidance": {
            "range_m": guide["range_m"],
            "closing_speed_m_s": guide["closing_speed_m_s"],
            "los_rate_rad_s": guide["los_rate_rad_s"],
            "n_nav": guide["n_nav"],
            "accel_cmd_m_s2": guide["accel_cmd_m_s2"],
            "los_deg": los_deg,
            "heading_rad": p.guide_heading_rad,
            "heading_error_deg": heading_error_deg,
            "capture_possible": capture,
            "intercept_time_s": t_i,
            "interceptor_speed_m_s": vi,
        },
        "mc": mc,
        "mc_ok": bool(mc_ok),
        # requirement record (for gates and conclusions)
        "requirements": {
            "bandwidth_rad_s": p.req_bandwidth_rad_s,
            "phase_margin_deg": p.req_phase_margin_deg,
            "gain_margin_db": p.req_gain_margin_db,
        },
        # verdict rows for the conclusions table
        "verdicts": {
            "inner_margins": "PASS" if inner_req_ok else "FAIL",
            "outer_margins": "PASS" if outer_req_ok else "FAIL",
            "outer_bandwidth": "PASS" if bw_theta >= p.req_bandwidth_rad_s
            else "FAIL",
            "nav_budget": "PASS" if nav_ok else "FAIL",
            "mc_robustness": "PASS" if mc_ok else "FAIL",
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


def render_gnc_report_markdown(m: dict) -> str:
    """Render the report content model as the deliverable markdown."""
    p = m["plant"]
    i = m["inner"]
    o = m["outer"]
    d = m["digital"]
    n = m["nav"]
    ob = m["observer"]
    lq = m["lqr"]
    g = m["guidance"]
    mc = m["mc"]
    req = m["requirements"]
    v = m["verdicts"]
    gm_in = i["margins"]["gm_db"]
    pm_in = i["margins"]["pm_deg"]
    L = ob["L"]
    lines = [
        "# " + m["document_type"],
        "",
        "**Vehicle:** %s" % m["vehicle"],
        "**Condition:** %s" % m["condition"],
        "**Mission / item:** %s" % m["mission"],
        "**Status:** %s" % m["status"],
        "",
        "## 1. Architecture and plant",
        "",
        "- Control architecture: cascade pitch attitude hold - inner pitch "
        "rate (q) loop with PID; outer pitch attitude (theta) loop "
        "(proportional). Guidance and navigation layers analyzed in "
        "sections 2 and 6.",
        "- Frames: body-fixed axes (x forward, z down) for the short-period "
        "model; stability axes for the longitudinal modes; inertial NED for "
        "the guidance geometry.",
        "- Plant (reduced-order short-period, elevator to pitch rate, at the "
        "stated cruise condition):",
        "",
        "  G_q(s) = %s" % p["model"],
        "",
        "  with short-period natural frequency %.1f rad/s, damping %.2f "
        "and elevator effectiveness %.1f 1/s (example trim data; "
        "verify against the vehicle aerodynamic database)." % (
            p["wn_sp"], p["zeta_sp"], p["b"]),
        "- States: pitch rate q (plant state; the short-period model "
        "implicitly includes angle of attack). Input: elevator deflection. "
        "Output: pitch rate q. Pitch attitude theta = q/s for the outer "
        "loop.",
        "- Assumptions: rigid airframe (no aeroelastic modes in this band), "
        "actuator modeled at >= 40 rad/s in the follow-up stage.",
        "",
        "## 2. Navigation",
        "",
        "- Sensor suite: rate gyro (pitch axis) and accelerometer-derived "
        "pitch measurement; scalar attitude Kalman filter at %d Hz."
        % int(round(1.0 / n["dt_s"])),
        "- Noise models: process noise q = %.4f deg^2 per step (integrated "
        "gyro drift), measurement noise r = %.2f deg^2 (accel-derived "
        "pitch, non-accelerated-flight assumption)." % (n["q_deg2"],
                                                        n["r_deg2"]),
        "- Filter: constant model f = 1, h = 1. Steady-state predicted "
        "covariance P = %.4f deg^2; steady-state gain K = %.4f; "
        "post-update covariance P+ = %.4f deg^2." % (
            n["p_pred"], n["gain"], n["p_apost"]),
        "- Attitude (pitch) error budget: 1-sigma = %.3f deg against a "
        "budget of %.1f deg - %s." % (
            n["sigma_deg"], n["budget_deg"],
            "MET" if n["ok"] else "NOT MET"),
        "- Innovation monitor: 1-sigma innovation = %.3f deg."
        % n["innovation_sigma_deg"],
        "- GNSS/RAIM: not part of this attitude channel; the "
        "gnss-pseudorange-positioning / gnss-raim-fde / "
        "dilution-of-precision leaves apply when a full position "
        "navigation solution is in scope.",
        "",
        "## 3. Control design",
        "",
        "Inner pitch-rate loop (PID by pole placement on the short-period "
        "plant, matched to (s^2 + 2 z_i wn_i s + wn_i^2)(s + p3_i)):",
        "",
        "| Loop | Gains | Phase margin | Gain margin | Requirement | Verdict |",
        "|---|---|---|---|---|---|",
        "| inner q (PID) | kp=%.2f, ki=%.2f, kd=%.2f | %.1f deg | %s dB | "
        "PM >= %.0f deg, GM >= %.0f dB | %s |" % (
            i["kp"], i["ki"], i["kd"],
            (pm_in if not math.isinf(pm_in) else float("inf")),
            ("inf" if math.isinf(gm_in) else "%.1f" % gm_in),
            req["phase_margin_deg"], req["gain_margin_db"],
            "PASS" if i["req_ok"] else "FAIL"),
        "| outer theta (P) | kp_theta=%.3f 1/s | %.1f deg | inf dB | "
        "PM >= %.0f deg, GM >= 6 dB | %s |" % (
            o["kp_theta"], o["margins"]["pm_deg"],
            req["phase_margin_deg"],
            "PASS" if o["req_ok"] else "FAIL"),
        "",
        "Inner loop design: wn_i = %.1f rad/s (>= 3x the attitude "
        "bandwidth requirement of %.1f rad/s), zeta_i = %.2f, "
        "non-dominant pole p3_i = %.1f rad/s. Inner open loop "
        "L(s) = C(s) G_q(s): gain crossover %.1f rad/s, phase crossover %s, "
        "phase margin %.1f deg, gain margin %s dB (type-1 loop, phase "
        "recovers above -180 deg so the gain margin is infinite)." % (
            i["wn"], req["bandwidth_rad_s"], i["zeta"], i["p3"],
            i["margins"]["wgc"],
            ("none" if math.isinf(i["margins"]["wpc"])
             else "%.1f rad/s" % i["margins"]["wpc"]),
            pm_in, gm_in),
        "",
        "Outer loop: the closed inner loop is reduced to the lag "
        "a/(s + a) with a = zeta_i * wn_i = %.1f rad/s, so the outer "
        "attitude plant is a/(s(s + a)) (type-1). The proportional gain "
        "kp_theta is sized for damping zeta = %.2f "
        "(f(z) = 1 at z = 0.707, so bandwidth = natural frequency):" % (
            o["a_lag"], o["zeta_theta"]),
        "",
        "- Natural frequency from the bandwidth requirement: "
        "wn,req = w_bw / f(zeta) = %.1f / 1.000 = %.1f rad/s. The "
        "natural frequency implied by the damping target "
        "(wn = a / (2 zeta)) is %.2f rad/s and exceeds the requirement."
        % (req["bandwidth_rad_s"], req["bandwidth_rad_s"],
           o["wn_theta"]),
        "- Achieved: wn_theta = %.2f rad/s, zeta_theta = %.2f, "
        "bandwidth w_bw = %.2f rad/s >= %.1f rad/s requirement (%s), "
        "phase margin %.1f deg >= %.0f deg (%s), gain margin inf dB "
        ">= 6 dB (%s)." % (
            o["wn_theta"], o["zeta_theta"], o["bw_rad_s"],
            req["bandwidth_rad_s"],
            "PASS" if o["bw_rad_s"] >= req["bandwidth_rad_s"] else "FAIL",
            o["margins"]["pm_deg"], req["phase_margin_deg"],
            "PASS" if o["margins"]["pm_deg"] >= req["phase_margin_deg"]
            else "FAIL",
            "PASS"),
        "",
        "## 4. Digital implementation",
        "",
        "- Sample period T = %.3f s (%d Hz); closed-loop characteristic "
        "frequency wn_i = %.1f rad/s." % (d["T_s"], int(round(1.0 / d["T_s"])),
                                          i["wn"]),
        "- Sample-rate rule (10-20 samples per closed-loop cycle): "
        "w_s,min = 10 * wn_i = %.1f rad/s, T_max = %.4f s; verdict: %s "
        "(T = %.3f s <= T_max)." % (
            d["w_s_min"], d["t_max_s"], d["verdict"], d["T_s"]),
        "- Inner PID velocity-form coefficients at T = %.3f s "
        "(u(k) = u(k-1) + b0 e(k) + b1 e(k-1) + b2 e(k-2)): "
        "b0 = %.4f, b1 = %.4f, b2 = %.4f, a1 = -1." % (
            d["T_s"], d["disc"]["b0"], d["disc"]["b1"], d["disc"]["b2"]),
        "",
        "## 5. State estimation (observer)",
        "",
        "- Full-order observer (Luenberger/Ackermann) for the comparison "
        "state-feedback design; plant %s, measured state theta (C = "
        "[1, 0])." % ob["plant_note"],
        "- Observer poles: %.0f rad/s (double) - about 10x faster than the "
        "controller poles (separation principle), settling time "
        "4/sigma = %.3f s." % (ob["poles"][0], ob["settling_time_s"]),
        "- Observer gain L = [%.1f, %.1f]." % (L[0], L[1]),
        "",
        "## 6. Guidance and optimal control",
        "",
        "Guidance (terminal approach example, proportional navigation "
        "comparison; relative state from the nav estimate):",
        "",
        "- Geometry: range r = %.1f m, line-of-sight %.2f deg; heading "
        "error %.2f deg; closing speed Vc = %.2f m/s; line-of-sight rate "
        "%.5f rad/s." % (g["range_m"], g["los_deg"], g["heading_error_deg"],
                         g["closing_speed_m_s"], g["los_rate_rad_s"]),
        "- Commanded lateral acceleration a_c = N * Vc * lam_dot = "
        "%.1f * %.1f * %.5f = %.2f m/s^2 (%.2f g) with N = %.1f; pure "
        "pursuit capture possible (V_i = %.1f m/s > V_t = 0), tail-chase "
        "intercept time ~%.1f s." % (
            g["n_nav"], g["closing_speed_m_s"], g["los_rate_rad_s"],
            g["accel_cmd_m_s2"], g["accel_cmd_m_s2"] / 9.80665,
            g["n_nav"], g["interceptor_speed_m_s"], g["intercept_time_s"]),
        "",
        "Optimal control (LQR comparison on the normalized pitch-axis "
        "model x = [theta, q], x_dot = A x + B u with "
        "A = [[0,1],[0,-%.0f]], B = [0,1], u = normalized elevator pitch "
        "acceleration):" % lq["a_d"],
        "",
        "- Weights: Q = diag(%.0f, %.0f) (state error), R = %.1f (control "
        "effort)." % (lq["q1"], lq["q2"], lq["r"]),
        "- Riccati solution P = [[%.3f, %.3f],[%.3f, %.3f]]; gain "
        "K = R^-1 B' P = [%.2f, %.2f]." % (
            lq["P"][0][0], lq["P"][0][1], lq["P"][1][0], lq["P"][1][1],
            lq["K"][0], lq["K"][1]),
        "- Closed loop A - B K stable: %s (poles at -%.2f +/- j%.2f "
        "rad/s, wn = %.2f rad/s, zeta = %.2f). The LQR result is a "
        "comparison design on the same axis; the PID cascade of section 3 "
        "is the baseline." % (
            "yes" if lq["stable"] else "no",
            -lq["poles"][0][0], abs(lq["poles"][0][1]),
            math.sqrt(lq["K"][0]), lq["a_d"] / (2 * math.sqrt(lq["K"][0]))),
        "",
        "## 7. Space GNC",
        "",
        "- Not applicable for this aircraft example. The space leaves "
        "(attitude-dynamics, orbit-dynamics, orbit-determination, "
        "rendezvous-phasing) load when the vehicle is a spacecraft.",
        "",
        "## 8. Monte Carlo / robustness",
        "",
        "- Monte Carlo on the outer loop (%d draws, seed %d): lag a and "
        "gain kp_theta varied uniformly over +/- %.0f%% (a, inner-loop "
        "uncertainty) and +/- %.0f%% (kp_theta, implementation "
        "tolerance)." % (
            mc["draws"], mc["seed"], mc["a_tol_pct"], mc["kp_tol_pct"]),
        "- Result: phase margin min %.1f deg / mean %.1f deg / max %.1f "
        "deg; all %d draws >= 45 deg (%s); zeta_theta range %.2f-%.2f; "
        "minimum bandwidth %.2f rad/s (still >= %.1f rad/s requirement)."
        % (mc["pm_min_deg"], mc["pm_mean_deg"], mc["pm_max_deg"],
           mc["draws"], "PASS" if mc["all_pass"] else "FAIL",
           mc["zeta_min"], mc["zeta_max"], mc["bandwidth_min_rad_s"],
           req["bandwidth_rad_s"]),
        "- Disturbance response: the rate-loop integral gives zero "
        "steady-state attitude error to constant pitch disturbances "
        "(type-1 loop); transient response and gust loads verified in the "
        "full 6-DOF simulation (open item).",
        "",
        "## 9. Conclusions",
        "",
        "| Gate | Result |",
        "|---|---|",
        "| Inner loop margins vs requirement | %s |" % v["inner_margins"],
        "| Outer loop margins vs requirement | %s |" % v["outer_margins"],
        "| Attitude bandwidth >= %.1f rad/s | %s |" % (
            req["bandwidth_rad_s"], v["outer_bandwidth"]),
        "| Nav error budget (1-sigma <= %.1f deg) | %s |" % (
            n["budget_deg"], v["nav_budget"]),
        "| Monte Carlo robustness (PM >= 45 deg) | %s |" % v["mc_robustness"],
        "",
        "- Margins are design predictions from the stated reduced-order "
        "model and sensor assumptions.",
        "- Open items for flight test / formal verification: full 6-DOF "
        "nonlinear simulation with actuator and aeroelastic models, "
        "sensor-in-the-loop tests, gain-schedule coverage of the flight "
        "envelope, and handling-qualities evaluation per MIL-STD-1797A "
        "where applicable.",
        "",
        "## Appendix A. Calculation traceability",
        "",
        "- PID gains: pole placement matching "
        "(s^2 + 2 z wn s + wn^2)(s + p3) (pid-control-design).",
        "- Bandwidth/natural frequency: w_bw = f(z) wn with "
        "f(z) = sqrt(1 - 2z^2 + sqrt(2 - 4z^2 + 4z^4)); f(0.707) = 1.",
        "- Margins: type-1 loop L = K/(s(s + a)) closed form; general "
        "loops evaluated on jw with root-sum unwrapped phase "
        "(frequency-response-design).",
        "- LQR: K = R^-1 B' P, ARE closed form (lqr-design).",
        "- Kalman: steady-state covariance = scalar Riccati root; "
        "K = h P/(h^2 P + r) (kalman-filter-design).",
        "- Observer: Ackermann L = phi(A) O^-1 e_n (observer-design).",
        "- Guidance: a_c = N Vc lam_dot (pursuit-guidance).",
        "- Digital: 10-20 samples per closed-loop cycle; velocity-form "
        "discrete PID (digital-control-design).",
        "",
        "---",
        "*Generated by Aero Agent Roles gnc-engineer core (%s). DRAFT - "
        "for human GNC lead review. Design predictions only; not flight "
        "software release, not a certification finding, not an approval "
        "document.*" % m["generated"],
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evidence gates
# ---------------------------------------------------------------------------

def _margins_pass(m: dict) -> bool:
    req = m["requirements"]
    i = m["inner"]["margins"]
    o = m["outer"]["margins"]
    ipm = i["pm_deg"]
    igm = i["gm_db"]
    return (not math.isinf(ipm) and ipm >= req["phase_margin_deg"]
            and (math.isinf(igm) or igm >= req["gain_margin_db"])
            and not math.isinf(o["pm_deg"])
            and o["pm_deg"] >= req["phase_margin_deg"])


def check_gnc_report(m: dict) -> dict:
    """Evidence gates against the report content model."""
    req = m["requirements"]
    results = {
        "gains_present": all(
            isinstance(m[k].get(x), (int, float))
            for k, xs in (("inner", ("kp", "ki", "kd")),
                          ("outer", ("kp_theta",))) for x in xs),
        "margins_meet_requirement": bool(_margins_pass(m)),
        "bandwidth_meets_requirement": bool(
            m["outer"]["bw_rad_s"] >= req["bandwidth_rad_s"]),
        "nav_error_budget_met": bool(m["nav"]["ok"]),
        "mc_robustness_pass": bool(m["mc_ok"]),
        "sign_off_honest": m.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_gnc_report_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    checks = {
        "has_title": "gnc design report" in low,
        "has_plant": "g_q(s)" in low,
        "has_gains": bool(__import__("re").search(r"kp\s*=\s*\d", low)),
        "has_phase_margin": "phase margin" in low,
        "has_gain_margin": "gain margin" in low,
        "has_nav_budget": "error budget" in low,
        "no_blank_fields": "___" not in md_text,
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling: check a GNC report."""
    return check_gnc_report_markdown(md_text)


# ---------------------------------------------------------------------------
# Example project (tests + worked-example generation)
# ---------------------------------------------------------------------------

def example_project() -> GncProject:
    return GncProject()


def example_report_markdown() -> str:
    return render_gnc_report_markdown(build_gnc_report(example_project()))


if __name__ == "__main__":
    proj = example_project()
    model = build_gnc_report(proj)
    md = render_gnc_report_markdown(model)
    obs_L = model["observer"]["L"]
    print("VEHICLE: %s" % model["vehicle"])
    print("PLANT: %s" % model["plant"]["model"])
    print("INNER PID: kp=%.2f ki=%.2f kd=%.2f | PM=%.1f deg GM=%s dB"
          % (model["inner"]["kp"], model["inner"]["ki"],
             model["inner"]["kd"], model["inner"]["margins"]["pm_deg"],
             model["inner"]["margins"]["gm_db"]))
    print("OUTER: kp_theta=%.3f | PM=%.1f deg | BW=%.2f rad/s"
          % (model["outer"]["kp_theta"], model["outer"]["margins"]["pm_deg"],
             model["outer"]["bw_rad_s"]))
    print("NAV: 1-sigma=%.3f deg K=%.4f" % (model["nav"]["sigma_deg"],
                                            model["nav"]["gain"]))
    print("GUIDANCE: a_c=%.2f m/s^2" % model["guidance"]["accel_cmd_m_s2"])
    print("LQR K=[%.2f, %.2f] stable=%s" % (model["lqr"]["K"][0],
                                            model["lqr"]["K"][1],
                                            model["lqr"]["stable"]))
    print("OBS L=[%.1f, %.1f]" % (obs_L[0], obs_L[1]))
    print("MC: PM min=%.1f mean=%.1f max=%.1f all_pass=%s"
          % (model["mc"]["pm_min_deg"], model["mc"]["pm_mean_deg"],
             model["mc"]["pm_max_deg"], model["mc"]["all_pass"]))
    print("GATES(model): %s" % check_gnc_report(model))
    print("GATES(markdown): %s" % check_gnc_report_markdown(md))
    print("RENDERED: %d chars" % len(md))
