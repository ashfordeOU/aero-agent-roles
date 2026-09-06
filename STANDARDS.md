# Aero Agent Roles Standards Reference (STANDARDS.md)

Every role references standards from the aerospace regulatory and
quality ecosystem. This file is generated from every role's
`standards_bound` frontmatter (the same source `manifest.json` is
generated from) — a standard's row and `Roles`/`Gated` columns can
never silently drift from the tree again. Names and publishers below
are the only hand-maintained facts (external-world data); see
`STANDARD_META` in `scripts/gen_visuals.py` to add a new standard.

## The summary-not-copy rule

The only allowed way to reference any mapped standard is
**summary-not-copy**: name + paraphrase + short attributed quotes
(<100 words) + link to the publisher's official channel. Never reproduce
objective tables, appendix text, or multi-line verbatim blocks; never
include standards PDFs; never include material from illegally hosted
copies.

`Gated: true` means **verbatim text from that standard must NEVER appear
anywhere in this repository** - a role that references a gated standard
lists it as `reference-only`. `Gated: false` means the text is quotable
with attribution (paraphrase still preferred).

The standards themselves remain the copyrighted works of their publishers
(RTCA/EUROCAE, SAE International, IAQG, ASME, ECSS, EASA, FAA) and must
be purchased or accessed through the publishers' official channels.

## Standards referenced

| id | Standard | Publisher | Roles | Gated |
|---|---|---|---|---|
| ac-90-105a | FAA AC 90-105A, Approval Guidance for RNP Operations and Baro-VNAV | FAA | flight-management-engineer | False |
| arinc-429 | ARINC 429 (Mark 33 DITS) | ARINC / Aeronautical Radio Inc | data-bus-avionics-engineer | True |
| arinc-664 | ARINC 664 Part 7 (AFDX) | ARINC / Aeronautical Radio Inc | data-bus-avionics-engineer | True |
| arp4754a | SAE ARP4754A, Development of Civil Aircraft and Systems | SAE | do254-hardware-engineer, guidance-engineer, mbse-modeling-engineer, state-estimation-engineer, systems-integration-engineer | True |
| arp4761a | arp4761a | unknown — add to STANDARD_META | mbse-modeling-engineer, systems-integration-engineer | True |
| as9100 | AS9100D, Aerospace QMS Requirements | SAE / IAQG | as9100-quality-auditor, ndt-engineer | True |
| asme-vv-20 | ASME V&V 20-2009, Verification and Validation in CFD and Heat Transfer | ASME | numerical-analysis-engineer | True |
| asme-y14-5 | ASME Y14.5, Dimensioning and Tolerancing | ASME | engineering-analysis-engineer | True |
| cs-25 | EASA CS-25, Certification Specifications | EASA | airworthiness-compliance-engineer, flight-test-performance-engineer, guidance-engineer | False |
| do-160 | RTCA DO-160G / EUROCAE ED-14G, Environmental Conditions and Test Procedures for Airborne Equipment | RTCA/EUROCAE | do160-environmental-engineer | True |
| do-178c | RTCA DO-178C / EUROCAE ED-12C, Software Considerations in Airborne Systems | RTCA/EUROCAE | do178c-cert-engineer | True |
| do-236c | RTCA DO-236C, MASPS: RNP for Area Navigation | RTCA | flight-management-engineer | True |
| do-254 | RTCA DO-254 / EUROCAE ED-80, Design Assurance for Airborne Electronic Hardware | RTCA/EUROCAE | do254-hardware-engineer | True |
| do-283a | RTCA DO-283A, MOPS for RNP Area Navigation (RNP AR) | RTCA | flight-management-engineer | True |
| ecss | ECSS engineering + product-assurance standards (E-ST-10/32/33/40, Q-ST-80) | ECSS | space-systems-engineer | True |
| far-25 | 14 CFR Part 25, Airworthiness Standards: Transport Category Airplanes | FAA | aerodynamics-engineer, aircraft-design-engineer, airworthiness-compliance-engineer, flight-mechanics-engineer, flight-test-engineer, flight-test-performance-engineer, guidance-engineer, structures-loads-engineer | False |
| far-33 | 14 CFR Part 33, Airworthiness Standards: Aircraft Engines | FAA | propulsion-engineer | False |
| mil-std-1553 | MIL-STD-1553B, Digital Time Division Command/Response Multiplex Data Bus | US DoD | data-bus-avionics-engineer | False |
| mil-std-1797a | MIL-STD-1797A, Flying Qualities of Piloted Aircraft | US DoD | flight-mechanics-engineer, flight-test-engineer, gnc-engineer | False |
| mmpsd | MMPDS, Metallic Materials Properties Development and Standardization | Battelle / FAA | structures-loads-engineer | True |
| naca-tr-824 | NACA Report 824, Summary of Airfoil Data | NACA/NASA (public domain) | high-speed-aerodynamics-engineer | True |
| nas-410 | NAS 410, Certification and Qualification of Nondestructive Test Personnel | AIA/SAE | ndt-engineer | True |

## Purchase links

Standards are available from the publishers' official channels:
RTCA (rtca.org), SAE International (sae.org), IAQG (iaqg.org), ASME
(asme.org), ECSS (ecss.nl), FAA (ecfr.gov), EASA (easa.europa.eu).
