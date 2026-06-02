"""IPBox-compatible REST shim on :30200 (transition aid).

Maps IPBox REST endpoints to field bus commands via UDPBus + DeviceRegistry.
Not the product API -- see docs/superpowers/specs/2026-05-18-gateway-architecture-design.md.
"""

from __future__ import annotations

import time
from typing import Any

from aiohttp import web

from gateway.config import GatewayConfig
from gateway.device_registry import DeviceKey, DeviceRegistry
from gateway.types import DeviceType
from gateway.installation import InstallationConfig
from gateway.models import DimmerCommand, RelayAction, RelayCommand
from gateway.payloads.dimmer import decode_dimmer_payload, encode_dim_command, encode_dim_off
from gateway.payloads.relay import decode_relay_payload, encode_relay_command
from gateway.udp_bus import UDPBus


class RESTShim:
    def __init__(
        self,
        bus: UDPBus,
        registry: DeviceRegistry,
        config: GatewayConfig | None = None,
    ) -> None:
        self.bus = bus
        self.registry = registry
        self.config = config or GatewayConfig.from_env()
        self.installation = self.config.installation
        self.app = web.Application()
        self.app.router.add_get("/api/v1/comp/items", self.get_comp_items)
        self.app.router.add_get("/api/v1/action/action", self.action_action)

    def _lookup_legacy_id(self, legacy_id: int) -> tuple[DeviceType, str, int] | None:
        """Look up a channel by IPBox legacy_id. Returns (type, module_ip, channel) or None."""
        if self.installation is None:
            return None
        return self.installation.legacy_id_to_channel(legacy_id)

    def _all_items(self) -> list[tuple[int, DeviceType, str, int]]:
        """Return all (legacy_id, device_type, module_ip, channel) from installation."""
        if self.installation is None:
            return []
        result = []
        for legacy_id in self.installation.all_legacy_ids():
            entry = self.installation.legacy_id_to_channel(legacy_id)
            if entry:
                result.append((legacy_id, entry[0], entry[1], entry[2]))
        return result

    async def get_comp_items(self, request: web.Request) -> web.Response:
        """Return known devices with live state from registry."""
        items: list[dict[str, Any]] = []

        for comp_id, dtype, module_ip, ch in self._all_items():
            if dtype == DeviceType.RELAY:
                key = DeviceKey(dtype, module_ip, ch)
                rs = self.registry.get_relay_state(key)
                items.append({
                    "id": comp_id,
                    "type": "relay",
                    "channel": ch,
                    "module": module_ip,
                    "state": rs.state if rs else "unknown",
                })
            elif dtype == DeviceType.DIMMER:
                key = DeviceKey(dtype, module_ip, ch)
                ds = self.registry.get_dimmer_state(key)
                items.append({
                    "id": comp_id,
                    "type": "dimmer",
                    "channel": ch,
                    "module": module_ip,
                    "level_percent": ds.level_percent if ds else None,
                })

        return web.json_response(items)

    async def action_action(self, request: web.Request) -> web.Response:
        try:
            comp_id = int(request.query.get("id", ""))
        except ValueError:
            raise web.HTTPBadRequest(text="missing or invalid id")

        entry = self._lookup_legacy_id(comp_id)
        if entry is None:
            raise web.HTTPNotFound(text=f"unknown component id {comp_id}")

        dtype, module_ip, ch = entry

        action_type = request.query.get("actionType", "ON").upper()
        value_s = request.query.get("value", "1")
        try:
            value = int(value_s)
        except ValueError:
            value = 1

        sent_ts = time.monotonic()
        payload: bytes | None = None

        if dtype == DeviceType.RELAY:
            if action_type == "ON" and value > 0:
                cmd = RelayCommand(channel=ch, action=RelayAction.ON)
            elif action_type == "OFF" or value == 0:
                cmd = RelayCommand(channel=ch, action=RelayAction.OFF)
            else:
                cmd = RelayCommand(channel=ch, action=RelayAction.ON)
            payload = encode_relay_command(cmd)
        elif dtype == DeviceType.DIMMER:
            if action_type == "DIM":
                if not 0 <= value <= 100:
                    raise web.HTTPBadRequest(text="value must be 0-100 for DIM")
                payload = encode_dim_command(DimmerCommand(channel=ch, level=value))
            elif value == 0:
                payload = encode_dim_off(ch)
            else:
                payload = encode_dim_command(DimmerCommand(channel=ch, level=100))
        else:
            raise web.HTTPNotFound(text=f"component id {comp_id} is not a relay or dimmer")

        await self.bus.send_command(module_ip, payload)
        reply_pkt = await self.bus.correlate_reply(
            module_ip=module_ip,
            after_ts=sent_ts,
            timeout_ms=self.config.reply_timeout_ms,
        )
        reply_parsed = None
        if reply_pkt:
            if dtype == DeviceType.RELAY:
                reply_parsed = decode_relay_payload(reply_pkt.data)
            elif dtype == DeviceType.DIMMER:
                reply_parsed = decode_dimmer_payload(reply_pkt.data)

        return web.json_response(
            {
                "ok": True,
                "id": comp_id,
                "sent_hex": payload.hex() if payload else "",
                "reply": reply_parsed,
            }
        )


def create_app(
    bus: UDPBus | None = None,
    registry: DeviceRegistry | None = None,
    config: GatewayConfig | None = None,
) -> web.Application:
    cfg = config or GatewayConfig.from_env()
    udp = bus or UDPBus(cfg)
    reg = registry or DeviceRegistry()
    return RESTShim(udp, reg, cfg).app