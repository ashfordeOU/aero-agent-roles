#!/usr/bin/env bash
# Sync the GitHub About sidebar (description · homepage · topics) from
# docs/metrics.json, so the public numbers come from the tree and can never
# be hand-edited into staleness. Needs network plus a repo-scoped token,
# so it is deliberately NOT one of the offline gates. Two ways it runs:
#   make about                    — manual, from the local tree
#   .ci-native --best-effort line — every push refreshes About (non-fatal:
#                                   a network flake must never block a push)
set -euo pipefail

# --best-effort: run normally but never exit nonzero (gate-safe wrapper)
if [[ " $* " == *" --best-effort "* ]]; then
  args=()
  for a in "$@"; do [[ "$a" == --best-effort ]] || args+=("$a"); done
  if ! bash "$0" ${args[@]+"${args[@]}"}; then
    echo "WARN about: sync failed (non-fatal — network or token unavailable)"
  fi
  exit 0
fi

cd "$(git rev-parse --show-toplevel)"

url=$(git remote get-url origin)
token=$(printf '%s' "$url" | sed -E 's#https://[^:]+:([^@]+)@.*#\1#')
slug=$(printf '%s' "$url" | sed -E -e 's#.*github\.com/##' -e 's#\.git$##')
# Not every clone embeds a token in the remote URL (e.g. a mirror pushing
# via a credential helper) — fall back to gh's own token, for the account
# that OWNS the repo first. The bare `gh auth token` answers for whichever
# account is active, and with the development account active the PATCH got
# HTTP 403 and the description stayed stale behind a "non-fatal" warning
# (2026-09-26).
if [ "$token" = "$url" ] && command -v gh >/dev/null 2>&1; then
  owner=${slug%%/*}
  token=$(gh auth token --user "$owner" 2>/dev/null \
          || gh auth token 2>/dev/null || true)
fi
if [ -z "$token" ] || [ "$slug" = "$url" ]; then
  echo "FAIL about: no usable token (neither embedded in origin nor via gh auth token) or unexpected remote shape" >&2
  exit 1
fi

metrics="docs/metrics.json"

payload=$(METRICS="$metrics" /usr/bin/python3 - <<'PY'
import glob, json, os, re
m = json.load(open(os.environ["METRICS"]))
# FP-17 (2026-09-26): say DISTINCT skills (a skill bound by three roles is
# one skill, not three) and say the roles are drafts, because every ROLE.md
# says so. The draft count is read from the tree, never typed.
statuses = [re.search(r"^status:\s*(\S+)", open(p).read(), re.M)
            for p in glob.glob("roles/*/ROLE.md")]
drafts = sum(1 for s in statuses if s and s.group(1) == "draft")
if drafts == m["roles"]:
    roles = f"{m['roles']} draft roles"
else:
    roles = f"{m['roles']} roles ({drafts} still draft)"
desc = ("\U0001F9D1\u200D\U0001F680 The role layer for aerospace engineering agents — "
        f"{roles} binding {m['skills_distinct']} distinct Aero Agent Skills "
        f"({m['skills_bound']} bindings) across {m['domains']} domains, "
        f"verified by {m['tests']} offline tests, gated on {m['standards']} "
        "standards. Every role ends at the human sign-off. Apache-2.0 · by "
        "Ashforde OÜ")
print(json.dumps({"description": desc, "homepage": "https://ashforde.org/aeroagentroles"}))
PY
)

topics='{"names":["aerospace","aerospace-engineering","agent-skills","ai-agents","arp4754a","as9100","avionics","certification","claude-code","compliance","do-178c","ecss","gnc","llm","mcp","propulsion","role-library","space-systems","systems-engineering"]}'

resp=$(mktemp)
trap 'rm -f "$resp"' EXIT

code=$(curl -sS --max-time 20 -o "$resp" -w '%{http_code}' -X PATCH \
  -H "Authorization: Bearer $token" -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/$slug" -d "$payload")
if [ "$code" != "200" ]; then
  echo "FAIL about: description/homepage PATCH -> HTTP $code" >&2
  cat "$resp" >&2
  exit 1
fi

code=$(curl -sS --max-time 20 -o "$resp" -w '%{http_code}' -X PUT \
  -H "Authorization: Bearer $token" -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/$slug/topics" -d "$topics")
if [ "$code" != "200" ]; then
  echo "FAIL about: topics PUT -> HTTP $code" >&2
  cat "$resp" >&2
  exit 1
fi

n=$(/usr/bin/python3 -c "import json,sys;print(len(json.load(open(sys.argv[1]))['names']))" "$resp")
echo "PASS about: $slug description + homepage synced from local tree, $n topics set"
