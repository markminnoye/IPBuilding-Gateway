# Web UI Backup / Restore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an operator download `devices.json`, upload a validated replacement, or reset it to empty, from the ingress Web UI.

**Architecture:** Three new REST endpoints on `GatewayAPI` (export/import/reset) reuse the existing `AtomicWriter` flock and the existing `InstallationConfig._parse()` validation (the same code the gateway uses at boot). A new "Backup & restore" section in the self-contained `webui.py` HTML/JS drives them via relative `fetch()` calls, per the file's ingress constraint.

**Tech Stack:** Python 3, aiohttp (server), vanilla JS (ingress page), pytest + aiohttp `TestClient`/`TestServer`.

## Global Constraints

- All `fetch()` calls added to `gateway/webui.py` MUST use relative paths (e.g. `"api/v1/devices/export"`, never a leading `/`) — see the module docstring at the top of that file.
- The three new static routes (`/api/v1/devices/export`, `/api/v1/devices/import`, `/api/v1/devices/reset`) MUST be registered in `GatewayAPI.start()` **before** the existing `add_get("/api/v1/devices/{device_id}", ...)` line, or the dynamic route swallows them (see Task 3 for why).
- Import/reset writes MUST go through `self._writer` (`AtomicWriter`), the same flock-protected path PATCH uses. Never write `cfg.devices_file` directly.
- No automatic backup before overwrite (decided trade-off — Download is the backup mechanism).
- Upload validation is structural only: anything `InstallationConfig._parse()` accepts is a valid upload, including `{"modules": []}`. No extra business-rule checks (e.g. "must have active channels").
- Reset confirmation is a plain browser `confirm()` — no type-to-confirm UI.
- Export response `Content-Type` MUST be `application/octet-stream`, not `application/json` — see Task 2 for why (the shared `_api_error_middleware` would otherwise rebuild the response and drop the `Content-Disposition` header).

---

### Task 1: `validate_devices_document` helper

**Files:**
- Modify: `gateway/device_config.py`
- Test: `tests/test_device_config.py`

**Interfaces:**
- Consumes: `gateway.installation.InstallationConfig._parse(raw: dict) -> InstallationConfig`, `gateway.installation.InstallationError`, `gateway.device_config.DeviceConfigError(code: str, message: str, details: dict | None = None)` (all already exist).
- Produces: `gateway.device_config.validate_devices_document(raw: object) -> dict` — returns `raw` unchanged on success, raises `DeviceConfigError` (code `"invalid_devices_file"`) on any structural problem. Task 4 (import handler) calls this directly.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_device_config.py` (new import `validate_devices_document`, new test class at end of file):

```python
from gateway.device_config import (
    DeviceConfigError,
    apply_channel_patch,
    apply_pushbutton_patch,
    installation_to_raw_dict,
    validate_channel_fields,
    validate_devices_document,
    validate_pushbutton_fields,
)
```

```python
class TestValidateDevicesDocument:
    def test_accepts_empty_modules(self) -> None:
        raw = {"modules": []}
        assert validate_devices_document(raw) == raw

    def test_accepts_well_formed_document(self) -> None:
        raw = {
            "modules": [
                {
                    "name": "IP0200PoE",
                    "ip": "10.10.1.30",
                    "type": "relay",
                    "mac": "00:24:77:52:ac:be",
                    "channels": [
                        {
                            "ch": 0,
                            "name": "Keuken LED",
                            "room": "Keuken",
                            "semantic_type": "light",
                            "active": True,
                            "max_watt": 60,
                        }
                    ],
                },
            ]
        }
        assert validate_devices_document(raw) == raw

    def test_rejects_non_dict(self) -> None:
        with pytest.raises(DeviceConfigError) as exc_info:
            validate_devices_document([1, 2, 3])
        assert exc_info.value.code == "invalid_devices_file"

    def test_rejects_duplicate_mac(self) -> None:
        raw = {
            "modules": [
                {"name": "A", "ip": "10.10.1.30", "type": "relay",
                 "mac": "00:24:77:52:ac:be", "channels": []},
                {"name": "B", "ip": "10.10.1.31", "type": "relay",
                 "mac": "00:24:77:52:ac:be", "channels": []},
            ]
        }
        with pytest.raises(DeviceConfigError) as exc_info:
            validate_devices_document(raw)
        assert exc_info.value.code == "invalid_devices_file"
        assert "Duplicate module MAC" in exc_info.value.message

    def test_rejects_unknown_module_type(self) -> None:
        raw = {"modules": [{"name": "A", "ip": "10.10.1.30", "type": "bogus"}]}
        with pytest.raises(DeviceConfigError) as exc_info:
            validate_devices_document(raw)
        assert exc_info.value.code == "invalid_devices_file"

    def test_rejects_old_flat_buttons_format(self) -> None:
        raw = {"modules": [], "buttons": []}
        with pytest.raises(DeviceConfigError) as exc_info:
            validate_devices_document(raw)
        assert exc_info.value.code == "invalid_devices_file"
        assert "Old flat devices.json format" in exc_info.value.message
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_device_config.py::TestValidateDevicesDocument -v`
Expected: FAIL with `ImportError: cannot import name 'validate_devices_document'`

- [ ] **Step 3: Implement `validate_devices_document`**

In `gateway/device_config.py`, change the import line:

```python
from gateway.installation import InstallationConfig
```
to:
```python
from gateway.installation import InstallationConfig, InstallationError
```

Then add this function after `validate_pushbutton_fields` (before `apply_channel_patch`):

```python
def validate_devices_document(raw: object) -> dict:
    """Validate a full devices.json document for import (POST /api/v1/devices/import).

    Runs it through InstallationConfig._parse — the same code the gateway uses
    at boot — so "if it imports, the gateway boots with it". Returns ``raw``
    unchanged on success. Raises DeviceConfigError (matching the PATCH error
    model) on any structural problem: not a dict, invalid module type,
    duplicate MAC/IP/device id, or the old flat top-level "buttons" format.
    """
    if not isinstance(raw, dict):
        raise DeviceConfigError(
            "invalid_devices_file", "Document must be a JSON object"
        )
    try:
        InstallationConfig._parse(raw)
    except InstallationError as exc:
        raise DeviceConfigError("invalid_devices_file", str(exc)) from exc
    return raw
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_device_config.py -v`
Expected: all PASS (existing tests + new `TestValidateDevicesDocument` class)

- [ ] **Step 5: Commit**

```bash
git add gateway/device_config.py tests/test_device_config.py
git commit -m "feat: add validate_devices_document for full devices.json import validation"
```

---

### Task 2: `ModuleMetadataCache.clear()`

**Files:**
- Modify: `gateway/module_metadata.py`
- Test: `tests/test_module_metadata.py`

**Interfaces:**
- Consumes: `ModuleMetadataCache._by_mac: dict[str, ModuleMetadata]` (existing private attribute).
- Produces: `ModuleMetadataCache.clear() -> None` — empties the cache. Task 5 (import handler) and Task 6 (reset handler) call this after a wholesale devices.json replacement, since old cached `getSysSet`/`getButtons` data no longer corresponds to any module in the new installation.

- [ ] **Step 1: Write the failing test**

`tests/test_module_metadata.py` already imports both `ModuleMetadata` and
`ModuleMetadataCache` at the top of the file — no import changes needed. Add
this test class:

```python
class TestModuleMetadataCacheClear:
    def test_clear_empties_cache(self) -> None:
        cache = ModuleMetadataCache()
        cache._by_mac["00:24:77:52:ac:be"] = ModuleMetadata(
            network={}, button="", allow="", buttons=None, fetched_at=None
        )
        assert cache.all_macs() == ["00:24:77:52:ac:be"]
        cache.clear()
        assert cache.all_macs() == []
        assert cache.get("00:24:77:52:ac:be") is None
```

(`ModuleMetadata`'s fields — `network: dict[str, str]`, `button: str`,
`allow: str`, `buttons: list[dict] | None`, `fetched_at: str | None`, all with
defaults — are confirmed at `gateway/module_metadata.py:88-95`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_module_metadata.py::TestModuleMetadataCacheClear -v`
Expected: FAIL with `AttributeError: 'ModuleMetadataCache' object has no attribute 'clear'`

- [ ] **Step 3: Implement `clear()`**

In `gateway/module_metadata.py`, add this method to `ModuleMetadataCache` (near `all_macs`):

```python
    def clear(self) -> None:
        """Empty the cache. Used after a wholesale devices.json replacement
        (import/reset), where cached metadata for the old module set is stale."""
        self._by_mac.clear()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_module_metadata.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add gateway/module_metadata.py tests/test_module_metadata.py
git commit -m "feat: add ModuleMetadataCache.clear() for wholesale config replacement"
```

---

### Task 3: `GET /api/v1/devices/export`

**Files:**
- Modify: `gateway/gateway_api.py`
- Test: `tests/test_gateway_api_backup_restore.py` (new)

**Interfaces:**
- Consumes: `self._cfg.devices_file: str` (existing `GatewayConfig` attribute, already used by `AtomicWriter`).
- Produces: `GatewayAPI._get_devices_export(request) -> web.Response`, registered as `GET /api/v1/devices/export`. No later task depends on its internals, only on the route existing.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gateway_api_backup_restore.py`:

```python
"""Tests for GET/POST /api/v1/devices/export|import|reset (backup & restore)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from gateway import gateway_api
from gateway.auto_discovery import DiscoveryConfig
from gateway.device_config import installation_to_raw_dict
from gateway.device_registry import DeviceRegistry
from gateway.installation import InstallationConfig


def _make_installation(modules: list[dict[str, Any]] | None = None) -> InstallationConfig:
    return InstallationConfig._parse({"modules": modules or []})


def _write_devices_file(path: Path, installation: InstallationConfig) -> None:
    path.write_text(json.dumps(installation_to_raw_dict(installation), indent=2), encoding="utf-8")


def _make_api(
    installation: InstallationConfig,
    devices_file: Path,
    metadata_cache: gateway_api.ModuleMetadataCache | None = None,
) -> gateway_api.GatewayAPI:
    bus = MagicMock()
    reg = DeviceRegistry()
    for mc in installation.modules:
        reg.register_module(mc.ip, mc.type)
    cfg = MagicMock()
    cfg.installation = installation
    cfg.devices_file = str(devices_file)
    cfg.discovery = DiscoveryConfig(lock_timeout_s=5.0)
    cfg.api_host = "127.0.0.1"
    cfg.api_port = 8080
    cfg.metadata_timeout_s = 5
    return gateway_api.GatewayAPI(bus, reg, cfg, metadata_cache=metadata_cache)


def _app_with_routes(api: gateway_api.GatewayAPI) -> web.Application:
    app = web.Application(middlewares=[api._api_error_middleware])
    app.router.add_get("/api/v1/devices/export", api._get_devices_export)
    app.router.add_get("/api/v1/devices/{device_id}", api._get_device)
    return app


@pytest.fixture
def sample_installation() -> InstallationConfig:
    return _make_installation([
        {
            "name": "IP0200PoE",
            "ip": "10.10.1.30",
            "type": "relay",
            "mac": "00:24:77:52:ac:be",
            "channels": [
                {
                    "ch": 0,
                    "name": "Keuken LED",
                    "room": "Keuken",
                    "semantic_type": "light",
                    "active": True,
                    "max_watt": 60,
                }
            ],
        }
    ])


class TestExport:
    @pytest.mark.asyncio
    async def test_export_returns_file_bytes_with_attachment_header(
        self, tmp_path: Path, sample_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, sample_installation)
        on_disk_bytes = devices_file.read_bytes()

        api = _make_api(sample_installation, devices_file)
        app = _app_with_routes(api)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/v1/devices/export")
            assert resp.status == 200
            assert "attachment" in resp.headers["Content-Disposition"]
            assert "devices.json" in resp.headers["Content-Disposition"]
            body = await resp.read()
            assert body == on_disk_bytes

    @pytest.mark.asyncio
    async def test_export_missing_file_returns_404(self, tmp_path: Path) -> None:
        devices_file = tmp_path / "does_not_exist.json"
        api = _make_api(_make_installation(), devices_file)
        app = _app_with_routes(api)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/v1/devices/export")
            assert resp.status == 404
            body = await resp.json()
            assert body["error"] == "devices_file_missing"

    @pytest.mark.asyncio
    async def test_export_route_not_shadowed_by_dynamic_device_route(
        self, tmp_path: Path, sample_installation: InstallationConfig
    ) -> None:
        """Regression: /api/v1/devices/export must not be swallowed by
        GET /api/v1/devices/{device_id} as device_id="export"."""
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, sample_installation)
        api = _make_api(sample_installation, devices_file)
        app = _app_with_routes(api)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/v1/devices/export")
            # A 404 device_not_found here (rather than 200 with Content-Disposition)
            # would mean the dynamic route won — the real bug this test guards against.
            assert resp.status == 200
            assert "Content-Disposition" in resp.headers
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_gateway_api_backup_restore.py -v`
Expected: FAIL with `AttributeError: 'GatewayAPI' object has no attribute '_get_devices_export'`

- [ ] **Step 3: Implement the export handler**

In `gateway/gateway_api.py`, add this method in the "REST handlers" section, directly after `_get_devices` (around line 416):

```python
    async def _get_devices_export(self, request: web.Request) -> web.Response:
        """GET /api/v1/devices/export — download devices.json as-is from disk.

        Returns the exact on-disk bytes (not re-serialized) so the download is
        byte-identical to what the running gateway loaded. Uses
        application/octet-stream (not application/json) so
        _api_error_middleware's schema_version stamping — which rebuilds the
        response via web.json_response() and would silently drop the
        Content-Disposition header — never triggers for this route.
        """
        try:
            with open(self._cfg.devices_file, "rb") as fh:
                data = fh.read()
        except FileNotFoundError:
            raise ApiError(404, "devices_file_missing")

        return web.Response(
            body=data,
            content_type="application/octet-stream",
            headers={"Content-Disposition": 'attachment; filename="devices.json"'},
        )
```

Then in `start()`, insert the route registration **before** the existing `add_get("/api/v1/devices/{device_id}", ...)` block (around line 194-198):

```python
        self._app.router.add_get("/api/v1/devices", self._get_devices)
        # Static devices/* sub-routes MUST be registered before the dynamic
        # {device_id} route below — aiohttp resolves routes in registration
        # order, and {device_id} matches literal segments like "export" too.
        self._app.router.add_get(
            "/api/v1/devices/export", self._get_devices_export
        )
        self._app.router.add_get(
            "/api/v1/devices/{device_id}",
            self._get_device,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_gateway_api_backup_restore.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add gateway/gateway_api.py tests/test_gateway_api_backup_restore.py
git commit -m "feat: add GET /api/v1/devices/export endpoint"
```

---

### Task 4: `POST /api/v1/devices/import`

**Files:**
- Modify: `gateway/gateway_api.py`
- Test: `tests/test_gateway_api_backup_restore.py`

**Interfaces:**
- Consumes: `validate_devices_document(raw: object) -> dict` (Task 1), `self._writer.write(data: dict) -> bool` (existing `AtomicWriter` method — see `gateway/auto_discovery.py`), `self._meta_cache.clear() -> None` (Task 2), `DeviceConfigError` (existing).
- Produces: `GatewayAPI._post_devices_import(request) -> web.Response`, registered as `POST /api/v1/devices/import`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_gateway_api_backup_restore.py`. First extend `_app_with_routes`:

```python
def _app_with_routes(api: gateway_api.GatewayAPI) -> web.Application:
    app = web.Application(middlewares=[api._api_error_middleware])
    app.router.add_get("/api/v1/devices/export", api._get_devices_export)
    app.router.add_post("/api/v1/devices/import", api._post_devices_import)
    app.router.add_post("/api/v1/devices/reset", api._post_devices_reset)
    app.router.add_get("/api/v1/devices/{device_id}", api._get_device)
    return app
```

(This replaces the `_app_with_routes` from Task 3 — same function, more routes registered. Reset route is included now since Task 5's tests reuse this same fixture function.)

Then add the test class:

```python
class TestImport:
    @pytest.mark.asyncio
    async def test_import_valid_document_replaces_file_and_reloads(
        self, tmp_path: Path, sample_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, sample_installation)
        api = _make_api(sample_installation, devices_file)
        app = _app_with_routes(api)

        new_doc = {
            "modules": [
                {
                    "name": "IP0200PoE",
                    "ip": "10.10.1.40",
                    "type": "relay",
                    "mac": "00:24:77:52:ac:cf",
                    "channels": [
                        {"ch": 0, "name": "Nieuwe lamp", "room": "Bureau",
                         "semantic_type": "light", "active": True, "max_watt": 20},
                        {"ch": 1, "name": "Extra", "room": "Bureau",
                         "semantic_type": "switch", "active": True, "max_watt": 0},
                    ],
                }
            ]
        }

        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/api/v1/devices/import",
                data=json.dumps(new_doc),
                headers={"Content-Type": "application/json"},
            )
            assert resp.status == 200
            body = await resp.json()
            assert body["ok"] is True
            assert body["modules"] == 1
            assert body["channels"] == 2
            assert body["pushbuttons"] == 0

        on_disk = json.loads(devices_file.read_text(encoding="utf-8"))
        assert on_disk == new_doc
        assert api._cfg.installation.module_by_ip("10.10.1.40") is not None
        assert api._cfg.installation.module_by_ip("10.10.1.30") is None

    @pytest.mark.asyncio
    async def test_import_empty_modules_is_valid(
        self, tmp_path: Path, sample_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, sample_installation)
        api = _make_api(sample_installation, devices_file)
        app = _app_with_routes(api)

        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/api/v1/devices/import",
                data=json.dumps({"modules": []}),
                headers={"Content-Type": "application/json"},
            )
            assert resp.status == 200
            body = await resp.json()
            assert body["modules"] == 0

    @pytest.mark.asyncio
    async def test_import_invalid_json_returns_400(
        self, tmp_path: Path, sample_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, sample_installation)
        original_bytes = devices_file.read_bytes()
        api = _make_api(sample_installation, devices_file)
        app = _app_with_routes(api)

        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/api/v1/devices/import",
                data="{not valid json",
                headers={"Content-Type": "application/json"},
            )
            assert resp.status == 400
            body = await resp.json()
            assert body["error"] == "invalid_json"

        assert devices_file.read_bytes() == original_bytes

    @pytest.mark.asyncio
    async def test_import_duplicate_mac_returns_400_and_leaves_file_unchanged(
        self, tmp_path: Path, sample_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, sample_installation)
        original_bytes = devices_file.read_bytes()
        api = _make_api(sample_installation, devices_file)
        app = _app_with_routes(api)

        bad_doc = {
            "modules": [
                {"name": "A", "ip": "10.10.1.30", "type": "relay",
                 "mac": "00:24:77:52:ac:be", "channels": []},
                {"name": "B", "ip": "10.10.1.31", "type": "relay",
                 "mac": "00:24:77:52:ac:be", "channels": []},
            ]
        }

        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/api/v1/devices/import",
                data=json.dumps(bad_doc),
                headers={"Content-Type": "application/json"},
            )
            assert resp.status == 400
            body = await resp.json()
            assert body["error"] == "invalid_devices_file"

        assert devices_file.read_bytes() == original_bytes

    @pytest.mark.asyncio
    async def test_import_old_flat_buttons_format_returns_400(
        self, tmp_path: Path, sample_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, sample_installation)
        api = _make_api(sample_installation, devices_file)
        app = _app_with_routes(api)

        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/api/v1/devices/import",
                data=json.dumps({"modules": [], "buttons": []}),
                headers={"Content-Type": "application/json"},
            )
            assert resp.status == 400
            body = await resp.json()
            assert body["error"] == "invalid_devices_file"

    @pytest.mark.asyncio
    async def test_import_clears_stale_metadata_cache(
        self, tmp_path: Path, sample_installation: InstallationConfig
    ) -> None:
        from gateway.module_metadata import ModuleMetadata, ModuleMetadataCache

        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, sample_installation)
        cache = ModuleMetadataCache()
        cache._by_mac["00:24:77:52:ac:be"] = ModuleMetadata(
            network={}, button="", allow="", buttons=None, fetched_at=None
        )
        api = _make_api(sample_installation, devices_file, metadata_cache=cache)
        app = _app_with_routes(api)

        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/api/v1/devices/import",
                data=json.dumps({"modules": []}),
                headers={"Content-Type": "application/json"},
            )
            assert resp.status == 200

        assert cache.all_macs() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_gateway_api_backup_restore.py::TestImport -v`
Expected: FAIL with `AttributeError: 'GatewayAPI' object has no attribute '_post_devices_import'`

- [ ] **Step 3: Implement the import handler**

In `gateway/gateway_api.py`, add the import at the top with the other `device_config` imports (existing block around line 33-40):

```python
from gateway.device_config import (
    DeviceConfigError,
    apply_channel_patch,
    apply_pushbutton_patch,
    installation_to_raw_dict,
    validate_channel_fields,
    validate_devices_document,
    validate_pushbutton_fields,
)
```

Add this method after `_get_devices_export` (Task 3):

```python
    async def _post_devices_import(self, request: web.Request) -> web.Response:
        """POST /api/v1/devices/import — replace devices.json wholesale.

        Body is the full replacement document (raw JSON, not multipart). Validated
        via validate_devices_document (the same InstallationConfig._parse used at
        boot) before anything is written.
        """
        try:
            body = await request.json()
        except Exception:
            raise ApiError(400, "invalid_json", "Body must be valid JSON")

        try:
            validated = validate_devices_document(body)
        except DeviceConfigError as exc:
            raise ApiError(400, exc.code, exc.message, exc.details)

        ok = await asyncio.to_thread(self._writer.write, validated)
        if not ok:
            raise ApiError(503, "write_locked", "devices.json is locked; retry later")

        self._cfg.installation = InstallationConfig.load(self._cfg.devices_file)
        self._meta_cache.clear()
        asyncio.create_task(self._broadcast(self._build_snapshot()))

        installation = self._cfg.installation
        channel_count = sum(len(mc.channels) for mc in installation.modules)
        return web.json_response({
            "ok": True,
            "modules": len(installation.modules),
            "channels": channel_count,
            "pushbuttons": len(installation.pushbuttons),
            "schema_version": 2,
        })
```

Then in `start()`, register the route in the same block added in Task 3 (before the dynamic `{device_id}` route):

```python
        self._app.router.add_get(
            "/api/v1/devices/export", self._get_devices_export
        )
        self._app.router.add_post(
            "/api/v1/devices/import", self._post_devices_import
        )
        self._app.router.add_get(
            "/api/v1/devices/{device_id}",
            self._get_device,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_gateway_api_backup_restore.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add gateway/gateway_api.py tests/test_gateway_api_backup_restore.py
git commit -m "feat: add POST /api/v1/devices/import endpoint with structural validation"
```

---

### Task 5: `POST /api/v1/devices/reset`

**Files:**
- Modify: `gateway/gateway_api.py`
- Test: `tests/test_gateway_api_backup_restore.py`

**Interfaces:**
- Consumes: same as Task 4 (`self._writer.write`, `self._meta_cache.clear`, `InstallationConfig.load`).
- Produces: `GatewayAPI._post_devices_reset(request) -> web.Response`, registered as `POST /api/v1/devices/reset`.

- [ ] **Step 1: Write the failing tests**

`_app_with_routes` already registers `/api/v1/devices/reset` from Task 4's step 1 edit — no fixture change needed. Add this test class to `tests/test_gateway_api_backup_restore.py`:

```python
class TestReset:
    @pytest.mark.asyncio
    async def test_reset_empties_devices_file(
        self, tmp_path: Path, sample_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, sample_installation)
        api = _make_api(sample_installation, devices_file)
        app = _app_with_routes(api)

        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/api/v1/devices/reset")
            assert resp.status == 200
            body = await resp.json()
            assert body["ok"] is True

        on_disk = json.loads(devices_file.read_text(encoding="utf-8"))
        assert on_disk == {"modules": []}
        assert api._cfg.installation.modules == []

    @pytest.mark.asyncio
    async def test_reset_clears_metadata_cache(
        self, tmp_path: Path, sample_installation: InstallationConfig
    ) -> None:
        from gateway.module_metadata import ModuleMetadata, ModuleMetadataCache

        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, sample_installation)
        cache = ModuleMetadataCache()
        cache._by_mac["00:24:77:52:ac:be"] = ModuleMetadata(
            network={}, button="", allow="", buttons=None, fetched_at=None
        )
        api = _make_api(sample_installation, devices_file, metadata_cache=cache)
        app = _app_with_routes(api)

        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/api/v1/devices/reset")
            assert resp.status == 200

        assert cache.all_macs() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_gateway_api_backup_restore.py::TestReset -v`
Expected: FAIL with `AttributeError: 'GatewayAPI' object has no attribute '_post_devices_reset'`

- [ ] **Step 3: Implement the reset handler**

Add this method after `_post_devices_import` in `gateway/gateway_api.py`:

```python
    async def _post_devices_reset(self, request: web.Request) -> web.Response:
        """POST /api/v1/devices/reset — empty devices.json to {"modules": []}.

        Same write/reload/broadcast path as import; the "document" is fixed
        rather than client-supplied.
        """
        ok = await asyncio.to_thread(self._writer.write, {"modules": []})
        if not ok:
            raise ApiError(503, "write_locked", "devices.json is locked; retry later")

        self._cfg.installation = InstallationConfig.load(self._cfg.devices_file)
        self._meta_cache.clear()
        asyncio.create_task(self._broadcast(self._build_snapshot()))

        return web.json_response({"ok": True, "schema_version": 2})
```

Register the route in `start()`, in the same block (still before the dynamic route):

```python
        self._app.router.add_post(
            "/api/v1/devices/import", self._post_devices_import
        )
        self._app.router.add_post(
            "/api/v1/devices/reset", self._post_devices_reset
        )
        self._app.router.add_get(
            "/api/v1/devices/{device_id}",
            self._get_device,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_gateway_api_backup_restore.py -v`
Expected: all PASS

- [ ] **Step 5: Run the full test suite to confirm no regressions**

Run: `pytest tests/ -v`
Expected: all PASS (in particular `test_gateway_api_devices_patch.py`, `test_gateway_api_webui.py`, `test_installation.py`, `test_device_config.py` unaffected)

- [ ] **Step 6: Commit**

```bash
git add gateway/gateway_api.py tests/test_gateway_api_backup_restore.py
git commit -m "feat: add POST /api/v1/devices/reset endpoint"
```

---

### Task 6: Web UI — "Backup & restore" section

**Files:**
- Modify: `gateway/webui.py`
- Test: `tests/test_gateway_api_webui.py`

**Interfaces:**
- Consumes: the three endpoints from Tasks 3–5 (`GET api/v1/devices/export`, `POST api/v1/devices/import`, `POST api/v1/devices/reset`), all relative paths.
- Produces: HTML section + JS wiring inside the `INDEX_HTML` string constant. No other task depends on this.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_gateway_api_webui.py` (append to the existing `TestWebUiRoute` class, using the existing `_make_api` fixture already in that file):

```python
    @pytest.mark.asyncio
    async def test_webui_html_has_backup_restore_section(self, tmp_path: Path) -> None:
        api = _make_api(tmp_path)
        app = web.Application(middlewares=[api._api_error_middleware])
        app.router.add_get("/", api._get_webui)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            body = await resp.text()

        assert "Backup" in body
        assert "api/v1/devices/export" in body
        assert "api/v1/devices/import" in body
        assert "api/v1/devices/reset" in body

    @pytest.mark.asyncio
    async def test_webui_backup_restore_uses_relative_fetch_paths(self, tmp_path: Path) -> None:
        api = _make_api(tmp_path)
        app = web.Application(middlewares=[api._api_error_middleware])
        app.router.add_get("/", api._get_webui)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            body = await resp.text()

        assert '"/api/v1/devices/export"' not in body
        assert '"/api/v1/devices/import"' not in body
        assert '"/api/v1/devices/reset"' not in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_gateway_api_webui.py -v`
Expected: FAIL — `assert "Backup" in body` fails (section doesn't exist yet)

- [ ] **Step 3: Add the HTML section**

In `gateway/webui.py`, add a new `<section>` immediately after the existing `danger-zone` section (after the closing `</section>` that follows `discoverStatus`/`discoverModules`, before the `<script>` tag):

```html
<section class="danger-zone">
  <h2>Backup &amp; restore</h2>
  <p class="danger-note">Manage devices.json directly. Upload and Reset overwrite the running configuration.</p>
  <div class="danger-action">
    <button id="exportDevices" class="btn-icon" type="button">Download devices.json</button>
    <span id="exportStatus" class="status"></span>
    <p class="danger-desc">Downloads the exact file currently on disk.</p>
  </div>
  <div class="danger-action">
    <button id="importDevices" class="btn-icon" type="button">Upload devices.json</button>
    <input id="importFile" type="file" accept=".json,application/json" style="display:none">
    <span id="importStatus" class="status"></span>
    <p class="danger-desc">Validates the file before replacing devices.json. Rejected on any structural error — nothing is written.</p>
  </div>
  <div class="danger-action">
    <button id="resetDevices" class="btn-icon btn-scan" type="button">Reset devices.json</button>
    <span id="resetStatus" class="status"></span>
    <p class="danger-desc">Empties devices.json (removes all modules and devices). Cannot be undone — download a backup first.</p>
  </div>
</section>
```

- [ ] **Step 4: Add the JS wiring**

In `gateway/webui.py`, inside the existing `<script>` IIFE, add these constants near the top alongside `DEVICES_URL`/`MODULES_URL`:

```javascript
  var EXPORT_URL = "api/v1/devices/export";
  var IMPORT_URL = "api/v1/devices/import";
  var RESET_URL = "api/v1/devices/reset";
```

Add these functions and wiring calls right before the final `wireScanButton("discoverModules", ...)` call (so they run during the same IIFE setup):

```javascript
  function wireExportButton() {
    var button = document.getElementById("exportDevices");
    var status = document.getElementById("exportStatus");
    button.addEventListener("click", function () {
      button.disabled = true;
      setStatus(status, "Downloading…", "");
      fetch(EXPORT_URL)
        .then(function (resp) {
          if (!resp.ok) {
            return resp.json().then(function (body) {
              throw new Error(describeActionError(resp.status, body));
            });
          }
          return resp.blob();
        })
        .then(function (blob) {
          var url = URL.createObjectURL(blob);
          var a = document.createElement("a");
          a.href = url;
          a.download = "devices.json";
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
          setStatus(status, "Downloaded", "ok");
        })
        .catch(function (err) {
          setStatus(status, err.message || "Network error", "err");
        })
        .then(function () {
          button.disabled = false;
        });
    });
  }

  function wireImportButton() {
    var button = document.getElementById("importDevices");
    var fileInput = document.getElementById("importFile");
    var status = document.getElementById("importStatus");
    button.addEventListener("click", function () {
      fileInput.click();
    });
    fileInput.addEventListener("change", function () {
      var file = fileInput.files[0];
      fileInput.value = "";
      if (!file) return;
      setStatus(status, "Uploading…", "");
      var reader = new FileReader();
      reader.onload = function () {
        fetch(IMPORT_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: reader.result,
        })
          .then(function (resp) {
            return resp.json().then(function (body) {
              return { status: resp.status, body: body };
            });
          })
          .then(function (result) {
            if (result.status === 200) {
              setStatus(
                status,
                "Loaded " + result.body.modules + " module(s), " +
                  result.body.channels + " channel(s)",
                "ok"
              );
              load();
            } else {
              setStatus(status, describeActionError(result.status, result.body), "err");
            }
          })
          .catch(function () {
            setStatus(status, "Network error", "err");
          });
      };
      reader.onerror = function () {
        setStatus(status, "Could not read file", "err");
      };
      reader.readAsText(file);
    });
  }

  function wireResetButton() {
    var button = document.getElementById("resetDevices");
    var status = document.getElementById("resetStatus");
    button.addEventListener("click", function () {
      if (!confirm("This empties devices.json and removes all devices. Continue?")) {
        return;
      }
      button.disabled = true;
      setStatus(status, "Resetting…", "");
      fetch(RESET_URL, { method: "POST" })
        .then(function (resp) {
          return resp.json().then(function (body) {
            return { status: resp.status, body: body };
          });
        })
        .then(function (result) {
          if (result.status === 200) {
            setStatus(status, "Reset", "ok");
            load();
          } else {
            setStatus(status, describeActionError(result.status, result.body), "err");
          }
        })
        .catch(function () {
          setStatus(status, "Network error", "err");
        })
        .then(function () {
          button.disabled = false;
        });
    });
  }

  wireExportButton();
  wireImportButton();
  wireResetButton();
```

Note: these three `wire*Button()` calls go alongside (not replacing) the existing `wireScanButton("discoverModules", ...)` call and the final `document.getElementById("reload")...` lines already at the bottom of the IIFE.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_gateway_api_webui.py -v`
Expected: all PASS

- [ ] **Step 6: Manual smoke check in a browser**

Run: `python -m gateway.main` (or the project's existing local-dev entrypoint — check `README_gateway.md` if unsure) with a `devices.json` pointed at a temp copy, then open `http://localhost:8080/` (adjust port to `GatewayConfig.api_port`) and:
1. Click "Download devices.json" — confirm a file downloads and its content matches the on-disk file.
2. Click "Upload devices.json", choose a valid file — confirm the table refreshes and the status shows a module/channel count.
3. Choose an invalid file (e.g. malformed JSON) — confirm an inline error appears and the table is unchanged.
4. Click "Reset devices.json" — confirm the browser `confirm()` appears, and after accepting, the table empties.

Expected: all four behaviors match. This step has no automated assertion — it exists because `verification-before-completion` requires exercising the actual UI, not just unit tests, before claiming the feature works.

- [ ] **Step 7: Commit**

```bash
git add gateway/webui.py tests/test_gateway_api_webui.py
git commit -m "feat: add Backup & restore section to ingress Web UI"
```

---

### Task 7: Changelog entry

**Files:**
- Modify: `ipbuilding_gateway/CHANGELOG.md`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing (docs only).

- [ ] **Step 1: Read the current `[Unreleased]` state**

Run: `head -30 ipbuilding_gateway/CHANGELOG.md`

Check whether an `## [Unreleased]` section already exists above `## [1.3.1]`. If yes, add to it. If not, create one.

- [ ] **Step 2: Add the changelog entry**

Insert directly after the `## Versiebeleid` block and before `## [1.3.1] - 2026-07-13` (add a new `## [Unreleased]` heading if one doesn't already exist):

```markdown
## [Unreleased]

### Added
- **Backup & restore in de Web UI.** Download het huidige `devices.json`, upload een handmatig bewerkt bestand (gevalideerd vóór het wordt weggeschreven — een ongeldig bestand wijzigt niets), of reset naar een lege installatie. Nieuwe endpoints: `GET /api/v1/devices/export`, `POST /api/v1/devices/import`, `POST /api/v1/devices/reset`.
```

- [ ] **Step 3: Commit**

```bash
git add ipbuilding_gateway/CHANGELOG.md
git commit -m "docs: changelog entry for Web UI backup/restore"
```

---

## Final Verification

- [ ] Run the full test suite once more: `pytest tests/ -v` — expect all PASS, no skips added.
- [ ] Run `ruff check gateway/ tests/test_gateway_api_backup_restore.py` (or whatever lint command the repo's CI uses — check `.github/` if unsure) and fix any findings.
- [ ] Confirm `git log --oneline` shows one commit per task (7 commits total across this plan), each with a passing test suite at that point.

At this point, hand off to **superpowers:finishing-a-development-branch** to decide how to land the branch (merge/PR/cleanup).
