# Aero Agent Roles — Maintenance & Handover

How this repo is maintained, gated, and handed over. Read this BEFORE
working on roles. Mirrors AeroSkills docs/MAINTENANCE_AND_HANDOVER.md.

## What this repo is
Role bank layered on Aero Agent Skills: professional roles that bind +
order skills to own end-to-end deliverables (cert plans, compliance
matrices, audit reports). Full program definition:
`~/company-ops/veda/knowledge/records/aero-two-repo-program-2026-09-04.md`.

## Repo chain
dev `~/company-ops/aero-agent-roles` → private `arjun-0077/aero-agent-roles`
→ public `ashfordeOU/aero-agent-roles` (founder GO required). Tokens live
in the standard Hermes token store (same .tmp PAT discipline as AeroSkills
— paths resolved in scripts, NEVER committed or referenced by value).
Author identity: `ashfordeOU <contact@ashforde.org>`.

## The 5 gates (make validate)
1. role-lint — structure, frontmatter, bound-skill resolution
2. role-tests — every role's offline test suite (roles/*/tests/)
3. no-verbatim — templates/SOURCES never reproduce proprietary text
4. security — no local info, creds, machine paths (tripwire)
5. manifest — manifest.json matches the tree

## How to add a role
1. Read docs/ROLE-STANDARD.md (the contract anatomy).
2. Pick the real deliverable type + bind REAL aero-agent-skills leaves
   (verify each path exists in ~/AeroSkills/skills/).
3. Write ROLE.md (frontmatter + 7 body sections) + templates/ (ORIGINAL
   skeleton) + tests/test_role_<slug>.py + SOURCES.md (tier/status).
4. Run `bash scripts/gate-role-tests.sh` + `python3 scripts/role-lint.py`.
5. Add to skills-demand list if bound leaves are missing in AeroSkills.
6. CEO gate → commit → (after GO) private → public.

## Adding a role = adding a gate row
roles/ is auto-discovered by role-lint + gen_manifest. No registry edit
needed for the role itself; the REPO registration lives in veda
ops/repo-registry.json + products-state.json (see program Part D).

## Maintenance cadence
- Daily: veda all-knower watches this repo (git_state/site/parity) once
  registered; heavy-maintainer sweeps; backup_knowledge covers dev dir.
- Weekly: role depth audit (are bound skills still current in
  AeroSkills? do sources need re-verification?)
- Source register: any owned standard purchase updates SOURCES.md.
- Quiet hours 20:00-08:00 UTC: no role token burn.

## Known limits
- Roles are DRAFT-level contracts until their TIER-2 sources are owned +
  verified (see roles/*/SOURCES.md buy-lists). We do NOT claim
  cert-ready output from unverified sources — that line never moves.
- Tests check structure + skill resolution + deterministic workflow,
  not deliverable legal correctness (human sign-off always required).

## Handover checklist (new session/operator)
1. Read this file + docs/ROLE-STANDARD.md.
2. `cd ~/company-ops/aero-agent-roles && make validate` — must pass.
3. Read roles/*/SOURCES.md — know which sources are owned vs needed.
4. Check veda products-state.json for repo status + the program record.
5. Never push to public without founder GO (new product = READY=ASK).

Maintainer: Arjun (CEO) + Veda team. Last updated 2026-09-04.
