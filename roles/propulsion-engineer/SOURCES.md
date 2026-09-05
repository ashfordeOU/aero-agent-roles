# SOURCES.md - Propulsion Engineer

| Source | Role use | Gated |
|---|---|---|
| 14 CFR Part 33 | engine certification context | false |
| Mattingly, Aircraft Engine Design | cycle analysis methodology (book) | true |
| Hill & Peterson, Mechanics and Thermodynamics of Propulsion | propulsion fundamentals (book) | true |
| Sutton, Rocket Propulsion Elements | rocket propulsion reference (book) | true |
| NASA CEA documentation | equilibrium combustion tooling | false |
| AeroSkills propulsion leaves (gas-turbine-cycle, real-cycle-effects, turbofan-cycle, bypass-ratio-trade, turbofan-off-design, compressor-map, propelling-nozzle, rocket-engine-cycle, nozzle-design) | domain rules and reference-typical values encoded in core/propulsion_core.py: Brayton/real-cycle relations and anchors, choked-flow and area-Mach relations, standard-day corrections, surge-margin definitions, throttle bands, rocket propellant table (LOX/RP-1, LOX/LH2, N2O4/MMH, hydrazine) and feed-cycle chamber-pressure bounds | false (offline mirrors) |

Summary-not-copy per STANDARDS.md. The core encodes the *relations*
(summary of common propulsion methodology) with reference-typical
values used in the bound leaves; no leaf script is imported and no
proprietary text is reproduced.
