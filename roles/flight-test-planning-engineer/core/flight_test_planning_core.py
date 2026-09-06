#!/usr/bin/env python3
"""flight_test_planning_core.py - Flight Test Planning Engineer executable core.

Author: ashfordeOU · Aero Agent Roles (agentskills.io ROLE.md host).

This is the role's ENGINE: given a flight test campaign and its facts it
runs the flight-test-operations/planning domain rules encoded by the
bound AeroSkills leaves - Nyquist-rate instrumentation sizing, sensor
range and calibration release, PCM minor-frame and bit-rate sizing,
supercommutation/subcommutation assignment, IRIG-B time coding, latency
budgeting, ground-link and telemetry quality checks, frame-sync period
planning, airspeed position error calibration (PEC) relations, the FAR 36
noise certification measurement geometry and EPNL/cumulative-margin
acceptance math, build-up ordering with prerequisites, test-matrix grid
expansion with repeats and steady-state validation, and requirement-to-
point traceability - and BUILDS the Flight Test Plan and Requirements
Traceability content. It also gate-checks deliverables. Standalone: no
external repo needed.

Domain rules encoded here are common-knowledge flight test, measurement
and telemetry methodology as summarized (summary-not-copy) in the bound
flight-test-operations/planning leaves of AeroSkills, which in turn frame
FAR-25/CS-25 and the FAR 36 noise certification measurement procedure at
reference level only. No regulation text is reproduced; the applicable
noise limits and certification basis remain program inputs. Every
constant below carries the leaf or standard-practice source in its name
or docstring (e.g. NOISE_CUMULATIVE_REQUIRED_DB = 10.0 EPNdB, the typical
chapter 4 / stage 4 cumulative margin rule at reference level).
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from datetime import date


def _today() -> str:
    return os.environ.get("ROLE_GEN_DATE", date.today().isoformat())


# ---------------------------------------------------------------------------
# Domain tables (public process knowledge; magnitudes per standard practice)
# ---------------------------------------------------------------------------

# Noise certification reference geometry (typical public FAR 36 measurement
# summary values, as encoded by the noise-certification-test leaf):
# flyover measured on the extended centerline 6500 m from brake release,
# sideline 450 m lateral of the centerline, approach under the flight path
# 1200 m from the threshold at 120 m altitude on the 3 degree glide slope.
FLYOVER_DISTANCE_M = 6500.0
SIDELINE_LATERAL_M = 450.0
APPROACH_DISTANCE_M = 1200.0
APPROACH_ALTITUDE_M = 120.0
APPROACH_GLIDE_DEG = 3.0

# EPNL integration constants (noise-certification-test leaf):
# EPNL = 10*log10((1/T0)*sum(10**(PNLT/10))*dt) over the 10 dB down
# interval, T0 = 10 s reference duration.
NOISE_T0 = 10.0
NOISE_DB_DOWN = 10.0
# Typical chapter 4 / stage 4 cumulative margin rule constant, in EPNdB.
NOISE_CUMULATIVE_REQUIRED_DB = 10.0

# ISA sea level standard atmosphere module constants (position-error
# calibration leaf): compressible calibrated airspeed relations.
A0 = 340.294      # m/s, sea level speed of sound
P0 = 101325.0     # Pa, sea level static pressure
RHO0 = 1.225      # kg/m^3, sea level air density
G0 = 9.80665      # m/s^2, standard gravity
R_AIR = 287.053   # J/(kg K), specific gas constant of dry air
T0_ISA = 288.15   # K, sea level temperature
LAPSE = 0.0065    # K/m, troposphere lapse rate
TROPOPAUSE = 11000.0   # m, ISA tropopause height
T_STRAT = 216.65  # K, ISA stratosphere isothermal temperature
_TROP_EXP = G0 / (R_AIR * LAPSE)
# m/s, reference indicated airspeed of the tower fly-by pass used by the
# reduced fly-by form when the pass speed is not supplied (mid range of a
# typical PEC sweep, matching the leaf worked example).
FLYBY_REFERENCE_CAS = 100.0
# PEC data quality verdict thresholds (position-error-calibration leaf):
# coverage >= 0.95 of planned points inside the calibrated span and
# residual RMS <= 1.0 m/s for an adequate verdict.
PEC_COVERAGE_MIN = 0.95
PEC_RESIDUAL_RMS_MAX = 1.0

# Practical acquisition chains sample above the Nyquist rate to leave
# headroom for the anti-aliasing filter rolloff (flight-test-instrumentation
# leaf): fs_req = margin * 2 * fmax, default margin 2.5 (5 times fmax).
INSTRUMENT_MARGIN = 2.5


def _finite(x):
    return isinstance(x, (int, float)) and math.isfinite(x)


# ---------------------------------------------------------------------------
# Flight test instrumentation: Nyquist, sensor range, ADC, calibration
# ---------------------------------------------------------------------------


def nyquist_ok(sample_rate, max_freq):
    """True when sample_rate >= 2 * max_freq (the Nyquist criterion)."""
    if isinstance(sample_rate, bool) or not isinstance(sample_rate, (int, float)):
        raise ValueError("sample_rate must be numeric, got %r" % (sample_rate,))
    if isinstance(max_freq, bool) or not isinstance(max_freq, (int, float)):
        raise ValueError("max_freq must be numeric, got %r" % (max_freq,))
    if sample_rate <= 0:
        raise ValueError("sample_rate must be > 0, got %r" % (sample_rate,))
    if max_freq <= 0:
        raise ValueError("max_freq must be > 0, got %r" % (max_freq,))
    return sample_rate >= 2 * max_freq


def sensor_range_verdict(measured_value, sensor_range):
    """\"ok\" when |measured_value| <= sensor_range else \"over-range\"."""
    if isinstance(measured_value, bool) or not isinstance(
            measured_value, (int, float)):
        raise ValueError("measured_value must be numeric, got %r"
                         % (measured_value,))
    if isinstance(sensor_range, bool) or not isinstance(
            sensor_range, (int, float)):
        raise ValueError("sensor_range must be numeric, got %r"
                         % (sensor_range,))
    if sensor_range <= 0:
        raise ValueError("sensor_range must be > 0, got %r" % (sensor_range,))
    return "ok" if abs(measured_value) <= sensor_range else "over-range"


def quantization_error(bits, range_value):
    """Resolution (1 LSB) of an ideal N-bit ADC over a full-scale range."""
    if isinstance(bits, bool) or not isinstance(bits, int):
        raise ValueError("bits must be an int, got %r" % (bits,))
    if bits < 1:
        raise ValueError("bits must be >= 1, got %r" % (bits,))
    if isinstance(range_value, bool) or not isinstance(
            range_value, (int, float)):
        raise ValueError("range_value must be numeric, got %r" % (range_value,))
    if range_value <= 0:
        raise ValueError("range_value must be > 0, got %r" % (range_value,))
    return range_value / (2 ** bits)


def required_sample_rate(max_freq, margin=INSTRUMENT_MARGIN):
    """Required sample rate: margin * 2 * max_freq (default margin 2.5)."""
    if isinstance(max_freq, bool) or not isinstance(max_freq, (int, float)):
        raise ValueError("max_freq must be numeric, got %r" % (max_freq,))
    if max_freq <= 0:
        raise ValueError("max_freq must be > 0, got %r" % (max_freq,))
    if isinstance(margin, bool) or not isinstance(margin, (int, float)):
        raise ValueError("margin must be numeric, got %r" % (margin,))
    if margin <= 0:
        raise ValueError("margin must be > 0, got %r" % (margin,))
    return margin * 2 * max_freq


def calibration_verdict(calibrated, due):
    """True when calibrated AND recalibration is not due."""
    for name, val in (("calibrated", calibrated), ("due", due)):
        if not isinstance(val, bool):
            raise ValueError("%s must be a bool, got %r" % (name, val))
    return calibrated and not due


# ---------------------------------------------------------------------------
# Telemetry and data acquisition: PCM frame sizing, IRIG, conditioning,
# latency, ground link, quality
# ---------------------------------------------------------------------------


def pcm_frame_size(words_per_frame, bits_per_word):
    """Size of one PCM minor frame in bits: words * bits per word."""
    for name, val in (("words_per_frame", words_per_frame),
                      ("bits_per_word", bits_per_word)):
        if isinstance(val, bool) or not isinstance(val, int):
            raise ValueError("%s must be an int, got %r" % (name, val))
        if val < 1:
            raise ValueError("%s must be >= 1, got %r" % (name, val))
    return words_per_frame * bits_per_word


def pcm_bit_rate(frame_rate, words_per_frame, bits_per_word):
    """Bit rate of the PCM stream: frame_rate * frame size bits."""
    if isinstance(frame_rate, bool) or not isinstance(
            frame_rate, (int, float)):
        raise ValueError("frame_rate must be numeric, got %r" % (frame_rate,))
    if frame_rate <= 0:
        raise ValueError("frame_rate must be > 0, got %r" % (frame_rate,))
    return frame_rate * pcm_frame_size(words_per_frame, bits_per_word)


def supercommutated_instances(channel_sample_rate, frame_rate):
    """Supercommutated channel appearances per minor frame (integer > 1)."""
    for name, val in (("channel_sample_rate", channel_sample_rate),
                      ("frame_rate", frame_rate)):
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise ValueError("%s must be numeric, got %r" % (name, val))
        if val <= 0:
            raise ValueError("%s must be > 0, got %r" % (name, val))
    instances = channel_sample_rate / frame_rate
    if instances <= 1:
        raise ValueError(
            "channel_sample_rate must exceed frame_rate for "
            "supercommutation, got %r instances per frame" % (instances,))
    if instances != int(instances):
        raise ValueError(
            "supercommutated instances per frame must be an integer, got %r"
            % (instances,))
    return int(instances)


def subcommutated_instances(frame_rate, channel_sample_rate):
    """Subcommutated frames per sample of a slow channel (integer > 1)."""
    for name, val in (("frame_rate", frame_rate),
                      ("channel_sample_rate", channel_sample_rate)):
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise ValueError("%s must be numeric, got %r" % (name, val))
        if val <= 0:
            raise ValueError("%s must be > 0, got %r" % (name, val))
    frames_per_sample = frame_rate / channel_sample_rate
    if frames_per_sample <= 1:
        raise ValueError(
            "channel_sample_rate must be below frame_rate for "
            "subcommutation, got %r frames per sample" % (frames_per_sample,))
    if frames_per_sample != int(frames_per_sample):
        raise ValueError(
            "subcommutated frames per sample must be an integer, got %r"
            % (frames_per_sample,))
    return int(frames_per_sample)


def irig_b_time_of_year(day_of_year, seconds_of_day):
    """Seconds of year for an IRIG-B time-of-year code."""
    if isinstance(day_of_year, bool) or not isinstance(day_of_year, int):
        raise ValueError("day_of_year must be an int, got %r" % (day_of_year,))
    if not (1 <= day_of_year <= 366):
        raise ValueError("day_of_year must be in 1..366, got %r"
                         % (day_of_year,))
    if isinstance(seconds_of_day, bool) or not isinstance(
            seconds_of_day, (int, float)):
        raise ValueError("seconds_of_day must be numeric, got %r"
                         % (seconds_of_day,))
    if not (0 <= seconds_of_day < 86400):
        raise ValueError("seconds_of_day must be in [0, 86400), got %r"
                         % (seconds_of_day,))
    return (day_of_year - 1) * 86400 + seconds_of_day


def conditioning_verdict(sensor_span, gain, adc_range):
    """\"ok\" when the conditioned span (sensor_span * gain) fits the ADC."""
    for name, val in (("sensor_span", sensor_span), ("gain", gain),
                      ("adc_range", adc_range)):
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise ValueError("%s must be numeric, got %r" % (name, val))
        if val <= 0:
            raise ValueError("%s must be > 0, got %r" % (name, val))
    conditioned_span = sensor_span * gain
    return "ok" if conditioned_span <= adc_range else "over-range"


def total_latency(acquisition_ms, processing_ms, link_ms):
    """End-to-end telemetry data latency: sum of the three delays in ms."""
    total = 0.0
    for name, val in (("acquisition_ms", acquisition_ms),
                      ("processing_ms", processing_ms),
                      ("link_ms", link_ms)):
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise ValueError("%s must be numeric, got %r" % (name, val))
        if val < 0:
            raise ValueError("%s must be >= 0, got %r" % (name, val))
        total += val
    return total


def latency_ok(total_ms, requirement_ms):
    """True when total_ms <= requirement_ms."""
    if isinstance(total_ms, bool) or not isinstance(total_ms, (int, float)):
        raise ValueError("total_ms must be numeric, got %r" % (total_ms,))
    if total_ms < 0:
        raise ValueError("total_ms must be >= 0, got %r" % (total_ms,))
    if isinstance(requirement_ms, bool) or not isinstance(
            requirement_ms, (int, float)):
        raise ValueError("requirement_ms must be numeric, got %r"
                         % (requirement_ms,))
    if requirement_ms <= 0:
        raise ValueError("requirement_ms must be > 0, got %r"
                         % (requirement_ms,))
    return total_ms <= requirement_ms


def latency_buffer_samples(latency_s, sample_rate):
    """Samples buffered in the pipeline: ceil(latency_s * sample_rate)."""
    if isinstance(latency_s, bool) or not isinstance(latency_s, (int, float)):
        raise ValueError("latency_s must be numeric, got %r" % (latency_s,))
    if latency_s < 0:
        raise ValueError("latency_s must be >= 0, got %r" % (latency_s,))
    if isinstance(sample_rate, bool) or not isinstance(
            sample_rate, (int, float)):
        raise ValueError("sample_rate must be numeric, got %r"
                         % (sample_rate,))
    if sample_rate <= 0:
        raise ValueError("sample_rate must be > 0, got %r" % (sample_rate,))
    return int(math.ceil(latency_s * sample_rate))


def ground_link_ok(received_power_dbm, sensitivity_dbm, min_margin_dbm):
    """True when the link margin meets the minimum margin."""
    for name, val in (("received_power_dbm", received_power_dbm),
                      ("sensitivity_dbm", sensitivity_dbm),
                      ("min_margin_dbm", min_margin_dbm)):
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise ValueError("%s must be numeric, got %r" % (name, val))
    if min_margin_dbm <= 0:
        raise ValueError("min_margin_dbm must be > 0, got %r"
                         % (min_margin_dbm,))
    margin = received_power_dbm - sensitivity_dbm
    return margin >= min_margin_dbm


def telemetry_quality_ok(bit_error_rate, dropout_percent,
                         ber_limit, dropout_limit):
    """True when BER <= ber_limit and dropouts <= dropout_limit."""
    if isinstance(bit_error_rate, bool) or not isinstance(
            bit_error_rate, (int, float)):
        raise ValueError("bit_error_rate must be numeric, got %r"
                         % (bit_error_rate,))
    if not (0 <= bit_error_rate <= 1):
        raise ValueError("bit_error_rate must be in [0, 1], got %r"
                         % (bit_error_rate,))
    if isinstance(dropout_percent, bool) or not isinstance(
            dropout_percent, (int, float)):
        raise ValueError("dropout_percent must be numeric, got %r"
                         % (dropout_percent,))
    if not (0 <= dropout_percent <= 100):
        raise ValueError("dropout_percent must be in [0, 100], got %r"
                         % (dropout_percent,))
    for name, val in (("ber_limit", ber_limit), ("dropout_limit",
                                                  dropout_limit)):
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise ValueError("%s must be numeric, got %r" % (name, val))
    if not (0.0 < ber_limit <= 1.0):
        raise ValueError("ber_limit must be in (0, 1], got %r"
                         % (ber_limit,))
    if not (0.0 < dropout_limit <= 100.0):
        raise ValueError("dropout_limit must be in (0, 100], got %r"
                         % (dropout_limit,))
    return bit_error_rate <= ber_limit and dropout_percent <= dropout_limit


# ---------------------------------------------------------------------------
# PCM decommutation: frame sync period arithmetic
# ---------------------------------------------------------------------------


def frame_period_words(data_words_per_frame, idle_words):
    """Words from one sync word to the next: 1 + data + idle."""
    if data_words_per_frame < 0:
        raise ValueError("data_words_per_frame must be non-negative")
    if idle_words < 0:
        raise ValueError("idle_words must be non-negative")
    return 1 + data_words_per_frame + idle_words


# ---------------------------------------------------------------------------
# Airspeed position error calibration (PEC): compressible airspeed
# relations and reference-method reduction
# ---------------------------------------------------------------------------


def calibrated_airspeed(qc):
    """Calibrated airspeed V_cas in m/s from impact pressure qc in Pa."""
    if not _finite(qc) or qc < 0.0:
        raise ValueError(
            "impact pressure must be a finite value >= 0 Pa, got %r" % (qc,))
    return A0 * math.sqrt(5.0 * ((qc / P0 + 1.0) ** (2.0 / 7.0) - 1.0))


def impact_pressure_from_cas(v_cas):
    """Impact pressure qc in Pa for a calibrated airspeed in m/s."""
    if not _finite(v_cas) or v_cas < 0.0:
        raise ValueError(
            "calibrated airspeed must be a finite value >= 0 m/s, got %r"
            % (v_cas,))
    return P0 * ((1.0 + 0.2 * (v_cas / A0) ** 2.0) ** 3.5 - 1.0)


def position_error(v_ias, v_cas):
    """Position error correction dVp = V_cas - V_ias in m/s."""
    if not _finite(v_ias) or v_ias < 0.0:
        raise ValueError("indicated airspeed must be a finite value >= 0 m/s")
    if not _finite(v_cas) or v_cas < 0.0:
        raise ValueError("calibrated airspeed must be a finite value >= 0 m/s")
    return v_cas - v_ias


def _isa_pressure(altitude_m):
    """ISA static pressure in Pa at a pressure altitude in m."""
    if not _finite(altitude_m):
        raise ValueError("altitude must be finite, got %r" % (altitude_m,))
    if altitude_m <= TROPOPAUSE:
        p = P0 * (1.0 - LAPSE * altitude_m / T0_ISA) ** _TROP_EXP
    else:
        p_tropo = P0 * (1.0 - LAPSE * TROPOPAUSE / T0_ISA) ** _TROP_EXP
        p = p_tropo * math.exp(-G0 * (altitude_m - TROPOPAUSE)
                               / (R_AIR * T_STRAT))
    return p


def tower_flyby_position_error(geometric_height, pressure_altitude,
                               temperature, v_ias=None):
    """Position error dVp in m/s from one tower fly-by pass.

    The static pressure error follows the altimeter scale (hydrostatic)
    relation dp_s = rho * g0 * dh with dh = H_geom - H_p and rho =
    p(H_p)/(R*T); the same dp_s displaces the impact pressure seen by
    the standard airspeed indicator by -dp_s, so
        V_cas = V_isa(qc(V_ias) + dp_s),  dVp = V_cas - V_ias
    using the exact compressible airspeed indicator law. When the pass
    speed is not supplied the indicator scale is evaluated at
    FLYBY_REFERENCE_CAS. A low altimeter reading (H_p < H_geom) gives a
    positive correction.
    """
    if not _finite(geometric_height) or geometric_height < 0.0:
        raise ValueError("geometric height must be a finite value >= 0 m")
    if not _finite(pressure_altitude):
        raise ValueError("pressure altitude must be finite, got %r"
                         % (pressure_altitude,))
    if not _finite(temperature) or temperature <= 0.0:
        raise ValueError("temperature must be a finite value > 0 K")
    if v_ias is None:
        v_ias = FLYBY_REFERENCE_CAS
    if not _finite(v_ias) or v_ias < 0.0:
        raise ValueError("pass airspeed must be a finite value >= 0 m/s")
    dh = geometric_height - pressure_altitude
    rho = _isa_pressure(pressure_altitude) / (R_AIR * temperature)
    dp_s = rho * G0 * dh
    qc_total = impact_pressure_from_cas(v_ias) + dp_s
    return calibrated_airspeed(qc_total) - v_ias


def gps_doublet_tas(v1g, v2g):
    """True airspeed V_tas in m/s from a GPS ground speed doublet."""
    if not _finite(v1g) or v1g < 0.0:
        raise ValueError("ground speed V1g must be a finite value >= 0 m/s")
    if not _finite(v2g) or v2g < 0.0:
        raise ValueError("ground speed V2g must be a finite value >= 0 m/s")
    return 0.5 * (v1g + v2g)


def tas_to_cas(v_tas, density_ratio):
    """Calibrated airspeed V_cas = V_tas * sqrt(rho/rho0)."""
    if not _finite(v_tas) or v_tas < 0.0:
        raise ValueError("true airspeed must be a finite value >= 0 m/s")
    if not _finite(density_ratio) or density_ratio <= 0.0:
        raise ValueError("density ratio must be a finite value > 0")
    return v_tas * math.sqrt(density_ratio)


# ---------------------------------------------------------------------------
# Noise certification test: reference geometry, EPNL, margins
# ---------------------------------------------------------------------------


def noise_geometry(condition):
    """Reference geometry dict for a noise certification condition."""
    if condition == "flyover":
        return {"condition": "flyover",
                "distance_m": FLYOVER_DISTANCE_M,
                "reference": "extended runway centerline, brake release point"}
    if condition == "sideline":
        return {"condition": "sideline",
                "lateral_m": SIDELINE_LATERAL_M,
                "reference": "lateral of runway centerline at max takeoff "
                             "noise"}
    if condition == "approach":
        return {"condition": "approach",
                "distance_m": APPROACH_DISTANCE_M,
                "altitude_m": APPROACH_ALTITUDE_M,
                "glide_deg": APPROACH_GLIDE_DEG,
                "reference": "under the flight path from the threshold"}
    raise ValueError("unknown condition: %r (expected flyover, sideline or "
                     "approach)" % (condition,))


def _interpolated_db(pnlt, dt, time):
    """Linear interpolation of the PNLT series in dB at a given time."""
    n = len(pnlt)
    position = time / dt
    index = int(math.floor(position))
    if index < 0:
        return pnlt[0]
    if index >= n - 1:
        return pnlt[-1]
    fraction = position - index
    return pnlt[index] * (1.0 - fraction) + pnlt[index + 1] * fraction


def epnl_from_pnlt(pnlt_series, dt=0.5):
    """EPNL from a PNLT time history with the 10 dB down rule.

    EPNL = 10 * log10((1 / T0) * integral of 10**(PNLT/10) dt) over the
    10 dB down interval, boundaries linearly interpolated between the
    bracketing samples; a series that never drops 10 dB below its peak
    is integrated over the full recorded span with truncated False.
    Returns (epnl_db, t_start_s, t_end_s, truncated).
    """
    if not _finite(dt) or dt <= 0.0:
        raise ValueError("dt must be a finite positive time step")
    pnlt = list(pnlt_series)
    if not pnlt:
        raise ValueError("pnlt_series must not be empty")
    for value in pnlt:
        if not _finite(value):
            raise ValueError("pnlt_series contains a non-finite sample")
    n = len(pnlt)
    peak_index = max(range(n), key=lambda idx: pnlt[idx])
    peak_db = pnlt[peak_index]
    threshold_db = peak_db - NOISE_DB_DOWN

    index = peak_index
    while index > 0 and pnlt[index - 1] > threshold_db:
        index -= 1
    if index > 0 and pnlt[index - 1] <= threshold_db:
        left_db = pnlt[index - 1]
        t_start = ((index - 1) * dt
                   + (threshold_db - left_db) / (pnlt[index] - left_db) * dt)
        left_found = True
    else:
        t_start = 0.0
        left_found = False

    index = peak_index
    while index < n - 1 and pnlt[index + 1] > threshold_db:
        index += 1
    if index < n - 1 and pnlt[index + 1] <= threshold_db:
        right_db = pnlt[index + 1]
        t_end = (index * dt
                 + (threshold_db - pnlt[index]) / (right_db - pnlt[index]) * dt)
        right_found = True
    else:
        t_end = (n - 1) * dt
        right_found = False

    truncated = left_found or right_found

    if n == 1:
        energy = 10.0 ** (pnlt[0] / 10.0) * dt
    else:
        breakpoints = [t_start]
        for sample_index in range(n):
            sample_time = sample_index * dt
            if t_start < sample_time < t_end:
                breakpoints.append(sample_time)
        breakpoints.append(t_end)
        breakpoints = sorted(set(breakpoints))
        energy = 0.0
        for left, right in zip(breakpoints, breakpoints[1:]):
            left_db = _interpolated_db(pnlt, dt, left)
            right_db = _interpolated_db(pnlt, dt, right)
            energy += ((10.0 ** (left_db / 10.0)
                        + 10.0 ** (right_db / 10.0)) / 2.0 * (right - left))

    epnl_db = 10.0 * math.log10(energy / NOISE_T0)
    return epnl_db, t_start, t_end, truncated


def margin_to_limit(epnl, limit):
    """(margin_db, verdict) with margin_db = limit - epnl."""
    if not _finite(epnl):
        raise ValueError("epnl must be a finite value in EPNdB")
    if not _finite(limit):
        raise ValueError("limit must be a finite value in EPNdB")
    if limit < 0.0:
        raise ValueError("limit must not be negative")
    margin_db = limit - epnl
    return margin_db, ("pass" if margin_db >= 0.0 else "fail")


def cumulative_margin(margins):
    """Three-point cumulative margin assessment (typical chapter 4 rule).

    Sum of the per-point margins must be >= NOISE_CUMULATIVE_REQUIRED_DB
    and every individual margin >= 0 for a pass. Returns a dict with
    sum_db, required_db, min_margin_db, verdict and reasons.
    """
    margins = list(margins)
    if not margins:
        raise ValueError("margins must not be empty")
    for margin in margins:
        if not _finite(margin):
            raise ValueError("margins contains a non-finite value")
    sum_db = sum(margins)
    min_db = min(margins)
    reasons = []
    if sum_db < NOISE_CUMULATIVE_REQUIRED_DB:
        reasons.append(
            "sum of margins %.3f EPNdB below the required %.1f EPNdB"
            % (sum_db, NOISE_CUMULATIVE_REQUIRED_DB))
    if min_db < 0.0:
        reasons.append("individual margin %.3f EPNdB below zero" % min_db)
    if not reasons:
        reasons.append(
            "sum of margins %.3f EPNdB meets the required %.1f EPNdB and "
            "every individual margin is at or above zero"
            % (sum_db, NOISE_CUMULATIVE_REQUIRED_DB))
    verdict = ("pass" if (sum_db >= NOISE_CUMULATIVE_REQUIRED_DB
                          and min_db >= 0.0) else "fail")
    return {"sum_db": sum_db, "required_db": NOISE_CUMULATIVE_REQUIRED_DB,
            "min_margin_db": min_db, "verdict": verdict,
            "reasons": reasons}


def noise_test_matrix(takeoff_weight, landing_weight, v2_kt,
                      approach_speed_kt, limits):
    """Three-condition certification test matrix rows.

    Flyover reference speed V2 + 10 kt (typical FAR 36 measurement
    summary); sideline reference V2; approach flown in landing
    configuration at the reference approach speed. Limits are state
    inputs from the certification basis. Rows carry configuration,
    weight, reference speed, stated limit and demonstration target
    (target equals the stated limit).
    """
    if not isinstance(limits, dict):
        raise ValueError("limits must be a dict")
    for condition in ("flyover", "sideline", "approach"):
        if condition not in limits:
            raise ValueError("limits missing key %r" % condition)
    for name, value in (("takeoff_weight", takeoff_weight),
                        ("landing_weight", landing_weight),
                        ("v2_kt", v2_kt),
                        ("approach_speed_kt", approach_speed_kt)):
        if not _finite(value) or value <= 0.0:
            raise ValueError("%s must be a finite positive value" % name)
    rows = []
    for condition in ("flyover", "sideline", "approach"):
        if condition == "approach":
            configuration = "landing"
            weight = landing_weight
            speed = approach_speed_kt
        else:
            configuration = "takeoff"
            weight = takeoff_weight
            speed = v2_kt + (10.0 if condition == "flyover" else 0.0)
        limit = limits[condition]
        if not _finite(limit) or limit < 0.0:
            raise ValueError("limit for %r must not be negative" % condition)
        rows.append({"condition": condition,
                     "configuration": configuration,
                     "weight_kg": weight,
                     "reference_speed_kt": speed,
                     "limit": limit,
                     "target_epnl": limit})
    return rows


# ---------------------------------------------------------------------------
# Test point matrix design and build-up planning
# ---------------------------------------------------------------------------


def build_test_matrix(altitudes, speeds, weights, configurations):
    """Expand the condition sweeps into the full grid of test points.

    Grid ordered altitude-major, then speed, then weight, then
    configuration; point ids tp1..tpN in grid order. Returns
    {"points": [...], "count": N} with each point a dict carrying id,
    altitude, speed, weight, configuration and repeat False.
    """
    for label, values in (("altitudes", altitudes), ("speeds", speeds),
                          ("weights", weights)):
        if not isinstance(values, list) or len(values) == 0:
            raise ValueError("%s must be a non-empty list, got %r"
                             % (label, values))
        for v in values:
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ValueError("%s levels must be numeric, got %r"
                                 % (label, v))
    for v in altitudes:
        if v < 0:
            raise ValueError("altitude levels must be >= 0, got %r" % (v,))
    for v in speeds:
        if v <= 0:
            raise ValueError("speed levels must be > 0, got %r" % (v,))
    for v in weights:
        if v <= 0:
            raise ValueError("weight levels must be > 0, got %r" % (v,))
    if not isinstance(configurations, list) or len(configurations) == 0:
        raise ValueError("configurations must be a non-empty list, got %r"
                         % (configurations,))
    for c in configurations:
        if not isinstance(c, str) or not c:
            raise ValueError("configuration labels must be non-empty "
                             "strings, got %r" % (c,))
    points = []
    idx = 0
    for altitude in altitudes:
        for speed in speeds:
            for weight in weights:
                for config in configurations:
                    idx += 1
                    points.append({"id": "tp%d" % idx,
                                   "altitude": altitude,
                                   "speed": speed,
                                   "weight": weight,
                                   "configuration": config,
                                   "repeat": False})
    return {"points": points, "count": len(points)}


def add_repeat_points(points, repeat_interval):
    """Mark every repeat_interval-th point (1-based grid order) as repeat.

    Returns a new list; the input list is not modified.
    """
    if not isinstance(points, list) or len(points) == 0:
        raise ValueError("points must be a non-empty list, got %r" % (points,))
    if isinstance(repeat_interval, bool) or not isinstance(
            repeat_interval, int):
        raise ValueError("repeat_interval must be an int, got %r"
                         % (repeat_interval,))
    if repeat_interval < 2:
        raise ValueError("repeat_interval must be >= 2, got %r"
                         % (repeat_interval,))
    seen = set()
    for pt in points:
        if not isinstance(pt, dict):
            raise ValueError("each test point must be a dict, got %r" % (pt,))
        pid = pt.get("id")
        if not isinstance(pid, str) or not pid:
            raise ValueError("test point id must be a non-empty string, "
                             "got %r" % (pid,))
        if pid in seen:
            raise ValueError("duplicate test point id %r" % (pid,))
        seen.add(pid)
        if "repeat" not in pt or not isinstance(pt["repeat"], bool):
            raise ValueError("test point %r needs a bool repeat key" % (pid,))
    out = []
    for i, pt in enumerate(points, 1):
        copy = dict(pt)
        if i % repeat_interval == 0:
            copy["repeat"] = True
        out.append(copy)
    return out


def sequence_for_efficiency(points):
    """Order points for efficient flying: configuration blocks, then
    altitude ascending, then speed ascending (deterministic stable)."""
    if not isinstance(points, list) or len(points) == 0:
        raise ValueError("points must be a non-empty list, got %r" % (points,))
    for pt in points:
        if not isinstance(pt, dict):
            raise ValueError("each test point must be a dict, got %r" % (pt,))
        cfg = pt.get("configuration")
        if not isinstance(cfg, str) or not cfg:
            raise ValueError("test point configuration must be a non-empty "
                             "string, got %r" % (cfg,))
        for key in ("altitude", "speed"):
            val = pt.get(key)
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise ValueError("test point %r %s must be numeric, got %r"
                                 % (pt.get("id"), key, val))
    order = {}
    for pt in points:
        cfg = pt["configuration"]
        if cfg not in order:
            order[cfg] = len(order)
    return sorted(points, key=lambda pt: (order[pt["configuration"]],
                                          pt["altitude"], pt["speed"]))


def steady_state_check(points, tolerances, observed):
    """Check every flown point against the steady state tolerance band.

    A point is valid when |observed - planned| <= tolerance for altitude,
    speed and weight. Returns {"valid": [...], "invalid": [...],
    "verdict": "all-valid" | "invalid-points"}.
    """
    if not isinstance(points, list) or len(points) == 0:
        raise ValueError("points must be a non-empty list, got %r" % (points,))
    for key in ("altitude", "speed", "weight"):
        if key not in tolerances:
            raise ValueError("tolerances missing required key %r" % (key,))
        tol = tolerances[key]
        if isinstance(tol, bool) or not isinstance(tol, (int, float)):
            raise ValueError("tolerance %r must be numeric, got %r"
                             % (key, tol))
        if tol < 0:
            raise ValueError("tolerance %r must be >= 0, got %r" % (key, tol))
    if not isinstance(observed, dict):
        raise ValueError("observed must be a dict mapping point ids to "
                         "readings, got %r" % (observed,))
    planned = {}
    for pt in points:
        if not isinstance(pt, dict):
            raise ValueError("each test point must be a dict, got %r" % (pt,))
        pid = pt.get("id")
        if not isinstance(pid, str) or not pid:
            raise ValueError("test point id must be a non-empty string, "
                             "got %r" % (pid,))
        if pid in planned:
            raise ValueError("duplicate test point id %r" % (pid,))
        for key in ("altitude", "speed", "weight"):
            val = pt.get(key)
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise ValueError("test point %r %s must be numeric, got %r"
                                 % (pid, key, val))
        planned[pid] = pt
    for pid in planned:
        if pid not in observed:
            raise ValueError("observed has no reading for test point %r"
                             % (pid,))
    for pid, reading in observed.items():
        if pid not in planned:
            raise ValueError("observed has a reading for unknown test "
                             "point %r" % (pid,))
        if not isinstance(reading, dict):
            raise ValueError("observed reading for %r must be a dict, got %r"
                             % (pid, reading))
        for key in ("altitude", "speed", "weight"):
            val = reading.get(key)
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise ValueError("observed %r %s must be numeric, got %r"
                                 % (pid, key, val))
    valid, invalid = [], []
    for pid, pt in planned.items():
        ok = all(abs(observed[pid][key] - pt[key]) <= tolerances[key]
                 for key in ("altitude", "speed", "weight"))
        (valid if ok else invalid).append(pid)
    verdict = "all-valid" if not invalid else "invalid-points"
    return {"valid": valid, "invalid": invalid, "verdict": verdict}


def test_matrix_complete(points, objectives):
    """Check that every test objective has at least one covering point.

    Returns {"uncovered": [...], "coverage": {...}, "verdict":
    "complete" | "incomplete"}.
    """
    if not isinstance(points, list) or len(points) == 0:
        raise ValueError("points must be a non-empty list, got %r" % (points,))
    if not isinstance(objectives, list) or len(objectives) == 0:
        raise ValueError("objectives must be a non-empty list, got %r"
                         % (objectives,))
    for obj in objectives:
        if not isinstance(obj, str) or not obj:
            raise ValueError("objective ids must be non-empty strings, "
                             "got %r" % (obj,))
    seen = set()
    for pt in points:
        if not isinstance(pt, dict):
            raise ValueError("each test point must be a dict, got %r" % (pt,))
        pid = pt.get("id")
        if not isinstance(pid, str) or not pid:
            raise ValueError("test point id must be a non-empty string, "
                             "got %r" % (pid,))
        if pid in seen:
            raise ValueError("duplicate test point id %r" % (pid,))
        seen.add(pid)
        covers = pt.get("covers")
        if not isinstance(covers, list) or not all(
                isinstance(c, str) and c for c in covers):
            raise ValueError("test point %r covers must be a list of "
                             "strings, got %r" % (pid, covers))
    coverage = {}
    for obj in objectives:
        coverage[obj] = [pt["id"] for pt in points if obj in pt["covers"]]
    uncovered = sorted(o for o in objectives if not coverage[o])
    verdict = "complete" if not uncovered else "incomplete"
    return {"uncovered": uncovered, "coverage": coverage, "verdict": verdict}


def build_up_order(test_points):
    """Order flight blocks by ascending risk; flag missing prerequisites.

    Each point is a dict with id, numeric risk >= 0 and a prerequisites
    list of point ids. Returns {"ordered": [...], "missing_prerequisites":
    [...], "verdict": "ok" | "missing-prerequisites"}; ties keep input
    order so the result is deterministic.
    """
    if not isinstance(test_points, list) or len(test_points) == 0:
        raise ValueError("test_points must be a non-empty list, got %r"
                         % (test_points,))
    seen = set()
    for pt in test_points:
        if not isinstance(pt, dict):
            raise ValueError("each test point must be a dict, got %r" % (pt,))
        pid = pt.get("id")
        if not isinstance(pid, str) or not pid:
            raise ValueError("test point id must be a non-empty string, "
                             "got %r" % (pid,))
        if pid in seen:
            raise ValueError("duplicate test point id %r" % (pid,))
        seen.add(pid)
        risk = pt.get("risk")
        if isinstance(risk, bool) or not isinstance(risk, (int, float)):
            raise ValueError("test point %r risk must be numeric, got %r"
                             % (pid, risk))
        if risk < 0:
            raise ValueError("test point %r risk must be >= 0, got %r"
                             % (pid, risk))
        prereqs = pt.get("prerequisites")
        if prereqs is None:
            raise ValueError("test point %r has no prerequisites key" % (pid,))
        if not isinstance(prereqs, list) or not all(
                isinstance(p, str) and p for p in prereqs):
            raise ValueError("test point %r prerequisites must be a list of "
                             "strings, got %r" % (pid, prereqs))
    known = set(pt["id"] for pt in test_points)
    ordered = [pt for _, pt in sorted(enumerate(test_points),
                                      key=lambda t: (t[1]["risk"], t[0]))]
    missing = []
    for pt in ordered:
        gone = sorted(p for p in pt["prerequisites"] if p not in known)
        if gone:
            missing.append({"point": pt["id"], "missing": gone})
    verdict = "ok" if not missing else "missing-prerequisites"
    return {"ordered": ordered, "missing_prerequisites": missing,
            "verdict": verdict}


def instrumentation_complete(required, provided):
    """Check that every required instrument is in the provided set.

    Names compare exactly after stripping whitespace. Returns
    {"missing": [...], "verdict": "complete" | "incomplete"}.
    """
    if not isinstance(required, list) or len(required) == 0:
        raise ValueError("required must be a non-empty list, got %r"
                         % (required,))
    if not isinstance(provided, list):
        raise ValueError("provided must be a list, got %r" % (provided,))
    for name in required + provided:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("instrument names must be non-empty strings, "
                             "got %r" % (name,))
    req = [n.strip() for n in required]
    prov = [n.strip() for n in provided]
    missing = sorted(set(req) - set(prov))
    verdict = "complete" if not missing else "incomplete"
    return {"missing": missing, "verdict": verdict}


def go_no_gate(weather_ok, aircraft_ready, instrumentation_ok,
               safety_review_ok):
    """Go/no-go gate verdict before a flight test point.

    The flight is released only when every check is True. Returns
    {"go": bool, "blockers": [...], "verdict": "GO" | "NO-GO"}.
    """
    checks = {"weather_ok": weather_ok, "aircraft_ready": aircraft_ready,
              "instrumentation_ok": instrumentation_ok,
              "safety_review_ok": safety_review_ok}
    for name, val in checks.items():
        if not isinstance(val, bool):
            raise ValueError("%s must be a bool, got %r" % (name, val))
    blockers = [name for name, val in checks.items() if not val]
    go = len(blockers) == 0
    return {"go": go, "blockers": blockers,
            "verdict": "GO" if go else "NO-GO"}


# ---------------------------------------------------------------------------
# Project facts (dataclass) and reference item
# ---------------------------------------------------------------------------

NOISE_CONDITIONS = ("flyover", "sideline", "approach")


@dataclass
class FlightTestPlanItem:
    """Project facts the role needs to build the flight test plan."""
    item_name: str = ""
    description: str = ""
    program: str = ""
    airframe: str = ""
    certification_basis: str = "FAR/CS-25"
    authority: str = ""
    noise_limits_note: str = ""
    # test objectives: {id, text, trace_to: [point-id | campaign tag]}
    objectives: list = field(default_factory=list)
    # requirements: {id, text, source, verification, status,
    #                trace_objectives: [...]}
    requirements: list = field(default_factory=list)
    # matrix sweeps
    altitudes: list = field(default_factory=list)
    speeds: list = field(default_factory=list)
    weights: list = field(default_factory=list)
    configurations: list = field(default_factory=list)
    repeat_interval: int = 5
    matrix_objectives: list = field(default_factory=list)
    steady_state_tolerances: dict = field(default_factory=dict)
    steady_state_observed: dict = field(default_factory=dict)
    # instrumentation
    channels: list = field(default_factory=list)   # dicts, see example_item
    required_instruments: list = field(default_factory=list)
    provided_instruments: list = field(default_factory=list)
    adc_bits: int = 16
    adc_range_v: float = 10.0
    # telemetry facts
    telemetry_words: int = 64
    telemetry_bits: int = 16
    telemetry_frame_rate: float = 50.0
    supercommutated: list = field(default_factory=list)
    subcommutated: list = field(default_factory=list)
    irig_day_of_year: int = 1
    irig_seconds_of_day: float = 0.0
    conditioning: dict = field(default_factory=dict)
    latency: dict = field(default_factory=dict)
    link: dict = field(default_factory=dict)
    quality: dict = field(default_factory=dict)
    # PCM decommutation validation fixture (reference layout)
    decomm_sync_word_hex: str = "0xEB90"
    decomm_data_words: int = 8
    decomm_idle_words: int = 1
    decomm_sid_word_index: int = 0
    decomm_sid_mask: int = 0x0003
    decomm_fixed: list = field(default_factory=list)     # {channel, word}
    decomm_super: list = field(default_factory=list)     # {channel, slots}
    decomm_sub: list = field(default_factory=list)       # {channel, word, subframes}
    decomm_flight_duration_s: float = 3600.0
    # PEC campaign
    pec_planned_ias: list = field(default_factory=list)
    pec_methods: list = field(default_factory=list)
    pec_note: str = ""
    # noise certification campaign
    noise_takeoff_weight_kg: float = 0.0
    noise_landing_weight_kg: float = 0.0
    noise_v2_kt: float = 0.0
    noise_approach_speed_kt: float = 0.0
    noise_limits: dict = field(default_factory=dict)
    # build-up flight blocks: {id, name, risk, prerequisites}
    build_up_blocks: list = field(default_factory=list)
    # go/no-go gate checks for the first build-up flight
    preflight_checks: dict = field(default_factory=dict)
    supporting_note: str = ""


def example_item() -> FlightTestPlanItem:
    """Reference item: the certification flight test campaign of the
    FGS-2000-equipped transport category airplane (Example Airframers
    program, FAR-25 basis). Every numeric fact below is the real rule or
    worked-example value of the bound flight-test-operations/planning
    leaves, or an explicit program input (noise limits)."""
    objectives = [
        {"id": "OBJ-01", "text": "Position-error calibrate the air data "
         "sources across the planned PEC speed range before envelope "
         "expansion.",
         "trace_to": ["PEC-campaign"]},
        {"id": "OBJ-02", "text": "Fly the guidance-mode performance "
         "build-up points across the test matrix.",
         "trace_to": ["tp1", "tp2", "tp3", "tp4", "tp5", "tp6", "tp7",
                      "tp8", "tp9", "tp10", "tp11", "tp12"]},
        {"id": "OBJ-03", "text": "Verify the end-to-end telemetry "
         "latency and data quality on the ground and on the first "
         "telemetry flight.",
         "trace_to": ["BLK-01", "BLK-04"]},
        {"id": "OBJ-04", "text": "Verify PCM decommutation recovers every "
         "assigned channel from a recorded stream.",
         "trace_to": ["BLK-02"]},
        {"id": "OBJ-05", "text": "Demonstrate noise certification margins "
         "at the three FAR 36 measurement conditions.",
         "trace_to": ["NOISE-campaign"]},
        {"id": "OBJ-06", "text": "Release every instrumented channel with "
         "current calibration and adequate range, rate and resolution.",
         "trace_to": ["BLK-01"]},
    ]
    requirements = [
        {"id": "RQ-01", "text": "Air data sources shall be position-error "
         "calibrated across the planned speed range before envelope "
         "expansion flights (FAR/CS-25 flight instrument context).",
         "source": "FAR/CS-25.1303 context", "verification": "flight-test",
         "status": "planned", "trace_objectives": ["OBJ-01"]},
        {"id": "RQ-02", "text": "The acquisition chain shall sample every "
         "measurement channel above its Nyquist rate with anti-alias "
         "filter headroom (instrumentation design rule).",
         "source": "flight-test-instrumentation leaf",
         "verification": "analysis", "status": "planned",
         "trace_objectives": ["OBJ-06"]},
        {"id": "RQ-03", "text": "The telemetry stream shall deliver every "
         "instrumented channel to the ground station within the latency "
         "requirement and within the BER and dropout limits.",
         "source": "telemetry-data-acquisition leaf",
         "verification": "flight-test", "status": "planned",
         "trace_objectives": ["OBJ-03"]},
        {"id": "RQ-04", "text": "Every test objective shall be covered by "
         "at least one test point or dedicated campaign in the matrix.",
         "source": "flight-test-planning leaf", "verification": "analysis",
         "status": "planned", "trace_objectives":
             ["OBJ-02", "OBJ-04", "OBJ-05"]},
        {"id": "RQ-05", "text": "Noise certification measurements shall be "
         "taken at the FAR 36 reference conditions with every individual "
         "margin at or above zero and a cumulative three-point margin of "
         "at least 10 EPNdB.",
         "source": "noise-certification-test leaf (chapter 4 style rule)",
         "verification": "flight-test", "status": "planned",
         "trace_objectives": ["OBJ-05"]},
        {"id": "RQ-06", "text": "Envelope build-up shall fly blocks in "
         "ascending risk order with every prerequisite block flown "
         "first, and each flight released only by the go/no-go gate.",
         "source": "flight-test-planning leaf (build-up approach)",
         "verification": "analysis", "status": "planned",
         "trace_objectives": ["OBJ-02", "OBJ-04"]},
    ]
    channels = [
        {"id": "PITOT", "parameter": "Pitot pressure (airspeed source)",
         "unit": "Pa", "max_value": 90000.0, "sensor_range": 110000.0,
         "fmax_hz": 5.0, "calibrated": True, "cal_due": False},
        {"id": "STATIC", "parameter": "Static pressure (airspeed source)",
         "unit": "Pa", "max_value": 85000.0, "sensor_range": 110000.0,
         "fmax_hz": 5.0, "calibrated": True, "cal_due": False},
        {"id": "ACCV", "parameter": "Vertical acceleration at CG",
         "unit": "g", "max_value": 2.5, "sensor_range": 4.0,
         "fmax_hz": 20.0, "calibrated": True, "cal_due": False},
        {"id": "Q", "parameter": "Pitch rate", "unit": "deg/s",
         "max_value": 30.0, "sensor_range": 60.0, "fmax_hz": 10.0,
         "calibrated": True, "cal_due": False},
        {"id": "DELE", "parameter": "Elevator position", "unit": "deg",
         "max_value": 20.0, "sensor_range": 30.0, "fmax_hz": 10.0,
         "calibrated": True, "cal_due": False},
        {"id": "STRAIN", "parameter": "Wing root bending strain",
         "unit": "microstrain", "max_value": 1500.0,
         "sensor_range": 2500.0, "fmax_hz": 25.0, "calibrated": True,
         "cal_due": False},
        {"id": "N1", "parameter": "Engine N1 speed", "unit": "%",
         "max_value": 105.0, "sensor_range": 110.0, "fmax_hz": 5.0,
         "calibrated": True, "cal_due": False},
    ]
    required_instruments = [c["parameter"] for c in channels]
    provided_instruments = required_instruments + [
        "IRIG-B time code generator", "PCM encoder", "PCM decoder"]
    channels_ok = all(c["calibrated"] and not c["cal_due"]
                      for c in channels)
    build_up_blocks = [
        {"id": "BLK-01", "name": "FTI ground release and telemetry ground "
         "validation", "risk": 0, "prerequisites": []},
        {"id": "BLK-02", "name": "PCM decommutation validation on a "
         "recorded stream", "risk": 0, "prerequisites": []},
        {"id": "BLK-03", "name": "PEC campaign flights (tower fly-by / "
         "GPS ground speed doublet)", "risk": 1,
         "prerequisites": ["BLK-01"]},
        {"id": "BLK-04", "name": "Matrix build-up block, 1500 m altitude "
         "band", "risk": 2, "prerequisites": ["BLK-01", "BLK-03"]},
        {"id": "BLK-05", "name": "Matrix build-up block, 3000 m altitude "
         "band", "risk": 3, "prerequisites": ["BLK-04"]},
        {"id": "BLK-06", "name": "Noise certification measurement flights",
         "risk": 3, "prerequisites": ["BLK-03", "BLK-04"]},
    ]
    observed = {}
    # observed readings equal the planned conditions (steady state held)
    idx = 0
    for altitude in (1500.0, 3000.0):
        for speed in (110.0, 130.0, 150.0):
            for weight in (55000.0,):
                for config in ("clean", "takeoff"):
                    idx += 1
                    observed["tp%d" % idx] = {"altitude": altitude,
                                              "speed": speed,
                                              "weight": weight}
    return FlightTestPlanItem(
        item_name="Certification flight test campaign of the FGS-2000-"
                  "equipped transport category airplane",
        description="The campaign plans and traces the certification "
                    "flight tests that support the FGS-2000 flight "
                    "guidance system program: airspeed position error "
                    "calibration of the air data sources, the guidance-"
                    "mode performance build-up matrix across the "
                    "configurations, the FAR 36 noise certification "
                    "measurement conditions, and the instrumentation, "
                    "telemetry and PCM decommutation chain that records "
                    "and delivers every channel to the ground station.",
        program="FGS-2000 flight guidance system certification",
        airframe="Transport category airplane (FGS-2000-equipped)",
        certification_basis="FAR-25 (noise measurement procedure per FAR "
                            "36 summary)",
        authority="FAA",
        noise_limits_note="Applicable noise limits are program inputs from "
                          "the certification basis (stated per condition "
                          "in this plan); they are not derived here.",
        objectives=objectives,
        requirements=requirements,
        altitudes=[1500.0, 3000.0],
        speeds=[110.0, 130.0, 150.0],
        weights=[55000.0],
        configurations=["clean", "takeoff"],
        repeat_interval=5,
        matrix_objectives=["OBJ-02"],
        steady_state_tolerances={"altitude": 30.0, "speed": 2.0,
                                 "weight": 500.0},
        steady_state_observed=observed,
        channels=channels,
        required_instruments=required_instruments,
        provided_instruments=provided_instruments,
        adc_bits=16,
        adc_range_v=10.0,
        telemetry_words=64,
        telemetry_bits=16,
        telemetry_frame_rate=50.0,
        supercommutated=[{"channel": "ACCV vertical acceleration (CG)",
                          "sample_rate_hz": 100.0},
                         {"channel": "STRAIN wing root strain",
                          "sample_rate_hz": 200.0}],
        subcommutated=[{"channel": "OILT oil temperature",
                        "sample_rate_hz": 12.5}],
        irig_day_of_year=32,
        irig_seconds_of_day=43200.0,
        conditioning={"sensor_span_v": 4.0, "gain": 2.0, "adc_range_v": 10.0},
        latency={"acquisition_ms": 5.0, "processing_ms": 10.0,
                 "link_ms": 25.0, "requirement_ms": 50.0,
                 "buffer_latency_s": 0.05, "buffer_sample_rate": 200.0},
        link={"received_power_dbm": -95.0, "sensitivity_dbm": -110.0,
              "min_margin_dbm": 10.0},
        quality={"bit_error_rate": 1.0e-5, "dropout_percent": 0.5,
                 "ber_limit": 1.0e-4, "dropout_limit": 1.0},
        decomm_sync_word_hex="0xEB90",
        decomm_data_words=8,
        decomm_idle_words=1,
        decomm_sid_word_index=0,
        decomm_sid_mask=0x0003,
        decomm_fixed=[{"channel": "A", "word": 1},
                      {"channel": "B", "word": 4},
                      {"channel": "C", "word": 6},
                      {"channel": "D", "word": 7}],
        decomm_super=[{"channel": "A2", "slots": [3, 5]}],
        decomm_sub=[{"channel": "S", "word": 2, "subframes": 4}],
        decomm_flight_duration_s=3600.0,
        pec_planned_ias=[60.0, 80.0, 100.0, 120.0, 140.0],
        pec_methods=["tower-fly-by", "gps-ground-speed-doublet"],
        pec_note="Reduction relations and reference worked examples are "
                 "the compressible airspeed law and PEC practice of the "
                 "position-error-calibration leaf.",
        noise_takeoff_weight_kg=78000.0,
        noise_landing_weight_kg=62000.0,
        noise_v2_kt=155.0,
        noise_approach_speed_kt=135.0,
        noise_limits={"flyover": 89.0, "sideline": 94.0, "approach": 98.0},
        build_up_blocks=build_up_blocks,
        preflight_checks={"weather_ok": True, "aircraft_ready": True,
                          "instrumentation_ok": channels_ok,
                          "safety_review_ok": True},
        supporting_note=("All quantities in this plan are computed by the "
                         "role core from the real rules of the bound "
                         "flight-test-operations/planning leaves "
                         "(Nyquist sample-rate sizing, PCM frame and bit "
                         "rate, super/subcommutation, IRIG-B time coding, "
                         "latency/link/quality verdicts, PEC airspeed "
                         "relations, EPNL integration and cumulative "
                         "margin rule, matrix expansion and build-up "
                         "ordering). The worked values in the method "
                         "validation cards are the leaves' reference "
                         "worked examples, used pre-flight to validate "
                         "the reduction chain; they are not flight data."),
    )


# ---------------------------------------------------------------------------
# Method validation cards: reference worked examples of the bound leaves,
# recomputed by the core pre-flight to validate the reduction chain.
# ---------------------------------------------------------------------------

# Each card: id, title, source, checks: list of {label, value_fn, unit,
# reference, tolerance}. Numeric checks compare |value - reference| <=
# tolerance; string checks require exact equality. Reference values are
# the documented worked-example outputs of the bound leaves.
CARD_SPECS = [
    {"id": "M-01", "title": "Required sample rate (Nyquist headroom, "
     "default margin 2.5)", "source": "flight-test-instrumentation leaf "
     "worked rule (5 times fmax)",
     "checks": [{"label": "required_sample_rate(fmax=20 Hz)",
                 "value_fn": lambda: required_sample_rate(20.0),
                 "unit": "Hz", "reference": 100.0, "tolerance": 1e-6}]},
    {"id": "M-02", "title": "ADC resolution of the acquisition chain",
     "source": "flight-test-instrumentation leaf rule (R / 2^N)",
     "checks": [{"label": "quantization_error(16 bit, 10 V span)",
                 "value_fn": lambda: quantization_error(16, 10.0),
                 "unit": "V", "reference": 10.0 / 2 ** 16,
                 "tolerance": 1e-12}]},
    {"id": "M-03", "title": "PCM minor frame period in words",
     "source": "pcm-telemetry-decommutation leaf worked example (8 data "
     "words + 1 idle word)",
     "checks": [{"label": "frame_period_words(8, 1)",
                 "value_fn": lambda: float(frame_period_words(8, 1)),
                 "unit": "words", "reference": 10.0, "tolerance": 0.0}]},
    {"id": "M-04", "title": "PCM stream bit rate",
     "source": "telemetry-data-acquisition leaf worked example "
     "(50 frames/s of 1024 bits)",
     "checks": [{"label": "pcm_bit_rate(50, 64, 16)",
                 "value_fn": lambda: pcm_bit_rate(50.0, 64, 16),
                 "unit": "bit/s", "reference": 51200.0, "tolerance": 0.0}]},
    {"id": "M-05", "title": "Supercommutated channel instances per frame",
     "source": "telemetry-data-acquisition leaf worked example "
     "(200 Hz channel on a 50 frame/s stream)",
     "checks": [{"label": "supercommutated_instances(200, 50)",
                 "value_fn": lambda: float(supercommutated_instances(200.0,
                                                                     50.0)),
                 "unit": "per frame", "reference": 4.0, "tolerance": 0.0}]},
    {"id": "M-06", "title": "Subcommutated channel frames per sample",
     "source": "telemetry-data-acquisition leaf worked example "
     "(25 Hz channel on a 100 frame/s stream)",
     "checks": [{"label": "subcommutated_instances(100, 25)",
                 "value_fn": lambda: float(subcommutated_instances(100.0,
                                                                   25.0)),
                 "unit": "frames per sample", "reference": 4.0,
                 "tolerance": 0.0}]},
    {"id": "M-07", "title": "IRIG-B time of year coding",
     "source": "telemetry-data-acquisition leaf worked example "
     "(day 32 at 43200 s)",
     "checks": [{"label": "irig_b_time_of_year(32, 43200)",
                 "value_fn": lambda: irig_b_time_of_year(32, 43200.0),
                 "unit": "s", "reference": 2721600.0, "tolerance": 0.0}]},
    {"id": "M-08", "title": "End-to-end telemetry latency",
     "source": "telemetry-data-acquisition leaf worked example "
     "(5 + 10 + 25 ms)",
     "checks": [{"label": "total_latency(5, 10, 25)",
                 "value_fn": lambda: total_latency(5.0, 10.0, 25.0),
                 "unit": "ms", "reference": 40.0, "tolerance": 1e-9}]},
    {"id": "M-09", "title": "Compressible airspeed identity "
     "(impact pressure / calibrated airspeed round trip)",
     "source": "position-error-calibration leaf worked example "
     "(6258.4 Pa at 100 m/s)",
     "checks": [
         {"label": "impact_pressure_from_cas(100 m/s)",
          "value_fn": lambda: impact_pressure_from_cas(100.0),
          "unit": "Pa", "reference": 6258.4, "tolerance": 0.5},
         {"label": "calibrated_airspeed(qc(100 m/s))",
          "value_fn": lambda: calibrated_airspeed(
              impact_pressure_from_cas(100.0)),
          "unit": "m/s", "reference": 100.0, "tolerance": 1e-6}]},
    {"id": "M-10", "title": "Tower fly-by position error reduction",
     "source": "position-error-calibration leaf worked example "
     "(H_g 500 m, H_p 490 m, 288.15 K -> +0.88 m/s)",
     "checks": [
         {"label": "tower_flyby_position_error(500, 490, 288.15)",
          "value_fn": lambda: tower_flyby_position_error(500.0, 490.0,
                                                         288.15),
          "unit": "m/s", "reference": 0.88, "tolerance": 0.01},
         {"label": "tower_flyby_position_error(500, 510, 288.15) (sign "
          "check: altimeter high)",
          "value_fn": lambda: tower_flyby_position_error(500.0, 510.0,
                                                         288.15),
          "unit": "m/s", "reference": -0.89, "tolerance": 0.01}]},
    {"id": "M-11", "title": "GPS ground speed doublet reduction",
     "source": "position-error-calibration leaf worked example "
     "(98/102 m/s -> 100 m/s TAS; 94.87 m/s CAS at rho/rho0 0.9)",
     "checks": [
         {"label": "gps_doublet_tas(98, 102)",
          "value_fn": lambda: gps_doublet_tas(98.0, 102.0),
          "unit": "m/s", "reference": 100.0, "tolerance": 1e-9},
         {"label": "tas_to_cas(100, rho/rho0=0.9)",
          "value_fn": lambda: tas_to_cas(100.0, 0.9),
          "unit": "m/s", "reference": 94.87, "tolerance": 0.01}]},
    {"id": "M-12", "title": "EPNL integration (10 dB down rule, 10 s "
     "normalization)",
     "source": "noise-certification-test leaf worked example "
     "(constant 90 dB run, 41 samples at 0.5 s -> 93.0103 EPNdB)",
     "checks": [{"label": "epnl_from_pnlt(90 dB x 41 @ 0.5 s)",
                 "value_fn": lambda: epnl_from_pnlt([90.0] * 41, 0.5)[0],
                 "unit": "EPNdB", "reference": 93.0103, "tolerance": 1e-3}]},
    {"id": "M-13", "title": "Cumulative three-point margin rule "
     "(chapter 4 style)",
     "source": "noise-certification-test leaf worked example "
     "(margins [3, 4, 4] sum to 11.0 EPNdB, pass)",
     "checks": [{"label": "cumulative_margin([3, 4, 4]).sum_db",
                 "value_fn": lambda: cumulative_margin([3.0, 4.0, 4.0])[
                     "sum_db"],
                 "unit": "EPNdB", "reference": 11.0, "tolerance": 1e-9}]},
    {"id": "M-14", "title": "Go/no-go gate rejects a failed check",
     "source": "flight-test-planning leaf rule (any failed check forces "
     "NO-GO and names the blocker)",
     "checks": [{"label": "go_no_gate(True, True, False, True).verdict",
                 "value_fn": lambda: go_no_gate(True, True, False, True)[
                     "verdict"],
                 "unit": "", "reference": "NO-GO", "tolerance": None}]},
    {"id": "M-15", "title": "Sensor range verdict",
     "source": "flight-test-instrumentation leaf rule "
     "(|value| <= range -> ok)",
     "checks": [{"label": "sensor_range_verdict(90000 Pa, 110000 Pa)",
                 "value_fn": lambda: sensor_range_verdict(90000.0,
                                                          110000.0),
                 "unit": "", "reference": "ok", "tolerance": None}]},
]


def _card_check_pass(value, reference, tolerance):
    if tolerance is None:
        return str(value) == str(reference)
    return abs(float(value) - float(reference)) <= float(tolerance)


def build_validation_cards() -> list:
    """Compute the method validation cards (JSON-safe dicts)."""
    cards = []
    for spec in CARD_SPECS:
        checks = []
        for chk in spec["checks"]:
            try:
                value = chk["value_fn"]()
            except Exception as e:  # noqa: BLE001 - record honest row
                value = "error: %s" % str(e)[:80]
            checks.append({
                "label": chk["label"],
                "value": value,
                "unit": chk["unit"],
                "reference": chk["reference"],
                "pass": bool(_card_check_pass(value, chk["reference"],
                                              chk["tolerance"])),
            })
        cards.append({"id": spec["id"], "title": spec["title"],
                      "source": spec["source"], "checks": checks})
    return cards


# ---------------------------------------------------------------------------
# Builder: assemble the Flight Test Plan and Requirements Traceability
# ---------------------------------------------------------------------------


def build_flight_test_plan(item: FlightTestPlanItem) -> dict:
    """Build the complete flight test plan content model."""
    # --- test point matrix: grid expansion, repeats, coverage, order ---
    grid = build_test_matrix(item.altitudes, item.speeds, item.weights,
                             item.configurations)
    points = add_repeat_points(grid["points"], item.repeat_interval)
    for pt in points:
        pt["covers"] = ["OBJ-02"]
    repeat_ids = [p["id"] for p in points if p["repeat"]]
    efficiency = sequence_for_efficiency(points)
    efficiency_ids = [p["id"] for p in efficiency]
    steady = steady_state_check(points, item.steady_state_tolerances,
                                item.steady_state_observed)
    coverage = test_matrix_complete(points, item.matrix_objectives)
    matrix = {
        "altitudes": list(item.altitudes),
        "speeds": list(item.speeds),
        "weights": list(item.weights),
        "configurations": list(item.configurations),
        "count": grid["count"],
        "repeat_interval": item.repeat_interval,
        "repeat_ids": repeat_ids,
        "matrix_objectives": list(item.matrix_objectives),
        "points": points,
        "efficiency_order": efficiency_ids,
        "steady_state": steady,
        "coverage": coverage,
        "tolerances": dict(item.steady_state_tolerances),
    }

    # --- instrumentation: range, Nyquist rate, calibration, completeness ---
    adc_step = quantization_error(item.adc_bits, item.adc_range_v)
    channel_rows = []
    for ch in item.channels:
        req_rate = required_sample_rate(ch["fmax_hz"])
        channel_rows.append({
            "id": ch["id"], "parameter": ch["parameter"], "unit": ch["unit"],
            "max_value": ch["max_value"], "sensor_range": ch["sensor_range"],
            "range_verdict": sensor_range_verdict(ch["max_value"],
                                                  ch["sensor_range"]),
            "fmax_hz": ch["fmax_hz"],
            "sample_rate_hz": req_rate,
            "nyquist_ok": nyquist_ok(req_rate, ch["fmax_hz"]),
            "calibrated": ch["calibrated"], "cal_due": ch["cal_due"],
            "calibration_ok": calibration_verdict(ch["calibrated"],
                                                  ch["cal_due"]),
        })
    completeness = instrumentation_complete(item.required_instruments,
                                             item.provided_instruments)
    release_ok = (completeness["verdict"] == "complete"
                  and all(r["range_verdict"] == "ok" for r in channel_rows)
                  and all(r["calibration_ok"] for r in channel_rows)
                  and all(r["nyquist_ok"] for r in channel_rows))
    instrumentation = {
        "channels": channel_rows,
        "adc_bits": item.adc_bits,
        "adc_range_v": item.adc_range_v,
        "adc_step_v": adc_step,
        "completeness": completeness,
        "release": {"verdict": "released" if release_ok else "not-released",
                    "ok": release_ok},
    }

    # --- telemetry chain: frame, rate, assignments, time, latency,
    # link, quality ---
    frame_size = pcm_frame_size(item.telemetry_words, item.telemetry_bits)
    bit_rate = pcm_bit_rate(item.telemetry_frame_rate, item.telemetry_words,
                            item.telemetry_bits)
    super_rows = [{"channel": s["channel"],
                   "sample_rate_hz": s["sample_rate_hz"],
                   "instances_per_frame": supercommutated_instances(
                       s["sample_rate_hz"], item.telemetry_frame_rate)}
                  for s in item.supercommutated]
    sub_rows = [{"channel": s["channel"],
                 "sample_rate_hz": s["sample_rate_hz"],
                 "frames_per_sample": subcommutated_instances(
                     item.telemetry_frame_rate, s["sample_rate_hz"])}
                for s in item.subcommutated]
    cond_verdict = conditioning_verdict(item.conditioning["sensor_span_v"],
                                        item.conditioning["gain"],
                                        item.conditioning["adc_range_v"])
    lat_total = total_latency(item.latency["acquisition_ms"],
                              item.latency["processing_ms"],
                              item.latency["link_ms"])
    lat_ok = latency_ok(lat_total, item.latency["requirement_ms"])
    link_margin = (item.link["received_power_dbm"]
                   - item.link["sensitivity_dbm"])
    link_ok = ground_link_ok(item.link["received_power_dbm"],
                             item.link["sensitivity_dbm"],
                             item.link["min_margin_dbm"])
    quality_ok = telemetry_quality_ok(
        item.quality["bit_error_rate"], item.quality["dropout_percent"],
        item.quality["ber_limit"], item.quality["dropout_limit"])
    telemetry = {
        "frame": {"words_per_frame": item.telemetry_words,
                  "bits_per_word": item.telemetry_bits,
                  "frame_size_bits": frame_size},
        "stream": {"frame_rate": item.telemetry_frame_rate,
                   "bit_rate": bit_rate},
        "supercommutated": super_rows,
        "subcommutated": sub_rows,
        "irig": {"day_of_year": item.irig_day_of_year,
                 "seconds_of_day": item.irig_seconds_of_day,
                 "seconds_of_year": irig_b_time_of_year(
                     item.irig_day_of_year, item.irig_seconds_of_day)},
        "conditioning": {"sensor_span_v": item.conditioning["sensor_span_v"],
                         "gain": item.conditioning["gain"],
                         "conditioned_span_v": (item.conditioning[
                             "sensor_span_v"] * item.conditioning["gain"]),
                         "adc_range_v": item.conditioning["adc_range_v"],
                         "verdict": cond_verdict},
        "latency": {"acquisition_ms": item.latency["acquisition_ms"],
                    "processing_ms": item.latency["processing_ms"],
                    "link_ms": item.latency["link_ms"],
                    "total_ms": lat_total,
                    "requirement_ms": item.latency["requirement_ms"],
                    "ok": lat_ok,
                    "buffer_samples": latency_buffer_samples(
                        item.latency["buffer_latency_s"],
                        item.latency["buffer_sample_rate"])},
        "link": {"received_power_dbm": item.link["received_power_dbm"],
                 "sensitivity_dbm": item.link["sensitivity_dbm"],
                 "min_margin_dbm": item.link["min_margin_dbm"],
                 "margin_db": link_margin, "ok": link_ok},
        "quality": {"bit_error_rate": item.quality["bit_error_rate"],
                    "dropout_percent": item.quality["dropout_percent"],
                    "ber_limit": item.quality["ber_limit"],
                    "dropout_limit": item.quality["dropout_limit"],
                    "ok": quality_ok},
    }

    # --- PCM decommutation plan: period and expected recovered samples ---
    period = frame_period_words(item.decomm_data_words,
                                item.decomm_idle_words)
    frames_expected = int(item.decomm_flight_duration_s
                          * item.telemetry_frame_rate)
    layout_rows = []
    for f in item.decomm_fixed:
        layout_rows.append({"channel": f["channel"], "kind": "fixed",
                            "word": f["word"], "per_frame": 1,
                            "samples": frames_expected})
    for s in item.decomm_super:
        layout_rows.append({"channel": s["channel"], "kind": "super",
                            "slots": list(s["slots"]),
                            "per_frame": len(s["slots"]),
                            "samples": frames_expected * len(s["slots"])})
    for s in item.decomm_sub:
        per_id = frames_expected // s["subframes"]
        layout_rows.append({"channel": s["channel"], "kind": "sub",
                            "word": s["word"], "subframes": s["subframes"],
                            "per_frame": 1,
                            "samples": per_id * s["subframes"],
                            "samples_per_subframe_id": per_id})
    decommutation = {
        "sync_word_hex": item.decomm_sync_word_hex,
        "data_words_per_frame": item.decomm_data_words,
        "idle_words": item.decomm_idle_words,
        "period_words": period,
        "sid_word_index": item.decomm_sid_word_index,
        "sid_mask": item.decomm_sid_mask,
        "layout": layout_rows,
        "flight_duration_s": item.decomm_flight_duration_s,
        "frames_expected": frames_expected,
    }

    # --- PEC campaign ---
    pec = {
        "planned_ias": list(item.pec_planned_ias),
        "methods": list(item.pec_methods),
        "acceptance": {"coverage_min": PEC_COVERAGE_MIN,
                       "residual_rms_max": PEC_RESIDUAL_RMS_MAX,
                       "flyby_reference_cas": FLYBY_REFERENCE_CAS},
        "note": item.pec_note,
    }

    # --- noise certification campaign ---
    noise_rows = noise_test_matrix(item.noise_takeoff_weight_kg,
                                   item.noise_landing_weight_kg,
                                   item.noise_v2_kt,
                                   item.noise_approach_speed_kt,
                                   item.noise_limits)
    noise = {
        "takeoff_weight_kg": item.noise_takeoff_weight_kg,
        "landing_weight_kg": item.noise_landing_weight_kg,
        "v2_kt": item.noise_v2_kt,
        "approach_speed_kt": item.noise_approach_speed_kt,
        "limits": dict(item.noise_limits),
        "geometry": [noise_geometry(c) for c in NOISE_CONDITIONS],
        "matrix_rows": noise_rows,
        "acceptance": {"cumulative_required_db":
                           NOISE_CUMULATIVE_REQUIRED_DB,
                       "t0_s": NOISE_T0, "db_down": NOISE_DB_DOWN},
        "limits_note": item.noise_limits_note,
    }

    # --- build-up ordering and go/no-go gate ---
    order = build_up_order(item.build_up_blocks)
    ordered_blocks = order["ordered"]
    max_risk = max(b["risk"] for b in item.build_up_blocks)
    gate = go_no_gate(item.preflight_checks.get("weather_ok", False),
                      item.preflight_checks.get("aircraft_ready", False),
                      item.preflight_checks.get("instrumentation_ok", False),
                      item.preflight_checks.get("safety_review_ok", False))
    build_up = {
        "blocks": ordered_blocks,
        "verdict": order["verdict"],
        "missing_prerequisites": order["missing_prerequisites"],
        "max_risk": max_risk,
    }

    # --- objectives and requirements traceability ---
    objective_rows = []
    for obj in item.objectives:
        covering = list(obj.get("trace_to", []))
        objective_rows.append({"id": obj["id"], "text": obj["text"],
                               "covering": covering,
                               "traced": bool(covering)})
    req_rows = []
    for r in item.requirements:
        trace_obj = list(r.get("trace_objectives", []))
        req_rows.append({"id": r["id"], "text": r["text"],
                         "source": r.get("source", ""),
                         "verification": r.get("verification", ""),
                         "status": r.get("status", "planned"),
                         "trace_objectives": trace_obj,
                         "traced": bool(trace_obj)})
    objectives_all = all(row["traced"] for row in objective_rows)
    requirements_all = all(row["traced"] for row in req_rows)
    status_counts = {}
    for row in req_rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    traceability = {
        "objectives": objective_rows,
        "objective_verdict": ("complete" if objectives_all
                              else "incomplete"),
        "requirements": req_rows,
        "requirement_verdict": ("trace-complete" if requirements_all
                                else "trace-gaps"),
        "requirement_status_counts": status_counts,
        "total_objectives": len(objective_rows),
        "total_requirements": len(req_rows),
    }

    # --- method validation cards (pre-flight reduction checks) ---
    cards = build_validation_cards()
    cards_all_pass = all(chk["pass"] for card in cards
                         for chk in card["checks"])

    return {
        "document_type": "Flight Test Plan and Requirements Traceability",
        "status": "draft-for-review",
        "item": item.item_name,
        "item_description": item.description,
        "program": item.program,
        "airframe": item.airframe,
        "certification_basis": item.certification_basis,
        "authority": item.authority,
        "matrix": matrix,
        "instrumentation": instrumentation,
        "telemetry": telemetry,
        "decommutation": decommutation,
        "pec": pec,
        "noise": noise,
        "build_up": build_up,
        "go_no_go": gate,
        "traceability": traceability,
        "validation_cards": cards,
        "validation_cards_all_pass": cards_all_pass,
        "supporting_note": item.supporting_note,
        "generated": _today(),
    }


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


def _fmt(x, nd=4) -> str:
    if isinstance(x, float):
        if x == 0.0:
            return "0"
        if x == int(x) and abs(x) < 1e15:
            return str(int(x))
        if 1e-4 <= abs(x) < 1e6:
            return "%.*g" % (nd, x)
        return "%.1e" % x
    return str(x)


def _fmt_list(values, nd=4) -> str:
    return ", ".join(_fmt(v, nd) for v in values)


def _fmt_p(x) -> str:
    """Compact numeric formatting for engineering values."""
    if isinstance(x, float):
        if x == 0.0:
            return "0"
        if 1e-4 <= abs(x) < 1e6:
            return ("%.4g" % x).rstrip(".").rstrip("0") \
                if "." in "%.4g" % x else "%.4g" % x
        return "%.2e" % x
    return str(x)


def _join_names(items):
    if not items:
        return "-"
    return ", ".join(str(x) for x in items)


def render_flight_test_plan_markdown(model: dict) -> str:
    """Render the plan content model as the deliverable markdown."""
    L = []
    A = L.append
    A("# Flight Test Plan and Requirements Traceability")
    A("")
    A("**Item:** %s" % model["item"])
    A("**Program:** %s" % model["program"])
    A("**Airframe:** %s" % model["airframe"])
    A("**Certification basis:** %s" % model["certification_basis"])
    A("**Authority:** %s" % model["authority"])
    A("**Status:** %s" % model["status"])
    A("")
    A("> **DRAFT for human review - not an approval document.** This plan "
      "is a planning artifact for the program sign-off chain. It does not "
      "issue certification approval, claim regulatory sign-off, or release "
      "any aircraft for flight beyond the program's own go/no-go "
      "authority. Noise limits are program inputs from the certification "
      "basis, not derived here.")
    A("")
    A("## 1. Campaign scope and basis")
    A("")
    A(model["item_description"])
    A("")
    A("Bound AeroSkills leaves grounding this plan (all under "
      "flight-test-operations/planning): flight-test-instrumentation, "
      "flight-test-planning, noise-certification-test, "
      "pcm-telemetry-decommutation, position-error-calibration, "
      "telemetry-data-acquisition and test-point-matrix-design. Every "
      "number below is computed by the role core from the real rules of "
      "those leaves; method validation cards (section 11) recompute the "
      "leaves' reference worked examples pre-flight to validate the "
      "reduction chain. No flight data is claimed.")
    A("")
    A("## 2. Test objectives and requirements traceability")
    A("")
    A("| Objective | Traced to (points / blocks / campaigns) | Traced |")
    A("|---|---|---|")
    for row in model["traceability"]["objectives"]:
        A("| %s | %s | %s |" % (row["id"], _join_names(row["covering"]),
                                "yes" if row["traced"] else "NO"))
    A("")
    A("Objective coverage verdict: **%s** (%d/%d traced)."
      % (model["traceability"]["objective_verdict"].upper(),
         model["traceability"]["total_objectives"],
         model["traceability"]["total_objectives"]))
    A("")
    A("| Requirement | Source | Verification | Status | Traced via |")
    A("|---|---|---|---|---|")
    for row in model["traceability"]["requirements"]:
        A("| %s | %s | %s | %s | %s |"
          % (row["id"], row["source"], row["verification"],
             row["status"], _join_names(row["trace_objectives"])))
    A("")
    A("Requirement trace verdict: **%s** (%d/%d requirements traced to a "
      "planned point, block or campaign). Verification status rollup: %s "
      "- verification executes during the campaign; this plan claims no "
      "completed verification."
      % (model["traceability"]["requirement_verdict"].upper(),
         model["traceability"]["total_requirements"],
         model["traceability"]["total_requirements"],
         ", ".join("%s %d" % (k, v)
                   for k, v in sorted(
                       model["traceability"][
                           "requirement_status_counts"].items()))))
    A("")
    A("## 3. Test point matrix")
    A("")
    mtx = model["matrix"]
    A("Condition sweeps (one axis at a time, grid is the cartesian "
      "product, altitude-major): altitude %s m, speed %s m/s, weight %s "
      "kg, configuration %s."
      % (_fmt_list(mtx["altitudes"]), _fmt_list(mtx["speeds"]),
         _fmt_list(mtx["weights"]),
         ", ".join(str(c) for c in mtx["configurations"])))
    A("")
    A("**Grid count: %d test points.** Repeat interval %d -> repeat "
      "points: %s." % (mtx["count"], mtx["repeat_interval"],
                       _join_names(mtx["repeat_ids"])))
    A("")
    A("| Point | Altitude (m) | Speed (m/s) | Weight (kg) | "
      "Configuration | Repeat |")
    A("|---|---|---|---|---|---|")
    for p in mtx["points"]:
        A("| %s | %s | %s | %s | %s | %s |"
          % (p["id"], _fmt(p["altitude"]), _fmt(p["speed"]),
             _fmt(p["weight"]), p["configuration"],
             "yes" if p["repeat"] else ""))
    A("")
    A("## 4. Point sequencing, repeats and steady state criteria")
    A("")
    A("Efficiency sequence (configuration flown in one block, altitude "
      "swept once, then speed levels): %s."
      % ", ".join(mtx["efficiency_order"]))
    A("")
    A("Steady state tolerance band per condition: altitude +-%s m, "
      "speed +-%s m/s, weight +-%s kg. A flown point is valid only when "
      "every observed value lies inside the band (|observed - planned| "
      "<= tolerance); invalid points are reflown before the matrix "
      "closes."
      % (_fmt(mtx["tolerances"]["altitude"]),
         _fmt(mtx["tolerances"]["speed"]),
         _fmt(mtx["tolerances"]["weight"])))
    ss = mtx["steady_state"]
    A("")
    A("Steady state check on the recorded readings: %d valid, %d invalid "
      "-> verdict **%s**."
      % (len(ss["valid"]), len(ss["invalid"]), ss["verdict"].upper()))
    cov = mtx["coverage"]
    A("")
    A("Matrix coverage of the matrix objectives (%s): verdict **%s**, "
      "uncovered: %s."
      % (", ".join(str(o) for o in mtx.get("matrix_objectives", [])),
         cov["verdict"].upper(), _join_names(cov["uncovered"])))
    A("")
    A("## 5. Instrumentation plan")
    A("")
    ins = model["instrumentation"]
    A("Every channel is sized at the required sample rate "
      "(margin 2.5 x the Nyquist rate, i.e. 5 times the maximum "
      "frequency of interest) with the anti-aliasing filter set ahead of "
      "the sampler. ADC: %d bit over a %s V full-scale span -> "
      "resolution %s V (1 LSB); worst-case quantization error half a "
      "step."
      % (ins["adc_bits"], _fmt(ins["adc_range_v"]),
         _fmt(ins["adc_step_v"])))
    A("")
    A("| Channel | Parameter | Max value | Sensor range | Range | "
      "fmax (Hz) | Sample rate (Hz) | Nyquist | Cal current |")
    A("|---|---|---|---|---|---|---|---|---|")
    for ch in ins["channels"]:
        A("| %s | %s | %s %s | +-%s %s | %s | %s | %s | %s | %s |"
          % (ch["id"], ch["parameter"], _fmt(ch["max_value"]),
             ch["unit"], _fmt(ch["sensor_range"]), ch["unit"],
             ch["range_verdict"], _fmt(ch["fmax_hz"]),
             _fmt(ch["sample_rate_hz"]),
             "ok" if ch["nyquist_ok"] else "FAIL",
             "yes" if ch["calibration_ok"] else "DUE"))
    A("")
    A("Instrumentation completeness (required vs provided): verdict "
      "**%s**, missing: %s. Release verdict: **%s** - a channel is "
      "released only when its calibration is current, its sensor range "
      "covers the expected signal, and its sample rate satisfies the "
      "Nyquist criterion with margin."
      % (ins["completeness"]["verdict"].upper(),
         _join_names(ins["completeness"]["missing"]),
         ins["release"]["verdict"].upper()))
    A("")
    A("## 6. Telemetry and data acquisition plan")
    A("")
    tel = model["telemetry"]
    A("PCM minor frame: %d words of %d bits -> **%d bits per frame**; "
      "stream bit rate at %s frames/s -> **%s bit/s**."
      % (tel["frame"]["words_per_frame"], tel["frame"]["bits_per_word"],
         tel["frame"]["frame_size_bits"], _fmt(tel["stream"]["frame_rate"]),
         _fmt(tel["stream"]["bit_rate"])))
    A("")
    A("Supercommutated channels (sampled faster than the frame rate, "
      "integer instances per frame):")
    A("")
    A("| Channel | Sample rate (Hz) | Instances per frame |")
    A("|---|---|---|")
    for s in tel["supercommutated"]:
        A("| %s | %s | %d |" % (s["channel"], _fmt(s["sample_rate_hz"]),
                                s["instances_per_frame"]))
    A("")
    A("Subcommutated channels (sampled slower than the frame rate, "
      "integer frames per sample):")
    A("")
    A("| Channel | Sample rate (Hz) | Frames per sample |")
    A("|---|---|---|")
    for s in tel["subcommutated"]:
        A("| %s | %s | %d |" % (s["channel"], _fmt(s["sample_rate_hz"]),
                                s["frames_per_sample"]))
    A("")
    A("IRIG-B time coding: day of year %d, seconds of day %s -> seconds "
      "of year **%s s**."
      % (tel["irig"]["day_of_year"], _fmt(tel["irig"]["seconds_of_day"]),
         _fmt(tel["irig"]["seconds_of_year"])))
    A("")
    A("Signal conditioning: sensor span %s V x gain %s = %s V conditioned "
      "span vs %s V ADC full scale -> verdict **%s**."
      % (_fmt(tel["conditioning"]["sensor_span_v"]),
         _fmt(tel["conditioning"]["gain"]),
         _fmt(tel["conditioning"]["conditioned_span_v"]),
         _fmt(tel["conditioning"]["adc_range_v"]),
         tel["conditioning"]["verdict"].upper()))
    A("")
    A("Data latency: acquisition %s ms + processing %s ms + link %s ms = "
      "**%s ms** end-to-end vs requirement %s ms -> %s; pipeline buffer "
      "holds %d samples (ceil(latency x sample rate))."
      % (_fmt(tel["latency"]["acquisition_ms"]),
         _fmt(tel["latency"]["processing_ms"]),
         _fmt(tel["latency"]["link_ms"]), _fmt(tel["latency"]["total_ms"]),
         _fmt(tel["latency"]["requirement_ms"]),
         "within requirement" if tel["latency"]["ok"] else "EXCEEDS",
         tel["latency"]["buffer_samples"]))
    A("")
    A("Ground station link: received power %s dBm, receiver sensitivity "
      "%s dBm -> margin %s dB vs %s dB minimum -> %s."
      % (_fmt(tel["link"]["received_power_dbm"]),
         _fmt(tel["link"]["sensitivity_dbm"]),
         _fmt(tel["link"]["margin_db"]),
         _fmt(tel["link"]["min_margin_dbm"]),
         "ok" if tel["link"]["ok"] else "FAIL"))
    A("")
    A("Telemetry quality: bit error rate %s vs limit %s, dropouts %s %% "
      "vs limit %s %% -> data release verdict %s."
      % (_fmt(tel["quality"]["bit_error_rate"]),
         _fmt(tel["quality"]["ber_limit"]),
         _fmt(tel["quality"]["dropout_percent"]),
         _fmt(tel["quality"]["dropout_limit"]),
         "ok" if tel["quality"]["ok"] else "REVIEW"))
    A("")
    A("## 7. PCM telemetry decommutation plan")
    A("")
    dec = model["decommutation"]
    A("Decommutation validation fixture (reference layout of the "
      "pcm-telemetry-decommutation leaf worked example): sync word %s, "
      "%d data words + %d idle word(s) -> **frame period %d words**; "
      "subframe id at data word %d masked with 0x%04X."
      % (dec["sync_word_hex"], dec["data_words_per_frame"],
         dec["idle_words"], dec["period_words"],
         dec["sid_word_index"], dec["sid_mask"]))
    A("")
    A("Planned telemetry flight duration %s s at %s frames/s -> %d "
      "expected minor frames; recovered samples per channel follow the "
      "demultiplex rules (fixed: 1 value per frame; supercommutated: one "
      "value per slot per frame; subcommutated: keyed by subframe id)."
      % (_fmt(dec["flight_duration_s"]),
         _fmt(model["telemetry"]["stream"]["frame_rate"]),
         dec["frames_expected"]))
    A("")
    A("| Channel | Kind | Word(s) | Values per frame | Expected samples |")
    A("|---|---|---|---|---|")
    for row in dec["layout"]:
        if row["kind"] == "fixed":
            A("| %s | fixed | %d | 1 | %d |"
              % (row["channel"], row["word"], row["samples"]))
        elif row["kind"] == "super":
            A("| %s | super | %s | %d | %d |"
              % (row["channel"], _join_names(row["slots"]),
                 row["per_frame"], row["samples"]))
        else:
            A("| %s | sub (%d subframes) | %d | 1 | %d (%d per subframe "
              "id) |"
              % (row["channel"], row["subframes"], row["word"],
                 row["samples"], row["samples_per_subframe_id"]))
    A("")
    A("A corrupted sync word drops the whole frame from every channel; "
      "the recovered series feed data reduction only after the sync miss "
      "report is reviewed.")
    A("")
    A("## 8. Airspeed position error calibration (PEC) campaign")
    A("")
    pec = model["pec"]
    A("Planned calibration points at indicated airspeeds %s m/s, flown "
      "by the %s reference method(s); repeat passes at a scheduled speed "
      "are combined by their least-squares mean."
      % (_fmt_list(pec["planned_ias"]), ", ".join(pec["methods"])))
    A("")
    A("PEC acceptance criteria (data quality verdict): coverage of "
      "planned points inside the calibrated span >= **%.2f** and "
      "residual RMS of the observations about the piecewise-linear "
      "correction curve <= **%s m/s**; the verdict is adequate only when "
      "both hold, else the campaign extends to cover the planned points."
      % (pec["acceptance"]["coverage_min"],
         _fmt(pec["acceptance"]["residual_rms_max"])))
    A("")
    A("Correction curve knots (V_ias, dVp) become the PEC table rows "
      "V_cas = V_ias + dVp that feed the data reduction of every later "
      "flight. The compressible airspeed relations used by the reduction "
      "are validated pre-flight in the cards of section 11 (M-09 to "
      "M-11); the fly-by reduction evaluates the indicator scale at the "
      "reference pass speed (%s m/s when the pass speed is not "
      "recorded)." % _fmt(pec["acceptance"]["flyby_reference_cas"]))
    A("")
    A(pec["note"])
    A("")
    A("## 9. Noise certification measurement campaign")
    A("")
    nz = model["noise"]
    A("Reference measurement geometry (typical public FAR 36 summary "
      "values):")
    A("")
    for g in nz["geometry"]:
        if g["condition"] == "flyover":
            A("- Flyover: microphone on the extended runway centerline "
              "%s m from the brake release point (%s)."
              % (_fmt(g["distance_m"]), g["reference"]))
        elif g["condition"] == "sideline":
            A("- Sideline: microphone %s m lateral of the runway "
              "centerline at the point of maximum takeoff noise (%s)."
              % (_fmt(g["lateral_m"]), g["reference"]))
        else:
            A("- Approach: microphone %s m from the threshold under the "
              "flight path at %s m altitude on the %s degree glide slope "
              "(%s)."
              % (_fmt(g["distance_m"]), _fmt(g["altitude_m"]),
                 _fmt(g["glide_deg"]), g["reference"]))
    A("")
    A("Certification test matrix rows (weights and reference speeds; "
      "flyover speed reference V2 + 10 kt):")
    A("")
    A("| Condition | Configuration | Weight (kg) | Reference speed (kt) | "
      "Limit (EPNdB) | Demonstration target (EPNdB) |")
    A("|---|---|---|---|---|---|")
    for r in nz["matrix_rows"]:
        A("| %s | %s | %s | %s | %s | %s |"
          % (r["condition"], r["configuration"], _fmt(r["weight_kg"]),
             _fmt(r["reference_speed_kt"]), _fmt(r["limit"]),
             _fmt(r["target_epnl"])))
    A("")
    A("Acceptance rule applied to the measured EPNL of each run: "
      "individual margin (limit - EPNL) >= 0 per point, and the "
      "cumulative three-point margin (sum of the individual margins) "
      ">= **%s EPNdB** (typical chapter 4 / stage 4 check at reference "
      "level; the exact rule set depends on the certification basis). "
      "The EPNL integration (10 dB down rule, %s s normalization) and "
      "the margin math are validated pre-flight in the cards of section "
      "11 (M-12, M-13)."
      % (_fmt(nz["acceptance"]["cumulative_required_db"]),
         _fmt(nz["acceptance"]["t0_s"])))
    A("")
    A("%s" % nz["limits_note"])
    A("")
    A("## 10. Build-up flights and go/no-go gate")
    A("")
    bu = model["build_up"]
    A("Flight blocks ordered by the build-up approach (ascending risk; a "
      "block is flown only after its prerequisites):")
    A("")
    A("| Block | Flight block | Risk level | Prerequisites |")
    A("|---|---|---|---|")
    for b in bu["blocks"]:
        A("| %s | %s | %d | %s |"
          % (b["id"], b["name"], b["risk"],
             _join_names(b["prerequisites"])))
    A("")
    A("Build-up order verdict: **%s** (missing prerequisites: %s). "
      "Highest planned risk level: %d."
      % (bu["verdict"].upper(), _join_names(
          ["%s->%s" % (m["point"], _join_names(m["missing"]))
           for m in bu["missing_prerequisites"]]), bu["max_risk"]))
    A("")
    gg = model["go_no_go"]
    A("Go/no-go gate for the first build-up flight (weather, aircraft "
      "readiness, instrumentation release, safety review - all must "
      "pass):")
    A("")
    A("| Check | Passed |")
    A("|---|---|")
    for name, val in (("weather_ok", gg.get("weather_ok")),
                      ("aircraft_ready", gg.get("aircraft_ready")),
                      ("instrumentation_ok", gg.get("instrumentation_ok")),
                      ("safety_review_ok", gg.get("safety_review_ok"))):
        A("| %s | %s |" % (name, "yes" if val else "NO"))
    A("")
    A("**Go/no-go verdict: %s** (blockers: %s). A NO-GO names the "
      "blocker and the flight does not depart; the gate is re-run before "
      "every flight."
      % (gg["verdict"], _join_names(gg["blockers"])))
    A("")
    A("## 11. Method validation cards (reduction and analysis checks)")
    A("")
    A("Each card recomputes a reference worked example of a bound leaf "
      "with the role's own reduction/analysis code. These are pre-flight "
      "software validation checks - they are not flight data and carry "
      "no compliance claim.")
    A("")
    for card in model["validation_cards"]:
        A("**%s - %s** (source: %s)" % (card["id"], card["title"],
                                        card["source"]))
        A("")
        A("| Check | Computed | Reference | PASS |")
        A("|---|---|---|---|")
        for chk in card["checks"]:
            A("| %s | %s %s | %s %s | %s |"
              % (chk["label"], _fmt(chk["value"]), chk["unit"],
                 _fmt(chk["reference"]), chk["unit"],
                 "PASS" if chk["pass"] else "FAIL"))
        A("")
    A("## 12. Plan issuance, evidence gates and close-out")
    A("")
    A("This plan is issued as a **DRAFT** for human review in the "
      "program sign-off chain. It is **not an approval** and carries no "
      "regulatory authority: certification approval is issued by the "
      "regulator/designee, and individual flights are released only by "
      "the program's go/no-go gate (section 10).")
    A("")
    A("Close-out rollup at issuance: objectives traced %d/%d (verdict "
      "%s); requirements traced %d/%d (verdict %s); matrix steady-state "
      "verdict %s; instrumentation release %s; validation cards %s. "
      "Verification of every requirement executes during the campaign "
      "and is reported separately after each flight."
      % (model["traceability"]["total_objectives"],
         model["traceability"]["total_objectives"],
         model["traceability"]["objective_verdict"].upper(),
         model["traceability"]["total_requirements"],
         model["traceability"]["total_requirements"],
         model["traceability"]["requirement_verdict"].upper(),
         mtx["steady_state"]["verdict"].upper(),
         model["instrumentation"]["release"]["verdict"].upper(),
         "all pass" if model["validation_cards_all_pass"] else "FAIL"))
    A("")
    A("Generated: %s  ·  Role: flight-test-planning-engineer  ·  "
      "Status: %s" % (model["generated"], model["status"]))
    A("")
    A("---")
    A("")
    A("*Flight Test Plan and Requirements Traceability - DRAFT for human "
      "review. Not an approval document.*")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Evidence gates
# ---------------------------------------------------------------------------

GATE_HELP = {
    "scope_identified": "item, airframe, basis, authority and honest "
                        "draft status present",
    "risk_levels_identified": "build-up blocks carry numeric risk levels "
                              "and are ordered by the build-up approach",
    "requirements_traceable": "every objective and requirement traces to "
                              "a planned point, block or campaign",
    "matrix_numbers_present": "grid count equals the cartesian product, "
                              "repeat points and efficiency order exist",
    "steady_state_checked": "flown points validated against the steady "
                            "state tolerance band with a verdict",
    "instrumentation_released": "every channel current on calibration, "
                                "in-range and sampled above Nyquist",
    "telemetry_numbers_present": "frame size, bit rate, IRIG time, "
                                 "latency/link/quality verdicts present",
    "decommutation_numbers_present": "frame period and expected "
                                     "per-channel recovered samples",
    "campaign_acceptance_defined": "PEC coverage/residual acceptance and "
                                   "noise cumulative margin rule stated",
    "build_up_gate_checked": "go/no-go verdict and blocker list present",
    "validation_cards_pass": "all method validation cards pass",
    "sign_off_honest": "document is marked draft-for-review, not approval",
}


def check_flight_test_plan(model: dict, risk_level=None) -> dict:
    """Run the evidence gates against a plan content model."""
    mtx = model.get("matrix", {})
    ins = model.get("instrumentation", {})
    tel = model.get("telemetry", {})
    dec = model.get("decommutation", {})
    pec = model.get("pec", {})
    nz = model.get("noise", {})
    bu = model.get("build_up", {})
    tr = model.get("traceability", {})
    results = {
        "scope_identified": bool(model.get("item")) and bool(
            model.get("certification_basis")) and model.get(
            "status") == "draft-for-review",
        "risk_levels_identified": bool(bu.get("blocks")) and all(
            isinstance(b.get("risk"), int) and b["risk"] >= 0
            for b in bu["blocks"]) and bu.get("verdict") in ("ok",
                                                             "missing-prerequisites"),
        "requirements_traceable": tr.get("objective_verdict") == "complete"
            and tr.get("requirement_verdict") == "trace-complete"
            and tr.get("total_objectives", 0) > 0,
        "matrix_numbers_present": (mtx.get("count")
                                   == len(mtx.get("points", []))
                                   == (len(mtx.get("altitudes", []))
                                       * len(mtx.get("speeds", []))
                                       * len(mtx.get("weights", []))
                                       * len(mtx.get("configurations", [])))
                                   and bool(mtx.get("repeat_ids"))
                                   and bool(mtx.get("efficiency_order"))),
        "steady_state_checked": mtx.get("steady_state", {}).get(
            "verdict") in ("all-valid", "invalid-points"),
        "instrumentation_released": bool(ins.get("channels")) and ins.get(
            "release", {}).get("ok") is True,
        "telemetry_numbers_present": (
            isinstance(tel.get("stream", {}).get("bit_rate"), (int, float))
            and tel["stream"]["bit_rate"] > 0.0
            and tel.get("irig", {}).get("seconds_of_year", 0) > 0
            and tel.get("latency", {}).get("ok") in (True, False)
            and tel.get("link", {}).get("ok") in (True, False)
            and tel.get("quality", {}).get("ok") in (True, False)),
        "decommutation_numbers_present": dec.get("period_words", 0) > 0
            and dec.get("frames_expected", 0) > 0
            and bool(dec.get("layout")),
        "campaign_acceptance_defined": (
            abs(pec.get("acceptance", {}).get("coverage_min", 0.0)
                - PEC_COVERAGE_MIN) < 1e-12
            and abs(pec["acceptance"]["residual_rms_max"]
                    - PEC_RESIDUAL_RMS_MAX) < 1e-12
            and abs(nz.get("acceptance", {}).get("cumulative_required_db",
                                                 0.0)
                    - NOISE_CUMULATIVE_REQUIRED_DB) < 1e-12
            and bool(nz.get("geometry")) and bool(nz.get("matrix_rows"))),
        "build_up_gate_checked": model.get("go_no_go", {}).get(
            "verdict") in ("GO", "NO-GO") and isinstance(
            model["go_no_go"].get("blockers"), list),
        "validation_cards_pass": bool(model.get("validation_cards"))
            and model.get("validation_cards_all_pass") is True,
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    if risk_level is not None:
        results["risk_level_%d_covered" % risk_level] = (
            bu.get("max_risk", -1) >= risk_level)
    results["all_pass"] = all(results.values())
    return results


def check_flight_test_plan_markdown(md_text: str, risk_level=None) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    checks = {
        "has_title": "flight test plan and requirements traceability" in low,
        "has_item": "item:" in low and "certification basis" in low,
        "has_traceability": "trace-complete" in low
            and "objective coverage verdict" in low,
        "has_matrix_number": "grid count" in low and "test points" in low
            and "repeat points" in low,
        "has_instrumentation_number": "sample rate" in low and "hz" in low,
        "has_telemetry_number": "bit/s" in low and "seconds of year" in low,
        "has_decomm_number": "frame period" in low and "words" in low,
        "has_pec_acceptance": "0.95" in low and "residual rms" in low,
        "has_noise_acceptance": "epndb" in low and "6500" in low,
        "has_build_up_gate": "go/no-go verdict" in low
            and ("go" in low or "no-go" in low),
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
    }
    if risk_level is not None:
        # the build-up table carries one row per block:
        # | BLK-06 | <name> | 3 | <prereqs> |
        block_risks = [int(m.group(2)) for m in
                       re.finditer(r"\|\s*(BLK-\d+)\s*\|[^|]*\|\s*(\d+)\s*\|",
                                   md_text)]
        checks["risk_level_%d_covered" % risk_level] = bool(
            block_risks and max(block_risks) >= risk_level)
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling."""
    return check_flight_test_plan_markdown(md_text)


def example_plan_markdown() -> str:
    return render_flight_test_plan_markdown(
        build_flight_test_plan(example_item()))


if __name__ == "__main__":
    model = build_flight_test_plan(example_item())
    md = render_flight_test_plan_markdown(model)
    print("ITEM:", model["item"])
    print("MATRIX COUNT:", model["matrix"]["count"])
    print("BIT RATE:", model["telemetry"]["stream"]["bit_rate"])
    print("FRAME PERIOD WORDS:", model["decommutation"]["period_words"])
    print("GO/NO-GO:", model["go_no_go"]["verdict"])
    print("TRACE:", model["traceability"]["requirement_verdict"])
    print("GATES:", check_flight_test_plan(model))
    print("RENDERED:", len(md), "chars")
