# SOURCES.md - Data Bus / Avionics Network Engineer

Standards and documents this role references. Summary-not-copy: see
[STANDARDS.md](../../STANDARDS.md) for the full rule and purchase links.

| Source | Role use | Gated |
|---|---|---|
| ARINC 429 (Mark 33 DITS) | 32-bit word format, octal label, SDI, SSM, parity, BNR/BCD coding, 12.5/100 kbps topology, 36 bit-times per word loading model | true (TIER-2, reference-only) |
| ARINC 664 Part 7 (AFDX) | virtual link definition, BAG sizing, 100 Mbps link budget, redundancy, jitter/latency margins | true (TIER-2, reference-only) |
| MIL-STD-1553B | 20-bit command/status/data words, BC/RT operation, dual redundant bus, 1 Mbps command/response protocol | false (TIER-1, US public domain) |
| MIL-STD-1553 bus loading practice | minor-frame schedule, wire-word counting, 24 us word slot, 80% loading guideline | false (derived practice) |
| ARINC 429 loading practice | label-rate schedule budgets, word-per-second capacity (~2778 wps @ 100 kbps), 80% design guideline | false (derived practice) |

The AeroSkills data-bus leaves (avionics/data-bus/arinc429-protocol,
arinc429-bus-loading, arinc664-afdx, mil-std-1553,
mil-std-1553-bus-loading) encode the protocol/loading rules this role
computes with; their SKILL.md files and scripts are the field-level
reference, and each standards-map entry above marks the ARINC family as
summary-only.

The assessment and loading templates in `templates/` are original
structures informed by common-knowledge protocol summaries and the
leaf logic files. No proprietary standard text is reproduced.
