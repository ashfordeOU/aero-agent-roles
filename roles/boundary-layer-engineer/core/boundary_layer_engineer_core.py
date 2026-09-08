#!/usr/bin/env python3
"""boundary_layer_engineer_core.py - Boundary-Layer Engineer executable core.

This is the role's ENGINE: given a project's viscous-flow assessment
facts (a 2-D wing section, an axisymmetric fuselage forebody, a small
downstream strut, a leading-edge surface finish, a nose radius, a small
protruding sensor and a stated surface/freestream oscillation) it
computes:

1. laminar boundary-layer growth and the Michel-criterion natural-
   transition location (boundary-layer-theory, boundary-layer-transition)
2. section profile drag from the trailing-edge momentum state via the
   Squire-Young formula, with the Blasius flat-plate reduction check
   (squire-young-profile-drag), plus a Thwaites attached-flow check
   (boundary-layer-separation)
3. the Mangler axisymmetric transform for the fuselage forebody, cone
   values at equal running length vs the plain 2-D estimate
   (mangler-axisymmetric-transform)
4. the laminar far-wake velocity-defect profile and wake-survey drag
   downstream of a small strut (laminar-far-wake)
5. rough-wall skin friction and the trip criterion for a stated
   leading-edge surface finish (rough-wall-skin-friction)
6. the stagnation-point boundary layer at the fuselage nose
   (stagnation-flow-boundary-layer)
7. Stokes creeping-flow drag on a small protruding sensor
   (stokes-creeping-flow-drag)
8. the unsteady laminar Stokes layer for a stated surface oscillation
   (unsteady-laminar-stokes-layers)
9. an assembled section + component drag table and an honest verdict
   against a stated laminar-drag target

It BUILDS the Boundary-Layer and Viscous Drag Analysis Report and
gate-checks deliverables. Standalone: no external repo needed.

Every formula below is the REAL domain rule encoded in the bound Aero
Agent Skills leaves under aerodynamics/boundary-layer/ (boundary-layer-
theory, boundary-layer-transition, boundary-layer-separation, rough-
wall-skin-friction, stagnation-flow-boundary-layer, laminar-far-wake,
mangler-axisymmetric-transform, squire-young-profile-drag, stokes-
creeping-flow-drag, unsteady-laminar-stokes-layers). Those leaves
encode standard boundary-layer methodology (Blasius similarity
solution, Thwaites integral relation, the Michel and Stratford
criteria, the Squire-Young trailing-edge drag mapping, the Mangler
1948 axisymmetric transform, the Stokes 1851 creeping-flow solution
and the Stokes first/second unsteady problems), cited through NACA
TR-824, summary-only. No proprietary standard text is reproduced.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date


def _today() -> str:
    import os
    return os.environ.get("ROLE_GEN_DATE", date.today().isoformat())


def _check_positive(value, name) -> None:
    if value is None or value <= 0.0:
        raise ValueError("%s must be positive: %r" % (name, value))


# ---------------------------------------------------------------------------
# Physical constants (SI)
# ---------------------------------------------------------------------------
SQRT3 = math.sqrt(3.0)
INV_SQRT3 = 1.0 / SQRT3
LN2 = math.log(2.0)

# boundary-layer-theory leaf constants (Blasius similarity, flat plate)
BLASIUS_DELTA_C = 5.0
BLASIUS_DELTA_STAR_C = 1.7208
BLASIUS_THETA_C = 0.664
BLASIUS_CF_LOCAL_C = 0.664
BLASIUS_CF_AVG_C = 1.328
TURB_DELTA_C = 0.37
TURB_CF_LOCAL_C = 0.0592
TURB_CF_AVG_C = 0.074

# boundary-layer-transition leaf constants (Thwaites / Michel)
THWAITES_C = 0.45
MICHEL_A = 1.174
MICHEL_B = 22400.0
MICHEL_P = 0.46

# boundary-layer-separation leaf constant (laminar separation)
THWAITES_LAMBDA_SEP = -0.09

# squire-young-profile-drag leaf constants
SY_H_TE_DEFAULT = 1.4
SY_GROWTH_C = 0.664 ** 2  # 0.440896, pinned to the Blasius theta identity

# mangler-axisymmetric-transform leaf constant is SQRT3 / INV_SQRT3 above

# rough-wall-skin-friction leaf constants
ROUGH_SMOOTH_K_PLUS = 5.0
ROUGH_FULLY_K_PLUS = 70.0
ROUGH_MIN_X_OVER_KS = 100.0
ROUGH_TRIP_RE_K = 600.0

# stagnation-flow-boundary-layer leaf constants
STAG_DELTA_C = 2.4
STAG_FPP_2D = 1.2326       # Hiemenz
STAG_FPP_AXISYM = 1.3119   # Homann

# unsteady-laminar-stokes-layers leaf constant
RAYLEIGH_DELTA99_COEF = 3.6428


def reynolds_number(u_ms: float, x_m: float, nu_m2s: float) -> float:
    """Local Reynolds number Re_x = U*x/nu (boundary-layer-theory leaf)."""
    _check_positive(u_ms, "u_ms")
    _check_positive(x_m, "x_m")
    _check_positive(nu_m2s, "nu_m2s")
    return u_ms * x_m / nu_m2s


# ===========================================================================
# 1. boundary-layer-theory + boundary-layer-transition: laminar growth and
#    the Michel-criterion natural-transition location
# ===========================================================================

def blasius_theta(x_m: float, re_x: float) -> float:
    """Blasius momentum thickness theta = 0.664*x/sqrt(Re_x), m."""
    _check_positive(x_m, "x_m")
    _check_positive(re_x, "re_x")
    return BLASIUS_THETA_C * x_m / math.sqrt(re_x)


def blasius_delta(x_m: float, re_x: float) -> float:
    """Blasius 99-percent thickness delta = 5.0*x/sqrt(Re_x), m."""
    _check_positive(x_m, "x_m")
    _check_positive(re_x, "re_x")
    return BLASIUS_DELTA_C * x_m / math.sqrt(re_x)


def blasius_delta_star(x_m: float, re_x: float) -> float:
    """Blasius displacement thickness delta* = 1.7208*x/sqrt(Re_x), m."""
    _check_positive(x_m, "x_m")
    _check_positive(re_x, "re_x")
    return BLASIUS_DELTA_STAR_C * x_m / math.sqrt(re_x)


def blasius_cf_local(re_x: float) -> float:
    """Local laminar skin friction Cf = 0.664/sqrt(Re_x)."""
    _check_positive(re_x, "re_x")
    return BLASIUS_CF_LOCAL_C / math.sqrt(re_x)


def blasius_cf_average(re_x: float) -> float:
    """Average (one side) laminar skin friction Cf = 1.328/sqrt(Re_x)."""
    _check_positive(re_x, "re_x")
    return BLASIUS_CF_AVG_C / math.sqrt(re_x)


def turbulent_delta(x_m: float, re_x: float) -> float:
    """1/7-power turbulent thickness delta = 0.37*x/Re_x^(1/5), m."""
    _check_positive(x_m, "x_m")
    _check_positive(re_x, "re_x")
    return TURB_DELTA_C * x_m / re_x ** 0.2


def turbulent_theta(delta_m: float) -> float:
    """1/7-power turbulent momentum thickness theta = 7*delta/72, m."""
    _check_positive(delta_m, "delta_m")
    return 7.0 * delta_m / 72.0


def shape_factor(delta_star_m: float, theta_m: float) -> float:
    """Shape factor H = delta*/theta, dimensionless."""
    _check_positive(delta_star_m, "delta_star_m")
    _check_positive(theta_m, "theta_m")
    return delta_star_m / theta_m


def re_theta_flat_plate(re_x: float) -> float:
    """Flat-plate closed-form Re_theta = sqrt(THWAITES_C*Re_x)."""
    _check_positive(re_x, "re_x")
    return math.sqrt(THWAITES_C * re_x)


def michel_threshold(re_x: float) -> float:
    """Michel criterion threshold Re_theta,tr on the local Re_x."""
    _check_positive(re_x, "re_x")
    return MICHEL_A * (1.0 + MICHEL_B / re_x) * re_x ** MICHEL_P


def michel_criterion(re_x: float, re_theta: float) -> bool:
    """True when the Michel criterion is met (transition onset)."""
    _check_positive(re_x, "re_x")
    if re_theta < 0:
        raise ValueError("re_theta must be >= 0")
    return re_theta >= michel_threshold(re_x)


def flat_plate_transition(nu_m2s: float, ue_ms: float, x_max_m: float,
                          tol: float = 1e-6) -> dict:
    """Natural-transition station on a constant-Ue flat plate.

    Bisects the margin m(x) = Re_theta(x) - Re_theta,tr(x) between the
    flat-plate closed-form Re_theta = sqrt(0.45*Re_x) and the Michel
    threshold, mirroring the boundary-layer-transition leaf's own
    flat_plate_transition helper and worked example (x_tr ~ 0.81 m at
    Ue = 30 m/s, nu = 1.46e-5 m2/s over a 2 m run).
    """
    _check_positive(nu_m2s, "nu_m2s")
    _check_positive(ue_ms, "ue_ms")
    _check_positive(x_max_m, "x_max_m")

    def margin(x):
        re_x = reynolds_number(ue_ms, x, nu_m2s)
        return re_theta_flat_plate(re_x) - michel_threshold(re_x)

    lo, hi = 1e-6 * x_max_m, x_max_m
    if margin(hi) < 0:
        return {"x_tr_m": None, "re_x_tr": None, "re_theta_tr": None,
                "note": "transition not reached within the supplied run"}
    if margin(lo) >= 0:
        lo = 1e-9
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if margin(mid) < 0:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol * x_max_m:
            break
    x_tr = 0.5 * (lo + hi)
    re_x_tr = reynolds_number(ue_ms, x_tr, nu_m2s)
    return {"x_tr_m": x_tr, "re_x_tr": re_x_tr,
            "re_theta_tr": re_theta_flat_plate(re_x_tr),
            "note": "Michel criterion crossing, zero-pressure-gradient "
                    "closed form"}


# ===========================================================================
# 2. squire-young-profile-drag + boundary-layer-separation (attached check)
# ===========================================================================

def trailing_edge_factor(u_te_ms: float, u_inf_ms: float,
                         h_te: float = SY_H_TE_DEFAULT) -> float:
    """Edge-velocity factor (U_TE/U_inf)^((H_TE+5)/2), dimensionless."""
    _check_positive(u_te_ms, "u_te_ms")
    _check_positive(u_inf_ms, "u_inf_ms")
    if h_te <= 1.0:
        raise ValueError("h_te must be > 1.0 (attached boundary layer)")
    return (u_te_ms / u_inf_ms) ** ((h_te + 5.0) / 2.0)


def squire_young_profile_drag(theta_te_m: float, c_m: float,
                              u_te_ms: float, u_inf_ms: float,
                              h_te: float = SY_H_TE_DEFAULT) -> float:
    """Squire-Young section profile drag, one surface, dimensionless.

    c_d,p = 2*(theta_TE/c)*(U_TE/U_inf)^((H_TE+5)/2)
    """
    _check_positive(theta_te_m, "theta_te_m")
    _check_positive(c_m, "c_m")
    factor = trailing_edge_factor(u_te_ms, u_inf_ms, h_te)
    return 2.0 * (theta_te_m / c_m) * factor


def momentum_thickness_at_te(xs, ues, nu_m2s: float) -> float:
    """Laminar momentum thickness at the trailing edge (cumulative
    trapezoid Thwaites-style integral growth), theta_TE^2 = GROWTH_C *
    nu / U_TE^6 * integral_0^c Ue^5 dx (squire-young-profile-drag leaf).
    """
    if len(xs) < 2 or len(xs) != len(ues):
        raise ValueError("xs and ues must be equal-length, >= 2 stations")
    _check_positive(nu_m2s, "nu_m2s")
    for u in ues:
        _check_positive(u, "ue station")
    integral = ues[0] ** 5 * xs[0]
    for i in range(1, len(xs)):
        dx = xs[i] - xs[i - 1]
        if dx <= 0:
            raise ValueError("xs must be strictly increasing")
        integral += 0.5 * (ues[i] ** 5 + ues[i - 1] ** 5) * dx
    u_te = ues[-1]
    return math.sqrt(SY_GROWTH_C * nu_m2s / u_te ** 6 * integral)


def fully_laminar_profile_drag(xs, ues, nu_m2s: float, c_m: float,
                               u_inf_ms: float,
                               h_te: float = SY_H_TE_DEFAULT) -> dict:
    """One-call fully laminar chain: growth then Squire-Young mapping."""
    theta_te = momentum_thickness_at_te(xs, ues, nu_m2s)
    u_te = ues[-1]
    cdp = squire_young_profile_drag(theta_te, c_m, u_te, u_inf_ms, h_te)
    return {"theta_te_m": theta_te, "u_te_ms": u_te, "cdp": cdp,
            "factor": trailing_edge_factor(u_te, u_inf_ms, h_te)}


def thwaites_lambda_profile(xs, ues, nu_m2s: float):
    """Thwaites pressure-gradient parameter lambda at each station
    (boundary-layer-separation leaf): lambda = theta^2/nu * dU/dx.
    """
    if len(xs) < 2 or len(xs) != len(ues):
        raise ValueError("xs and ues must be equal-length, >= 2 stations")
    thetas = []
    integral = 0.0
    prev_x = xs[0]
    prev_u = ues[0]
    for i, (x, u) in enumerate(zip(xs, ues)):
        if i > 0:
            dx = x - prev_x
            if dx <= 0:
                raise ValueError("xs must be strictly increasing")
            integral += 0.5 * (u ** 5 + prev_u ** 5) * dx
        thetas.append(math.sqrt(THWAITES_C * nu_m2s / u ** 6 * integral)
                     if integral > 0 else 0.0)
        prev_x, prev_u = x, u
    lambdas = []
    n = len(xs)
    for i in range(n):
        if i == 0:
            dudx = (ues[1] - ues[0]) / (xs[1] - xs[0])
        elif i == n - 1:
            dudx = (ues[-1] - ues[-2]) / (xs[-1] - xs[-2])
        else:
            dudx = (ues[i + 1] - ues[i - 1]) / (xs[i + 1] - xs[i - 1])
        lambdas.append(thetas[i] ** 2 / nu_m2s * dudx)
    return lambdas


def laminar_separation_station(xs, ues, nu_m2s: float):
    """First station where Thwaites lambda <= -0.09, or None (attached)."""
    lambdas = thwaites_lambda_profile(xs, ues, nu_m2s)
    for i, lam in enumerate(lambdas):
        if lam <= THWAITES_LAMBDA_SEP:
            return {"index": i, "x_m": xs[i], "lambda": lam}
    return None


# ===========================================================================
# 3. mangler-axisymmetric-transform: fuselage forebody cone
# ===========================================================================

def cone_radius(x_m: float, half_angle_deg: float) -> float:
    """Sharp-cone surface radius r0(x) = x*tan(alpha), m."""
    _check_positive(x_m, "x_m")
    if not 0.0 < half_angle_deg < 90.0:
        raise ValueError("half_angle_deg must be in (0, 90)")
    return x_m * math.tan(math.radians(half_angle_deg))


def mangler_xi(x_m: float, half_angle_deg: float,
              ref_length_m: float) -> float:
    """Mangler transformed running length xi = r0(x)^2*x/(3*L^2), m."""
    _check_positive(ref_length_m, "ref_length_m")
    r0 = cone_radius(x_m, half_angle_deg)
    return r0 ** 2 * x_m / (3.0 * ref_length_m ** 2)


def cone_skin_friction(cf_flat: float) -> float:
    """Cone skin friction at equal running length, SQRT3*cf_flat."""
    _check_positive(cf_flat, "cf_flat")
    return SQRT3 * cf_flat


def cone_wall_shear(tau_w_flat: float) -> float:
    """Cone wall shear at equal running length, SQRT3*tau_w_flat, Pa."""
    _check_positive(tau_w_flat, "tau_w_flat")
    return SQRT3 * tau_w_flat


def cone_boundary_layer_thickness(delta_flat: float) -> float:
    """Cone 99-percent thickness at equal running length, delta_flat/sqrt3."""
    _check_positive(delta_flat, "delta_flat")
    return INV_SQRT3 * delta_flat


def cone_displacement_thickness(delta_star_flat: float) -> float:
    """Cone displacement thickness at equal running length."""
    _check_positive(delta_star_flat, "delta_star_flat")
    return INV_SQRT3 * delta_star_flat


def cone_momentum_thickness(theta_flat: float) -> float:
    """Cone momentum thickness at equal running length."""
    _check_positive(theta_flat, "theta_flat")
    return INV_SQRT3 * theta_flat


def cone_lateral_area(x_m: float, half_angle_deg: float) -> float:
    """Cone lateral (wetted) surface area from the apex to x, m^2.

    A = pi*r0(x)*slant_length with slant_length = x/cos(alpha) (exact
    cone geometry, not the small-angle approximation).
    """
    r0 = cone_radius(x_m, half_angle_deg)
    slant = x_m / math.cos(math.radians(half_angle_deg))
    return math.pi * r0 * slant


# ===========================================================================
# 4. laminar-far-wake: downstream of a small strut
# ===========================================================================

def momentum_thickness_blasius(u_ms: float, c_m: float,
                               nu_m2s: float) -> float:
    """Trailing-edge Blasius momentum thickness theta_c, one side, m."""
    _check_positive(u_ms, "u_ms")
    _check_positive(c_m, "c_m")
    _check_positive(nu_m2s, "nu_m2s")
    return BLASIUS_THETA_C * math.sqrt(nu_m2s * c_m / u_ms)


def plate_drag_per_span(u_ms: float, rho_kgm3: float, nu_m2s: float,
                        c_m: float, sides: int = 2) -> float:
    """Plate drag per unit span, D = sides*rho*U^2*theta_c, N/m."""
    if sides < 1:
        raise ValueError("sides must be >= 1")
    theta_c = momentum_thickness_blasius(u_ms, c_m, nu_m2s)
    return sides * rho_kgm3 * u_ms ** 2 * theta_c


def plate_drag_coefficient(u_ms: float, rho_kgm3: float, nu_m2s: float,
                           c_m: float, sides: int = 2) -> float:
    """Plate drag coefficient C_D = D/(0.5*rho*U^2*c)."""
    d = plate_drag_per_span(u_ms, rho_kgm3, nu_m2s, c_m, sides)
    return d / (0.5 * rho_kgm3 * u_ms ** 2 * c_m)


def wake_spread_parameter(u_ms: float, nu_m2s: float, x_m: float) -> float:
    """Gaussian wake spread parameter B = U/(4*nu*x), 1/m^2."""
    _check_positive(u_ms, "u_ms")
    _check_positive(nu_m2s, "nu_m2s")
    _check_positive(x_m, "x_m")
    return u_ms / (4.0 * nu_m2s * x_m)


def centerline_defect_from_drag(d_nm: float, rho_kgm3: float, u_ms: float,
                                b_1m2: float) -> float:
    """Centerline wake defect u_c = (D/(rho*U))*sqrt(B/pi), m/s."""
    _check_positive(d_nm, "d_nm")
    _check_positive(b_1m2, "b_1m2")
    return (d_nm / (rho_kgm3 * u_ms)) * math.sqrt(b_1m2 / math.pi)


def velocity_defect_gaussian(u_c_ms: float, b_1m2: float, y_m: float) -> float:
    """Gaussian defect profile u1(y) = u_c*exp(-B*y^2), m/s."""
    if u_c_ms < 0:
        raise ValueError("u_c_ms must be >= 0")
    return u_c_ms * math.exp(-b_1m2 * y_m ** 2)


def half_defect_width(b_1m2: float) -> float:
    """Half-defect width y_half = sqrt(ln(2)/B), m."""
    _check_positive(b_1m2, "b_1m2")
    return math.sqrt(LN2 / b_1m2)


def one_over_e_width(b_1m2: float) -> float:
    """1/e width y_e = sqrt(1/B), m."""
    _check_positive(b_1m2, "b_1m2")
    return math.sqrt(1.0 / b_1m2)


def defect_integral(u_c_ms: float, b_1m2: float) -> float:
    """Momentum integral of the Gaussian, u_c*sqrt(pi/B), m^2/s."""
    _check_positive(b_1m2, "b_1m2")
    return u_c_ms * math.sqrt(math.pi / b_1m2)


def drag_from_wake(u_c_ms: float, b_1m2: float, rho_kgm3: float,
                   u_ms: float) -> float:
    """Wake-survey drag D = rho*U*integral(u1)dy, N/m."""
    return rho_kgm3 * u_ms * defect_integral(u_c_ms, b_1m2)


def full_momentum_deficit(rho_kgm3: float, u_ms: float, u_c_ms: float,
                          b_1m2: float) -> float:
    """Nonlinear momentum deficit (honesty check), N/m."""
    _check_positive(b_1m2, "b_1m2")
    linear = u_ms * defect_integral(u_c_ms, b_1m2)
    quad = u_c_ms ** 2 * math.sqrt(math.pi / (2.0 * b_1m2))
    return rho_kgm3 * (linear - quad)


# ===========================================================================
# 5. rough-wall-skin-friction: leading-edge surface finish
# ===========================================================================

def smooth_turbulent_cf(re_x: float) -> float:
    """Smooth-wall turbulent baseline Cf = 0.0592/Re_x^0.2."""
    _check_positive(re_x, "re_x")
    return TURB_CF_LOCAL_C / re_x ** 0.2


def friction_velocity(u_inf_ms: float, cf: float) -> float:
    """Friction velocity u_tau = U_inf*sqrt(Cf/2), m/s."""
    _check_positive(u_inf_ms, "u_inf_ms")
    _check_positive(cf, "cf")
    return u_inf_ms * math.sqrt(cf / 2.0)


def sand_roughness_reynolds(rho_kgm3: float, u_tau_ms: float, k_s_m: float,
                            mu_pas: float) -> float:
    """Roughness Reynolds number k+ = rho*u_tau*k_s/mu."""
    _check_positive(rho_kgm3, "rho_kgm3")
    _check_positive(u_tau_ms, "u_tau_ms")
    _check_positive(k_s_m, "k_s_m")
    _check_positive(mu_pas, "mu_pas")
    return rho_kgm3 * u_tau_ms * k_s_m / mu_pas


def classify_regime(k_plus: float) -> str:
    """Classify the k+ regime: smooth, transitional, fully-rough."""
    if k_plus < 0:
        raise ValueError("k_plus must be >= 0")
    if k_plus < ROUGH_SMOOTH_K_PLUS:
        return "smooth"
    if k_plus <= ROUGH_FULLY_K_PLUS:
        return "transitional"
    return "fully-rough"


def rough_wall_cf(x_m: float, k_s_m: float) -> float:
    """Fully-rough Schlichting correlation, valid for x/k_s >= 100."""
    _check_positive(x_m, "x_m")
    _check_positive(k_s_m, "k_s_m")
    if x_m / k_s_m < ROUGH_MIN_X_OVER_KS:
        raise ValueError("x/k_s below the 100.0 validity floor")
    return (2.87 + 1.58 * math.log10(x_m / k_s_m)) ** (-2.5)


def cf_with_roughness(re_x: float, x_m: float, k_s_m: float,
                      rho_kgm3: float, u_inf_ms: float,
                      mu_pas: float) -> dict:
    """Select the operative Cf without iteration (smooth / blend / rough)."""
    cf_smooth = smooth_turbulent_cf(re_x)
    u_tau = friction_velocity(u_inf_ms, cf_smooth)
    k_plus = sand_roughness_reynolds(rho_kgm3, u_tau, k_s_m, mu_pas)
    regime = classify_regime(k_plus)
    if regime == "smooth":
        cf_used = cf_smooth
        cf_rough_or_iterated = cf_smooth
        note = "hydraulically smooth: roughness inactive"
    else:
        cf_rough = rough_wall_cf(x_m, k_s_m)
        cf_rough_or_iterated = cf_rough
        if regime == "fully-rough":
            cf_used = cf_rough
            note = "fully rough: Schlichting correlation used directly"
        else:
            frac = ((math.log(k_plus) - math.log(ROUGH_SMOOTH_K_PLUS))
                    / (math.log(ROUGH_FULLY_K_PLUS)
                       - math.log(ROUGH_SMOOTH_K_PLUS)))
            cf_used = math.exp(math.log(cf_smooth)
                               + frac * (math.log(cf_rough)
                                         - math.log(cf_smooth)))
            note = "transitional: log-linear blend between smooth and rough"
    return {"regime": regime, "k_s_plus": k_plus, "cf_smooth": cf_smooth,
            "cf_rough_or_iterated": cf_rough_or_iterated, "cf_used": cf_used,
            "note": note}


def trip_criterion(u_ms: float, k_m: float, nu_m2s: float,
                   re_k_crit: float = ROUGH_TRIP_RE_K) -> dict:
    """Trip test: re_k = U*k/nu against the critical roughness Reynolds."""
    _check_positive(u_ms, "u_ms")
    _check_positive(k_m, "k_m")
    _check_positive(nu_m2s, "nu_m2s")
    _check_positive(re_k_crit, "re_k_crit")
    re_k = u_ms * k_m / nu_m2s
    return {"re_k": re_k, "trip_expected": re_k >= re_k_crit}


# ===========================================================================
# 6. stagnation-flow-boundary-layer: fuselage nose
# ===========================================================================

def stagnation_velocity_gradient(flow_type: str, u_inf_ms: float,
                                 radius_m: float) -> float:
    """Potential-flow stagnation velocity gradient a = du_e/ds, 1/s."""
    _check_positive(u_inf_ms, "u_inf_ms")
    _check_positive(radius_m, "radius_m")
    ft = flow_type.lower()
    if ft in ("cylinder", "2d", "two-dimensional"):
        return 2.0 * u_inf_ms / radius_m
    if ft in ("sphere", "axisymmetric", "axi"):
        return 1.5 * u_inf_ms / radius_m
    raise ValueError("unknown flow_type: %r" % flow_type)


def stagnation_boundary_layer_thickness(nu_m2s: float, a_1s: float) -> float:
    """99-percent stagnation-layer thickness delta = 2.4*sqrt(nu/a), m."""
    _check_positive(nu_m2s, "nu_m2s")
    _check_positive(a_1s, "a_1s")
    return STAG_DELTA_C * math.sqrt(nu_m2s / a_1s)


def stagnation_wall_shear(rho_kgm3: float, nu_m2s: float, a_1s: float,
                          u_inf_ms: float, flow_type: str) -> float:
    """Stagnation wall shear tau_w = mu*U_inf*sqrt(a/nu)*fpp, Pa."""
    _check_positive(rho_kgm3, "rho_kgm3")
    _check_positive(nu_m2s, "nu_m2s")
    _check_positive(a_1s, "a_1s")
    _check_positive(u_inf_ms, "u_inf_ms")
    mu = rho_kgm3 * nu_m2s
    ft = flow_type.lower()
    if ft in ("cylinder", "2d", "two-dimensional"):
        fpp = STAG_FPP_2D
    elif ft in ("sphere", "axisymmetric", "axi"):
        fpp = STAG_FPP_AXISYM
    else:
        raise ValueError("unknown flow_type: %r" % flow_type)
    return mu * u_inf_ms * math.sqrt(a_1s / nu_m2s) * fpp


def stagnation_skin_friction_coefficient(rho_kgm3: float, u_inf_ms: float,
                                         tau_w_pa: float) -> float:
    """Cf = tau_w / (0.5*rho*U_inf^2)."""
    _check_positive(rho_kgm3, "rho_kgm3")
    _check_positive(u_inf_ms, "u_inf_ms")
    _check_positive(tau_w_pa, "tau_w_pa")
    return tau_w_pa / (0.5 * rho_kgm3 * u_inf_ms ** 2)


# ===========================================================================
# 7. stokes-creeping-flow-drag: small protruding sensor
# ===========================================================================

def radius_reynolds(u_ms: float, a_m: float, nu_m2s: float) -> float:
    """Radius-based creeping-flow Reynolds number Re_a = U*a/nu."""
    _check_positive(u_ms, "u_ms")
    _check_positive(a_m, "a_m")
    _check_positive(nu_m2s, "nu_m2s")
    return u_ms * a_m / nu_m2s


def diameter_reynolds(u_ms: float, a_m: float, nu_m2s: float) -> float:
    """Diameter-based creeping-flow Reynolds number Re_D = U*2a/nu."""
    return 2.0 * radius_reynolds(u_ms, a_m, nu_m2s)


def stokes_drag(mu_pas: float, a_m: float, u_ms: float) -> float:
    """Total Stokes drag F = 6*pi*mu*a*U, N."""
    _check_positive(mu_pas, "mu_pas")
    _check_positive(a_m, "a_m")
    _check_positive(u_ms, "u_ms")
    return 6.0 * math.pi * mu_pas * a_m * u_ms


def stokes_pressure_drag(mu_pas: float, a_m: float, u_ms: float) -> float:
    """Pressure (form) drag, one third of the total, N."""
    return 2.0 * math.pi * mu_pas * a_m * u_ms


def stokes_friction_drag(mu_pas: float, a_m: float, u_ms: float) -> float:
    """Friction drag, two thirds of the total, N."""
    return 4.0 * math.pi * mu_pas * a_m * u_ms


def stokes_drag_coefficient(rho_kgm3: float, mu_pas: float, u_ms: float,
                            a_m: float) -> float:
    """Drag coefficient Cd = 24/Re_D = 12*mu/(rho*U*a)."""
    _check_positive(rho_kgm3, "rho_kgm3")
    _check_positive(u_ms, "u_ms")
    _check_positive(a_m, "a_m")
    return 12.0 * mu_pas / (rho_kgm3 * u_ms * a_m)


def stokes_surface_pressure_delta(theta_rad: float, mu_pas: float,
                                  u_ms: float, a_m: float) -> float:
    """Surface pressure p - p_inf = -1.5*(mu*U/a)*cos(theta), Pa."""
    _check_positive(mu_pas, "mu_pas")
    _check_positive(u_ms, "u_ms")
    _check_positive(a_m, "a_m")
    return -1.5 * (mu_pas * u_ms / a_m) * math.cos(theta_rad)


def stokes_wall_shear_stress(theta_rad: float, mu_pas: float, u_ms: float,
                             a_m: float) -> float:
    """Wall shear tau_w = 1.5*(mu*U/a)*sin(theta), Pa."""
    _check_positive(mu_pas, "mu_pas")
    _check_positive(u_ms, "u_ms")
    _check_positive(a_m, "a_m")
    return 1.5 * (mu_pas * u_ms / a_m) * math.sin(theta_rad)


def oseen_correction(re_a: float) -> float:
    """Oseen first-order drag correction factor 1 + (3/8)*Re_a."""
    if re_a < 0:
        raise ValueError("re_a must be >= 0")
    return 1.0 + 0.375 * re_a


def oseen_drag(mu_pas: float, a_m: float, u_ms: float, nu_m2s: float) -> float:
    """Oseen-corrected Stokes drag, N."""
    re_a = radius_reynolds(u_ms, a_m, nu_m2s)
    return stokes_drag(mu_pas, a_m, u_ms) * oseen_correction(re_a)


# ===========================================================================
# 8. unsteady-laminar-stokes-layers: surface/freestream oscillation
# ===========================================================================

def stokes_penetration_depth(nu_m2s: float, omega_rads: float) -> float:
    """Stokes second-problem penetration depth sqrt(2*nu/omega), m."""
    _check_positive(nu_m2s, "nu_m2s")
    _check_positive(omega_rads, "omega_rads")
    return math.sqrt(2.0 * nu_m2s / omega_rads)


def stokes_second_amplitude_at_depth(u_ms: float, y_m: float,
                                     delta_m: float) -> float:
    """Local oscillation amplitude U*exp(-y/delta), m/s."""
    if y_m < 0:
        raise ValueError("y_m must be >= 0")
    _check_positive(delta_m, "delta_m")
    return u_ms * math.exp(-y_m / delta_m)


def stokes_second_phase_lag(y_m: float, delta_m: float) -> float:
    """Phase lag at depth y, y/delta radians."""
    if y_m < 0:
        raise ValueError("y_m must be >= 0")
    _check_positive(delta_m, "delta_m")
    return y_m / delta_m


def stokes_second_shear_amplitude(rho_kgm3: float, u_ms: float,
                                  nu_m2s: float, omega_rads: float) -> float:
    """Wall shear amplitude tau_amp = rho*U*sqrt(nu*omega), Pa."""
    _check_positive(rho_kgm3, "rho_kgm3")
    _check_positive(u_ms, "u_ms")
    _check_positive(nu_m2s, "nu_m2s")
    _check_positive(omega_rads, "omega_rads")
    return rho_kgm3 * u_ms * math.sqrt(nu_m2s * omega_rads)


def stokes_second_wall_shear(rho_kgm3: float, u_ms: float, nu_m2s: float,
                             omega_rads: float, t_s: float) -> float:
    """Wall shear time history, leads plate velocity by 45 deg, Pa."""
    tau_amp = stokes_second_shear_amplitude(rho_kgm3, u_ms, nu_m2s,
                                            omega_rads)
    return tau_amp * math.cos(omega_rads * t_s + math.pi / 4.0)


def reduced_frequency(omega_rads: float, c_m: float, u_inf_ms: float) -> float:
    """Reduced frequency k = omega*c/(2*U_inf), standard definition."""
    _check_positive(omega_rads, "omega_rads")
    _check_positive(c_m, "c_m")
    _check_positive(u_inf_ms, "u_inf_ms")
    return omega_rads * c_m / (2.0 * u_inf_ms)


# ===========================================================================
# Report data model
# ===========================================================================

@dataclass
class BLItem:
    """Project facts the role needs to build the analysis report.

    Reference-typical values are labeled as such in the report; every
    number in the deliverable is computed from these stated inputs.
    """
    program_name: str = "Halcyon-18 natural-laminar-flow sailplane"
    item_name: str = ("Halcyon-18 wing root section and fuselage forebody "
                      "boundary-layer assessment")
    description: str = ("Boundary-layer and viscous-drag assessment of a "
                        "natural-laminar-flow sailplane wing root section "
                        "and an axisymmetric fuselage forebody at cruise, "
                        "plus a small protruding sensor and a stated "
                        "surface oscillation.")
    # air properties (standard sea-level, reference-typical)
    rho_kgm3: float = 1.225
    nu_m2s: float = 1.46e-5
    mu_pas: float = 1.225 * 1.46e-5

    # 1/2: wing section
    chord_m: float = 0.65
    u_inf_ms: float = 79.0
    n_stations: int = 400
    ramp_a: float = 0.10           # Ue = U_inf*(1 - ramp_a*x/c)
    h_te: float = SY_H_TE_DEFAULT
    laminar_drag_target_cdp: float = 0.0011

    # 3: fuselage forebody cone
    cone_half_angle_deg: float = 8.0
    cone_running_length_m: float = 1.2
    cone_ref_length_m: float = 1.0

    # 4: wake strut
    strut_chord_m: float = 0.05
    wake_station_factor: float = 100.0

    # 5: leading-edge surface finish
    roughness_ks_m: float = 5.0e-5   # 0.05 mm (light paint/insect debris)
    roughness_station_m: float = 0.05
    roughness_element_k_m: float = 3.0e-5

    # 6: fuselage nose
    nose_radius_m: float = 0.20

    # 7: small protruding sensor (static-pressure tap / bead)
    sensor_radius_m: float = 1.0e-4
    sensor_local_speed_ms: float = 0.01

    # 8: surface oscillation
    osc_freq_hz: float = 20.0
    osc_amplitude_ms: float = 2.0

    certification_basis: str = "NACA TR-824 boundary-layer methodology " \
                               "(reference-only)"


# ===========================================================================
# Section builders
# ===========================================================================

def _wing_edge_velocity_profile(item: BLItem):
    xs = [i * item.chord_m / (item.n_stations - 1)
         for i in range(item.n_stations)]
    xs[0] = max(xs[0], 1e-9)
    ues = [item.u_inf_ms * (1.0 - item.ramp_a * x / item.chord_m) for x in xs]
    return xs, ues


def build_transition_section(item: BLItem) -> dict:
    re_c = reynolds_number(item.u_inf_ms, item.chord_m, item.nu_m2s)
    trans = flat_plate_transition(item.nu_m2s, item.u_inf_ms, item.chord_m)
    delta_c = blasius_delta(item.chord_m, re_c)
    delta_star_c = blasius_delta_star(item.chord_m, re_c)
    theta_c = blasius_theta(item.chord_m, re_c)
    cf_local_c = blasius_cf_local(re_c)
    cf_avg_c = blasius_cf_average(re_c)
    return {
        "re_c": re_c, "delta_c_m": delta_c, "delta_star_c_m": delta_star_c,
        "theta_c_m": theta_c, "cf_local_c": cf_local_c, "cf_avg_c": cf_avg_c,
        "shape_factor": shape_factor(delta_star_c, theta_c),
        "criterion": "Michel empirical criterion on the Thwaites-grown "
                    "momentum-thickness Reynolds number, zero-pressure-"
                    "gradient closed form (boundary-layer-transition leaf)",
        "x_tr_m": trans["x_tr_m"], "re_x_tr": trans["re_x_tr"],
        "re_theta_tr": trans["re_theta_tr"],
        "x_tr_over_c": (trans["x_tr_m"] / item.chord_m
                        if trans["x_tr_m"] else None),
    }


def build_profile_drag_section(item: BLItem) -> dict:
    xs, ues = _wing_edge_velocity_profile(item)
    chain = fully_laminar_profile_drag(xs, ues, item.nu_m2s, item.chord_m,
                                       item.u_inf_ms, item.h_te)
    re_c = reynolds_number(item.u_inf_ms, item.chord_m, item.nu_m2s)
    blasius_check_cdp = BLASIUS_CF_AVG_C / math.sqrt(re_c)
    theta_blasius = BLASIUS_THETA_C * item.chord_m / math.sqrt(re_c)
    zero_pg_identity = squire_young_profile_drag(theta_blasius, item.chord_m,
                                                 item.u_inf_ms,
                                                 item.u_inf_ms, item.h_te)
    sep = laminar_separation_station(xs, ues, item.nu_m2s)
    return {
        "u_te_over_u_inf": ues[-1] / item.u_inf_ms,
        "theta_te_m": chain["theta_te_m"], "u_te_ms": chain["u_te_ms"],
        "edge_velocity_factor": chain["factor"],
        "cdp_one_surface": chain["cdp"],
        "cdp_both_surfaces": 2.0 * chain["cdp"],
        "blasius_check_cdp": blasius_check_cdp,
        "zero_pg_identity_cdp": zero_pg_identity,
        "identity_residual": abs(zero_pg_identity - blasius_check_cdp),
        "attached_check": ("attached (Thwaites lambda never crosses -0.09 "
                          "over the run)" if sep is None
                          else "separation flagged at x/c=%.3f"
                              % (sep["x_m"] / item.chord_m)),
    }


def build_mangler_section(item: BLItem) -> dict:
    x = item.cone_running_length_m
    ue = item.u_inf_ms
    re_x = reynolds_number(ue, x, item.nu_m2s)
    cf_flat = blasius_cf_local(re_x)
    tau_w_flat = 0.5 * item.rho_kgm3 * ue ** 2 * cf_flat
    delta_flat = blasius_delta(x, re_x)
    delta_star_flat = blasius_delta_star(x, re_x)
    theta_flat = blasius_theta(x, re_x)

    r0 = cone_radius(x, item.cone_half_angle_deg)
    xi = mangler_xi(x, item.cone_half_angle_deg, item.cone_ref_length_m)
    cf_cone = cone_skin_friction(cf_flat)
    tau_w_cone = cone_wall_shear(tau_w_flat)
    delta_cone = cone_boundary_layer_thickness(delta_flat)
    delta_star_cone = cone_displacement_thickness(delta_star_flat)
    theta_cone = cone_momentum_thickness(theta_flat)
    h_cone = shape_factor(delta_star_cone, theta_cone)

    # laminar sqrt(x)-scaling identity: average Cf = 2x local Cf, on both
    # the flat plate and the (same x-dependence) Mangler-transformed cone.
    cf_cone_avg = 2.0 * cf_cone
    area = cone_lateral_area(x, item.cone_half_angle_deg)
    drag_n = cf_cone_avg * 0.5 * item.rho_kgm3 * ue ** 2 * area

    return {
        "re_x": re_x, "cone_radius_m": r0, "mangler_xi_m": xi,
        "cf_flat": cf_flat, "tau_w_flat_pa": tau_w_flat,
        "delta_flat_m": delta_flat, "delta_star_flat_m": delta_star_flat,
        "theta_flat_m": theta_flat,
        "cf_cone": cf_cone, "tau_w_cone_pa": tau_w_cone,
        "delta_cone_m": delta_cone, "delta_star_cone_m": delta_star_cone,
        "theta_cone_m": theta_cone, "h_cone": h_cone,
        "theta_ratio_cone_over_2d": theta_cone / theta_flat,
        "wetted_area_m2": area, "cf_cone_avg": cf_cone_avg,
        "drag_n": drag_n,
    }


def build_wake_section(item: BLItem) -> dict:
    c = item.strut_chord_m
    u = item.u_inf_ms
    nu = item.nu_m2s
    rho = item.rho_kgm3
    re_c = reynolds_number(u, c, nu)
    theta_c = momentum_thickness_blasius(u, c, nu)
    d = plate_drag_per_span(u, rho, nu, c)
    cd = plate_drag_coefficient(u, rho, nu, c)
    x = item.wake_station_factor * c
    b = wake_spread_parameter(u, nu, x)
    u_c = centerline_defect_from_drag(d, rho, u, b)
    y_half = half_defect_width(b)
    y_e = one_over_e_width(b)
    integral = defect_integral(u_c, b)
    d_wake = drag_from_wake(u_c, b, rho, u)
    full = full_momentum_deficit(rho, u, u_c, b)
    return {
        "re_c": re_c, "theta_c_m": theta_c, "plate_drag_nm": d,
        "plate_cd": cd, "station_x_m": x, "spread_b_1m2": b,
        "centerline_defect_ms": u_c, "half_width_m": y_half,
        "one_over_e_width_m": y_e, "momentum_integral_m2s": integral,
        "wake_survey_drag_nm": d_wake,
        "full_deficit_nm": full,
        "linearization_residual_pct": 100.0 * (d_wake - full) / d_wake,
    }


def build_roughness_section(item: BLItem) -> dict:
    x = item.roughness_station_m
    re_x = reynolds_number(item.u_inf_ms, x, item.nu_m2s)
    result = cf_with_roughness(re_x, x, item.roughness_ks_m, item.rho_kgm3,
                               item.u_inf_ms, item.mu_pas)
    trip = trip_criterion(item.u_inf_ms, item.roughness_element_k_m,
                          item.nu_m2s)
    return {"re_x": re_x, **result, "trip": trip}


def build_stagnation_section(item: BLItem) -> dict:
    a = stagnation_velocity_gradient("sphere", item.u_inf_ms,
                                     item.nose_radius_m)
    delta = stagnation_boundary_layer_thickness(item.nu_m2s, a)
    tau_w = stagnation_wall_shear(item.rho_kgm3, item.nu_m2s, a,
                                  item.u_inf_ms, "sphere")
    cf = stagnation_skin_friction_coefficient(item.rho_kgm3, item.u_inf_ms,
                                              tau_w)
    return {"flow_type": "axisymmetric (Homann)", "a_1s": a,
            "delta_m": delta, "tau_w_pa": tau_w, "cf": cf}


def build_stokes_section(item: BLItem) -> dict:
    a = item.sensor_radius_m
    u = item.sensor_local_speed_ms
    mu = item.mu_pas
    re_a = radius_reynolds(u, a, item.nu_m2s)
    re_d = diameter_reynolds(u, a, item.nu_m2s)
    f = stokes_drag(mu, a, u)
    fp = stokes_pressure_drag(mu, a, u)
    ff = stokes_friction_drag(mu, a, u)
    cd = stokes_drag_coefficient(item.rho_kgm3, mu, u, a)
    p_stag = stokes_surface_pressure_delta(math.pi, mu, u, a)
    tau_eq = stokes_wall_shear_stress(math.pi / 2.0, mu, u, a)
    f_oseen = oseen_drag(mu, a, u, item.nu_m2s)
    return {"radius_m": a, "local_speed_ms": u, "re_a": re_a, "re_d": re_d,
            "drag_n": f, "pressure_drag_n": fp, "friction_drag_n": ff,
            "drag_coefficient": cd,
            "stagnation_pressure_delta_pa": p_stag,
            "equator_wall_shear_pa": tau_eq,
            "oseen_drag_n": f_oseen,
            "oseen_increase_pct": 100.0 * (f_oseen - f) / f}


def build_unsteady_section(item: BLItem) -> dict:
    omega = 2.0 * math.pi * item.osc_freq_hz
    delta = stokes_penetration_depth(item.nu_m2s, omega)
    stations = [0.0, 0.5, 1.0, 2.0, 3.0]
    profile = []
    for ratio in stations:
        y = ratio * delta
        amp = stokes_second_amplitude_at_depth(item.osc_amplitude_ms, y,
                                               delta)
        lag_rad = stokes_second_phase_lag(y, delta)
        profile.append({"y_over_delta": ratio, "y_m": y,
                        "amplitude_ms": amp,
                        "lag_deg": math.degrees(lag_rad)})
    tau_amp = stokes_second_shear_amplitude(item.rho_kgm3,
                                            item.osc_amplitude_ms,
                                            item.nu_m2s, omega)
    k_red = reduced_frequency(omega, item.chord_m, item.u_inf_ms)
    # boundary-layer thickness for scale comparison (at the wing TE)
    re_c = reynolds_number(item.u_inf_ms, item.chord_m, item.nu_m2s)
    delta_bl = blasius_delta(item.chord_m, re_c)
    return {"omega_rads": omega, "penetration_depth_m": delta,
            "profile": profile, "wall_shear_amplitude_pa": tau_amp,
            "reduced_frequency": k_red,
            "delta_bl_at_te_m": delta_bl,
            "depth_ratio_to_bl": delta / delta_bl,
            "relevance_note": (
                "penetration depth is %.1f%% of the trailing-edge "
                "boundary-layer thickness at %.3g reduced frequency: "
                % (100.0 * delta / delta_bl, k_red)
                + ("the Stokes layer stays well inside the mean boundary "
                   "layer; quasi-steady treatment of the mean flow is "
                   "adequate" if delta < delta_bl else
                   "the Stokes layer is comparable to or exceeds the mean "
                   "boundary-layer thickness; unsteady effects should be "
                   "carried into the mean-flow analysis"))}


def build_report(item: BLItem) -> dict:
    """Build the complete Boundary-Layer and Viscous Drag Analysis Report."""
    transition = build_transition_section(item)
    profile_drag = build_profile_drag_section(item)
    mangler = build_mangler_section(item)
    wake = build_wake_section(item)
    roughness = build_roughness_section(item)
    stagnation = build_stagnation_section(item)
    stokes = build_stokes_section(item)
    unsteady = build_unsteady_section(item)

    q_inf = 0.5 * item.rho_kgm3 * item.u_inf_ms ** 2
    wing_drag_per_span = profile_drag["cdp_both_surfaces"] * q_inf * \
        item.chord_m

    drag_table = [
        {"component": "Wing section profile drag (both surfaces)",
         "basis": "per unit span", "value": wing_drag_per_span,
         "units": "N/m"},
        {"component": "Strut far-wake survey drag",
         "basis": "per unit span", "value": wake["wake_survey_drag_nm"],
         "units": "N/m"},
        {"component": "Fuselage forebody friction drag (to x=%.2f m)"
                     % item.cone_running_length_m,
         "basis": "discrete body", "value": mangler["drag_n"],
         "units": "N"},
        {"component": "Sensor-pod Stokes drag (Oseen-corrected)",
         "basis": "discrete body", "value": stokes["oseen_drag_n"],
         "units": "N"},
    ]

    verdict_gap = (profile_drag["cdp_both_surfaces"]
                  - item.laminar_drag_target_cdp)
    if transition["x_tr_over_c"] is not None:
        transition_note = (
            "Michel-criterion natural transition at x/c=%.3f falls short "
            "of the fully laminar target used above (full-chord laminar "
            "run to the trailing edge); realizing the target profile-drag "
            "estimate requires the shaped favorable-gradient pressure "
            "distribution of the NLF airfoil (or boundary-layer suction/"
            "hybrid laminar-flow control) beyond the mild ramp modeled "
            "here, and should be re-verified with a coupled panel/eN "
            "method (e.g. XFOIL) before release."
            % transition["x_tr_over_c"])
    else:
        transition_note = "Transition not reached within the modeled run."

    verdict = {
        "target_cdp": item.laminar_drag_target_cdp,
        "computed_cdp_both_surfaces": profile_drag["cdp_both_surfaces"],
        "gap_cdp": verdict_gap,
        "meets_target": verdict_gap <= 0.0,
        "transition_caveat": transition_note,
    }

    return {
        "schema_version": 1,
        "role": "boundary-layer-engineer",
        "deliverable_type": "boundary-layer and viscous drag analysis report",
        "document_type": "Boundary-Layer and Viscous Drag Analysis Report",
        "item": item.item_name,
        "program": item.program_name,
        "description": item.description,
        "certification_basis": item.certification_basis,
        "generated": _today(),
        "status": "draft-for-review",
        "inputs": {"rho_kgm3": item.rho_kgm3, "nu_m2s": item.nu_m2s,
                  "mu_pas": item.mu_pas, "chord_m": item.chord_m,
                  "u_inf_ms": item.u_inf_ms},
        "transition": transition,
        "profile_drag": profile_drag,
        "mangler": mangler,
        "wake": wake,
        "roughness": roughness,
        "stagnation": stagnation,
        "stokes": stokes,
        "unsteady": unsteady,
        "drag_table": drag_table,
        "verdict": verdict,
    }


# ===========================================================================
# Markdown rendering
# ===========================================================================

def render_report_markdown(model: dict) -> str:
    t = model["transition"]
    p = model["profile_drag"]
    m = model["mangler"]
    w = model["wake"]
    r = model["roughness"]
    s = model["stagnation"]
    k = model["stokes"]
    u = model["unsteady"]
    v = model["verdict"]
    inp = model["inputs"]

    lines = []
    lines.append("# " + model["document_type"])
    lines.append("")
    lines.append("**Item:** %s" % model["item"])
    lines.append("**Program:** %s" % model["program"])
    lines.append("**Reference basis:** %s" % model["certification_basis"])
    lines.append("**Status:** %s" % model["status"])
    lines.append("")
    lines.append(model["description"])
    lines.append("")
    lines.append("Reference air properties: rho = %.3f kg/m3, nu = %.3g "
                 "m2/s (mu = %.4g Pa s); wing chord c = %.2f m at "
                 "freestream U_inf = %.1f m/s."
                 % (inp["rho_kgm3"], inp["nu_m2s"], inp["mu_pas"],
                    inp["chord_m"], inp["u_inf_ms"]))
    lines.append("")

    lines.append("## 1. Laminar boundary-layer growth and transition "
                "(wing section)")
    lines.append("")
    lines.append("- Chord Reynolds number Re_c = %.4e." % t["re_c"])
    lines.append("- Blasius trailing-edge state at the chord station: "
                 "delta = %.3f mm, delta* = %.3f mm, theta = %.4f mm, "
                 "H = %.4f." % (1000 * t["delta_c_m"],
                               1000 * t["delta_star_c_m"],
                               1000 * t["theta_c_m"], t["shape_factor"]))
    lines.append("- Local/average skin friction at the chord station: "
                 "Cf_local = %.5f, Cf_avg = %.5f."
                 % (t["cf_local_c"], t["cf_avg_c"]))
    lines.append("- Transition criterion: %s." % t["criterion"])
    if t["x_tr_m"] is not None:
        lines.append("- Natural transition: x_tr = %.4f m (x/c = %.3f), "
                     "Re_x,tr = %.4e, Re_theta,tr = %.1f."
                     % (t["x_tr_m"], t["x_tr_over_c"], t["re_x_tr"],
                        t["re_theta_tr"]))
    else:
        lines.append("- Natural transition: not reached over the modeled "
                     "run.")
    lines.append("")

    lines.append("## 2. Section profile drag (Squire-Young)")
    lines.append("")
    lines.append("- Modeled trailing-edge state: U_TE/U_inf = %.3f "
                 "(mild aft pressure recovery), H_TE = %.2f."
                 % (p["u_te_over_u_inf"], SY_H_TE_DEFAULT))
    lines.append("- Trailing-edge momentum thickness (fully laminar "
                 "integral growth) theta_TE = %.5f mm; edge-velocity "
                 "factor = %.4f." % (1000 * p["theta_te_m"],
                                    p["edge_velocity_factor"]))
    lines.append("- Squire-Young profile drag: c_d,p = %.5f (one surface), "
                 "%.5f (both surfaces)."
                 % (p["cdp_one_surface"], p["cdp_both_surfaces"]))
    lines.append("- Blasius flat-plate reduction check 1.328/sqrt(Re_c) = "
                 "%.5f (zero-pressure-gradient identity residual %.2e)."
                 % (p["blasius_check_cdp"], p["identity_residual"]))
    lines.append("- Attached-flow check (Thwaites lambda, boundary-layer-"
                 "separation leaf): %s." % p["attached_check"])
    lines.append("")

    lines.append("## 3. Mangler axisymmetric transform (fuselage forebody)")
    lines.append("")
    lines.append("- Cone surface radius r0(x) = %.4f m; Mangler equivalent "
                 "2-D running length xi = %.5f m (at Re_x = %.4e)."
                 % (m["cone_radius_m"], m["mangler_xi_m"], m["re_x"]))
    lines.append("- Flat-plate baseline at the same running length: "
                 "Cf = %.5f, tau_w = %.4f Pa, delta = %.3f mm, "
                 "delta* = %.4f mm, theta = %.4f mm."
                 % (m["cf_flat"], m["tau_w_flat_pa"], 1000 * m["delta_flat_m"],
                    1000 * m["delta_star_flat_m"], 1000 * m["theta_flat_m"]))
    lines.append("- Cone values at equal running length (sqrt(3) laminar "
                 "cone factor): Cf = %.5f, tau_w = %.4f Pa, "
                 "delta = %.3f mm, delta* = %.4f mm, theta = %.4f mm, "
                 "H = %.4f."
                 % (m["cf_cone"], m["tau_w_cone_pa"], 1000 * m["delta_cone_m"],
                    1000 * m["delta_star_cone_m"], 1000 * m["theta_cone_m"],
                    m["h_cone"]))
    lines.append("- Axisymmetric momentum thickness is %.1f%% of the plain "
                 "2-D (flat-plate) estimate at the same station (the "
                 "1/sqrt(3) cone factor)."
                 % (100.0 * m["theta_ratio_cone_over_2d"]))
    lines.append("- Forebody wetted area %.4f m2; friction drag "
                 "(average Cf = 2x local laminar identity) = %.2f N."
                 % (m["wetted_area_m2"], m["drag_n"]))
    lines.append("")

    lines.append("## 4. Laminar far wake (downstream strut)")
    lines.append("")
    lines.append("- Strut trailing-edge state at Re_c = %.4e: "
                 "theta_c = %.4f mm; plate drag %.4f N/m "
                 "(C_D = %.5f)." % (w["re_c"], 1000 * w["theta_c_m"],
                                   w["plate_drag_nm"], w["plate_cd"]))
    lines.append("- Far-wake traverse at x = %.3f m downstream of the "
                 "trailing edge: spread parameter B = %.3f 1/m2, "
                 "centerline defect u_c = %.5f m/s."
                 % (w["station_x_m"], w["spread_b_1m2"],
                    w["centerline_defect_ms"]))
    lines.append("- Wake widths: half-defect %.4f mm, 1/e %.4f mm."
                 % (1000 * w["half_width_m"], 1000 * w["one_over_e_width_m"]))
    lines.append("- Momentum integral %.5e m2/s; wake-survey drag "
                 "%.4f N/m (matches the plate drag); nonlinear honesty "
                 "residual %.3f%%."
                 % (w["momentum_integral_m2s"], w["wake_survey_drag_nm"],
                    w["linearization_residual_pct"]))
    lines.append("")

    lines.append("## 5. Rough-wall skin friction (leading-edge finish)")
    lines.append("")
    lines.append("- Station Re_x = %.4e: smooth-wall baseline Cf = %.5f."
                 % (r["re_x"], r["cf_smooth"]))
    lines.append("- Roughness Reynolds number k+ = %.2f -> regime: "
                 "**%s** (%s)." % (r["k_s_plus"], r["regime"], r["note"]))
    lines.append("- Operative skin-friction coefficient Cf_used = %.5f."
                 % r["cf_used"])
    lines.append("- Trip criterion: Re_k = %.1f -> trip expected: **%s**."
                 % (r["trip"]["re_k"], r["trip"]["trip_expected"]))
    lines.append("")

    lines.append("## 6. Stagnation-point boundary layer (fuselage nose)")
    lines.append("")
    lines.append("- Flow type: %s." % s["flow_type"])
    lines.append("- Stagnation velocity gradient a = %.2f 1/s; "
                 "99-percent layer thickness = %.4f mm."
                 % (s["a_1s"], 1000 * s["delta_m"]))
    lines.append("- Wall shear tau_w = %.4f Pa; skin-friction coefficient "
                 "Cf = %.5f." % (s["tau_w_pa"], s["cf"]))
    lines.append("")

    lines.append("## 7. Stokes creeping-flow drag (protruding sensor)")
    lines.append("")
    lines.append("- Sensor radius a = %.1f microns at local (near-wall) "
                 "speed U = %.3f m/s: Re_a = %.5f, Re_D = %.5f (creeping "
                 "regime)." % (1e6 * k["radius_m"], k["local_speed_ms"],
                              k["re_a"], k["re_d"]))
    lines.append("- Stokes drag F = %.4e N (pressure %.4e N, friction "
                 "%.4e N, exact 1:2 split); Cd = %.2f."
                 % (k["drag_n"], k["pressure_drag_n"], k["friction_drag_n"],
                    k["drag_coefficient"]))
    lines.append("- Windward stagnation-point pressure rise +%.4e Pa; "
                 "equatorial wall shear %.4e Pa."
                 % (k["stagnation_pressure_delta_pa"],
                    k["equator_wall_shear_pa"]))
    lines.append("- Oseen-corrected drag %.4e N (+%.2f%% over the pure "
                 "Stokes value)." % (k["oseen_drag_n"],
                                    k["oseen_increase_pct"]))
    lines.append("")

    lines.append("## 8. Unsteady laminar Stokes layer (surface oscillation)")
    lines.append("")
    lines.append("- Oscillation at omega = %.2f rad/s: penetration depth "
                 "= %.4f mm." % (u["omega_rads"],
                                1000 * u["penetration_depth_m"]))
    lines.append("| y/delta | amplitude (m/s) | phase lag (deg) |")
    lines.append("|---|---|---|")
    for row in u["profile"]:
        lines.append("| %.1f | %.4f | %.2f |"
                     % (row["y_over_delta"], row["amplitude_ms"],
                        row["lag_deg"]))
    lines.append("")
    lines.append("- Wall-shear amplitude = %.4f Pa."
                 % u["wall_shear_amplitude_pa"])
    lines.append("- Reduced frequency k = %.4f. %s"
                 % (u["reduced_frequency"], u["relevance_note"]))
    lines.append("")

    lines.append("## 9. Assembled drag table and verdict")
    lines.append("")
    lines.append("| Component | Basis | Value | Units |")
    lines.append("|---|---|---|---|")
    for row in model["drag_table"]:
        lines.append("| %s | %s | %.4g | %s |"
                     % (row["component"], row["basis"], row["value"],
                        row["units"]))
    lines.append("")
    lines.append("Per-span (N/m) and discrete-body (N) entries above are "
                 "NOT summed to a single number: the wing and wake-strut "
                 "rows are per unit span, the forebody and sensor rows are "
                 "discrete-body totals, and no vehicle span/wetted-area "
                 "basis has been stated to combine them honestly.")
    lines.append("")
    lines.append("- Laminar-drag target c_d,p (both surfaces): %.4f."
                 % v["target_cdp"])
    lines.append("- Computed Squire-Young c_d,p (both surfaces, fully "
                 "laminar target run): %.4f (gap %+.4f, %s)."
                 % (v["computed_cdp_both_surfaces"], v["gap_cdp"],
                    "meets target" if v["meets_target"]
                    else "above target"))
    lines.append("- %s" % v["transition_caveat"])
    lines.append("")
    lines.append("## Open items for human review")
    lines.append("")
    lines.append("- The wing edge-velocity ramp, the fuselage cone angle "
                 "and running length, the strut chord, the surface "
                 "roughness height and the sensor/oscillation parameters "
                 "are stated design assumptions for this reference item; "
                 "confirm against the program's actual geometry and CFD/"
                 "wind-tunnel data before release.")
    lines.append("- The fully laminar Squire-Young estimate (Section 2) "
                 "represents the NLF design target; Section 1's Michel-"
                 "criterion finding is the honesty check against it "
                 "(see the Section 9 caveat).")
    lines.append("- The forebody friction-drag estimate (Section 3) uses "
                 "the sqrt(x)-scaling average-equals-2x-local identity "
                 "carried over from the flat-plate laminar result; a full "
                 "streamwise integration should replace it before release.")
    lines.append("")
    lines.append("---")
    lines.append("*Generated by Aero Agent Roles boundary-layer-engineer "
                 "core (%s). DRAFT for human boundary-layer engineering "
                 "review. Not an approval document and not a "
                 "certification approval.*" % model["generated"])
    return "\n".join(lines)


# ===========================================================================
# Evidence gates
# ===========================================================================

def check_report(model: dict) -> dict:
    """Run the evidence gates against the report model."""
    t = model["transition"]
    p = model["profile_drag"]
    m = model["mangler"]
    w = model["wake"]
    r = model["roughness"]
    s = model["stagnation"]
    k = model["stokes"]
    u = model["unsteady"]
    results = {
        "item_identified": bool(model.get("item")),
        "transition_located": t.get("x_tr_m") is not None,
        "profile_drag_computed": p.get("cdp_both_surfaces", 0) > 0,
        "blasius_identity_holds": p.get("identity_residual", 1.0) < 1e-6,
        "mangler_ratio_correct": abs(m.get("theta_ratio_cone_over_2d", 0)
                                    - INV_SQRT3) < 1e-9,
        "wake_drag_positive": w.get("wake_survey_drag_nm", 0) > 0,
        "roughness_regime_identified": r.get("regime") in
            ("smooth", "transitional", "fully-rough"),
        "stagnation_layer_present": s.get("delta_m", 0) > 0,
        "stokes_drag_positive": k.get("drag_n", 0) > 0,
        "unsteady_depth_present": u.get("penetration_depth_m", 0) > 0,
        "sign_off_honest": model.get("status") == "draft-for-review",
    }
    results["all_pass"] = all(results.values())
    return results


def check_report_markdown(md_text: str) -> dict:
    """Gate-check the rendered markdown deliverable."""
    low = md_text.lower()
    checks = {
        "has_title": "boundary-layer and viscous drag analysis report"
                    in low,
        "has_numbers": "re_c" in low and "mm" in low and "pa" in low,
        "has_squire_young": "squire-young" in low,
        "has_mangler": "mangler" in low,
        "has_stokes": "stokes" in low,
        "has_draft_marker": "draft" in low,
        "has_not_approval": "not an approval" in low,
        "has_no_cert_claim": "not a certification approval" in low,
    }
    checks["all_pass"] = all(checks.values())
    return checks


def validate_deliverable_text(md_text: str) -> dict:
    """Public entry point used by gate tooling."""
    return check_report_markdown(md_text)


# ===========================================================================
# Example item (for tests and worked-example generation)
# ===========================================================================

def example_item() -> BLItem:
    return BLItem()


def example_report_markdown() -> str:
    item = example_item()
    model = build_report(item)
    return render_report_markdown(model)


if __name__ == "__main__":
    item = example_item()
    model = build_report(item)
    md = render_report_markdown(model)
    print("ITEM: %s" % model["item"])
    print("TRANSITION x/c: %s" % model["transition"]["x_tr_over_c"])
    print("PROFILE DRAG cdp (both surfaces): %.5f"
         % model["profile_drag"]["cdp_both_surfaces"])
    print("GATES: %s" % check_report(model))
    print("RENDERED: %d chars" % len(md))
