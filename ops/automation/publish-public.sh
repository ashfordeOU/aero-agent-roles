#!/usr/bin/env bash
# Sync the roles dev tree to the public release repo
# (github.com/ashfordeOU/aero-agent-roles). Same safety model as the
# sibling aero-agent-skills publish-public.sh:
#   1. Export the full committed tree via `git archive` (never a raw
#      working-tree copy).
#   2. Run the REAL gate battery INSIDE the export. Abort on failure —
#      the public repo is never touched with a broken state.
#   3. Sync a PERSISTENT local mirror clone (never re-init per run).
#      Replace its working tree with the fresh export, commit ON TOP of
#      existing history, push normally. Never force-push. If rejected,
#      STOP and report.
#   4. No-op if nothing changed — safe on a timer.
#
# Usage:
#   bash ops/automation/publish-public.sh              # sync if changed
#   bash ops/automation/publish-public.sh --dry-run     # export + gates only
set -euo pipefail

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

DEV_REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PUBLIC_REMOTE="https://github.com/ashfordeOU/aero-agent-roles.git"
MIRROR="$HOME/Code/.aero-agent-roles-public-mirror"
SCRATCH="$(mktemp -d)"
DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

log() { echo "[roles-publish] $(date -u +%FT%TZ) $*"; }
trap 'rm -rf "$SCRATCH"' EXIT

cd "$DEV_REPO"

# token file: same PAT that pushes ashforde-site + aero-agent-skills
TOKEN_FILE="$HOME/.hermes/.gh_pat_ashfordesite.tmp"
if [ -f "$TOKEN_FILE" ] && [ -r "$TOKEN_FILE" ]; then
  TOKEN=$(cat "$TOKEN_FILE")
  PUBLIC_REMOTE="https://x-access-token:${TOKEN}@github.com/ashfordeOU/aero-agent-roles.git"
else
  log "WARN: no token file; will attempt unauthenticated (likely fails)"
fi

# 1. export committed tree
log "exporting committed tree"
git archive --format=tar --prefix=export/ HEAD -o "$SCRATCH/tree.tar"
mkdir -p "$SCRATCH/export"
tar -xf "$SCRATCH/tree.tar" -C "$SCRATCH"
EXPORT="$SCRATCH/export"

# 2. gate battery inside the export
log "running gates inside export"
if ! (cd "$EXPORT" && make validate >/tmp/roles-pub-validate.log 2>&1); then
  log "GATES FAILED inside export — public repo NOT touched"
  tail -5 /tmp/roles-pub-validate.log
  exit 1
fi
log "gates PASS inside export"

if [ "$DRY_RUN" = "1" ]; then
  log "dry-run: export + gates passed, mirror/push skipped"
  exit 0
fi

# 3. persistent mirror sync
if [ ! -d "$MIRROR/.git" ]; then
  log "initializing mirror at $MIRROR"
  mkdir -p "$MIRROR"
  git clone "$PUBLIC_REMOTE" "$MIRROR"
else
  log "mirror exists, fetching"
  git -C "$MIRROR" fetch origin main
fi

# Replace working tree with export, commit on top
git -C "$MIRROR" rm -rf --quiet . 2>/dev/null || true
cp -R "$EXPORT"/. "$MIRROR"/

cd "$MIRROR"
HEAD_BEFORE=$(git rev-parse HEAD 2>/dev/null || echo none)

# 4. no-op if nothing changed
if git diff --quiet HEAD -- . 2>/dev/null && [ -z "$(git status --porcelain)" ]; then
  log "no changes — no-op"
  exit 0
fi

git add -A
if ! git diff --cached --quiet; then
  git -c user.name="ashfordeOU" -c user.email="contact@ashforde.org" \
      commit -m "sync: roles repo state $(date -u +%Y-%m-%d)" >/dev/null
  log "committed in mirror"
fi

log "pushing to public"
if ! git push origin main 2>&1; then
  log "PUSH REJECTED — someone pushed out of band; stop, do not force"
  exit 1
fi
log "public sync complete: $(git rev-parse --short HEAD)"

# About sidebar refresh on the public repo (best-effort; the About set
# on the dev repo covers private; this keeps the PUBLIC repo's About in
# step without a separate manual act). Never blocks the sync result.
if command -v curl >/dev/null 2>&1 && [ -n "${TOKEN:-}" ]; then
  curl -s -X PATCH -H "Authorization: Bearer $TOKEN" \
       -H "Accept: application/vnd.github+json" \
       "https://api.github.com/repos/ashfordeOU/aero-agent-roles" \
       -d '{"homepage":"https://ashforde.org/aeroagentroles/"}' >/dev/null 2>&1 \
    && log "public about: homepage synced" \
    || log "public about: homepage sync skipped (network/token)"
fi
