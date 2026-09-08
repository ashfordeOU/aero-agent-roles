#!/usr/bin/env python3
"""dispatch-audit.py — cross-check every role core against its bound
AeroSkills logic where a matching computation exists.

This is the compounding power verification: as the skills repo grows
logic files, more role computations become cross-checkable. Each row
records: core value, skill value, delta, agrees. Roles with no
dispatchable pair (or no AeroSkills present) report honestly.

The dispatch map is explicit per role: (leaf, skill module fn, core
module fn, kwargs for both, param-name translation when signatures
differ). Extend the map as more pairs are identified.

Usage: python3 scripts/dispatch-audit.py [--json]
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import sys

ROLES_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_ROOT = os.environ.get("AEROSKILLS_DEV", os.path.expanduser("~/AeroSkills"))


def load_core(role_slug: str):
    """Load role core via sys.path (same way role tests import it)."""
    core_dir = os.path.join(ROLES_ROOT, "roles", role_slug, "core")
    files = [f for f in os.listdir(core_dir) if f.endswith("_core.py")]
    if not files:
        return None
    mod_name = files[0][:-3]
    sys.path.insert(0, core_dir)
    try:
        mod = importlib.import_module(mod_name)
        return mod
    except Exception:
        return None


def load_skill_logic(leaf: str, fn_name: str):
    logic_dir = os.path.join(SKILLS_ROOT, "skills", leaf, "scripts")
    if not os.path.isdir(logic_dir):
        return None
    for lf in sorted(os.listdir(logic_dir)):
        if lf.endswith(".py") and not lf.startswith("test_"):
            spec = importlib.util.spec_from_file_location(
                "skill_logic", os.path.join(logic_dir, lf))
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
            except Exception:
                continue
            if hasattr(mod, fn_name):
                return mod
    return None


# dispatch map: role -> list of cross-check pairs.
# Each pair: leaf (skill leaf), skill_fn, core_fn (name in role core),
# kwargs (values), skill_param_map (core kwarg -> skill kwarg when names
# differ), tolerance. Only pairs verified to exist in BOTH modules.
DISPATCH_MAP = {
    "aircraft-systems-sizing-engineer": [
        {
            "leaf": "vehicle-design/sizing/aircraft-electrical-load-analysis",
            "skill_fn": "load_fraction",
            "core_fn": "load_fraction",
            "kwargs": {"continuous_kva": 54.35, "installed_kva": 180.0},
            "skill_param_map": {},
        },
        {
            "leaf": "vehicle-design/sizing/air-cycle-machine-sizing",
            "skill_fn": "required_bleed_flow",
            "core_fn": "required_bleed_flow",
            "kwargs": {"q_load": 7133.611867836247, "t4_effective": 280.0,
                       "target_t": 288.0},
            "skill_param_map": {},
        },
        {
            "leaf": "vehicle-design/sizing/fuel-jettison-sizing",
            "skill_fn": "required_jettison_rate",
            "core_fn": "required_jettison_rate",
            "kwargs": {"mtow_kg": 79000.0, "mlw_kg": 66000.0},
            "skill_param_map": {},
        },
        {
            "leaf": "vehicle-design/sizing/tire-sizing",
            "skill_fn": "tire_diameter_inches",
            "core_fn": "tire_diameter_inches",
            "kwargs": {"load_lb": 39187.0},
            "skill_param_map": {},
        },
        {
            "leaf": "vehicle-design/sizing/window-aperture-sizing",
            "skill_fn": "pane_thickness",
            "core_fn": "pane_thickness",
            "kwargs": {"pressure_pa": 73907.0, "radius_m": 0.145,
                       "allowable_stress_pa": 40e6},
            "skill_param_map": {},
        },
        {
            "leaf": "vehicle-design/sizing/landing-gear-layout",
            "skill_fn": "tipback_angle",
            "core_fn": "tipback_angle",
            "kwargs": {"h_cg": 1.8, "x_mg": 15.0, "x_cg_aft": 14.3},
            "skill_param_map": {},
        },
    ],
    "flight-mechanics-engineer": [
        {
            "leaf": "flight-mechanics/performance/breguet-range",
            "skill_fn": "breguet_range",
            "core_fn": "breguet_range",
            "kwargs": {"v_ms": 235.0, "tsfc_kg_per_n_s": 1.5e-5,
                       "ld": 18.0, "m0_kg": 70000.0, "m1_kg": 50000.0},
            "skill_param_map": {},
        },
    ],
    "structures-loads-engineer": [
        {
            "leaf": "structures/loads/gust-maneuver-loads",
            "skill_fn": "gust_alleviation_factor",
            "core_fn": "gust_alleviation_factor",
            "kwargs": {"ws": 100.0, "cbar": 11.18, "a": 5.7,
                       "rho": 0.0023769},
            "skill_param_map": {},
        },
    ],
    "guidance-engineer": [
        {
            "leaf": "gnc-autonomy/guidance/proportional-navigation",
            "skill_fn": "commanded_acceleration",
            "core_fn": "commanded_acceleration",
            "kwargs": {"rx": 1000.0, "ry": 100.0, "vx": -200.0, "vy": 0.0,
                       "n_nav": 4.0},
            "skill_param_map": {},
        },
        {
            "leaf": "gnc-autonomy/guidance/augmented-proportional-navigation",
            "skill_fn": "apn_command",
            "core_fn": "apn_command",
            "kwargs": {"navigation_ratio": 4.0,
                       "closing_velocity": 199.007438041998,
                       "los_rate": 0.019801980198,
                       "target_lateral_accel": 20.0},
            "skill_param_map": {},
        },
        {
            "leaf": "gnc-autonomy/guidance/pursuit-guidance",
            "skill_fn": "heading_error",
            "core_fn": "heading_error",
            "kwargs": {"psi": 0.0, "rx": 1000.0, "ry": 100.0},
            "skill_param_map": {},
        },
    ],
    "state-estimation-engineer": [
        {
            "leaf": "gnc-autonomy/estimation-filtering/complementary-filter",
            "skill_fn": "steady_state_verdict",
            "core_fn": "steady_state_verdict",
            "kwargs": {"innovation_norms": [5e-4, 3e-4, 2e-4, 1e-4],
                       "tolerance": 1e-3},
            "skill_param_map": {},
        },
        {
            "leaf": "gnc-autonomy/estimation-filtering/unscented-kalman-filter",
            "skill_fn": "nees",
            "core_fn": "nees",
            "kwargs": {"x_est": [300.0, 40.0],
                       "p_est": [[100.0, 0.0], [0.0, 100.0]],
                       "x_true": [295.0, 42.0]},
            "skill_param_map": {},
        },
        {
            "leaf": "gnc-autonomy/estimation-filtering/particle-filter",
            "skill_fn": "effective_sample_size",
            "core_fn": "effective_sample_size",
            "kwargs": {"weights": [0.25, 0.25, 0.25, 0.25]},
            "skill_param_map": {},
        },
    ],
    "ndt-engineer": [
        {
            "leaf": "manufacturing-quality/ndt/ndt-method-selection",
            "skill_fn": "sensitivity_rank",
            "core_fn": "sensitivity_rank",
            "kwargs": {"method": "UT"},
            "skill_param_map": {},
        },
        {
            "leaf": "manufacturing-quality/ndt/eddy-current-inspection",
            "skill_fn": "standard_depth_of_penetration",
            "core_fn": "standard_depth_of_penetration",
            "kwargs": {"frequency": 1e5, "conductivity": 5.8e7},
            "skill_param_map": {},
        },
        {
            "leaf": "manufacturing-quality/ndt/eddy-current-inspection",
            "skill_fn": "select_frequency_for_flaw",
            "core_fn": "select_frequency_for_flaw",
            "kwargs": {"flaw_depth": 1e-3, "conductivity": 1.74e7,
                       "penetration_factor": 2.0},
            "skill_param_map": {},
        },
        {
            "leaf": "manufacturing-quality/ndt/liquid-penetrant-inspection",
            "skill_fn": "capillary_pressure",
            "core_fn": "capillary_pressure",
            "kwargs": {"surface_tension": 0.032, "contact_angle_deg": 5.0,
                       "radius": 1e-6},
            "skill_param_map": {},
        },
        {
            "leaf": "manufacturing-quality/ndt/liquid-penetrant-inspection",
            "skill_fn": "dwell_time_for_depth",
            "core_fn": "dwell_time_for_depth",
            "kwargs": {"depth": 1e-3, "surface_tension": 0.032,
                       "contact_angle_deg": 5.0, "viscosity": 0.008,
                       "radius": 1e-6},
            "skill_param_map": {},
        },
        {
            "leaf": "manufacturing-quality/ndt/radiographic-inspection",
            "skill_fn": "geometric_unsharpness",
            "core_fn": "geometric_unsharpness",
            "kwargs": {"focal_spot_mm": 3.0, "sod_mm": 500.0, "odd_mm": 30.0},
            "skill_param_map": {},
        },
        {
            "leaf": "manufacturing-quality/ndt/radiographic-inspection",
            "skill_fn": "iqi_sensitivity_percent",
            "core_fn": "iqi_sensitivity_percent",
            "kwargs": {"visible_thickness_mm": 0.6, "part_thickness_mm": 30.0},
            "skill_param_map": {},
        },
        {
            "leaf": "manufacturing-quality/ndt/computed-tomography",
            "skill_fn": "tube_energy_kv",
            "core_fn": "tube_energy_kv",
            "kwargs": {"material": "aluminum", "thickness_mm": 50.0},
            "skill_param_map": {},
        },
        {
            "leaf": "manufacturing-quality/ndt/computed-tomography",
            "skill_fn": "void_diameter",
            "core_fn": "void_diameter",
            "kwargs": {"void_voxels": 64000, "voxel_size_m": 1e-4},
            "skill_param_map": {},
        },
        {
            "leaf": "manufacturing-quality/ndt/magnetic-particle-inspection",
            "skill_fn": "head_shot_current",
            "core_fn": "head_shot_current",
            "kwargs": {"diameter_in": 2.0, "amperes_per_inch": 800.0},
            "skill_param_map": {},
        },
        {
            "leaf": "manufacturing-quality/ndt/leak-testing",
            "skill_fn": "pressure_decay_rate",
            "core_fn": "pressure_decay_rate",
            "kwargs": {"volume_L": 5.0, "dP_bar": 0.02, "time_s": 600.0},
            "skill_param_map": {},
        },
        {
            "leaf": "manufacturing-quality/ndt/shearography-inspection",
            "skill_fn": "strain_from_phase",
            "core_fn": "strain_from_phase",
            "kwargs": {"phase_rad": 0.5, "shear_mm": 5.0},
            "skill_param_map": {},
        },
        {
            "leaf": "manufacturing-quality/ndt/acoustic-emission-inspection",
            "skill_fn": "felicity_ratio",
            "core_fn": "felicity_ratio",
            "kwargs": {"resume_load": 0.85, "previous_max_load": 1.0},
            "skill_param_map": {},
        },
    ],
    "quality-management-engineer": [
        {
            "leaf": "manufacturing-quality/as9100/measurement-systems-analysis",
            "skill_fn": "number_distinct_categories",
            "core_fn": "number_distinct_categories",
            "kwargs": {"pv": 0.04677, "grr": 0.0052},
            "skill_param_map": {},
        },
        {
            "leaf": "manufacturing-quality/as9100/gage-linearity-bias-study",
            "skill_fn": "mean_bias",
            "core_fn": "mean_bias",
            "kwargs": {"biases": [0.004, 0.012, 0.021, 0.030, 0.042]},
            "skill_param_map": {},
        },
        {
            "leaf": "manufacturing-quality/as9100/attribute-agreement-analysis",
            "skill_fn": "percent_agreement",
            "core_fn": "percent_agreement",
            "kwargs": {"table": [[23, 4], [2, 1]]},
            "skill_param_map": {},
        },
        {
            "leaf": "manufacturing-quality/as9100/statistical-process-control",
            "skill_fn": "process_sigma",
            "core_fn": "process_sigma",
            "kwargs": {"rbar": 0.00875, "n": 5},
            "skill_param_map": {},
        },
        {
            "leaf": "manufacturing-quality/as9100/individuals-and-moving-range-chart",
            "skill_fn": "mean",
            "core_fn": "mean",
            "kwargs": {"values": [119.6, 120.8, 121.3, 119.9, 120.5,
                                  121.1, 120.2, 119.8, 120.9, 121.0]},
            "skill_param_map": {},
        },
        {
            "leaf": "manufacturing-quality/as9100/acceptance-sampling",
            "skill_fn": "oc_acceptance_probability",
            "core_fn": "oc_acceptance_probability",
            "kwargs": {"n": 80, "ac": 2, "p": 0.01},
            "skill_param_map": {},
        },
        {
            "leaf": "manufacturing-quality/as9100/variables-acceptance-sampling",
            "skill_fn": "form_q_upper",
            "core_fn": "form_q_upper",
            "kwargs": {"usl": 25.150, "xbar": 25.102, "s": 0.0098},
            "skill_param_map": {},
        },
    ],
    "mbse-modeling-engineer": [
        {
            "leaf": "systems-engineering-safety/mbse/requirements-modeling",
            "skill_fn": "count_shall_clauses",
            "core_fn": "count_shall_clauses",
            "kwargs": {"text": "The CPCS shall maintain cabin pressure "
                               "altitude at or below 8000 feet during "
                               "normal cruise operation."},
            "skill_param_map": {},
        },
        {
            "leaf": "systems-engineering-safety/mbse/n2-diagram",
            "skill_fn": "total_interfaces",
            "core_fn": "total_interfaces",
            "kwargs": {
                "elements": ["Cabin Pressure Controller",
                             "Outflow Valve Assembly",
                             "Safety Valve Assembly",
                             "Pressure Sensor Package"],
                "matrix": [[0, 1, 0, 0],
                           [1, 0, 0, 0],
                           [1, 0, 0, 0],
                           [1, 0, 0, 0]],
            },
            "skill_param_map": {},
        },
        {
            "leaf": "systems-engineering-safety/mbse/trade-study-analysis",
            "skill_fn": "weighted_score",
            "core_fn": "weighted_score",
            "kwargs": {"weights": [0.5, 0.3, 0.2], "scores": [8, 6, 9]},
            "skill_param_map": {},
        },
    ],
    "rocket-propulsion-engineer": [
        {
            "leaf": "propulsion/rocket/nozzle-design",
            "skill_fn": "mass_flow",
            "core_fn": "mass_flow",
            "kwargs": {"p0_pa": 7.0e6, "t0_k": 3500.0, "a_throat_m2": 0.02,
                       "gamma": 1.2, "r_j_kgk": 350.0},
            "skill_param_map": {},
        },
        {
            "leaf": "propulsion/rocket/rocket-sizing",
            "skill_fn": "rocket_equation_delta_v",
            "core_fn": "rocket_equation_delta_v",
            "kwargs": {"isp_s": 300.0, "m0_kg": 100000.0, "mf_kg": 50000.0},
            "skill_param_map": {},
        },
        {
            "leaf": "propulsion/rocket/rocket-staging",
            "skill_fn": "structural_index",
            "core_fn": "structural_index",
            "kwargs": {"structure_kg": 10000.0, "propellant_kg": 90000.0},
            "skill_param_map": {},
        },
        {
            "leaf": "propulsion/rocket/rocket-engine-cycle",
            "skill_fn": "pump_power",
            "core_fn": "pump_power",
            "kwargs": {"mdot_prop": 100.0, "p_discharge": 12.0e6,
                       "p_inlet": 0.3e6, "rho_prop": 1140.0,
                       "eta_pump": 0.7},
            "skill_param_map": {},
        },
        {
            "leaf": "propulsion/rocket/combustion-chamber-design",
            "skill_fn": "theoretical_cstar",
            "core_fn": "theoretical_cstar",
            "kwargs": {"chamber_temp": 3670.0, "molecular_weight": 23.0,
                       "gamma": 1.2},
            "skill_param_map": {},
        },
        {
            "leaf": "propulsion/rocket/solid-rocket-motor",
            "skill_fn": "equilibrium_chamber_pressure",
            "core_fn": "equilibrium_chamber_pressure",
            "kwargs": {"rho_p": 1800.0, "a": 2.0e-5, "n": 0.35,
                       "A_b": 180.5, "A_t": 0.361, "c_star": 1600.0},
            "skill_param_map": {},
        },
        {
            "leaf": "propulsion/rocket/thrust-chamber-cooling",
            "skill_fn": "bartz_hot_gas_coefficient",
            "core_fn": "bartz_hot_gas_coefficient",
            "kwargs": {"chamber_pressure_pa": 7.0e6, "cstar_m_s": 1750.0,
                       "throat_diameter_m": 0.15, "mu_gas": 8.0e-5,
                       "cp_gas": 2000.0, "prandtl_gas": 0.72},
            "skill_param_map": {},
        },
        {
            "leaf": "propulsion/rocket/cold-gas-thruster",
            "skill_fn": "choked_mass_flow",
            "core_fn": "choked_mass_flow",
            "kwargs": {"pressure": 25.0e6, "temperature": 300.0,
                       "throat_area": 7.854e-7, "gamma": 1.4,
                       "gas_const": 296.8},
            "skill_param_map": {},
        },
        {
            "leaf": "propulsion/rocket/hybrid-rocket-motor",
            "skill_fn": "regression_rate",
            "core_fn": "regression_rate",
            "kwargs": {"g_o": 200.0, "fuel": "HTPB-N2O"},
            "skill_param_map": {},
        },
        {
            "leaf": "propulsion/rocket/injector-design",
            "skill_fn": "orifice_count",
            "core_fn": "orifice_count",
            "kwargs": {"total_mass_flow_kgs": 0.4,
                       "per_orifice_mass_flow_kgs": 0.1},
            "skill_param_map": {},
        },
        {
            "leaf": "propulsion/rocket/propellant-selection",
            "skill_fn": "density_impulse",
            "core_fn": "density_impulse",
            "kwargs": {"isp_s": 300.0, "bulk_density_kg_m3": 1000.0},
            "skill_param_map": {},
        },
        {
            "leaf": "propulsion/rocket/rocket-gravity-loss",
            "skill_fn": "gravity_loss_pitched",
            "core_fn": "gravity_loss_pitched",
            "kwargs": {"burn_time_s": 190.0, "mean_path_angle_deg": 45.0},
            "skill_param_map": {},
        },
        {
            "leaf": "propulsion/rocket/rocket-nozzle-flow-separation",
            "skill_fn": "separation_mach",
            "core_fn": "separation_mach",
            "kwargs": {"pc": 10.0e6, "p_sep": 40530.0, "gamma": 1.2},
            "skill_param_map": {},
        },
        {
            "leaf": "propulsion/rocket/thrust-vector-control",
            "skill_fn": "side_force",
            "core_fn": "side_force",
            "kwargs": {"thrust": 4105.0e3, "deflection_rad": 0.0873},
            "skill_param_map": {},
        },
    ],
    "navigation-engineer": [
        {
            "leaf": "gnc-autonomy/navigation/inertial-navigation",
            "skill_fn": "deg_per_hour_to_rad_s",
            "core_fn": "deg_per_hour_to_rad_s",
            "kwargs": {"deg_per_hour": 0.01},
            "skill_param_map": {},
        },
        {
            "leaf": "gnc-autonomy/navigation/inertial-navigation",
            "skill_fn": "accel_bias_position_error",
            "core_fn": "accel_bias_position_error",
            "kwargs": {"bias": 1e-3, "t": 60.0},
            "skill_param_map": {},
        },
        {
            "leaf": "gnc-autonomy/navigation/gnss-carrier-smoothing",
            "skill_fn": "alpha_from_time_constant",
            "core_fn": "hatch_alpha",
            "kwargs": {"tau": 100.0, "big_t": 1.0},
            "skill_param_map": {"big_t": "T"},
        },
        {
            "leaf": "gnc-autonomy/navigation/gnss-raim-fde",
            "skill_fn": "normal_quantile",
            "core_fn": "normal_quantile",
            "kwargs": {"p": 0.99999},
            "skill_param_map": {},
        },
        {
            "leaf": "gnc-autonomy/navigation/gnss-raim-fde",
            "skill_fn": "chi2_quantile",
            "core_fn": "chi2_quantile",
            "kwargs": {"df": 2, "p": 0.99999},
            "skill_param_map": {},
        },
        {
            "leaf": "gnc-autonomy/navigation/bearing-only-localization",
            "skill_fn": "geometry_dilution_factor",
            "core_fn": "geometry_dilution_factor",
            "kwargs": {"observers": [(0.0, 0.0), (1800.0, 200.0),
                                      (900.0, 1600.0)],
                       "bearings_deg": [36.384351815835885,
                                        149.53445508054014,
                                        273.1798301198642]},
            "skill_param_map": {},
        },
    ],
    "boundary-layer-engineer": [
        {
            "leaf": "aerodynamics/boundary-layer/mangler-axisymmetric-transform",
            "skill_fn": "mangler_xi",
            "core_fn": "mangler_xi",
            "kwargs": {"x_m": 2.0, "half_angle_deg": 8.0,
                       "ref_length_m": 5.0},
            "skill_param_map": {"x_m": "x", "ref_length_m": "ref_length"},
        },
        {
            "leaf": "aerodynamics/boundary-layer/squire-young-profile-drag",
            "skill_fn": "squire_young_profile_drag",
            "core_fn": "squire_young_profile_drag",
            "kwargs": {"theta_te_m": 0.00023069990401880476, "c_m": 0.65,
                       "u_te_ms": 79.0, "u_inf_ms": 79.0},
            "skill_param_map": {"theta_te_m": "theta_te", "c_m": "chord",
                                "u_te_ms": "u_te", "u_inf_ms": "u_inf"},
        },
        {
            "leaf": "aerodynamics/boundary-layer/rough-wall-skin-friction",
            "skill_fn": "smooth_turbulent_cf",
            "core_fn": "smooth_turbulent_cf",
            "kwargs": {"re_x": 2.0e6},
            "skill_param_map": {},
        },
        {
            "leaf": "aerodynamics/boundary-layer/stokes-creeping-flow-drag",
            "skill_fn": "stokes_drag",
            "core_fn": "stokes_drag",
            "kwargs": {"mu_pas": 1.7885e-5, "a_m": 1.0e-4, "u_ms": 0.01},
            "skill_param_map": {"mu_pas": "mu", "a_m": "a", "u_ms": "U"},
        },
        {
            "leaf": "aerodynamics/boundary-layer/laminar-far-wake",
            "skill_fn": "wake_spread_parameter",
            "core_fn": "wake_spread_parameter",
            "kwargs": {"u_ms": 30.0, "nu_m2s": 1.46e-5, "x_m": 1.0},
            "skill_param_map": {"u_ms": "U", "nu_m2s": "nu", "x_m": "x"},
        },
        {
            "leaf": "aerodynamics/boundary-layer/unsteady-laminar-stokes-layers",
            "skill_fn": "stokes_penetration_depth",
            "core_fn": "stokes_penetration_depth",
            "kwargs": {"nu_m2s": 1.46e-5,
                       "omega_rads": 2.0 * math.pi * 20.0},
            "skill_param_map": {"nu_m2s": "nu", "omega_rads": "omega"},
        },
        {
            "leaf": "aerodynamics/boundary-layer/boundary-layer-transition",
            "skill_fn": "michel_threshold",
            "core_fn": "michel_threshold",
            "kwargs": {"re_x": 2.0e6},
            "skill_param_map": {},
        },
        {
            "leaf": "aerodynamics/boundary-layer/boundary-layer-theory",
            "skill_fn": "shape_factor",
            "core_fn": "shape_factor",
            "kwargs": {"delta_star_m": 1.7208e-3, "theta_m": 0.664e-3},
            "skill_param_map": {"delta_star_m": "delta_star",
                                "theta_m": "theta"},
        },
    ],
    "autopilot-control-engineer": [
        {
            "leaf": "gnc-autonomy/control/l1-adaptive-control",
            "skill_fn": "control_output",
            "core_fn": "l1_control_output",
            "kwargs": {"nu": 0.5, "r": 1.0, "a_m": -2.0, "b": 1.0},
            "skill_param_map": {},
        },
        {
            "leaf": "gnc-autonomy/control/l1-adaptive-control",
            "skill_fn": "sigma_true",
            "core_fn": "l1_sigma_true",
            "kwargs": {"x": 1.0, "plant_a": -1.0, "a_m": -2.0, "b": 1.0,
                       "d": 1.0},
            "skill_param_map": {},
        },
        {
            "leaf": "gnc-autonomy/control/root-locus-design",
            "skill_fn": "damping_ratio",
            "core_fn": "damping_ratio_rl",
            "kwargs": {"a": 2.857, "K": 4.0812245},
            "skill_param_map": {},
        },
        {
            "leaf": "gnc-autonomy/control/root-locus-design",
            "skill_fn": "gain_for_damping",
            "core_fn": "gain_for_damping_rl",
            "kwargs": {"a": 2.857, "zeta": 0.7071067811865476},
            "skill_param_map": {},
        },
        {
            "leaf": "gnc-autonomy/control/state-space-analysis",
            "skill_fn": "is_controllable",
            "core_fn": "controllable_2state",
            "kwargs": {"A": [[0.0, 1.0], [-51.84, -8.64]],
                       "B": [[0.0], [5.0]]},
            "skill_param_map": {},
        },
        {
            "leaf": "gnc-autonomy/control/gain-scheduling",
            "skill_fn": "schedule_gain",
            "core_fn": "schedule_gain",
            "kwargs": {"table": [(100.0, 10.0), (200.0, 20.0),
                                  (300.0, 15.0)], "x": 150.0},
            "skill_param_map": {"x": "sched_var_value"},
        },
    ],
    "safety-assessment-engineer": [
        {
            "leaf": "systems-engineering-safety/arp4761a/fta-fmea",
            "skill_fn": "cut_set_probability",
            "core_fn": "fta_cut_set_probability",
            "kwargs": {"cut_set": frozenset({"E_CH_A", "E_CH_B"}),
                       "probs": {"E_CH_A": 1e-5, "E_CH_B": 1e-5,
                                 "E_CCF": 2e-10}},
            "skill_param_map": {},
        },
        {
            "leaf": "systems-engineering-safety/arp4761a/fault-tree-importance-measures",
            "skill_fn": "top_event_probability",
            "core_fn": "fta_top_probability",
            "kwargs": {"cut_sets": [{"E_CH_A", "E_CH_B"}, {"E_CCF"}],
                       "probs": {"E_CH_A": 1e-5, "E_CH_B": 1e-5,
                                 "E_CCF": 2e-10}},
            "skill_param_map": {},
        },
        {
            "leaf": "systems-engineering-safety/arp4761a/failure-mode-criticality",
            "skill_fn": "item_criticality",
            "core_fn": "fmea_item_criticality",
            "kwargs": {
                "modes": [{"id": "M1", "alpha": 0.5, "beta": 1.0},
                          {"id": "M2", "alpha": 0.3, "beta": 1.0},
                          {"id": "M3", "alpha": 0.2, "beta": 0.5}],
                "item_failure_rate": 1e-5, "operating_time": 1.0},
            "skill_param_map": {},
        },
        {
            "leaf": "systems-engineering-safety/arp4761a/functional-hazard-assessment",
            "skill_fn": "target_met",
            "core_fn": "target_met",
            "kwargs": {"severity": "Catastrophic",
                       "probability_per_fh": 5e-10},
            "skill_param_map": {},
        },
        {
            "leaf": "systems-engineering-safety/arp4761a/ssa-closure",
            "skill_fn": "severity_target",
            "core_fn": "severity_target",
            "kwargs": {"severity": "catastrophic"},
            "skill_param_map": {},
        },
    ],
}


def run() -> int:
    results = []
    for role_slug in sorted(DISPATCH_MAP):
        core_mod = load_core(role_slug)
        if core_mod is None:
            results.append({"role": role_slug, "error": "core not loadable"})
            continue
        role_rows = []
        for pair in DISPATCH_MAP[role_slug]:
            skill_mod = load_skill_logic(pair["leaf"], pair["skill_fn"])
            if skill_mod is None:
                role_rows.append({
                    "leaf": pair["leaf"], "dispatched": False,
                    "reason": "skill logic unavailable"})
                continue
            core_fn = getattr(core_mod, pair["core_fn"], None)
            if core_fn is None:
                role_rows.append({
                    "leaf": pair["leaf"], "dispatched": False,
                    "reason": "core fn missing"})
                continue
            try:
                # call core with its params
                core_val = core_fn(**pair["kwargs"])
                # call skill, translating param names
                skill_kwargs = dict(pair["kwargs"])
                for core_k, skill_k in pair.get("skill_param_map", {}).items():
                    if core_k in skill_kwargs:
                        skill_kwargs[skill_k] = skill_kwargs.pop(core_k)
                skill_val = getattr(skill_mod, pair["skill_fn"])(**skill_kwargs)
                delta = abs(float(core_val) - float(skill_val))
                role_rows.append({
                    "leaf": pair["leaf"],
                    "function": pair["skill_fn"],
                    "dispatched": True,
                    "core_value": round(float(core_val), 6),
                    "skill_value": round(float(skill_val), 6),
                    "delta": round(delta, 9),
                    "agrees": delta <= pair.get("tolerance", 1e-6),
                })
            except Exception as e:
                role_rows.append({
                    "leaf": pair["leaf"], "dispatched": True,
                    "error": str(e)[:150], "agrees": False})
        results.append({"role": role_slug, "checks": role_rows})

    if "--json" in sys.argv:
        print(json.dumps(results, indent=1))
    else:
        for r in results:
            for c in r.get("checks", []):
                if c.get("dispatched") and "error" not in c:
                    mark = "AGREE" if c["agrees"] else "DISAGREE"
                    print(f"{r['role']}: {c['leaf']} {mark} "
                          f"core={c['core_value']} skill={c['skill_value']} "
                          f"delta={c['delta']}")
                else:
                    print(f"{r['role']}: {c.get('leaf')} not dispatched "
                          f"({c.get('reason', c.get('error', '?'))})")
    return 0


if __name__ == "__main__":
    sys.exit(run())
