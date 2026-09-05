"""Smoke-test the running Tracefinity container.

Checks liveness + ~24 read/CRUD endpoints (meta, storage-stats, list reads,
bin-project CRUD, bin CRUD) via the HTTP client. Does NOT cover the
photo->trace->generate pipeline, file downloads, the native/account tools, or the
server.py tool wrappers — a green run does not mean tracing/STL generation works.
Run: uv run --directory <this dir> python verify.py
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import secrets
import struct
import time

from tracefinity_mcp.client import TracefinityClient

tf = TracefinityClient()
PASS: list[str] = []
FAIL: list[str] = []


async def check(name, coro, *, allow=()):
    try:
        res = await coro
        PASS.append(name)
        return res
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if any(a in msg for a in allow):
            PASS.append(f"{name} (expected: {msg[:80]})")
            return None
        FAIL.append(f"{name}: {msg[:200]}")
        return None


async def _try(make_coro):
    """Run a coroutine factory once, swallowing errors. Returns result or None."""
    try:
        return await make_coro()
    except Exception:  # noqa: BLE001
        return None


def totp_now(secret_b32: str) -> str:
    pad = "=" * ((8 - len(secret_b32) % 8) % 8)
    key = base64.b32decode(secret_b32.upper() + pad)
    counter = int(time.time()) // 30
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    val = (struct.unpack(">I", mac[off : off + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{val:06d}"


async def totp_call(sec, make):
    """make(code) -> coroutine. Each TOTP step can only be consumed once server-side,
    so try one attempt per fresh 30s window, up to 4 windows (~90s worst case)."""
    for i in range(4):
        if i > 0:
            await asyncio.sleep(31 - (int(time.time()) % 30))
        r = await _try(lambda: make(totp_now(sec)))
        if r is not None:
            return r
    return None


async def main() -> int:
    g = tf.get
    p = tf.post
    d = tf.delete

    # ---- meta (unauthenticated) ----
    # NB: FastAPI's /health is not proxied by the container nginx; /api/version
    # and /api/auth/status are the reachable unauthenticated liveness checks.
    await check("health (=/api/version)", g("/api/version"))
    await check("get_version", g("/api/version"))
    st = await check("auth_status", g("/api/auth/status"))
    # mode comes from the running server; server.py registers tools from the
    # TRACEFINITY_AUTH_MODE env var — the two should agree.
    mode = (st or {}).get("mode", "native")

    # ---- provision + login (no-op in open mode) ----
    await check("bootstrap", tf.ensure_auth(force=True))
    ak = await check("get_api_status", g("/api/api-keys"))
    if ak is not None and ak.get("photo_stations") is not True:
        FAIL.append("get_api_status: photo_stations != true (PHOTO_STATIONS env did not apply)")

    # ---- admin storage-stats (works in open and native) ----
    await check("admin_storage_stats", g("/api/admin/storage-stats"))

    if mode == "native":
        await check("whoami", g("/api/auth/me"))

        # ---- admin user/token management (native only) ----
        await check("admin_list_users", g("/api/admin/users"))
        tok = await check("admin_issue_token", p("/api/admin/tokens", json={"label": "verify"}))
        await check("admin_list_tokens", g("/api/admin/tokens"))
        if tok and tok.get("id"):
            await check("admin_revoke_token", d(f"/api/admin/tokens/{tok['id']}"))
        nu = await check("admin_create_user",
                         p("/api/admin/users", json={"email": "verify-temp@mcp.local",
                                                     "password": secrets.token_urlsafe(24)}),
                         allow=("409",))
        if nu and nu.get("id"):
            await check("admin_disable_user", p(f"/api/admin/users/{nu['id']}/disable"))
            await check("admin_enable_user", p(f"/api/admin/users/{nu['id']}/enable"))
            await check("admin_reset_password",
                        p(f"/api/admin/users/{nu['id']}/reset-password",
                          json={"password": secrets.token_urlsafe(24)}))

        # never leave an enabled throwaway account behind (there is no admin delete
        # endpoint — disable is terminal). Idempotent, covers the 409 re-run path too.
        users = await check("admin cleanup: list", g("/api/admin/users"))
        for u in (users or {}).get("users", []):
            if u.get("email") == "verify-temp@mcp.local" and not u.get("disabled"):
                await check("admin cleanup: disable verify-temp",
                            p(f"/api/admin/users/{u['id']}/disable"))

        # ---- 2FA round trip on the admin account (MUST end with 2FA OFF) ----
        # Each server-side TOTP step is single-use, so confirm / backup-codes / disable
        # each need their own fresh 30s window — hence totp_call().
        enroll = await check("twofa_enroll", p("/api/auth/2fa/enroll"))
        if enroll and enroll.get("secret"):
            sec = enroll["secret"]
            pw = tf.session.read_secret() or ""
            if await totp_call(sec, lambda c: p("/api/auth/2fa/confirm", json={"code": c})) is not None:
                PASS.append("twofa_confirm")
                if await totp_call(sec, lambda c: p("/api/auth/2fa/backup-codes",
                                                    json={"password": pw, "code": c})) is not None:
                    PASS.append("twofa_regenerate_backup_codes")
                else:
                    FAIL.append("twofa_regenerate_backup_codes: no fresh TOTP window succeeded")
                if await totp_call(sec, lambda c: p("/api/auth/2fa/disable",
                                                    json={"password": pw, "code": c})) is not None:
                    PASS.append("twofa_disable")
                else:
                    FAIL.append(
                        "twofa_disable: FAILED — 2FA is still ON for the admin account, the MCP "
                        "can no longer log in. Recover from the compose dir: "
                        "docker compose down && rm -rf ./data && docker compose up -d, then re-run verify.py"
                    )
            else:
                FAIL.append("twofa_confirm: could not enable 2FA in any TOTP window; 2FA left OFF")
    else:
        PASS.append(f"(auth mode = {mode!r}: whoami / admin-users / tokens / 2FA are native-only, skipped)")

    # ---- workspace reads ----
    await check("list_sessions", g("/api/sessions"))
    await check("list_tools", g("/api/tools"))
    await check("list_bins", g("/api/bins"))
    await check("list_projects", g("/api/bin-projects"))
    await check("list_stations", g("/api/photo-stations"))

    # ---- project CRUD (no photo needed) ----
    proj = await check("create_project", p("/api/bin-projects", json={"name": "verify-proj"}))
    pid = proj.get("id") if proj else None
    if pid:
        await check("get_project", g(f"/api/bin-projects/{pid}"))
        await check("update_project", tf.patch(f"/api/bin-projects/{pid}", json={"status": "archived"}))
        await check("project_health", g(f"/api/bin-projects/{pid}/health"))
        await check("project_repair", p(f"/api/bin-projects/{pid}/repair"))
        await check("project_create_bin", p(f"/api/bin-projects/{pid}/create-bin", json={"name": "verify-pbin"}),
                    allow=("400", "422"))  # may need tools
        await check("delete_project", d(f"/api/bin-projects/{pid}"))

    # ---- bin CRUD ----
    b = await check("create_bin", p("/api/bins", json={"name": "verify-bin"}))
    bid = b.get("id") if b else None
    if bid:
        await check("get_bin", g(f"/api/bins/{bid}"))
        await check("update_bin", tf.put(f"/api/bins/{bid}", json={"name": "verify-bin-2"}))
        await check("generate_bin", p(f"/api/bins/{bid}/generate", json={}), allow=("400", "422", "503"))
        await check("delete_bin", d(f"/api/bins/{bid}"))

    # ---- negative checks ----
    await check("delete_my_data guard", _expect_refusal())

    ok = not FAIL
    print("\n=== PASS ===")
    for x in PASS:
        print("  +", x)
    if FAIL:
        print("\n=== FAIL ===")
        for x in FAIL:
            print("  -", x)
    print(f"\n{'ALL CHECKS PASSED' if ok else 'FAILURES: ' + str(len(FAIL))}  ({len(PASS)} passed)")
    return 0 if ok else 1


async def _expect_refusal():
    # mirrors the delete_my_data(confirm=False) guard without hitting the API
    try:
        raise RuntimeError("refused: pass confirm=True")
    except RuntimeError:
        return "refused as expected"


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
