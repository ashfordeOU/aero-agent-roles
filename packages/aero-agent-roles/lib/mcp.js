// MCP server over stdio: newline-delimited JSON-RPC 2.0, zero dependencies.
// Same wire protocol and host-config shape as Aero Agent Skills' MCP
// server (JetBrains AI Assistant/Junie, Claude Desktop, VS Code, Cursor,
// Windsurf all speak this identically) — implements initialize, ping,
// tools/list, tools/call, plus the SEP-2640 resources model
// (resources/list, resources/read over role:// URIs) so roles are
// discoverable as resources, not only through tool calls. Anything else
// gets -32601, and requests without an id are notifications and never
// answered. Offline: every answer comes from the bundled manifest — no
// network, ever.
'use strict';

const { Catalog, tokens, version } = require('./catalog');
const fs = require('fs');
const path = require('path');

/* Reverse binding index: skill leaf path -> [role slugs that bind it].
   Built once from ROLE.md frontmatter (skills_bound), cached. Lets a host
   answer "which role owns the deliverable for this skill?" offline. */
let _reverseCache = null;
function reverseIndex(catalog) {
  if (_reverseCache) return _reverseCache;
  const inv = new Map();
  const root = catalog.root; // roles tree (repo checkout or bundled)
  for (const r of catalog.roles) {
    const roleMd = path.join(root, r.slug, 'ROLE.md');
    let text = '';
    try { text = fs.readFileSync(roleMd, 'utf8'); } catch (e) { continue; }
    const m = text.match(/^---\n([\s\S]*?)\n---/);
    if (!m) continue;
    const fm = m[1];
    const block = fm.match(/^skills_bound:([\s\S]*?)(?=^[a-z_]+:|\Z)/m);
    if (!block) continue;
    for (const lm of block[1].matchAll(/^\s+-\s+([a-z0-9\-/]+)/gm)) {
      const leaf = lm[1];
      if (!inv.has(leaf)) inv.set(leaf, []);
      inv.get(leaf).push(r.slug);
    }
  }
  _reverseCache = inv;
  return _reverseCache;
}

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
  {
    name: 'suggest_role',
    description: 'Reverse binding: given a bound skill leaf path (e.g. avionics/do178c/planning) '
      + 'or a task in plain words, return the role(s) that own the end-to-end deliverable for it. '
      + 'Use when a loaded skill says "who executes this method?" — the role pulls the skill '
      + 'forward; this tool inverts the map. For a task query it ranks roles by title/domain overlap.',
    inputSchema: {
      type: 'object',
      properties: {
        skill: { type: 'string', description: 'Bound skill leaf path (family/pack/skill).' },
        task: { type: 'string', description: 'Plain-words task to rank roles for (alternative to skill).' },
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
    case 'suggest_role': {
      const inv = reverseIndex(catalog);
      if (args.skill) {
        const skill = String(args.skill).replace(/\/+$/, '');
        const roles = inv.get(skill) || [];
        if (roles.length === 0) {
          const prefixHits = [...inv.entries()].filter(([p]) => p.startsWith(skill + '/')).slice(0, 10);
          if (prefixHits.length === 0) return toolError(`no role binds skill '${skill}' (unbound leaf — wave candidate).`);
          return text(`leaves under ${skill} bound by roles:\n` + prefixHits.map(([p, rs]) => `${p}: ${rs.join(', ')}`).join('\n'));
        }
        return text(`${skill}\n  bound by roles:\n` + roles.map((r) => `    -> roles/${r}/ROLE.md`).join('\n'));
      }
      if (args.task) {
        const q = new Set(tokens(String(args.task)));
        const scored = catalog.roles.map((r) => {
          const hay = new Set(tokens(`${r.title} ${r.deliverable_type} ${r.domain} ${r.slug}`));
          let s = 0; for (const w of q) if (hay.has(w)) s += 1;
          return { r, s };
        }).filter((x) => x.s > 0).sort((a, b) => b.s - a.s || (a.r.slug < b.r.slug ? -1 : 1)).slice(0, 8);
        if (scored.length === 0) return toolError('no role matches that task. Call list_domains to browse.');
        return text(scored.map(({ r, s }) => `${r.slug} (score ${s}): ${r.title} — ${r.deliverable_type}`).join('\n'));
      }
      return toolError('suggest_role needs a skill leaf path or a task query.');
    }
    default:
      return toolError(`unknown tool '${name}'`);
  }
}

function resourcesList(catalog) {
  // SEP-2640: roles are resources under the role:// namespace. Every role
  // is listed so hosts can enumerate without guessing slugs; domains are
  // collection URIs.
  const out = [];
  const seen = new Set();
  const push = (uri, name, kind) => {
    if (seen.has(uri)) return;
    seen.add(uri);
    out.push({ uri, name, mimeType: 'text/markdown', description: `${kind} — ${name}` });
  };
  for (const r of catalog.roles) {
    push(`role://${r.slug}`, r.slug, 'role');
    push(`role://${r.domain}`, r.domain, 'role domain');
  }
  push('role://', 'role bank root', 'role');
  return out;
}

function readResource(catalog, uri) {
  const u = String(uri || '');
  if (u === 'role://' || u === 'role:') {
    return text(`Aero Agent Roles — resource root\n\nDomains:\n${domainsSummary(catalog)}\n\nLoad a domain or role with role://<domain> or role://<slug>\n`);
  }
  if (!u.startsWith('role://')) return toolError(`unknown resource uri '${uri}' (expected role://…)`);
  const path = u.slice('role://'.length).replace(/\/+$/, '');
  if (!path) return text(`Aero Agent Roles — resource root\n\n${domainsSummary(catalog)}\n`);
  const role = catalog.find(path);
  if (role) return text(catalog.readRoleMd(role.slug));
  const inDomain = catalog.roles.filter((r) => r.domain === path);
  if (inDomain.length > 0) {
    return text(`${path} — ${inDomain.length} roles\n` + inDomain.map((r) => `${r.slug}: ${r.title} — ${r.deliverable_type}`).join('\n'));
  }
  return toolError(`no role or domain '${path}'. Closest: ${catalog.search(path.replace(/-/g, ' '), 3).map((h) => h.role.slug).join(', ') || 'none'}`);
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
          capabilities: {
            tools: { listChanged: false },
            resources: { subscribe: false, listChanged: false },
          },
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
      case 'resources/list':
        try {
          return reply(req.id, { resources: resourcesList(catalog) });
        } catch (e) {
          return reply(req.id, undefined, { code: -32603, message: `resources/list failed: ${e.message}` });
        }
      case 'resources/read':
        try {
          const uri = req.params && req.params.uri;
          const res = readResource(catalog, uri);
          return reply(req.id, { contents: [{ uri, mimeType: 'text/markdown', text: res.content[0].text }] });
        } catch (e) {
          return reply(req.id, undefined, { code: -32603, message: `resources/read failed: ${e.message}` });
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

module.exports = { serve, callTool, TOOLS, resourcesList, readResource };
