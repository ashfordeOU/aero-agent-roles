# Contributing to Aero Agent Roles

Aero Agent Roles is an open role layer for civil aerospace engineering
agents, published by Ashforde OÜ (Estonia) under Apache-2.0. Roles bind
verified [Aero Agent Skills](https://github.com/ashfordeOU/aero-agent-skills)
leaves into end-to-end deliverables.

## Ground rules (AGENTS.md)

- ONE main branch; every change lands on main as a complete commit.
- Every commit is complete: code + docs + tests + state together.
- Clean at rest: zero uncommitted files.
- Test-first: failing test → fix → passing test.
- Evidence over claims: no role ships without receipts.

## What a role is

A role is a WORKER, not a job description. Every role in `roles/<slug>/`
must be an executable engine:

```
ROLE.md          contract: identity, deliverable, workflow, gates, boundaries
SOURCES.md       standards referenced (summary only, never verbatim)
templates/       FILLED generated deliverable (zero blanks)
core/*_core.py   executable domain engine (stdlib only)
cli.py           build / check / --bundle / --profile
tests/           core tests + role tests + bundle/profile tests
```

## Contribution workflow

1. Read `docs/ROLE-STANDARD.md` and `docs/PROTOCOL.md` before starting.
2. For non-trivial work, open an issue or discussion first so the change
   is scoped and agreed.
3. Build the change with its tests. The gate suite is the definition of
   done for any role or tooling change:

```bash
make validate    # 5 real gates: role-lint, role-tests, no-verbatim, security, manifest
make growth      # coverage matrix + release law + stale-stats guard
make package-test  # npm/CLI/MCP smoke (when packaging touched)
```

4. Regenerate derived artifacts and commit them together:
   `python3 scripts/coverage-matrix.py`, `python3 scripts/update-role-ratings.py`,
   `python3 scripts/gen_manifest.py`, `make visuals`.
5. Push. Never force-push.

## The 100% bar

A role is only "done" when it runs STANDALONE
(`AEROSKILLS_DEV=/nonexistent python3 cli.py build`) AND deeper with the
skills library (bound-leaf dispatch cross-checks). Both modes gate-check.
A template with blank fields is not done.

## Content rules

- Bind REAL Aero Agent Skills leaves; never invent domain rules.
- Public-domain regulations (FAR/CS) are quotable with citation.
- Never reproduce proprietary standard text (see STANDARDS.md discipline).
- Every deliverable ends at the human sign-off — roles never approve,
  certify, or clear.

## Certification

Every contributor certifies their submission contains no controlled
data and no verbatim standards text. By opening a pull request you
accept the [Code of Conduct](CODE_OF_CONDUCT.md).
