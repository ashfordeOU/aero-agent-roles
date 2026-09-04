# GNC Design Report Template (ORIGINAL skeleton)

Draft deliverable. Fill every section.

## 1. Architecture and plant
- Control architecture (inner/outer loops, guidance, nav): ___
- Plant model + frames + states/inputs/outputs: ___

## 2. Navigation
- Sensor suite + noise models: ___ · Filter architecture: ___
- Position/attitude error budget: ___ · RAIM/FDE status: ___

## 3. Control design
| Loop | Gain | Phase margin | Gain margin | Requirement |
|---|---|---|---|---|
| inner | | | | |
| outer | | | | |

## 4. Digital / observer
- Sample rate + discrete design: ___ · Observer gains/poles: ___

## 5. Allocation / scheduling
- Control allocation: ___ · Gain schedule / adaptive notes: ___

## 6. Guidance / optimal control
- Guidance law + performance: ___ · LQR/MPC/trajectory results: ___

## 7. Space GNC (if applicable)
- Attitude control: ___ · Orbit determination: ___ · Rendezvous: ___

## 8. Monte Carlo / robustness
- Disturbance response: ___ · MC/covariance results: ___

## 9. Conclusions
- Margins vs requirement: ___ · Open items for flight test / formal
  verification: ___

---
*DRAFT - for human GNC lead review. Not flight software release or an
approval document.*
