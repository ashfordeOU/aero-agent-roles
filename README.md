# Aero Agent Roles

**Professional engineering roles for AI agents — built on [Aero Agent Skills](https://github.com/ashfordeOU/aero-agent-skills).**

Aero Agent Skills is a library of 500+ verified engineering skills
(DO-178C planning, FAR 25.341 gust loads, AS9100 internal audits — each
gated, tested, and standards-anchored). Aero Agent Roles goes one layer
higher: it packages those skills into **roles** that own an end-to-end
deliverable — the certification plan, the compliance matrix, the audit
report — with evidence gates at every stage and a human sign-off line
that is never crossed.

> **Skills = "do this task correctly."**
> **Roles = "own this deliverable end to end."**

Instead of assembling 30 skill files yourself, you adopt a role. The
role knows the workflow order, the evidence each stage must produce, and
the hard boundary where human judgment takes over.

## Roles (first cohort)

| Role | What it produces | Bound skills |
|---|---|---|
| [DO-178C Certification Engineer](roles/do178c-cert-engineer/ROLE.md) | Plan for Software Aspects of Certification (PSAC) + verification evidence set | 9 DO-178C skills |
| [Airworthiness Compliance Engineer](roles/airworthiness-compliance-engineer/ROLE.md) | Compliance checklist / certification matrix (reg → MoC → document → status) | 9 certification skills |
| [AS9100 Quality Auditor](roles/as9100-quality-auditor/ROLE.md) | Audit plan + findings report + corrective-action follow-up | 15 quality/FAI skills |

Each role directory contains:
- **ROLE.md** — the contract: role identity, deliverable contract,
  ordered workflow, evidence gates, boundaries, verification
- **templates/** — original deliverable skeletons (never copied from
  proprietary sources)
- **tests/** — offline test suite proving bound skills resolve and the
  workflow is deterministic
- **SOURCES.md** — the standards and documents behind the role, with
  tier and verification status

## How it works

A role binds real, existing skills from Aero Agent Skills and orders them
into the workflow a practicing engineer follows. For example, the
DO-178C Certification Engineer runs: planning → development framework →
verification strategy → test evidence → configuration management → tool
qualification → previously-developed-software check → data/control
coupling analysis → airworthiness liaison, and produces a PSAC skeleton
for human review.

Every role ends at the same line: **the human sign-off.** Roles produce
draft deliverables with evidence — they never issue certification
approval, declare compliance findings, or claim regulatory sign-off.

## Standards discipline

Aerospace standards are largely proprietary (RTCA, EUROCAE, SAE, IAQG).
This repository respects that:
- Public-domain regulations (FAR/CS, FAA/EASA guidance) are cited.
- Proprietary standards are referenced by identifier only — never
  reproduced.
- Deliverable templates are original structures, not copied artifacts.

## Quality gates

Every role passes a 5-gate battery before it ships:
1. **Role lint** — structure, frontmatter, bound-skill resolution
2. **Role tests** — offline test suite passes (skills resolve, workflow
   deterministic, template complete)
3. **No-verbatim** — no proprietary standard text reproduced
4. **Security** — no secrets, credentials, or local paths
5. **Manifest** — generated manifest matches the tree

Run locally:

```bash
make validate
```

## Layout

```
roles/<role-slug>/
├── ROLE.md          # the role contract
├── templates/       # original deliverable skeletons
├── tests/           # offline role tests
└── SOURCES.md       # per-role source register
docs/                # conventions and handover
sources/             # shared source register (Tier 1-4)
scripts/             # gates and role tooling
```

## Roadmap

- First cohort shipped (DO-178C, airworthiness, AS9100) — v0.1
- Next: systems safety (ARP4761A), DO-254 hardware certification,
  flight test, stress/loads, requirements verification roles
- Role → skills demand feedback: missing skills surface as build
  priorities in Aero Agent Skills

## License

Apache-2.0. Standards referenced within roles remain the property of
their respective publishers; no proprietary content is reproduced.

## Related

- [Aero Agent Skills](https://github.com/ashfordeOU/aero-agent-skills) —
  the knowledge substrate this role bank builds on
