# SOURCES.md - Boundary-Layer Engineer

Standards and documents this role references. Summary-not-copy: see
[STANDARDS.md](../../STANDARDS.md) for the full rule and purchase links.

| Source | Role use | Gated |
|---|---|---|
| NACA TR-824 | framing context for the classical boundary-layer family; reference-only | true |
| Aero Agent Skills aerodynamics/boundary-layer leaves (10) | the domain rules the core implements: Blasius similarity solution, Thwaites integral relation, the Michel and Stratford criteria, the Squire-Young trailing-edge drag mapping, the Mangler 1948 axisymmetric transform, the Stokes 1851 creeping-flow solution and the Stokes first/second unsteady problems | false |

The boundary-layer relations encoded in
`core/boundary_layer_engineer_core.py` are standard engineering
methodology as carried by the bound Aero Agent Skills logic files:
Blasius (1908) flat-plate similarity thicknesses and skin friction,
the 1/7-power turbulent correlation, the Thwaites (1949) integral
momentum-thickness relation, the Michel (1952) natural-transition
criterion and the Stratford turbulent-recovery criterion, the
Squire and Young (ARC R&M 1838, 1938) trailing-edge profile-drag
mapping (as validated by Coder and Maughmer, Journal of Aircraft
52(3), 2015), the Mangler (1948) axisymmetric-body transform, the
Goldstein (1933) laminar far-wake similarity solution, the Stokes
(1851) creeping-flow sphere solution with the Oseen first-order
correction, and the classical Stokes first- and second-problem
unsteady laminar layers, all as presented in Schlichting
*Boundary-Layer Theory* and White *Viscous Fluid Flow*. Reference-
typical geometry, roughness and oscillation values (the wing edge-
velocity ramp, the fuselage cone angle, the strut chord, the surface
finish height and the oscillation frequency/amplitude) are documented
assumptions in the report, never vendor or proprietary data. No
proprietary standard text is reproduced; summaries and original
structures only.
