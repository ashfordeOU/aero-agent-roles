#!/usr/bin/env node
// Offline smoke battery for the npm package. Fails loud, exits 1.
//
//  1. manifest freshness invariants vs docs/metrics.json
//  2. installer: copy + role-not-found error path
//  3. MCP server: initialize / tools/list / tools/call round-trip on stdio
//  4. CLI: list, search, show
import { spawn, execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const here = path.dirname(fileURLToPath(import.meta.url));
const pkgRoot = path.join(here, '..');
const repoRoot = path.join(pkgRoot, '..', '..');
const require = createRequire(import.meta.url);
const { Catalog } = require('../lib/catalog.js');
const { install } = require('../lib/install.js');
const bin = path.join(pkgRoot, 'bin', 'aero-agent-roles.js');

let failures = 0;
const check = (name, fn) => {
  try {
    fn();
    console.log(`PASS ${name}`);
  } catch (e) {
    failures += 1;
    console.error(`FAIL ${name}: ${e.message}`);
  }
};

const catalog = new Catalog();
const metrics = JSON.parse(fs.readFileSync(path.join(repoRoot, 'docs', 'metrics.json'), 'utf8'));

check('manifest counts match docs/metrics.json', () => {
  assert.equal(catalog.manifest.counts.roles, metrics.roles);
  assert.equal(catalog.manifest.counts.domains, metrics.domains);
  assert.equal(catalog.manifest.counts.skills_bound, metrics.skills_bound);
  assert.equal(catalog.manifest.counts.tests, metrics.tests);
  assert.equal(catalog.manifest.counts.standards, metrics.standards);
});

check('manifest role entries match the tree', () => {
  assert.equal(catalog.roles.length, metrics.roles);
  assert.equal(new Set(catalog.roles.map((r) => r.domain)).size, metrics.domains);
  for (const r of catalog.roles) {
    assert.ok(fs.existsSync(path.join(catalog.root, r.slug, 'ROLE.md')), `missing ${r.slug}/ROLE.md`);
    assert.ok(r.title, `empty title in ${r.slug}`);
    assert.ok(r.deliverable_type, `empty deliverable_type in ${r.slug}`);
  }
  assert.ok(catalog.manifest.standards.length > 0, 'standards register empty');
});

check('installer copies a role and requires --dest', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'aeroroles-install-'));
  try {
    const slug = catalog.roles[0].slug;
    const result = install(catalog, [slug], { dest: tmp });
    assert.equal(result.installed.length, 1);
    assert.ok(fs.existsSync(path.join(tmp, slug, 'ROLE.md')), 'ROLE.md copied');
    assert.throws(() => install(catalog, [slug], {}), /--dest/, 'install without --dest throws');
    assert.throws(() => install(catalog, ['not-a-real-role'], { dest: tmp }), /no role/, 'unknown slug throws');
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

const mcpRoundTrip = () => new Promise((resolve, reject) => {
  const child = spawn(process.execPath, [bin, 'mcp'], { stdio: ['pipe', 'pipe', 'inherit'] });
  const responses = [];
  let buf = '';
  const timer = setTimeout(() => { child.kill(); reject(new Error('MCP server timed out')); }, 15000);
  child.stdout.on('data', (d) => {
    buf += d;
    let nl;
    while ((nl = buf.indexOf('\n')) !== -1) {
      responses.push(JSON.parse(buf.slice(0, nl)));
      buf = buf.slice(nl + 1);
      if (responses.length === 7) {
        clearTimeout(timer);
        child.stdin.end();
        resolve(responses);
      }
    }
  });
  child.on('error', reject);
  const send = (m) => child.stdin.write(JSON.stringify(m) + '\n');
  send({ jsonrpc: '2.0', id: 1, method: 'initialize', params: { protocolVersion: '2025-06-18', capabilities: {}, clientInfo: { name: 'smoke', version: '0' } } });
  send({ jsonrpc: '2.0', method: 'notifications/initialized' });
  send({ jsonrpc: '2.0', id: 2, method: 'tools/list' });
  send({ jsonrpc: '2.0', id: 3, method: 'tools/call', params: { name: 'search_roles', arguments: { query: 'DO-178C software certification plan' } } });
  send({ jsonrpc: '2.0', id: 4, method: 'tools/call', params: { name: 'get_role', arguments: { slug: 'do178c-cert-engineer' } } });
  send({ jsonrpc: '2.0', id: 5, method: 'resources/list' });
  send({ jsonrpc: '2.0', id: 6, method: 'resources/read', params: { uri: 'role://do178c-cert-engineer' } });
  send({ jsonrpc: '2.0', id: 7, method: 'tools/call', params: { name: 'suggest_role', arguments: { skill: 'avionics/do178c/planning' } } });
});

try {
  const [init, toolsList, search, getRole, resList, resRead, suggest] = await mcpRoundTrip();
  check('MCP initialize handshake', () => {
    assert.equal(init.result.serverInfo.name, 'aero-agent-roles');
    assert.ok(init.result.capabilities.tools);
    assert.ok(init.result.capabilities.resources, 'advertises resources capability');
  });
  check('MCP tools/list exposes 6 tools', () => {
    assert.equal(toolsList.result.tools.length, 6);
    for (const t of toolsList.result.tools) assert.ok(t.inputSchema && t.description, t.name);
  });
  check('MCP search_roles finds the DO-178C role', () => {
    assert.ok(search.result.content[0].text.includes('do178c-cert-engineer'), search.result.content[0].text.split('\n')[0]);
  });
  check('MCP get_role returns the full ROLE.md', () => {
    assert.ok(getRole.result.content[0].text.includes('name: do178c-cert-engineer'));
  });
  check('MCP resources/list enumerates role:// URIs', () => {
    assert.ok(resList.result.resources.length >= metrics.roles, `expected >=${metrics.roles} resources, got ${resList.result.resources.length}`);
    assert.ok(resList.result.resources.some((r) => r.uri === 'role://do178c-cert-engineer'), 'role listed');
  });
  check('MCP resources/read serves a role body', () => {
    assert.equal(resRead.result.contents[0].uri, 'role://do178c-cert-engineer');
    assert.ok(resRead.result.contents[0].text.includes('name: do178c-cert-engineer'), 'body is the ROLE.md');
  });
  check('MCP suggest_role inverts skill -> role', () => {
    assert.ok(suggest.result.content[0].text.includes('do178c-cert-engineer'), suggest.result.content[0].text.split('\n')[0]);
  });
} catch (e) {
  failures += 1;
  console.error(`FAIL MCP round-trip: ${e.message}`);
}

check('CLI list / search / show', () => {
  const list = execFileSync(process.execPath, [bin, 'list'], { encoding: 'utf8' });
  assert.ok(list.includes('avionics'), 'list names domains');
  assert.ok(list.includes(`${metrics.roles} roles`), 'list totals from manifest');
  const search = execFileSync(process.execPath, [bin, 'search', 'certification', 'plan', 'software'], { encoding: 'utf8' });
  assert.ok(search.includes('do178c-cert-engineer') || search.includes('do254-hardware-engineer'), 'search finds a certification role');
  const show = execFileSync(process.execPath, [bin, 'show', 'do178c-cert-engineer'], { encoding: 'utf8' });
  assert.ok(show.startsWith('---\ntype: role'), 'show prints raw ROLE.md');
});

if (failures) {
  console.error(`\nFAIL package smoke: ${failures} failing checks`);
  process.exit(1);
}
console.log('\nPASS package smoke: manifest + installer + MCP + CLI green');
