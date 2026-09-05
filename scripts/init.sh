#!/usr/bin/env bash
# One-time setup: create local config + runtime dirs, pull the image, sync the MCP env.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$here"

export PATH="$HOME/.docker/bin:$HOME/.local/bin:$PATH"
_need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1 — run  bash scripts/preflight.sh --fix"; exit 1; }; }
_need docker
_need uv
docker info >/dev/null 2>&1 || { echo "docker daemon not running — start Docker, or run  bash scripts/preflight.sh --fix"; exit 1; }

[ -f .env ] || { cp .env.example .env; echo "created .env — review it"; }
mkdir -p data mcp/secrets mcp/downloads

echo "pulling the Tracefinity image..."
docker compose pull

echo "syncing the MCP virtualenv..."
( cd mcp && uv sync )

cat <<EOF

done. next:
  docker compose up -d          # start Tracefinity (backend answers after ~30-90 s, usually ~40)
  ./scripts/install-mcp.sh      # register the MCP (prompts: Claude / Gemini / both)
  (cd mcp && uv run python verify.py)
EOF
