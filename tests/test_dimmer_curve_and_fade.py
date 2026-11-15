"""Tests for per-channel dim_gamma curve and per-channel default_fade."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp.test_utils import make_mocked_request

from gateway.config import GatewayConfig
from gateway.device_config import DeviceConfigError, validate_channel_fields
from gateway.device_registry import DeviceKey, DeviceRegistry, DimmerState
from gateway.gateway_api import GatewayAPI
from gateway.installation import (
    DEFAULT_DIM_GAMMA,
    DEFAULT_DIMMER_FADE,
    ChannelConfig,
    InstallationConfig,
)
from gateway.payloads.dimmer import apply_dim_gamma, invert_dim_gamma
from gateway.types import DeviceType


def _write_devices_file(tmp_path: Path, modules: list[dict]) -> Path:
    path = tmp_path / "devices.json"
    path.write_text(json.dumps({"modules": modules}), encoding="utf-8")
    return path


def _make_api_with_file(tmp_path: Path, modules: list[dict]) -> GatewayAPI:
    devices_file = _write_devices_file(tmp_path, modules)
    inst = InstallationConfig.load(devices_file)
    cfg = GatewayConfig(
        devices_file=str(devices_file),
        installation=inst,
        field_modules={m["ip"]: m["type"] for m in modules},
    )
    registry = DeviceRegistry()
    bus = MagicMock()
    bus.last_send_ts = 0.0
    return GatewayAPI(bus, registry, cfg)


class TestDimGammaMath:
    def test_identity_gamma_one(self) -> None:
        for v in (0, 1, 25, 50, 75, 100):
            assert apply_dim_gamma(v, 1.0) == v
            assert invert_dim_gamma(v, 1.0) == v

    def test_endpoints_preserved(self) -> None:
        for g in (1.0, 2.2, 2.8):
            assert apply_dim_gamma(0, g) == 0
            assert apply_dim_gamma(100, g) == 100
            assert invert_dim_gamma(0, g) == 0
            assert invert_dim_gamma(100, g) == 100

    def test_positive_ui_never_maps_to_zero(self) -> None:
        assert apply_dim_gamma(1, 3.0) == 1
        assert invert_dim_gamma(1, 1.0) == 1
        assert invert_dim_gamma(1, 3.0) == 22

    def test_gamma_2_2_midpoint_and_roundtrip(self) -> None:
        bus = apply_dim_gamma(50, 2.2)
        assert bus == 22
        assert invert_dim_gamma(bus, 2.2) == 50


class TestSchemaAndValidation:
    def test_channel_defaults_and_serialization(self) -> None:
        ch = ChannelConfig(ch=0, name="Living")
        assert ch.effective_default_fade == DEFAULT_DIMMER_FADE == 30
        assert ch.effective_dim_gamma == DEFAULT_DIM_GAMMA == 1.0
        raw = ch.to_dict()
        assert "default_fade" not in raw
        assert "dim_gamma" not in raw

        ch.default_fade = 15
        ch.dim_gamma = 2.2
        raw2 = ch.to_dict()
        assert raw2["default_fade"] == 15
        assert raw2["dim_gamma"] == 2.2

        reloaded = ChannelConfig.from_dict(raw2)
        assert reloaded.default_fade == 15
        assert reloaded.dim_gamma == 2.2

    def test_validate_channel_dim_gamma(self) -> None:
        assert validate_channel_fields({"dim_gamma": 2.256}, DeviceType.DIMMER) == {
            "dim_gamma": 2.26
        }
        assert validate_channel_fields({"dim_gamma": None}, DeviceType.DIMMER) == {
            "dim_gamma": None
        }
        with pytest.raises(DeviceConfigError):
            validate_channel_fields({"dim_gamma": 2.2}, DeviceType.RELAY)
        for bad in (0.9, 3.6, 5.0, True, "2.2", float("nan")):
            with pytest.raises(DeviceConfigError):
                validate_channel_fields({"dim_gamma": bad}, DeviceType.DIMMER)

    def test_validate_channel_default_fade(self) -> None:
        assert validate_channel_fields({"default_fade": 0}, DeviceType.DIMMER) == {
            "default_fade": 0
        }
        assert validate_channel_fields({"default_fade": 255}, DeviceType.DIMMER) == {
            "default_fade": 255
        }
        assert validate_channel_fields({"default_fade": None}, DeviceType.DIMMER) == {
            "default_fade": None
        }
        with pytest.raises(DeviceConfigError):
            validate_channel_fields({"default_fade": 30}, DeviceType.RELAY)
        for bad in (-1, 256, True, "30", 1.5):
            with pytest.raises(DeviceConfigError):
                validate_channel_fields({"default_fade": bad}, DeviceType.DIMMER)


class TestGatewayDimmerCurveAndFade:
    @pytest.mark.asyncio
    async def test_command_and_state_apply_gamma_and_default_fade(
        self, tmp_path: Path
    ) -> None:
        api = _make_api_with_file(
            tmp_path,
            [
                {
                    "ip": "10.10.1.40",
                    "type": "dimmer",
                    "mac": "00:24:77:52:9e:a8",
                    "channels": [
                        {
                            "ch": 0,
                            "name": "Living",
                            "active": True,
                            "max_watt": 100,
                            "dim_gamma": 2.2,
                            "default_fade": 45,
                        }
                    ],
                }
            ],
        )
        reply_future: asyncio.Future = asyncio.Future()
        reply_future.set_result(None)
        api._bus.correlate_reply = MagicMock(return_value=reply_future)
        send_future: asyncio.Future = asyncio.Future()
        send_future.set_result(None)
        api._bus.send_command.return_value = send_future

        # UI 50% with gamma=2.2 -> bus 22%, channel default_fade=45 -> S0221045
        ok, error = await api._execute_command("10.10.1.40-0", "DIM", 50)
        assert ok is True
        assert error is None
        api._bus.send_command.assert_called_with(
            "10.10.1.40", b"S0221045", expect_reply=True
        )

        # Bus reports 22% -> snapshot and state_changed invert back to UI 50%
        key = DeviceKey(DeviceType.DIMMER, "10.10.1.40", 0)
        api._registry.seed_dimmer_state(key, 22)
        devices = api._build_device_list()
        assert devices[0]["level"] == 50
        assert devices[0]["dim_gamma"] == 2.2
        assert devices[0]["default_fade"] == 45
        msg = api._build_state_changed(key, DimmerState(level_percent=22))
        assert msg is not None
        assert msg["level"] == 50

    @pytest.mark.asyncio
    async def test_patch_device_dim_gamma_and_default_fade(
        self, tmp_path: Path
    ) -> None:
        api = _make_api_with_file(
            tmp_path,
            [
                {
                    "ip": "10.10.1.40",
                    "type": "dimmer",
                    "mac": "00:24:77:52:9e:a8",
                    "channels": [{"ch": 0, "name": "Living", "active": True}],
                }
            ],
        )

        req = make_mocked_request("PATCH", "/", match_info={"device_id": "10.10.1.40-0"})
        req.json = AsyncMock(return_value={"dim_gamma": 2.4, "default_fade": 12})
        resp_dev = await api._patch_device(req)
        assert resp_dev.status == 200
        dev_body = json.loads(resp_dev.text)
        assert dev_body["dim_gamma"] == 2.4
        assert dev_body["default_fade"] == 12

        resp_ui = await api._get_webui(make_mocked_request("GET", "/"))
        assert resp_ui.status == 200
        assert "Gamma" in resp_ui.text
        assert "Uitgang" in resp_ui.text
        assert "1.0 = lineair (uit)" in resp_ui.text
        assert "2.2 = natuurlijk / aanbevolen" in resp_ui.text
        assert "2.8 = extra fijn onderin" in resp_ui.text
        assert "Default transition fade (0–255, ~0,1 s per eenheid):" in resp_ui.text
