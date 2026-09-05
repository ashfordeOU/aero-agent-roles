# SOURCES.md - Numerical Analysis Engineer

Standards and documents this role references. Summary-not-copy: see
[STANDARDS.md](../../STANDARDS.md) for the full rule and purchase links.
The numerical methods themselves (Newton, Simpson/Gauss quadrature,
Richardson extrapolation, Gaussian elimination, condition numbers) are
classical analysis and public-domain methodology; the bound AeroSkills
leaves paraphrase them and anchor their tables.

| Source | Role use | Gated |
|---|---|---|
| ASME V&V 20-2009, Standard for Verification and Validation in CFD and Heat Transfer | discretization-error vocabulary (observed order, Richardson extrapolation, grid convergence index, safety factor) used in the memo's convergence section | true |
| Classical numerical analysis (Newton 1669/1711; Simpson 1743; Gauss 1814; Richardson 1910/1927; Euler-Maclaurin error analysis) | reference methods: quadrature rules, root iterations, error estimates - public domain, paraphrased | false |
| NACA Report 824 (public-domain anchor of the cross-cutting/numerics leaves) | compressible-flow relation context for the area-Mach inversion anchor used by the root-finding leaf | false |

The verification-memo template in `templates/` is an original
structure produced by the role's own core engine; it contains no
reproduced text from any standard. ASME V&V 20-2009 is referenced for
its methodology vocabulary only (summary-not-copy, TIER-2).
