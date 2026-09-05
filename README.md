<p align="center">
  <img src="docs/logo-mark.png" alt="Aero Agent Roles — role layer mark" width="200">
</p>

<p align="center">
  <strong>The role layer for aerospace engineering agents.</strong><br>
  Roles bind verified Aero Agent Skills leaves into end-to-end deliverables — certification plans, compliance matrices, audit reports — with evidence gates and a human sign-off line.
</p>

<!-- gen:statline -->
<p align="center">
  <img src="docs/statline-dark.png" alt="12 roles · 12 executable engines · 353 tests · 5 gates per role · Apache-2.0" width="100%">
</p>
<!-- /gen:statline -->

<!-- gen:badges -->
<p align="center">
  <a href="roles/"><img src="https://img.shields.io/badge/roles-12-a78bfa?style=flat&labelColor=1a1e35" alt="roles 12"></a>
  <a href="https://github.com/ashfordeOU/aero-agent-skills"><img src="https://img.shields.io/badge/skills_bound-336-0ea5e9?style=flat&labelColor=1a1e35" alt="skills bound 336"></a>
  <a href="roles/"><img src="https://img.shields.io/badge/offline_tests-353-2ea043?style=flat&labelColor=1a1e35" alt="offline tests 353"></a>
  <a href="STANDARDS.md"><img src="https://img.shields.io/badge/standards-9-f97316?style=flat&labelColor=1a1e35" alt="standards 9"></a>
  <a href="https://agentskills.io"><img src="https://img.shields.io/badge/format-agentskills.io-8b5cf6?style=flat&labelColor=1a1e35" alt="format agentskills.io"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-2ea043?style=flat&labelColor=1a1e35" alt="Apache-2.0"></a>
</p>
<!-- /gen:badges -->

---

Aero Agent Skills is the verified knowledge layer: 500+ gated, tested,
standards-anchored skills. Aero Agent Roles packages that knowledge into
**roles that own a deliverable end to end**. Instead of assembling thirty
skill files, adopt a role. The role knows the workflow order, the evidence
each stage must produce, and the hard boundary where a human signs.

> **Skills = "do this task correctly."**
> **Roles = "own this deliverable end to end."**

## Roles

Each role directory contains `ROLE.md` (the contract), `templates/`
(original deliverable skeletons), `tests/` (offline verification), and
`SOURCES.md` (standards referenced).

| Role | Deliverable | Skills bound |
|---|---|---|
| [AS9100 Quality / Internal Auditor](roles/as9100-quality-auditor/ROLE.md) | audit plan + findings report + corrective-action follow-up | 15 |
| [Aerodynamics Engineer](roles/aerodynamics-engineer/ROLE.md) | aerodynamic design + analysis report | 28 |
| [Aircraft Conceptual Design Engineer](roles/aircraft-design-engineer/ROLE.md) | concept design package (sizing + layout + cost) | 34 |
| [Airworthiness Compliance Engineer](roles/airworthiness-compliance-engineer/ROLE.md) | compliance checklist / certification matrix | 9 |
| [DO-178C Software Certification Engineer](roles/do178c-cert-engineer/ROLE.md) | certification plan + verification evidence set | 9 |
| [Engineering Analysis and Data Engineer](roles/engineering-analysis-engineer/ROLE.md) | analysis verification + engineering report | 42 |
| [Flight Mechanics Engineer](roles/flight-mechanics-engineer/ROLE.md) | performance + stability and control analysis report | 38 |
| [Flight Test Engineer](roles/flight-test-engineer/ROLE.md) | flight test plan + envelope expansion report | 21 |
| [Guidance, Navigation and Control (GNC) Engineer](roles/gnc-engineer/ROLE.md) | control design + guidance/navigation analysis report | 23 |
| [Propulsion Engineer](roles/propulsion-engineer/ROLE.md) | propulsion system design + cycle analysis report | 34 |
| [Space Systems Engineer](roles/space-systems-engineer/ROLE.md) | spacecraft mission + subsystem design report | 45 |
| [Structures and Loads Engineer](roles/structures-loads-engineer/ROLE.md) | loads + strength/stability analysis report | 38 |
|---|| Role | Deliverable | Skills bound |
|---|---|---|
| [AS9100 Quality / Internal Auditor](roles/as9100-quality-auditor/ROLE.md) | audit plan + findings report + corrective-action follow-up | 15 |
| [Aerodynamics Engineer](roles/aerodynamics-engineer/ROLE.md) | aerodynamic design + analysis report | 28 |
| [Aircraft Conceptual Design Engineer](roles/aircraft-design-engineer/ROLE.md) | concept design package (sizing + layout + cost) | 34 |
| [Airworthiness Compliance Engineer](roles/airworthiness-compliance-engineer/ROLE.md) | compliance checklist / certification matrix | 9 |
| [DO-178C Software Certification Engineer](roles/do178c-cert-engineer/ROLE.md) | certification plan + verification evidence set | 9 |
| [Engineering Analysis and Data Engineer](roles/engineering-analysis-engineer/ROLE.md) | analysis verification + engineering report | 42 |
| [Flight Mechanics Engineer](roles/flight-mechanics-engineer/ROLE.md) | performance + stability and control analysis report | 38 |
| [Flight Test Engineer](roles/flight-test-engineer/ROLE.md) | flight test plan + envelope expansion report | 21 |
| [Guidance, Navigation and Control (GNC) Engineer](roles/gnc-engineer/ROLE.md) | control design + guidance/navigation analysis report | 23 |
| [Propulsion Engineer](roles/propulsion-engineer/ROLE.md) | propulsion system design + cycle analysis report | 34 |
| [Space Systems Engineer](roles/space-systems-engineer/ROLE.md) | spacecraft mission + subsystem design report | 45 |
| [Structures and Loads Engineer](roles/structures-loads-engineer/ROLE.md) | loads + strength/stability analysis report | 38 |

## How a role works

A role binds real, existing skills from Aero Agent Skills and orders them
into the workflow a practicing engineer follows. The DO-178C role runs:
planning, development framework, verification strategy, test evidence,
configuration management, tool qualification, previously-developed-
software check, data/control coupling analysis, airworthiness liaison.
Each stage has an evidence gate. The output is a draft for human review.

Every role ends at the same line: **the human sign-off**. Roles produce
draft deliverables with evidence. They never issue certification approval,
declare compliance findings, or claim regulatory sign-off.

## Standards discipline

Aerospace standards are largely proprietary (RTCA, EUROCAE, SAE, IAQG).
This repository follows the same **summary-not-copy** rule as Aero Agent
Skills: name + paraphrase + short attributed quotes, never reproduction.
Public-domain regulations (FAR/CS) are quotable with citation. See
[STANDARDS.md](STANDARDS.md) for the full reference.

## Quality gates

Every role passes a 5-gate battery before it ships:

```bash
make validate
```

1. **Role lint** - structure, frontmatter, bound-skill resolution
2. **Role tests** - offline suite passes (skills resolve, workflow deterministic)
3. **No-verbatim** - no proprietary standard text reproduced
4. **Security** - no secrets, credentials, local paths
5. **Manifest** - generated manifest matches the tree

## Layout

```
roles/<role-slug>/
├── ROLE.md          # the role contract
├── templates/       # original deliverable skeletons
├── tests/           # offline role tests
└── SOURCES.md       # standards referenced by the role
docs/                # role anatomy standard, handover
scripts/             # gates and role tooling
```

## License

Apache-2.0. Standards referenced within roles remain the property of
their respective publishers; no proprietary content is reproduced.

## Related

- [Aero Agent Skills](https://github.com/ashfordeOU/aero-agent-skills) - the knowledge substrate this role bank builds on
- [Aero Agent Roles on the web](https://ashforde.org/aeroagentroles/)
