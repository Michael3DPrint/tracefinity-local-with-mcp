# MCP tools

The server (`mcp/tracefinity_mcp/server.py`) wraps the **local Tracefinity
install's REST API** (`http://localhost:3000/api/*` by default, via
`TRACEFINITY_BASE_URL`). It does not use that install's web UI, and has nothing to
do with the hosted `tracefinity.net`.

**58 tools** in the default `open` mode. The MCP talks only to the local API
(including reading `/api/auth/status` to detect the mode) and does no
login/account operations; the 16 account/login/2FA/admin functions in the last
catalogue row are not registered. Against a local `native` instance those 16
register too (74 total) — not the documented default. See
[README → Authentication](../README.md#authentication-three-separate-layers).

## Catalogue

| Group | Tools |
|---|---|
| Meta | `health`, `get_version`, `get_api_status`, `auth_status`, `bootstrap` |
| Upload / trace | `upload_photo`, `set_corners`, `redetect_corners`, `reuse_corners`, `trace`, `trace_from_mask`, `update_polygons` |
| Sessions | `list_sessions`, `get_session`, `update_session`, `delete_session`, `session_debug`, `generate_session_output`, `save_tools`, `download_session_stl` / `_3mf` / `_parts` |
| Tool library | `list_tools`, `get_tool`, `update_tool`, `auto_rotate_tool`, `delete_tool`, `download_tool_svg` |
| Bins | `list_bins`, `get_bin`, `create_bin`, `update_bin`, `delete_bin`, `generate_bin`, `download_bin_stl` / `_3mf` / `_parts` / `_insert` |
| Bin projects | `list_projects`, `create_project`, `get_project`, `update_project`, `delete_project`, `project_add_tools`, `project_remove_tool`, `project_link_bins`, `project_unlink_bin`, `project_create_bin`, `project_health`, `project_repair` |
| Photo stations | `list_stations`, `get_station`, `create_station`, `update_station`, `delete_station`, `session_station_suggestions` (need `PHOTO_STATIONS=true`, which this repo sets) |
| Account | `delete_my_data` (destructive; needs `confirm=true`) |
| Meta | `admin_storage_stats` (works without accounts — verified by `verify.py`) |
| **`native` only** (16 tools — not registered in `open`, the default) | `whoami`, `change_password`, `logout`, `twofa_enroll` / `_confirm` / `_disable` / `_regenerate_backup_codes`, `admin_list_users`, `admin_create_user`, `admin_disable_user`, `admin_enable_user`, `admin_reset_password`, `admin_clear_2fa`, `admin_list_tokens`, `admin_issue_token`, `admin_revoke_token` |

## About the "`native` only" row

Those 16 functions manage Tracefinity *accounts* — meaningless in `open` mode
(single-user, no account system) — so the MCP never registers them: an LLM can't
call them. `admin_storage_stats` and `delete_my_data` work in both modes; every
workflow tool is unaffected.

## Typical flow

```
upload_photo(image_path="…/tools.jpg")            -> session_id
set_corners(session_id, corners=<4 {x,y}>, paper_size="A4")
trace(session_id)                                 -> polygons
save_tools(session_id)                            -> tool_ids
create_bin(tool_ids=[…])                          -> bin_id
generate_bin(bin_id); download_bin_stl(bin_id)    -> file in mcp/downloads/
```

`corners` can be passed straight from `upload_photo`'s `detected_corners`.
`paper_size` is one of `A4`, `Letter`, `A3`, `Tabloid`.

## Which MCP client

Any of them — this is a plain MCP **stdio** server with no model/vendor SDK.
See the [Use with an MCP client](../README.md#use-with-an-mcp-client) table in the
README for Claude Code / Claude Desktop / Cursor / Cline / Zed / Continue / Goose /
LibreChat / LM Studio / SDK setups. The universal config is:

```
command: uv
args:    run --directory <abs path>/mcp tracefinity-mcp
env:     TRACEFINITY_BASE_URL=http://localhost:3000
```

`TRACEFINITY_AUTH_MODE=open` is optional — it just skips a mode-detection read;
the default behaves the same.

Run it by hand to check it starts:

```bash
cd mcp && uv run tracefinity-mcp
# or, with the MCP Inspector UI:
npx @modelcontextprotocol/inspector uv run --directory mcp tracefinity-mcp
```

Config knobs (env): `TRACEFINITY_BASE_URL`, `TRACEFINITY_AUTH_MODE`,
`TRACEFINITY_SECRET_DIR`, `TRACEFINITY_DOWNLOAD_DIR`.
