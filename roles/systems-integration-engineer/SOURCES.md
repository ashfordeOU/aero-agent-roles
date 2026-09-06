# SOURCES.md - Systems Integration Engineer

Standards and documents this role references. Summary-not-copy: see
[STANDARDS.md](../../STANDARDS.md) for the full rule and purchase links.

| Source | Role use | Gated |
|---|---|---|
| SAE ARP4754A | system development assurance: FDAL/IDAL assignment, requirements allocation/traceability/validation, integration verification, configuration management, certification interface | true |
| SAE ARP4761A | failure-condition severity categorization (FHA framing) feeding the severity-to-DAL assignment; common-cause analysis for the independence alternative | true |
| RTCA DO-178C / ED-12C | downstream software planning context (software aspects of items this role assures) | true |
| RTCA DO-254 / ED-80 | downstream hardware planning context (hardware aspects of items this role assures) | true |
| FAA AC 20-174 | FAA recognition of ARP4754A as an acceptable means of compliance for development assurance (context) | false |

The plan template in `templates/` is an original structure informed by
public-domain guidance (AC 20-174) and summary process knowledge bound
from the AeroSkills ARP4754A leaves. SAE text is proprietary and is
never reproduced; the severity categories and the A..E assurance scale
are common development-assurance methodology summarized from the bound
leaves. Conservative defaults (e.g. the 0.95 validation closure
threshold, full vs baseline safety assessment depth) are project-defined
sanity bands documented in the bound leaf logic and confirmed against
the approved program plan.
