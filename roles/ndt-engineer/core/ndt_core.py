#!/usr/bin/env python3
"""ndt_core.py - NDT Engineer executable core.

This is the role's ENGINE: given an aerospace part's project facts it
selects non-destructive testing (NDT) methods per candidate defect
class and material class, computes inspection parameters for the
selected methods, frames acceptance/disposition, checks NDT personnel
qualification, and BUILDS the Nondestructive Test Plan and Method
Selection Report content. It also gate-checks deliverables. Standalone:
no external repo needed.

Every formula below is mirrored from the bound AeroSkills leaf logic
(manufacturing-quality/ndt/*, same org, Apache-2.0):
  ndt-method-selection        decision table + sensitivity ranking
  eddy-current-inspection     penetration depth / frequency selection
  liquid-penetrant-inspection capillary + Washburn dwell math
  radiographic-inspection     density / IQI / unsharpness verdict
  computed-tomography         voxel / resolution / porosity math
  magnetic-particle-inspection magnetization + indication math
  leak-testing                decay rate / disposition math
  acoustic-emission-inspection hit/event/Felicity-ratio math
  shearography-inspection     strain / load / disposition math
  ndt-personnel-qualification recert / vision / level rules
Standards (AS9100D, NAS 410) are referenced, never reproduced; the
levels/intervals are documented paraphrase-safe defaults from the
bound leaves, and the governing qualified procedure always rules.
"""
from __future__ import annotations

import json  # noqa: F401  (kept: model round-trips in tests)
import math
import re
from dataclasses import dataclass, field
from datetime import date

# ---------------------------------------------------------------------------
# Domain tables (mirrored from the bound ndt-method-selection leaf logic)
# ---------------------------------------------------------------------------

DEFECT_CLASSES = ("surface", "near-surface", "internal")
MATERIAL_CLASSES = ("ferromagnetic", "non-ferromagnetic", "non-conductive")

# Decision table: defect class -> applicable methods. Surface defects also
# depend on the material class; internal/near-surface do not (leaf contract).
DECISION_TABLE = {
    "internal": ("RT", "UT"),
    "near-surface": ("ET", "UT"),
    "surface": {
        "ferromagnetic": ("MT", "PT"),
        "non-ferromagnetic": ("ET", "PT"),
        "non-conductive": ("PT",),
    },
}

SENSITIVITY_RANK = {"UT": 5, "RT": 4, "ET": 4, "MT": 3, "PT": 3}
COST_RANK = {"RT": 4, "UT": 3, "ET": 2, "MT": 2, "PT": 1}
TIE_ORDER = ("RT", "UT", "ET", "MT", "PT")

METHOD_NAMES = {
    "RT": "radiography (RT)",
    "UT": "ultrasonic testing (UT)",
    "ET": "eddy current testing (ET)",
    "PT": "liquid penetrant testing (PT)",
    "MT": "magnetic particle testing (MT)",
    "CT": "computed tomography (CT)",
}

# ---------------------------------------------------------------------------
# Personnel qualification tables (mirrored from ndt-personnel-qualification)
# ---------------------------------------------------------------------------

RECERT_INTERVAL_MONTHS_DEFAULT = 36  # NAS-410-style recertification norm
VISION_INTERVAL_MONTHS_DEFAULT = 12  # annual near-vision norm
PERSONNEL_LEVELS = ("i", "ii", "iii")

# Minimum certification level to perform / to interpret and disposition
# indications, per method (common aerospace practice paraphrase; the
# employer's written practice governs). Level I performs under a Level II
# or III supervisor; interpretation and written acceptance typically
# require Level II minimum. NAS 410 covers ET/UT/RT/PT/MT; CT and leak
# personnel follow employer written practice, modeled at the same
# Level II minimum.
PERFORM_LEVEL = {"ET": "i", "PT": "i", "RT": "i", "UT": "i", "MT": "i",
                 "CT": "ii", "LT": "ii"}
INTERPRET_LEVEL = {"ET": "ii", "PT": "ii", "RT": "ii", "UT": "ii",
                   "MT": "ii", "CT": "ii", "LT": "ii"}

_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _is_leap_year(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _days_in_month(year, month):
    if month == 2 and _is_leap_year(year):
        return 29
    return _MONTH_DAYS[month - 1]


def add_months_clamped(base_iso, months):
    """ISO date + months, day clamped to the target month end."""
    y, m, d = (int(p) for p in base_iso.split("-"))
    total = y * 12 + (m - 1) + months
    ny = total // 12
    nm = total % 12 + 1
    nd = min(d, _days_in_month(ny, nm))
    return date(ny, nm, nd).isoformat()


def recert_due_date(cert_date_iso,
                    interval_months=RECERT_INTERVAL_MONTHS_DEFAULT):
    return add_months_clamped(cert_date_iso, interval_months)


def vision_due_date(last_vision_iso,
                    interval_months=VISION_INTERVAL_MONTHS_DEFAULT):
    return add_months_clamped(last_vision_iso, interval_months)


def certification_status(cert_date_iso, recert_due_iso, vision_due_iso,
                         today_iso):
    """current | recert-due | vision-due | recert-and-vision-due."""
    recert_overdue = today_iso > recert_due_iso
    vision_overdue = today_iso > vision_due_iso
    if recert_overdue and vision_overdue:
        return "recert-and-vision-due"
    if recert_overdue:
        return "recert-due"
    if vision_overdue:
        return "vision-due"
    return "current"


def supervision_valid(operator_level, supervisor_level):
    op = operator_level.strip().lower()
    sup = supervisor_level.strip().lower()
    if op == "i":
        return sup in ("ii", "iii")
    return True


def level_meets(held_level, required_level):
    """True when held certification level meets the required level."""
    return PERSONNEL_LEVELS.index(held_level.strip().lower()) >= \
        PERSONNEL_LEVELS.index(required_level.strip().lower())


def upgrade_eligible(current_level, target_level, held_hours, required_hours,
                     held_months, required_months, exam_passed):
    if PERSONNEL_LEVELS.index(target_level) != \
            PERSONNEL_LEVELS.index(current_level) + 1:
        raise ValueError("upgrade target must be exactly one level above")
    return (held_hours >= required_hours and held_months >= required_months
            and bool(exam_passed))


def qualification_review(record, today_iso):
    """Full personnel-record review as one verdict dict (mirrors the leaf's
    qualification_review). record carries cert_date_iso, last_vision_iso,
    operator_level, supervisor_level and optional upgrade inputs."""
    recert_due = recert_due_date(record["cert_date_iso"])
    vision_due = vision_due_date(record["last_vision_iso"])
    status = certification_status(record["cert_date_iso"], recert_due,
                                  vision_due, today_iso)
    up = None
    up_in = record.get("upgrade_inputs")
    if up_in:
        up = upgrade_eligible(record["operator_level"], up_in["target_level"],
                              up_in["held_hours"], up_in["required_hours"],
                              up_in["held_months"], up_in["required_months"],
                              up_in["exam_passed"])
    return {
        "certification_status": status,
        "recert_due_date_iso": recert_due,
        "vision_due_date_iso": vision_due,
        "supervision_ok": supervision_valid(record["operator_level"],
                                            record["supervisor_level"]),
        "upgrade_eligible": up,
    }


# ---------------------------------------------------------------------------
# Method selection (mirrored from ndt-method-selection leaf logic)
# ---------------------------------------------------------------------------

def applicable_methods(defect_class, material_class):
    if defect_class not in DEFECT_CLASSES:
        raise ValueError("unknown defect class: %r" % (defect_class,))
    if material_class not in MATERIAL_CLASSES:
        raise ValueError("unknown material class: %r" % (material_class,))
    if defect_class == "surface":
        return sorted(DECISION_TABLE["surface"][material_class])
    return sorted(DECISION_TABLE[defect_class])


def sensitivity_rank(method):
    if method not in SENSITIVITY_RANK:
        raise ValueError("unknown method: %r" % (method,))
    return SENSITIVITY_RANK[method]


def cost_rank(method):
    if method not in COST_RANK:
        raise ValueError("unknown method: %r" % (method,))
    return COST_RANK[method]


def select_method(defect_class, material_class):
    """Pick the highest-sensitivity applicable method; ties by TIE_ORDER
    (later wins). Mirrors the ndt-method-selection leaf select_method."""
    applicable = applicable_methods(defect_class, material_class)
    top = max(applicable,
              key=lambda m: (SENSITIVITY_RANK[m], TIE_ORDER.index(m)))
    alternates = [m for m in applicable if m != top]
    return {
        "method": top,
        "alternates": alternates,
        "rationale": ("%s defect in %s material: %s is the "
                      "highest-sensitivity applicable method"
                      % (defect_class, material_class, top)),
    }


# ---------------------------------------------------------------------------
# Eddy current (ET) - mirrored from eddy-current-inspection leaf logic
# ---------------------------------------------------------------------------

MU0 = 4.0 * math.pi * 1e-7  # vacuum permeability, H/m
COPPER_100_IACS = 5.8e7     # S/m, 100 pct IACS reference


def conductivity_from_iacs(percent_iacs):
    return (percent_iacs / 100.0) * COPPER_100_IACS


def standard_depth_of_penetration(frequency, conductivity,
                                  relative_permeability=1.0):
    mu = MU0 * relative_permeability
    return 1.0 / math.sqrt(math.pi * frequency * mu * conductivity)


def frequency_for_depth(depth, conductivity, relative_permeability=1.0):
    mu = MU0 * relative_permeability
    return 1.0 / (math.pi * mu * conductivity * depth * depth)


def select_frequency_for_flaw(flaw_depth, conductivity,
                              relative_permeability=1.0,
                              penetration_factor=2.0):
    """Frequency that puts the standard depth of penetration at
    penetration_factor x flaw depth (>= 2 for subsurface flaws, < 1 for
    surface-flaw sharp response)."""
    return frequency_for_depth(penetration_factor * flaw_depth, conductivity,
                               relative_permeability)


def eddy_current_density_ratio(depth, delta):
    return math.exp(-depth / delta)


def phase_lag_degrees(depth, delta):
    return (depth / delta) * 180.0 / math.pi


def et_plan(flaw_depth_m, percent_iacs, penetration_factor,
            label="subsurface"):
    """One eddy-current parameter row: frequency, standard depth of
    penetration, density ratio and phase lag at the flaw depth."""
    sigma = conductivity_from_iacs(percent_iacs)
    f = select_frequency_for_flaw(flaw_depth_m, sigma,
                                  penetration_factor=penetration_factor)
    delta = standard_depth_of_penetration(f, sigma)
    return {
        "label": label,
        "flaw_depth_m": flaw_depth_m,
        "percent_iacs": percent_iacs,
        "conductivity_sm": sigma,
        "penetration_factor": penetration_factor,
        "frequency_hz": f,
        "delta_m": delta,
        "density_ratio_at_flaw": eddy_current_density_ratio(flaw_depth_m,
                                                            delta),
        "phase_lag_deg": phase_lag_degrees(flaw_depth_m, delta),
        "inputs": {"flaw_depth_m": flaw_depth_m,
                   "percent_iacs": percent_iacs,
                   "penetration_factor": penetration_factor},
    }


# ---------------------------------------------------------------------------
# Liquid penetrant (PT) - mirrored from liquid-penetrant-inspection leaf
# ---------------------------------------------------------------------------

GRAVITY = 9.80665


def _wetting_cos(contact_angle_deg):
    return math.cos(math.radians(contact_angle_deg))


def capillary_pressure(surface_tension, contact_angle_deg, radius):
    return 2.0 * surface_tension * _wetting_cos(contact_angle_deg) / radius


def washburn_penetration_depth(surface_tension, contact_angle_deg, viscosity,
                               radius, time):
    return math.sqrt(radius * surface_tension
                     * _wetting_cos(contact_angle_deg) * time
                     / (2.0 * viscosity))


def dwell_time_for_depth(depth, surface_tension, contact_angle_deg,
                         viscosity, radius):
    return (2.0 * viscosity * depth * depth
            / (radius * surface_tension * _wetting_cos(contact_angle_deg)))


def crack_radius_from_width(width):
    return width / 2.0


def bleed_out_width(flaw_width, bleed_factor):
    return flaw_width * bleed_factor


def bleed_out_ratio(indication_width, flaw_width):
    return indication_width / flaw_width


def developer_coverage_mass(area, areal_density):
    return area * areal_density


def contrast_ratio(background_reflectance, indication_reflectance):
    return (abs(background_reflectance - indication_reflectance)
            / max(background_reflectance, indication_reflectance))


def pt_plan(pt, part_area_m2):
    """One liquid-penetrant parameter row for the surface-crack zone.

    pt carries the penetrant properties and the crack/development facts
    (typical values documented in the bound leaf; the qualified penetrant
    system and procedure govern the real settings)."""
    gamma = pt["surface_tension_nm"]
    theta = pt["contact_angle_deg"]
    eta = pt["viscosity_pas"]
    crack_depth = pt["crack_depth_m"]
    opening = pt["crack_opening_width_m"]
    dwell_ref = pt.get("reference_dwell_s", 300.0)
    areal = pt.get("developer_areal_density_kgm2", 0.15)
    bleed = pt.get("bleed_factor", 4.0)
    radius = crack_radius_from_width(opening)
    depth_ref = washburn_penetration_depth(gamma, theta, eta, radius,
                                           dwell_ref)
    t_fill = dwell_time_for_depth(crack_depth, gamma, theta, eta, radius)
    indication_w = bleed_out_width(opening, bleed)
    return {
        "surface_tension_nm": gamma,
        "contact_angle_deg": theta,
        "viscosity_pas": eta,
        "crack_depth_m": crack_depth,
        "crack_opening_width_m": opening,
        "effective_capillary_radius_m": radius,
        "capillary_pressure_pa": capillary_pressure(gamma, theta, radius),
        "washburn_depth_at_reference_s_m": depth_ref,
        "reference_dwell_s": dwell_ref,
        "dwell_time_to_fill_s": t_fill,
        "bleed_factor": bleed,
        "indication_width_m": indication_w,
        "bleed_out_ratio": bleed_out_ratio(indication_w, opening),
        "developer_mass_kg": developer_coverage_mass(part_area_m2, areal),
        "developer_areal_density_kgm2": areal,
        "part_area_m2": part_area_m2,
        "contrast_ratio": contrast_ratio(0.8, 0.05),
        "inputs": {"crack_depth_m": crack_depth,
                   "crack_opening_width_m": opening,
                   "reference_dwell_s": dwell_ref},
    }


# ---------------------------------------------------------------------------
# Radiography (RT) - mirrored from radiographic-inspection leaf logic
# ---------------------------------------------------------------------------

DENSITY_BAND = (2.0, 4.0)
UNSHARPNESS_LIMIT_MM = 0.25
SENSITIVITY_LIMIT_PERCENT = 2.0


def geometric_unsharpness(focal_spot_mm, sod_mm, odd_mm):
    return focal_spot_mm * odd_mm / sod_mm


def exposure_time(base_time, distance, reference_distance):
    return base_time * (distance / reference_distance) ** 2


def iqi_sensitivity_percent(visible_thickness_mm, part_thickness_mm):
    return visible_thickness_mm / part_thickness_mm * 100.0


def density_verdict(film_density):
    band = DENSITY_BAND
    if band[0] <= film_density <= band[1]:
        verdict, ok = "acceptable", True
    elif film_density < band[0]:
        verdict, ok = "too-low", False
    else:
        verdict, ok = "too-high", False
    return {"density": film_density, "acceptable": ok, "verdict": verdict,
            "band": list(band)}


def discontinuity_class(geometry_descriptor):
    desc = (geometry_descriptor or "").strip().lower()
    if any(k in desc for k in ("round", "globular", "spherical", "gas")):
        return "porosity"
    if any(k in desc for k in ("elongated", "linear", "sharp", "hairline",
                               "tight")):
        return "crack"
    if any(k in desc for k in ("compact", "dense", "metallic",
                               "high-density")):
        return "inclusion"
    if any(k in desc for k in ("flat", "planar", "layered", "angular",
                               "slag")):
        return "slag"
    raise ValueError("unknown geometry descriptor %r" % (geometry_descriptor,))


def rt_setup_verdict(unsharpness_mm, sensitivity_percent, film_density,
                     unsharpness_limit_mm=UNSHARPNESS_LIMIT_MM,
                     sensitivity_limit_percent=SENSITIVITY_LIMIT_PERCENT):
    dv = density_verdict(film_density)
    reasons = []
    if unsharpness_mm > unsharpness_limit_mm:
        reasons.append("geometric unsharpness %.3f mm exceeds the %.3f mm "
                       "limit" % (unsharpness_mm, unsharpness_limit_mm))
    if sensitivity_percent > sensitivity_limit_percent:
        reasons.append("IQI sensitivity %.2f percent exceeds the %.2f "
                       "percent limit" % (sensitivity_percent,
                                          sensitivity_limit_percent))
    if not dv["acceptable"]:
        reasons.append("film density %.2f is %s (band %.1f to %.1f)"
                       % (film_density, dv["verdict"], DENSITY_BAND[0],
                          DENSITY_BAND[1]))
    return {"acceptable": not reasons, "reasons": reasons}


def rt_plan(setup):
    """One radiography parameter row from a setup facts dict."""
    ug = geometric_unsharpness(setup["focal_spot_mm"], setup["sod_mm"],
                               setup["odd_mm"])
    exposure = exposure_time(setup["base_exposure_min"],
                             setup["sod_mm"] + setup["odd_mm"],
                             setup["reference_distance_mm"])
    sens = iqi_sensitivity_percent(setup["iq_visible_mm"],
                                   setup["section_thickness_mm"])
    verdict = rt_setup_verdict(ug, sens, setup["film_density"])
    return {
        "focal_spot_mm": setup["focal_spot_mm"],
        "sod_mm": setup["sod_mm"],
        "odd_mm": setup["odd_mm"],
        "geometric_unsharpness_mm": ug,
        "unsharpness_limit_mm": UNSHARPNESS_LIMIT_MM,
        "exposure_min": exposure,
        "iq_visible_mm": setup["iq_visible_mm"],
        "section_thickness_mm": setup["section_thickness_mm"],
        "iqi_sensitivity_percent": sens,
        "sensitivity_limit_percent": SENSITIVITY_LIMIT_PERCENT,
        "film_density": setup["film_density"],
        "density_band": list(DENSITY_BAND),
        "density_verdict": density_verdict(setup["film_density"])["verdict"],
        "setup_acceptable": verdict["acceptable"],
        "setup_reasons": verdict["reasons"],
        "discontinuity_class": discontinuity_class(
            setup["geometry_descriptor"]),
        "inputs": dict(setup),
    }


# ---------------------------------------------------------------------------
# Computed tomography (CT) - mirrored from computed-tomography leaf logic
# ---------------------------------------------------------------------------

DETECT_FACTOR = 3
PROJECTION_K = math.pi / 2.0
KV_PER_MM = {"aluminum": 7.0, "titanium": 9.0, "steel": 14.0, "nickel": 16.0}


def magnification(sod, odd):
    return (sod + odd) / sod


def voxel_size(pixel_pitch, sod, odd):
    return pixel_pitch / magnification(sod, odd)


def resolution_check(voxel_size_m, required_flaw_m):
    smallest = voxel_size_m * DETECT_FACTOR
    if smallest <= required_flaw_m * (1.0 + 1e-9):
        return ("PASS: smallest detectable feature %.3e m (3 voxels) is at "
                "or below the required %.3e m flaw size"
                % (smallest, required_flaw_m))
    return ("FAIL: smallest detectable feature %.3e m (3 voxels) exceeds "
            "the required %.3e m flaw size" % (smallest, required_flaw_m))


def projection_count(columns_span):
    return int(math.ceil(PROJECTION_K * columns_span))


def tube_energy_kv(material, thickness_mm):
    key = material.strip().lower()
    if key not in KV_PER_MM:
        raise ValueError("unknown material %r" % (material,))
    return KV_PER_MM[key] * thickness_mm


def scan_time(num_projections, exposure_s_per_proj):
    return num_projections * exposure_s_per_proj


def ct_number(mu, mu_water):
    return 1000.0 * (mu - mu_water) / mu_water


def material_class_from_ct_number(hu):
    if hu <= -950.0:
        return "air-or-gas"
    if hu < -100.0:
        return "low-density-void"
    if hu < 100.0:
        return "polymer-composite"
    if hu < 1000.0:
        return "light-alloy"
    return "high-density-metal"


def porosity_fraction(void_voxels, total_voxels):
    return 100.0 * void_voxels / total_voxels


def void_diameter(void_voxels, voxel_size_m):
    if void_voxels == 0:
        return 0.0
    volume = void_voxels * voxel_size_m ** 3
    return 2.0 * (3.0 * volume / (4.0 * math.pi)) ** (1.0 / 3.0)


def ct_plan(ct):
    """One CT parameter row from a CT facts dict."""
    mag = magnification(ct["sod_m"], ct["odd_m"])
    vox = voxel_size(ct["pixel_pitch_m"], ct["sod_m"], ct["odd_m"])
    nproj = projection_count(ct["columns_span"])
    kv = tube_energy_kv(ct["material"], ct["thickness_mm"])
    return {
        "magnification": mag,
        "voxel_size_m": vox,
        "required_flaw_m": ct["required_flaw_m"],
        "resolution": resolution_check(vox, ct["required_flaw_m"]),
        "projection_count": nproj,
        "tube_energy_kv": kv,
        "scan_time_s": scan_time(nproj, ct["exposure_s_per_proj"]),
        "porosity_percent": porosity_fraction(ct["void_voxels"],
                                              ct["total_voxels"]),
        "void_diameter_m": void_diameter(ct["void_voxels"], vox),
        "ct_number_hu": ct_number(ct["mu"], ct["mu_water"]),
        "material_class": material_class_from_ct_number(
            ct_number(ct["mu"], ct["mu_water"])),
        "inputs": dict(ct),
    }


# ---------------------------------------------------------------------------
# Magnetic particle (MT) - mirrored from magnetic-particle-inspection leaf
# ---------------------------------------------------------------------------

FIELD_BAND_FLUORESCENT = (2400.0, 4800.0)
FIELD_BAND_VISIBLE = (2400.0, 3200.0)
RESIDUAL_FIELD_LIMIT_AM = 3.0
LOW_FILL_CONSTANT = 45000.0
HIGH_FILL_CONSTANT = 35000.0
LINEAR_RATIO = 3.0


def head_shot_current(diameter_in, amperes_per_inch=800.0):
    return amperes_per_inch * diameter_in


def central_conductor_current(conductor_diameter_in, amperes_per_inch=800.0):
    return amperes_per_inch * conductor_diameter_in


def effective_diameter_hollow(outer_diameter, inner_diameter):
    return math.sqrt(outer_diameter * outer_diameter
                     - inner_diameter * inner_diameter)


def effective_ld_ratio(length, effective_diameter):
    return length / effective_diameter


def coil_ampere_turns_low_fill(ld_ratio):
    return LOW_FILL_CONSTANT / ld_ratio


def coil_ampere_turns_high_fill(ld_ratio):
    return HIGH_FILL_CONSTANT / (ld_ratio + 2.0)


def coil_current_from_turns(ampere_turns, turns):
    return ampere_turns / float(turns)


def solenoid_field_strength(ampere_turns, coil_length_m):
    return ampere_turns / coil_length_m


def tangential_field_verdict(field_am, fluorescent=True):
    low, high = FIELD_BAND_FLUORESCENT if fluorescent else FIELD_BAND_VISIBLE
    if field_am < low:
        return "low"
    if field_am > high:
        return "high"
    return "adequate"


def coverage_step(shot_width, overlap_fraction):
    return shot_width * (1.0 - overlap_fraction)


def particle_size_class(median_diameter_um):
    for limit, label in ((10.0, "extra-fine"), (20.0, "fine"),
                         (35.0, "medium")):
        if median_diameter_um < limit:
            return label
    return "coarse"


def particle_sensitivity(median_diameter_um):
    for limit, label in ((20.0, "high"), (35.0, "standard")):
        if median_diameter_um < limit:
            return label
    return "low"


def bath_concentration_check(concentration_ml_per_100ml, method="fluorescent"):
    low, high = (BATH_FLUORESCENT if method == "fluorescent"
                 else BATH_VISIBLE)
    if concentration_ml_per_100ml < low:
        return "below-range"
    if concentration_ml_per_100ml > high:
        return "above-range"
    return "within-range"


BATH_FLUORESCENT = (0.1, 0.4)
BATH_VISIBLE = (1.0, 2.0)


def indication_is_linear(length_mm, width_mm):
    return length_mm / width_mm >= LINEAR_RATIO


def magnetization_for_defect(defect_orientation):
    o = defect_orientation.strip().lower()
    if o in ("longitudinal", "axial", "axially-oriented"):
        return "circular"
    if o in ("transverse", "circumferential", "circumferentially-oriented"):
        return "longitudinal"
    raise ValueError("unknown defect orientation %r" % (defect_orientation,))


def acceptance_verdict(relevant, indication_length_mm, max_allowed_mm):
    if not relevant:
        return "evaluate"
    if indication_length_mm > max_allowed_mm:
        return "reject"
    return "accept"


def residual_field_verdict(residual_am, limit_am=RESIDUAL_FIELD_LIMIT_AM):
    if residual_am > limit_am:
        return "demagnetize"
    return "acceptable"


def mt_plan(mt):
    """One magnetic-particle parameter row (ferromagnetic parts)."""
    if mt["magnetization"] == "circular":
        current_a = head_shot_current(mt["diameter_in"])
        field_am = None
        turns_ni = None
        coil_current = None
    else:
        deff = effective_diameter_hollow(mt["outer_diameter_in"],
                                         mt["inner_diameter_in"])
        ld = effective_ld_ratio(mt["length_in"], deff)
        ni = coil_ampere_turns_low_fill(ld)
        current_a = None
        field_am = solenoid_field_strength(ni, mt["coil_length_m"])
        turns_ni = ni
        coil_current = coil_current_from_turns(ni, mt["turns"])
    return {
        "defect_orientation": mt["defect_orientation"],
        "magnetization": magnetization_for_defect(mt["defect_orientation"]),
        "head_shot_current_a": current_a,
        "coil_ampere_turns": turns_ni,
        "coil_current_a": coil_current,
        "tangential_field_am": field_am,
        "tangential_verdict": (tangential_field_verdict(field_am)
                               if field_am is not None else None),
        "particle_size_class": particle_size_class(mt["median_particle_um"]),
        "particle_sensitivity": particle_sensitivity(mt["median_particle_um"]),
        "bath_check": bath_concentration_check(mt["bath_concentration"],
                                               mt["bath_method"]),
        "coverage_step_m": coverage_step(mt["shot_width_m"],
                                         mt["overlap_fraction"]),
        "indication_linear": indication_is_linear(mt["indication_length_mm"],
                                                  mt["indication_width_mm"]),
        "indication_verdict": acceptance_verdict(mt["indication_relevant"],
                                                 mt["indication_length_mm"],
                                                 mt["max_allowed_mm"]),
        "residual_field_verdict": residual_field_verdict(mt["residual_am"]),
        "inputs": dict(mt),
    }


# ---------------------------------------------------------------------------
# Leak testing (LT) - mirrored from leak-testing leaf logic
# ---------------------------------------------------------------------------

BAR_TO_ATM = 0.986923
STD_TEMP_K = 293.15
MS_THRESHOLD = 1e-6
SNIFFER_THRESHOLD = 1e-5
BUBBLE_THRESHOLD = 1e-2
REVIEW_RATIO = 1.25

VALID_METHODS = ("pressure-decay", "vacuum-decay", "bubble",
                 "helium-sniffer", "helium-mass-spectrometer-hood")


def pressure_decay_rate(volume_L, dP_bar, time_s, temp_K=STD_TEMP_K):
    return (volume_L * 1000.0) * (dP_bar * BAR_TO_ATM) / time_s \
        * (STD_TEMP_K / temp_K)


def gauge_resolution_time(volume_L, gauge_res_bar, target_sccs,
                          temp_K=STD_TEMP_K):
    volume_cc = volume_L * 1000.0
    dP_atm = gauge_res_bar * BAR_TO_ATM
    return volume_cc * dP_atm / target_sccs * (STD_TEMP_K / temp_K)


def method_recommendation(required_sensitivity_sccs, access_both_sides,
                          need_localization, part_pressure_capable):
    if required_sensitivity_sccs <= MS_THRESHOLD:
        return ("helium-mass-spectrometer-hood",
                "required sensitivity %.1e scc/s is at or below the 1e-6 "
                "scc/s hood threshold" % required_sensitivity_sccs)
    if need_localization and required_sensitivity_sccs <= SNIFFER_THRESHOLD:
        return ("helium-sniffer",
                "localization needed and required sensitivity %.1e scc/s "
                "is at or below the 1e-5 scc/s sniffer threshold"
                % required_sensitivity_sccs)
    if not access_both_sides:
        if part_pressure_capable:
            return ("pressure-decay",
                    "only one side accessible and the part holds pressure, "
                    "so a decay test on the sealed internal volume fits")
        return ("vacuum-decay",
                "only one side accessible and the part cannot take internal "
                "pressure, so an evacuated-chamber decay test fits")
    if need_localization and required_sensitivity_sccs <= BUBBLE_THRESHOLD:
        return ("bubble",
                "localization needed and required sensitivity %.1e scc/s "
                "is at or below the 1e-2 scc/s bubble immersion threshold"
                % required_sensitivity_sccs)
    return ("pressure-decay",
            "no tighter constraint applies, so pressurize the sealed "
            "volume and watch the pressure decay")


def disposition(measured_sccs, max_allowable_sccs, method):
    margin_db = (10.0 * math.log10(max_allowable_sccs / measured_sccs)
                 if measured_sccs > 0 else float("inf"))
    if measured_sccs <= max_allowable_sccs:
        verdict = "accept"
    elif measured_sccs > REVIEW_RATIO * max_allowable_sccs:
        verdict = "reject"
    else:
        verdict = "review"
    return {"verdict": verdict, "margin_db": margin_db}


def leak_plan(lt):
    """One leak-test parameter row from a leak facts dict."""
    rec_method, rec_reason = method_recommendation(
        lt["required_sensitivity_sccs"], lt["access_both_sides"],
        lt["need_localization"], lt["part_pressure_capable"])
    rate = pressure_decay_rate(lt["volume_L"], lt["dP_bar"], lt["time_s"])
    outcome = disposition(rate, lt["max_allowable_sccs"], "pressure-decay")
    gres = gauge_resolution_time(lt["volume_L"], lt["gauge_res_bar"],
                                 lt["max_allowable_sccs"])
    return {
        "method_recommendation": rec_method,
        "recommendation_reason": rec_reason,
        "volume_L": lt["volume_L"],
        "dP_bar": lt["dP_bar"],
        "time_s": lt["time_s"],
        "leak_rate_sccs": rate,
        "max_allowable_sccs": lt["max_allowable_sccs"],
        "verdict": outcome["verdict"],
        "margin_db": outcome["margin_db"],
        "gauge_res_bar": lt["gauge_res_bar"],
        "gauge_resolution_time_s": gres,
        "gauge_adequate": lt["time_s"] >= gres,
        "inputs": dict(lt),
    }


# ---------------------------------------------------------------------------
# Acoustic emission (AE) - mirrored from acoustic-emission-inspection leaf
# ---------------------------------------------------------------------------

def hit_threshold_check(amplitudes_db, threshold_db):
    hits = [a for a in amplitudes_db if a >= threshold_db]
    return {"threshold_db": threshold_db, "hits": hits,
            "hit_count": len(hits), "total_signals": len(amplitudes_db)}


def group_hits_to_events(arrival_times, hdt):
    if not arrival_times:
        return []
    ordered = sorted(arrival_times)
    events = [[ordered[0]]]
    for t in ordered[1:]:
        if t - events[-1][-1] > hdt:
            events.append([t])
        else:
            events[-1].append(t)
    return events


def source_location_linear(sensor_distance, arrival_times, wave_speed):
    t1, t2 = arrival_times
    return (sensor_distance + wave_speed * (t1 - t2)) / 2.0


def felicity_ratio(resume_load, previous_max_load):
    return resume_load / previous_max_load


def kaiser_effect_check(resume_load, previous_max_load,
                        felicity_threshold=0.95):
    ratio = felicity_ratio(resume_load, previous_max_load)
    return {"felicity_ratio": ratio,
            "kaiser_effect_holds": ratio >= 1.0,
            "felicity_effect": ratio < 1.0,
            "damage_indicated": ratio < felicity_threshold,
            "felicity_threshold": felicity_threshold}


# ---------------------------------------------------------------------------
# Shearography - mirrored from shearography-inspection leaf logic
# ---------------------------------------------------------------------------

LASER_WAVELENGTH_NM = 532.0
NOISE_FLOOR_PHASE_RAD = 0.1
MIN_SNR = 3.0
SHEAR_DIVISOR = 2.0
REVIEW_BAND = 0.2
TYPICAL_LOAD_STEPS = {"vacuum": {2.0: 20.0, 6.0: 40.0, 12.0: 60.0},
                      "thermal": 5.0, "vibration": 30.0}


def strain_from_phase(phase_rad, shear_mm, wavelength_nm=LASER_WAVELENGTH_NM):
    return (phase_rad * wavelength_nm * 1e-9
            / (4.0 * math.pi * shear_mm * 1e-3))


def min_detectable_strain(noise_floor_rad, shear_mm,
                          wavelength_nm=LASER_WAVELENGTH_NM):
    single = (noise_floor_rad * wavelength_nm * 1e-9
              / (4.0 * math.pi * shear_mm * 1e-3))
    return MIN_SNR * single


def shear_for_defect(defect_size_mm):
    return defect_size_mm / SHEAR_DIVISOR


def select_load(part_thickness_mm, load_type):
    entry = TYPICAL_LOAD_STEPS[load_type]
    if not isinstance(entry, dict):
        return float(entry)
    thicknesses = sorted(entry)
    for lo_t, hi_t in zip(thicknesses, thicknesses[1:]):
        if lo_t <= part_thickness_mm <= hi_t:
            slope = (entry[hi_t] - entry[lo_t]) / (hi_t - lo_t)
            return entry[lo_t] + slope * (part_thickness_mm - lo_t)
    if part_thickness_mm <= thicknesses[0]:
        lo_t, hi_t = thicknesses[0], thicknesses[1]
        slope = (entry[hi_t] - entry[lo_t]) / (hi_t - lo_t)
        return entry[lo_t] + slope * (part_thickness_mm - lo_t)
    lo_t, hi_t = thicknesses[-2], thicknesses[-1]
    slope = (entry[hi_t] - entry[lo_t]) / (hi_t - lo_t)
    return entry[hi_t] + slope * (part_thickness_mm - hi_t)


def scan_plan(part_area_m2, fov_area_m2, overlap):
    passes = int(math.ceil(part_area_m2 / (fov_area_m2 * (1.0 - overlap))))
    return {"passes": passes,
            "overlap_area": passes * fov_area_m2 * overlap}


def anomaly_disposition(anomaly_size_mm, allow_size_mm, snr):
    reasons = []
    band_limit = allow_size_mm * (1.0 + REVIEW_BAND)
    if anomaly_size_mm >= band_limit:
        return {"verdict": "reject", "reasons": [
            "anomaly %g mm is at or above %g mm, the allowable plus the "
            "%g review band" % (anomaly_size_mm, band_limit, REVIEW_BAND)]}
    if anomaly_size_mm > allow_size_mm:
        reasons.append("anomaly %g mm exceeds the allowable %g mm but lies "
                       "within the %g review band"
                       % (anomaly_size_mm, allow_size_mm, REVIEW_BAND))
        if snr < MIN_SNR:
            reasons.append("snr %g is below MIN_SNR %g" % (snr, MIN_SNR))
        return {"verdict": "review", "reasons": reasons}
    if snr < MIN_SNR:
        reasons.append("anomaly %g mm is within the allowable %g mm but "
                       "snr %g is below MIN_SNR %g"
                       % (anomaly_size_mm, allow_size_mm, snr, MIN_SNR))
        return {"verdict": "review", "reasons": reasons}
    reasons.append("anomaly %g mm is within the allowable %g mm and snr "
                   "%g meets MIN_SNR %g"
                   % (anomaly_size_mm, allow_size_mm, snr, MIN_SNR))
    return {"verdict": "accept", "reasons": reasons}


# ---------------------------------------------------------------------------
# Item facts + builder
# ---------------------------------------------------------------------------

@dataclass
class DefectCandidate:
    defect_name: str
    defect_class: str          # surface | near-surface | internal
    zone: str = ""
    geometry_descriptor: str = ""   # RT discontinuity vocabulary
    description: str = ""


@dataclass
class InspectionItem:
    """Project facts the role needs to build the NDT plan."""
    item_name: str
    item_number: str = ""
    description: str = ""
    material: str = ""
    material_class: str = "non-ferromagnetic"
    percent_iacs: float = 30.0
    manufacture_route: str = ""
    drawing_ref: str = ""
    candidate_defects: list = field(default_factory=list)
    # method fact groups (SI where noted)
    penetrant: dict = field(default_factory=dict)
    pt_surface_area_m2: float = 0.5
    eddy_surface: dict = field(default_factory=dict)
    eddy_subsurface: dict = field(default_factory=dict)
    radiography: dict = field(default_factory=dict)
    tomography: dict = field(default_factory=dict)
    leak: dict = field(default_factory=dict)
    magnetic_particle: dict = field(default_factory=dict)
    personnel_record: dict = field(default_factory=dict)
    certification_basis: str = "AS9100D special-process control (internal)"

    def _today(self):
        return date.today().isoformat()


def build_report(item: InspectionItem) -> dict:
    """Build the complete NDT plan content model from project facts."""
    mat = item.material_class

    population = []
    for d in item.candidate_defects:
        pick = select_method(d.defect_class, mat)
        population.append({
            "defect_name": d.defect_name,
            "zone": d.zone,
            "defect_class": d.defect_class,
            "material_class": mat,
            "geometry_descriptor": d.geometry_descriptor,
            "description": d.description,
            "applicable": applicable_methods(d.defect_class, mat),
            "top_method": pick["method"],
            "alternates": pick["alternates"],
            "rationale": pick["rationale"],
            "sensitivity": {m: SENSITIVITY_RANK[m]
                            for m in applicable_methods(d.defect_class, mat)},
        })

    cards = {}
    if item.eddy_surface:
        cards["eddy-current-surface"] = et_plan(**item.eddy_surface)
    if item.eddy_subsurface:
        cards["eddy-current-subsurface"] = et_plan(**item.eddy_subsurface)
    if item.penetrant:
        cards["liquid-penetrant"] = pt_plan(item.penetrant,
                                            item.pt_surface_area_m2)
    if item.radiography:
        cards["radiography"] = rt_plan(item.radiography)
    if item.tomography:
        cards["computed-tomography"] = ct_plan(item.tomography)
    if item.magnetic_particle:
        cards["magnetic-particle"] = mt_plan(item.magnetic_particle)
    if item.leak:
        cards["leak-test"] = leak_plan(item.leak)

    # personnel: record dates are held relative to today so the plan never
    # goes stale; due dates computed by the leaf's month-add/clamp rules.
    today = date.today()
    record = dict(item.personnel_record)
    record.setdefault("cert_date_iso",
                      add_months_clamped(today.isoformat(), -24))
    record.setdefault("last_vision_iso",
                      add_months_clamped(today.isoformat(), -6))
    review = qualification_review(record, today.isoformat())
    methods_in_plan = _methods_in_plan(population, cards)
    personnel = {
        "record": record,
        "review": review,
        "review_date": today.isoformat(),
        "method_levels": [
            {"method": m,
             "interpretation_level": INTERPRET_LEVEL[m],
             "performance_level": PERFORM_LEVEL[m],
             "operator_meets": level_meets(record.get("operator_level", "ii"),
                                           INTERPRET_LEVEL[m])}
            for m in methods_in_plan],
    }

    return {
        "document_type": "Nondestructive Test Plan and Method Selection Report",
        "status": "draft-for-review",
        "item": item.item_name,
        "item_number": item.item_number,
        "item_description": item.description,
        "material": item.material,
        "material_class": mat,
        "percent_iacs": item.percent_iacs,
        "manufacture_route": item.manufacture_route,
        "drawing_ref": item.drawing_ref,
        "certification_basis": item.certification_basis,
        "defect_population": population,
        "parameter_cards": cards,
        "personnel": personnel,
        "acceptance_framing": acceptance_framing(cards, mat),
        "generated": today.isoformat(),
    }


def _method_present(method, cards):
    keys = {"ET": "eddy-current", "PT": "liquid-penetrant",
            "RT": "radiography", "CT": "computed-tomography",
            "MT": "magnetic-particle", "LT": "leak-test"}
    return any(k.startswith(keys[method]) for k in cards)


def _methods_in_plan(population, cards):
    """Methods this plan actually uses: the selected/alternate methods of
    the defect population plus any method that has a parameter card.
    Canonical order MT, PT, ET, UT, RT, CT, LT."""
    methods = set()
    for row in population:
        methods.add(row["top_method"])
        methods.update(row["alternates"])
    for k in cards:
        for m, prefix in (("ET", "eddy-current"), ("PT", "liquid-penetrant"),
                          ("RT", "radiography"), ("CT", "computed-tomography"),
                          ("MT", "magnetic-particle"), ("LT", "leak-test")):
            if k.startswith(prefix):
                methods.add(m)
    order = ("MT", "PT", "ET", "UT", "RT", "CT", "LT")
    return [m for m in order if m in methods]


def acceptance_framing(cards, material_class):
    """Disposition rules per method family - framing input only, the
    customer acceptance document / engineering authority disposes."""
    rows = []
    if "magnetic-particle" in cards:
        rows.append({
            "method": "MT",
            "rule": ("relevant indications are accepted when their length "
                     "does not exceed the acceptance limit and rejected "
                     "when it does; non-relevant indications (threads, "
                     "geometry, magnetic writing) are recorded and "
                     "evaluated, never auto-disposed; linear "
                     "(length/width >= 3) indications are crack-like and "
                     "evaluated against the linear limit")})
    if any(k.startswith("eddy-current") for k in cards):
        rows.append({
            "method": "ET",
            "rule": ("signal amplitude and phase vs the calibrated "
                     "reference standard gate sizing; indications are "
                     "evaluated against the acceptance document for the "
                     "zone (crack-like vs volumetric responses)")})
    if "liquid-penetrant" in cards:
        rows.append({
            "method": "PT",
            "rule": ("rounded indications (pores) and linear indications "
                     "(cracks, laps) are sized from the bleed-out image "
                     "and evaluated against their class limits; excessive "
                     "background is a process failure, not an indication")})
    if "radiography" in cards:
        rows.append({
            "method": "RT",
            "rule": ("the discontinuity class (porosity / crack / "
                     "inclusion / slag) gates the applicable acceptance "
                     "criteria; the technique verdict (unsharpness, IQI "
                     "sensitivity, film density) must be acceptable "
                     "before any disposition is made")})
    if "computed-tomography" in cards:
        rows.append({
            "method": "CT",
            "rule": ("segmented void fraction and equivalent void "
                     "diameter are disposition inputs against the casting "
                     "acceptance standard; resolution must first pass the "
                     "required-flaw check")})
    if "leak-test" in cards:
        rows.append({
            "method": "LT",
            "rule": ("measured leak rate is accepted when at or below the "
                     "maximum allowable, rejected when above 1.25x the "
                     "allowable, reviewed in between (margin band)")})
    if material_class == "ferromagnetic":
        rows.append({
            "method": "MT",
            "rule": ("residual field must be below the demagnetization "
                     "limit before the part returns to service")})
    return {"framing_note":
            "All dispositions in this plan are INPUTS for the responsible "
            "engineering authority; the customer acceptance document and "
            "the qualified procedure govern.",
            "method_rules": rows}


def _fmt(x, fmt="%.4g"):
    if x is None:
        return "n/a"
    return fmt % x


def _fmt_sci(x, fmt="%.3e"):
    if x is None:
        return "n/a"
    return fmt % x


def render_report_markdown(model: dict) -> str:
    """Render the content model as the deliverable markdown document."""
    L = []
    ap = L.append
    ap("# Nondestructive Test Plan and Method Selection Report")
    ap("")
    ap("**Item:** %s%s" % (model["item"],
                           ("  (%s)" % model["item_number"])
                           if model["item_number"] else ""))
    ap("**Material:** %s (%s, %g pct IACS)  **Route:** %s"
       % (model["material"], model["material_class"], model["percent_iacs"],
          model["manufacture_route"]))
    if model["drawing_ref"]:
        ap("**Drawing:** %s" % model["drawing_ref"])
    ap("**Certification basis:** %s" % model["certification_basis"])
    ap("**Status:** %s" % model["status"])
    ap("")
    if model["item_description"]:
        ap("Scope: %s" % model["item_description"])
        ap("")

    ap("## 1. Candidate defect population and method selection")
    ap("")
    ap("Method selection follows the bound ndt-method-selection decision "
       "logic: defect class (surface / near-surface / internal) x material "
       "class (%s) defines the applicable set, and sensitivity rank "
       "(UT 5, RT/ET 4, MT/PT 3) picks the method (cost is reporting "
       "only)." % model["material_class"])
    ap("")
    for row in model["defect_population"]:
        ap("### 1.%d  %s" % (model["defect_population"].index(row) + 1,
                             row["defect_name"]))
        ap("")
        if row["description"]:
            ap("- Zone / note: %s" % row["description"])
        ap("- Defect class: %s  ·  material class: %s"
           % (row["defect_class"], row["material_class"]))
        ap("- Applicable methods: %s"
           % ", ".join("%s (sensitivity %d)"
                       % (METHOD_NAMES[m], row["sensitivity"][m])
                       for m in row["applicable"]))
        ap("- **Selected method: %s** — %s."
           % (METHOD_NAMES[row["top_method"]], row["rationale"]))
        ap("- Alternates: %s"
           % ", ".join(METHOD_NAMES[m] for m in row["alternates"])
           if row["alternates"] else "- Alternates: none")
        ap("")

    ap("## 2. Inspection parameters per selected method")
    ap("")
    cards = model["parameter_cards"]
    ap("_Parameter rows below are computed by the role core mirroring the "
       "bound method leaf logic. The qualified procedure and the "
       "engineering specification govern the actual inspection settings._")
    ap("")
    ap("### 2.1 Eddy current (ET) — surface zone")
    if "eddy-current-surface" in cards:
        c = cards["eddy-current-surface"]
        ap("- Flaw depth: %.3g m; conductivity %g pct IACS (%.3g S/m)"
           % (c["flaw_depth_m"], c["percent_iacs"], c["conductivity_sm"]))
        ap("- Test frequency (penetration factor %.2g): **%.0f Hz**; "
           "standard depth of penetration **%.4g m**"
           % (c["penetration_factor"], c["frequency_hz"], c["delta_m"]))
        ap("- Current density at the flaw depth: %.3f of surface; "
           "phase lag %.2f deg"
           % (c["density_ratio_at_flaw"], c["phase_lag_deg"]))
    else:
        ap("- Not applicable to this part (no surface-conductive zone).")
    ap("")
    ap("### 2.2 Eddy current (ET) — near-surface zone")
    if "eddy-current-subsurface" in cards:
        c = cards["eddy-current-subsurface"]
        ap("- Subsurface flaw depth %.3g m: frequency **%.0f Hz**, "
           "standard depth of penetration %.4g m keeps the flaw at half a "
           "delta (density ratio %.3f, phase lag %.2f deg)"
           % (c["flaw_depth_m"], c["frequency_hz"], c["delta_m"],
              c["density_ratio_at_flaw"], c["phase_lag_deg"]))
    else:
        ap("- Not applicable.")
    ap("")
    ap("### 2.3 Liquid penetrant (PT) — surface-breaking crack zone")
    if "liquid-penetrant" in cards:
        c = cards["liquid-penetrant"]
        ap("- Penetrant: gamma %.3g N/m, contact angle %g deg, viscosity "
           "%.4g Pa.s; crack opening %.3g m -> effective capillary radius "
           "%.3g m" % (c["surface_tension_nm"], c["contact_angle_deg"],
                       c["viscosity_pas"], c["crack_opening_width_m"],
                       c["effective_capillary_radius_m"]))
        ap("- Capillary pressure across the meniscus: **%.3g Pa**"
           % c["capillary_pressure_pa"])
        ap("- Washburn model: penetration depth %.4g m at the %g s "
           "reference dwell; computed time to fill the %.3g m-deep "
           "reference crack %.4g s (dwell scales with depth squared and "
           "inversely with crack radius)" % (c["washburn_depth_at_reference_s_m"],
                                             c["reference_dwell_s"],
                                             c["crack_depth_m"],
                                             c["dwell_time_to_fill_s"]))
        ap("- Indication sizing: bleed-out width %.3g m for the %.3g m "
           "opening (ratio %.1f); developer %.3g kg at %.3g kg/m2 over "
           "%.2f m2; fluorescent contrast vs background %.3f"
           % (c["indication_width_m"], c["crack_opening_width_m"],
              c["bleed_out_ratio"], c["developer_mass_kg"],
              c["developer_areal_density_kgm2"], c["part_area_m2"],
              c["contrast_ratio"]))
        ap("- Dwell: procedure-qualified penetrant dwell governs; the "
           "model numbers above are sizing inputs, not settings.")
    else:
        ap("- Not applicable (no non-porous surface-breaking crack zone).")
    ap("")
    ap("### 2.4 Radiography (RT) — internal volumetric zone")
    if "radiography" in cards:
        c = cards["radiography"]
        ap("- Setup: focal spot %.1f mm, SOD %.0f mm, ODD %.0f mm -> "
           "geometric unsharpness **%.2f mm** (limit %.2f mm)"
           % (c["focal_spot_mm"], c["sod_mm"], c["odd_mm"],
              c["geometric_unsharpness_mm"], c["unsharpness_limit_mm"]))
        ap("- Exposure (inverse-square): **%.3g min** at the working "
           "distance" % c["exposure_min"])
        ap("- IQI sensitivity: %.2f pct (%.1f mm visible on %.0f mm "
           "section; limit %.1f pct)"
           % (c["iqi_sensitivity_percent"], c["iq_visible_mm"],
              c["section_thickness_mm"], c["sensitivity_limit_percent"]))
        ap("- Film density %.2f in band %.1f-%.1f (%s); technique verdict: "
           "**%s**"
           % (c["film_density"], c["density_band"][0], c["density_band"][1],
              c["density_verdict"],
              "acceptable" if c["setup_acceptable"] else
              "NOT acceptable: " + "; ".join(c["setup_reasons"])))
        ap("- Expected discontinuity class from image geometry: %s "
           "(acceptance criteria per class)"
           % c["discontinuity_class"])
    else:
        ap("- Not applicable (no internal volumetric zone).")
    ap("")
    ap("### 2.5 Computed tomography (CT) — supplemental volumetric sizing")
    if "computed-tomography" in cards:
        c = cards["computed-tomography"]
        ap("- Magnification %.2f, voxel size %.3g m; required flaw %.3g m"
           % (c["magnification"], c["voxel_size_m"], c["required_flaw_m"]))
        ap("- Resolution: %s" % c["resolution"])
        ap("- Scan plan: %d projections at %g kV (%.0f s), material %s "
           "thickness %.0f mm" % (c["projection_count"],
                                  c["tube_energy_kv"], c["scan_time_s"],
                                  c["inputs"]["material"],
                                  c["inputs"]["thickness_mm"]))
        ap("- Porosity ROI: %.3g pct void fraction, equivalent spherical "
           "void diameter %.3g m; CT number %+.0f HU -> %s"
           % (c["porosity_percent"], c["void_diameter_m"],
              c["ct_number_hu"], c["material_class"]))
    else:
        ap("- Not applicable.")
    ap("")
    ap("### 2.6 Magnetic particle (MT) — ferromagnetic parts")
    if "magnetic-particle" in cards:
        c = cards["magnetic-particle"]
        ap("- %s defect -> %s magnetization"
           % (c["defect_orientation"], c["magnetization"]))
        ap("- Magnetizing current: %s"
           % ("head shot %.0f A" % c["head_shot_current_a"]
              if c["head_shot_current_a"] is not None
              else "coil %.0f A (%.0f A-turns)" % (c["coil_current_a"],
                                                   c["coil_ampere_turns"])))
        if c["tangential_field_am"] is not None:
            ap("- Tangential field %.0f A/m: %s (fluorescent band 2400-4800 "
               "A/m)" % (c["tangential_field_am"], c["tangential_verdict"]))
        ap("- Medium: %s particles (%s sensitivity); bath %s"
           % (c["particle_size_class"], c["particle_sensitivity"],
              c["bath_check"]))
        ap("- Coverage step %.2f m at %.0f pct overlap; indication "
           "length/width ratio %.1f -> %s; indication verdict: %s; "
           "residual field: %s"
           % (c["coverage_step_m"], c["inputs"]["overlap_fraction"] * 100,
              c["inputs"]["indication_length_mm"]
              / c["inputs"]["indication_width_mm"],
              "linear (crack-like)" if c["indication_linear"] else "rounded",
              c["indication_verdict"], c["residual_field_verdict"]))
    else:
        ap("- Not applicable to this non-ferromagnetic part; retained in "
           "the method library for ferromagnetic parts (forgings, steel "
           "castings).")
    ap("")
    ap("### 2.7 Leak test (LT) — sealed assembly")
    if "leak-test" in cards:
        c = cards["leak-test"]
        ap("- Method recommendation: **%s** — %s"
           % (c["method_recommendation"], c["recommendation_reason"]))
        ap("- Pressure decay: %.3g L at dP %.3g bar over %.0f s -> leak "
           "rate **%.4g scc/s**; allowable %.3g scc/s -> disposition "
           "**%s** (margin %.2f dB)"
           % (c["volume_L"], c["dP_bar"], c["time_s"], c["leak_rate_sccs"],
              c["max_allowable_sccs"], c["verdict"], c["margin_db"]))
        ap("- Gauge adequacy: %g bar resolution needs >= %.1f s to catch "
           "the allowable leak; test time %.0f s is %s"
           % (c["gauge_res_bar"], c["gauge_resolution_time_s"],
              c["time_s"], "adequate" if c["gauge_adequate"]
              else "NOT adequate"))
    else:
        ap("- Not applicable (no sealed-volume requirement).")
    ap("")

    ap("## 3. NDT personnel qualification")
    ap("")
    p = model["personnel"]
    rec = p["record"]
    rv = p["review"]
    ap("- Operator level: Level %s (supervisor Level %s)"
       % (rec["operator_level"].upper(), rec["supervisor_level"].upper()))
    ap("- Certification status as of %s: **%s** (recert due %s; near-vision "
       "due %s)"
       % (p["review_date"], rv["certification_status"],
          rv["recert_due_date_iso"], rv["vision_due_date_iso"]))
    ap("- Supervision pairing: %s"
       % ("valid (Level I operators work under Level II/III)"
          if rv["supervision_ok"] else "INVALID"))
    if rv["upgrade_eligible"] is not None:
        ap("- Upgrade evaluation (toward Level III): %s"
           % ("eligible when hours, months and examination are met"
              if rv["upgrade_eligible"] else "not yet eligible"))
    ap("- Per-method certification check (interpretation of results "
       "requires the level shown):")
    for row in p["method_levels"]:
        ap("  - %s: Level %s to interpret, Level %s to perform — operator "
           "%s" % (row["method"], row["interpretation_level"].upper(),
                   row["performance_level"].upper(),
                   "meets" if row["operator_meets"] else "DOES NOT meet"))
    ap("")

    af = model["acceptance_framing"]
    ap("## 4. Acceptance and disposition framing")
    ap("")
    ap(af["framing_note"])
    ap("")
    for rule in af["method_rules"]:
        ap("- **%s:** %s" % (rule["method"], rule["rule"]))
    ap("")

    ap("## 5. Open items for the responsible authority")
    ap("")
    ap("- Confirm the acceptance limits and the qualified procedure "
       "revisions named in the drawing and the program plan.")
    ap("- Confirm operator certification records and intervals match the "
       "employer's written practice.")
    ap("")
    ap("---")
    ap("*Generated by Aero Agent Roles ndt-engineer core (%s). DRAFT for "
       "human NDT engineering review. Not an approval document; carries "
       "no acceptance or certification authority.*" % model["generated"])
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Evidence gate checkers
# ---------------------------------------------------------------------------

GATE_DETAILS = {
    "method_selection_complete": "every candidate defect has a selected "
                                 "method + alternates + rationale",
    "parameters_computed": "each method card carries computed parameters",
    "personnel_qualified": "operator record current, supervision valid, "
                           "level requirements met",
    "acceptance_framed": "disposition rules present for every method",
    "sign_off_honest": "document marked draft-for-review, not approval",
}


def check_report(model: dict) -> dict:
    """Run the evidence gates against a plan model."""
    results = {}
    population = model.get("defect_population", [])
    cards = model.get("parameter_cards", {})
    results["method_selection_complete"] = bool(population) and all(
        row.get("top_method") and row.get("alternates") is not None
        and row.get("rationale") for row in population)
    results["parameters_computed"] = bool(cards) and all(
        isinstance(card, dict)
        and any(isinstance(v, (int, float)) for v in card.values())
        for card in cards.values())
    p = model.get("personnel", {})
    rv = p.get("review", {})
    results["personnel_qualified"] = (
        rv.get("certification_status") == "current"
        and bool(rv.get("supervision_ok"))
        and all(row.get("operator_meets") for row in
                p.get("method_levels", [])))
    af = model.get("acceptance_framing", {})
    results["acceptance_framed"] = (
        bool(af.get("method_rules")) and bool(af.get("framing_note")))
    results["sign_off_honest"] = model.get("status") == "draft-for-review"
    results["all_pass"] = all(results.values())
    return results


def check_report_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    checks = {
        "has_title": "nondestructive test plan and method selection report"
                     in low,
        "has_item": "**item:**" in low,
        "has_selection": "selected method" in low,
        "has_numbers": "standard depth of penetration" in low
                       and "leak rate" in low,
        "has_personnel": "personnel qualification" in low,
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling."""
    return check_report_markdown(md_text)


# ---------------------------------------------------------------------------
# Example item (for tests + worked-example generation)
# ---------------------------------------------------------------------------

def example_item() -> InspectionItem:
    """Reference item: a critical cast aluminum aerospace part with three
    candidate defect classes (surface crack, near-surface porosity,
    internal shrinkage) plus the sealed-housing leak check."""
    defects = [
        DefectCandidate(
            defect_name="Fatigue crack at oil-feed boss",
            defect_class="surface",
            zone="oil-feed boss, machined face",
            description="surface-breaking crack zone on the machined "
                        "boss face (non-ferromagnetic aluminum)",
        ),
        DefectCandidate(
            defect_name="Subsurface gas porosity under machined skin",
            defect_class="near-surface",
            zone="machined wall, 1 mm below surface",
            description="near-surface gas porosity band beneath the "
                        "machined skin",
        ),
        DefectCandidate(
            defect_name="Internal shrinkage porosity in lug section",
            defect_class="internal",
            zone="thick lug section, 30 mm section",
            geometry_descriptor="round globular gas pockets",
            description="internal shrinkage/gas porosity population in "
                        "the thick lug section",
        ),
    ]
    return InspectionItem(
        item_name="Main Gearbox Housing (investment casting)",
        item_number="PN 7450-103",
        description=("Critical cast aluminum gearbox housing; the casting "
                     "is fully machined after NDT and holds oil under "
                     "pressure in service."),
        material="A356 aluminum alloy casting",
        material_class="non-ferromagnetic",
        percent_iacs=30.0,
        manufacture_route="investment cast + T6",
        drawing_ref="DWG 7450-103 rev C",
        candidate_defects=defects,
        penetrant={"surface_tension_nm": 0.032, "contact_angle_deg": 5.0,
                   "viscosity_pas": 0.008, "crack_depth_m": 1e-3,
                   "crack_opening_width_m": 4e-6,
                   "reference_dwell_s": 300.0,
                   "developer_areal_density_kgm2": 0.15,
                   "bleed_factor": 4.0},
        pt_surface_area_m2=0.5,
        eddy_surface={"flaw_depth_m": 1e-3, "percent_iacs": 30.0,
                      "penetration_factor": 0.5,
                      "label": "surface crack (sharp response)"},
        eddy_subsurface={"flaw_depth_m": 1e-3, "percent_iacs": 30.0,
                         "penetration_factor": 2.0,
                         "label": "near-surface porosity"},
        radiography={"focal_spot_mm": 3.0, "sod_mm": 500.0, "odd_mm": 30.0,
                     "base_exposure_min": 4.0,
                     "reference_distance_mm": 900.0,
                     "iq_visible_mm": 0.6, "section_thickness_mm": 30.0,
                     "film_density": 2.5,
                     "geometry_descriptor": "round globular gas pockets"},
        tomography={"pixel_pitch_m": 200e-6, "sod_m": 0.300, "odd_m": 0.300,
                    "required_flaw_m": 0.5e-3, "columns_span": 1024,
                    "material": "aluminum", "thickness_mm": 50.0,
                    "exposure_s_per_proj": 0.1, "void_voxels": 64000,
                    "total_voxels": 8000000, "mu": 28.0, "mu_water": 20.0},
        leak={"required_sensitivity_sccs": 1e-1,
              "access_both_sides": False, "need_localization": False,
              "part_pressure_capable": True,
              "volume_L": 5.0, "dP_bar": 0.02, "time_s": 600.0,
              "max_allowable_sccs": 0.2, "gauge_res_bar": 5e-4},
        personnel_record={"operator_level": "ii",
                          "supervisor_level": "iii",
                          "upgrade_inputs": {"target_level": "iii",
                                             "held_hours": 720,
                                             "required_hours": 700,
                                             "held_months": 26,
                                             "required_months": 24,
                                             "exam_passed": True}},
        certification_basis="AS9100D special-process control; NAS 410 "
                            "personnel qualification practice",
    )


def example_report_markdown() -> str:
    return render_report_markdown(build_report(example_item()))


if __name__ == "__main__":
    item = example_item()
    model = build_report(item)
    md = render_report_markdown(model)
    print("SELECTED METHODS:")
    for row in model["defect_population"]:
        print("  %-45s -> %s (alts %s)"
              % (row["defect_name"], row["top_method"], row["alternates"]))
    print("CARDS: %s" % ", ".join(sorted(model["parameter_cards"])))
    p = model["personnel"]
    print("PERSONNEL: %s | supervision_ok=%s"
          % (p["review"]["certification_status"],
             p["review"]["supervision_ok"]))
    print("GATES: %s" % check_report(model))
    print("RENDERED: %d chars" % len(md))
