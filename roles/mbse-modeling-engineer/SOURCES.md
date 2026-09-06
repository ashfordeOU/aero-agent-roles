# SOURCES.md - MBSE Modeling Engineer

Standards and documents this role references. Summary-not-copy: see
[STANDARDS.md](../../STANDARDS.md) for the full rule and purchase links.

| Source | Role use | Gated |
|---|---|---|
| SAE ARP4754A | development process context: assurance levels, development planning, traceability expectations for the model | true |
| SAE ARP4761A | system safety assessment context behind FDAL determination (FHA/PSSA input) | true |
| OMG SysML v1.7 | diagram kinds and semantics (bdd, ibd, param, req, act, seq, stm, uc, pkg) - open specification | false |
| INCOSE Systems Engineering Handbook | MBSE method context, N2 chart interface analysis | false |
| FAA AC 25.1309-1B / EASA AMC 25.1309 | severity categories feeding development assurance level practice | false |

The plan templates and governance language in `templates/` are
original structures. Diagram-kind selection, requirement screening,
traceability roll-up, N2 counts, state-machine reachability, and
constraint evaluation mirror the executable logic of the bound MBSE
leaves in Aero Agent Skills (systems-engineering-safety/mbse/*), which
encode common modeling practice and reference ARP4754A summary-only.
No proprietary text is reproduced.
