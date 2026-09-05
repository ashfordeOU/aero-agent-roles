// Catalog loader. Answers list/show/search from the bundled manifest.json
// + roles/ tree — offline, deterministic, no telemetry, no network.
//
// Roles are adopted deliberately, not routed by a trigger description the
// way Aero Agent Skills' SKILL.md files are (ROLE.md has no `description`
// field) — search() here is a plain token-overlap match over title,
// deliverable_type, and domain, useful for "what role fits this job"
// browsing, not a claimed parity port of any evaluated router.
'use strict';

const fs = require('node:fs');
const path = require('node:path');

const STOP = new Set([
  'a', 'an', 'the', 'for', 'or', 'and', 'of', 'to', 'in', 'on', 'with',
  'is', 'are', 'was', 'be', 'at', 'by', 'from', 'as', 'into', 'onto',
]);

const TOKEN_RE = /[a-z0-9][a-z0-9-]*/g;

function tokens(text) {
  const out = [];
  for (const m of String(text).toLowerCase().matchAll(TOKEN_RE)) {
    if (!STOP.has(m[0])) out.push(m[0]);
  }
  return out;
}

const PKG_ROOT = path.join(__dirname, '..');

function rolesRoot() {
  // Prefer the repo checkout so a stale prepack payload copy can never
  // shadow the live tree in development; installed packages have no
  // ../../roles and fall through to the bundled copy.
  const repo = path.join(PKG_ROOT, '..', '..', 'roles');
  if (fs.existsSync(repo) && fs.existsSync(path.join(PKG_ROOT, '..', '..', 'manifest.json'))) return repo;
  const bundled = path.join(PKG_ROOT, 'roles');
  if (fs.existsSync(bundled)) return bundled;
  throw new Error('roles tree not found (looked for the repo checkout and a bundled roles/)');
}

function loadManifest() {
  return JSON.parse(fs.readFileSync(path.join(PKG_ROOT, 'manifest.json'), 'utf8'));
}

function version() {
  return JSON.parse(fs.readFileSync(path.join(PKG_ROOT, 'package.json'), 'utf8')).version;
}

class Catalog {
  constructor() {
    this.root = rolesRoot();
    this.manifest = loadManifest();
    this._tok = new Map();
  }

  get roles() {
    return this.manifest.roles;
  }

  find(slug) {
    return this.manifest.roles.find((r) => r.slug === slug);
  }

  readRoleMd(slug) {
    return fs.readFileSync(path.join(this.root, slug, 'ROLE.md'), 'utf8');
  }

  _tokensFor(role) {
    let t = this._tok.get(role.slug);
    if (!t) {
      t = {
        haystack: new Set(tokens(`${role.title} ${role.deliverable_type} ${role.domain} ${role.slug}`)),
      };
      this._tok.set(role.slug, t);
    }
    return t;
  }

  score(role, query) {
    const q = new Set(tokens(query));
    if (q.size === 0) return 0;
    const t = this._tokensFor(role);
    let s = 0;
    for (const w of q) if (t.haystack.has(w)) s += 1;
    return s;
  }

  search(query, limit = 5) {
    const scored = this.manifest.roles.map((r) => ({ role: r, score: this.score(r, query) }));
    scored.sort((a, b) => b.score - a.score
      || (a.role.slug < b.role.slug ? -1 : a.role.slug > b.role.slug ? 1 : 0));
    return scored.filter((s) => s.score > 0).slice(0, limit);
  }
}

module.exports = { Catalog, tokens, version, PKG_ROOT };
