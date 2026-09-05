#!/usr/bin/env bash
# Quick environment sanity check. Non-zero exit if something's wrong.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$here"
rc=0
say() { printf '%-32s %s\n' "$1" "$2"; }
chk() { if eval "$2" >/dev/null 2>&1; then say "$1" "ok"; else say "$1" "FAIL"; rc=1; fi; }

chk "docker on PATH"        "command -v docker"
chk "docker daemon"         "docker info"
chk "docker compose plugin" "docker compose version"
chk "uv on PATH"            "command -v uv"
chk "an MCP client CLI"     "command -v claude || command -v gemini"

img="$(grep -oE 'ghcr\.io/tracefinity/tracefinity:[^ ]+' compose.yaml | head -1)"
chk "image tag resolvable"  "docker manifest inspect $img"

port="$( ( [ -f .env ] && grep -E '^TRACEFINITY_PORT=' .env | cut -d= -f2- ) || true )"
port="${port:-3000}"
if curl -fsS "http://localhost:${port}/api/auth/status" >/dev/null 2>&1; then
  say "tracefinity :${port}" "up"
else
  say "tracefinity :${port}" "not responding (start with: docker compose up -d)"
fi

exit $rc
