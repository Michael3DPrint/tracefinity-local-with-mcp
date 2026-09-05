# Security

This is a **local, single-user** deployment. It has no authentication and does not
add any — that is acceptable *only* because the intended deployment is loopback
(the default) or a LAN you control. The hardening in the repo (CI, digest-pin
option, resource caps) is defense-in-depth for sharing the repo; the deployment
itself is intentionally minimal.

## Authentication: three separate layers

"Auth" here means three unrelated things. Only layer 1 exists in this setup:

```
 (1) LLM / client auth      (2) MCP → local install      (3) local install's own auth
 ─────────────────────      ──────────────────────       ────────────────────────────
 Claude Code / Gemini  ──▶  tracefinity-mcp (stdio)  ──▶  the LOCAL INSTALL, :3000
 signed in as you           no listener, no network        ├─ REST API  /api/*  ◀── MCP
 (claude.ai / Google);      no credentials, no login       └─ web UI    /       ◀── browser / phone
 it launches the MCP        (local API calls only)         AUTH_MODE = open  (no login)
```

(The "local install" is your self-hosted container — **not** `tracefinity.net`. Its
REST API and web UI are the same install on the same port.)

**(1) LLM / client auth** — how *you* are signed in to the assistant and its API
billing (claude.ai, a Google account, …). Entirely the client's concern; **this
repo touches none of it**. The client starts `tracefinity-mcp` as a local child
process — registering it (`install-mcp.sh` or `.mcp.json`) is an explicit local
trust grant. There is no port, token, or password between the client and the MCP:
the MCP trusts whatever process spawned it and inherits that process's OS user
and environment.

**(2) MCP → local install** — **no credentials.** The MCP reads
`/api/auth/status` (a local call) to detect the mode, then in `open` mode does no
`setup`/`login` and sends nothing; `mcp/secrets/` stays empty. It *can* provision
and log in against a local `native` instance, but that isn't the documented
default.

**(3) The local install's own auth** — **none.** `AUTH_MODE=open`: no accounts, no
login, no 2FA, single `default` workspace. Anyone who can reach the port has full
access to the API and web UI alike — which is why the port is loopback by default
and LAN use is "trusted networks only".

This is deliberate: the project's purpose is a **single-user, local or
trusted-LAN** deployment. It's documented for `open` mode; the MCP also works
against a local `native` instance but that's not the focus. If you need multiple
users or internet exposure, run Tracefinity yourself behind your own auth proxy.

| Layer | Authenticates | In this setup |
|---|---|---|
| (1) LLM client | you → the assistant + its API | your vendor account — not touched by this repo |
| (2) MCP → local install | the MCP process → the REST API | **none** |
| (3) Local install | callers of the API + web UI | **none** (`open` mode) |

## Network exposure

**Every call in the system:**

| # | Call | Transport | Travels over | Authenticated? |
|---|---|---|---|---|
| 1 | you ⇄ your assistant (Claude Code / Gemini) | the vendor's own API | internet | your vendor account — **layer 1**, outside this repo |
| 1b | MCP tool results → the assistant's LLM | rides row 1 (part of the conversation) | internet | — when you use the MCP, tool arguments + JSON results (session / tool / bin metadata, coordinates, file paths — **not** the photo or STL bytes) reach the LLM provider, like any other message |
| 2 | assistant → `tracefinity-mcp` | local **stdio** subprocess — no socket, no port | **same machine only** | none; the trust is "you ran `install-mcp.sh`". Inherits the assistant's OS user + env |
| 3 | `tracefinity-mcp` → local install `/api/*` | HTTP to `TRACEFINITY_BASE_URL` | **loopback** (keep it that way) | **none** — this setup has no Tracefinity auth (**layer 2**) |
| 4 | browser / phone → local install `/` (web UI) | HTTP | **loopback**, or **LAN** if `TRACEFINITY_BIND=0.0.0.0` | **none** — same open instance, no login (**layer 3**) |
| 5 | `docker compose pull` → GHCR | HTTPS, outbound | internet | none (public image); once per pinned version |
| 6 | container → GitHub releases | HTTPS, outbound | internet | none; tracing-model weights (some at container startup, the rest on first trace), one-time, cached in `data/` |
| 7 | container → Gemini / Replicate / fal | HTTPS, outbound | internet | **your API key — only if you set one** in `compose.override.yaml`; off by default |

Rows 2–4 are request/response *into* the local stack; 5–7 are the container
reaching *out*; rows 1 / 1b are between you and your cloud assistant. Nothing here
*accepts* a connection from the internet (see the inbound table).

**Inbound — who can reach the local install** (rows 3–4 above), set by `TRACEFINITY_BIND`:

| Tier | `TRACEFINITY_BIND` | Who can hit `:3000` | With `AUTH_MODE=open` (default) |
|---|---|---|---|
| **Loopback** (default) | `127.0.0.1` | only this machine | fine — nothing off-box can connect |
| **LAN** | `0.0.0.0` | every device on the same network — your phone, other computers, *and* anything else on that Wi-Fi/subnet (a guest laptop, a compromised IoT device) | **unauthenticated full access** for all of them. Only do this on a network you control; there is no auth to fall back on. |
| **Internet / external** | — | **nothing.** This repo binds a local port only — it never sets up port-forwarding, a tunnel, or a public reverse proxy. | n/a |

**This overlay is built for a single user on loopback or a trusted LAN — that's
the whole point.** It has no authentication and does not add any. If you need
multi-user access, real logins, or any internet exposure, this is the wrong tool:
deploy Tracefinity yourself behind your own auth proxy + TLS (or use upstream's
Helm chart). Do not port-forward / tunnel (`ngrok`, `cloudflared`, a reverse
proxy) this setup as-is — an open instance on a public address is immediate,
total data loss.

**Bottom line:** the *install* is local — only inbound path is loopback, only
outbound is the one-time image pull + model weights. But **driving it through the
MCP puts your workspace metadata into a cloud LLM conversation** (row 1b); the
browser path (row 4) does not. Setting `TRACEFINITY_BIND=0.0.0.0` adds LAN
inbound; nothing here ever adds internet inbound; setting an AI key adds row 7.

## Other notes

- **No access control, by design.** There is no login; anyone who can reach the
  port has full API access — upload, trace, generate, **read and delete all
  data**. Acceptable *only* because the intended deployment is loopback or a LAN
  you control (see the tables above).
- **No TLS.** All traffic is plain HTTP. Fine over loopback; over a LAN, uploaded
  photos and traced data cross the network in the clear.
- **Keep `TRACEFINITY_BASE_URL` local.** The MCP follows redirects and, if it ever
  reached a real login, would send credentials; point it only at
  `http://localhost` / `https://…`, never a remote plain-HTTP host.
- **Secrets live only in git-ignored files:** `.env`, `compose.override.yaml`,
  `mcp/secrets/` (0600). Put real `GOOGLE_API_KEY` / `REPLICATE_API_TOKEN` /
  `FAL_KEY` in `compose.override.yaml`, never in `compose.yaml`. `scrub-check.sh`
  (also in CI) fails the build on leaked machine paths.
- **The MCP exposes destructive tools** (`delete_my_data`, `delete_*`) and feeds
  workspace content — tool names, notes, AI-generated labels — straight into the
  model. Treat that content as untrusted (prompt-injection surface), especially
  before wiring this into an autonomous agent, and doubly so in `open` + LAN mode
  where anyone can plant content. (The account/login/2FA/admin tools aren't
  registered in `open` mode — see [Authentication](#authentication-three-separate-layers).)
- **`upload_photo` / `download_*` read and write arbitrary local paths** with the
  MCP process's privileges (`download_*` takes a `dest_dir`; `upload_photo` takes
  any file path). Same caution as any file tool.
- **`preflight.sh --fix`** runs the official installer scripts for Homebrew / uv /
  Docker (`curl … | sh`) and, on Linux, `sudo` package installs — only when you
  confirm or pass `-y`. Adding your user to the `docker` group (Linux) grants
  root-equivalent host access; that's Docker's model, not this repo's.
- **CI runs PR-supplied code** in an ephemeral runner with a read-only token and
  no secrets. Keep the repo private, or rely on GitHub's first-run-contributor
  approval gate, if that matters to you.
- **Image is pinned by tag, not digest.** Add a digest pin in
  `compose.override.yaml` (see the example) for immutability.
- Container runs as non-root (UID 1000) with `no-new-privileges`. Optional
  `mem_limit` / `pids_limit` hardening is in `compose.override.example.yaml`.
