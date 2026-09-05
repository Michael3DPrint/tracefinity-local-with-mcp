#!/usr/bin/env bash
# Register the Tracefinity MCP server with an MCP client.
#
#   ./scripts/install-mcp.sh            # interactive: pick Claude / Gemini / both
#   ./scripts/install-mcp.sh claude
#   ./scripts/install-mcp.sh gemini
#   ./scripts/install-mcp.sh both
#
# This checkout's absolute path is resolved automatically; nothing
# machine-specific is committed.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mcp_dir="$here/mcp"
name="tracefinity"

# value: env > .env > default
_from_env() {  # $1 = var name, $2 = default
  local v="${!1:-}"
  if [ -z "$v" ] && [ -f "$here/.env" ]; then
    v="$(grep -E "^$1=" "$here/.env" | tail -1 | cut -d= -f2- || true)"
  fi
  printf '%s' "${v:-$2}"
}
base="$(_from_env TRACEFINITY_BASE_URL http://localhost:3000)"
auth_mode="$(_from_env TRACEFINITY_AUTH_MODE open)"

target="${1:-}"
if [ -z "$target" ]; then
  if [ ! -t 0 ]; then
    echo "usage: $0 [claude|gemini|both]" >&2
    exit 2
  fi
  echo "Register the Tracefinity MCP with which client?"
  echo "  1) Claude   (claude mcp add, user scope)"
  echo "  2) Gemini   (gemini mcp add, or ~/.gemini/settings.json)"
  echo "  3) Both"
  printf "Choice [1/2/3]: "
  read -r ans || true
  case "${ans:-}" in
    1|claude|Claude|c) target=claude ;;
    2|gemini|Gemini|g) target=gemini ;;
    3|both|Both|b)      target=both ;;
    *) echo "no choice made — nothing done"; exit 1 ;;
  esac
fi

install_claude() {
  command -v claude >/dev/null || { echo "claude: CLI not found on PATH — skipped"; return 1; }
  claude mcp remove -s user "$name" >/dev/null 2>&1 || true
  claude mcp add -s user "$name" \
    -e "TRACEFINITY_BASE_URL=$base" \
    -e "TRACEFINITY_AUTH_MODE=$auth_mode" \
    -- uv run --directory "$mcp_dir" tracefinity-mcp
  claude mcp list 2>/dev/null | grep -i "$name" || true
  echo "claude: registered (run 'claude' or /mcp if a session is already open)"
}

install_gemini() {
  if command -v gemini >/dev/null 2>&1; then
    gemini mcp remove "$name" >/dev/null 2>&1 || true
    if gemini mcp add -s user -e "TRACEFINITY_BASE_URL=$base" -e "TRACEFINITY_AUTH_MODE=$auth_mode" \
         "$name" uv run --directory "$mcp_dir" tracefinity-mcp >/dev/null 2>&1; then
      gemini mcp list 2>/dev/null | grep -i "$name" || true
      echo "gemini: registered via 'gemini mcp add'"
      return 0
    fi
    echo "gemini: 'gemini mcp add' unavailable/failed — writing settings.json instead"
  fi

  local f="$HOME/.gemini/settings.json"
  mkdir -p "$HOME/.gemini"
  [ -s "$f" ] || printf '{}\n' > "$f"

  if command -v jq >/dev/null 2>&1; then
    local tmp; tmp="$(mktemp)"
    jq --arg dir "$mcp_dir" --arg base "$base" --arg mode "$auth_mode" --arg name "$name" '
      .mcpServers = (.mcpServers // {})
      | .mcpServers[$name] = {
          command: "uv",
          args: ["run", "--directory", $dir, "tracefinity-mcp"],
          env: { TRACEFINITY_BASE_URL: $base, TRACEFINITY_AUTH_MODE: $mode }
        }
    ' "$f" > "$tmp" && mv "$tmp" "$f"
  else
    python3 - "$f" "$mcp_dir" "$base" "$auth_mode" "$name" <<'PY'
import json, sys
f, mcp_dir, base, mode, name = sys.argv[1:6]
try:
    with open(f) as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        data = {}
except Exception:
    data = {}
data.setdefault("mcpServers", {})[name] = {
    "command": "uv",
    "args": ["run", "--directory", mcp_dir, "tracefinity-mcp"],
    "env": {"TRACEFINITY_BASE_URL": base, "TRACEFINITY_AUTH_MODE": mode},
}
with open(f, "w") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
PY
  fi
  echo "gemini: wrote $name to $f"
}

rc=0
case "$target" in
  claude) install_claude || rc=1 ;;
  gemini) install_gemini || rc=1 ;;
  both)   install_claude || rc=1; install_gemini || rc=1 ;;
  *) echo "unknown target: $target (expected claude|gemini|both)" >&2; exit 2 ;;
esac
exit $rc
