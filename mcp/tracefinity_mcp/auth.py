"""Principal resolution + self-provisioning of the Tracefinity admin account.

Only used against a local `native` Tracefinity instance (not the documented
default). Identity is derived from the OS user. The generated password is a
throwaway local credential stored under `mcp/secrets/<principal>.secret` (next to
this package; override with TRACEFINITY_SECRET_DIR), 0600. Nothing here is committed.
"""
from __future__ import annotations

import getpass
import os
import pathlib
import re
import secrets
import socket
import string

import httpx

# self-contained: the secret lives next to this package, under mcp/secrets/,
# so the whole Tracefinity stack is one movable directory. Override with
# TRACEFINITY_SECRET_DIR if needed.
CONFIG_DIR = pathlib.Path(
    os.environ.get(
        "TRACEFINITY_SECRET_DIR",
        str(pathlib.Path(__file__).resolve().parent.parent / "secrets"),
    )
).expanduser()


def resolve_principal() -> str:
    try:
        user = getpass.getuser()
    except Exception:
        user = "agent"
    host = (socket.gethostname() or "local").split(".")[0]
    slug = re.sub(r"[^a-z0-9._-]", "-", f"{user}-{host}".lower()).strip("-.")
    return slug or "agent"


def principal_email(principal: str) -> str:
    local = re.sub(r"[^a-z0-9._-]", "", principal) or "agent"
    return f"{local}@mcp.local"


class Session:
    """Owns the principal, the secret file, and the setup/login handshake.

    The shared httpx.AsyncClient's cookie jar carries the auth cookie that
    /auth/setup and /auth/login set; nothing is persisted between processes
    except the password in the secret file.
    """

    def __init__(self) -> None:
        self.principal = resolve_principal()
        self.email = principal_email(self.principal)
        self.mode: str | None = None  # set by bootstrap(): "open" | "native"
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:  # keep the secret dir owner-only, not just the file
            os.chmod(CONFIG_DIR, 0o700)
        except OSError:
            pass
        self.secret_path = CONFIG_DIR / f"{self.principal}.secret"

    # ---- secret file -------------------------------------------------------
    def read_secret(self) -> str | None:
        try:
            return self.secret_path.read_text().strip() or None
        except FileNotFoundError:
            return None

    def _create_secret(self, password: str) -> None:
        # O_EXCL: never clobber an existing secret (race-safe for the common case)
        fd = os.open(self.secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(password + "\n")

    def update_secret(self, password: str) -> None:
        tmp = self.secret_path.parent / (self.secret_path.name + ".tmp")
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        # O_NOFOLLOW: never write through a symlink someone planted at the tmp path
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
        fd = os.open(tmp, flags, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(password + "\n")
        os.replace(tmp, self.secret_path)

    @staticmethod
    def _new_password() -> str:
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(32))

    # ---- handshake -------------------------------------------------------
    async def bootstrap(self, client: httpx.AsyncClient) -> None:
        # When the operator has declared an open instance, do not touch the auth
        # system at all — not even the status probe.
        if os.environ.get("TRACEFINITY_AUTH_MODE", "").strip().lower() == "open":
            self.mode = "open"
            return

        status = (await client.get("/api/auth/status")).json()
        mode = status.get("mode")
        if mode == "open":
            # no accounts, no login: unauthenticated requests fall back to the
            # "default" workspace. /api/auth/* and /api/admin/users|tokens 404
            # in this mode — that is expected.
            self.mode = "open"
            return
        if mode != "native":
            raise RuntimeError(
                f"Tracefinity auth mode is {mode!r}; the MCP supports 'open' or 'native'. "
                "Set AUTH_MODE in docker-compose.override.yaml and restart."
            )
        self.mode = "native"

        if status.get("setup_required"):
            password = self.read_secret()
            if password is None:
                password = self._new_password()
                try:
                    self._create_secret(password)
                except FileExistsError:
                    password = self.read_secret()
            resp = await client.post(
                "/api/auth/setup", json={"email": self.email, "password": password}
            )
            if resp.status_code < 400:
                return  # setup set the auth cookie
            if resp.status_code != 409:
                raise RuntimeError(f"/api/auth/setup failed {resp.status_code}: {resp.text}")
            # 409 => already set up by someone else; fall through to login

        if self.read_secret() is None:
            raise RuntimeError(
                "Tracefinity setup is already complete but there is no local secret at "
                f"{self.secret_path}. Either restore that file, or reset the instance "
                "from the repo root: `docker compose down && rm -rf data && "
                "docker compose up -d`, then retry."
            )
        await self.login(client)

    async def login(self, client: httpx.AsyncClient) -> None:
        password = self.read_secret()
        if password is None:
            raise RuntimeError(f"no secret at {self.secret_path}")
        resp = await client.post(
            "/api/auth/login", json={"email": self.email, "password": password}
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"/api/auth/login failed {resp.status_code}: {resp.text}")
        body = resp.json()
        if body.get("pending"):
            raise RuntimeError(
                "2FA is enabled on this account; non-interactive login cannot complete. "
                "Disable it from an interactive session (twofa_disable) or reset the instance."
            )
