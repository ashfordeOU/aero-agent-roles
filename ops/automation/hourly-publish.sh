#!/usr/bin/env bash
# Roles hourly umbrella: sync the public repo, then refresh the public
# About + landing page. Each step is INDEPENDENT: a transient gate
# failure in publish-public must not starve the About/page refresh —
# the page pulls the latest PUBLIC content (which may already be synced
# by an earlier run), so About/site always echo the newest released
# state. Mirrors the Aero Skills umbrella + founder directive
# (2026-09-06): releases/packages/site actions originate from the
# PUBLIC repo, never private dev.
set -uo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SITE_REPO="${ASHFORDE_SITE_REPO:-$HOME/company-ops/ashforde-site}"

echo "===== $(date -u +%FT%TZ) roles-hourly-publish starting ====="

echo "--- roles public repo sync ---"
bash "$SCRIPT_DIR/publish-public.sh" \
  || echo "!!! roles public sync FAILED this run (may be transient) — continuing to About/page"

echo "--- roles public About sync (independent) ---"
# refresh About on the PUBLIC repo from the mirror (origin IS public),
# so description/topics/homepage always echo the newest committed state
MIRROR="$HOME/Code/.aero-agent-roles-public-mirror"
if [ -d "$MIRROR/.git" ] && [ -f "$SCRIPT_DIR/update-about.sh" ]; then
  cp "$SCRIPT_DIR/update-about.sh" "$MIRROR/ops/automation/" 2>/dev/null || true
  (cd "$MIRROR" && bash ops/automation/update-about.sh 2>&1) \
    || echo "!!! roles public About sync FAILED"
fi

echo "--- roles landing page sync (independent) ---"
if [ -f "$SITE_REPO/aeroagentroles/sync-and-publish.sh" ]; then
  (cd "$SITE_REPO" && bash aeroagentroles/sync-and-publish.sh) \
    || echo "!!! roles landing page sync FAILED — ashforde.org/aeroagentroles not updated"
else
  echo "!!! roles sync-and-publish.sh missing in $SITE_REPO"
fi

echo "===== $(date -u +%FT%TZ) roles-hourly-publish done ====="
