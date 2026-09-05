# SOURCES.md - Flight Test Performance Engineer

Standards and documents this role references. Summary-not-copy: see
[STANDARDS.md](../../STANDARDS.md) for the full rule and purchase links.

| Source | Role use | Gated |
|---|---|---|
| FAR Part 25 (Subpart B) | takeoff/landing distance definitions context (35 ft obstacle, 1.67 field length factor practice), V-speed context | false |
| CS-25 (EASA) | EASA counterpart of the Part 25 performance context | false |
| ICAO Standard Atmosphere (Doc 7488) | ISA temperature/pressure/density model used for all reductions to standard conditions | false |
| AeroSkills flight-test-operations/performance leaves | the concrete reduction methods (trapezoid ground roll, Vref = 1.23 x Vs0, total-energy P_s, sqrt(w_ref/w_test) fuel-flow correction, sqrt(w/w_ref) speed correction, sigma^0.7 thrust lapse) | true |

Domain-logic rule: every number the core produces comes from a REAL
method in the bound AeroSkills leaves or from quotable public physics
(ISA atmosphere, FAR/CS-25 summary context). Conservative defaults
(dry-runway braking friction mu = 0.42, thrust lapse exponent 0.7,
scatter band +-10%) are documented in the core module docstrings and in
this table. The worked-example sortie data in the report template are
SIMULATED (marked as such in the deliverable) and must be replaced by
recorded flight data before the report leaves draft.
