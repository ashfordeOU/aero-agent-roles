# Aero Agent Roles — MCP server (in-repo)

This repo IS an MCP server. The delivery server ships inside the repo and
registers with any host from the repo itself — no external install
required.

## What the server provides

Run it directly:

```bash
node packages/aero-agent-roles/bin/aero-agent-roles.js mcp
# or
npm --prefix packages/aero-agent-roles run mcp
```

Zero dependencies, stdio newline-delimited JSON-RPC 2.0. Tools:

| Tool | What it answers |
|---|---|
| `search_roles` | rank roles against a task |
| `get_role` | full ROLE.md body |
| `list_domains` / `list_roles` | browse |
| `get_standards` | standards register |
| `suggest_role` | **reverse binding** — skill leaf → owning role(s), or task → ranked roles |

Resources (SEP-2640): `role://<slug>` and `role://<domain>` via
`resources/list` + `resources/read`.

## Register from this repo (any host)

```bash
bash scripts/mcp-install.sh
```

The installer (idempotent):
1. Confirms `.mcp.json` exists at the repo root — **that file IS the
   registration** for VS Code, Cursor, Windsurf, Claude Desktop project
   scope, and Gemini CLI. It is committed with repo-relative paths so any
   clone works.
2. Registers project-scope with Claude Code if the CLI is present.
3. Prints the exact Hermes config block (set `HERMES_CONFIG_TARGET=write`
   to have it written for you).
4. Self-verifies with a live `initialize` + `tools/list` round-trip.

## Register a published copy (consumers)

```json
{ "mcpServers": { "aero-agent-roles": { "command": "npx", "args": ["-y", "aero-agent-roles", "mcp"] } } }
```

## CLI mirror

The same binary answers on the command line: `list`, `search`, `show`,
`install`, `where`, `mcp`.

## MCP access policy

Roles may declare `mcp_allowed` / `mcp_blocked` in ROLE.md frontmatter
(default: offline-only). Enforced by `scripts/role-lint.py` (part of
`make validate`). See [docs/MCP-ACCESS.md](docs/MCP-ACCESS.md).

## Smoke coverage

`packages/aero-agent-roles/test/smoke.mjs` covers handshake, tools
(incl. `suggest_role`), resources/list, resources/read, and the CLI in
one offline battery: `npm --prefix packages/aero-agent-roles test`.
