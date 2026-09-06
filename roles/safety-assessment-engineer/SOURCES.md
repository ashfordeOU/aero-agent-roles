# SOURCES.md - Safety Assessment Engineer

Standards and documents this role references. Summary-not-copy: see
[STANDARDS.md](../../STANDARDS.md) for the full rule and purchase links.

| Source | Role use | Gated |
|---|---|---|
| SAE ARP4761A | safety assessment process (FHA/PSSA/SSA), FTA, FMEA, CCA methods | true |
| SAE ARP4754A | development assurance context (FDAL/IDAL), requirements traceability | true |
| 14 CFR Part 25.1309 (FAR-25) | failure-condition severity categories and probability magnitudes | false |
| EASA CS-25.1309 (CS-25) | EASA mirror of the 25.1309 safety requirements | false |
| FAA AC 25.1309-1A | probability band terminology (extremely improbable ... probable) | false |
| MIL-STD-1629A | quantitative FMECA criticality convention (beta/alpha, C_m) | false |

The safety assessment report template in `templates/` is an original
structure informed by public-domain guidance (AC 25.1309-1A, FAR/CS
25.1309) and paraphrase-level process knowledge. Probability targets
(catastrophic <1e-9 per flight hour, hazardous <1e-7, major <1e-5,
minor <1e-3) are the common-knowledge magnitudes of standard practice,
not reproduced text. No proprietary SAE text is reproduced.
