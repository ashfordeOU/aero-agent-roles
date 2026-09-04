# Aero Agent Roles — role bank on top of Aero Agent Skills

**The commercialization layer.** Aero Agent Skills = the knowledge substrate
(correct, gated, standard-anchored leaves). This repo = professional roles
that BIND + ORDER those skills to own an END-TO-END deliverable — with
evidence gates and a human sign-off stop.

> Skills = "do this task correctly." Roles = "own this deliverable end to
> end." A buyer adopts a role (an AI Certification Engineer that produces
> the certification plan), not 500 skill files.

## Program definition
Full operating model (flows, needs, gaps, systems coverage, roadmap):
`~/company-ops/veda/knowledge/records/aero-two-repo-program-2026-09-04.md`
(the v2 audited plan — registration pattern, systems matrix, backup,
quiet-hours, security gates, handover).

## Layout
```
roles/<role-slug>/
├── ROLE.md          # role contract (frontmatter + body)
├── templates/       # ORIGINAL deliverable skeletons (never copied)
├── tests/           # role tests: bound skills resolve, order deterministic
└── SOURCES.md       # per-role source register (tier/status/verification)
docs/                # DOMAINS, handover, conventions
sources/             # shared source register (Tier 1-4)
scripts/             # gates, generation, role tooling
ops/automation/      # wave/role briefs + state (mirror AeroSkills)
```

## Repo chain (same as AeroSkills)
dev ~/company-ops/aero-agent-roles → private arjun-0077/aero-agent-roles →
public ashfordeOU/aero-agent-roles (post founder GO). npm package
aero-agent-roles. Same author identity (ashfordeOU), same tripwires, same
CI-first, same no-verbatim + security-audit discipline.

## Status
- 2026-09-04: GO from founder. Skeleton + first role cohort in progress.
  Quiet-hours noted (founder override for this build).

## Roles (first cohort)
1. do178c-cert-engineer — software certification, PSAC + verification
2. airworthiness-compliance-engineer — Part 21/CS compliance matrix
3. as9100-quality-auditor — QMS internal audit

See roles/<slug>/ROLE.md per role. Maintainer: Arjun (CEO) + Veda team.
Handover: docs/MAINTENANCE_AND_HANDOVER.md.
