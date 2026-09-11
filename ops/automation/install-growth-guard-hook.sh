#!/usr/bin/env bash
# install-growth-guard-hook.sh — install the fail-closed growth gate as this
# repo's pre-push hook. Hook files are not versioned, so the hook itself is a
# thin wrapper around the tracked guard; re-run this after a fresh clone.
#
#   bash ops/automation/install-growth-guard-hook.sh
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
HOOK="$ROOT/.git/hooks/pre-push"

cat > "$HOOK" <<'HOOK_EOF'
#!/usr/bin/env bash
# Installed by ops/automation/install-growth-guard-hook.sh — do not edit this
# copy; edit ops/automation/growth-guard.sh instead.
exec bash "$(git rev-parse --show-toplevel)/ops/automation/growth-guard.sh"
HOOK_EOF

chmod +x "$HOOK"
echo "installed: $HOOK -> ops/automation/growth-guard.sh"
