# Spacecraft Mission and Subsystem Design Report

**Spacecraft:** Aurora-1 Earth Observation Microsatellite
**Mission:** 600 km circular sun-synchronous Earth observation microsatellite, 5-year design life, 10:30 LTDN.
**Status:** draft-for-review

## 1. Mission and orbit

- Orbit: circular, altitude 600.0 km, inclination 97.8 deg (sun-synchronous), e = 0.000.
- Orbit radius: 6978 km; period 96.7 min (5801 s); 14.9 orbits/day; circular velocity 7558 m/s.
- Launch: rideshare, direct injection; design life 5 years.

## 2. Transfer / maneuvers and delta-v budget

- Injection: direct insertion (rideshare, direct injection); no interplanetary C3 or launch-window constraint applies (LEO circular mission).
- Delta-v contributions (m/s):
  - Injection dispersion correction: 20.0
  - Orbit maintenance (drag, 5 yr): 15.0
  - Collision avoidance (2 maneuvers): 10.0
  - End-of-life disposal (perigee lowering): 141.7
- Disposal leg is a single retrograde burn lowering perigee from 600 km to 100 km (Hohmann half-transfer, 141.7 m/s).
- Nominal total delta-v: 186.7 m/s; budgeted with 15% margin: **214.8 m/s**.
- Propellant (Isp 220 s, Tsiolkovsky): **15.7 kg**; wet mass 165.7 kg (9.5% propellant fraction).

## 3. Environment

- Eclipse (worst case, beta = 0): shadow fraction 36.7%; eclipse time 35.5 min per orbit.
- Perturbations at 600 km SSO: J2 nodal precession used for the sun-synchronous plane; drag is the long-term orbit maintenance driver (budgeted above); three-body effects negligible at this altitude.
- Radiation/debris: 600 km SSO sits in the inner belt proton/electron environment; parts list to a 25-50 krad(Si) total dose class (ECSS-Q-ST-60-15C practice); conjunction screening budgeted as 2 avoidance maneuvers over life.

## 4. ADCS

- Determination: star tracker (knowledge ~5 arcsec 1-sigma), sun sensors, 3-axis rate gyro, magnetometer; TRIAD/QUEST batch solutions on the C&DH.
- Control: 3 orthogonal wheels + 1 redundant reaction wheels, momentum capacity **1.0 N m s** each at 6000 rpm (wheel inertia 1.59 x 1e-3 kg m^2, h = J*omega); torque class 0.02 N m; magnetorquers for momentum desaturation.
- Sizing: slew 90 deg in 90 s -> slew momentum 0.349 N m s (J = 20 kg m^2 x omega 17.5 x 1e-3 rad/s); disturbance accumulation 0.0348 N m s/orbit; required with margin 0.58 N m s < capacity 1.0 N m s.
- Pointing error budget (3-sigma RSS): **0.048 deg** vs requirement 0.1 deg (margin x 2.1, meets).
  - attitude determination (star tracker): 0.020 deg
  - control error (deadband + PD residual): 0.030 deg
  - wheel-induced jitter: 0.020 deg
  - sensor/actuator alignment: 0.020 deg
  - thermal distortion: 0.015 deg

## 5. Power and thermal

| Item | Day power (W) | Eclipse power (W) |
|---|---|---|
| Payload (optical imager) | 60 | 0 |
| Avionics / C&DH | 30 | 30 |
| ADCS | 15 | 15 |
| Comms (S-band Rx + X-band Tx duty) | 20 | 10 |
| Thermal (heater duty) | 15 | 25 |
| **Total** | **140** | **80** |

- Orbit-average load: 118.0 W over a 96.7 min orbit (36.7% eclipse).
- Battery: 80 W x 35.5 min eclipse at 30% DoD / 90% efficiency requires **175.2 Wh**; sized **215 Wh** Li-ion (margin 23%).
- Solar array: daylight power 248.5 W; EOL specific power 315.1 W/m^2 (AM0 1367 W/m^2, 30% cells, packing 0.85, 2%/yr x 5 yr) -> array area **0.79 m^2**.
- Thermal balance: 55 W continuous dissipation rejected by a radiator at 20 deg C (eps 0.90) -> **0.15 m^2**; eclipse heater duty 25 W is in the load table.

## 6. Comms

- Slant range at 5 deg elevation: 2329 km.
- Downlink (X-band 8.2 GHz, 150 Mbps): EIRP 31.0 dBW, path loss 178.1 dB, C/N0 98.8 dB-Hz, Eb/N0 17.0 dB vs 10.5 dB required -> **margin 6.5 dB**.
- Uplink (S-band 2.1 GHz, 4 kbps command): **margin 34.3 dB**.
- Data: 11.2 GB per 10 min pass x 6 passes/day = **67.5 GB/day** capacity vs 30 GB/day imaging need (margin x 2.2); on-board storage 256 GB.

## 7. Propulsion and C&DH

- Propulsion: 15.7 kg hydrazine (Isp 220 s) at 1008 kg/m^3 -> 15.6 L propellant, 16.6 L spherical Ti tank (radius 15.8 cm, wall 0.33 mm, shell 0.51 kg, pressurant 3.9 g He); 4 x 1 N thrusters.
- C&DH: single rad-tolerant computer (LEON-class) with watchdog + triple-redundant command path; ECSS-E-ST-40 / ECSS-Q-ST-80 software and product assurance context; on-board storage solid-state recorder with EDAC.

## 8. System budgets

| Budget | Value | Margin policy | Closes |
|---|---|---|---|
| mass (dry) | 150 kg (subsystems sum to stated 150 kg) | 20% at subsystem level in stated rows | YES |
| mass (wet) | 165.7 kg | propellant on top of dry budget | YES |
| power | 140 W day / 80 W eclipse | battery 23%, array 20% | YES |
| delta-v | 186.7 m/s nominal / 214.8 m/s budgeted | 15% | YES |
| pointing | 0.048 deg (3-sigma) | vs 0.1 deg requirement | YES |
| link margin | down 6.5 dB / up 34.3 dB | >= 3 dB | YES |

## 9. Conclusions and open items

- Budgets close? **YES - all budgets close** (delta-v True, power True, pointing True, link True, mass True).
- Open items for detailed phase: refined disturbance torque model with beta-angle profile; flight-like array incidence/cosine losses; thermal model with component-level margins; star tracker alignment campaign; launch-vehicle interface agreement and actual dispersion.

---
*Generated by Aero Agent Roles space-systems-engineer core (2026-09-05). DRAFT for human space systems lead review. Not launch readiness. Not an approval document.*