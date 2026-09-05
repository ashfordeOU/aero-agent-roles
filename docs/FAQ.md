# Aero Agent Roles FAQ

Answers grounded in the repo as it stands. Where a claim points at an
artifact, the artifact is named so you can check it yourself.

## What is a "role" here?

A role is an executable WORKER: a domain engine (`core/*_core.py`) plus
a CLI that builds a real engineering deliverable (certification plan,
compliance matrix, audit report, analysis memo), gate-checks it, and
emits an evidence bundle. It is not a job description or a prompt.

## How is Aero Agent Roles different from Aero Agent Skills?

Aero Agent Skills is the knowledge substrate — verified methods
(SKILL.md leaves with logic). Aero Agent Roles is the capability layer —
workers that BIND those skills into end-to-end deliverables with
computed numbers, gates, and provenance. Skills = knowledge. Roles =
capability that uses the knowledge.

## What does "verified" mean?

For each role: a replayable offline test suite that passes
(`make validate`, 5 gates: role-lint, role-tests, no-verbatim, security,
manifest) plus the 100% audit (audit-100.sh: core + cli + filled
template + tests per role). When the Aero Agent Skills library is
present, the role dispatches bound leaf logic and cross-checks its own
computed numbers against the leaf's — agreement is recorded in
provenance.json. "Verified" = the gate battery passes on the commit you
are looking at.

## Is Aero Agent Roles certified?

No. Aero Agent Roles is not a certification body, and nothing here is
approved by FAA, EASA, RTCA, SAE, IAQG, or any government for any
specific program. Roles encode methodology and compute numbers from
public engineering rules; the standards themselves remain the authority
and must be purchased from their publishers (STANDARDS.md). Every
deliverable is a DRAFT for human review and explicitly not an approval.

## Can a role sign off or approve anything?

No. Every generated deliverable carries a code-enforced
DRAFT / not-an-approval marker. A role ends where a human (DER, CVE,
designated engineer) begins.

## What is the export-control status?

Aero Agent Roles is an open, unrestricted library of civil aerospace
engineering methodology for AI agents, published by Ashforde OÜ
(Estonia) under Apache-2.0. The content is educational: general
engineering principles, processes, and tool-usage guidance. It is not
ITAR/EAR-controlled technical data, and no proprietary standards text
is reproduced. Standards are referenced and summarized only (see
STANDARDS.md). As published, this library falls within the EU dual-use
"public domain" exclusion (Annex I General Technology Note, Regulation
(EU) 2021/821). Users are solely responsible for their own compliance.

## Are roles affiliated with RTCA, SAE, EASA, FAA, or any government?

No. Not affiliated with or endorsed by RTCA, EUROCAE, SAE International,
IAQG, EASA, FAA, or any government. Standards references are
informational only.

## Why is the npm package not published yet?

The npm package (`aero-agent-roles`) is wired and smoke-tested but
intentionally `private: true`. npm publish is a deliberate, versioned
release action with real registry history — it is cut from the
just-published public tree at a role-count milestone (v1.1.0 @ 25 roles)
the same way Aero Agent Skills releases are managed. See
`scripts/release-manager.py`.

## How do I add a role or request one?

Read CONTRIBUTING.md and docs/ROLE-STANDARD.md. The repo grows in role
waves selected deterministically by `scripts/wave-planner.py` from
coverage gaps in the Aero Agent Skills library. If you need a specific
role, open an issue naming the skills family / deliverable you want.

## What is the license?

Apache-2.0. See LICENSE · NOTICE · SECURITY.md · CONTRIBUTING.md ·
STANDARDS.md · CODE_OF_CONDUCT.md. Standards referenced within roles
remain the property of their respective publishers.

## Who maintains this?

Aero Agent Roles is built and maintained by Ashforde OÜ (Estonia).
Copyright © 2026 Ashforde OÜ.
