# Roles-Wave Operating Brief (v1) — how the roles repo grows

Mirror of the AeroSkills wave mechanism. The roles repo grows in
**role waves**: a CEO dispatch to a role-builder, each wave adds N roles
targeted at coverage gaps from `docs/COVERAGE-MATRIX.md`.

## Cadence

- A role wave may start when the skills repo has landed new leaves OR
  when the coverage matrix shows a family below the binding bar.
- Wave size: 3-6 roles (each is a full 100% build: core engine + filled
  template + gates + tests + bundle + profile). Smaller than skills
  waves because each role is a bigger artifact.
- No two waves race the same repo (same doctrine as skills).

## Wave trigger (deterministic)

Run `python3 scripts/coverage-matrix.py`. A wave is justified when:

1. A family is below the **70% binding bar** AND has >= 4 unbound leaves
   in a coherent sub-cluster, OR
2. The skills repo grew leaves in a family that now exceeds its roles'
   binding (new role-ready sub-clusters), OR
3. A customer program profile needs a role variant (customer pull).

Current gaps (from the generated matrix): avionics 23%, manufacturing-
quality 31%, flight-test-operations 50%, gnc-autonomy 55%,
systems-engineering-safety 16%, vehicle-design 68%, aerodynamics 68%.

## Role anatomy (100% standard, non-negotiable)

Every role in every wave:
```
roles/<slug>/ROLE.md         contract (identity, deliverable, workflow,
                             gates, boundaries, HOW TO RUN)
roles/<slug>/SOURCES.md      standards referenced
roles/<slug>/templates/*.md  FILLED generated deliverable (0 blanks)
roles/<slug>/core/<slug>_core.py   executable domain engine
roles/<slug>/cli.py          build/check/--bundle/--profile
roles/<slug>/tests/          core tests + role tests + bundle/profile tests
```
Gates: `make validate` (role-lint, role-tests, no-verbatim, security,
manifest) must pass. New role = bind REAL leaves from the coverage
matrix candidates; domain logic grounded in the bound AeroSkills
scripts or quotable public standards. Never invented rules.

## Release law (role count)

- v1.0 @ 12 roles (current baseline)
- v1.1 @ 25 roles
- v1.2 @ 50 roles
- Each milestone: git tag `roles-vX.Y.Z`, manifest bump, GitHub
  Release, site update, KB record. Same 100-skill style law, applied to
  roles (the founder's commercialization layer release bar).
- Each role release pins `skills_release` it cross-checks against.

## Dispatch growth rule

Every wave should extend skill-dispatch cross-checks where the bound
skills have logic files. The role core and the bound leaf compute the
same quantity independently; provenance.json records agreement/delta.
This is the compounding power axis: skills growth makes roles stronger.

## Close-out checklist (every wave)

1. `make validate` 5/5
2. `bash scripts/audit-100.sh` 12+/12+ PASS
3. Full test battery 0 failures
4. `python3 scripts/coverage-matrix.py --check` up to date
5. Manifest regenerated (`python3 scripts/gen_manifest.py`)
6. Visuals/README stats regenerated if role count changed
7. Commit + push private. Public on founder GO only.
8. KB record of the wave (roles, coverage delta, gates green).

## Quiet hours

Roles work is QH-gated like every bot-system job: 20:00-08:00 UTC null
burn unless the founder waives it (as he did for the original role build
and the 100% rebuild).
