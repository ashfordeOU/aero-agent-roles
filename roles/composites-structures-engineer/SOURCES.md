# SOURCES.md - Composite Structures Engineer

Standards and documents this role references. Summary-not-copy: see
[STANDARDS.md](../../STANDARDS.md) for the full rule and purchase links.

| Source | Role use | Gated |
|---|---|---|
| 14 CFR Part 25 (FAR-25) | structural rules: strength (25.305), proof of structure (25.307), damage tolerance (25.571) — public regulation context | false |
| EASA CS-25 | European certification specifications counterpart of FAR-25 | true |
| CMH-17 (Composite Materials Handbook) | statistical basis methodology (A/B-basis, pooling, knockdowns for environment/BVID/open hole) — reference by name only, no tables reproduced | true |
| FAA AC 20-107B | composite aircraft structure guidance (context for the evidence plan) | false |
| Daniel & Ishai, "Engineering Mechanics of Composite Materials" | classical lamination theory and failure criteria (standard methodology) | false |

## Provenance of the numbers

The engine's worked example uses the published T300/5208-style lamina
constants that the bound AeroSkills composite leaves themselves use as
their worked-example material (lamina stiffness, allowables, expansion
coefficients). All laminate-level numbers are exact classical lamination
theory arithmetic: stiffness from the CLT A/D assembly, failure indices
from the Tsai-Wu and max-stress criteria, hygrothermal coefficients from
the exact 2x2 CLT free-expansion solution, buckling loads from the
energy method for a simply supported orthotropic plate. Knockdown factor
magnitudes (environment, BVID) are conservative engineering inputs the
report states explicitly; they must be confirmed by the program's
coupon-test data before any human sign-off.

The templates/ deliverable is an original synthesis (structure and
text), never a copy of CMH-17 or AC 20-107B content.
