# aero-agent-roles

**The role layer for aerospace engineering agents** — professional roles that bind verified [Aero Agent Skills](https://github.com/ashfordeOU/aero-agent-skills) into end-to-end deliverables, with evidence gates and a human sign-off stop, shipped as an npm CLI and an MCP server. Built and maintained by [Ashforde OÜ](https://ashforde.org).

> **Not yet published.** This package is wired and tested (`make package-test`) but `private: true` in `package.json` — npm refuses to publish it until that is deliberately removed. Ready to release, not released.

Full role bank, figures, and provenance: [github.com/ashfordeOU/aero-agent-roles](https://github.com/ashfordeOU/aero-agent-roles) · [ashforde.org/aeroagentroles](https://ashforde.org/aeroagentroles)

Each role is gated by a replayable offline battery (structure lint, offline behavior tests, no-verbatim sweep, security tripwire, manifest-matches-tree). This package bundles the tree at the released commit; live counts come from `aero-roles list`, never from this README.

## CLI

```bash
npm i -g aero-agent-roles   # or: npx aero-agent-roles <command>

aero-roles list                                    # domains, roles, skills bound
aero-roles search "DO-178C certification plan"
aero-roles show do178c-cert-engineer
aero-roles install do178c-cert-engineer --dest ./roles
```

`install` copies a role's full folder (`ROLE.md`, `templates/`, `tests/`, `core/`, `cli.py`) to `--dest <dir>` (`--link` symlinks instead of copying). A role is **not** an agent-router skill — `ROLE.md` has no trigger `description` the way `SKILL.md` does — so `install` does not register a role with any host's skill router; it hands you the files to run directly (`python3 <dest>/<slug>/cli.py build --bundle`) or to point an agent at by path.

## MCP server

Works in any Model Context Protocol host: JetBrains AI Assistant and Junie, Claude Desktop, Claude Code, VS Code, Cursor, Windsurf, Gemini CLI.

```json
{
  "mcpServers": {
    "aero-agent-roles": {
      "command": "npx",
      "args": ["-y", "aero-agent-roles", "mcp"]
    }
  }
}
```

Tools: `search_roles` (title/deliverable/domain match), `get_role` (full `ROLE.md`), `list_domains`, `list_roles`, `get_standards` (the machine-readable standards register: publisher, gated flag, which roles bind it).

## What a role is

A folder with a `ROLE.md`: YAML frontmatter (identity, deliverable type, bound standards + skills), a body the agent follows (ordered workflow stages, an evidence gate per stage, forbidden actions, the human sign-off stop), an executable domain engine (`core/*.py` + `cli.py`) that computes the real deliverable offline, and an offline behavior-contract test.

Every role ends at the same line: **the human sign-off**. Roles produce draft deliverables with evidence. They never issue certification approval, declare compliance findings, or claim regulatory sign-off.

## License

Apache-2.0 © Ashforde OÜ (Estonia). Not affiliated with or endorsed by RTCA, EUROCAE, SAE International, IAQG, EASA, FAA, or any government.
