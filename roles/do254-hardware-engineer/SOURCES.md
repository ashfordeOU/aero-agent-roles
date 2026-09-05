# SOURCES.md - DO-254 Airborne Electronic Hardware Engineer

Standards and documents this role references. Summary-not-copy: see
[STANDARDS.md](../../STANDARDS.md) for the full rule and purchase links.

| Source | Role use | Gated |
|---|---|---|
| RTCA DO-254 / EUROCAE ED-80 | design assurance of airborne electronic hardware: DAL, AEH classes, life cycle data, verification objectives | true |
| SAE ARP4754A | development assurance level derivation from failure conditions (shared with systems safety) | true |
| RTCA DO-178C | hardware/software integration boundary with hosted software | true |
| FAA AC 20-152A | FAA acceptance of DO-254 for AEH; simple vs complex guidance | false |

Bound AeroSkills leaves under `avionics/do254/` (hardware-planning,
requirements-capture, verification, configuration-management) encode
paraphrased common-knowledge summaries of DO-254 practice and are
dispatched for cross-check by `cli.py` when present. The PHAC template
in `templates/` is an original structure informed by public-domain
guidance (AC 20-152A) and summary process knowledge. No proprietary
text is reproduced.
