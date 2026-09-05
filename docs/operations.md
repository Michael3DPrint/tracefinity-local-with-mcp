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
[README → Authentication](../README.md#authentication-three-separate-layers) for
the full picture and why this is deliberate. This overlay is documented for `open`
mode; the MCP also works against a local `native` instance, but that isn't the
focus. For multiple users or internet exposure, deploy Tracefinity yourself behind
your own auth proxy.

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

## Updating Tracefinity

Merge the Dependabot PR that bumps the image tag in `compose.yaml`, then:

```bash
docker compose pull
docker compose up -d
```

To roll back, set the previous tag in `compose.override.yaml` and pull again.

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
