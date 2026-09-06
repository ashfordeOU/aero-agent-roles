# Maintenance & Handover

What a new maintainer (human or agent) needs to operate this repo cold.

## What this repository is

Aero Agent Roles — the roles bank on Aero Agent Skills. Each role is an
EXECUTABLE WORKER: a domain core engine + CLI that builds a real
deliverable, gate-checks it, emits an evidence bundle, and tailors to a
customer program profile. 33 roles today, growing in role waves
(docs/WAVE-BRIEF.md).

## Repo layout

```
roles/<slug>/ROLE.md          contract: identity, deliverable, workflow,
                              gates, boundaries, HOW TO RUN
roles/<slug>/SOURCES.md       standards referenced
roles/<slug>/templates/*.md   FILLED generated deliverable (0 blanks)
roles/<slug>/core/*_core.py   executable domain engine (stdlib only)
roles/<slug>/cli.py           build/check/--bundle/--profile
roles/<slug>/tests/           core + role + bundle/profile tests
scripts/evidence.py           shared bundle writer + profile loader +
                              dispatch helper
scripts/{role-lint,gate-role-tests,gate-no-verbatim,gate-security,
         gen_manifest,audit-100,spot-cli}.py|.sh   gates + audits
scripts/binding-ledger.py     growth meter (coverage % vs AeroSkills)
scripts/coverage-matrix.py    generates docs/COVERAGE-MATRIX.md (wave planner)
scripts/release-law.py        role-count release milestones
scripts/dispatch-audit.py     cross-checks core vs bound skill logic
scripts/update-role-ratings.py  generates eval/role-ratings.md
docs/PROTOCOL.md              evidence bundle contract
docs/PROFILE-SCHEMA.md        program profile contract
docs/COVERAGE-MATRIX.md       generated per-family coverage
docs/WAVE-BRIEF.md            how roles grow (waves)
eval/role-ratings.md          generated mechanical ratings
profiles/                     example customer program profiles
manifest.json                 role manifest (generated)
```

## The 5 gates (make validate)

1. role-lint (structure/frontmatter/bound skills)
2. role-tests (every role's offline suite passes)
3. no-verbatim (templates/SOURCES never reproduce proprietary text)
4. security (no local info/creds/machine paths — tripwire; the local-path
   pattern derives from $HOME at runtime, never literal)
5. manifest (manifest.json matches tree)

Plus `make growth` (coverage-matrix up to date + release law).

## Evidence protocol (PROTOCOL.md v1)

Every `cli.py build --bundle` emits next to the deliverable:
```
evidence/model.json       every computed number as data
evidence/gates.json       PASS/FAIL per evidence gate + exit code
evidence/provenance.json  core file/functions + bound skill dispatch
                          rows (cross-checked values, delta, agrees)
```
Any harness (Claude Code, Codex, Cursor, Hermes, CI) can consume the
bundle. The `scripts/compare.py` harness runs a question through raw
LLM vs role vs role+skills to demonstrate the trust-layer value
(docs/trust-layer-proof-2026-09-05.md).

## Program profiles (PROFILE-SCHEMA.md)

`cli.py build --profile <customer.json>` tailors a role to a customer
program: basis, authority, DER/CVE, document prefix, standards. The
DRAFT / not-an-approval marker is code-enforced regardless of profile.
Profiles live in profiles/ (example-airframer.json = FAR-25,
easa-supplier.json = CS-25).

## Growth (docs/WAVE-BRIEF.md)

- binding-ledger.py shows coverage % vs the AeroSkills leaf tree
- A role wave is triggered when a family is below the 70% binding bar
  with >= 4 coherent unbound leaves (see COVERAGE-MATRIX.md)
- release-law.py: v1.0 @12 (current), v1.1 @25, v1.2 @50
- dispatch-audit.py: extend the DISPATCH_MAP as roles/skills grow; the
  compounding power axis (skills growth → more cross-checks)

## Ratings

`python3 scripts/update-role-ratings.py` regenerates eval/role-ratings.md
from mechanical evidence (tests pass, blanks, audit-100, bound skills).
Run after any role change; commit the updated ledger.

## Adding a role (100% standard)

Every role MUST have: ROLE.md + SOURCES.md + filled template (0 blanks)
+ core engine + cli.py (build/check/--bundle/--profile) + tests. Gates
must pass. Bind REAL leaves from the coverage matrix candidates; ground
domain logic in bound AeroSkills scripts or quotable public standards.
Never invent reg numbers. Never commit local paths or secrets.

## Known limits

- role-lint requires core/ + cli.py + test_*_core.py per role (enforced)
- dispatch map is explicit per role; not every computation has a bound
  skill pair yet — extend as skills grow
- public repo push is founder-GO only (ashfordeOU token allowlist)

## Handover checklist (new maintainer)

1. `cd ~/company-ops/aero-agent-roles && make validate` (5/5) and
   `make growth` — both must pass
2. `bash scripts/audit-100.sh` (12/12) + `bash scripts/spot-cli.sh`
3. Run a full test sweep: `for t in roles/*/tests/test_*.py; do python3
   $t; done` (0 failures)
4. Rebuild generated docs: `python3 scripts/coverage-matrix.py && python3
   scripts/gen_manifest.py && python3 scripts/update-role-ratings.py`
   then `git diff` to confirm only real changes
5. Confirm repo clean + pushed: `git status -sb` (== origin/main)
6. Check the monitoring cron exists: [CEO] Aero Agent Roles status
   (15m tick, monitor-gated, quiet-aware)
7. Read docs/WAVE-BRIEF.md before starting the next role wave; target
   roles come from docs/COVERAGE-MATRIX.md
8. KB records live in ~/company-ops/veda/knowledge/records/ (search
   aero-*). Push veda too if you added records.

A fresh pickup means: clone/pull roles repo, run the checklist above,
and the roles + evidence protocol + growth system are fully
operable — no tribal knowledge required.
