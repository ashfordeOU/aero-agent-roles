// Installer: copies one role's full folder (ROLE.md, templates/, tests/,
// core/, cli.py, SOURCES.md) to a destination directory.
//
// Unlike Aero Agent Skills' installer, this does NOT claim any agent-host
// skill-router integration: ROLE.md has no `description` trigger field, so
// dropping it into a host's skills/ directory would not make it
// discoverable by that host's router — it would just be an inert folder.
// A role is adopted deliberately (a human or agent runs its cli.py
// directly), so `install` is a plain "get me this role's files" copy, not
// a harness-aware install. `--dest` is required for exactly that reason.
'use strict';

const fs = require('node:fs');
const path = require('node:path');

function install(catalog, slugs, opts) {
  if (!opts.dest) {
    throw new Error("install requires --dest <dir> (roles are not agent-router "
      + "skills, so there is no default harness skills root to guess)");
  }
  const dest = path.resolve(opts.dest);
  const selection = slugs.length === 0 || slugs.includes('all')
    ? catalog.roles.slice()
    : slugs.map((slug) => {
      const r = catalog.find(slug);
      if (!r) {
        const near = catalog.search(slug.replace(/-/g, ' '), 3).map((s) => s.role.slug).join(', ');
        throw new Error(`no role '${slug}'. Closest: ${near || 'none'}. Run \`aero-roles list\`.`);
      }
      return r;
    });
  fs.mkdirSync(dest, { recursive: true });
  const installed = [];
  for (const r of selection) {
    const src = path.join(catalog.root, r.slug);
    const dst = path.join(dest, r.slug);
    if (opts.link) {
      fs.rmSync(dst, { recursive: true, force: true });
      fs.symlinkSync(src, dst, 'dir');
    } else {
      fs.cpSync(src, dst, { recursive: true, force: true });
    }
    installed.push({ slug: r.slug, folder: r.slug });
  }
  return { dest, installed, linked: !!opts.link };
}

module.exports = { install };
