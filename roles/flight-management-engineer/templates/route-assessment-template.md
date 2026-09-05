# Flight Plan and RNAV/RNP Route Assessment

**Route:** AERO ROUTE R1 (illustrative - not a filed plan)
**Aircraft:** Mid-size transport (illustrative example)
**Cruise level:** FL350 (illustrative profile)
**Status:** draft-for-review

## 1. Route structure and track distance

The assessed route contains 5 waypoints and 4 legs. Waypoints are illustrative identifiers with coordinates; the route is a synthetic example for the role deliverable, not a published navigation database procedure.

| Waypoint | Latitude | Longitude | Role |
|---|---|---|---|
| W001 | 41.0000 N | 75.0000 W | route origin / start of RNP segment |
| W002 | 40.0000 N | 74.5000 W | RF leg entry fix |
| W003 | 39.7418 N | 74.6499 W | derived: RF leg exit fix (computed) |
| HOLDF | 38.7418 N | 74.6499 W | derived: holding fix (computed from W003) |
| W005 | 38.0000 N | 75.0000 W | RTA fix / VNAV crossing constraint |

| Leg | Type | From | To | Track (deg)* | Distance (NM) |
|---|---|---|---|---|---|
*TF legs: initial great-circle track. RF leg: exit track after the turn (the value shown is the flight tangent at the exit fix).*

| 1 | TF (great-circle) | W001 | W002 | 159.0 deg | 64.23 |
| 2 | RF (radius-to-fix) | W002 | W003 | 249.0 deg | 18.85 |
| 3 | TF (great-circle) | W003 | HOLDF | 180.0 deg | 60.04 |
| 4 | TF (great-circle) | HOLDF | W005 | 200.4 deg | 47.49 |

Total track distance: **190.61 NM**.

Leg 1 track-distance method check (rhumb line vs great circle): rhumb 64.233 NM, great-circle 64.233 NM, difference 0.2 m (0.000 %), rhumb course 159.2 deg. Great-circle tracks are used for the TF legs.

## 2. Radius-to-fix (RF) leg construction (leg 2)

The RF leg from W002 turns RIGHT at radius 12.0 NM with the published swept angle 90.0 deg. Entry fix is the origin of the leg local tangent frame (x = east, y = north, NM).

- Turn centre (local NM): (-11.204, -4.296)
- Exit fix (local NM): (-6.908, -15.501)  (on radius circle: True)
- Swept angle: 90.0 deg; arc length: 18.85 NM
- Exit track: 249.0 deg; chord: 16.97 NM
- RF leg valid: True

## 3. RNP containment on the RNP segment

Segment: W002 - HOLDF - W005 (en-route/arrival RNAV portion)
- Required navigation performance (RNP): 0.3 NM = 555.6 m
- Lateral 1-sigma position error input: 200 m
- Actual navigation performance (ANP), 95% containment (2 x sigma): 400.0 m (0.2160 NM)
- Required margin (10 % of RNP): 55.6 m
- Containment check (ANP + margin <= RNP): **PASS** - margin available 100.0 m

## 4. Holding pattern entry at HOLDF

Approach track at the holding fix: 180.0 deg (leg 3, due-south meridian). Hold inbound course 260.0 deg, right turns. Approach angle alpha to the holding axis: 80.0 deg (sector rule: direct <= 70 deg, teardrop 70 < alpha <= 110 deg, parallel > 110 deg).

- Entry type: **teardrop**
- Outbound leg timing at FL200 (20000 ft): 90 s
- Outbound heading 80.0 deg, wind 40.0 deg/30 kt, TAS 260 kt: 1-in-60 corrected heading **75.55 deg**
- First (entry) lap estimate: 330 s

## 5. RTA time control at W005

RTA evaluated from the HOLDF exit, 47.5 NM before W005, slot demand 25 s later than the nominal arrival.
- Current ground speed: 240.0 m/s; nominal ETA: 366.5 s; RTA time error: -25.0 s
- Required ground speed: 224.7 m/s; required Mach: 0.7267
- Commanded Mach: **0.7267**; verdict: **rta-feasible** (feasible: True)
- Achievable window at 20000 ft: [346 s, 407 s] (61 s wide)

## 6. Performance and vertical (VNAV) profile

ECON cruise at FL350, cost index 30 kg/h, weight 62000 kg:
- ECON Mach: **0.7723** (TAS 445.2 kt, fuel 5.323 kg/NM); envelope [0.70, 0.82] Mach; max-range reference (CI 0): Mach 0.7706, fuel 5.323 kg/NM

Vertical path: descend FL350 -> FL200 on a 3.0 deg flight path (318.4 ft/NM) to cross HOLDF AT FL200, then continue toward W005 (constraint AT 6000 ft).
- Top of descent (air): 47.1 NM before HOLDF; with 15 kt headwind at 450 kt TAS: 48.7 NM ground distance, starting 11.3 NM inside leg 3 (60.04 NM) - no path conflict.
- Crossing altitude at W005 continuing the 3.0 deg path: 4877 ft vs constraint AT 6000 ft: **FAIL**
- Gradient required to comply: 295 ft/NM (2.78 deg)
- Vertical band checks: cruise FL350 within band: PASS; HOLDF crossing FL200 within band: PASS

## 7. DME arc and radio navaid geometry checks

Published arc transition check: radius 15 NM from the arc navaid between radials 30 and 90:
- Arc length: 15.71 NM; chord: 15.00 NM; turn angle: 60.0 deg
- Bank angle to hold the arc at 250 kt TAS: 3.47 deg; turn radius at 25 deg bank: 1.95 NM
- DME slant range at 15 NM ground range, FL200: 28441 m (planar ground range 27780 m); arc start point bearing 30.0 deg, reciprocal radial 210.0 deg

## 8. Findings and recommendations

- **[FINDING]** W005 crossing constraint not met on the planned 3.0 deg path - Continuing the 3.0 deg descent path from the FL200 hold crossing reaches W005 at 4877 ft, below the AT 6000 ft constraint by 1123 ft. Replan the arrival profile: the descent leg from the hold to W005 requires a gradient no steeper than 295 ft/NM (2.78 deg).

Recommendation: resolve every [FINDING] before the route is offered for operational dispatch review. Numerical values in this assessment are computed by the role core from the stated route facts and the bound flight-management logic leaves.

---
*Generated by Aero Agent Roles flight-management-engineer core (2026-09-05). DRAFT for human flight operations / dispatch review. This document is not a clearance, not a filed flight plan, and not an approval; the operator and the flight crew retain all operational decision authority.*
