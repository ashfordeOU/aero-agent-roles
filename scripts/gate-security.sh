#!/usr/bin/env bash
# gate-security.sh — roles repo tripwire: no secrets, credentials,
# machine paths, or dangerous content in anything that could go public.
# NOTE: this script derives the local-path pattern from $HOME at runtime
# so no literal local path ever appears in the repository (maintainer
# mandate: no local info in public repos).
set -uo pipefail
cd "$(dirname "$0")/.."
fail=0

# 1. Secret-like strings anywhere in tracked content (exclude this script
# and the publish machinery, which may reference token FILE PATHS — never
# values; the pattern still catches real secrets everywhere else). A
# line containing GitHub Actions' ${{ secrets.X }} expression references
# a secret by NAME only (the value lives in GitHub's encrypted store, never
# in the repo), so those specific lines are excluded too — anything else
# secret-shaped in a workflow file still fails the gate.
if grep -rniE "(^|[^a-z])sk-[a-z0-9]{10,}|api[_-]?key[[:space:]]*[:=][[:space:]]*[\"']|BEGIN (RSA |EC |OPENSSH )?PRIVATE|bearer [a-z0-9]{10,}|gh_pat|\\.tmp token|password[[:space:]]*[:=][[:space:]]*[^[:space:]]" \
    --include="*.md" --include="*.py" --include="*.sh" --include="*.yaml" --include="*.yml" . 2>/dev/null \
    | grep -v ".git/" | grep -v "scripts/gate-security.sh" \
    | grep -v "ops/automation/publish-public.sh" \
    | grep -vE '\$\{\{[[:space:]]*secrets\.[A-Za-z_]+[[:space:]]*\}\}'; then
  echo "FAIL: secret-like string found (above)"; fail=1
fi

# 2. Local machine paths — pattern from $HOME at runtime
HOME_PAT=$(printf '%s' "$HOME" | sed 's|/|\\/|g')
if grep -rniE "$HOME_PAT|/Volumes/|/Users/[a-z]" \
    --include="*.md" --include="*.py" --include="*.sh" . 2>/dev/null \
    | grep -v ".git/" | grep -v "scripts/gate-security.sh"; then
  echo "FAIL: local path found (above)"; fail=1
fi

[ "$fail" = "0" ] && echo "security: clean"
exit "$fail"
