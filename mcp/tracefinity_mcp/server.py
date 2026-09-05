"""Tracefinity MCP server — wraps the local Tracefinity REST API as MCP tools.

The MCP talks only to the local API at TRACEFINITY_BASE_URL (default
localhost:3000), including reading /api/auth/status to detect the mode. In the
default "open" mode it does no login/account operations (no /api/auth/setup, no
/api/auth/login, no credentials) and the 16 account/login/2FA/admin tools are not
registered — 58 tools instead of 74. Set TRACEFINITY_AUTH_MODE=native (against a
local native instance) to register the other 16; that path is not the documented
default. See auth.py.

No `from __future__ import annotations` here on purpose: FastMCP introspects each
tool's signature to build its input schema, and eager (non-stringized)
annotations are the reliable path. Requires Python >= 3.10 for `X | None`.
"""
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import TracefinityClient

mcp = FastMCP("tracefinity")
tf = TracefinityClient()

# Register the 16 account/login/2FA/admin-user tools only when the operator has
# declared a native-auth instance. Default (unset / "open") = they are never
# registered, so the model has no account-management surface.
NATIVE = os.environ.get("TRACEFINITY_AUTH_MODE", "").strip().lower() == "native"


def native_tool(fn):
    """Register the tool only in native-auth mode; otherwise leave it out."""
    return mcp.tool()(fn) if NATIVE else fn


def _clean(**kw: Any) -> dict[str, Any]:
    """Drop keys whose value is None."""
    return {k: v for k, v in kw.items() if v is not None}


# ============================================================ meta / status
@mcp.tool()
async def health() -> dict:
    """Liveness probe. GET /api/version — the FastAPI /health route is not exposed
    through the container's nginx (only /api/, /storage/, / are), so /api/version
    is the reachable unauthenticated check."""
    return await tf.get("/api/version")


@mcp.tool()
async def get_version() -> dict:
    """Running Tracefinity version. GET /api/version."""
    return await tf.get("/api/version")


@mcp.tool()
async def get_api_status() -> dict:
    """Provider + available tracers ({google, provider, provider_label, tracers}). GET /api/api-keys."""
    return await tf.get("/api/api-keys")


# ============================================================ auth
@mcp.tool()
async def auth_status() -> dict:
    """Auth mode + whether first-run setup is still pending. GET /api/auth/status."""
    return await tf.get("/api/auth/status")


@mcp.tool()
async def bootstrap() -> dict:
    """Force the provision/login handshake now (normally lazy). Idempotent."""
    await tf.ensure_auth(force=True)
    return {
        "principal": tf.session.principal,
        "email": tf.session.email,
        "secret_path": str(tf.session.secret_path),
    }


@native_tool
async def whoami() -> dict:
    """The logged-in account. GET /api/auth/me."""
    return await tf.get("/api/auth/me")


@native_tool
async def change_password(new_password: str) -> dict:
    """Change this principal's password and rewrite the local secret file. POST /api/auth/password.
    Min 8 chars. Logs out other devices (not this one)."""
    current = tf.session.read_secret()
    if current is None:
        raise RuntimeError("no local secret to authenticate the change")
    await tf.post("/api/auth/password", json={"current_password": current, "new_password": new_password})
    tf.session.update_secret(new_password)
    return {"status": "password changed", "secret_path": str(tf.session.secret_path)}


@native_tool
async def twofa_enroll() -> dict:
    """Begin TOTP enrolment; returns {secret, otpauth_uri}. POST /api/auth/2fa/enroll."""
    return await tf.post("/api/auth/2fa/enroll")


@native_tool
async def twofa_confirm(code: str) -> dict:
    """Confirm TOTP with a live 6-digit code; enables 2FA, returns backup codes. POST /api/auth/2fa/confirm.
    WARNING: once enabled, this MCP can no longer log in non-interactively. Use twofa_disable to undo."""
    return await tf.post("/api/auth/2fa/confirm", json={"code": code})


@native_tool
async def twofa_disable(code: str) -> dict:
    """Disable TOTP (password from the secret file + a live code). POST /api/auth/2fa/disable."""
    return await tf.post(
        "/api/auth/2fa/disable",
        json={"password": tf.session.read_secret() or "", "code": code},
    )


@native_tool
async def twofa_regenerate_backup_codes(code: str) -> dict:
    """Regenerate backup codes (password + live code). POST /api/auth/2fa/backup-codes."""
    return await tf.post(
        "/api/auth/2fa/backup-codes",
        json={"password": tf.session.read_secret() or "", "code": code},
    )


@native_tool
async def logout() -> dict:
    """Revoke the current auth token. POST /api/auth/logout. The next tool call re-logs in."""
    await tf.post("/api/auth/logout")
    tf._booted = False
    return {"status": "logged out"}


# ============================================================ admin (native, cookie)
@native_tool
async def admin_list_users() -> dict:
    """All accounts. GET /api/admin/users."""
    return await tf.get("/api/admin/users")


@native_tool
async def admin_create_user(email: str, password: str | None = None, is_admin: bool = False,
                            id: str | None = None) -> dict:
    """Create an account. POST /api/admin/users. Exactly one of password/password_hash required
    (this tool only sends password). Password min 8 chars."""
    return await tf.post("/api/admin/users", json=_clean(email=email, password=password, is_admin=is_admin, id=id))


@native_tool
async def admin_disable_user(account_id: str) -> dict:
    """Disable an account and revoke its tokens. POST /api/admin/users/{id}/disable."""
    return await tf.post(f"/api/admin/users/{account_id}/disable")


@native_tool
async def admin_enable_user(account_id: str) -> dict:
    """Re-enable an account. POST /api/admin/users/{id}/enable."""
    return await tf.post(f"/api/admin/users/{account_id}/enable")


@native_tool
async def admin_reset_password(account_id: str, password: str) -> dict:
    """Set a new password for an account (revokes its tokens). POST /api/admin/users/{id}/reset-password."""
    return await tf.post(f"/api/admin/users/{account_id}/reset-password", json={"password": password})


@native_tool
async def admin_clear_2fa(account_id: str) -> dict:
    """Clear a locked-out account's 2FA. POST /api/admin/users/{id}/clear-2fa."""
    return await tf.post(f"/api/admin/users/{account_id}/clear-2fa")


@native_tool
async def admin_list_tokens() -> dict:
    """List admin API tokens. GET /api/admin/tokens."""
    return await tf.get("/api/admin/tokens")


@native_tool
async def admin_issue_token(label: str = "", expires_in_days: int | None = None) -> dict:
    """Issue an admin API token; raw value returned once. POST /api/admin/tokens."""
    return await tf.post("/api/admin/tokens", json=_clean(label=label, expires_in_days=expires_in_days))


@native_tool
async def admin_revoke_token(token_id: str) -> dict:
    """Revoke an admin API token. DELETE /api/admin/tokens/{id}."""
    return await tf.delete(f"/api/admin/tokens/{token_id}")


@mcp.tool()
async def admin_storage_stats() -> dict:
    """Instance-wide storage usage snapshot. GET /api/admin/storage-stats."""
    return await tf.get("/api/admin/storage-stats")


# ============================================================ account
@mcp.tool()
async def delete_my_data(confirm: bool = False) -> dict:
    """DESTRUCTIVE. DELETE /api/users/me — deletes this account, its tokens, and ALL stored
    data (sessions/tools/bins/projects). In native mode this also removes the admin account
    and returns the instance to first-run setup. Refused unless confirm=True."""
    if not confirm:
        raise RuntimeError("refused: pass confirm=True to delete the account and all data")
    res = await tf.delete("/api/users/me")
    tf._booted = False
    return {"status": "deleted", "detail": res}


# ============================================================ upload / corners / trace
@mcp.tool()
async def upload_photo(image_path: str, station_id: str | None = None,
                       capture_crop: str | None = None) -> dict:
    """Upload a photo; auto-detects paper corners. POST /api/upload (multipart 'image').
    capture_crop is a JSON string {x,y,width,height} in 0..1 (needs photo-stations). Returns
    {session_id, image_url, detected_corners, image_width, image_height, ...}."""
    return await tf.upload("/api/upload", "image", image_path,
                           data=_clean(station_id=station_id, capture_crop=capture_crop))


@mcp.tool()
async def set_corners(session_id: str, corners: list[dict], paper_size: str,
                      save_station_name: str | None = None) -> dict:
    """Apply perspective correction from 4 paper corners. POST /api/sessions/{id}/corners.
    corners: list of 4 {"x":float,"y":float} in image pixels.
    paper_size: one of A4, Letter, A3, Tabloid.
    save_station_name: also save these corners as a photo-station (needs photo-stations).
    Returns {corrected_image_url, scale_factor, warnings, station}."""
    body = _clean(corners=corners, paper_size=paper_size, save_station_name=save_station_name)
    return await tf.post(f"/api/sessions/{session_id}/corners", json=body)


@mcp.tool()
async def redetect_corners(session_id: str) -> dict:
    """Re-run automatic corner detection. POST /api/sessions/{id}/redetect-corners. Needs photo-stations."""
    return await tf.post(f"/api/sessions/{session_id}/redetect-corners")


@mcp.tool()
async def reuse_corners(session_id: str, station_id: str) -> dict:
    """Apply a saved photo-station's corners to this session. POST /api/sessions/{id}/reuse-corners.
    Needs photo-stations."""
    return await tf.post(f"/api/sessions/{session_id}/reuse-corners", json={"station_id": station_id})


@mcp.tool()
async def trace(session_id: str, tracer: str | None = None) -> dict:
    """AI-trace tool outlines from the corrected image. POST /api/sessions/{id}/trace.
    tracer: optional id from get_api_status().tracers (default = instance primary, e.g. 'isnet').
    Returns {polygons:[{id,points,label,...}], mask_url}."""
    return await tf.post(f"/api/sessions/{session_id}/trace", json=_clean(tracer=tracer))


@mcp.tool()
async def trace_from_mask(session_id: str, mask_path: str) -> dict:
    """Trace contours from an uploaded B/W mask. POST /api/sessions/{id}/trace-mask (multipart 'mask')."""
    return await tf.upload(f"/api/sessions/{session_id}/trace-mask", "mask", mask_path)


@mcp.tool()
async def update_polygons(session_id: str, polygons: list[dict]) -> dict:
    """Replace the session's traced polygons. PUT /api/sessions/{id}/polygons.
    polygons: list of {id, points:[{x,y}], label, finger_holes?, interior_rings?}."""
    return await tf.put(f"/api/sessions/{session_id}/polygons", json={"polygons": polygons})


# ============================================================ sessions
@mcp.tool()
async def list_sessions() -> dict:
    """List trace sessions. GET /api/sessions."""
    return await tf.get("/api/sessions")


@mcp.tool()
async def get_session(session_id: str) -> dict:
    """Full session state. GET /api/sessions/{id}."""
    return await tf.get(f"/api/sessions/{session_id}")


@mcp.tool()
async def update_session(session_id: str, name: str | None = None, description: str | None = None,
                         tags: list[str] | None = None, layout: dict | None = None) -> dict:
    """Update session metadata / layout. PATCH /api/sessions/{id}."""
    return await tf.patch(f"/api/sessions/{session_id}",
                          json=_clean(name=name, description=description, tags=tags, layout=layout))


@mcp.tool()
async def delete_session(session_id: str) -> dict:
    """Delete a session. DELETE /api/sessions/{id}."""
    return await tf.delete(f"/api/sessions/{session_id}")


@mcp.tool()
async def session_debug(session_id: str) -> dict:
    """Contour-detection debug images (URLs). GET /api/sessions/{id}/debug."""
    return await tf.get(f"/api/sessions/{session_id}/debug")


@mcp.tool()
async def generate_session_output(session_id: str, bin_config: dict | None = None) -> dict:
    """Generate STL/3MF from the session's traced polygons. POST /api/sessions/{id}/generate.
    bin_config: partial GenerateRequest (grid_x, grid_y, height_units, wall_thickness,
    cutout_depth, cutout_clearance, cutout_chamfer, magnets, stacking_lip, bed_size,
    text_labels:[...], polygons:[...] to override). {} uses sensible defaults + session polygons.
    Then call download_session_stl / _3mf / _parts. Returns GenerateResponse."""
    return await tf.post(f"/api/sessions/{session_id}/generate", json=bin_config or {})


@mcp.tool()
async def save_tools(session_id: str, polygon_ids: list[str] | None = None) -> dict:
    """Convert traced polygons into library tools (px->mm, centred). POST /api/sessions/{id}/save-tools.
    polygon_ids: subset to save; omit for all. Returns {tool_ids:[...]}."""
    return await tf.post(f"/api/sessions/{session_id}/save-tools", json=_clean(polygon_ids=polygon_ids))


@mcp.tool()
async def download_session_stl(session_id: str, dest_dir: str | None = None) -> dict:
    """Download the session STL. GET /api/files/{id}/bin.stl. Returns {path}."""
    return {"path": await tf.download(f"/api/files/{session_id}/bin.stl", dest_dir, f"session-{session_id[:8]}.stl")}


@mcp.tool()
async def download_session_3mf(session_id: str, dest_dir: str | None = None) -> dict:
    """Download the session 3MF. GET /api/files/{id}/bin.3mf. Returns {path}."""
    return {"path": await tf.download(f"/api/files/{session_id}/bin.3mf", dest_dir, f"session-{session_id[:8]}.3mf")}


@mcp.tool()
async def download_session_parts(session_id: str, dest_dir: str | None = None) -> dict:
    """Download the session split-parts ZIP. GET /api/files/{id}/bin_parts.zip. Returns {path}."""
    return {"path": await tf.download(f"/api/files/{session_id}/bin_parts.zip", dest_dir, f"session-{session_id[:8]}-parts.zip")}


# ============================================================ photo stations (PHOTO_STATIONS=true)
@mcp.tool()
async def list_stations() -> dict:
    """List photo stations. GET /api/photo-stations."""
    return await tf.get("/api/photo-stations")


@mcp.tool()
async def get_station(station_id: str) -> dict:
    """Get a photo station. GET /api/photo-stations/{id}."""
    return await tf.get(f"/api/photo-stations/{station_id}")


@mcp.tool()
async def create_station(name: str, session_id: str, paper_size: str | None = None,
                         corners: list[dict] | None = None) -> dict:
    """Save a session's calibration as a reusable station. POST /api/photo-stations.
    Falls back to the session's own paper_size/corners when omitted."""
    return await tf.post("/api/photo-stations",
                         json=_clean(name=name, session_id=session_id, paper_size=paper_size, corners=corners))


@mcp.tool()
async def update_station(station_id: str, name: str | None = None, paper_size: str | None = None,
                         corners: list[dict] | None = None) -> dict:
    """Update a photo station. PATCH /api/photo-stations/{id}."""
    return await tf.patch(f"/api/photo-stations/{station_id}",
                          json=_clean(name=name, paper_size=paper_size, corners=corners))


@mcp.tool()
async def delete_station(station_id: str) -> dict:
    """Delete a photo station. DELETE /api/photo-stations/{id}."""
    return await tf.delete(f"/api/photo-stations/{station_id}")


@mcp.tool()
async def session_station_suggestions(session_id: str) -> dict:
    """Stations that match this session's image. GET /api/sessions/{id}/station-suggestions."""
    return await tf.get(f"/api/sessions/{session_id}/station-suggestions")


# ============================================================ tools library
@mcp.tool()
async def list_tools() -> dict:
    """List library tools. GET /api/tools."""
    return await tf.get("/api/tools")


@mcp.tool()
async def get_tool(tool_id: str) -> dict:
    """Get a tool. GET /api/tools/{id}."""
    return await tf.get(f"/api/tools/{tool_id}")


@mcp.tool()
async def update_tool(tool_id: str, name: str | None = None, points: list[dict] | None = None,
                      finger_holes: list[dict] | None = None, interior_rings: list[list[dict]] | None = None,
                      smoothed: bool | None = None, smooth_level: float | None = None,
                      category: str | None = None, drawer: str | None = None,
                      tags: list[str] | None = None, project_ids: list[str] | None = None,
                      review_status: str | None = None, needs_cleanup: bool | None = None,
                      source_image_transform: list[float] | None = None) -> dict:
    """Update a tool. PUT /api/tools/{id}. All fields optional."""
    return await tf.put(f"/api/tools/{tool_id}", json=_clean(
        name=name, points=points, finger_holes=finger_holes, interior_rings=interior_rings,
        smoothed=smoothed, smooth_level=smooth_level, category=category, drawer=drawer,
        tags=tags, project_ids=project_ids, review_status=review_status,
        needs_cleanup=needs_cleanup, source_image_transform=source_image_transform))


@mcp.tool()
async def auto_rotate_tool(tool_id: str) -> dict:
    """Optimal rotation angle (deg) to minimise the bounding box. POST /api/tools/{id}/auto-rotate.
    Returns {angle}. Does not mutate; feed it back via update_tool if wanted."""
    return await tf.post(f"/api/tools/{tool_id}/auto-rotate")


@mcp.tool()
async def delete_tool(tool_id: str) -> dict:
    """Delete a tool. DELETE /api/tools/{id}."""
    return await tf.delete(f"/api/tools/{tool_id}")


@mcp.tool()
async def download_tool_svg(tool_id: str, dest_dir: str | None = None) -> dict:
    """Download a tool outline as SVG. GET /api/files/tools/{id}/tool.svg. Returns {path}."""
    return {"path": await tf.download(f"/api/files/tools/{tool_id}/tool.svg", dest_dir, f"tool-{tool_id[:8]}.svg")}


# ============================================================ bins
@mcp.tool()
async def list_bins() -> dict:
    """List bins. GET /api/bins."""
    return await tf.get("/api/bins")


@mcp.tool()
async def get_bin(bin_id: str) -> dict:
    """Get a bin (syncs placed tools with library versions). GET /api/bins/{id}."""
    return await tf.get(f"/api/bins/{bin_id}")


@mcp.tool()
async def create_bin(name: str | None = None, project_id: str | None = None,
                     tool_ids: list[str] | None = None, bin_config: dict | None = None) -> dict:
    """Create a bin. POST /api/bins. tool_ids pre-places those library tools and auto-sizes.
    bin_config: partial BinDefaults (grid_x, grid_y, height_units, ...)."""
    return await tf.post("/api/bins", json=_clean(
        name=name, project_id=project_id, tool_ids=tool_ids, bin_config=bin_config))


@mcp.tool()
async def update_bin(bin_id: str, name: str | None = None, project_id: str | None = None,
                     bin_config: dict | None = None, placed_tools: list[dict] | None = None,
                     text_labels: list[dict] | None = None) -> dict:
    """Update a bin. PUT /api/bins/{id}. bin_config may include text_labels."""
    return await tf.put(f"/api/bins/{bin_id}", json=_clean(
        name=name, project_id=project_id, bin_config=bin_config,
        placed_tools=placed_tools, text_labels=text_labels))


@mcp.tool()
async def delete_bin(bin_id: str) -> dict:
    """Delete a bin and its output files. DELETE /api/bins/{id}."""
    return await tf.delete(f"/api/bins/{bin_id}")


@mcp.tool()
async def generate_bin(bin_id: str) -> dict:
    """Generate STL/3MF for a bin. POST /api/bins/{id}/generate (no body). 400 if the bin has
    no placed tools; may return 503 Retry-After under load. Then call
    download_bin_stl / _3mf / _parts / _insert. Returns GenerateResponse."""
    return await tf.post(f"/api/bins/{bin_id}/generate")


@mcp.tool()
async def download_bin_stl(bin_id: str, dest_dir: str | None = None) -> dict:
    """Download bin STL. GET /api/files/bins/{id}/bin.stl. Returns {path}."""
    return {"path": await tf.download(f"/api/files/bins/{bin_id}/bin.stl", dest_dir, f"bin-{bin_id[:8]}.stl")}


@mcp.tool()
async def download_bin_3mf(bin_id: str, dest_dir: str | None = None) -> dict:
    """Download bin 3MF. GET /api/files/bins/{id}/bin.3mf. Returns {path}."""
    return {"path": await tf.download(f"/api/files/bins/{bin_id}/bin.3mf", dest_dir, f"bin-{bin_id[:8]}.3mf")}


@mcp.tool()
async def download_bin_parts(bin_id: str, dest_dir: str | None = None) -> dict:
    """Download bin split-parts ZIP. GET /api/files/bins/{id}/bin_parts.zip. Returns {path}."""
    return {"path": await tf.download(f"/api/files/bins/{bin_id}/bin_parts.zip", dest_dir, f"bin-{bin_id[:8]}-parts.zip")}


@mcp.tool()
async def download_bin_insert(bin_id: str, dest_dir: str | None = None) -> dict:
    """Download the contrast-insert STL. GET /api/files/bins/{id}/bin_insert.stl. Returns {path}."""
    return {"path": await tf.download(f"/api/files/bins/{bin_id}/bin_insert.stl", dest_dir, f"bin-{bin_id[:8]}-insert.stl")}


# ============================================================ bin projects
@mcp.tool()
async def list_projects() -> dict:
    """List bin projects with counts. GET /api/bin-projects."""
    return await tf.get("/api/bin-projects")


@mcp.tool()
async def create_project(name: str, description: str | None = None, status: str | None = None,
                         target_grid_x: float | None = None, target_grid_y: float | None = None,
                         default_bin_config: dict | None = None, notes: str | None = None,
                         tool_ids: list[str] | None = None) -> dict:
    """Create a project. POST /api/bin-projects. status: active|ready_to_print|printed|archived."""
    return await tf.post("/api/bin-projects", json=_clean(
        name=name, description=description, status=status, target_grid_x=target_grid_x,
        target_grid_y=target_grid_y, default_bin_config=default_bin_config, notes=notes,
        tool_ids=tool_ids))


@mcp.tool()
async def get_project(project_id: str) -> dict:
    """Project detail incl. placed/unplaced tool ids. GET /api/bin-projects/{id}."""
    return await tf.get(f"/api/bin-projects/{project_id}")


@mcp.tool()
async def update_project(project_id: str, name: str | None = None, description: str | None = None,
                         status: str | None = None, target_grid_x: float | None = None,
                         target_grid_y: float | None = None, default_bin_config: dict | None = None,
                         notes: str | None = None) -> dict:
    """Update project metadata/status. PATCH /api/bin-projects/{id}."""
    return await tf.patch(f"/api/bin-projects/{project_id}", json=_clean(
        name=name, description=description, status=status, target_grid_x=target_grid_x,
        target_grid_y=target_grid_y, default_bin_config=default_bin_config, notes=notes))


@mcp.tool()
async def delete_project(project_id: str) -> dict:
    """Delete project metadata (tools and bins are kept). DELETE /api/bin-projects/{id}."""
    return await tf.delete(f"/api/bin-projects/{project_id}")


@mcp.tool()
async def project_add_tools(project_id: str, tool_ids: list[str]) -> dict:
    """Add tools to a project. POST /api/bin-projects/{id}/tools."""
    return await tf.post(f"/api/bin-projects/{project_id}/tools", json={"tool_ids": tool_ids})


@mcp.tool()
async def project_remove_tool(project_id: str, tool_id: str) -> dict:
    """Remove a tool from a project. DELETE /api/bin-projects/{id}/tools/{tool_id}."""
    return await tf.delete(f"/api/bin-projects/{project_id}/tools/{tool_id}")


@mcp.tool()
async def project_link_bins(project_id: str, bin_ids: list[str], import_tools: bool = False,
                            allow_reassign: bool = False) -> dict:
    """Link existing bins to a project. POST /api/bin-projects/{id}/bins."""
    return await tf.post(f"/api/bin-projects/{project_id}/bins",
                         json={"bin_ids": bin_ids, "import_tools": import_tools, "allow_reassign": allow_reassign})


@mcp.tool()
async def project_unlink_bin(project_id: str, bin_id: str) -> dict:
    """Detach a bin from a project. DELETE /api/bin-projects/{id}/bins/{bin_id}."""
    return await tf.delete(f"/api/bin-projects/{project_id}/bins/{bin_id}")


@mcp.tool()
async def project_create_bin(project_id: str, name: str | None = None,
                             tool_ids: list[str] | None = None, bin_config: dict | None = None) -> dict:
    """Create a new bin from selected project tools. POST /api/bin-projects/{id}/create-bin."""
    return await tf.post(f"/api/bin-projects/{project_id}/create-bin",
                         json=_clean(name=name, tool_ids=tool_ids, bin_config=bin_config))


@mcp.tool()
async def project_health(project_id: str) -> dict:
    """Report project/tool/bin link mismatches. GET /api/bin-projects/{id}/health."""
    return await tf.get(f"/api/bin-projects/{project_id}/health")


@mcp.tool()
async def project_repair(project_id: str) -> dict:
    """Repair safe link mismatches. POST /api/bin-projects/{id}/repair."""
    return await tf.post(f"/api/bin-projects/{project_id}/repair")


# ============================================================ entrypoint
def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
