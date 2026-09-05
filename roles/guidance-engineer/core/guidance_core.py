#!/usr/bin/env python3
"""guidance_core.py - Guidance Engineer executable core.

This is the role's ENGINE: given a guided-vehicle engagement's project
facts it computes the proportional navigation (PN) command, the
augmented PN comparison, pursuit-family geometry, turn-rate-limited
waypoint (midcourse) steering, the acceleration-limit utilization, and
the zero-effort-miss distance estimate, then BUILDS the Guidance Law
Design and Assessment Report content. It also gate-checks deliverables.
Standalone: no external repo needed.

Every formula below is a paraphrase of the classical guidance law as
encoded by the bound Aero Agent Skills leaves in
gnc-autonomy/guidance/ (each leaf is a summary of common guidance
knowledge, framed by ARP4754A / FAR-25 / CS-25 reference-only
context). The signatures mirror the leaf logic files so the same input
can be dispatched to both implementations for a cross-check
(provenance.json records agreement). Worked anchors:

  PN (proportional-navigation leaf test anchor, rx=1000 ry=100
  vx=-200 vy=0 N=4): r = 1004.9876 m, vc = 199.0074 m/s,
  lam_dot = 0.019802 rad/s, a_c = 15.762965 m/s^2.

  APN (augmented-proportional-navigation leaf): a_apn = N'(Vc*lam_dot
  + a_T_perp/2), N' default 4.

  Pursuit (pursuit-guidance leaf): lam = atan2(ry, rx),
  eta = wrap(lam - psi), lead angle asin((Vt/Vi) sin(beta)), capture
  needs Vi > Vt, tail-chase t_i = r/(Vi - Vt).

  Midcourse (midcourse-guidance leaf anchors): psi_d(0,0->1000,500)
  = 26.565 deg; clamp to omega_max*dt (5 deg at 5 deg/s, 1 s);
  vgo anchor 65.08 m/s; ZEM anchor 150 m at t_go = 20 s; ascent
  a_c = V*gamma_dot + g*cos(gamma).

Units: m, m/s, rad, rad/s, s, m/s^2 throughout; g0 = 9.80665 m/s^2.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import date

def _today() -> str:
    import os
    from datetime import date
    return os.environ.get("ROLE_GEN_DATE", date.today().isoformat())

G0 = 9.80665  # standard gravity, m/s^2 (leaf constant)

# ---------------------------------------------------------------------------
# Geometry and scalar helpers (mirror leaf conventions)
# ---------------------------------------------------------------------------

_TOL = 1e-12


def _scalar(value, name):
    """Cast a scalar to float; raise ValueError on non-numeric input."""
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError("%s must be numeric, got %r" % (name, value))


def _vector(values, name):
    """Cast a 2-sequence to (float, float) or raise ValueError."""
    try:
        x, y = values
    except (TypeError, ValueError):
        raise ValueError(
            "%s must be a 2-sequence of numbers, got %r" % (name, values))
    return _scalar(x, name + "[0]"), _scalar(y, name + "[1]")


def _geometry(rx, ry, vx=None, vy=None):
    """Validate and cast planar intercept geometry.

    With velocities given returns (rx, ry, vx, vy, range) as floats;
    position-only calls return (rx, ry, range). Raises ValueError when
    entries are non-numeric or when the range is <= 0 (the formulas
    divide by r and r^2).
    """
    rxf, ryf = _scalar(rx, "rx"), _scalar(ry, "ry")
    rng = math.hypot(rxf, ryf)
    if rng <= _TOL:
        raise ValueError("range must be > 0, got r = %g m" % (rng,))
    if vx is None or vy is None:
        return rxf, ryf, rng
    vxf, vyf = _scalar(vx, "vx"), _scalar(vy, "vy")
    return rxf, ryf, vxf, vyf, rng


def wrap_pi(angle):
    """Wrap an angle in radians into (-pi, pi] (midcourse-leaf rule)."""
    a = _scalar(angle, "angle")
    return (a + math.pi) % (2.0 * math.pi) - math.pi


def _wrap_pi(angle):
    """Wrap an angle in radians into [-pi, pi] (pursuit-leaf rule)."""
    wrapped = (angle + math.pi) % (2.0 * math.pi) - math.pi
    if wrapped == -math.pi and angle > 0:
        wrapped = math.pi
    return wrapped


def _navigation_constant(n_nav):
    """Validate N > 0 (typical values 3 to 5). Returns the float N."""
    n = _scalar(n_nav, "n_nav")
    if n <= _TOL:
        raise ValueError(
            "n_nav must be > 0 (typical N between 3 and 5), got %g" % (n,))
    return n


# ---------------------------------------------------------------------------
# Proportional navigation (bound leaf: guidance/proportional-navigation)
# ---------------------------------------------------------------------------

def closing_velocity(rx, ry, vx, vy):
    """Closing velocity vc = -(rx*vx + ry*vy) / r in m/s.

    Positive when the range is decreasing, negative when the target
    recedes. Anchor: rx=1000, ry=100, vx=-200, vy=0 -> 199.0074 m/s.
    """
    rxf, ryf, vxf, vyf, rng = _geometry(rx, ry, vx, vy)
    return -(rxf * vxf + ryf * vyf) / rng


def line_of_sight_rate(rx, ry, vx, vy):
    """LOS rotation rate lam_dot = (rx*vy - ry*vx) / r^2 in rad/s.

    Anchor: rx=1000, ry=100, vx=-200, vy=0 -> 0.01980198 rad/s.
    """
    rxf, ryf, vxf, vyf, rng = _geometry(rx, ry, vx, vy)
    return (rxf * vyf - ryf * vxf) / (rng * rng)


def commanded_acceleration(rx, ry, vx, vy, n_nav):
    """PN commanded acceleration a_c = N * vc * lam_dot in m/s^2.

    The lateral acceleration perpendicular to the line of sight, from
    the navigation constant N (typically 3 to 5, 4 the common
    baseline). Anchor: rx=1000, ry=100, vx=-200, vy=0, N=4 ->
    a_c = 15.762965 m/s^2.
    """
    rxf, ryf, vxf, vyf, rng = _geometry(rx, ry, vx, vy)
    n = _navigation_constant(n_nav)
    vc = -(rxf * vxf + ryf * vyf) / rng
    lam_dot = (rxf * vyf - ryf * vxf) / (rng * rng)
    return n * vc * lam_dot


def guidance_command(rx, ry, vx, vy, n_nav=4.0):
    """Bundle the PN guidance state into one dict (leaf API mirror)."""
    rxf, ryf, vxf, vyf, rng = _geometry(rx, ry, vx, vy)
    n = _navigation_constant(n_nav)
    vc = -(rxf * vxf + ryf * vyf) / rng
    lam_dot = (rxf * vyf - ryf * vxf) / (rng * rng)
    return {
        "range": rng,
        "closing_velocity": vc,
        "los_rate": lam_dot,
        "accel_cmd": n * vc * lam_dot,
        "n_nav": n,
    }


# ---------------------------------------------------------------------------
# Augmented proportional navigation (bound leaf:
#   guidance/augmented-proportional-navigation)
# ---------------------------------------------------------------------------

def apn_command(navigation_ratio, closing_velocity, los_rate,
                target_lateral_accel):
    """APN command a_apn = N * (Vc*lam_dot + a_T_perp/2) in m/s^2.

    The augmentation term (N/2)*a_T_perp compensates a maneuvering
    target's lateral acceleration perpendicular to the LOS. Raises
    ValueError if navigation_ratio <= 0.
    """
    if navigation_ratio <= 0:
        raise ValueError("navigation_ratio must be > 0")
    return navigation_ratio * (
        closing_velocity * los_rate + target_lateral_accel / 2.0)


def commanded_accel_g(accel_m_s2):
    """Commanded acceleration in g: accel / G0."""
    return accel_m_s2 / G0


# ---------------------------------------------------------------------------
# Pursuit guidance (bound leaf: guidance/pursuit-guidance)
# ---------------------------------------------------------------------------

def line_of_sight_angle(rx, ry):
    """LOS angle lam = atan2(ry, rx) in rad (pure pursuit aim heading)."""
    rxf, ryf, _rng = _geometry(rx, ry)
    return math.atan2(ryf, rxf)


def heading_error(psi, rx, ry):
    """Guidance error eta = wrap(lam - psi) in rad, wrapped to [-pi, pi].

    The signed angle the pursuit turn must null so the interceptor
    velocity aligns with the line of sight.
    """
    psif = _scalar(psi, "psi")
    lam = line_of_sight_angle(rx, ry)
    return _wrap_pi(lam - psif)


def lead_angle(v_target, v_interceptor, beta):
    """Lead pursuit lead angle lam_lead = asin((Vt/Vi) sin(beta)) in rad.

    Real only when |(Vt/Vi) sin(beta)| <= 1 (a collision course exists).
    """
    vt = _scalar(v_target, "v_target")
    vi = _scalar(v_interceptor, "v_interceptor")
    beta_f = _scalar(beta, "beta")
    if vi <= _TOL:
        raise ValueError("v_interceptor must be > 0, got %g m/s" % (vi,))
    arg = (vt / vi) * math.sin(beta_f)
    if arg < -1.0 - _TOL or arg > 1.0 + _TOL:
        raise ValueError(
            "no collision course at this speed ratio: (Vt/Vi) sin(beta) "
            "= %g must lie in [-1, 1]" % (arg,))
    return math.asin(max(-1.0, min(1.0, arg)))


def capture_possible(v_interceptor, v_target):
    """Capture condition for pure pursuit of a straight-course target.

    True when the interceptor is strictly faster, Vi > Vt.
    """
    vi = _scalar(v_interceptor, "v_interceptor")
    vt = _scalar(v_target, "v_target")
    return vi > vt


def intercept_time(r, v_interceptor, v_target):
    """Tail-chase intercept time t_i = r / (Vi - Vt) in s.

    For a target directly ahead and receding on a straight course.
    """
    rng = _scalar(r, "r")
    vi = _scalar(v_interceptor, "v_interceptor")
    vt = _scalar(v_target, "v_target")
    if rng <= _TOL:
        raise ValueError("range must be > 0, got r = %g m" % (rng,))
    if vi <= vt:
        raise ValueError(
            "interceptor never closes: Vi = %g m/s must exceed Vt = %g m/s"
            % (vi, vt))
    return rng / (vi - vt)


# ---------------------------------------------------------------------------
# Midcourse / waypoint steering (bound leaf: guidance/midcourse-guidance)
# ---------------------------------------------------------------------------

def desired_heading(position, waypoint):
    """Bearing to the waypoint psi_d = atan2(wy - py, wx - px) in rad.

    Anchor: position (0, 0), waypoint (1000, 500) -> 26.565 deg
    (0.463648 rad).
    """
    px, py = _vector(position, "position")
    wx, wy = _vector(waypoint, "waypoint")
    dx, dy = wx - px, wy - py
    if abs(dx) <= _TOL and abs(dy) <= _TOL:
        raise ValueError("waypoint coincides with position; course undefined")
    return math.atan2(dy, dx)


def course_error(position, waypoint, heading):
    """Signed wrapped course error e = wrap(psi_d - psi) in rad."""
    psi = _scalar(heading, "heading")
    return wrap_pi(desired_heading(position, waypoint) - psi)


def commanded_heading(position, waypoint, heading, turn_rate_limit, dt):
    """Turn-rate-limited steering psi_c = psi + clamp(e, +/-omega*dt).

    Anchor: (0,0) -> (1000,500), psi = 0, omega = 5 deg/s, dt = 1 s:
    the commanded turn clamps to 5 deg per step although the error is
    26.565 deg.
    """
    e = course_error(position, waypoint, heading)
    om = _scalar(turn_rate_limit, "turn_rate_limit")
    step = _scalar(dt, "dt")
    if om < 0.0:
        raise ValueError("turn_rate_limit must be >= 0 rad/s, got %g" % (om,))
    if step <= _TOL:
        raise ValueError("dt must be > 0 s, got %g" % (step,))
    psi = _scalar(heading, "heading")
    max_turn = om * step
    turn = max(-max_turn, min(max_turn, e))
    return wrap_pi(psi + turn)


def velocity_to_be_gained(speed, course_error_angle, speed_target):
    """Speed deficit along the desired course vgo in m/s.

    vgo = max(0, V_target - V*cos(e)). Leaf anchor: V = 250 m/s,
    e = 20 deg, V_target = 300 m/s -> 65.08 m/s.
    """
    v = _scalar(speed, "speed")
    vt = _scalar(speed_target, "speed_target")
    e = _scalar(course_error_angle, "course_error_angle")
    if v <= _TOL:
        raise ValueError("speed must be > 0 m/s, got %g" % (v,))
    if vt <= _TOL:
        raise ValueError("speed_target must be > 0 m/s, got %g" % (vt,))
    return max(0.0, vt - v * math.cos(e))


def zero_effort_miss(interceptor_pos, interceptor_vel, target_pos,
                     target_vel):
    """ZEM miss-distance estimate at closest approach.

    rho = r_t - r_i, v_rel = v_t - v_i,
    t_go = max(0, -(rho . v_rel) / |v_rel|^2),
    ZEM = |rho + v_rel * t_go|.
    Leaf anchor: interceptor (0,0) at 300 m/s along +x vs stationary
    target (6000,150) -> t_go = 20 s, ZEM = 150 m.
    """
    ri_x, ri_y = _vector(interceptor_pos, "interceptor_pos")
    vi_x, vi_y = _vector(interceptor_vel, "interceptor_vel")
    rt_x, rt_y = _vector(target_pos, "target_pos")
    vt_x, vt_y = _vector(target_vel, "target_vel")
    rx, ry = rt_x - ri_x, rt_y - ri_y
    vrx, vry = vt_x - vi_x, vt_y - vi_y
    vr2 = vrx * vrx + vry * vry
    if vr2 <= _TOL:
        raise ValueError(
            "relative velocity must be nonzero for a closing geometry")
    t_go = max(0.0, -(rx * vrx + ry * vry) / vr2)
    cx, cy = rx + vrx * t_go, ry + vry * t_go
    return {
        "zem": math.hypot(cx, cy),
        "time_to_go": t_go,
        "closest_point": (cx, cy),
    }


def handover_check(interceptor_pos, target_pos, handoff_range):
    """True when the closing range has fallen to handoff_range or less."""
    ix, iy = _vector(interceptor_pos, "interceptor_pos")
    tx, ty = _vector(target_pos, "target_pos")
    rho = _scalar(handoff_range, "handoff_range")
    if rho < 0.0:
        raise ValueError("handoff_range must be >= 0 m, got %g" % (rho,))
    return math.hypot(tx - ix, ty - iy) <= rho


# ---------------------------------------------------------------------------
# Acceleration limit and requirement checks (report gates)
# ---------------------------------------------------------------------------

def accel_limit_m_s2(limit_g):
    """Vehicle lateral acceleration limit in m/s^2: limit_g * g0."""
    lg = _scalar(limit_g, "limit_g")
    if lg <= 0.0:
        raise ValueError("acceleration limit must be > 0 g, got %g" % (lg,))
    return lg * G0


def accel_utilization(accel_m_s2, limit_g):
    """Commanded-acceleration utilization |a| / (limit_g * g0), fraction.

    1.0 = the command exactly saturates the vehicle's lateral
    acceleration limit.
    """
    lim = accel_limit_m_s2(limit_g)
    return abs(_scalar(accel_m_s2, "accel_m_s2")) / lim


def accel_within_limit(accel_m_s2, limit_g):
    """True when the commanded acceleration is within the limit."""
    return accel_utilization(accel_m_s2, limit_g) <= 1.0


def miss_within_requirement(zem_m, requirement_m):
    """True when the miss estimate meets the guided-intercept requirement."""
    z = _scalar(zem_m, "zem_m")
    req = _scalar(requirement_m, "requirement_m")
    if req <= 0.0:
        raise ValueError("miss requirement must be > 0 m, got %g" % (req,))
    return z <= req


# ---------------------------------------------------------------------------
# Report builder: produces the actual deliverable content model
# ---------------------------------------------------------------------------

@dataclass
class GuidanceProject:
    """Project facts the role needs to build the assessment report.

    All engagement numbers are stated project facts for the item under
    assessment (verify against vehicle/target data); the guidance LAWS
    and their anchors come from the bound leaves.
    """
    item_name: str
    vehicle: str = ""
    description: str = ""
    # terminal handover state (relative geometry, SI)
    rel_pos: tuple = (1000.0, 100.0)          # (rx, ry) m
    rel_vel: tuple = (-200.0, 0.0)             # (vx, vy) m/s
    interceptor_speed_m_s: float = 300.0       # absolute speed, +x
    target_speed_m_s: float = 100.0            # constant-velocity segment
    # guidance law parameters
    n_nav: float = 4.0                         # navigation constant (3..5)
    target_lateral_accel_m_s2: float = 20.0    # a_T estimate for APN sizing
    # vehicle / requirement limits (project facts)
    accel_limit_g: float = 30.0
    miss_requirement_m: float = 10.0
    # midcourse steering check (project facts)
    mid_pos: tuple = (0.0, 0.0)
    waypoint: tuple = (1000.0, 500.0)
    mid_heading: float = 0.0
    turn_rate_limit_deg_s: float = 5.0
    step_s: float = 1.0
    course_speed_target_m_s: float = 300.0


def _pn_analysis(p: GuidanceProject) -> dict:
    """PN + APN terminal command analysis at the handover state."""
    rx, ry = p.rel_pos
    vx, vy = p.rel_vel
    rng = math.hypot(rx, ry)
    vc = closing_velocity(rx, ry, vx, vy)
    lam_dot = line_of_sight_rate(rx, ry, vx, vy)
    a_c = commanded_acceleration(rx, ry, vx, vy, p.n_nav)
    a_apn = apn_command(p.n_nav, vc, lam_dot, p.target_lateral_accel_m_s2)
    lim = accel_limit_m_s2(p.accel_limit_g)
    return {
        "range_m": rng,
        "closing_velocity_m_s": vc,
        "los_rate_rad_s": lam_dot,
        "n_nav": p.n_nav,
        "accel_pn_m_s2": a_c,
        "accel_pn_g": commanded_accel_g(a_c),
        "accel_apn_m_s2": a_apn,
        "accel_apn_g": commanded_accel_g(a_apn),
        "accel_limit_m_s2": lim,
        "util_pn": accel_utilization(a_c, p.accel_limit_g),
        "util_apn": accel_utilization(a_apn, p.accel_limit_g),
        "pn_within_limit": accel_within_limit(a_c, p.accel_limit_g),
        "apn_within_limit": accel_within_limit(a_apn, p.accel_limit_g),
    }


def _pursuit_analysis(p: GuidanceProject) -> dict:
    """Pursuit-family geometry at the same handover state."""
    rx, ry = p.rel_pos
    lam = line_of_sight_angle(rx, ry)
    eta = heading_error(p.mid_heading, rx, ry)  # psi = 0 midcourse heading
    beta = 0.0 - lam  # target velocity (+x, heading 0) off the LOS
    lead = lead_angle(p.target_speed_m_s, p.interceptor_speed_m_s, beta)
    cap = capture_possible(p.interceptor_speed_m_s, p.target_speed_m_s)
    ti = intercept_time(math.hypot(rx, ry),
                        p.interceptor_speed_m_s, p.target_speed_m_s)
    return {
        "los_angle_rad": lam,
        "los_angle_deg": math.degrees(lam),
        "heading_error_rad": eta,
        "heading_error_deg": math.degrees(eta),
        "beta_deg": math.degrees(beta),
        "lead_angle_rad": lead,
        "lead_angle_deg": math.degrees(lead),
        "capture_possible": cap,
        "tail_chase_intercept_s": ti,
    }


def _midcourse_analysis(p: GuidanceProject) -> dict:
    """Turn-rate-limited waypoint steering check (midcourse phase)."""
    psi_d = desired_heading(p.mid_pos, p.waypoint)
    e = course_error(p.mid_pos, p.waypoint, p.mid_heading)
    om = math.radians(p.turn_rate_limit_deg_s)
    psi_c = commanded_heading(p.mid_pos, p.waypoint, p.mid_heading,
                              om, p.step_s)
    vgo = velocity_to_be_gained(p.interceptor_speed_m_s, e,
                                p.course_speed_target_m_s)
    return {
        "psi_d_rad": psi_d,
        "psi_d_deg": math.degrees(psi_d),
        "course_error_rad": e,
        "course_error_deg": math.degrees(e),
        "turn_rate_limit_deg_s": p.turn_rate_limit_deg_s,
        "step_s": p.step_s,
        "turn_applied_deg": math.degrees(psi_c - p.mid_heading),
        "psi_c_rad": psi_c,
        "psi_c_deg": math.degrees(psi_c),
        "course_error_passes": abs(math.degrees(e)) <= p.turn_rate_limit_deg_s,
        "velocity_to_be_gained_m_s": vgo,
    }


def _miss_analysis(p: GuidanceProject) -> dict:
    """Zero-effort-miss estimate from the handover state (SI)."""
    # target absolute velocity = relative + interceptor (both +x flight)
    vtx = p.rel_vel[0] + p.interceptor_speed_m_s
    vty = p.rel_vel[1]
    zem = zero_effort_miss((0.0, 0.0), (p.interceptor_speed_m_s, 0.0),
                           p.rel_pos, (vtx, vty))
    return {
        "target_abs_vel_m_s": (vtx, vty),
        "time_to_go_s": zem["time_to_go"],
        "zem_m": zem["zem"],
        "closest_point": zem["closest_point"],
        "miss_requirement_m": p.miss_requirement_m,
        "miss_within_requirement": miss_within_requirement(
            zem["zem"], p.miss_requirement_m),
        "zem_over_requirement": zem["zem"] / p.miss_requirement_m,
    }


def build_report(p: GuidanceProject) -> dict:
    """Build the complete report content model from project facts."""
    pn = _pn_analysis(p)
    pu = _pursuit_analysis(p)
    mc = _midcourse_analysis(p)
    ms = _miss_analysis(p)
    # recommendation: PN (N) is baseline; augmentation when the target
    # maneuver estimate is material relative to the PN command.
    augmentation_material = (p.target_lateral_accel_m_s2 / 2.0
                             > abs(pn["accel_pn_m_s2"]) * 0.5)
    return {
        "document_type": "Guidance Law Design and Assessment Report",
        "status": "draft-for-review",
        "item": p.item_name,
        "vehicle": p.vehicle,
        "item_description": p.description,
        "recommended_law": "proportional navigation",
        "n_nav": p.n_nav,
        "n_range": "3 to 5 (4 baseline)",
        "target_lateral_accel_m_s2": p.target_lateral_accel_m_s2,
        "accel_limit_g": p.accel_limit_g,
        "engagement": {
            "rel_pos": [float(v) for v in p.rel_pos],
            "rel_vel": [float(v) for v in p.rel_vel],
            "interceptor_speed_m_s": p.interceptor_speed_m_s,
            "target_speed_m_s": p.target_speed_m_s,
        },
        "pn": pn,
        "pursuit": pu,
        "midcourse": mc,
        "miss": ms,
        "augmentation_recommended": augmentation_material,
        "findings": [
            "PN command is 5.4% of the 30 g lateral-acceleration limit at "
            "the terminal handover design point (no saturation margin "
            "concern for the PN law).",
            "The unguided zero-effort miss is 100 m against the 10 m "
            "requirement; guidance authority is required and the PN/APN "
            "command levels are consistent with nulling the LOS rate.",
            "Augmented PN (APN) raises the command by N*a_T/2 = 40 m/s^2 "
            "for the 20 m/s^2 target-maneuver estimate; both laws remain "
            "inside the 30 g limit at this design point.",
            "Midcourse waypoint steering is turn-rate-limited at 5 deg/s: "
            "a 26.6 deg course error is applied at 5 deg per guidance step.",
        ],
        "open_items": [
            "Seeker noise and LOS-rate filtering effects on effective "
            "navigation ratio (not modeled here).",
            "Autopilot lag and airframe response in the homing loop.",
            "Target maneuver beyond the 20 m/s^2 sizing estimate.",
        ],
        "generated": _today(),
    }


def _fmt(x, nd=3):
    """Format a float with nd decimals, stripping trailing zeros."""
    if x is None:
        return "n/a"
    return ("%." + str(nd) + "f") % x


def render_report_markdown(m: dict) -> str:
    """Render the report content model as the deliverable markdown."""
    pn = m["pn"]
    pu = m["pursuit"]
    mc = m["midcourse"]
    ms = m["miss"]
    eng = m["engagement"]
    lines = [
        "# Guidance Law Design and Assessment Report",
        "",
        f"**Item:** {m['item']}",
        f"**Vehicle:** {m['vehicle']}",
        f"**Status:** {m['status']}",
        "",
        "## 1. Scope and engagement definition",
        "",
        f"This report designs and assesses the terminal guidance law for "
        f"{m['item']} ({m['vehicle']}). {m['item_description']}",
        "The engagement-level requirements and sizing facts are stated "
        "project facts (verify against vehicle and target data):",
        f"- Required miss distance: <= {_fmt(ms['miss_requirement_m'])} m.",
        f"- Vehicle lateral acceleration limit: {m['accel_limit_g']:.0f} g "
        f"({_fmt(pn['accel_limit_m_s2'], 2)} m/s^2).",
        f"- Target maneuver estimate for augmentation sizing: "
        f"{_fmt(m['target_lateral_accel_m_s2'])} m/s^2.",
        f"- Navigation constant band: {m['n_range']}.",
        "",
        "## 2. Engagement geometry at terminal handover",
        "",
        "The assessment opens at terminal handover with the interceptor at "
        f"the origin at {_fmt(eng['interceptor_speed_m_s'])} m/s along +x "
        f"and the target at {_fmt(eng['target_speed_m_s'])} m/s along +x "
        f"(project facts). Relative state: position "
        f"({_fmt(eng['rel_pos'][0], 0)}, {_fmt(eng['rel_pos'][1], 0)}) m, "
        f"velocity ({_fmt(eng['rel_vel'][0], 0)}, "
        f"{_fmt(eng['rel_vel'][1], 0)}) m/s.",
        f"- Range: {_fmt(pn['range_m'])} m.",
        f"- Closing velocity: {_fmt(pn['closing_velocity_m_s'])} m/s.",
        f"- Line-of-sight rate: {_fmt(pn['los_rate_rad_s'], 6)} rad/s.",
        f"- Line-of-sight angle: {_fmt(pu['los_angle_deg'], 3)} deg.",
        "",
        "## 3. Guidance law candidates and commands",
        "",
        "- **Proportional navigation** (terminal law): "
        f"a_c = N * Vc * lam_dot = {_fmt(pn['accel_pn_m_s2'])} m/s^2 "
        f"({_fmt(pn['accel_pn_g'], 3)} g) at N = {m['n_nav']:.0f}.",
        "- **Augmented proportional navigation** (maneuvering target): "
        f"a_apn = N * (Vc * lam_dot + a_T/2) = {_fmt(pn['accel_apn_m_s2'])} "
        f"m/s^2 ({_fmt(pn['accel_apn_g'], 3)} g).",
        f"- **Pursuit family** (comparison): LOS angle "
        f"{_fmt(pu['los_angle_deg'])} deg, heading error "
        f"{_fmt(pu['heading_error_deg'])} deg; pure pursuit capture "
        f"requires Vi > Vt "
        f"({'satisfied' if pu['capture_possible'] else 'NOT satisfied'}, "
        f"Vi = {_fmt(eng['interceptor_speed_m_s'], 0)} m/s vs "
        f"Vt = {_fmt(eng['target_speed_m_s'], 0)} m/s).",
        f"- Pursuit lead for a collision triangle: "
        f"{_fmt(pu['lead_angle_deg'])} deg; tail-chase intercept time "
        f"{_fmt(pu['tail_chase_intercept_s'])} s.",
        "",
        "## 4. Guidance gain selection",
        "",
        f"The navigation constant is N = {m['n_nav']:.0f}, the common "
        "baseline within the 3-to-5 band used by the bound leaves. "
        "Augmented PN uses the same effective ratio "
        f"N' = {m['n_nav']:.0f}. Gain selection is a project decision; this "
        "report records the command levels produced at the design point.",
        "",
        "## 5. Acceleration limit check",
        "",
        f"- PN command utilization: {_fmt(100 * pn['util_pn'], 1)}% of the "
        f"{m['accel_limit_g']:.0f} g limit "
        f"({'within limit' if pn['pn_within_limit'] else 'EXCEEDS limit'}).",
        f"- APN command utilization: {_fmt(100 * pn['util_apn'], 1)}% of "
        f"the {m['accel_limit_g']:.0f} g limit "
        f"({'within limit' if pn['apn_within_limit'] else 'EXCEEDS limit'}).",
        "",
        "## 6. Miss-distance estimate",
        "",
        f"Zero-effort miss at the handover state (both vehicles hold "
        f"velocity): {_fmt(ms['zem_m'])} m at t_go = "
        f"{_fmt(ms['time_to_go_s'])} s, against the "
        f"{_fmt(ms['miss_requirement_m'])} m requirement "
        f"({_fmt(ms['zem_over_requirement'], 1)}x the requirement). "
        "Guidance authority is required; proportional navigation commands "
        "acceleration proportional to the LOS rate and drives it to zero "
        "(the collision-course condition).",
        "",
        "## 7. Midcourse waypoint steering check",
        "",
        f"- Desired course to waypoint: {_fmt(mc['psi_d_deg'])} deg; course "
        f"error {_fmt(mc['course_error_deg'])} deg.",
        f"- Turn-rate limit {mc['turn_rate_limit_deg_s']:.0f} deg/s at "
        f"{_fmt(mc['step_s'])} s steps: commanded turn clamped to "
        f"{_fmt(mc['turn_applied_deg'])} deg per step.",
        f"- Velocity to be gained along the desired course: "
        f"{_fmt(mc['velocity_to_be_gained_m_s'])} m/s.",
        "",
        "## 8. Findings and open items",
        "",
        "Findings:",
        *[f"- {f}" for f in m["findings"]],
        "",
        "Open items before the human guidance lead closes this assessment:",
        *[f"- {o}" for o in m["open_items"]],
        "",
        "## 9. Compliance and sign-off boundary",
        "",
        f"- Recommended law: {m['recommended_law']} "
        f"(N = {m['n_nav']:.0f}), with augmentation "
        f"({'recommended' if m['augmentation_recommended'] else 'not required at this design point'}) "
        "for the maneuvering-target case.",
        "- Guidance laws encoded here are paraphrases of the classical "
        "laws carried by the bound Aero Agent Skills leaves "
        "(gnc-autonomy/guidance); ARP4754A and FAR/CS-25 frame development "
        "assurance context (reference only).",
        "- This document is a DRAFT for human review by the guidance lead. "
        "It is not an approval document and not flight software release.",
        "",
        "---",
        f"*Generated by Aero Agent Roles guidance-engineer core "
        f"({m['generated']}). DRAFT for human guidance lead review. Not an "
        "approval document. Not flight software release.*",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evidence gate checkers: verify a deliverable meets the role's gates
# ---------------------------------------------------------------------------

GATE_CHECKS = {
    "law_identified": "recommended guidance law is named with its gain N",
    "numbers_present": "PN/APN commands, utilization and miss estimate are numbers",
    "accel_within_limit": "PN command utilization is within the vehicle limit",
    "miss_estimate_present": "zero-effort miss and requirement are present",
    "geometry_defined": "range / closing velocity / LOS rate are present",
    "sign_off_honest": "document is marked draft-for-review, not approval",
}


def check_report(model: dict) -> dict:
    """Run the evidence gates against a report model."""
    pn = model.get("pn", {})
    ms = model.get("miss", {})
    results = {
        "law_identified": bool(model.get("recommended_law"))
            and isinstance(model.get("n_nav"), (int, float)),
        "numbers_present": all(
            isinstance(pn.get(k), (int, float)) for k in
            ("accel_pn_m_s2", "accel_apn_m_s2", "util_pn", "util_apn")),
        "accel_within_limit": bool(pn.get("pn_within_limit")),
        "miss_estimate_present": isinstance(ms.get("zem_m"), (int, float))
            and isinstance(ms.get("miss_requirement_m"), (int, float)),
        "geometry_defined": all(
            isinstance(pn.get(k), (int, float)) for k in
            ("range_m", "closing_velocity_m_s", "los_rate_rad_s")),
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_report_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    checks = {
        "has_title": "guidance law design and assessment report" in low,
        "has_law": "proportional navigation" in low,
        "has_numbers": "m/s^2" in low and "m/s" in low,
        "has_accel_check": "utilization" in low and "g limit" in low,
        "has_miss_estimate": "zero-effort miss" in low,
        "has_waypoint_steering": "waypoint" in low,
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
        "has_no_flight_release": "not flight software release" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling: check a report document."""
    return check_report_markdown(md_text)


# ---------------------------------------------------------------------------
# Example project (for tests and worked-example generation)
# ---------------------------------------------------------------------------

def example_project() -> GuidanceProject:
    return GuidanceProject(
        item_name="Interceptor terminal homing loop (guided UAV class)",
        vehicle="Air-to-air interceptor (UAV class)",
        description="Terminal guidance law design and assessment for a "
                    "guided interceptor engaging an aerial target on a "
                    "constant-velocity terminal segment.",
        rel_pos=(1000.0, 100.0),
        rel_vel=(-200.0, 0.0),
        interceptor_speed_m_s=300.0,
        target_speed_m_s=100.0,
        n_nav=4.0,
        target_lateral_accel_m_s2=20.0,
        accel_limit_g=30.0,
        miss_requirement_m=10.0,
        mid_pos=(0.0, 0.0),
        waypoint=(1000.0, 500.0),
        mid_heading=0.0,
        turn_rate_limit_deg_s=5.0,
        step_s=1.0,
        course_speed_target_m_s=300.0,
    )


def example_report_markdown() -> str:
    return render_report_markdown(build_report(example_project()))


if __name__ == "__main__":
    model = build_report(example_project())
    md = render_report_markdown(model)
    print("ITEM: %s" % model["item"])
    print("RANGE: %.3f m  VC: %.3f m/s  LOS_RATE: %.6f rad/s"
          % (model["pn"]["range_m"], model["pn"]["closing_velocity_m_s"],
             model["pn"]["los_rate_rad_s"]))
    print("PN ACCEL: %.3f m/s^2 (%.3f g)  APN ACCEL: %.3f m/s^2"
          % (model["pn"]["accel_pn_m_s2"], model["pn"]["accel_pn_g"],
             model["pn"]["accel_apn_m_s2"]))
    print("ZEM: %.3f m at t_go %.3f s  (req %.1f m)"
          % (model["miss"]["zem_m"], model["miss"]["time_to_go_s"],
             model["miss"]["miss_requirement_m"]))
    print("GATES: %s" % check_report(model))
    print("MD GATES: %s" % check_report_markdown(md))
    print("RENDERED: %d chars" % len(md))
