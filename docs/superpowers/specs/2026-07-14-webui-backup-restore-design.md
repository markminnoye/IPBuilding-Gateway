# Web UI Backup / Restore — Design

**Date:** 2026-07-14
**Status:** Approved (brainstorm), pending implementation plan
**Component:** Gateway northbound API (`gateway/gateway_api.py`) + ingress Web UI (`gateway/webui.py`)

## Summary

Add manual backup/restore for `devices.json` to the ingress Web UI so an operator
can, without shell access to the add-on container:

1. **Download** the current `devices.json` as a file.
2. **Upload** a hand-edited `devices.json`, which is validated before it replaces
   the running config.
3. **Reset** `devices.json` to an empty installation (`{"modules": []}`).

This mirrors the way the existing PATCH flow persists config: validate → atomic
write under the file lock → reload `cfg.installation` → broadcast a fresh snapshot
to WebSocket clients.

## Motivation

`devices.json` is the single source of truth for the installation. Today it can
only be edited through per-field PATCH from the table, or by discovery. There is
no way to take a full backup, restore a known-good copy, or start clean from the
UI — the operator would need container/file access. Backup/restore closes that
gap and gives a safe recovery path when an installation gets into a bad state.

## Requirements

- Download returns the **exact on-disk bytes** of `devices.json` (byte-for-byte
  what the running gateway loaded), as a browser file download.
- Upload accepts a full replacement document, **validates structurally**, and only
  replaces `devices.json` if validation passes.
- Reset empties `devices.json` to `{"modules": []}`.
- All write paths use the existing `AtomicWriter` file lock (same as PATCH), so
  concurrent discovery / PATCH writes cannot interleave.
- After a successful upload or reset, the in-memory installation is reloaded and a
  snapshot is broadcast so connected companions/UI update without a restart.

### Decided trade-offs (from brainstorm)

- **No automatic backup** before overwrite. The Download button is the backup
  mechanism. Keeps the implementation simple and avoids `.bak` file clutter.
- **Structural validation only.** Accept anything `InstallationConfig._parse()`
  loads. An empty `{"modules": []}` document is a valid upload.
- **Simple `confirm()` dialog** for Reset (no type-to-confirm).

### Out of scope (YAGNI)

- Automatic / timestamped / versioned backups.
- Partial upload or merge (upload is always a full replace).
- Non-blocking validation warnings (e.g. "0 active channels").
- Undo after reset.

## Architecture

### New REST endpoints (`gateway/gateway_api.py`)

Registered alongside the existing `/api/v1/devices*` routes in `start()`, and
**before** `add_get("/api/v1/devices/{device_id}", ...)`. aiohttp's router
resolves resources in registration order; `{device_id}` is a dynamic segment
that matches the literal string `"export"` (or `"import"`, `"reset"`) just as
readily as a real device id. If the dynamic route were registered first, `GET
/api/v1/devices/export` would be swallowed by `_get_device` (device_id="export",
404) instead of reaching the export handler. The three new static routes must
therefore be added ahead of the existing dynamic `/api/v1/devices/{device_id}`
GET/PATCH routes.

#### `GET /api/v1/devices/export`

- Reads the raw bytes of `cfg.devices_file` from disk.
- Returns them with:
  - `Content-Type: application/octet-stream` (see note below — **not**
    `application/json`)
  - `Content-Disposition: attachment; filename="devices.json"`
- Serves the exact on-disk content — **not** re-serialized from
  `installation_to_raw_dict()` — so the download equals what is persisted.
- If the file does not exist: `ApiError(404, "devices_file_missing")`.

Note on content type: `_api_error_middleware` inspects every successful
`web.Response` whose `content_type == "application/json"`; if the body parses as
a JSON dict, the middleware **rebuilds the response via `web.json_response(...)`**
to stamp `schema_version`. A fresh `web.json_response` call discards any headers
set on the original response — it would silently drop `Content-Disposition` and
break the browser download. Since `devices.json`'s content (`{"modules": [...]}`)
always parses as a JSON dict, this is not a hypothetical: it fires on every
export. The export handler therefore uses `content_type="application/octet-stream"`
so the middleware's `content_type == "application/json"` guard is `False` and the
response passes through untouched, headers intact. The browser still downloads
correctly — `Content-Disposition: attachment` forces save-as regardless of MIME
type. Verify in tests: the response has the `Content-Disposition` header AND the
body is byte-identical to the file on disk.

#### `POST /api/v1/devices/import`

- Request body: raw JSON (`Content-Type: application/json`) — the full replacement
  document. The browser reads the chosen file client-side via `FileReader` and
  sends its text as the body. No multipart.
- Validation pipeline:
  1. `await request.json()` — invalid JSON → `ApiError(400, "invalid_json")`.
  2. `validate_devices_document(raw)` (new helper, see below) — runs
     `InstallationConfig._parse(raw)`. On `InstallationError`, raise
     `ApiError(400, "invalid_devices_file", message=<InstallationError text>)`.
- On success: persist with `self._writer.write(raw)` (atomic, under flock).
  - Lock timeout (`write()` returns `False`) → `ApiError(503, "write_locked")`.
- After write:
  - `cfg.installation = InstallationConfig.load(cfg.devices_file)`
  - **Clear the whole module-metadata cache** (`self._meta_cache`). An import
    replaces the module set wholesale, so any cached `getSysSet`/`getButtons`
    metadata for the old modules is stale. Clearing is the simplest correct
    behaviour; the next `modules/refresh` (or the periodic refresh) repopulates
    it. If `ModuleMetadataCache` has no `clear()` today, the plan adds a minimal
    one.
  - `asyncio.create_task(self._broadcast(self._build_snapshot()))`
- Response `200`:
  ```json
  { "ok": true, "modules": <n>, "channels": <n>, "pushbuttons": <n>,
    "schema_version": 2 }
  ```
  Counts come from the freshly loaded `cfg.installation`.

#### `POST /api/v1/devices/reset`

- No body required.
- Persist `{"modules": []}` via `self._writer.write({"modules": []})`.
  - Lock timeout → `ApiError(503, "write_locked")`.
- Same post-write reload + cache clear + broadcast as import.
- Response `200`: `{ "ok": true, "schema_version": 2 }`.

### Validation helper (`gateway/device_config.py`)

Add a thin wrapper so the parse rules are not duplicated:

```python
def validate_devices_document(raw: dict) -> dict:
    """Validate a full devices.json document for import.

    Runs it through InstallationConfig._parse (the same code the gateway uses
    at boot), so "if it imports, the gateway boots with it". Returns the raw
    dict unchanged on success. Raises DeviceConfigError on any InstallationError
    so the handler reuses the existing typed-error path.
    """
    if not isinstance(raw, dict):
        raise DeviceConfigError("invalid_devices_file", "Document must be a JSON object")
    try:
        InstallationConfig._parse(raw)
    except InstallationError as exc:
        raise DeviceConfigError("invalid_devices_file", str(exc)) from exc
    return raw
```

The handler maps `DeviceConfigError` → `ApiError(400, exc.code, exc.message)`,
consistent with `_patch_device`.

### Web UI (`gateway/webui.py`)

A new `<section class="danger-zone">` below the existing "Installation & network"
section, titled **"Backup & restore"**, with three actions and per-action status
spans. All `fetch()` calls use **relative** paths (ingress constraint already
documented at the top of the file).

- **Download** — `fetch("api/v1/devices/export")` → `resp.blob()` →
  object URL assigned to a temporary `<a download="devices.json">` that is clicked
  programmatically, then the URL is revoked. This downloads without navigating the
  ingress page away.
- **Upload** — a hidden `<input type="file" accept=".json,application/json">`.
  On change: `FileReader.readAsText` → `POST api/v1/devices/import` with
  `Content-Type: application/json` and the file text as body. On `200`, show
  `"Loaded: N modules, M channels"` and call the existing `load()` to refresh the
  table. On error, show the server `message`. Reset the input value so re-choosing
  the same file fires `change` again.
- **Reset** — `confirm("This empties devices.json and removes all devices. Continue?")`
  → `POST api/v1/devices/reset`. On `200`, show "Reset" and call `load()`.

Two new icons may be added to the existing inline `ICONS` map if needed
(`download` and `upload` MDI paths already exist in the file and can be reused).

### Data flow (upload)

```
file picker → FileReader (client) → POST /api/v1/devices/import (raw JSON body)
  → request.json()  → validate_devices_document → InstallationConfig._parse
  → AtomicWriter.write (flock)  → InstallationConfig.load → clear meta cache
  → broadcast snapshot → 200 {ok, counts}
  → UI: status + load()
```

## Error handling

| Condition | Status | code |
|---|---|---|
| Export: file missing | 404 | `devices_file_missing` |
| Import: body not JSON | 400 | `invalid_json` |
| Import: fails `_parse` | 400 | `invalid_devices_file` |
| Import/reset: lock timeout | 503 | `write_locked` |
| Any handler crash | 500 | `internal` (existing middleware) |

The UI surfaces `body.message` for all error responses (existing
`describeActionError` pattern).

## Testing (TDD)

New `tests/test_gateway_api_backup_restore.py`:

- **Export**: returns 200, `Content-Disposition: attachment`, body byte-identical
  to the file on disk; missing file → 404.
- **Import (valid)**: replaces file, 200 with correct counts, `cfg.installation`
  reloaded, snapshot broadcast; empty `{"modules": []}` accepted.
- **Import (invalid)**: broken JSON → 400 `invalid_json`; duplicate MAC / duplicate
  device id / unknown module type / old flat `buttons[]` → 400
  `invalid_devices_file`; file on disk unchanged after a rejected import.
- **Reset**: file becomes `{"modules": []}`, 200, installation reloaded.
- **Lock timeout**: writer returns False → 503 `write_locked` (file unchanged).

Extend `tests/test_gateway_api_webui.py`:

- HTML contains the three relative endpoint paths (`api/v1/devices/export`,
  `api/v1/devices/import`, `api/v1/devices/reset`) and the "Backup & restore"
  section.

## Changelog

Minor version bump in `ipbuilding_gateway/CHANGELOG.md` (new REST endpoints,
backward-compatible; old companions keep working). Customer-facing note that the
Web UI can now back up, restore, and reset the device configuration.

## Files touched

- `gateway/gateway_api.py` — three handlers + route registration.
- `gateway/device_config.py` — `validate_devices_document` helper.
- `gateway/webui.py` — "Backup & restore" section + JS.
- `tests/test_gateway_api_backup_restore.py` — new.
- `tests/test_gateway_api_webui.py` — extend.
- `ipbuilding_gateway/CHANGELOG.md` — entry.
