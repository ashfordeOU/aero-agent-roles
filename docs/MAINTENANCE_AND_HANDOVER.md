# Aero Agent Roles — Maintenance & Handover

How this repository is maintained, gated, and handed over. Read this
BEFORE contributing roles.

## What this repository is
Role bank layered on Aero Agent Skills: professional roles that bind +
order skills to own end-to-end deliverables (certification plans,
compliance matrices, audit reports).

## Contribution flow
1. Read docs/ROLE-STANDARD.md (the contract anatomy).
2. Pick the real deliverable type + bind REAL aero-agent-skills leaves
   (verify each path exists in the skills repository).
3. Write ROLE.md (frontmatter + 7 body sections) + templates/ (ORIGINAL
   skeleton) + tests/test_role_<slug>.py + SOURCES.md (tier/status).
4. Run `bash scripts/gate-role-tests.sh` + `python3 scripts/role-lint.py`.
5. Add to skills-demand list if bound leaves are missing in Aero Skills.
6. Maintainer gate → commit → private → public release.

## The 5 gates (make validate)
1. role-lint — structure, frontmatter, bound-skill resolution
2. role-tests — every role's offline test suite (roles/*/tests/)
3. no-verbatim — templates/SOURCES never reproduce proprietary text
4. security — no secrets, credentials, local paths (tripwire)
5. manifest — manifest.json matches the tree

## Adding a role = auto-discovered
roles/ is auto-discovered by role-lint + gen_manifest. No registry edit
needed for the role itself.

## Maintenance cadence
- Continuous: role tests + gates run on every change.
- Weekly: role depth audit (are bound skills still current in Aero
  Skills? do sources need re-verification?)
- Source register: any owned standard purchase updates SOURCES.md.

## Known limits
- Roles are DRAFT-level contracts until their TIER-2 sources are owned +
  verified (see roles/*/SOURCES.md acquisition notes). We do NOT claim
  cert-ready output from unverified sources — that line never moves.
- Tests check structure + skill resolution + deterministic workflow,
  not deliverable legal correctness (human sign-off always required).

## Handover checklist (new maintainer)
1. Read this file + docs/ROLE-STANDARD.md.
2. `cd <repo> && make validate` — must pass.
3. Read roles/*/SOURCES.md — know which sources are owned vs needed.
4. Never push to the public repository before the maintainer gate
   (new product = explicit release decision).

Maintainer: Aero Agent Roles team.
