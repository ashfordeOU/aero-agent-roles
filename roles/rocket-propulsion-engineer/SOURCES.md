# SOURCES.md - Rocket Propulsion Engineer

Standards and documents this role references. Summary-not-copy: see
[STANDARDS.md](../../STANDARDS.md) for the full rule and purchase links.

| Source | Role use | Gated |
|---|---|---|
| ECSS space-systems engineering standards (E-ST series) | framing context for rocket propulsion engineering; reference-only | true |
| Aero Agent Skills propulsion/rocket leaves (14) | the domain rules the core implements: rocket equation, staging, gravity loss, engine cycles, chamber/nozzle/cooling/injector/TVC, solid/hybrid/cold-gas ballistics | false |

The propulsion relations encoded in `core/rocket_propulsion_core.py`
are standard engineering methodology as carried by the bound Aero
Agent Skills logic files (isentropic compressible flow, ideal rocket
equation, Vieille burn-rate law, Bartz and Dittus-Boelter heat
transfer, pump/turbine power balance). Reference-typical propellant,
gas-property and channel-geometry values are documented assumptions in
the report, never vendor data. No proprietary standard text is
reproduced; summaries and original structures only.
