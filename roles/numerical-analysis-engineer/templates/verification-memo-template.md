# Numerical Methods Verification Memo

**Code under verification:** Loads Post-Processor (LPP) (version v2.3.1)
**Verification basis:** classical numerical analysis (Richardson 1910/1927; Euler-Maclaurin error analysis; Newton/Simpson/Gauss); ASME V&V 20-2009 vocabulary for discretization error
**Status:** draft-for-review

## 1. Scope and method selection

The LPP loads post-processor turns the spanwise load distribution into the half-span resultant used by the loads report, inverts the isentropic area-Mach relation for duct sizing, and solves the 2x2 aerodynamic coefficient system A c = b. This memo independently verifies the numerical methods of the item above: the spanwise-load integral, the area-Mach root inversion, and the loads coefficient solve are each recomputed with reference methods and compared against the code's reported values and claimed tolerances. A three-mesh convergence study and a conditioning report bound the discretization and rounding error of the results.

| Operation | Code method | Reference method | Why |
|---|---|---|---|
| spanwise load intensity w(y) = w0*(1 - (2y/span)^2), half-span integral | composite trapezoid, n=16 panels | composite Simpson | Composite Simpson error scales with h^4 and the rule is exact for polynomials of degree <= 3, beating trapezoid on smooth integrands at moderate panel counts. |
| area-Mach inversion (A/A* = 1.2, subsonic) | code-internal Newton solver | Newton-Raphson (quadratic, simple root) with bisection bracket cross-check | Bisection guarantees convergence when the bracket straddles zero (linear); Newton gives quadratic convergence from a nearby guess when the derivative is non-zero; agreement of the two independent iterations cross-validates the root. |
| loads coefficient solve A c = b | code-internal dense solver | Gaussian elimination with partial pivoting | Partial pivoting bounds element growth and avoids zero pivots; the reference residual A x - b is checked at machine precision, and the conditioning report bounds how much backward error the solve amplifies. |

## 2. Reference computations

### 2.1 Reference integral

Integrand: spanwise load intensity w(y) = w0*(1 - (2y/span)^2), half-span integral on [0.000000, 18.000000] m (peak load 4200 N/m, span 36 m).
- Reference value (composite Simpson): 50400.000000 N
- Closed-form anchor w0*span/3: 50400.000000 N (the integrand is a quadratic, so Simpson is exact here)
- Richardson error estimate at the code's panel count: the trapezoid error scales with h^2, giving error(2n) = |I_2n - I_n|/3 = 12.304688 N.

### 2.2 Reference root

- isentropic area-Mach inversion (A/A* = 1.2, gamma = 1.4), subsonic branch: M* = 0.590248761
- Reference method: reference Newton-Raphson from x0 = 0.3 + bisection bracket cross-check - converged in 6 iterations, residual |f| = 2.22e-16
- Derivative at the root f'(M*) = -1.238449 (non-zero: simple root, quadratic convergence expected); root sensitivity per unit residual 1/|f'| = 0.807462
- Bracket [0.200, 0.990] straddles zero: True
- Bisection cross-check: M = 0.590248761, agreement with Newton 8.17e-12

### 2.3 Reference linear solve

- Reference solution c = A^-1 b: 0.285714286, 0.285714286
- Condition number kappa = s_max/s_min: 7.0000
- Conditioning assessment: kappa = 7: up to 0.85 decimal digits of input uncertainty can be amplified by the solve

## 3. Cross-check against the engineering code

Each operation: code-reported value vs reference value; verdict PASS when the discrepancy is within the code's own claimed tolerance.

### 3.1 Integration

- Operation: spanwise load integral
- Code method: composite trapezoid, n=16 panels
- Reference method: composite Simpson, n=64 (exact for degree <= 3) + Richardson error estimate
- Code-reported value: 50350.781250000 N
- Reference value (composite Simpson, n=64): 50400.000000000 N
- Discrepancy: 49.218750000 N
- Code-claimed tolerance: 1.000 N
- Richardson estimate of the code's n-panel error: 49.218750 N (from the code's own n and 2n outputs)
- **Verdict: FAIL**
- Method fingerprint: the reference engine's trapezoid at the code's panel count reproduces the code output (50350.781250000) - the code's method was identified correctly.

### 3.2 Root finding

- Operation: isentropic area-Mach inversion (A/A* = 1.2, gamma = 1.4), subsonic branch
- Code method: code-internal Newton solver
- Reference method: reference Newton-Raphson from x0 = 0.3 + bisection bracket cross-check
- Code-reported value: M = 0.590248761
- Reference value: M* = 0.590248760988 (residual |f| = 2.22e-16)
- Bisection cross-check: M = 0.590248761 (agreement with Newton 8.17e-12)
- Discrepancy: 1.15e-11
- Code-claimed tolerance: 1.00e-08
- **Verdict: PASS**

### 3.3 Linear solve

- Operation: loads coefficient solve A c = b
- Code method: code-internal dense solver
- Reference method: Gaussian elimination with partial pivoting (reference engine)
- Code-reported solution: [0.285714000, 0.285714000]
- Reference solution: [0.285714286, 0.285714286]
- Discrepancy (max component): 2.86e-07
- Code-claimed tolerance: 1.00e-06
- **Verdict: PASS**
- Condition number kappa = s_max/s_min: 7.0000
- Conditioning: kappa = 7: up to 0.85 decimal digits of input uncertainty can be amplified by the solve

## 4. Convergence and error analysis

Three-mesh study of the code's own outputs (refinement ratio r = 2, finest f1 to coarsest f3):

- 64: 50396.923828
- 32: 50387.695312
- 16: 50350.781250
- Observed order p = 2.000 (consistent with composite trapezoid (order 2))
- Richardson extrapolated value: 50400.000000
- Grid convergence index (GCI, Fs = 1.25): 7.63e-05 fraction (0.0076%)
- Verdict: monotone converged
- Code-reported value vs finest mesh: 46.142578 N

## 5. Findings and recommendations

### F-1 (Discrepancy)

spanwise load integral reports 50350.781250 N while the reference integration gives 50400.000000 N: discrepancy 49.218750 N exceeds the code's claimed tolerance of 1 N.

Evidence: Richardson error estimate of the code's n-panel output is 49.218750 N (measured discrepancy 49.218750 N); the three-mesh study shows observed order 2.00, so the code's panel count cannot support the claimed tolerance.

Recommendation: Refine to n >= 64 panels or switch to a composite Simpson rule, and gate the output with a Richardson error estimate before release.

### O-1 (Observation)

root-finding (isentropic area-Mach inversion (A/A* = 1.2, gamma = 1.4), subsonic branch) verified within the code's claimed tolerance (discrepancy 1.1549e-11 <= 1e-08).

### O-2 (Observation)

linear solve (loads coefficient solve A c = b) verified within the code's claimed tolerance (discrepancy 2.85714e-07 <= 1e-06).

## 6. Verification limits

- Scope: the three numerical operations named above, on the example item's input set. Other code paths (ODE integration, interpolation, least-squares fitting, finite-difference derivatives, uncertainty propagation) follow the same reference-engine workflow when exercised.
- The code's claimed tolerances are inputs to this memo, not endorsements; a PASS verdict means the claim is supported by the reference computation on this input set.
- Export classification: uncontrolled technical data (example).

---
*Generated by Aero Agent Roles numerical-analysis-engineer core (2026-09-06). DRAFT for human numerical-analysis review. Not an approval document.*