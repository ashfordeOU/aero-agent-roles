# SOURCES.md - Flight Management Engineer

Standards and documents this role references. Summary-not-copy: see
[STANDARDS.md](../../STANDARDS.md) for the full rule and purchase links.

| Source | Role use | Gated |
|---|---|---|
| RTCA DO-236C | RNAV/RNP system and FMS functional requirements, RNP containment and alerting concepts (95% containment basis) | true |
| RTCA DO-283A | RNP AR procedure design criteria (RF leg context) | true |
| FAA AC 90-105A | public approval guidance for RNP operations and baro-VNAV in the U.S. NAS, oceanic and remote airspace | false |
| FAA AC 90-101A | public approval guidance for RNP AR procedures (RF legs, containment) | false |
| FAA AIM / Instrument Flying Handbook | holding pattern entry sectors and timing (operational procedure, paraphrased) | false |
| 14 CFR Part 25 | airworthiness context for the FMS procedure function | false |
| ICAO Doc 9613 (PBN Manual) | performance-based navigation framework (reference only) | true |

Acquisition status: DO-236C/DO-283A are purchased RTCA documents -
referenced summary-only, never quoted. AC 90-105A, AC 90-101A, the AIM
and 14 CFR Part 25 are public FAA documents (available from faa.gov);
paraphrase preferred, short attributed quotes allowed.

The role's numeric rules are public geometric/physical equations
(spherical great-circle geometry, coordinated-turn radius
V^2/(g tan(bank)), the 1-in-60 rule, ISA atmosphere) and the documented
leaf models of the bound AeroSkills avionics/flight-management leaves:
RNP containment (ANP = 2 x 1-sigma, 95% containment), the 70/110
holding-entry sector rule, outbound leg timing (60 s at or below
14000 ft, 90 s above), DME arc/radius-to-fix geometry, and the
documented simplified mid-size-transport drag/fuel model (calibrate per
aircraft against the FMS performance manual). No proprietary table or
standard text is reproduced anywhere in this role.
