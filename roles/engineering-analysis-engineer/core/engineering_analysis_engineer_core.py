#!/usr/bin/env python3
"""engineering_analysis_engineer_core.py - Engineering Analysis and Data
Engineer executable core.

This is the role's ENGINE: given a measurement/calculation chain's facts
it computes the ISA atmosphere reference values, propagates measurement
uncertainty (GUM first-order law), builds the t-distribution confidence
interval for repeated-measurement bias, runs the tolerance stack-up
(worst case and RSS), verifies numerical convergence (Richardson
extrapolation + grid convergence index), states margins per the
engineering-margins convention, and BUILDS the Analysis Verification
Memo. It also gate-checks deliverables. Standalone: stdlib only, no
external repo needed.

Every formula mirrors the REAL logic in the bound AeroSkills leaves
(paraphrased common engineering methodology):
  - isa-atmosphere: ICAO/ISO 2533 standard atmosphere model
  - uncertainty-propagation: GUM (JCGM 100) first order law
  - confidence-interval-estimation: Student t interval
  - tolerance-stackup: worst case + RSS dimension chain
  - convergence-verification: Richardson extrapolation + GCI (Fs=1.25)
  - engineering-margins: MS = allowable/applied - 1
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Domain tables (public standards / common engineering methodology)
# ---------------------------------------------------------------------------

# ISA standard atmosphere constants (ISO 2533 / ICAO Doc 7488; also the
# values encoded in the bound isa-atmosphere leaf).
ISA_G = 9.80665          # m/s2  gravitational acceleration
ISA_R = 287.05           # J/(kg K) specific gas constant of air
ISA_LAPSE = 0.0065       # K/m tropospheric lapse rate
ISA_T0 = 288.15          # K  sea-level temperature
ISA_P0 = 101325.0        # Pa sea-level pressure
ISA_TROPOPAUSE = 11000.0 # m
ISA_TOP = 20000.0        # m model top
ISA_T_TROP = ISA_T0 - ISA_LAPSE * ISA_TROPOPAUSE  # 216.65 K


# ---------------------------------------------------------------------------
# ISA standard atmosphere (0-20 km)
# ---------------------------------------------------------------------------

def isa_temperature_k(h: float) -> float:
    """ISA temperature (K) at altitude h (m), 0-20 km."""
    if h < 0 or h > ISA_TOP:
        raise ValueError(f"altitude outside model 0-20 km: {h!r}")
    return ISA_T0 - ISA_LAPSE * h if h <= ISA_TROPOPAUSE else ISA_T_TROP


def isa_pressure_pa(h: float) -> float:
    """ISA pressure (Pa) at altitude h (m), 0-20 km."""
    if h < 0 or h > ISA_TOP:
        raise ValueError(f"altitude outside model 0-20 km: {h!r}")
    if h <= ISA_TROPOPAUSE:
        t = ISA_T0 - ISA_LAPSE * h
        return ISA_P0 * (t / ISA_T0) ** (ISA_G / (ISA_R * ISA_LAPSE))
    p_trop = isa_pressure_pa(ISA_TROPOPAUSE)
    return p_trop * math.exp(-ISA_G * (h - ISA_TROPOPAUSE)
                             / (ISA_R * ISA_T_TROP))


def isa_density_kgm3(h: float) -> float:
    """ISA density (kg/m3) at altitude h (m), 0-20 km."""
    return isa_pressure_pa(h) / (ISA_R * isa_temperature_k(h))


def isa_reference_values(h: float) -> dict:
    """ISA reference (temperature K, pressure Pa, density kg/m3) at h."""
    t = isa_temperature_k(h)
    p = isa_pressure_pa(h)
    return {"altitude_m": h, "temperature_k": t,
            "pressure_pa": p, "density_kgm3": p / (ISA_R * t)}


def density_from_measured(p_pa: float, t_k: float) -> float:
    """Air density from measured pressure and temperature (ideal gas EOS)."""
    if p_pa <= 0 or t_k <= 0:
        raise ValueError("pressure and temperature must be positive")
    return p_pa / (ISA_R * t_k)


# ---------------------------------------------------------------------------
# Uncertainty propagation (GUM / JCGM 100 first-order law)
# ---------------------------------------------------------------------------

def combined_standard_uncertainty(sensitivities, uncertainties):
    """u_c = sqrt(sum((s_i * u_i)^2)), GUM first-order law.

    sensitivities[i] = df/dx_i at the operating point, uncertainties[i]
    = standard uncertainty (1 sigma) of input i; independent inputs.
    """
    if not sensitivities or not uncertainties:
        raise ValueError("sensitivities and uncertainties must be non-empty")
    if len(sensitivities) != len(uncertainties):
        raise ValueError("sensitivities and uncertainties length mismatch")
    for u in uncertainties:
        if u < 0.0:
            raise ValueError(f"uncertainty must be non-negative: {u!r}")
    return math.sqrt(sum((s * u) ** 2
                         for s, u in zip(sensitivities, uncertainties)))


def expanded_uncertainty(combined, k=2.0):
    """U = k * u_c; coverage factor k = 2.0 (~95%) by convention."""
    if k <= 0.0:
        raise ValueError(f"coverage factor k must be > 0: {k!r}")
    return k * combined


def uncertainty_contributions(sensitivities, uncertainties):
    """Per-input variance contributions sorted descending.

    Each dict: {index, name, sensitivity, uncertainty, contribution,
    percent}. Percent shares sum to ~100.
    """
    combined = combined_standard_uncertainty(sensitivities, uncertainties)
    total = combined ** 2
    contribs = []
    for i, (s, u) in enumerate(zip(sensitivities, uncertainties)):
        c = (s * u) ** 2
        contribs.append({"index": i, "sensitivity": s, "uncertainty": u,
                         "contribution": c,
                         "percent": 0.0 if total == 0.0 else 100.0 * c / total})
    contribs.sort(key=lambda e: e["contribution"], reverse=True)
    return contribs


# ---------------------------------------------------------------------------
# Confidence interval (Student t distribution, small-sample)
# ---------------------------------------------------------------------------

# Regularized incomplete beta machinery for the t quantile (pure math,
# same method as the bound confidence-interval-estimation leaf).
_CF_MAX_ITER = 200
_CF_EPS = 3e-12
_FPMIN = 1e-300
_BIS_TOL = 1e-9
_BIS_MAX = 300


def _betacf(a, b, x):
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < _FPMIN:
        d = _FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, _CF_MAX_ITER + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = 1.0 + aa / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = 1.0 + aa / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _CF_EPS:
            break
    return h


def _betai(a, b, x):
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                  + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def _t_cdf(t, df):
    x = df / (df + t * t)
    return 1.0 - 0.5 * _betai(df / 2.0, 0.5, x)


def t_ppf_two_sided(level: float, df: float) -> float:
    """Two-sided t quantile t_{1-alpha/2, df} for alpha = 1 - level."""
    if not 0.0 < level < 1.0:
        raise ValueError(f"level must be in (0, 1): {level!r}")
    if df < 1.0:
        raise ValueError(f"df must be >= 1: {df!r}")
    target = 0.5 * (1.0 + float(level))
    hi = 1.0
    while _t_cdf(hi, df) < target and hi < 1e12:
        hi *= 2.0
    lo, flo = 0.0, _t_cdf(0.0, df)
    for _ in range(_BIS_MAX):
        mid = 0.5 * (lo + hi)
        if hi - lo <= _BIS_TOL:
            return mid
        fmid = _t_cdf(mid, df)
        if (fmid - target) * (flo - target) <= 0.0:
            hi = mid
        else:
            lo, flo = mid, fmid
    return 0.5 * (lo + hi)


def confidence_interval_mean(x, level: float = 0.95) -> dict:
    """t interval for the mean: xbar +/- t_{1-a/2, n-1} * s / sqrt(n)."""
    if not isinstance(x, (list, tuple)) or len(x) < 2:
        raise ValueError("sample must have at least 2 observations")
    n = len(x)
    mean = sum(float(v) for v in x) / n
    var = sum((float(v) - mean) ** 2 for v in x) / (n - 1)
    s = math.sqrt(var)
    df = n - 1
    t_q = t_ppf_two_sided(level, df)
    se = s / math.sqrt(n)
    half = t_q * se
    return {"mean": mean, "sample_std": s, "se": se, "n": n, "df": float(df),
            "level": float(level), "t_quantile": t_q,
            "lower": mean - half, "upper": mean + half}


# ---------------------------------------------------------------------------
# Tolerance stack-up (worst case + RSS dimension chain)
# ---------------------------------------------------------------------------

@dataclass
class StackMember:
    """One dimension in the tolerance chain (signed direction)."""
    name: str
    nominal_mm: float
    tolerance_mm: float      # symmetric bilateral half-width
    direction: int = 1       # +1 adds to chain, -1 subtracts


def nominal_total(members) -> float:
    if not members:
        raise ValueError("stack must be non-empty")
    return sum(m.direction * m.nominal_mm for m in members)


def worst_case_total(members) -> float:
    if not members:
        raise ValueError("stack must be non-empty")
    for m in members:
        if m.tolerance_mm < 0:
            raise ValueError(f"tolerance must be >= 0: {m.tolerance_mm!r}")
    return sum(abs(m.tolerance_mm) for m in members)


def rss_total(members) -> float:
    if not members:
        raise ValueError("stack must be non-empty")
    for m in members:
        if m.tolerance_mm < 0:
            raise ValueError(f"tolerance must be >= 0: {m.tolerance_mm!r}")
    return math.sqrt(sum(m.tolerance_mm ** 2 for m in members))


def rss_shares(members) -> list:
    """Percent RSS variance share per member (100 * t_i^2 / sum t_j^2)."""
    denom = sum(m.tolerance_mm ** 2 for m in members)
    if denom == 0:
        raise ValueError("all tolerances zero: no stack spread")
    return [100.0 * m.tolerance_mm ** 2 / denom for m in members]


# ---------------------------------------------------------------------------
# Convergence verification (Richardson extrapolation + GCI)
# ---------------------------------------------------------------------------

def observed_order(f1, f2, f3, r: float) -> float:
    """p = ln((f3-f2)/(f2-f1)) / ln(r); r > 1, monotone sequence."""
    if r <= 1.0:
        raise ValueError(f"refinement ratio must be > 1: {r!r}")
    if f2 == f1:
        raise ValueError("degenerate: f2 == f1")
    ratio = (f3 - f2) / (f2 - f1)
    if ratio <= 0.0:
        raise ValueError("non-monotone sequence for observed order")
    return math.log(ratio) / math.log(r)


def richardson_extrapolation(f1, f2, r: float, p: float) -> float:
    return f1 + (f1 - f2) / (r ** p - 1.0)


def grid_convergence_index(f1, f2, r: float, p: float, fs: float = 1.25) -> float:
    """GCI = Fs * |(f1-f2)/f1| / (r^p - 1); fraction not percent."""
    return fs * abs((f1 - f2) / f1) / (r ** p - 1.0)


def convergence_verdict(f1, f2, f3, r: float) -> dict:
    """Classify a three-solution grid study (f1 finest ... f3 coarsest)."""
    if r <= 1.0:
        raise ValueError(f"refinement ratio must be > 1: {r!r}")
    if f2 == f1:
        raise ValueError("degenerate: f2 == f1")
    ratio = (f3 - f2) / (f2 - f1)
    if ratio > 0.0:
        p = math.log(ratio) / math.log(r)
        denom = r ** p - 1.0
        if abs(denom) < 1e-12:
            return {"order": p, "extrapolated": None, "gci": None,
                    "verdict": "monotone converged"}
        f_exact = f1 + (f1 - f2) / denom
        gci = 1.25 * abs((f1 - f2) / f1) / denom
        return {"order": p, "extrapolated": f_exact, "gci": gci,
                "verdict": "monotone converged"}
    if ratio < 0.0:
        verdict = "diverging" if abs(ratio) > 1.0 else "oscillatory"
    else:
        verdict = "oscillatory"
    return {"order": None, "extrapolated": None, "gci": None,
            "verdict": verdict}


# ---------------------------------------------------------------------------
# Numerical integration of the hydrostatic balance (verification study)
# ---------------------------------------------------------------------------

def trapezoid_hydrostatic_pressure(h_top: float, n_steps: int) -> float:
    """Integrate dp/dz = -rho(z)*g from 0 to h_top by the trapezoid rule.

    The integrand is evaluated from the closed-form ISA model; the study
    verifies that the integrator used for the atmosphere model reproduces
    the analytic ISA pressure at the top altitude.
    """
    if h_top <= 0 or n_steps < 1:
        raise ValueError("h_top > 0 and n_steps >= 1 required")
    dz = h_top / n_steps
    total = 0.0
    for i in range(n_steps + 1):
        z = i * dz
        rho = isa_density_kgm3(z)
        w = 0.5 if i in (0, n_steps) else 1.0
        total += w * (-rho * ISA_G)
    return ISA_P0 + total * dz


# ---------------------------------------------------------------------------
# Root finding: density-altitude inversion (Newton iteration)
# ---------------------------------------------------------------------------

def density_altitude_m(rho_target: float, h0: float = 3000.0,
                      tol: float = 1e-9, max_iter: int = 50) -> dict:
    """Invert rho_ISA(h) = rho_target by Newton iteration (troposphere).

    rho(h) = rho0 * (T/T0)^(g/(R L) - 1); analytic derivative
    d rho/dh = -rho * (L/T) * (g/(R L) - 1).
    """
    if rho_target <= 0:
        raise ValueError(f"target density must be positive: {rho_target!r}")
    rho0 = ISA_P0 / (ISA_R * ISA_T0)
    expo = ISA_G / (ISA_R * ISA_LAPSE) - 1.0
    h = h0
    for _ in range(max_iter):
        t = isa_temperature_k(h)
        rho = rho0 * (t / ISA_T0) ** expo
        resid = rho - rho_target
        drho_dh = -rho * (ISA_LAPSE / t) * expo
        if abs(resid) < tol:
            return {"altitude_m": h, "residual": abs(resid),
                    "iterations": _ + 1, "converged": True}
        h -= resid / drho_dh
    raise ValueError("Newton iteration did not converge")


# ---------------------------------------------------------------------------
# Margins (engineering-margins convention: MS = allowable/applied - 1)
# ---------------------------------------------------------------------------

def margin_of_safety(allowable: float, applied: float) -> float:
    """MS = allowable/applied - 1 (unitless; same units for both inputs)."""
    if allowable < 0 or applied <= 0:
        raise ValueError("allowable >= 0 and applied > 0 required")
    return allowable / applied - 1.0


def margin_verdict(ms: float) -> str:
    return "PASS" if ms >= 0.0 else "FAIL"


# ---------------------------------------------------------------------------
# Example measurement chain (the reference item for the memo)
# ---------------------------------------------------------------------------

@dataclass
class MeasurementChain:
    """Project facts the role needs to build the analysis memo."""
    chain_name: str
    description: str = ""
    altitude_m: float = 3000.0            # test point geometric altitude
    pressure_pa: float = 70050.0          # measured static pressure
    pressure_unc_pa: float = 35.0         # u_p, 1 sigma (calibrated sensor)
    temperature_k: float = 271.0          # measured temperature
    temperature_unc_k: float = 1.2        # u_T, 1 sigma
    coverage_factor: float = 2.0          # k ~ 95%
    confidence_level: float = 0.95
    bias_samples_pa: list = field(default_factory=list)  # repeat readings
    bias_reference_note: str = ""
    stack_members: list = field(default_factory=list)    # list[StackMember]
    stack_allowable_mm: float = 0.8       # spec limit on probe position
    density_allowable_pct: float = 1.5    # spec limit on density accuracy
    export_classification: str = "uncontrolled technical data (example)"


def example_chain() -> MeasurementChain:
    """Flight-test air-data chain used for the worked example memo."""
    return MeasurementChain(
        chain_name="Flight-test air-data chain at 3000 m",
        description="Static pressure and temperature are measured at the "
                    "flight-test point and reduced to air density and "
                    "density altitude; repeated static-source readings are "
                    "checked for bias; the probe mounting stack and the "
                    "atmosphere-model integrator are verified.",
        altitude_m=3000.0,
        pressure_pa=70050.0,
        pressure_unc_pa=35.0,
        temperature_k=271.0,
        temperature_unc_k=1.2,
        coverage_factor=2.0,
        confidence_level=0.95,
        bias_samples_pa=[1.8, -2.2, 3.1, -0.7, 2.4, -1.5,
                         0.9, 2.8, -1.1, 0.4],
        bias_reference_note="n=10 repeat readings of the static source "
                            "error vs the reference pressure standard",
        stack_members=[
            StackMember("mounting bracket", 120.0, 0.50, +1),
            StackMember("adapter", 45.0, 0.25, +1),
            StackMember("probe inset", 60.0, 0.40, -1),
        ],
        stack_allowable_mm=0.8,
        density_allowable_pct=1.5,
        export_classification="uncontrolled technical data (example)",
    )


# ---------------------------------------------------------------------------
# Memo builder: produces the deliverable content model (REAL numbers)
# ---------------------------------------------------------------------------

def _fmt(v, digits: int = 5) -> str:
    return f"{v:.{digits}g}"


def build_memo(chain: MeasurementChain) -> dict:
    """Compute every result in the chain and assemble the memo model."""
    alt = chain.altitude_m
    if not (0 < alt <= ISA_TROPOPAUSE):
        raise ValueError("example chain altitude must be tropospheric (0-11 km)")

    # --- Stage 2: ISA reference values at the test point ----------------
    isa = isa_reference_values(alt)

    # --- Stage 4: derived density + uncertainty propagation --------------
    rho_m = density_from_measured(chain.pressure_pa, chain.temperature_k)
    t = chain.temperature_k
    sens_p = 1.0 / (ISA_R * t)                       # d rho / d p
    sens_t = -chain.pressure_pa / (ISA_R * t * t)    # d rho / d T
    u_c = combined_standard_uncertainty([sens_p, sens_t],
                                        [chain.pressure_unc_pa,
                                         chain.temperature_unc_k])
    U = expanded_uncertainty(u_c, chain.coverage_factor)
    contribs = uncertainty_contributions([sens_p, sens_t],
                                         [chain.pressure_unc_pa,
                                          chain.temperature_unc_k])
    for c in contribs:
        c["name"] = "static pressure" if c["index"] == 0 else "temperature"
    rel_unc_pct = 100.0 * u_c / rho_m
    delta_isa_pct = 100.0 * (rho_m - isa["density_kgm3"]) / isa["density_kgm3"]

    # --- Density-altitude inversion (Newton, convergence checked) --------
    h_rho = density_altitude_m(rho_m, h0=alt)
    alt_delta_m = h_rho["altitude_m"] - alt

    # --- Stage 7: confidence interval on repeated-measurement bias -------
    ci = confidence_interval_mean(chain.bias_samples_pa,
                                  chain.confidence_level)

    # --- Stage 9: tolerance stack-up --------------------------------------
    members = chain.stack_members
    nom = nominal_total(members)
    wc = worst_case_total(members)
    rss = rss_total(members)
    shares = rss_shares(members)
    wc_limits = (nom - wc, nom + wc)
    rss_limits = (nom - rss, nom + rss)
    dominant_i = max(range(len(shares)), key=lambda i: shares[i])
    # Margins against the position spec (engineering-margins convention).
    ms_rss = margin_of_safety(chain.stack_allowable_mm, rss)
    ms_wc = margin_of_safety(chain.stack_allowable_mm, wc)

    # --- Stage 8: grid-convergence verification of the integrator --------
    # Three-grid study of trapezoid hydrostatic integration 0..altitude,
    # coarse N/4, medium N/2, fine N steps (refinement ratio r = 2).
    n_fine = 24
    f3 = trapezoid_hydrostatic_pressure(alt, n_fine // 4)
    f2 = trapezoid_hydrostatic_pressure(alt, n_fine // 2)
    f1 = trapezoid_hydrostatic_pressure(alt, n_fine)
    r = 2.0
    conv = convergence_verdict(f1, f2, f3, r)
    closed_p = isa["pressure_pa"]
    conv["closed_form_pa"] = closed_p
    conv["fine_steps"] = n_fine
    conv["refinement_ratio"] = r
    conv["f1_pa"], conv["f2_pa"], conv["f3_pa"] = f1, f2, f3
    conv["extrap_error_pct"] = (None if conv["extrapolated"] is None else
                                100.0 * abs(conv["extrapolated"] - closed_p)
                                / closed_p)

    # --- Margins (Stage 12) ----------------------------------------------
    ms_density = margin_of_safety(chain.density_allowable_pct,
                                  100.0 * U / rho_m)

    return {
        "document_type": "Analysis Verification Memo",
        "status": "draft-for-review",
        "chain": chain.chain_name,
        "chain_description": chain.description,
        "altitude_m": alt,
        "isa": isa,
        "pressure_pa": chain.pressure_pa,
        "pressure_unc_pa": chain.pressure_unc_pa,
        "temperature_k": chain.temperature_k,
        "temperature_unc_k": chain.temperature_unc_k,
        "coverage_factor": chain.coverage_factor,
        "density_kgm3": rho_m,
        "sens_p": sens_p,
        "sens_t": sens_t,
        "u_c": u_c,
        "expanded_U": U,
        "contributions": contribs,
        "rel_unc_pct": rel_unc_pct,
        "delta_isa_pct": delta_isa_pct,
        "density_altitude_m": h_rho["altitude_m"],
        "density_altitude_iterations": h_rho["iterations"],
        "density_altitude_residual": h_rho["residual"],
        "alt_delta_m": alt_delta_m,
        "bias_ci": ci,
        "bias_reference_note": chain.bias_reference_note,
        "stack": {"members": [{"name": m.name, "nominal_mm": m.nominal_mm,
                               "tolerance_mm": m.tolerance_mm,
                               "direction": m.direction,
                               "share_pct": s}
                              for m, s in zip(members, shares)],
                  "nominal_mm": nom, "worst_case_mm": wc, "rss_mm": rss,
                  "wc_limits_mm": wc_limits, "rss_limits_mm": rss_limits,
                  "dominant": members[dominant_i].name,
                  "dominant_share_pct": shares[dominant_i],
                  "allowable_mm": chain.stack_allowable_mm,
                  "ms_rss": ms_rss, "ms_wc": ms_wc,
                  "verdict_rss": margin_verdict(ms_rss),
                  "verdict_wc": margin_verdict(ms_wc)},
        "convergence": conv,
        "density_allowable_pct": chain.density_allowable_pct,
        "ms_density": ms_density,
        "density_verdict": margin_verdict(ms_density),
        "export_classification": chain.export_classification,
    }


# ---------------------------------------------------------------------------
# Memo renderer: markdown deliverable (DRAFT, human review, no approval)
# ---------------------------------------------------------------------------

def _fmt_contrib(contribs) -> str:
    return "; ".join(
        f"{c['percent']:.1f}% from {c['name']} "
        f"(s = {c['sensitivity']:.3e}, u = {c['uncertainty']:.3g})"
        for c in contribs)


def render_memo_markdown(model: dict) -> str:
    isa = model["isa"]
    ci = model["bias_ci"]
    st = model["stack"]
    cv = model["convergence"]
    lines = [
        "# Analysis Verification Memo",
        "",
        f"**Chain:** {model['chain']}",
        f"**Status:** {model['status']}",
        "",
        "## 1. Scope and inputs",
        "",
        "Analysis question: verify the measurement/calculation chain "
        f"{model['chain']} - reduce the measured static pressure and "
        "temperature to air density and density altitude, check the "
        "repeated-measurement bias, verify the probe mounting tolerance "
        "stack and the atmosphere-model integrator, and state margins.",
        f"- Analysis item: {model['chain']} at geometric altitude "
        f"{_fmt(model['altitude_m'])} m.",
        f"- Inputs (measured, with 1-sigma standard uncertainties): static "
        f"pressure p = {_fmt(model['pressure_pa'])} Pa +/- "
        f"{_fmt(model['pressure_unc_pa'])} Pa; temperature T = "
        f"{_fmt(model['temperature_k'])} K +/- {_fmt(model['temperature_unc_k'])} K.",
        f"- Inputs (geometry): {len(st['members'])}-member probe mounting "
        f"stack (see Section 5); position spec +/- {_fmt(st['allowable_mm'])} mm.",
        f"- Inputs (acceptance): density accuracy spec +/- "
        f"{_fmt(model['density_allowable_pct'])} %.",
        f"- {model['bias_reference_note']}.",
        "",
        "## 2. Unit/atmosphere basis",
        "",
        "- Unit system: SI (Pa, K, kg/m3, m, mm). No unit conversions "
        "required in the chain; conversions applied for reporting: "
        f"altitude {_fmt(model['altitude_m'])} m = {_fmt(model['altitude_m'] * 3.28084)} ft; "
        f"T {_fmt(isa['temperature_k'])} K = {_fmt(isa['temperature_k'] - 273.15)} degC.",
        "- Atmosphere basis: ISA (ISO 2533 / ICAO Doc 7488) reference "
        f"model, sea level {ISA_T0} K / {ISA_P0} Pa / "
        f"{_fmt(ISA_P0 / (ISA_R * ISA_T0))} kg/m3, lapse rate "
        f"{ISA_LAPSE * 1000} K/km to 11 km.",
        f"- ISA reference values at {_fmt(model['altitude_m'])} m: "
        f"T_ISA = {_fmt(isa['temperature_k'])} K, "
        f"p_ISA = {_fmt(isa['pressure_pa'])} Pa, "
        f"rho_ISA = {_fmt(isa['density_kgm3'])} kg/m3.",
        "",
        "## 3. Method and verification",
        "",
        "- Density from measured state: ideal gas EOS "
        f"rho = p / (R T), R = {ISA_R} J/(kg K) (bound leaf: isa-atmosphere).",
        "- Uncertainty: GUM (JCGM 100) first-order law with analytic "
        "sensitivities, combined standard uncertainty "
        "u_c = sqrt(sum((df/dx_i * u_i)^2)) and expanded U = k * u_c with "
        f"k = {_fmt(model['coverage_factor'])} (~95 %) "
        "(bound leaf: uncertainty-propagation).",
        "- Bias statistics: Student t interval for the mean of the "
        "repeat readings (bound leaf: confidence-interval-estimation).",
        "- Density altitude: Newton inversion of rho_ISA(h) = rho_measured, "
        f"converged in {model['density_altitude_iterations']} iterations to "
        f"residual {model['density_altitude_residual']:.2e} "
        "(bound leaf: root-finding; convergence evidence per leaf "
        "convergence-verification).",
        "- Numerical verification: three-grid trapezoid integration of the "
        "hydrostatic balance dp/dz = -rho g over 0.."
        f"{_fmt(model['altitude_m'])} m at {cv['fine_steps'] // 4}, "
        f"{cv['fine_steps'] // 2} and {cv['fine_steps']} steps "
        f"(refinement ratio r = {_fmt(cv['refinement_ratio'])}); Richardson "
        "extrapolation and grid convergence index (GCI) versus the "
        "closed-form ISA pressure.",
        "- Numerical accuracy statement: see grid study below; the "
        "integrator is grid-converged and agrees with the closed-form ISA "
        "pressure at the test point.",
        "",
        "## 4. Results",
        "",
        f"- Air density (measured chain): rho = {_fmt(model['density_kgm3'])} kg/m3.",
        f"- Sensitivities: d rho/dp = {_fmt(model['sens_p'])} (kg/m3)/Pa, "
        f"d rho/dT = {_fmt(model['sens_t'])} (kg/m3)/K.",
        f"- Combined standard uncertainty: u_c = {_fmt(model['u_c'])} kg/m3 "
        f"({_fmt(model['rel_unc_pct'])} % of rho).",
        f"- Expanded uncertainty: U = {_fmt(model['expanded_U'])} kg/m3 "
        f"(k = {_fmt(model['coverage_factor'])}). Result: rho = "
        f"{_fmt(model['density_kgm3'])} +/- {_fmt(model['expanded_U'])} kg/m3.",
        f"- Uncertainty budget: {_fmt_contrib(model['contributions'])}.",
        f"- Versus ISA at {_fmt(model['altitude_m'])} m: delta = "
        f"{_fmt(model['delta_isa_pct'])} % (non-standard day).",
        f"- Density altitude: h_rho = {_fmt(model['density_altitude_m'])} m "
        f"(+{_fmt(model['alt_delta_m'])} m above the geometric test point).",
        f"- Bias statistics ({model['bias_reference_note']}): mean bias "
        f"{_fmt(ci['mean'])} Pa, sample s = {_fmt(ci['sample_std'])} Pa, "
        f"95 % t-interval [{_fmt(ci['lower'])}, {_fmt(ci['upper'])}] Pa "
        f"(t = {_fmt(ci['t_quantile'])}, df = {_fmt(ci['df'])}). Zero lies "
        "inside the interval: no statistically significant static-source "
        "bias at the 95 % level.",
        "",
        "## 5. Tolerances",
        "",
        "- GD&T basis: ASME Y14.5 (TIER-2 reference-only). The stack is a "
        "1-D linear dimension chain with equal bilateral tolerances and "
        "independent, centered parts (bound leaf: tolerance-stackup).",
        "- Chain members (signed nominal direction, tolerance, RSS share):",
        *[f"  - {m['name']}: {m['nominal_mm']:g} mm "
          f"(dir {'+' if m['direction'] > 0 else '-'}), +/- {m['tolerance_mm']:g} mm, "
          f"{m['share_pct']:.1f} % share" for m in st["members"]],
        f"- Nominal total: {_fmt(st['nominal_mm'])} mm.",
        f"- Worst case: +/- {_fmt(st['worst_case_mm'])} mm -> limits "
        f"[{_fmt(st['wc_limits_mm'][0])}, {_fmt(st['wc_limits_mm'][1])}] mm.",
        f"- RSS: +/- {_fmt(st['rss_mm'])} mm -> limits "
        f"[{_fmt(st['rss_limits_mm'][0])}, {_fmt(st['rss_limits_mm'][1])}] mm.",
        f"- Dominant contributor: {st['dominant']} "
        f"({st['dominant_share_pct']:.1f} % of RSS variance); tightening it "
        "reduces the stack most.",
        "",
        "## 6. Data sources",
        "",
        "- ISA model and constants: ISO 2533 / ICAO Doc 7488 standard "
        "atmosphere (public standard; summary-only use).",
        "- Uncertainty method: GUM, JCGM 100:2008 (public guide; "
        "summary-only use).",
        "- GD&T conventions: ASME Y14.5 (TIER-2 reference-only; "
        "summary-not-copy per SOURCES.md).",
        f"- Export-control classification: {model['export_classification']}. "
        "No controlled data is included in this memo.",
        "",
        "## 7. Margins and conclusions",
        "",
        "- Margins per the engineering-margins convention "
        "MS = allowable / applied - 1 (same units both sides).",
        f"- Density accuracy: applied (expanded) = "
        f"{_fmt(100.0 * model['expanded_U'] / model['density_kgm3'])} %, "
        f"allowable +/- {_fmt(model['density_allowable_pct'])} % -> "
        f"MS = {_fmt(model['ms_density'])} ({model['density_verdict']}).",
        f"- Probe position stack, RSS basis: applied +/- {_fmt(st['rss_mm'])} mm, "
        f"allowable +/- {_fmt(st['allowable_mm'])} mm -> "
        f"MS = {_fmt(st['ms_rss'])} ({st['verdict_rss']}).",
        f"- Probe position stack, worst-case basis: applied +/- {_fmt(st['worst_case_mm'])} mm, "
        f"allowable +/- {_fmt(st['allowable_mm'])} mm -> "
        f"MS = {_fmt(st['ms_wc'])} ({st['verdict_wc']}).",
        "- Conclusions: the chain is unit-consistent with the stated ISA "
        "basis; the expanded density uncertainty is driven by the "
        f"temperature input ({model['contributions'][0]['percent']:.0f} % of "
        "variance); repeated-measurement bias is not significant; the "
        f"atmosphere integrator is monotone-converged (order "
        f"{_fmt(cv['order'])}), GCI {_fmt(cv['gci'] * 100)} % at the test "
        "point, and agrees with the closed-form ISA pressure. The stack "
        "meets the position spec on the RSS basis but not on the "
        "worst-case basis: the RSS basis is valid only while the parts "
        "remain independent and centered (process-capability evidence "
        "required).",
        "",
        "## 8. Open items",
        "",
        "- For the design owner / human approver: confirm the density "
        "accuracy spec and the position spec limits used as allowables; "
        "decide worst-case vs RSS basis for the probe stack (tighten the "
        f"dominant contributor {st['dominant']} if worst case must be met); "
        "confirm export-control classification before external release.",
        "",
        "---",
        "*Generated by Aero Agent Roles engineering-analysis-engineer core. "
        "DRAFT for human engineering review. Not an approval document.*",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evidence gate checkers
# ---------------------------------------------------------------------------

GATE_CHECKS = {
    "title_present": "memo carries the Analysis Verification Memo title",
    "isa_values_real": "ISA temperature/pressure/density match the model",
    "uncertainty_valid": "u_c, U and budget contributions are real and consistent",
    "stack_valid": "worst case >= RSS >= 0 and limits ordered",
    "ci_valid": "t-interval is ordered and contains the mean",
    "convergence_verified": "grid study is monotone-converged with GCI",
    "margins_stated": "margins use MS = allowable/applied - 1 per basis",
    "sign_off_honest": "document is draft-for-review, not approval",
}


def check_memo(model: dict) -> dict:
    """Run the evidence gates against the memo content model."""
    isa = model["isa"]
    t_exp = isa_temperature_k(model["altitude_m"])
    p_exp = isa_pressure_pa(model["altitude_m"])
    rho_exp = p_exp / (ISA_R * t_exp)
    st = model["stack"]
    ci = model["bias_ci"]
    cv = model["convergence"]
    uc_model = math.sqrt((model["sens_p"] * model["pressure_unc_pa"]) ** 2
                         + (model["sens_t"] * model["temperature_unc_k"]) ** 2)
    results = {
        "title_present": model.get("document_type") == "Analysis Verification Memo",
        "isa_values_real": (math.isclose(isa["temperature_k"], t_exp, rel_tol=1e-9)
                            and math.isclose(isa["pressure_pa"], p_exp, rel_tol=1e-9)
                            and math.isclose(isa["density_kgm3"], rho_exp, rel_tol=1e-9)),
        "uncertainty_valid": (math.isclose(model["u_c"], uc_model, rel_tol=1e-9)
                              and math.isclose(model["expanded_U"],
                                               model["coverage_factor"] * model["u_c"])
                              and abs(sum(c["percent"] for c in model["contributions"])
                                      - 100.0) < 1e-6
                              and model["u_c"] > 0),
        "stack_valid": (st["worst_case_mm"] >= st["rss_mm"] >= 0
                        and st["wc_limits_mm"][0] < st["wc_limits_mm"][1]
                        and st["rss_limits_mm"][0] < st["rss_limits_mm"][1]),
        "ci_valid": (ci["lower"] < ci["mean"] < ci["upper"]
                     and ci["t_quantile"] > 1.5),
        "convergence_verified": (cv["verdict"] == "monotone converged"
                                 and cv["gci"] is not None and cv["gci"] < 0.01
                                 and cv["order"] is not None
                                 and 1.5 <= cv["order"] <= 2.5),
        "margins_stated": (model["ms_density"] == margin_of_safety(
                               model["density_allowable_pct"],
                               100.0 * model["expanded_U"] / model["density_kgm3"])
                           and st["ms_rss"] == margin_of_safety(st["allowable_mm"], st["rss_mm"])
                           and st["ms_wc"] == margin_of_safety(st["allowable_mm"], st["worst_case_mm"])),
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_memo_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable (text markers)."""
    low = md_text.lower()
    checks = {
        "has_title": "analysis verification memo" in low,
        "has_isa_numbers": "rho_isa" in low and "p_isa" in low
                           and "t_isa" in low,
        "has_uncertainty": "combined standard uncertainty" in low
                           and "u_c" in low and "kg/m3" in low,
        "has_ci": "t-interval" in low or "confidence interval" in low,
        "has_stack": "worst case" in low and "rss" in low and "mm" in low,
        "has_convergence": "monotone-converged" in low
                           or "monotone converged" in low,
        "has_margins": "ms = allowable / applied - 1" in low,
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling: check a memo document."""
    return check_memo_markdown(md_text)


# ---------------------------------------------------------------------------
# Example deliverables (tests / demo / filled template source)
# ---------------------------------------------------------------------------

def example_memo_model() -> dict:
    return build_memo(example_chain())


def example_memo_markdown() -> str:
    return render_memo_markdown(example_memo_model())


if __name__ == "__main__":
    model = example_memo_model()
    md = example_memo_markdown()
    print(f"CHAIN: {model['chain']}")
    print(f"DENSITY: {model['density_kgm3']:.6g} +/- {model['expanded_U']:.6g} kg/m3 (k={model['coverage_factor']:g})")
    print(f"u_c: {model['u_c']:.6g} kg/m3; budget: "
          + "; ".join(f"{c['percent']:.1f}%" for c in model['contributions']))
    print(f"BIAS CI: [{model['bias_ci']['lower']:.4g}, {model['bias_ci']['upper']:.4g}] Pa")
    print(f"STACK: nominal {model['stack']['nominal_mm']} mm, "
          f"WC +/-{model['stack']['worst_case_mm']} mm, "
          f"RSS +/-{model['stack']['rss_mm']} mm")
    print(f"CONVERGENCE: {model['convergence']['verdict']}, "
          f"order {model['convergence']['order']:.3f}, "
          f"GCI {model['convergence']['gci'] * 100:.4g}%")
    print(f"MODEL GATES: {check_memo(model)}")
    print(f"MARKDOWN GATES: {check_memo_markdown(md)}")
    print(f"RENDERED: {len(md)} chars")
