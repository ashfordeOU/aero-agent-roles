#!/usr/bin/env python3
"""aircraft_systems_sizing_core.py - Aircraft Systems Sizing Engineer engine.

The role's ENGINE: given an aircraft's systems requirements it sizes each
aircraft system with REAL domain formulas from the bound AeroSkills
vehicle-design/sizing leaves (each leaf's scripts/*_logic.py encodes the
formulas this core mirrors):

  - electrical power system (aircraft-electrical-load-analysis leaf):
    duty-weighted continuous load, coincident peak, essential load, and
    the single-generator-out margin (FAR 25.1355 context)
  - ECS air cycle machine (air-cycle-machine-sizing leaf): bootstrap
    pack compressor/turbine/heat-exchanger states, shaft balance, and
    the bleed flow that carries the cooling load
  - avionics bay cooling (avionics-bay-cooling-sizing leaf): bay heat
    load, cooling airflow, and per-LRU case temperature verdicts
  - supplemental oxygen (aircraft-oxygen-system-sizing leaf): passenger
    generator demand, crew diluter-demand, and crew bottle volume
  - wheel brakes (brake-energy-sizing leaf): RTO/landing kinetic energy,
    per-brake heat sink sizing and temperature rise
  - cabin outflow + relief valves (cabin-outflow-valve-sizing leaf):
    choked-flow effective areas at the cruise and clamp conditions
  - fuel feed (fuel-feed-system-sizing leaf): line velocity, losses,
    NPSHa vs NPSHr, boost pump power
  - fuel jettison (fuel-jettison-sizing leaf): dumpable fuel and the
    15-minute (900 s) landing-weight rate per FAR 25.1001 context
  - fuel tank inerting (fuel-tank-inerting-sizing leaf): NEA washout
    flow to the target ullage oxygen fraction
  - hydraulic actuation (hydraulic-actuator-sizing leaf): piston area,
    bore, rod buckling diameter, preferred sizes, mass estimate
  - landing gear layout (landing-gear-layout leaf): tipback, tail strike
    clearance, lateral turnover, and nose gear static load fractions
  - ram air turbine (ram-air-turbine-sizing leaf): emergency power rotor
    swept area and disk diameter
  - tires (tire-sizing leaf): static load per tire, diameter/width power
    law fits, required tire count
  - window apertures (window-aperture-sizing leaf): design pressure
    differential, pane thickness and margin for the pressurized cabin

Every number below is produced by code from these formulas; nothing is
invented. The core runs STANDALONE (no AeroSkills checkout needed); the
CLI additionally dispatches the bound leaves' own logic functions when
the skills repo is present and records agreement in provenance.json.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from datetime import date

# ---------------------------------------------------------------------------
# Shared physical constants (identical to the bound leaf modules)
# ---------------------------------------------------------------------------
G0 = 9.80665              # standard gravity, m/s^2
PSI_TO_PA = 6894.757      # Pa per psi
R_AIR = 287.0             # J/(kg K)
GAMMA_AIR = 1.4
CP_AIR = 1005.0           # J/(kg K) dry air
RHO_SL = 1.225            # kg/m3 ISA sea level
SCFM_PER_M3S = 2118.88    # standard cubic feet per minute per m3/s


def _today() -> str:
    return os.environ.get("ROLE_GEN_DATE", date.today().isoformat())


# ===========================================================================
# 1. ELECTRICAL LOAD ANALYSIS  (aircraft-electrical-load-analysis leaf)
# ===========================================================================
def continuous_load(consumers):
    """Duty-weighted continuous load kVA (leaf: continuous_load)."""
    if not consumers:
        raise ValueError("consumers dict must not be empty")
    rollup = []
    for power_kva, duty in consumers.values():
        if power_kva < 0.0:
            raise ValueError("consumer power must be >= 0 kVA")
        if not (0.0 <= duty <= 1.0):
            raise ValueError("consumer duty must lie in [0, 1]")
        rollup.append(power_kva * duty)
    return {"continuous_kva": sum(rollup), "rollup": rollup}


def diversity_peak(continuous_kva, diversity_factor):
    """Coincident peak kVA = diversity_factor * continuous load."""
    if continuous_kva < 0.0:
        raise ValueError("continuous load must be >= 0 kVA")
    if not (0.0 < diversity_factor <= 1.0):
        raise ValueError("diversity factor must lie in (0, 1]")
    return diversity_factor * continuous_kva


def essential_load(consumers, essential_names):
    """Essential load kVA at full rated power (failure-case bookkeeping)."""
    if not consumers:
        raise ValueError("consumers dict must not be empty")
    total = 0.0
    names = []
    for name in essential_names:
        if name not in consumers:
            raise ValueError("essential consumer %r not in consumers" % name)
        total += consumers[name][0]
        names.append(name)
    return {"essential_kva": total, "essential_consumers": names}


def generator_out_margin(n_generators, generator_kva, essential_kva):
    """Single-generator-out margin dict (leaf formula)."""
    if n_generators < 1:
        raise ValueError("n_generators must be >= 1")
    if generator_kva <= 0.0:
        raise ValueError("generator_kva must be > 0")
    if essential_kva < 0.0:
        raise ValueError("essential_kva must be >= 0")
    remaining_kva = (n_generators - 1) * generator_kva
    if n_generators == 1:
        return {"remaining_kva": 0.0, "margin": -1.0, "verdict": "FAIL"}
    margin = (remaining_kva - essential_kva) / remaining_kva
    verdict = "PASS" if margin >= 0.0 else "FAIL"
    return {"remaining_kva": remaining_kva, "margin": margin,
            "verdict": verdict}


def load_fraction(continuous_kva, installed_kva):
    """Normal load fraction = continuous / installed kVA."""
    if installed_kva <= 0.0:
        raise ValueError("installed_kva must be > 0")
    return continuous_kva / installed_kva


# ===========================================================================
# 2. AIR CYCLE MACHINE  (air-cycle-machine-sizing leaf)
# ===========================================================================
_EXP = (GAMMA_AIR - 1.0) / GAMMA_AIR
BALANCE_TOL_W = 1.0


def compressor_exit(bleed_p1, bleed_t1, pr_c, eta_c):
    """T2/T1 + (1 + (pr^EXP - 1)/eta), p2 = p1*pr (leaf: compressor_exit)."""
    t2 = bleed_t1 * (1.0 + (pr_c ** _EXP - 1.0) / eta_c)
    return {"t2": t2, "p2": bleed_p1 * pr_c}


def heat_exchanger_exit(t_hot_in, effectiveness, t_sink):
    """T3 = T_hot - eff*(T_hot - T_sink) (leaf: heat_exchanger_exit)."""
    return t_hot_in - effectiveness * (t_hot_in - t_sink)


def turbine_exit(p3, t3, pr_t, eta_t, p_cabin):
    """Cooling turbine exit (leaf: turbine_exit); p4 = p_cabin."""
    p4 = p_cabin
    t4 = t3 * (1.0 - eta_t * (1.0 - (p4 / p3) ** _EXP))
    return {"t4": t4, "p4": p4, "pr_t": pr_t}


def compressor_power(m_dot, t1, t2):
    """W_c = m_dot * CP_AIR * (T2 - T1)."""
    return m_dot * CP_AIR * (t2 - t1)


def turbine_power(m_dot, t3, t4):
    """W_t = m_dot * CP_AIR * (T3 - T4)."""
    return m_dot * CP_AIR * (t3 - t4)


def shaft_balance(w_compressor, w_turbine):
    """Two-wheel ACM balance verdict (leaf formula, 1 W band)."""
    balanced = w_turbine + BALANCE_TOL_W >= w_compressor
    deficit_w = max(w_compressor - w_turbine, 0.0)
    return {"balanced": balanced, "w_compressor": w_compressor,
            "w_turbine": w_turbine, "deficit_w": deficit_w,
            "power_ratio": w_turbine / w_compressor}


def t3_required_for_balance(t1, t2, eta_t, p3, p_cabin):
    """Turbine inlet temperature that closes W_t = W_c (leaf formula)."""
    denom = eta_t * (1.0 - (p_cabin / p3) ** _EXP)
    return (t2 - t1) / denom


def hx_effectiveness_for_balance(t2, t_sink, t3_required):
    """Effectiveness that lands T3 on the balance value (leaf formula)."""
    return (t2 - t3_required) / (t2 - t_sink)


def cooling_capacity(m_dot, t_turbine_out, t_cabin_supply_target):
    """Delivered cooling power Q = m_dot*CP_AIR*(T_target - T4), signed W."""
    return m_dot * CP_AIR * (t_cabin_supply_target - t_turbine_out)


def required_bleed_flow(q_load, t4_effective, target_t):
    """Bleed flow (kg/s) that carries the load: Q/(CP_AIR*(T_target - T4))."""
    return q_load / (CP_AIR * (target_t - t4_effective))


# ===========================================================================
# 3. AVIONICS BAY COOLING  (avionics-bay-cooling-sizing leaf)
# ===========================================================================
DEFAULT_AIR_DENSITY = 1.2
DEFAULT_CASE_CONDUCTANCE_W_K = 12.0


def bay_heat_load(lru_dissipations_w):
    """Roll up bay heat load from {lru: W} or [W, ...] (leaf formula)."""
    if lru_dissipations_w is None:
        raise ValueError("LRU dissipation list must not be empty")
    try:
        items = list(lru_dissipations_w.items())
        per_lru = dict(items)
    except AttributeError:
        items = list(enumerate(lru_dissipations_w))
        per_lru = [p for _, p in items]
    if not items:
        raise ValueError("LRU dissipation list must not be empty")
    for label, power in items:
        if power < 0:
            raise ValueError("negative LRU dissipation is non-physical")
    total = float(sum(power for _, power in items))
    return {"total_w": total, "per_lru_w": per_lru}


def cooling_mass_flow(total_heat_w, supply_temp_c, exhaust_limit_c,
                      cp=CP_AIR):
    """m_dot = Q/(cp*(T_limit - T_supply)); exhaust sized to the limit."""
    delta_t = exhaust_limit_c - supply_temp_c
    if total_heat_w == 0:
        flow = 0.0
    else:
        flow = total_heat_w / (cp * delta_t)
    return {"mass_flow_kg_s": flow, "exhaust_temp_c": exhaust_limit_c}


def volumetric_flow(mass_flow_kg_s, density=DEFAULT_AIR_DENSITY):
    """Mass flow to volumetric flow and CFM (leaf formula)."""
    flow_m3_s = mass_flow_kg_s / density
    return {"flow_m3_s": flow_m3_s, "flow_cfm": flow_m3_s * SCFM_PER_M3S}


def lru_case_temperature(power_w, conductance_w_k, inlet_air_temp_c):
    """T_case = T_inlet + P/(hA) (leaf formula)."""
    rise = power_w / conductance_w_k
    return {"case_temp_c": inlet_air_temp_c + rise, "rise_k": rise}


def case_verdict(case_temp_c, case_limit_c):
    """PASS/FAIL verdict with margin K for one LRU case temperature."""
    margin = case_limit_c - case_temp_c
    verdict = "PASS" if case_temp_c <= case_limit_c else "FAIL"
    return {"verdict": verdict, "margin_k": margin}


def bay_cooling_summary(lru_dissipations_w, supply_temp_c, exhaust_limit_c,
                        lru_case_limits_c,
                        density=DEFAULT_AIR_DENSITY,
                        conductance_w_k=DEFAULT_CASE_CONDUCTANCE_W_K):
    """Complete avionics bay cooling summary (leaf bay_cooling_summary)."""
    heat = bay_heat_load(lru_dissipations_w)
    total_w = heat["total_w"]
    powers = (list(heat["per_lru_w"].values())
              if isinstance(heat["per_lru_w"], dict)
              else list(heat["per_lru_w"]))
    flow = cooling_mass_flow(total_w, supply_temp_c, exhaust_limit_c)
    volume = volumetric_flow(flow["mass_flow_kg_s"], density)
    case_temps, verdicts = {}, {}
    for i, (power, limit) in enumerate(zip(powers, lru_case_limits_c)):
        case = lru_case_temperature(power, conductance_w_k, supply_temp_c)
        case_temps[i] = case["case_temp_c"]
        verdicts[i] = case_verdict(case["case_temp_c"], limit)["verdict"]
    any_fail = any(v == "FAIL" for v in verdicts.values())
    flowless_with_heat = total_w > 0 and flow["mass_flow_kg_s"] <= 0
    bay_verdict = "FAIL" if (any_fail or flowless_with_heat) else "PASS"
    return {"total_w": total_w,
            "mass_flow_kg_s": flow["mass_flow_kg_s"],
            "flow_m3_s": volume["flow_m3_s"],
            "flow_cfm": volume["flow_cfm"],
            "exhaust_temp_c": flow["exhaust_temp_c"],
            "case_temps_c": case_temps,
            "case_verdicts": verdicts,
            "bay_verdict": bay_verdict}


# ===========================================================================
# 4. SUPPLEMENTAL OXYGEN  (aircraft-oxygen-system-sizing leaf)
# ===========================================================================
R_O2 = 259.8              # J/(kg K)
RHO_O2_STP = 1.429        # kg/m3 at 0 C, 101.325 kPa
STORAGE_TEMP_K = 288.15
FLOW_PAX_SLPM = 5.0
FLOW_CREW_SLPM = 2.5
PAX_PROTECTION_MIN = 22.0
CREW_PROTECTION_MIN = 120.0


def passenger_demand(n_passengers, flow_slpm=FLOW_PAX_SLPM,
                     duration_min=PAX_PROTECTION_MIN):
    """Passenger oxygen demand: volume SL + mass kg (leaf formula)."""
    volume_sl = n_passengers * flow_slpm * duration_min
    mass_kg = volume_sl * 1e-3 * RHO_O2_STP
    return {"volume_sl": volume_sl, "mass_kg": mass_kg}


def generator_units(n_passengers):
    """Continuous-flow generator count = one per passenger."""
    return int(n_passengers)


def crew_demand(n_crew, flow_slpm=FLOW_CREW_SLPM,
                duration_min=CREW_PROTECTION_MIN):
    """Crew diluter-demand oxygen: volume SL + mass kg."""
    volume_sl = n_crew * flow_slpm * duration_min
    mass_kg = volume_sl * 1e-3 * RHO_O2_STP
    return {"volume_sl": volume_sl, "mass_kg": mass_kg}


def bottle_volume(mass_kg, service_pressure_psi,
                  temperature_k=STORAGE_TEMP_K):
    """Crew gaseous bottle volume m3/L from the ideal gas law (leaf)."""
    p_pa = service_pressure_psi * PSI_TO_PA
    volume_m3 = mass_kg * R_O2 * temperature_k / p_pa
    return {"volume_m3": volume_m3, "volume_l": volume_m3 * 1000.0}


def oxygen_summary(n_passengers, n_crew, service_pressure_psi):
    """Full supplemental oxygen sizing summary (leaf oxygen_summary)."""
    pax = passenger_demand(n_passengers)
    crew = crew_demand(n_crew)
    bottle = bottle_volume(crew["mass_kg"], service_pressure_psi)
    return {
        "passenger_demand_sl": pax["volume_sl"],
        "passenger_mass_kg": pax["mass_kg"],
        "generator_units": generator_units(n_passengers),
        "crew_demand_sl": crew["volume_sl"],
        "crew_mass_kg": crew["mass_kg"],
        "bottle_volume_m3": bottle["volume_m3"],
        "bottle_volume_l": bottle["volume_l"],
        "total_mass_kg": pax["mass_kg"] + crew["mass_kg"],
    }


# ===========================================================================
# 5. WHEEL BRAKE ENERGY  (brake-energy-sizing leaf)
# ===========================================================================
CP_CARBON = 1200.0
REVERSE_THRUST_CREDIT_DEFAULT = 0.0


def rto_energy_J(mtow_kg, v1_m_s):
    """Rejected-takeoff kinetic energy E = 0.5*mtow*v1^2, J (leaf)."""
    return 0.5 * mtow_kg * v1_m_s * v1_m_s


def landing_energy_J(mlw_kg, touchdown_speed_m_s):
    """Landing-stop kinetic energy E = 0.5*mlw*v_td^2, J (leaf)."""
    return 0.5 * mlw_kg * touchdown_speed_m_s * touchdown_speed_m_s


def per_brake_energy_J(total_energy_J, n_braked_wheels,
                       reverse_credit=REVERSE_THRUST_CREDIT_DEFAULT):
    """Energy per braked wheel after reverse-thrust credit (leaf formula)."""
    return total_energy_J * (1.0 - reverse_credit) / n_braked_wheels


def required_heat_sink_mass_kg(energy_per_brake_J, cp, delta_t_K):
    """Heat-sink mass per brake = E/(cp*delta_t) (leaf formula)."""
    return energy_per_brake_J / (cp * delta_t_K)


def temperature_rise_K(energy_per_brake_J, mass_kg, cp):
    """Adiabatic heat-sink rise = E/(mass*cp), K (leaf formula)."""
    return energy_per_brake_J / (mass_kg * cp)


def braking_distance_m(v_m_s, decel_g):
    """Braking distance v^2/(2*a) with a = decel_g * g0 (leaf formula)."""
    return v_m_s * v_m_s / (2.0 * decel_g * G0)


def brake_energy_analyze(mtow_kg, v1_m_s, mlw_kg, touchdown_speed_m_s,
                         n_braked_wheels, delta_t_allowable_K,
                         heat_sink_mass_available_kg, decel_g,
                         heat_sink_cp=CP_CARBON,
                         reverse_credit=REVERSE_THRUST_CREDIT_DEFAULT):
    """Wheel-brake sizing review (mirrors leaf analyze() results)."""
    e_rto = rto_energy_J(mtow_kg, v1_m_s)
    e_land = landing_energy_J(mlw_kg, touchdown_speed_m_s)
    per_rto = per_brake_energy_J(e_rto, n_braked_wheels, reverse_credit)
    per_land = per_brake_energy_J(e_land, n_braked_wheels, reverse_credit)
    if per_rto >= per_land:
        governing_case, per_brake_governing = "rto", per_rto
    else:
        governing_case, per_brake_governing = "landing", per_land
    required_mass = required_heat_sink_mass_kg(
        per_brake_governing, heat_sink_cp, delta_t_allowable_K)
    actual_rise = temperature_rise_K(
        per_brake_governing, heat_sink_mass_available_kg, heat_sink_cp)
    delta_t_margin = delta_t_allowable_K - actual_rise
    distance = braking_distance_m(v1_m_s, decel_g)
    verdict = ("brake-energy-pass"
               if delta_t_margin >= 0.0
               and required_mass <= heat_sink_mass_available_kg
               else "brake-energy-fail")
    return {"E_rto_J": e_rto, "E_land_J": e_land,
            "per_brake_rto_J": per_rto, "per_brake_landing_J": per_land,
            "governing_case": governing_case,
            "per_brake_governing_J": per_brake_governing,
            "required_heat_sink_mass_kg": required_mass,
            "heat_sink_mass_available_kg": heat_sink_mass_available_kg,
            "actual_temperature_rise_K": actual_rise,
            "delta_t_allowable_K": delta_t_allowable_K,
            "delta_t_margin_K": delta_t_margin,
            "braking_distance_m": distance, "verdict": verdict}


# ===========================================================================
# 6. CABIN OUTFLOW + RELIEF VALVES  (cabin-outflow-valve-sizing leaf)
# ===========================================================================
T_CABIN_DEFAULT = 288.0
DP_CLAMP_DEFAULT = 61363.0        # 8.9 psi differential clamp
CRITICAL_RATIO = (2.0 / (GAMMA_AIR + 1.0)) ** (GAMMA_AIR / (GAMMA_AIR - 1.0))
FLUX_FACTOR = (2.0 / (GAMMA_AIR + 1.0)) ** (
    (GAMMA_AIR + 1.0) / (2.0 * (GAMMA_AIR - 1.0)))


def choked_mass_flux(p_cab_pa, t_cabin_k=T_CABIN_DEFAULT):
    """Choked mass flux G = p*sqrt(gamma/(R T))*flux_factor (leaf)."""
    return (p_cab_pa * math.sqrt(GAMMA_AIR / (R_AIR * t_cabin_k))
            * FLUX_FACTOR)


def is_choked(p_cab_pa, p_amb_pa):
    """True when p_amb/p_cab < critical ratio (leaf formula)."""
    return (p_amb_pa / p_cab_pa) < CRITICAL_RATIO


def valve_area(m_dot_kg_s, p_cab_pa, t_cabin_k=T_CABIN_DEFAULT):
    """Effective area m2 + equivalent diameter m for choked flow (leaf)."""
    flux = choked_mass_flux(p_cab_pa, t_cabin_k)
    area_m2 = m_dot_kg_s / flux
    diameter_m = math.sqrt(4.0 * area_m2 / math.pi)
    return {"area_m2": area_m2, "diameter_m": diameter_m}


def outflow_valve_sizing(m_pack_kg_s, p_cab_pa, p_amb_pa,
                         max_valve_diameter_m, t_cabin_k=T_CABIN_DEFAULT):
    """Outflow valve effective area at the cruise pack inflow (leaf)."""
    area = valve_area(m_pack_kg_s, p_cab_pa, t_cabin_k)
    return {"choked": True,
            "mass_flux_kg_m2s": choked_mass_flux(p_cab_pa, t_cabin_k),
            "area_m2": area["area_m2"], "diameter_m": area["diameter_m"],
            "fit_verdict": ("PASS"
                            if area["diameter_m"] <= max_valve_diameter_m
                            else "FAIL")}


def relief_valve_sizing(m_pack_kg_s, p_amb_pa, dp_clamp_pa=DP_CLAMP_DEFAULT,
                        max_valve_diameter_m=None,
                        t_cabin_k=T_CABIN_DEFAULT):
    """Pressure-relief valve area at the differential clamp ceiling (leaf)."""
    p_cab_pa = p_amb_pa + dp_clamp_pa
    area = valve_area(m_pack_kg_s, p_cab_pa, t_cabin_k)
    return {"choked": True,
            "mass_flux_kg_m2s": choked_mass_flux(p_cab_pa, t_cabin_k),
            "area_m2": area["area_m2"], "diameter_m": area["diameter_m"],
            "fit_verdict": ("PASS"
                            if area["diameter_m"] <= max_valve_diameter_m
                            else "FAIL")}


# ===========================================================================
# 7. FUEL FEED  (fuel-feed-system-sizing leaf)
# ===========================================================================
LAMINAR_RE_LIMIT = 2300.0
BLASIUS_COEFF = 0.3164
K_LAMINAR = 64.0


def line_velocity(mass_flow_kg_s, density_kg_m3, diameter_m):
    """Feed line mean velocity (leaf formula)."""
    area_m2 = math.pi * diameter_m ** 2 / 4.0
    velocity_m_s = mass_flow_kg_s / (density_kg_m3 * area_m2)
    return {"velocity_m_s": velocity_m_s, "area_m2": area_m2}


def reynolds_number(velocity_m_s, diameter_m, density_kg_m3, viscosity_pa_s):
    """Re = V D rho / mu (leaf formula)."""
    return velocity_m_s * diameter_m * density_kg_m3 / viscosity_pa_s


def friction_factor(reynolds):
    """Darcy friction factor: 64/Re laminar, Blasius turbulent (leaf)."""
    if reynolds < LAMINAR_RE_LIMIT:
        return K_LAMINAR / reynolds
    return BLASIUS_COEFF * reynolds ** -0.25


def major_loss_pa(friction, length_m, diameter_m, density_kg_m3,
                  velocity_m_s):
    """Major friction loss f (L/D) rho V^2/2, Pa (leaf formula)."""
    return (friction * (length_m / diameter_m) * density_kg_m3
            * velocity_m_s ** 2 / 2.0)


def minor_loss_pa(loss_coefficient_k, density_kg_m3, velocity_m_s):
    """Minor loss K rho V^2/2, Pa (leaf formula)."""
    return loss_coefficient_k * density_kg_m3 * velocity_m_s ** 2 / 2.0


def static_head_pa(density_kg_m3, height_m):
    """Static head rho g h, Pa (leaf formula)."""
    return density_kg_m3 * G0 * height_m


def npsh_available(source_pressure_pa, static_head_pa, line_loss_pa,
                   vapor_pressure_pa, density_kg_m3):
    """NPSHa in metres of fuel column (leaf formula)."""
    numerator = (source_pressure_pa + static_head_pa - line_loss_pa
                 - vapor_pressure_pa)
    return numerator / (density_kg_m3 * G0)


def feed_verdict(npsh_available_m, npsh_required_m):
    """Feed PASS/FAIL from NPSHa vs NPSHr (leaf formula)."""
    margin_m = npsh_available_m - npsh_required_m
    verdict = "PASS" if margin_m >= 0.0 else "FAIL"
    return {"margin_m": margin_m, "verdict": verdict}


def boost_pump_power(flow_m3_s, pressure_rise_pa, efficiency):
    """Boost pump hydraulic power P = Q dp / eta, W (leaf formula)."""
    power_w = flow_m3_s * pressure_rise_pa / efficiency
    return {"power_w": power_w, "pressure_rise_pa": pressure_rise_pa}


def fuel_feed_summary(mass_flow_kg_s, density_kg_m3, diameter_m, length_m,
                      viscosity_pa_s, loss_coefficient_k, tank_height_m,
                      source_pressure_pa, vapor_pressure_pa,
                      npsh_required_m, boost_pressure_rise_pa,
                      boost_efficiency):
    """Full fuel feed sizing dict (mirrors leaf feed_system_summary)."""
    vel = line_velocity(mass_flow_kg_s, density_kg_m3, diameter_m)
    velocity_m_s = vel["velocity_m_s"]
    reynolds = reynolds_number(velocity_m_s, diameter_m, density_kg_m3,
                               viscosity_pa_s)
    friction = friction_factor(reynolds)
    major = major_loss_pa(friction, length_m, diameter_m, density_kg_m3,
                          velocity_m_s)
    minor = minor_loss_pa(loss_coefficient_k, density_kg_m3, velocity_m_s)
    total_line_loss_pa = major + minor
    static = static_head_pa(density_kg_m3, tank_height_m)
    npsh = npsh_available(source_pressure_pa, static, total_line_loss_pa,
                          vapor_pressure_pa, density_kg_m3)
    verdict = feed_verdict(npsh, npsh_required_m)
    flow_m3_s = mass_flow_kg_s / density_kg_m3
    if boost_pressure_rise_pa > 0:
        boost = boost_pump_power(flow_m3_s, boost_pressure_rise_pa,
                                 boost_efficiency)
        boost_power_w = boost["power_w"]
        npsh_with_boost_m = npsh_available(
            source_pressure_pa + boost_pressure_rise_pa, static,
            total_line_loss_pa, vapor_pressure_pa, density_kg_m3)
    else:
        boost_power_w = 0.0
        npsh_with_boost_m = npsh
    return {"velocity_m_s": velocity_m_s, "area_m2": vel["area_m2"],
            "reynolds": reynolds, "friction_factor": friction,
            "major_loss_pa": major, "minor_loss_pa": minor,
            "total_line_loss_pa": total_line_loss_pa,
            "static_head_pa": static, "npsh_available_m": npsh,
            "npsh_required_m": npsh_required_m,
            "margin_m": verdict["margin_m"], "verdict": verdict["verdict"],
            "npsh_with_boost_m": npsh_with_boost_m,
            "boost_pressure_rise_pa": boost_pressure_rise_pa,
            "boost_power_w": boost_power_w}


# ===========================================================================
# 8. FUEL JETTISON  (fuel-jettison-sizing leaf, FAR 25.1001 context)
# ===========================================================================
JETTISON_LIMIT_S = 900.0
DESIGN_MARGIN_DEFAULT = 1.1


def dumpable_fuel_mass(mtow_kg, mlw_kg):
    """Fuel (kg) that must be dumpable to reach MLW = MTOW - MLW."""
    return mtow_kg - mlw_kg


def required_jettison_rate(mtow_kg, mlw_kg, limit_s=JETTISON_LIMIT_S):
    """Required average jettison rate over the 15-minute limit (kg/s)."""
    return (mtow_kg - mlw_kg) / limit_s


def design_jettison_rate(required_rate_kg_s, margin=DESIGN_MARGIN_DEFAULT):
    """Design rate with the design margin (leaf formula)."""
    return required_rate_kg_s * margin


def per_mast_flow(design_rate_kg_s, n_masts):
    """Design flow per dump mast (leaf formula)."""
    return design_rate_kg_s / n_masts


def time_to_landing_weight(dumpable_mass_kg, design_rate_kg_s):
    """{time_s, verdict} at the design rate vs the 900 s limit."""
    time_s = dumpable_mass_kg / design_rate_kg_s
    return {"time_s": time_s,
            "verdict": "PASS" if time_s <= JETTISON_LIMIT_S else "FAIL"}


def jettison_summary(mtow_kg, mlw_kg, n_masts, margin=DESIGN_MARGIN_DEFAULT):
    """Complete jettison sizing dict (mirrors leaf jettison_summary)."""
    dumpable = dumpable_fuel_mass(mtow_kg, mlw_kg)
    required = required_jettison_rate(mtow_kg, mlw_kg)
    design = design_jettison_rate(required, margin)
    per_mast = per_mast_flow(design, n_masts)
    check = time_to_landing_weight(dumpable, design)
    return {"mtow_kg": mtow_kg, "mlw_kg": mlw_kg,
            "dumpable_mass_kg": dumpable, "required_rate_kg_s": required,
            "design_rate_kg_s": design, "margin": margin,
            "n_masts": n_masts, "per_mast_flow_kg_s": per_mast,
            "limit_s": JETTISON_LIMIT_S, "time_s": check["time_s"],
            "verdict": check["verdict"]}


# ===========================================================================
# 9. FUEL TANK INERTING  (fuel-tank-inerting-sizing leaf)
# ===========================================================================
C0_AIR = 0.21
C_NEA_DEFAULT = 0.05


def nea_flow_required(ullage_m3, target_o2_fraction, time_s,
                      c_nea=C_NEA_DEFAULT, c0=C0_AIR):
    """Required NEA flow Q = (V/t) ln((c0-c_nea)/(tgt-c_nea)) (leaf)."""
    flow = (ullage_m3 / time_s) * math.log(
        (c0 - c_nea) / (target_o2_fraction - c_nea))
    return {"flow_m3_s": flow, "flow_scfm": flow * SCFM_PER_M3S}


def ullage_o2_fraction(ullage_m3, nea_flow_m3_s, time_s, c_nea=C_NEA_DEFAULT,
                       c0=C0_AIR):
    """Ullage O2 after time_s at fixed flow (exponential washout, leaf)."""
    if nea_flow_m3_s == 0.0 or time_s == 0.0:
        return c0
    return c_nea + (c0 - c_nea) * math.exp(-nea_flow_m3_s * time_s / ullage_m3)


def washout_time(ullage_m3, nea_flow_m3_s, target_o2_fraction,
                 c_nea=C_NEA_DEFAULT, c0=C0_AIR):
    """Time (s) to wash the ullage to the target fraction (leaf formula)."""
    return (ullage_m3 / nea_flow_m3_s) * math.log(
        (c0 - c_nea) / (target_o2_fraction - c_nea))


def inerting_summary(ullage_m3, target_o2_fraction, time_s,
                     max_nea_capacity_m3_s, c_nea=C_NEA_DEFAULT,
                     c0=C0_AIR):
    """Full inerting sizing dict (mirrors leaf inerting_summary)."""
    flow = nea_flow_required(ullage_m3, target_o2_fraction, time_s,
                             c_nea, c0)
    o2_at_time = ullage_o2_fraction(ullage_m3, flow["flow_m3_s"], time_s,
                                    c_nea, c0)
    return {"flow_m3_s": flow["flow_m3_s"],
            "flow_scfm": flow["flow_scfm"], "o2_at_time": o2_at_time,
            "capacity_verdict":
                "PASS" if flow["flow_m3_s"] <= max_nea_capacity_m3_s
                else "FAIL"}


# ===========================================================================
# 10. HYDRAULIC ACTUATION  (hydraulic-actuator-sizing leaf)
# ===========================================================================
PRESSURE_MARGIN = 1.10
MECHANICAL_EFFICIENCY = 0.90
BUCKLING_FACTOR_OF_SAFETY = 2.0
END_FIXITY_K = 1.0
MODULUS_ROD = 205e9
ROD_DENSITY = 7850.0
STEEL_YIELD = 1100e6
PREFERRED_BORES_MM = (25.0, 32.0, 40.0, 50.0, 63.0, 80.0, 100.0, 125.0)
PREFERRED_RODS_MM = (12.0, 16.0, 20.0, 25.0, 32.0, 40.0, 50.0, 63.0)


def piston_area(load_N, pressure_Pa):
    """Required piston area = load*margin/(pressure*efficiency) (leaf)."""
    return load_N * PRESSURE_MARGIN / (pressure_Pa * MECHANICAL_EFFICIENCY)


def bore_diameter(area_m2):
    """Bore diameter m from piston area: sqrt(4A/pi)."""
    return math.sqrt(4.0 * area_m2 / math.pi)


def annulus_area(bore_m, rod_m):
    """Rod-side annulus = pi/4 (bore^2 - rod^2), m2 (leaf formula)."""
    return math.pi / 4.0 * (bore_m ** 2 - rod_m ** 2)


def retract_capability(annulus_area_m2, pressure_Pa):
    """Retract-direction force from annulus area (leaf formula)."""
    return (annulus_area_m2 * pressure_Pa * MECHANICAL_EFFICIENCY
            / PRESSURE_MARGIN)


def rod_buckling_diameter(load_N, rod_length_m):
    """Min rod diameter m for Euler buckling at full extension (leaf)."""
    inertia = (load_N * BUCKLING_FACTOR_OF_SAFETY
               * (END_FIXITY_K * rod_length_m) ** 2
               / (math.pi ** 2 * MODULUS_ROD))
    return (64.0 * inertia / math.pi) ** 0.25


def select_preferred(value_m, preferred_mm):
    """Nearest preferred diameter mm at or above value_m (leaf)."""
    value_mm = value_m * 1000.0
    for preferred in preferred_mm:
        if preferred >= value_mm:
            return float(preferred)
    raise ValueError("required diameter exceeds the largest preferred size")


def actuator_mass(bore_m, rod_m, stroke_m):
    """Actuator mass estimate kg (leaf formula, 0.6 barrel fill factor)."""
    rod_volume = math.pi / 4.0 * rod_m ** 2 * stroke_m
    barrel_volume = math.pi / 4.0 * (bore_m ** 2 - rod_m ** 2) * stroke_m
    return (rod_volume + 0.6 * barrel_volume) * ROD_DENSITY


def actuator_review(load_N, pressure_Pa, rod_length_m, stroke_m):
    """Full linear actuator sizing review (mirrors leaf actuator_review)."""
    area = piston_area(load_N, pressure_Pa)
    bore_req = bore_diameter(area)
    bore_pref_mm = select_preferred(bore_req, PREFERRED_BORES_MM)
    buckling_req = rod_buckling_diameter(load_N, rod_length_m)
    rod_pref_mm = select_preferred(buckling_req, PREFERRED_RODS_MM)
    bore_pref_m = bore_pref_mm / 1000.0
    rod_pref_m = rod_pref_mm / 1000.0
    annulus = annulus_area(bore_pref_m, rod_pref_m)
    retract = retract_capability(annulus, pressure_Pa)
    stress = load_N / (math.pi / 4.0 * rod_pref_m ** 2)
    inertia_act = math.pi / 64.0 * rod_pref_m ** 4
    crit_load = (math.pi ** 2 * MODULUS_ROD * inertia_act
                 / (END_FIXITY_K * rod_length_m) ** 2)
    margin = crit_load / load_N
    mass = actuator_mass(bore_pref_m, rod_pref_m, stroke_m)
    verdict = "pass" if (retract >= load_N and stress <= STEEL_YIELD) else "fail"
    return {"piston_area": area, "bore_mm": bore_req * 1000.0,
            "annulus_area": annulus, "rod_buckling_mm": buckling_req * 1000.0,
            "bore_pref_mm": bore_pref_mm, "rod_pref_mm": rod_pref_mm,
            "retract_capability_N": retract, "rod_stress_Pa": stress,
            "buckling_margin": margin, "mass_kg": mass, "verdict": verdict}


# ===========================================================================
# 11. LANDING GEAR LAYOUT  (landing-gear-layout leaf)
# ===========================================================================
def tipback_angle(h_cg, x_mg, x_cg_aft):
    """Tipback angle deg about the main gear contact at the aft CG (leaf)."""
    margin = x_mg - x_cg_aft
    return math.degrees(math.atan(margin / h_cg))


def tail_strike_clearance_angle(h_tail_contact, x_tail, x_mg):
    """Tail strike clearance angle deg at rotation (leaf formula)."""
    arm = x_tail - x_mg
    return math.degrees(math.atan(h_tail_contact / arm))


def lateral_turnover_angle(h_cg, track):
    """Simplified lateral turnover angle deg, main gear pair (leaf)."""
    return math.degrees(math.atan(2.0 * h_cg / track))


def lateral_turnover_tricycle_angle(h_cg, x_cg, x_mg, x_ng, track):
    """Tricycle diagonal turnover angle deg (leaf formula)."""
    wheelbase = x_mg - x_ng
    half_track = track / 2.0
    d_perp = ((x_cg - x_ng) * half_track
              / math.sqrt(wheelbase * wheelbase + half_track * half_track))
    return math.degrees(math.atan(d_perp / h_cg))


def nose_gear_static_load_fraction(x_cg, x_mg, x_ng):
    """Nose gear static load fraction at a CG station (leaf formula)."""
    return (x_mg - x_cg) / (x_mg - x_ng)


# ===========================================================================
# 12. RAM AIR TURBINE  (ram-air-turbine-sizing leaf)
# ===========================================================================
CP_RAT_DEFAULT = 0.10
BETZ_LIMIT = 16.0 / 27.0


def rat_swept_area(p_req_w, v_m_s, rho=RHO_SL, cp=CP_RAT_DEFAULT):
    """Required rotor swept area m2 = p/(0.5 rho V^3 cp) (leaf)."""
    return p_req_w / (0.5 * rho * v_m_s ** 3 * cp)


def disk_diameter(area_m2):
    """Rotor disk diameter m from swept area: sqrt(4A/pi)."""
    return math.sqrt(4.0 * area_m2 / math.pi)


def rat_available_power(area_m2, v_m_s, rho=RHO_SL, cp=CP_RAT_DEFAULT):
    """Available wind power W through the swept area (leaf formula)."""
    return 0.5 * rho * v_m_s ** 3 * area_m2 * cp


def rat_sizing_summary(p_req_w, v_m_s, max_stowage_diameter_m,
                       rho=RHO_SL, cp=CP_RAT_DEFAULT):
    """Full RAT sizing dict (mirrors leaf rat_sizing_summary)."""
    area_m2 = rat_swept_area(p_req_w, v_m_s, rho, cp)
    diameter_m = disk_diameter(area_m2)
    available_w = rat_available_power(area_m2, v_m_s, rho, cp)
    return {"area_m2": area_m2, "diameter_m": diameter_m,
            "available_w": available_w,
            "margin_w": available_w - p_req_w,
            "stowage_verdict":
                "PASS" if diameter_m <= max_stowage_diameter_m else "FAIL"}


# ===========================================================================
# 13. TIRES  (tire-sizing leaf)
# ===========================================================================
LB_PER_KG = 2.2046226218487757
MM_PER_IN = 25.4


def kg_to_lb(mass_kg):
    """kg to pounds."""
    return mass_kg * LB_PER_KG


def static_load_per_tire(mtow_kg, gear_fraction, n_tires):
    """Static load per tire (kg) on one gear (leaf formula)."""
    return mtow_kg * gear_fraction / n_tires


def tire_diameter_inches(load_lb, coeff=1.63, exponent=0.315):
    """Estimated tire diameter in inches (class-I power law fit, leaf)."""
    return coeff * load_lb ** exponent


def tire_width_inches(load_lb, coeff=0.40, exponent=0.36):
    """Estimated tire width in inches (class-I power law fit, leaf)."""
    return coeff * load_lb ** exponent


def footprint_area_sqin(load_lb, pressure_psi):
    """Footprint contact area sqin = load/pressure (leaf formula)."""
    return load_lb / pressure_psi


def rolling_radius_inches(diameter_in):
    """Rolling radius = diameter/2 (leaf formula)."""
    return diameter_in / 2.0


def required_number_of_tires(total_gear_load_lb, max_load_per_tire_lb):
    """Required tire count = ceil(total/max per tire) (leaf formula)."""
    return int(math.ceil(total_gear_load_lb / max_load_per_tire_lb))


# ===========================================================================
# 14. WINDOW APERTURES  (window-aperture-sizing leaf)
# ===========================================================================
P0_PA = 101325.0
T0_K = 288.15
LAPSE_K_PER_M = 0.0065
TROPOPAUSE_M = 11000.0
TROPOPAUSE_TEMP_K = 216.65
R_GAS = 287.05
TROPOSPHERIC_EXPONENT = G0 / (R_GAS * LAPSE_K_PER_M)
CLAMPED_PLATE_STRESS_COEF = 0.75
CERT_PRESSURE_FACTOR = 1.33


def isa_pressure_pa(altitude_m):
    """ISA pressure Pa (troposphere + isothermal stratosphere, leaf)."""
    if altitude_m <= TROPOPAUSE_M:
        ratio = 1.0 - LAPSE_K_PER_M * altitude_m / T0_K
        return P0_PA * ratio ** TROPOSPHERIC_EXPONENT
    p_tropo = (P0_PA * (1.0 - LAPSE_K_PER_M * TROPOPAUSE_M / T0_K)
               ** TROPOSPHERIC_EXPONENT)
    exponent = (-G0 * (altitude_m - TROPOPAUSE_M)
                / (R_GAS * TROPOPAUSE_TEMP_K))
    return p_tropo * math.exp(exponent)


def design_pressure_differential(cabin_altitude_m, flight_altitude_m,
                                 certification_factor=CERT_PRESSURE_FACTOR):
    """Design cabin dp dict (leaf design_pressure_differential)."""
    cabin_pressure_pa = isa_pressure_pa(cabin_altitude_m)
    ambient_pressure_pa = isa_pressure_pa(flight_altitude_m)
    limit_differential_pa = cabin_pressure_pa - ambient_pressure_pa
    return {"cabin_pressure_pa": cabin_pressure_pa,
            "ambient_pressure_pa": ambient_pressure_pa,
            "limit_differential_pa": limit_differential_pa,
            "design_differential_pa":
                limit_differential_pa * certification_factor}


def plate_max_stress_clamped_circular(pressure_pa, radius_m, thickness_m):
    """sigma_max = 0.75 p (r/t)^2, clamped edge (Roark closed form, leaf)."""
    ratio = radius_m / thickness_m
    return CLAMPED_PLATE_STRESS_COEF * pressure_pa * ratio * ratio


def pane_thickness(pressure_pa, radius_m, allowable_stress_pa):
    """Required pane thickness m: t = r sqrt(0.75 p/sigma_allow) (leaf)."""
    return radius_m * math.sqrt(
        CLAMPED_PLATE_STRESS_COEF * pressure_pa / allowable_stress_pa)


def pane_margin(pressure_pa, radius_m, thickness_m, allowable_stress_pa):
    """Margin = allowable/computed_stress - 1 (leaf formula)."""
    stress = plate_max_stress_clamped_circular(pressure_pa, radius_m,
                                               thickness_m)
    return allowable_stress_pa / stress - 1.0


def window_weight(radius_m, thickness_m, material_density_kg_m3, n_windows):
    """Pane weight rollup {per_window_kg, total_kg} (leaf formula)."""
    per_window_kg = (material_density_kg_m3 * math.pi * radius_m
                     * radius_m * thickness_m)
    return {"per_window_kg": per_window_kg,
            "total_kg": per_window_kg * n_windows}


# ===========================================================================
# Project facts + sizing entry point
# ===========================================================================
@dataclass
class AircraftSystemsItem:
    """Project facts the role needs to build the sizing report."""
    aircraft_name: str = "Example 180-seat single-aisle transport"
    basis: str = "FAR/CS-25"
    # electrical
    consumers: dict = field(default_factory=dict)
    diversity_factor: float = 0.85
    essential_names: list = field(default_factory=list)
    n_generators: int = 2
    generator_kva: float = 90.0
    # ACM pack
    pack_bleed_p1_pa: float = 240000.0
    pack_bleed_t1_k: float = 340.0
    pack_pr_c: float = 3.0
    pack_eta_c: float = 0.78
    pack_eta_t: float = 0.85
    pack_sink_t_k: float = 320.0
    pack_cabin_p_pa: float = 101325.0
    pack_flow_kg_s: float = 0.9
    pack_target_t_k: float = 288.0
    pack_heat_load_w: float = 0.0      # computed in build when 0
    # avionics bay cooling
    lru_dissipations_w: list = field(default_factory=list)
    lru_case_limits_c: list = field(default_factory=list)
    bay_supply_temp_c: float = 20.0
    bay_exhaust_limit_c: float = 55.0
    # oxygen
    n_passengers: int = 180
    n_crew: int = 6
    oxygen_service_pressure_psi: float = 1850.0
    # brakes / masses
    mtow_kg: float = 79000.0
    mlw_kg: float = 66000.0
    v1_m_s: float = 77.0
    touchdown_speed_m_s: float = 70.0
    n_braked_wheels: int = 4
    delta_t_allowable_k: float = 550.0
    heat_sink_mass_available_kg: float = 120.0
    decel_g: float = 0.45
    # outflow / relief valves
    outflow_m_pack_kg_s: float = 1.2
    outflow_p_cab_pa: float = 75622.0     # ISA cabin 8,000 ft
    outflow_p_amb_pa: float = 19677.0     # ISA 39,000 ft
    outflow_max_valve_diameter_m: float = 0.25
    relief_p_amb_pa: float = 11597.0      # ISA 50,000 ft
    # fuel feed
    feed_mass_flow_kg_s: float = 0.55
    fuel_density_kg_m3: float = 780.0
    feed_diameter_m: float = 0.05
    feed_length_m: float = 4.0
    fuel_viscosity_pa_s: float = 0.0016
    feed_loss_coefficient_k: float = 2.5
    feed_tank_height_m: float = 0.5
    feed_source_pressure_pa: float = 34000.0
    fuel_vapor_pressure_pa: float = 14000.0
    feed_npsh_required_m: float = 1.5
    feed_boost_rise_pa: float = 69000.0   # 10 psi boost pump
    feed_boost_efficiency: float = 0.7
    # jettison
    n_masts: int = 2
    # inerting
    inerting_ullage_m3: float = 3.0
    inerting_target_o2: float = 0.12
    inerting_time_s: float = 240.0
    inerting_max_flow_m3_s: float = 0.05
    # hydraulic actuation
    actuator_load_N: float = 40000.0
    system_pressure_pa: float = 3000.0 * PSI_TO_PA
    actuator_rod_length_m: float = 0.55
    actuator_stroke_m: float = 0.18
    # landing gear layout
    h_cg_m: float = 1.8
    x_mg_m: float = 15.0
    x_cg_aft_m: float = 14.3
    x_cg_fwd_m: float = 12.9
    x_ng_m: float = 4.2
    x_tail_contact_m: float = 19.5
    h_tail_contact_m: float = 1.1
    track_m: float = 6.4
    # RAT
    rat_p_req_w: float = 5000.0
    rat_v_m_s: float = 130.0
    rat_max_stowage_diameter_m: float = 0.9
    # tires
    main_gear_fraction: float = 0.90
    n_tires_per_main_gear: int = 2
    tire_pressure_psi: float = 200.0
    # windows
    window_cabin_altitude_m: float = 2438.0     # 8,000 ft
    window_flight_altitude_m: float = 11887.0   # 39,000 ft
    window_radius_m: float = 0.145
    window_allowable_stress_pa: float = 40.0e6
    window_density_kg_m3: float = 2580.0
    n_windows: int = 64


def _default_consumers() -> dict:
    """Example 180-seat transport electrical consumers {name: (kVA, duty)}.

    Duty cycles are the fraction of flight time each consumer draws its
    rated power (leaf bookkeeping convention). Values are representative
    transport-system magnitudes used to exercise the sizing math.
    """
    return {
        "flight control actuation": (18.0, 0.6),
        "avionics + instruments": (6.0, 1.0),
        "ECS packs + fans": (14.0, 0.8),
        "anti-ice (wing + cowl)": (22.0, 0.2),
        "lighting": (4.0, 0.8),
        "galley loads": (30.0, 0.3),
        "cargo systems": (3.0, 0.4),
        "fuel pumps": (2.5, 1.0),
        "cabin entertainment": (8.0, 0.6),
        "utility + maintenance": (2.5, 0.5),
    }


DEFAULT_ESSENTIAL = ["flight control actuation", "avionics + instruments",
                     "fuel pumps"]

DEFAULT_LRUS = {"FMC": 150.0, "ADIRU": 120.0, "VHF/COM": 80.0,
                "TCAS": 70.0, "EICAS": 60.0, "radio nav": 90.0,
                "data concentrator": 110.0, "flight recorder": 40.0}
DEFAULT_LRU_LIMITS_C = [70.0, 70.0, 65.0, 65.0, 60.0, 65.0, 70.0, 70.0]


def example_item() -> AircraftSystemsItem:
    """Reference project facts for the worked example report."""
    item = AircraftSystemsItem()
    item.consumers = _default_consumers()
    item.essential_names = list(DEFAULT_ESSENTIAL)
    item.lru_dissipations_w = list(DEFAULT_LRUS.values())
    item.lru_case_limits_c = list(DEFAULT_LRU_LIMITS_C)
    return item


def _sys(model, name, d):
    model["systems"][name] = d


def _fmt_verdict(v):
    return str(v).upper() if isinstance(v, str) else str(v)


def build_report(item: AircraftSystemsItem) -> dict:
    """Build the complete Aircraft System Sizing Report content model."""
    # -- 1. electrical ------------------------------------------------------
    cont = continuous_load(item.consumers)
    continuous_kva = cont["continuous_kva"]
    peak_kva = diversity_peak(continuous_kva, item.diversity_factor)
    ess = essential_load(item.consumers, item.essential_names)
    gen = generator_out_margin(item.n_generators, item.generator_kva,
                               ess["essential_kva"])
    installed_kva = item.n_generators * item.generator_kva
    electrical = {
        "consumers": {k: v[0] for k, v in item.consumers.items()},
        "duty": {k: v[1] for k, v in item.consumers.items()},
        "continuous_kva": continuous_kva,
        "coincident_peak_kva": peak_kva,
        "diversity_factor": item.diversity_factor,
        "essential_kva": ess["essential_kva"],
        "essential_consumers": ess["essential_consumers"],
        "n_generators": item.n_generators,
        "generator_kva": item.generator_kva,
        "installed_kva": installed_kva,
        "remaining_kva": gen["remaining_kva"],
        "generator_out_margin": gen["margin"],
        "generator_out_verdict": gen["verdict"],
        "load_fraction": load_fraction(continuous_kva, installed_kva),
    }
    # -- 2. ACM pack (balanced bootstrap chain) -----------------------------
    c = compressor_exit(item.pack_bleed_p1_pa, item.pack_bleed_t1_k,
                        item.pack_pr_c, item.pack_eta_c)
    t2 = c["t2"]
    p2 = c["p2"]
    t3_req = t3_required_for_balance(item.pack_bleed_t1_k, t2,
                                     item.pack_eta_t, p2,
                                     item.pack_cabin_p_pa)
    eff = hx_effectiveness_for_balance(t2, item.pack_sink_t_k, t3_req)
    t3 = heat_exchanger_exit(t2, eff, item.pack_sink_t_k)
    t = turbine_exit(p2, t3, p2 / item.pack_cabin_p_pa, item.pack_eta_t,
                     item.pack_cabin_p_pa)
    wc = compressor_power(item.pack_flow_kg_s, item.pack_bleed_t1_k, t2)
    wt = turbine_power(item.pack_flow_kg_s, t3, t["t4"])
    bal = shaft_balance(wc, wt)
    cool_cap = cooling_capacity(item.pack_flow_kg_s, t["t4"],
                                item.pack_target_t_k)
    # the cabin cooling load at the pack design point equals the delivered
    # cooling of the balanced flow; required bleed flow then returns the
    # design flow (round-trip consistency of the closed pack chain)
    heat_load = item.pack_heat_load_w if item.pack_heat_load_w else cool_cap
    bleed_req = required_bleed_flow(heat_load, t["t4"], item.pack_target_t_k)
    acm = {
        "t1_k": item.pack_bleed_t1_k, "p1_pa": item.pack_bleed_p1_pa,
        "compressor_pr": item.pack_pr_c, "compressor_eta": item.pack_eta_c,
        "t2_k": t2, "p2_pa": p2,
        "hx_effectiveness_for_balance": eff,
        "t3_balance_k": t3_req, "t3_k": t3,
        "turbine_eta": item.pack_eta_t, "t4_k": t["t4"],
        "compressor_power_w": wc, "turbine_power_w": wt,
        "shaft_balanced": bal["balanced"], "shaft_deficit_w": bal["deficit_w"],
        "cooling_capacity_w": cool_cap, "heat_load_w": heat_load,
        "required_bleed_flow_kg_s": bleed_req,
    }
    # -- 3. avionics bay cooling -------------------------------------------
    bay = bay_cooling_summary(item.lru_dissipations_w, item.bay_supply_temp_c,
                              item.bay_exhaust_limit_c,
                              item.lru_case_limits_c)
    avionics = {
        "bay_heat_load_w": bay["total_w"],
        "supply_temp_c": item.bay_supply_temp_c,
        "exhaust_limit_c": item.bay_exhaust_limit_c,
        "mass_flow_kg_s": bay["mass_flow_kg_s"],
        "flow_m3_s": bay["flow_m3_s"],
        "flow_cfm": bay["flow_cfm"],
        "case_temps_c": {str(k): round(v, 1)
                         for k, v in bay["case_temps_c"].items()},
        "case_verdicts": {str(k): v for k, v in bay["case_verdicts"].items()},
        "bay_verdict": bay["bay_verdict"],
    }
    # -- 4. oxygen ----------------------------------------------------------
    oxy = oxygen_summary(item.n_passengers, item.n_crew,
                         item.oxygen_service_pressure_psi)
    oxygen = {
        "n_passengers": item.n_passengers, "n_crew": item.n_crew,
        "passenger_demand_sl": oxy["passenger_demand_sl"],
        "passenger_mass_kg": oxy["passenger_mass_kg"],
        "generator_units": oxy["generator_units"],
        "crew_demand_sl": oxy["crew_demand_sl"],
        "crew_mass_kg": oxy["crew_mass_kg"],
        "service_pressure_psi": item.oxygen_service_pressure_psi,
        "bottle_volume_l": oxy["bottle_volume_l"],
        "bottle_volume_m3": oxy["bottle_volume_m3"],
        "total_mass_kg": oxy["total_mass_kg"],
    }
    # -- 5. brakes ----------------------------------------------------------
    brake = brake_energy_analyze(
        item.mtow_kg, item.v1_m_s, item.mlw_kg, item.touchdown_speed_m_s,
        item.n_braked_wheels, item.delta_t_allowable_k,
        item.heat_sink_mass_available_kg, item.decel_g)
    brake["n_braked_wheels"] = item.n_braked_wheels
    brake["decel_g"] = item.decel_g
    # -- 6. outflow + relief valves ----------------------------------------
    ov = outflow_valve_sizing(item.outflow_m_pack_kg_s,
                              item.outflow_p_cab_pa, item.outflow_p_amb_pa,
                              item.outflow_max_valve_diameter_m)
    rv = relief_valve_sizing(item.outflow_m_pack_kg_s,
                             item.relief_p_amb_pa,
                             max_valve_diameter_m=item.outflow_max_valve_diameter_m)
    valves = {
        "pack_flow_kg_s": item.outflow_m_pack_kg_s,
        "cabin_pressure_pa": item.outflow_p_cab_pa,
        "ambient_39000ft_pa": item.outflow_p_amb_pa,
        "outflow_area_m2": ov["area_m2"], "outflow_diameter_m": ov["diameter_m"],
        "outflow_mass_flux_kg_m2s": ov["mass_flux_kg_m2s"],
        "outflow_fit_verdict": ov["fit_verdict"],
        "relief_ambient_pa": item.relief_p_amb_pa,
        "relief_area_m2": rv["area_m2"], "relief_diameter_m": rv["diameter_m"],
        "relief_fit_verdict": rv["fit_verdict"],
    }
    # -- 7. fuel feed -------------------------------------------------------
    feed = fuel_feed_summary(
        item.feed_mass_flow_kg_s, item.fuel_density_kg_m3,
        item.feed_diameter_m, item.feed_length_m, item.fuel_viscosity_pa_s,
        item.feed_loss_coefficient_k, item.feed_tank_height_m,
        item.feed_source_pressure_pa, item.fuel_vapor_pressure_pa,
        item.feed_npsh_required_m, item.feed_boost_rise_pa,
        item.feed_boost_efficiency)
    # -- 8. jettison --------------------------------------------------------
    jet = jettison_summary(item.mtow_kg, item.mlw_kg, item.n_masts)
    # -- 9. inerting --------------------------------------------------------
    inert = inerting_summary(item.inerting_ullage_m3, item.inerting_target_o2,
                             item.inerting_time_s, item.inerting_max_flow_m3_s)
    inert["ullage_m3"] = item.inerting_ullage_m3
    inert["target_o2_fraction"] = item.inerting_target_o2
    inert["time_s"] = item.inerting_time_s
    # -- 10. hydraulic actuation -------------------------------------------
    act = actuator_review(item.actuator_load_N, item.system_pressure_pa,
                          item.actuator_rod_length_m, item.actuator_stroke_m)
    act["load_N"] = item.actuator_load_N
    act["system_pressure_psi"] = item.system_pressure_pa / PSI_TO_PA
    act["rod_length_m"] = item.actuator_rod_length_m
    act["stroke_m"] = item.actuator_stroke_m
    # -- 11. landing gear layout -------------------------------------------
    nose_fwd = nose_gear_static_load_fraction(item.x_cg_fwd_m, item.x_mg_m,
                                              item.x_ng_m)
    nose_aft = nose_gear_static_load_fraction(item.x_cg_aft_m, item.x_mg_m,
                                              item.x_ng_m)
    gear = {
        "tipback_angle_deg": tipback_angle(item.h_cg_m, item.x_mg_m,
                                           item.x_cg_aft_m),
        "tail_strike_clearance_deg": tail_strike_clearance_angle(
            item.h_tail_contact_m, item.x_tail_contact_m, item.x_mg_m),
        "lateral_turnover_deg": lateral_turnover_angle(item.h_cg_m,
                                                       item.track_m),
        "tricycle_turnover_aft_deg": lateral_turnover_tricycle_angle(
            item.h_cg_m, item.x_cg_aft_m, item.x_mg_m, item.x_ng_m,
            item.track_m),
        "tricycle_turnover_fwd_deg": lateral_turnover_tricycle_angle(
            item.h_cg_m, item.x_cg_fwd_m, item.x_mg_m, item.x_ng_m,
            item.track_m),
        "nose_load_fraction_fwd": nose_fwd,
        "nose_load_fraction_aft": nose_aft,
        "nose_fraction_verdict": (
            "PASS" if 0.05 <= nose_fwd <= 0.20 and 0.05 <= nose_aft <= 0.20
            else "FAIL"),
    }
    # -- 12. RAT ------------------------------------------------------------
    rat = rat_sizing_summary(item.rat_p_req_w, item.rat_v_m_s,
                             item.rat_max_stowage_diameter_m)
    rat["p_req_w"] = item.rat_p_req_w
    rat["v_m_s"] = item.rat_v_m_s
    # -- 13. tires ----------------------------------------------------------
    main_load_kg = item.mtow_kg * item.main_gear_fraction / 2.0
    load_per_tire_kg = static_load_per_tire(item.mtow_kg,
                                            item.main_gear_fraction,
                                            item.n_tires_per_main_gear * 2)
    load_per_tire_lb = kg_to_lb(load_per_tire_kg)
    d_in = tire_diameter_inches(load_per_tire_lb)
    w_in = tire_width_inches(load_per_tire_lb)
    required_main_tires = required_number_of_tires(
        kg_to_lb(main_load_kg), kg_to_lb(load_per_tire_kg))
    tires = {
        "main_gear_fraction": item.main_gear_fraction,
        "load_per_tire_kg": load_per_tire_kg,
        "load_per_tire_lb": load_per_tire_lb,
        "diameter_in": d_in, "width_in": w_in,
        "diameter_mm": d_in * MM_PER_IN, "width_mm": w_in * MM_PER_IN,
        "rolling_radius_in": rolling_radius_inches(d_in),
        "footprint_sqin": footprint_area_sqin(load_per_tire_lb,
                                              item.tire_pressure_psi),
        "tire_pressure_psi": item.tire_pressure_psi,
        "required_tires_main_gear": required_main_tires,
        "installed_tires_per_main_strut": item.n_tires_per_main_gear,
        "tire_verdict": ("PASS"
                         if required_main_tires <= item.n_tires_per_main_gear
                         else "FAIL"),
    }
    # -- 14. window apertures ----------------------------------------------
    wdp = design_pressure_differential(item.window_cabin_altitude_m,
                                       item.window_flight_altitude_m)
    p_design = wdp["design_differential_pa"]
    t_pane = pane_thickness(p_design, item.window_radius_m,
                            item.window_allowable_stress_pa)
    # installed pane: next standard 0.5 mm step at or above the required
    # thickness (never undersize the requirement)
    t_installed_mm = math.ceil(t_pane * 1000.0 / 0.5) * 0.5
    t_installed = t_installed_mm / 1000.0
    margin = pane_margin(p_design, item.window_radius_m, t_installed,
                         item.window_allowable_stress_pa)
    wt = window_weight(item.window_radius_m, t_installed,
                       item.window_density_kg_m3, item.n_windows)
    windows = {
        "cabin_altitude_m": item.window_cabin_altitude_m,
        "flight_altitude_m": item.window_flight_altitude_m,
        "cabin_pressure_pa": wdp["cabin_pressure_pa"],
        "ambient_pressure_pa": wdp["ambient_pressure_pa"],
        "limit_differential_pa": wdp["limit_differential_pa"],
        "design_differential_pa": p_design,
        "pane_radius_m": item.window_radius_m,
        "pane_thickness_required_mm": t_pane * 1000.0,
        "pane_thickness_mm": t_installed_mm,
        "pane_margin": margin,
        "pane_stress_pa": plate_max_stress_clamped_circular(
            p_design, item.window_radius_m, t_installed),
        "allowable_stress_pa": item.window_allowable_stress_pa,
        "weight_per_window_kg": wt["per_window_kg"],
        "total_pane_weight_kg": wt["total_kg"],
        "n_windows": item.n_windows,
    }

    model = {
        "document_type": "Aircraft System Sizing Report",
        "status": "draft-for-review",
        "item": item.aircraft_name,
        "basis": item.basis,
        "generated": _today(),
        "systems": {},
    }
    _sys(model, "electrical", electrical)
    _sys(model, "air_cycle_machine", acm)
    _sys(model, "avionics_bay_cooling", avionics)
    _sys(model, "oxygen", oxygen)
    _sys(model, "brakes", brake)
    _sys(model, "valves", valves)
    _sys(model, "fuel_feed", feed)
    _sys(model, "fuel_jettison", jet)
    _sys(model, "fuel_tank_inerting", inert)
    _sys(model, "hydraulic_actuator", act)
    _sys(model, "landing_gear_layout", gear)
    _sys(model, "ram_air_turbine", rat)
    _sys(model, "tires", tires)
    _sys(model, "windows", windows)
    model["verdicts"] = {
        "electrical": electrical["generator_out_verdict"],
        "acm_shaft": "PASS" if acm["shaft_balanced"] else "FAIL",
        "avionics_bay": avionics["bay_verdict"],
        "brakes": "PASS" if brake["verdict"] == "brake-energy-pass" else "FAIL",
        "outflow_valve": valves["outflow_fit_verdict"],
        "relief_valve": valves["relief_fit_verdict"],
        "fuel_feed": feed["verdict"],
        "fuel_jettison": jet["verdict"],
        "inerting": inert["capacity_verdict"],
        "hydraulic_actuator": "PASS" if act["verdict"] == "pass" else "FAIL",
        "landing_gear_layout": gear["nose_fraction_verdict"],
        "rat": rat["stowage_verdict"],
        "tires": tires["tire_verdict"],
        "windows": "PASS" if windows["pane_margin"] >= 0.0 else "FAIL",
    }
    return model


def _mm(v):
    """Millimetres from metres, formatted."""
    return v * 1000.0


def render_report_markdown(model: dict) -> str:
    """Render the sizing content model as the deliverable markdown."""
    s = model["systems"]
    el = s["electrical"]
    acm = s["air_cycle_machine"]
    av = s["avionics_bay_cooling"]
    ox = s["oxygen"]
    br = s["brakes"]
    va = s["valves"]
    ff = s["fuel_feed"]
    jt = s["fuel_jettison"]
    in_ = s["fuel_tank_inerting"]
    hy = s["hydraulic_actuator"]
    lg = s["landing_gear_layout"]
    rt = s["ram_air_turbine"]
    ti = s["tires"]
    wi = s["windows"]
    v = model["verdicts"]

    lru_lines = "; ".join(
        f"LRU {k} {tc:.0f} C ({ver})"
        for k, tc, ver in zip(av["case_temps_c"].keys(),
                              av["case_temps_c"].values(),
                              av["case_verdicts"].values()))

    lines = [
        "# Aircraft System Sizing Report",
        "",
        f"**Item:** {model['item']}",
        f"**Certification basis:** {model['basis']}",
        "**Status:** draft-for-review (DRAFT for human review; not an "
        "approval)",
        "",
        "## 1. Electrical power system (FAR 25.1355 sizing context)",
        "",
        f"- Duty-weighted continuous load = **{el['continuous_kva']:.1f} kVA** "
        f"(diversity factor {el['diversity_factor']:.2f}; coincident peak "
        f"**{el['coincident_peak_kva']:.1f} kVA**).",
        f"- Essential load = **{el['essential_kva']:.1f} kVA** at full rated "
        f"power ({', '.join(el['essential_consumers'])}).",
        f"- Installed capacity = {el['n_generators']} x "
        f"{el['generator_kva']:.0f} kVA = **{el['installed_kva']:.0f} kVA**; "
        f"load fraction = **{el['load_fraction']:.2f}**.",
        f"- Single-generator-out: remaining capacity "
        f"**{el['remaining_kva']:.0f} kVA**, margin "
        f"**{el['generator_out_margin']:+.2f}** -> **{v['electrical']}**.",
        "",
        "## 2. ECS air cycle machine (bootstrap pack)",
        "",
        f"- Pack-inlet bleed {acm['p1_pa']/1000.0:.0f} kPa / "
        f"{acm['t1_k']:.0f} K; compressor PR {acm['compressor_pr']:.1f}, "
        f"eta_c {acm['compressor_eta']:.2f}: T2 = **{acm['t2_k']:.0f} K**, "
        f"p2 = {acm['p2_pa']/1000.0:.0f} kPa.",
        f"- Heat exchanger closes the shaft: effectiveness "
        f"**{acm['hx_effectiveness_for_balance']:.2f}**, T3 = "
        f"**{acm['t3_k']:.0f} K** (balance T3 {acm['t3_balance_k']:.0f} K).",
        f"- Turbine (eta_t {acm['turbine_eta']:.2f}) exit T4 = "
        f"**{acm['t4_k']:.0f} K**; compressor shaft "
        f"{acm['compressor_power_w']/1000.0:.1f} kW, turbine shaft "
        f"{acm['turbine_power_w']/1000.0:.1f} kW "
        f"-> shaft balanced = **{acm['shaft_balanced']}**.",
        f"- Delivered cooling {acm['cooling_capacity_w']/1000.0:.1f} kW vs "
        f"cabin load {acm['heat_load_w']/1000.0:.1f} kW; required bleed flow "
        f"= **{acm['required_bleed_flow_kg_s']:.3f} kg/s**.",
        "",
        "## 3. Avionics bay cooling",
        "",
        f"- Bay heat load = **{av['bay_heat_load_w']:.0f} W**; cooling supply "
        f"{av['supply_temp_c']:.0f} C to {av['exhaust_limit_c']:.0f} C limit.",
        f"- Cooling airflow = **{av['mass_flow_kg_s']:.3f} kg/s** "
        f"({av['flow_cfm']:.0f} CFM).",
        f"- LRU case temperatures: {lru_lines} "
        f"-> bay verdict **{av['bay_verdict']}**.",
        "",
        "## 4. Supplemental oxygen",
        "",
        f"- Passengers ({ox['n_passengers']}): continuous-flow demand "
        f"**{ox['passenger_demand_sl']/1000.0:.0f} kSL** "
        f"({ox['generator_units']:.0f} generators, one per passenger).",
        f"- Crew ({ox['n_crew']}): diluter-demand "
        f"**{ox['crew_demand_sl']/1000.0:.1f} kSL**, stored "
        f"{ox['crew_mass_kg']:.1f} kg at "
        f"{ox['service_pressure_psi']:.0f} psi -> bottle "
        f"**{ox['bottle_volume_l']:.0f} L** "
        f"({ox['bottle_volume_m3']:.3f} m3).",
        f"- Total stored oxygen mass = **{ox['total_mass_kg']:.1f} kg**.",
        "",
        "## 5. Wheel brakes (RTO / landing energy)",
        "",
        f"- RTO energy at V1 = {br['E_rto_J']/1e6:.0f} MJ; landing-stop "
        f"energy = {br['E_land_J']/1e6:.0f} MJ; governing case "
        f"**{br['governing_case']}** "
        f"({br['per_brake_governing_J']/1e6:.1f} MJ per brake, "
        f"{br['n_braked_wheels']} braked wheels).",
        f"- Required heat sink {br['required_heat_sink_mass_kg']:.1f} kg vs "
        f"{br['heat_sink_mass_available_kg']:.0f} kg available per brake; "
        f"temperature rise **{br['actual_temperature_rise_K']:.0f} K** "
        f"(allowable {br['delta_t_allowable_K']:.0f} K, margin "
        f"{br['delta_t_margin_K']:+.0f} K).",
        f"- Braking distance at {br['decel_g']:.2f} g = "
        f"**{br['braking_distance_m']:.0f} m** -> **{v['brakes']}**.",
        "",
        "## 6. Cabin outflow and pressure-relief valves",
        "",
        f"- Outflow valve: choked mass flux "
        f"{va['outflow_mass_flux_kg_m2s']:.0f} kg/m2s at the cruise cabin "
        f"pressure {va['cabin_pressure_pa']/1000.0:.0f} kPa; area "
        f"**{va['outflow_area_m2']*1e4:.1f} cm2**, equivalent diameter "
        f"**{va['outflow_diameter_m']*1000.0:.0f} mm** "
        f"-> **{v['outflow_valve']}**.",
        f"- Relief valve at the 8.9 psi differential clamp (ambient "
        f"{va['relief_ambient_pa']/1000.0:.0f} kPa): area "
        f"**{va['relief_area_m2']*1e4:.1f} cm2**, diameter "
        f"**{va['relief_diameter_m']*1000.0:.0f} mm** "
        f"-> **{v['relief_valve']}**.",
        "",
        "## 7. Fuel feed system",
        "",
        f"- Feed line {ff['area_m2']*1e4:.1f} cm2: velocity "
        f"**{ff['velocity_m_s']:.2f} m/s**, Re = {ff['reynolds']:.0f}, "
        f"Darcy f = {ff['friction_factor']:.4f}.",
        f"- Line losses {ff['major_loss_pa']/1000.0:.1f} kPa major + "
        f"{ff['minor_loss_pa']/1000.0:.1f} kPa minor "
        f"(total {ff['total_line_loss_pa']/1000.0:.1f} kPa); static head "
        f"{ff['static_head_pa']/1000.0:.1f} kPa.",
        f"- NPSHa = **{ff['npsh_available_m']:.2f} m** vs required "
        f"{ff['npsh_required_m']:.2f} m; boost pump (+"
        f"{ff['boost_pressure_rise_pa']/PSI_TO_PA:.0f} psi) -> "
        f"NPSHa {ff['npsh_with_boost_m']:.2f} m, pump power "
        f"**{ff['boost_power_w']/1000.0:.1f} kW** -> **{v['fuel_feed']}**.",
        "",
        "## 8. Fuel jettison (FAR 25.1001 context)",
        "",
        f"- Dumpable fuel to reach MLW = **{jt['dumpable_mass_kg']/1000.0:.1f} t** "
        f"(MTOW {jt['mtow_kg']/1000.0:.0f} t, MLW {jt['mlw_kg']/1000.0:.0f} t).",
        f"- Required average rate {jt['required_rate_kg_s']:.1f} kg/s over "
        f"{jt['limit_s']:.0f} s; design rate "
        f"**{jt['design_rate_kg_s']:.1f} kg/s** (margin {jt['margin']:.2f}) "
        f"over {jt['n_masts']} masts = {jt['per_mast_flow_kg_s']:.1f} kg/s "
        f"each.",
        f"- Time to landing weight = **{jt['time_s']:.0f} s** "
        f"-> **{v['fuel_jettison']}**.",
        "",
        "## 9. Fuel tank inerting (NEA washout)",
        "",
        f"- Ullage washout from 21% to {in_['target_o2_fraction']:.0%} O2 in "
        f"{in_['time_s']:.0f} s (ullage {in_['ullage_m3']:.1f} m3): "
        f"required NEA flow **{in_['flow_m3_s']*1000.0:.0f} L/s "
        f"({in_['flow_scfm']:.0f} SCFM)** -> **{v['inerting']}**.",
        "",
        "## 10. Hydraulic actuation (3000 psi system)",
        "",
        f"- Actuator load {hy['load_N']/1000.0:.0f} kN at "
        f"{hy['system_pressure_psi']:.0f} psi: piston area "
        f"**{hy['piston_area']*1e4:.2f} cm2**, required bore "
        f"{hy['bore_mm']:.0f} mm -> preferred **{hy['bore_pref_mm']:.0f} mm**.",
        f"- Rod (Euler buckling, FoS 2.0 over {hy['rod_length_m']:.1f} m): "
        f"required {hy['rod_buckling_mm']:.1f} mm -> preferred "
        f"**{hy['rod_pref_mm']:.0f} mm**; retract capability "
        f"{hy['retract_capability_N']/1000.0:.0f} kN, rod stress "
        f"{hy['rod_stress_Pa']/1e6:.0f} MPa, buckling margin "
        f"{hy['buckling_margin']:.1f}.",
        f"- Mass estimate **{hy['mass_kg']:.1f} kg** at "
        f"{hy['stroke_m']*1000.0:.0f} mm stroke "
        f"-> **{v['hydraulic_actuator']}**.",
        "",
        "## 11. Landing gear layout",
        "",
        f"- Tipback angle at the aft CG = **{lg['tipback_angle_deg']:.1f} deg**.",
        f"- Tail strike clearance at rotation = "
        f"**{lg['tail_strike_clearance_deg']:.1f} deg**.",
        f"- Lateral turnover (main pair) = {lg['lateral_turnover_deg']:.1f} "
        f"deg; tricycle diagonal {lg['tricycle_turnover_fwd_deg']:.1f} deg "
        f"(fwd CG) / {lg['tricycle_turnover_aft_deg']:.1f} deg (aft CG).",
        f"- Nose gear static load fraction "
        f"**{lg['nose_load_fraction_fwd']:.2f}** (fwd CG) to "
        f"**{lg['nose_load_fraction_aft']:.2f}** (aft CG).",
        "",
        "## 12. Ram air turbine (emergency power)",
        "",
        f"- Required {rt['p_req_w']/1000.0:.1f} kW at "
        f"{rt['v_m_s']:.0f} m/s: swept area **{rt['area_m2']:.3f} m2**, "
        f"disk diameter **{rt['diameter_m']*1000.0:.0f} mm**, available "
        f"{rt['available_w']/1000.0:.1f} kW "
        f"-> stowage **{v['rat']}**.",
        "",
        "## 13. Tires (main gear)",
        "",
        f"- Static load per tire = **{ti['load_per_tire_kg']:.0f} kg** "
        f"({ti['load_per_tire_lb']:.0f} lb).",
        f"- Class-I fit: diameter **{ti['diameter_in']:.1f} in "
        f"({ti['diameter_mm']:.0f} mm)**, width **{ti['width_in']:.1f} in "
        f"({ti['width_mm']:.0f} mm)**, rolling radius "
        f"{ti['rolling_radius_in']:.1f} in.",
        f"- Footprint {ti['footprint_sqin']:.0f} in2 at "
        f"{ti['tire_pressure_psi']:.0f} psi; {ti['required_tires_main_gear']:.0f} "
        f"tires required per main gear.",
        "",
        "## 14. Window apertures (pressurized cabin)",
        "",
        f"- ISA cabin pressure {wi['cabin_pressure_pa']/1000.0:.1f} kPa at "
        f"{wi['cabin_altitude_m']:.0f} m vs "
        f"{wi['ambient_pressure_pa']/1000.0:.1f} kPa at "
        f"{wi['flight_altitude_m']:.0f} m: limit differential "
        f"{wi['limit_differential_pa']/1000.0:.1f} kPa, design "
        f"**{wi['design_differential_pa']/1000.0:.1f} kPa** (1.33 factor).",
        f"- Clamped circular pane r = {wi['pane_radius_m']*1000.0:.0f} mm: "
        f"required thickness **{wi['pane_thickness_required_mm']:.1f} mm** "
        f"(installed {wi['pane_thickness_mm']:.1f} mm), edge "
        f"stress {wi['pane_stress_pa']/1e6:.0f} MPa vs "
        f"{wi['allowable_stress_pa']/1e6:.0f} MPa allowable "
        f"-> margin **{wi['pane_margin']:+.2f}**.",
        f"- Pane weight {wi['weight_per_window_kg']:.2f} kg per window x "
        f"{wi['n_windows']} = **{wi['total_pane_weight_kg']:.0f} kg**.",
        "",
        "## Verdict summary",
        "",
        "| System | Verdict |",
        "|---|---|",
        *[f"| {name} | {ver} |" for name, ver in v.items()],
        "",
        "---",
        f"*Generated by Aero Agent Roles aircraft-systems-sizing-engineer core "
        f"({model['generated']}). DRAFT for human systems engineering review. "
        "Not an approval document - no certification approval is claimed, no "
        "compliance finding is declared. Sizes are conceptual class-I values "
        "for the stated example aircraft.*",
    ]
    return "\n".join(lines)


GATE_CHECKS = {
    "item_identified": "report names the aircraft and basis",
    "systems_sized": "all 14 system sections carry computed numbers",
    "key_numbers_present": "sizing numbers appear for each system",
    "verdicts_present": "every system verdict is PASS or FAIL",
    "sign_off_honest": "document is marked draft-for-review, not approval",
}


def check_report(model: dict) -> dict:
    """Run the evidence gates against the report model."""
    systems = model.get("systems", {})
    expected = ["electrical", "air_cycle_machine", "avionics_bay_cooling",
                "oxygen", "brakes", "valves", "fuel_feed", "fuel_jettison",
                "fuel_tank_inerting", "hydraulic_actuator",
                "landing_gear_layout", "ram_air_turbine", "tires", "windows"]
    all_sized = all(name in systems and systems[name] for name in expected)
    verdicts = model.get("verdicts", {})
    all_verdicts = (len(verdicts) == len(expected)
                    and all(str(x) in ("PASS", "FAIL")
                            for x in verdicts.values()))
    results = {
        "item_identified": bool(model.get("item")) and bool(model.get("basis")),
        "systems_sized": all_sized,
        "key_numbers_present": _key_numbers_present(model),
        "verdicts_present": all_verdicts,
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def _key_numbers_present(model: dict) -> bool:
    """True when at least one computed number exists per system section."""
    s = model.get("systems", {})
    numeric = {
        "electrical": "continuous_kva", "air_cycle_machine": "t4_k",
        "avionics_bay_cooling": "mass_flow_kg_s", "oxygen": "total_mass_kg",
        "brakes": "per_brake_governing_J", "valves": "outflow_area_m2",
        "fuel_feed": "npsh_available_m", "fuel_jettison": "design_rate_kg_s",
        "fuel_tank_inerting": "flow_m3_s", "hydraulic_actuator": "piston_area",
        "landing_gear_layout": "tipback_angle_deg",
        "ram_air_turbine": "diameter_m", "tires": "diameter_in",
        "windows": "pane_thickness_mm",
    }
    return all(name in s and key in s[name] for name, key in numeric.items())


def check_report_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    checks = {
        "has_title": "aircraft system sizing report" in low,
        "has_item": "**item:**" in low,
        "has_sections": all(
            "## %d." % n in md_text for n in range(1, 15)),
        "has_verdict_summary": "## verdict summary" in low,
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling."""
    return check_report_markdown(md_text)


def example_report_markdown() -> str:
    """Render the worked-example report (used by tests + template)."""
    return render_report_markdown(build_report(example_item()))


if __name__ == "__main__":
    model = build_report(example_item())
    md = render_report_markdown(model)
    print("ITEM: %s" % model["item"])
    print("ELECTRICAL continuous: %.1f kVA; essential %.1f kVA; "
          "gen-out margin %+.2f"
          % (model["systems"]["electrical"]["continuous_kva"],
             model["systems"]["electrical"]["essential_kva"],
             model["systems"]["electrical"]["generator_out_margin"]))
    print("VERDICTS: %s" % model["verdicts"])
    print("GATES: %s" % check_report(model))
    print("RENDERED: %d chars" % len(md))
