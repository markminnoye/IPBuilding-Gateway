"""Tests for the gateway button timing state machine (plan §3.2).

The gateway classifies raw press/release edges into press/long_press/release
events by arming a per-button asyncio timer at press time. These tests
cover the state transitions and threshold handling without touching any
real fieldbus.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway import gateway_api
from gateway.device_registry import DeviceKey, DeviceRegistry, DeviceType, ButtonEvent
from gateway.installation import (
    ButtonConfig,
    DEFAULT_BUTTON_HOLD_THRESHOLD_S,
    InstallationConfig,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_installation(buttons: list[dict[str, Any]] | None = None) -> InstallationConfig:
    raw: dict[str, Any] = {
        "modules": [
            {
                "name": "IP1100PoE",
                "ip": "10.10.1.50",
                "type": "input",
                "mac": "00:24:77:52:ad:aa",
                "channels": [],
            }
        ]
    }
    if buttons:
        raw["buttons"] = buttons
    return InstallationConfig._parse(raw)


def _make_api(installation: InstallationConfig) -> gateway_api.GatewayAPI:
    bus = MagicMock()
    reg = DeviceRegistry()
    for mc in installation.modules:
        reg.register_module(mc.ip, mc.type)
    cfg = MagicMock()
    cfg.installation = installation
    cfg.api_host = "127.0.0.1"
    cfg.api_port = 8080
    return gateway_api.GatewayAPI(bus, reg, cfg)


def _input_key() -> DeviceKey:
    return DeviceKey(DeviceType.INPUT, "10.10.1.50", 0)


async def _drain_broadcasts(api: gateway_api.GatewayAPI) -> list[dict[str, Any]]:
    """Let any scheduled _broadcast coroutines finish; return the messages."""
    # The gateway uses ``asyncio.create_task(self._broadcast(msg))`` so the
    # coroutines run on the current event loop. We give them a chance to
    # finish by awaiting one tick.
    await asyncio.sleep(0)
    # Gather any completed tasks. We don't have a registry of broadcast
    # tasks, but the broadcast itself just iterates over an internal
    # ``_ws_clients`` set. Tests mock bus to no-op so we only need to
    # ensure tasks have a chance to be scheduled.
    await asyncio.sleep(0)
    return []


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestButtonThreshold:
    def test_default_threshold_when_no_button(self) -> None:
        inst = _make_installation()
        assert inst.button_threshold("2f8185190000df") == DEFAULT_BUTTON_HOLD_THRESHOLD_S

    def test_explicit_threshold_from_config(self) -> None:
        inst = _make_installation([
            {"id": "2f8185190000df", "module_id": "00:24:77:52:ad:aa",
             "name": "Keuken knop", "hold_threshold_s": 2.0}
        ])
        assert inst.button_threshold("2f8185190000df") == 2.0

    def test_threshold_lookup_is_case_insensitive(self) -> None:
        inst = _make_installation([
            {"id": "2F8185190000DF", "hold_threshold_s": 1.0}
        ])
        assert inst.button_threshold("2f8185190000df") == 1.0


class TestButtonStateMachine:
    """Drive the gateway's _on_button_event and inspect the broadcast bus.

    The gateway's broadcast is via ``asyncio.create_task``; we patch the
    helper to capture messages synchronously so we can assert on the
    sequence without spinning an event loop.
    """

    def _make_capturing_api(self, installation: InstallationConfig) -> gateway_api.GatewayAPI:
        api = _make_api(installation)
        api._captured: list[dict[str, Any]] = []

        def _capture(self_api, id_hex: str, action: str) -> None:
            api._captured.append({"id": id_hex, "action": action})

        # Replace _broadcast_button with a synchronous capture.
        api._broadcast_button = _capture.__get__(api, type(api))  # type: ignore[assignment]
        return api

    def _press(self, api: gateway_api.GatewayAPI, id_hex: str) -> None:
        evt = ButtonEvent(action="press", id_hex=id_hex)
        api._on_button_event(_input_key(), evt)

    def _release(self, api: gateway_api.GatewayAPI, id_hex: str) -> None:
        evt = ButtonEvent(action="release", id_hex=id_hex)
        api._on_button_event(_input_key(), evt)

    def _run_long_press_timer(self, api: gateway_api.GatewayAPI, id_hex: str) -> None:
        """Manually fire the long_press callback (bypasses the loop timer)."""
        api._fire_long_press(id_hex)

    @pytest.mark.asyncio
    async def test_short_press_emits_press_then_release(self) -> None:
        inst = _make_installation([
            {"id": "2f8185190000df", "hold_threshold_s": 0.5}
        ])
        api = self._make_capturing_api(inst)

        self._press(api, "2f8185190000df")
        # Manually fire the long_press callback before release — that's
        # exactly what the asyncio timer would do if held past threshold.
        self._run_long_press_timer(api, "2f8185190000df")
        self._release(api, "2f8185190000df")

        actions = [m["action"] for m in api._captured]
        assert actions == ["press", "long_press", "release"]
        assert all(m["id"] == "2f8185190000df" for m in api._captured)

    @pytest.mark.asyncio
    async def test_short_press_no_long_press(self) -> None:
        inst = _make_installation([
            {"id": "2f8185190000df", "hold_threshold_s": 0.5}
        ])
        api = self._make_capturing_api(inst)

        self._press(api, "2f8185190000df")
        self._release(api, "2f8185190000df")

        actions = [m["action"] for m in api._captured]
        assert actions == ["press", "release"]

    @pytest.mark.asyncio
    async def test_double_press_resets_state(self) -> None:
        inst = _make_installation([
            {"id": "2f8185190000df", "hold_threshold_s": 0.5}
        ])
        api = self._make_capturing_api(inst)

        # Press -> long_press fired -> press again before release
        self._press(api, "2f8185190000df")
        self._run_long_press_timer(api, "2f8185190000df")
        # A second press without an intervening release should reset
        # press_started_at and long_press_fired, so a subsequent manual
        # timer fire emits a second long_press frame. That's the current
        # gateway behaviour — dedup is a companion concern.
        self._press(api, "2f8185190000df")
        self._run_long_press_timer(api, "2f8185190000df")
        self._release(api, "2f8185190000df")
        actions = [m["action"] for m in api._captured]
        assert actions == ["press", "long_press", "press", "long_press", "release"]

    @pytest.mark.asyncio
    async def test_long_press_after_release_is_noop(self) -> None:
        inst = _make_installation([
            {"id": "2f8185190000df", "hold_threshold_s": 0.1}
        ])
        api = self._make_capturing_api(inst)

        self._press(api, "2f8185190000df")
        self._release(api, "2f8185190000df")
        # Fire long_press callback after release — should be a no-op.
        self._run_long_press_timer(api, "2f8185190000df")

        actions = [m["action"] for m in api._captured]
        # No long_press frame in the captured output.
        assert "long_press" not in actions
        assert actions == ["press", "release"]

    def test_unknown_action_is_ignored(self) -> None:
        inst = _make_installation()
        api = self._make_capturing_api(inst)
        # ``_on_button_event`` is synchronous (no await inside), so we
        # can call it without an event loop.
        api._on_button_event(_input_key(), ButtonEvent(action="unknown", id_hex="x"))
        assert api._captured == []

    @pytest.mark.asyncio
    async def test_case_insensitive_id_matching(self) -> None:
        inst = _make_installation([
            {"id": "2F8185190000DF", "hold_threshold_s": 0.1}
        ])
        api = self._make_capturing_api(inst)
        self._press(api, "2f8185190000df")  # lowercase
        # The id_hex should be normalised to lowercase in the broadcast.
        assert api._captured[-1]["id"] == "2f8185190000df"


class TestSchemaVersion:
    def test_snapshot_includes_schema_version_2(self) -> None:
        inst = _make_installation()
        api = _make_api(inst)
        snap = api._build_snapshot()
        assert snap["schema_version"] == 2
        assert snap["type"] == "snapshot"
        assert "modules" in snap
        assert "devices" in snap
