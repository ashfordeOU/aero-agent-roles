# SOURCES.md - Flight Mechanics Engineer

Summary-not-copy per STANDARDS.md. The core (core/flight_mechanics_core.py)
encodes the equations of the bound AeroSkills leaves below (paraphrase of
common flight-mechanics practice); every number in the generated report
traces to one of these rules or to the stated example input basis.

## Standards / regulations referenced (context, quotable with citation)

| Source | Role use | Gated |
|---|---|---|
| 14 CFR Part 25 (FAR/CS 25.121, 25.125, 25.181) | minimum climb gradients; landing field length factor; dynamic stability context | true (gradients, landing factor, heavy-damping context) |
| MIL-STD-1797A | flying qualities levels, mode criteria tables (summary paraphrase) | true (level bands used by the gates) |
| MIL-F-8785C style level-1 bands (as summarized by the short-period leaf) | short-period damping/frequency bands | true |
| ISA atmosphere (public standard model) | density/temperature/speed of sound at altitude | false |

## Bound AeroSkills leaves whose rules the core encodes

| Leaf (rule the core encodes) | Role use | Gated |
|---|---|---|
| flight-mechanics/performance/breguet-range | R = (V/(TSFC*g))*(L/D)*ln(m0/m1) | true |
| flight-mechanics/performance/breguet-endurance | jet loiter endurance | true |
| flight-mechanics/performance/specific-range | SAR = V*(L/D)/(TSFC*W) | false |
| flight-mechanics/performance/climb-performance | ROC=(T-D)V/W; gradient; time to climb; service ceiling | true |
| flight-mechanics/performance/takeoff-performance | Vs, V_LOF=1.2*Vs, ground roll | true |
| flight-mechanics/performance/landing-performance | Vref=1.3*Vs, air distance, ground roll, 1.67 factor | true |
| flight-mechanics/performance/glide-performance | glide ratio/angle/sink | false |
| flight-mechanics/performance/turn-performance | n=1/cos(phi), rate, radius | false |
| flight-mechanics/performance/oei-climb-gradient | T_oei derate; FAR 25.121 gradients | true |
| flight-mechanics/performance/energy-height | h_e, kinetic height, Ps | false |
| flight-mechanics/performance/wind-effects | wind triangle/groundspeed | false |
| flight-mechanics/stability-control/longitudinal-stability | neutral point, static margin | true |
| flight-mechanics/stability-control/dynamic-stability | short period/phugoid/lateral mode formulas, criteria | true |
| flight-mechanics/stability-control/short-period-mode-analysis | SP frequency/damping, level bands | true |
| flight-mechanics/stability-control/phugoid-mode-analysis | Lanchester phugoid characteristics | true |
| flight-mechanics/stability-control/lateral-directional-stability | fin/dihedral derivative build, DR/roll/spiral | true |
| flight-mechanics/stability-control/trim-analysis | CL_trim, elevator to trim | false |
| flight-mechanics/handling-qualities/mil-std-1797a | category/class/level mode criteria tables | true |
| flight-mechanics/handling-qualities/cooper-harper-rating | HQR decision tree (flight-test campaign) | false |

## Reference books (method context for the derivative builds)

| Source | Role use | Gated |
|---|---|---|
| Stevens & Lewis, Aircraft Control and Simulation | dynamics/derivative conventions | false |
| Roskam, Airplane Flight Dynamics | S&C methods, class-range derivative data | false |

Example-configuration data (mass, geometry, thrust, polar, derivative
coefficients) are stated per-run inputs in the class range of a 150-seat
twin-engine transport and are flagged in the report as open items pending
project data and the AVL derivative build.
