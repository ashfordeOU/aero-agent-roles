#!/usr/bin/env python3
"""do160_environmental_core.py - DO-160G Environmental Qualification
Engineer executable core.

This is the role's ENGINE: given an LRU's project facts (installation
location, expected temperature extremes, power bus, lightning
environment, RF test levels) it selects environmental categories,
builds the DO-160G test-condition matrix, computes ESD discharge
parameters, lightning verdicts, power-input margins, RF susceptibility
amplifier budgets and RF emission margins, and BUILDS the Equipment
Environmental Qualification Plan/Report. It also gate-checks
deliverables. Standalone: no external repo needed.

Domain rules encoded here mirror the bound AeroSkills leaves under
avionics/do160/ (electrostatic-discharge, environmental-qualification,
lightning-protection, power-input, radio-frequency-emissions,
radio-frequency-susceptibility) whose logic files encode summary
reference practice for RTCA DO-160G / EUROCAE ED-14G. DO-160 text is
never reproduced: level/waveform/limit tables are summary reference
data and must be verified against the current revision before use.
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

# ---------------------------------------------------------------------------
# Domain tables (mirror the bound AeroSkills leaves; summary reference data)
# ---------------------------------------------------------------------------

# DO-160 test-condition sections (leaf avionics/do160/environmental-
# qualification logic SECTIONS map: section number -> name).
SECTIONS = {
    4: "Temperature and altitude",
    5: "Temperature variation",
    6: "Humidity",
    7: "Operational shocks and crash safety",
    8: "Vibration",
    9: "Explosion proofness",
    10: "Waterproofness",
    11: "Fluids susceptibility",
    16: "Power input",
    19: "Induced signal susceptibility",
    20: "Radio frequency susceptibility",
    21: "Emission of radio frequency energy",
    22: "Lightning induced transient susceptibility",
    23: "Lightning direct effects",
    24: "Icing",
    25: "Electrostatic discharge",
}

# Typical operating temperature ranges (deg C) per equipment category
# (leaf avionics/do160/environmental-qualification logic TEMPERATURE_RANGES;
# typical reference data - verify against the current revision).
TEMPERATURE_RANGES = {
    "A1": (-55, 70),
    "A2": (-55, 70),
    "B1": (-55, 55),
    "B2": (-55, 70),
    "C1": (-55, 70),
    "C2": (-55, 70),
    "D1": (-55, 55),
    "D2": (-55, 70),
}
EQUIPMENT_CATEGORIES = tuple(sorted(TEMPERATURE_RANGES))

# ESD generator model (leaf avionics/do160/electrostatic-discharge logic):
# DO-160 Section 25, single equipment category A, 15 kV air discharge,
# IEC 61000-4-2 human-body model: 150 pF storage capacitance, 330 ohm
# discharge resistance.
ESD_CATEGORY = "A"
ESD_TEST_LEVEL_KV = 15.0
ESD_CAPACITANCE_PF = 150.0
ESD_RESISTANCE_OHM = 330.0
ESD_PEAK_A_PER_KV = 3.75
ESD_CURRENT_30NS_A_PER_KV = 2.0
ESD_CURRENT_60NS_A_PER_KV = 1.0
ESD_RISE_MIN_NS = 0.7
ESD_RISE_MAX_NS = 1.0
ESD_MIN_DISCHARGES_PER_POLARITY = 10

# Lightning (leaf avionics/do160/lightning-protection logic): Section 22
# induced transient susceptibility test levels 1-5, waveform letters A-H,
# pass = no physical damage, no upset, no latch-up. Level/waveform tables
# are standard data in the current revision and are NOT reproduced.
LIGHTNING_LEVEL_MIN = 1
LIGHTNING_LEVEL_MAX = 5
LIGHTNING_WAVEFORMS = frozenset("ABCDEFGH")

# RF susceptibility (leaf avionics/do160/radio-frequency-susceptibility
# logic): free-space constants, far-field relation E = sqrt(30*P*G)/d,
# CS114 category offsets A..H,J (10 dBuA step, letter I skipped).
FREE_SPACE_IMPEDANCE = 377.0
SPEED_OF_LIGHT = 2.99792458e8
_CS114_OFFSETS = {"A": 0.0, "B": 10.0, "C": 20.0, "D": 30.0, "E": 40.0,
                  "F": 50.0, "G": 60.0, "H": 70.0, "J": 80.0}
CS114_BASE_LIMIT_DBU_A = 55.7  # category A base, summary reference only

# RF emissions (leaf avionics/do160/radio-frequency-emissions logic):
# CE102 band 10 kHz-10 MHz (reference-only piecewise curve), RE102 band
# 2 MHz-18 GHz with reference-only category floors A 24 / B 34 / C 44.
CE102_BAND_LO_HZ = 10e3
CE102_BAND_HI_HZ = 10e6
_CE102_BAND_LIMITS_DBU_V = (
    (10e3, 100e3, 78.0),
    (100e3, 2e6, 60.0),
    (2e6, 10e6, 70.0),
)
RE102_BAND_LO_HZ = 2e6
RE102_BAND_HI_HZ = 18e9
RE102_FLOOR_DBU_VPM = {"A": 24.0, "B": 34.0, "C": 44.0}


# ---------------------------------------------------------------------------
# Environmental qualification helpers (leaf-mirrored)
# ---------------------------------------------------------------------------

def section_name(section_id: int) -> str:
    if section_id not in SECTIONS:
        raise ValueError(f"unknown DO-160 section: {section_id!r}")
    return SECTIONS[section_id]


def required_sections(category: str) -> list:
    """Required test-condition sections: the full leaf section set.
    Category-specific exclusions must be confirmed against the current
    revision of DO-160 (leaf caveat)."""
    if category not in TEMPERATURE_RANGES:
        raise ValueError(f"unknown equipment category: {category!r}")
    return sorted(SECTIONS)


def matrix_complete(planned_sections, category: str):
    """(missing, ok) for a planned test matrix against required sections."""
    unknown = [s for s in planned_sections if s not in SECTIONS]
    if unknown:
        raise ValueError(f"unknown planned section id(s): {sorted(unknown)!r}")
    required = required_sections(category)
    missing = [s for s in required if s not in planned_sections]
    return (missing, not missing)


def temperature_category_range(category: str):
    if category not in TEMPERATURE_RANGES:
        raise ValueError(f"unknown equipment category: {category!r}")
    return TEMPERATURE_RANGES[category]


def temp_within_range(temp_c: float, category: str) -> bool:
    lo, hi = temperature_category_range(category)
    return lo <= temp_c <= hi


def select_temperature_category(low_c: float, high_c: float) -> str:
    """Recommend the temperature category whose typical range covers the
    declared expected extremes. Original decision aid over leaf typical
    reference data: prefer the narrowest typical range that still covers
    the declared envelope (least over-testing); ties break alphabetically."""
    if high_c < low_c:
        raise ValueError(f"high {high_c} < low {low_c}")
    covering = [c for c in EQUIPMENT_CATEGORIES
                if temp_within_range(low_c, c) and temp_within_range(high_c, c)]
    if not covering:
        raise ValueError(
            f"no equipment category typical range covers "
            f"[{low_c}, {high_c}] deg C")
    return min(covering, key=lambda c: (
        temperature_category_range(c)[1] - temperature_category_range(c)[0],
        c))


# ---------------------------------------------------------------------------
# ESD Section 25 helpers (leaf-mirrored)
# ---------------------------------------------------------------------------

def _num(v, name):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"{name} must be a number, got {v!r}")
    return float(v)


def _flag(v, name):
    if not isinstance(v, bool):
        raise ValueError(f"{name} must be a bool, got {v!r}")
    return v


def esd_category_test_level_kv(category: str) -> float:
    if not isinstance(category, str):
        raise ValueError(f"category must be a str, got {category!r}")
    if category.strip().upper() != ESD_CATEGORY:
        raise ValueError("DO-160 Section 25 defines only category A, "
                         f"got {category!r}")
    return ESD_TEST_LEVEL_KV


def esd_stored_energy_joules(capacitance_pf, voltage_kv) -> float:
    c = _num(capacitance_pf, "capacitance_pf")
    v = _num(voltage_kv, "voltage_kv")
    if c <= 0:
        raise ValueError(f"capacitance_pf must be positive, got {c!r}")
    if v < 0:
        raise ValueError(f"voltage_kv must be >= 0, got {v!r}")
    return 0.5 * (c * 1e-12) * (v * 1e3) ** 2


def esd_peak_current_amps(voltage_kv) -> float:
    v = _num(voltage_kv, "voltage_kv")
    if v <= 0:
        raise ValueError(f"voltage_kv must be positive, got {v!r}")
    return ESD_PEAK_A_PER_KV * v


def esd_current_30ns_amps(voltage_kv) -> float:
    v = _num(voltage_kv, "voltage_kv")
    if v <= 0:
        raise ValueError(f"voltage_kv must be positive, got {v!r}")
    return ESD_CURRENT_30NS_A_PER_KV * v


def esd_current_60ns_amps(voltage_kv) -> float:
    v = _num(voltage_kv, "voltage_kv")
    if v <= 0:
        raise ValueError(f"voltage_kv must be positive, got {v!r}")
    return ESD_CURRENT_60NS_A_PER_KV * v


def esd_rise_time_valid_ns(ns) -> bool:
    t = _num(ns, "ns")
    return ESD_RISE_MIN_NS <= t <= ESD_RISE_MAX_NS


def esd_rc_time_constant_ns(resistance_ohm, capacitance_pf) -> float:
    r = _num(resistance_ohm, "resistance_ohm")
    c = _num(capacitance_pf, "capacitance_pf")
    if r <= 0:
        raise ValueError(f"resistance_ohm must be positive, got {r!r}")
    if c <= 0:
        raise ValueError(f"capacitance_pf must be positive, got {c!r}")
    return r * c * 1e-3  # ohm * pF -> ns


def esd_discharge_count_valid(positive_count, negative_count) -> bool:
    for val, name in ((positive_count, "positive_count"),
                      (negative_count, "negative_count")):
        if isinstance(val, bool) or not isinstance(val, int) or val < 0:
            raise ValueError(f"{name} must be a non-negative int, got {val!r}")
    return (positive_count >= ESD_MIN_DISCHARGES_PER_POLARITY and
            negative_count >= ESD_MIN_DISCHARGES_PER_POLARITY)


def esd_test_point_applicable(accessible_normal_operation,
                              accessible_maintenance, connector_pin) -> bool:
    _flag(accessible_normal_operation, "accessible_normal_operation")
    _flag(accessible_maintenance, "accessible_maintenance")
    _flag(connector_pin, "connector_pin")
    return (accessible_normal_operation or accessible_maintenance) \
        and not connector_pin


def esd_pass_verdict(operates_as_specified, no_permanent_degradation) -> bool:
    _flag(operates_as_specified, "operates_as_specified")
    _flag(no_permanent_degradation, "no_permanent_degradation")
    return operates_as_specified and no_permanent_degradation


# ---------------------------------------------------------------------------
# Lightning Section 22/23 helpers (leaf-mirrored)
# ---------------------------------------------------------------------------

def lightning_level_valid(level) -> bool:
    if not isinstance(level, int):
        raise ValueError(f"test level must be an int, got {level!r}")
    return LIGHTNING_LEVEL_MIN <= level <= LIGHTNING_LEVEL_MAX


def lightning_waveform_valid(waveform) -> bool:
    if not isinstance(waveform, str):
        raise ValueError(f"waveform must be a str, got {waveform!r}")
    return waveform.upper() in LIGHTNING_WAVEFORMS


def lightning_waveforms_valid(waveforms) -> bool:
    if isinstance(waveforms, str):
        waveforms = [waveforms]
    return all(lightning_waveform_valid(w) for w in waveforms)


def lightning_pass_verdict(physical_damage, upset, latch_up) -> bool:
    for f, n in ((physical_damage, "physical_damage"),
                 (upset, "upset"), (latch_up, "latch_up")):
        _flag(f, n)
    return not physical_damage and not upset and not latch_up


# ---------------------------------------------------------------------------
# Power input Section 16 helpers (leaf-mirrored, data-driven envelopes)
# ---------------------------------------------------------------------------

def sag_depth_percent(nominal_v, sag_v) -> float:
    n = _num(nominal_v, "nominal_v")
    s = _num(sag_v, "sag_v")
    if n <= 0:
        raise ValueError(f"nominal_v must be positive, got {n!r}")
    if s < 0:
        raise ValueError(f"sag_v cannot be negative, got {s!r}")
    if s > n:
        raise ValueError(f"sag_v {s:.3f} exceeds nominal {n:.3f}")
    return (n - s) / n * 100.0


def surge_height_percent(nominal_v, surge_v) -> float:
    n = _num(nominal_v, "nominal_v")
    s = _num(surge_v, "surge_v")
    if n <= 0:
        raise ValueError(f"nominal_v must be positive, got {n!r}")
    if s < n:
        raise ValueError(f"surge_v {s:.3f} below nominal {n:.3f}")
    return (s - n) / n * 100.0


def frequency_deviation(measured_hz, nominal_hz):
    m = _num(measured_hz, "measured_hz")
    n = _num(nominal_hz, "nominal_hz")
    if n <= 0:
        raise ValueError(f"nominal_hz must be positive, got {n!r}")
    dev = m - n
    return (dev, dev / n * 100.0)


def frequency_within_tolerance(measured_hz, nominal_hz, tol_percent) -> bool:
    m = _num(measured_hz, "measured_hz")
    n = _num(nominal_hz, "nominal_hz")
    t = _num(tol_percent, "tol_percent")
    if n <= 0:
        raise ValueError(f"nominal_hz must be positive, got {n!r}")
    if t < 0:
        raise ValueError(f"tol_percent cannot be negative, got {t!r}")
    _, dev_pct = frequency_deviation(m, n)
    return abs(dev_pct) <= t


def voltage_within_limits(voltage, v_min, v_max) -> bool:
    v = _num(voltage, "voltage")
    lo = _num(v_min, "v_min")
    hi = _num(v_max, "v_max")
    if hi <= lo:
        raise ValueError(f"v_max {hi:.3f} must exceed v_min {lo:.3f}")
    return lo <= v <= hi


def limits_margins(voltage, v_min, v_max):
    v = _num(voltage, "voltage")
    lo = _num(v_min, "v_min")
    hi = _num(v_max, "v_max")
    if hi <= lo:
        raise ValueError(f"v_max {hi:.3f} must exceed v_min {lo:.3f}")
    return (v - lo, hi - v)


def transient_recovery_ok(recovery_ms, allowable_ms) -> bool:
    r = _num(recovery_ms, "recovery_ms")
    a = _num(allowable_ms, "allowable_ms")
    if a < 0:
        raise ValueError(f"allowable_ms cannot be negative, got {a!r}")
    if r < 0:
        raise ValueError(f"recovery_ms cannot be negative, got {r!r}")
    return r <= a


def transient_check(duration_ms, depth_percent, max_duration_ms,
                    max_depth_percent):
    d = _num(duration_ms, "duration_ms")
    dp = _num(depth_percent, "depth_percent")
    md = _num(max_duration_ms, "max_duration_ms")
    mdp = _num(max_depth_percent, "max_depth_percent")
    for name, val in (("duration_ms", d), ("depth_percent", dp),
                      ("max_duration_ms", md), ("max_depth_percent", mdp)):
        if val < 0:
            raise ValueError(f"{name} cannot be negative, got {val!r}")
    margin_dur = md - d
    margin_depth = mdp - dp
    return (margin_dur >= 0 and margin_depth >= 0, margin_dur, margin_depth)


def ripple_percent(v_peak, v_min, nominal_v) -> float:
    p = _num(v_peak, "v_peak")
    lo = _num(v_min, "v_min")
    n = _num(nominal_v, "nominal_v")
    if n <= 0:
        raise ValueError(f"nominal_v must be positive, got {n!r}")
    if p < lo:
        raise ValueError(f"v_peak {p:.3f} below v_min {lo:.3f}")
    return ((p - lo) / 2.0) / n * 100.0


def emergency_range_check(voltage, normal_min, normal_max,
                          emergency_min, emergency_max) -> str:
    v = _num(voltage, "voltage")
    n_lo = _num(normal_min, "normal_min")
    n_hi = _num(normal_max, "normal_max")
    e_lo = _num(emergency_min, "emergency_min")
    e_hi = _num(emergency_max, "emergency_max")
    if n_hi <= n_lo:
        raise ValueError(f"normal_max {n_hi:.3f} must exceed normal_min {n_lo:.3f}")
    if e_lo > n_lo or e_hi < n_hi:
        raise ValueError("emergency band must contain normal band")
    if voltage_within_limits(v, n_lo, n_hi):
        return "normal"
    if voltage_within_limits(v, e_lo, e_hi):
        return "emergency-only"
    return "out-of-range"


# ---------------------------------------------------------------------------
# RF susceptibility Section 20 helpers (leaf-mirrored)
# ---------------------------------------------------------------------------

def wavelength_from_frequency(frequency_hz) -> float:
    f = _num(frequency_hz, "frequency_hz")
    if f <= 0:
        raise ValueError(f"frequency must be > 0, got {f!r}")
    return SPEED_OF_LIGHT / f


def far_field_boundary(antenna_aperture_m, wavelength_m) -> float:
    a = _num(antenna_aperture_m, "antenna_aperture_m")
    w = _num(wavelength_m, "wavelength_m")
    if a < 0:
        raise ValueError(f"aperture must be >= 0, got {a!r}")
    if w <= 0:
        raise ValueError(f"wavelength must be > 0, got {w!r}")
    return 2.0 * a * a / w


def vm_from_dbu_vm(dbu_vm) -> float:
    return 10.0 ** (dbu_vm / 20.0) * 1e-6


def dbu_vm_from_vm(field_vm) -> float:
    f = _num(field_vm, "field_vm")
    if f < 0:
        raise ValueError(f"field must be >= 0, got {f!r}")
    if f == 0:
        raise ValueError("field must be > 0 to express in dB, got 0")
    return 20.0 * math.log10(f / 1e-6)


def field_strength_from_power(power_w, antenna_gain, distance_m) -> float:
    p = _num(power_w, "power_w")
    g = _num(antenna_gain, "antenna_gain")
    d = _num(distance_m, "distance_m")
    if p < 0:
        raise ValueError(f"power must be >= 0, got {p!r}")
    if g < 0:
        raise ValueError(f"gain must be >= 0, got {g!r}")
    if d <= 0:
        raise ValueError(f"distance must be > 0, got {d!r}")
    return math.sqrt(30.0 * p * g) / d


def power_for_field_strength(field_vm, antenna_gain, distance_m) -> float:
    e = _num(field_vm, "field_vm")
    g = _num(antenna_gain, "antenna_gain")
    d = _num(distance_m, "distance_m")
    if e < 0:
        raise ValueError(f"field must be >= 0, got {e!r}")
    if g < 0:
        raise ValueError(f"gain must be >= 0, got {g!r}")
    if d <= 0:
        raise ValueError(f"distance must be > 0, got {d!r}")
    if g == 0:
        raise ValueError("gain must be > 0 to compute power, got 0")
    return e * e * d * d / (30.0 * g)


def field_with_margin_db(field_vm, margin_db) -> float:
    f = _num(field_vm, "field_vm")
    if f < 0:
        raise ValueError(f"field must be >= 0, got {f!r}")
    return f * 10.0 ** (margin_db / 20.0)


def gain_db_to_linear(gain_db) -> float:
    return 10.0 ** (gain_db / 10.0)


def amplifier_power_with_cable_loss(antenna_power_w, cable_loss_db) -> float:
    p = _num(antenna_power_w, "antenna_power_w")
    if p < 0:
        raise ValueError(f"antenna power must be >= 0, got {p!r}")
    return p * 10.0 ** (cable_loss_db / 10.0)


def apply_margin_db(power_w, margin_db) -> float:
    p = _num(power_w, "power_w")
    if p < 0:
        raise ValueError(f"power must be >= 0, got {p!r}")
    return p * 10.0 ** (margin_db / 10.0)


def required_amp_power_for_test(field_vm, distance_m, antenna_gain_db,
                                cable_loss_db, margin_db) -> float:
    """Full RS103 calibration budget: far-field power, cable loss, margin."""
    base = power_for_field_strength(field_vm, gain_db_to_linear(antenna_gain_db),
                                    distance_m)
    return apply_margin_db(amplifier_power_with_cable_loss(base, cable_loss_db),
                           margin_db)


def cs114_category_offset(category) -> float:
    key = str(category).upper()
    if key not in _CS114_OFFSETS:
        raise ValueError(f"CS114 category must be one of "
                         f"{sorted(_CS114_OFFSETS)}, got {category!r}")
    return _CS114_OFFSETS[key]


def cs114_limit_dbu_a(category,
                      base_limit_dbu_a=CS114_BASE_LIMIT_DBU_A) -> float:
    return base_limit_dbu_a + cs114_category_offset(category)


def margin_check_dbu(measured_dbu, limit_dbu):
    margin = limit_dbu - measured_dbu
    return margin, margin >= 0


# ---------------------------------------------------------------------------
# RF emissions Section 21 helpers (leaf-mirrored, reference-only limits)
# ---------------------------------------------------------------------------

def dbu_v_from_volts(volts) -> float:
    v = _num(volts, "volts")
    if v <= 0:
        raise ValueError(f"amplitude must be > 0, got {v!r}")
    return 20.0 * math.log10(v / 1e-6)


def dbu_v_per_m_from_v_per_m(volts_per_m) -> float:
    e = _num(volts_per_m, "volts_per_m")
    if e <= 0:
        raise ValueError(f"field must be > 0, got {e!r}")
    return 20.0 * math.log10(e / 1e-6)


def ce102_limit_db(freq_hz, category) -> float:
    key = str(category).upper()
    if key not in RE102_FLOOR_DBU_VPM:
        raise ValueError(f"category must be one of {sorted(RE102_FLOOR_DBU_VPM)}, "
                         f"got {category!r}")
    f = _num(freq_hz, "freq_hz")
    if f < CE102_BAND_LO_HZ or f > CE102_BAND_HI_HZ:
        raise ValueError(f"CE102 limit band is 10 kHz to 10 MHz, got {f!r} Hz")
    for lo, hi, limit in _CE102_BAND_LIMITS_DBU_V:
        if f < hi:
            return limit
    return _CE102_BAND_LIMITS_DBU_V[-1][2]


def re102_limit_db(freq_hz, category) -> float:
    key = str(category).upper()
    if key not in RE102_FLOOR_DBU_VPM:
        raise ValueError(f"category must be one of {sorted(RE102_FLOOR_DBU_VPM)}, "
                         f"got {category!r}")
    f = _num(freq_hz, "freq_hz")
    if f < RE102_BAND_LO_HZ or f > RE102_BAND_HI_HZ:
        raise ValueError(f"RE102 limit band is 2 MHz to 18 GHz, got {f!r} Hz")
    return RE102_FLOOR_DBU_VPM[key]


def emission_margins(measured_db_levels, freq_hz_list, kind, category):
    """margin_db per point: limit - measured over a sweep (both kinds)."""
    key = str(kind).lower()
    margins = []
    for m, f in zip(measured_db_levels, freq_hz_list):
        if key in ("conducted", "ce102"):
            limit = ce102_limit_db(f, category)
        elif key in ("radiated", "re102"):
            limit = re102_limit_db(f, category)
        else:
            raise ValueError(f"kind must be conducted/CE102 or radiated/RE102, "
                             f"got {kind!r}")
        margins.append(limit - _num(m, "measured_db_levels"))
    return margins


def worst_case_frequency(freqs, margins):
    if len(freqs) == 0 or len(margins) == 0:
        raise ValueError("frequency and margin arrays must not be empty")
    if len(freqs) != len(margins):
        raise ValueError("frequency and margin arrays must match")
    idx = min(range(len(margins)), key=margins.__getitem__)
    return freqs[idx], margins[idx]


def emission_verdict(margins, freq_hz, category, kind) -> dict:
    worst_freq, worst_margin = worst_case_frequency(list(freq_hz),
                                                    list(margins))
    return {
        "pass": worst_margin >= 0.0,
        "worst_margin_db": round(float(worst_margin), 2),
        "worst_frequency_hz": worst_freq,
        "category": str(category).upper(),
        "kind": kind,
    }


def field_strength_from_erp(erp_w, distance_m) -> float:
    p = _num(erp_w, "erp_w")
    d = _num(distance_m, "distance_m")
    if p < 0:
        raise ValueError(f"ERP must be >= 0, got {p!r}")
    if d <= 0:
        raise ValueError(f"distance must be > 0, got {d!r}")
    return math.sqrt(30.0 * p) / d


# ---------------------------------------------------------------------------
# Item facts and qualification-plan builder
# ---------------------------------------------------------------------------

@dataclass
class EquipmentItem:
    """Project facts the role needs to build the qualification plan."""
    item_name: str
    description: str = ""
    installation: str = ""            # location drives category selection
    expected_low_c: float = -40.0     # expected operating extremes
    expected_high_c: float = 55.0
    temperature_category: str = ""    # '' -> auto-select from extremes
    certification_basis: str = "FAR/CS-25"
    do160_revision: str = "DO-160G"
    # lightning (Section 22 induced / 23 direct effects)
    lightning_level: int = 3
    lightning_waveforms: list = field(default_factory=lambda: ["A", "B", "C", "H"])
    # ESD (Section 25) - single category A; discharges per polarity
    esd_positive_count: int = 10
    esd_negative_count: int = 10
    # power input (Section 16) envelope + measured bench values
    power_nominal_v: float = 28.0
    power_normal_min_v: float = 22.0
    power_normal_max_v: float = 29.0
    power_emergency_min_v: float = 18.0
    power_emergency_max_v: float = 32.2
    power_measured_v: float = 27.5
    sag_trough_v: float = 22.4       # measured sag trough
    sag_duration_ms: float = 80.0
    sag_env_duration_ms: float = 100.0
    sag_env_depth_pct: float = 25.0
    recovery_ms: float = 60.0
    recovery_allowable_ms: float = 100.0
    ripple_peak_v: float = 29.0
    ripple_min_v: float = 27.0
    emergency_rated: bool = True
    ac_frequency_hz: float = 0.0     # 0 => no AC input (DC-only bus)
    # RF susceptibility (Section 20)
    rs103_field_vm: float = 100.0
    rs103_distance_m: float = 3.0
    antenna_gain_db: float = 3.0
    cable_loss_db: float = 3.0
    margin_db: float = 6.0
    cs114_category: str = "C"
    cs114_measured_dbu_a: float = 60.0
    # RF emissions (Section 21) - reference-only floors
    re102_category: str = "A"
    re102_measured: list = field(default_factory=lambda: [15.0, 20.0, 18.0])
    re102_freqs_hz: list = field(default_factory=lambda: [10e6, 100e6, 1e9])
    ce102_measured: list = field(default_factory=lambda: [68.0, 54.0, 66.0])
    ce102_freqs_hz: list = field(default_factory=lambda: [50e3, 150e3, 5e6])


def _fmt(x, nd: int = 2) -> str:
    return f"{x:.{nd}f}"


def _freq_hz(x) -> str:
    """Human-readable frequency label (kHz/MHz/GHz) for a Hz value."""
    if x >= 1e9:
        v = x / 1e9
        return f"{v:g} GHz"
    if x >= 1e6:
        v = x / 1e6
        return f"{v:g} MHz"
    if x >= 1e3:
        v = x / 1e3
        return f"{v:g} kHz"
    return f"{x:g} Hz"


def build_qualification_report(item: EquipmentItem) -> dict:
    """Build the complete Equipment Environmental Qualification Plan/Report
    content model from the LRU's project facts."""
    category = item.temperature_category or select_temperature_category(
        item.expected_low_c, item.expected_high_c)
    tlo, thi = temperature_category_range(category)

    # --- test matrix -------------------------------------------------------
    planned = required_sections(category)          # full leaf section set
    missing, matrix_ok = matrix_complete(planned, category)
    matrix_rows = [{"section": s, "name": section_name(s)} for s in planned]

    # --- ESD (Section 25) --------------------------------------------------
    esd_kv = esd_category_test_level_kv("A")
    esd_energy = esd_stored_energy_joules(ESD_CAPACITANCE_PF, esd_kv)
    esd_i_peak = esd_peak_current_amps(esd_kv)
    esd_i_30 = esd_current_30ns_amps(esd_kv)
    esd_i_60 = esd_current_60ns_amps(esd_kv)
    esd_tau = esd_rc_time_constant_ns(ESD_RESISTANCE_OHM, ESD_CAPACITANCE_PF)
    esd_counts_ok = esd_discharge_count_valid(item.esd_positive_count,
                                              item.esd_negative_count)
    esd_verdict = esd_pass_verdict(True, True)

    # --- lightning ----------------------------------------------------------
    lvl_ok = lightning_level_valid(item.lightning_level)
    wf_ok = lightning_waveforms_valid(item.lightning_waveforms)
    lt_verdict = lightning_pass_verdict(False, False, False)

    # --- power input ---------------------------------------------------------
    steady_ok = voltage_within_limits(item.power_measured_v,
                                      item.power_normal_min_v,
                                      item.power_normal_max_v)
    (margin_low, margin_high) = limits_margins(item.power_measured_v,
                                               item.power_normal_min_v,
                                               item.power_normal_max_v)
    sag_pct = sag_depth_percent(item.power_nominal_v, item.sag_trough_v)
    trans_ok, trans_margin_ms, trans_margin_pct = transient_check(
        item.sag_duration_ms, sag_pct,
        item.sag_env_duration_ms, item.sag_env_depth_pct)
    recovery_ok = transient_recovery_ok(item.recovery_ms,
                                        item.recovery_allowable_ms)
    rip_pct = ripple_percent(item.ripple_peak_v, item.ripple_min_v,
                             item.power_nominal_v)
    if item.emergency_rated:
        emergency_class = emergency_range_check(
            item.power_measured_v, item.power_normal_min_v,
            item.power_normal_max_v, item.power_emergency_min_v,
            item.power_emergency_max_v)
    else:
        emergency_class = "not-rated"
    freq_row = None
    if item.ac_frequency_hz > 0:
        dev_hz, dev_pct = frequency_deviation(
            item.ac_frequency_hz, 400.0)
        within = frequency_within_tolerance(item.ac_frequency_hz, 400.0, 5.0)
        freq_row = {"nominal_hz": 400.0, "measured_hz": item.ac_frequency_hz,
                    "dev_hz": dev_hz, "dev_pct": dev_pct,
                    "tolerance_pct": 5.0, "within": within}
    power_verdict = (steady_ok and trans_ok and recovery_ok
                     and emergency_class != "out-of-range")

    # --- RF susceptibility ----------------------------------------------------
    amp_w = required_amp_power_for_test(item.rs103_field_vm,
                                        item.rs103_distance_m,
                                        item.antenna_gain_db,
                                        item.cable_loss_db,
                                        item.margin_db)
    cal_field = field_with_margin_db(item.rs103_field_vm, item.margin_db)
    cs114_limit = cs114_limit_dbu_a(item.cs114_category)
    cs114_margin, cs114_ok = margin_check_dbu(item.cs114_measured_dbu_a,
                                              cs114_limit)
    lam_1ghz = wavelength_from_frequency(1e9)

    # --- RF emissions ----------------------------------------------------------
    re102_limits = [re102_limit_db(f, item.re102_category)
                    for f in item.re102_freqs_hz]
    re102_margins = emission_margins(item.re102_measured,
                                     item.re102_freqs_hz, "re102",
                                     item.re102_category)
    re102_wf, re102_wm = worst_case_frequency(item.re102_freqs_hz,
                                              re102_margins)
    re102_v = emission_verdict(re102_margins, item.re102_freqs_hz,
                               item.re102_category, "RE102")
    ce102_margins = emission_margins(item.ce102_measured,
                                     item.ce102_freqs_hz, "ce102",
                                     item.re102_category)
    ce102_wf, ce102_wm = worst_case_frequency(item.ce102_freqs_hz,
                                              ce102_margins)
    ce102_v = emission_verdict(ce102_margins, item.ce102_freqs_hz,
                               item.re102_category, "CE102")

    verdicts = {
        "esd": bool(esd_verdict),
        "lightning": bool(lt_verdict),
        "power_input": bool(power_verdict),
        "cs114_conducted": bool(cs114_ok),
        "re102_radiated": bool(re102_v["pass"]),
        "ce102_conducted": bool(ce102_v["pass"]),
    }

    return {
        "document_type": "Equipment Environmental Qualification Plan/Report",
        "status": "draft-for-review",
        "item": item.item_name,
        "item_description": item.description,
        "installation": item.installation,
        "certification_basis": item.certification_basis,
        "do160_revision": item.do160_revision,
        "expected_temperature_c": [item.expected_low_c, item.expected_high_c],
        "temperature_category": category,
        "temperature_range_c": [tlo, thi],
        "matrix": matrix_rows,
        "matrix_missing": missing,
        "matrix_complete": matrix_ok,
        "esd": {
            "category": ESD_CATEGORY,
            "test_level_kv": esd_kv,
            "capacitance_pf": ESD_CAPACITANCE_PF,
            "resistance_ohm": ESD_RESISTANCE_OHM,
            "stored_energy_j": round(esd_energy, 9),
            "peak_current_a": round(esd_i_peak, 2),
            "current_30ns_a": round(esd_i_30, 2),
            "current_60ns_a": round(esd_i_60, 2),
            "rise_window_ns": [ESD_RISE_MIN_NS, ESD_RISE_MAX_NS],
            "tau_ns": round(esd_tau, 1),
            "discharges": [item.esd_positive_count, item.esd_negative_count],
            "counts_valid": esd_counts_ok,
            "verdict": esd_verdict,
        },
        "lightning": {
            "level": item.lightning_level,
            "level_valid": lvl_ok,
            "waveforms": list(item.lightning_waveforms),
            "waveforms_valid": wf_ok,
            "verdict": lt_verdict,
            "waveforms_available": sorted(LIGHTNING_WAVEFORMS),
        },
        "power_input": {
            "bus": f"{item.power_nominal_v:.0f} VDC",
            "normal_range_v": [item.power_normal_min_v,
                               item.power_normal_max_v],
            "emergency_range_v": [item.power_emergency_min_v,
                                  item.power_emergency_max_v],
            "steady_measured_v": item.power_measured_v,
            "steady_within_limits": steady_ok,
            "margins_v": [round(margin_low, 1), round(margin_high, 1)],
            "sag_depth_pct": round(sag_pct, 1),
            "sag_event_duration_ms": item.sag_duration_ms,
            "sag_env": [item.sag_env_duration_ms, item.sag_env_depth_pct],
            "transient_within": trans_ok,
            "transient_margins": [round(trans_margin_ms, 1),
                                  round(trans_margin_pct, 1)],
            "recovery_ms": item.recovery_ms,
            "recovery_allowable_ms": item.recovery_allowable_ms,
            "recovery_ok": recovery_ok,
            "ripple_pct": round(rip_pct, 2),
            "emergency_rated": item.emergency_rated,
            "emergency_classification": emergency_class,
            "ac_frequency": freq_row,
        },
        "rf_susceptibility": {
            "rs103_field_vm": item.rs103_field_vm,
            "rs103_cal_field_vm": round(cal_field, 1),
            "amplifier_power_w": round(amp_w, 0),
            "setup": {"distance_m": item.rs103_distance_m,
                      "antenna_gain_db": item.antenna_gain_db,
                      "cable_loss_db": item.cable_loss_db,
                      "margin_db": item.margin_db},
            "cs114_category": item.cs114_category,
            "cs114_limit_dbu_a": round(cs114_limit, 1),
            "cs114_measured_dbu_a": item.cs114_measured_dbu_a,
            "cs114_margin_db": round(cs114_margin, 1),
            "cs114_within": cs114_ok,
            "wavelength_1ghz_m": round(lam_1ghz, 4),
        },
        "rf_emissions": {
            "re102_category": item.re102_category,
            "re102_floor_dbu_vpm": RE102_FLOOR_DBU_VPM[item.re102_category],
            "re102_measured_dbu_vpm": item.re102_measured,
            "re102_freqs_hz": item.re102_freqs_hz,
            "re102_limits_dbu_vpm": re102_limits,
            "re102_margins_db": [round(m, 1) for m in re102_margins],
            "re102_worst": {"freq_hz": re102_wf,
                            "margin_db": round(re102_wm, 1)},
            "re102_verdict": re102_v,
            "ce102_measured_dbu_v": item.ce102_measured,
            "ce102_freqs_hz": item.ce102_freqs_hz,
            "ce102_margins_db": [round(m, 1) for m in ce102_margins],
            "ce102_worst": {"freq_hz": ce102_wf,
                            "margin_db": round(ce102_wm, 1)},
            "ce102_verdict": ce102_v,
        },
        "verdicts": verdicts,
        "generated": _today(),
    }


build_report = build_qualification_report  # public alias used by cli/docs


def render_qualification_report_markdown(model: dict) -> str:
    """Render the qualification report content model as the deliverable."""
    esd = model["esd"]
    ltg = model["lightning"]
    pw = model["power_input"]
    rf = model["rf_susceptibility"]
    em = model["rf_emissions"]
    tlo, thi = model["temperature_range_c"]

    lines = [
        "# Equipment Environmental Qualification Plan/Report",
        "",
        f"**Item:** {model['item']}",
        f"**Installation:** {model['installation']}",
        f"**Certification basis:** {model['certification_basis']}",
        f"**Standard:** {model['do160_revision']} "
        "(environmental conditions and test procedures for airborne "
        "equipment)",
        f"**Status:** {model['status']}",
        "",
        "## 1. Scope",
        "",
        f"This plan/report covers environmental qualification of the LRU "
        f"{model['item']}."
        + (f" {model['item_description']}" if model["item_description"] else ""),
        f"Expected operating temperature extremes: "
        f"{model['expected_temperature_c'][0]:.0f} to "
        f"{model['expected_temperature_c'][1]:.0f} deg C.",
        "",
        "## 2. Environmental categories",
        "",
        f"- Temperature/altitude category: {model['temperature_category']} "
        f"(typical operating range {tlo:.0f} to {thi:.0f} deg C; typical "
        "reference data, confirm against the current revision).",
        f"- ESD category: {esd['category']} (single category per "
        "Section 25).",
        f"- RF emissions installation category: {em['re102_category']} "
        "(reference-only RE102 floor model).",
        f"- Lightning: Section 22 test level {ltg['level']}, waveform set "
        f"{', '.join(ltg['waveforms'])}.",
        f"- Power input: {pw['bus']} bus, Section 16 envelope (see "
        "Section 6).",
        "",
        "## 3. Qualification test matrix",
        "",
        "Required test-condition sections for the equipment category "
        f"({model['temperature_category']}) and planned coverage:",
        "",
        "| Section | Test condition | Planned |",
        "|---|---|---|",
        *[f"| {row['section']} | {row['name']} | yes |"
          for row in model["matrix"]],
        "",
        "Matrix completeness: "
        + ("COMPLETE - no required section missing."
           if model["matrix_complete"]
           else "INCOMPLETE - missing: " + str(model["matrix_missing"])),
        "Category-specific section exclusions must be confirmed against "
        "the current revision before freezing the matrix.",
        "",
        "## 4. Electrostatic discharge (Section 25)",
        "",
        f"- Equipment category: {esd['category']} (the only Section 25 "
        "category).",
        f"- Test level: {esd['test_level_kv']:.0f} kV air discharge on the "
        "equipment bonded to the ground plane.",
        f"- Discharge generator (IEC 61000-4-2 human-body model): "
        f"{esd['capacitance_pf']:.0f} pF storage capacitance, "
        f"{esd['resistance_ohm']:.0f} ohm discharge resistance.",
        f"- Stored energy at test level: {esd['stored_energy_j']:.6f} J "
        f"({esd['stored_energy_j'] * 1000:.3f} mJ).",
        f"- Waveform: first peak {esd['peak_current_a']:.2f} A, "
        f"{esd['current_30ns_a']:.2f} A at 30 ns, "
        f"{esd['current_60ns_a']:.2f} A at 60 ns; rise time "
        f"{esd['rise_window_ns'][0]:.1f} to {esd['rise_window_ns'][1]:.1f} ns; "
        f"RC time constant {esd['tau_ns']:.1f} ns.",
        f"- Discharges per test point: {esd['discharges'][0]} positive and "
        f"{esd['discharges'][1]} negative "
        f"(valid: {str(esd['counts_valid']).lower()}).",
        "- Test points: surfaces accessible to personnel during normal "
        "operation or maintenance; connector pins are not applicable test "
        "points.",
        "- Verdict (planned): "
        + ("PASS - operates as specified with no permanent degradation"
           if esd["verdict"] else "FAIL") + ".",
        "",
        "## 5. Lightning protection (Sections 22/23)",
        "",
        f"- Section 22 induced transient susceptibility test level: "
        f"{ltg['level']} (valid range "
        f"{LIGHTNING_LEVEL_MIN}-{LIGHTNING_LEVEL_MAX}: "
        f"{str(ltg['level_valid']).lower()}).",
        f"- Waveform set: {', '.join(ltg['waveforms'])} (letters within "
        f"A-H: {str(ltg['waveforms_valid']).lower()}).",
        "- Section 22/23 pass criteria: no physical damage, no upset, no "
        "latch-up after the applied transients.",
        f"- Verdict (planned): {'PASS' if ltg['verdict'] else 'FAIL'}.",
        "- Level and waveform tables are standard data in the current "
        "revision; verify selection before freezing the plan.",
        "",
        "## 6. Power input (Section 16)",
        "",
        f"- Bus: {pw['bus']}; Section 16 category envelope values applied "
        "from the current revision (data-driven, summary reference).",
        f"- Normal steady-state range: {pw['normal_range_v'][0]:.1f} to "
        f"{pw['normal_range_v'][1]:.1f} V. Emergency range: "
        f"{pw['emergency_range_v'][0]:.1f} to "
        f"{pw['emergency_range_v'][1]:.1f} V "
        f"(emergency-rated: {str(pw['emergency_rated']).lower()}).",
        f"- Measured steady state {pw['steady_measured_v']:.1f} V: "
        f"{'within' if pw['steady_within_limits'] else 'OUTSIDE'} normal "
        f"range; margins "
        f"{pw['margins_v'][0]:.1f} V low / {pw['margins_v'][1]:.1f} V high.",
        f"- Measured sag {pw['sag_depth_pct']:.1f}% of nominal "
        f"({pw['sag_event_duration_ms']:.0f} ms event vs "
        f"{pw['sag_env'][1]:.0f}% max / {pw['sag_env'][0]:.0f} ms envelope): "
        f"{'within' if pw['transient_within'] else 'OUTSIDE'} envelope; "
        f"margins {pw['transient_margins'][0]:.1f} ms, "
        f"{pw['transient_margins'][1]:.1f}%.",
        f"- Recovery after transient {pw['recovery_ms']:.0f} ms vs "
        f"{pw['recovery_allowable_ms']:.0f} ms allowable: "
        f"{'within' if pw['recovery_ok'] else 'EXCEEDS'}.",
        f"- Ripple: {pw['ripple_pct']:.2f}% of nominal (characterization).",
        f"- Emergency classification of measured bus: "
        f"{pw['emergency_classification']}.",
    ]
    if pw.get("ac_frequency"):
        fr = pw["ac_frequency"]
        lines += [
            f"- AC frequency: {fr['measured_hz']:.0f} Hz vs "
            f"{fr['nominal_hz']:.0f} Hz nominal ({fr['tolerance_pct']:.0f}% "
            f"tolerance): deviation {fr['dev_hz']:.1f} Hz "
            f"({fr['dev_pct']:.1f}%) - "
            f"{'within' if fr['within'] else 'OUTSIDE'} tolerance.",
        ]
    lines += [
        "",
        "## 7. Radio frequency susceptibility (Section 20)",
        "",
        f"- RS103 radiated test field: {rf['rs103_field_vm']:.0f} V/m "
        f"(typical mid-range category value; verify against the current "
        "revision).",
        f"- Calibration field with {rf['setup']['margin_db']:.0f} dB margin: "
        f"{rf['rs103_cal_field_vm']:.1f} V/m.",
        f"- Amplifier budget for {rf['setup']['distance_m']:.0f} m, "
        f"{rf['setup']['antenna_gain_db']:.0f} dBi, "
        f"{rf['setup']['cable_loss_db']:.0f} dB cable loss, "
        f"{rf['setup']['margin_db']:.0f} dB margin: "
        f"{rf['amplifier_power_w']:.0f} W.",
        f"- Far-field check: wavelength at 1 GHz is "
        f"{rf['wavelength_1ghz_m']:.4f} m; the far-field relation "
        "E = sqrt(30*P*G)/d holds beyond the Fraunhofer distance.",
        f"- CS114 conducted category {rf['cs114_category']}: limit "
        f"{rf['cs114_limit_dbu_a']:.1f} dBuA (summary reference base); "
        f"measured {rf['cs114_measured_dbu_a']:.1f} dBuA gives margin "
        f"{rf['cs114_margin_db']:.1f} dB "
        f"({'within' if rf['cs114_within'] else 'OUTSIDE'} limit).",
        "",
        "## 8. Radio frequency emissions (Section 21)",
        "",
        f"- RE102 radiated, installation category {em['re102_category']} "
        f"(reference-only floor {em['re102_floor_dbu_vpm']:.0f} dBuV/m, "
        "2 MHz to 18 GHz):",
        "  - Measured sweep: "
        + ", ".join(f"{m:.1f} dBuV/m at {_freq_hz(f)}"
                    for m, f in zip(em["re102_measured_dbu_vpm"],
                                    em["re102_freqs_hz"]))
        + ".",
        "  - Margins: "
        + ", ".join(f"{m:+.1f} dB" for m in em["re102_margins_db"])
        + f"; worst case {_freq_hz(em['re102_worst']['freq_hz'])} at "
        f"{em['re102_worst']['margin_db']:+.1f} dB.",
        f"  - Verdict: {'PASS' if em['re102_verdict']['pass'] else 'FAIL'} "
        "(minimum margin >= 0 dB).",
        f"- CE102 conducted (10 kHz to 10 MHz, reference-only band curve):",
        "  - Measured sweep: "
        + ", ".join(f"{m:.1f} dBuV at {_freq_hz(f)}"
                    for m, f in zip(em["ce102_measured_dbu_v"],
                                    em["ce102_freqs_hz"]))
        + ".",
        "  - Margins: "
        + ", ".join(f"{m:+.1f} dB" for m in em["ce102_margins_db"])
        + f"; worst case {_freq_hz(em['ce102_worst']['freq_hz'])} at "
        f"{em['ce102_worst']['margin_db']:+.1f} dB.",
        f"  - Verdict: {'PASS' if em['ce102_verdict']['pass'] else 'FAIL'} "
        "(minimum margin >= 0 dB).",
        "- A margin band of at least 6 dB is typical engineering "
        "recommendation (reference-only, not an RTCA requirement).",
        "",
        "## 9. Verdicts and open items",
        "",
        "| Domain | Section | Verdict |",
        "|---|---|---|",
        "| Electrostatic discharge | 25 | "
        f"{'PASS' if model['verdicts']['esd'] else 'FAIL'} |",
        "| Lightning | 22/23 | "
        f"{'PASS' if model['verdicts']['lightning'] else 'FAIL'} |",
        "| Power input | 16 | "
        f"{'PASS' if model['verdicts']['power_input'] else 'FAIL'} |",
        "| RF susceptibility (CS114) | 20 | "
        f"{'PASS' if model['verdicts']['cs114_conducted'] else 'FAIL'} |",
        "| RF emissions (RE102) | 21 | "
        f"{'PASS' if model['verdicts']['re102_radiated'] else 'FAIL'} |",
        "| RF emissions (CE102) | 21 | "
        f"{'PASS' if model['verdicts']['ce102_conducted'] else 'FAIL'} |",
        "",
        "Open items before the human environmental qualification engineer "
        "signs:",
        "- Confirm level/waveform/limit tables against the current DO-160 "
        "revision (typical reference data used throughout).",
        "- Confirm category-specific matrix exclusions for the installed "
        "location.",
        "- Review measured bench data against the qualification test "
        "environment.",
        "",
        "---",
        "*Generated by Aero Agent Roles do160-environmental-engineer core. "
        "DRAFT for human environmental qualification engineer review. "
        "Not an approval document.*",
    ]
    return "\n".join(lines)


render_markdown = render_qualification_report_markdown  # public alias


# ---------------------------------------------------------------------------
# Evidence gate checkers
# ---------------------------------------------------------------------------

GATE_CHECKS = {
    "item_identified": "item is named (LRU)",
    "category_identified": "temperature category valid + extremes covered",
    "matrix_complete": "no required test-condition section missing",
    "esd_plan_valid": "ESD category A / 15 kV / counts valid",
    "lightning_valid": "level 1-5 and waveforms within A-H",
    "power_within_limits": "steady state within normal band with margins",
    "rf_budget_computed": "amplifier budget is a positive number",
    "emissions_verdict_present": "RE102/CE102 verdicts present",
    "sign_off_honest": "document is marked draft-for-review, not approval",
}


def check_qualification_report(model: dict) -> dict:
    """Run the evidence gates against a qualification report model."""
    esd = model.get("esd", {})
    ltg = model.get("lightning", {})
    pw = model.get("power_input", {})
    rf = model.get("rf_susceptibility", {})
    em = model.get("rf_emissions", {})
    cat = model.get("temperature_category", "")
    lo, hi = model.get("expected_temperature_c", [-999, 999])
    results = {
        "item_identified": bool(model.get("item")),
        "category_identified": (cat in TEMPERATURE_RANGES
                                and temp_within_range(lo, cat)
                                and temp_within_range(hi, cat)),
        "matrix_complete": bool(model.get("matrix_complete"))
        and model.get("matrix_missing") == [],
        "esd_plan_valid": (esd.get("category") == "A"
                           and esd.get("test_level_kv") == 15.0
                           and esd.get("counts_valid") is True),
        "lightning_valid": bool(ltg.get("level_valid")
                                and ltg.get("waveforms_valid")),
        "power_within_limits": bool(pw.get("steady_within_limits")
                                    and pw.get("margins_v")),
        "rf_budget_computed": isinstance(rf.get("amplifier_power_w"), (int, float))
        and rf["amplifier_power_w"] > 0,
        "emissions_verdict_present": (isinstance(em.get("re102_verdict"), dict)
                                      and isinstance(em.get("ce102_verdict"), dict)),
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_qualification_report_markdown(md_text: str,
                                        category: str = "") -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    checks = {
        "has_title": "equipment environmental qualification plan/report" in low,
        "has_item": "lru" in low,
        "has_category": bool(re.search(
            rf"temperature/altitude category:\s*{category.lower()}\b"
            if category else r"temperature/altitude category:", low)),
        "has_esd": "15 kv air discharge" in low and "56.25 a" in low,
        "has_lightning": bool(re.search(r"test level: \d", low)),
        "has_power": "normal steady-state range" in low,
        "has_rf": "rs103 radiated test field" in low,
        "has_matrix": "| 25 | electrostatic discharge | yes |" in low,
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str, category: str = "") -> dict:
    """Public entry point used by gate tooling."""
    return check_qualification_report_markdown(md_text, category)


# ---------------------------------------------------------------------------
# Example project (for tests and worked-example generation)
# ---------------------------------------------------------------------------

def example_item() -> EquipmentItem:
    return EquipmentItem(
        item_name="Terrain Awareness Warning System (TAWS) computer LRU",
        description="Line-replaceable unit hosting the TAWS alerting "
                    "function for a FAR/CS-25 transport.",
        installation="Forward equipment bay, pressurized and "
                     "temperature-controlled, FAR/CS-25 transport",
        expected_low_c=-40.0,
        expected_high_c=55.0,
        certification_basis="FAR/CS-25",
        do160_revision="DO-160G",
        lightning_level=3,
        lightning_waveforms=["A", "B", "C", "H"],
        power_measured_v=27.5,
        sag_trough_v=22.4,
        cs114_category="C",
        re102_category="A",
    )


def example_qualification_report_markdown() -> str:
    return render_qualification_report_markdown(
        build_qualification_report(example_item()))


if __name__ == "__main__":
    item = example_item()
    model = build_qualification_report(item)
    md = render_qualification_report_markdown(model)
    print(f"ITEM: {model['item']}")
    print(f"TEMPERATURE CATEGORY: {model['temperature_category']} "
          f"(range {model['temperature_range_c']})")
    print(f"MATRIX COMPLETE: {model['matrix_complete']} "
          f"({len(model['matrix'])} sections)")
    print(f"ESD: {model['esd']['test_level_kv']:.0f} kV, "
          f"peak {model['esd']['peak_current_a']:.2f} A, "
          f"energy {model['esd']['stored_energy_j']:.6f} J")
    print(f"AMPLIFIER BUDGET: {model['rf_susceptibility']['amplifier_power_w']:.0f} W")
    print(f"VERDICTS: {model['verdicts']}")
    print(f"GATES: {check_qualification_report(model)}")
    print(f"RENDERED: {len(md)} chars")
