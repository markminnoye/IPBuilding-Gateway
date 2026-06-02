"""Northbound product API: WebSocket /ws + REST /api/v1/

Replaces the IPBox REST shim on :30200 as the canonical product API.
Uses entity_id format (e.g. "10.10.1.30:relay:0") instead of ipbox_id.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from aiohttp import web
from aiohttp.web import WebSocketResponse

from gateway.config import GatewayConfig
from gateway.device_registry import DeviceKey, DeviceRegistry, DeviceType, RelayState, DimmerState
from gateway.installation import InstallationConfig
from gateway.payloads import encode_relay_command, encode_dim_command, encode_dim_off
from gateway.models import RelayAction, RelayCommand, DimmerCommand
from gateway.udp_bus import UDPBus

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_entity_id(entity_id: str) -> tuple[str, DeviceType, int] | None:
    """Parse entity_id into (module_ip, device_type, channel)."""
    parts = entity_id.split(":")
    if len(parts) != 3:
        return None
    module_ip, dtype_str, ch_str = parts
    try:
        dtype = DeviceType(dtype_str)
        channel = int(ch_str)
        return (module_ip, dtype, channel)
    except ValueError:
        return None


def _entity_id_to_key(entity_id: str) -> DeviceKey | None:
    parsed = _parse_entity_id(entity_id)
    if parsed is None:
        return None
    module_ip, dtype, channel = parsed
    return DeviceKey(dtype, module_ip, channel)


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
    ) -> None:
        self._bus = bus
        self._registry = registry
        self._cfg = config
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        # All active WebSocket connections
        self._ws_clients: set[WebSocketResponse] = set()
        self._ws_lock = asyncio.Lock()
        # Registry callbacks — stored so we can unregister on stop
        self._state_cb: Any = None
        self._button_cb: Any = None

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    async def start(self) -> None:
        """Start the aiohttp API server and register registry callbacks."""
        self._app = web.Application()
        self._app.router.add_get("/ws", self._ws_handler)
        self._app.router.add_get("/api/v1/devices", self._get_devices)
        self._app.router.add_post(
            "/api/v1/devices/{entity_id}/command", self._post_command
        )
        self._app.router.add_post(
            "/api/v1/provision/autonomy", self._post_autonomy
        )

        # Register registry callbacks
        self._state_cb = self._registry.on_state_changed(self._on_state_changed)
        self._button_cb = self._registry.on_button_event(self._on_button_event)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._cfg.api_host, self._cfg.api_port)
        await self._site.start()
        log.info(
            "GatewayAPI started  api=%s:%d",
            self._cfg.api_host,
            self._cfg.api_port,
        )

    async def stop(self) -> None:
        """Stop the server and clean up registry callbacks."""
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
            self._site = None
        if self._state_cb is not None:
            self._registry._state_callbacks[:] = [
                cb for cb in self._registry._state_callbacks
                if cb is not self._state_cb
            ]
            self._state_cb = None
        if self._button_cb is not None:
            self._registry._event_callbacks[:] = [
                cb for cb in self._registry._event_callbacks
                if cb is not self._button_cb
            ]
            self._button_cb = None
        log.info("GatewayAPI stopped")

    # -------------------------------------------------------------------------
    # WebSocket
    # -------------------------------------------------------------------------

    async def _ws_handler(self, request: web.Request) -> WebSocketResponse:
        """Handle WebSocket connections.

        On connect: send device_list (full snapshot).
        Bidirectional: broadcast state_changed/button_event → client;
        receive command → dispatch.
        """
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        async with self._ws_lock:
            self._ws_clients.add(ws)
        log.info("WS client connected (total %d)", len(self._ws_clients))

        try:
            # Send device list snapshot on connect
            device_list = self._build_device_list()
            await ws.send_json({"type": "device_list", "devices": device_list})

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

    async def _get_devices(self, request: web.Request) -> web.Response:
        """GET /api/v1/devices — return full device list as JSON."""
        device_list = self._build_device_list()
        return web.json_response({"devices": device_list})

    async def _post_command(self, request: web.Request) -> web.Response:
        """POST /api/v1/devices/{entity_id}/command — send a command."""
        entity_id = request.match_info["entity_id"]
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

        ok, error = await self._execute_command(entity_id, action, value)
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
    # Command execution
    # -------------------------------------------------------------------------

    async def _execute_command(
        self, entity_id: str, action: str, value: Any
    ) -> tuple[bool, str | None]:
        """Parse entity_id, encode and send the UDP command, wait for reply."""
        parsed = _parse_entity_id(entity_id)
        if parsed is None:
            return False, f"invalid entity_id: {entity_id}"
        module_ip, dtype, channel = parsed

        # Encode the command
        if dtype == DeviceType.RELAY:
            if action == "ON":
                cmd = RelayCommand(channel=channel, action=RelayAction.ON)
            elif action == "OFF":
                cmd = RelayCommand(channel=channel, action=RelayAction.OFF)
            elif action == "PULSE":
                cmd = RelayCommand(channel=channel, action=RelayAction.PULSE)
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

    def _build_device_list(self) -> list[dict[str, Any]]:
        """Build the device_list snapshot from installation config + registry."""
        devices = []
        installation = self._cfg.installation

        for mc in (installation.modules if installation else []):
            for ch in mc.channels:
                # Skip inactive channels
                if not ch.active:
                    continue

                entity_id = f"{mc.ip}:{mc.type.value}:{ch.ch}"
                device: dict[str, Any] = {
                    "id": entity_id,
                    "name": ch.name or f"Ch {ch.ch}",
                    "room": ch.room,
                    "semantic_type": ch.semantic_type,
                    "active": ch.active,
                    "max_watt": ch.max_watt,
                    "firmware": mc.firmware,
                }

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

        entity_id = f"{key.module_ip}:{key.device_type.value}:{key.channel}"
        max_watt = ch_config.max_watt

        if key.device_type == DeviceType.RELAY:
            assert isinstance(new, RelayState)
            return {
                "type": "state_changed",
                "id": entity_id,
                "state": new.state,
                "max_watt": max_watt,
                "current_watt": max_watt if new.state == "on" else 0,
            }
        elif key.device_type == DeviceType.DIMMER:
            assert isinstance(new, DimmerState)
            level = new.level_percent
            return {
                "type": "state_changed",
                "id": entity_id,
                "state": "on" if (level and level > 0) else "off",
                "level": level,
                "max_watt": max_watt,
                "current_watt": (max_watt * level // 100) if level else 0,
            }
        return None

