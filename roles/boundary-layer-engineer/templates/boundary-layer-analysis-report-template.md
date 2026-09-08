# Boundary-Layer and Viscous Drag Analysis Report

**Item:** Halcyon-18 wing root section and fuselage forebody boundary-layer assessment
**Program:** Halcyon-18 natural-laminar-flow sailplane
**Reference basis:** NACA TR-824 boundary-layer methodology (reference-only)
**Status:** draft-for-review

Boundary-layer and viscous-drag assessment of a natural-laminar-flow sailplane wing root section and an axisymmetric fuselage forebody at cruise, plus a small protruding sensor and a stated surface oscillation.

Reference air properties: rho = 1.225 kg/m3, nu = 1.46e-05 m2/s (mu = 1.789e-05 Pa s); wing chord c = 0.65 m at freestream U_inf = 79.0 m/s.

## 1. Laminar boundary-layer growth and transition (wing section)

- Chord Reynolds number Re_c = 3.5171e+06.
- Blasius trailing-edge state at the chord station: delta = 1.733 mm, delta* = 0.596 mm, theta = 0.2301 mm, H = 2.5916.
- Local/average skin friction at the chord station: Cf_local = 0.00035, Cf_avg = 0.00071.
- Transition criterion: Michel empirical criterion on the Thwaites-grown momentum-thickness Reynolds number, zero-pressure-gradient closed form (boundary-layer-transition leaf).
- Natural transition: x_tr = 0.3078 m (x/c = 0.474), Re_x,tr = 1.6657e+06, Re_theta,tr = 865.8.

## 2. Section profile drag (Squire-Young)

- Modeled trailing-edge state: U_TE/U_inf = 0.900 (mild aft pressure recovery), H_TE = 1.40.
- Trailing-edge momentum thickness (fully laminar integral growth) theta_TE = 0.27898 mm; edge-velocity factor = 0.7138.
- Squire-Young profile drag: c_d,p = 0.00061 (one surface), 0.00123 (both surfaces).
- Blasius flat-plate reduction check 1.328/sqrt(Re_c) = 0.00071 (zero-pressure-gradient identity residual 0.00e+00).
- Attached-flow check (Thwaites lambda, boundary-layer-separation leaf): attached (Thwaites lambda never crosses -0.09 over the run).

## 3. Mangler axisymmetric transform (fuselage forebody)

- Cone surface radius r0(x) = 0.1686 m; Mangler equivalent 2-D running length xi = 0.01138 m (at Re_x = 6.4932e+06).
- Flat-plate baseline at the same running length: Cf = 0.00026, tau_w = 0.9961 Pa, delta = 2.355 mm, delta* = 0.8104 mm, theta = 0.3127 mm.
- Cone values at equal running length (sqrt(3) laminar cone factor): Cf = 0.00045, tau_w = 1.7253 Pa, delta = 1.359 mm, delta* = 0.4679 mm, theta = 0.1805 mm, H = 2.5916.
- Axisymmetric momentum thickness is 57.7% of the plain 2-D (flat-plate) estimate at the same station (the 1/sqrt(3) cone factor).
- Forebody wetted area 0.6420 m2; friction drag (average Cf = 2x local laminar identity) = 2.22 N.

## 4. Laminar far wake (downstream strut)

- Strut trailing-edge state at Re_c = 2.7055e+05: theta_c = 0.0638 mm; plate drag 0.9760 N/m (C_D = 0.00511).
- Far-wake traverse at x = 5.000 m downstream of the trailing edge: spread parameter B = 270547.945 1/m2, centerline defect u_c = 2.95951 m/s.
- Wake widths: half-defect 1.6006 mm, 1/e 1.9226 mm.
- Momentum integral 1.00849e-02 m2/s; wake-survey drag 0.9760 N/m (matches the plate drag); nonlinear honesty residual 2.649%.

## 5. Rough-wall skin friction (leading-edge finish)

- Station Re_x = 2.7055e+05: smooth-wall baseline Cf = 0.00485.
- Roughness Reynolds number k+ = 13.32 -> regime: **transitional** (transitional: log-linear blend between smooth and rough).
- Operative skin-friction coefficient Cf_used = 0.00533.
- Trip criterion: Re_k = 162.3 -> trip expected: **False**.

## 6. Stagnation-point boundary layer (fuselage nose)

- Flow type: axisymmetric (Homann).
- Stagnation velocity gradient a = 592.50 1/s; 99-percent layer thickness = 0.3767 mm.
- Wall shear tau_w = 11.8082 Pa; skin-friction coefficient Cf = 0.00309.

## 7. Stokes creeping-flow drag (protruding sensor)

- Sensor radius a = 100.0 microns at local (near-wall) speed U = 0.010 m/s: Re_a = 0.06849, Re_D = 0.13699 (creeping regime).
- Stokes drag F = 3.3712e-10 N (pressure 1.1237e-10 N, friction 2.2475e-10 N, exact 1:2 split); Cd = 175.20.
- Windward stagnation-point pressure rise +2.6828e-03 Pa; equatorial wall shear 2.6828e-03 Pa.
- Oseen-corrected drag 3.4578e-10 N (+2.57% over the pure Stokes value).

## 8. Unsteady laminar Stokes layer (surface oscillation)

- Oscillation at omega = 125.66 rad/s: penetration depth = 0.4820 mm.
| y/delta | amplitude (m/s) | phase lag (deg) |
|---|---|---|
| 0.0 | 2.0000 | 0.00 |
| 0.5 | 1.2131 | 28.65 |
| 1.0 | 0.7358 | 57.30 |
| 2.0 | 0.2707 | 114.59 |
| 3.0 | 0.0996 | 171.89 |

- Wall-shear amplitude = 0.1049 Pa.
- Reduced frequency k = 0.5170. penetration depth is 27.8% of the trailing-edge boundary-layer thickness at 0.517 reduced frequency: the Stokes layer stays well inside the mean boundary layer; quasi-steady treatment of the mean flow is adequate

## 9. Assembled drag table and verdict

| Component | Basis | Value | Units |
|---|---|---|---|
| Wing section profile drag (both surfaces) | per unit span | 3.045 | N/m |
| Strut far-wake survey drag | per unit span | 0.976 | N/m |
| Fuselage forebody friction drag (to x=1.20 m) | discrete body | 2.215 | N |
| Sensor-pod Stokes drag (Oseen-corrected) | discrete body | 3.458e-10 | N |

Per-span (N/m) and discrete-body (N) entries above are NOT summed to a single number: the wing and wake-strut rows are per unit span, the forebody and sensor rows are discrete-body totals, and no vehicle span/wetted-area basis has been stated to combine them honestly.

- Laminar-drag target c_d,p (both surfaces): 0.0011.
- Computed Squire-Young c_d,p (both surfaces, fully laminar target run): 0.0012 (gap +0.0001, above target).
- Michel-criterion natural transition at x/c=0.474 falls short of the fully laminar target used above (full-chord laminar run to the trailing edge); realizing the target profile-drag estimate requires the shaped favorable-gradient pressure distribution of the NLF airfoil (or boundary-layer suction/hybrid laminar-flow control) beyond the mild ramp modeled here, and should be re-verified with a coupled panel/eN method (e.g. XFOIL) before release.

## Open items for human review

- The wing edge-velocity ramp, the fuselage cone angle and running length, the strut chord, the surface roughness height and the sensor/oscillation parameters are stated design assumptions for this reference item; confirm against the program's actual geometry and CFD/wind-tunnel data before release.
- The fully laminar Squire-Young estimate (Section 2) represents the NLF design target; Section 1's Michel-criterion finding is the honesty check against it (see the Section 9 caveat).
- The forebody friction-drag estimate (Section 3) uses the sqrt(x)-scaling average-equals-2x-local identity carried over from the flat-plate laminar result; a full streamwise integration should replace it before release.

---
*Generated by Aero Agent Roles boundary-layer-engineer core (2026-09-08). DRAFT for human boundary-layer engineering review. Not an approval document and not a certification approval.*
