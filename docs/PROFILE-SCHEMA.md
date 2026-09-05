# Program Profile Schema (v1) — customer tailoring for roles

A program profile is a JSON file that tailors a role to a specific
customer program. One role engine serves every customer: the profile
carries the basis, the regs/standards set, deliverable format, and
sign-off chain. Profiles are inputs, never code.

## Schema

```json
{
  "schema_version": 1,
  "customer": "Example Airframers Ltd",
  "program": "FGS-2000 autopilot certification",
  "basis": "FAR-25",                 // FAR-25 | CS-25 | AS9100D | ...
  "authority": "FAA",                // cert authority / registrar
  "der": "ACME DER, delegated for systems & equipment (FAA)",
  "standards": ["DO-178C", "DO-330", "ARP4754A"],
  "regs": ["25.1309", "25.301", "25.571"],
  "deliverable_format": "customer-psac",  // format variant the customer expects
  "sign_off_chain": ["Lead SW Engineer", "DER"],
  "document_prefix": "FGS-SW-PSAC",
  "revision": "Rev A",
  "notes": "free text for the role: customer conventions, tool names"
}
```

## Role behavior under a profile

When `--profile <file.json>` is passed to `cli.py build`:

1. The role loads the profile and applies it to the item/example:
   - `basis` and `authority` appear in the deliverable header
   - `document_prefix` + `revision` label the document
   - `customer`/`program`/`der`/`sign_off_chain` appear in the sign-off
     section (never as approval — still DRAFT for human review)
   - `standards`/`regs` filter or annotate which bound sources the role
     cites (roles already bind the relevant leaves)
   - `notes` are surfaced as context in the deliverable preamble
2. When no profile is given, the role uses its built-in example item
   and generic basis (the current behavior — unchanged).

## Honesty boundary (unchanged)

A profile tailors the deliverable SHAPE and CONTEXT. It does NOT make
the role claim approval, issue a finding, or certify. The DRAFT /
human-review / not-an-approval marker is code-enforced regardless of
profile. Profiles never carry credentials, paths, or secrets.

## Examples in this directory

- examples/example-airframer.json   (FAR-25 transport program)
- examples/easa-supplier.json       (CS-25 EASA supplier)
