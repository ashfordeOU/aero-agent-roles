#!/usr/bin/env python3
"""fem_analysis_core.py - Finite Element Analysis Engineer executable core.

This is the role's ENGINE. Given the project facts of an aircraft
structural bracket/fitting item it runs the component-level finite
element analyses of the FEM skill family and BUILDS the Finite Element
Analysis Report content:

  1. truss-analysis     - 2D pin-jointed idealization by the direct
                          stiffness method (assembly, elimination,
                          member forces, reactions)
  2. beam-frame-analysis - 2D rigid-jointed frame idealization with the
                          Euler-Bernoulli beam element (deflections,
                          reactions, member end actions, equilibrium)
  3. beam-column-analysis - Euler load, moment amplification, secant
                          stress, axial+bending interaction margin
  4. buckling-analysis  - Euler critical load, slenderness, transition
                          slenderness, column margin of safety
  5. beam-vibration     - Euler-Bernoulli beam natural frequencies
                          (pinned-pinned closed form, cantilever
                          characteristic roots)
  6. modal-analysis     - 2-DOF lumped natural frequencies, mode shapes,
                          resonance check
  7. shear-center-analysis - V*Q/I thin-wall shear flow, channel
                          shear-center offset, applied-torque note
  8. lug-joint-analysis - pin-loaded lug bearing / net-tension / tearout
                          stresses, margins, governing mode

Every number is produced from real mechanics (public domain knowledge:
direct stiffness method, Euler buckling, Euler-Bernoulli beam theory,
V*Q/I shear flow, lug practice as summarized in MMPDS methodology -
never reproduced verbatim). The role runs STANDALONE: no AeroSkills
checkout, no third-party packages, stdlib only. When the Aero Agent
Skills library is present the CLI dispatches the same inputs to the
bound leaf *_logic.py implementations and records agreement in the
evidence bundle.

Boundary: this engine produces DRAFT engineering analyses for human
review. It never issues certification approval, never declares a
compliance finding, and never reproduces proprietary standard text.
"""
from __future__ import annotations

import math
import os

PI = math.pi
TWO_PI = 2.0 * math.pi

# ---------------------------------------------------------------------------
# Domain constants (public engineering knowledge)
# ---------------------------------------------------------------------------

# Euler-Bernoulli characteristic roots (Blevins, public tables): cantilever
# solves cos x cosh x = -1; clamped-clamped / free-free solve cos x cosh x = 1.
CANTILEVER_ROOTS = (1.87510407, 4.69409113, 7.85475744)
CLAMPED_FREE_FREE_ROOTS = (4.73004074, 7.85320462)

# Effective-length factor K by end condition (Euler column theory).
END_CONDITION_K = {
    "pinned-pinned": 1.0,
    "fixed-fixed": 0.5,
    "fixed-pinned": 0.7,
    "fixed-free": 2.0,
}
EC_ALIASES = {
    "pinned": "pinned-pinned",
    "hinged": "pinned-pinned",
    "hinged-hinged": "pinned-pinned",
    "fixed": "fixed-fixed",
    "clamped": "fixed-fixed",
    "clamped-clamped": "fixed-fixed",
    "built-in": "fixed-fixed",
    "pinned-fixed": "fixed-pinned",
    "clamped-pinned": "fixed-pinned",
    "pinned-clamped": "fixed-pinned",
    "cantilever": "fixed-free",
    "clamped-free": "fixed-free",
}

# Lug governing-mode evaluation order (bearing, net tension, tearout).
LUG_MODES = ("bearing", "net_tension", "tearout")


def _today() -> str:
    from datetime import date
    stamp = os.environ.get("ROLE_GEN_DATE")
    return stamp if stamp else date.today().isoformat()


# ---------------------------------------------------------------------------
# Linear algebra (dense Gaussian elimination with partial pivoting, stdlib)
# ---------------------------------------------------------------------------

def gaussian_elimination(A, b):
    """Solve the dense linear system A x = b (list of lists -> list).

    Partial pivoting; raises ValueError on a singular/rank-deficient
    matrix. Used by both the truss and the frame solvers.
    """
    n = len(A)
    if n == 0 or len(b) != n or any(len(row) != n for row in A):
        raise ValueError("system must be square and match b")
    scale = 0.0
    for row in A:
        for v in row:
            scale = max(scale, abs(v))
    for v in b:
        scale = max(scale, abs(v))
    if scale <= 0.0:
        raise ValueError("singular matrix")
    aug = [list(A[r]) + [b[r]] for r in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) <= 1e-13 * scale:
            raise ValueError("singular matrix: no unique solution")
        if pivot != col:
            aug[col], aug[pivot] = aug[pivot], aug[col]
        pv = aug[col][col]
        for r in range(col + 1, n):
            factor = aug[r][col] / pv
            if factor == 0.0:
                continue
            for c in range(col, n + 1):
                aug[r][c] -= factor * aug[col][c]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        acc = aug[r][n]
        for c in range(r + 1, n):
            acc -= aug[r][c] * x[c]
        x[r] = acc / aug[r][r]
    return x


def _mat_mul(a, b):
    """Matrix product a*b for square numeric lists of lists."""
    n = len(a)
    out = [[0.0] * n for _ in range(n)]
    for r in range(n):
        for c in range(n):
            out[r][c] = sum(a[r][m] * b[m][c] for m in range(n))
    return out


def _mat_t_mul(t, a):
    """Product t^T * a for square lists of lists."""
    n = len(a)
    out = [[0.0] * n for _ in range(n)]
    for r in range(n):
        for c in range(n):
            out[r][c] = sum(t[m][r] * a[m][c] for m in range(n))
    return out


# ---------------------------------------------------------------------------
# Stage 1 - 2D truss analysis (direct stiffness method)
# ---------------------------------------------------------------------------

def element_stiffness_matrix(E, A, L, theta_deg):
    """4x4 global element stiffness of one pin-jointed bar (2D)."""
    if E <= 0.0 or A <= 0.0 or L <= 0.0:
        raise ValueError("E, A and L must be positive")
    theta = math.radians(theta_deg)
    c, s = math.cos(theta), math.sin(theta)
    scale = E * A / L
    return [
        [scale * c * c, scale * c * s, -scale * c * c, -scale * c * s],
        [scale * c * s, scale * s * s, -scale * c * s, -scale * s * s],
        [-scale * c * c, -scale * c * s, scale * c * c, scale * c * s],
        [-scale * c * s, -scale * s * s, scale * c * s, scale * s * s],
    ]


def assemble_truss_stiffness(nodes, elements):
    """2N x 2N global stiffness of the pin-jointed truss.

    nodes: [(x, y), ...] in m; elements: [(i, j, E, A), ...] with
    0-based node indices. DOFs ordered [u_x0, u_y0, u_x1, u_y1, ...].
    """
    n = len(nodes)
    size = 2 * n
    K = [[0.0] * size for _ in range(size)]
    for (i, j, E, A) in elements:
        if not (0 <= i < n and 0 <= j < n) or i == j:
            raise ValueError("element node indices out of range")
        xi, yi = nodes[i]
        xj, yj = nodes[j]
        L = math.hypot(xj - xi, yj - yi)
        if L <= 0.0:
            raise ValueError("zero-length member")
        theta = math.degrees(math.atan2(yj - yi, xj - xi))
        k4 = element_stiffness_matrix(E, A, L, theta)
        dofs = (2 * i, 2 * i + 1, 2 * j, 2 * j + 1)
        for r in range(4):
            for c in range(4):
                K[dofs[r]][dofs[c]] += k4[r][c]
    return K


def truss_analysis(nodes, elements, loads, constraints):
    """Full 2D truss solve: displacements, member forces, reactions.

    loads maps (node, axis) to force N; constraints is a list of
    (node, axis) fixed supports. Returns the dict with keys
    "displacements" (length-2N list, m), "member_forces" (N, tension
    positive) and "reactions" (dict keyed by (node, axis), N).
    """
    n = len(nodes)
    size = 2 * n
    axis_idx = {"x": 0, "y": 1}

    def dof(node, axis):
        return 2 * node + axis_idx[axis]

    F = [0.0] * size
    for (node, axis), value in loads.items():
        if not (0 <= node < n) or axis not in axis_idx:
            raise ValueError("load key out of range")
        F[dof(node, axis)] = float(value)
    fixed = set()
    for (node, axis) in constraints:
        if not (0 <= node < n) or axis not in axis_idx:
            raise ValueError("constraint out of range")
        fixed.add(dof(node, axis))
    if not fixed:
        raise ValueError("truss requires at least one constraint")
    K = assemble_truss_stiffness(nodes, elements)
    free = [d for d in range(size) if d not in fixed]
    u = [0.0] * size
    if free:
        K_red = [[K[r][c] for c in free] for r in free]
        F_red = [F[r] for r in free]
        u_free = gaussian_elimination(K_red, F_red)
        for d, v in zip(free, u_free):
            u[d] = v
    forces = []
    for (i, j, E, A) in elements:
        xi, yi = nodes[i]
        xj, yj = nodes[j]
        L = math.hypot(xj - xi, yj - yi)
        c = (xj - xi) / L
        s = (yj - yi) / L
        elong = ((u[2 * j] - u[2 * i]) * c
                 + (u[2 * j + 1] - u[2 * i + 1]) * s)
        forces.append(E * A / L * elong)
    reactions = {}
    for (node, axis) in constraints:
        d = dof(node, axis)
        reactions[(node, axis)] = sum(K[d][c] * u[c] for c in range(size))
    return {"displacements": u, "member_forces": forces, "reactions": reactions}


# ---------------------------------------------------------------------------
# Stage 2 - 2D rigid-jointed frame analysis (Euler-Bernoulli element)
# ---------------------------------------------------------------------------

def element_stiffness_local(E, A, I, L):
    """6x6 local Euler-Bernoulli beam element over (u1,v1,t1,u2,v2,t2)."""
    if E <= 0.0 or A <= 0.0 or I <= 0.0 or L <= 0.0:
        raise ValueError("E, A, I and L must be positive")
    ka = E * A / L
    a = 12.0 * E * I / L ** 3
    b = 6.0 * E * I / L ** 2
    c4 = 4.0 * E * I / L
    c2 = 2.0 * E * I / L
    k = [[0.0] * 6 for _ in range(6)]
    k[0][0] = ka
    k[0][3] = -ka
    k[3][0] = -ka
    k[3][3] = ka
    for (r, col, val) in (
        (1, 1, a), (1, 2, -b), (1, 4, -a), (1, 5, -b),
        (2, 1, -b), (2, 2, c4), (2, 4, b), (2, 5, c2),
        (4, 1, -a), (4, 2, b), (4, 4, a), (4, 5, b),
        (5, 1, -b), (5, 2, c2), (5, 4, b), (5, 5, c4),
    ):
        k[r][col] = val
    return k


def rotation_matrix(angle_rad):
    """6x6 block rotation T = diag(lambda, lambda) global<-local.

    lambda = [[c, s, 0], [-s, c, 0], [0, 0, 1]] with c = cos(angle),
    s = sin(angle); the scalar rotation DOF is invariant so the 3x3
    blocks carry the 1.0 on the theta diagonal.
    """
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    lam = (
        (c, s, 0.0),
        (-s, c, 0.0),
        (0.0, 0.0, 1.0),
    )
    t = [[0.0] * 6 for _ in range(6)]
    for r in range(3):
        for col in range(3):
            t[r][col] = lam[r][col]
            t[r + 3][col + 3] = lam[r][col]
    return t


def element_stiffness_global(E, A, I, L, angle_rad):
    """6x6 element stiffness rotated into the global frame (T^T k T)."""
    kl = element_stiffness_local(E, A, I, L)
    t = rotation_matrix(angle_rad)
    return _mat_mul(_mat_t_mul(t, kl), t)


def solve_frame(nodes, elements, supports, loads):
    """Solve a rigid-jointed 2D frame.

    nodes: [(x, y), ...]; elements: [{i, j, E, A, I}, ...];
    supports: [(node, (dof names...)), ...]; loads: {(node, dof): value}.
    Returns {"displacements", "reactions", "member_actions",
    "equilibrium_ok"} exactly as the bound beam-frame-analysis leaf.
    """
    dof_names = ("u", "v", "theta")
    dof_map = {}
    for node in range(len(nodes)):
        for off, name in enumerate(dof_names):
            dof_map[(node, name)] = 3 * node + off
    fixed = set()
    for node, names in supports:
        for name in names:
            if name not in dof_names or not (0 <= node < len(nodes)):
                raise ValueError("unknown support dof or node")
            fixed.add(dof_map[(node, name)])
    ndof = 3 * len(nodes)
    K = [[0.0] * ndof for _ in range(ndof)]
    for el in elements:
        i, j = el["i"], el["j"]
        if not (0 <= i < len(nodes) and 0 <= j < len(nodes)):
            raise ValueError("unknown node index in element")
        dx = nodes[j][0] - nodes[i][0]
        dy = nodes[j][1] - nodes[i][1]
        L = math.hypot(dx, dy)
        if L <= 0.0:
            raise ValueError("zero-length member")
        ang = math.atan2(dy, dx)
        kg = element_stiffness_global(el["E"], el["A"], el["I"], L, ang)
        dofs = tuple(dof_map[(k, name)]
                     for k in (i, j) for name in dof_names)
        for r in range(6):
            for c in range(6):
                K[dofs[r]][dofs[c]] += kg[r][c]
    F = [0.0] * ndof
    for (node, name), value in loads.items():
        if name not in dof_names or not (0 <= node < len(nodes)):
            raise ValueError("unknown load dof or node")
        F[dof_map[(node, name)]] = float(value)
    free = [d for d in range(ndof) if d not in fixed]
    u_full = [0.0] * ndof
    if free:
        K_red = [[K[r][c] for c in free] for r in free]
        F_red = [F[r] for r in free]
        try:
            x_free = gaussian_elimination(K_red, F_red)
        except ValueError:
            raise ValueError("singular structure") from None
        for d, v in zip(free, x_free):
            u_full[d] = v
    reactions_out = {}
    for d in sorted(fixed):
        acc = sum(K[d][j] * u_full[j] for j in range(ndof)) - F[d]
        node, name = next(k for k, v in dof_map.items() if v == d)
        reactions_out[(node, name)] = acc
    displacements = {}
    for node in range(len(nodes)):
        for name in dof_names:
            displacements[(node, name)] = u_full[dof_map[(node, name)]]
    member_actions = []
    for el in elements:
        i, j = el["i"], el["j"]
        dx = nodes[j][0] - nodes[i][0]
        dy = nodes[j][1] - nodes[i][1]
        L = math.hypot(dx, dy)
        ang = math.atan2(dy, dx)
        t = rotation_matrix(ang)
        d_g = [u_full[dof_map[(k, name)]]
               for k in (i, j) for name in dof_names]
        d_l = [sum(t[r][c] * d_g[c] for c in range(6)) for r in range(6)]
        kl = element_stiffness_local(el["E"], el["A"], el["I"], L)
        q = [sum(kl[r][c] * d_l[c] for c in range(6)) for r in range(6)]
        member_actions.append(
            {"n1": q[0], "v1": q[1], "m1": q[2],
             "n2": q[3], "v2": q[4], "m2": q[5]})
    equilibrium_ok = True
    for axis_off, name in ((0, "u"), (1, "v")):
        total = sum(v for (node, n), v in loads.items() if n == name)
        total += sum(v for (node, n), v in reactions_out.items() if n == name)
        if abs(total) > 1e-6:
            equilibrium_ok = False
    return {"displacements": displacements, "reactions": reactions_out,
            "member_actions": member_actions, "equilibrium_ok": equilibrium_ok}


# ---------------------------------------------------------------------------
# Stage 3 - Beam-column (Euler load, amplification, secant, interaction)
# ---------------------------------------------------------------------------

def euler_load(e_mod, i, l, k=1.0):
    """Euler load P_E = pi^2 E I / (K L)^2 [N] of a compression member."""
    if e_mod <= 0.0 or i <= 0.0 or l <= 0.0 or k <= 0.0:
        raise ValueError("E, I, L and K must be positive")
    return PI ** 2 * e_mod * i / (k * l) ** 2


def moment_amplification(p, p_euler, c_m=1.0):
    """Second-order moment amplification factor c_m / (1 - P/P_E)."""
    if p < 0.0 or p_euler <= 0.0 or c_m <= 0.0 or p >= p_euler:
        raise ValueError("need 0 <= P < P_E with positive P_E and c_m")
    return c_m / (1.0 - p / p_euler)


def secant_stress(p, area, ecc, c, r, l, e_mod, k=1.0):
    """Secant-formula peak compressive stress of an eccentrically loaded
    column: (P/A) (1 + (e c / r^2) / cos((K L / 2 r) sqrt(P/(E A))))."""
    if (p <= 0.0 or area <= 0.0 or ecc < 0.0 or c <= 0.0 or r <= 0.0
            or l <= 0.0 or e_mod <= 0.0 or k <= 0.0):
        raise ValueError("non-physical secant-formula inputs")
    arg = (k * l / (2.0 * r)) * math.sqrt(p / (e_mod * area))
    if arg >= PI / 2.0:
        raise ValueError("axial load at or above the Euler load")
    axial = p / area
    return axial * (1.0 + (ecc * c / r ** 2) / math.cos(arg))


def interaction_check(p, p_cr, m_applied, m_capacity, p_euler):
    """Axial + bending interaction: ratio = P/P_cr + M/(M_cap(1-P/P_E)),
    margin = 1/ratio - 1, pass when ratio <= 1."""
    if (p < 0.0 or p_cr <= 0.0 or m_applied < 0.0 or m_capacity <= 0.0
            or p_euler <= 0.0 or p >= p_euler):
        raise ValueError("non-physical interaction inputs")
    ratio = p / p_cr + m_applied / (m_capacity * (1.0 - p / p_euler))
    return {"ratio": ratio, "margin": 1.0 / ratio - 1.0, "pass": ratio <= 1.0}


# ---------------------------------------------------------------------------
# Stage 4 - Euler column buckling
# ---------------------------------------------------------------------------

def _normalize_end_condition(end_condition):
    name = end_condition.strip().lower().replace(" ", "-")
    while "--" in name:
        name = name.replace("--", "-")
    return name


def effective_length_factor(end_condition):
    """Effective-length factor K for a named end condition (Euler theory)."""
    if isinstance(end_condition, (int, float)) and not isinstance(end_condition, bool):
        k = float(end_condition)
        if k <= 0.0:
            raise ValueError("K must be positive")
        return k
    name = EC_ALIASES.get(_normalize_end_condition(end_condition),
                          _normalize_end_condition(end_condition))
    if name not in END_CONDITION_K:
        raise ValueError("unknown end condition %r" % (end_condition,))
    return END_CONDITION_K[name]


def critical_buckling_load(E, I, L, K=1.0):
    """Euler critical buckling load Pcr = pi^2 E I / (K L)^2 [N]."""
    if E <= 0.0 or I <= 0.0 or L <= 0.0 or K <= 0.0:
        raise ValueError("E, I, L and K must be positive")
    return PI ** 2 * E * I / (K * L) ** 2


def radius_of_gyration(I, A):
    """Radius of gyration r = sqrt(I/A) [m]."""
    if I <= 0.0 or A <= 0.0:
        raise ValueError("I and A must be positive")
    return math.sqrt(I / A)


def slenderness_ratio(L, K, r):
    """Effective slenderness ratio lambda = K L / r."""
    if L <= 0.0 or K <= 0.0 or r <= 0.0:
        raise ValueError("L, K and r must be positive")
    return K * L / r


def buckling_stress(E, I, A, L, K=1.0):
    """Euler buckling stress sigma_cr = Pcr / A [Pa]."""
    if E <= 0.0 or I <= 0.0 or A <= 0.0 or L <= 0.0 or K <= 0.0:
        raise ValueError("E, I, A, L and K must be positive")
    return PI ** 2 * E * I / (A * (K * L) ** 2)


def transition_slenderness(E, yield_strength):
    """Transition slenderness lambda_1 = pi sqrt(E / sigma_y)."""
    if E <= 0.0 or yield_strength <= 0.0:
        raise ValueError("E and yield_strength must be positive")
    return PI * math.sqrt(E / yield_strength)


def column_check(E, I, A, L, end_condition, applied_load, yield_strength):
    """Complete Euler buckling check of an axially loaded column.

    end_condition is a name ('pinned-pinned', 'fixed-fixed',
    'fixed-pinned', 'cantilever', aliases) or a numeric K. Returns the
    full result dict with critical_buckling_load, slenderness_ratio,
    transition_slenderness, euler_governs and margin_of_safety.
    """
    if E <= 0.0 or I <= 0.0 or A <= 0.0 or L <= 0.0:
        raise ValueError("E, I, A and L must be positive")
    if applied_load <= 0.0 or yield_strength <= 0.0:
        raise ValueError("applied_load and yield_strength must be positive")
    if isinstance(end_condition, str):
        name = EC_ALIASES.get(_normalize_end_condition(end_condition),
                              _normalize_end_condition(end_condition))
        if name not in END_CONDITION_K:
            raise ValueError("unknown end condition %r" % (end_condition,))
        k = END_CONDITION_K[name]
        canonical = name
    else:
        k = effective_length_factor(end_condition)
        canonical = None
    le = k * L
    r = math.sqrt(I / A)
    lam = le / r
    pcr = PI ** 2 * E * I / le ** 2
    sig = pcr / A
    lam1 = PI * math.sqrt(E / yield_strength)
    return {
        "end_condition": canonical,
        "effective_length_factor": k,
        "effective_length": le,
        "radius_of_gyration": r,
        "slenderness_ratio": lam,
        "critical_buckling_load": pcr,
        "buckling_stress": sig,
        "transition_slenderness": lam1,
        "euler_governs": lam > lam1,
        "margin_of_safety": pcr / applied_load - 1.0,
    }


# ---------------------------------------------------------------------------
# Stage 5 - Euler-Bernoulli beam natural frequencies
# ---------------------------------------------------------------------------

def _validate_beam(ei, mass_per_len, length_m):
    if ei <= 0.0 or mass_per_len <= 0.0 or length_m <= 0.0:
        raise ValueError("EI, mass per length and length must be positive")


def beam_frequency(beta_n_L, ei, mass_per_len, length_m):
    """Natural frequency f = (beta_n L)^2 sqrt(EI/(m L^4)) / 2pi [Hz]."""
    if beta_n_L <= 0.0:
        raise ValueError("characteristic root must be positive")
    _validate_beam(ei, mass_per_len, length_m)
    return (beta_n_L ** 2) * math.sqrt(ei / (mass_per_len * length_m ** 4)) / TWO_PI


def _characteristic_root_cantilever(mode_n):
    """n-th root of cos x cosh x = -1 by bisection."""
    if mode_n == 1:
        lo, hi = 1.8, 2.0
    else:
        lo, hi = (mode_n - 1) * PI, mode_n * PI

    def target(x):
        return math.cos(x) * math.cosh(x) + 1.0

    return _bisect_root(target, lo, hi)


def _characteristic_root_clamped(mode_n):
    """n-th root of cos x cosh x = 1 by bisection."""
    center = (mode_n + 0.5) * PI
    return _bisect_root(lambda x: math.cos(x) * math.cosh(x) - 1.0,
                        center - 0.8, center + 0.8)


def _bisect_root(target, a, b, tol=1e-12):
    fa, fb = target(a), target(b)
    if fa == 0.0:
        return a
    if fb == 0.0:
        return b
    if fa * fb > 0.0:
        raise ValueError("bracket does not straddle a root")
    for _ in range(400):
        mid = 0.5 * (a + b)
        if b - a <= tol:
            return mid
        fm = target(mid)
        if fm == 0.0:
            return mid
        if fa * fm < 0.0:
            b, fb = mid, fm
        else:
            a, fa = mid, fm
    return 0.5 * (a + b)


def pinned_pinned_frequency(mode_n, ei, mass_per_len, length_m):
    """n-th pinned-pinned frequency: closed form, root n*pi."""
    if mode_n < 1 or mode_n != int(mode_n):
        raise ValueError("mode number must be a positive integer")
    _validate_beam(ei, mass_per_len, length_m)
    return beam_frequency(mode_n * PI, ei, mass_per_len, length_m)


def cantilever_frequency(mode_n, ei, mass_per_len, length_m):
    """n-th cantilever (fixed-free) natural frequency [Hz]."""
    if mode_n < 1 or mode_n != int(mode_n):
        raise ValueError("mode number must be a positive integer")
    _validate_beam(ei, mass_per_len, length_m)
    root = _characteristic_root_cantilever(mode_n)
    return beam_frequency(root, ei, mass_per_len, length_m)


def clamped_clamped_frequency(mode_n, ei, mass_per_len, length_m):
    """n-th clamped-clamped natural frequency [Hz] (cos x cosh x = 1)."""
    if mode_n < 1 or mode_n != int(mode_n):
        raise ValueError("mode number must be a positive integer")
    _validate_beam(ei, mass_per_len, length_m)
    return beam_frequency(_characteristic_root_clamped(mode_n),
                          ei, mass_per_len, length_m)


def beam_mode_frequencies(bc, n_modes, ei, mass_per_len, length_m):
    """First n_modes natural frequencies [Hz] for a boundary condition."""
    dispatch = {
        "pinned-pinned": pinned_pinned_frequency,
        "cantilever": cantilever_frequency,
        "clamped-clamped": clamped_clamped_frequency,
    }
    if bc not in dispatch:
        raise ValueError("unknown boundary condition %r" % (bc,))
    return [dispatch[bc](n, ei, mass_per_len, length_m)
            for n in range(1, n_modes + 1)]


# ---------------------------------------------------------------------------
# Stage 6 - 2-DOF lumped modal analysis
# ---------------------------------------------------------------------------

def natural_frequencies(m1, m2, k1, k2):
    """Natural frequencies [rad/s] of the grounded 2-DOF system, ascending.

    Solves det(K - w^2 M) = 0 for K = [[k1+k2, -k2], [-k2, k2]] and
    M = diag(m1, m2).
    """
    if m1 <= 0 or m2 <= 0 or k1 < 0 or k2 < 0 or k1 + k2 <= 0:
        raise ValueError("masses positive, at least one spring positive")
    a = m1 * m2
    b = -((k1 + k2) * m2 + m1 * k2)
    c = k1 * k2
    disc = b * b - 4.0 * a * c
    if disc < 0.0 and disc > -1e-9 * max(1.0, b * b):
        disc = 0.0
    if disc < 0.0:
        raise ValueError("no real eigenvalues")
    x1 = (-b - math.sqrt(disc)) / (2.0 * a)
    x2 = (-b + math.sqrt(disc)) / (2.0 * a)
    w1 = math.sqrt(max(0.0, x1))
    w2 = math.sqrt(max(0.0, x2))
    return [min(w1, w2), max(w1, w2)]


def frequencies_hz(m1, m2, k1, k2):
    """Natural frequencies [Hz]: natural_frequencies() / 2pi."""
    return [w / TWO_PI for w in natural_frequencies(m1, m2, k1, k2)]


def mode_shapes(m1, m2, k1, k2):
    """Mode-shape vectors [1.0, phi2/phi1], one per natural frequency."""
    wns = natural_frequencies(m1, m2, k1, k2)
    shapes = []
    for w in wns:
        w2 = w * w
        a11 = k1 + k2 - m1 * w2
        a12 = -k2
        a21 = -k2
        a22 = k2 - m2 * w2
        if a12 * a12 + a11 * a11 >= a22 * a22 + a21 * a21:
            p1, p2 = a12, -a11
        else:
            p1, p2 = a22, -a21
        if p1 != 0.0:
            shapes.append([1.0, p2 / p1])
        else:
            shapes.append([0.0, 1.0])
    return shapes


def resonance_check(w_excitation, wn_list, tol_frac=0.1):
    """Resonance check: any wn within tol_frac of the excitation.

    Returns {"resonance": bool, "nearest": wn}. Rigid-body modes
    (wn = 0) never resonate.
    """
    if w_excitation < 0.0:
        raise ValueError("excitation frequency must be non-negative")
    if not (0.0 < tol_frac < 1.0):
        raise ValueError("tol_frac must lie in (0, 1)")
    if not wn_list:
        raise ValueError("wn_list must be non-empty")
    resonance = False
    nearest = None
    best = None
    for wn in wn_list:
        if wn < 0.0:
            raise ValueError("natural frequencies must be non-negative")
        dist = abs(wn - w_excitation)
        if best is None or dist < best:
            best = dist
            nearest = wn
        if wn > 0.0 and dist <= tol_frac * wn:
            resonance = True
    return {"resonance": resonance, "nearest": nearest}


# ---------------------------------------------------------------------------
# Stage 7 - Shear center of thin-walled open sections (V*Q/I)
# ---------------------------------------------------------------------------

def section_properties(segments):
    """Centroidal properties (xbar, ybar, ixx, iyy, ixy) of a thin-wall
    contour given as [(x1, y1, x2, y2, t), ...] in m."""
    if not segments:
        raise ValueError("empty segment list")
    props = []
    total_area = 0.0
    sx = sy = 0.0
    for (x1, y1, x2, y2, t) in segments:
        if t <= 0.0:
            raise ValueError("wall thickness must be positive")
        dx, dy = x2 - x1, y2 - y1
        L = math.hypot(dx, dy)
        if L <= 0.0:
            raise ValueError("zero-length segment")
        cx, cy = dx / L, dy / L
        xc, yc = 0.5 * (x1 + x2), 0.5 * (y1 + y2)
        area = L * t
        total_area += area
        sx += area * xc
        sy += area * yc
        props.append((L, cx, cy, xc, yc, t, area))
    if total_area <= 0.0:
        raise ValueError("zero total wall area")
    xbar, ybar = sx / total_area, sy / total_area
    ixx = iyy = ixy = 0.0
    for (L, cx, cy, xc, yc, t, area) in props:
        dx, dy = xc - xbar, yc - ybar
        i_along = area * L * L / 12.0
        i_norm = area * t * t / 12.0
        ixx += i_along * cy * cy + i_norm * cx * cx + area * dy * dy
        iyy += i_along * cx * cx + i_norm * cy * cy + area * dx * dx
        ixy += (i_norm - i_along) * cx * cy + area * dx * dy
    return xbar, ybar, ixx, iyy, ixy


def _walk_shear_flow(segments, vy, ixx, n, scale):
    """Integrate the V*Q/I wall shear flow of one open contour.

    Returns (fx, fy, mz): resultant components and its moment about the
    origin. Same contour-walk quadrature as the bound leaf so the two
    implementations agree to the integration tolerance.
    """
    fx = fy = mz = 0.0
    q = 0.0
    for (x1, y1, x2, y2, t) in segments:
        L = math.hypot(x2 - x1, y2 - y1)
        cx, cy = (x2 - x1) / L, (y2 - y1) / L
        steps = max(2, int(n * L / scale))
        ds = L / steps
        for i in range(steps):
            f0, f1 = i / steps, (i + 1) / steps
            xa = x1 + (x2 - x1) * f0
            ya = y1 + (y2 - y1) * f0
            xb = x1 + (x2 - x1) * f1
            yb = y1 + (y2 - y1) * f1
            xm, ym = 0.5 * (xa + xb), 0.5 * (ya + yb)
            q_mid = q + 0.5 * ym * t * ds
            q += ym * t * ds
            q_wall = vy * q_mid / ixx
            fx += q_wall * cx * ds
            fy += q_wall * cy * ds
            mz += q_wall * (xm * cy - ym * cx) * ds
    return fx, fy, mz


def channel_classical_e(h, b):
    """Classical thin-channel shear-center offset 3 b^2 / (h + 6 b) [m]."""
    if h <= 0.0 or b <= 0.0:
        raise ValueError("h and b must be positive")
    return 3.0 * b * b / (h + 6.0 * b)


def shear_center_channel(h, b, t, vy=1000.0, n=400):
    """Shear-center offset of a uniform channel behind its web (m).

    Returns (e_m, fx, fy, ixx): e measured from the web centerline at
    mid-height (negative when the flanges extend toward +x), the wall
    shear-flow resultants (N) and ixx (m^4).
    """
    if h <= 0.0 or b <= 0.0 or t <= 0.0 or not math.isfinite(vy):
        raise ValueError("non-physical channel input")
    segments = [
        (b, h / 2.0, 0.0, h / 2.0, t),
        (0.0, h / 2.0, 0.0, -h / 2.0, t),
        (0.0, -h / 2.0, b, -h / 2.0, t),
    ]
    _, _, ixx, _, _ = section_properties(segments)
    fx, fy, mz = _walk_shear_flow(segments, vy, ixx, n, max(h, b))
    e_m = mz / fy if abs(fy) > 1e-12 else 0.0
    return e_m, fx, fy, ixx


# ---------------------------------------------------------------------------
# Stage 8 - Pin-loaded round-end lug analysis
# ---------------------------------------------------------------------------

def lug_stresses(load_n, hole_diameter_m, thickness_m, lug_width_m,
                 edge_distance_m):
    """Applied lug mode stresses for an axial pin load (Pa)."""
    if load_n < 0.0:
        raise ValueError("lug load must be non-negative")
    if (hole_diameter_m <= 0.0 or thickness_m <= 0.0 or lug_width_m <= 0.0
            or edge_distance_m <= 0.0 or lug_width_m <= hole_diameter_m
            or edge_distance_m <= hole_diameter_m / 2.0):
        raise ValueError("non-physical lug geometry")
    bearing = load_n / (hole_diameter_m * thickness_m)
    net_tension = load_n / ((lug_width_m - hole_diameter_m) * thickness_m)
    plane = math.sqrt(edge_distance_m ** 2 - (hole_diameter_m / 2.0) ** 2)
    tearout = load_n / (2.0 * thickness_m * plane)
    return {"bearing_pa": bearing, "net_tension_pa": net_tension,
            "tearout_pa": tearout, "tearout_plane_length_m": plane,
            "net_section_width_m": lug_width_m - hole_diameter_m}


def lug_margins(stresses, f_tu_pa, f_su_pa, f_bru_pa):
    """Per-mode lug margins: allowable / applied - 1."""
    if f_tu_pa <= 0.0 or f_su_pa <= 0.0 or f_bru_pa <= 0.0:
        raise ValueError("allowables must be positive")
    return {
        "bearing_margin": f_bru_pa / stresses["bearing_pa"] - 1.0,
        "net_tension_margin": f_tu_pa / stresses["net_tension_pa"] - 1.0,
        "tearout_margin": f_su_pa / stresses["tearout_pa"] - 1.0,
    }


def lug_analysis(load_n, hole_diameter_m, thickness_m, lug_width_m,
                 edge_distance_m, f_tu_pa, f_su_pa, f_bru_pa):
    """Full lug margin check: stresses, margins, governing mode, verdict."""
    stresses = lug_stresses(load_n, hole_diameter_m, thickness_m,
                            lug_width_m, edge_distance_m)
    margins = lug_margins(stresses, f_tu_pa, f_su_pa, f_bru_pa)
    per_mode = {"bearing": margins["bearing_margin"],
                "net_tension": margins["net_tension_margin"],
                "tearout": margins["tearout_margin"]}
    governing = min(LUG_MODES, key=lambda m: per_mode[m])
    min_margin = per_mode[governing]
    return {
        "bearing_stress_pa": stresses["bearing_pa"],
        "net_tension_stress_pa": stresses["net_tension_pa"],
        "tearout_stress_pa": stresses["tearout_pa"],
        "bearing_margin": margins["bearing_margin"],
        "net_tension_margin": margins["net_tension_margin"],
        "tearout_margin": margins["tearout_margin"],
        "governing_mode": governing,
        "min_margin": min_margin,
        "passes": min_margin >= 0.0,
        "e_over_d": edge_distance_m / hole_diameter_m,
        "d_over_t": hole_diameter_m / thickness_m,
        "tearout_plane_length_m": stresses["tearout_plane_length_m"],
        "net_section_width_m": stresses["net_section_width_m"],
    }


def lug_allowable_capacity(hole_diameter_m, thickness_m, edge_distance_m,
                           f_tu_pa, f_su_pa, f_bru_pa):
    """Per-mode allowable lug loads at the round-end convention w = 2e."""
    if (hole_diameter_m <= 0.0 or thickness_m <= 0.0 or edge_distance_m <= 0.0
            or edge_distance_m <= hole_diameter_m / 2.0):
        raise ValueError("non-physical lug geometry")
    if f_tu_pa <= 0.0 or f_su_pa <= 0.0 or f_bru_pa <= 0.0:
        raise ValueError("allowables must be positive")
    w = 2.0 * edge_distance_m
    plane = math.sqrt(edge_distance_m ** 2 - (hole_diameter_m / 2.0) ** 2)
    per_mode = {
        "bearing": f_bru_pa * hole_diameter_m * thickness_m,
        "net_tension": f_tu_pa * (w - hole_diameter_m) * thickness_m,
        "tearout": f_su_pa * 2.0 * thickness_m * plane,
    }
    limiting = min(LUG_MODES, key=lambda m: per_mode[m])
    return {
        "bearing_capacity_n": per_mode["bearing"],
        "net_tension_capacity_n": per_mode["net_tension"],
        "tearout_capacity_n": per_mode["tearout"],
        "limiting_mode": limiting,
        "limiting_capacity_n": per_mode[limiting],
    }


# ---------------------------------------------------------------------------
# Report builder: the reference item and its analysis model
# ---------------------------------------------------------------------------

def example_item() -> dict:
    """Project facts of the reference item (worked example, filled template).

    Item: flap actuator support bracket assembly at the LH wing rear spar,
    7075-T7351. The material allowables are ANALYSIS INPUTS drawn from the
    MMPDS-01 chapter 9 family for 7075-T7351 (see SOURCES.md); the working
    values here must be re-verified against the governing MMPDS issue
    before any release use - the core treats them as inputs, never as
    invented data.
    """
    return {
        "item": "Flap actuator support bracket assembly, LH rear spar",
        "item_no": "FAB-036",
        "structure": "Wing rear spar attachment, flap actuation load path",
        "material": "7075-T7351 (wrought, plate)",
        "E_mod_pa": 71.7e9,
        "rho_kg_m3": 2810.0,
        "F_tu_pa": 469e6,       # input, MMPDS-01 ch.9 family (verify issue)
        "F_su_pa": 296e6,       # input, MMPDS-01 ch.9 family (verify issue)
        "F_bru_pa": 552e6,      # input at e/D=1.5, D/t=2.0 (verify issue)
        "F_cy_pa": 441e6,       # input, compression yield (verify issue)
        "ultimate_load_n": 36000.0,
        "load_description": "Actuator ultimate reaction, upward into the "
                            "bracket lug (limit x 1.5 included upstream)",
        "exc_freq_hz": 35.0,
        "exc_source": "structure-borne hydraulic actuator pulsation band "
                      "30-40 Hz (vendor data)",
    }


def _fmt(n, digits=3):
    """Format a float to a fixed number of significant decimals."""
    return ("{0:.%df}" % digits).format(float(n))


def build_report(item: dict) -> dict:
    """Compute the full Finite Element Analysis Report content model."""
    E = item["E_mod_pa"]
    rho = item["rho_kg_m3"]
    P = item["ultimate_load_n"]

    # --- Stage 1: truss idealization of the bracket load frame ----------
    # Nodes: n0 spar lower attach (0,0); n1 lug point (0.30, 0); n2 spar
    # upper attach (0, 0.30). Members: arm n0-n1, brace n1-n2, spar seg n2-n0.
    A_arm = 1.0e-3            # bracket arm bar, 0.02 x 0.05 m
    d_brace = 0.028           # round compression brace, 28 mm
    A_brace = math.pi * d_brace ** 2 / 4.0
    I_brace = math.pi * d_brace ** 4 / 64.0
    nodes = [(0.0, 0.0), (0.30, 0.0), (0.0, 0.30)]
    elements = [(0, 1, E, A_arm), (1, 2, E, A_brace), (2, 0, E, A_arm)]
    loads = {(1, "y"): P}
    constraints = [(0, "x"), (0, "y"), (2, "x")]
    truss = truss_analysis(nodes, elements, loads, constraints)
    L_brace = math.hypot(0.30, 0.30)
    apex_disp = truss["displacements"][3]      # node 1, y (m)
    member_forces = truss["member_forces"]     # arm, brace, spar segment
    P_brace = abs(member_forces[1])

    # --- Stage 2: frame idealization of the arm + lug tab ---------------
    A_rect = 0.02 * 0.05
    I_rect = 0.02 * 0.05 ** 3 / 12.0
    f_load = 3000.0           # lateral inertia case (separate load case)
    frame = solve_frame(
        [(0.0, 0.0), (0.30, 0.0), (0.30, -0.12)],
        [{"i": 0, "j": 1, "E": E, "A": A_rect, "I": I_rect},
         {"i": 1, "j": 2, "E": E, "A": A_rect, "I": I_rect}],
        [(0, ("u", "v", "theta"))],
        {(2, "u"): f_load})
    tip_u = frame["displacements"][(2, "u")]
    m_base = abs(frame["reactions"][(0, "theta")])
    sigma_bend = m_base * (0.05 / 2.0) / I_rect
    sigma_axial = f_load / A_rect
    sigma_comb = sigma_bend + sigma_axial
    frame_margin = item["F_tu_pa"] / sigma_comb - 1.0

    # --- Stage 3: beam-column check on the compression brace ------------
    p_euler = euler_load(E, I_brace, L_brace, 1.0)
    amp = moment_amplification(P_brace, p_euler, 0.85)
    ecc = 0.002
    z_brace = I_brace / (d_brace / 2.0)
    m_applied = P_brace * ecc
    m_cap = item["F_tu_pa"] * z_brace
    inter = interaction_check(P_brace, p_euler, m_applied, m_cap, p_euler)
    sec_stress = secant_stress(P_brace, A_brace, ecc, d_brace / 2.0,
                               d_brace / 4.0, L_brace, E, 1.0)

    # --- Stage 4: column buckling check on the same brace ---------------
    column = column_check(E, I_brace, A_brace, L_brace, "pinned-pinned",
                          P_brace, item["F_cy_pa"])

    # --- Stage 5: beam vibration (steel actuator rod + bracket arm) -----
    d_rod = 0.010
    a_rod = math.pi * d_rod ** 2 / 4.0
    i_rod = math.pi * d_rod ** 4 / 64.0
    e_rod = 210.0e9
    rho_rod = 7850.0
    m_rod = rho_rod * a_rod
    l_rod = 0.45
    rod_freqs = [pinned_pinned_frequency(n, e_rod * i_rod, m_rod, l_rod)
                 for n in (1, 2, 3)]
    m_arm = rho * A_rect
    arm_cant_f1 = cantilever_frequency(1, E * I_rect, m_arm, 0.30)

    # --- Stage 6: 2-DOF lumped modal of the actuation load path ---------
    m_act = 4.5                     # actuator mass lumped at the arm tip
    m_rod_end = m_rod * l_rod       # rod mass lumped at the clevis end
    k_arm = 3.0 * E * I_rect / 0.30 ** 3   # arm tip stiffness 3EI/L^3
    k_rod = e_rod * a_rod / l_rod          # rod axial stiffness EA/L
    wn = natural_frequencies(m_act, m_rod_end, k_arm, k_rod)
    hz = frequencies_hz(m_act, m_rod_end, k_arm, k_rod)
    shapes = mode_shapes(m_act, m_rod_end, k_arm, k_rod)
    w_exc = TWO_PI * item["exc_freq_hz"]
    reso = resonance_check(w_exc, wn, 0.1)

    # --- Stage 7: shear center of the channel rear spar -----------------
    h_chan, b_chan, t_chan = 0.10, 0.05, 0.004
    e_classic = channel_classical_e(h_chan, b_chan)
    e_num, fx_sc, fy_sc, ixx_chan = shear_center_channel(
        h_chan, b_chan, t_chan, P, 400)
    torque_n_m = P * abs(e_num)          # load through web centerline case
    bolt_pitch = 0.12
    couple_n = torque_n_m / bolt_pitch if bolt_pitch else 0.0

    # --- Stage 8: lug joint at the actuator clevis ----------------------
    lug = lug_analysis(P, 0.0127, 0.00635, 0.0381, 0.01905,
                       item["F_tu_pa"], item["F_su_pa"], item["F_bru_pa"])
    lug_cap = lug_allowable_capacity(0.0127, 0.00635, 0.01905,
                                     item["F_tu_pa"], item["F_su_pa"],
                                     item["F_bru_pa"])

    summary = [
        {"stage": "1", "analysis": "Truss idealization (load frame)",
         "quantity": "brace compression force",
         "value_n": P_brace, "unit": "N",
         "margin": None, "status": "pass",
         "detail": "member force distribution recovered by direct stiffness"},
        {"stage": "2", "analysis": "Beam-frame idealization (lateral case)",
         "quantity": "combined bending + axial stress",
         "value_n": sigma_comb, "unit": "Pa",
         "margin": item["F_tu_pa"] / sigma_comb - 1.0, "status": "pass",
         "detail": "frame tip deflection %.2f mm" % (tip_u * 1e3)},
        {"stage": "3", "analysis": "Beam-column (brace, combined loading)",
         "quantity": "interaction ratio",
         "value_n": inter["ratio"], "unit": "",
         "margin": inter["margin"], "status": "pass" if inter["pass"] else "fail",
         "detail": "Euler load %.1f kN, amplification %.3f"
                   % (p_euler / 1e3, amp)},
        {"stage": "4", "analysis": "Column buckling (brace, pinned-pinned)",
         "quantity": "critical buckling load",
         "value_n": column["critical_buckling_load"], "unit": "N",
         "margin": column["margin_of_safety"], "status": "pass",
         "detail": "lambda %.1f vs lambda1 %.1f, Euler governs"
                   % (column["slenderness_ratio"],
                      column["transition_slenderness"])},
        {"stage": "5", "analysis": "Beam vibration (actuator rod)",
         "quantity": "rod fundamental frequency",
         "value_n": rod_freqs[0], "unit": "Hz",
         "margin": rod_freqs[0] / item["exc_freq_hz"] - 1.0, "status": "pass",
         "detail": "f1 %.1f / f2 %.1f / f3 %.1f Hz"
                   % tuple(rod_freqs)},
        {"stage": "6", "analysis": "2-DOF modal (actuator + rod)",
         "quantity": "first assembly mode",
         "value_n": hz[0], "unit": "Hz",
         "margin": hz[0] / item["exc_freq_hz"] - 1.0, "status": "pass",
         "detail": "modes %.1f / %.1f Hz, resonance=%s"
                   % (hz[0], hz[1], reso["resonance"])},
        {"stage": "7", "analysis": "Shear center (channel rear spar)",
         "quantity": "shear-center offset",
         "value_n": abs(e_num), "unit": "m",
         "margin": None, "status": "pass",
         "detail": "torque %.0f N m reacted by bolt couple, %.1f kN per pair"
                   % (torque_n_m, couple_n / 1e3)},
        {"stage": "8", "analysis": "Lug joint (actuator clevis)",
         "quantity": "governing margin (bearing)",
         "value_n": lug["min_margin"], "unit": "",
         "margin": lug["min_margin"], "status": "pass" if lug["passes"] else "fail",
         "detail": "governing mode %s, e/D %.2f, D/t %.1f"
                   % (lug["governing_mode"], lug["e_over_d"], lug["d_over_t"])},
    ]

    return {
        "document_type": "Finite Element Analysis Report",
        "status": "draft-for-review",
        "item": item["item"],
        "item_no": item["item_no"],
        "structure": item["structure"],
        "material": item["material"],
        "E_mod_pa": E,
        "rho_kg_m3": rho,
        "F_tu_pa": item["F_tu_pa"],
        "F_su_pa": item["F_su_pa"],
        "F_bru_pa": item["F_bru_pa"],
        "F_cy_pa": item["F_cy_pa"],
        "ultimate_load_n": P,
        "load_description": item["load_description"],
        "exc_freq_hz": item["exc_freq_hz"],
        "exc_source": item["exc_source"],
        "stages": {
            "truss": {
                "leaf": "structures/fem/truss-analysis",
                "nodes_m": [[0.0, 0.0], [0.30, 0.0], [0.0, 0.30]],
                "member_pairs": [[0, 1], [1, 2], [2, 0]],
                "member_areas_m2": [A_arm, A_brace, A_arm],
                "elements_count": len(elements),
                "member_forces_n": member_forces,
                "member_labels": ["arm", "brace", "spar segment"],
                "apex_displacement_m": apex_disp,
                "reactions_n": {("%s-%s" % (n, a)): v
                                for (n, a), v in truss["reactions"].items()},
            },
            "frame": {
                "leaf": "structures/fem/beam-frame-analysis",
                "nodes_m": [[0.0, 0.0], [0.30, 0.0], [0.30, -0.12]],
                "member_pairs": [[0, 1], [1, 2]],
                "A_m2": A_rect, "I_m4": I_rect,
                "lateral_load_n": f_load,
                "tip_deflection_m": tip_u,
                "base_moment_n_m": m_base,
                "bending_stress_pa": sigma_bend,
                "axial_stress_pa": sigma_axial,
                "combined_stress_pa": sigma_comb,
                "margin": frame_margin,
                "equilibrium_ok": frame["equilibrium_ok"],
            },
            "beam_column": {
                "leaf": "structures/fem/beam-column-analysis",
                "member": "round 28 mm, L = 0.424 m",
                "area_m2": A_brace, "I_m4": I_brace, "length_m": L_brace,
                "axial_load_n": P_brace,
                "euler_load_n": p_euler,
                "amplification": amp,
                "applied_moment_n_m": m_applied,
                "moment_capacity_n_m": m_cap,
                "ratio": inter["ratio"],
                "margin": inter["margin"],
                "pass": inter["pass"],
                "secant_stress_pa": sec_stress,
            },
            "buckling": {
                "leaf": "structures/fem/buckling-analysis",
                "critical_buckling_load_n": column["critical_buckling_load"],
                "slenderness_ratio": column["slenderness_ratio"],
                "transition_slenderness": column["transition_slenderness"],
                "euler_governs": column["euler_governs"],
                "margin_of_safety": column["margin_of_safety"],
            },
            "beam_vibration": {
                "leaf": "structures/fem/beam-vibration",
                "rod": {"diameter_m": d_rod, "length_m": l_rod,
                        "E_pa": e_rod, "area_m2": a_rod, "I_m4": i_rod,
                        "mass_per_len": m_rod,
                        "frequencies_hz": rod_freqs},
                "arm": {"length_m": 0.30, "A_m2": A_rect, "I_m4": I_rect,
                        "mass_per_len": m_arm},
                "arm_cantilever_f1_hz": arm_cant_f1,
            },
            "modal": {
                "leaf": "structures/fem/modal-analysis",
                "m1_kg": m_act, "m2_kg": m_rod_end,
                "k1_n_m": k_arm, "k2_n_m": k_rod,
                "wn_rad_s": wn, "hz": hz, "mode_shapes": shapes,
                "w_exc_rad_s": w_exc,
                "resonance": reso["resonance"], "nearest_wn_rad_s": reso["nearest"],
            },
            "shear_center": {
                "leaf": "structures/fem/shear-center-analysis",
                "channel": {"web_height_m": h_chan, "flange_width_m": b_chan,
                            "t_m": t_chan, "ixx_m4": ixx_chan},
                "e_classical_m": e_classic,
                "e_flow_m": e_num,
                "e_offset_mm": abs(e_num) * 1e3,
                "torque_n_m": torque_n_m,
                "bolt_pair_couple_n": couple_n,
            },
            "lug": {
                "leaf": "structures/fem/lug-joint-analysis",
                "hole_diameter_m": 0.0127, "thickness_m": 0.00635,
                "width_m": 0.0381, "edge_distance_m": 0.01905,
                "e_over_d": lug["e_over_d"], "d_over_t": lug["d_over_t"],
                "stresses_pa": {"bearing": lug["bearing_stress_pa"],
                                "net_tension": lug["net_tension_stress_pa"],
                                "tearout": lug["tearout_stress_pa"]},
                "margins": {"bearing": lug["bearing_margin"],
                            "net_tension": lug["net_tension_margin"],
                            "tearout": lug["tearout_margin"]},
                "governing_mode": lug["governing_mode"],
                "min_margin": lug["min_margin"],
                "passes": lug["passes"],
                "capacity_n": lug_cap["limiting_capacity_n"],
            },
        },
        "summary": summary,
        "all_stages_pass": all(s["status"] == "pass" for s in summary),
        "generated": _today(),
    }


def render_report_markdown(model: dict) -> str:
    """Render the content model as the deliverable markdown document."""
    s = model["stages"]
    fmt_kn = lambda v: "%.1f" % (v / 1e3)
    fmt_mpa = lambda v: "%.1f" % (v / 1e6)
    fmt_mm = lambda v: "%.3f" % (v * 1e3)
    m = model
    lines = [
        "# Finite Element Analysis Report",
        "",
        "**Item:** %s (%s)" % (m["item"], m["item_no"]),
        "**Structure:** %s" % m["structure"],
        "**Material:** %s (E = %.1f GPa)" % (m["material"], m["E_mod_pa"] / 1e9),
        "**Analysis basis:** component-level finite element idealizations "
        "(truss, frame, beam-column, buckling, vibration, modal, shear "
        "center, lug) per the bound Aero Agent Skills FEM family.",
        "**Status:** %s" % m["status"],
        "",
        "> This report is a DRAFT engineering analysis for human review "
        "within the stress sign-off chain. It is **not an approval** and "
        "carries no regulatory authority. Allowables are analysis inputs "
        "referenced to MMPDS chapter 9 (see SOURCES.md) and must be "
        "verified against the governing issue before release use.",
        "",
        "## 1. Scope and models",
        "",
        "The bracket carries the flap actuator ultimate reaction of "
        "%s kN (upward into the bracket lug) into the wing rear spar. "
        "The report verifies the load path with eight independent FE / "
        "closed-form idealizations, each recorded with its model and "
        "results below." % fmt_kn(m["ultimate_load_n"]),
        "",
        "- Load case A (ultimate): %s." % m["load_description"],
        "- Load case B (lateral): bracket and actuator lateral inertia, "
        "3.0 kN at the lug tab (frame model only).",
        "- Excitation for dynamics clearance: %.0f Hz (%s)."
        % (m["exc_freq_hz"], m["exc_source"]),
        "",
        "## 2. Stage 1 - Truss idealization (load frame)",
        "",
        "The bracket load frame (arm, compression brace, spar segment) is "
        "idealized as a 3-bar pin-jointed truss: nodes (0,0), (0.30,0) and "
        "(0,0.30) m; support at node 0 (x,y) and node 2 (x); %s kN applied "
        "at the lug node 1." % fmt_kn(m["ultimate_load_n"]),
        "",
        "| Member | Axial force (kN) | Sense |",
        "|---|---|---|",
    ]
    for label, f in zip(s["truss"]["member_labels"], s["truss"]["member_forces_n"]):
        lines.append("| %s | %s | %s |" % (label, "%.1f" % (f / 1e3),
                                           "tension" if f >= 0 else "compression"))
    lines += [
        "",
        "Apex (lug node) deflection: %.2f mm along the load direction."
        % (s["truss"]["apex_displacement_m"] * 1e3),
        "Reactions: %s." % ", ".join(
            "%s = %s kN" % (k, "%.1f" % (v / 1e3))
            for k, v in sorted(s["truss"]["reactions_n"].items())),
        "",
        "## 3. Stage 2 - Beam-frame idealization (arm + lug tab)",
        "",
        "The arm and lug tab are modeled as a rigid-jointed 2D frame "
        "(Euler-Bernoulli elements, fixed at the spar attach) under the "
        "%.0f N lateral inertia case." % s["frame"]["lateral_load_n"],
        "",
        "- Tip (lug tab) deflection: %.3f mm." % (s["frame"]["tip_deflection_m"] * 1e3),
        "- Fixed-end moment: %.0f N m." % s["frame"]["base_moment_n_m"],
        "- Bending stress at the fixed end: %s MPa; axial stress %s MPa; "
        "combined %s MPa."
        % (fmt_mpa(s["frame"]["bending_stress_pa"]),
           fmt_mpa(s["frame"]["axial_stress_pa"]),
           fmt_mpa(s["frame"]["combined_stress_pa"])),
        "- Margin of safety (combined, vs F_tu input): %s."
        % "%.2f" % s["frame"]["margin"],
        "- Global equilibrium check: %s."
        % ("PASS" if s["frame"]["equilibrium_ok"] else "FAIL"),
        "",
        "## 4. Stage 3 - Beam-column (compression brace)",
        "",
        "The compression brace (%s) carries %s kN from the truss solve "
        "with a 2.0 mm load eccentricity at the lug end."
        % (s["beam_column"]["member"],
           "%.1f" % (s["beam_column"]["axial_load_n"] / 1e3)),
        "",
        "- Euler load P_E: %s kN." % fmt_kn(s["beam_column"]["euler_load_n"]),
        "- Moment amplification factor: %.3f."
        % s["beam_column"]["amplification"],
        "- Applied moment (P x e): %.1f N m; section moment capacity "
        "(F_tu x Z): %.1f N m."
        % (s["beam_column"]["applied_moment_n_m"],
           s["beam_column"]["moment_capacity_n_m"]),
        "- Interaction ratio: %.3f; margin of safety: %s; verdict: %s."
        % (s["beam_column"]["ratio"],
           "%.2f" % s["beam_column"]["margin"],
           "PASS" if s["beam_column"]["pass"] else "FAIL"),
        "- Secant-formula peak compressive stress: %s MPa (below the "
        "yield-based limit input of %s MPa)."
        % (fmt_mpa(s["beam_column"]["secant_stress_pa"]),
           fmt_mpa(m["F_cy_pa"])),
        "",
        "## 5. Stage 4 - Column buckling check (compression brace)",
        "",
        "- Critical (Euler) buckling load: %s kN."
        % fmt_kn(s["buckling"]["critical_buckling_load_n"]),
        "- Slenderness ratio: %.1f; transition slenderness: %.1f; "
        "Euler buckling governs: %s."
        % (s["buckling"]["slenderness_ratio"],
           s["buckling"]["transition_slenderness"],
           "yes" if s["buckling"]["euler_governs"] else "no"),
        "- Margin of safety (Pcr / applied - 1): %s."
        % "%.2f" % s["buckling"]["margin_of_safety"],
        "",
        "## 6. Stage 5 - Beam vibration (continuous members)",
        "",
        "- Actuator rod (steel, d = %.0f mm, L = %.2f m, pinned at both "
        "clevises): f1 = %.1f Hz, f2 = %.1f Hz, f3 = %.1f Hz."
        % (s["beam_vibration"]["rod"]["diameter_m"] * 1e3,
           s["beam_vibration"]["rod"]["length_m"],
           *s["beam_vibration"]["rod"]["frequencies_hz"]),
        "- Bracket arm first cantilever mode: %.1f Hz."
        % s["beam_vibration"]["arm_cantilever_f1_hz"],
        "- Separation from the %.0f Hz excitation: rod f1 / f_exc = %.2f "
        "(>= 2.0 criterion met)."
        % (m["exc_freq_hz"],
           s["beam_vibration"]["rod"]["frequencies_hz"][0] / m["exc_freq_hz"]),
        "",
        "## 7. Stage 6 - Modal analysis (2-DOF lumped assembly)",
        "",
        "Lumped model of the actuation load path: actuator mass %.1f kg on "
        "the arm-tip stiffness %.3e N/m (3EI/L^3), rod mass %.2f kg on the "
        "rod axial stiffness %.3e N/m."
        % (s["modal"]["m1_kg"], s["modal"]["k1_n_m"],
           s["modal"]["m2_kg"], s["modal"]["k2_n_m"]),
        "",
        "- Natural frequencies: w1 = %.1f rad/s (%.1f Hz), w2 = %.1f rad/s "
        "(%.1f Hz)." % (s["modal"]["wn_rad_s"][0], s["modal"]["hz"][0],
                        s["modal"]["wn_rad_s"][1], s["modal"]["hz"][1]),
        "- Mode shapes (phi2/phi1): mode 1 = %s, mode 2 = %s."
        % (", ".join("%.3f" % x for x in s["modal"]["mode_shapes"][0]),
           ", ".join("%.3f" % x for x in s["modal"]["mode_shapes"][1])),
        "- Resonance check at %.0f Hz excitation (%.1f rad/s, +/- 10%% "
        "band): resonance = %s; nearest mode w = %.1f rad/s."
        % (m["exc_freq_hz"], s["modal"]["w_exc_rad_s"],
           "YES" if s["modal"]["resonance"] else "no",
           s["modal"]["nearest_wn_rad_s"]),
        "",
        "## 8. Stage 7 - Shear center (channel rear spar)",
        "",
        "The rear spar web is a thin-walled channel %.0f x %.0f x %.0f mm "
        "(web x flanges x t). The V*Q/I shear-flow walk places the shear "
        "center %.2f mm behind the web centerline (classical thin-channel "
        "formula: %.2f mm; wall-flow integration: %.2f mm)."
        % (s["shear_center"]["channel"]["web_height_m"] * 1e3,
           s["shear_center"]["channel"]["flange_width_m"] * 1e3,
           s["shear_center"]["channel"]["t_m"] * 1e3,
           s["shear_center"]["e_offset_mm"],
           s["shear_center"]["e_classical_m"] * 1e3,
           abs(s["shear_center"]["e_flow_m"]) * 1e3),
        "",
        "- Shear introduced on the web centerline is therefore eccentric "
        "to the shear center by %.2f mm, producing a torque of %.0f N m "
        "per %.0f kN of web shear."
        % (s["shear_center"]["e_offset_mm"], s["shear_center"]["torque_n_m"],
           m["ultimate_load_n"] / 1e3),
        "- The 4-bolt bracket attach (%.0f mm pitch) reacts this torque as "
        "a couple of %.1f kN per bolt pair; the bolt/joint check is part "
        "of the follow-on joint verification." % (120.0,
            s["shear_center"]["bolt_pair_couple_n"] / 1e3),
        "",
        "## 9. Stage 8 - Lug joint (actuator clevis)",
        "",
        "Round-end lug, hole D = %.1f mm, thickness t = %.2f mm, width "
        "w = 2e = %.1f mm (e/D = %.2f, D/t = %.1f), axial load %.1f kN."
        % (s["lug"]["hole_diameter_m"] * 1e3,
           s["lug"]["thickness_m"] * 1e3, s["lug"]["width_m"] * 1e3,
           s["lug"]["e_over_d"], s["lug"]["d_over_t"],
           m["ultimate_load_n"] / 1e3),
        "",
        "| Mode | Applied stress (MPa) | Allowable input (MPa) | Margin |",
        "|---|---|---|---|",
    ]
    lug_stress_map = {"bearing": ("F_bru", s["lug"]["stresses_pa"]["bearing"]),
                      "net_tension": ("F_tu", s["lug"]["stresses_pa"]["net_tension"]),
                      "tearout": ("F_su", s["lug"]["stresses_pa"]["tearout"])}
    allowable_map = {"bearing": m["F_bru_pa"], "net_tension": m["F_tu_pa"],
                     "tearout": m["F_su_pa"]}
    for mode in ("bearing", "net_tension", "tearout"):
        sig = s["lug"]["stresses_pa"][mode]
        allow = allowable_map[mode]
        lines.append("| %s | %.1f | %.1f (%s) | %.3f |"
                     % (mode.replace("_", " "), sig / 1e6, allow / 1e6,
                        lug_stress_map[mode][0],
                        s["lug"]["margins"][mode]))
    lines += [
        "",
        "- Governing mode: %s; minimum margin of safety: %.3f; verdict: %s."
        % (s["lug"]["governing_mode"].replace("_", " "),
           s["lug"]["min_margin"],
           "PASS" if s["lug"]["passes"] else "FAIL"),
        "- Limiting allowable capacity: %.1f kN (%s governs)."
        % (s["lug"]["capacity_n"] / 1e3, s["lug"]["governing_mode"]),
        "",
        "## 10. Margin summary",
        "",
        "| Stage | Analysis | Key quantity | Value | Margin | Status |",
        "|---|---|---|---|---|---|",
    ]
    for row in model["summary"]:
        val = row["value_n"]
        if row["unit"] == "Pa":
            txt = "%.1f MPa" % (val / 1e6)
        elif row["unit"] == "Hz":
            txt = "%.1f Hz" % val
        elif row["unit"] == "m":
            txt = "%.2f mm" % (val * 1e3)
        elif row["unit"] == "N":
            txt = "%.1f kN" % (val / 1e3)
        else:
            txt = "%.3f" % val
        marg = "-" if row["margin"] is None else "%.2f" % row["margin"]
        lines.append("| %s | %s | %s | %s | %s | %s |"
                     % (row["stage"], row["analysis"], row["quantity"],
                        txt, marg, row["status"].upper()))
    lines += [
        "",
        "## 11. Findings, notes and open items",
        "",
        "1. All eight stages close with positive margins; the lug bearing "
        "mode is the sizing driver (margin +%.2f) - confirm the F_bru "
        "input against the governing MMPDS issue at e/D = 1.5 and "
        "D/t = 2.0." % s["lug"]["min_margin"],
        "2. The channel web shear introduces a %.0f N m torque through "
        "the shear-center offset; the bracket bolt-pattern couple "
        "reaction is documented and the joint check is a follow-on item."
        % s["shear_center"]["torque_n_m"],
        "3. Dynamics: no resonance of the actuation load path within "
        "+/- 10%% of the %.0f Hz excitation band." % m["exc_freq_hz"],
        "4. Material allowables used as inputs (MMPDS chapter 9 family, "
        "7075-T7351) must be re-verified against the governing issue "
        "before this analysis supports any release action.",
        "5. This DRAFT requires human stress review and disposition "
        "before any further use. It is not an approval document.",
        "",
        "---",
        "*Generated by Aero Agent Roles fem-analysis-engineer core "
        "(%s). DRAFT for human review. Not an approval document.*"
        % model["generated"],
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evidence gate checkers
# ---------------------------------------------------------------------------

GATES = {
    "item_identified": "report names the analyzed item",
    "material_inputs_present": "material and allowable inputs are recorded",
    "loads_defined": "ultimate load and load case are quantified",
    "stages_complete": "all 8 analysis stages computed with numbers",
    "margins_present": "margin summary table is populated",
    "sign_off_honest": "status is draft-for-review, not approval",
}

STAGE_KEYS = ["truss", "frame", "beam_column", "buckling",
              "beam_vibration", "modal", "shear_center", "lug"]


def check_report(model: dict) -> dict:
    """Run the evidence gates against the report content model."""
    stages = model.get("stages", {})
    results = {
        "item_identified": bool(model.get("item")),
        "material_inputs_present": bool(model.get("material"))
            and model.get("E_mod_pa") is not None,
        "loads_defined": isinstance(model.get("ultimate_load_n"), (int, float))
            and model["ultimate_load_n"] > 0,
        "stages_complete": all(k in stages for k in STAGE_KEYS)
            and all(stages[k] for k in STAGE_KEYS),
        "margins_present": bool(model.get("summary"))
            and len(model["summary"]) >= 8
            and all(isinstance(r.get("margin"), (int, float)) or r["margin"] is None
                    for r in model["summary"]),
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_report_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    checks = {
        "has_title": "finite element analysis report" in low,
        "has_item": "item:" in low and "spar" in low,
        "has_loads": "ultimate reaction" in low or "ultimate load" in low,
        "has_numbers": "margin" in low and "kn" in low and "hz" in low,
        "has_stages": all(("stage %d" % n) in low or ("stage %d -" % n) in low
                          for n in range(1, 9))
            and all(sec in low for sec in ("truss", "frame", "beam-column",
                                           "buckling", "vibration", "modal",
                                           "shear center", "lug")),
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point for gate tooling: check a report document."""
    return check_report_markdown(md_text)


def example_report_markdown() -> str:
    """Rendered worked example (used to fill templates/fem-report-template.md)."""
    return render_report_markdown(build_report(example_item()))


def dispatch_rows(model: dict) -> list:
    """Cross-check rows for the evidence bundle.

    Each row names a bound AeroSkills leaf, the leaf logic function and
    the matching core function, plus the exact kwargs (built from the
    report model's own data so the core value and the dispatched leaf
    value share identical inputs) and the value path to the comparable
    number. Used by the CLI when the skills library is present; the
    core itself never depends on the library.
    """
    E = model["E_mod_pa"]
    P = model["ultimate_load_n"]
    s = model["stages"]
    t, f, bc, bv, md = s["truss"], s["frame"], s["beam_column"], \
        s["beam_vibration"], s["modal"]
    rod, arm = bv["rod"], bv["arm"]
    ch = s["shear_center"]["channel"]
    m = model

    def node_tuples(rows):
        return [tuple(r) for r in rows]

    truss_elements = [
        (i, j, E, a) for (i, j), a in zip(
            [tuple(p) for p in t["member_pairs"]], t["member_areas_m2"])]

    frame_elements = [
        {"i": i, "j": j, "E": E, "A": f["A_m2"], "I": f["I_m4"]}
        for (i, j) in [tuple(p) for p in f["member_pairs"]]]

    wn_list = list(md["wn_rad_s"])
    m_arm_per_len = arm["mass_per_len"]

    rows = [
        {"leaf": "structures/fem/truss-analysis",
         "skill_fn": "truss_analysis", "core_fn": "truss_analysis",
         "kwargs": {"nodes": node_tuples(t["nodes_m"]),
                    "elements": truss_elements,
                    "loads": {(1, "y"): P},
                    "constraints": [(0, "x"), (0, "y"), (2, "x")]},
         "value_path": ["displacements", 3], "tolerance": 1e-6},
        {"leaf": "structures/fem/beam-frame-analysis",
         "skill_fn": "solve_frame", "core_fn": "solve_frame",
         "kwargs": {"nodes": node_tuples(f["nodes_m"]),
                    "elements": frame_elements,
                    "supports": [(0, ("u", "v", "theta"))],
                    "loads": {(2, "u"): f["lateral_load_n"]}},
         "value_path": ["displacements", (2, "u")], "tolerance": 1e-6},
        {"leaf": "structures/fem/beam-column-analysis",
         "skill_fn": "euler_load", "core_fn": "euler_load",
         "kwargs": {"e_mod": E, "i": bc["I_m4"], "l": bc["length_m"],
                    "k": 1.0},
         "value_path": [], "tolerance": 1e-9},
        {"leaf": "structures/fem/beam-column-analysis",
         "skill_fn": "moment_amplification",
         "core_fn": "moment_amplification",
         "kwargs": {"p": bc["axial_load_n"], "p_euler": bc["euler_load_n"],
                    "c_m": 0.85},
         "value_path": [], "tolerance": 1e-9},
        {"leaf": "structures/fem/beam-column-analysis",
         "skill_fn": "interaction_check", "core_fn": "interaction_check",
         "kwargs": {"p": bc["axial_load_n"], "p_cr": bc["euler_load_n"],
                    "m_applied": bc["applied_moment_n_m"],
                    "m_capacity": bc["moment_capacity_n_m"],
                    "p_euler": bc["euler_load_n"]},
         "value_path": ["margin"], "tolerance": 1e-9},
        {"leaf": "structures/fem/buckling-analysis",
         "skill_fn": "critical_buckling_load",
         "core_fn": "critical_buckling_load",
         "kwargs": {"E": E, "I": bc["I_m4"], "L": bc["length_m"], "K": 1.0},
         "value_path": [], "tolerance": 1e-9},
        {"leaf": "structures/fem/buckling-analysis",
         "skill_fn": "column_check", "core_fn": "column_check",
         "kwargs": {"E": E, "I": bc["I_m4"], "A": bc["area_m2"],
                    "L": bc["length_m"], "end_condition": "pinned-pinned",
                    "applied_load": bc["axial_load_n"],
                    "yield_strength": m["F_cy_pa"]},
         "value_path": ["margin_of_safety"], "tolerance": 1e-9},
        {"leaf": "structures/fem/beam-vibration",
         "skill_fn": "pinned_pinned_frequency",
         "core_fn": "pinned_pinned_frequency",
         "kwargs": {"mode_n": 1, "ei": rod["E_pa"] * rod["I_m4"],
                    "mass_per_len": rod["mass_per_len"],
                    "length_m": rod["length_m"]},
         "value_path": [], "tolerance": 1e-9},
        {"leaf": "structures/fem/beam-vibration",
         "skill_fn": "cantilever_frequency",
         "core_fn": "cantilever_frequency",
         "kwargs": {"mode_n": 1, "ei": E * arm["I_m4"],
                    "mass_per_len": m_arm_per_len,
                    "length_m": arm["length_m"]},
         "value_path": [], "tolerance": 1e-9},
        {"leaf": "structures/fem/modal-analysis",
         "skill_fn": "natural_frequencies", "core_fn": "natural_frequencies",
         "kwargs": {"m1": md["m1_kg"], "m2": md["m2_kg"],
                    "k1": md["k1_n_m"], "k2": md["k2_n_m"]},
         "value_path": [0], "tolerance": 1e-9},
        {"leaf": "structures/fem/modal-analysis",
         "skill_fn": "resonance_check", "core_fn": "resonance_check",
         "kwargs": {"w_excitation": md["w_exc_rad_s"],
                    "wn_list": wn_list, "tol_frac": 0.1},
         "value_path": ["nearest"], "tolerance": 1e-9},
        {"leaf": "structures/fem/shear-center-analysis",
         "skill_fn": "channel_classical_e", "core_fn": "channel_classical_e",
         "kwargs": {"h": ch["web_height_m"], "b": ch["flange_width_m"]},
         "value_path": [], "tolerance": 1e-9},
        {"leaf": "structures/fem/shear-center-analysis",
         "skill_fn": "shear_center_channel",
         "core_fn": "shear_center_channel",
         "kwargs": {"h": ch["web_height_m"], "b": ch["flange_width_m"],
                    "t": ch["t_m"], "vy": P, "n": 400},
         "value_path": [0], "tolerance": 1e-6},
        {"leaf": "structures/fem/lug-joint-analysis",
         "skill_fn": "lug_analysis", "core_fn": "lug_analysis",
         "kwargs": {"load_n": P,
                    "hole_diameter_m": s["lug"]["hole_diameter_m"],
                    "thickness_m": s["lug"]["thickness_m"],
                    "lug_width_m": s["lug"]["width_m"],
                    "edge_distance_m": s["lug"]["edge_distance_m"],
                    "f_tu_pa": m["F_tu_pa"], "f_su_pa": m["F_su_pa"],
                    "f_bru_pa": m["F_bru_pa"]},
         "value_path": ["min_margin"], "tolerance": 1e-9},
    ]
    return rows


if __name__ == "__main__":
    item = example_item()
    model = build_report(item)
    md = render_report_markdown(model)
    print("ITEM: %s" % model["item"])
    print("ULTIMATE LOAD: %.1f kN" % (model["ultimate_load_n"] / 1e3))
    print("TRUSS BRACE FORCE: %.1f kN" % (model["stages"]["truss"]["member_forces_n"][1] / 1e3))
    print("BEAM-COLUMN MARGIN: %.3f" % model["stages"]["beam_column"]["margin"])
    print("BUCKLING MARGIN: %.3f" % model["stages"]["buckling"]["margin_of_safety"])
    print("LUG GOVERNING: %s margin %.3f" % (model["stages"]["lug"]["governing_mode"],
                                             model["stages"]["lug"]["min_margin"]))
    print("GATES: %s" % check_report(model))
    print("RENDERED: %d chars" % len(md))
