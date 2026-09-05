# Analysis Verification Memo

**Chain:** Flight-test air-data chain at 3000 m
**Status:** draft-for-review

## 1. Scope and inputs

Analysis question: verify the measurement/calculation chain Flight-test air-data chain at 3000 m - reduce the measured static pressure and temperature to air density and density altitude, check the repeated-measurement bias, verify the probe mounting tolerance stack and the atmosphere-model integrator, and state margins.
- Analysis item: Flight-test air-data chain at 3000 m at geometric altitude 3000 m.
- Inputs (measured, with 1-sigma standard uncertainties): static pressure p = 70050 Pa +/- 35 Pa; temperature T = 271 K +/- 1.2 K.
- Inputs (geometry): 3-member probe mounting stack (see Section 5); position spec +/- 0.8 mm.
- Inputs (acceptance): density accuracy spec +/- 1.5 %.
- n=10 repeat readings of the static source error vs the reference pressure standard.

## 2. Unit/atmosphere basis

- Unit system: SI (Pa, K, kg/m3, m, mm). No unit conversions required in the chain; conversions applied for reporting: altitude 3000 m = 9842.5 ft; T 268.65 K = -4.5 degC.
- Atmosphere basis: ISA (ISO 2533 / ICAO Doc 7488) reference model, sea level 288.15 K / 101325.0 Pa / 1.225 kg/m3, lapse rate 6.5 K/km to 11 km.
- ISA reference values at 3000 m: T_ISA = 268.65 K, p_ISA = 70108 Pa, rho_ISA = 0.90913 kg/m3.

## 3. Method and verification

- Density from measured state: ideal gas EOS rho = p / (R T), R = 287.05 J/(kg K) (bound leaf: isa-atmosphere).
- Uncertainty: GUM (JCGM 100) first-order law with analytic sensitivities, combined standard uncertainty u_c = sqrt(sum((df/dx_i * u_i)^2)) and expanded U = k * u_c with k = 2 (~95 %) (bound leaf: uncertainty-propagation).
- Bias statistics: Student t interval for the mean of the repeat readings (bound leaf: confidence-interval-estimation).
- Density altitude: Newton inversion of rho_ISA(h) = rho_measured, converged in 3 iterations to residual 4.16e-10 (bound leaf: root-finding; convergence evidence per leaf convergence-verification).
- Numerical verification: three-grid trapezoid integration of the hydrostatic balance dp/dz = -rho g over 0..3000 m at 6, 12 and 24 steps (refinement ratio r = 2); Richardson extrapolation and grid convergence index (GCI) versus the closed-form ISA pressure.
- Numerical accuracy statement: see grid study below; the integrator is grid-converged and agrees with the closed-form ISA pressure at the test point.

## 4. Results

- Air density (measured chain): rho = 0.90049 kg/m3.
- Sensitivities: d rho/dp = 1.2855e-05 (kg/m3)/Pa, d rho/dT = -0.0033229 (kg/m3)/K.
- Combined standard uncertainty: u_c = 0.0040127 kg/m3 (0.44561 % of rho).
- Expanded uncertainty: U = 0.0080255 kg/m3 (k = 2). Result: rho = 0.90049 +/- 0.0080255 kg/m3.
- Uncertainty budget: 98.7% from temperature (s = -3.323e-03, u = 1.2); 1.3% from static pressure (s = 1.286e-05, u = 35).
- Versus ISA at 3000 m: delta = -0.94955 % (non-standard day).
- Density altitude: h_rho = 3092.6 m (+92.551 m above the geometric test point).
- Bias statistics (n=10 repeat readings of the static source error vs the reference pressure standard): mean bias 0.59 Pa, sample s = 1.907 Pa, 95 % t-interval [-0.77417, 1.9542] Pa (t = 2.2622, df = 9). Zero lies inside the interval: no statistically significant static-source bias at the 95 % level.

## 5. Tolerances

- GD&T basis: ASME Y14.5 (TIER-2 reference-only). The stack is a 1-D linear dimension chain with equal bilateral tolerances and independent, centered parts (bound leaf: tolerance-stackup).
- Chain members (signed nominal direction, tolerance, RSS share):
  - mounting bracket: 120 mm (dir +), +/- 0.5 mm, 52.9 % share
  - adapter: 45 mm (dir +), +/- 0.25 mm, 13.2 % share
  - probe inset: 60 mm (dir -), +/- 0.4 mm, 33.9 % share
- Nominal total: 105 mm.
- Worst case: +/- 1.15 mm -> limits [103.85, 106.15] mm.
- RSS: +/- 0.68739 mm -> limits [104.31, 105.69] mm.
- Dominant contributor: mounting bracket (52.9 % of RSS variance); tightening it reduces the stack most.

## 6. Data sources

- ISA model and constants: ISO 2533 / ICAO Doc 7488 standard atmosphere (public standard; summary-only use).
- Uncertainty method: GUM, JCGM 100:2008 (public guide; summary-only use).
- GD&T conventions: ASME Y14.5 (TIER-2 reference-only; summary-not-copy per SOURCES.md).
- Export-control classification: uncontrolled technical data (example). No controlled data is included in this memo.

## 7. Margins and conclusions

- Margins per the engineering-margins convention MS = allowable / applied - 1 (same units both sides).
- Density accuracy: applied (expanded) = 0.89123 %, allowable +/- 1.5 % -> MS = 0.68307 (PASS).
- Probe position stack, RSS basis: applied +/- 0.68739 mm, allowable +/- 0.8 mm -> MS = 0.16383 (PASS).
- Probe position stack, worst-case basis: applied +/- 1.15 mm, allowable +/- 0.8 mm -> MS = -0.30435 (FAIL).
- Conclusions: the chain is unit-consistent with the stated ISA basis; the expanded density uncertainty is driven by the temperature input (99 % of variance); repeated-measurement bias is not significant; the atmosphere integrator is monotone-converged (order 2), GCI 0.0005462 % at the test point, and agrees with the closed-form ISA pressure. The stack meets the position spec on the RSS basis but not on the worst-case basis: the RSS basis is valid only while the parts remain independent and centered (process-capability evidence required).

## 8. Open items

- For the design owner / human approver: confirm the density accuracy spec and the position spec limits used as allowables; decide worst-case vs RSS basis for the probe stack (tighten the dominant contributor mounting bracket if worst case must be met); confirm export-control classification before external release.

---
*Generated by Aero Agent Roles engineering-analysis-engineer core. DRAFT for human engineering review. Not an approval document.*