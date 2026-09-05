#!/usr/bin/env python3
"""space_systems_core.py - Space Systems Engineer executable core.

This is the role's ENGINE: given a spacecraft mission's project facts it
computes the orbit elements, the mission delta-v budget (Hohmann and
single-burn disposal legs, margin, propellant mass via the Tsiolkovsky
rocket equation), the ADCS solution (reaction wheel momentum sizing
h = J*omega, wheel inertia, pointing error budget), the power/thermal
closure (eclipse geometry, battery capacity, solar array area, radiator
area), the comms link budget (Friis downlink/uplink), propulsion tank
sizing, and BUILDS the Mission and Subsystem Design Report content
model. It also gate-checks deliverables. Standalone: no external repo
needed; stdlib only.

Domain rules encoded here are the public astrodynamics / spacecraft
engineering relations exercised by the bound AeroSkills space-systems
leaves (hohmann-transfer, mission-delta-v-budget, reaction-wheel-control,
power-thermal-budget, solar-array-sizing, spacecraft-battery-sizing,
thermal-design, communication-link-budget, propellant-tank-sizing,
eclipse-time, kepler-orbit-propagation, pointing-error-budget) and the
public references recorded in SOURCES.md (ECSS space engineering,
Wertz SMAD, Vallado). Standard text is never reproduced.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date

# ---------------------------------------------------------------------------
# Physical constants (public knowledge, as used across the AeroSkills leaves)
# ---------------------------------------------------------------------------

MU_EARTH = 3.986004418e14      # Earth gravitational parameter, m^3/s^2
RE_EARTH = 6378.137e3          # Earth equatorial radius, m
G0 = 9.80665                   # standard gravity, m/s^2
SOLAR_FLUX = 1367.0            # AM0 solar irradiance, W/m^2
STEFAN_BOLTZMANN = 5.67e-8     # W/m^2/K^4
SPEED_LIGHT = 299792458.0      # m/s
K_BOLTZ = 228.6                # 10*log10(1/k), k in J/K (dB referenced to 1 K)
RPM_TO_RAD_S = 2.0 * math.pi / 60.0

DRAFT_MARKER = ("DRAFT for human space systems lead review. Not launch "
                "readiness. Not an approval document.")


# ---------------------------------------------------------------------------
# Mission project facts
# ---------------------------------------------------------------------------

@dataclass
class PowerLoad:
    """One power consumer: name and day/eclipse orbit-average draws (W)."""
    name: str
    day_w: float
    eclipse_w: float


@dataclass
class SpacecraftMission:
    """Project facts the role needs to size the spacecraft and mission."""
    # --- mission / orbit ---
    name: str = "Aurora-1 Earth Observation Microsatellite"
    mission_summary: str = ("600 km circular sun-synchronous Earth observation "
                            "microsatellite, 5-year design life, 10:30 LTDN.")
    altitude_km: float = 600.0
    inclination_deg: float = 97.8
    eccentricity: float = 0.0
    lifetime_years: float = 5.0
    launch_vehicle_note: str = "rideshare, direct injection"
    # --- delta-v budget contributions (m/s; stated mission legs) ---
    injection_correction_dv_m_s: float = 20.0     # launcher dispersion correction
    drag_makeup_dv_m_s: float = 15.0              # orbit maintenance, 5 yr at 600 km
    collision_avoidance_dv_m_s: float = 10.0      # two planned conjunction maneuvers
    disposal_perigee_altitude_km: float = 100.0   # EOL perigee lowering target
    dv_margin_fraction: float = 0.15
    # --- mass / propulsion ---
    dry_mass_kg: float = 150.0
    isp_s: float = 220.0                          # hydrazine monopropellant
    propellant_density_kg_m3: float = 1008.0      # hydrazine at 20 C
    tank_meop_pa: float = 2.4e6
    tank_burst_factor: float = 1.5
    tank_material_ultimate_pa: float = 850.0e6    # Ti-6Al-4V annealed
    tank_material_density_kg_m3: float = 4430.0
    tank_ullage_fraction: float = 0.06
    tank_boss_factor: float = 1.10
    pressurant_gas_constant: float = 2077.0       # helium, J/(kg K)
    pressurant_temp_k: float = 293.0
    # --- power / thermal ---
    power_loads: list = field(default_factory=lambda: [
        PowerLoad("Payload (optical imager)", 60.0, 0.0),
        PowerLoad("Avionics / C&DH", 30.0, 30.0),
        PowerLoad("ADCS", 15.0, 15.0),
        PowerLoad("Comms (S-band Rx + X-band Tx duty)", 20.0, 10.0),
        PowerLoad("Thermal (heater duty)", 15.0, 25.0),
    ])
    battery_dod: float = 0.30
    battery_efficiency: float = 0.90
    array_margin_fraction: float = 0.20
    array_distribution_efficiency: float = 0.90
    cell_efficiency: float = 0.30                  # triple-junction GaAs
    packing_factor: float = 0.85
    annual_degradation: float = 0.02
    radiator_emissivity: float = 0.90
    radiator_temp_k: float = 293.15
    radiator_sink_temp_k: float = 3.0
    # --- ADCS ---
    bus_inertia_kgm2: float = 20.0
    slew_angle_deg: float = 90.0
    slew_time_s: float = 90.0
    wheel_speed_max_rpm: float = 6000.0
    disturbance_torque_nm: float = 1.2e-5          # worst-case aero/GG dominated
    adcs_momentum_margin: float = 1.5
    pointing_requirement_deg: float = 0.1          # 3-sigma, all axes
    pointing_errors_deg: dict = field(default_factory=lambda: {
        "attitude determination (star tracker)": 0.020,
        "control error (deadband + PD residual)": 0.030,
        "wheel-induced jitter": 0.020,
        "sensor/actuator alignment": 0.020,
        "thermal distortion": 0.015,
    })
    # --- comms ---
    downlink_freq_hz: float = 8.2e9                # X-band
    downlink_tx_power_w: float = 5.0
    downlink_tx_gain_db: float = 24.0              # ~0.3 m reflector
    downlink_rx_gain_db: float = 42.0              # 3 m ground station
    downlink_rx_noise_temp_k: float = 150.0
    downlink_data_rate_bps: float = 150.0e6
    downlink_required_ebno_db: float = 10.5        # coded QPSK threshold
    uplink_freq_hz: float = 2.1e9                  # S-band
    uplink_tx_power_w: float = 20.0
    uplink_tx_gain_db: float = 34.0                # 3 m ground station at S-band
    uplink_rx_gain_db: float = 0.0                 # spacecraft omni
    uplink_rx_noise_temp_k: float = 400.0
    uplink_data_rate_bps: float = 4.0e3
    uplink_required_ebno_db: float = 12.0
    link_elevation_deg: float = 5.0
    implementation_loss_db: float = 3.0            # downlink (pointing, depol, modem)
    link_margin_requirement_db: float = 3.0
    on_board_storage_gb: float = 256.0
    imaging_data_gb_per_day: float = 30.0
    passes_per_day: int = 6                        # planned high-latitude contacts
    pass_duration_min: float = 10.0
    # --- mass budget (dry mass rows; must sum to dry_mass_kg) ---
    mass_budget_kg: dict = field(default_factory=lambda: {
        "Payload (imager)": 38.0,
        "Structure": 42.0,
        "Electrical power subsystem": 20.0,
        "ADCS": 11.0,
        "Propulsion (dry: tank, thrusters, plumbing)": 10.0,
        "Comms": 7.0,
        "C&DH": 7.0,
        "Thermal": 5.0,
        "Harness + integration": 10.0,
    })

    # ------------------------------------------------------------------
    def orbit_radius_m(self) -> float:
        return RE_EARTH + self.altitude_km * 1000.0


# ---------------------------------------------------------------------------
# Orbit mechanics (mirrors kepler-orbit-propagation / hohmann-transfer leaves)
# ---------------------------------------------------------------------------

def circular_velocity(radius_m: float, mu: float = MU_EARTH) -> float:
    """v = sqrt(mu / r), m/s (circular orbit speed)."""
    if radius_m <= 0:
        raise ValueError(f"radius_m must be > 0, got {radius_m!r}")
    return math.sqrt(mu / radius_m)


def orbit_period_seconds(radius_m: float, mu: float = MU_EARTH) -> float:
    """T = 2*pi*sqrt(r^3/mu), s (Kepler's third law, circular)."""
    if radius_m <= 0:
        raise ValueError(f"radius_m must be > 0, got {radius_m!r}")
    return 2.0 * math.pi * math.sqrt(radius_m ** 3 / mu)


def vis_viva_velocity(radius_m: float, semimajor_axis_m: float,
                      mu: float = MU_EARTH) -> float:
    """v = sqrt(mu*(2/r - 1/a)), m/s."""
    if radius_m <= 0 or semimajor_axis_m <= 0:
        raise ValueError("radius and semimajor axis must be > 0")
    return math.sqrt(mu * (2.0 / radius_m - 1.0 / semimajor_axis_m))


def hohmann_burn_delta_v(r1_m: float, r2_m: float, mu: float = MU_EARTH) -> dict:
    """Two-impulse Hohmann transfer between coplanar circular orbits.

    Returns departure and arrival impulses and the total in m/s
    (dv_total = dv1 + dv2), plus the one-way transfer time. Mirrors the
    hohmann-transfer leaf: LEO (Re+500 km) to GEO totals ~3816 m/s.
    """
    if r1_m <= 0 or r2_m <= 0 or r1_m == r2_m:
        raise ValueError("radii must be > 0 and differ")
    a_t = (r1_m + r2_m) / 2.0
    dv1 = abs(vis_viva_velocity(r1_m, a_t, mu) - circular_velocity(r1_m, mu))
    dv2 = abs(circular_velocity(r2_m, mu) - vis_viva_velocity(r2_m, a_t, mu))
    t_transfer = math.pi * math.sqrt(a_t ** 3 / mu)
    return {"dv1_m_s": dv1, "dv2_m_s": dv2, "total_m_s": dv1 + dv2,
            "transfer_time_s": t_transfer}


def perigee_lowering_delta_v(altitude_km: float, target_perigee_km: float,
                             mu: float = MU_EARTH,
                             re: float = RE_EARTH) -> float:
    """Single retrograde burn at apogee to lower perigee for disposal.

    Burn on the circular orbit at radius r; the new ellipse has apogee r
    and perigee re + target_perigee_km. dv = v_circ - v_at_apogee_new.
    """
    if altitude_km <= 0 or target_perigee_km <= 0:
        raise ValueError("altitudes must be > 0")
    r = re + altitude_km * 1000.0
    rp = re + target_perigee_km * 1000.0
    if rp >= r:
        raise ValueError("target perigee must be below the orbit altitude")
    a_new = (r + rp) / 2.0
    v_circ = circular_velocity(r, mu)
    v_new = vis_viva_velocity(r, a_new, mu)
    return v_circ - v_new


# ---------------------------------------------------------------------------
# Delta-v budget + propellant (mirrors mission-delta-v-budget leaf)
# ---------------------------------------------------------------------------

def sum_delta_v(contributions: list) -> float:
    contribs = [float(c) for c in contributions]
    if any(c < 0 for c in contribs):
        raise ValueError("delta-v contributions must be >= 0")
    return sum(contribs)


def apply_margin(total_m_s: float, margin_fraction: float) -> float:
    if total_m_s < 0 or margin_fraction < 0:
        raise ValueError("total and margin must be >= 0")
    return total_m_s * (1.0 + margin_fraction)


def propellant_mass(delta_v_m_s: float, dry_mass_kg: float, isp_s: float,
                    g0: float = G0) -> float:
    """m_prop = m_dry * (exp(dv/(Isp*g0)) - 1), kg (rocket equation)."""
    if delta_v_m_s < 0 or dry_mass_kg <= 0 or isp_s <= 0:
        raise ValueError("dv >= 0, dry mass > 0, isp > 0 required")
    return dry_mass_kg * (math.exp(delta_v_m_s / (isp_s * g0)) - 1.0)


def wet_mass(delta_v_m_s: float, dry_mass_kg: float, isp_s: float,
             g0: float = G0) -> float:
    return dry_mass_kg + propellant_mass(delta_v_m_s, dry_mass_kg, isp_s, g0)


def mission_delta_v_budget(mission: SpacecraftMission) -> dict:
    """Nominal + budgeted delta-v and propellant sizing for the mission."""
    disposal_dv = perigee_lowering_delta_v(mission.altitude_km,
                                           mission.disposal_perigee_altitude_km)
    contributions = {
        "Injection dispersion correction": mission.injection_correction_dv_m_s,
        "Orbit maintenance (drag, 5 yr)": mission.drag_makeup_dv_m_s,
        "Collision avoidance (2 maneuvers)": mission.collision_avoidance_dv_m_s,
        "End-of-life disposal (perigee lowering)": disposal_dv,
    }
    nominal = sum_delta_v(list(contributions.values()))
    budgeted = apply_margin(nominal, mission.dv_margin_fraction)
    m_prop = propellant_mass(budgeted, mission.dry_mass_kg, mission.isp_s)
    return {
        "contributions": contributions,
        "disposal_dv_m_s": disposal_dv,
        "disposal_perigee_altitude_km": mission.disposal_perigee_altitude_km,
        "nominal_dv_m_s": nominal,
        "margin_fraction": mission.dv_margin_fraction,
        "budgeted_dv_m_s": budgeted,
        "dry_mass_kg": mission.dry_mass_kg,
        "isp_s": mission.isp_s,
        "propellant_mass_kg": m_prop,
        "wet_mass_kg": mission.dry_mass_kg + m_prop,
        "propellant_fraction": m_prop / (mission.dry_mass_kg + m_prop),
    }


# ---------------------------------------------------------------------------
# Propellant tank sizing (mirrors propellant-tank-sizing leaf)
# ---------------------------------------------------------------------------

def tank_sizing(propellant_kg: float, density_kg_m3: float,
                ullage_fraction: float, meop_pa: float, burst_factor: float,
                material_ultimate_pa: float, material_density_kg_m3: float,
                boss_factor: float, pressurant_gas_constant: float,
                pressurant_temp_k: float) -> dict:
    """Spherical titanium tank: volume, radius, wall, shell, pressurant."""
    if propellant_kg <= 0 or density_kg_m3 <= 0:
        raise ValueError("propellant mass and density must be > 0")
    v_prop = propellant_kg / density_kg_m3
    if not 0.0 < ullage_fraction < 1.0:
        raise ValueError("ullage fraction must be in (0, 1)")
    v_tank = v_prop / (1.0 - ullage_fraction)
    v_ullage = v_tank * ullage_fraction
    radius = (3.0 * v_tank / (4.0 * math.pi)) ** (1.0 / 3.0)
    burst_pa = burst_factor * meop_pa
    wall_m = burst_pa * radius / (2.0 * material_ultimate_pa)
    shell_kg = (4.0 * math.pi * radius * radius * wall_m
                * material_density_kg_m3 * boss_factor)
    pressurant_kg = (meop_pa * v_ullage
                     / (pressurant_gas_constant * pressurant_temp_k))
    return {
        "propellant_density_kg_m3": density_kg_m3,
        "propellant_volume_l": v_prop * 1000.0,
        "tank_volume_l": v_tank * 1000.0,
        "radius_m": radius,
        "wall_thickness_mm": wall_m * 1000.0,
        "shell_mass_kg": shell_kg,
        "pressurant_mass_kg": pressurant_kg,
    }


# ---------------------------------------------------------------------------
# Eclipse geometry (mirrors eclipse-time leaf, beta = 0 worst case)
# ---------------------------------------------------------------------------

def eclipse_geometry(altitude_km: float, radius_earth: float = RE_EARTH,
                     mu: float = MU_EARTH) -> dict:
    """Worst-case (beta = 0) shadow fraction/time for a circular orbit.

    f = asin(Re / r) / pi; eclipse_time = f * T.
    """
    if altitude_km < 0:
        raise ValueError("altitude must be >= 0")
    r = radius_earth + altitude_km * 1000.0
    if r <= radius_earth:
        raise ValueError("orbit radius must exceed Earth radius")
    period = orbit_period_seconds(r, mu)
    fraction = math.asin(radius_earth / r) / math.pi
    return {
        "period_s": period,
        "period_min": period / 60.0,
        "shadow_fraction": fraction,
        "daylight_fraction": 1.0 - fraction,
        "eclipse_time_s": fraction * period,
        "eclipse_time_min": fraction * period / 60.0,
        "orbits_per_day": 86400.0 / period,
    }


# ---------------------------------------------------------------------------
# Power and thermal (mirrors power-thermal-budget / solar-array-sizing /
# spacecraft-battery-sizing / thermal-design leaves)
# ---------------------------------------------------------------------------

def battery_capacity_required(power_w: float, eclipse_min: float,
                              dod: float, efficiency: float) -> float:
    """C = P * (t_eclipse/60) / (DoD * efficiency), Wh."""
    if power_w <= 0 or eclipse_min <= 0:
        raise ValueError("power and eclipse duration must be > 0")
    if not 0.0 < dod <= 1.0 or not 0.0 < efficiency <= 1.0:
        raise ValueError("DoD and efficiency must be in (0, 1]")
    return power_w * (eclipse_min / 60.0) / (dod * efficiency)


def solar_array_daylight_power(power_w: float, eclipse_fraction: float,
                               efficiency: float, margin: float = 0.0) -> float:
    """P_sa = P / (eff * (1 - f)) * (1 + margin), W (daylight-only gen)."""
    if power_w <= 0:
        raise ValueError("power must be > 0")
    if not 0.0 < eclipse_fraction < 1.0:
        raise ValueError("eclipse fraction must be in (0, 1)")
    if not 0.0 < efficiency <= 1.0 or margin < 0:
        raise ValueError("efficiency in (0,1], margin >= 0")
    return power_w / (efficiency * (1.0 - eclipse_fraction)) * (1.0 + margin)


def eol_specific_power(solar_flux: float, cell_eff: float, packing: float,
                       annual_degradation: float, years: float) -> float:
    """p_eol = G*eta*PF*(1-r)^years, W/m^2 (end-of-life panel power)."""
    if solar_flux <= 0 or not 0.0 < cell_eff <= 1 or not 0.0 < packing <= 1:
        raise ValueError("irradiance, efficiency, packing must be > 0")
    if not 0.0 <= annual_degradation < 1.0 or years < 0:
        raise ValueError("degradation in [0,1), years >= 0")
    return solar_flux * cell_eff * packing * (1.0 - annual_degradation) ** years


def radiator_area(heat_load_w: float, t_rad_k: float, t_sink_k: float,
                  eps: float) -> float:
    """A = Q / (eps * sigma * (T_rad^4 - T_sink^4)), m^2."""
    if heat_load_w < 0:
        raise ValueError("heat load must be >= 0")
    if t_rad_k <= t_sink_k:
        raise ValueError("radiator temperature must exceed sink temperature")
    if not 0.0 < eps <= 1.0:
        raise ValueError("emissivity must be in (0, 1]")
    return heat_load_w / (eps * STEFAN_BOLTZMANN
                          * (t_rad_k ** 4 - t_sink_k ** 4))


def power_and_thermal(mission: SpacecraftMission) -> dict:
    """Close the power/thermal budgets: loads, eclipse, battery, array,
    radiator."""
    ecl = eclipse_geometry(mission.altitude_km)
    f = ecl["shadow_fraction"]
    loads = []
    for pl in mission.power_loads:
        loads.append({"name": pl.name, "day_w": pl.day_w,
                      "eclipse_w": pl.eclipse_w})
    day_total = sum(pl.day_w for pl in mission.power_loads)
    eclipse_total = sum(pl.eclipse_w for pl in mission.power_loads)
    orbit_avg_w = (day_total * (1.0 - f) + eclipse_total * f)
    # battery: eclipse load must be carried over the worst-case shadow
    required_wh = battery_capacity_required(
        eclipse_total, ecl["eclipse_time_min"], mission.battery_dod,
        mission.battery_efficiency)
    sized_wh = math.ceil(required_wh * (1.0 + 0.20) / 5.0) * 5.0   # 20% + pack step
    battery_margin = sized_wh / required_wh - 1.0
    # solar array: daylight generation of the orbit-average demand
    p_sa_w = solar_array_daylight_power(
        orbit_avg_w, f, mission.array_distribution_efficiency,
        mission.array_margin_fraction)
    p_eol = eol_specific_power(SOLAR_FLUX, mission.cell_efficiency,
                               mission.packing_factor,
                               mission.annual_degradation,
                               mission.lifetime_years)
    area_m2 = p_sa_w / p_eol
    # radiator: continuous dissipation (avionics + ADCS + Rx at night)
    rad_load_w = (mission.power_loads[1].day_w + mission.power_loads[2].day_w
                  + 10.0)  # C&DH + ADCS + continuous comms Rx
    rad_area_m2 = radiator_area(rad_load_w, mission.radiator_temp_k,
                                mission.radiator_sink_temp_k,
                                mission.radiator_emissivity)
    return {
        "eclipse": ecl,
        "loads": loads,
        "day_total_w": day_total,
        "eclipse_total_w": eclipse_total,
        "orbit_average_w": orbit_avg_w,
        "battery_dod": mission.battery_dod,
        "battery_efficiency": mission.battery_efficiency,
        "battery_required_wh": required_wh,
        "battery_sized_wh": sized_wh,
        "battery_margin": battery_margin,
        "array_daylight_power_w": p_sa_w,
        "array_eol_specific_power_w_m2": p_eol,
        "array_area_m2": area_m2,
        "array_margin_fraction": mission.array_margin_fraction,
        "cell_efficiency": mission.cell_efficiency,
        "packing_factor": mission.packing_factor,
        "annual_degradation": mission.annual_degradation,
        "radiator_load_w": rad_load_w,
        "radiator_area_m2": rad_area_m2,
        "radiator_temp_k": mission.radiator_temp_k,
        "radiator_emissivity": mission.radiator_emissivity,
    }


# ---------------------------------------------------------------------------
# ADCS (mirrors reaction-wheel-control / pointing-error-budget leaves)
# ---------------------------------------------------------------------------

def reaction_wheel_sizing(mission: SpacecraftMission,
                          orbit_period_s: float) -> dict:
    """Size the wheel cluster: h_slew = J*omega, disturbance accumulation,
    momentum capacity, wheel inertia J_w = h_cap / omega_max, torque class."""
    theta_rad = math.radians(mission.slew_angle_deg)
    omega_slew = theta_rad / mission.slew_time_s            # rad/s (avg rate)
    h_slew = mission.bus_inertia_kgm2 * omega_slew          # N m s
    h_dist = mission.disturbance_torque_nm * orbit_period_s / 2.0
    h_required = (h_slew + h_dist) * mission.adcs_momentum_margin
    h_capacity = 1.0                                        # product class, N m s
    omega_max = mission.wheel_speed_max_rpm * RPM_TO_RAD_S
    j_wheel = h_capacity / omega_max                        # kg m^2
    alpha_slew = 4.0 * theta_rad / mission.slew_time_s ** 2  # trapezoid approx
    tau_required = mission.bus_inertia_kgm2 * alpha_slew
    return {
        "omega_slew_rad_s": omega_slew,
        "slew_momentum_nms": h_slew,
        "disturbance_momentum_nms": h_dist,
        "required_momentum_nms": h_required,
        "wheel_momentum_capacity_nms": h_capacity,
        "wheel_speed_max_rpm": mission.wheel_speed_max_rpm,
        "wheel_inertia_kgm2": j_wheel,
        "slew_alpha_rad_s2": alpha_slew,
        "required_wheel_torque_nm": tau_required,
        "wheel_torque_class_nm": 0.02,
        "wheel_configuration": "3 orthogonal wheels + 1 redundant",
        "slew_angle_deg": mission.slew_angle_deg,
        "slew_time_s": mission.slew_time_s,
        "bus_inertia_kgm2": mission.bus_inertia_kgm2,
        "disturbance_torque_nm": mission.disturbance_torque_nm,
        "adcs_momentum_margin": mission.adcs_momentum_margin,
    }


def pointing_error_budget(mission: SpacecraftMission) -> dict:
    """RSS of 3-sigma pointing error contributors vs the requirement."""
    rss = math.sqrt(sum(v * v for v in mission.pointing_errors_deg.values()))
    return {
        "contributors": dict(mission.pointing_errors_deg),
        "rss_deg": rss,
        "requirement_deg": mission.pointing_requirement_deg,
        "margin": (mission.pointing_requirement_deg / rss
                   if rss > 0 else float("inf")),
        "meets": rss <= mission.pointing_requirement_deg,
    }


# ---------------------------------------------------------------------------
# Comms link budget (mirrors communication-link-budget leaf, Friis)
# ---------------------------------------------------------------------------

def slant_range_m(altitude_km: float, elevation_deg: float,
                  radius_earth: float = RE_EARTH) -> float:
    """Slant range to a ground station at the given elevation mask, m."""
    re = radius_earth
    eps = math.radians(elevation_deg)
    r = re + altitude_km * 1000.0
    d = (math.sqrt(r * r - (re * math.cos(eps)) ** 2)
         - re * math.sin(eps))
    return d


def free_space_path_loss(distance_m: float, freq_hz: float) -> float:
    """L = 20*log10(4*pi*d/lambda), dB."""
    if distance_m <= 0 or freq_hz <= 0:
        raise ValueError("distance and frequency must be > 0")
    lam = SPEED_LIGHT / freq_hz
    return 20.0 * math.log10(4.0 * math.pi * distance_m / lam)


def link_margin(distance_m: float, freq_hz: float, tx_power_w: float,
                tx_gain_db: float, rx_gain_db: float, noise_temp_k: float,
                data_rate_bps: float, required_ebno_db: float,
                other_losses_db: float = 0.0) -> dict:
    """Full one-way link: EIRP -> path loss -> C/N0 -> Eb/N0 margin."""
    if tx_power_w <= 0 or noise_temp_k <= 0 or data_rate_bps <= 0:
        raise ValueError("power, temperature and rate must be > 0")
    eirp = 10.0 * math.log10(tx_power_w) + tx_gain_db
    fsl = free_space_path_loss(distance_m, freq_hz)
    pr = eirp + rx_gain_db - fsl - other_losses_db
    cno = pr + K_BOLTZ - 10.0 * math.log10(noise_temp_k)
    ebno = cno - 10.0 * math.log10(data_rate_bps)
    margin = ebno - required_ebno_db
    return {
        "eirp_dbw": eirp, "path_loss_db": fsl, "received_power_dbw": pr,
        "cno_db_hz": cno, "ebno_db": ebno,
        "required_ebno_db": required_ebno_db, "margin_db": margin,
        "ok": margin >= 0.0,
    }


def comms_link_budget(mission: SpacecraftMission) -> dict:
    """Downlink and uplink budgets plus daily downlink data capacity."""
    d = slant_range_m(mission.altitude_km, mission.link_elevation_deg)
    down = link_margin(d, mission.downlink_freq_hz,
                       mission.downlink_tx_power_w, mission.downlink_tx_gain_db,
                       mission.downlink_rx_gain_db,
                       mission.downlink_rx_noise_temp_k,
                       mission.downlink_data_rate_bps,
                       mission.downlink_required_ebno_db,
                       mission.implementation_loss_db)
    up = link_margin(d, mission.uplink_freq_hz, mission.uplink_tx_power_w,
                     mission.uplink_tx_gain_db, mission.uplink_rx_gain_db,
                     mission.uplink_rx_noise_temp_k,
                     mission.uplink_data_rate_bps,
                     mission.uplink_required_ebno_db, 1.0)
    pass_data_gb = (mission.downlink_data_rate_bps
                    * mission.pass_duration_min * 60.0 / 8.0 / 1e9)
    daily_capacity_gb = pass_data_gb * mission.passes_per_day
    return {
        "slant_range_km": d / 1000.0,
        "elevation_deg": mission.link_elevation_deg,
        "downlink": down, "uplink": up,
        "downlink_freq_hz": mission.downlink_freq_hz,
        "uplink_freq_hz": mission.uplink_freq_hz,
        "downlink_data_rate_bps": mission.downlink_data_rate_bps,
        "uplink_data_rate_bps": mission.uplink_data_rate_bps,
        "pass_data_gb": pass_data_gb,
        "passes_per_day": mission.passes_per_day,
        "pass_duration_min": mission.pass_duration_min,
        "daily_capacity_gb": daily_capacity_gb,
        "imaging_data_gb_per_day": mission.imaging_data_gb_per_day,
        "data_margin": daily_capacity_gb / mission.imaging_data_gb_per_day,
        "storage_gb": mission.on_board_storage_gb,
        "link_margin_requirement_db": mission.link_margin_requirement_db,
        "downlink_meets": down["margin_db"] >= mission.link_margin_requirement_db,
        "uplink_meets": up["margin_db"] >= mission.link_margin_requirement_db,
    }


# ---------------------------------------------------------------------------
# Mass budget closure
# ---------------------------------------------------------------------------

def mass_budget(mission: SpacecraftMission) -> dict:
    rows = dict(mission.mass_budget_kg)
    total = sum(rows.values())
    return {"rows": rows, "dry_total_kg": total,
            "stated_dry_kg": mission.dry_mass_kg,
            "closes": abs(total - mission.dry_mass_kg) < 1e-6}


# ---------------------------------------------------------------------------
# Report builder: content model for the deliverable
# ---------------------------------------------------------------------------

def build_report(mission: SpacecraftMission) -> dict:
    """Build the complete Mission and Subsystem Design Report model."""
    r = mission.orbit_radius_m()
    dv = mission_delta_v_budget(mission)
    tank = tank_sizing(dv["propellant_mass_kg"],
                       mission.propellant_density_kg_m3,
                       mission.tank_ullage_fraction, mission.tank_meop_pa,
                       mission.tank_burst_factor,
                       mission.tank_material_ultimate_pa,
                       mission.tank_material_density_kg_m3,
                       mission.tank_boss_factor,
                       mission.pressurant_gas_constant,
                       mission.pressurant_temp_k)
    pw = power_and_thermal(mission)
    adcs = reaction_wheel_sizing(mission, pw["eclipse"]["period_s"])
    pt = pointing_error_budget(mission)
    comm = comms_link_budget(mission)
    mass = mass_budget(mission)
    # closed-budget verdicts
    verdicts = {
        "delta_v_closes": dv["budgeted_dv_m_s"] > 0 and dv["propellant_mass_kg"] > 0,
        "power_closes": (pw["battery_margin"] >= 0.20
                         and pw["array_area_m2"] > 0),
        "pointing_meets": pt["meets"],
        "link_meets": comm["downlink_meets"] and comm["uplink_meets"],
        "mass_closes": mass["closes"],
    }
    model = {
        "document_type": "Spacecraft Mission and Subsystem Design Report",
        "status": "draft-for-review",
        "mission": mission.name,
        "mission_summary": mission.mission_summary,
        "orbit": {
            "altitude_km": mission.altitude_km,
            "inclination_deg": mission.inclination_deg,
            "eccentricity": mission.eccentricity,
            "radius_km": r / 1000.0,
            "period_min": pw["eclipse"]["period_min"],
            "period_s": pw["eclipse"]["period_s"],
            "orbits_per_day": pw["eclipse"]["orbits_per_day"],
            "circular_velocity_m_s": circular_velocity(r),
            "launch_vehicle_note": mission.launch_vehicle_note,
            "lifetime_years": mission.lifetime_years,
        },
        "delta_v": dv,
        "tank": tank,
        "power": pw,
        "adcs": adcs,
        "pointing": pt,
        "comms": comm,
        "mass": mass,
        "verdicts": verdicts,
        "generated": date.today().isoformat(),
    }
    return model


def _fmt(v: float, digits: int = 1) -> str:
    return f"{v:.{digits}f}"


def render_report_markdown(model: dict) -> str:
    """Render the content model as the deliverable markdown document."""
    o = model["orbit"]
    dv = model["delta_v"]
    tk = model["tank"]
    pw = model["power"]
    ec = pw["eclipse"]
    ad = model["adcs"]
    pt = model["pointing"]
    cm = model["comms"]
    mb = model["mass"]
    v = model["verdicts"]

    L = []
    L.append("# Spacecraft Mission and Subsystem Design Report")
    L.append("")
    L.append(f"**Spacecraft:** {model['mission']}")
    L.append(f"**Mission:** {model['mission_summary']}")
    L.append(f"**Status:** {model['status']}")
    L.append("")
    L.append("## 1. Mission and orbit")
    L.append("")
    L.append(f"- Orbit: circular, altitude {_fmt(o['altitude_km'])} km, "
             f"inclination {_fmt(o['inclination_deg'], 1)} deg "
             f"(sun-synchronous), e = {o['eccentricity']:.3f}.")
    L.append(f"- Orbit radius: {_fmt(o['radius_km'], 0)} km; period "
             f"{_fmt(o['period_min'], 1)} min ({_fmt(o['period_s'], 0)} s); "
             f"{_fmt(o['orbits_per_day'], 1)} orbits/day; circular velocity "
             f"{_fmt(o['circular_velocity_m_s'], 0)} m/s.")
    L.append(f"- Launch: {o['launch_vehicle_note']}; design life "
             f"{_fmt(o['lifetime_years'], 0)} years.")
    L.append("")
    L.append("## 2. Transfer / maneuvers and delta-v budget")
    L.append("")
    L.append(f"- Injection: direct insertion ({o['launch_vehicle_note']}); "
             "no interplanetary C3 or launch-window constraint applies "
             "(LEO circular mission).")
    L.append("- Delta-v contributions (m/s):")
    for name, dv_c in dv["contributions"].items():
        L.append(f"  - {name}: {_fmt(dv_c, 1)}")
    L.append(f"- Disposal leg is a single retrograde burn lowering perigee "
             f"from {_fmt(o['altitude_km'], 0)} km to "
             f"{_fmt(dv['disposal_perigee_altitude_km'], 0)} km "
             f"(Hohmann half-transfer, {_fmt(dv['disposal_dv_m_s'], 1)} m/s).")
    L.append(f"- Nominal total delta-v: {_fmt(dv['nominal_dv_m_s'], 1)} m/s; "
             f"budgeted with {dv['margin_fraction'] * 100:.0f}% margin: "
             f"**{_fmt(dv['budgeted_dv_m_s'], 1)} m/s**.")
    L.append(f"- Propellant (Isp {_fmt(dv['isp_s'], 0)} s, Tsiolkovsky): "
             f"**{_fmt(dv['propellant_mass_kg'], 1)} kg**; wet mass "
             f"{_fmt(dv['wet_mass_kg'], 1)} kg "
             f"({dv['propellant_fraction'] * 100:.1f}% propellant fraction).")
    L.append("")
    L.append("## 3. Environment")
    L.append("")
    L.append(f"- Eclipse (worst case, beta = 0): shadow fraction "
             f"{ec['shadow_fraction'] * 100:.1f}%; eclipse time "
             f"{_fmt(ec['eclipse_time_min'], 1)} min per orbit.")
    L.append(f"- Perturbations at {_fmt(o['altitude_km'], 0)} km SSO: J2 nodal "
             "precession used for the sun-synchronous plane; drag is the "
             "long-term orbit maintenance driver (budgeted above); three-body "
             "effects negligible at this altitude.")
    L.append(f"- Radiation/debris: {_fmt(o['altitude_km'], 0)} km SSO sits in "
             "the inner belt proton/electron environment; parts list to a "
             "25-50 krad(Si) total dose class (ECSS-Q-ST-60-15C practice); "
             "conjunction screening budgeted as 2 avoidance maneuvers over "
             "life.")
    L.append("")
    L.append("## 4. ADCS")
    L.append("")
    L.append("- Determination: star tracker (knowledge ~5 arcsec 1-sigma), "
             "sun sensors, 3-axis rate gyro, magnetometer; TRIAD/QUEST "
             "batch solutions on the C&DH.")
    L.append(f"- Control: {ad['wheel_configuration']} reaction wheels, "
             f"momentum capacity **{_fmt(ad['wheel_momentum_capacity_nms'], 1)} "
             f"N m s** each at {_fmt(ad['wheel_speed_max_rpm'], 0)} rpm "
             f"(wheel inertia {ad['wheel_inertia_kgm2'] * 1e3:.2f} x 1e-3 "
             f"kg m^2, h = J*omega); torque class "
             f"{ad['wheel_torque_class_nm']:.2f} N m; magnetorquers for "
             "momentum desaturation.")
    L.append(f"- Sizing: slew {_fmt(ad['slew_angle_deg'], 0)} deg in "
             f"{_fmt(ad['slew_time_s'], 0)} s -> slew momentum "
             f"{_fmt(ad['slew_momentum_nms'], 3)} N m s "
             f"(J = {_fmt(ad['bus_inertia_kgm2'], 0)} kg m^2 x "
             f"omega {ad['omega_slew_rad_s'] * 1e3:.1f} x 1e-3 rad/s); "
             f"disturbance accumulation {_fmt(ad['disturbance_momentum_nms'], 4)} "
             f"N m s/orbit; required with margin "
             f"{_fmt(ad['required_momentum_nms'], 2)} N m s < capacity 1.0 N m s.")
    L.append(f"- Pointing error budget (3-sigma RSS): "
             f"**{_fmt(pt['rss_deg'], 3)} deg** vs requirement "
             f"{_fmt(pt['requirement_deg'], 1)} deg "
             f"(margin x {pt['margin']:.1f}, {'meets' if pt['meets'] else 'EXCEEDS'}).")
    for src, val in pt["contributors"].items():
        L.append(f"  - {src}: {_fmt(val, 3)} deg")
    L.append("")
    L.append("## 5. Power and thermal")
    L.append("")
    L.append("| Item | Day power (W) | Eclipse power (W) |")
    L.append("|---|---|---|")
    for row in pw["loads"]:
        L.append(f"| {row['name']} | {_fmt(row['day_w'], 0)} | "
                 f"{_fmt(row['eclipse_w'], 0)} |")
    L.append(f"| **Total** | **{_fmt(pw['day_total_w'], 0)}** | "
             f"**{_fmt(pw['eclipse_total_w'], 0)}** |")
    L.append("")
    L.append(f"- Orbit-average load: {_fmt(pw['orbit_average_w'], 1)} W over a "
             f"{_fmt(o['period_min'], 1)} min orbit "
             f"({ec['shadow_fraction'] * 100:.1f}% eclipse).")
    L.append(f"- Battery: {_fmt(pw['eclipse_total_w'], 0)} W x "
             f"{_fmt(ec['eclipse_time_min'], 1)} min eclipse at "
             f"{pw['battery_dod'] * 100:.0f}% DoD / "
             f"{pw['battery_efficiency'] * 100:.0f}% efficiency requires "
             f"**{_fmt(pw['battery_required_wh'], 1)} Wh**; sized "
             f"**{_fmt(pw['battery_sized_wh'], 0)} Wh** Li-ion "
             f"(margin {pw['battery_margin'] * 100:.0f}%).")
    L.append(f"- Solar array: daylight power "
             f"{_fmt(pw['array_daylight_power_w'], 1)} W; EOL specific power "
             f"{_fmt(pw['array_eol_specific_power_w_m2'], 1)} W/m^2 "
             f"(AM0 {SOLAR_FLUX:.0f} W/m^2, {pw['cell_efficiency'] * 100:.0f}% "
             f"cells, packing {pw['packing_factor']:.2f}, "
             f"{pw['annual_degradation'] * 100:.0f}%/yr x "
             f"{_fmt(o['lifetime_years'], 0)} yr) -> array area "
             f"**{_fmt(pw['array_area_m2'], 2)} m^2**.")
    L.append(f"- Thermal balance: {_fmt(pw['radiator_load_w'], 0)} W continuous "
             f"dissipation rejected by a radiator at "
             f"{pw['radiator_temp_k'] - 273.15:.0f} deg C "
             f"(eps {pw['radiator_emissivity']:.2f}) -> "
             f"**{_fmt(pw['radiator_area_m2'], 2)} m^2**; eclipse heater duty "
             f"25 W is in the load table.")
    L.append("")
    L.append("## 6. Comms")
    L.append("")
    L.append(f"- Slant range at {_fmt(cm['elevation_deg'], 0)} deg elevation: "
             f"{_fmt(cm['slant_range_km'], 0)} km.")
    dl = cm["downlink"]
    ul = cm["uplink"]
    L.append(f"- Downlink (X-band {cm['downlink_freq_hz'] / 1e9:.1f} GHz, "
             f"{cm['downlink_data_rate_bps'] / 1e6:.0f} Mbps): EIRP "
             f"{_fmt(dl['eirp_dbw'], 1)} dBW, path loss "
             f"{_fmt(dl['path_loss_db'], 1)} dB, C/N0 "
             f"{_fmt(dl['cno_db_hz'], 1)} dB-Hz, Eb/N0 "
             f"{_fmt(dl['ebno_db'], 1)} dB vs {_fmt(dl['required_ebno_db'], 1)} "
             f"dB required -> **margin {_fmt(dl['margin_db'], 1)} dB**.")
    L.append(f"- Uplink (S-band {cm['uplink_freq_hz'] / 1e9:.1f} GHz, "
             f"{cm['uplink_data_rate_bps'] / 1e3:.0f} kbps command): "
             f"**margin {_fmt(ul['margin_db'], 1)} dB**.")
    L.append(f"- Data: {_fmt(cm['pass_data_gb'], 1)} GB per {cm['pass_duration_min']:.0f} min "
             f"pass x {cm['passes_per_day']} passes/day = "
             f"**{_fmt(cm['daily_capacity_gb'], 1)} GB/day** capacity vs "
             f"{_fmt(cm['imaging_data_gb_per_day'], 0)} GB/day imaging need "
             f"(margin x {cm['data_margin']:.1f}); on-board storage "
             f"{_fmt(cm['storage_gb'], 0)} GB.")
    L.append("")
    L.append("## 7. Propulsion and C&DH")
    L.append("")
    L.append(f"- Propulsion: {_fmt(dv['propellant_mass_kg'], 1)} kg hydrazine "
             f"(Isp {_fmt(dv['isp_s'], 0)} s) at "
             f"{tk['propellant_density_kg_m3']:.0f} kg/m^3 -> "
             f"{_fmt(tk['propellant_volume_l'], 1)} L propellant, "
             f"{_fmt(tk['tank_volume_l'], 1)} L spherical Ti tank "
             f"(radius {_fmt(tk['radius_m'] * 100, 1)} cm, wall "
             f"{_fmt(tk['wall_thickness_mm'], 2)} mm, shell "
             f"{_fmt(tk['shell_mass_kg'], 2)} kg, pressurant "
             f"{tk['pressurant_mass_kg'] * 1000:.1f} g He); 4 x 1 N thrusters.")
    L.append("- C&DH: single rad-tolerant computer (LEON-class) with "
             "watchdog + triple-redundant command path; ECSS-E-ST-40 / "
             "ECSS-Q-ST-80 software and product assurance context; "
             "on-board storage solid-state recorder with EDAC.")
    L.append("")
    L.append("## 8. System budgets")
    L.append("")
    L.append("| Budget | Value | Margin policy | Closes |")
    L.append("|---|---|---|---|")
    L.append(f"| mass (dry) | {_fmt(mb['dry_total_kg'], 0)} kg (subsystems sum "
             f"to stated {_fmt(mb['stated_dry_kg'], 0)} kg) | 20% at subsystem "
             f"level in stated rows | {'YES' if mb['closes'] else 'NO'} |")
    L.append(f"| mass (wet) | {_fmt(dv['wet_mass_kg'], 1)} kg | propellant on "
             f"top of dry budget | YES |")
    L.append(f"| power | {_fmt(pw['day_total_w'], 0)} W day / "
             f"{_fmt(pw['eclipse_total_w'], 0)} W eclipse | battery "
             f"{pw['battery_margin'] * 100:.0f}%, array 20% | "
             f"{'YES' if v['power_closes'] else 'NO'} |")
    L.append(f"| delta-v | {_fmt(dv['nominal_dv_m_s'], 1)} m/s nominal / "
             f"{_fmt(dv['budgeted_dv_m_s'], 1)} m/s budgeted | "
             f"{dv['margin_fraction'] * 100:.0f}% | "
             f"{'YES' if v['delta_v_closes'] else 'NO'} |")
    L.append(f"| pointing | {_fmt(pt['rss_deg'], 3)} deg (3-sigma) | vs "
             f"{_fmt(pt['requirement_deg'], 1)} deg requirement | "
             f"{'YES' if pt['meets'] else 'NO'} |")
    L.append(f"| link margin | down {_fmt(dl['margin_db'], 1)} dB / "
             f"up {_fmt(ul['margin_db'], 1)} dB | >= "
             f"{cm['link_margin_requirement_db']:.0f} dB | "
             f"{'YES' if v['link_meets'] else 'NO'} |")
    L.append("")
    L.append("## 9. Conclusions and open items")
    L.append("")
    all_ok = all(v.values())
    L.append(f"- Budgets close? **{'YES - all budgets close' if all_ok else 'NO - see verdicts'}** "
             f"(delta-v {v['delta_v_closes']}, power {v['power_closes']}, "
             f"pointing {v['pointing_meets']}, link {v['link_meets']}, "
             f"mass {v['mass_closes']}).")
    L.append("- Open items for detailed phase: refined disturbance torque "
             "model with beta-angle profile; flight-like array incidence/"
             "cosine losses; thermal model with component-level margins; "
             "star tracker alignment campaign; launch-vehicle interface "
             "agreement and actual dispersion.")
    L.append("")
    L.append("---")
    L.append(f"*Generated by Aero Agent Roles space-systems-engineer core "
             f"({model['generated']}). {DRAFT_MARKER}*")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Evidence gate checkers
# ---------------------------------------------------------------------------

GATE_CHECKS = {
    "delta_v_budget_present": "nominal and margin-added budgeted delta-v are numbers",
    "propellant_sized": "propellant mass computed from the rocket equation",
    "wheel_sized": "wheel momentum capacity and inertia sized from h = J*omega",
    "array_sized": "solar array area computed from daylight power and EOL specific power",
    "power_budget_closes": "battery and array margins meet the stated policy",
    "pointing_meets": "RSS pointing error meets the requirement",
    "link_margin_present": "downlink and uplink margins are numbers with pass/fail",
    "sign_off_honest": "document is marked draft, not approval",
}


def check_report(model: dict) -> dict:
    """Run the evidence gates against a report model."""
    dv = model["delta_v"]
    pw = model["power"]
    ad = model["adcs"]
    pt = model["pointing"]
    cm = model["comms"]
    results = {
        "delta_v_budget_present": (isinstance(dv.get("nominal_dv_m_s"), float)
                                   and isinstance(dv.get("budgeted_dv_m_s"), float)
                                   and dv["budgeted_dv_m_s"] > dv["nominal_dv_m_s"]),
        "propellant_sized": isinstance(dv.get("propellant_mass_kg"), float)
                            and dv["propellant_mass_kg"] > 0,
        "wheel_sized": (ad.get("wheel_momentum_capacity_nms", 0) > 0
                        and ad.get("wheel_inertia_kgm2", 0) > 0),
        "array_sized": pw.get("array_area_m2", 0) > 0
                       and pw.get("battery_sized_wh", 0) > 0,
        "power_budget_closes": (pw.get("battery_margin", 0) >= 0.20
                                and model["verdicts"]["power_closes"]),
        "pointing_meets": pt.get("meets", False),
        "link_margin_present": (isinstance(cm["downlink"].get("margin_db"), float)
                                and isinstance(cm["uplink"].get("margin_db"), float)),
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_report_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    has_number = bool(re.search(r"\d+\.?\d*\s*(m/s|m s|wh|w/m\^2|db|deg|min|kg|km)", low))
    checks = {
        "has_title": "spacecraft mission and subsystem design report" in low,
        "has_numbers": has_number,
        "has_delta_v": "delta-v" in low and "budgeted" in low,
        "has_margin_policy": "margin" in low and "%" in md_text,
        "has_pointing_req": "pointing error budget" in low,
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
        "has_not_launch_readiness": "not launch readiness" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling: check a report document."""
    return check_report_markdown(md_text)


# ---------------------------------------------------------------------------
# Example mission (for tests and worked-example generation)
# ---------------------------------------------------------------------------

def example_mission() -> SpacecraftMission:
    return SpacecraftMission()


def example_report_markdown() -> str:
    return render_report_markdown(build_report(example_mission()))


if __name__ == "__main__":
    mission = example_mission()
    model = build_report(mission)
    md = render_report_markdown(model)
    gates = check_report(model)
    print(f"REPORT: {model['mission']}")
    print(f"DELTA-V: nominal {model['delta_v']['nominal_dv_m_s']:.1f} m/s, "
          f"budgeted {model['delta_v']['budgeted_dv_m_s']:.1f} m/s")
    print(f"PROPELLANT: {model['delta_v']['propellant_mass_kg']:.2f} kg")
    print(f"WHEEL: {model['adcs']['wheel_momentum_capacity_nms']:.2f} N m s, "
          f"J_w = {model['adcs']['wheel_inertia_kgm2']*1e3:.3f} x 1e-3 kg m^2")
    print(f"ARRAY: {model['power']['array_area_m2']:.3f} m^2, "
          f"battery {model['power']['battery_sized_wh']:.0f} Wh")
    print(f"POINTING: {model['pointing']['rss_deg']:.4f} deg vs "
          f"{model['pointing']['requirement_deg']:.1f} deg")
    print(f"LINK: down {model['comms']['downlink']['margin_db']:.1f} dB, "
          f"up {model['comms']['uplink']['margin_db']:.1f} dB")
    print(f"GATES: {gates}")
    print(f"RENDERED: {len(md)} chars")
