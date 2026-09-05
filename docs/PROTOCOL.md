# Role Evidence Protocol (v1)

Every Aero Agent Role emits a **structured evidence bundle** alongside
its deliverable, so ANY harness (Claude Code, Codex, Cursor, Hermes, a
CI pipeline, a human) can consume the result programmatically. This is
the role layer's protocol contract.

## Output layout

A role run produces, under the output directory (default: alongside the
deliverable, in `evidence/`):

```
<deliverable>.md                 human-readable deliverable (report,
                                 matrix, PSAC, memo ...)
evidence/
  model.json                     the computed content model: every number,
                                 every row, every verdict, as data
  gates.json                     evidence-gate verdicts: PASS/FAIL per gate
                                 plus the overall result + exit semantics
  provenance.json                where each number came from: role core
                                 function + bound skill leaf + skill logic
                                 file (when dispatch ran) + version pins
```

## File contracts

### model.json
The full computed model as emitted by the role's `build_<deliverable>()`.
Schema is role-specific but MUST be plain JSON (no functions, no NaN),
MUST round-trip, and MUST contain every number that appears in the
markdown deliverable (the markdown is a rendering of this model).

Top-level keys every model carries:
```json
{
  "schema_version": 1,
  "role": "structures-loads-engineer",
  "deliverable_type": "loads + strength report",
  "item": {"name": "...", "...": "input facts"},
  "generated": "2026-09-05T...",
  "status": "draft-for-review",
  "...": "role-specific computed content"
}
```

### gates.json
```json
{
  "schema_version": 1,
  "role": "structures-loads-engineer",
  "checker": "check_report",
  "gates": [
    {"gate": "level_identified", "pass": true, "detail": "..."},
    {"gate": "...", "pass": false, "detail": "..."}
  ],
  "all_pass": true,
  "exit_code": 0
}
```
`exit_code` mirrors the CLI exit: 0 = all_pass, 1 = any gate failed.
Harnesses SHOULD treat a non-zero `exit_code` as "deliverable rejected".

### provenance.json
```json
{
  "schema_version": 1,
  "role": "structures-loads-engineer",
  "core": {
    "file": "core/structures_loads_core.py",
    "functions": ["gust_load_factor", "vn_diagram", "..."],
    "version": "0.1.0"
  },
  "skills": [
    {
      "leaf": "structures/loads/gust-maneuver-loads",
      "skill_md": "SKILL.md",
      "logic_file": "scripts/gust_load_logic.py",
      "function": "gust_load_factor",
      "dispatched": true,
      "core_value": 2.51,
      "skill_value": 2.51,
      "delta": 0.0,
      "agrees": true,
      "skills_release": "v1.3.0+"
    }
  ],
  "disclaimer": "DRAFT for human review. Not an approval document."
}
```
`dispatched: false` means no skill logic was available for that stage
(role core ran standalone); the role is still valid, just not
cross-checked for that number.

## Cross-check semantics (skill dispatch)

When a bound skill leaf ships a logic file, the role MAY dispatch it
and compare against the core's own computation:

- `delta` = |core − skill| (in the number's natural units, or relative
  when units differ)
- `agrees: true` when delta ≤ the role's tolerance (recorded in the
  provenance row; default 1e-6 for identical formulas, up to 1e-2 for
  analytic approximations)
- The bundle records BOTH values. A human or harness can see two
  independent implementations agreeing — the strongest available
  evidence short of physical test.

## CLI contract (all roles)

```
python3 cli.py build [--out <file.md>] [--bundle] [--profile <p.json>]
    # --bundle  also write evidence/{model,gates,provenance}.json
    # --profile apply a customer/program profile (basis, regs, formats)
python3 cli.py check --file <file.md> [--dal/--level X]
    # exit 0 = PASS, 1 = FAIL (machine-readable via exit code)
```

## Compatibility statement

The bundle is plain JSON + Markdown. Any harness that can run a
terminal command can consume it: parse model.json for numbers, gates.json
for verdicts, provenance.json for sources. No SDK, no server, no
proprietary format.

## Boundary (unchanged, code-enforced)

Every deliverable carries the DRAFT + human-review + not-an-approval
marker. The bundle's `status` and `disclaimer` say the same. Nothing in
this protocol changes the role's certification-honesty boundary.
