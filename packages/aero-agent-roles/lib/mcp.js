// MCP server over stdio: newline-delimited JSON-RPC 2.0, zero dependencies.
// Same wire protocol and host-config shape as Aero Agent Skills' MCP
// server (JetBrains AI Assistant/Junie, Claude Desktop, VS Code, Cursor,
// Windsurf all speak this identically) — implements initialize, ping,
// tools/list, tools/call; anything else gets -32601, and requests without
// an id are notifications and never answered. Offline: every answer comes
// from the bundled manifest — no network, ever.
'use strict';

const { Catalog, version } = require('./catalog');

const TOOLS = [
  {
    name: 'search_roles',
    description: 'Search Aero Agent Roles by plain-text match over title, deliverable type, and '
      + 'domain. Use when a task needs a role that owns an end-to-end aerospace-engineering '
      + 'deliverable (a certification plan, a compliance matrix, an analysis report), not just a '
      + 'single skill. Returns ranked role slugs; load the winner with get_role.',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'The deliverable or job, in plain words.' },
        limit: { type: 'integer', minimum: 1, maximum: 25, description: 'Max results (default 5).' },
      },
      required: ['query'],
      additionalProperties: false,
    },
  },
  {
    name: 'get_role',
    description: 'Fetch one complete ROLE.md by slug (e.g. do178c-cert-engineer). Use after '
      + 'search_roles or list_roles to load the full contract: the ordered workflow stages, the '
      + 'evidence gate per stage, the bound skills and standards, forbidden actions, and the human '
      + 'sign-off stop.',
    inputSchema: {
      type: 'object',
      properties: {
        slug: { type: 'string', description: 'Role slug as returned by search_roles or list_roles.' },
      },
      required: ['slug'],
      additionalProperties: false,
    },
  },
  {
    name: 'list_domains',
    description: 'List the engineering domains with their role and skills-bound counts. Use to get '
      + 'an overview of what the role bank covers before searching or browsing.',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  },
  {
    name: 'list_roles',
    description: 'List roles, optionally filtered to one domain. Use to browse a discipline; each '
      + 'entry gives the slug to pass to get_role.',
    inputSchema: {
      type: 'object',
      properties: {
        domain: { type: 'string', description: 'Domain, e.g. avionics.' },
      },
      additionalProperties: false,
    },
  },
  {
    name: 'get_standards',
    description: 'Look up the machine-readable aerospace standards register: publisher, whether '
      + 'verbatim text is gated, and which roles bind it. Use when a task cites a standard '
      + '(DO-178C, ARP4754A, AS9100, CS-25, ECSS, ...) and you need its scope or handling rules. '
      + 'Omit id to list all.',
    inputSchema: {
      type: 'object',
      properties: {
        id: { type: 'string', description: 'Standard id, e.g. do-178c (case-insensitive).' },
      },
      additionalProperties: false,
    },
  },
];

function text(t) {
  return { content: [{ type: 'text', text: t }], isError: false };
}

function toolError(t) {
  return { content: [{ type: 'text', text: t }], isError: true };
}

function domainsSummary(catalog) {
  const doms = new Map();
  for (const r of catalog.roles) {
    const d = doms.get(r.domain) || { roles: 0, skills_bound: 0 };
    d.roles += 1;
    d.skills_bound += r.skills_bound;
    doms.set(r.domain, d);
  }
  return [...doms.entries()].sort()
    .map(([name, d]) => `${name}: ${d.roles} roles, ${d.skills_bound} skills bound`)
    .join('\n');
}

function callTool(catalog, name, args) {
  args = args || {};
  switch (name) {
    case 'search_roles': {
      if (!args.query || !String(args.query).trim()) return toolError('query is required');
      const limit = Math.min(Math.max(args.limit || 5, 1), 25);
      const hits = catalog.search(String(args.query), limit);
      if (hits.length === 0) return toolError('no role matches that query. Call list_domains or list_roles to browse.');
      return text(hits.map((h, i) => `${i + 1}. ${h.role.slug} (score ${h.score})\n   ${h.role.title} — ${h.role.deliverable_type}`).join('\n\n'));
    }
    case 'get_role': {
      const role = catalog.find(String(args.slug || ''));
      if (!role) {
        const near = catalog.search(String(args.slug || '').replace(/-/g, ' '), 3)
          .map((h) => h.role.slug).join(', ');
        return toolError(`no role '${args.slug}'. Closest: ${near || 'none'}.`);
      }
      return text(catalog.readRoleMd(role.slug));
    }
    case 'list_domains':
      return text(domainsSummary(catalog));
    case 'list_roles': {
      let roles = catalog.roles;
      if (args.domain) roles = roles.filter((r) => r.domain === args.domain);
      if (roles.length === 0) return toolError('no roles match that domain filter. Call list_domains first.');
      return text(roles.map((r) => `${r.slug}: ${r.title} — ${r.deliverable_type}`).join('\n'));
    }
    case 'get_standards': {
      let standards = catalog.manifest.standards;
      if (args.id) {
        const id = String(args.id).toLowerCase();
        standards = standards.filter((s) => s.id.toLowerCase() === id);
        if (standards.length === 0) return toolError(`no standard with id '${args.id}'. Omit id to list all.`);
      }
      return text(standards.map((s) =>
        `${s.id}: ${s.name}\n  publisher: ${s.publisher}${s.gated ? ' (gated: no verbatim text)' : ''}\n  roles: ${s.roles.join(', ')}`)
        .join('\n\n'));
    }
    default:
      return toolError(`unknown tool '${name}'`);
  }
}

function serve() {
  const catalog = new Catalog();
  let buffer = '';

  const reply = (id, result, error) => {
    const msg = { jsonrpc: '2.0', id };
    if (error) msg.error = error;
    else msg.result = result;
    process.stdout.write(JSON.stringify(msg) + '\n');
  };

  const handle = (req) => {
    const isNotification = req.id === undefined || req.id === null;
    switch (req.method) {
      case 'initialize':
        return reply(req.id, {
          protocolVersion: (req.params && req.params.protocolVersion) || '2025-06-18',
          capabilities: { tools: { listChanged: false } },
          serverInfo: { name: 'aero-agent-roles', version: version() },
        });
      case 'ping':
        return reply(req.id, {});
      case 'tools/list':
        return reply(req.id, { tools: TOOLS });
      case 'tools/call':
        try {
          return reply(req.id, callTool(catalog, req.params && req.params.name, req.params && req.params.arguments));
        } catch (e) {
          return reply(req.id, toolError(`tool failed: ${e.message}`));
        }
      default:
        if (isNotification) return undefined;
        return reply(req.id, undefined, { code: -32601, message: `method not found: ${req.method}` });
    }
  };

  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (chunk) => {
    buffer += chunk;
    let nl;
    while ((nl = buffer.indexOf('\n')) !== -1) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (!line) continue;
      let req;
      try {
        req = JSON.parse(line);
      } catch {
        reply(null, undefined, { code: -32700, message: 'parse error' });
        continue;
      }
      handle(req);
    }
  });
  process.stdin.on('end', () => process.exit(0));
}

module.exports = { serve, callTool, TOOLS };
