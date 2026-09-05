#!/usr/bin/env bash
# Fail if machine-specific or personal strings are present in tracked files.
# Runs in CI and is worth running before any commit.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$here"

# NOTE: "@mcp.local" is intentionally allowed — it is the fake domain the MCP
# builds at runtime from the OS username, and the synthetic verify.py test account.
pattern='(/Users/[A-Za-z]|/home/[A-Za-z]|192\.168\.[0-9]|10\.[0-9]+\.[0-9]+\.[0-9]+|[A-Za-z-]+\.local:[0-9]|MacBook|claude\.ai/code/session)'

# standard, non-personal paths that legitimately contain /home/ or /Users/
allow='/home/(linuxbrew|runner)\b|/Users/Shared\b'

hits="$(grep -rInE "$pattern" . \
  --exclude-dir=.git \
  --exclude-dir=.venv \
  --exclude-dir=node_modules \
  --exclude-dir=data \
  --exclude-dir=secrets \
  --exclude-dir=downloads \
  --exclude-dir=__pycache__ \
  --exclude='*.lock' \
  --exclude='scrub-check.sh' 2>/dev/null | grep -vE "$allow" || true)"

if [ -n "$hits" ]; then
  echo "scrub-check FAILED — machine/personal strings found:"
  echo "$hits"
  exit 1
fi
echo "scrub-check clean"
