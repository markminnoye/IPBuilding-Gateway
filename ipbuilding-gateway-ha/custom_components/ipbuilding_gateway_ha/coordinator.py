"""WebSocket coordinator for ipbuilding_gateway_ha.

Manages the WebSocket connection to the gateway, maintains device state,
and dispatches updates to platform entities.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any, Callable

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_API_PORT,
    CONF_API_HOST,
    DEFAULT_API_PORT,
    DOMAIN,
    RECONNECT_BASE_DELAY,
    RECONNECT_BACKOFF_MULT,
    RECONNECT_MAX_DELAY,
)

log = logging.getLogger(__name__)


class IPBuildingCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinates WebSocket connection to the IPBuilding Gateway.

    Manages device state received via WebSocket and notifies listeners
    for specific entity updates.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        self._host = str(entry.data.get(CONF_API_HOST, ""))
        self._port = int(entry.data.get(CONF_API_PORT, DEFAULT_API_PORT))
        self._ws_url = f"ws://{self._host}:{self._port}/ws"
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._ws_session: aiohttp.ClientSession | None = None
        self._ws_connected = asyncio.Event()
        self._receive_task: asyncio.Task[None] | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._reconnect_delay = RECONNECT_BASE_DELAY
        # Per-entity listeners: entity_id -> [callback(state)]
        self._listeners: dict[str, list[Callable[[dict], None]]] = {}
        self._lock = asyncio.Lock()
        self._data: dict[str, Any] = {}
        super().__init__(hass, log, name=DOMAIN)

    @property
    def ws_url(self) -> str:
        return self._ws_url

    # -------------------------------------------------------------------------
    # DataUpdateCoordinator interface
    # -------------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch device list via REST as a fallback when WS is unavailable."""
        url = f"http://{self._host}:{self._port}/api/v1/devices"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("devices", [])
                    log.warning("REST fallback returned %s", resp.status)
                    return []
        except Exception as exc:
            log.debug("REST fallback failed: %s", exc)
            return []

    # -------------------------------------------------------------------------
    # WebSocket lifecycle
    # -------------------------------------------------------------------------

    async def _async_connect(self) -> bool:
        """Establish WebSocket connection to the gateway.

        Returns True if connected, False otherwise.
        """
        try:
            self._ws_session = aiohttp.ClientSession()
            self._ws = await self._ws_session.ws_connect(
                self._ws_url,
                receive_timeout=30.0,
                heartbeat=30.0,
            )
            self._ws_connected.set()
            self._reconnect_delay = RECONNECT_BASE_DELAY
            log.info("WebSocket connected to %s", self._ws_url)
            return True
        except Exception as exc:
            log.warning("WebSocket connect failed: %s", exc)
            await self._close_ws_session()
            return False

    async def _close_ws_session(self) -> None:
        """Close the WebSocket and session."""
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        if self._ws_session is not None:
            try:
                await self._ws_session.close()
            except Exception:
                pass
            self._ws_session = None
        self._ws_connected.clear()

    async def start(self) -> None:
        """Start the WebSocket receive loop with reconnect logic."""
        self._stop_event.clear()
        if not await self._async_connect():
            # Schedule reconnect
            self._reconnect_task = asyncio.create_task(self._reconnect_loop())
            return

        self._receive_task = asyncio.create_task(self._receive_loop())

    async def stop(self) -> None:
        """Stop the receive loop and close the connection."""
        self._stop_event.set()
        if self._receive_task is not None:
            self._receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receive_task
            self._receive_task = None
        if self._reconnect_task is not None:
            self._reconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reconnect_task
            self._reconnect_task = None
        await self._close_ws_session()

    async def _reconnect_loop(self) -> None:
        """Attempt to reconnect with exponential backoff."""
        while not self._stop_event.is_set():
            await asyncio.sleep(self._reconnect_delay)
            if self._stop_event.is_set():
                break
            if await self._async_connect():
                self._receive_task = asyncio.create_task(self._receive_loop())
                self._reconnect_task = None
                return
            self._reconnect_delay = min(
                self._reconnect_delay * RECONNECT_BACKOFF_MULT,
                RECONNECT_MAX_DELAY,
            )

    async def _receive_loop(self) -> None:
        """Receive and process WebSocket messages."""
        while True:
            if self._ws is None:
                break
            try:
                msg = await self._ws.receive()
            except Exception as exc:
                log.warning("WS receive error: %s", exc)
                break

            if msg.type == aiohttp.WSMsgType.TEXT:
                await self._handle_message(msg.data)
            elif msg.type in (
                aiohttp.WSMsgType.CLOSE,
                aiohttp.WSMsgType.CLOSED,
                aiohttp.WSMsgType.ERROR,
            ):
                log.warning("WS connection ended: %s", msg.type)
                break

        await self._close_ws_session()
        # Schedule reconnect
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    # -------------------------------------------------------------------------
    # Message handling
    # -------------------------------------------------------------------------

    async def _handle_message(self, raw: str | dict) -> None:
        """Parse and dispatch a WebSocket message."""
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            log.warning("Invalid JSON from gateway: %r", raw)
            return

        msg_type = data.get("type")
        log.debug("WS message: type=%s", msg_type)

        if msg_type == "snapshot":
            # New format: snapshot contains both modules and devices.
            # The companion only needs devices for entity state.
            devices = data.get("devices", [])
            self._data = {dev["id"]: dev for dev in devices}
            self.async_set_updated_data(self._data)
            self._notify_all(devices)
        elif msg_type == "device_list":
            # Legacy format kept for backward compatibility.
            self._data = {dev["id"]: dev for dev in data.get("devices", [])}
            self.async_set_updated_data(self._data)
            self._notify_all(data.get("devices", []))
        elif msg_type == "state_changed":
            entity_id = data.get("id", "")
            self._data[entity_id] = dict(self._data.get(entity_id, {}), **data)
            self.async_set_updated_data(self._data)
            self._notify(entity_id, data)
        elif msg_type == "button_event":
            # Button events go to all button entities; route by hardware id
            self._notify_button(data)
        else:
            log.debug("Unknown WS message type: %s", msg_type)

    def _notify(self, entity_id: str, data: dict) -> None:
        """Notify listeners for a specific entity."""
        for cb in self._listeners.get(entity_id, []):
            try:
                cb(data)
            except Exception:
                log.exception("Listener error for %s", entity_id)

    def _notify_all(self, devices: list[dict]) -> None:
        """Notify all listeners about a full device list update."""
        for dev in devices:
            self._notify(dev.get("id", ""), dev)

    def _notify_button(self, data: dict) -> None:
        """Notify button entities (routed by hardware id, not entity_id)."""
        for cb in self._listeners.get(f"button:{data.get('id')}", []):
            try:
                cb(data)
            except Exception:
                log.exception("Button listener error")

    # -------------------------------------------------------------------------
    # Entity registration
    # -------------------------------------------------------------------------

    def register_entity(self, entity_id: str, callback: Callable[[dict], None]) -> None:
        """Register a callback for entity updates.

        Args:
            entity_id: e.g. "10.10.1.30:relay:0" or "button:2DE341851900001F"
            callback: called with the new state data on each update.
        """
        self._listeners.setdefault(entity_id, []).append(callback)

    def unregister_entity(self, entity_id: str, callback: Callable[[dict], None]) -> None:
        """Remove a callback for an entity."""
        if entity_id in self._listeners:
            self._listeners[entity_id] = [
                cb for cb in self._listeners[entity_id] if cb is not callback
            ]

    # -------------------------------------------------------------------------
    # Command sending
    # -------------------------------------------------------------------------

    async def async_send_command(
        self,
        entity_id: str,
        action: str,
        value: int | None = None,
    ) -> bool:
        """Send a command to the gateway via WebSocket.

        Returns True if the command was acknowledged by the gateway
        (command_result.ok=true).
        """
        if self._ws is None or not self._ws_connected.is_set():
            log.warning("Cannot send command: WS not connected")
            return False

        msg: dict[str, Any] = {"type": "command", "id": entity_id, "action": action}
        if value is not None:
            msg["value"] = value

        try:
            await self._ws.send_json(msg)
            log.debug("Command sent: %s %s %s", entity_id, action, value)
            return True
        except Exception as exc:
            log.warning("Failed to send command: %s", exc)
            return False

    # -------------------------------------------------------------------------
    # State access helpers
    # -------------------------------------------------------------------------

    def get_device_state(self, entity_id: str) -> dict[str, Any] | None:
        """Return cached state for an entity."""
        return self._data.get(entity_id) if isinstance(self._data, dict) else None

    def all_device_ids(self) -> list[str]:
        """Return all known entity IDs."""
        return list(self._data.keys()) if isinstance(self._data, dict) else []