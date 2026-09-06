<p align="center">
  <img src="docs/logo-mark.png" alt="Aero Agent Roles — role layer mark" width="200">
</p>

<p align="center">
  <img src="docs/title-dark.png" alt="Aero Agent Roles — aerospace engineering · by Ashforde OÜ · Apache-2.0" width="620">
</p>

<p align="center">
  <strong>The role layer for aerospace engineering agents.</strong><br>
  Roles bind verified Aero Agent Skills leaves into end-to-end deliverables — certification plans, compliance matrices, audit reports — with evidence gates and a human sign-off line.
</p>

<!-- gen:statline -->
<p align="center">
  <img src="docs/statline-dark.png" alt="24 roles · 446 skills bound · 919 offline tests · 22 standards · 5/5 gates · Apache-2.0" width="100%">
</p>
<!-- /gen:statline -->

<!-- gen:badges -->
<p align="center">
  <a href="roles/"><img src="https://img.shields.io/badge/roles-24-a78bfa?style=flat&labelColor=1a1e35" alt="roles 24"></a>
  <a href="https://github.com/ashfordeOU/aero-agent-skills"><img src="https://img.shields.io/badge/skills_bound-446-0ea5e9?style=flat&labelColor=1a1e35" alt="skills bound 446"></a>
  <a href="roles/"><img src="https://img.shields.io/badge/offline_tests-919-2ea043?style=flat&labelColor=1a1e35" alt="offline tests 919"></a>
  <a href="STANDARDS.md"><img src="https://img.shields.io/badge/standards-22-f97316?style=flat&labelColor=1a1e35" alt="standards 22"></a>
  <a href="https://agentskills.io"><img src="https://img.shields.io/badge/format-agentskills.io-8b5cf6?style=flat&labelColor=1a1e35" alt="format agentskills.io"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-2ea043?style=flat&labelColor=1a1e35" alt="Apache-2.0"></a>
</p>
<p align="center">
  <a href="https://www.npmjs.com/package/aero-agent-roles"><img src="https://img.shields.io/badge/npm-aero--agent--roles-0ea5e9?style=flat&labelColor=1a1e35" alt="npm aero-agent-roles"></a>
  <a href="packages/aero-agent-roles/"><img src="https://img.shields.io/badge/cli-aero--roles-8b5cf6?style=flat&labelColor=1a1e35" alt="cli aero-roles"></a>
  <a href="packages/aero-agent-roles/lib/mcp.js"><img src="https://img.shields.io/badge/mcp_server-claude_%C2%B7_cursor_%C2%B7_vscode-ec4899?style=flat&labelColor=1a1e35" alt="MCP server for Claude Desktop, Cursor, VS Code"></a>
  <a href=".claude-plugin/"><img src="https://img.shields.io/badge/claude_code-plugin-f97316?style=flat&labelColor=1a1e35" alt="claude code plugin"></a>
  <a href="packages/jetbrains-plugin/"><img src="https://img.shields.io/badge/jetbrains-plugin_(marketplace_pending)-6e7590?style=flat&labelColor=1a1e35" alt="JetBrains plugin, built, marketplace submission pending"></a>
</p>
<!-- /gen:badges -->

<p align="center">
  <a href="#domain-map">Domain map</a> ·
  <a href="#roles">Roles</a> ·
  <a href="#how-a-role-works">How a role works</a> ·
  <a href="#standards-discipline">Standards discipline</a> ·
  <a href="#quality-gates">Quality gates</a> ·
  <a href="#roadmap">Roadmap</a> ·
  <a href="#faq">FAQ</a>
</p>

---

Aero Agent Skills is the verified knowledge layer: 500+ gated, tested,
standards-anchored skills. Aero Agent Roles packages that knowledge into
**roles that own a deliverable end to end**. Instead of assembling thirty
skill files, adopt a role. The role knows the workflow order, the evidence
each stage must produce, and the hard boundary where a human signs.

> **Skills = "do this task correctly."**
> **Roles = "own this deliverable end to end."**

## Domain map

<!-- gen:overview -->
**24 roles** across **12 domains**, binding **446 skills** from Aero Agent Skills and verified by **919 offline tests** — every figure below is computed from the tree at HEAD; nothing is hand-counted.
<!-- /gen:overview -->

<p align="center">
  <img src="docs/domain-radar-dark.png" alt="Domain coverage radar: skills bound vs offline tests across 12 domains" width="100%">
</p>

<p align="center">
  <img src="docs/domain-polar-dark.png" alt="Polar rose: roles per domain, area-true" width="100%">
</p>

Full per-domain role lists: **[docs/DOMAINS.md](docs/DOMAINS.md)**.

## Roles

<p align="center">
  <img src="docs/structure-dark.png" alt="Role bank structure sunburst: inner ring of 12 domains, outer ring of roles, arc length proportional to skills bound" width="100%">
</p>

Each role directory contains `ROLE.md` (the contract), `templates/`
(original deliverable skeletons), `tests/` (offline verification), and
`SOURCES.md` (standards referenced).

<!-- gen:role-table -->
| Role | Deliverable | Skills bound |
|---|---|---|
| [AS9100 Quality / Internal Auditor](roles/as9100-quality-auditor/ROLE.md) | audit plan + findings report + corrective-action follow-up | 15 |
| [Aerodynamics Engineer](roles/aerodynamics-engineer/ROLE.md) | aerodynamic design + analysis report | 28 |
| [Aircraft Conceptual Design Engineer](roles/aircraft-design-engineer/ROLE.md) | concept design package (sizing + layout + cost) | 34 |
| [Airworthiness Compliance Engineer](roles/airworthiness-compliance-engineer/ROLE.md) | compliance checklist / certification matrix | 9 |
| [DO-160G Environmental Qualification Engineer](roles/do160-environmental-engineer/ROLE.md) | equipment environmental qualification plan/report | 6 |
| [DO-178C Software Certification Engineer](roles/do178c-cert-engineer/ROLE.md) | certification plan + verification evidence set | 9 |
| [DO-254 Airborne Electronic Hardware Engineer](roles/do254-hardware-engineer/ROLE.md) | Plan for Hardware Aspects of Certification (PHAC) + design assurance evidence set | 4 |
| [Data Bus / Avionics Network Engineer](roles/data-bus-avionics-engineer/ROLE.md) | avionics data bus loading + protocol assessment | 5 |
| [Engineering Analysis and Data Engineer](roles/engineering-analysis-engineer/ROLE.md) | analysis verification + engineering report | 42 |
| [Flight Management Engineer](roles/flight-management-engineer/ROLE.md) | flight plan and RNAV/RNP route assessment | 11 |
| [Flight Mechanics Engineer](roles/flight-mechanics-engineer/ROLE.md) | performance + stability and control analysis report | 38 |
| [Flight Test Engineer](roles/flight-test-engineer/ROLE.md) | flight test plan + envelope expansion report | 21 |
| [Flight Test Performance Engineer](roles/flight-test-performance-engineer/ROLE.md) | flight test performance data analysis report | 15 |
| [Guidance Engineer](roles/guidance-engineer/ROLE.md) | guidance law design and assessment report | 9 |
| [Guidance, Navigation and Control (GNC) Engineer](roles/gnc-engineer/ROLE.md) | control design + guidance/navigation analysis report | 23 |
| [High-Speed Aerodynamics Engineer](roles/high-speed-aerodynamics-engineer/ROLE.md) | High-Speed Aerodynamic Analysis Memo | 19 |
| [MBSE Modeling Engineer](roles/mbse-modeling-engineer/ROLE.md) | system model architecture + MBSE plan | 6 |
| [NDT Engineer](roles/ndt-engineer/ROLE.md) | nondestructive test plan + method selection report | 10 |
| [Numerical Analysis Engineer](roles/numerical-analysis-engineer/ROLE.md) | numerical methods verification memo | 10 |
| [Propulsion Engineer](roles/propulsion-engineer/ROLE.md) | propulsion system design + cycle analysis report | 34 |
| [Space Systems Engineer](roles/space-systems-engineer/ROLE.md) | spacecraft mission + subsystem design report | 45 |
| [State Estimation Engineer](roles/state-estimation-engineer/ROLE.md) | navigation state estimator design report | 7 |
| [Structures and Loads Engineer](roles/structures-loads-engineer/ROLE.md) | loads + strength/stability analysis report | 38 |
| [Systems Integration Engineer](roles/systems-integration-engineer/ROLE.md) | System Development Assurance and Integration Plan (ARP4754A) | 8 |
<!-- /gen:role-table -->

### See a role

This is the artifact — one real role, exactly as agents receive it:

<details>
<summary><code>do178c-cert-engineer</code> — ROLE.md frontmatter (excerpt)</summary>

```yaml
name: do178c-cert-engineer
title: "DO-178C Software Certification Engineer"
domain: avionics
deliverable_type: "certification plan + verification evidence set"
standards_bound:
  - id: do-178c
    tier: TIER-2
    reference-only: true
skills_bound:
  - avionics/do178c/planning
  - avionics/do178c/development
  - avionics/do178c/verification
```

</details>

The body walks the agent through: planning → development framework →
verification strategy → test evidence → configuration management → tool
qualification → previously-developed-software check → data/control
coupling analysis → airworthiness liaison — **where the agent must stop
and let a human sign**.

<p align="center">
  <img src="docs/role-anatomy-dark.png" alt="Anatomy of a role: frontmatter contract, workflow body with evidence gates, executable domain engine, offline behavior contract test" width="100%">
</p>

## How a role works

<p align="center">
  <img src="docs/how-it-works-dark.png" alt="Pipeline: adopt a role → role binds skills from manifest.json → workflow stages run in order → each stage has an evidence gate → core engine computes the deliverable → stop gate: human sign-off" width="100%">
</p>

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

<p align="center">
  <img src="docs/gates-dark.png" alt="Verification battery: commit passes 5 validate gates and the visuals-freshness check before CI goes green" width="100%">
</p>

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

## Roadmap

**Shipped:** 22 professional roles binding 432 verified Aero Agent
Skills leaves across 12 engineering domains, every role an executable
worker (core engine + CLI + filled template + tests) gated by
`make validate` (5/5) and the 100% audit — from DO-178C certification
engineer and DO-254 hardware engineer to structures, avionics data
bus, GNC guidance/state-estimation, flight test performance, NDT, and
high-speed aerodynamics. Evidence protocol (`--bundle`) emits
deliverable + model.json + gates.json + provenance.json for any
harness; program profiles (`--profile`) tailor one engine to any
customer's basis; npm CLI + MCP server packaged (`aero-agent-roles`).

**Now:** role waves selected deterministically by the coverage planner
(`scripts/wave-planner.py`) — closing the weakest families first
(systems engineering & safety, manufacturing quality), every new role
landing with its core engine, filled deliverable, bundle protocol, and
dispatch cross-checks against the live skills library.

**Later:** the full role-count release ladder (v1.1.0 @ 25, v1.2.0 @ 50
roles) with npm publish from the public tree; role chains that
orchestrate multi-role programs (cert engineer ← structures ← flight
test); reference builds for airframers and suppliers; marketplace
listings alongside Aero Agent Skills.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a PR: every role
ships with its executable core + filled template + tests, every
contributor certifies their submission contains no controlled data and
no verbatim standards text, every merge must pass `make validate` (5/5)
and `make growth`.

## Security

Roles are executable workers — review the core engine, `cli.py`, and any
bound-skill logic before you run one, the same way you would review any
code dependency. Report vulnerabilities privately per
[SECURITY.md](SECURITY.md).

## FAQ

[docs/FAQ.md](docs/FAQ.md) covers license, certification status, export
control, what verified means, roles-vs-skills, and affiliation. Short
answers: Apache-2.0, not certified, not controlled as published,
verified = replayable `make validate` 5/5 + the 100% audit on the commit
you are looking at, roles = executable workers on the skills substrate,
not affiliated with RTCA, SAE, EASA, FAA, or any government.

## Compliance notice

Aero Agent Roles is an open, unrestricted library of civil aerospace
engineering methodology for AI agents, published by Ashforde OÜ
(Estonia) under Apache-2.0. The content is educational: general
engineering principles, processes, and tool-usage guidance. It is not
ITAR/EAR-controlled technical data, and no proprietary standards text
is reproduced. Standards are referenced and summarized only (see
[STANDARDS.md](STANDARDS.md)). As published, this library falls within
the EU dual-use "public domain" exclusion (Annex I General Technology
Note, Regulation (EU) 2021/821). Users are solely responsible for their
own compliance. Not affiliated with or endorsed by RTCA, EUROCAE, SAE
International, IAQG, EASA, FAA, or any government.

## License

Apache-2.0. See [LICENSE](LICENSE) · [NOTICE](NOTICE) ·
[SECURITY.md](SECURITY.md) · [CONTRIBUTING.md](CONTRIBUTING.md) ·
[STANDARDS.md](STANDARDS.md) · [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

Aero Agent Roles is built and maintained by Ashforde OÜ (Estonia).
Copyright © 2026 Ashforde OÜ.

## Related

- [Aero Agent Skills](https://github.com/ashfordeOU/aero-agent-skills) - the knowledge substrate this role bank builds on
- [Aero Agent Roles on the web](https://ashforde.org/aeroagentroles/)

---

<div align="center">

### ⭐ Stars are our telemetry

**Every star steers the flight plan — it decides which engineering family gets the next role wave.**<br>
**If a role saved your team a certification cycle, send one back.**

<a href="https://github.com/ashfordeOU/aero-agent-roles/stargazers"><img src="https://img.shields.io/github/stars/ashfordeOU/aero-agent-roles?style=for-the-badge&logo=github&labelColor=1a1e35&color=f97316" alt="Star Aero Agent Roles on GitHub"></a>

</div>
