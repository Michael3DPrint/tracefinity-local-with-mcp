# tracefinity-local-with-mcp

Self-host [Tracefinity](https://github.com/tracefinity/tracefinity) from its
published container image — one local install serving a browser **web UI** and a
**REST API** on `localhost:3000` — plus a local **MCP server** that wraps that API
for any [Model Context Protocol](https://modelcontextprotocol.io) client (58 tools
in the default `open` mode). The MCP is a plain stdio process, not tied to any
model or vendor; Claude Code is used in the examples only because it has a
one-command install helper. No connection to the hosted `tracefinity.net`.

A **deployment overlay** — no upstream source vendored. The image
`ghcr.io/tracefinity/tracefinity:<tag>` in [`compose.yaml`](compose.yaml) is the
only upstream dependency; Dependabot also bumps the MCP's Python deps and the CI
actions. Built for a **single user on loopback or a trusted LAN** — it has no
authentication (see [`docs/security.md`](docs/security.md)).

> **Installing this with an agent?** → [`docs/agent-install.md`](docs/agent-install.md)
> (ordered, non-interactive, with success criteria).

## Prerequisites

Clone the repo (needs `git`), then run **`./scripts/preflight.sh`** — it checks
everything below and, at a terminal, offers to install what's missing (macOS via
Homebrew, Linux via your package manager). `--fix` installs non-interactively;
`--check` only reports.

| Tool | Required? | macOS | Linux | Page |
|---|---|---|---|---|
| **git** | yes — to clone | `xcode-select --install` or `brew install git` | `sudo apt-get install -y git` (etc.) | <https://git-scm.com/downloads> |
| **curl** | yes — scripts + installers | preinstalled | preinstalled on most; `sudo apt-get install -y curl` | — |
| **Docker** + Compose v2 plugin, **daemon running** | yes — runs Tracefinity | `brew install --cask docker`, then launch Docker.app once | `curl -fsSL https://get.docker.com \| sh`, then `sudo usermod -aG docker $USER` + re-login | <https://www.docker.com/products/docker-desktop/> · <https://docs.docker.com/engine/install/> |
| **uv** (bundles Python ≥ 3.10) | yes — MCP server + `verify.py` | `brew install uv` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | <https://docs.astral.sh/uv/getting-started/installation/> |
| **Homebrew** | macOS helper for the above | `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"` | *(optional — Linuxbrew)* | <https://brew.sh> |
| `jq` *or* `python3` | no — `install-mcp.sh gemini` fallback | `brew install jq` | `sudo apt-get install -y jq` | <https://jqlang.github.io/jq/download/> |
| `claude` *or* `gemini` CLI | no — only to wire the MCP into that assistant | — | — | [`docs/mcp-tools.md`](docs/mcp-tools.md#use-with-an-mcp-client) |
| `gh` (GitHub CLI) | no — only if this repo is **private** | `brew install gh` | `sudo apt-get install -y gh` | <https://cli.github.com> |

**~6 GB disk** (image ≈ 4.5 GB + model weights + a small host venv) and outbound
internet on first run (image pull; tracing-model weights download into the
container, one-time, cached in `data/`). If `docker` / `uv` "aren't found" they
may just be off your shell `PATH` — `preflight.sh` flags this.

## Quick start

```bash
git clone https://github.com/Michael3DPrint/tracefinity-local-with-mcp
cd tracefinity-local-with-mcp

./scripts/preflight.sh           # checks brew/docker/uv/… — offers to install what's missing
./scripts/init.sh                # creates .env + dirs, pulls the image, uv sync
docker compose up -d             # backend answers after ~30-90 s (usually ~40; 502 until then)
(cd mcp && uv run python verify.py)   # expect: ALL CHECKS PASSED

./scripts/install-mcp.sh         # prompts: Claude / Gemini / both  (or pass one as an arg)
```

Open `http://localhost:3000` — the local install's **web UI** (the MCP uses the
same install's API at `/api/*`). Default `open` mode has no login. On Linux the
container may create `./data` root-owned — see
[`docs/operations.md`](docs/operations.md#run-the-container-as-your-host-user).

## Use with an MCP client

Any MCP client works — point it at `uv run --directory <abs>/mcp tracefinity-mcp`
(stdio) with `TRACEFINITY_BASE_URL=http://localhost:3000`. Per-client setup
(Claude Code / Desktop, Cursor, Cline, Zed, Gemini CLI, SDKs) and the tool
catalogue: **[`docs/mcp-tools.md`](docs/mcp-tools.md)**.

## Security

Local, single-user, **no authentication**. Fine because the port is bound to
`127.0.0.1` by default. Opening it to the LAN (`TRACEFINITY_BIND=0.0.0.0`) gives
every device on that network unauthenticated full access; never expose it to the
internet as-is. Driving it through the MCP sends workspace **metadata** (not the
photo or STL bytes) to your cloud LLM as part of the conversation. Full picture,
call-by-call: **[`docs/security.md`](docs/security.md)**.

## Docs

| | |
|---|---|
| [`docs/how-it-works.md`](docs/how-it-works.md) | terminology, the signal-flow diagram, repo layout |
| [`docs/operations.md`](docs/operations.md) | start/stop, verify, LAN access, updating, teardown, troubleshooting |
| [`docs/mcp-tools.md`](docs/mcp-tools.md) | the MCP package, tool catalogue, typical flow, per-client setup |
| [`docs/security.md`](docs/security.md) | the three auth layers, network exposure tables, hardening notes |
| [`docs/agent-install.md`](docs/agent-install.md) | non-interactive install runbook for an agent |

## Notes

- Claude Code's project memory lives under `~/.claude/`, separate from this repo —
  nothing about your setup is captured here.
- Not affiliated with or endorsed by Tracefinity. Upstream is MIT licensed.
