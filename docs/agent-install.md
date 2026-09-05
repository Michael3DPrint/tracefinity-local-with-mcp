# Automated install (for an agent)

Given only *"install this repo and make it work"*, follow this exactly. Every step
is idempotent — safe to re-run.

**Adopt these defaults without asking:** clone into the current working directory;
auth mode `open` (no login); bundled IS-Net tracer (no API key); an empty `.env`
is fine. This is a checkout to **run**, not to develop — do not `git add` /
`commit` / `push`, and do not modify tracked files.

**0 — Be able to clone.** Ensure `git` exists (`git --version`). If it's missing:
macOS `xcode-select --install`, Linux `sudo apt-get install -y git`. If the repo
is **private**, also `gh auth login` (install `gh` first) or configure a PAT / SSH key.

**1 — Clone.**
```bash
git clone https://github.com/Michael3DPrint/tracefinity-local-with-mcp
cd tracefinity-local-with-mcp
```

**2 — Toolchain.** `bash scripts/preflight.sh --fix -y` — checks and installs
brew / docker / uv / jq / etc. **It must exit 0 before continuing.** A non-zero
exit means something couldn't be auto-installed — almost always **Docker Desktop
on macOS**, which needs a manual first launch (`open -a Docker`, wait ~30 s), or a
Linux `docker` group re-login. Resolve what it names, then re-run it. If Docker
genuinely can't be installed/started non-interactively, stop and report that.
Then `export PATH="$HOME/.docker/bin:$HOME/.local/bin:$PATH"` for the rest of the run.

**3 — Setup.** `bash scripts/init.sh` — writes `.env`, makes dirs,
`docker compose pull` (~4.5 GB, allow several minutes), `uv sync`. Re-run on a
transient network error.

**4 — Start & wait.** `docker compose up -d`, then poll — the backend loads ML
models and nginx returns **502 for ~30–90 s (usually ~40)**, which is normal:
```bash
for i in $(seq 1 30); do curl -fsS localhost:3000/api/version && break || sleep 6; done
```
Proceed once that prints `{"version":"..."}`.

**5 — Verify (acceptance test).** `cd mcp && uv run python verify.py`.
**Pass = last line is `ALL CHECKS PASSED`.** (In `open` mode the account / login /
2FA / admin-user checks are skipped by design — those tools aren't registered;
that is not a failure. It is also an *endpoint smoke test* — it does not exercise
tracing or geometry.) On failure see [operations.md](operations.md#troubleshooting).

**6 — Register the MCP.** The bare command prompts and would hang an unattended
run — **always pass the client as an argument**:
- Claude Code present → `bash scripts/install-mcp.sh claude`, then confirm the
  client lists `tracefinity` as connected (`claude mcp list` for Claude Code;
  the client's MCP panel otherwise).
- Gemini CLI present → `bash scripts/install-mcp.sh gemini`.
- Neither → skip; the server still runs standalone (`cd mcp && uv run tracefinity-mcp`).

**Done when** all three hold: `curl -fsS localhost:3000/api/version` returns a
version, `verify.py` prints `ALL CHECKS PASSED`, and (if a client CLI exists) the
MCP shows connected. Report those results.

**Reset if interrupted:** `docker compose down && rm -rf data && docker compose up -d`
(data is throwaway). Full teardown in [operations.md](operations.md).
