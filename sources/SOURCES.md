# Aero Agent Roles — shared source register (TIER 1-4)

Every deep role traces its claims to an owned, tiered, verified source
(program Part C). Per-role registers live at roles/<slug>/SOURCES.md;
this file is the cross-repo view.

## Tiers
- TIER-1 public-domain/free: FAR/CS, NASA, MIL-STD, EASA free — quotable.
- TIER-2 proprietary-sold: DO-178C, DO-254, ARP4754A/4761A, AS9100/9102,
  ISO 19011/9001 — READ to extract process; NEVER reproduce.
- TIER-3 textbooks: Raymer, Roskam, Anderson, Torenbeek, Megson.
- TIER-4 research papers: AIAA etc.

## Register

| Standard | Tier | Needed by role | Acquisition | Cost est. |
|---|---|---|---|---|
| RTCA DO-178C / ED-12C | 2 | do178c-cert-engineer | NEEDED (founder) | ~$400 |
| RTCA DO-330 | 2 | do178c-cert-engineer | NEEDED | ~$250 |
| SAE ARP4754A | 2 | do178c + airworthiness | NEEDED (shared) | ~$200 |
| SAE ARP4761A | 2 | (future systems-safety) | NEEDED | ~$200 |
| AS9100D | 2 | as9100-quality-auditor | NEEDED | ~$150 |
| AS9102 | 2 | as9100-quality-auditor | NEEDED | ~$100 |
| ISO 19011 | 2 | as9100-quality-auditor | NEEDED | ~$120 |
| ISO 9001:2015 | 2 | as9100-quality-auditor | NEEDED | ~$120 |
| FAA AC 20-115D | 1 | do178c-cert-engineer | owned (free) | $0 |
| EASA AMC 20-115C | 1 | do178c-cert-engineer | owned (free) | $0 |
| 14 CFR Part 21/25 | 1 | airworthiness-compliance | owned (free) | $0 |
| EASA CS-25/Part 21 | 1 | airworthiness-compliance | owned (free) | $0 |
| IAQG public guides | 1 | as9100-quality-auditor | owned (free) | $0 |

**First-cohort buy-list total: ~$1,540** (DO-178C + DO-330 + ARP4754A +
AS9100D + AS9102 + ISO 19011 + ISO 9001). Founder per-purchase GO
required (money > €50 rule). See roles/*/SOURCES.md for per-role detail.

## Storage rule
Owned PDFs live OUTSIDE the git repo (git-ignored, license-aware).
Extraction output (process notes, summaries, cross-refs) is committed —
never the verbatim standard text.
