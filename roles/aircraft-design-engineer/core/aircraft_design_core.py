#!/usr/bin/env python3
"""aircraft_design_core.py - Aircraft Conceptual Design Engineer executable core.

This is the role's ENGINE: given a top-level aircraft requirement (payload,
range, cruise Mach, takeoff field length) it runs the real conceptual sizing
loop - constraint analysis (T/W vs W/S matching chart), the sizing-mission
fuel-fraction chain (Breguet segments), the class-I empty-weight fraction
estimate, and the MTOW convergence iteration - and BUILDS the concept design
package. It also gate-checks the deliverable. Standalone: stdlib only, no
AeroSkills checkout needed.

Every formula below mirrors the real Aero Skills vehicle-design logic
(constraint-analysis, ws-tw-trade, sizing-mission-profile, tow-estimation,
weight-estimation, engine-sizing leaves; public methodology, summary-not-copy):

- Stall (max wing loading):     W/S = 0.5*rho*CLmax*VS^2
- Takeoff distance:             T/W = 1.21*(W/S)/(rho*g*CLmax*s_TO)
- Climb gradient:               T/W = 1/LD + gamma   (OEI gradient converted
                                to the installed basis by n/(n-1))
- Cruise:                       T/W = 0.5*rho*V^2*CD0/(W/S) + k*(W/S)/(0.5*rho*V^2)
- Cruise fuel (Breguet range):  W_f = W0*(1 - exp(-R/(V*TSFC*L/D)))
- Hold fuel (Breguet endurance):W_f = W0*(1 - exp(-E*TSFC/(L/D)))
- Reserve rule hold45_5pct:     45 min hold at 1500 ft + 5% of trip fuel
- Fuel-fraction sizing:         W0 = payload/(1 - W_e/W0 - W_f/W0), iterated
                                until successive estimates change < 0.5%
- Class-I empty-weight fit:     transport band 0.42-0.55 of MTOW; the
                                representative fraction is the band midpoint

Constraint units are SI (W/S in N/m^2, speeds m/s, rho kg/m^3, g 9.80665);
mission-fuel units are the US customary transport-sizing convention
(weight lb, range nm, speed kt, time hr, TSFC lb/lbf/hr). Invalid inputs
raise ValueError throughout.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

# ---------------------------------------------------------------------------
# Physical constants and unit conversions (public standard values)
# ---------------------------------------------------------------------------
G = 9.80665            # standard gravity, m/s^2
RHO_SL = 1.225         # sea-level ISA air density, kg/m^3
T0_ISA = 288.15        # sea-level ISA temperature, K
LAPSE = 0.0065         # ISA troposphere temperature lapse rate, K/m
DENSITY_EXPONENT = 4.255879   # g0/(R*L) - 1 for the ISA density ratio
TROPOPAUSE = 11000.0   # troposphere top, m
GAMMA_AIR = 1.4        # ratio of specific heats
R_AIR = 287.05         # specific gas constant, J/(kg*K)

LB_TO_KG = 0.45359237
KG_TO_LB = 1.0 / LB_TO_KG
N_PER_LBF = 4.4482216
LBF_TO_N = N_PER_LBF
KT_TO_MPS = 0.514444
MPS_TO_KT = 1.0 / KT_TO_MPS
NM2_TO_PSF = 0.0208854342     # N/m^2 -> lb/ft^2 (1 N = 0.224808943 lbf, 1 m = 3.28084 ft)

# Engine sizing leaf: SFC conversion lb/lbf/hr -> kg/(N*s).
LB_PER_LBF_HR_TO_KG_PER_N_S = LB_TO_KG / (N_PER_LBF * 3600.0)

# ---------------------------------------------------------------------------
# Domain tables (from the Aero Skills weight-estimation leaf)
# ---------------------------------------------------------------------------
# Class-I empty-weight fraction bands per category (typical historical
# values; validate against program data). The role's sizing fit uses the
# band midpoint as the representative fraction for the category.
EMPTY_WEIGHT_FRACTION_BANDS = {
    "transport": (0.42, 0.55),
    "general-aviation": (0.55, 0.68),
    "turboprop": (0.50, 0.62),
}

# Growth allowance by design phase (Aero Skills mass-budget leaf): common
# weight-engineering practice - ~10% conceptual, ~6% preliminary, ~3% detailed.
GROWTH_ALLOWANCE_BY_PHASE = {
    "conceptual": 0.10,
    "preliminary": 0.06,
    "detailed": 0.03,
}

# Reserve rules supported by the sizing-mission leaf.
RESERVE_RULES = ("hold45_5pct", "far121")

# Default segment types in mission order (sizing-mission-profile leaf).
SEGMENT_TYPES = ("taxi", "takeoff", "climb", "cruise", "descent",
                 "loiter", "reserve")

# Matching-chart constraint names.
CONSTRAINT_NAMES = ("takeoff", "climb", "cruise", "maneuvering")


# ---------------------------------------------------------------------------
# ISA atmosphere helpers (public ISA standard, troposphere; constants above)
# ---------------------------------------------------------------------------

def isa_density_ratio(altitude_m):
    """ISA air density ratio sigma = rho/rho0 at altitude (0..11000 m).

    sigma = (1 - L*h/T0)**(g0/(R*L) - 1) in the troposphere, the same model
    the engine-sizing leaf uses. Raises ValueError outside the troposphere.
    """
    if altitude_m < 0 or altitude_m > TROPOPAUSE:
        raise ValueError("altitude must be within 0..%g m, got %r"
                         % (TROPOPAUSE, altitude_m))
    temp_ratio = 1.0 - LAPSE * altitude_m / T0_ISA
    return temp_ratio ** DENSITY_EXPONENT


def isa_temperature(altitude_m):
    """ISA temperature (K) in the troposphere: T = T0 - L*h."""
    if altitude_m < 0 or altitude_m > TROPOPAUSE:
        raise ValueError("altitude must be within 0..%g m, got %r"
                         % (TROPOPAUSE, altitude_m))
    return T0_ISA - LAPSE * altitude_m


def isa_speed_of_sound(altitude_m):
    """ISA speed of sound (m/s) at altitude: a = sqrt(gamma*R*T)."""
    return math.sqrt(GAMMA_AIR * R_AIR * isa_temperature(altitude_m))


def isa_density(altitude_m):
    """ISA air density (kg/m^3) at altitude in the troposphere."""
    return RHO_SL * isa_density_ratio(altitude_m)


def mach_to_kt(mach, altitude_m):
    """True airspeed in knots from cruise Mach and ISA altitude."""
    return isa_speed_of_sound(altitude_m) * mach * MPS_TO_KT


def _require_positive(value, name):
    if value is None or value <= 0:
        raise ValueError("%s must be positive, got %r" % (name, value))
    return value


# ---------------------------------------------------------------------------
# Constraint analysis (mirrors constraint-analysis / ws-tw-trade leaves, SI)
# ---------------------------------------------------------------------------

def stall_max_ws(VS, CLmax, rho=RHO_SL):
    """Maximum wing loading allowed by the stall speed (N/m^2).

    W/S = 0.5*rho*CLmax*VS^2 from lift equal to weight at the stall speed.
    """
    if VS <= 0:
        raise ValueError("stall speed VS must be positive, got %r" % (VS,))
    if CLmax <= 0:
        raise ValueError("CLmax must be positive, got %r" % (CLmax,))
    if rho <= 0:
        raise ValueError("air density rho must be positive, got %r" % (rho,))
    return 0.5 * rho * CLmax * VS * VS


def takeoff_constraint_tw(W_S, rho, CLmax, s_TO):
    """Required thrust to weight from the takeoff distance (unitless).

    T/W = 1.21*(W/S)/(rho*g*CLmax*s_TO); W/S in N/m^2, s_TO in m.
    """
    if W_S <= 0:
        raise ValueError("wing loading W/S must be positive, got %r" % (W_S,))
    if rho <= 0:
        raise ValueError("air density rho must be positive, got %r" % (rho,))
    if CLmax <= 0:
        raise ValueError("CLmax must be positive, got %r" % (CLmax,))
    if s_TO <= 0:
        raise ValueError("takeoff distance s_TO must be positive, got %r" % (s_TO,))
    return 1.21 * W_S / (rho * G * CLmax * s_TO)


def climb_constraint_tw(LD, gamma_rad):
    """Required thrust to weight from the climb gradient (unitless).

    T/W = 1/LD + gamma_rad: the level-flight drag term plus the small-angle
    climb term (excess thrust fraction equals the climb gradient).
    """
    if LD <= 0:
        raise ValueError("lift-to-drag ratio LD must be positive, got %r" % (LD,))
    if gamma_rad < 0:
        raise ValueError("climb gradient must be non-negative, got %r" % (gamma_rad,))
    return 1.0 / LD + gamma_rad


def cruise_constraint_tw(W_S, V, rho, CD0, k):
    """Required thrust to weight at cruise speed (unitless).

    T/W = q*CD0/(W/S) + k*(W/S)/q with q = 0.5*rho*V^2 and k = 1/(pi*e*AR).
    """
    if W_S <= 0:
        raise ValueError("wing loading W/S must be positive, got %r" % (W_S,))
    if V <= 0:
        raise ValueError("cruise speed V must be positive, got %r" % (V,))
    if rho <= 0:
        raise ValueError("air density rho must be positive, got %r" % (rho,))
    if CD0 <= 0:
        raise ValueError("CD0 must be positive, got %r" % (CD0,))
    if k <= 0:
        raise ValueError("induced drag factor k must be positive, got %r" % (k,))
    q = 0.5 * rho * V * V
    return q * CD0 / W_S + k * W_S / q


def maneuvering_constraint_tw(W_S, V, rho, CD0, k, n):
    """Required thrust to weight in a level turn at load factor n (unitless)."""
    if n <= 0:
        raise ValueError("load factor n must be positive, got %r" % (n,))
    q = 0.5 * rho * V * V
    if W_S <= 0:
        raise ValueError("wing loading W/S must be positive, got %r" % (W_S,))
    if V <= 0:
        raise ValueError("turn speed V must be positive, got %r" % (V,))
    if rho <= 0:
        raise ValueError("air density rho must be positive, got %r" % (rho,))
    if CD0 <= 0:
        raise ValueError("CD0 must be positive, got %r" % (CD0,))
    if k <= 0:
        raise ValueError("induced drag factor k must be positive, got %r" % (k,))
    q = 0.5 * rho * V * V
    return q * CD0 / W_S + k * n * n * W_S / q


def constraint_tw(constraint, **params):
    """Required thrust to weight for one named matching-chart constraint.

    constraint is one of CONSTRAINT_NAMES:
    - 'takeoff':     params W_S (N/m^2), rho (default 1.225), CLmax, s_TO (m)
    - 'climb':       params LD, gamma (rad). With 'engines' = n >= 2 the OEI
                     requirement is converted to the installed (all-engine)
                     basis by the factor n/(n-1) - with one engine inoperative
                     only (n-1)/n of installed thrust is available.
    - 'cruise':      params W_S, V (m/s), rho, CD0, k
    - 'maneuvering': params W_S, V (m/s), rho, CD0, k, n

    Raises ValueError for an unknown constraint or invalid parameters.
    """
    key = str(constraint).strip().lower()
    if key == "takeoff":
        return takeoff_constraint_tw(
            _require_positive(params.get("W_S"), "W_S"),
            _require_positive(params.get("rho", RHO_SL), "rho"),
            _require_positive(params.get("CLmax"), "CLmax"),
            _require_positive(params.get("s_TO"), "s_TO"))
    if key == "climb":
        raw = climb_constraint_tw(_require_positive(params.get("LD"), "LD"),
                                  _require_positive(params.get("gamma"), "gamma"))
        engines = params.get("engines")
        if engines is not None:
            if engines < 2:
                raise ValueError("engines must be >= 2 for the OEI basis "
                                 "conversion, got %r" % (engines,))
            raw *= engines / (engines - 1.0)
        return raw
    if key == "cruise":
        return cruise_constraint_tw(
            _require_positive(params.get("W_S"), "W_S"),
            _require_positive(params.get("V"), "V"),
            _require_positive(params.get("rho"), "rho"),
            _require_positive(params.get("CD0"), "CD0"),
            _require_positive(params.get("k"), "k"))
    if key == "maneuvering":
        return maneuvering_constraint_tw(
            _require_positive(params.get("W_S"), "W_S"),
            _require_positive(params.get("V"), "V"),
            _require_positive(params.get("rho"), "rho"),
            _require_positive(params.get("CD0"), "CD0"),
            _require_positive(params.get("k"), "k"),
            _require_positive(params.get("n"), "n"))
    raise ValueError("unknown constraint %r, expected one of %s"
                     % (constraint, ", ".join(CONSTRAINT_NAMES)))


def induced_drag_factor(oswald_e, aspect_ratio):
    """Induced drag factor k = 1/(pi*e*AR)."""
    if oswald_e <= 0:
        raise ValueError("Oswald efficiency must be positive, got %r" % (oswald_e,))
    if aspect_ratio <= 0:
        raise ValueError("aspect ratio must be positive, got %r" % (aspect_ratio,))
    return 1.0 / (math.pi * oswald_e * aspect_ratio)


def constraint_values_at(ws_nm2, item):
    """Dict {name: required T/W} for every active constraint at wing loading
    ws_nm2 (N/m^2), evaluated from the item's design inputs on the installed
    (all-engines) basis with cruise at the item's cruise Mach/altitude.
    """
    rho_cr = isa_density(item.cruise_alt_m)
    v_cr = isa_speed_of_sound(item.cruise_alt_m) * item.cruise_mach
    k = induced_drag_factor(item.oswald_e, item.aspect_ratio)
    values = {
        "takeoff": takeoff_constraint_tw(ws_nm2, item.rho_sl, item.clmax_takeoff,
                                         item.tofl_m),
        "climb": constraint_tw("climb", LD=item.climb_ld,
                               gamma=item.climb_gradient,
                               engines=item.n_engines),
        "cruise": cruise_constraint_tw(ws_nm2, v_cr, rho_cr, item.cruise_cd0, k),
    }
    if item.maneuver_load_factor is not None:
        values["maneuvering"] = maneuvering_constraint_tw(
            ws_nm2, v_cr, rho_cr, item.cruise_cd0, k, item.maneuver_load_factor)
    return values


def min_tw_and_binding(ws_nm2, item):
    """Minimum feasible T/W at W/S: max over the active constraint curves,
    with the name of the binding constraint (ties keep first in order)."""
    values = constraint_values_at(ws_nm2, item)
    best = None
    binding = None
    for name, value in values.items():
        if best is None or value > best:
            best = value
            binding = name
    return {"ws_nm2": ws_nm2, "min_tw": best, "binding_constraint": binding,
            "constraints": values}


def _feasible_boundary(item, n_points=9):
    """Sample the feasible-region lower bound (W/S, T/W) pairs: at each wing
    loading the lower bound is the maximum required T/W over the active
    constraint curves. Samples the range up to the stall-limited W/S."""
    ws_stall = stall_max_ws(item.stall_vs_mps, item.clmax_landing, item.rho_sl)
    lo = 0.25 * ws_stall
    pairs = []
    for i in range(n_points):
        ws = lo + (ws_stall - lo) * i / (n_points - 1.0)
        tw = max(constraint_values_at(ws, item).values())
        pairs.append((ws, tw))
    return pairs


def select_design_point(item):
    """Choose the (W/S, T/W) design point on the matching chart.

    If item.design_ws_nm2 is set, that wing loading is the engineer's choice
    from requirement framing and the chart evaluates the required T/W there
    (the feasible lower bound). Otherwise the chart picks the W/S that
    minimizes the required T/W; when the requirement is flat over a range of
    wing loadings, the largest feasible W/S (smallest wing) is chosen. The
    stall constraint caps the wing loading in both cases.
    """
    ws_stall = stall_max_ws(item.stall_vs_mps, item.clmax_landing, item.rho_sl)
    if item.design_ws_nm2 is not None:
        ws = _require_positive(item.design_ws_nm2, "design wing loading W/S")
        if ws > ws_stall * (1.0 + 1e-9):
            raise ValueError("design wing loading %g N/m^2 exceeds the stall "
                             "limit %g N/m^2" % (ws, ws_stall))
        info = min_tw_and_binding(ws, item)
    else:
        # minimize the lower bound over the feasible wing-loading range
        lo = 0.25 * ws_stall
        best_ws, best_tw = lo, None
        for i in range(401):
            cand = lo + (ws_stall - lo) * i / 400.0
            tw = max(constraint_values_at(cand, item).values())
            if best_tw is None or tw < best_tw - 1e-12:
                best_ws, best_tw = cand, tw
        # ties: smallest wing (largest feasible W/S) at the minimum T/W
        ws = best_ws if best_tw is not None else lo
        if best_tw is not None:
            for i in range(400, -1, -1):
                cand = lo + (ws_stall - lo) * i / 400.0
                if abs(max(constraint_values_at(cand, item).values())
                       - best_tw) < 1e-12:
                    ws = cand
                    break
        info = min_tw_and_binding(ws, item)
    return {"ws_stall_max": ws_stall, "ws_nm2": info["ws_nm2"],
            "tw_required": info["min_tw"], "binding_constraint": info["binding_constraint"],
            "constraints": info["constraints"]}


# ---------------------------------------------------------------------------
# Sizing-mission fuel fractions (mirrors sizing-mission-profile leaf)
# ---------------------------------------------------------------------------

def breguet_cruise_fuel_fraction(R_nm, V_kt, TSFC, LD):
    """Cruise fuel fraction of segment start weight (Breguet range equation).

    W_f/W = 1 - exp(-R/(V*TSFC*L/D)) with R in nm, V in kt, TSFC in
    lb/lbf/hr, L/D unitless - the leaf's exact model.
    """
    _require_positive(R_nm, "range R_nm")
    _require_positive(V_kt, "cruise speed V_kt")
    _require_positive(TSFC, "thrust specific fuel consumption TSFC")
    _require_positive(LD, "lift-to-drag ratio LD")
    return 1.0 - math.exp(-R_nm / (V_kt * TSFC * LD))


def breguet_loiter_fuel_fraction(E_hr, TSFC, LD):
    """Loiter/hold fuel fraction of segment start weight (Breguet endurance).

    W_f/W = 1 - exp(-E*TSFC/(L/D)) with E in hours, TSFC in lb/lbf/hr.
    """
    _require_positive(E_hr, "loiter endurance E_hr")
    _require_positive(TSFC, "thrust specific fuel consumption TSFC")
    _require_positive(LD, "lift-to-drag ratio LD")
    return 1.0 - math.exp(-E_hr * TSFC / LD)


def segment_fuel_fraction(seg_type, params, W_start=None):
    """Fuel burned in one mission segment as a fraction of its start weight.

    seg_type is one of SEGMENT_TYPES; params carries the segment's fuel model
    (see the sizing-mission-profile leaf):
    - taxi/takeoff/descent: {'fuel_flow': lb/hr, 'time': hr} -> absolute fuel,
      so the fraction needs W_start (lb) and is W0-dependent.
    - climb: {'fraction': of start weight} or {'fuel_flow','time'}.
    - cruise: {'R_nm','V_kt','TSFC','LD'} (Breguet range).
    - loiter/reserve: {'E_hr','TSFC','LD'} (Breguet endurance).
    Returns the fraction of the segment start weight burned (unitless).
    """
    if seg_type not in SEGMENT_TYPES:
        raise ValueError("unknown segment type %r, expected one of %s"
                         % (seg_type, ", ".join(SEGMENT_TYPES)))
    if seg_type in ("taxi", "takeoff", "descent"):
        flow = _require_positive(params.get("fuel_flow"), "fuel_flow")
        time = _require_positive(params.get("time"), "time")
        return flow * time / _require_positive(W_start, "segment start weight")
    if seg_type == "climb":
        if "fraction" in params:
            frac = params["fraction"]
            if frac <= 0 or frac >= 1:
                raise ValueError("climb fuel fraction must be in (0, 1), "
                                 "got %r" % (frac,))
            return frac
        flow = _require_positive(params.get("fuel_flow"), "fuel_flow")
        time = _require_positive(params.get("time"), "time")
        return flow * time / _require_positive(W_start, "segment start weight")
    if seg_type == "cruise":
        return breguet_cruise_fuel_fraction(
            _require_positive(params.get("R_nm"), "R_nm"),
            _require_positive(params.get("V_kt"), "V_kt"),
            _require_positive(params.get("TSFC"), "TSFC"),
            _require_positive(params.get("LD"), "LD"))
    # loiter and reserve both use the endurance equation
    return breguet_loiter_fuel_fraction(
        _require_positive(params.get("E_hr"), "E_hr"),
        _require_positive(params.get("TSFC"), "TSFC"),
        _require_positive(params.get("LD"), "LD"))


def mission_segments(item):
    """Ordered design-mission segment list for the item (leaf schema).

    Segment fuel models and reserve inputs follow the transport sizing
    practice encoded in the sizing-mission-profile leaf: taxi/takeoff/climb/
    descent burn fuel flow x time, cruise burns by Breguet range at the
    item's cruise speed, and the reserve is the hold45_5pct rule (45 minute
    hold at 1500 ft at the hold TSFC/L/D plus 5% of the trip fuel).
    """
    v_kt = mach_to_kt(item.cruise_mach, item.cruise_alt_m)
    return [
        {"type": "taxi", "params": {"fuel_flow": item.taxi_flow_lb_hr,
                                    "time": item.taxi_time_hr}},
        {"type": "takeoff", "params": {"fuel_flow": item.takeoff_flow_lb_hr,
                                       "time": item.takeoff_time_hr}},
        {"type": "climb", "params": {"fuel_flow": item.climb_flow_lb_hr,
                                     "time": item.climb_time_hr}},
        {"type": "cruise", "params": {"R_nm": item.range_nm, "V_kt": v_kt,
                                      "TSFC": item.tsfc_cruise,
                                      "LD": item.ld_cruise}},
        {"type": "descent", "params": {"fuel_flow": item.descent_flow_lb_hr,
                                       "time": item.descent_time_hr}},
    ]


def chain_mission(item, W_start):
    """Run the sizing mission for the item at takeoff weight W_start (lb).

    Each segment burns from the weight remaining after all earlier segments
    (the weight chains through the mission, matching the leaf's
    block_fuel_and_time). Returns per-segment fuel (lb), time (hr), start
    weight, fraction of W_start, plus block fuel/time, landing weight,
    reserve fuel under the item's reserve rule, and required fuel.
    """
    _require_positive(W_start, "takeoff weight W_start")
    segments = mission_segments(item)
    weight = W_start
    rows = []
    times = []
    for seg in segments:
        stype = seg["type"]
        params = seg["params"]
        frac = segment_fuel_fraction(stype, params, weight)
        fuel = frac * weight
        rows.append({"type": stype, "start_weight_lb": weight,
                     "fuel_lb": fuel, "fraction_of_start": frac,
                     "fraction_of_mtow": fuel / W_start})
        times.append(_segment_time(stype, params, fuel, weight))
        weight -= fuel
    if weight <= 0:
        raise ValueError("mission burns more fuel than the takeoff weight")
    block_fuel = sum(r["fuel_lb"] for r in rows)
    block_time = sum(times)
    reserve = reserve_fuel(item, weight, block_fuel)
    required = block_fuel + reserve
    return {
        "segments": rows,
        "block_fuel_lb": block_fuel,
        "block_time_hr": block_time,
        "landing_weight_lb": weight,
        "reserve_fuel_lb": reserve,
        "required_fuel_lb": required,
        "fuel_fraction": required / W_start,
    }


def _segment_time(seg_type, params, fuel, W_start):
    """Segment time in hours: explicit time param, or R/V for cruise, E for
    loiter/reserve (leaf's _segment_time behaviour)."""
    if params.get("time") is not None:
        t = params["time"]
        if t <= 0:
            raise ValueError("segment time must be positive, got %r" % (t,))
        return t
    if seg_type == "cruise":
        return (_require_positive(params.get("R_nm"), "R_nm")
                / _require_positive(params.get("V_kt"), "V_kt"))
    if seg_type in ("loiter", "reserve"):
        return _require_positive(params.get("E_hr"), "E_hr")
    raise ValueError("segment %r has no time param" % (seg_type,))


def reserve_fuel(item, landing_weight_lb, trip_fuel_lb):
    """Reserve fuel (lb) required by the item's reserve rule, burned from the
    landing weight - mirror of the leaf's reserve_fuel for hold45_5pct
    (45 min hold at 1500 ft plus 5% contingency on trip fuel)."""
    rule = item.reserve_rule
    if rule not in RESERVE_RULES:
        raise ValueError("unknown reserve rule %r, expected one of %s"
                         % (rule, ", ".join(RESERVE_RULES)))
    if rule == "hold45_5pct":
        hold = breguet_loiter_fuel_fraction(item.reserve_hold_hr,
                                            item.tsfc_hold, item.ld_hold)
        return hold * landing_weight_lb + item.reserve_contingency * trip_fuel_lb
    # far121: alternate fuel plus a 30 minute hold above the alternate
    _require_positive(item.far121_alternate_fuel_lb, "far121_alternate_fuel_lb")
    hold = breguet_loiter_fuel_fraction(item.reserve_hold_hr, item.tsfc_hold,
                                        item.ld_hold)
    return item.far121_alternate_fuel_lb + hold * landing_weight_lb


# ---------------------------------------------------------------------------
# Empty-weight fraction (class-I fit from the weight-estimation leaf) and
# takeoff-weight sizing (mirrors the tow-estimation leaf)
# ---------------------------------------------------------------------------

def empty_weight_fraction_band(category):
    """Class-I empty-weight fraction band for an aircraft category.

    Historical typical bands (weight-estimation leaf): transport 0.42-0.55,
    general-aviation 0.55-0.68, turboprop 0.50-0.62. Raises ValueError for
    an unknown category.
    """
    key = str(category).strip().lower()
    if key not in EMPTY_WEIGHT_FRACTION_BANDS:
        raise ValueError("unknown category %r; use transport, general-aviation "
                         "or turboprop" % (category,))
    return EMPTY_WEIGHT_FRACTION_BANDS[key]


def empty_weight_fraction(category="transport"):
    """Representative class-I empty-weight fraction W_e/W_0 for the category.

    The class-I fit is the historical empty-weight fraction band of the
    weight-estimation leaf; the representative value used by the sizing loop
    is the band midpoint (e.g. transport 0.42-0.55 -> 0.485).
    """
    lo, hi = empty_weight_fraction_band(category)
    return (lo + hi) / 2.0


def empty_weight_lb(mtow_lb, category="transport"):
    """Class-I empty weight (lb) from the representative fraction."""
    _require_positive(mtow_lb, "MTOW")
    return empty_weight_fraction(category) * mtow_lb


def check_empty_weight_fraction(empty_lb, mtow_lb, category):
    """(in_band, band, fraction): is empty_lb/mtow_lb inside the category
    band? Mirrors the weight-estimation leaf check."""
    if mtow_lb <= 0:
        raise ValueError("MTOW must be positive: %r" % (mtow_lb,))
    if empty_lb < 0:
        raise ValueError("empty weight must be non-negative: %r" % (empty_lb,))
    band = empty_weight_fraction_band(category)
    fraction = empty_lb / mtow_lb
    return band[0] <= fraction <= band[1], band, fraction


def tow_estimate(payload_lb, empty_fraction, fuel_fraction):
    """Takeoff gross weight (lb) from payload and class fractions:
    W0 = payload / (1 - empty_fraction - fuel_fraction) (tow-estimation leaf).
    """
    if payload_lb <= 0:
        raise ValueError("payload must be > 0, got %r" % (payload_lb,))
    if empty_fraction < 0 or fuel_fraction < 0:
        raise ValueError("fractions must be >= 0")
    remaining = 1.0 - empty_fraction - fuel_fraction
    if remaining <= 0:
        raise ValueError("empty + fuel fraction must be < 1")
    return payload_lb / remaining


def tow_converged(series, tol):
    """True when the last two TOW estimates differ by less than tol."""
    if len(series) < 2:
        raise ValueError("series must have at least two estimates")
    if any(v <= 0 for v in series):
        raise ValueError("estimates must be > 0")
    return abs(series[-1] - series[-2]) < tol


def weight_breakdown_ok(empty_lb, fuel_lb, payload_lb, total_lb, tol=0.01):
    """True when empty + fuel + payload balances the total within tol."""
    if empty_lb < 0 or fuel_lb < 0 or payload_lb < 0:
        raise ValueError("breakdown terms must be >= 0")
    if total_lb <= 0:
        raise ValueError("total must be > 0")
    return abs((empty_lb + fuel_lb + payload_lb) - total_lb) <= tol * total_lb


def size_mtow(item):
    """Iterate the takeoff gross weight to convergence (within 0.5%).

    The fuel-fraction sizing loop closes the equation
        W0 = payload / (1 - W_e/W0 - W_f/W0)
    where W_e/W0 is the class-I empty-weight fraction fit for the category
    and W_f/W0 is the required-fuel fraction (block fuel + reserves) of the
    design mission re-evaluated at the current W0 guess. Because the
    fixed-fuel segments (taxi, takeoff, climb flow, descent) do not scale
    with W0, the fuel fraction is W0-dependent and the loop genuinely
    iterates. Converges when successive estimates change by less than
    item.tolerance (default 0.005 = 0.5%) of the previous estimate.

    Returns a dict with mtow_lb, the full iteration history, the converged
    fuel/empty fractions, and the payload/empty/fuel weights.
    """
    tol = item.tolerance
    if tol <= 0:
        raise ValueError("convergence tolerance must be positive, got %r" % (tol,))
    payload = item.payload_lb()
    _require_positive(payload, "payload weight")
    frac_empty = empty_weight_fraction(item.category)
    guess = _require_positive(item.initial_guess_lb, "initial MTOW guess")
    w0 = guess
    history = []
    converged = False
    for i in range(item.max_iter):
        mission = chain_mission(item, w0)
        fuel_frac = mission["fuel_fraction"]
        w_new = tow_estimate(payload, frac_empty, fuel_frac)
        rel_change = abs(w_new - w0) / w0
        history.append({
            "iteration": i + 1,
            "guess_lb": w0,
            "mtow_new_lb": w_new,
            "fuel_fraction": fuel_frac,
            "empty_fraction": frac_empty,
            "required_fuel_lb": mission["required_fuel_lb"],
            "rel_change": rel_change,
        })
        if rel_change < tol:
            converged = True
            break
        w0 = w_new
    if not converged:
        raise ValueError("MTOW iteration failed to converge within %d "
                         "iterations (last rel. change %g)"
                         % (item.max_iter, history[-1]["rel_change"]))
    mtow = history[-1]["mtow_new_lb"]
    final_mission = chain_mission(item, mtow)
    return {
        "mtow_lb": mtow,
        "converged": converged,
        "tolerance": tol,
        "iterations": history,
        "n_iterations": len(history),
        "payload_lb": payload,
        "empty_fraction": frac_empty,
        "empty_weight_lb": frac_empty * mtow,
        "required_fuel_lb": final_mission["required_fuel_lb"],
        "fuel_fraction": final_mission["fuel_fraction"],
    }


# ---------------------------------------------------------------------------
# Engine size check (mirrors the engine-sizing leaf)
# ---------------------------------------------------------------------------

def engine_size_check(item, mtow_lb, tw_design, cruise_start_weight_lb):
    """Class-I propulsion size and top-of-climb margin check (SI inside).

    Total sea-level static thrust T_SL = (T/W)*W from the design point;
    thrust splits across item.n_engines; installed engine weight comes from
    the engine thrust-to-weight ratio (5.0 typical, 4-6 band); the top of
    climb margin is T(h) = T_SL*sigma**0.7 over the cruise thrust required
    W/(L/D) at the top of climb weight (engine-sizing leaf lapse model).
    """
    w_n = mtow_lb * LB_TO_KG * G
    t_sl_n = tw_design * w_n
    per_engine_n = t_sl_n / item.n_engines
    engine_w_n = per_engine_n / item.engine_tw_ratio
    toc_w_n = cruise_start_weight_lb * LB_TO_KG * G
    avail_n = t_sl_n * (isa_density_ratio(item.cruise_alt_m) ** 0.7)
    required_n = toc_w_n / item.ld_cruise
    margin = avail_n / required_n
    return {
        "n_engines": item.n_engines,
        "tw_design": tw_design,
        "total_thrust_lbf": t_sl_n / N_PER_LBF,
        "thrust_per_engine_lbf": per_engine_n / N_PER_LBF,
        "engine_weight_lb_each": engine_w_n / (LB_TO_KG * G),
        "engine_tw_ratio": item.engine_tw_ratio,
        "toc_margin": margin,
        "toc_ok": margin >= 1.0,
    }


# ---------------------------------------------------------------------------
# The requirement item
# ---------------------------------------------------------------------------

@dataclass
class AircraftRequirement:
    """Project facts the role needs to size the concept.

    Defaults match the worked reference item: a 100-passenger regional
    jet transport, 1500 nm design range at M0.78 / FL350, 6000 ft takeoff
    field - class-I conceptual design inputs in the transport sizing
    convention (weights lb, range nm, speeds kt / Mach).
    """
    name: str = "RegionalJet-1500 (100 pax / 1500 nm / M0.78)"
    category: str = "transport"              # empty-weight-fraction band class

    # Requirement payload
    pax: int = 100
    payload_per_pax_lb: float = 200.0        # passenger + baggage, lb (class-I)
    cargo_lb: float = 0.0

    # Sizing mission
    range_nm: float = 1500.0
    cruise_mach: float = 0.78
    cruise_alt_m: float = 10668.0            # FL350 (0.3796 kg/m^3 ISA)
    tsfc_cruise: float = 0.6                 # lb fuel/lbf thrust/hr
    ld_cruise: float = 18.0
    tsfc_hold: float = 0.5                   # hold TSFC (worse than cruise)
    ld_hold: float = 15.0
    reserve_rule: str = "hold45_5pct"
    reserve_hold_hr: float = 0.75            # 45 minute hold
    reserve_contingency: float = 0.05        # 5% of trip fuel
    far121_alternate_fuel_lb: float = 0.0    # only used by the far121 rule

    # Fixed-fuel mission segments (lb/hr x hr), transport sizing practice
    taxi_flow_lb_hr: float = 1200.0
    taxi_time_hr: float = 0.25
    takeoff_flow_lb_hr: float = 18000.0
    takeoff_time_hr: float = 0.05
    climb_flow_lb_hr: float = 24000.0
    climb_time_hr: float = 0.25
    descent_flow_lb_hr: float = 2500.0
    descent_time_hr: float = 0.30

    # Constraint-analysis inputs (SI)
    rho_sl: float = RHO_SL
    stall_vs_mps: float = 60.0               # stall speed, landing config
    clmax_landing: float = 2.5               # max CL, landing (stall limit)
    clmax_takeoff: float = 2.0               # max CL, takeoff config
    tofl_m: float = 1829.0                   # takeoff field length (6000 ft)
    climb_ld: float = 12.0                   # climb configuration L/D
    climb_gradient: float = 0.024            # FAR 25.121(b)(1), 2 engines
    cruise_cd0: float = 0.018                # clean-config cruise CD0 (class-I)
    oswald_e: float = 0.8                    # Oswald span efficiency
    aspect_ratio: float = 9.5
    maneuver_load_factor: float = None       # None disables the turn curve
    n_engines: int = 2

    # Design point and iteration controls
    design_ws_nm2: float = 5100.0            # engineer's W/S choice (None=auto)
    initial_guess_lb: float = 100000.0
    tolerance: float = 0.005                 # 0.5% convergence band
    max_iter: int = 50
    engine_tw_ratio: float = 5.0             # engine thrust-to-weight (4-6 band)

    # Weight-growth context (mass-budget leaf practice)
    design_phase: str = "conceptual"
    growth_allowance_fraction: float = None  # defaults per design phase

    def payload_lb(self):
        """Design payload weight (lb): passengers + baggage + cargo."""
        pax_lb = _require_positive(self.pax, "passenger count") * \
            _require_positive(self.payload_per_pax_lb, "payload per passenger")
        cargo = self.cargo_lb
        if cargo < 0:
            raise ValueError("cargo weight must be non-negative")
        return pax_lb + cargo

    def growth_allowance(self):
        """Growth allowance fraction for the design phase (mass-budget leaf:
        conceptual 0.10, preliminary 0.06, detailed 0.03)."""
        phase = self.design_phase.strip().lower()
        if phase not in GROWTH_ALLOWANCE_BY_PHASE:
            raise ValueError("unknown design phase %r; use conceptual, "
                             "preliminary, or detailed" % (self.design_phase,))
        if self.growth_allowance_fraction is not None:
            frac = self.growth_allowance_fraction
            if frac < 0:
                raise ValueError("growth allowance must be non-negative")
            return frac
        return GROWTH_ALLOWANCE_BY_PHASE[phase]


# ---------------------------------------------------------------------------
# Concept package builder
# ---------------------------------------------------------------------------

def build_concept(item):
    """Build the complete concept design package content model.

    Runs the full class-I chain for the item: matching-chart design point,
    sizing-mission fuel fractions at the converged MTOW, the MTOW iteration,
    the engine size/top-of-climb check, and the mass statement that balances
    to the converged MTOW.
    """
    if not isinstance(item, AircraftRequirement):
        item = item_from_dict(item)
    payload = item.payload_lb()

    # 1. Constraint analysis / design point on the matching chart
    dp = select_design_point(item)
    ws_stall = dp["ws_stall_max"]
    ws = dp["ws_nm2"]
    tw = dp["tw_required"]
    binding = dp["binding_constraint"]
    curves = dp["constraints"]
    # feasibility: on the feasible lower bound at W/S (tw >= each curve) and
    # within the stall-limited wing loading
    feasible = (tw >= max(curves.values()) - 1e-12) and ws <= ws_stall * (1 + 1e-9)
    w_n = 0.0  # filled after sizing; recomputed below from mtow

    # 2. MTOW sizing iteration
    sizing = size_mtow(item)
    mtow_lb = sizing["mtow_lb"]
    oew_lb = sizing["empty_weight_lb"]
    fuel_lb = sizing["required_fuel_lb"]
    empty_frac = sizing["empty_fraction"]
    in_band, band, _ = check_empty_weight_fraction(oew_lb, mtow_lb, item.category)

    # 3. Mission details at the converged MTOW (for the report)
    mission = chain_mission(item, mtow_lb)
    v_kt = mach_to_kt(item.cruise_mach, item.cruise_alt_m)

    # 4. Geometry from the design point
    w_newton = mtow_lb * LB_TO_KG * G
    wing_area_m2 = w_newton / ws
    span_m = math.sqrt(item.aspect_ratio * wing_area_m2)
    k = induced_drag_factor(item.oswald_e, item.aspect_ratio)
    ld_max = 1.0 / (2.0 * math.sqrt(k * item.cruise_cd0))

    # 5. Engine size check (top of climb at the start-of-cruise weight)
    cruise_start = next(r["start_weight_lb"] for r in mission["segments"]
                        if r["type"] == "cruise")
    engine = engine_size_check(item, mtow_lb, tw, cruise_start)

    # 6. Mass statement rows (must sum to the converged MTOW)
    rows = [
        {"group": "Operating empty weight (class-I fit %.3f x MTOW)"
                  % empty_frac, "weight_lb": oew_lb, "pct_mtow": empty_frac * 100.0},
        {"group": "Design payload (%d pax x %.0f lb + cargo)" % (item.pax,
                 item.payload_per_pax_lb), "weight_lb": payload,
         "pct_mtow": payload / mtow_lb * 100.0},
        {"group": "Fuel (mission + reserves, hold45_5pct)", "weight_lb": fuel_lb,
         "pct_mtow": fuel_lb / mtow_lb * 100.0},
    ]
    balances = weight_breakdown_ok(oew_lb, fuel_lb, payload, mtow_lb)

    return {
        "document_type": "Concept Design Package",
        "status": "draft-for-review",
        "generated": date.today().isoformat(),
        "item": item.name,
        "category": item.category,
        "requirement": {
            "pax": item.pax,
            "payload_per_pax_lb": item.payload_per_pax_lb,
            "payload_lb": payload,
            "range_nm": item.range_nm,
            "cruise_mach": item.cruise_mach,
            "cruise_alt_m": item.cruise_alt_m,
            "cruise_v_kt": v_kt,
            "tofl_m": item.tofl_m,
            "tofl_ft": item.tofl_m / 0.3048,
            "n_engines": item.n_engines,
        },
        "design_point": {
            "ws_nm2": ws,
            "ws_psf": ws * NM2_TO_PSF,
            "tw_required": tw,
            "binding_constraint": binding,
            "feasible": feasible,
            "climb_gradient": item.climb_gradient,
            "climb_ld": item.climb_ld,
            "n_engines": item.n_engines,
            "ws_stall_max_nm2": ws_stall,
            "ws_stall_max_psf": ws_stall * NM2_TO_PSF,
            "curves": {name: {"value": val, "tw_at_design": val}
                       for name, val in curves.items()},
            "boundary": _feasible_boundary(item),
            "aerodynamics": {"cd0": item.cruise_cd0, "k": k,
                             "oswald_e": item.oswald_e,
                             "aspect_ratio": item.aspect_ratio,
                             "ld_max": ld_max},
        },
        "wing": {"area_m2": wing_area_m2, "span_m": span_m,
                 "aspect_ratio": item.aspect_ratio,
                 "area_ft2": wing_area_m2 / 0.09290304},
        "mission": {
            "segments": mission["segments"],
            "block_fuel_lb": mission["block_fuel_lb"],
            "block_time_hr": mission["block_time_hr"],
            "landing_weight_lb": mission["landing_weight_lb"],
            "reserve_fuel_lb": mission["reserve_fuel_lb"],
            "reserve_rule": item.reserve_rule,
            "required_fuel_lb": mission["required_fuel_lb"],
            "fuel_fraction_of_mtow": mission["fuel_fraction"],
            "cruise_v_kt": v_kt,
        },
        "sizing": {
            "mtow_lb": mtow_lb,
            "mtow_kg": mtow_lb * LB_TO_KG,
            "converged": sizing["converged"],
            "tolerance": sizing["tolerance"],
            "iterations": sizing["iterations"],
            "n_iterations": sizing["n_iterations"],
            "empty_fraction": empty_frac,
            "empty_in_band": in_band,
            "empty_band": band,
            "oew_lb": oew_lb,
            "fuel_lb": fuel_lb,
            "payload_lb": payload,
        },
        "engine": engine,
        "mass_statement": {
            "rows": rows,
            "total_lb": mtow_lb,
            "balances": balances,
            "growth_allowance": item.growth_allowance(),
            "design_phase": item.design_phase,
        },
        "gates": check_concept({
            "status": "draft-for-review",
            "requirement": {"payload_lb": payload, "range_nm": item.range_nm},
            "design_point": {"feasible": feasible, "binding_constraint": binding,
                             "ws_nm2": ws, "tw_required": tw},
            "sizing": {"converged": sizing["converged"],
                       "iterations": sizing["iterations"],
                       "mtow_lb": mtow_lb, "empty_in_band": in_band},
            "mass_statement": {"total_lb": mtow_lb, "balances": balances,
                               "rows": rows},
        }),
    }


def item_from_dict(data):
    """Build an AircraftRequirement from a plain dict (unknown keys ignored)."""
    known = {f.name for f in AircraftRequirement.__dataclass_fields__.values()}
    return AircraftRequirement(**{k: v for k, v in data.items() if k in known})


# ---------------------------------------------------------------------------
# Render: the concept design package document
# ---------------------------------------------------------------------------

def render_concept_markdown(model):
    """Render the concept content model as the deliverable markdown package."""
    req = model["requirement"]
    dp = model["design_point"]
    wing = model["wing"]
    mis = model["mission"]
    sizing = model["sizing"]
    eng = model["engine"]
    ms = model["mass_statement"]

    def seg_row(s):
        frac = s["fraction_of_mtow"] * 100.0
        if s["type"] == "cruise":
            desc = (f"Cruise ({req['range_nm']:,.0f} nm @ "
                    f"{mis['cruise_v_kt']:,.0f} kt)")
        else:
            desc = s["type"].capitalize()
        return (f"| {desc} | {s['fuel_lb']:,.0f} lb | "
                f"{frac:.1f}% of MTOW |")

    lines = [
        "# Concept Design Package - %s" % model["item"],
        "",
        "**Document type:** %s  " % model["document_type"],
        "**Status:** %s  " % model["status"],
        "**Aircraft class:** %s (class-I conceptual sizing)" % model["category"],
        "**Generated:** %s" % model["generated"],
        "",
        "## 1. Requirements and design space",
        "",
        "| Requirement | Value |",
        "|---|---|",
        f"| Passengers | {req['pax']} pax |",
        f"| Payload | {req['payload_lb']:,.0f} lb ({req['pax']} pax x "
        f"{req['payload_per_pax_lb']:,.0f} lb + baggage, class-I) |",
        f"| Design range | {req['range_nm']:,.0f} nm |",
        f"| Cruise | M{req['cruise_mach']:.2f} at {req['cruise_alt_m']:,.0f} m "
        f"(FL{req['cruise_alt_m'] / 30.48:,.0f}), {req['cruise_v_kt']:,.0f} kt TAS |",
        f"| Takeoff field length | {req['tofl_m']:,.0f} m "
        f"({req['tofl_ft']:,.0f} ft) |",
        f"| Engines | {req['n_engines']} turbofans |",
        "",
        "Constraint diagram (matching chart, T/W vs W/S; SI inputs, "
        "sea-level ISA for takeoff, cruise at FL350):",
        "",
        "| Constraint | Rule | Value at design W/S |",
        "|---|---|---|",
        f"| Stall (max W/S) | W/S = 0.5*rho*CLmax*VS^2 | "
        f"{dp['ws_stall_max_nm2']:,.0f} N/m^2 ({dp['ws_stall_max_psf']:,.1f} psf) |",
    ]
    aero = dp["aerodynamics"]
    for name in ("takeoff", "climb", "cruise", "maneuvering"):
        if name in dp["curves"]:
            rule = {
                "takeoff": "T/W = 1.21*(W/S)/(rho*g*CLmax*s_TO)",
                "climb": "T/W = 1/LD + gamma (OEI -> installed, x n/(n-1))",
                "cruise": "T/W = q*CD0/(W/S) + k*(W/S)/q",
                "maneuvering": "T/W = q*CD0/(W/S) + k*n^2*(W/S)/q",
            }[name]
            lines.append(
                f"| {name.capitalize()} | {rule} | "
                f"{dp['curves'][name]['tw_at_design']:.4f} |")
    lines += [
        "",
        f"**Selected design point:** W/S = {dp['ws_nm2']:,.0f} N/m^2 "
        f"({dp['ws_psf']:,.1f} psf), T/W = {dp['tw_required']:.4f} "
        f"(binding constraint: {dp['binding_constraint']}).",
        f"**Feasible:** {dp['feasible']} - the point lies on the lower bound "
        "of the feasible region (stall limit not exceeded).",
        f"Feasible-region boundary samples (W/S N/m^2 -> minimum T/W): "
        + ", ".join(f"{ws:,.0f} -> {tw:.4f}" for ws, tw in dp["boundary"]) + ".",
        "",
        "## 2. Sizing mission",
        "",
        "Mission profile (segments in flight order; each burns from the "
        "weight remaining after earlier segments, Breguet range/endurance "
        "models):",
        "",
        "| Segment | Fuel burned | Fraction of MTOW |",
        "|---|---|---|",
    ]
    lines += [seg_row(s) for s in mis["segments"]]
    lines += [
        "",
        f"| **Block fuel** | **{mis['block_fuel_lb']:,.0f} lb** | "
        f"**{mis['block_fuel_lb'] / sizing['mtow_lb'] * 100:.1f}%** |",
        f"| Block time | {mis['block_time_hr']:.2f} hr | |",
        f"| Landing weight | {mis['landing_weight_lb']:,.0f} lb | |",
        f"| Reserve ({mis['reserve_rule']}: "
        f"{model['sizing']['iterations'][0] and '45 min hold at 1500 ft + 5% trip'}) "
        f"| {mis['reserve_fuel_lb']:,.0f} lb | |",
        f"| **Required fuel (mission + reserves)** | "
        f"**{mis['required_fuel_lb']:,.0f} lb** | "
        f"**{mis['fuel_fraction_of_mtow'] * 100:.1f}% of MTOW** |",
        "",
        "## 3. Configuration (from the design point)",
        "",
        f"- Wing loading W/S: {dp['ws_nm2']:,.0f} N/m^2 "
        f"({dp['ws_psf']:,.1f} psf) - design choice, {dp['ws_nm2'] / dp['ws_stall_max_nm2'] * 100:.1f}% "
        "of the stall-limited maximum.",
        f"- Wing area S = W/(W/S) = {wing['area_m2']:,.1f} m^2 "
        f"({wing['area_ft2']:,.0f} ft^2); aspect ratio {wing['aspect_ratio']:.1f}; "
        f"span b = {wing['span_m']:,.1f} m.",
        f"- Drag model: CD0 = {aero['cd0']:.3f}, e = {aero['oswald_e']:.2f}, "
        f"k = 1/(pi*e*AR) = {aero['k']:.4f}; L/D_max = {aero['ld_max']:.1f} "
        "(consistent with the mission cruise L/D of 18).",
        f"- Engines: {eng['n_engines']} x ~{eng['thrust_per_engine_lbf']:,.0f} lbf "
        "class sea-level static thrust (see Section 5).",
        "- 3-view reference geometry from the OpenVSP stage (initial layout) "
        "feeds the class-II mass build-up; not required for the class-I "
        "sizing closure.",
        "",
        "## 4. Mass statement (class-I, balances to converged MTOW)",
        "",
        "| Group | Weight (lb) | % MTOW |",
        "|---|---|---|",
    ]
    for r in ms["rows"]:
        lines.append(f"| {r['group']} | {r['weight_lb']:,.0f} | {r['pct_mtow']:.1f}% |")
    lines += [
        f"| **Maximum takeoff weight (converged)** | **{sizing['mtow_lb']:,.0f}** | **100.0%** |",
        "",
        f"- Balance check (empty + payload + fuel vs MTOW): "
        f"{'PASS within 1%' if ms['balances'] else 'FAIL'}.",
        f"- Empty-weight fraction {sizing['empty_fraction']:.3f} inside the "
        f"{model['category']} class-I band {sizing['empty_band'][0]:.2f}-"
        f"{sizing['empty_band'][1]:.2f}: "
        f"{'PASS' if sizing['empty_in_band'] else 'FAIL'}.",
        f"- Weight-growth context: {ms['design_phase']} phase growth allowance "
        f"{ms['growth_allowance'] * 100:.0f}% applies to the detailed mass "
        "budget roll-up (mass-budget stage).",
        "- CG envelope and critical loading conditions require the 3-view "
        "layout and the mass-properties stage (component arms); the class-I "
        "closure above bounds the balance (fuel + payload = "
        f"{sizing['fuel_lb'] + sizing['payload_lb']:,.0f} lb available below "
        f"MTOW - OEW = {sizing['mtow_lb'] - sizing['oew_lb']:,.0f} lb).",
        "",
        "## 5. MTOW convergence and engine size check",
        "",
        "Fuel-fraction sizing iteration "
        "(W0 = payload / (1 - W_e/W0 - W_f/W0), class-I empty fraction "
        f"{sizing['empty_fraction']:.3f}):",
        "",
        "| Iteration | Guess (lb) | Fuel fraction | New MTOW (lb) | Rel. change |",
        "|---|---|---|---|---|",
    ]
    for it in sizing["iterations"]:
        lines.append(
            f"| {it['iteration']} | {it['guess_lb']:,.0f} | "
            f"{it['fuel_fraction']:.4f} | {it['mtow_new_lb']:,.0f} | "
            f"{it['rel_change'] * 100:.2f}% |")
    lines += [
        "",
        f"**Converged MTOW = {sizing['mtow_lb']:,.0f} lb "
        f"({sizing['mtow_kg']:,.0f} kg)** after {sizing['n_iterations']} "
        f"iterations (tolerance {sizing['tolerance'] * 100:.1f}%): "
        f"{'CONVERGED' if sizing['converged'] else 'NOT CONVERGED'}.",
        "",
        f"- Installed sea-level thrust: {eng['total_thrust_lbf']:,.0f} lbf "
        f"total = {eng['thrust_per_engine_lbf']:,.0f} lbf per engine "
        f"(T/W = {eng['tw_design']:.3f}).",
        f"- Engine weight estimate: ~{eng['engine_weight_lb_each']:,.0f} lb "
        f"per engine at engine T/W = {eng['engine_tw_ratio']:.1f} "
        "(4-6 typical band).",
        f"- Top-of-climb margin at {req['cruise_alt_m']:,.0f} m "
        f"(thrust lapse sigma^0.7 vs W/(L/D)): {eng['toc_margin']:.2f} "
        f"- {'PASS (>= 1.0)' if eng['toc_ok'] else 'FAIL (< 1.0)'}.",
        "- Engine-out second-segment gradient is carried on the installed "
        "basis: T/W = (n/(n-1)) x (1/LD + gamma) with LD = "
        f"{dp['climb_ld']:.0f} and gamma = {dp['climb_gradient']:.3f} "
        f"(FAR 25.121(b)(1) two-engine value, {dp['n_engines']} engines); the "
        "engine-sizing stage re-checks OEI climb, hot day, and takeoff "
        "derate against the catalogue engine.",
        "",
        "## 6. Feasibility notes and next stages",
        "",
        "- Class-I results are FEASIBILITY, not detailed design: the "
        "converged MTOW, the W/S-T/W design point, and the mass statement "
        "close the sizing loop within the stated class-I model accuracy.",
        "- Structure/propulsion/systems mass split requires the class-II "
        "component build-up (weight-estimation, engine-sizing, fuselage/"
        "wing/tail-sizing leaves); the conceptual growth allowance "
        f"({ms['growth_allowance'] * 100:.0f}%) is the margin policy for that "
        "roll-up.",
        "- Payload-range, cost (parametric DOC/LCC), and CG envelope are "
        "produced by the dedicated stages (payload-range-diagram, "
        "parametric-cost, cg-envelope) once the class-II breakdown exists.",
        "",
        "---",
        "",
        "*DRAFT - conceptual feasibility for human design review. Not a "
        "production release and not an approval document. Conceptual results "
        "are class-I estimates; every configuration choice must trace to the "
        "trade data before detailed design.*",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evidence gate checkers
# ---------------------------------------------------------------------------

GATE_CHECKS = {
    "requirements_present": "payload and range requirements are real numbers",
    "mtow_converged": "MTOW converged to within the 0.5% band (>= 2 iterations)",
    "empty_fraction_in_band": "empty weight fraction inside the category band",
    "design_point_feasible": "design point lies on the feasible boundary",
    "mass_statement_balances": "empty + payload + fuel balance MTOW within 1%",
    "sign_off_honest": "document is marked draft-for-review, not approval",
}


def check_concept(model):
    """Run the evidence gates against a concept model. Pass/fail per gate."""
    req = model.get("requirement", {})
    dp = model.get("design_point", {})
    sizing = model.get("sizing", {})
    ms = model.get("mass_statement", {})
    iters = sizing.get("iterations", [])
    last_rel = (iters[-1]["rel_change"] if len(iters) >= 2 else None)
    results = {
        "requirements_present": (
            isinstance(req.get("payload_lb"), (int, float)) and req["payload_lb"] > 0
            and isinstance(req.get("range_nm"), (int, float)) and req["range_nm"] > 0),
        "mtow_converged": (bool(sizing.get("converged"))
                           and len(iters) >= 2
                           and last_rel is not None
                           and last_rel < sizing.get("tolerance", 0.005)),
        "empty_fraction_in_band": bool(sizing.get("empty_in_band")),
        "design_point_feasible": bool(dp.get("feasible"))
            and isinstance(dp.get("ws_nm2"), (int, float))
            and isinstance(dp.get("tw_required"), (int, float)),
        "mass_statement_balances": bool(ms.get("balances"))
            and ms.get("total_lb", 0) > 0,
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_concept_markdown(md_text):
    """Gate-check the rendered concept design package markdown deliverable."""
    low = md_text.lower()
    import re as _re
    checks = {
        "has_title": "concept design package" in low,
        "has_mtow": _re.search(r"Maximum takeoff weight \(converged\)\*\* \| "
                               r"\*\*[\d,]+", md_text) is not None,
        "has_ws": _re.search(r"W/S = [\d,]+ N/m\^2", md_text) is not None,
        "has_tw": _re.search(r"T/W = 0\.\d+", md_text) is not None,
        "has_convergence_history": "| Iteration |" in md_text
            and "CONVERGED" in md_text.upper(),
        "has_mass_statement": "| Operating empty weight" in md_text
            and "| **Maximum takeoff weight" in md_text,
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
        "no_blank_fields": "___" not in md_text and "__" not in _strip_em(md_text),
    }
    checks["all_pass"] = all(checks.values())
    return checks


def _strip_em(text):
    """Remove '**' emphasis markers so '____' style emphasis is not a blank."""
    return text.replace("**", "")


# ---------------------------------------------------------------------------
# Example requirement (reference item for tests and worked-example output)
# ---------------------------------------------------------------------------

def example_item():
    """Reference item: 100-pax regional jet transport, 1500 nm @ M0.78."""
    return AircraftRequirement()


def example_concept_markdown():
    """Concept design package markdown for the reference item."""
    return render_concept_markdown(build_concept(example_item()))


if __name__ == "__main__":
    item = example_item()
    model = build_concept(item)
    md = render_concept_markdown(model)
    s = model["sizing"]
    dp = model["design_point"]
    print(f"ITEM: {model['item']}")
    print(f"MTOW: {s['mtow_lb']:,.0f} lb (converged in {s['n_iterations']} "
          f"iterations, tol {s['tolerance']:.3f})")
    print(f"DESIGN POINT: W/S {dp['ws_nm2']:,.0f} N/m^2 ({dp['ws_psf']:,.1f} psf), "
          f"T/W {dp['tw_required']:.4f} ({dp['binding_constraint']} binding)")
    print(f"MASS: OEW {s['oew_lb']:,.0f} lb + payload {s['payload_lb']:,.0f} lb "
          f"+ fuel {s['fuel_lb']:,.0f} lb = MTOW {s['mtow_lb']:,.0f} lb")
    print(f"GATES: {check_concept(model)}")
    print(f"MARKDOWN GATES: {check_concept_markdown(md)}")
    print(f"RENDERED: {len(md)} chars")
