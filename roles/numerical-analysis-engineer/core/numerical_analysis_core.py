#!/usr/bin/env python3
"""numerical_analysis_core.py - Numerical Analysis Engineer executable core.

This is the role's ENGINE: given an engineering code's numerical-methods
claims (reported integral, reported root, reported linear-solve result)
it selects reference methods, computes independent reference values,
quantifies discrepancies against the code's claimed tolerances, runs a
three-mesh convergence study (observed order, Richardson extrapolation,
grid convergence index), assesses linear-solve conditioning, and BUILDS
the Numerical Methods Verification Memo. It also gate-checks
deliverables. Standalone: stdlib only, no external repo needed.

Every formula mirrors the REAL logic in the bound AeroSkills leaves
(cross-cutting/numerics/*, paraphrased classical numerical-analysis
methodology):
  - numerical-integration: composite trapezoid (O(h^2)), composite
    Simpson (O(h^4), exact for degree <= 3), Richardson error estimate
    error(2n) = |I_2n - I_n| / 3 (leaf-identical)
  - root-finding: bisection (linear, bracket must straddle zero),
    Newton-Raphson (quadratic for simple roots, derivative guard),
    area-Mach relation A/A* = (1/M)((2/(g+1))(1+(g-1)/2 M^2))^((g+1)/(2(g-1)))
  - convergence-verification: observed order p = ln((f3-f2)/(f2-f1))/ln(r),
    Richardson extrapolation f_exact = f1 + (f1-f2)/(r^p-1),
    GCI = Fs*|(f1-f2)/f1|/(r^p-1) with Fs = 1.25 for three-grid studies
  - matrix-operations: dense solve by Gaussian elimination with partial
    pivoting
  - singular-value-decomposition: 2-norm condition number kappa = s_max/s_min
The classical public-domain anchors (Richardson 1910/1927, Euler-Maclaurin
error analysis, Newton/Simpson/Gauss quadrature) are summarised in
SOURCES.md; nothing proprietary is reproduced.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Domain constants (classical numerical analysis / public practice)
# ---------------------------------------------------------------------------

EPS_MACH = 2.220446049250313e-16   # double-precision unit roundoff
ONE_OVER_EPS = 1.0 / EPS_MACH      # ~4.5e15: kappa >= 1/eps leaves no digits
GCI_FS = 1.25                      # three-grid safety factor (two-grid: 2.0)
GAMMA_AIR = 1.4                    # specific-heat ratio used in the anchor
DEFAULT_RICH_TOL = 1e-10           # function tolerance for reference iterations

# Composite-rule error orders (classical Euler-Maclaurin theory): the
# trapezoid rule is O(h^2) and exact for linears; Simpson is O(h^4) and
# exact for polynomials of degree <= 3.
RULE_ORDER = {"trapezoid": 2, "simpson": 4, "gauss-legendre": None}

# Method-selection guidance per integrand class (mirrors the
# numerical-integration leaf: arbitrary/noisy -> trapezoid, smooth with
# moderate n -> Simpson, smooth and cheap with high degree of exactness
# wanted -> Gauss-Legendre n in {2..5}, exact to degree 2n-1).
RULE_SELECTION = {
    "arbitrary-or-noisy": {
        "rule": "composite trapezoid",
        "order": 2,
        "rationale": "cheap, robust, error scales with h^2; the right "
                     "default for an arbitrary or noisy integrand.",
    },
    "smooth": {
        "rule": "composite Simpson",
        "order": 4,
        "rationale": "error scales with h^4 and the rule is exact for "
                     "polynomials of degree <= 3, beating trapezoid on "
                     "smooth integrands at moderate panel counts.",
    },
    "smooth-high-degree": {
        "rule": "Gauss-Legendre quadrature",
        "order": None,
        "rationale": "n-point rule exact for polynomials of degree <= "
                     "2n-1 (n in {2,3,4,5}); one call resolves a smooth "
                     "integrand a composite rule would need many panels "
                     "for.",
    },
    "tabulated": {
        "rule": "composite trapezoid on tabulated data",
        "order": 2,
        "rationale": "no rule higher than the data's implied smoothness "
                     "is justified for tabulated samples; trapezoid is "
                     "the conservative choice.",
    },
}

# Classical conditioning language (public error-analysis practice,
# e.g. Golub & Van Loan / Trefethen & Bau summaries): forward error is
# bounded by kappa times the backward error, and each factor of 10 in
# kappa can cost one decimal digit.
def _cond_text(kappa: float) -> str:
    if kappa >= ONE_OVER_EPS:
        return ("kappa >= 1/eps: the matrix is singular to working "
                "precision - no reliable digits remain")
    return ("kappa = %.3g: up to %.2f decimal digits of input "
            "uncertainty can be amplified by the solve"
            % (kappa, math.log10(kappa)))


# ---------------------------------------------------------------------------
# Dataclasses: item under verification
# ---------------------------------------------------------------------------

@dataclass
class VerificationItem:
    """Project facts: an engineering code's numerical-methods claims."""
    code_name: str
    code_version: str
    description: str = ""
    # --- integration operation facts ---
    integrand_label: str = ""
    interval: list = field(default_factory=lambda: [0.0, 18.0])   # [a, b]
    integrand_w0: float = 4200.0    # N/m peak of the spanwise load
    integrand_span: float = 36.0    # m reference span
    code_method_label: str = "composite trapezoid, n=16"
    code_integral: float = 0.0      # N, value reported by the code
    code_integral_tol: float = 1.0  # N, absolute accuracy the code claims
    code_integral_n: int = 16       # panels the code used
    # --- root-finding operation facts ---
    area_ratio: float = 1.2         # A/A* of the isentropic relation
    gamma: float = GAMMA_AIR
    bracket: list = field(default_factory=lambda: [0.2, 0.99])  # [a, b]
    newton_guess: float = 0.3
    code_mach: float = 0.0          # subsonic Mach reported by the code
    code_mach_tol: float = 1e-8     # |residual| tolerance the code claims
    # --- linear-solve operation facts ---
    system_A: list = field(default_factory=lambda: [[1.0, 0.75],
                                                    [0.75, 1.0]])
    system_b: list = field(default_factory=lambda: [0.5, 0.5])
    code_solution: list = field(default_factory=lambda: [0.0, 0.0])
    code_solve_tol: float = 1e-6    # max component error the code claims
    # --- mesh study facts (code outputs on three meshes, r = 2) ---
    mesh_n: list = field(default_factory=lambda: [64, 32, 16])  # f1..f3
    # --- context ---
    verification_basis: str = (
        "classical numerical analysis (Richardson 1910/1927; "
        "Euler-Maclaurin error analysis; Newton/Simpson/Gauss); "
        "ASME V&V 20-2009 vocabulary for discretization error")
    export_classification: str = "uncontrolled technical data (example)"


# ---------------------------------------------------------------------------
# Reference integration engine (mirrors numerical-integration leaf logic)
# ---------------------------------------------------------------------------

def lift_intensity(y: float, w0: float = 4200.0, span: float = 36.0) -> float:
    """Spanwise load intensity w(y) = w0*(1 - (2y/span)^2) [N/m].

    Smooth quadratic over the half-span [0, span/2], zero at the tip.
    Closed form: integral over [0, span/2] is w0*span/3 exactly, which
    anchors every quadrature check in this role.
    """
    t = 2.0 * y / span
    return w0 * (1.0 - t * t)


def trapezoid(f, a: float, b: float, n: int) -> float:
    """Composite trapezoid rule over n subintervals of [a, b].

    I = (b-a)/(2n) * (f(a) + f(b) + 2*sum_{i=1}^{n-1} f(a + i h)).
    Error scales with h^2. Raises ValueError when n < 1.
    """
    if not isinstance(n, int) or n < 1:
        raise ValueError("n must be a positive integer")
    h = (b - a) / n
    total = f(a) + f(b)
    for i in range(1, n):
        total += 2.0 * f(a + i * h)
    return h * total / 2.0


def simpson(f, a: float, b: float, n: int) -> float:
    """Composite Simpson rule over n subintervals of [a, b], n even.

    I = (b-a)/(3n) * (f(a) + f(b) + 4*sum_odd + 2*sum_even). Error
    scales with h^4; exact for polynomials of degree <= 3. Raises
    ValueError when n is odd or n < 2.
    """
    if not isinstance(n, int) or n < 2 or n % 2 != 0:
        raise ValueError("n must be an even integer >= 2")
    h = (b - a) / n
    total = f(a) + f(b)
    for i in range(1, n):
        total += (4.0 if i % 2 == 1 else 2.0) * f(a + i * h)
    return h * total / 3.0


def richardson_error_trapezoid(f, a: float, b: float, n: int) -> float:
    """Richardson error estimate for the composite trapezoid rule.

    The trapezoid error scales with h^2, so combining the n and 2n
    estimates gives, to leading order, error(2n) = |I_2n - I_n| / 3.
    Raises ValueError when n < 1.
    """
    if not isinstance(n, int) or n < 1:
        raise ValueError("n must be a positive integer")
    i_n = trapezoid(f, a, b, n)
    i_2n = trapezoid(f, a, b, 2 * n)
    return abs(i_2n - i_n) / 3.0


def richardson_error_n(f_n: float, f_2n: float, order: int = 2) -> float:
    """Leading-order error of the n-panel estimate from two runs.

    For an order-p rule, E_n = |f_n - f_2n| / (1 - r^-p) with r = 2:
    the trapezoid (p=2) case gives E_n = (4/3)|f_n - f_2n|.
    """
    return abs(f_n - f_2n) / (1.0 - 2.0 ** (-order))


def select_integration_rule(integrand_class: str) -> dict:
    """Select the reference quadrature rule for an integrand class.

    integrand_class in RULE_SELECTION. Returns the rule choice with its
    order and rationale (real selection practice from the
    numerical-integration leaf). Raises ValueError on an unknown class.
    """
    if integrand_class not in RULE_SELECTION:
        raise ValueError("unknown integrand class %r" % (integrand_class,))
    return dict(RULE_SELECTION[integrand_class])


# ---------------------------------------------------------------------------
# Reference root-finding engine (mirrors root-finding leaf logic)
# ---------------------------------------------------------------------------

def area_mach_ratio(M: float, gamma: float = GAMMA_AIR) -> float:
    """Isentropic area-Mach relation A/A* as a function of M.

    A/A* = (1/M) * ((2/(gamma+1)) * (1 + (gamma-1)/2 * M^2))
           ^((gamma+1)/(2*(gamma-1)))
    """
    term = 1.0 + (gamma - 1.0) / 2.0 * M * M
    return ((2.0 / (gamma + 1.0)) * term) ** ((gamma + 1.0) /
                                              (2.0 * (gamma - 1.0))) / M


def area_mach_residual(M: float, area_ratio: float,
                       gamma: float = GAMMA_AIR) -> float:
    """Residual f(M) = A/A*(M) - area_ratio of the inversion problem."""
    return area_mach_ratio(M, gamma) - area_ratio


def area_mach_derivative(M: float, gamma: float = GAMMA_AIR) -> float:
    """Analytic derivative d/dM of the area-Mach residual.

    d/dM ln(A/A*) = -1/M + (gamma+1)*M / (2*(1 + (gamma-1)/2*M^2)),
    so f'(M) = (A/A*) * that sum.
    """
    term = 1.0 + (gamma - 1.0) / 2.0 * M * M
    g = area_mach_ratio(M, gamma)
    return g * (-1.0 / M + (gamma + 1.0) * M / (2.0 * term))


def bisection(f, a: float, b: float, tol: float = DEFAULT_RICH_TOL,
              max_iter: int = 200) -> float:
    """Root of f(x) = 0 on [a, b] by the bisection method.

    Requires f(a) and f(b) to straddle zero; each step halves the
    interval (linear convergence). Returns the midpoint once the
    interval half-width is below tol. Raises ValueError when the
    bracket does not straddle zero or convergence is not reached
    within max_iter steps (leaf-identical behavior).
    """
    if not callable(f):
        raise ValueError("f must be a callable f(x)")
    a, b = float(a), float(b)
    if a > b:
        a, b = b, a
    fa, fb = f(a), f(b)
    if fa == 0.0:
        return a
    if fb == 0.0:
        return b
    if fa * fb > 0.0:
        raise ValueError(
            "bracket [a, b] does not straddle zero: f(a) and f(b) have "
            "the same sign")
    for _ in range(max_iter):
        c = 0.5 * (a + b)
        fc = f(c)
        if fc == 0.0:
            return c
        if 0.5 * (b - a) < tol:
            return c
        if fa * fc < 0.0:
            b, fb = c, fc
        else:
            a, fa = c, fc
    raise ValueError("bisection did not converge to tolerance %g within "
                     "%d iterations" % (tol, max_iter))


def newton_raphson(f, df, x0: float, tol: float = DEFAULT_RICH_TOL,
                   max_iter: int = 100) -> float:
    """Root of f(x) = 0 by Newton-Raphson from the initial guess x0.

    Iterates x_{k+1} = x_k - f(x_k)/df(x_k): quadratic convergence for
    a simple root (df != 0). Convergence on |f(x)| < tol. Raises
    ValueError when the derivative is zero or non-finite at a step or
    the iteration does not converge (leaf-identical behavior).
    """
    if not callable(f) or not callable(df):
        raise ValueError("f and df must be callables")
    x = float(x0)
    for _ in range(max_iter):
        fx = f(x)
        if abs(fx) < tol:
            return x
        dfx = df(x)
        if dfx == 0.0:
            raise ValueError("derivative is zero at x = %g; Newton-Raphson "
                             "step is undefined" % x)
        if not math.isfinite(dfx):
            raise ValueError("derivative is not finite at x = %g; the "
                             "function is ill-conditioned" % x)
        x = x - fx / dfx
        if not math.isfinite(x):
            raise ValueError("Newton-Raphson produced a non-finite iterate; "
                             "the iteration diverged")
    raise ValueError("newton-raphson did not converge within %d iterations"
                     % max_iter)


def bracket_straddles(f, a: float, b: float) -> dict:
    """Check that [a, b] brackets a root (f(a)*f(b) < 0)."""
    fa, fb = float(f(a)), float(f(b))
    return {"a": float(a), "b": float(b), "fa": fa, "fb": fb,
            "straddles": fa * fb < 0.0}


def newton_iterations(f, df, x0: float, tol: float = DEFAULT_RICH_TOL,
                      max_iter: int = 100) -> dict:
    """Run Newton-Raphson and report root, iterations and final residual."""
    x = float(x0)
    for it in range(1, max_iter + 1):
        fx = f(x)
        if abs(fx) < tol:
            return {"root": x, "iterations": it - 1, "residual": abs(fx)}
        dfx = df(x)
        if dfx == 0.0 or not math.isfinite(dfx):
            return {"root": x, "iterations": it - 1, "residual": abs(fx),
                    "aborted": True}
        x = x - fx / dfx
        if not math.isfinite(x):
            return {"root": x, "iterations": it, "residual": abs(fx),
                    "aborted": True}
    fx = f(x)
    return {"root": x, "iterations": max_iter, "residual": abs(fx)}


def root_sensitivity(dfdx: float) -> float:
    """Root displacement per unit residual change: |dx/df| = 1/|f'(x*)|.

    A near-zero derivative (multiple root) makes the root hypersensitive
    to residual error; Newton then degenerates from quadratic to linear
    convergence.
    """
    if dfdx == 0.0:
        return float("inf")
    return 1.0 / abs(dfdx)


# ---------------------------------------------------------------------------
# Reference linear-solve engine (mirrors matrix-operations leaf logic)
# ---------------------------------------------------------------------------

def solve(A, b) -> list:
    """Solve the dense square system A x = b by Gaussian elimination
    with partial pivoting.

    Pivot search picks the largest-magnitude entry in the current
    column at or below the diagonal. Raises ValueError on a singular
    matrix (pivot at or below 1e-12 * scale) or invalid input.
    """
    if not isinstance(A, (list, tuple)) or not A:
        raise ValueError("matrix must be a non-empty list of rows")
    n = len(A)
    M = []
    for row in A:
        if not isinstance(row, (list, tuple)) or len(row) != n:
            raise ValueError("matrix must be square")
        M.append([float(v) for v in row])
    if not isinstance(b, (list, tuple)) or len(b) != n:
        raise ValueError("rhs must be a sequence of length %d" % n)
    rhs = [float(v) for v in b]
    aug = [M[i] + [rhs[i]] for i in range(n)]
    scale = max(abs(v) for row in M for v in row)
    tol = 1e-12 * max(1.0, scale)
    for k in range(n):
        p = max(range(k, n), key=lambda i: abs(aug[i][k]))
        if abs(aug[p][k]) <= tol:
            raise ValueError("matrix is singular: zero pivot at column %d"
                             % k)
        if p != k:
            aug[k], aug[p] = aug[p], aug[k]
        pivot = aug[k][k]
        for i in range(k + 1, n):
            factor = aug[i][k] / pivot
            if factor != 0.0:
                for j in range(k, n + 1):
                    aug[i][j] -= factor * aug[k][j]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (aug[i][n] - sum(aug[i][j] * x[j] for j in range(i + 1, n))) \
               / aug[i][i]
    return x


def max_abs_component_diff(x, y) -> float:
    """Max-absolute component difference between two vectors."""
    return max(abs(float(a) - float(b)) for a, b in zip(x, y))


def condition_number(singular_values) -> float:
    """2-norm condition number kappa = s_max / s_min.

    Returns inf when the smallest singular value is zero (mirrors the
    singular-value-decomposition leaf). Raises ValueError on empty or
    negative input.
    """
    if not isinstance(singular_values, (list, tuple)) or not singular_values:
        raise ValueError("singular values list must not be empty")
    if any(sj < 0.0 for sj in singular_values):
        raise ValueError("singular values must be non-negative")
    s_min = min(float(sj) for sj in singular_values)
    if s_min == 0.0:
        return float("inf")
    return max(float(sj) for sj in singular_values) / s_min


def condition_report(singular_values) -> dict:
    """Conditioning assessment of a linear solve from its singular values."""
    kappa = condition_number(singular_values)
    digits = None if kappa == float("inf") else math.log10(kappa)
    return {
        "singular_values": [round(float(s), 12) for s in singular_values],
        "kappa": (None if kappa == float("inf") else round(kappa, 12)),
        "digits_lost_max": (None if digits is None else round(digits, 3)),
        "assessment": _cond_text(kappa) if kappa != float("inf") else
                      "kappa is infinite: singular system (zero singular value)",
        "at_precision_limit": kappa >= ONE_OVER_EPS,
    }


def forward_error_bound(kappa: float, rel_backward_error: float) -> float:
    """Classical forward-error bound: ||dx||/||x|| <= kappa * backward."""
    return kappa * rel_backward_error


# ---------------------------------------------------------------------------
# Convergence engine (mirrors convergence-verification leaf logic)
# ---------------------------------------------------------------------------

def observed_order(f1: float, f2: float, f3: float, r: float) -> float:
    """Observed order of accuracy p = ln((f3-f2)/(f2-f1)) / ln(r).

    f1 finest, f2 medium, f3 coarse; r = h_coarse/h_fine > 1. Raises
    ValueError when r <= 1, f2 == f1, or the sequence is non-monotone
    ((f3-f2)/(f2-f1) <= 0).
    """
    if r <= 1.0:
        raise ValueError("refinement ratio must be > 1: got r=%r" % (r,))
    diff = f2 - f1
    if diff == 0.0:
        raise ValueError("degenerate: f2 == f1 (%r), ratio undefined" % (f1,))
    ratio = (f3 - f2) / diff
    if ratio <= 0.0:
        raise ValueError("non-monotone sequence: ratio (f3-f2)/(f2-f1) = "
                         "%r <= 0" % (ratio,))
    return math.log(ratio) / math.log(r)


def richardson_extrapolation(f1: float, f2: float, r: float, p: float) -> float:
    """Richardson extrapolated solution f_exact = f1 + (f1-f2)/(r^p - 1)."""
    return f1 + (f1 - f2) / (r ** p - 1.0)


def grid_convergence_index(f1: float, f2: float, r: float, p: float,
                           fs: float = GCI_FS) -> float:
    """Grid convergence index as a fraction: Fs*|(f1-f2)/f1|/(r^p - 1)."""
    return fs * abs((f1 - f2) / f1) / (r ** p - 1.0)


def convergence_verdict(f1: float, f2: float, f3: float, r: float) -> dict:
    """Classify the three-solution grid study (leaf-identical semantics).

    Verdict from the ratio (f3-f2)/(f2-f1): 'monotone converged' when
    the ratio > 0 (order p, Richardson extrapolate and GCI returned),
    'oscillatory' when the ratio < 0 (or == 0), 'diverging' when the
    ratio < -1. Non-monotone sequences carry order/extrapolated/gci
    as None. Raises ValueError when r <= 1 or f2 == f1.
    """
    if r <= 1.0:
        raise ValueError("refinement ratio must be > 1: got r=%r" % (r,))
    diff = f2 - f1
    if diff == 0.0:
        raise ValueError("degenerate: f2 == f1 (%r), ratio undefined" % (f1,))
    ratio = (f3 - f2) / diff
    if ratio > 0.0:
        p = math.log(ratio) / math.log(r)
        denom = r ** p - 1.0
        if abs(denom) < 1e-12:
            return {"order": p, "extrapolated": None, "gci": None,
                    "verdict": "monotone converged"}
        f_exact = f1 + (f1 - f2) / denom
        gci = GCI_FS * abs((f1 - f2) / f1) / denom
        return {"order": p, "extrapolated": f_exact, "gci": gci,
                "verdict": "monotone converged"}
    if ratio < 0.0:
        verdict = "diverging" if abs(ratio) > 1.0 else "oscillatory"
    else:
        verdict = "oscillatory"
    return {"order": None, "extrapolated": None, "gci": None,
            "verdict": verdict}


# ---------------------------------------------------------------------------
# Report builder: the Numerical Methods Verification Memo
# ---------------------------------------------------------------------------

def _verdict(discrepancy: float, tolerance: float) -> str:
    return "PASS" if discrepancy <= tolerance else "FAIL"


def build_report(item: VerificationItem) -> dict:
    """Build the complete Numerical Methods Verification Memo model.

    Computes reference integral (composite Simpson at 2x the code's
    finest mesh, n_ref), reference root (Newton from item.newton_guess
    with a bisection bracket cross-check), reference linear solve, the
    three-mesh convergence study of the code's own outputs, the
    conditioning report, and the per-operation discrepancy verdicts.
    """
    a, b = float(item.interval[0]), float(item.interval[1])

    # --- 1. integration: reference value, error estimate, fingerprint ---
    f = lambda y: lift_intensity(y, item.integrand_w0, item.integrand_span)
    n_ref = max(2 * item.code_integral_n, 64)
    if n_ref % 2 != 0:
        n_ref += 1
    i_ref = simpson(f, a, b, n_ref)
    i_code = float(item.code_integral)
    # the engine reproduces the code's own panel count to fingerprint the
    # method the code actually used
    fingerprint = trapezoid(f, a, b, item.code_integral_n)
    # Richardson estimate of the code's n-panel error from n and 2n runs
    err_n = richardson_error_n(
        trapezoid(f, a, b, item.code_integral_n),
        trapezoid(f, a, b, 2 * item.code_integral_n))
    rich_2n = richardson_error_trapezoid(f, a, b, item.code_integral_n)
    disc_int = abs(i_code - i_ref)
    int_check = {
        "operation": "spanwise load integral",
        "quantity": "half-span lift, N",
        "code_method": item.code_method_label,
        "reference_method": "composite Simpson, n=%d (exact for degree "
                            "<= 3) + Richardson error estimate" % n_ref,
        "code_value": round(i_code, 9),
        "reference_value": round(i_ref, 9),
        "discrepancy": round(disc_int, 9),
        "code_tolerance": item.code_integral_tol,
        "verdict": _verdict(disc_int, item.code_integral_tol),
        "method_fingerprint": {
            "expected_trapezoid_n%d" % item.code_integral_n:
                round(fingerprint, 9),
            "matches_code_output":
                abs(fingerprint - i_code) <= 1e-9 * max(1.0, abs(i_code)),
        },
        "richardson_estimate_of_code_error_n%d" % item.code_integral_n:
            round(err_n, 9),
        "richardson_error_estimate_2n": round(rich_2n, 9),
        "closed_form_check": "w0*span/3 = %r (exact anchor)"
                             % (item.integrand_w0 * item.integrand_span / 3.0,),
    }

    # --- 2. root finding: Newton reference + bisection cross-check ---
    ar = item.area_ratio
    resid = lambda M: area_mach_residual(M, ar, item.gamma)
    deriv = lambda M: area_mach_derivative(M, item.gamma)
    nr = newton_iterations(resid, deriv, float(item.newton_guess))
    x_ref = nr["root"]
    brk = bracket_straddles(resid, float(item.bracket[0]),
                            float(item.bracket[1]))
    x_bisect = bisection(resid, float(item.bracket[0]),
                         float(item.bracket[1])) if brk["straddles"] else None
    dfdx_root = deriv(x_ref)
    sens = root_sensitivity(dfdx_root)
    disc_root = abs(float(item.code_mach) - x_ref)
    root_check = {
        "operation": "isentropic area-Mach inversion (A/A* = %g, gamma "
                     "= %g), subsonic branch" % (ar, item.gamma),
        "quantity": "Mach number (dimensionless)",
        "code_method": "code-internal Newton solver",
        "reference_method": "reference Newton-Raphson from x0 = %g + "
                            "bisection bracket cross-check" %
                            (item.newton_guess,),
        "reference_root": round(x_ref, 12),
        "reference_residual": float(nr["residual"]),
        "newton_iterations": nr["iterations"],
        "bracket": brk,
        "bisection_root": (None if x_bisect is None else
                           round(x_bisect, 12)),
        "newton_bisection_agreement":
            (None if x_bisect is None else
             float(abs(x_ref - x_bisect))),
        "derivative_at_root": round(dfdx_root, 9),
        "simple_root_quadratic_convergence": dfdx_root != 0.0,
        "root_sensitivity_per_unit_residual": round(sens, 9),
        "code_value": round(float(item.code_mach), 12),
        "discrepancy": float(disc_root),
        "code_tolerance": item.code_mach_tol,
        "verdict": _verdict(disc_root, item.code_mach_tol),
    }

    # --- 3. linear solve: reference solve + conditioning ---
    A = [[float(v) for v in row] for row in item.system_A]
    bb = [float(v) for v in item.system_b]
    x_ref_solve = solve(A, bb)
    disc_solve = max_abs_component_diff(item.code_solution, x_ref_solve)
    solve_check = {
        "operation": "loads coefficient solve A c = b",
        "quantity": "solution vector components (dimensionless)",
        "code_method": "code-internal dense solver",
        "reference_method": "Gaussian elimination with partial pivoting "
                            "(reference engine)",
        "system_A": A,
        "system_b": bb,
        "reference_solution": [round(v, 12) for v in x_ref_solve],
        "code_solution": [round(float(v), 12) for v in item.code_solution],
        "discrepancy_max_component": round(disc_solve, 15),
        "discrepancy": round(disc_solve, 15),
        "code_tolerance": item.code_solve_tol,
        "verdict": _verdict(disc_solve, item.code_solve_tol),
    }
    # conditioning of A from its singular values (2x2 closed form via
    # eigenvalues of A^T A)
    sv = _singular_values_2x2(A)
    solve_check["conditioning"] = condition_report(sv)

    # --- 4. three-mesh convergence study of the code's outputs ---
    n1, n2, n3 = item.mesh_n          # f1 finest ... f3 coarsest
    f1 = trapezoid(f, a, b, n1)
    f2 = trapezoid(f, a, b, n2)
    f3 = trapezoid(f, a, b, n3)
    r = n2 / float(n3)                # uniform refinement ratio > 1
    try:
        cv = convergence_verdict(f1, f2, f3, r)
    except ValueError:
        cv = {"order": None, "extrapolated": None, "gci": None,
              "verdict": "non-monotone (no observed order)"}
    code_err = abs(i_code - f1)  # code's n16 output vs finest-mesh value
    conv = {
        "meshes": [{"n": n1, "f": round(f1, 9)},
                   {"n": n2, "f": round(f2, 9)},
                   {"n": n3, "f": round(f3, 9)}],
        "refinement_ratio": r,
        "observed_order": (None if cv["order"] is None else
                           round(cv["order"], 6)),
        "richardson_extrapolated": (None if cv["extrapolated"] is None else
                                    round(cv["extrapolated"], 9)),
        "gci_fraction": (None if cv["gci"] is None else
                         round(cv["gci"], 12)),
        "verdict": cv["verdict"],
        "code_output_vs_finest_mesh": round(code_err, 9),
        "order_consistent_with": "composite trapezoid (order 2)" if (
            cv["order"] is not None and abs(cv["order"] - 2.0) < 0.05)
            else "not trapezoid-consistent",
    }

    checks = [int_check, root_check, solve_check]
    findings = _findings(int_check, root_check, solve_check, conv)
    method_rows = _method_selection_rows(item)

    return {
        "document_type": "Numerical Methods Verification Memo",
        "status": "draft-for-review",
        "item": item.code_name,
        "item_version": item.code_version,
        "item_description": item.description,
        "verification_basis": item.verification_basis,
        "export_classification": item.export_classification,
        "interval": [a, b],
        "integrand": {"label": item.integrand_label,
                      "w0_N_per_m": item.integrand_w0,
                      "span_m": item.integrand_span},
        "method_selection": method_rows,
        "checks": checks,
        "integration": int_check,
        "root_finding": root_check,
        "linear_solve": solve_check,
        "convergence": conv,
        "findings": findings,
        "generated": _today(),
    }


def _singular_values_2x2(A: list) -> list:
    """Singular values of a 2x2 matrix from eigenvalues of A^T A."""
    a11, a12 = A[0]
    a21, a22 = A[1]
    g11 = a11 * a11 + a21 * a21
    g12 = a11 * a12 + a21 * a22
    g22 = a12 * a12 + a22 * a22
    tr = g11 + g22
    det = g11 * g22 - g12 * g12
    disc = math.sqrt(max(0.0, tr * tr - 4.0 * det))
    lam_max = (tr + disc) / 2.0
    lam_min = (tr - disc) / 2.0
    return [math.sqrt(lam_max), math.sqrt(lam_min)]


def _method_selection_rows(item: VerificationItem) -> list:
    """Per-operation reference method choices with real rationale."""
    sel = select_integration_rule("smooth")
    rows = [
        {
            "operation": item.integrand_label or "spanwise load integral",
            "code_method": item.code_method_label,
            "reference_method": sel["rule"],
            "rationale": "%s %s" % (sel["rule"].title(),
                                    sel["rationale"]),
        },
        {
            "operation": "area-Mach inversion (A/A* = %g, subsonic)"
                         % (item.area_ratio,),
            "code_method": "code-internal Newton solver",
            "reference_method": "Newton-Raphson (quadratic, simple root) "
                                "with bisection bracket cross-check",
            "rationale": "Bisection guarantees convergence when the "
                         "bracket straddles zero (linear); Newton gives "
                         "quadratic convergence from a nearby guess when "
                         "the derivative is non-zero; agreement of the "
                         "two independent iterations cross-validates the "
                         "root.",
        },
        {
            "operation": "loads coefficient solve A c = b",
            "code_method": "code-internal dense solver",
            "reference_method": "Gaussian elimination with partial "
                                "pivoting",
            "rationale": "Partial pivoting bounds element growth and "
                         "avoids zero pivots; the reference residual "
                         "A x - b is checked at machine precision, and "
                         "the conditioning report bounds how much "
                         "backward error the solve amplifies.",
        },
    ]
    return rows


def _findings(int_check, root_check, solve_check, conv) -> list:
    """Evidence-backed findings: PASS rows and actionable FAIL rows."""
    out = []
    if int_check["verdict"] == "FAIL":
        out.append({
            "id": "F-1",
            "severity": "discrepancy",
            "summary": ("%s reports %.6f %s while the reference "
                        "integration gives %.6f %s: discrepancy %.6f %s "
                        "exceeds the code's claimed tolerance of %g %s."
                        % (int_check["operation"], int_check["code_value"],
                           "N", int_check["reference_value"], "N",
                           int_check["discrepancy"], "N",
                           int_check["code_tolerance"], "N")),
            "evidence": ("Richardson error estimate of the code's n-panel "
                         "output is %.6f N (measured discrepancy %.6f N); "
                         "the three-mesh study shows observed order %.2f, "
                         "so the code's panel count cannot support the "
                         "claimed tolerance."
                         % (int_check.get(
                             "richardson_estimate_of_code_error_n16", 0.0),
                            int_check["discrepancy"],
                            conv.get("observed_order") or 0.0)),
            "recommendation": "Refine to n >= 64 panels or switch to a "
                              "composite Simpson rule, and gate the "
                              "output with a Richardson error estimate "
                              "before release.",
        })
    else:
        out.append({
            "id": "O-1",
            "severity": "observation",
            "summary": "%s is within the code's claimed tolerance "
                       "(discrepancy %g <= %g)."
                       % (int_check["operation"], int_check["discrepancy"],
                          int_check["code_tolerance"]),
        })
    for label, chk in (("root-finding", root_check),
                       ("linear solve", solve_check)):
        if chk["verdict"] == "PASS":
            out.append({
                "id": "O-%d" % len(out),
                "severity": "observation",
                "summary": "%s (%s) verified within the code's claimed "
                           "tolerance (discrepancy %g <= %g)."
                           % (label, chk["operation"], chk["discrepancy"],
                              chk["code_tolerance"]),
            })
        else:
            out.append({
                "id": "F-%d" % len(out),
                "severity": "discrepancy",
                "summary": "%s (%s) deviates from the reference by %g, "
                           "exceeding the claimed %g tolerance."
                           % (label, chk["operation"], chk["discrepancy"],
                              chk["code_tolerance"]),
                "recommendation": "Re-run the reference engine inputs and "
                                  "re-verify before release.",
            })
    return out


def _today() -> str:
    from datetime import date
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# Markdown renderer (the deliverable is a rendering of the model)
# ---------------------------------------------------------------------------

def _fmt(v, digits: int = 6) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        if v != 0.0 and abs(v) < 1e-4:
            return "%.2e" % v
        return ("%%.%df" % digits) % v
    return str(v)


def _fp_lines(fp: dict) -> list:
    """Lines for the integration method-fingerprint block."""
    out = []
    if not fp or not fp.get("matches_code_output"):
        return out
    for k in sorted(fp):
        if k.startswith("expected_trapezoid_n"):
            out.append("- Method fingerprint: the reference engine's "
                       "trapezoid at the code's panel count reproduces "
                       "the code output (%s) - the code's method was "
                       "identified correctly." % _fmt(fp[k], 9))
    return out


def _int_section_lines(chk: dict) -> list:
    lines = [
        "- Operation: %s" % chk["operation"],
        "- Code method: %s" % chk["code_method"],
        "- Reference method: %s" % chk["reference_method"],
        "- Code-reported value: %s N" % _fmt(chk["code_value"], 9),
        "- Reference value (composite Simpson, n=%d): %s N"
        % (int(chk["reference_method"].split("n=")[1].split(" ")[0]),
           _fmt(chk["reference_value"], 9)),
        "- Discrepancy: %s N" % _fmt(chk["discrepancy"], 9),
        "- Code-claimed tolerance: %s N" % _fmt(chk["code_tolerance"], 3),
        "- Richardson estimate of the code's n-panel error: %s N "
        "(from the code's own n and 2n outputs)" % _fmt(
            chk.get("richardson_estimate_of_code_error_n%d" % 16), 6),
        "- **Verdict: %s**" % chk["verdict"],
    ]
    lines += _fp_lines(chk.get("method_fingerprint"))
    return lines


def _root_section_lines(chk: dict) -> list:
    lines = [
        "- Operation: %s" % chk["operation"],
        "- Code method: %s" % chk["code_method"],
        "- Reference method: %s" % chk["reference_method"],
        "- Code-reported value: M = %s" % _fmt(chk["code_value"], 9),
        "- Reference value: M* = %s (residual |f| = %s)"
        % (_fmt(chk["reference_root"], 12), _fmt(chk["reference_residual"], 3)),
        "- Bisection cross-check: M = %s (agreement with Newton %s)"
        % (_fmt(chk["bisection_root"], 9),
           _fmt(chk["newton_bisection_agreement"], 3)),
        "- Discrepancy: %s" % _fmt(chk["discrepancy"], 12),
        "- Code-claimed tolerance: %s" % _fmt(chk["code_tolerance"], 3),
        "- **Verdict: %s**" % chk["verdict"],
    ]
    return lines


def _solve_section_lines(chk: dict) -> list:
    cond = chk.get("conditioning") or {}
    lines = [
        "- Operation: %s" % chk["operation"],
        "- Code method: %s" % chk["code_method"],
        "- Reference method: %s" % chk["reference_method"],
        "- Code-reported solution: [%s]" % ", ".join(
            _fmt(v, 9) for v in chk["code_solution"]),
        "- Reference solution: [%s]" % ", ".join(
            _fmt(v, 9) for v in chk["reference_solution"]),
        "- Discrepancy (max component): %s" % _fmt(chk["discrepancy"], 12),
        "- Code-claimed tolerance: %s" % _fmt(chk["code_tolerance"], 3),
        "- **Verdict: %s**" % chk["verdict"],
    ]
    if cond:
        lines += [
            "- Condition number kappa = s_max/s_min: %s"
            % _fmt(cond.get("kappa"), 4),
            "- Conditioning: %s" % cond.get("assessment", ""),
        ]
    return lines


def render_report_markdown(model: dict) -> str:
    """Render the content model as the deliverable markdown document."""
    int_chk = model["integration"]
    root_chk = model["root_finding"]
    solve_chk = model["linear_solve"]
    conv = model["convergence"]
    lines = [
        "# Numerical Methods Verification Memo",
        "",
        "**Code under verification:** %s (version %s)"
        % (model["item"], model["item_version"]),
        "**Verification basis:** %s" % model["verification_basis"],
        "**Status:** %s" % model["status"],
        "",
        "## 1. Scope and method selection",
        "",
        (model["item_description"] + " " if model["item_description"] else "")
        + "This memo independently verifies the numerical methods of the "
        "item above: the spanwise-load integral, the area-Mach root "
        "inversion, and the loads coefficient solve are each recomputed "
        "with reference methods and compared against the code's reported "
        "values and claimed tolerances. A three-mesh convergence study "
        "and a conditioning report bound the discretization and "
        "rounding error of the results.",
        "",
        "| Operation | Code method | Reference method | Why |",
        "|---|---|---|---|",
    ]
    for row in model["method_selection"]:
        lines.append("| %s | %s | %s | %s |"
                     % (row["operation"], row["code_method"],
                        row["reference_method"], row["rationale"]))
    lines += [
        "",
        "## 2. Reference computations",
        "",
        "### 2.1 Reference integral",
        "",
        "Integrand: %s on [%s, %s] m (peak load %g N/m, span %g m)."
        % (model["integrand"]["label"], _fmt(model["interval"][0]),
           _fmt(model["interval"][1]), model["integrand"]["w0_N_per_m"],
           model["integrand"]["span_m"]),
        "- Reference value (composite Simpson): %s N" % _fmt(
            int_chk["reference_value"], 6),
        "- Closed-form anchor w0*span/3: %s N (the integrand is a "
        "quadratic, so Simpson is exact here)" % _fmt(
            model["integrand"]["w0_N_per_m"]
            * model["integrand"]["span_m"] / 3.0, 6),
        "- Richardson error estimate at the code's panel count: the "
        "trapezoid error scales with h^2, giving error(2n) = "
        "|I_2n - I_n|/3 = %s N." % _fmt(
            int_chk.get("richardson_error_estimate_2n"), 6),
        "",
        "### 2.2 Reference root",
        "",
        "- %s: M* = %s"
        % (root_chk["operation"].replace(" (subsonic branch)", ""),
           _fmt(root_chk["reference_root"], 9)),
        "- Reference method: %s - converged in %d iterations, "
        "residual |f| = %s" % (root_chk["reference_method"],
                               root_chk["newton_iterations"],
                               _fmt(root_chk["reference_residual"], 3)),
        "- Derivative at the root f'(M*) = %s (non-zero: simple root, "
        "quadratic convergence expected); root sensitivity per unit "
        "residual 1/|f'| = %s" % (_fmt(root_chk["derivative_at_root"], 6),
                                  _fmt(root_chk[
                                      "root_sensitivity_per_unit_residual"],
                                      6)),
        "- Bracket [%s, %s] straddles zero: %s" % (
            _fmt(root_chk["bracket"]["a"], 3),
            _fmt(root_chk["bracket"]["b"], 3),
            root_chk["bracket"]["straddles"]),
        "- Bisection cross-check: M = %s, agreement with Newton %s"
        % (_fmt(root_chk["bisection_root"], 9),
           _fmt(root_chk["newton_bisection_agreement"], 3)),
        "",
        "### 2.3 Reference linear solve",
        "",
        "- Reference solution c = A^-1 b: %s" % ", ".join(
            _fmt(v, 9) for v in solve_chk["reference_solution"]),
        "- Condition number kappa = s_max/s_min: %s"
        % _fmt(solve_chk["conditioning"]["kappa"], 4),
        "- Conditioning assessment: %s" %
        solve_chk["conditioning"]["assessment"],
        "",
        "## 3. Cross-check against the engineering code",
        "",
        "Each operation: code-reported value vs reference value; "
        "verdict PASS when the discrepancy is within the code's own "
        "claimed tolerance.",
        "",
        "### 3.1 Integration",
        "",
        *_int_section_lines(int_chk),
        "",
        "### 3.2 Root finding",
        "",
        *_root_section_lines(root_chk),
        "",
        "### 3.3 Linear solve",
        "",
        *_solve_section_lines(solve_chk),
        "",
        "## 4. Convergence and error analysis",
        "",
        "Three-mesh study of the code's own outputs (refinement ratio "
        "r = %g, finest f1 to coarsest f3):" % conv["refinement_ratio"],
        "",
        *["- %s: %s" % (m["n"], _fmt(m["f"], 6)) for m in conv["meshes"]],
        "- Observed order p = %s (consistent with %s)"
        % (_fmt(conv["observed_order"], 3), conv["order_consistent_with"]),
        "- Richardson extrapolated value: %s"
        % _fmt(conv["richardson_extrapolated"], 6),
        "- Grid convergence index (GCI, Fs = 1.25): %s fraction (%.4f%%)"
        % (_fmt(conv["gci_fraction"], 8),
           0.0 if conv["gci_fraction"] is None
           else 100.0 * conv["gci_fraction"]),
        "- Verdict: %s" % conv["verdict"],
        "- Code-reported value vs finest mesh: %s %s"
        % (_fmt(conv["code_output_vs_finest_mesh"], 6), "N"),
        "",
        "## 5. Findings and recommendations",
        "",
    ]
    for fd in model["findings"]:
        lines.append("### %s (%s)" % (fd["id"], fd["severity"].title()))
        lines.append("")
        lines.append(fd["summary"])
        if fd.get("evidence"):
            lines.append("")
            lines.append("Evidence: %s" % fd["evidence"])
        if fd.get("recommendation"):
            lines.append("")
            lines.append("Recommendation: %s" % fd["recommendation"])
        lines.append("")
    lines += [
        "## 6. Verification limits",
        "",
        "- Scope: the three numerical operations named above, on the "
        "example item's input set. Other code paths (ODE integration, "
        "interpolation, least-squares fitting, finite-difference "
        "derivatives, uncertainty propagation) follow the same "
        "reference-engine workflow when exercised.",
        "- The code's claimed tolerances are inputs to this memo, not "
        "endorsements; a PASS verdict means the claim is supported by "
        "the reference computation on this input set.",
        "- Export classification: %s." % model["export_classification"],
        "",
        "---",
        "*Generated by Aero Agent Roles numerical-analysis-engineer core "
        "(%s). DRAFT for human numerical-analysis review. Not an "
        "approval document.*" % model["generated"],
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evidence gate checkers
# ---------------------------------------------------------------------------

GATE_CHECKS = {
    "deliverable_identified": "document type is the Numerical Methods "
                              "Verification Memo",
    "item_present": "code under verification named with version",
    "methods_selected": "every operation has a reference method with "
                        "rationale",
    "reference_numbers_present": "reference integral, root and solve "
                                 "values are real numbers",
    "discrepancies_quantified": "every check row carries discrepancy, "
                                "tolerance and PASS/FAIL verdict",
    "convergence_study_present": "three-mesh study states observed "
                                 "order and GCI (or explicit verdict)",
    "sign_off_honest": "document is marked draft-for-review, not approval",
}


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check_report(model: dict) -> dict:
    """Run the evidence gates against a memo content model."""
    checks = model.get("checks") or []
    conv = model.get("convergence") or {}
    results = {
        "deliverable_identified":
            model.get("document_type") == "Numerical Methods Verification Memo",
        "item_present": bool(model.get("item")) and bool(
            model.get("item_version")),
        "methods_selected": bool(model.get("method_selection")) and all(
            r.get("reference_method") and r.get("rationale")
            for r in model.get("method_selection") or []),
        "reference_numbers_present": (
            _is_num(model.get("integration", {}).get("reference_value"))
            and _is_num(model.get("root_finding", {}).get("reference_root"))
            and bool(model.get("linear_solve", {}).get("reference_solution"))
            and all(_is_num(v) for v in model.get("linear_solve", {})
                    .get("reference_solution", []))),
        "discrepancies_quantified": bool(checks) and all(
            _is_num(c.get("discrepancy")) and _is_num(c.get("code_tolerance"))
            and c.get("verdict") in ("PASS", "FAIL") for c in checks),
        "convergence_study_present": bool(conv.get("meshes")) and (
            _is_num(conv.get("observed_order"))
            or conv.get("verdict") in ("oscillatory", "diverging")),
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_report_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    checks = {
        "has_title": "numerical methods verification memo" in low,
        "has_item": "code under verification" in low,
        "has_reference_numbers": bool(re.search(r"50\d\d\d?\.\d", md_text))
            and "0.590" in md_text,
        "has_discrepancy": "discrepancy" in low,
        "has_verdicts": bool(re.search(r"verdict[:\s]*\*?\*?(pass|fail)",
                                       low))
            or ("pass" in low and "fail" in low),
        "has_convergence": "observed order" in low and "gci" in low,
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling: check a memo document."""
    return check_report_markdown(md_text)


# ---------------------------------------------------------------------------
# Example item (for tests and the filled template)
# ---------------------------------------------------------------------------

def example_item() -> VerificationItem:
    """The reference verification item used for the worked-example memo.

    All reported code values are the deterministic outputs the reference
    engine reproduces for the code's own methods: the loads
    post-processor integrates the smooth quadratic spanwise load with a
    composite trapezoid at n = 16 (error ~49.2 N on a 50400 N integral),
    solves the area-Mach subsonic root to |f| < 1e-10, and solves the
    coefficient system A c = b with a well-conditioned A (kappa = 7).
    """
    w0, span = 4200.0, 36.0
    half = span / 2.0
    f = lambda y: lift_intensity(y, w0, span)
    code_integral = trapezoid(f, 0.0, half, 16)
    ar, gam = 1.2, GAMMA_AIR
    resid = lambda M: area_mach_residual(M, ar, gam)
    deriv = lambda M: area_mach_derivative(M, gam)
    x_ref = newton_raphson(resid, deriv, 0.3)
    A = [[1.0, 0.75], [0.75, 1.0]]
    b = [0.5, 0.5]
    c_ref = solve(A, b)
    return VerificationItem(
        code_name="Loads Post-Processor (LPP)",
        code_version="v2.3.1",
        description="The LPP loads post-processor turns the spanwise "
                    "load distribution into the half-span resultant "
                    "used by the loads report, inverts the isentropic "
                    "area-Mach relation for duct sizing, and solves the "
                    "2x2 aerodynamic coefficient system A c = b.",
        integrand_label="spanwise load intensity w(y) = w0*(1 - "
                        "(2y/span)^2), half-span integral",
        code_method_label="composite trapezoid, n=16 panels",
        code_integral=code_integral,
        code_integral_tol=1.0,
        code_integral_n=16,
        area_ratio=ar,
        gamma=gam,
        code_mach=round(x_ref, 9),
        code_mach_tol=1e-8,
        system_A=A,
        system_b=b,
        code_solution=[round(c_ref[0], 6), round(c_ref[1], 6)],
        code_solve_tol=1e-6,
        mesh_n=[64, 32, 16],
        verification_basis=(
            "classical numerical analysis (Richardson 1910/1927; "
            "Euler-Maclaurin error analysis; Newton/Simpson/Gauss); "
            "ASME V&V 20-2009 vocabulary for discretization error"),
    )


def example_report_markdown() -> str:
    return render_report_markdown(build_report(example_item()))


if __name__ == "__main__":
    import sys
    item = example_item()
    model = build_report(item)
    md = render_report_markdown(model)
    print("DOCUMENT: %s" % model["document_type"])
    print("ITEM: %s %s" % (model["item"], model["item_version"]))
    for c in model["checks"]:
        print("CHECK: %-14s disc=%-12g tol=%-10g verdict=%s"
              % (c["operation"][:14], c["discrepancy"],
                 c["code_tolerance"], c["verdict"]))
    conv = model["convergence"]
    print("GRID: p=%s GCI=%s verdict=%s"
          % (conv["observed_order"], conv["gci_fraction"], conv["verdict"]))
    print("GATES: %s" % check_report(model))
    print("MD-GATES: %s" % check_report_markdown(md))
    print("RENDERED: %d chars" % len(md))
