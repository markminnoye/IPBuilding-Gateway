"""Northbound product API: WebSocket /ws + REST /api/v1/

Replaces the IPBox REST shim on :30200 as the canonical product API.
Uses entity_id format (e.g. "10.10.1.30-0") — type is resolved server-side
from installation config, never trusted from the client.

Module vs device model
----------------------
- **Module** = physical IPBuilding controller (relay/dimmer/input).
  Identified by MAC (module_id).  Exposed via GET /api/v1/modules.
  Runtime metadata (network, button config) fetched via HTTP getSysSet/getButtons
  and cached in ModuleMetadataCache.
- **Device** = logical channel (light, fan, switch) on a module.
  Identified by custom slug or default {module_ip}-{channel}.
  Exposed via GET /api/v1/devices.
- WebSocket sends ``snapshot`` on connect (modules + devices together).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import aiohttp
from aiohttp import web
from aiohttp.web import WebSocketResponse

from gateway.config import GatewayConfig
from gateway.auto_discovery import AtomicWriter
from gateway.device_config import (
    DeviceConfigError,
    apply_channel_patch,
    apply_pushbutton_patch,
    installation_to_raw_dict,
    sync_channels_from_wire,
    sync_input_pushbuttons_from_cache,
    validate_channel_fields,
    validate_devices_document,
    validate_pushbutton_fields,
)
from gateway.device_registry import DeviceKey, DeviceRegistry, DeviceType, RelayState, DimmerState
from gateway.discovery import fetch_module_backup_channels, resolve_module_model
from gateway.health import GatewayHealthMonitor
from gateway.installation import (
    InstallationConfig,
    module_by_northbound_id,
    northbound_module_id,
)
from gateway.module_metadata import ModuleMetadataCache, normalize_button_hardware_id
from gateway.payloads import (
    encode_dim_command,
    encode_dim_off,
    encode_dim_start,
    encode_dim_stop,
    encode_dim_toggle,
    encode_relay_command,
)
from gateway.models import RelayAction, RelayCommand, DimmerCommand
from gateway.udp_bus import UDPBus
from gateway.webui import INDEX_HTML

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _ButtonState:
    """Per-button timing state for press → long_press / multi-press.

    The IP1100PoE wire only carries ``press`` (edge 0x01) and ``release``
    (edge 0x00) frames. ``long_press`` is derived from a per-button
    ``hold_threshold_s``; opt-in ``double_press`` / ``triple_press`` use an
    inter-click window (``multi_press_window_ms``) when enabled.
    """

    press_started_at: float | None = None
    long_press_fired: bool = False
    long_press_handle: asyncio.TimerHandle | None = None
    click_count: int = 0
    multi_handle: asyncio.TimerHandle | None = None


# ---------------------------------------------------------------------------
# REST error model
# ---------------------------------------------------------------------------


class ApiError(Exception):
    """Raised by REST handlers to return a typed error response.

    The companion and any future clients should switch on ``status`` first
    and the ``code`` field of the body. See plan §A.
    """

    def __init__(
        self,
        status: int,
        code: str,
        message: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message or code)
        self.status = status
        self.code = code
        self.message = message or code
        self.details = details or {}


def _json_error(err: ApiError) -> web.Response:
    body: dict[str, Any] = {"error": err.code, "message": err.message}
    if err.details:
        body["details"] = err.details
    return web.json_response(body, status=err.status)


def _resolve_entity_id(
    entity_id: str, installation: InstallationConfig | None
) -> tuple[str, DeviceType, int] | None:
    """Resolve entity_id (device_id) into (module_ip, device_type, channel).

    The device type is looked up from the installation config — never derived
    from the entity_id string itself.  This prevents clients from spoofing
    the device type.

    Returns None if the entity_id is unknown.
    """
    if installation is None:
        return None
    entry = installation.device_id_to_entry(entity_id)
    if entry is None:
        return None
    dtype, module_ip, channel = entry
    return (module_ip, dtype, channel)


# ---------------------------------------------------------------------------
# GatewayAPI
# ---------------------------------------------------------------------------


class GatewayAPI:
    """Northbound WebSocket + REST API server.

    Runs on api_host:api_port (default 0.0.0.0:8080) in parallel with
    the IPBox REST shim on :30200.  Broadcasts state_changed and
    button_event to all connected WebSocket clients.
    """

    def __init__(
        self,
        bus: UDPBus,
        registry: DeviceRegistry,
        config: GatewayConfig,
        metadata_cache: ModuleMetadataCache | None = None,
        health: GatewayHealthMonitor | None = None,
    ) -> None:
        self._bus = bus
        self._registry = registry
        self._cfg = config
        self._meta_cache = metadata_cache or ModuleMetadataCache()
        self._health = health or GatewayHealthMonitor()
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        # All active WebSocket connections
        self._ws_clients: set[WebSocketResponse] = set()
        self._ws_lock = asyncio.Lock()
        # Registry callbacks — stored so we can unregister on stop
        self._state_cb: Any = None
        self._button_cb: Any = None
        # Discovery orchestrator (set after construction via set_orchestrator)
        self._orchestrator: Any = None
        self._health_cb: Callable[[], None] | None = None
        # Per-button timing state (key: hardware id lowercase). Tracks the
        # press→release interval so we can emit long_press after the per-button
        # hold_threshold_s elapses. Only classification lives here — direction
        # and dim-loop logic belong in HA (see plan §6).
        self._button_state: dict[str, _ButtonState] = {}
        lock_timeout_s = (
            config.discovery.lock_timeout_s if config.discovery else 15.0
        )
        self._writer = AtomicWriter(config.devices_file, lock_timeout_s=lock_timeout_s)

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    async def start(self) -> None:
        """Start the aiohttp API server and register registry callbacks."""
        self._app = web.Application(middlewares=[self._api_error_middleware])
        self._app.router.add_get("/", self._get_webui)
        self._app.router.add_get("/ws", self._ws_handler)
        self._app.router.add_get("/health", self._get_health)
        self._app.router.add_get("/api/v1/status", self._get_status)
        self._app.router.add_get("/api/v1/devices", self._get_devices)
        # Static devices/* sub-routes MUST be registered before the dynamic
        # {device_id} route below — aiohttp resolves routes in registration
        # order, and {device_id} matches literal segments like "export" too.
        self._app.router.add_get(
            "/api/v1/devices/export", self._get_devices_export
        )
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
        self._app.router.add_patch(
            "/api/v1/devices/{device_id}",
            self._patch_device,
        )
        self._app.router.add_post(
            "/api/v1/devices/{device_id}/command",
            self._post_command,
        )
        self._app.router.add_post(
            "/api/v1/provision/autonomy", self._post_autonomy
        )
        # Modules resource (module metadata + network config from HTTP cache)
        self._app.router.add_get("/api/v1/modules", self._get_modules)
        self._app.router.add_get(
            "/api/v1/modules/{module_id}", self._get_module
        )
        self._app.router.add_post(
            "/api/v1/modules/{module_id}/refresh", self._post_module_refresh
        )
        self._app.router.add_post("/api/v1/modules/refresh", self._post_modules_refresh)
        # Runtime auto-discovery
        self._app.router.add_post("/api/v1/discover", self._post_discover)

        # Register registry callbacks
        self._state_cb = self._registry.on_state_changed(self._on_state_changed)
        self._button_cb = self._registry.on_button_event(self._on_button_event)
        self._health_cb = self._on_health_changed
        self._health.on_change(self._health_cb)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._cfg.api_host, self._cfg.api_port)
        await self._site.start()
        log.info(
            "GatewayAPI started  api=%s:%d",
            self._cfg.api_host,
            self._cfg.api_port,
        )

    def set_orchestrator(self, orchestrator: Any) -> None:
        """Set the discovery orchestrator (called by main.py after construction)."""
        self._orchestrator = orchestrator

    async def stop(self) -> None:
        """Stop the server and clean up registry callbacks.

        Closes any open WebSocket clients with a 1.0s timeout so a slow
        client can't drag out gateway shutdown. Then aiohttp's
        ``runner.cleanup()`` finishes within a bounded time.
        """
        # Force-close open WS clients first so runner.cleanup() doesn't
        # wait for their linger timeout.
        for ws in list(self._ws_clients):
            try:
                await asyncio.wait_for(ws.close(code=1001, message=b"server shutdown"), timeout=1.0)
            except Exception as exc:
                log.debug("WS close during shutdown: %s", exc)
        if self._runner is not None:
            try:
                await asyncio.wait_for(self._runner.cleanup(), timeout=5.0)
            except asyncio.TimeoutError:
                log.warning("aiohttp runner.cleanup() timed out after 5s")
            except Exception as exc:
                log.warning("aiohttp runner.cleanup() raised: %s", exc)
            finally:
                self._runner = None
                self._site = None
        if self._state_cb is not None:
            self._registry.unregister_state_changed(self._state_cb)
            self._state_cb = None
        if self._button_cb is not None:
            self._registry.unregister_button_event(self._button_cb)
            self._button_cb = None
        if self._health_cb is not None:
            # GatewayHealthMonitor has no unregister; drop reference only.
            self._health_cb = None
        log.info("GatewayAPI stopped")

    # -------------------------------------------------------------------------
    # Middleware
    # -------------------------------------------------------------------------

    @web.middleware
    async def _api_error_middleware(
        self, request: web.Request, handler: Callable
    ) -> web.StreamResponse:
        """Translate ApiError raised in handlers into typed JSON responses.

        Successful responses are wrapped to include ``schema_version: 2`` so
        clients can detect the contract version on every reply.
        """
        try:
            response = await handler(request)
        except ApiError as exc:
            return _json_error(exc)
        except web.HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("Unhandled error in %s", request.path)
            return web.json_response(
                {
                    "error": "internal",
                    "message": str(exc) or "internal server error",
                    "request_id": f"{time.monotonic_ns():x}",
                },
                status=500,
            )

        # Stamp schema_version on JSON responses (success path only).
        if (
            isinstance(response, web.Response)
            and response.content_type == "application/json"
        ):
            try:
                payload = json.loads(response.body)
            except Exception:
                return response
            if isinstance(payload, dict) and "schema_version" not in payload:
                payload["schema_version"] = 2
                response = web.json_response(payload, status=response.status)
        return response

    # -------------------------------------------------------------------------
    # WebSocket
    # -------------------------------------------------------------------------

    async def _ws_handler(self, request: web.Request) -> WebSocketResponse:
        """Handle WebSocket connections.

        On connect: send snapshot (modules + devices).
        Bidirectional: broadcast state_changed/button_event → client;
        receive command → dispatch.

        Keep-alive: server-side heartbeat. The companion runs aiohttp 3.13.5
        client-side which has a known race where PONG frames are sometimes
        consumed by the receive() loop instead of the heartbeat task
        (aio-libs/aiohttp#12030, fixed in 3.14.0). To avoid 30s reconnect
        storms we keep ``heartbeat=None`` on the companion side and let the
        server drive PINGs. 60s is a safe interval: simulated-mode gateways
        have very little WS traffic, and modules are polled every 2s on
        UDP regardless of the WS keep-alive.
        """
        ws = web.WebSocketResponse(heartbeat=60)
        await ws.prepare(request)

        async with self._ws_lock:
            self._ws_clients.add(ws)
        log.info("WS client connected (total %d)", len(self._ws_clients))

        try:
            # Send snapshot on connect
            snapshot = self._build_snapshot()
            await ws.send_json(snapshot)

            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    await self._handle_ws_command(ws, msg.data)
                elif msg.type == web.WSMsgType.ERROR:
                    log.warning("WS error: %s", ws.exception())
        finally:
            async with self._ws_lock:
                self._ws_clients.discard(ws)
            log.info("WS client disconnected (total %d)", len(self._ws_clients))

        return ws

    async def _handle_ws_command(
        self, ws: WebSocketResponse, raw: str
    ) -> None:
        """Parse and dispatch a client → gateway command message."""
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            log.warning("WS received unparseable JSON: %r", raw)
            return

        msg_type = data.get("type")
        if msg_type != "command":
            log.debug("WS ignored non-command message type %r", msg_type)
            return

        entity_id = data.get("id")
        action = data.get("action")
        value = data.get("value")

        if not entity_id or not action:
            log.warning("WS command missing id or action: %s", data)
            return

        ok, error = await self._execute_command(entity_id, action, value)
        await ws.send_json(
            {"type": "command_result", "id": entity_id, "ok": ok, "error": error}
        )

    # -------------------------------------------------------------------------
    # REST handlers
    # -------------------------------------------------------------------------

    async def _get_webui(self, request: web.Request) -> web.Response:
        """GET / — serve the self-contained ingress web UI (device list/editor)."""
        return web.Response(text=INDEX_HTML, content_type="text/html")

    async def _get_health(self, request: web.Request) -> web.Response:
        """GET /health — liveness probe for HA Supervisor watchdog."""
        snap = self._health.snapshot(include_actions=False)
        return web.json_response({
            "status": snap["status"],
            "version": snap["version"],
        })

    async def _get_status(self, request: web.Request) -> web.Response:
        """GET /api/v1/status — full gateway health snapshot."""
        return web.json_response(self._status_payload())

    def _status_payload(self) -> dict[str, Any]:
        """Health snapshot plus deployment-specific hub role fields."""
        body = self._health.snapshot()
        body["hub_role"] = self._cfg.hub_role
        body["input_mode_label"] = self._cfg.input_mode_label
        body["multi_press"] = self._cfg.multi_press
        body["multi_press_window_ms"] = self._cfg.multi_press_window_ms
        return body

    async def _get_devices(self, request: web.Request) -> web.Response:
        """GET /api/v1/devices — return full device list as JSON."""
        raw_include = request.query.get("include_inactive")
        include_inactive: bool | None = None
        if raw_include is not None:
            include_inactive = raw_include.lower() in ("1", "true", "yes")
        device_list = self._build_device_list(include_inactive=include_inactive)
        return web.json_response({"devices": device_list, "schema_version": 2})

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

    async def _get_device(self, request: web.Request) -> web.Response:
        """GET /api/v1/devices/{device_id} — return single device."""
        device_id = request.match_info["device_id"]
        devices = self._build_device_list(include_inactive=True)
        for d in devices:
            if d["id"] == device_id:
                return web.json_response(d)
        raise ApiError(404, "device_not_found", details={"device_id": device_id})

    async def _patch_device(self, request: web.Request) -> web.Response:
        """PATCH /api/v1/devices/{device_id} — update northbound config fields."""
        device_id = request.match_info["device_id"]
        try:
            body = await request.json()
        except Exception:
            raise ApiError(400, "invalid_json", "Body must be valid JSON")

        if not isinstance(body, dict):
            raise ApiError(400, "invalid_json", "Body must be a JSON object")

        if not body:
            raise ApiError(
                400,
                "empty_body",
                "Body must include at least one field to update",
            )

        installation = self._cfg.installation
        if installation is None:
            raise ApiError(500, "no_installation", "No installation loaded")

        channel_entry = installation.device_id_to_entry(device_id)
        button_cfg = installation.pushbutton_by_id(device_id) if channel_entry is None else None

        if channel_entry is None and button_cfg is None:
            raise ApiError(404, "device_not_found", details={"device_id": device_id})

        if channel_entry is not None:
            dtype, module_ip, channel = channel_entry
            try:
                validated = validate_channel_fields(body, module_type=dtype)
            except DeviceConfigError as exc:
                raise ApiError(400, exc.code, exc.message, exc.details)

            def mutate(raw: dict) -> dict:
                inst = InstallationConfig._parse(raw)
                apply_channel_patch(inst, module_ip, channel, validated)
                return installation_to_raw_dict(inst)
        else:
            try:
                validated = validate_pushbutton_fields(body)
            except DeviceConfigError as exc:
                raise ApiError(400, exc.code, exc.message, exc.details)

            def mutate(raw: dict) -> dict:
                inst = InstallationConfig._parse(raw)
                apply_pushbutton_patch(inst, device_id, validated)
                return installation_to_raw_dict(inst)

        try:
            ok, _new_raw = await asyncio.to_thread(
                self._writer.read_modify_write, mutate
            )
        except DeviceConfigError as exc:
            if exc.code == "device_not_found":
                raise ApiError(404, exc.code, exc.message, exc.details)
            raise ApiError(400, exc.code, exc.message, exc.details)
        if not ok:
            raise ApiError(503, "write_locked", "devices.json is locked; retry later")

        self._cfg.installation = InstallationConfig.load(self._cfg.devices_file)
        asyncio.create_task(self._broadcast(self._build_snapshot()))

        device = self._device_dict_for_id(device_id)
        if device is None:
            raise ApiError(404, "device_not_found", details={"device_id": device_id})
        return web.json_response({**device, "schema_version": 2})

    async def _post_command(self, request: web.Request) -> web.Response:
        """POST /api/v1/devices/{device_id}/command — send a command."""
        device_id = request.match_info["device_id"]
        try:
            body = await request.json()
        except Exception:
            raise ApiError(400, "invalid_json", "Body must be valid JSON")

        action = body.get("action")
        value = body.get("value")
        if not action:
            raise ApiError(400, "missing_action", "Body must contain 'action'")

        ok, error = await self._execute_command(device_id, action, value)
        if ok:
            return web.json_response({"ok": True, "schema_version": 2})
        # Map internal error strings to typed codes so the client can act.
        code = "command_failed"
        status = 422
        details: dict[str, Any] = {"device_id": device_id, "action": action}
        if error and "unknown" in error:
            code = "device_not_found"
            status = 404
        elif error == "channel inactive":
            code = "channel_inactive"
            status = 422
        elif error and "unsupported" in error:
            code = "unsupported_action"
            status = 422
            details["valid_actions"] = [
                "ON",
                "OFF",
                "PULSE",
                "TOGGLE",
                "DIM",
                "DIM_START",
                "DIM_STOP",
            ]  # noqa: E501
        raise ApiError(status, code, error or "command failed", details)

    async def _post_autonomy(self, request: web.Request) -> web.Response:
        """POST /api/v1/provision/autonomy — stub for EEPROM sync (Fase 8)."""
        # TODO(Fase 8): implement saveAutonomy → IP1100PoE HTTP API
        log.info("Autonomy provisioning called (stub — Fase 8)")
        raise ApiError(501, "not_implemented", "Autonomy provisioning is not yet implemented")

    # -------------------------------------------------------------------------
    # Module resource (REST)
    # -------------------------------------------------------------------------

    async def persist_pushbuttons_from_cache(
        self, module_mac: str | None = None,
    ) -> None:
        """Public wrapper: write cached getButtons into devices.json."""
        await self._persist_pushbuttons_from_cache(module_mac)

    async def persist_channels_from_backup(
        self, module_mac: str | None = None,
    ) -> None:
        """Fetch backupConfig from relay/dimmer modules and merge channels."""
        await self._persist_channels_from_backup(module_mac)

    async def _persist_pushbuttons_from_cache(
        self, module_mac: str | None = None,
    ) -> None:
        """Merge ModuleMetadataCache getButtons into devices.json on disk."""
        if self._cfg.installation is None:
            return

        def mutate(raw: dict) -> dict:
            inst = InstallationConfig._parse(raw)
            sync_input_pushbuttons_from_cache(
                inst, self._meta_cache, module_mac=module_mac,
            )
            return installation_to_raw_dict(inst)

        try:
            ok, _new_raw = await asyncio.to_thread(
                self._writer.read_modify_write, mutate,
            )
        except Exception:
            log.warning(
                "Failed to persist pushbuttons to devices.json", exc_info=True,
            )
            return
        if not ok:
            log.warning("devices.json locked; pushbuttons not persisted")
            return
        self._cfg.installation = InstallationConfig.load(self._cfg.devices_file)

    async def _persist_channels_from_backup(
        self, module_mac: str | None = None,
    ) -> None:
        """Merge backupConfig channel slots into devices.json on disk."""
        installation = self._cfg.installation
        if installation is None:
            return

        target_mac = module_mac.lower() if module_mac else None
        wire_by_mac: dict[str, list[dict[str, Any]]] = {}

        connector = aiohttp.TCPConnector(limit=8)
        async with aiohttp.ClientSession(connector=connector) as sess:
            tasks: list[tuple[str, asyncio.Task[list[dict[str, Any]]]]] = []
            for mc in installation.modules:
                if mc.type not in (DeviceType.RELAY, DeviceType.DIMMER):
                    continue
                if not mc.mac:
                    continue
                if target_mac is not None and mc.mac.lower() != target_mac:
                    continue

                async def _fetch(module=mc) -> list[dict[str, Any]]:
                    return await fetch_module_backup_channels(
                        module.ip,
                        module.type.value,
                        self._cfg.metadata_timeout_s,
                        sess=sess,
                    )

                tasks.append((mc.mac.lower(), asyncio.create_task(_fetch())))

            for mac, task in tasks:
                try:
                    wire_by_mac[mac] = await task
                except Exception:
                    log.warning(
                        "backupConfig fetch failed for module %s",
                        mac,
                        exc_info=True,
                    )

        if not wire_by_mac:
            return

        def mutate(raw: dict) -> dict:
            inst = InstallationConfig._parse(raw)
            for mc in inst.modules:
                mac_key = mc.mac.lower()
                if target_mac is not None and mac_key != target_mac:
                    continue
                wire = wire_by_mac.get(mac_key)
                if wire:
                    sync_channels_from_wire(mc, wire)
            return installation_to_raw_dict(inst)

        try:
            ok, _new_raw = await asyncio.to_thread(
                self._writer.read_modify_write, mutate,
            )
        except Exception:
            log.warning(
                "Failed to persist channels to devices.json", exc_info=True,
            )
            return
        if not ok:
            log.warning("devices.json locked; channels not persisted")
            return
        self._cfg.installation = InstallationConfig.load(self._cfg.devices_file)

    async def _get_modules(self, request: web.Request) -> web.Response:
        """GET /api/v1/modules — return all modules with cached metadata."""
        module_list = self._build_module_list()
        return web.json_response({"modules": module_list, "schema_version": 2})

    async def _get_module(self, request: web.Request) -> web.Response:
        """GET /api/v1/modules/{module_id} — single module by MAC."""
        module_id = request.match_info["module_id"].lower()
        module_list = self._build_module_list()
        for m in module_list:
            if m["id"] == module_id:
                return web.json_response(m)
        raise ApiError(404, "module_not_found", details={"module_id": module_id})

    async def _post_module_refresh(self, request: web.Request) -> web.Response:
        """POST /api/v1/modules/{module_id}/refresh — reload one module from field bus."""
        installation = self._cfg.installation
        if installation is None:
            raise ApiError(500, "no_installation", "No installation loaded")

        module_id = request.match_info["module_id"]
        mc = module_by_northbound_id(installation, module_id)
        if mc is None:
            raise ApiError(
                404, "module_not_found", details={"module_id": module_id},
            )

        try:
            await self._meta_cache.refresh_one(
                mc, timeout=self._cfg.metadata_timeout_s,
            )
        except Exception as exc:
            log.warning("module refresh failed for %s: %s", module_id, exc)

        await self._persist_pushbuttons_from_cache(
            module_mac=mc.mac or None,
        )
        await self._persist_channels_from_backup(
            module_mac=mc.mac or None,
        )

        asyncio.create_task(self._broadcast(self._build_snapshot()))
        northbound_id = northbound_module_id(mc.mac, mc.ip)
        module_list = self._build_module_list()
        for m in module_list:
            if m["id"] == northbound_id:
                return web.json_response({**m, "schema_version": 2})
        raise ApiError(
            404, "module_not_found", details={"module_id": module_id},
        )

    async def _post_modules_refresh(self, request: web.Request) -> web.Response:
        """POST /api/v1/modules/refresh — reload getSysSet/getButtons from all modules."""
        installation = self._cfg.installation
        if installation is None:
            raise ApiError(500, "no_installation", "No installation loaded")
        try:
            await self._meta_cache.refresh(
                installation, timeout=self._cfg.metadata_timeout_s,
            )
        except Exception as exc:
            log.warning("modules refresh failed: %s", exc)
        await self._persist_pushbuttons_from_cache()
        await self._persist_channels_from_backup()
        # Push the new module + device state to connected clients so freshly
        # discovered input buttons appear in the companion without a reload.
        asyncio.create_task(self._broadcast(self._build_snapshot()))
        module_list = self._build_module_list()
        return web.json_response({"modules": module_list, "schema_version": 2})

    async def _post_discover(self, request: web.Request) -> web.Response:
        """POST /api/v1/discover — run forced discovery (ARP-sweep + HTTP identify).

        Works regardless of passive_arp_monitor / auto_discover_on_start toggles.
        Writes new modules to devices.json with active:false; updates firmware on
        existing modules.
        """
        if self._orchestrator is None:
            raise ApiError(503, "orchestrator_unavailable", "Discovery orchestrator not available")
        try:
            result = await self._orchestrator.run_forced_discovery()
            return web.json_response({**result, "schema_version": 2})
        except Exception as exc:
            log.exception("POST /api/v1/discover failed")
            raise ApiError(500, "discovery_failed", str(exc))

    # -------------------------------------------------------------------------
    # Command execution
    # -------------------------------------------------------------------------

    async def _execute_command(
        self, entity_id: str, action: str, value: Any
    ) -> tuple[bool, str | None]:
        """Resolve entity_id, encode and send the UDP command, wait for reply."""
        parsed = _resolve_entity_id(entity_id, self._cfg.installation)
        if parsed is None:
            return False, f"unknown or invalid entity_id: {entity_id}"
        module_ip, dtype, channel = parsed

        # Refuse commands for inactive channels so a manually-enabled HA entity
        # can't drive UDP traffic to a not-yet-wired relay/dimmer.
        installation = self._cfg.installation
        if installation is not None:
            mc = installation.module_by_ip(module_ip)
            if mc is not None:
                ch_cfg = next((c for c in mc.channels if c.ch == channel), None)
                if ch_cfg is not None and not ch_cfg.active:
                    return False, "channel inactive"

        # Encode the command
        # ``awaits_reply`` is shared across relay and dimmer branches so the
        # post-send "wait for correlate_reply" decision stays in one place.
        # DIM_START is the only fire-and-forget action today; everything else
        # (relay ON/OFF/PULSE/TOGGLE, dimmer DIM/TOGGLE/DIM_STOP) replies with
        # a status frame that must land on the right registry key.
        awaits_reply = True
        if dtype == DeviceType.RELAY:
            if action == "ON":
                cmd = RelayCommand(channel=channel, action=RelayAction.ON)
            elif action == "OFF":
                cmd = RelayCommand(channel=channel, action=RelayAction.OFF)
            elif action == "PULSE":
                cmd = RelayCommand(channel=channel, action=RelayAction.PULSE)
            elif action == "TOGGLE":
                cmd = RelayCommand(channel=channel, action=RelayAction.TOGGLE)
            else:
                return False, f"unsupported relay action: {action}"
            payload = encode_relay_command(cmd)
        elif dtype == DeviceType.DIMMER:
            if action == "DIM":
                level = int(value) if value is not None else 0
                if level == 0:
                    payload = encode_dim_off(channel)
                else:
                    cmd = DimmerCommand(channel=channel, level=level)
                    payload = encode_dim_command(cmd)
            elif action == "TOGGLE":
                payload = encode_dim_toggle(channel)
            elif action == "DIM_START":
                payload = encode_dim_start(channel)
            elif action == "DIM_STOP":
                payload = encode_dim_stop(channel)
            else:
                return False, f"unsupported dimmer action: {action}"
            # DIM_START produces no reply on the wire — the dimmer just begins
            # ramping. TOGGLE/DIM_STOP reply with I0154<ch><VV> (as DIM does),
            # so the channel-less reply still needs to land on the right key.
            if action == "DIM_START":
                awaits_reply = False
            else:
                self._registry.track_dimmer_channel(module_ip, channel)
        else:
            return False, f"unsupported device type: {dtype.value}"

        # Send and wait for reply
        try:
            await self._bus.send_command(module_ip, payload)
            if not awaits_reply:
                # DIM_START — fire-and-forget; no reply to correlate.
                return True, None
            reply = await self._bus.correlate_reply(
                module_ip=module_ip,
                after_ts=self._bus.last_send_ts,
                timeout_ms=self._cfg.reply_timeout_ms,
            )
            if reply is None:
                log.warning(
                    "command %s on %s timed out (no reply)", action, entity_id
                )
            return True, None
        except Exception as exc:
            log.exception("command %s on %s failed: %s", action, entity_id, exc)
            return False, str(exc)

    # -------------------------------------------------------------------------
    # Registry callbacks → broadcast
    # -------------------------------------------------------------------------

    def _on_state_changed(
        self, key: DeviceKey, old: Any, new: Any
    ) -> None:
        msg = self._build_state_changed(key, new)
        if msg:
            asyncio.create_task(self._broadcast(msg))

    _MULTI_ACTION = {1: "single_press", 2: "double_press", 3: "triple_press"}

    def _on_button_event(self, key: DeviceKey, evt: Any) -> None:
        """Classify a raw button event and broadcast press/gestures/release.

        The wire only delivers ``press`` and ``release`` edges. We arm a
        per-button timer on press; if the timer fires before the matching
        release we emit ``long_press`` (the operator's hold threshold from
        ``getButtons.func2.holdSeconds``). On release we cancel the timer;
        if no long_press fired we emit ``single_press`` (or, when global
        ``multi_press`` is enabled, delay until the inter-click window
        expires so ``double_press`` / ``triple_press`` can accumulate),
        then always emit ``release``.
        """
        if not self._cfg.claims_input_modules:
            return
        id_hex = (evt.id_hex or "").lower()
        action = (evt.action or "").lower()
        if not id_hex or action not in ("press", "release"):
            log.debug("Button event ignored: id=%s action=%s", id_hex, action)
            return

        state = self._button_state.setdefault(id_hex, _ButtonState())

        if action == "press":
            # Idempotent: a second press without a release resets the
            # long-press timer. Do NOT reset click_count / multi_handle —
            # a press inside an open multi-press window is the next click.
            if state.long_press_handle is not None:
                state.long_press_handle.cancel()
                state.long_press_handle = None
            state.press_started_at = time.monotonic()
            state.long_press_fired = False
            self._broadcast_button(id_hex, "press")
            # Arm long_press timer.
            threshold = self._button_threshold(id_hex)
            loop = asyncio.get_running_loop()
            state.long_press_handle = loop.call_later(
                threshold, self._fire_long_press, id_hex
            )
        else:  # release
            if state.long_press_handle is not None:
                state.long_press_handle.cancel()
                state.long_press_handle = None
            # press_started_at is the "currently held" sentinel (same guard
            # _fire_long_press uses). A release without an active press —
            # a duplicate release frame, or one with no matching press — must
            # NOT synthesise a single_press, or downstream toggles fire twice.
            had_active_press = state.press_started_at is not None
            was_long = state.long_press_fired
            state.press_started_at = None
            state.long_press_fired = False

            if not had_active_press:
                self._broadcast_button(id_hex, "release")
                return

            if was_long:
                # A hold never participates in multi-press; reset and emit
                # only the raw release edge (long_press already fired).
                state.click_count = 0
                if state.multi_handle is not None:
                    state.multi_handle.cancel()
                    state.multi_handle = None
                self._broadcast_button(id_hex, "release")
                return

            if not self._cfg.multi_press:
                # Default path: immediate single_press.
                self._broadcast_button(id_hex, "single_press")
                self._broadcast_button(id_hex, "release")
                return

            # Multi-press path: count this click and (re)arm the window.
            state.click_count += 1
            if state.multi_handle is not None:
                state.multi_handle.cancel()
            loop = asyncio.get_running_loop()
            state.multi_handle = loop.call_later(
                self._cfg.multi_press_window_ms / 1000.0,
                self._fire_single_or_multi,
                id_hex,
            )
            self._broadcast_button(id_hex, "release")

    def _fire_long_press(self, id_hex: str) -> None:
        """Timer callback: emit long_press if the button is still pressed."""
        state = self._button_state.get(id_hex)
        if state is None or state.press_started_at is None:
            return  # already released; no-op
        state.long_press_fired = True
        state.long_press_handle = None
        self._broadcast_button(id_hex, "long_press")

    def _fire_single_or_multi(self, id_hex: str) -> None:
        """Inter-click window expired: emit single/double/triple_press."""
        state = self._button_state.get(id_hex)
        if state is None or state.click_count == 0:
            return
        count = state.click_count
        state.click_count = 0
        state.multi_handle = None
        # Counts above 3 cap at triple_press but report the true count.
        action = self._MULTI_ACTION.get(count, "triple_press")
        self._broadcast_button(id_hex, action, count=count)

    def _broadcast_button(
        self, id_hex: str, action: str, count: int | None = None
    ) -> None:
        """Send a button_event to all WS clients. Coroutine, scheduled."""
        log.info(
            "BUTTON %s: %s%s", id_hex, action, f" x{count}" if count else ""
        )
        msg: dict[str, Any] = {
            "type": "button_event",
            "id": id_hex,
            "action": action,
        }
        if count is not None:
            msg["count"] = count
        asyncio.create_task(self._broadcast(msg))

    def _button_threshold(self, id_hex: str) -> float:
        """Look up the hold threshold for a button id (seconds)."""
        installation = self._cfg.installation
        if installation is None:
            from gateway.installation import DEFAULT_BUTTON_HOLD_THRESHOLD_S
            return DEFAULT_BUTTON_HOLD_THRESHOLD_S
        return installation.pushbutton_threshold(id_hex)

    def _on_health_changed(self) -> None:
        payload = self._health.snapshot(include_actions=False)
        payload["hub_role"] = self._cfg.hub_role
        payload["input_mode_label"] = self._cfg.input_mode_label
        payload["multi_press"] = self._cfg.multi_press
        payload["multi_press_window_ms"] = self._cfg.multi_press_window_ms
        asyncio.create_task(
            self._broadcast({"type": "gateway_status", **payload})
        )

    async def _broadcast(self, msg: dict) -> None:
        """Send a JSON message to all connected WebSocket clients."""
        async with self._ws_lock:
            clients = list(self._ws_clients)
        dead = []
        for ws in clients:
            if ws.closed:
                dead.append(ws)
                continue
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._ws_lock:
                for ws in dead:
                    self._ws_clients.discard(ws)

    # -------------------------------------------------------------------------
    # Message builders
    # -------------------------------------------------------------------------

    def _build_module_list(self) -> list[dict[str, Any]]:
        """Build the modules list: config fields + cached network/button metadata."""
        installation = self._cfg.installation
        if installation is None:
            return []

        modules: list[dict[str, Any]] = []
        for mc in installation.modules:
            meta = self._meta_cache.get(mc.mac)
            module_id = northbound_module_id(mc.mac, mc.ip)
            entry: dict[str, Any] = {
                "id": module_id,
                "ip": mc.ip,
                "name": mc.name,
                "model": resolve_module_model(mc.model, mc.type.value),
                "type": mc.type.value,
                "firmware": mc.firmware,
                "mac": mc.mac,
            }
            # Runtime-only fields (not persisted to devices.json)
            if mc.last_seen is not None:
                entry["last_seen"] = mc.last_seen
            if mc.last_seen_source:
                entry["last_seen_source"] = mc.last_seen_source
            # Merge cached metadata
            if meta is not None:
                entry["network"] = meta.network
                entry["button"] = meta.button
                entry["allow"] = meta.allow
                if meta.buttons is not None:
                    entry["buttons"] = meta.buttons
                if meta.fetched_at is not None:
                    entry["fetched_at"] = meta.fetched_at
            else:
                entry["network"] = {}
                entry["button"] = ""
                entry["allow"] = ""
            modules.append(entry)

        return modules

    def _build_snapshot(self) -> dict[str, Any]:
        """Build the WebSocket snapshot sent on connect.

        ``schema_version`` bumps when the wire contract changes in a
        backward-compatible way. v1 has no field (implicit). v2 adds
        ``action: "long_press"`` and ``action: "release"`` to button_event
        frames. Older clients ignore unknown fields and unknown action
        values, so v1 clients keep working against a v2 gateway.
        """
        return {
            "type": "snapshot",
            "schema_version": 2,
            "modules": self._build_module_list(),
            "devices": self._build_device_list(),
            "gateway_status": self._health.snapshot(include_actions=False)
            | {
                "hub_role": self._cfg.hub_role,
                "input_mode_label": self._cfg.input_mode_label,
                "multi_press": self._cfg.multi_press,
                "multi_press_window_ms": self._cfg.multi_press_window_ms,
            },
        }

    def _resolve_include_inactive(self, include_inactive: bool | None) -> bool:
        if include_inactive is not None:
            return include_inactive
        return self._cfg.expose_inactive_channels

    def _build_device_list(
        self, *, include_inactive: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Build the device list from installation config + registry.

        Removes firmware (module-level, not per-channel). Adds module_id (MAC),
        module_ip (current), and channel (int).

        Inactive relay/dimmer channels are omitted unless
        ``expose_inactive_channels`` is enabled or ``include_inactive=True``.
        """
        show_inactive = self._resolve_include_inactive(include_inactive)
        devices = []
        installation = self._cfg.installation

        for mc in (installation.modules if installation else []):
            module_id = northbound_module_id(mc.mac, mc.ip)
            for ch in mc.channels:
                if not ch.active and not show_inactive:
                    continue
                device: dict[str, Any] = {
                    "id": ch.id,
                    "module_id": module_id,
                    "module_ip": mc.ip,
                    "channel": ch.ch,
                    "name": ch.name or f"Ch {ch.ch}",
                    "room": ch.room,
                    "semantic_type": ch.semantic_type,
                    "device_type": mc.type.value,
                    "active": ch.active,
                    "max_watt": ch.max_watt,
                }

                # Inactive channels included only when requested; state is fixed
                # to "inactive" (not "unknown") to distinguish "channel disabled
                # in devices.json" from "no recent fieldbus response".
                if not ch.active:
                    device["state"] = "inactive"
                    device["current_watt"] = 0
                    devices.append(device)
                    continue

                # Attach current state from registry
                key = DeviceKey(mc.type, mc.ip, ch.ch)
                if mc.type == DeviceType.RELAY:
                    rs = self._registry.get_relay_state(key)
                    device["state"] = rs.state if rs else "unknown"
                    device["current_watt"] = (
                        ch.max_watt if (rs and rs.state == "on") else 0
                    )
                elif mc.type == DeviceType.DIMMER:
                    ds = self._registry.get_dimmer_state(key)
                    level = ds.level_percent if ds else None
                    device["level"] = level
                    if level is None:
                        # No data yet — distinguish "no recent fieldbus
                        # response" from "off". Previously collapsed to
                        # "off", which the companion rendered as a real
                        # off state right after gateway/companion
                        # restart while the HTTP hydration was still
                        # pending.
                        device["state"] = "unknown"
                        device["current_watt"] = 0
                    elif level > 0:
                        device["state"] = "on"
                        device["current_watt"] = (
                            ch.max_watt * level // 100 if ch.max_watt else 0
                        )
                    else:
                        device["state"] = "off"
                        device["current_watt"] = 0

                devices.append(device)

            if mc.type == DeviceType.INPUT and self._cfg.claims_input_modules:
                meta = self._meta_cache.get(mc.mac)
                if meta is not None and meta.buttons:
                    for btn in meta.buttons:
                        raw_id = btn.get("id")
                        if not raw_id:
                            continue
                        device_id = normalize_button_hardware_id(str(raw_id))
                        meta_name = (
                            btn.get("descr")
                            or btn.get("name")
                            or f"Button {device_id}"
                        )
                        meta_room = btn.get("gr") or btn.get("room") or ""
                        cfg_btn = (
                            installation.pushbutton_by_id(device_id)
                            if installation
                            else None
                        )
                        entry: dict[str, Any] = {
                            "id": device_id,
                            "module_id": module_id,
                            "module_ip": mc.ip,
                            "name": cfg_btn.name or meta_name if cfg_btn else meta_name,
                            "room": cfg_btn.room if cfg_btn is not None else meta_room,
                            "semantic_type": "button",
                            "device_type": "input",
                            "channel": cfg_btn.channel if cfg_btn is not None else btn.get("index"),
                        }
                        if cfg_btn is not None:
                            entry["active"] = cfg_btn.active
                        devices.append(entry)

        return devices

    def _device_dict_for_id(self, device_id: str) -> dict[str, Any] | None:
        """Return a single device dict (GET/PATCH shape) by device id."""
        for d in self._build_device_list(include_inactive=True):
            if d["id"] == device_id:
                return d

        installation = self._cfg.installation
        if installation is None:
            return None

        btn = installation.pushbutton_by_id(device_id)
        if btn is None:
            return None

        mc = (
            module_by_northbound_id(installation, btn.module_id)
            if btn.module_id
            else None
        )
        if mc is None:
            for candidate in installation.modules:
                if any(pb.id.lower() == btn.id.lower() for pb in candidate.pushbuttons):
                    mc = candidate
                    break
        module_id = northbound_module_id(mc.mac, mc.ip) if mc else btn.module_id
        entry: dict[str, Any] = {
            "id": btn.id.lower(),
            "module_id": module_id,
            "module_ip": mc.ip if mc is not None else "",
            "name": btn.name or f"Button {btn.id}",
            "room": btn.room,
            "semantic_type": "button",
            "device_type": "input",
            "active": btn.active,
            "channel": btn.channel,
        }
        return entry

    def _build_state_changed(self, key: DeviceKey, new: Any) -> dict[str, Any] | None:
        """Build a state_changed message for a given device key."""
        # Look up channel config from installation
        installation = self._cfg.installation
        if installation is None:
            return None

        mc = installation.module_by_ip(key.module_ip)
        if mc is None:
            return None

        ch_config = None
        for ch in mc.channels:
            if ch.ch == key.channel:
                ch_config = ch
                break

        if ch_config is None:
            return None

        # Don't push state changes for inactive channels — companion has them
        # marked disabled and doesn't render them.
        if not ch_config.active:
            return None

        device_id = installation.entry_to_device_id(key.device_type, key.module_ip, key.channel)
        if device_id is None:
            return None
        max_watt = ch_config.max_watt

        if key.device_type == DeviceType.RELAY:
            assert isinstance(new, RelayState)
            return {
                "type": "state_changed",
                "id": device_id,
                "state": new.state,
                "max_watt": max_watt,
                "current_watt": max_watt if new.state == "on" else 0,
            }
        elif key.device_type == DeviceType.DIMMER:
            assert isinstance(new, DimmerState)
            level = new.level_percent
            return {
                "type": "state_changed",
                "id": device_id,
                "state": "on" if (level and level > 0) else "off",
                "level": level,
                "max_watt": max_watt,
                "current_watt": (max_watt * level // 100) if level else 0,
            }
        return None

