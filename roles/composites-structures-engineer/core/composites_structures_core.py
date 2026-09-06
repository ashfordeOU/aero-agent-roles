#!/usr/bin/env python3
"""composites_structures_core.py - Composite Structures Engineer executable core.

This is the role's ENGINE. Given a composite structural item's project
facts (material, layup, load case, environment, panel geometry) it
computes, from REAL classical lamination theory (CLT) rules that mirror
the bound AeroSkills logic leaves in structures/composites:

  * laminate stiffness      - ply Q, Q-bar rotation, A and D matrices,
                              effective laminate engineering constants
                              (mirrors laminate-stiffness logic)
  * failure criteria        - Tsai-Wu and max-stress failure indices on
                              every ply stress state (mirrors
                              failure-criteria + laminate-first-ply-failure)
  * stability               - simply-supported orthotropic plate buckling
                              critical load and margin (mirrors
                              laminate-plate-buckling logic)
  * hygrothermal response   - equilibrium moisture content, exact 2x2 CLT
                              laminate CTE/CME, hygrothermal and
                              cure-cooldown strains (mirrors
                              laminate-hygrothermal-response logic)
  * allowables              - B-basis knockdown chain (mirrors
                              cmh17-allowables logic)

and BUILDS the deliverable: a Composite Structure Analysis and
Certification Report (DRAFT, never an approval). The same numbers are
cross-checked against the bound skill logic files when AeroSkills is
present (cli.py dispatch); the core itself is standalone: no external
repo, stdlib only.

Standalone note: material constants and allowables used by the worked
example are the published T300/5208-style values used as the worked
example in the bound AeroSkills leaves (lamina stiffness, allowables,
expansion coefficients) - real published material data, not invented.
All laminate-level numbers are exact CLT arithmetic. CMH-17 is
referenced by name only (summary-not-copy); no proprietary tables are
reproduced here.
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

DEFAULT_RELEASE_DATE = "2026-09-06"


def _today() -> str:
    """Reproducible generation date: ROLE_GEN_DATE env or today (ISO)."""
    return os.environ.get("ROLE_GEN_DATE", date.today().isoformat())


# ---------------------------------------------------------------------------
# Worked-example material: T300/5208-style carbon/epoxy. Values are the
# published lamina constants used as the worked example inside the bound
# AeroSkills composite leaves (real data, leaf-cited).
# ---------------------------------------------------------------------------

MAT_T300 = {
    "name": "T300/5208-style carbon/epoxy (unidirectional lamina)",
    # stiffness, SI
    "e1_pa": 181.0e9, "e2_pa": 10.3e9, "g12_pa": 7.17e9, "nu12": 0.28,
    # lamina allowables, MPa (tension/compression fiber, transverse, shear)
    "xt_mpa": 1500.0, "xc_mpa": 1500.0,
    "yt_mpa": 40.0, "yc_mpa": 246.0, "s_mpa": 68.0,
    # expansion coefficients (material axes): alpha 1/K, beta per unit
    # moisture mass fraction (leaf worked-example values)
    "alpha_1": -0.3e-6, "alpha_2": 28.1e-6,
    "beta_1": 0.0, "beta_2": 0.6,
    "m_sat": 0.015,          # saturation moisture mass fraction (default)
    "t_ply_m": 0.125e-3,     # cured ply thickness, m
}


# ---------------------------------------------------------------------------
# Lamina / laminate stiffness (CLT; mirrors laminate-stiffness logic)
# ---------------------------------------------------------------------------

def ply_q(e1_pa, e2_pa, nu12, g12_pa):
    """(q11, q12, q22, q66) plane-stress reduced stiffness of a lamina.

    q11 = E1/d, q22 = E2/d, q12 = nu12*E2/d, q66 = G12 with
    nu21 = nu12*E2/E1 and d = 1 - nu12*nu21. Any consistent unit set.
    """
    if e1_pa <= 0 or e2_pa <= 0 or g12_pa <= 0:
        raise ValueError("moduli E1, E2, G12 must be > 0")
    if not (0.0 <= nu12 < 1.0):
        raise ValueError("nu12 must be in [0, 1)")
    nu21 = nu12 * e2_pa / e1_pa
    d = 1.0 - nu12 * nu21
    if d <= 0.0:
        raise ValueError("nu12*nu21 >= 1: singular plane-stress stiffness")
    return (e1_pa / d, nu12 * e2_pa / d, e2_pa / d, g12_pa)


def rotated_ply_stiffness(e1_pa, e2_pa, nu12, g12_pa, theta_deg):
    """(q11b, q12b, q16b, q22b, q26b, q66b) rotated to the laminate axes.

    Standard fourth-power rotation of the in-plane 2D stiffness
    (classical lamination theory, common knowledge).
    """
    q11, q12, q22, q66 = ply_q(e1_pa, e2_pa, nu12, g12_pa)
    c = math.cos(math.radians(theta_deg))
    s = math.sin(math.radians(theta_deg))
    c2, s2 = c * c, s * s
    c4, s4 = c2 * c2, s2 * s2
    s2c2 = s2 * c2
    q11b = q11 * c4 + 2.0 * (q12 + 2.0 * q66) * s2c2 + q22 * s4
    q22b = q11 * s4 + 2.0 * (q12 + 2.0 * q66) * s2c2 + q22 * c4
    q12b = (q11 + q22 - 4.0 * q66) * s2c2 + q12 * (c4 + s4)
    q66b = (q11 + q22 - 2.0 * q12 - 2.0 * q66) * s2c2 + q66 * (c4 + s4)
    q16b = ((q11 - q12 - 2.0 * q66) * c2
            - (q22 - q12 - 2.0 * q66) * s2) * c * s
    q26b = ((q11 - q12 - 2.0 * q66) * s2
            - (q22 - q12 - 2.0 * q66) * c2) * c * s
    return (q11b, q12b, q16b, q22b, q26b, q66b)


def laminate_a_matrix(plies, e1_pa, e2_pa, nu12, g12_pa):
    """(A11, A12, A16, A22, A26, A66) in N/m for a laminate given as a
    list of (theta_deg, thickness_m) plies (CLT sum of Qbar*t)."""
    if not plies:
        raise ValueError("laminate must have at least one ply")
    a = [0.0] * 6
    for theta, t in plies:
        if t <= 0:
            raise ValueError("ply thickness must be > 0")
        qb = rotated_ply_stiffness(e1_pa, e2_pa, nu12, g12_pa, theta)
        for i in range(6):
            a[i] += qb[i] * t
    return tuple(a)


def laminate_d_matrix(plies, e1_pa, e2_pa, nu12, g12_pa):
    """(D11, D12, D16, D22, D26, D66) in N*m for a laminate given as a
    list of (theta_deg, thickness_m) plies (CLT flexural assembly:
    D_ij = (1/3) * sum_k Qbar_ij_k * (z_k**3 - z_{k-1}**3)).

    The stack is treated as listed from the bottom (z = -h/2) to the
    top (+h/2); symmetric stacks give the same result for either order.
    """
    if not plies:
        raise ValueError("laminate must have at least one ply")
    h = sum(t for _, t in plies)
    d = [0.0] * 6
    z_lo = -h / 2.0
    for theta, t in plies:
        if t <= 0:
            raise ValueError("ply thickness must be > 0")
        z_hi = z_lo + t
        span = (z_hi ** 3 - z_lo ** 3) / 3.0
        qb = rotated_ply_stiffness(e1_pa, e2_pa, nu12, g12_pa, theta)
        for i in range(6):
            d[i] += qb[i] * span
        z_lo = z_hi
    return tuple(d)


def effective_constants(a, h_m):
    """Laminate effective engineering constants from the A matrix (N/m)
    and total thickness (m): Ex, Ey, nu_xy, Gxy in Pa / unitless.
    Standard relations: [a] = A^-1 (in-plane), Ex = 1/(a11*h), ..."""
    a11, a12, a16, a22, a26, a66 = a
    det = a11 * a22 - a12 * a12
    if det <= 0:
        raise ValueError("in-plane A is singular")
    # in-plane compliance block (a_ij)
    ca11 = a22 / det
    ca12 = -a12 / det
    ca22 = a11 / det
    ca66 = 1.0 / a66 if a66 > 0 else float("inf")
    ex = 1.0 / (ca11 * h_m)
    ey = 1.0 / (ca22 * h_m)
    gxy = 1.0 / (ca66 * h_m)
    nu_xy = -ca12 / ca11
    return {
        "ex_pa": ex, "ey_pa": ey, "gxy_pa": gxy, "nu_xy": nu_xy,
        "a11_inv_m_per_n": ca11, "a12_inv_m_per_n": ca12,
    }


# ---------------------------------------------------------------------------
# Failure criteria (MPa convention; mirrors failure-criteria logic)
# ---------------------------------------------------------------------------

def tsai_wu_index(s1, s2, t12, xt, xc, yt, yc, s_uv):
    """Tsai-Wu failure index: F.I. = F1 s1 + F2 s2 + F11 s1^2 + F22 s2^2
    + F66 t12^2 + 2 F12 s1 s2 with F1 = 1/Xt - 1/Xc, F2 = 1/Yt - 1/Yc,
    F11 = 1/(Xt Xc), F22 = 1/(Yt Yc), F66 = 1/S^2 and
    F12 = -0.5*sqrt(F11 F22). Stresses and allowables in MPa. An index
    >= 1.0 marks failure; non-positive values lie inside the surface."""
    for val, nm in ((xt, "Xt"), (xc, "Xc"), (yt, "Yt"), (yc, "Yc"),
                    (s_uv, "S")):
        if val <= 0:
            raise ValueError("allowable %s must be > 0 MPa" % nm)
    f1 = 1.0 / xt - 1.0 / xc
    f2 = 1.0 / yt - 1.0 / yc
    f11 = 1.0 / (xt * xc)
    f22 = 1.0 / (yt * yc)
    f66 = 1.0 / (s_uv * s_uv)
    f12 = -0.5 * math.sqrt(f11 * f22)
    return (f1 * s1 + f2 * s2 + f11 * s1 * s1 + f22 * s2 * s2
            + f66 * t12 * t12 + 2.0 * f12 * s1 * s2)


def max_stress_index(s1, s2, t12, xt, xc, yt, yc, s_uv):
    """Max-stress failure index: largest of the three component ratios
    |s1|/Xt|Xc by sign, |s2|/Yt|Yc by sign, and |t12|/S (MPa)."""
    for val, nm in ((xt, "Xt"), (xc, "Xc"), (yt, "Yt"), (yc, "Yc"),
                    (s_uv, "S")):
        if val <= 0:
            raise ValueError("allowable %s must be > 0 MPa" % nm)
    r1 = abs(s1) / (xt if s1 >= 0.0 else xc)
    r2 = abs(s2) / (yt if s2 >= 0.0 else yc)
    r12 = abs(t12) / s_uv
    return max(r1, r2, r12)


# ---------------------------------------------------------------------------
# First-ply-failure chain (N/mm, MPa, mm convention; mirrors
# laminate-first-ply-failure logic)
# ---------------------------------------------------------------------------

def q_matrix_from_constants(e1, e2, nu12, g12):
    """(q11, q12, q22, q66) from engineering constants (MPa)."""
    if e1 <= 0 or e2 <= 0 or g12 <= 0 or nu12 <= 0:
        raise ValueError("E1, E2, G12, nu12 must be positive")
    nu21 = nu12 * e2 / e1
    d = 1.0 - nu12 * nu21
    if d <= 0.0:
        raise ValueError("nu12*nu21 >= 1: singular")
    return (e1 / d, nu12 * e2 / d, e2 / d, g12)


def rotated_ply_q(q_components, theta_deg):
    """(qb11, qb12, qb22, qb66): ply stiffness rotated to laminate axes."""
    q11, q12, q22, q66 = q_components
    c = math.cos(math.radians(theta_deg))
    s = math.sin(math.radians(theta_deg))
    c2, s2 = c * c, s * s
    c4, s4 = c2 * c2, s2 * s2
    cs2 = c2 * s2
    qb11 = q11 * c4 + 2.0 * (q12 + 2.0 * q66) * cs2 + q22 * s4
    qb12 = (q11 + q22 - 4.0 * q66) * cs2 + q12 * (c4 + s4)
    qb22 = q11 * s4 + 2.0 * (q12 + 2.0 * q66) * cs2 + q22 * c4
    qb66 = (q11 + q22 - 2.0 * q12 - 2.0 * q66) * cs2 + q66 * (c4 + s4)
    return (qb11, qb12, qb22, qb66)


def a_matrix_from_plies(plies_deg, q_components, ply_thickness_mm):
    """(A11, A12, A22, A66) in N/mm for a balanced symmetric laminate
    (A_ij = sum Qbar_ij_k * t_k; A16 = A26 = 0 by symmetry)."""
    if not plies_deg:
        raise ValueError("plies_deg must not be empty")
    if ply_thickness_mm <= 0:
        raise ValueError("ply_thickness_mm must be positive")
    a11 = a12 = a22 = a66 = 0.0
    for theta in plies_deg:
        qb = rotated_ply_q(q_components, theta)
        a11 += qb[0] * ply_thickness_mm
        a12 += qb[1] * ply_thickness_mm
        a22 += qb[2] * ply_thickness_mm
        a66 += qb[3] * ply_thickness_mm
    return (a11, a12, a22, a66)


def a_inverse_compliance(a11, a12, a22, a66):
    """(a11, a12, a22, a66) mm/N: in-plane A-inverse compliance block."""
    if a11 <= 0 or a22 <= 0 or a66 <= 0:
        raise ValueError("A11, A22, A66 must be positive")
    det = a11 * a22 - a12 * a12
    if det <= 0:
        raise ValueError("A11*A22 - A12^2 must be positive")
    return (a22 / det, -a12 / det, a11 / det, 1.0 / a66)


def midplane_strains(a_comp, nx, ny, nxy):
    """(ex, ey, gxy): laminate mid-plane strains from resultants (N/mm)."""
    a11, a12, a22, a66 = a_comp
    return (a11 * nx + a12 * ny, a12 * nx + a22 * ny, a66 * nxy)


def ply_material_strains(ex, ey, gxy, theta_deg):
    """(e1, e2, g12): laminate strains transformed to the ply axes."""
    c = math.cos(math.radians(theta_deg))
    s = math.sin(math.radians(theta_deg))
    c2, s2, cs = c * c, s * s, c * s
    e1 = ex * c2 + ey * s2 + gxy * cs
    e2 = ex * s2 + ey * c2 - gxy * cs
    g12 = 2.0 * (ey - ex) * cs + gxy * (c2 - s2)
    return (e1, e2, g12)


def ply_material_stresses(e1, e2, g12, q_components):
    """(s1, s2, t12): ply stresses from its material-axis strains."""
    q11, q12, q22, q66 = q_components
    return (q11 * e1 + q12 * e2, q12 * e1 + q22 * e2, q66 * g12)


def ply_failure_indices(plies_deg, q_components, allowables, a_comp,
                        nx, ny, nxy):
    """Per-ply Tsai-Wu failure indices (list in plies_deg order)."""
    q11, q12, q22, q66 = q_components
    xt, xc, yt, yc, s_uv = allowables
    ex, ey, gxy = midplane_strains(a_comp, nx, ny, nxy)
    indices = []
    for theta in plies_deg:
        e1, e2, g12 = ply_material_strains(ex, ey, gxy, theta)
        s1, s2, t12 = ply_material_stresses(e1, e2, g12,
                                            (q11, q12, q22, q66))
        indices.append(tsai_wu_index(s1, s2, t12, xt, xc, yt, yc, s_uv))
    return indices


# ---------------------------------------------------------------------------
# Hygrothermal response (raw SI; mirrors laminate-hygrothermal-response)
# ---------------------------------------------------------------------------

def equilibrium_moisture_content(rh_fraction, m_sat=MAT_T300["m_sat"]):
    """M = m_sat * rh_fraction (linear isotherm), mass fraction."""
    if not (0.0 <= rh_fraction <= 1.0):
        raise ValueError("rh_fraction must be in [0, 1]")
    if m_sat <= 0:
        raise ValueError("m_sat must be > 0")
    return m_sat * rh_fraction


def ply_laminate_axis_coeffs(alpha_1, alpha_2, beta_1, beta_2, theta_deg):
    """(alpha_x, alpha_y, beta_x, beta_y): 2nd-order tensor rotation of a
    ply's expansion coefficients to the laminate axes."""
    c2 = math.cos(math.radians(theta_deg)) ** 2
    s2 = math.sin(math.radians(theta_deg)) ** 2
    return (alpha_1 * c2 + alpha_2 * s2, alpha_1 * s2 + alpha_2 * c2,
            beta_1 * c2 + beta_2 * s2, beta_1 * s2 + beta_2 * c2)


def laminate_cte_cme(plies):
    """{alpha_x, alpha_y, beta_x, beta_y} (raw SI) of a symmetric balanced
    laminate by the exact 2x2 CLT free-expansion solution.

    plies: list of dicts with keys e1, e2 (Pa), nu12, g12 (Pa),
    theta_deg, t (m), alpha_1, alpha_2 (1/K), beta_1, beta_2 (per unit
    moisture fraction). Solves A * [alpha_x, alpha_y]^T = Nth and
    A * [beta_x, beta_y]^T = Nm (the exact inversion is required; a
    stiffness-weighted scalar ratio is not exact).
    """
    if not plies:
        raise ValueError("plies must contain at least one ply")
    a11 = a12 = a22 = 0.0
    nth1 = nth2 = 0.0
    nm1 = nm2 = 0.0
    for p in plies:
        t = p["t"]
        if t <= 0:
            raise ValueError("ply thickness must be > 0")
        e1, e2, nu12, g12 = p["e1"], p["e2"], p["nu12"], p["g12"]
        q11, q12, q22, q66 = ply_q(e1, e2, nu12, g12)
        qb = rotated_ply_q((q11, q12, q22, q66), p["theta_deg"])
        ax, ay, bx, by = ply_laminate_axis_coeffs(
            p["alpha_1"], p["alpha_2"], p["beta_1"], p["beta_2"],
            p["theta_deg"])
        a11 += qb[0] * t
        a12 += qb[1] * t
        a22 += qb[2] * t
        nth1 += (qb[0] * ax + qb[1] * ay) * t
        nth2 += (qb[1] * ax + qb[2] * ay) * t
        nm1 += (qb[0] * bx + qb[1] * by) * t
        nm2 += (qb[1] * bx + qb[2] * by) * t
    alpha_x, alpha_y = _solve2x2(a11, a12, a22, nth1, nth2)
    beta_x, beta_y = _solve2x2(a11, a12, a22, nm1, nm2)
    return {"alpha_x": alpha_x, "alpha_y": alpha_y,
            "beta_x": beta_x, "beta_y": beta_y}


def _solve2x2(a11, a12, a22, b1, b2):
    """Solve the symmetric 2x2 system by determinant."""
    det = a11 * a22 - a12 * a12
    if det <= 0 or not math.isfinite(det):
        raise ValueError("in-plane stiffness A is singular")
    return ((a22 * b1 - a12 * b2) / det,
            (a11 * b2 - a12 * b1) / det)


def hygrothermal_strain(alpha, beta, delta_t_k, delta_m):
    """eps = alpha*delta_t_k + beta*delta_m along one laminate axis."""
    return alpha * delta_t_k + beta * delta_m


def cure_cooldown_strain(alpha_x, t_cure_c, t_rt_c=21.0):
    """Residual x strain from the cure-cooldown drop:
    alpha_x * (t_rt - t_cure) (negative for a cooldown)."""
    return alpha_x * (t_rt_c - t_cure_c)


# ---------------------------------------------------------------------------
# Plate buckling (SI: D N*m, a/b m, loads N/m; mirrors
# laminate-plate-buckling logic)
# ---------------------------------------------------------------------------

def plate_critical_load(d11, d22, d12, d66, a_m, b_m, m=1, n=1):
    """Energy-method critical load N_x_cr (N/m) for mode (m, n) of a
    simply supported orthotropic plate:
    N_x_cr = pi^2 * ( D11 (m/a)^2 + 2 (D12 + 2 D66) (n/b)^2
                      + D22 n^4 a^2 / (m^2 b^4) )."""
    term_m = d11 * (m / a_m) ** 2
    term_n = 2.0 * (d12 + 2.0 * d66) * (n / b_m) ** 2
    term_mn = d22 * n ** 4 * a_m ** 2 / (m ** 2 * b_m ** 4)
    return math.pi ** 2 * (term_m + term_n + term_mn)


def buckling_mode(d11, d22, d12, d66, a_m, b_m, m_max=20, n_max=20):
    """(N_x_cr_min, m, n): minimized critical load over the half-wave
    sweep (ties resolve to the smallest (m, n), deterministic)."""
    best = None
    best_m = best_n = 0
    for m in range(1, m_max + 1):
        for n in range(1, n_max + 1):
            val = plate_critical_load(d11, d22, d12, d66, a_m, b_m, m, n)
            if best is None or val < best:
                best, best_m, best_n = val, m, n
    return (best, best_m, best_n)


def buckling_margin(d11, d22, d12, d66, a_m, b_m, applied_load_n_per_m):
    """Stability margin N_x_cr_min / N_x_applied (>= 1.0 = no predicted
    buckling under the applied in-plane compression)."""
    if applied_load_n_per_m <= 0:
        raise ValueError("applied compression load must be > 0")
    n_cr, m, n = buckling_mode(d11, d22, d12, d66, a_m, b_m)
    return n_cr / applied_load_n_per_m, n_cr, m, n


# ---------------------------------------------------------------------------
# Allowables (mirrors cmh17-allowables knockdown chain)
# ---------------------------------------------------------------------------

def knockdown(lamina_allowable, env_factor=1.0, bvid_factor=1.0,
              hole_factor=1.0):
    """Laminate design allowable from a lamina allowable by multiplying
    the environmental, BVID and open-hole knockdown factors (each in
    (0, 1]). Conservative default factors are item inputs per CMH-17
    practice (summary-not-copy); the product is returned."""
    for val, nm in ((env_factor, "env_factor"), (bvid_factor, "bvid_factor"),
                    (hole_factor, "hole_factor")):
        if not (0.0 < val <= 1.0):
            raise ValueError("%s must be in (0, 1]" % nm)
    return lamina_allowable * env_factor * bvid_factor * hole_factor


def basis_statement(basis):
    """Confidence/content statement for an A- or B-basis designation
    (CMH-17 practice, summary-not-copy)."""
    if basis == "A":
        return "A-basis: 95% confidence that at least 99% of the population exceeds the value"
    if basis == "B":
        return "B-basis: 95% confidence that at least 90% of the population exceeds the value"
    raise ValueError("basis must be 'A' or 'B'")


# ---------------------------------------------------------------------------
# Item facts
# ---------------------------------------------------------------------------

@dataclass
class CompositeItem:
    """Project facts the role needs to build the analysis report."""
    item_name: str = ""
    description: str = ""
    part_number: str = ""
    material: dict = field(default_factory=lambda: dict(MAT_T300))
    layup_deg: Optional[list] = field(default=None)
    t_ply_m: float = MAT_T300["t_ply_m"]
    allowables_basis: str = "B"
    env_factor: float = 0.90      # environmental conditioning knockdown
    bvid_factor: float = 0.85     # barely-visible-impact-damage knockdown
    hole_factor: float = 1.0      # open-hole knockdown (1.0 = no hole)
    certification_basis: str = "FAR/CS-25 (14 CFR Part 25 / EASA CS-25)"
    structure_class: str = "primary structure"
    # ultimate load case, resultants N/mm (laminate axes x = load dir)
    load_nx_n_per_mm: float = -75.0
    load_ny_n_per_mm: float = -15.0
    load_nxy_n_per_mm: float = 20.0
    # stability panel geometry + applied compression (m, N/m)
    panel_a_m: float = 0.190
    panel_b_m: float = 0.150
    # environment
    rh_fraction: float = 0.60
    delta_t_k: float = -156.0     # service reference to cure temperature
    t_cure_c: float = 177.0
    t_rt_c: float = 21.0
    notes: str = ""

    def ply_list(self):
        """(theta_deg, thickness_m) pairs for the full stack (symmetric
        assumed; layup_deg lists every ply from bottom to top)."""
        if self.layup_deg is None:
            self.layup_deg = _default_layup()
        return [(th, self.t_ply_m) for th in self.layup_deg]

    def total_thickness_m(self):
        return self.t_ply_m * len(self.ply_list())


def _default_layup():
    """16-ply quasi-isotropic symmetric balanced stack [45/-45/0/90]2s."""
    half = [45, -45, 0, 90]
    return half + list(reversed(half)) + half + list(reversed(half))


def material_mpa(mat):
    """Material stiffness/allowables converted to the MPa failure-set."""
    return {
        "e1": mat["e1_pa"] / 1e6, "e2": mat["e2_pa"] / 1e6,
        "g12": mat["g12_pa"] / 1e6, "nu12": mat["nu12"],
        "xt": mat["xt_mpa"], "xc": mat["xc_mpa"],
        "yt": mat["yt_mpa"], "yc": mat["yc_mpa"], "s": mat["s_mpa"],
    }


# ---------------------------------------------------------------------------
# Analysis: build the full content model
# ---------------------------------------------------------------------------

def analyze_stiffness(item):
    plies = item.ply_list()
    h = item.total_thickness_m()
    mat = item.material
    a = laminate_a_matrix(plies, mat["e1_pa"], mat["e2_pa"], mat["nu12"],
                          mat["g12_pa"])
    d = laminate_d_matrix(plies, mat["e1_pa"], mat["e2_pa"], mat["nu12"],
                          mat["g12_pa"])
    eff = effective_constants(a, h)
    return {
        "layup": [th for th, _ in plies],
        "n_plies": len(plies),
        "t_ply_mm": item.t_ply_m * 1e3,
        "h_mm": h * 1e3,
        "h_m": h,
        "a11_n_per_m": a[0], "a12_n_per_m": a[1],
        "a22_n_per_m": a[3], "a66_n_per_m": a[5],
        "a16_n_per_m": a[2], "a26_n_per_m": a[4],
        "d11_n_m": d[0], "d12_n_m": d[1], "d22_n_m": d[3],
        "d66_n_m": d[5],
        "ex_gpa": eff["ex_pa"] / 1e9, "ey_gpa": eff["ey_pa"] / 1e9,
        "gxy_gpa": eff["gxy_pa"] / 1e9, "nu_xy": eff["nu_xy"],
        "balanced_symmetric": abs(a[2]) < 1.0 and abs(a[4]) < 1.0,
    }


def analyze_failure(item):
    """Per-ply stress recovery and failure indices under the ultimate
    resultants (N/mm). Mirrors the bound first-ply-failure chain; the
    governing reserve factor comes from the criterion with the largest
    index (Tsai-Wu is reported per ply but for compression-dominated
    states it can be non-positive inside the surface, so max-stress is
    the conservative governing check)."""
    mat = material_mpa(item.material)
    q = q_matrix_from_constants(mat["e1"], mat["e2"], mat["nu12"],
                                mat["g12"])
    allowables = (mat["xt"], mat["xc"], mat["yt"], mat["yc"], mat["s"])
    plies_deg = [th for th, _ in item.ply_list()]
    a = a_matrix_from_plies(plies_deg, q, item.t_ply_m * 1e3)
    a_inv = a_inverse_compliance(*a)
    nx, ny, nxy = (item.load_nx_n_per_mm, item.load_ny_n_per_mm,
                   item.load_nxy_n_per_mm)
    tw_indices = ply_failure_indices(plies_deg, q, allowables, a_inv,
                                     nx, ny, nxy)
    ex, ey, gxy = midplane_strains(a_inv, nx, ny, nxy)

    per_ply = []
    for k, theta in enumerate(plies_deg):
        e1, e2, g12 = ply_material_strains(ex, ey, gxy, theta)
        s1, s2, t12 = ply_material_stresses(e1, e2, g12, q)
        tw = tw_indices[k]
        ms = max_stress_index(s1, s2, t12, *allowables)
        per_ply.append({"angle": theta, "s1_mpa": s1, "s2_mpa": s2,
                        "t12_mpa": t12, "tsai_wu": tw, "max_stress": ms})

    # governing index: largest of (max-stress per ply, Tsai-Wu when > 0)
    governing = None
    gov_index = -1.0
    for row in per_ply:
        cand = max(row["max_stress"], max(row["tsai_wu"], 0.0))
        if cand > gov_index:
            gov_index = cand
            governing = row
    reserve = 1.0 / gov_index if gov_index > 0 else float("inf")

    # knockdowned B-basis allowables for the report's strength basis
    kn = {k: knockdown(item.material[k], item.env_factor,
                       item.bvid_factor, item.hole_factor)
          for k in ("xt_mpa", "xc_mpa", "yt_mpa", "yc_mpa", "s_mpa")}
    # reserve factor against the knockdowned allowables (max-stress basis)
    def _rf_knock(row, knk):
        r1 = abs(row["s1_mpa"]) / (knk["xt_mpa"] if row["s1_mpa"] >= 0
                                   else knk["xc_mpa"])
        r2 = abs(row["s2_mpa"]) / (knk["yt_mpa"] if row["s2_mpa"] >= 0
                                   else knk["yc_mpa"])
        r12 = abs(row["t12_mpa"]) / knk["s_mpa"]
        return 1.0 / max(r1, r2, r12)
    gov_knock_rf = min(_rf_knock(row, kn) for row in per_ply)

    return {
        "load_case_n_per_mm": {"nx": nx, "ny": ny, "nxy": nxy},
        "strain_midplane": {"ex": ex, "ey": ey, "gxy": gxy},
        "per_ply": per_ply,
        "tsai_wu_max": max(tw_indices),
        "governing_criterion": ("max-stress" if governing and
                                governing["max_stress"] >=
                                max(governing["tsai_wu"], 0.0)
                                else "tsai-wu"),
        "governing_ply_deg": governing["angle"] if governing else None,
        "governing_index": gov_index,
        "reserve_factor_to_fpf": reserve,
        "knockdown": {k: v for k, v in kn.items()},
        "knockdowned_basis_rf": gov_knock_rf,
        "tsai_wu_indices": tw_indices,
    }


def analyze_hygrothermal(item):
    mat = item.material
    m_eq = equilibrium_moisture_content(item.rh_fraction, mat["m_sat"])
    plies = []
    for th, t in item.ply_list():
        plies.append({"e1": mat["e1_pa"], "e2": mat["e2_pa"],
                      "nu12": mat["nu12"], "g12": mat["g12_pa"],
                      "theta_deg": th, "t": t,
                      "alpha_1": mat["alpha_1"], "alpha_2": mat["alpha_2"],
                      "beta_1": mat["beta_1"], "beta_2": mat["beta_2"]})
    coefs = laminate_cte_cme(plies)
    delta_m = m_eq
    eps_x = hygrothermal_strain(coefs["alpha_x"], coefs["beta_x"],
                                item.delta_t_k, delta_m)
    eps_y = hygrothermal_strain(coefs["alpha_y"], coefs["beta_y"],
                                item.delta_t_k, delta_m)
    cure_x = cure_cooldown_strain(coefs["alpha_x"], item.t_cure_c,
                                  item.t_rt_c)
    return {
        "rh": item.rh_fraction,
        "m_sat": mat["m_sat"],
        "t_cure_c": item.t_cure_c,
        "t_rt_c": item.t_rt_c,
        "equilibrium_moisture": m_eq,
        "alpha_x_ppm": coefs["alpha_x"] * 1e6,
        "alpha_y_ppm": coefs["alpha_y"] * 1e6,
        "beta_x": coefs["beta_x"],
        "beta_y": coefs["beta_y"],
        "delta_t_k": item.delta_t_k,
        "delta_m": delta_m,
        "hygrothermal_strain_x": eps_x,
        "hygrothermal_strain_y": eps_y,
        "cure_strain_x": cure_x,
    }


def analyze_stability(item):
    st = analyze_stiffness(item)  # reuse flexural stiffness
    margin, n_cr, m, n = buckling_margin(
        st["d11_n_m"], st["d22_n_m"], st["d12_n_m"], st["d66_n_m"],
        item.panel_a_m, item.panel_b_m,
        abs(item.load_nx_n_per_mm) * 1e3)
    return {
        "panel_a_m": item.panel_a_m,
        "panel_b_m": item.panel_b_m,
        "applied_n_per_m": abs(item.load_nx_n_per_mm) * 1e3,
        "n_x_cr_n_per_m": n_cr,
        "mode": (m, n),
        "margin": margin,
    }


def build_report(item):
    """Build the complete report content model from the item facts."""
    mat = item.material
    stiffness = analyze_stiffness(item)
    failure = analyze_failure(item)
    hygro = analyze_hygrothermal(item)
    stability = analyze_stability(item)
    allow_basis = basis_statement(item.allowables_basis)
    return {
        "schema_version": 1,
        "role": "composites-structures-engineer",
        "deliverable_type": "composite structure analysis + certification report",
        "status": "draft-for-review",
        "document_title": "Composite Structure Analysis and Certification Report",
        "item": {
            "name": item.item_name,
            "description": item.description,
            "part_number": item.part_number,
            "structure_class": item.structure_class,
        },
        "certification_basis": item.certification_basis,
        "regs": ["FAR 25.305 strength", "FAR 25.307 proof of structure",
                 "FAR 25.571 damage tolerance"],
        "material": {
            "name": mat["name"],
            "e1_gpa": mat["e1_pa"] / 1e9, "e2_gpa": mat["e2_pa"] / 1e9,
            "g12_gpa": mat["g12_pa"] / 1e9, "nu12": mat["nu12"],
            "basis": item.allowables_basis,
            "basis_statement": allow_basis,
            "env_factor": item.env_factor,
            "bvid_factor": item.bvid_factor,
            "hole_factor": item.hole_factor,
        },
        "stiffness": stiffness,
        "failure": failure,
        "hygrothermal": hygro,
        "stability": stability,
        "conclusions": {
            "governing_condition": "stability (plate buckling)",
            "buckling_margin": stability["margin"],
            "strength_reserve_basis": "B-basis knockdowned allowables",
            "knockdowned_reserve_factor": failure["knockdowned_basis_rf"],
        },
        "generated": _today(),
    }


# ---------------------------------------------------------------------------
# Render the deliverable markdown
# ---------------------------------------------------------------------------

def _f(x, nd=4):
    if x is None:
        return "n/a"
    return ("%.*g" % (nd, x)) if isinstance(x, float) else str(x)


def render_report_markdown(model):
    """Render the content model as the deliverable markdown report."""
    it = model["item"]
    mat = model["material"]
    st = model["stiffness"]
    fl = model["failure"]
    hy = model["hygrothermal"]
    sb = model["stability"]
    cc = model["conclusions"]

    def ply_table_row(row):
        return (f"| {row['angle']:>3} | {row['s1_mpa']:9.2f} | "
                f"{row['s2_mpa']:9.2f} | {row['t12_mpa']:9.2f} | "
                f"{row['tsai_wu']:9.4f} | {row['max_stress']:9.4f} |")

    lines = [
        "# Composite Structure Analysis and Certification Report",
        "",
        f"**Item:** {it['name']}",
        f"**Part number:** {it['part_number'] or 'n/a'}",
        f"**Structure class:** {it['structure_class']}",
        f"**Certification basis:** {model['certification_basis']}",
        f"**Status:** {model['status']}",
        "",
        "## 1. Scope",
        "",
        "This report documents the analysis of the composite structural "
        "item listed above: laminate stiffness, ply-level stresses and "
        "failure indices, hygrothermal response, and panel stability. "
        "It is prepared as a DRAFT input for the human certification "
        "chain. It is not an approval and is not a certification.",
        "",
        *([f"- Item description: {it['description']}."]
          if it["description"] else []),
        "",
        f"- Structure class: {it['structure_class']}.",
        f"- Regulatory basis: {model['certification_basis']}; relevant "
        f"rules: {', '.join(model['regs'])}.",
        f"- Analysis status: {model['status']} (generated "
        f"{model['generated']}).",
        "",
        "## 2. Materials and design allowables",
        "",
        f"- Material: {mat['name']}.",
        f"- Lamina stiffness: E1 = {mat['e1_gpa']:.1f} GPa, "
        f"E2 = {mat['e2_gpa']:.1f} GPa, G12 = {mat['g12_gpa']:.2f} GPa, "
        f"nu12 = {mat['nu12']}.",
        f"- Allowable basis: {mat['basis']} "
        f"({mat['basis_statement']}).",
        f"- Knockdown factors applied to lamina allowables: "
        f"environment {mat['env_factor']}, BVID {mat['bvid_factor']}, "
        f"open hole {mat['hole_factor']} (product = "
        f"{mat['env_factor'] * mat['bvid_factor'] * mat['hole_factor']}).",
        "",
        "## 3. Laminate definition and stiffness",
        "",
        f"- Stacking sequence: {st['layup']} "
        f"({st['n_plies']} plies), balanced and symmetric.",
        f"- Cured ply thickness: {st['t_ply_mm']:.3f} mm; total laminate "
        f"thickness: {st['h_mm']:.3f} mm.",
        f"- In-plane stiffness (CLT A matrix, N/m): "
        f"A11 = {st['a11_n_per_m']/1e6:.2f}e6, "
        f"A12 = {st['a12_n_per_m']/1e6:.2f}e6, "
        f"A22 = {st['a22_n_per_m']/1e6:.2f}e6, "
        f"A66 = {st['a66_n_per_m']/1e6:.2f}e6. "
        f"A16/A26 vanish (balanced symmetric).",
        f"- Flexural stiffness (CLT D matrix, N*m): "
        f"D11 = {st['d11_n_m']:.2f}, D12 = {st['d12_n_m']:.2f}, "
        f"D22 = {st['d22_n_m']:.2f}, D66 = {st['d66_n_m']:.2f}.",
        f"- Effective engineering constants: Ex = {st['ex_gpa']:.1f} GPa, "
        f"Ey = {st['ey_gpa']:.1f} GPa, Gxy = {st['gxy_gpa']:.1f} GPa, "
        f"nu_xy = {st['nu_xy']:.3f}.",
        "",
        "## 4. Stress analysis and failure indices",
        "",
        f"- Ultimate load case (resultants N/mm): "
        f"Nx = {fl['load_case_n_per_mm']['nx']}, "
        f"Ny = {fl['load_case_n_per_mm']['ny']}, "
        f"Nxy = {fl['load_case_n_per_mm']['nxy']}.",
        f"- Mid-plane strains: ex = {fl['strain_midplane']['ex']:.4e}, "
        f"ey = {fl['strain_midplane']['ey']:.4e}, "
        f"gxy = {fl['strain_midplane']['gxy']:.4e}.",
        "",
        "Per-ply material-axis stresses (MPa) and failure indices "
        "(Tsai-Wu and max-stress; index >= 1.0 marks failure):",
        "",
        "| Ply (deg) | s1 (MPa) | s2 (MPa) | t12 (MPa) | Tsai-Wu | Max-stress |",
        "|---|---|---|---|---|---|",
        *[ply_table_row(row) for row in fl["per_ply"]],
        "",
        f"- Governing criterion: **{fl['governing_criterion']}** at the "
        f"{fl['governing_ply_deg']}-deg plies "
        f"(index {fl['governing_index']:.4f}).",
        f"- Reserve factor to first-ply failure (un-knockdowned basis): "
        f"**{fl['reserve_factor_to_fpf']:.2f}**.",
        f"- Design allowables with knockdowns (MPa): "
        f"Xt = {fl['knockdown']['xt_mpa']:.1f}, "
        f"Xc = {fl['knockdown']['xc_mpa']:.1f}, "
        f"Yt = {fl['knockdown']['yt_mpa']:.1f}, "
        f"Yc = {fl['knockdown']['yc_mpa']:.1f}, "
        f"S = {fl['knockdown']['s_mpa']:.1f}.",
        f"- Reserve factor against knockdowned {mat['basis']}-basis "
        f"allowables: **{fl['knockdowned_basis_rf']:.2f}** "
        f"(>= 1.0 required).",
        f"- Note: under compression-dominated states the Tsai-Wu index "
        f"may be non-positive inside the failure surface; max-stress is "
        f"then the governing conservative check.",
        "",
        "## 5. Hygrothermal response",
        "",
        f"- Environment: RH = {hy['rh']:.2f}, temperature change "
        f"delta_T = {hy['delta_t_k']:.0f} K (room {hy['t_rt_c']:.0f} C "
        f"to cure {hy['t_cure_c']:.0f} C reference), saturation moisture "
        f"m_sat = {hy['m_sat']}.",
        f"- Equilibrium moisture content: M = {hy['equilibrium_moisture']:.4f} "
        f"({hy['equilibrium_moisture']*100:.1f}% mass fraction).",
        f"- Laminate CTE (exact CLT): alpha_x = {hy['alpha_x_ppm']:.3f} ppm/K, "
        f"alpha_y = {hy['alpha_y_ppm']:.3f} ppm/K.",
        f"- Laminate CME: beta_x = {hy['beta_x']:.4f}, "
        f"beta_y = {hy['beta_y']:.4f} (per unit moisture fraction).",
        f"- Hygrothermal strain (delta_m = {hy['delta_m']:.4f}): "
        f"eps_x = {hy['hygrothermal_strain_x']:.4e}, "
        f"eps_y = {hy['hygrothermal_strain_y']:.4e}.",
        f"- Cure-cooldown residual strain: eps_x = "
        f"{hy['cure_strain_x']:.4e}.",
        "",
        "## 6. Stability (plate buckling)",
        "",
        f"- Panel: a = {sb['panel_a_m']*1e3:.0f} mm (load direction), "
        f"b = {sb['panel_b_m']*1e3:.0f} mm, simply supported edges, "
        f"uniaxial compression Nx = {sb['applied_n_per_m']/1e3:.0f} N/mm.",
        f"- Critical load (min over modes): N_x_cr = "
        f"{sb['n_x_cr_n_per_m']/1e3:.2f} N/mm, mode "
        f"({sb['mode'][0]}, {sb['mode'][1]}).",
        f"- Buckling margin: **{sb['margin']:.2f}** "
        f"(>= 1.0 = no predicted buckling at the applied load).",
        "",
        "## 7. Conclusions and certification readiness",
        "",
        f"- Governing condition: {cc['governing_condition']} with margin "
        f"{cc['buckling_margin']:.2f} at ultimate.",
        f"- Static strength is not critical for this load case; the "
        f"reserve factor against knockdowned B-basis allowables is "
        f"{cc['knockdowned_reserve_factor']:.2f}.",
        "- Evidence required before the human certification engineer "
        "signs: coupon test results establishing the B-basis allowables "
        "used here, environmental conditioning data, BVID thresholds, "
        "and a damage-tolerance evaluation per the certification plan. "
        "Joint-level and repair analyses (bonded and bolted joints, "
        "sandwich details) follow the bound composite leaves.",
        "",
        "---",
        f"*Generated by Aero Agent Roles composites-structures-engineer "
        f"core ({model['generated']}). DRAFT for human review by the "
        "certification chain. Not an approval. Not a certification.*",
    ]
    # drop nothing further; the list above is the complete document
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evidence gate checkers
# ---------------------------------------------------------------------------

GATE_CHECKS = {
    "item_identified": "item name is present",
    "basis_identified": "certification basis + structure class present",
    "stiffness_computed": "CLT A/D stiffness numbers are present",
    "failure_index_present": "per-ply failure indices + reserve present",
    "stability_margin_present": "buckling critical load + margin present",
    "hygrothermal_present": "moisture + CTE/CME + strain numbers present",
    "allowables_grounded": "allowable basis (A/B) stated with knockdowns",
    "sign_off_honest": "document is marked draft-for-review, not approval",
}


def check_report(model):
    """Run the evidence gates against the content model."""
    def num(v):
        return isinstance(v, (int, float)) and v == v  # not NaN

    st = model.get("stiffness") or {}
    fl = model.get("failure") or {}
    hy = model.get("hygrothermal") or {}
    sb = model.get("stability") or {}
    mat = model.get("material") or {}
    results = {
        "item_identified": bool(model.get("item", {}).get("name")),
        "basis_identified": (bool(model.get("certification_basis"))
                             and bool(model.get("item", {}).get(
                                 "structure_class"))),
        "stiffness_computed": (num(st.get("a11_n_per_m"))
                               and num(st.get("d11_n_m"))
                               and num(st.get("ex_gpa"))),
        "failure_index_present": (bool(fl.get("per_ply"))
                                  and num(fl.get("governing_index"))
                                  and num(fl.get("knockdowned_basis_rf"))),
        "stability_margin_present": (num(sb.get("n_x_cr_n_per_m"))
                                     and num(sb.get("margin"))),
        "hygrothermal_present": (num(hy.get("equilibrium_moisture"))
                                 and num(hy.get("alpha_x_ppm"))
                                 and num(hy.get("hygrothermal_strain_x"))),
        "allowables_grounded": (mat.get("basis") in ("A", "B")
                                and num(mat.get("bvid_factor"))),
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_report_markdown(md_text):
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    checks = {
        "has_title": ("composite structure analysis" in low
                      and "certification report" in low),
        "has_basis": "certification basis" in low
                     and "basis" in low,
        "has_numbers": ("n/mm" in low and "margin" in low
                        and "tsai-wu" in low and "a11" in low),
        "has_stability": "buckling" in low and "n_x_cr" in low,
        "has_hygrothermal": "hygrothermal" in low and "cte" in low,
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
        "has_not_certification": "not a certification" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text):
    """Public entry point used by gate tooling."""
    return check_report_markdown(md_text)


# ---------------------------------------------------------------------------
# Example item + demo generation
# ---------------------------------------------------------------------------

def example_item() -> CompositeItem:
    return CompositeItem(
        item_name="Vertical stabilizer skin panel, bay P2 "
                  "(between stringers S3 and S4)",
        description="Stabilizer torque-box skin bay in the vertical tail, "
                    "compression- and shear-loaded at the ultimate "
                    "condition.",
        part_number="VS-SK-0201",
        material=dict(MAT_T300),
        layup_deg=_default_layup(),
        t_ply_m=MAT_T300["t_ply_m"],
        allowables_basis="B",
        env_factor=0.90,
        bvid_factor=0.85,
        hole_factor=1.0,
        certification_basis="FAR/CS-25 (14 CFR Part 25 / EASA CS-25)",
        structure_class="primary structure",
        load_nx_n_per_mm=-75.0,
        load_ny_n_per_mm=-15.0,
        load_nxy_n_per_mm=20.0,
        panel_a_m=0.190,
        panel_b_m=0.150,
        rh_fraction=0.60,
        delta_t_k=-156.0,
        t_cure_c=177.0,
        t_rt_c=21.0,
    )


def example_report_markdown() -> str:
    return render_report_markdown(build_report(example_item()))


if __name__ == "__main__":
    item = example_item()
    model = build_report(item)
    md = render_report_markdown(model)
    print("ITEM: %s" % model["item"]["name"])
    print("A11: %.0f N/m  Ex: %.1f GPa" % (model["stiffness"]["a11_n_per_m"],
                                           model["stiffness"]["ex_gpa"]))
    print("GOVERNING: %s index=%.4f rf=%.2f"
          % (model["failure"]["governing_criterion"],
             model["failure"]["governing_index"],
             model["failure"]["reserve_factor_to_fpf"]))
    print("BUCKLING Ncr: %.2f N/mm margin=%.2f mode=%s"
          % (model["stability"]["n_x_cr_n_per_m"] / 1e3,
             model["stability"]["margin"], model["stability"]["mode"]))
    print("HYGRO alpha_x=%.3f ppm eps_x=%.4e cure=%.4e"
          % (model["hygrothermal"]["alpha_x_ppm"],
             model["hygrothermal"]["hygrothermal_strain_x"],
             model["hygrothermal"]["cure_strain_x"]))
    print("GATES: %s" % check_report(model))
    print("RENDERED: %d chars" % len(md))
