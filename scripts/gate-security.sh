#!/usr/bin/env bash
# gate-security.sh — roles repo tripwire: no local info, credentials,
# machine paths, or dangerous content in anything that could go public.
set -uo pipefail
cd "$(dirname "$0")/.."
fail=0

# 1. Secret-like strings anywhere in tracked content (exclude this script)
if grep -rniE "(^|[^a-z])sk-[a-z0-9]{10,}|api[_-]?key[[:space:]]*[:=]|BEGIN (RSA |EC |OPENSSH )?PRIVATE|bearer [a-z0-9]{10,}|gh_pat|\.tmp token|password[[:space:]]*[:=]" \
    --include="*.md" --include="*.py" --include="*.sh" --include="*.yaml" --include="*.yml" . 2>/dev/null \
    | grep -v ".git/" | grep -v "scripts/gate-security.sh"; then
  echo "FAIL: secret-like string found (above)"; fail=1
fi

# 2. Local machine paths (exclude this script + legit repo paths)
if grep -rniE "__HOME__|/Volumes/|/Users/[a-z]" \
    --include="*.md" --include="*.py" --include="*.sh" . 2>/dev/null \
    | grep -v ".git/" | grep -v "scripts/gate-security.sh" \
    | grep -v "__REPO__"; then
  echo "FAIL: local path found (above)"; fail=1
fi

[ "$fail" = "0" ] && echo "security: clean"
exit "$fail"
