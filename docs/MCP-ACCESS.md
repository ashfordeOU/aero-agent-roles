# MCP Access Policy (roles + skills)

Both Aero Agent Roles (`ROLE.md` frontmatter) and Aero Agent Skills
(`SKILL.md` frontmatter) carry the same optional MCP access grammar.
The rule is enforced by `scripts/role-lint.py` (roles repo) and
`scripts/spec_lint.py` (AeroSkills repo, gate 1).

## Default: offline-only

**Absent `mcp_allowed` means the role/skill is offline-only.** It runs on
its own content, stdlib logic files, and local templates — never on live
MCP servers. This is the deterministic 100% standard and remains the
default for the whole library. A host that offers MCP servers must not
assume a role/skill wants them.

## Grammar

```yaml
# Optional. Omit entirely for an offline-only role/skill.
mcp_allowed:
  - aero-agent-skills:read   # consult the skills library over MCP
  - aero-agent-roles:read    # consult the role bank over MCP
mcp_blocked:
  - worldintel               # hard deny; wins over mcp_allowed
```

- `mcp_allowed`: non-empty list of `<server>:<read|write>` entries.
- `mcp_blocked`: list of server names never reachable for this item.
- Any server NOT in `mcp_allowed` is blocked, even without `mcp_blocked`.
- `mcp_blocked` without `mcp_allowed` is redundant and rejected by lint.

## Semantic

- `read`  = search/list/read resources and tools on that server.
- `write` = call mutating tools (create, update, publish, send).
- A role/skill declaring `mcp_allowed` is still gated: every deliverable
  keeps its DRAFT / not-an-approval markers and evidence gates. MCP
  access widens inputs, never weakens the boundary.

## Why

The founder asked (2026-09-08) whether Aero skills/roles can do MCP tool
calls, serve as plugins, and carry reference files. Answers:

1. **MCP tool calls** — yes, when the host has the server and the
   role/skill declares it in `mcp_allowed`. Delivery servers ship in
   `packages/*/lib/mcp.js` and speak stdio JSON-RPC (zero deps).
2. **Plugin** — the npm packages register MCP servers; Hermes loads them
   via `mcp_servers` config; Claude Code via `claude mcp add`.
3. **Reference files** — roles carry `SOURCES.md`, `templates/`,
   `core/`; skills carry `references/`, `scripts/`, `assets/`.

## Enforcement

- Roles repo: `python3 scripts/role-lint.py` (part of `make validate`).
- AeroSkills: `bash scripts/gate-spec-lint.sh` (gate 1, part of the
  5-gate battery).
