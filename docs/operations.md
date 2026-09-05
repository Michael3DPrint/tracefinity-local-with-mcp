# Operations

All commands run from the repo root unless noted. If `docker` / `uv` aren't
found, prepend their dirs to `PATH` (macOS: `export PATH="$HOME/.docker/bin:$HOME/.local/bin:$PATH"`).

## Start / stop / status

```bash
docker compose up -d        # start (~30-90 s to answer, usually ~40; 502 until then)
docker compose ps
docker compose logs -f      # follow logs
docker compose down         # stop + remove container (data/ is kept)
./scripts/doctor.sh         # environment + liveness check
```

## Verify the MCP end to end

```bash
cd mcp && uv run python verify.py
```
Expected last line: `ALL CHECKS PASSED`. This is an **endpoint smoke test** — it
does not cover tracing, geometry, downloads, or the tool wrappers (`verify.py`
docstring has the detail). The account / login / 2FA checks are skipped — there is
no authentication in this setup.

## No authentication

`AUTH_MODE=open`: no accounts, no login, no 2FA, a single `default` workspace. See
[security.md](security.md#authentication-three-separate-layers) for the full
picture and why this is deliberate. This overlay is documented for `open` mode;
the MCP also works against a local `native` instance, but that isn't the focus.
For multiple users or internet exposure, deploy Tracefinity yourself behind your
own auth proxy.

## LAN / phone access

By default the port is bound to `127.0.0.1` (this machine only). To reach the
**web UI** from a phone or another computer on your network — **read
[security.md](security.md#network-exposure) first**: with `AUTH_MODE=open` this
gives every device on that network unauthenticated full access.

```bash
# in .env
TRACEFINITY_BIND=0.0.0.0
```
then `docker compose up -d`. From the same network:

- `http://<this-machine-ip>:3000` — IP via `ipconfig getifaddr en0` (macOS) or
  `hostname -I` (Linux)
- `http://<this-machine-hostname>.local:3000` — usually works from phones and
  survives IP changes

If the macOS firewall is on, allow incoming connections for Docker when prompted.
Set `TRACEFINITY_BIND=127.0.0.1` again to lock it back down.

## Upload size limit

Uploads are capped at **25 MB** by the image's bundled nginx (`MAX_UPLOAD_MB=20`
app-side, via `TRACEFINITY_MAX_UPLOAD_MB` in `.env`). This is fixed for this
overlay — there is no supported way to raise it. Typical phone photos are 2–8 MB.

## Reset all data

```bash
docker compose down
rm -rf ./data
docker compose up -d
```

## Run the container as your host user

So `./data` isn't root-owned — put this in `compose.override.yaml`:

```yaml
services:
  tracefinity:
    environment:
      PUID: "1000"   # id -u
      PGID: "1000"   # id -g
```

## Updating — Tracefinity, MCP deps, CI

[`.github/dependabot.yml`](../.github/dependabot.yml) opens PRs for three things:

| ecosystem | path | schedule | what |
|---|---|---|---|
| `docker-compose` | `/` | weekly | the Tracefinity image tag in `compose.yaml` |
| `uv` | `/mcp` | weekly | the MCP's Python deps (`mcp`, `httpx`) via `mcp/uv.lock` |
| `github-actions` | `/` | monthly | the CI action versions |

For an **image bump**, CI ([`ci.yml`](../.github/workflows/ci.yml)) starts the new
image and runs `verify.py` against it — an endpoint smoke test only, so still
eyeball a real photo after a big jump. Merge the PR, then locally:

```bash
docker compose pull
docker compose up -d
```

Roll back by setting the previous tag in `compose.override.yaml` and pulling
again. Manual bump: edit the tag in `compose.yaml` (or the override) and pull.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `502 Bad Gateway` right after `up` | backend still loading models — wait ~30-90 s (usually ~40) |
| first `trace` call is slow / errors offline | some tracing models download at container startup, the rest on first trace; needs outbound internet once, then cached in `data/` |
| phone can't reach `http://<host>:3000` | same network? `TRACEFINITY_BIND` not `127.0.0.1`? macOS firewall allowing Docker? |
| `command not found: docker` / `uv` | add `~/.docker/bin` / `~/.local/bin` to `PATH` |
| `verify.py` can't connect | container not up, or wrong `TRACEFINITY_BASE_URL` |
| MCP tools missing in the client | run `./scripts/install-mcp.sh` (Claude / Gemini / both), then reload that client (`/mcp` or restart) |
| `ModuleNotFoundError: mcp.server.fastmcp` | shouldn't happen — `pyproject.toml` pins `mcp[cli]<2`. If it does, the pin was lost: `cd mcp && rm -rf .venv && uv sync` |
| upload returns 413 | the photo is over the 25 MB nginx cap — shrink it |
