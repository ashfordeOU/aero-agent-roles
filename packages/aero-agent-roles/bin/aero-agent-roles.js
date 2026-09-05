#!/usr/bin/env node
// aero-agent-roles CLI: list / search / show / install / where / mcp.
// Everything answers from the bundled tree + generated manifest — offline,
// deterministic, no telemetry, no network.
'use strict';

const { Catalog, version } = require('../lib/catalog');
const { install } = require('../lib/install');

const HELP = `aero-agent-roles ${version()} — the role layer for aerospace engineering agents (Ashforde OU)

Usage:
  aero-roles list [domain]                  browse domains, roles
  aero-roles search <job words...>          match roles by title/deliverable/domain
  aero-roles show <role-slug>                print one ROLE.md
  aero-roles install <role-slug...> --dest <dir>
      --dest <dir>                          required: destination directory
      --link                                symlink instead of copy
      selector: all | <role-slug> (default: all)
  aero-roles mcp                            run the MCP server on stdio
  aero-roles where                          print the bundled roles root
  aero-roles version

MCP host config (JetBrains AI Assistant/Junie, Claude Desktop, VS Code, Cursor, Windsurf):
  {"mcpServers":{"aero-agent-roles":{"command":"npx","args":["-y","aero-agent-roles","mcp"]}}}

Note: a role is not an agent-router skill (ROLE.md has no trigger
description) — install copies role folders for direct/CLI use, it does
not register them with any host's skill router.
`;

function parseFlags(argv) {
  const flags = {};
  const rest = [];
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === '--dest') flags.dest = argv[++i];
    else if (argv[i] === '--link') flags.link = true;
    else rest.push(argv[i]);
  }
  return { flags, rest };
}

function cmdList(catalog, domain) {
  if (!domain) {
    const doms = new Map();
    for (const r of catalog.roles) {
      const d = doms.get(r.domain) || { roles: 0, skills_bound: 0 };
      d.roles += 1;
      d.skills_bound += r.skills_bound;
      doms.set(r.domain, d);
    }
    for (const [name, d] of [...doms.entries()].sort()) {
      console.log(`${name.padEnd(28)} ${String(d.roles).padStart(3)} roles ${String(d.skills_bound).padStart(4)} skills bound`);
    }
    console.log(`\n${catalog.manifest.counts.roles} roles, ${catalog.manifest.counts.domains} domains, ${catalog.manifest.counts.skills_bound} skills bound. \`list <domain>\` to drill in.`);
    return;
  }
  const hits = catalog.roles.filter((r) => r.domain === domain);
  if (hits.length === 0) {
    console.error(`nothing under '${domain}'. Run \`aero-roles list\` for domains.`);
    process.exitCode = 1;
    return;
  }
  for (const r of hits) console.log(`${r.slug}: ${r.title} — ${r.deliverable_type}`);
}

function main() {
  const [cmd, ...args] = process.argv.slice(2);
  if (!cmd || cmd === 'help' || cmd === '--help' || cmd === '-h') {
    console.log(HELP);
    return;
  }
  if (cmd === 'version' || cmd === '--version' || cmd === '-v') {
    console.log(version());
    return;
  }
  if (cmd === 'mcp') {
    require('../lib/mcp').serve();
    return;
  }

  const catalog = new Catalog();
  if (cmd === 'list') {
    cmdList(catalog, args[0]);
  } else if (cmd === 'search') {
    const query = args.join(' ').trim();
    if (!query) {
      console.error('usage: aero-roles search <job words...>');
      process.exitCode = 1;
      return;
    }
    const hits = catalog.search(query, 5);
    if (hits.length === 0) {
      console.log('no role matches. Run `aero-roles list` to browse.');
      return;
    }
    for (const [i, h] of hits.entries()) {
      console.log(`${i + 1}. ${h.role.slug}  (score ${h.score})\n   ${h.role.title} — ${h.role.deliverable_type}`);
    }
  } else if (cmd === 'show') {
    const role = catalog.find(args[0] || '');
    if (!role) {
      console.error(`no role '${args[0] || ''}'. Try \`aero-roles search\`.`);
      process.exitCode = 1;
      return;
    }
    process.stdout.write(catalog.readRoleMd(role.slug));
  } else if (cmd === 'install') {
    const { flags, rest } = parseFlags(args);
    try {
      const result = install(catalog, rest, flags);
      for (const item of result.installed) console.log(`${result.linked ? 'linked' : 'installed'} ${item.slug} -> ${item.folder}/`);
      console.log(`\n${result.installed.length} roles ${result.linked ? 'linked' : 'installed'} into ${result.dest}`);
    } catch (e) {
      console.error(e.message);
      process.exitCode = 1;
    }
  } else if (cmd === 'where') {
    console.log(catalog.root);
  } else {
    console.error(`unknown command '${cmd}'\n`);
    console.log(HELP);
    process.exitCode = 1;
  }
}

main();
