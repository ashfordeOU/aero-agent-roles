#!/usr/bin/env bash
# mcp-install.sh — register this repo's MCP server with the hosts found on
# this machine. Keeps MCP usable from INSIDE the repo on any clone: editors
# read .mcp.json at the project root (committed), Claude Code gets a
# project-scope registration, Hermes gets a config snippet. Idempotent.
# Run:  bash scripts/mcp-install.sh [--verify-only]
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
server="node packages/aero-agent-roles/bin/aero-agent-roles.js mcp"
name="aero-agent-roles"
mcp_json="$repo_root/.mcp.json"

echo "== Aero Agent Roles — MCP installer =="
echo "repo:  $repo_root"

if [ -f "$mcp_json" ]; then
  echo "ok    .mcp.json present (repo-relative paths, portable)"
else
  echo "FAIL  .mcp.json missing at repo root — refusing to continue"
  exit 1
fi

if command -v claude >/dev/null 2>&1; then
  out="$(claude mcp add --scope project "$name" -- node "packages/aero-agent-roles/bin/aero-agent-roles.js" mcp 2>&1 || true)"
  case "$out" in
    *"already exists in .mcp.json"*) echo "ok    claude code: '$name' already in .mcp.json (project scope)";;
    *"Added"*|*"updated"*) echo "ok    claude code: registered '$name' (project scope)";;
    *) echo "warn  claude code: $out";;
  esac
else
  echo "skip  claude code CLI not found"
fi

if [ "${HERMES_CONFIG_TARGET:-}" = "write" ] && command -v hermes >/dev/null 2>&1; then
  hermes config set "mcp_servers.$name.command" node
  hermes config set "mcp_servers.$name.args" "[\"$repo_root/packages/aero-agent-roles/bin/aero-agent-roles.js\", \"mcp\"]"
  hermes config set "mcp_servers.$name.enabled" true
  echo "ok    hermes: wrote mcp_servers.$name into hermes config"
else
  echo "hint  hermes: add this to ~/.hermes/config.yaml under mcp_servers:"
  cat <<EOF
  $name:
    command: node
    args:
      - $repo_root/packages/aero-agent-roles/bin/aero-agent-roles.js
      - mcp
    enabled: true
EOF
fi

echo "== self-verify =="
if (cd "$repo_root" && printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"installer","version":"0"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | node packages/aero-agent-roles/bin/aero-agent-roles.js mcp 2>/dev/null \
  | python3 -c 'import json,sys
lines=[json.loads(l) for l in sys.stdin if l.strip()]
tools=lines[-1].get("result",{}).get("tools",[]) if lines else []
print(f"tools: {len(tools)}") if tools else print("FAIL no tools") or sys.exit(1)'); then
  echo "PASS  MCP server reachable and answering tools/list"
else
  echo "FAIL  MCP server did not answer — check node and the package path"
  exit 1
fi
echo "== done =="
