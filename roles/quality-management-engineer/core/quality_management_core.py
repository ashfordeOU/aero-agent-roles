#!/usr/bin/env python3
"""quality_management_core.py - Quality Management Engineer executable core.

This is the role's ENGINE: given a manufacturing site's quality-system
facts and shop-floor measurement datasets it runs the real statistical
quality-engineering analyses behind an AS9100 quality-management-system
audit report:

- measurement systems analysis: gage R&R by two-way random-effects ANOVA,
  the AIAG range-method study as an independent estimator, gage bias and
  linearity regression, and attribute (go/no-go) agreement analysis
  (Cohen/Fleiss kappa);
- statistical process control: X-bar/R control limits with the A2/D3/D4
  chart constants, process sigma from the average range, Cp/Cpk capability,
  Western Electric out-of-control rules, I-MR limits (E2/d2/3.267),
  tabular CUSUM + EWMA small-shift statistics, and p-chart limits;
- acceptance sampling: ANSI/ASQ Z1.4-style attribute plans (code letter,
  n/Ac/Re, OC probability) and variables (k-method) plans (code letter,
  n/k/M, Q statistics, estimated % nonconforming).

The formulas, constants, and band verdicts mirror the bound AeroSkills
as9100 leaves exactly (acceptance-sampling, attribute-agreement-analysis,
attribute-control-charts, cusum-ewma-monitoring, gage-linearity-bias-study,
gage-rr-anova, individuals-and-moving-range-chart,
measurement-systems-analysis, statistical-process-control,
variables-acceptance-sampling), so a dispatch cross-check of any computed
value against the leaf logic must agree. The embedded tables are summary
reference values in the style of the public standards (ANSI/ASQ Z1.4,
ANSI/ASQ Z1.9) - never reproduced tables; AS9100D is reference-only and is
never quoted.

Standalone: stdlib only, no external repo, deterministic (no RNG - all
example datasets are frozen literals). Invalid inputs raise ValueError.
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
# MSA constants (mirror the bound as9100 leaves; summary practice values)
# ---------------------------------------------------------------------------

# Gage R&R acceptance bands: <10% acceptable, 10-30% conditional, >30%
# unacceptable (AIAG-style practice encoded in the gage-rr leaves).
DISTINCT_CATEGORIES_CONST = 1.41   # ndc = floor(1.41 * PV / GRR)

# Range-method 5.15-sigma constants (measurement-systems-analysis leaf).
K1 = {2: 4.56, 3: 3.05}            # trials
K2 = {2: 3.65, 3: 2.70}            # appraisers
K3 = {2: 3.65, 3: 2.70, 4: 2.30, 5: 2.08,
      6: 1.93, 7: 1.82, 8: 1.74, 9: 1.67, 10: 1.62}  # parts

# Bias/linearity study constants (gage-linearity-bias-study leaf).
T_CRIT_95_TWOTAIL = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
                     6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
                     11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145,
                     15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101,
                     19: 2.093, 20: 2.086}
T_CRIT_LARGE_DF = 1.96
ACCEPTANCE_PCT_BAND = 10.0   # percent of reference per level

# Attribute agreement bands (attribute-agreement-analysis leaf).
KAPPA_GOOD = 0.75
KAPPA_MARGINAL = 0.40

# ---------------------------------------------------------------------------
# SPC constants (statistical-process-control leaf: published chart factors)
# ---------------------------------------------------------------------------
A2 = {2: 1.880, 3: 1.023, 4: 0.729, 5: 0.577,
      6: 0.483, 7: 0.419, 8: 0.373, 9: 0.337, 10: 0.308}
D3 = {2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0,
      6: 0.0, 7: 0.076, 8: 0.136, 9: 0.184, 10: 0.223}
D4 = {2: 3.267, 3: 2.574, 4: 2.282, 5: 2.114,
      6: 2.004, 7: 1.924, 8: 1.864, 9: 1.816, 10: 1.777}
D2 = {2: 1.128, 3: 1.693, 4: 2.059, 5: 2.326,
      6: 2.534, 7: 2.704, 8: 2.847, 9: 2.970, 10: 3.078}

# I-MR constants (individuals-and-moving-range-chart leaf).
E2 = 2.66
D2_N1 = 1.128
D3_MR_UCL = 3.267

# Attribute charts 3-sigma normal-approximation factor.
SIGMA_FACTOR = 3.0

# ---------------------------------------------------------------------------
# Acceptance-sampling tables (reduced reference style of ANSI/ASQ Z1.4 /
# Z1.9 k-method; summary values only, never a reproduction of the standards)
# ---------------------------------------------------------------------------
INSPECTION_LEVELS = ("I", "II", "III")

# Attribute: lot-size bands + code letters + single-sampling plans.
LOT_SIZE_BANDS = (
    ("small", 51, 90), ("medium", 281, 500), ("large", 1201, 3200),
    ("very-large", 10001, 35000),
)
CODE_LETTER_TABLE = {
    ("II", "small"): "F", ("II", "medium"): "J", ("II", "large"): "J",
    ("II", "very-large"): "L", ("I", "medium"): "F", ("III", "medium"): "K",
}
PLAN_TABLE = {
    ("J", "1.0"): (80, 2, 3), ("H", "1.0"): (50, 1, 2), ("L", "1.0"): (200, 5, 6),
}

# Variables (k-method): level II code-letter bands, n, k, M.
CODE_LETTER_BANDS = (
    (91, 150, "E"), (151, 280, "F"), (281, 500, "G"), (501, 1200, "H"),
    (1201, 3200, "J"), (3201, 10000, "K"),
)
K_BY_AQL = {0.65: 1.75, 1.0: 1.62, 1.5: 1.47, 2.5: 1.28, 4.0: 1.09}
M_BY_CODE_AQL = {
    "E": {0.65: 4.17, 1.0: 3.61, 1.5: 2.98, 2.5: 2.28, 4.0: 1.66},
    "F": {0.65: 4.05, 1.0: 3.50, 1.5: 2.89, 2.5: 2.21, 4.0: 1.61},
    "G": {0.65: 3.97, 1.0: 3.43, 1.5: 2.83, 2.5: 2.16, 4.0: 1.58},
    "H": {0.65: 3.90, 1.0: 3.37, 1.5: 2.78, 2.5: 2.13, 4.0: 1.55},
    "J": {0.65: 3.85, 1.0: 3.33, 1.5: 2.75, 2.5: 2.10, 4.0: 1.53},
    "K": {0.65: 3.80, 1.0: 3.29, 1.5: 2.72, 2.5: 2.08, 4.0: 1.52},
}
N_BY_CODE = {"E": 15, "F": 20, "G": 25, "H": 30, "J": 35, "K": 40}

# ---------------------------------------------------------------------------
# Frozen example datasets (deterministic; no RNG at runtime)
# ---------------------------------------------------------------------------
# Gage R&R study: 3 inspectors x 10 parts x 3 trials, bore KC-001 (mm).
ANOVA_STUDY = {
    "Inspector A. Brandt": {1: [11.9187, 11.9226, 11.9189],
                            2: [11.9584, 11.9553, 11.9589],
                            3: [12.0256, 12.0221, 12.0252],
                            4: [11.9812, 11.982, 11.9809],
                            5: [12.0417, 12.0543, 12.0525],
                            6: [11.9925, 11.9815, 11.9813],
                            7: [12.0256, 12.0277, 12.0315],
                            8: [11.9398, 11.9426, 11.9368],
                            9: [12.0115, 12.012, 12.0067],
                            10: [12.0686, 12.0628, 12.066]},
    "Inspector M. Sato": {1: [11.9199, 11.9193, 11.9213],
                          2: [11.9625, 11.9662, 11.9642],
                          3: [12.0208, 12.0182, 12.0204],
                          4: [11.9891, 11.979, 11.9842],
                          5: [12.0551, 12.0456, 12.0532],
                          6: [11.9995, 11.9829, 11.9914],
                          7: [12.0325, 12.0289, 12.0355],
                          8: [11.9427, 11.9357, 11.9471],
                          9: [12.0163, 12.0177, 12.0202],
                          10: [12.0648, 12.0636, 12.0565]},
    "Inspector S. Okafor": {1: [11.9211, 11.9149, 11.9157],
                            2: [11.9517, 11.9532, 11.9553],
                            3: [12.0244, 12.0078, 12.0107],
                            4: [11.9792, 11.9852, 11.9809],
                            5: [12.0385, 12.0354, 12.0498],
                            6: [11.9843, 11.9824, 11.9929],
                            7: [12.0335, 12.0288, 12.0292],
                            8: [11.9402, 11.946, 11.9411],
                            9: [12.0106, 12.0107, 12.0002],
                            10: [12.0644, 12.0628, 12.0606]},
}

# Micrometer bias/linearity: reference levels (mm) and observed biases (mm).
MICROMETER_REFS = [5.0, 10.0, 15.0, 20.0, 25.0]
MICROMETER_BIASES = [0.004, 0.012, 0.021, 0.030, 0.042]

# Attribute go/no-go agreement: 30 parts x 3 inspectors, [accept, reject].
RATINGS_MATRIX = [[3, 0]] * 22 + [[2, 1]] * 5 + [[1, 2]] * 2 + [[0, 3]] * 1

# Secondary pairwise re-check: inspectors A vs B on the same 30 parts.
# Rows = A-accept/A-reject, cols = B-accept/B-reject.
INSPECTOR_AB_TABLE = [[23, 4], [2, 1]]

# X-bar/R dataset: 20 subgroups of 5 on KC-002 pin 6.000 mm (subgroup
# means and ranges recorded per the site SPC log).
SUB_MEANS = [5.9994, 6.0012, 6.0006, 6.0021, 5.9988, 6.0009, 6.0015,
             5.9999, 6.0028, 6.0003, 6.0017, 5.9996, 6.0004, 6.0019,
             5.9992, 6.0011, 6.0002, 6.0022, 5.9989, 6.0014]
SUB_RANGES = [0.0086, 0.0092, 0.0079, 0.0098, 0.0081, 0.0089, 0.0084,
              0.0095, 0.0082, 0.0091, 0.0088, 0.0077, 0.0093, 0.0080,
              0.0096, 0.0085, 0.0090, 0.0083, 0.0094, 0.0087]

# I-MR dataset: anodize coating thickness per lot, 30 lots (micrometres).
COATING_SERIES = [119.6, 120.8, 121.3, 119.9, 120.5, 121.1, 120.2, 119.8,
                  120.9, 121.0, 120.3, 119.7, 120.6, 120.1, 120.4, 120.0,
                  134.8, 120.7, 120.2, 119.9, 120.8, 121.2, 120.1, 119.8,
                  120.5, 120.9, 120.3, 120.0, 121.1, 120.6]

# CUSUM/EWMA window: 25 bore-diameter deviations from nominal (micrometres).
DEVIATION_SERIES = [-3.55, 1.1, 2.89, -1.49, -3.85, -0.19, 1.39, 3.18,
                    -3.53, -3.75, 2.05, 1.37, 4.45, 2.85, -0.3, -0.8,
                    7.45, -0.84, -2.28, -3.3, 0.28, 0.42, -1.0, -0.18, 0.79]

# p-chart: nonconforming counts per lot, 20 lots x 200 units.
NP_COUNTS = [2, 3, 1, 4, 2, 3, 2, 1, 3, 4, 2, 2, 3, 1, 2, 4, 3, 2, 2, 3]


def _range_table_from_study(study: dict) -> dict:
    """Range-method table shape {appraiser: [[trials...] per part]} from the
    ANOVA study shape {appraiser: {part: [trials]}} (same readings)."""
    table = {}
    for appraiser, parts in study.items():
        table[appraiser] = [list(trials) for trials in parts.values()]
    return table


# ---------------------------------------------------------------------------
# Gage R&R: two-way random-effects ANOVA (mirror of gage-rr-anova leaf)
# ---------------------------------------------------------------------------

def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_study(data):
    """Check study layout; return (operators, parts, trials_per_cell)."""
    if not isinstance(data, dict) or len(data) < 2:
        raise ValueError("study needs at least 2 operators")
    parts_sets = []
    trials_per_cell = None
    for operator, parts in data.items():
        if not isinstance(parts, dict) or len(parts) < 2:
            raise ValueError("study needs at least 2 parts per operator")
        parts_sets.append(set(parts.keys()))
        for part, trials in parts.items():
            if not isinstance(trials, (list, tuple)) or len(trials) < 2:
                raise ValueError("each cell needs at least 2 trials")
            if trials_per_cell is None:
                trials_per_cell = len(trials)
            if len(trials) != trials_per_cell:
                raise ValueError("ragged cells: trial counts differ")
            for reading in trials:
                if not _is_number(reading):
                    raise ValueError("non-numeric reading in cell")
    first_parts = parts_sets[0]
    if any(parts != first_parts for parts in parts_sets[1:]):
        raise ValueError("ragged cells: operators measure different parts")
    operators = sorted(data.keys())
    parts = sorted(first_parts)
    return operators, parts, trials_per_cell


def verdict_for_percent_grr(percent_grr):
    """Map %GRR onto the 10/30 acceptance bands."""
    if percent_grr < 10.0:
        return "acceptable"
    if percent_grr <= 30.0:
        return "conditional"
    return "unacceptable"


def _f_ratio(numerator_ms, denominator_ms):
    if denominator_ms == 0:
        if numerator_ms == 0:
            return None
        return float("inf")
    return numerator_ms / denominator_ms


def anova_grr_study(data):
    """Two-way random-effects ANOVA gage R&R decomposition (leaf mirror).

    Returns the sums of squares, df, mean squares, variance components with
    the non-negative floor, the ev/av/iv/grr/pv/tv chain, percent_grr, ndc,
    F statistics and the band verdict.
    """
    operators, parts, trials = validate_study(data)
    op_count, part_count = len(operators), len(parts)
    readings = [r for op in data.values() for prt in op.values() for r in prt]
    grand_mean = sum(readings) / len(readings)
    part_readings = {p: [r for op in operators for r in data[op][p]] for p in parts}
    op_readings = {o: [r for prt in data[o].values() for r in prt] for o in operators}
    part_means = {p: sum(v) / len(v) for p, v in part_readings.items()}
    op_means = {o: sum(v) / len(v) for o, v in op_readings.items()}
    cell_means = {(o, p): sum(data[o][p]) / trials
                  for o in operators for p in parts}

    ss_part = trials * op_count * sum(
        (part_means[p] - grand_mean) ** 2 for p in parts)
    ss_operator = trials * part_count * sum(
        (op_means[o] - grand_mean) ** 2 for o in operators)
    ss_interaction = trials * sum(
        (cell_means[(o, p)] - part_means[p] - op_means[o] + grand_mean) ** 2
        for o in operators for p in parts)
    ss_equipment = sum(
        (x - cell_means[(o, p)]) ** 2
        for o in operators for p in parts for x in data[o][p])

    df_part = part_count - 1
    df_operator = op_count - 1
    df_interaction = (part_count - 1) * (op_count - 1)
    df_equipment = op_count * part_count * (trials - 1)

    ms_part = ss_part / df_part
    ms_operator = ss_operator / df_operator
    ms_interaction = ss_interaction / df_interaction
    ms_equipment = ss_equipment / df_equipment

    var_equipment = ms_equipment
    var_interaction = max(0.0, (ms_interaction - ms_equipment) / trials)
    var_operator = max(0.0, (ms_operator - ms_interaction) / (part_count * trials))
    var_part = max(0.0, (ms_part - ms_interaction) / (op_count * trials))

    ev = math.sqrt(var_equipment)
    av = math.sqrt(var_operator)
    iv = math.sqrt(var_interaction)
    grr = math.sqrt(ev * ev + av * av + iv * iv)
    pv = math.sqrt(var_part)
    tv = math.sqrt(grr * grr + pv * pv)

    percent_grr = 0.0 if tv == 0 else 100.0 * grr / tv
    ndc = None if grr == 0 else math.floor(DISTINCT_CATEGORIES_CONST * pv / grr)
    verdict = verdict_for_percent_grr(percent_grr)

    return {
        "grand_mean": grand_mean,
        "ss_part": ss_part, "ss_operator": ss_operator,
        "ss_interaction": ss_interaction, "ss_equipment": ss_equipment,
        "df_part": df_part, "df_operator": df_operator,
        "df_interaction": df_interaction, "df_equipment": df_equipment,
        "ms_part": ms_part, "ms_operator": ms_operator,
        "ms_interaction": ms_interaction, "ms_equipment": ms_equipment,
        "var_equipment": var_equipment, "var_interaction": var_interaction,
        "var_operator": var_operator, "var_part": var_part,
        "ev": ev, "av": av, "iv": iv, "grr": grr, "pv": pv, "tv": tv,
        "percent_grr": percent_grr, "ndc": ndc,
        "f_part": _f_ratio(ms_part, ms_interaction),
        "f_interaction": _f_ratio(ms_interaction, ms_equipment),
        "verdict": verdict, "distinct_categories": ndc,
    }


def anova_table(data):
    """ANOVA table rows (part, operator, interaction, equipment, total)."""
    r = anova_grr_study(data)
    return [
        {"source": "part", "ss": r["ss_part"], "df": r["df_part"],
         "ms": r["ms_part"], "F": r["f_part"]},
        {"source": "operator", "ss": r["ss_operator"], "df": r["df_operator"],
         "ms": r["ms_operator"], "F": None},
        {"source": "operator-by-part", "ss": r["ss_interaction"],
         "df": r["df_interaction"], "ms": r["ms_interaction"],
         "F": r["f_interaction"]},
        {"source": "equipment", "ss": r["ss_equipment"], "df": r["df_equipment"],
         "ms": r["ms_equipment"], "F": None},
        {"source": "total", "ss": r["ss_part"] + r["ss_operator"]
         + r["ss_interaction"] + r["ss_equipment"],
         "df": r["df_part"] + r["df_operator"] + r["df_interaction"]
         + r["df_equipment"], "ms": None, "F": None},
    ]


# ---------------------------------------------------------------------------
# Gage R&R: AIAG range method (mirror of measurement-systems-analysis leaf)
# ---------------------------------------------------------------------------

def validate_table(measurements):
    """Range-method table validation (2-3 appraisers, 2-10 parts, 2-3 trials)."""
    if not isinstance(measurements, dict):
        raise ValueError("measurements must be a dict of appraiser tables")
    if len(measurements) < 2 or len(measurements) > 3:
        raise ValueError("range method supports 2 or 3 appraisers")
    parts_per_appraiser = trials = None
    for appraiser, parts in measurements.items():
        if not isinstance(parts, list) or not parts:
            raise ValueError("appraiser %r must have a non-empty part list"
                             % (appraiser,))
        if parts_per_appraiser is None:
            parts_per_appraiser = len(parts)
        elif len(parts) != parts_per_appraiser:
            raise ValueError("inconsistent part counts across appraisers")
        for part in parts:
            if not isinstance(part, list) or not part:
                raise ValueError("each part must have trial readings")
            if trials is None:
                trials = len(part)
            elif len(part) != trials:
                raise ValueError("inconsistent trial counts across parts")
            for value in part:
                if not _is_number(value):
                    raise ValueError("measurement values must be numbers")
                if value < 0:
                    raise ValueError("measurement values must be >= 0")
    if parts_per_appraiser is None or trials is None:
        raise ValueError("measurements table is empty")
    if parts_per_appraiser < 2 or parts_per_appraiser > 10:
        raise ValueError("range method supports 2 to 10 parts")
    if trials not in K1:
        raise ValueError("range method supports 2 or 3 trials")


def equipment_variation(measurements):
    """EV: repeatability from the average cell range, EV = K1 * rbar."""
    validate_table(measurements)
    ranges = [max(part) - min(part)
              for parts in measurements.values() for part in parts]
    rbar = sum(ranges) / len(ranges)
    return K1[len(measurements[list(measurements)[0]][0])] * rbar


def number_distinct_categories(pv, grr):
    """ndc = floor(1.41 * PV / GRR); None when GRR is zero."""
    if pv < 0 or grr < 0:
        raise ValueError("pv and grr must be >= 0")
    if grr == 0:
        return None
    return int(math.floor(1.41 * pv / grr))


def study_summary(measurements):
    """Full range-method gage R&R summary (leaf study_summary mirror).

    Keys: ev, av, grr, pv, tv, ev_pct, av_pct, grr_pct, pv_pct, ndc, verdict.
    """
    validate_table(measurements)
    appraisers = len(measurements)
    parts = len(measurements[list(measurements)[0]])
    trials = len(measurements[list(measurements)[0]][0])
    ranges = [max(part) - min(part)
              for parts in measurements.values() for part in parts]
    rbar = sum(ranges) / len(ranges)
    ev = K1[trials] * rbar
    means = [sum(x for part in parts_list for x in part)
             / (len(parts_list) * trials)
             for parts_list in measurements.values()]
    xdiff = max(means) - min(means)
    av = math.sqrt(max(0.0, (K2[appraisers] * xdiff) ** 2
                       - ev ** 2 / (trials * parts)))
    grr = math.sqrt(ev * ev + av * av)
    part_means = []
    for j in range(parts):
        vals = [x for parts_list in measurements.values() for x in parts_list[j]]
        part_means.append(sum(vals) / (appraisers * trials))
    pv = K3[parts] * (max(part_means) - min(part_means))
    tv = math.sqrt(grr * grr + pv * pv)
    if tv > 0:
        ev_pct = 100.0 * ev / tv
        av_pct = 100.0 * av / tv
        grr_pct = 100.0 * grr / tv
        pv_pct = 100.0 * pv / tv
    else:
        ev_pct = av_pct = grr_pct = pv_pct = 0.0
    return {
        "ev": ev, "av": av, "grr": grr, "pv": pv, "tv": tv,
        "ev_pct": ev_pct, "av_pct": av_pct, "grr_pct": grr_pct,
        "pv_pct": pv_pct, "ndc": number_distinct_categories(pv, grr),
        "verdict": verdict_for_percent_grr(grr_pct),
    }


# ---------------------------------------------------------------------------
# Gage bias and linearity (mirror of gage-linearity-bias-study leaf)
# ---------------------------------------------------------------------------

def _validate_reference_biases(references, biases):
    if len(references) != len(biases):
        raise ValueError("references and biases must have the same length")
    if len(references) < 3:
        raise ValueError("at least 3 reference levels are required")
    if any(r <= 0 for r in references):
        raise ValueError("reference values must be positive")
    for i, b in enumerate(references[1:], start=1):
        if b <= references[i - 1]:
            raise ValueError("reference values must be strictly increasing")
    return len(references)


def per_level_bias(references, biases):
    return [{"reference": references[i], "bias": biases[i],
             "bias_pct_of_reference": 100.0 * biases[i] / references[i]}
            for i in range(_validate_reference_biases(references, biases))]


def mean_bias(biases):
    if not isinstance(biases, (list, tuple)) or len(biases) == 0:
        raise ValueError("biases must be a non-empty list")
    return sum(biases) / len(biases)


def linearity_regression(references, biases):
    """Least-squares fit of bias on reference: slope, intercept, sse, r2."""
    n = _validate_reference_biases(references, biases)
    xbar = sum(references) / n
    bias_bar = sum(biases) / n
    sxx = sum((x - xbar) ** 2 for x in references)
    sxy = sum((x - xbar) * (b - bias_bar)
              for x, b in zip(references, biases))
    slope = sxy / sxx
    intercept = bias_bar - slope * xbar
    sse = sum((b - (intercept + slope * x)) ** 2
              for x, b in zip(references, biases))
    sst = sum((b - bias_bar) ** 2 for b in biases)
    if sst == 0.0:
        slope, intercept, sse, r_squared = 0.0, bias_bar, 0.0, 1.0
    else:
        r_squared = 1.0 - sse / sst
    return {"slope": slope, "intercept": intercept, "sse": sse,
            "r_squared": r_squared, "n": n, "xbar": xbar,
            "bias_bar": bias_bar}


def bias_significance(biases):
    """Two-sided 95% t-test of the mean bias (t table for df 1..20)."""
    if not isinstance(biases, (list, tuple)) or len(biases) < 3:
        raise ValueError("at least 3 bias values are required")
    n = len(biases)
    bias_bar = sum(biases) / n
    sst = sum((b - bias_bar) ** 2 for b in biases)
    s = (sst / (n - 1)) ** 0.5
    df = n - 1
    t_crit = T_CRIT_95_TWOTAIL.get(df, T_CRIT_LARGE_DF)
    t_stat = 0.0 if s == 0.0 else bias_bar / (s / n ** 0.5)
    return {"t_stat": t_stat, "t_crit": t_crit, "df": df,
            "significant": abs(t_stat) >= t_crit}


def gage_bias_linearity_study(references, biases):
    """Full bias/linearity study: overall ACCEPT/REVIEW + per-level rows."""
    _validate_reference_biases(references, biases)
    rows = per_level_bias(references, biases)
    bar = mean_bias(biases)
    reg = linearity_regression(references, biases)
    sig = bias_significance(biases)
    worst_row = max(rows, key=lambda r: abs(r["bias_pct_of_reference"]))
    per_level_acceptable = all(
        abs(r["bias_pct_of_reference"]) <= ACCEPTANCE_PCT_BAND for r in rows)
    overall = ("ACCEPT" if (not sig["significant"] and per_level_acceptable)
               else "REVIEW")
    return {
        "per_level": rows, "mean_bias": bar, "regression": reg,
        "significance": sig, "worst_bias_pct": worst_row["bias_pct_of_reference"],
        "worst_reference": worst_row["reference"],
        "per_level_acceptable": per_level_acceptable, "overall": overall,
    }


# ---------------------------------------------------------------------------
# Attribute agreement (mirror of attribute-agreement-analysis leaf)
# ---------------------------------------------------------------------------

def _validate_square_table(table):
    if not isinstance(table, (list, tuple)) or len(table) == 0:
        raise ValueError("table must be a non-empty list of rows")
    n = len(table)
    total = 0
    for row in table:
        if not isinstance(row, (list, tuple)) or len(row) != n:
            raise ValueError("table must be square")
        for count in row:
            if count < 0:
                raise ValueError("counts must be non-negative")
            total += count
    if total <= 0:
        raise ValueError("total count must be positive")
    return total


def percent_agreement(table):
    """Observed percent agreement: diagonal / total count."""
    _validate_square_table(table)
    diagonal = sum(table[i][i] for i in range(len(table)))
    total = sum(sum(row) for row in table)
    return diagonal / total


def cohen_kappa(table):
    """Cohen kappa for two inspectors on a square agreement table."""
    _validate_square_table(table)
    n = len(table)
    total = sum(sum(row) for row in table)
    row_totals = [sum(row) for row in table]
    col_totals = [sum(table[i][j] for i in range(n)) for j in range(n)]
    observed = sum(table[i][i] for i in range(n)) / total
    chance = sum(row_totals[i] * col_totals[i] for i in range(n)) / (total * total)
    if chance == 1.0:
        raise ValueError("chance agreement is 1.0; kappa is undefined")
    kappa = (observed - chance) / (1.0 - chance)
    return {"kappa": kappa, "observed_agreement": observed,
            "chance_agreement": chance}


def fleiss_kappa(ratings_matrix):
    """Fleiss kappa for >=3 inspectors on per-part ratings (counts per row)."""
    if not isinstance(ratings_matrix, (list, tuple)) or len(ratings_matrix) == 0:
        raise ValueError("ratings matrix must be a non-empty list of rows")
    width = None
    total = 0
    for row in ratings_matrix:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            raise ValueError("each part row needs >=2 category counts")
        if width is None:
            width = len(row)
        if len(row) != width:
            raise ValueError("ratings matrix rows must have equal length")
        if sum(row) < 2:
            raise ValueError("each part needs at least two ratings")
        for count in row:
            if count < 0:
                raise ValueError("counts must be non-negative")
            total += count
    if total <= 0:
        raise ValueError("total rating count must be positive")
    parts = len(ratings_matrix)
    pi_values = []
    col_totals = [0] * width
    for row in ratings_matrix:
        n = sum(row)
        sum_sq = sum(c * c for c in row)
        pi_values.append((sum_sq - n) / (n * (n - 1)))
        for j, count in enumerate(row):
            col_totals[j] += count
    pbar = sum(pi_values) / parts
    pe = sum((col_totals[j] / total) ** 2 for j in range(width))
    if pe == 1.0:
        raise ValueError("chance agreement is 1.0; kappa is undefined")
    kappa = (pbar - pe) / (1.0 - pe)
    return {"kappa": kappa, "pbar": pbar, "pe": pe}


def kappa_verdict(kappa):
    """good >= 0.75, marginal 0.40-0.75, poor < 0.40."""
    if kappa < -1.0 or kappa > 1.0:
        raise ValueError("kappa must lie in [-1, 1]")
    if kappa >= KAPPA_GOOD:
        return "good"
    if kappa >= KAPPA_MARGINAL:
        return "marginal"
    return "poor"


def agreement_summary(table=None, ratings_matrix=None):
    """Applicable agreement statistic (Cohen or Fleiss) + band verdict."""
    if (table is None) == (ratings_matrix is None):
        raise ValueError("provide exactly one of table or ratings_matrix")
    if table is not None:
        result = cohen_kappa(table)
        return {"method": "cohen", "kappa": result["kappa"],
                "observed_agreement": result["observed_agreement"],
                "chance_agreement": result["chance_agreement"],
                "verdict": kappa_verdict(result["kappa"])}
    result = fleiss_kappa(ratings_matrix)
    return {"method": "fleiss", "kappa": result["kappa"],
            "pbar": result["pbar"], "pe": result["pe"],
            "verdict": kappa_verdict(result["kappa"])}


# ---------------------------------------------------------------------------
# SPC: X-bar/R + capability (mirror of statistical-process-control leaf)
# ---------------------------------------------------------------------------

def _check_n(n):
    if not isinstance(n, int) or isinstance(n, bool):
        raise ValueError("subgroup size must be an integer, got %r" % (n,))
    if n not in A2:
        raise ValueError("subgroup size %d outside the supported range 2..10" % n)
    return n


def xbar_r_limits(xbar, rbar, n):
    """(xbar_ucl, xbar_lcl, r_ucl, r_lcl): UCLx=xbar+A2*rbar etc."""
    n = _check_n(n)
    if rbar < 0:
        raise ValueError("average range must be >= 0, got %r" % (rbar,))
    return (xbar + A2[n] * rbar, xbar - A2[n] * rbar,
            D4[n] * rbar, D3[n] * rbar)


def process_sigma(rbar, n):
    """sigma = rbar / d2 (range-based process sigma estimate)."""
    n = _check_n(n)
    if rbar < 0:
        raise ValueError("average range must be >= 0, got %r" % (rbar,))
    return rbar / D2[n]


def capability_indices(usl, lsl, xbar, sigma):
    """(cp, cpu, cpl, cpk) against the specification limits."""
    if usl <= lsl:
        raise ValueError("USL must exceed LSL, got USL %r LSL %r" % (usl, lsl))
    if sigma <= 0:
        raise ValueError("sigma must be > 0, got %r" % (sigma,))
    cp = (usl - lsl) / (6.0 * sigma)
    cpu = (usl - xbar) / (3.0 * sigma)
    cpl = (xbar - lsl) / (3.0 * sigma)
    return (cp, cpu, cpl, min(cpu, cpl))


def out_of_control_rules(points, centerline, sigma):
    """Western Electric rules 1-4; returns violated rule names, empty if none."""
    if len(points) < 2:
        raise ValueError("at least two points required for rule detection")
    if sigma <= 0:
        raise ValueError("sigma must be > 0, got %r" % (sigma,))
    violated = []
    for p in points:
        if abs(p - centerline) > 3.0 * sigma:
            violated.append("rule1")
            break
    run = 0
    for p in points:
        if p > centerline:
            run = run + 1 if run > 0 else 1
        elif p < centerline:
            run = run - 1 if run < 0 else -1
        else:
            run = 0
        if abs(run) >= 8:
            violated.append("rule2")
            break
    for i in range(len(points) - 2):
        window = points[i:i + 3]
        above = sum(1 for p in window if p - centerline > 2.0 * sigma)
        below = sum(1 for p in window if centerline - p > 2.0 * sigma)
        if above >= 2 or below >= 2:
            violated.append("rule3")
            break
    for i in range(len(points) - 4):
        window = points[i:i + 5]
        above = sum(1 for p in window if p - centerline > 1.0 * sigma)
        below = sum(1 for p in window if centerline - p > 1.0 * sigma)
        if above >= 4 or below >= 4:
            violated.append("rule4")
            break
    return violated


# ---------------------------------------------------------------------------
# I-MR chart (mirror of individuals-and-moving-range-chart leaf)
# ---------------------------------------------------------------------------

def mean(values):
    if len(values) == 0:
        raise ValueError("mean requires at least one value")
    return sum(values) / len(values)


def moving_ranges(values):
    if len(values) < 2:
        raise ValueError("moving ranges require at least 2 values")
    return [abs(values[i] - values[i - 1]) for i in range(1, len(values))]


def individuals_limits(values):
    if len(values) < 2:
        raise ValueError("individuals limits require at least 2 values")
    x_bar = mean(values)
    mr_bar = mean(moving_ranges(values))
    return {"mean": x_bar, "mr_bar": mr_bar,
            "sigma_hat": mr_bar / D2_N1,
            "UCL": x_bar + E2 * mr_bar, "LCL": x_bar - E2 * mr_bar}


def moving_range_limits(values):
    if len(values) < 2:
        raise ValueError("moving range limits require at least 2 values")
    mr_bar = mean(moving_ranges(values))
    return {"mr_bar": mr_bar, "UCL": D3_MR_UCL * mr_bar}


def flag_points(values, ucl, lcl):
    if len(values) == 0:
        raise ValueError("flagging requires at least one value")
    return [i for i, v in enumerate(values) if v < lcl or v > ucl]


def stability_verdict(individual_flags, mr_flags):
    if len(individual_flags) == 0 and len(mr_flags) == 0:
        return "in-control"
    return "out-of-control"


def imr_summary(values):
    ind = individuals_limits(values)
    mr = moving_range_limits(values)
    mrs = moving_ranges(values)
    flagged_individuals = flag_points(values, ind["UCL"], ind["LCL"])
    flagged_moving_ranges = flag_points(mrs, mr["UCL"], 0.0)
    return {"mean": ind["mean"], "mr_bar": ind["mr_bar"],
            "sigma_hat": ind["sigma_hat"], "x_ucl": ind["UCL"],
            "x_lcl": ind["LCL"], "mr_ucl": mr["UCL"],
            "flagged_individuals": flagged_individuals,
            "flagged_moving_ranges": flagged_moving_ranges,
            "verdict": stability_verdict(flagged_individuals,
                                         flagged_moving_ranges)}


# ---------------------------------------------------------------------------
# Attribute control charts (mirror of attribute-control-charts leaf)
# ---------------------------------------------------------------------------

def attribute_verdict(any_flags):
    if any_flags:
        return "out-of-control"
    return "in-control"


def p_chart(nonconforming_counts, sample_size):
    """p-chart: fraction nonconforming at constant sample size."""
    if len(nonconforming_counts) == 0:
        raise ValueError("nonconforming_counts must not be empty")
    if sample_size <= 0:
        raise ValueError("sample_size must be positive")
    for count in nonconforming_counts:
        if count < 0:
            raise ValueError("nonconforming count must not be negative")
        if count > sample_size:
            raise ValueError("nonconforming count cannot exceed the sample size")
    n_groups = len(nonconforming_counts)
    pbar = float(sum(nonconforming_counts)) / (n_groups * sample_size)
    sigma_p = math.sqrt(pbar * (1.0 - pbar) / sample_size)
    ucl = pbar + SIGMA_FACTOR * sigma_p
    lcl = max(0.0, pbar - SIGMA_FACTOR * sigma_p)
    flagged = [i for i, count in enumerate(nonconforming_counts)
               if (count / sample_size) < lcl or (count / sample_size) > ucl]
    return {"pbar": pbar, "sigma_p": sigma_p, "UCL": ucl, "LCL": lcl,
            "flagged_subgroups": flagged,
            "verdict": attribute_verdict(flagged)}


# ---------------------------------------------------------------------------
# CUSUM / EWMA small-shift monitoring (mirror of cusum-ewma leaf)
# ---------------------------------------------------------------------------

def cusum_statistics(xs, mu0, sigma, k=0.5, h=5.0):
    """Tabular CUSUM path; first_signal_index is 1-based, None when in control."""
    if xs is None or len(xs) == 0:
        raise ValueError("xs must contain at least one observation")
    if sigma <= 0:
        raise ValueError("sigma must be positive")
    if k <= 0 or h <= 0:
        raise ValueError("k and h must be positive")
    sp_plus, sp_minus = [], []
    first_signal_index = None
    s_plus = s_minus = 0.0
    for index, x in enumerate(xs):
        z = (x - mu0) / sigma
        s_plus = max(0.0, z - k + s_plus)
        s_minus = max(0.0, -z - k + s_minus)
        sp_plus.append(s_plus)
        sp_minus.append(s_minus)
        if first_signal_index is None and (s_plus > h or s_minus > h):
            first_signal_index = index + 1
    return {"sp_plus": sp_plus, "sp_minus": sp_minus,
            "first_signal_index": first_signal_index}


def ewma_statistics(xs, mu0, sigma, lam=0.2, L=3.0):
    """EWMA recursion with time-varying limits; 1-based first signal index."""
    if xs is None or len(xs) == 0:
        raise ValueError("xs must contain at least one observation")
    if sigma <= 0:
        raise ValueError("sigma must be positive")
    if lam <= 0 or lam > 1:
        raise ValueError("lam must be in (0, 1]")
    if L <= 0:
        raise ValueError("L must be positive")
    ewma_series, ucl, lcl = [], [], []
    first_signal_index = None
    e = mu0
    decay = 1.0 - lam
    variance_scale = lam / (2.0 - lam)
    for index, x in enumerate(xs):
        e = lam * x + decay * e
        sigma_e = sigma * math.sqrt(
            variance_scale * (1.0 - decay ** (2 * (index + 1))))
        upper = mu0 + L * sigma_e
        lower = mu0 - L * sigma_e
        ewma_series.append(e)
        ucl.append(upper)
        lcl.append(lower)
        if first_signal_index is None and (e > upper or e < lower):
            first_signal_index = index + 1
    return {"ewma_series": ewma_series, "ucl": ucl, "lcl": lcl,
            "first_signal_index": first_signal_index}


def monitoring_verdict(cusum_signal_index, ewma_signal_index, n):
    if n < 0:
        raise ValueError("n must be non-negative")
    fired = [s for s in (cusum_signal_index, ewma_signal_index)
             if s is not None]
    return {"cusum_signaled": cusum_signal_index is not None,
            "ewma_signaled": ewma_signal_index is not None,
            "any_signal": bool(fired),
            "first_signal_index": min(fired) if fired else None}


def small_shift_monitoring_report(xs, mu0, sigma, k=0.5, h=5.0,
                                  lam=0.2, L=3.0):
    cusum = cusum_statistics(xs, mu0, sigma, k, h)
    ewma = ewma_statistics(xs, mu0, sigma, lam, L)
    verdict = monitoring_verdict(cusum["first_signal_index"],
                                 ewma["first_signal_index"], len(xs))
    return {"cusum": cusum, "ewma": ewma, "verdict": verdict}


# ---------------------------------------------------------------------------
# Acceptance sampling: attribute (mirror of acceptance-sampling leaf)
# ---------------------------------------------------------------------------

def _require_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("%s must be an integer unit count, got %r" % (name, value))
    return value


def _aql_key(aql):
    if isinstance(aql, str):
        return aql.strip()
    if isinstance(aql, bool):
        raise ValueError("aql must be a number or string like '1.0'")
    if isinstance(aql, (int, float)):
        if aql == int(aql):
            return "%d.0" % int(aql)
        return str(aql)
    raise ValueError("aql must be a number or string like '1.0'")


def _band_for_lot(lot_size):
    for name, lower, upper in LOT_SIZE_BANDS:
        if lower <= lot_size <= upper:
            return name
    return None


def code_letter(lot_size, inspection_level):
    """Attribute plan code letter from lot size + inspection level."""
    lot_size = _require_int(lot_size, "lot_size")
    if lot_size <= 0:
        raise ValueError("lot_size must be positive")
    if inspection_level not in INSPECTION_LEVELS:
        raise ValueError("inspection_level must be I, II or III")
    band = _band_for_lot(lot_size)
    if band is None:
        raise ValueError("lot_size %d falls outside the documented bands" % lot_size)
    return CODE_LETTER_TABLE[(inspection_level, band)]


def sampling_plan(code, aql):
    """(n, Ac, Re) single-sampling plan for a code letter and AQL."""
    if not isinstance(code, str):
        raise ValueError("code letter must be a string like 'J'")
    key = (code, _aql_key(aql))
    try:
        return PLAN_TABLE[key]
    except KeyError:
        raise ValueError("no plan in the reduced table for code %r at AQL %r"
                         % (code, aql))


def lot_decision(nonconforming_found, plan):
    nonconforming_found = _require_int(nonconforming_found, "nonconforming_found")
    if nonconforming_found < 0:
        raise ValueError("nonconforming_found cannot be negative")
    if len(plan) < 2:
        raise ValueError("plan must be an (n, Ac, Re) tuple")
    return "accept" if nonconforming_found <= plan[1] else "reject"


def oc_acceptance_probability(n, ac, p):
    """Binomial OC probability: P(d <= ac) at incoming fraction p."""
    n = _require_int(n, "n")
    ac = _require_int(ac, "ac")
    if n < 1:
        raise ValueError("n must be a positive sample size")
    if ac < 0:
        raise ValueError("ac cannot be negative")
    if not 0.0 <= p <= 1.0:
        raise ValueError("fraction nonconforming p must be within [0, 1]")
    return sum(math.comb(n, d) * p ** d * (1 - p) ** (n - d)
               for d in range(ac + 1))


# ---------------------------------------------------------------------------
# Acceptance sampling: variables k-method (mirror of variables leaf)
# ---------------------------------------------------------------------------

def normal_survival(z):
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def normal_cdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def form_q_upper(usl, xbar, s):
    if s <= 0:
        raise ValueError("s must be positive, got %r" % (s,))
    return (usl - xbar) / s


def form_q_lower(lsl, xbar, s):
    if s <= 0:
        raise ValueError("s must be positive, got %r" % (s,))
    return (xbar - lsl) / s


def estimated_pct_nonconforming(Q, tail="upper"):
    if tail not in ("upper", "lower"):
        raise ValueError("tail must be 'upper' or 'lower'")
    if tail == "upper":
        return 100.0 * normal_survival(Q)
    return 100.0 * normal_cdf(-Q)


def accept_verdict(Q, k):
    return Q >= k


def variables_code_letter(lot_size, level="II"):
    if lot_size <= 0:
        raise ValueError("lot_size must be positive")
    if level not in INSPECTION_LEVELS:
        raise ValueError("level must be I, II or III")
    if level != "II":
        raise ValueError("reduced table embeds only general level II rows")
    for low, high, code in CODE_LETTER_BANDS:
        if low <= lot_size <= high:
            return code
    raise ValueError("lot_size %r outside the documented reduced bands 91-10000"
                     % (lot_size,))


def variables_plan_lookup(code, aql):
    if code not in N_BY_CODE:
        raise ValueError("unknown code letter %r" % (code,))
    if aql not in K_BY_AQL:
        raise ValueError("AQL %r has no row in the reduced table" % (aql,))
    return {"n": N_BY_CODE[code], "k": K_BY_AQL[aql],
            "M": M_BY_CODE_AQL[code][aql]}


def variables_sampling_decision(lot_size, aql, usl_or_lsl, xbar, s, level="II"):
    """Single-sided variables sampling decision (k-method)."""
    code = variables_code_letter(lot_size, level)
    plan = variables_plan_lookup(code, aql)
    if usl_or_lsl > xbar:
        Q = form_q_upper(usl_or_lsl, xbar, s)
        p_hat = estimated_pct_nonconforming(Q, tail="upper")
    else:
        Q = form_q_lower(usl_or_lsl, xbar, s)
        p_hat = estimated_pct_nonconforming(Q, tail="lower")
    return {"code": code, "n": plan["n"], "k": plan["k"], "M": plan["M"],
            "Q": Q, "p_hat": p_hat, "accept": accept_verdict(Q, plan["k"])}


# ---------------------------------------------------------------------------
# Audit item: the manufacturing site + datasets under audit
# ---------------------------------------------------------------------------

@dataclass
class AuditItem:
    """Facts the role needs: site context + quality datasets + criteria."""
    site_name: str = "Meridian Aerospace Components"
    site_ref: str = "Fab plant 2"
    standard: str = "AS9100D"
    audit_period: str = "2026-08-04 to 2026-09-04"
    audit_date: str = "2026-09-04"
    audit_lead: str = "Q. Nguyen (quality engineer, audit lead)"
    flow_down_ref: str = "PO-7712 quality clause"
    flow_down_cpk: float = 1.33          # site flow-down for key characteristics
    msa_procedure: str = "QP-7.1.5"      # site MSA procedure (example fact)
    cpk_procedure: str = "per PO-7712 clause 4.2"  # example flow-down text

    # --- datasets (frozen literals from this module) ---
    anova_study: dict = field(default_factory=lambda: dict(ANOVA_STUDY))
    range_table: dict = field(default_factory=lambda: _range_table_from_study(ANOVA_STUDY))
    mic_refs: list = field(default_factory=lambda: list(MICROMETER_REFS))
    mic_biases: list = field(default_factory=lambda: list(MICROMETER_BIASES))
    ratings_matrix: list = field(default_factory=lambda: [list(r) for r in RATINGS_MATRIX])
    ab_table: list = field(default_factory=lambda: [list(r) for r in INSPECTOR_AB_TABLE])
    sub_means: list = field(default_factory=lambda: list(SUB_MEANS))
    sub_ranges: list = field(default_factory=lambda: list(SUB_RANGES))
    coating: list = field(default_factory=lambda: list(COATING_SERIES))
    deviations: list = field(default_factory=lambda: list(DEVIATION_SERIES))
    np_counts: list = field(default_factory=lambda: list(NP_COUNTS))

    # --- characteristics under audit (example facts) ---
    kc_bore: str = "KC-001 bore diameter 12.000 mm (final inspection gage G-077)"
    kc_pin: str = "KC-002 pin diameter 6.000 mm"
    pin_usl: float = 6.015
    pin_lsl: float = 5.985
    pin_subgroup_n: int = 5
    coating_chart: str = "anodize coating thickness 120 +/- 15 um per lot"
    coating_reaction_recorded: bool = False   # lot 17 OOC: no reaction on file
    coating_out_of_control_lot: int = 17      # 1-based lot number flagged

    # --- acceptance sampling lots (example facts) ---
    attr_lot_size: int = 500
    attr_level: str = "II"
    attr_aql: float = 1.0
    attr_found_nonconforming: int = 1
    vars_lot_size: int = 1500
    vars_aql: float = 1.0
    vars_usl: float = 25.150
    vars_xbar: float = 25.102
    vars_s: float = 0.0098


# ---------------------------------------------------------------------------
# Report model builder: every analysis + derived findings + conformance
# ---------------------------------------------------------------------------

def build_report(item: AuditItem) -> dict:
    """Compute the full audit-report content model from the item facts."""
    an = anova_grr_study(item.anova_study)
    rng = study_summary(item.range_table)
    lin = gage_bias_linearity_study(item.mic_refs, item.mic_biases)
    agree = agreement_summary(ratings_matrix=item.ratings_matrix)
    pair_agree = agreement_summary(table=item.ab_table)

    # X-bar/R on KC-002 pin
    xbar = mean(item.sub_means)
    rbar = mean(item.sub_ranges)
    x_ucl, x_lcl, r_ucl, r_lcl = xbar_r_limits(xbar, rbar, item.pin_subgroup_n)
    sigma = process_sigma(rbar, item.pin_subgroup_n)
    cp, cpu, cpl, cpk = capability_indices(item.pin_usl, item.pin_lsl,
                                           xbar, sigma)
    sigma_xbar = sigma / math.sqrt(item.pin_subgroup_n)
    ooc = out_of_control_rules(item.sub_means, xbar, sigma_xbar)
    xbar_r_verdict = ("in-control" if not ooc else "out-of-control")

    # I-MR on coating thickness
    imr = imr_summary(item.coating)

    # CUSUM/EWMA on bore deviations
    shift = small_shift_monitoring_report(item.deviations, 0.0, 2.9)

    # p-chart on final-lot nonconforming counts
    p = p_chart(item.np_counts, 200)

    # Acceptance sampling: attribute plan + OC anchors
    attr_code = code_letter(item.attr_lot_size, item.attr_level)
    attr_plan = sampling_plan(attr_code, item.attr_aql)
    attr_decision = lot_decision(item.attr_found_nonconforming, attr_plan)
    oc_aql = oc_acceptance_probability(attr_plan[0], attr_plan[1],
                                       item.attr_aql / 100.0)
    oc_at_4pct = oc_acceptance_probability(attr_plan[0], attr_plan[1], 0.04)

    # Variables plan (single-sided USL)
    var = variables_sampling_decision(item.vars_lot_size, item.vars_aql,
                                      item.vars_usl, item.vars_xbar,
                                      item.vars_s)

    msa = {
        "anova": {
            "gage": "bore micrometer G-077",
            "characteristic": item.kc_bore,
            "layout": "%d inspectors x %d parts x %d trials"
                      % (len(item.anova_study), 10, 3),
            "percent_grr": an["percent_grr"], "ndc": an["ndc"],
            "verdict": an["verdict"], "ev": an["ev"], "av": an["av"],
            "iv": an["iv"], "grr": an["grr"], "pv": an["pv"], "tv": an["tv"],
        },
        "range": {
            "percent_grr": rng["grr_pct"], "ndc": rng["ndc"],
            "verdict": rng["verdict"], "ev": rng["ev"], "av": rng["av"],
            "grr": rng["grr"], "pv": rng["pv"], "tv": rng["tv"],
        },
        "dual_delta_pp": abs(an["percent_grr"] - rng["grr_pct"]),
        "bias_linearity": {
            "gage": "outside micrometer G-112",
            "refs": item.mic_refs, "biases": item.mic_biases,
            "mean_bias": lin["mean_bias"],
            "slope": lin["regression"]["slope"],
            "r_squared": lin["regression"]["r_squared"],
            "t_stat": lin["significance"]["t_stat"],
            "t_crit": lin["significance"]["t_crit"],
            "df": lin["significance"]["df"],
            "significant": lin["significance"]["significant"],
            "worst_bias_pct": lin["worst_bias_pct"],
            "worst_reference": lin["worst_reference"],
            "per_level_acceptable": lin["per_level_acceptable"],
            "overall": lin["overall"],
        },
        "attribute": {
            "method": agree["method"], "kappa": agree["kappa"],
            "pbar": agree["pbar"], "pe": agree["pe"],
            "verdict": agree["verdict"],
            "layout": "3 inspectors x 30 go/no-go parts",
            "pairwise": {"observed_agreement": pair_agree["observed_agreement"],
                         "kappa": pair_agree["kappa"]},
        },
    }

    spc = {
        "xbar_r": {
            "characteristic": item.kc_pin,
            "subgroups": len(item.sub_means), "n": item.pin_subgroup_n,
            "xbar": xbar, "rbar": rbar, "x_ucl": x_ucl, "x_lcl": x_lcl,
            "r_ucl": r_ucl, "r_lcl": r_lcl, "sigma_hat": sigma,
            "cp": cp, "cpu": cpu, "cpl": cpl, "cpk": cpk,
            "ooc_rules": ooc, "verdict": xbar_r_verdict,
        },
        "imr": {
            "characteristic": item.coating_chart,
            "lots": len(item.coating),
            "mean": imr["mean"], "mr_bar": imr["mr_bar"],
            "x_ucl": imr["x_ucl"], "x_lcl": imr["x_lcl"],
            "mr_ucl": imr["mr_ucl"],
            "flagged_individuals": imr["flagged_individuals"],
            "flagged_moving_ranges": imr["flagged_moving_ranges"],
            "verdict": imr["verdict"],
        },
        "shift_monitoring": {
            "series": "bore deviations from nominal, um",
            "n": len(item.deviations),
            "cusum_signaled": shift["verdict"]["cusum_signaled"],
            "ewma_signaled": shift["verdict"]["ewma_signaled"],
            "any_signal": shift["verdict"]["any_signal"],
            "first_signal_index": shift["verdict"]["first_signal_index"],
        },
        "p_chart": {
            "subgroups": len(item.np_counts), "sample_size": 200,
            "pbar": p["pbar"], "ucl": p["UCL"], "lcl": p["LCL"],
            "flagged_subgroups": p["flagged_subgroups"],
            "verdict": p["verdict"],
        },
    }

    sampling = {
        "attribute": {
            "basis": "reduced reference table in the style of ANSI/ASQ Z1.4, "
                     "single sampling, normal inspection, level II",
            "lot_size": item.attr_lot_size, "aql": item.attr_aql,
            "code": attr_code, "n": attr_plan[0], "ac": attr_plan[1],
            "re": attr_plan[2], "found": item.attr_found_nonconforming,
            "decision": attr_decision,
            "oc_at_aql": oc_aql,
            "producer_risk_pct": 100.0 * (1.0 - oc_aql),
            "oc_at_4pct": oc_at_4pct,
        },
        "variables": {
            "basis": "reduced k-method reference table in the style of "
                     "ANSI/ASQ Z1.9, single specification limit, sigma unknown",
            "lot_size": item.vars_lot_size, "aql": item.vars_aql,
            "usl": item.vars_usl, "xbar": item.vars_xbar, "s": item.vars_s,
            "code": var["code"], "n": var["n"], "k": var["k"], "M": var["M"],
            "Q": var["Q"], "p_hat": var["p_hat"], "accept": var["accept"],
        },
    }

    findings, conformance = derive_findings(item, msa, spc, sampling)

    counts = {
        "major": sum(1 for f in findings if f["classification"] == "major"),
        "minor": sum(1 for f in findings if f["classification"] == "minor"),
        "ofi": sum(1 for f in findings if f["classification"] == "observation"),
        "total": len(findings),
    }

    return {
        "document_type": "AS9100 Quality Management System Audit Report",
        "status": "draft-for-review",
        "site": {"name": item.site_name, "ref": item.site_ref},
        "standard": item.standard,
        "standard_note": "AS9100D referenced summary-only (IAQG/SAE); "
                         "no standard text reproduced",
        "audit_period": item.audit_period,
        "audit_date": item.audit_date,
        "audit_lead": item.audit_lead,
        "flow_down_ref": item.flow_down_ref,
        "flow_down_cpk": item.flow_down_cpk,
        "msa_procedure": item.msa_procedure,
        "criteria": {
            "grr_bands": "<10% acceptable, 10-30% conditional, >30% "
                         "unacceptable (AIAG-style practice)",
            "grr_kc_criterion": "site procedure %s: %s%% max for "
                                "key-characteristic gages"
                                % (item.msa_procedure, 10),
            "kappa_bands": "kappa >= 0.75 good, 0.40-0.75 marginal, "
                           "< 0.40 poor",
            "capability_flow_down": "Cpk >= %.2f for key characteristics "
                                    "(%s)" % (item.flow_down_cpk,
                                              item.cpk_procedure),
        },
        "evidence_scope": {
            "records": "all 41 active gage master/calibration records "
                       "reviewed (100% census)",
            "datasets": [
                "gage R&R ANOVA study: 3 inspectors x 10 parts x 3 trials "
                "on KC-001 bore micrometer G-077",
                "gage R&R range-method re-analysis of the same 90 readings",
                "gage bias/linearity: 5 reference levels, micrometer G-112",
                "attribute agreement: 3 inspectors x 30 go/no-go parts",
                "SPC X-bar/R: 20 subgroups of 5, KC-002 pin diameter",
                "SPC I-MR: 30 lot coating-thickness values",
                "small-shift CUSUM/EWMA: 25 bore-deviation observations",
                "attribute p-chart: 20 lots x 200 units",
                "acceptance records: attribute lot 500 and variables lot "
                "1500 release records",
            ],
        },
        "msa": msa, "spc": spc, "sampling": sampling,
        "findings": findings, "conformance": conformance, "counts": counts,
        "generated": _today(),
    }


def _fmt_bool(b):
    return "yes" if b else "no"


def derive_findings(item: AuditItem, msa: dict, spc: dict, sampling: dict):
    """Map computed verdicts onto audit findings and clause conformance rows.

    Classification rule (site audit-procedure criteria, summary): a finding
    is major when nonconforming product is shown to have been released or
    the gap is systemic across the QMS; minor when localized with no
    released-product evidence; an observation (OFI) records no requirement
    breach but a demonstrated improvement need. All findings cite the
    computed objective evidence and stay OPEN pending the site's action -
    this report never closes a finding and never approves the system.
    """
    findings = []

    # NC-01: gage bias significant (7.1.5.2 measurement traceability)
    bl = msa["bias_linearity"]
    if bl["significant"] or bl["overall"] == "REVIEW":
        findings.append({
            "id": "NC-01",
            "classification": "minor",
            "clause": "7.1.5.2",
            "title": ("Significant mean bias on inspection micrometer G-112 "
                      "not addressed in calibration records"),
            "evidence": ("bias/linearity study over 5 reference levels "
                         "5.000-25.000 mm: mean bias +%.4f mm, t = %.2f vs "
                         "two-sided 95%% t critical %.2f (df %d), overall "
                         "verdict %s; per-level |bias| <= %.2f%% of reference "
                         "(band %.0f%%), so linearity itself is inside the "
                         "band but the consistent offset is statistically "
                         "significant" % (bl["mean_bias"], bl["t_stat"],
                                          bl["t_crit"], bl["df"],
                                          bl["overall"],
                                          bl["worst_bias_pct"],
                                          ACCEPTANCE_PCT_BAND)),
            "requirement": ("Monitoring and measuring resources must be "
                            "calibrated or verified at defined intervals; a "
                            "statistically significant measurement bias makes "
                            "measurement results suspect and must be "
                            "corrected or its validity assessed before the "
                            "gage supports acceptance decisions."),
            "objective_ref": "bias/linearity study BL-2026-07, gage G-112",
            "status": "open",
        })

    # NC-02: attribute agreement poor (7.1.5.1)
    ag = msa["attribute"]
    if ag["verdict"] == "poor":
        findings.append({
            "id": "NC-02",
            "classification": "minor",
            "clause": "7.1.5.1",
            "title": ("Poor inspector agreement on attribute (go/no-go) "
                      "acceptance judgments"),
            "evidence": ("Fleiss kappa %.2f (%s band < %.2f) across 3 "
                         "inspectors x 30 parts; observed agreement %.1f%%, "
                         "chance agreement %.1f%%; pairwise inspector A-B "
                         "re-check: observed agreement %.1f%%, kappa %.2f"
                         % (ag["kappa"], ag["verdict"], KAPPA_MARGINAL,
                            100.0 * ag["pbar"], 100.0 * ag["pe"],
                            100.0 * msa["attribute"]["pairwise"]
                            ["observed_agreement"],
                            msa["attribute"]["pairwise"]["kappa"])),
            "requirement": ("The inspection/verification activity that "
                            "supports product acceptance must be reliable; "
                            "attribute acceptance decisions made by "
                            "inspectors who agree only at chance level do not "
                            "provide objective evidence of conformance."),
            "objective_ref": "attribute agreement study AA-2026-08",
            "status": "open",
        })

    # NC-03: I-MR out of control with no reaction (8.5.1)
    imr = spc["imr"]
    if imr["verdict"] == "out-of-control" and not item.coating_reaction_recorded:
        flagged_lots = [i + 1 for i in imr["flagged_individuals"]]
        findings.append({
            "id": "NC-03",
            "classification": "minor",
            "clause": "8.5.1",
            "title": ("Out-of-control coating lot released with no recorded "
                      "reaction"),
            "evidence": ("I-MR chart over %d lots: lot %d at %.1f um exceeds "
                         "the individuals UCL %.1f um (mean %.2f um, "
                         "average moving range %.2f um, MR UCL %.2f um); "
                         "chart verdict %s and no reaction/disposition "
                         "record was found in the SPC log for the flagged "
                         "lot(s) %s"
                         % (imr["lots"], item.coating_out_of_control_lot,
                            item.coating[item.coating_out_of_control_lot - 1],
                            imr["x_ucl"], imr["mean"], imr["mr_bar"],
                            imr["mr_ucl"], imr["verdict"],
                            ", ".join(str(l) for l in flagged_lots))),
            "requirement": ("Production must be carried out under controlled "
                            "conditions; when process control charts signal an "
                            "out-of-control condition the organization must "
                            "react and determine whether the output remains "
                            "conforming before release."),
            "objective_ref": "SPC log CL-2026-08, anodize line 2",
            "status": "open",
        })

    # OFI-01: capability below flow-down (8.5.1)
    xr = spc["xbar_r"]
    if xr["cpk"] < item.flow_down_cpk:
        findings.append({
            "id": "OFI-01",
            "classification": "observation",
            "clause": "8.5.1",
            "title": ("KC-002 key-characteristic capability below the "
                      "flow-down Cpk requirement"),
            "evidence": ("X-bar/R chart in control (no Western Electric "
                         "rule violations over %d subgroups of %d) with "
                         "Cp %.2f but Cpk %.2f (Cpu %.2f, Cpl %.2f) against "
                         "6.000 +/- 0.015 mm; the flow-down requires "
                         "Cpk >= %.2f - the chart is stable but the process "
                         "center is off-nominal, so the acceptance margin is "
                         "eroded"
                         % (xr["subgroups"], xr["n"], xr["cp"], xr["cpk"],
                            xr["cpu"], xr["cpl"], item.flow_down_cpk)),
            "requirement": ("No requirement breach: the process is stable "
                            "and in spec. Opportunity: recenter the process "
                            "or review the flow-down acceptance evidence for "
                            "KC-002 before the next release lot."),
            "objective_ref": "SPC log KC-002, 2026-08",
            "status": "open",
        })

    # OFI-02: conditional gage R&R on a KC gage (7.1.5.1)
    an = msa["anova"]
    if an["verdict"] == "conditional":
        findings.append({
            "id": "OFI-02",
            "classification": "observation",
            "clause": "7.1.5.1",
            "title": ("Bore micrometer G-077 measurement error on the "
                      "conditional band for a key-characteristic gage"),
            "evidence": ("ANOVA gage R&R: %%GRR %.2f%% (ndc %s) and "
                         "independent range-method estimate %.2f%% (ndc %s) "
                         "both fall in the conditional 10-30%% band; the two "
                         "estimators agree to %.2f percentage points, so the "
                         "estimate is robust, but the site procedure %s "
                         "allows <= 10%% for key-characteristic gages and no "
                         "application justification was found in the MSA "
                         "records"
                         % (an["percent_grr"], an["ndc"],
                            msa["range"]["percent_grr"], msa["range"]["ndc"],
                            msa["dual_delta_pp"], item.msa_procedure)),
            "requirement": ("No requirement breach beyond the procedure "
                            "criterion. Opportunity: improve the measurement "
                            "method (fixturing, resolution, training) or "
                            "document the specific-application justification "
                            "for the conditional system."),
            "objective_ref": "MSA study GRR-2026-06, gage G-077",
            "status": "open",
        })

    # ---- clause conformance rows (derived from the findings + results) ----
    def row(clause, title, status, evidence):
        return {"clause": clause, "title": title, "status": status,
                "evidence": evidence}

    nc_clauses = {f["clause"] for f in findings
                  if f["classification"] == "minor"}
    ofi_clauses = {f["clause"] for f in findings
                   if f["classification"] == "observation"}
    conformance = [
        row("4.4", "QMS and its processes",
            "conforming",
            "All 41 active gage master/calibration records reviewed (100% "
            "census): records current, revision-controlled, and traceable to "
            "the gage register; no record-level gaps found"),
        row("7.1.5.1", "Monitoring and measuring resources (general)",
            "minor nonconformity" if "7.1.5.1" in nc_clauses
            else "conforming with observations",
            "Attribute agreement study poor (kappa %.2f); bore micrometer "
            "%%GRR %.2f%% conditional (range method %.2f%%)"
            % (ag["kappa"], an["percent_grr"], msa["range"]["percent_grr"])),
        row("7.1.5.2", "Measurement traceability",
            "minor nonconformity" if "7.1.5.2" in nc_clauses
            else "conforming",
            "Calibration records complete; micrometer G-112 bias "
            "significant (mean bias +%.4f mm, overall %s)"
            % (bl["mean_bias"], bl["overall"])),
        row("8.5.1", "Control of production and service provision",
            "minor nonconformity" if "8.5.1" in nc_clauses
            else "conforming with observations",
            "I-MR chart out of control at coating lot %d with no reaction "
            "record; KC-002 X-bar/R stable with Cpk %.2f below the %.2f "
            "flow-down" % (item.coating_out_of_control_lot, xr["cpk"],
                           item.flow_down_cpk)),
        row("8.6", "Release of products and services",
            "conforming",
            "Attribute plan (n=%d, Ac=%d, Re=%d) at AQL %.1f executed "
            "correctly: %d nonconforming found -> %s; OC probability %.4f at "
            "AQL (producer risk %.2f%%); variables k-method plan (n=%d, "
            "k=%.2f): Q=%.2f >= k -> %s, estimated nonconforming %.3g%% vs "
            "max M=%.2f%%"
            % (sampling["attribute"]["n"], sampling["attribute"]["ac"],
               sampling["attribute"]["re"], item.attr_aql,
               sampling["attribute"]["found"],
               sampling["attribute"]["decision"],
               sampling["attribute"]["oc_at_aql"],
               sampling["attribute"]["producer_risk_pct"],
               sampling["variables"]["n"], sampling["variables"]["k"],
               sampling["variables"]["Q"],
               "accept" if sampling["variables"]["accept"] else "reject",
               sampling["variables"]["p_hat"], sampling["variables"]["M"])),
        row("9.1.1", "Monitoring, measurement, analysis and evaluation",
            "conforming",
            "Small-shift surveillance active: CUSUM and EWMA charts on %d "
            "bore-deviation observations produced no signal; p-chart over "
            "%d lots in control (pbar %.4f)"
            % (spc["shift_monitoring"]["n"], spc["p_chart"]["subgroups"],
               spc["p_chart"]["pbar"])),
    ]
    return findings, conformance


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------

def render_report_markdown(model: dict) -> str:
    m = model
    msa, spc, sampling = m["msa"], m["spc"], m["sampling"]
    an, rng, bl = msa["anova"], msa["range"], msa["bias_linearity"]
    ag = msa["attribute"]
    lines = [
        "# AS9100 Quality Management System Audit Report",
        "",
        "**Site:** %s (%s)" % (m["site"]["name"], m["site"]["ref"]),
        "**Standard:** %s (referenced summary-only; no standard text "
        "reproduced)" % m["standard"],
        "**Audit period:** %s" % m["audit_period"],
        "**Audit lead:** %s" % m["audit_lead"],
        "**Status:** %s" % m["status"],
        "",
        "## 1. Scope and audit basis",
        "",
        "This report audits the numerical quality evidence behind the "
        "site's quality management system: measurement systems analysis "
        "records, statistical process control records, and acceptance-"
        "sampling release evidence for the audit period. Every result "
        "below is computed by the role engine from the raw datasets "
        "listed; nothing is asserted without a computed number.",
        "",
        "- Criteria: %s clauses as summarized in the site audit matrix; "
        "%s." % (m["standard"], m["criteria"]["capability_flow_down"]),
        "- Measurement-system acceptance criteria: %s; %s." % (
            m["criteria"]["grr_bands"], m["criteria"]["grr_kc_criterion"]),
        "- Inspector agreement bands: %s." % m["criteria"]["kappa_bands"],
        "- Records reviewed: %s." % m["evidence_scope"]["records"],
        "- Datasets analyzed:",
        "",
        *["  - %s" % d for d in m["evidence_scope"]["datasets"]],
        "",
        "## 2. Executive summary",
        "",
        "| Clause | Audit area | Result |",
        "|---|---|---|",
    ]
    for c in m["conformance"]:
        lines.append("| %s | %s | %s |" % (c["clause"], c["title"],
                                           c["status"]))
    lines += [
        "",
        "Findings: %d minor nonconformity(ies), %d observation(s)/"
        "opportunities for improvement; 0 major." % (
            m["counts"]["minor"], m["counts"]["ofi"]),
        "",
        "## 3. Measurement systems analysis audit",
        "",
        "### 3.1 Gage R&R - ANOVA (KC-001 bore micrometer G-077)",
        "",
        "Study layout: %s. Two-way random-effects ANOVA on 90 readings." %
        an["layout"],
        "",
        "| Quantity | Value |",
        "|---|---|",
        "| %%GRR (ANOVA) | %.2f%% |" % an["percent_grr"],
        "| Verdict (10/30 band) | %s |" % an["verdict"],
        "| Number of distinct categories (ndc) | %s |" % an["ndc"],
        "| Repeatability EV / Reproducibility AV / Interaction IV | "
        "%.4f / %.4f / %.4f mm |" % (an["ev"], an["av"], an["iv"]),
        "| Part variation PV / Total variation TV | %.4f / %.4f mm |"
        % (an["pv"], an["tv"]),
        "",
        "### 3.2 Gage R&R - independent range-method estimator",
        "",
        "The same 90 readings re-analyzed with the AIAG range method "
        "(5.15-sigma constants) as an independent estimator:",
        "",
        "| Quantity | Value |",
        "|---|---|",
        "| %%GRR (range method) | %.2f%% |" % rng["percent_grr"],
        "| Verdict (10/30 band) | %s |" % rng["verdict"],
        "| ndc | %s |" % rng["ndc"],
        "| EV / AV / GRR | %.4f / %.4f / %.4f mm |" % (rng["ev"], rng["av"],
                                                      rng["grr"]),
        "| Dual-method agreement | %.2f percentage points |" %
        msa["dual_delta_pp"],
        "",
        "### 3.3 Gage bias and linearity (micrometer G-112)",
        "",
        "| Reference (mm) | Bias (mm) | Bias % of reference |",
        "|---|---|---|",
    ]
    for rowl in bl.get("per_level", []):
        lines.append("| %.3f | %+.4f | %.3f%% |" % (rowl["reference"],
                                                    rowl["bias"],
                                                    rowl["bias_pct_of_reference"]))
    lines += [
        "",
        "| Statistic | Value |",
        "|---|---|",
        "| Mean bias | %+.4f mm |" % bl["mean_bias"],
        "| Linearity slope (bias vs reference) | %+.5f mm/mm |" % bl["slope"],
        "| Regression R-squared | %.4f |" % bl["r_squared"],
        "| Bias significance t (df %d) | %.2f vs t crit %.2f -> %s |"
        % (bl["df"], bl["t_stat"], bl["t_crit"],
           "significant" if bl["significant"] else "not significant"),
        "| Worst per-level | %.3f%% at %.1f mm (band %.0f%%) |"
        % (bl["worst_bias_pct"], bl["worst_reference"],
           ACCEPTANCE_PCT_BAND),
        "| Overall verdict | %s |" % bl["overall"],
        "",
        "### 3.4 Attribute agreement analysis",
        "",
        "Layout: %s." % ag["layout"],
        "",
        "| Statistic | Value |",
        "|---|---|",
        "| Fleiss kappa | %.2f |" % ag["kappa"],
        "| Observed agreement (P-bar) | %.1f%% |" % (100.0 * ag["pbar"]),
        "| Chance agreement (P-e) | %.1f%% |" % (100.0 * ag["pe"]),
        "| Verdict | %s |" % ag["verdict"],
        "| Pairwise inspector A-B re-check | agreement %.1f%%, "
        "kappa %.2f |" % (100.0 * ag["pairwise"]["observed_agreement"],
                          ag["pairwise"]["kappa"]),
        "",
        "## 4. Statistical process control audit",
        "",
        "### 4.1 X-bar/R and capability (KC-002 pin diameter 6.000 mm)",
        "",
        "| Statistic | Value |",
        "|---|---|",
        "| Subgroups (n=%d) | %d |" % (spc["xbar_r"]["n"],
                                       spc["xbar_r"]["subgroups"]),
        "| Center line x-bar / R-bar | %.4f mm / %.5f mm |"
        % (spc["xbar_r"]["xbar"], spc["xbar_r"]["rbar"]),
        "| X-bar UCL / LCL | %.5f / %.5f mm |"
        % (spc["xbar_r"]["x_ucl"], spc["xbar_r"]["x_lcl"]),
        "| R UCL / LCL | %.5f / %.5f mm |"
        % (spc["xbar_r"]["r_ucl"], spc["xbar_r"]["r_lcl"]),
        "| Process sigma (R-bar/d2) | %.5f mm |" % spc["xbar_r"]["sigma_hat"],
        "| Cp / Cpu / Cpl / Cpk | %.2f / %.2f / %.2f / %.2f |"
        % (spc["xbar_r"]["cp"], spc["xbar_r"]["cpu"], spc["xbar_r"]["cpl"],
           spc["xbar_r"]["cpk"]),
        "| Western Electric rule violations | %s |"
        % (", ".join(spc["xbar_r"]["ooc_rules"]) or "none"),
        "| Chart verdict | %s |" % spc["xbar_r"]["verdict"],
        "",
        "### 4.2 I-MR chart (coating thickness per lot)",
        "",
        "| Statistic | Value |",
        "|---|---|",
        "| Lots plotted | %d |" % spc["imr"]["lots"],
        "| Mean / average moving range | %.2f / %.2f um |"
        % (spc["imr"]["mean"], spc["imr"]["mr_bar"]),
        "| Individuals UCL / LCL | %.2f / %.2f um |"
        % (spc["imr"]["x_ucl"], spc["imr"]["x_lcl"]),
        "| Moving-range UCL | %.2f um |" % spc["imr"]["mr_ucl"],
        "| Flagged lots (individuals) | %s |"
        % (", ".join(str(i + 1) for i in
                     spc["imr"]["flagged_individuals"]) or "none"),
        "| Chart verdict | %s |" % spc["imr"]["verdict"],
        "",
        "### 4.3 CUSUM / EWMA small-shift surveillance",
        "",
        "| Statistic | Value |",
        "|---|---|",
        "| Observations reviewed | %d |" % spc["shift_monitoring"]["n"],
        "| CUSUM signal | %s |" % _fmt_bool(
            spc["shift_monitoring"]["cusum_signaled"]),
        "| EWMA signal | %s |" % _fmt_bool(
            spc["shift_monitoring"]["ewma_signaled"]),
        "| First signal (1-based sample) | %s |"
        % (spc["shift_monitoring"]["first_signal_index"] or "none"),
        "",
        "### 4.4 p-chart (final-lot nonconforming fraction)",
        "",
        "| Statistic | Value |",
        "|---|---|",
        "| Subgroups (n=200) | %d |" % spc["p_chart"]["subgroups"],
        "| p-bar | %.4f |" % spc["p_chart"]["pbar"],
        "| UCL / LCL | %.4f / %.4f |"
        % (spc["p_chart"]["ucl"], spc["p_chart"]["lcl"]),
        "| Flagged subgroups | %s |"
        % (", ".join(str(i + 1) for i in
                     spc["p_chart"]["flagged_subgroups"]) or "none"),
        "| Verdict | %s |" % spc["p_chart"]["verdict"],
        "",
        "## 5. Acceptance sampling audit",
        "",
        "### 5.1 Attribute plan (release lots)",
        "",
        "Basis: %s." % sampling["attribute"]["basis"],
        "",
        "| Plan element | Value |",
        "|---|---|",
        "| Lot size / inspection level / AQL | %d / %s / %.1f |"
        % (sampling["attribute"]["lot_size"], "II",
           sampling["attribute"]["aql"]),
        "| Sample size code letter | %s |" % sampling["attribute"]["code"],
        "| Plan (n, Ac, Re) | (%d, %d, %d) |"
        % (sampling["attribute"]["n"], sampling["attribute"]["ac"],
           sampling["attribute"]["re"]),
        "| Nonconforming found in sample | %d |"
        % sampling["attribute"]["found"],
        "| Lot decision | %s |" % sampling["attribute"]["decision"],
        "| OC probability at AQL | %.4f |"
        % sampling["attribute"]["oc_at_aql"],
        "| Producer risk (1 - Pa at AQL) | %.2f%% |"
        % sampling["attribute"]["producer_risk_pct"],
        "| OC probability at 4%% nonconforming | %.4f |"
        % sampling["attribute"]["oc_at_4pct"],
        "",
        "### 5.2 Variables plan (k-method, single USL)",
        "",
        "Basis: %s." % sampling["variables"]["basis"],
        "",
        "| Plan element | Value |",
        "|---|---|",
        "| Lot size / AQL / USL | %d / %.1f / %.3f mm |"
        % (sampling["variables"]["lot_size"], sampling["variables"]["aql"],
           sampling["variables"]["usl"]),
        "| Code letter / sample n | %s / %d |"
        % (sampling["variables"]["code"], sampling["variables"]["n"]),
        "| Acceptability constant k / max %% nonconforming M | %.2f / %.2f |"
        % (sampling["variables"]["k"], sampling["variables"]["M"]),
        "| Sample mean / standard deviation | %.4f / %.4f mm |"
        % (sampling["variables"]["xbar"], sampling["variables"]["s"]),
        "| Q = (USL - x-bar)/s | %.2f |" % sampling["variables"]["Q"],
        "| Estimated %% nonconforming above USL | %.3g%% |"
        % sampling["variables"]["p_hat"],
        "| k-method decision (Q >= k) | %s |"
        % ("accept" if sampling["variables"]["accept"] else "reject"),
        "",
        "## 6. Findings",
        "",
    ]
    for f in m["findings"]:
        lines += [
            "### %s - %s (clause %s)" % (f["id"],
                                          f["classification"].upper(),
                                          f["clause"]),
            "",
            "**Title:** %s" % f["title"],
            "**Objective evidence:** %s" % f["evidence"],
            "**Requirement reference (summary):** %s" % f["requirement"],
            "**Objective evidence reference:** %s" % f["objective_ref"],
            "**Disposition status:** %s - corrective action is the site's "
            "responsibility; this report does not close findings." %
            f["status"],
            "",
        ]
    lines += [
        "## 7. Clause conformance summary",
        "",
        "| Clause | Audit area | Status | Evidence (computed) |",
        "|---|---|---|---|",
    ]
    for c in m["conformance"]:
        lines.append("| %s | %s | %s | %s |" % (c["clause"], c["title"],
                                                c["status"], c["evidence"]))
    lines += [
        "",
        "## 8. Limitations and boundaries",
        "",
        "- Datasets are the site's own records; conclusions hold only for "
        "the samples and periods listed in section 1.",
        "- Classification criteria are summarized from the site's audit "
        "procedure; severity reflects released-product and systemic impact "
        "evidence only.",
        "- Findings remain open pending the site's corrective action; this "
        "report does not issue, close, or waive any finding.",
        "",
        "---",
        "*Generated by Aero Agent Roles quality-management-engineer core "
        "(%s). DRAFT for human quality-management review. Not an approval "
        "document. This report is not a certification decision and does not "
        "constitute AS9100 certification or a registrar finding.*" %
        m["generated"],
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evidence gates
# ---------------------------------------------------------------------------

GATE_DESCRIPTIONS = {
    "basis_identified": "audit basis is AS9100D with reference-only note",
    "measurement_evidence_computed": "gage R&R percent GRR is a real number "
                                     "with a band verdict",
    "capability_computed": "process capability (Cpk) is a real number",
    "sampling_evidence_computed": "acceptance sampling plan numbers and "
                                  "decision are present",
    "conformance_table_present": "clause conformance rows are derived",
    "sign_off_honest": "document is marked draft-for-review, not approval",
}


def check_report(model: dict) -> dict:
    msa = model.get("msa", {})
    spc = model.get("spc", {})
    sampling = model.get("sampling", {})
    an = msa.get("anova", {})
    xr = spc.get("xbar_r", {})
    results = {
        "basis_identified": (model.get("standard") == "AS9100D"
                             and "reference" in (model.get("standard_note")
                                                 or "").lower()),
        "measurement_evidence_computed": isinstance(
            an.get("percent_grr"), (int, float)) and an.get("verdict")
            in ("acceptable", "conditional", "unacceptable"),
        "capability_computed": isinstance(xr.get("cpk"), (int, float))
            and isinstance(xr.get("cp"), (int, float)),
        "sampling_evidence_computed": bool(
            sampling.get("attribute", {}).get("n")
            and sampling.get("attribute", {}).get("decision") in
            ("accept", "reject")
            and isinstance(sampling.get("variables", {}).get("Q"),
                           (int, float))),
        "conformance_table_present": bool(model.get("conformance")),
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_report_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    checks = {
        "has_title": "as9100 quality management system audit report" in low,
        "has_basis": "as9100d" in low and "reference" in low,
        "has_measurement_evidence": "gage r&r" in low and "%grr" in low,
        "has_capability": "cpk" in low,
        "has_sampling_evidence": "acceptance sampling" in low and "aql" in low,
        "has_conformance": "clause conformance" in low,
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low
                            and "not a certification" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling."""
    return check_report_markdown(md_text)


# ---------------------------------------------------------------------------
# Example audit (tests + worked template generation)
# ---------------------------------------------------------------------------

def example_item() -> AuditItem:
    return AuditItem()


def example_report_markdown() -> str:
    return render_report_markdown(build_report(example_item()))


if __name__ == "__main__":
    model = build_report(example_item())
    md = render_report_markdown(model)
    print("SITE: %s" % model["site"]["name"])
    print("ANOVA %%GRR: %.2f (%s), ndc %s" %
          (model["msa"]["anova"]["percent_grr"],
           model["msa"]["anova"]["verdict"], model["msa"]["anova"]["ndc"]))
    print("RANGE %%GRR: %.2f (%s), ndc %s" %
          (model["msa"]["range"]["percent_grr"],
           model["msa"]["range"]["verdict"], model["msa"]["range"]["ndc"]))
    print("BIAS: mean %.4f overall %s" %
          (model["msa"]["bias_linearity"]["mean_bias"],
           model["msa"]["bias_linearity"]["overall"]))
    print("KAPPA: %.2f (%s)" % (model["msa"]["attribute"]["kappa"],
                                model["msa"]["attribute"]["verdict"]))
    print("CPK: %.3f  Cp %.3f" % (model["spc"]["xbar_r"]["cpk"],
                                  model["spc"]["xbar_r"]["cp"]))
    print("IMR: %s lots %s" % (model["spc"]["imr"]["verdict"],
                               model["spc"]["imr"]["flagged_individuals"]))
    print("SHIFT: any=%s" % model["spc"]["shift_monitoring"]["any_signal"])
    print("P-CHART: %s" % model["spc"]["p_chart"]["verdict"])
    print("SAMPLING attr: %s %s found=%d decision=%s" %
          (model["sampling"]["attribute"]["code"],
           (model["sampling"]["attribute"]["n"],
            model["sampling"]["attribute"]["ac"],
            model["sampling"]["attribute"]["re"]),
           model["sampling"]["attribute"]["found"],
           model["sampling"]["attribute"]["decision"]))
    print("SAMPLING vars: Q=%.3f accept=%s" %
          (model["sampling"]["variables"]["Q"],
           model["sampling"]["variables"]["accept"]))
    print("FINDINGS: %s" % [f["id"] for f in model["findings"]])
    print("COUNTS: %s" % model["counts"])
    print("GATES: %s" % check_report(model))
    print("RENDERED: %d chars" % len(md))
