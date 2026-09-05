# SOURCES.md - Engineering Analysis and Data Engineer

| Source | Role use | Gated |
|---|---|---|
| ASME Y14.5 | GD&T conventions (dimensioning/tolerancing basis for stacks) | true |
| ISO 2533 / ICAO Doc 7488 | Standard atmosphere: ISA constants and lapse model (sea level 288.15 K / 101325 Pa / 1.225 kg/m3, 6.5 K/km to 11 km) | false |
| JCGM 100:2008 (GUM) | Measurement uncertainty: first-order law u_c = sqrt(sum((df/dx_i * u_i)^2)), coverage factor k, expanded uncertainty | false |
| JCGM 101 (GUM Supp. 1) | Monte Carlo uncertainty evaluation context (bound leaf monte-carlo-sampling) | false |
| Student t distribution (standard statistics) | Small-sample confidence intervals: xbar +/- t_{1-alpha/2, n-1} * s/sqrt(n) | false |
| Richardson extrapolation / GCI (AIAA V&V practice) | Numerical convergence verification: observed order p, grid convergence index, Fs = 1.25 | false |
| MIL-STD-810 / DO-160 (context) | Data context where applicable | true |

Summary-not-copy per STANDARDS.md: public standards (ISO 2533, JCGM 100)
are used as common-knowledge method summaries, never reproduced verbatim;
ASME Y14.5 and MIL-STD-810 / DO-160 are reference-only.
