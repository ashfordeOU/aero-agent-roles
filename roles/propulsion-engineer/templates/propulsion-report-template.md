# Propulsion Design Report

**Item:** High-bypass turbofan for a 200-seat twin (design study)
**Vehicle / mission:** 200-seat twin-aisle-class transport, 2 wing-mounted engines - Subsonic transport cruise design point (M0.78, FL350)
**Engine class:** high-bypass turbofan (BPR 8, FPR 1.60, OPR 30, TIT 1650 K)
**Status:** draft-for-review
**Certification basis:** Design study in a FAR 33 engine-type context; no certification approval claimed

## 1. Requirement and selected cycle

- Thrust requirement (per engine, design point): 30.0 kN net at M0.78, 11 km ISA.
- Selected cycle: separate-stream turbofan with the fan on the low-pressure spool and the core compressor/turbine on the high-pressure spool. Rationale: high bypass ratio (8) lowers mean jet velocity and raises propulsive efficiency at a transonic cruise Mach; the OPR 30 / TIT 1650 K core delivers the cruise SFC of 0.541 lb/(lbf.h) computed below.
- Design airflow (total, matched to the requirement): 141.0 kg/s.

## 2. Cycle analysis (airbreathing)

On-design station state table (total temperature / total pressure, per kg/s inlet airflow basis; component efficiencies are stated inputs below):

| Station | Name | Tt (K) | Pt (kPa) |
|---|---|---|---|
| 2 | fan face | 245.4 | 35.5 |
| 13 | fan exit | 284.6 | 56.7 |
| 3 | compressor exit | 699.1 | 1063.7 |
| 4 | turbine inlet (TIT) | 1650.0 | 1010.5 |
| 5 | turbine exit | 996.2 | 97.5 |

Core nozzle (station 9): exit static 855 K / 52.7 kPa, jet velocity 565.6 m/s, Mach 1.000, choked, exit area 0.2936 m^2 (per engine).
Fan nozzle (station 19): exit static 237 K / 29.7 kPa, jet velocity 305.6 m/s, Mach 1.000, choked, exit area 1.1711 m^2 (per engine).

- Net thrust (per engine, design point): 30.0 kN = sum of m_dot*(V9 - V0) + (P9 - P0)*A9 over both streams.
- TSFC: 15.3 g/(kN.s)  (0.541 lb/(lbf.h)).
- Fuel/air ratio (core): 0.02937 (total basis 0.00326); fuel flow 0.460 kg/s per engine.
- Efficiencies: overall 0.349, thermal 0.412, propulsive 0.848 (kinetic-energy method over both streams); ideal Brayton at OPR 30: 0.622.

Input assumptions (stated): fan efficiency 0.90, core compressor efficiency 0.90, turbine 0.90, combustor 0.995 (pressure ratio 0.95), inlet recovery 0.995, fan-duct ratio 0.99, mechanical 0.99, nozzle velocity coefficient 0.99; fuel LHV 43.2 MJ/kg (kerosene class). Component maps and stage counts are representative input.

## 3. Off-design

Quick off-design model (turbofan-off-design leaf): corrected mass flow and turbine inlet temperature held at the design value; physical airflow scales by delta/sqrt(theta); net thrust is recomputed through the on-design cycle at each flight point.

| Point | Alt (km) | Mach | Throttle | Verdict | m_dot (kg/s) | F_net (kN) | TSFC g/(kN.s) | Surge clearance | Map verdict |
|---|---|---|---|---|---|---|---|---|---|
| SLS static | 0 | 0.00 | 1.00 | max-continuous | 370.1 | 111.5 | 9.7 | 15% | on-map |
| FL250 climb | 8 | 0.78 | 1.00 | max-continuous | 213.0 | 39.4 | 16.7 | 15% | on-map |
| FL350 design cruise | 11 | 0.78 | 1.00 | max-continuous | 141.0 | 30.0 | 15.3 | 15% | on-map |
| FL350 part power | 11 | 0.78 | 0.60 | cruise | 141.0 | 18.0 | 15.3 | 15% | on-map |
| FL390 top of cruise | 12 | 0.80 | 1.00 | max-continuous | 119.0 | 25.7 | 15.1 | 15% | on-map |

Surge clearance: representative core-compressor surge line set 115% above the operating line pressure ratio (34 vs OPR 30); the operating line clears surge at every envelope point (representative map input, not vendor data).

## 4. Component selection

| Component | Choice | Basis |
|---|---|---|
| Inlet | subsonic pitot, recovery 0.995 | cruise M0.78 |
| Fan | single stage, PR 1.60, eta 0.90 | Tt 285 K at design |
| Core compressor | multi-stage axial, PR 18.8 (OPR 30/fan 1.60) | Tt 699 K, representative map margin |
| Combustor | annular, eta 0.995, pressure ratio 0.95 | f/a 0.02937 |
| HP turbine | cooled (turbine-blade-cooling stage), eta 0.90 | Tt in 1650 K, Tt out 996 K |
| Core nozzle | convergent, choked at design | area 0.2936 m^2 |
| Fan nozzle | convergent, choked at design | area 1.1711 m^2 |

## 5. Integration

- Ram-drag bookkeeping (engine-airframe integration): net thrust above already subtracts the inlet momentum drag m_dot_0*V0 (= 32.6 kN at the design point).
- Installed performance: nacelle, pylon and bleed/accessory losses are NOT yet deducted; the uninstalled net thrust is 30.0 kN per engine.  Installation bookkeeping is a follow-on engine-airframe integration pass.

## 6. Rocket / space option (if applicable)

Not applicable to this airbreathing transport item - the engine selection is turbofan.  For a space item the rocket-engine-cycle and nozzle-design stages apply (see the rocket reference example in the core / cli build --engine rocket).

## 7. Electric option (if applicable)

Not applicable: no electric-propulsion role for a 30 kN cruise thrust requirement at M0.78.  Electric thrusters cover the low-thrust space regime (hall/gridded-ion), not airbreathing main propulsion.

## 8. Bypass-ratio trade and recommendation

First-order trade at fixed core conditions, fixed total mass flow and jet velocities held at the design-point values (bypass-ratio-trade leaf method):

| BPR | F/m_dot (N per kg/s) | TSFC g/(kN.s) | eta_o |
|---|---|---|---|
| 2 | 273.3 | 35.8 | 0.149 |
| 4 | 211.0 | 27.8 | 0.192 |
| 6 | 184.3 | 22.8 | 0.235 |
| 8 | 169.5 | 19.3 | 0.278 |
| 10 | 160.1 | 16.7 | 0.321 |
| 12 | 153.5 | 14.7 | 0.364 |

Raising BPR lowers specific thrust and TSFC by shifting flow to the fan stream (bypass-ratio-trade trend), at the cost of fan diameter and nacelle drag.  BPR 8 balances specific thrust with nacelle integration for a 200-seat twin; the design point above is the recommendation.  Open items: nacelle drag, turbine cooling flow, and the component map verification.

---
*Generated by Aero Agent Roles propulsion-engineer core (2026-09-05). DRAFT for human propulsion lead review. Not an approval document.*