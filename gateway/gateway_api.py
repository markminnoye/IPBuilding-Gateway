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
from typing import Any, Callable

from aiohttp import web
from aiohttp.web import WebSocketResponse

from gateway.config import GatewayConfig
from gateway.device_registry import DeviceKey, DeviceRegistry, DeviceType, RelayState, DimmerState
from gateway.health import GatewayHealthMonitor
from gateway.installation import InstallationConfig
from gateway.module_metadata import ModuleMetadataCache, normalize_button_hardware_id
from gateway.payloads import encode_relay_command, encode_dim_command, encode_dim_off
from gateway.models import RelayAction, RelayCommand, DimmerCommand
from gateway.udp_bus import UDPBus

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    async def start(self) -> None:
        """Start the aiohttp API server and register registry callbacks."""
        self._app = web.Application()
        self._app.router.add_get("/ws", self._ws_handler)
        self._app.router.add_get("/health", self._get_health)
        self._app.router.add_get("/api/v1/status", self._get_status)
        self._app.router.add_get("/api/v1/devices", self._get_devices)
        self._app.router.add_get(
            "/api/v1/devices/{device_id}",
            self._get_device,
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

    async def _get_health(self, request: web.Request) -> web.Response:
        """GET /health — liveness probe for HA Supervisor watchdog."""
        snap = self._health.snapshot(include_actions=False)
        return web.json_response({
            "status": snap["status"],
            "version": snap["version"],
        })

    async def _get_status(self, request: web.Request) -> web.Response:
        """GET /api/v1/status — full gateway health snapshot."""
        return web.json_response(self._health.snapshot())

    async def _get_devices(self, request: web.Request) -> web.Response:
        """GET /api/v1/devices — return full device list as JSON."""
        device_list = self._build_device_list()
        return web.json_response({"devices": device_list})

    async def _get_device(self, request: web.Request) -> web.Response:
        """GET /api/v1/devices/{device_id} — return single device."""
        device_id = request.match_info["device_id"]
        devices = self._build_device_list()
        for d in devices:
            if d["id"] == device_id:
                return web.json_response(d)
        return web.json_response({"error": "not found"}, status=404)

    async def _post_command(self, request: web.Request) -> web.Response:
        """POST /api/v1/devices/{device_id}/command — send a command."""
        device_id = request.match_info["device_id"]
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "invalid JSON"}, status=400)

        action = body.get("action")
        value = body.get("value")
        if not action:
            return web.json_response(
                {"ok": False, "error": "missing 'action'"}, status=400
            )

        ok, error = await self._execute_command(device_id, action, value)
        if ok:
            return web.json_response({"ok": True})
        else:
            return web.json_response(
                {"ok": False, "error": error or "command failed"}, status=422
            )

    async def _post_autonomy(self, request: web.Request) -> web.Response:
        """POST /api/v1/provision/autonomy — stub for EEPROM sync (Fase 8)."""
        # TODO(Fase 8): implement saveAutonomy → IP1100PoE HTTP API
        log.info("Autonomy provisioning called (stub — Fase 8)")
        return web.json_response(
            {"ok": False, "error": "not yet implemented"}, status=501
        )

    # -------------------------------------------------------------------------
    # Module resource (REST)
    # -------------------------------------------------------------------------

    async def _get_modules(self, request: web.Request) -> web.Response:
        """GET /api/v1/modules — return all modules with cached metadata."""
        module_list = self._build_module_list()
        return web.json_response({"modules": module_list})

    async def _get_module(self, request: web.Request) -> web.Response:
        """GET /api/v1/modules/{module_id} — single module by MAC."""
        module_id = request.match_info["module_id"].lower()
        module_list = self._build_module_list()
        for m in module_list:
            if m["id"] == module_id:
                return web.json_response(m)
        return web.json_response({"error": "not found"}, status=404)

    async def _post_modules_refresh(self, request: web.Request) -> web.Response:
        """POST /api/v1/modules/refresh — reload getSysSet/getButtons from all modules."""
        installation = self._cfg.installation
        if installation is None:
            return web.json_response({"error": "no installation loaded"}, status=500)
        try:
            await self._meta_cache.refresh(
                installation, timeout=self._cfg.metadata_timeout_s,
            )
        except Exception as exc:
            log.warning("modules refresh failed: %s", exc)
        # Push the new module + device state to connected clients so freshly
        # discovered input buttons appear in the companion without a reload.
        asyncio.create_task(self._broadcast(self._build_snapshot()))
        module_list = self._build_module_list()
        return web.json_response({"modules": module_list})

    async def _post_discover(self, request: web.Request) -> web.Response:
        """POST /api/v1/discover — run forced discovery (ARP-sweep + HTTP identify).

        Works regardless of passive_arp_monitor / auto_discover_on_start toggles.
        Writes new modules to devices.json with active:false; updates firmware on
        existing modules.
        """
        if self._orchestrator is None:
            return web.json_response({"ok": False, "error": "orchestrator not available"}, status=503)
        try:
            result = await self._orchestrator.run_forced_discovery()
            return web.json_response(result)
        except Exception as exc:
            log.exception("POST /api/v1/discover failed")
            return web.json_response({"ok": False, "error": str(exc)}, status=500)

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
            if action != "DIM":
                return False, f"unsupported dimmer action: {action}"
            level = int(value) if value is not None else 0
            if level == 0:
                payload = encode_dim_off(channel)
            else:
                cmd = DimmerCommand(channel=channel, level=level)
                payload = encode_dim_command(cmd)
        else:
            return False, f"unsupported device type: {dtype.value}"

        # Send and wait for reply
        try:
            await self._bus.send_command(module_ip, payload)
            # For dimmer commands, track the channel so that the next status
            # reply (which carries no channel) is stored under the correct key.
            if dtype == DeviceType.DIMMER and action == "DIM":
                self._registry.track_dimmer_channel(module_ip, channel)
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

    def _on_button_event(self, key: DeviceKey, evt: Any) -> None:
        msg = {
            "type": "button_event",
            "id": evt.id_hex,
            "action": evt.action,
        }
        asyncio.create_task(self._broadcast(msg))

    def _on_health_changed(self) -> None:
        payload = self._health.snapshot(include_actions=False)
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
            entry: dict[str, Any] = {
                "id": mc.mac,
                "ip": mc.ip,
                "name": mc.name,
                "model": mc.model,
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
        """Build the WebSocket snapshot sent on connect."""
        return {
            "type": "snapshot",
            "modules": self._build_module_list(),
            "devices": self._build_device_list(),
            "gateway_status": self._health.snapshot(include_actions=False),
        }

    def _build_device_list(self) -> list[dict[str, Any]]:
        """Build the device list from installation config + registry.

        Removes firmware (module-level, not per-channel). Adds module_id (MAC),
        module_ip (current), and channel (int).
        """
        devices = []
        installation = self._cfg.installation

        for mc in (installation.modules if installation else []):
            for ch in mc.channels:
                device: dict[str, Any] = {
                    "id": ch.id,
                    "module_id": mc.mac,
                    "module_ip": mc.ip,
                    "channel": ch.ch,
                    "name": ch.name or f"Ch {ch.ch}",
                    "room": ch.room,
                    "semantic_type": ch.semantic_type,
                    "device_type": mc.type.value,
                    "active": ch.active,
                    "max_watt": ch.max_watt,
                }

                # Inactive channels are still exposed so the companion can show
                # them as disabled+hidden entities. State is fixed to "inactive"
                # (not "unknown") to distinguish "channel disabled in
                # devices.json" from "no recent fieldbus response".
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
                    device["state"] = "on" if (level and level > 0) else "off"
                    if level is not None and ch.max_watt:
                        device["current_watt"] = ch.max_watt * level // 100
                    else:
                        device["current_watt"] = 0

                devices.append(device)

            if mc.type == DeviceType.INPUT:
                meta = self._meta_cache.get(mc.mac)
                if meta is not None and meta.buttons:
                    for btn in meta.buttons:
                        raw_id = btn.get("id")
                        if not raw_id:
                            continue
                        device_id = normalize_button_hardware_id(str(raw_id))
                        devices.append(
                            {
                                "id": device_id,
                                "module_id": mc.mac,
                                "module_ip": mc.ip,
                                "name": btn.get("descr")
                                or btn.get("name")
                                or f"Button {device_id}",
                                "room": btn.get("gr") or btn.get("room") or "",
                                "semantic_type": "button",
                                "device_type": "input",
                                "active": True,
                            }
                        )

        return devices

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

