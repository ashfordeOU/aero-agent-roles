#!/usr/bin/env python3
"""flight_management_core.py - Flight Management Engineer executable core.

This is the role's ENGINE. Given a candidate route's project facts
(waypoints, leg types, RNP value, hold data, RTA demand, aircraft
performance inputs) it computes the RNAV/RNP route assessment content:

- route structure: great-circle leg tracks/distances (lateral-navigation
  leaf math), total track distance (flight-planning), rhumb-line vs
  great-circle distance comparison (rhumb-line-leg);
- RF (radius-to-fix) leg construction: turn centre, swept angle, arc
  length, exit track, chord (radius-to-fix-leg);
- DME arc leg checks: arc length, chord, bank angle to hold the arc,
  turn radius (dme-arc-leg);
- RNP containment: ANP from the lateral 1-sigma error (95% containment =
  2 x sigma), required margin, pass/fail verdict (rnp-anp-containment);
- holding pattern entry: 70/110 sector rule, outbound leg timing,
  1-in-60 wind correction, entry lap estimate (holding-pattern-entry);
- RTA time control: ETA, required ground speed/Mach, achievable window,
  feasibility verdict (rta-time-control);
- VNAV vertical profile: top of descent, descent gradient, flight path
  angle, altitude at a fix, constraint verdict (vertical-navigation +
  flight-planning constraints), ECON cruise speed from the cost index
  (performance-computation);
- radio navaid geometry: DME slant range, VOR bearing/radial
  (radio-navigation-aids).

Every formula below is mirrored from the bound AeroSkills leaf logic
(avionics/flight-management/<leaf>/scripts/*_logic.py) or is a standard
public geometric/physical equation (spherical great-circle, coordinated
turn, ISA atmosphere). No proprietary standard text is reproduced; RNP /
RNP AR / PBN behaviour is summarized from public guidance (FAA AC
90-105A, AC 90-101A) and the RTCA DO-236C family is referenced
summary-only (see SOURCES.md). Constants are the leaf constants; the
performance model is the leaves' documented simplified mid-size
transport model and must be calibrated per aircraft.

Standalone: stdlib only, deterministic, offline, no AeroSkills needed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

# ---------------------------------------------------------------------------
# Physical / unit constants (SI base where noted)
# ---------------------------------------------------------------------------
NM_TO_M = 1852.0            # nautical mile to metre
M_TO_NM = 1.0 / NM_TO_M
KT_TO_MS = 0.514444         # knot to m/s
G_MS2 = 9.80665             # standard gravity, m/s^2
R_EARTH_M = 6371000.0       # spherical Earth radius (WGS-84 mean), m
FT_TO_M = 0.3048            # foot to metre
NM_TO_FT = 6076.1154        # feet per nautical mile
DEG_LAT_M = math.pi * R_EARTH_M / 180.0   # metres per degree of latitude

# ISA atmosphere (rta-time-control / performance-computation leaves)
GAMMA_AIR = 1.4             # ratio of specific heats, air
R_AIR = 287.05              # specific gas constant, J/(kg K)
ISA_SL_TEMP_K = 288.15      # ISA sea-level temperature, K
ISA_LAPSE_K_PER_M = 0.0065  # ISA troposphere lapse rate, K/m
ISA_TROPOPAUSE_M = 11000.0  # tropopause altitude, m

# RTA acceptance tolerance (rta-time-control leaf)
RTA_TIME_TOL_S = 5.0

# ---------------------------------------------------------------------------
# RNP / ANP containment  (bound leaf: rnp-anp-containment)
# ---------------------------------------------------------------------------
CONTAINMENT_SIGMA = 2.0     # ANP = 95th-percentile bound = 2 x 1-sigma error
VALID_VERDICTS = ("PASS", "FAIL")


def anp_from_sigma(sigma_lateral_m):
    """ANP as the 95th percentile containment bound: 2 * sigma (m)."""
    if sigma_lateral_m is None or sigma_lateral_m < 0.0:
        raise ValueError("sigma_lateral_m must be non-negative")
    return CONTAINMENT_SIGMA * float(sigma_lateral_m)


def containment_margin_m(rnp_m, margin_fraction=0.0):
    """Required margin in metres: rnp * margin_fraction."""
    if rnp_m is None or rnp_m <= 0.0:
        raise ValueError("rnp_m must be positive")
    if margin_fraction is None or margin_fraction < 0.0:
        raise ValueError("margin_fraction must be non-negative")
    return float(rnp_m) * margin_fraction


def containment_pass(anp_m, rnp_m, margin_fraction=0.0):
    """True when anp + required margin <= rnp (boundary inclusive)."""
    if anp_m is None or anp_m < 0.0:
        raise ValueError("anp_m must be non-negative")
    return (float(anp_m) + containment_margin_m(rnp_m, margin_fraction)
            <= float(rnp_m))


def margin_available_m(anp_m, rnp_m, margin_fraction=0.0):
    """Reserve left after the required margin: rnp - margin - anp (m)."""
    if anp_m is None or anp_m < 0.0:
        raise ValueError("anp_m must be non-negative")
    return (float(rnp_m) - containment_margin_m(rnp_m, margin_fraction)
            - float(anp_m))


def rnp_nm_to_m(rnp_nm):
    """Convert an RNP value in NM to metres (RNP 0.3 = 555.6 m)."""
    if rnp_nm is None or rnp_nm <= 0.0:
        raise ValueError("rnp_nm must be positive")
    return float(rnp_nm) * NM_TO_M


def containment_analysis(sigma_lateral_m=None, anp_m=None, rnp_m=0.3 * NM_TO_M,
                         margin_fraction=0.0):
    """Full containment check; anp taken directly or derived as 2*sigma.

    Returns {anp_m, rnp_m, required_margin_m, margin_available_m,
    pass, verdict}. Mirrors the bound rnp-anp-containment leaf analyze().
    """
    if anp_m is not None:
        anp = anp_from_sigma(anp_m / CONTAINMENT_SIGMA)
    else:
        if sigma_lateral_m is None:
            raise ValueError("supply sigma_lateral_m or anp_m")
        anp = anp_from_sigma(sigma_lateral_m)
    rnp = float(rnp_m)
    margin = containment_margin_m(rnp, margin_fraction)
    ok = containment_pass(anp, rnp, margin_fraction)
    return {
        "anp_m": round(anp, 3),
        "anp_nm": round(anp * M_TO_NM, 4),
        "rnp_m": round(rnp, 3),
        "rnp_nm": round(rnp * M_TO_NM, 4),
        "required_margin_m": round(margin, 3),
        "margin_available_m": round(margin_available_m(anp, rnp,
                                                       margin_fraction), 3),
        "pass": bool(ok),
        "verdict": "PASS" if ok else "FAIL",
    }


# ---------------------------------------------------------------------------
# Holding pattern entry  (bound leaf: holding-pattern-entry)
# ---------------------------------------------------------------------------
HOLD_DIRECT_SECTOR_LIMIT_DEG = 70.0
HOLD_TEARDROP_SECTOR_LIMIT_DEG = 110.0
VALID_ENTRY_TYPES = ("direct", "teardrop", "parallel")
VALID_TURN_DIRECTIONS = ("right", "left")
HOLD_LEG_ALTITUDE_THRESHOLD_FT = 14000.0
LOW_ALTITUDE_LEG_S = 60.0
HIGH_ALTITUDE_LEG_S = 90.0
HOLD_ENTRY_LAP_OFFSET_S = {
    "direct": 3 * 60.0, "teardrop": 4 * 60.0, "parallel": 5 * 60.0}


def _wrap_deg(angle):
    return angle % 360.0


def hold_alpha_deg(arrival_track_deg, hold_inbound_course_deg):
    """Approach angle to the holding axis, [0, 180].

    alpha is the smaller angle between the aircraft's track INTO the fix
    (the arrival leg track) and the holding pattern axis (the inbound
    course of the hold). Dead-on approach = 0 deg; approach along the
    outbound-course direction = 180 deg. This is the standard
    70/110-sector-rule basis: the sector classification consumes alpha
    measured on the holding side (the bound holding-pattern-entry leaf
    documents the same input convention).
    """
    diff = abs(_wrap_deg(arrival_track_deg) - _wrap_deg(hold_inbound_course_deg))
    alpha = diff if diff <= 180.0 else 360.0 - diff
    return alpha


def holding_entry_type(alpha_deg, turn_direction="right"):
    """Classify entry as direct / teardrop / parallel (70/110 rule).

    alpha <= 70 deg: direct; 70 < alpha <= 110 deg: teardrop; alpha >
    110 deg: parallel. alpha measured on the holding side in [0, 180];
    a left-hand hold mirrors the sectors and the same thresholds apply.
    """
    if turn_direction not in VALID_TURN_DIRECTIONS:
        raise ValueError("turn_direction must be 'right' or 'left'")
    if alpha_deg < 0.0 or alpha_deg > 180.0:
        raise ValueError("alpha_deg must lie in [0, 180]")
    if alpha_deg <= HOLD_DIRECT_SECTOR_LIMIT_DEG:
        return "direct"
    if alpha_deg <= HOLD_TEARDROP_SECTOR_LIMIT_DEG:
        return "teardrop"
    return "parallel"


def outbound_leg_seconds(altitude_ft):
    """Outbound leg timing: 60 s at/below 14000 ft, 90 s above."""
    if altitude_ft is None or altitude_ft < 0.0:
        raise ValueError("altitude_ft must be non-negative")
    if altitude_ft <= HOLD_LEG_ALTITUDE_THRESHOLD_FT:
        return LOW_ALTITUDE_LEG_S
    return HIGH_ALTITUDE_LEG_S


def wind_corrected_heading(outbound_heading_deg, wind_from_deg,
                           wind_speed_kt, tas_kt):
    """1-in-60 crosswind correction of the outbound heading, [0, 360)."""
    if tas_kt is None or tas_kt <= 0.0:
        raise ValueError("tas_kt must be positive")
    if wind_speed_kt is None or wind_speed_kt < 0.0:
        raise ValueError("wind_speed_kt must be non-negative")
    crosswind = (wind_speed_kt
                 * math.sin(math.radians(wind_from_deg - outbound_heading_deg)))
    correction = 60.0 * crosswind / tas_kt
    return _wrap_deg(outbound_heading_deg + correction), correction


def holding_entry_lap_seconds(entry, outbound_seconds):
    """First (entry) lap time: one timed outbound leg + sector offset."""
    if entry not in VALID_ENTRY_TYPES:
        raise ValueError("entry must be direct/teardrop/parallel")
    if outbound_seconds <= 0.0:
        raise ValueError("outbound_seconds must be positive")
    return outbound_seconds + HOLD_ENTRY_LAP_OFFSET_S[entry]


def hold_entry_analysis(arrival_track_deg, hold_inbound_course_deg,
                        turn_direction, altitude_ft, outbound_heading_deg,
                        wind_from_deg, wind_speed_kt, tas_kt):
    """Full holding assessment dict for a fix on the route."""
    alpha = hold_alpha_deg(arrival_track_deg, hold_inbound_course_deg)
    entry = holding_entry_type(alpha, turn_direction)
    leg_s = outbound_leg_seconds(altitude_ft)
    corrected, correction_raw = wind_corrected_heading(
        outbound_heading_deg, wind_from_deg, wind_speed_kt, tas_kt)
    return {
        "arrival_track_deg": round(float(arrival_track_deg) % 360.0, 1),
        "hold_inbound_course_deg": round(float(hold_inbound_course_deg) % 360.0, 1),
        "alpha_deg": round(alpha, 1),
        "turn_direction": turn_direction,
        "entry": entry,
        "hold_altitude_ft": int(altitude_ft),
        "outbound_leg_s": leg_s,
        "outbound_heading_deg": round(float(outbound_heading_deg) % 360.0, 1),
        "wind_from_deg": float(wind_from_deg) % 360.0,
        "wind_speed_kt": float(wind_speed_kt),
        "tas_kt": float(tas_kt),
        "wind_corrected_heading_deg": round(corrected, 2),
        "wind_correction_deg": round(correction_raw, 2),
        "entry_lap_s": holding_entry_lap_seconds(entry, leg_s),
        "direct_sector_deg": HOLD_DIRECT_SECTOR_LIMIT_DEG,
        "teardrop_sector_deg": HOLD_TEARDROP_SECTOR_LIMIT_DEG,
    }


# ---------------------------------------------------------------------------
# Great-circle lateral geometry  (bound leaf: lateral-navigation)
# ---------------------------------------------------------------------------
def _check_lat(lat, name="lat"):
    if lat is None or not math.isfinite(float(lat)) \
            or abs(float(lat)) > 90.0:
        raise ValueError("%s out of range [-90, 90]" % name)


def great_circle_distance_m(lat1, lon1, lat2, lon2):
    """Spherical great-circle distance in metres (R = 6371000 m)."""
    _check_lat(lat1, "lat1")
    _check_lat(lat2, "lat2")
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_lon = math.radians(lon2 - lon1)
    cos_sigma = (math.sin(p1) * math.sin(p2)
                 + math.cos(p1) * math.cos(p2) * math.cos(d_lon))
    cos_sigma = max(-1.0, min(1.0, cos_sigma))
    return R_EARTH_M * math.acos(cos_sigma)


def great_circle_track_deg(lat1, lon1, lat2, lon2):
    """Initial great-circle track in true degrees [0, 360)."""
    _check_lat(lat1, "lat1")
    _check_lat(lat2, "lat2")
    if lat1 == lat2 and lon1 == lon2:
        raise ValueError("identical positions: track undefined")
    d_lon = math.radians(lon2 - lon1)
    y = math.sin(d_lon) * math.cos(math.radians(lat2))
    x = (math.cos(math.radians(lat1)) * math.sin(math.radians(lat2))
         - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.cos(d_lon))
    return math.degrees(math.atan2(y, x)) % 360.0


def _offset_waypoint(lat, lon, x_east_nm, y_north_nm):
    """Approximate lat/lon of a local tangent-plane offset (NM) at (lat, lon).

    Local frame: x = east (NM), y = north (NM); the same short-range
    tangent-plane convention used by the bound radius-to-fix leaf. The
    longitude scaling uses the mid-latitude cosine. Documented short-range
    approximation only.
    """
    dlat = y_north_nm * NM_TO_M / DEG_LAT_M
    mid_lat = lat + dlat / 2.0
    dlon = (x_east_nm * NM_TO_M
            / (DEG_LAT_M * math.cos(math.radians(mid_lat))))
    return lat + dlat, lon + dlon


# ---------------------------------------------------------------------------
# Radius-to-fix (RF) leg  (bound leaf: radius-to-fix-leg)
# ---------------------------------------------------------------------------
def _compass_bearing_deg(dx, dy):
    return math.degrees(math.atan2(dx, dy)) % 360.0


def rf_turn_center(ef, inbound_track_deg, radius_nm, turn):
    """Turn centre C = EF + R * n (n on the turn side), in NM."""
    if radius_nm is None or radius_nm <= 0.0:
        raise ValueError("radius must be positive")
    if turn not in VALID_TURN_DIRECTIONS and turn.upper() not in ("RIGHT", "LEFT"):
        raise ValueError("turn must be RIGHT or LEFT")
    t = math.radians(inbound_track_deg)
    x_ef, y_ef = ef
    if turn.upper() == "RIGHT":
        nx, ny = math.cos(t), -math.sin(t)
    else:
        nx, ny = -math.cos(t), math.sin(t)
    return (x_ef + radius_nm * nx, y_ef + radius_nm * ny)


def rf_leg_geometry(ef, inbound_track_deg, radius_nm, turn, sweep_deg):
    """Construct an RF leg from entry fix, inbound track, radius, turn,
    published swept angle, and return the full geometry dict.

    The exit fix is placed on the radius circle at the published swept
    angle (standard RF path construction: arc angle is part of the
    published leg definition), so exit_on_arc is True by construction and
    valid = sweep_deg > 0. All distances in NM in the EF local frame.
    """
    if sweep_deg is None or sweep_deg <= 0.0 or sweep_deg >= 360.0:
        raise ValueError("sweep_deg must lie in (0, 360)")
    center = rf_turn_center(ef, inbound_track_deg, radius_nm, turn)
    cx, cy = center
    radial_ef = _compass_bearing_deg(ef[0] - cx, ef[1] - cy)
    if turn.upper() == "RIGHT":
        radial_xf = (radial_ef + sweep_deg) % 360.0
    else:
        radial_xf = (radial_ef - sweep_deg) % 360.0
    xf = (cx + radius_nm * math.sin(math.radians(radial_xf)),
          cy + radius_nm * math.cos(math.radians(radial_xf)))
    arc_len = radius_nm * math.radians(sweep_deg)
    exit_track = (radial_xf + 90.0) % 360.0 if turn.upper() == "RIGHT" \
        else (radial_xf - 90.0) % 360.0
    chord = math.hypot(xf[0] - ef[0], xf[1] - ef[1])
    return {
        "ef": (round(ef[0], 3), round(ef[1], 3)),
        "xf": (round(xf[0], 3), round(xf[1], 3)),
        "center_nm": (round(cx, 3), round(cy, 3)),
        "inbound_track_deg": round(float(inbound_track_deg) % 360.0, 1),
        "radius_nm": float(radius_nm),
        "turn": turn.upper(),
        "sweep_deg": float(sweep_deg),
        "exit_on_arc": True,
        "arc_length_nm": round(arc_len, 3),
        "exit_track_deg": round(exit_track, 1),
        "chord_nm": round(chord, 3),
        "valid": bool(sweep_deg > 0.0),
    }


# ---------------------------------------------------------------------------
# DME arc leg  (bound leaf: dme-arc-leg)
# ---------------------------------------------------------------------------
def _radial_short_diff_deg(current_deg, target_deg):
    diff = (float(target_deg) - float(current_deg)) % 360.0
    if diff > 180.0:
        diff -= 360.0
    return diff


def dme_arc_length_nm(r_nm, delta_radial_deg):
    if r_nm is None or r_nm <= 0.0:
        raise ValueError("DME radius must be positive")
    return r_nm * math.radians(delta_radial_deg)


def dme_arc_chord_nm(r_nm, delta_radial_deg):
    if r_nm is None or r_nm <= 0.0:
        raise ValueError("DME radius must be positive")
    return 2.0 * r_nm * math.sin(math.radians(delta_radial_deg) / 2.0)


def dme_arc_bank_angle_deg(tas_kt, r_nm):
    """Bank angle (deg) that holds radius r_nm at true airspeed tas."""
    if tas_kt is None or tas_kt <= 0.0:
        raise ValueError("true airspeed must be positive")
    if r_nm is None or r_nm <= 0.0:
        raise ValueError("DME radius must be positive")
    v = tas_kt * KT_TO_MS
    return math.degrees(math.atan(v * v / (G_MS2 * r_nm * NM_TO_M)))


def dme_arc_turn_radius_nm(tas_kt, bank_deg):
    """Turn radius V^2/(g*tan(bank)) in NM."""
    if tas_kt is None or tas_kt <= 0.0:
        raise ValueError("true airspeed must be positive")
    if bank_deg is None or not 0.0 < bank_deg < 90.0:
        raise ValueError("bank angle must lie in (0, 90) degrees")
    v = tas_kt * KT_TO_MS
    return (v * v / (G_MS2 * math.tan(math.radians(bank_deg)))) * M_TO_NM


def dme_arc_geometry(r_nm, radial_start_deg, radial_end_deg):
    """Arc geometry between two radials (shorter signed turn flown)."""
    if r_nm is None or r_nm <= 0.0:
        raise ValueError("DME radius must be positive")
    turn_deg = _radial_short_diff_deg(radial_start_deg, radial_end_deg)
    turn_mag = abs(turn_deg)
    return {
        "radius_nm": float(r_nm),
        "radial_start_deg": float(radial_start_deg) % 360.0,
        "radial_end_deg": float(radial_end_deg) % 360.0,
        "turn_angle_deg": round(turn_deg, 1),
        "arc_length_nm": round(dme_arc_length_nm(r_nm, turn_mag), 3),
        "chord_nm": round(dme_arc_chord_nm(r_nm, turn_mag), 3),
    }


# ---------------------------------------------------------------------------
# Rhumb line geometry  (bound leaf: rhumb-line-leg)
# ---------------------------------------------------------------------------
R_EARTH_RHUMB_M = 6371.0e3   # leaf constant; numerically equals R_EARTH_M


def _isometric_latitude(lat_deg):
    _check_lat(lat_deg)
    return math.log(math.tan(math.pi / 4.0 + math.radians(lat_deg) / 2.0))


def rhumb_distance_m(lat1, lon1, lat2, lon2):
    """Constant-course (rhumb) distance in metres."""
    _check_lat(lat1, "lat1")
    _check_lat(lat2, "lat2")
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    d_psi = _isometric_latitude(lat2) - _isometric_latitude(lat1)
    if abs(d_psi) < 1.0e-12:
        return R_EARTH_RHUMB_M * abs(d_lon) * math.cos(math.radians(lat1))
    return (R_EARTH_RHUMB_M * math.hypot(d_psi, d_lon)
            * abs(d_lat) / abs(d_psi))


def rhumb_course_deg(lat1, lon1, lat2, lon2):
    """Constant Mercator course in [0, 360)."""
    _check_lat(lat1, "lat1")
    _check_lat(lat2, "lat2")
    d_lon = math.radians(lon2 - lon1)
    d_psi = _isometric_latitude(lat2) - _isometric_latitude(lat1)
    return math.degrees(math.atan2(d_lon, d_psi)) % 360.0


def rhumb_vs_great_circle(lat1, lon1, lat2, lon2):
    """{rhumb_m, great_circle_m, delta_m, delta_pct} for one leg."""
    _check_lat(lat1, "lat1")
    _check_lat(lat2, "lat2")
    rhumb = rhumb_distance_m(lat1, lon1, lat2, lon2)
    gc = great_circle_distance_m(lat1, lon1, lat2, lon2)
    delta = rhumb - gc
    pct = 0.0 if gc == 0.0 else delta / gc * 100.0
    return {
        "rhumb_m": round(rhumb, 1),
        "great_circle_m": round(gc, 1),
        "delta_m": round(delta, 1),
        "delta_pct": round(pct, 3),
    }


# ---------------------------------------------------------------------------
# RTA time control  (bound leaf: rta-time-control)
# ---------------------------------------------------------------------------
def isa_speed_of_sound_m_s(altitude_m):
    """ISA speed of sound at altitude_m (troposphere lapse model)."""
    if altitude_m is None or altitude_m < 0.0:
        raise ValueError("altitude_m must be non-negative")
    if altitude_m <= ISA_TROPOPAUSE_M:
        temp_k = ISA_SL_TEMP_K - ISA_LAPSE_K_PER_M * altitude_m
    else:
        temp_k = ISA_SL_TEMP_K - ISA_LAPSE_K_PER_M * ISA_TROPOPAUSE_M
    return math.sqrt(GAMMA_AIR * R_AIR * temp_k)


def rta_eta_s(remaining_distance_m, ground_speed_m_s):
    """Estimated flight time to the waypoint (s) from t_now."""
    if remaining_distance_m is None or remaining_distance_m < 0.0:
        raise ValueError("remaining distance must be non-negative")
    if ground_speed_m_s is None or ground_speed_m_s <= 0.0:
        raise ValueError("ground speed must be positive")
    return remaining_distance_m / ground_speed_m_s


def rta_time_error_s(eta_rel_s, rta_time_s, t_now_s=0.0):
    """(t_now + eta) - rta; positive = late."""
    return (t_now_s + eta_rel_s) - rta_time_s


def rta_required_ground_speed_m_s(remaining_distance_m, rta_time_s,
                                  t_now_s=0.0):
    """Ground speed that lands exactly at RTA time."""
    if rta_time_s <= t_now_s:
        raise ValueError("rta_time_s must be > t_now_s")
    return remaining_distance_m / (rta_time_s - t_now_s)


def rta_tas_from_ground_speed(ground_speed_m_s, wind_along_m_s):
    tas = ground_speed_m_s - wind_along_m_s
    if tas <= 0.0:
        raise ValueError("wind makes true airspeed non-positive")
    return tas


def rta_mach_from_tas(tas_m_s, altitude_m):
    if tas_m_s <= 0.0:
        raise ValueError("tas must be positive")
    return tas_m_s / isa_speed_of_sound_m_s(altitude_m)


def rta_achievable_window(remaining_distance_m, altitude_m, wind_along_m_s,
                          mach_min, mach_max):
    """Earliest/latest arrival window from the cruise Mach envelope."""
    a_sound = isa_speed_of_sound_m_s(altitude_m)
    gs_min = mach_min * a_sound + wind_along_m_s
    gs_max = mach_max * a_sound + wind_along_m_s
    if gs_min <= 0.0:
        raise ValueError("headwind exceeds minimum-cruise true airspeed")
    if remaining_distance_m == 0.0:
        eta_min = eta_max = 0.0
    else:
        eta_min = remaining_distance_m / gs_max
        eta_max = remaining_distance_m / gs_min
    return {
        "gs_min_m_s": round(gs_min, 2),
        "gs_max_m_s": round(gs_max, 2),
        "eta_min_s": round(eta_min, 1),
        "eta_max_s": round(eta_max, 1),
        "window_s": round(eta_max - eta_min, 1),
    }


def rta_speed_command(remaining_distance_m, ground_speed_m_s,
                      wind_along_m_s, rta_time_s, altitude_m,
                      mach_min=0.70, mach_max=0.82, t_now_s=0.0):
    """RTA speed command law for an FMS time constraint at a waypoint.

    Within RTA_TIME_TOL_S of the required time the current speed is
    held; otherwise the required ground speed/Mach is commanded when
    inside [mach_min, mach_max]; outside, the nearest bound is commanded
    and the remaining time error of the best achievable arrival is
    reported with verdict rta-unfeasible.
    """
    if ground_speed_m_s <= 0.0:
        raise ValueError("ground speed must be positive")
    if rta_time_s <= t_now_s:
        raise ValueError("rta_time_s must be > t_now_s")
    eta_rel = rta_eta_s(remaining_distance_m, ground_speed_m_s)
    err = rta_time_error_s(eta_rel, rta_time_s, t_now_s)
    window = rta_achievable_window(remaining_distance_m, altitude_m,
                                   wind_along_m_s, mach_min, mach_max)
    a_sound = isa_speed_of_sound_m_s(altitude_m)
    if abs(err) <= RTA_TIME_TOL_S:
        command_mach = rta_mach_from_tas(
            rta_tas_from_ground_speed(ground_speed_m_s, wind_along_m_s),
            altitude_m)
        required_gs = ground_speed_m_s
        required_mach = None
        feasible = True
        verdict = "rta-feasible"
        predicted_eta = t_now_s + eta_rel
        remaining_error = err
    else:
        required_gs = rta_required_ground_speed_m_s(remaining_distance_m,
                                                    rta_time_s, t_now_s)
        required_mach = rta_mach_from_tas(
            rta_tas_from_ground_speed(required_gs, wind_along_m_s),
            altitude_m)
        if mach_min <= required_mach <= mach_max:
            command_mach = required_mach
            feasible = True
            verdict = "rta-feasible"
            predicted_eta = rta_time_s
            remaining_error = 0.0
        else:
            command_mach = mach_max if required_mach > mach_max else mach_min
            feasible = False
            verdict = "rta-unfeasible"
            best_gs = command_mach * a_sound + wind_along_m_s
            predicted_eta = t_now_s + remaining_distance_m / best_gs
            remaining_error = predicted_eta - rta_time_s
    return {
        "remaining_distance_m": round(remaining_distance_m, 1),
        "current_gs_m_s": round(ground_speed_m_s, 2),
        "wind_along_m_s": round(wind_along_m_s, 2),
        "current_eta_s": round(eta_rel, 1),
        "time_error_s": round(err, 1),
        "required_gs_m_s": round(required_gs, 2),
        "required_mach": round(required_mach, 4) if required_mach else None,
        "command_mach": round(command_mach, 4),
        "feasible": bool(feasible),
        "verdict": verdict,
        "window": window,
        "predicted_eta_s": round(predicted_eta, 1),
        "remaining_error_s": round(remaining_error, 1),
        "altitude_m": float(altitude_m),
        "mach_envelope": [mach_min, mach_max],
    }


# ---------------------------------------------------------------------------
# VNAV vertical profile  (bound leaves: vertical-navigation,
#                        performance-computation, flight-planning)
# ---------------------------------------------------------------------------
def vnav_tod_distance_nm(cruise_alt_ft, target_alt_ft, gradient_ft_nm):
    """Top of descent distance (NM): (cruise - target) / gradient."""
    if gradient_ft_nm is None or gradient_ft_nm <= 0.0:
        raise ValueError("gradient must be positive")
    if cruise_alt_ft <= target_alt_ft:
        raise ValueError("cruise altitude must exceed target altitude")
    return (cruise_alt_ft - target_alt_ft) / gradient_ft_nm


def vnav_descent_gradient_ft_nm(cruise_alt_ft, target_alt_ft, distance_nm):
    """Gradient implied by altitudes over a distance, ft/NM."""
    if distance_nm is None or distance_nm <= 0.0:
        raise ValueError("distance must be positive")
    if cruise_alt_ft <= target_alt_ft:
        raise ValueError("cruise altitude must exceed target altitude")
    return (cruise_alt_ft - target_alt_ft) / distance_nm


def vnav_fpa_deg(gradient_ft_nm):
    """Flight path angle: atan(gradient / ft-per-NM), degrees."""
    if gradient_ft_nm is None or gradient_ft_nm <= 0.0:
        raise ValueError("gradient must be positive")
    return math.degrees(math.atan(gradient_ft_nm / NM_TO_FT))


def vnav_altitude_at_ft(alt_start_ft, gradient_ft_nm, distance_nm):
    """Altitude after descending distance_nm along the gradient (ft)."""
    alt = alt_start_ft - gradient_ft_nm * distance_nm
    return alt


def vnav_constraint_ok(alt_at_constraint_ft, constraint_ft, at_or_above,
                       tol_ft=20.0):
    """Constraint verdict: AT (within tol_ft) or AT OR ABOVE."""
    if at_or_above:
        return alt_at_constraint_ft >= constraint_ft
    return abs(alt_at_constraint_ft - constraint_ft) <= tol_ft


def fpa_gradient_ft_nm(fpa_deg):
    """Gradient of a flight path angle: tan(fpa) * ft-per-NM."""
    return math.tan(math.radians(fpa_deg)) * NM_TO_FT


def vertical_band_ok(alt_ft, floor_ft, ceiling_ft):
    """Crossing band check (bound flight-planning leaf, feet units):
    True when floor <= alt <= ceiling; None = open."""
    if floor_ft is not None and ceiling_ft is not None \
            and floor_ft > ceiling_ft:
        raise ValueError("floor above ceiling")
    if floor_ft is not None and alt_ft < floor_ft:
        return False
    if ceiling_ft is not None and alt_ft > ceiling_ft:
        return False
    return True


# ---------------------------------------------------------------------------
# Performance (ECON cruise)  (bound leaf: performance-computation)
# ---------------------------------------------------------------------------
# Simplified documented three-term drag model of a mid-size transport.
# Coefficients are the leaf's order-of-magnitude defaults; they MUST be
# calibrated per aircraft against the FMS performance manual.
PERF_WING_AREA_M2 = 122.0
PERF_CD0 = 0.0210
PERF_OSWALD_E = 0.82
PERF_ASPECT_RATIO = 9.4
PERF_SFC_KG_N_S = 0.0000165
PERF_COMPRESSIBILITY = 2.4e-16
PERF_M_MIN = 0.70
PERF_M_MMO = 0.82
PERF_FT_TO_M = 0.3048
PERF_MS_TO_KTS = 1.943844492
PERF_KTS_TO_MS = 0.5144444444


def perf_isa_temperature_k(altitude_ft):
    h = altitude_ft * PERF_FT_TO_M
    if h <= ISA_TROPOPAUSE_M:
        return ISA_SL_TEMP_K - ISA_LAPSE_K_PER_M * h
    return ISA_SL_TEMP_K - ISA_LAPSE_K_PER_M * ISA_TROPOPAUSE_M


def perf_speed_of_sound_kts(altitude_ft):
    return math.sqrt(GAMMA_AIR * R_AIR * perf_isa_temperature_k(altitude_ft)) \
        * PERF_MS_TO_KTS


def perf_tas_from_mach(mach, altitude_ft):
    if mach <= 0.0:
        raise ValueError("mach must be positive")
    return mach * perf_speed_of_sound_kts(altitude_ft)


def perf_cost_index(time_cost_per_hour, fuel_cost_per_kg):
    if time_cost_per_hour < 0.0:
        raise ValueError("time cost must be non-negative")
    if fuel_cost_per_kg <= 0.0:
        raise ValueError("fuel cost must be positive")
    return time_cost_per_hour / fuel_cost_per_kg


def perf_isa_density_kgm3(altitude_ft):
    """ISA density in kg/m^3 (mirrors the performance-computation leaf)."""
    h = altitude_ft * PERF_FT_TO_M
    if h <= ISA_TROPOPAUSE_M:
        t = ISA_SL_TEMP_K - ISA_LAPSE_K_PER_M * h
        p = 101325.0 * (t / ISA_SL_TEMP_K) ** (-G_MS2 / (R_AIR * -ISA_LAPSE_K_PER_M))
    else:
        t_tropo = ISA_SL_TEMP_K - ISA_LAPSE_K_PER_M * ISA_TROPOPAUSE_M
        p_tropo = 101325.0 * (t_tropo / ISA_SL_TEMP_K) ** (
            -G_MS2 / (R_AIR * -ISA_LAPSE_K_PER_M))
        p = p_tropo * math.exp(-G_MS2 * (h - ISA_TROPOPAUSE_M)
                               / (R_AIR * t_tropo))
        t = t_tropo
    return p / (R_AIR * t)


def _perf_fuel_coeffs(weight_kg, altitude_ft):
    rho = perf_isa_density_kgm3(altitude_ft)
    w_n = weight_kg * G_MS2
    c1 = 0.5 * rho * PERF_WING_AREA_M2 * PERF_CD0
    c2 = (2.0 * w_n * w_n
          / (rho * PERF_WING_AREA_M2 * math.pi * PERF_OSWALD_E
             * PERF_ASPECT_RATIO))
    return c1, c2, PERF_COMPRESSIBILITY


def perf_fuel_per_nm(weight_kg, altitude_ft, tas_kts):
    """Cruise fuel burn, kg per nautical mile."""
    if weight_kg <= 0.0:
        raise ValueError("weight must be positive")
    if tas_kts <= 0.0:
        raise ValueError("tas must be positive")
    c1, c2, c3 = _perf_fuel_coeffs(weight_kg, altitude_ft)
    v = tas_kts * PERF_KTS_TO_MS
    return PERF_SFC_KG_N_S * NM_TO_M * (c1 * v + c2 / v ** 3 + c3 * v ** 7)


def perf_max_range_speed_kts(weight_kg, altitude_ft):
    """TAS (kts) minimizing fuel per NM (Newton root of dF/dV = 0)."""
    c1, c2, _c3 = _perf_fuel_coeffs(weight_kg, altitude_ft)

    def g(v):
        return c1 - 3.0 * c2 / v ** 4 + 7.0 * _c3 * v ** 6

    def gp(v):
        return 12.0 * c2 / v ** 5 + 42.0 * _c3 * v ** 5

    v = (3.0 * c2 / c1) ** 0.25
    for _ in range(60):
        f = g(v)
        df = gp(v)
        if df == 0.0:
            break
        step = f / df
        v -= step
        if v <= 1.0:
            v = 1.0
        if abs(step) < 1e-9:
            break
    return v * PERF_MS_TO_KTS


def perf_econ_mach_from_cost_index(ci_kg_per_h, weight_kg, altitude_ft):
    """ECON cruise Mach clamped into [M_MIN, M_MMO]."""
    if ci_kg_per_h is None or ci_kg_per_h < 0.0:
        raise ValueError("cost index must be non-negative")
    if weight_kg <= 0.0:
        raise ValueError("weight must be positive")
    c1, c2, c3 = _perf_fuel_coeffs(weight_kg, altitude_ft)
    a = PERF_SFC_KG_N_S * NM_TO_M
    time_scale = NM_TO_M / 3600.0

    def g(v):
        return (a * (c1 - 3.0 * c2 / v ** 4 + 7.0 * c3 * v ** 6)
                - ci_kg_per_h * time_scale / v ** 2)

    def gp(v):
        return (a * (12.0 * c2 / v ** 5 + 42.0 * c3 * v ** 5)
                + 2.0 * ci_kg_per_h * time_scale / v ** 3)

    v = perf_max_range_speed_kts(weight_kg, altitude_ft) * PERF_KTS_TO_MS
    for _ in range(60):
        f = g(v)
        df = gp(v)
        if df == 0.0:
            break
        step = f / df
        v -= step
        if v <= 1.0:
            v = 1.0
        if abs(step) < 1e-9:
            break
    mach = v / math.sqrt(GAMMA_AIR * R_AIR * perf_isa_temperature_k(altitude_ft))
    return min(PERF_M_MMO, max(PERF_M_MIN, mach))


def perf_econ_summary(ci_kg_per_h, weight_kg, altitude_ft):
    """ECON selection detail: Mach, TAS, fuel per NM, time per NM."""
    mach = perf_econ_mach_from_cost_index(ci_kg_per_h, weight_kg, altitude_ft)
    tas = perf_tas_from_mach(mach, altitude_ft)
    return {
        "cost_index_kg_per_h": float(ci_kg_per_h),
        "weight_kg": int(weight_kg),
        "altitude_ft": int(altitude_ft),
        "mach": round(mach, 4),
        "tas_kts": round(tas, 1),
        "fuel_per_nm_kg": round(perf_fuel_per_nm(weight_kg, altitude_ft, tas), 3),
        "time_per_nm_h": round(1.0 / tas, 6),
        "m_min": PERF_M_MIN,
        "m_mmo": PERF_M_MMO,
    }


def perf_max_range_summary(weight_kg, altitude_ft):
    """Max-range (minimum fuel per NM) reference, CI = 0."""
    tas = perf_max_range_speed_kts(weight_kg, altitude_ft)
    a_kts = perf_speed_of_sound_kts(altitude_ft)
    return {
        "mach": round(tas / a_kts, 4),
        "tas_kts": round(tas, 1),
        "fuel_per_nm_kg": round(perf_fuel_per_nm(weight_kg, altitude_ft, tas), 3),
    }


# ---------------------------------------------------------------------------
# Radio navaid geometry  (bound leaf: radio-navigation-aids)
# ---------------------------------------------------------------------------
def nav_bearing_deg(x_ac, y_ac):
    """Bearing from station to aircraft, degrees clockwise from north."""
    return math.degrees(math.atan2(x_ac, y_ac)) % 360.0


def nav_radial_deg(bearing_deg_input):
    """VOR radial FROM the station (reciprocal of bearing)."""
    return (float(bearing_deg_input) + 180.0) % 360.0


def nav_dme_slant_range_m(x_ac, y_ac, altitude_m):
    """DME slant range: sqrt(x^2 + y^2 + h^2), metres."""
    if altitude_m is None or altitude_m < 0.0:
        raise ValueError("altitude must be non-negative")
    return math.sqrt(x_ac * x_ac + y_ac * y_ac + altitude_m * altitude_m)


# ---------------------------------------------------------------------------
# Route model + report builder
# ---------------------------------------------------------------------------
@dataclass
class Route:
    """Project facts for a flight plan + RNAV/RNP route assessment."""
    route_id: str = "AERO ROUTE R1 (illustrative - not a filed plan)"
    aircraft: str = "Mid-size transport (illustrative example)"
    wpt_a: tuple = (41.0000, -75.0000)      # W001
    wpt_b: tuple = (40.0000, -74.5000)      # W002 (RF entry fix)
    wpt_e: tuple = (38.0000, -75.0000)      # W005 (RTA / constraint fix)
    leg1_ident: str = "W001"
    leg2_ident: str = "W002"
    hold_ident: str = "HOLDF"
    rta_ident: str = "W005"
    # RF leg (W002 -> W003)
    rf_radius_nm: float = 12.0
    rf_turn: str = "RIGHT"
    rf_sweep_deg: float = 90.0
    # RNP segment
    rnp_nm: float = 0.3
    sigma_lateral_m: float = 200.0          # 1-sigma lateral position error
    rnp_margin_fraction: float = 0.10
    rnp_segment: str = "W002 - HOLDF - W005 (en-route/arrival RNAV portion)"
    # Hold at W004/HOLDF
    hold_inbound_course_deg: float = 260.0
    hold_turn: str = "right"
    hold_altitude_ft: float = 20000.0
    hold_outbound_heading_deg: float = 80.0
    hold_wind_from_deg: float = 40.0
    hold_wind_speed_kt: float = 30.0
    hold_tas_kt: float = 260.0
    # RTA at W005 (evaluated from the hold exit at W004)
    rta_altitude_ft: float = 20000.0
    rta_current_gs_m_s: float = 240.0
    rta_wind_along_m_s: float = -5.0
    rta_demand_delay_s: float = 25.0        # slot: arrive 25 s later than nom.
    rta_mach_min: float = 0.70
    rta_mach_max: float = 0.82
    # VNAV profile
    vnav_cruise_ft: float = 35000.0
    vnav_path_fpa_deg: float = 3.0
    vnav_tas_kt: float = 450.0
    vnav_headwind_kt: float = 15.0
    # Perf (ECON)
    perf_cost_index: float = 30.0
    perf_weight_kg: float = 62000.0
    perf_altitude_ft: float = 35000.0
    # DME arc procedure check
    dme_radius_nm: float = 15.0
    dme_radial_start_deg: float = 30.0
    dme_radial_end_deg: float = 90.0
    dme_tas_kt: float = 250.0
    dme_fl_ft: float = 20000.0
    extra_notes: str = ""


def _leg_dist_nm(m):
    return m * M_TO_NM


def build_report(route: Route) -> dict:
    """Compute the complete route assessment content model.

    Leg 1: great-circle TF leg W001-W002 (track + distance).
    Leg 2: RF leg W002-W003 constructed from the published radius / turn
           / swept angle; W003 is the computed exit fix.
    Leg 3: TF meridian leg W003-W004 (hold fix), track exactly 180.
    Leg 4: TF leg W004-W005 (RTA fix).
    """
    lat_a, lon_a = route.wpt_a
    lat_b, lon_b = route.wpt_b
    # --- Leg 1 geometry
    l1_track = great_circle_track_deg(lat_a, lon_a, lat_b, lon_b)
    l1_dist_m = great_circle_distance_m(lat_a, lon_a, lat_b, lon_b)
    l1_rhumb = rhumb_vs_great_circle(lat_a, lon_a, lat_b, lon_b)
    # --- Leg 2: RF construction; inbound track = arrival track at W002
    ef = (0.0, 0.0)  # W002 as origin of the RF local frame
    rf = rf_leg_geometry(ef, l1_track, route.rf_radius_nm, route.rf_turn,
                         route.rf_sweep_deg)
    xf = rf["xf"]
    lat_c, lon_c = _offset_waypoint(lat_b, lon_b, xf[0], xf[1])
    # --- Leg 3: W003 -> W004, W004 placed 1.0 deg south of W003 (meridian)
    lat_d = lat_c - 1.0
    lon_d = lon_c
    l3_track = great_circle_track_deg(lat_c, lon_c, lat_d, lon_d)
    l3_dist_m = great_circle_distance_m(lat_c, lon_c, lat_d, lon_d)
    # --- Leg 4: W004 -> W005
    lat_e, lon_e = route.wpt_e
    l4_track = great_circle_track_deg(lat_d, lon_d, lat_e, lon_e)
    l4_dist_m = great_circle_distance_m(lat_d, lon_d, lat_e, lon_e)

    waypoints = [
        {"ident": route.leg1_ident, "lat": lat_a, "lon": lon_a,
         "derived": False, "note": "route origin / start of RNP segment"},
        {"ident": route.leg2_ident, "lat": lat_b, "lon": lon_b,
         "derived": False, "note": "RF leg entry fix"},
        {"ident": "W003", "lat": round(lat_c, 4), "lon": round(lon_c, 4),
         "derived": True, "note": "RF leg exit fix (computed)"},
        {"ident": route.hold_ident, "lat": round(lat_d, 4),
         "lon": round(lon_d, 4), "derived": True,
         "note": "holding fix (computed from W003)"},
        {"ident": route.rta_ident, "lat": lat_e, "lon": lon_e,
         "derived": False, "note": "RTA fix / VNAV crossing constraint"},
    ]
    legs = [
        {"leg": 1, "type": "TF (great-circle)", "from": route.leg1_ident,
         "to": route.leg2_ident, "track_deg": round(l1_track, 1),
         "distance_nm": round(_leg_dist_nm(l1_dist_m), 2)},
        {"leg": 2, "type": "RF (radius-to-fix)", "from": route.leg2_ident,
         "to": "W003", "track_deg": round(rf["exit_track_deg"], 1),
         "distance_nm": round(rf["arc_length_nm"], 2),
         "rf": rf},
        {"leg": 3, "type": "TF (great-circle)", "from": "W003",
         "to": route.hold_ident, "track_deg": round(l3_track, 1),
         "distance_nm": round(_leg_dist_nm(l3_dist_m), 2)},
        {"leg": 4, "type": "TF (great-circle)", "from": route.hold_ident,
         "to": route.rta_ident, "track_deg": round(l4_track, 1),
         "distance_nm": round(_leg_dist_nm(l4_dist_m), 2)},
    ]
    total_nm = sum(leg["distance_nm"] for leg in legs)

    # RNP containment on the RNP 0.3 segment
    rnp_m = rnp_nm_to_m(route.rnp_nm)
    containment = containment_analysis(
        sigma_lateral_m=route.sigma_lateral_m, rnp_m=rnp_m,
        margin_fraction=route.rnp_margin_fraction)

    # Holding at W004/HOLDF: arrival track = leg 3 track (meridian, 180)
    hold = hold_entry_analysis(
        arrival_track_deg=l3_track,
        hold_inbound_course_deg=route.hold_inbound_course_deg,
        turn_direction=route.hold_turn,
        altitude_ft=route.hold_altitude_ft,
        outbound_heading_deg=route.hold_outbound_heading_deg,
        wind_from_deg=route.hold_wind_from_deg,
        wind_speed_kt=route.hold_wind_speed_kt,
        tas_kt=route.hold_tas_kt)

    # RTA at W005 from the hold exit (W004)
    alt_rta_m = route.rta_altitude_ft * FT_TO_M
    eta_nom = rta_eta_s(l4_dist_m, route.rta_current_gs_m_s)
    rta_time_s = route.rta_demand_delay_s + eta_nom  # t_now = 0
    rta = rta_speed_command(
        remaining_distance_m=l4_dist_m,
        ground_speed_m_s=route.rta_current_gs_m_s,
        wind_along_m_s=route.rta_wind_along_m_s,
        rta_time_s=rta_time_s,
        altitude_m=alt_rta_m,
        mach_min=route.rta_mach_min, mach_max=route.rta_mach_max,
        t_now_s=0.0)

    # VNAV: 3.0 deg path FL350 -> FL200 crossing W004, then W004 -> W005
    path_gradient = fpa_gradient_ft_nm(route.vnav_path_fpa_deg)
    tod_air_nm = vnav_tod_distance_nm(route.vnav_cruise_ft, 20000.0,
                                      path_gradient)
    ground_factor = (route.vnav_tas_kt
                     / (route.vnav_tas_kt - route.vnav_headwind_kt))
    tod_ground_nm = tod_air_nm * ground_factor
    l3_nm = _leg_dist_nm(l3_dist_m)
    tod_in_leg3 = max(0.0, l3_nm - tod_ground_nm)
    # crossing at W005 continuing the same 3.0 deg path from FL200
    l4_nm = _leg_dist_nm(l4_dist_m)
    alt_at_w005_ft = vnav_altitude_at_ft(20000.0, path_gradient, l4_nm)
    w005_constraint_ft = 6000.0
    w005_ok = vnav_constraint_ok(alt_at_w005_ft, w005_constraint_ft,
                                 at_or_above=False, tol_ft=20.0)
    w005_at_or_above = vnav_constraint_ok(alt_at_w005_ft,
                                          w005_constraint_ft,
                                          at_or_above=True)
    required_gradient = vnav_descent_gradient_ft_nm(20000.0,
                                                    w005_constraint_ft, l4_nm)
    required_fpa = vnav_fpa_deg(required_gradient)
    # vertical band checks (flight-planning constraint model, feet)
    band_cruise = vertical_band_ok(route.vnav_cruise_ft, 33000.0, 39000.0)
    band_w004 = vertical_band_ok(20000.0, 19500.0, 20500.0)
    vnav = {
        "cruise_ft": int(route.vnav_cruise_ft),
        "hold_crossing_ft": 20000,
        "fpa_deg": route.vnav_path_fpa_deg,
        "path_gradient_ft_nm": round(path_gradient, 1),
        "tas_kt": route.vnav_tas_kt,
        "headwind_kt": route.vnav_headwind_kt,
        "tod_air_nm": round(tod_air_nm, 1),
        "tod_ground_nm": round(tod_ground_nm, 1),
        "leg3_nm": round(l3_nm, 2),
        "tod_in_leg3_nm": round(tod_in_leg3, 1),
        "leg4_nm": round(l4_nm, 2),
        "alt_at_w005_ft_3deg": round(alt_at_w005_ft, 0),
        "w005_constraint_ft": w005_constraint_ft,
        "w005_crossing_ok": bool(w005_ok),
        "w005_at_or_above_ok": bool(w005_at_or_above),
        "required_gradient_ft_nm": round(required_gradient, 1),
        "required_fpa_deg": round(required_fpa, 2),
        "band_cruise_ok": bool(band_cruise),
        "band_w004_ok": bool(band_w004),
    }

    # Performance (ECON cruise at FL350)
    econ = perf_econ_summary(route.perf_cost_index, route.perf_weight_kg,
                             route.perf_altitude_ft)
    maxrange = perf_max_range_summary(route.perf_weight_kg,
                                      route.perf_altitude_ft)

    # DME arc procedure check + radio navaid geometry
    dme = dme_arc_geometry(route.dme_radius_nm, route.dme_radial_start_deg,
                           route.dme_radial_end_deg)
    dme_bank = dme_arc_bank_angle_deg(route.dme_tas_kt, route.dme_radius_nm)
    dme_turn_r = dme_arc_turn_radius_nm(route.dme_tas_kt, 25.0)
    arc_alt_m = route.dme_fl_ft * FT_TO_M
    ground_m = route.dme_radius_nm * NM_TO_M
    slant_m = nav_dme_slant_range_m(ground_m, 0.0, arc_alt_m)
    pt_start = (route.dme_radius_nm * math.sin(math.radians(30.0)),
                route.dme_radius_nm * math.cos(math.radians(30.0)))
    bearing_start = nav_bearing_deg(pt_start[0], pt_start[1])
    nav = {
        "dme": dme,
        "dme_bank_angle_deg": round(dme_bank, 2),
        "dme_turn_radius_nm_25deg": round(dme_turn_r, 2),
        "slant_range_ground_m": round(ground_m, 0),
        "slant_range_m": round(slant_m, 0),
        "start_point_bearing_deg": round(bearing_start, 1),
        "start_point_radial_deg": round(nav_radial_deg(bearing_start), 1),
        "arc_altitude_ft": int(route.dme_fl_ft),
        "dme_tas_kt": float(route.dme_tas_kt),
    }

    # Rhumb-line leg comparison for leg 1
    rhumb_l1 = {
        "rhumb_nm": round(l1_rhumb["rhumb_m"] * M_TO_NM, 3),
        "gc_nm": round(l1_rhumb["great_circle_m"] * M_TO_NM, 3),
        "delta_m": l1_rhumb["delta_m"],
        "delta_pct": l1_rhumb["delta_pct"],
        "rhumb_course_deg": round(rhumb_course_deg(lat_a, lon_a, lat_b, lon_b), 1),
    }

    findings = []
    if not vnav["w005_crossing_ok"]:
        findings.append({
            "id": "F1",
            "severity": "finding",
            "title": "W005 crossing constraint not met on the planned 3.0 deg path",
            "detail": ("Continuing the 3.0 deg descent path from the FL200 "
                       "hold crossing reaches %s at %.0f ft, below the AT "
                       "%.0f ft constraint by %.0f ft. Replan the arrival "
                       "profile: the descent leg from the hold to %s "
                       "requires a gradient no steeper than %.0f ft/NM "
                       "(%.2f deg)."
                       % (route.rta_ident, alt_at_w005_ft, w005_constraint_ft,
                          6000.0 - alt_at_w005_ft, route.rta_ident,
                          required_gradient, required_fpa)),
        })
    if not containment["pass"]:
        findings.append({
            "id": "F2", "severity": "finding",
            "title": "RNP containment not met",
            "detail": "ANP exceeds the RNP containment bound on the segment.",
        })
    if not rta["feasible"]:
        findings.append({
            "id": "F3", "severity": "finding",
            "title": "RTA demand not achievable inside the Mach envelope",
            "detail": "The commanded bound Mach leaves a residual time error.",
        })
    if not findings:
        findings.append({
            "id": "F1", "severity": "info",
            "title": "No constraint violations found",
            "detail": "All checked route elements comply within the stated assumptions.",
        })

    model = {
        "document_type": "Flight Plan and RNAV/RNP Route Assessment",
        "status": "draft-for-review",
        "route_id": route.route_id,
        "aircraft": route.aircraft,
        "cruise_fl": int(route.vnav_cruise_ft),
        "waypoints": waypoints,
        "legs": legs,
        "total_distance_nm": round(total_nm, 2),
        "leg1_rhumb_comparison": rhumb_l1,
        "rnp": {
            "rnp_nm": route.rnp_nm,
            "rnp_m": round(rnp_m, 1),
            "segment": route.rnp_segment,
            "sigma_lateral_m": route.sigma_lateral_m,
            "containment": containment,
        },
        "hold": hold,
        "hold_fix": route.hold_ident,
        "rta_fix": route.rta_ident,
        "rta": rta,
        "rta_demand": {
            "evaluated_from": route.hold_ident,
            "to": route.rta_ident,
            "slot_delay_s": route.rta_demand_delay_s,
        },
        "vnav": vnav,
        "performance": {"econ": econ, "max_range_reference": maxrange},
        "navaid": nav,
        "findings": findings,
        "n_findings": len([f for f in findings if f["severity"] == "finding"]),
        "generated": date.today().isoformat(),
    }
    return model


# ---------------------------------------------------------------------------
# Render the deliverable markdown
# ---------------------------------------------------------------------------
def _fmt_nm(value):
    return "%.2f" % value


def render_report_markdown(model: dict) -> str:
    """Render the assessment model as the deliverable markdown document."""
    m = model
    rnp = m["rnp"]["containment"]
    hold = m["hold"]
    rta = m["rta"]
    vnav = m["vnav"]
    econ = m["performance"]["econ"]
    mr = m["performance"]["max_range_reference"]
    nav = m["navaid"]
    rh1 = m["leg1_rhumb_comparison"]

    lines = [
        "# Flight Plan and RNAV/RNP Route Assessment",
        "",
        "**Route:** %s" % m["route_id"],
        "**Aircraft:** %s" % m["aircraft"],
        "**Cruise level:** FL%d (illustrative profile)" % (m["cruise_fl"] // 100),
        "**Status:** %s" % m["status"],
        "",
        "## 1. Route structure and track distance",
        "",
        "The assessed route contains %d waypoints and %d legs. Waypoints are "
        "illustrative identifiers with coordinates; the route is a synthetic "
        "example for the role deliverable, not a published navigation "
        "database procedure." % (len(m["waypoints"]), len(m["legs"])),
        "",
        "| Waypoint | Latitude | Longitude | Role |",
        "|---|---|---|---|",
    ]
    for wp in m["waypoints"]:
        role = ("derived: " if wp["derived"] else "") + wp["note"]
        lines.append("| %s | %.4f N | %.4f W | %s |"
                     % (wp["ident"], abs(wp["lat"]), abs(wp["lon"]), role))
    lines += [
        "",
        "| Leg | Type | From | To | Track (deg)* | Distance (NM) |",
        "|---|---|---|---|---|---|",
        "*TF legs: initial great-circle track. RF leg: exit track after the "
        "turn (the value shown is the flight tangent at the exit fix).*",
        "",
    ]
    for leg in m["legs"]:
        lines.append("| %d | %s | %s | %s | %.1f deg | %s |"
                     % (leg["leg"], leg["type"], leg["from"], leg["to"],
                        leg["track_deg"], _fmt_nm(leg["distance_nm"])))
    lines += [
        "",
        "Total track distance: **%s NM**." % _fmt_nm(m["total_distance_nm"]),
        "",
        "Leg 1 track-distance method check (rhumb line vs great circle): "
        "rhumb %.3f NM, great-circle %.3f NM, difference %.1f m "
        "(%.3f %%), rhumb course %.1f deg. Great-circle tracks are used "
        "for the TF legs." % (rh1["rhumb_nm"], rh1["gc_nm"], rh1["delta_m"],
                              rh1["delta_pct"], rh1["rhumb_course_deg"]),
        "",
        "## 2. Radius-to-fix (RF) leg construction (leg 2)",
        "",
        "The RF leg from W002 turns %s at radius %s NM with the published "
        "swept angle %s deg. Entry fix is the origin of the leg local "
        "tangent frame (x = east, y = north, NM)." % (
            m["legs"][1]["rf"]["turn"], m["legs"][1]["rf"]["radius_nm"],
            m["legs"][1]["rf"]["sweep_deg"]),
        "",
        "- Turn centre (local NM): %s" % (m["legs"][1]["rf"]["center_nm"],),
        "- Exit fix (local NM): %s  (on radius circle: %s)" % (
            m["legs"][1]["rf"]["xf"], m["legs"][1]["rf"]["exit_on_arc"]),
        "- Swept angle: %s deg; arc length: %s NM" % (
            m["legs"][1]["rf"]["sweep_deg"], _fmt_nm(m["legs"][1]["rf"]["arc_length_nm"])),
        "- Exit track: %s deg; chord: %s NM" % (
            m["legs"][1]["rf"]["exit_track_deg"], _fmt_nm(m["legs"][1]["rf"]["chord_nm"])),
        "- RF leg valid: %s" % m["legs"][1]["rf"]["valid"],
        "",
        "## 3. RNP containment on the RNP segment",
        "",
        "Segment: %s" % m["rnp"]["segment"],
        "- Required navigation performance (RNP): %.1f NM = %.1f m" % (
            m["rnp"]["rnp_nm"], m["rnp"]["rnp_m"]),
        "- Lateral 1-sigma position error input: %.0f m" % m["rnp"]["sigma_lateral_m"],
        "- Actual navigation performance (ANP), 95%% containment "
        "(2 x sigma): %.1f m (%.4f NM)" % (rnp["anp_m"], rnp["anp_nm"]),
        "- Required margin (%.0f %% of RNP): %.1f m" % (
            m["rnp"]["containment"]["required_margin_m"]
            / m["rnp"]["rnp_m"] * 100.0,
            rnp["required_margin_m"]),
        "- Containment check (ANP + margin <= RNP): **%s** - margin "
        "available %.1f m" % (rnp["verdict"], rnp["margin_available_m"]),
        "",
        "## 4. Holding pattern entry at %s" % m["hold_fix"],
        "",
        "Approach track at the holding fix: %.1f deg (leg 3, due-south "
        "meridian). Hold inbound course %.1f deg, %s turns. Approach angle "
        "alpha to the holding axis: %.1f deg (sector rule: direct <= %.0f "
        "deg, teardrop %.0f < alpha <= %.0f deg, parallel > %.0f deg)."
        % (hold["arrival_track_deg"], hold["hold_inbound_course_deg"],
           hold["turn_direction"], hold["alpha_deg"],
           hold["direct_sector_deg"], hold["direct_sector_deg"],
           hold["teardrop_sector_deg"], hold["teardrop_sector_deg"]),
        "",
        "- Entry type: **%s**" % hold["entry"],
        "- Outbound leg timing at FL%d (%.0f ft): %.0f s"
          % (hold["hold_altitude_ft"] // 100, hold["hold_altitude_ft"],
             hold["outbound_leg_s"]),
        "- Outbound heading %s deg, wind %s deg/%.0f kt, TAS %.0f kt: "
        "1-in-60 corrected heading **%s deg**" % (
            hold["outbound_heading_deg"], hold["wind_from_deg"],
            hold["wind_speed_kt"], hold["tas_kt"],
            hold["wind_corrected_heading_deg"]),
        "- First (entry) lap estimate: %.0f s" % hold["entry_lap_s"],
        "",
        "## 5. RTA time control at %s" % m["rta_fix"],
        "",
        "RTA evaluated from the %s exit, %.1f NM before %s, slot demand "
        "%.0f s later than the nominal arrival." % (
            m["hold_fix"], vnav["leg4_nm"], m["rta_fix"],
            m["rta_demand"]["slot_delay_s"]),
        "- Current ground speed: %.1f m/s; nominal ETA: %.1f s; RTA time "
        "error: %+.1f s" % (rta["current_gs_m_s"], rta["current_eta_s"],
                            rta["time_error_s"]),
        "- Required ground speed: %.1f m/s; required Mach: %s" % (
            rta["required_gs_m_s"],
            ("%.4f" % rta["required_mach"]) if rta["required_mach"] else "n/a"),
        "- Commanded Mach: **%.4f**; verdict: **%s** (feasible: %s)" % (
            rta["command_mach"], rta["verdict"], rta["feasible"]),
        "- Achievable window at %.0f ft: [%.0f s, %.0f s] (%.0f s wide)" % (
            rta["altitude_m"] / FT_TO_M, rta["window"]["eta_min_s"],
            rta["window"]["eta_max_s"], rta["window"]["window_s"]),
        "",
        "## 6. Performance and vertical (VNAV) profile",
        "",
        "ECON cruise at FL%d, cost index %.0f kg/h, weight %.0f kg:" % (
            econ["altitude_ft"] // 100, econ["cost_index_kg_per_h"],
            econ["weight_kg"]),
        "- ECON Mach: **%.4f** (TAS %.1f kt, fuel %.3f kg/NM); envelope "
        "[%.2f, %.2f] Mach; max-range reference (CI 0): Mach %.4f, "
        "fuel %.3f kg/NM" % (econ["mach"], econ["tas_kts"],
                             econ["fuel_per_nm_kg"], econ["m_min"],
                             econ["m_mmo"], mr["mach"], mr["fuel_per_nm_kg"]),
        "",
        "Vertical path: descend FL%d -> FL200 on a %.1f deg flight path "
        "(%.1f ft/NM) to cross %s AT FL200, then continue toward %s "
        "(constraint AT %.0f ft)." % (
            vnav["cruise_ft"] // 100, vnav["fpa_deg"],
            vnav["path_gradient_ft_nm"], m["hold_fix"], m["rta_fix"],
            vnav["w005_constraint_ft"]),
        "- Top of descent (air): %.1f NM before %s; with %.0f kt headwind "
        "at %.0f kt TAS: %.1f NM ground distance, starting %.1f NM inside "
        "leg 3 (%.2f NM) - no path conflict." % (
            vnav["tod_air_nm"], m["hold_fix"], vnav["headwind_kt"],
            vnav["tas_kt"], vnav["tod_ground_nm"], vnav["tod_in_leg3_nm"],
            vnav["leg3_nm"]),
        "- Crossing altitude at %s continuing the %.1f deg path: %.0f ft "
        "vs constraint AT %.0f ft: **%s**" % (
            m["rta_fix"], vnav["fpa_deg"], vnav["alt_at_w005_ft_3deg"],
            vnav["w005_constraint_ft"],
            "PASS" if vnav["w005_crossing_ok"] else "FAIL"),
        "- Gradient required to comply: %.0f ft/NM (%.2f deg)" % (
            vnav["required_gradient_ft_nm"], vnav["required_fpa_deg"]),
        "- Vertical band checks: cruise FL%d within band: %s; %s crossing "
        "FL200 within band: %s" % (
            vnav["cruise_ft"] // 100,
            "PASS" if vnav["band_cruise_ok"] else "FAIL",
            m["hold_fix"], "PASS" if vnav["band_w004_ok"] else "FAIL"),
        "",
        "## 7. DME arc and radio navaid geometry checks",
        "",
        "Published arc transition check: radius %.0f NM from the arc "
        "navaid between radials %.0f and %.0f:" % (
            nav["dme"]["radius_nm"], nav["dme"]["radial_start_deg"],
            nav["dme"]["radial_end_deg"]),
        "- Arc length: %s NM; chord: %s NM; turn angle: %.1f deg" % (
            _fmt_nm(nav["dme"]["arc_length_nm"]),
            _fmt_nm(nav["dme"]["chord_nm"]), nav["dme"]["turn_angle_deg"]),
        "- Bank angle to hold the arc at %.0f kt TAS: %.2f deg; turn "
        "radius at 25 deg bank: %.2f NM" % (
            nav["dme_tas_kt"], nav["dme_bank_angle_deg"],
            nav["dme_turn_radius_nm_25deg"]),
        "- DME slant range at %.0f NM ground range, FL%d: %.0f m "
        "(planar ground range %.0f m); arc start point bearing %.1f deg, "
        "reciprocal radial %.1f deg" % (
            nav["dme"]["radius_nm"], nav["arc_altitude_ft"] // 100,
            nav["slant_range_m"], nav["slant_range_ground_m"],
            nav["start_point_bearing_deg"], nav["start_point_radial_deg"]),
        "",
        "## 8. Findings and recommendations",
        "",
    ]
    for f in m["findings"]:
        lines.append("- **[%s]** %s - %s" % (f["severity"].upper(),
                                             f["title"], f["detail"]))
    lines += [
        "",
        "Recommendation: resolve every [FINDING] before the route is "
        "offered for operational dispatch review. Numerical values in this "
        "assessment are computed by the role core from the stated route "
        "facts and the bound flight-management logic leaves.",
        "",
        "---",
        "*Generated by Aero Agent Roles flight-management-engineer core "
        "(%s). DRAFT for human flight operations / dispatch review. "
        "This document is not a clearance, not a filed flight plan, and "
        "not an approval; the operator and the flight crew retain all "
        "operational decision authority.*" % m["generated"],
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evidence gates
# ---------------------------------------------------------------------------
GATE_CHECKS = {
    "route_stated": "route has >= 2 waypoints and >= 1 leg with computed geometry",
    "rnp_present": "an RNP value > 0 is stated for the assessed segment",
    "containment_checked": "ANP-vs-RNP containment verdict present (PASS/FAIL)",
    "entries_correct": "holding entry classified as direct/teardrop/parallel",
    "sign_off_honest": "document is marked draft-for-review, not an approval",
}


def check_report(model: dict) -> dict:
    """Run the evidence gates against the model. Returns per-gate + all_pass."""
    wps = model.get("waypoints") or []
    legs = model.get("legs") or []
    containment = model.get("rnp", {}).get("containment") or {}
    hold = model.get("hold") or {}
    entry = hold.get("entry", "")
    results = {
        "route_stated": (len(wps) >= 2 and len(legs) >= 1
                         and all(isinstance(leg.get("distance_nm"), (int, float))
                                 and leg["distance_nm"] > 0 for leg in legs)),
        "rnp_present": (isinstance(model.get("rnp", {}).get("rnp_nm"),
                                   (int, float))
                        and model["rnp"]["rnp_nm"] > 0),
        "containment_checked": (isinstance(containment.get("pass"), bool)
                                and containment.get("verdict") in VALID_VERDICTS),
        "entries_correct": entry in VALID_ENTRY_TYPES,
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_report_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable (render markers)."""
    low = md_text.lower()
    checks = {
        "has_title": "flight plan and rnav/rnp route assessment" in low,
        "has_route": "total track distance" in low,
        "has_rnp": "rnp" in low and "anp" in low,
        "has_containment_verdict": "containment" in low and "pass" in low,
        "has_entry": any(e in low for e in VALID_ENTRY_TYPES),
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling: check an assessment doc."""
    return check_report_markdown(md_text)


# ---------------------------------------------------------------------------
# Example route (for tests and worked-example generation)
# ---------------------------------------------------------------------------
def example_item() -> Route:
    return Route()


def example_report_markdown() -> str:
    return render_report_markdown(build_report(example_item()))


if __name__ == "__main__":
    model = build_report(example_item())
    md = render_report_markdown(model)
    print("ROUTE: %s" % model["route_id"])
    print("TOTAL DISTANCE: %.2f NM" % model["total_distance_nm"])
    print("CONTAINMENT: %s (margin available %.1f m)"
          % (model["rnp"]["containment"]["verdict"],
             model["rnp"]["containment"]["margin_available_m"]))
    print("HOLD ENTRY: %s (alpha %.1f deg)"
          % (model["hold"]["entry"], model["hold"]["alpha_deg"]))
    print("RTA: %s, command Mach %.4f"
          % (model["rta"]["verdict"], model["rta"]["command_mach"]))
    print("W005 CROSSING: %s at %.0f ft"
          % ("PASS" if model["vnav"]["w005_crossing_ok"] else "FAIL",
             model["vnav"]["alt_at_w005_ft_3deg"]))
    print("FINDINGS: %d" % model["n_findings"])
    print("GATES: %s" % check_report(model))
    print("RENDERED: %d chars" % len(md))
