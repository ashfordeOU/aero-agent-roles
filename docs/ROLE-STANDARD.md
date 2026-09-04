# ROLE.md contract standard (Aero Agent Roles)

Every role = one directory `roles/<role-slug>/` with ROLE.md + templates/
+ tests/ + SOURCES.md. This file is the anatomy standard.

## Frontmatter (required)
```yaml
---
type: role
name: <role-slug>
title: "<Human job title>"
status: draft | active
domain: <aero domain family>
deliverable_type: "<what it produces: plan | matrix | report | assessment>"
standards_bound:
  - id: do-178c
    tier: TIER-2
    reference-only: true
skills_bound:            # REAL leaves from aero-agent-skills (verified)
  - avionics/do178c/planning
  - avionics/do178c/verification
tools_allowed: []        # what it may use (stdlib, offline by default)
forbidden:               # hard stops — never crosses these lines
  - "issue certification approval"
  - "claim regulatory sign-off"
  - "reproduce proprietary standard text"
sign_off_required: true  # human must sign the final deliverable
license: Apache-2.0
compatibility: "agentskills.io ROLE.md; any SKILL.md host"
metadata:
  version: 0.1.0
  author: Aero Agent Roles
  skills_release: "v1.3.0+"   # AeroSkills release band this binds to
---
```

## Body sections (required)
1. **Role identity** — what this role IS; when to use; when NOT to use.
2. **Deliverable contract** — the exact artifact(s) it produces, with the
   required shape (sections/fields). The deliverable is the point.
3. **Workflow** — ordered stages; each stage names the bound skill(s) it
   loads and what it produces at that stage.
4. **Evidence gates** — per stage: what "done" means, checkably. A stage
   without an evidence gate is not done.
5. **Boundary / forbidden** — hard stops (see frontmatter forbidden);
   the human sign-off line is ALWAYS respected.
6. **Verification** — how the role is tested (tests/), what the role test
   proves, known limits.
7. **Compliance** — standards referenced not reproduced; tier notes.

## Rules
- skills_bound entries MUST resolve to real leaves in aero-agent-skills.
  A role that binds a nonexistent skill FAILS the role creation gate.
- templates/ are ORIGINAL structure — never copied from AFuzion, Visure,
  or any proprietary template vendor (founder security/copyright gate).
- SOURCES.md records every standard/book the role depends on, with tier,
  acquisition status, extraction status, verification notes.
- Tests must run OFFLINE (stdlib only) — no network in role tests.

## Gate wiring
- `bash scripts/role-create-gate.sh <role-slug>` before every role commit.
- Role lint: frontmatter fields + bound-skill resolution + forbidden +
  deliverable_type present.
- Bound-skill check: each skills_bound path exists in the pinned
  aero-agent-skills release manifest.
