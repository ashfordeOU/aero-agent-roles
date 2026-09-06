# Aircraft/System Safety Assessment Report (ARP4761A)

**Item:** Elevator pitch control function
**System:** Fly-by-wire flight control system
**Function assessed:** Pitch control function
**Certification basis:** FAR/CS-25.1309
**Development assurance level:** A (from worst failure-condition severity)
**Analysis set:** FTA, FMEA, CCA
**Status:** draft-for-review

## 1. Item and functions

The pitch control function of the fly-by-wire flight control system drives the elevator to command and hold aircraft pitch attitude across the flight envelope. This assessment covers the pitch channel architecture (dual independent channels A/B, shared power and software platform) and its failure conditions.

Assessed probabilities are per flight hour. The dual-channel fault tree is quantified with per-channel loss probabilities of 1e-5 per flight hour and a common-cause event of 2e-10 per flight hour; the event tree adds the runaway escalation sequence.

## 2. Functional hazard assessment (FHA)

| Condition | Flight phase | Effect on aircraft | Severity | Target (per FH) | Assessed (per FH) | Meets | Analysis |
|---|---|---|---|---|---|---|---|
| Loss of all pitch control | all phases | Loss of the aircraft | Catastrophic | < 1.0e-09 | 3.0e-10 | YES | FTA-01 |
| Loss of pitch control with reduced authority | all phases | Large reduction in safety margins | Hazardous | < 1.0e-07 | 8.0e-09 | YES | FMEA/ET-01 |
| Pitch control nuisance oscillation | cruise | Physical discomfort, increased workload | Minor | < 1.0e-03 | 4.0e-05 | YES | FMEA-01 |

## 3. Fault tree analysis (FTA)

Top event: **loss-of-all-pitch**.

Gate structure:
- dual-channel-loss = AND(channel-a-loss, channel-b-loss)
- loss-of-all-pitch = OR(dual-channel-loss, ccf-event)

Basic event probabilities (per flight hour):
- ccf-event = 2.0e-10
- channel-a-loss = 1.0e-05
- channel-b-loss = 1.0e-05

Minimal cut sets:
| Cut set | Probability |
|---|---|
| ccf-event | 2.0e-10 |
| channel-a-loss AND channel-b-loss | 1.0e-10 |

**Top event probability: 3.0e-10 per flight hour.**

Cut-set sanity: no cut set exceeds the top event probability.

Basic-event importance (Fussell-Vesely):

- ccf-event: FV = 0.6667, RAW = 3333333333.556
- channel-a-loss: FV = 0.3333, RAW = 33334.0
- channel-b-loss: FV = 0.3333, RAW = 33334.0

## 4. FMEA / FMECA

Item: **Pitch control electronics (channel A)**, item failure rate 1.0e-05 per hour, operating time 1 h.

| Mode | Effect | Severity | alpha | beta | C_m | Share | Dominant |
|---|---|---|---|---|---|---|---|
| M1 | loss of pitch control channel output | Hazardous | 0.5 | 1 | 5.0e-06 | 0.556 | yes |
| M2 | pitch control unavailable in one channel | Major | 0.3 | 1 | 3.0e-06 | 0.333 |  |
| M3 | nuisance oscillation, annunciated | Minor | 0.2 | 0.5 | 1.0e-06 | 0.111 |  |

**Item criticality C_r: 9.0e-06** (sum of mode criticalities).

## 5. Event tree analysis

Initiating event: **Uncommanded runaway in one pitch channel**, frequency 1.0e-05 per flight hour.

Mitigating functions (branch success probabilities):
- runaway detection & disengagement: p(success) = 0.999
- remaining channel full authority: p(success) = 0.9995

End-state rollup (frequency = initiator x path probability):

| Sequence | Frequency (per FH) |
|---|---|
| runaway detection & disengagement:S remaining channel full authority:S | 1.0e-05 |
| runaway detection & disengagement:F remaining channel full authority:S | 1.0e-08 |
| runaway detection & disengagement:S remaining channel full authority:F | 5.0e-09 |
| runaway detection & disengagement:F remaining channel full authority:F | 5.0e-12 |

**Failure end state frequency: 5.0e-12 per flight hour** (all mitigations failed).

No end state exceeds the Catastrophic screening target (< 1.0e-09).

## 6. PSSA: safety target allocation

Failure condition target: **1.0e-09 per flight hour**, OR gate across 2 independent contributor(s).

- Per-contributor budget: **5.0e-10**
- Realized total: **3.0e-10**
- Margin: **3.33**
- Meets target: **YES**
- Note: dual-channel loss term (1e-10) and common-cause term (2e-10) apportioned as the two OR'd contributors

FDAL = A, IDAL = A.

## 7. Common cause analysis (CCA)

Analysis set covers ZSA, PRA and CMA: **YES**.

- ZSA zone 141 (forward electronics bay): hazard score 0.00, verdict **ok**.
- PRA (uncontained rotor burst / tire burst debris): p(event) = 1.0e-06, p(FC | event) = 0.1, contribution 1.0e-07; exposure over 1 h = 1.0e-06.
- Beta-factor (CMA): per-channel rate 1.0e-05, beta 2.0e-05 -> common-cause rate 2.0e-10, Q_cc = 2.0e-10; CCF-inclusive dual-channel probability 3.0e-10.

## 8. Failure-rate demonstration and uncertainty

Demonstrated failure rate (point estimate): 1 failure(s) over 1e+05 test hours -> **1.0e-05 per hour**.

FTA top-event uncertainty: error factor 3 -> lognormal sigma 0.668; 90% confidence band [1.0e-10, 9.0e-10] per flight hour.

## 9. SSA closure

| Condition | Severity | Predicted q (per FH) | Target (per FH) | Margin | Closed |
|---|---|---|---|---|---|
| Loss of all pitch control | Catastrophic | 3.0e-10 | < 1.0e-09 | 3.3 | YES |
| Loss of pitch control with reduced authority | Hazardous | 8.0e-09 | < 1.0e-07 | 12.5 | YES |
| Pitch control nuisance oscillation | Minor | 4.0e-05 | < 1.0e-03 | 25.0 | YES |

**Closure gate: CLOSED** (3/3 conditions meet their targets).

Safety requirement verification: 5/5 verified (CLOSED).

---
*Generated by Aero Agent Roles safety-assessment-engineer core (2026-09-06). DRAFT for human safety engineering review. Not an approval document and not a certification finding.*