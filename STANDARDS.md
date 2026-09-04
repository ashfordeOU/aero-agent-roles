# Aero Agent Roles Standards Reference (STANDARDS.md)

Every role references standards from the aerospace regulatory and
quality ecosystem. This file is the human-readable companion to the
per-role `SOURCES.md` files (which record what each role references).

## The summary-not-copy rule

The only allowed way to reference any mapped standard is
**summary-not-copy**: name + paraphrase + short attributed quotes
(<100 words) + link to the publisher's official channel. Never reproduce
objective tables, appendix text, or multi-line verbatim blocks; never
include standards PDFs; never include material from illegally hosted
copies.

`gated: true` means **verbatim text from that standard must NEVER appear
anywhere in this repository** - a role that references a gated standard
lists it as `reference-only`. `gated: false` means the text is quotable
with attribution (paraphrase still preferred).

The standards themselves remain the copyrighted works of their publishers
(RTCA/EUROCAE, SAE International, IAQG, EASA, FAA) and must be purchased
or accessed through the publishers' official channels.

## Standards referenced

| id | Standard | Publisher | Roles | Gated |
|---|---|---|---|---|
| do-178c | RTCA DO-178C / EUROCAE ED-12C, Software Considerations | RTCA/EUROCAE | do178c-cert-engineer | true |
| do-330 | RTCA DO-330, Software Tool Qualification | RTCA | do178c-cert-engineer | true |
| arp4754a | SAE ARP4754A, Development of Civil Aircraft and Systems | SAE | do178c, airworthiness | true |
| as9100 | AS9100D, Aerospace QMS Requirements | SAE/IAQG | as9100-quality-auditor | true |
| as9102 | AS9102, First Article Inspection | SAE/IAQG | as9100-quality-auditor | true |
| iso-19011 | ISO 19011, Auditing Management Systems | ISO | as9100-quality-auditor | true |
| iso-9001 | ISO 9001:2015, QMS Requirements | ISO | as9100-quality-auditor | true |
| far-21 | 14 CFR Part 21, Certification Procedures | FAA | airworthiness-compliance-engineer | false |
| far-25 | 14 CFR Part 25, Airworthiness Standards | FAA | airworthiness-compliance-engineer | false |
| cs-25 | EASA CS-25, Certification Specifications | EASA | airworthiness-compliance-engineer | false |
| amc-20-115 | EASA AMC 20-115C, Airborne Software | EASA | do178c-cert-engineer | false |
| ac-20-115 | FAA AC 20-115D, Airborne Software Assurance | FAA | do178c-cert-engineer | false |

## Purchase links

Standards are available from the publishers' official channels:
RTCA (rtca.org), SAE International (sae.org), IAQG (iaqg.org), ISO
(iso.org), FAA (ecfr.gov), EASA (easa.europa.eu).
