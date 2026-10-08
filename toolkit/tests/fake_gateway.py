"""Local stand-in for the gateway REST and WebSocket API."""

from __future__ import annotations

import json
import socket
from typing import Any

from aiohttp import web


class FakeGateway:
    def __init__(
        self,
        *,
        remote_debugging: bool = False,
        capabilities: list[str] | None = None,
        drop_first: bool = False,
    ) -> None:
        self.remote_debugging = remote_debugging
        self.capabilities = list(capabilities or [])
        self.drop_first = drop_first
        self.version = "0.0.0-test"
        self.hub_role = "slave"
        self.modules: list[dict[str, Any]] = [
            {
                "id": "module-a",
                "type": "relay",
                "model": "IP0200PoE",
                "firmware": "1",
                "name": "relay",
            }
        ]
        self.devices: list[dict[str, Any]] = [
            {"id": "channel-a", "device_type": "relay", "name": "lamp"}
        ]
        self.devices_after_reconnect: list[dict[str, Any]] = [
            {"id": "channel-b", "device_type": "dimmer", "name": "other"}
        ]
        self.received: list[dict[str, Any]] = []
        self.raw_calls: list[dict[str, Any]] = []
        self.raw_status = 200
        self.raw_body: dict[str, Any] | None = None
        self.replies: list[dict[str, Any]] = [
            {"hex": "5330303030", "from": "module", "port": 1001}
        ]
        self.frame_on_subscribe: dict[str, Any] | None = None
        self.log_level_reply: dict[str, Any] | None = None
        self.log_lines: list[dict[str, Any]] = []
        self.omit_toolkit_fields = False
        self.discover_calls: list[dict[str, Any]] = []
        self.command_calls: list[dict[str, Any]] = []
        self.command_status = 200
        self.command_body: dict[str, Any] = {"ok": True, "schema_version": 2}
        self.connects = 0
        self.port = 0
        self._sockets: list[web.WebSocketResponse] = []
        self._runner: web.AppRunner | None = None

    def status_body(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "status": "ok",
            "version": self.version,
            "uptime_seconds": 12,
            "subsystems": {
                "installation": "ok",
                "module_metadata": "ok",
                "discovery": "ok",
            },
            "issues": [],
            "hub_role": self.hub_role,
            "input_mode_label": "Slave",
        }
        if not self.omit_toolkit_fields:
            if not getattr(self, "omit_remote_debugging", False):
                body["remote_debugging"] = self.remote_debugging
            body["capabilities"] = list(self.capabilities)
        return body

    def snapshot_for(self, connect_index: int) -> dict[str, Any]:
        devices = self.devices if connect_index == 1 else self.devices_after_reconnect
        return {
            "type": "snapshot",
            "modules": self.modules,
            "devices": devices,
            "gateway_status": self.status_body(),
        }

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/api/v1/status", self._status)
        app.router.add_get("/api/v1/modules", self._modules)
        app.router.add_get("/api/v1/devices", self._devices)
        app.router.add_post("/api/v1/discover", self._discover)
        app.router.add_post("/api/v1/devices/{device_id}/command", self._command)
        app.router.add_post("/api/v1/debug/raw-send", self._raw)
        app.router.add_get("/ws", self._ws)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        self.port = sock.getsockname()[1]
        await web.SockSite(self._runner, sock).start()

    async def stop(self) -> None:
        for ws in list(self._sockets):
            await ws.close()
        if self._runner is not None:
            await self._runner.cleanup()

    async def push(self, payload: dict[str, Any]) -> None:
        for ws in list(self._sockets):
            if not ws.closed:
                await ws.send_json(payload)

    async def _status(self, _request: web.Request) -> web.Response:
        return web.json_response(self.status_body())

    async def _modules(self, _request: web.Request) -> web.Response:
        return web.json_response({"modules": self.modules})

    async def _devices(self, _request: web.Request) -> web.Response:
        return web.json_response({"devices": self.devices})

    async def _discover(self, request: web.Request) -> web.Response:
        body = await request.json()
        self.discover_calls.append(body if isinstance(body, dict) else {})
        self.modules.append(
            {
                "id": "module-b",
                "type": "dimmer",
                "model": "IP0300PoE",
                "firmware": "1",
                "name": "dimmer-b",
            }
        )
        self.devices.append(
            {
                "id": "device-b",
                "module_id": "module-b",
                "channel": 0,
                "device_type": "dimmer",
                "name": "lamp-b",
                "state": "off",
            }
        )
        return web.json_response(
            {
                "ok": True,
                "added": [{"mac": "module-b"}],
                "changed": [],
                "firmware_changed": [],
                "removed": [],
                "skipped_unidentified": [],
                "duration_ms": 1,
                "schema_version": 2,
            }
        )

    async def _command(self, request: web.Request) -> web.Response:
        body = await request.json()
        self.command_calls.append(
            {"device_id": request.match_info["device_id"], **body}
        )
        if self.command_status >= 400:
            return web.json_response(self.command_body, status=self.command_status)
        return web.json_response(self.command_body)

    async def _raw(self, request: web.Request) -> web.Response:
        body = await request.json()
        self.raw_calls.append(body)
        if self.raw_status >= 400:
            return web.json_response(self.raw_body or {"error": "rejected"}, status=self.raw_status)
        return web.json_response(
            {"ok": True, "sent_hex": body.get("payload_hex"), "replies": self.replies}
        )

    async def _ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.connects += 1
        index = self.connects
        await ws.send_json(self.snapshot_for(index))
        if self.drop_first and index == 1:
            await ws.close()
            return ws
        self._sockets.append(ws)
        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    self.received.append(data)
                    reply = None
                    if data.get("type") == "subscribe_udp_frames":
                        reply = self.frame_on_subscribe
                    elif data.get("type") == "subscribe_logs":
                        if not self.remote_debugging:
                            await ws.send_json(
                                {
                                    "type": "error",
                                    "error": "remote_debugging_disabled",
                                    "message": "uit",
                                }
                            )
                        else:
                            await ws.send_json(
                                {
                                    "type": "logs_subscribed",
                                    "min_level": data.get("min_level") or "info",
                                    "buffered": len(self.log_lines),
                                }
                            )
                            for line in self.log_lines:
                                await ws.send_json(line)
                        reply = None
                    elif data.get("type") == "set_log_level":
                        reply = self.log_level_reply
                    if reply is not None:
                        await ws.send_json(reply)
                elif msg.type in (web.WSMsgType.ERROR, web.WSMsgType.CLOSE):
                    break
        finally:
            if ws in self._sockets:
                self._sockets.remove(ws)
        return ws
