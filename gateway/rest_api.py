"""EXPERIMENTAL — IPBox-shaped REST on :30200 for RE/capture correlation only.

Not a product API. The open central service targets UDP/1001 + a TBD northbound
(MQTT/Matter/…). See docs/superpowers/specs/2026-05-18-gateway-architecture-design.md.
"""

from __future__ import annotations

import time
from typing import Any

from aiohttp import web

from gateway.config import GatewayConfig
from gateway.models import DimmerCommand, RelayAction, RelayCommand
from gateway.payloads.dimmer import decode_dimmer_payload, encode_dim_command, encode_dim_off
from gateway.payloads.relay import decode_relay_payload, encode_relay_command
from gateway.udp_bus import UDPBus

# Minimal inventory stub — replace with config/DB when provisioning RE lands
_DEFAULT_ITEMS: list[dict[str, Any]] = [
    {"id": 547, "type": "relay", "channel": 0, "module": "10.10.1.30"},
    {"id": 557, "type": "relay", "channel": 10, "module": "10.10.1.30"},
    {"id": 563, "type": "relay", "channel": 16, "module": "10.10.1.30"},
    {"id": 571, "type": "dimmer", "channel": 0, "module": "10.10.1.40"},
    {"id": 572, "type": "dimmer", "channel": 1, "module": "10.10.1.40"},
]

_RELAY_ID_CHANNEL: dict[int, int] = {547: 0, 557: 10, 563: 16, 570: 23}
_DIMMER_ID_CHANNEL: dict[int, int] = {571: 0, 572: 1, 573: 2}


class RESTApp:
    def __init__(self, bus: UDPBus, config: GatewayConfig | None = None) -> None:
        self.bus = bus
        self.config = config or GatewayConfig.from_env()
        self.app = web.Application()
        self.app.router.add_get("/api/v1/comp/items", self.get_comp_items)
        self.app.router.add_get("/api/v1/action/action", self.action_action)

    async def get_comp_items(self, request: web.Request) -> web.Response:
        return web.json_response(_DEFAULT_ITEMS)

    async def action_action(self, request: web.Request) -> web.Response:
        try:
            comp_id = int(request.query.get("id", ""))
        except ValueError:
            raise web.HTTPBadRequest(text="missing or invalid id")

        action_type = request.query.get("actionType", "ON").upper()
        value_s = request.query.get("value", "1")
        try:
            value = int(value_s)
        except ValueError:
            value = 1

        sent_ts = time.monotonic()
        module_ip: str | None = None
        payload: bytes | None = None

        if comp_id in _RELAY_ID_CHANNEL:
            ch = _RELAY_ID_CHANNEL[comp_id]
            if action_type == "ON" or (action_type == "ON" and value == 1):
                cmd = RelayCommand(channel=ch, action=RelayAction.ON)
            elif value == 0:
                cmd = RelayCommand(channel=ch, action=RelayAction.OFF)
            else:
                cmd = RelayCommand(channel=ch, action=RelayAction.ON)
            payload = encode_relay_command(cmd)
            module_ip = self.config.field_modules["relay"]
        elif comp_id in _DIMMER_ID_CHANNEL:
            ch = _DIMMER_ID_CHANNEL[comp_id]
            if action_type == "DIM":
                if not 0 <= value <= 100:
                    raise web.HTTPBadRequest(text="value must be 0-100 for DIM")
                payload = encode_dim_command(DimmerCommand(channel=ch, level=value))
            elif value == 0:
                payload = encode_dim_off(ch)
            else:
                payload = encode_dim_command(DimmerCommand(channel=ch, level=100))
            module_ip = self.config.field_modules["dimmer"]
        else:
            raise web.HTTPNotFound(text=f"unknown component id {comp_id}")

        await self.bus.send_command(module_ip, payload)
        reply_pkt = await self.bus.correlate_reply(
            module_ip=module_ip,
            after_ts=sent_ts,
            timeout_ms=self.config.reply_timeout_ms,
        )
        reply_parsed = None
        if reply_pkt:
            if comp_id in _RELAY_ID_CHANNEL:
                reply_parsed = decode_relay_payload(reply_pkt.data)
            else:
                reply_parsed = decode_dimmer_payload(reply_pkt.data)

        return web.json_response(
            {
                "ok": True,
                "id": comp_id,
                "sent_hex": payload.hex(),
                "reply": reply_parsed,
            }
        )


def create_app(bus: UDPBus | None = None, config: GatewayConfig | None = None) -> web.Application:
    cfg = config or GatewayConfig.from_env()
    udp = bus or UDPBus(cfg)
    return RESTApp(udp, cfg).app
