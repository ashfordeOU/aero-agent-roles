# Concept Design Package - RegionalJet-1500 (100 pax / 1500 nm / M0.78)

**Document type:** Concept Design Package  
**Status:** draft-for-review  
**Aircraft class:** transport (class-I conceptual sizing)
**Generated:** 2026-09-05

## 1. Requirements and design space

| Requirement | Value |
|---|---|
| Passengers | 100 pax |
| Payload | 20,000 lb (100 pax x 200 lb + baggage, class-I) |
| Design range | 1,500 nm |
| Cruise | M0.78 at 10,668 m (FL350), 450 kt TAS |
| Takeoff field length | 1,829 m (6,001 ft) |
| Engines | 2 turbofans |

Constraint diagram (matching chart, T/W vs W/S; SI inputs, sea-level ISA for takeoff, cruise at FL350):

| Constraint | Rule | Value at design W/S |
|---|---|---|
| Stall (max W/S) | W/S = 0.5*rho*CLmax*VS^2 | 5,512 N/m^2 (115.1 psf) |
| Takeoff | T/W = 1.21*(W/S)/(rho*g*CLmax*s_TO) | 0.1404 |
| Climb | T/W = 1/LD + gamma (OEI -> installed, x n/(n-1)) | 0.2147 |
| Cruise | T/W = q*CD0/(W/S) + k*(W/S)/q | 0.0569 |

**Selected design point:** W/S = 5,100 N/m^2 (106.5 psf), T/W = 0.2147 (binding constraint: climb).
**Feasible:** True - the point lies on the lower bound of the feasible region (stall limit not exceeded).
Feasible-region boundary samples (W/S N/m^2 -> minimum T/W): 1,378 -> 0.2147, 1,895 -> 0.2147, 2,412 -> 0.2147, 2,929 -> 0.2147, 3,445 -> 0.2147, 3,962 -> 0.2147, 4,479 -> 0.2147, 4,996 -> 0.2147, 5,512 -> 0.2147.

## 2. Sizing mission

Mission profile (segments in flight order; each burns from the weight remaining after earlier segments, Breguet range/endurance models):

| Segment | Fuel burned | Fraction of MTOW |
|---|---|---|
| Taxi | 300 lb | 0.2% of MTOW |
| Takeoff | 900 lb | 0.7% of MTOW |
| Climb | 6,000 lb | 5.0% of MTOW |
| Cruise (1,500 nm @ 450 kt) | 30,057 lb | 25.0% of MTOW |
| Descent | 750 lb | 0.6% of MTOW |

| **Block fuel** | **38,007 lb** | **31.6%** |
| Block time | 4.19 hr | |
| Landing weight | 82,292 lb | |
| Reserve (hold45_5pct: 45 min hold at 1500 ft + 5% trip) | 3,932 lb | |
| **Required fuel (mission + reserves)** | **41,939 lb** | **34.9% of MTOW** |

## 3. Configuration (from the design point)

- Wing loading W/S: 5,100 N/m^2 (106.5 psf) - design choice, 92.5% of the stall-limited maximum.
- Wing area S = W/(W/S) = 104.9 m^2 (1,129 ft^2); aspect ratio 9.5; span b = 31.6 m.
- Drag model: CD0 = 0.018, e = 0.80, k = 1/(pi*e*AR) = 0.0419; L/D_max = 18.2 (consistent with the mission cruise L/D of 18).
- Engines: 2 x ~12,912 lbf class sea-level static thrust (see Section 5).
- 3-view reference geometry from the OpenVSP stage (initial layout) feeds the class-II mass build-up; not required for the class-I sizing closure.

## 4. Mass statement (class-I, balances to converged MTOW)

| Group | Weight (lb) | % MTOW |
|---|---|---|
| Operating empty weight (class-I fit 0.485 x MTOW) | 58,345 | 48.5% |
| Design payload (100 pax x 200 lb + cargo) | 20,000 | 16.6% |
| Fuel (mission + reserves, hold45_5pct) | 41,939 | 34.9% |
| **Maximum takeoff weight (converged)** | **120,298** | **100.0%** |

- Balance check (empty + payload + fuel vs MTOW): PASS within 1%.
- Empty-weight fraction 0.485 inside the transport class-I band 0.42-0.55: PASS.
- Weight-growth context: conceptual phase growth allowance 10% applies to the detailed mass budget roll-up (mass-budget stage).
- CG envelope and critical loading conditions require the 3-view layout and the mass-properties stage (component arms); the class-I closure above bounds the balance (fuel + payload = 61,939 lb available below MTOW - OEW = 61,954 lb).

## 5. MTOW convergence and engine size check

Fuel-fraction sizing iteration (W0 = payload / (1 - W_e/W0 - W_f/W0), class-I empty fraction 0.485):

| Iteration | Guess (lb) | Fuel fraction | New MTOW (lb) | Rel. change |
|---|---|---|---|---|
| 1 | 100,000 | 0.3591 | 128,259 | 28.26% |
| 2 | 128,259 | 0.3454 | 117,944 | 8.04% |
| 3 | 117,944 | 0.3496 | 120,955 | 2.55% |
| 4 | 120,955 | 0.3483 | 120,007 | 0.78% |
| 5 | 120,007 | 0.3487 | 120,298 | 0.24% |

**Converged MTOW = 120,298 lb (54,566 kg)** after 5 iterations (tolerance 0.5%): CONVERGED.

- Installed sea-level thrust: 25,824 lbf total = 12,912 lbf per engine (T/W = 0.215).
- Engine weight estimate: ~2,582 lb per engine at engine T/W = 5.0 (4-6 typical band).
- Top-of-climb margin at 10,668 m (thrust lapse sigma^0.7 vs W/(L/D)): 1.81 - PASS (>= 1.0).
- Engine-out second-segment gradient is carried on the installed basis: T/W = (n/(n-1)) x (1/LD + gamma) with LD = 12 and gamma = 0.024 (FAR 25.121(b)(1) two-engine value, 2 engines); the engine-sizing stage re-checks OEI climb, hot day, and takeoff derate against the catalogue engine.

## 6. Feasibility notes and next stages

- Class-I results are FEASIBILITY, not detailed design: the converged MTOW, the W/S-T/W design point, and the mass statement close the sizing loop within the stated class-I model accuracy.
- Structure/propulsion/systems mass split requires the class-II component build-up (weight-estimation, engine-sizing, fuselage/wing/tail-sizing leaves); the conceptual growth allowance (10%) is the margin policy for that roll-up.
- Payload-range, cost (parametric DOC/LCC), and CG envelope are produced by the dedicated stages (payload-range-diagram, parametric-cost, cg-envelope) once the class-II breakdown exists.

---

*DRAFT - conceptual feasibility for human design review. Not a production release and not an approval document. Conceptual results are class-I estimates; every configuration choice must trace to the trade data before detailed design.*