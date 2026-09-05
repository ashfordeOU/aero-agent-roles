# SOURCES.md - High-Speed Aerodynamics Engineer

| Source | Role use | Gated |
|---|---|---|
| NACA TR-824 | compressible-flow relations data source (reference-only) | true |
| Anderson, Modern Compressible Flow (textbook) | shock/expansion anchors (M2: p2/p1 4.5, oblique (M2,10deg) example) | true |
| Korn rule (supercritical airfoil practice) | drag-divergence Mach estimate | false |
| Whitcomb area rule / Sears-Haack (NACA Report 1273) | zero-lift wave drag estimate | false |
| Blasius / Schlichting flat-plate boundary layer | laminar/turbulent thickness and skin friction | false |
| Michel transition criterion / Thwaites method | transition location estimate | false |
| Sutton-Graves stagnation heating correlation | stagnation-point heat flux screen | false |
| Billig bow-shock standoff correlations | nose standoff estimate | false |
| ISA standard atmosphere | flight-condition state | false |

Summary-not-copy per STANDARDS.md. Data references cite sources, never
reproduce them. All numbers in the memo are engineering estimates
from these methods - screening inputs, not CFD/wind-tunnel results and
never an approval.
