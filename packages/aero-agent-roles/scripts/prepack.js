// Runs on `npm pack` / `npm publish` from the repo checkout: copies the
// payload (roles tree, NOTICE) from the repo root into the package so the
// tarball is self-contained. The copy is gitignored — the repo tree stays
// the single source of truth.
'use strict';

const fs = require('node:fs');
const path = require('node:path');

const pkg = path.join(__dirname, '..');
const repo = path.join(pkg, '..', '..');

if (!fs.existsSync(path.join(repo, 'roles')) || !fs.existsSync(path.join(repo, 'manifest.json'))) {
  console.error('prepack: must run from the aero-agent-roles repo checkout (roles/ not found two levels up)');
  process.exit(1);
}

fs.rmSync(path.join(pkg, 'roles'), { recursive: true, force: true });
fs.cpSync(path.join(repo, 'roles'), path.join(pkg, 'roles'), { recursive: true });
fs.copyFileSync(path.join(repo, 'NOTICE'), path.join(pkg, 'NOTICE'));

// Strip Python bytecode caches: local test runs leave __pycache__/*.pyc
// behind, and a plain cpSync copies them straight into the tarball. Never
// ship compiled bytecode in a public package regardless of dev-tree state.
function stripPycache(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === '__pycache__') {
        fs.rmSync(full, { recursive: true, force: true });
      } else {
        stripPycache(full);
      }
    }
  }
}
stripPycache(path.join(pkg, 'roles'));

console.log('prepack: bundled roles/, NOTICE from repo root (pycache stripped)');
