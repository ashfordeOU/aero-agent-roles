#!/usr/bin/env bash
# Roles hourly umbrella: sync the public repo, then the landing page.
# Mirrors AeroSkills' hourly-publish.sh (founder: roles must run as
# cleanly as skills — public + site updates handled the same way).
#
# Step 1: publish-public.sh  — dev tree -> ashfordeOU/aero-agent-roles
# Step 2: roles page sync    — pull from PUBLIC repo -> ashforde.org/
# Best-effort between steps (they publish to different repos); each
# step's own gates abort only that step, never the whole run.
#
# Driven by launchd (org.ashforde.roles-hourly-publish), logged to
# ~/Library/Logs/roles-hourly-publish.log. Idempotent: both steps
# no-op when nothing changed.
set -uo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SITE_REPO="${ASHFORDE_SITE_REPO:-$HOME/company-ops/ashforde-site}"

echo "===== $(date -u +%FT%TZ) roles-hourly-publish starting ====="

echo "--- roles public repo sync ---"
if ! bash "$SCRIPT_DIR/publish-public.sh"; then
  echo "!!! roles public sync FAILED — nothing published to ashfordeOU/aero-agent-roles"
fi

echo "--- roles landing page sync ---"
if [ -f "$SITE_REPO/aeroagentroles/sync-and-publish.sh" ]; then
  if ! (cd "$SITE_REPO" && bash aeroagentroles/sync-and-publish.sh); then
    echo "!!! roles landing page sync FAILED — ashforde.org/aeroagentroles not updated"
  fi
else
  echo "!!! roles sync-and-publish.sh missing in $SITE_REPO"
fi

echo "===== $(date -u +%FT%TZ) roles-hourly-publish done ====="
