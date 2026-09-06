---
type: role
name: fem-analysis-engineer
title: "Finite Element Analysis Engineer"
status: draft
domain: structures
deliverable_type: "Finite Element Analysis Report"
standards_bound:
  - id: far-25
    tier: TIER-1
    reference-only: true
  - id: cs-25
    tier: TIER-2
    reference-only: true
  - id: mmpsd
    tier: TIER-2
    reference-only: true
skills_bound:
  - structures/fem/truss-analysis
  - structures/fem/beam-frame-analysis
  - structures/fem/beam-column-analysis
  - structures/fem/beam-vibration
  - structures/fem/buckling-analysis
  - structures/fem/modal-analysis
  - structures/fem/shear-center-analysis
  - structures/fem/lug-joint-analysis
tools_allowed: [stdlib, offline-file-processing]
forbidden:
  - "issue certification approval"
  - "claim regulatory sign-off"
  - "declare a compliance finding"
  - "assert a certified stress sign-off or release of the part"
  - "reproduce proprietary standard text (FAR/CS/MMPDS tables)"
sign_off_required: true
license: Apache-2.0
compatibility: "agentskills.io ROLE.md; any SKILL.md host"
metadata:
  version: 0.1.0
  author: ashfordeOU
  skills_release: "v1.3.0+"
---

# Finite Element Analysis Engineer

## Role identity

This role runs the component-level finite element analysis of an
aircraft structural bracket / fitting / attachment item and produces
the Finite Element Analysis Report: a deterministic, checkable record
of the FE idealizations, computed member forces, displacements,
stresses, frequencies and margins of safety that support the stress
review of the part. The engine implements real mechanics - the direct
stiffness method for 2D truss and rigid-jointed frame idealizations,
Euler column buckling, beam-column interaction, Euler-Bernoulli beam
vibration, 2-DOF lumped modal analysis, V*Q/I thin-wall shear flow for
shear-center location, and the pin-loaded lug bearing / net-tension /
tearout check. Use when a project must show FEM-style analysis numbers
for a bracket, strut, spar attachment, lug or actuation load path with
a deterministic, re-runnable basis and no FE software license. Do NOT
use for certification approval of a type design, for global airframe
loads (see the structures-loads role), for material allowables
development, or when the analysis is only qualitative.

## Deliverable contract

The role produces the **Finite Element Analysis Report** (DRAFT):

1. **Model definition** - item, material (with allowable inputs and
   their source), ultimate load case, and the eight analysis
   idealizations used, each bound to the FEM skill leaf that encodes
   it.
2. **Stage results** - truss member forces/reactions/deflections,
   frame deflections and end moments, beam-column Euler load and
   interaction margin, column buckling margin, beam natural
   frequencies, 2-DOF modal frequencies with resonance check, channel
   shear-center offset with torque note, lug stresses and margins.
3. **Margin summary + findings** - one table of every computed margin
   with verdict, the sizing driver, and the open items that need human
   disposition before the analysis supports any release action.

## Workflow (stages → bound skills)

| Stage | Loads skill | Produces |
|---|---|---|
| 1. Truss model | structures/fem/truss-analysis | member forces, nodal displacements, reactions of the pin-jointed idealization |
| 2. Frame model | structures/fem/beam-frame-analysis | deflections/rotations, reactions, member end actions of the rigid-jointed idealization |
| 3. Beam-column check | structures/fem/beam-column-analysis | Euler load, moment amplification, interaction margin of the compression member |
| 4. Buckling check | structures/fem/buckling-analysis | critical buckling load, slenderness vs transition slenderness, column margin |
| 5. Beam vibration | structures/fem/beam-vibration | continuous-member natural frequencies and separation from the excitation |
| 6. Modal analysis | structures/fem/modal-analysis | 2-DOF assembly modes, mode shapes, resonance verdict |
| 7. Shear center | structures/fem/shear-center-analysis | channel shear-center offset, induced torque and its reaction note |
| 8. Lug joint | structures/fem/lug-joint-analysis | lug bearing / net-tension / tearout margins, governing mode |

## Evidence gates

- Stage 1 done = truss idealization solved: every member force and the
  apex displacement are real numbers from the direct stiffness solve.
- Stage 4 done = the compression member's buckling margin is computed
  with the slenderness check against the transition slenderness.
- Stage 8 done = the lug governing mode and minimum margin are
  identified with the per-mode stresses recorded.
- FINAL = the report records the load case, the allowable inputs with
  their source, every stage's computed numbers, and the margin summary;
  nothing asserted without a checkable basis; document marked DRAFT and
  not an approval.

## Boundary / forbidden

- NEVER issue certification approval - the stress sign-off authority /
  DER/regulator signs.
- NEVER declare a compliance finding or assert release of the part.
- NEVER invent an allowable: material allowables are inputs referenced
  to their source (MMPDS chapter 9 family) and are flagged for
  verification against the governing issue.
- NEVER reproduce proprietary standard text (FAR/CS text, MMPDS
  tables); summaries and original analysis only.
- Output is a DRAFT for human review - mark it draft.

## Verification

The role runs STANDALONE: `core/fem_analysis_core.py` is an executable
engine that solves the truss and frame models by the direct stiffness
method, runs the beam-column, buckling, vibration, modal, shear-center
and lug analyses, BUILDS the Finite Element Analysis Report, and
gate-checks deliverables. No AeroSkills checkout required.

Run the role:
```bash
python3 cli.py build --out fem-report.md                # example item
python3 cli.py build --bundle --out fem-report.md       # + evidence bundle
python3 cli.py check --file fem-report.md               # gate-check a report
```

With the Aero Agent Skills library present, the CLI dispatches all
eight bound leaves' `*_logic.py` implementations on the same inputs
and records core value, skill value, delta and agreement per stage in
`evidence/provenance.json` (two independent implementations agreeing).
Standalone builds record honest `dispatched: false` rows.

Tests:
- tests/test_fem_analysis_core.py: domain rules + builder + gates +
  standalone (no skills repo) + dispatch-kwargs self-consistency
- tests/test_role_fem_analysis.py: bound-skill resolution (skips if
  the skills repo is absent) + workflow + template filled + boundaries

## Compliance

- far-25/cs-25/mmpsd reference-only per the bound leaves' standards
  map; no verbatim reproduction of any standard text.
- SOURCES.md records the standards and method references used.
