# SOURCES.md - Aircraft Systems Sizing Engineer

Standards and documents this role references. Summary-not-copy: see
[STANDARDS.md](../../STANDARDS.md) for the full rule and purchase links.

| Source | Role use | Gated |
|---|---|---|
| FAA FAR 25 (eCFR, public domain) | Subpart F systems sizing context: 25.1355 electrical system essential-load margin, 25.1001 fuel jettison 15-minute landing-weight limit, 25.365 pressurized-cabin loads (ultimate 1.33 factor paraphrase) | false |
| EASA CS-25 | Same Subpart F context for EASA-basis programs | false |
| AeroSkills vehicle-design/sizing leaves (14 bound) | The executable formulas this role's core mirrors: each leaf's scripts/*_logic.py encodes the sizing method (load rollup, ACM thermodynamics, choked-flow valve area, NPSH, Euler buckling, ISA atmosphere, class-I tire fits) | n/a |
| SAE ARP4754A | Development assurance context for the systems being sized (shared with systems safety) | true |

The report and templates in `templates/` are original structures
informed by public-domain regulation context (FAR/CS-25) and the bound
AeroSkills leaf methods. No proprietary text is reproduced; the sizing
methods are the common engineering practice encoded in the role's own
AeroSkills library.
