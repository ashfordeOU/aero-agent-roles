<p align="center">
  <img src="docs/logo-mark.png" alt="Aero Agent Roles — role layer mark" width="200">
</p>

<p align="center">
  <strong>The role layer for aerospace engineering agents.</strong><br>
  Roles bind verified Aero Agent Skills leaves into end-to-end deliverables — certification plans, compliance matrices, audit reports — with evidence gates and a human sign-off line.
</p>

<!-- gen:statline -->
<p align="center">
  <img src="docs/statline-dark.png" alt="3 roles · 33 skills bound · 16 offline tests · 5 gates per role · Apache-2.0" width="100%">
</p>
<!-- /gen:statline -->

<!-- gen:badges -->
<p align="center">
  <a href="roles/"><img src="https://img.shields.io/badge/roles-3-a78bfa?style=flat&labelColor=1a1e35" alt="roles 3"></a>
  <a href="https://github.com/ashfordeOU/aero-agent-skills"><img src="https://img.shields.io/badge/skills_bound-33-0ea5e9?style=flat&labelColor=1a1e35" alt="skills bound 33"></a>
  <a href="roles/"><img src="https://img.shields.io/badge/offline_tests-16-2ea043?style=flat&labelColor=1a1e35" alt="offline tests 16"></a>
  <a href="STANDARDS.md"><img src="https://img.shields.io/badge/standards-13-f97316?style=flat&labelColor=1a1e35" alt="standards 13"></a>
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
| [DO-178C Certification Engineer](roles/do178c-cert-engineer/ROLE.md) | Plan for Software Aspects of Certification + verification evidence | 9 |
| [Airworthiness Compliance Engineer](roles/airworthiness-compliance-engineer/ROLE.md) | Compliance checklist / certification matrix | 9 |
| [AS9100 Quality Auditor](roles/as9100-quality-auditor/ROLE.md) | Audit plan + findings + corrective-action follow-up | 15 |

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
