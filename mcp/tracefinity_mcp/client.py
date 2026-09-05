"""Thin async HTTP client for the Tracefinity API with auto (re)login."""
from __future__ import annotations

import os
import pathlib

import httpx

from .auth import Session

BASE_URL = os.environ.get("TRACEFINITY_BASE_URL", "http://localhost:3000").rstrip("/")
# self-contained: downloads land next to this package, under mcp/downloads/
DEFAULT_DOWNLOAD_DIR = os.path.expanduser(
    os.environ.get(
        "TRACEFINITY_DOWNLOAD_DIR",
        str(pathlib.Path(__file__).resolve().parent.parent / "downloads"),
    )
)

_NO_RETRY_PATHS = ("/api/auth/login", "/api/auth/setup", "/api/auth/status")


class ApiError(RuntimeError):
    pass


class TracefinityClient:
    def __init__(self) -> None:
        self.session = Session()
        self._client = httpx.AsyncClient(base_url=BASE_URL, timeout=180.0, follow_redirects=True)
        self._booted = False

    async def ensure_auth(self, force: bool = False) -> None:
        if force or not self._booted:
            await self.session.bootstrap(self._client)
            self._booted = True

    async def _raw(self, method: str, path: str, **kw) -> httpx.Response:
        resp = await self._client.request(method, path, **kw)
        # Only ever attempt a (re)login against a native-auth instance. In open
        # mode a 401 just propagates — the client never calls /api/auth/login.
        if (
            resp.status_code == 401
            and self.session.mode == "native"
            and not path.startswith(_NO_RETRY_PATHS)
        ):
            await self.session.login(self._client)
            resp = await self._client.request(method, path, **kw)
        if resp.status_code >= 400:
            raise ApiError(f"{method} {path} -> {resp.status_code}: {resp.text[:2000]}")
        return resp

    async def _json_or_text(self, resp: httpx.Response):
        ctype = resp.headers.get("content-type", "")
        if "application/json" in ctype:
            return resp.json()
        return {"status_code": resp.status_code, "text": resp.text}

    async def request(self, method: str, path: str, **kw):
        await self.ensure_auth()
        return await self._json_or_text(await self._raw(method, path, **kw))

    async def get(self, path: str, **kw):
        return await self.request("GET", path, **kw)

    async def post(self, path: str, json=None, **kw):
        return await self.request("POST", path, json=json, **kw)

    async def put(self, path: str, json=None, **kw):
        return await self.request("PUT", path, json=json, **kw)

    async def patch(self, path: str, json=None, **kw):
        return await self.request("PATCH", path, json=json, **kw)

    async def delete(self, path: str, **kw):
        return await self.request("DELETE", path, **kw)

    async def upload(self, path: str, field: str, file_path: str, data: dict | None = None):
        await self.ensure_auth()
        p = os.path.expanduser(file_path)
        with open(p, "rb") as fh:
            content = fh.read()
        files = {field: (os.path.basename(p), content)}
        resp = await self._raw("POST", path, files=files, data=data or {})
        return await self._json_or_text(resp)

    async def download(self, path: str, dest_dir: str | None = None, filename: str | None = None) -> str:
        await self.ensure_auth()
        dest = os.path.expanduser(dest_dir or DEFAULT_DOWNLOAD_DIR)
        os.makedirs(dest, exist_ok=True)
        resp = await self._raw("GET", path)
        name = filename or path.rstrip("/").split("/")[-1]
        out = os.path.join(dest, name)
        with open(out, "wb") as fh:
            fh.write(resp.content)
        return out
