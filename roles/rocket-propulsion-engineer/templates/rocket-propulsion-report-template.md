# Rocket Propulsion System Design Report

**Item:** Meridian-9 two-stage liquid propulsion system
**Program:** Meridian-9 medium launch vehicle
**Certification basis:** ECSS space-systems standards (reference-only)
**Status:** draft-for-review

## 1. Mission requirements

Two-stage LOX/RP-1 + LOX/LH2 launch vehicle delivering 5000 kg to low Earth orbit.
- Payload to low Earth orbit: 5000 kg.
- Net orbit-insertion delta-v target: 7800 m/s.
- Total ideal delta-v budget (incl. first-stage ascent losses): 9600 m/s.

## 2. Propellant screening

Reference-typical density impulse (Isp x bulk density, kg s/m3) ranks the candidate pairs on tank volume:

| Pair | Isp vac (s) | Bulk density (kg/m3) | Density impulse (kg s/m3) |
|---|---|---|---|
| LOX/RP-1 | 300 | 1027 | 308214 |
| LOX/LH2 | 430 | 344 | 147813 |
| N2O4/MMH | 320 | 1185 | 379285 |

- LOX family on a booster mission: **suitable**; LOX family on upper-stage duty: **suitable**.
- RP-1 (kerosene) family: **storable** - dense, storable at ambient temperature.
- Selection: LOX/RP-1 booster + LOX/LH2 upper stage (detailed in sections 5, 6, 10).

## 3. Staging and sizing

The ideal budget 9600 m/s is split 5700 m/s (booster) / 3900 m/s (upper). Equal-stage benchmark (identical stages, Isp 300 s, structural index 0.10): optimal per-stage mass ratio 5.1118, per-stage payload fraction 0.10625, total payload fraction 0.01129; minimum identical-stage count for a 1% total payload fraction: 2 stage(s).

| Quantity | Booster (S1) | Upper (S2) |
|---|---|---|
| Propellant pair | LOX/RP-1 | LOX/LH2 |
| Vacuum Isp (s) | 300 | 430 |
| Ideal delta-v (m/s) | 5700 | 3900 |
| Stage mass ratio | 6.941 | 2.522 |
| Payload fraction | 0.0490 | 0.3295 |
| Stage initial mass (kg) | 309860 | 15173 |
| Propellant mass (kg) | 265219 | 9155 |
| Inert mass (kg) | 29469 | 1017 |
| Structural index | 0.10 | 0.10 |

Upper-stage initial mass 15173 kg (incl. the 5000 kg payload) is the booster's payload; booster initial (liftoff) mass is 309860 kg.

## 4. Powered-ascent gravity-loss accounting (booster)

- Engine burn time: 190.1 s (propellant 265219 kg at 1395.3 kg/s).
- Liftoff thrust-to-weight: 1.23 (nominal sea-level thrust 3730 kN).
- Gravity loss (pitched ascent, mean flight-path angle 45 deg): 1318.1 m/s.
- Drag loss (reference): 150 m/s.
- Booster effective delta-v: 4231.9 m/s.
- Required total ideal delta-v for the 7800 m/s net target: 9268.1 m/s; allocated 9600 m/s (margin 331.9 m/s).

## 5. Booster engine feed cycle

Cycle: **gas-generator** on LOX/RP-1 at chamber pressure 10.00 MPa.
- Mass flow: 1395.3 kg/s total (1003.4 kg/s oxidizer, 391.9 kg/s fuel).
- Pump discharge pressure: 12.00 MPa; pump power 14.71 MW (ox) + 7.99 MW (fuel) = 22.70 MW.
- Turbine drive power: 27.68 MW (drive mass fraction 3%).
- Power balance: 4.98 MW (surplus).
- Verdict: gas-generator cycle feasible: total pump power 22.700 MW, turbine power 27.683 MW, surplus 4.983 MW, drive mass fraction 3%

Pressure-fed trade at the same thrust and burn time: tank mass penalty 3249 kg at tank pressure 5.00 MPa - pressure-fed cycle feasible at p_c 3.00 MPa: tank pressure 5.00 MPa, tank mass penalty 3249 kg for the 190 s burn basis.

## 6. Booster thrust chamber design

- Theoretical c*: 1776.1 m/s (Tc 3670 K, Mw 23 kg/kmol, gamma 1.20).
- Delivered c*: 1749.4 m/s (efficiency 0.985).
- Throat area: 2441.0 cm2 (diameter 557 mm).
- Chamber area: 8543 cm2 (diameter 1.04 m), contraction ratio 3.5.
- Chamber volume (L* = 1.0 m): 0.244 m3.

## 7. Booster nozzle design and flow separation

- Exit/throat area ratio: 16 (exit Mach 3.60).
- Exit static pressure: 67.7 kPa; exit area 3.91 m2.
- Ideal exit velocity: 2999 m/s.
- Ideal thrust: 4449 kN vacuum / 4054 kN sea level; nominal design 4105 kN (nozzle efficiency 0.923).
- Nominal Isp: 300.0 s vacuum / 272.6 s sea level.
- Expansion at sea level: **over** (exit pressure below ambient).
- Flow-separation station area ratio at sea level: 23.8 vs design 16 -> attached at ignition.
- Side-load advisory: attached at this ambient pressure: no separation side-load flag

## 8. Booster thrust-chamber cooling

Throat thermal balance (Bartz hot-gas side, Dittus-Boelter coolant side, series copper wall):
- Recovery temperature: 3635.4 K (throat static 3336.4 K).
- Hot-gas coefficient h_g: 10931 W/(m2 K); coolant coefficient h_c: 10391 W/(m2 K) (Re 10909, Nu 159.9).
- Heat flux: 17.41 MW/m2; hot wall 2043 K, cold wall 1976 K, wall drop 67.0 K.
- Copper wall limit 800 K: film-cooling handoff **REQUIRED**.
- Coolant mass flux to hold the limit: 157242 kg/(m2 s) vs the 12000 kg/(m2 s) reference channel flow.

## 9. Injector and thrust-vector control

Injector (unlike-doublet elements): layout of 1728 elements, injection velocity 79.0 m/s (fuel) / 67.0 m/s (oxidizer), momentum flux ratio 1.00, 1338 fuel orifices, 3455 oxidizer orifices.

TVC: gimbal deflection 5 deg at 4105 kN nominal thrust gives side force 358 kN and control torque 1073 kN m (moment arm 3.0 m); actuator authority 358 kN; axial thrust retained 99.6%.

## 10. Upper-stage propulsion

Cycle: **staged-combustion** on LOX/LH2 at chamber pressure 12.00 MPa.
- Mass flow: 71.1 kg/s total (60.2 kg/s oxidizer, 10.9 kg/s fuel); nominal vacuum thrust 300 kN.
- Pump power 4.05 MW, turbine power 54.05 MW, balance 50.00 MW.
- Verdict: staged-combustion cycle feasible: total pump power 4.051 MW, turbine power 54.052 MW, surplus 50.002 MW, drive mass fraction 100%

Cold-gas RCS (nitrogen, 25.00 MPa plenum, 1.00 mm throat, 60 s): per-thruster thrust 26.5 N, initial flow 45.1 g/s, tank gas 33.69 kg, blowdown time constant 748 s, operating time to 1.00 MPa: 2407 s, total impulse 19032 N s.

## 11. Alternate booster concepts (solid and hybrid screening)

Solid booster for the same booster duty (Isp 265 s, Vieille burn rate r = a p^n with a = 2.0e-05 m/s per Pa^n, n = 0.35):
- Equilibrium chamber pressure: 7.25 MPa at Kn = 500 (burn area 180.5 m2, throat 3611 cm2).
- Burn rate: 5.04 mm/s; mass flow 1637.0 kg/s (choked-flow / surface generation balance closed).
- Thrust 4254 kN, propellant 311162 kg, web 958 mm, total impulse 808.6 MN s.

Hybrid (HTPB-N2O) screened on the upper-stage burn duty: oxidizer flow 42.7 kg/s through a 0.25 m port (flux 217 kg/(m2 s)), regression rate 1.86 mm/s, fuel flow 4.8 kg/s, O/F 8.83, chamber pressure 5.00 MPa.

## 12. Performance summary

| Quantity | Value |
|---|---|
| Payload to LEO | 5000 kg |
| Liftoff mass | 309860 kg |
| Total ideal delta-v | 9600 m/s |
| Net insertion delta-v target | 7800 m/s |
| Booster mass ratio | 6.941 |
| Upper-stage mass ratio | 2.522 |
| Booster propellant flow | 1395.3 kg/s |
| Upper propellant flow | 71.1 kg/s |
| Booster total impulse | 780.3 MN s |
| Upper total impulse | 108.0 MN s |

## 13. Open items for human review

- Booster chamber and nozzle hot-side properties are reference-typical values; confirm with the program combustion model before release.
- Staging split and ascent-loss inputs (mean flight-path angle, drag loss) are stated design assumptions for the reference trajectory.
- The staged-combustion balance above uses reference-typical drive-gas properties (gas-generator table values) for the turbine model; re-derive the upper-stage preburner outlet state with the program cycle code before release.

---
*Generated by Aero Agent Roles rocket-propulsion-engineer core (2026-09-06). DRAFT for human rocket propulsion engineering review. Not an approval document and not a launch readiness decision.*
