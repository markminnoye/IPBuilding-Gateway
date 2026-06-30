"""Tests for gateway.config — env-default gating and devices.json load paths."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gateway.config import GatewayConfig


def test_from_env_uses_installation_when_devices_json_valid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    devices_file = tmp_path / "devices.json"
    devices_file.write_text(
        json.dumps({
            "modules": [{
                "ip": "10.10.1.99",
                "type": "relay",
                "channels": [],
            }],
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("GATEWAY_DEVICES_FILE", str(devices_file))
    monkeypatch.delenv("GATEWAY_SIMULATED", raising=False)
    monkeypatch.delenv("GATEWAY_USE_ENV_DEFAULTS", raising=False)

    cfg = GatewayConfig.from_env()

    assert cfg.installation is not None
    assert cfg.field_modules == {"relay": "10.10.1.99"}
    assert cfg.installation_load_error is None


def test_from_env_no_udp_fallback_when_devices_json_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    devices_file = tmp_path / "devices.json"
    monkeypatch.setenv("GATEWAY_DEVICES_FILE", str(devices_file))
    monkeypatch.delenv("GATEWAY_SIMULATED", raising=False)
    monkeypatch.delenv("GATEWAY_USE_ENV_DEFAULTS", raising=False)

    cfg = GatewayConfig.from_env()

    assert cfg.installation is None
    assert cfg.field_modules == {}
    assert cfg.installation_load_error is None


def test_from_env_no_udp_fallback_when_devices_json_invalid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    devices_file = tmp_path / "devices.json"
    devices_file.write_text(
        json.dumps({
            "modules": [{
                "ip": "10.10.1.55",
                "type": "unknown",
                "channels": [],
            }],
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("GATEWAY_DEVICES_FILE", str(devices_file))
    monkeypatch.delenv("GATEWAY_SIMULATED", raising=False)
    monkeypatch.delenv("GATEWAY_USE_ENV_DEFAULTS", raising=False)

    cfg = GatewayConfig.from_env()

    assert cfg.installation is None
    assert cfg.field_modules == {}
    assert cfg.installation_load_error is not None
    assert "unknown" in cfg.installation_load_error.lower()


def test_from_env_use_env_defaults_opt_in(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    devices_file = tmp_path / "devices.json"
    monkeypatch.setenv("GATEWAY_DEVICES_FILE", str(devices_file))
    monkeypatch.setenv("GATEWAY_USE_ENV_DEFAULTS", "1")
    monkeypatch.delenv("GATEWAY_SIMULATED", raising=False)

    cfg = GatewayConfig.from_env()

    assert cfg.use_env_defaults is True
    assert cfg.field_modules == {
        "relay": "10.10.1.30",
        "dimmer": "10.10.1.40",
        "input": "10.10.1.50",
    }


def test_from_env_simulated_mode_enables_env_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    devices_file = tmp_path / "devices.json"
    monkeypatch.setenv("GATEWAY_DEVICES_FILE", str(devices_file))
    monkeypatch.setenv("GATEWAY_SIMULATED", "1")
    monkeypatch.delenv("GATEWAY_USE_ENV_DEFAULTS", raising=False)

    cfg = GatewayConfig.from_env()

    assert cfg.simulated_mode is True
    assert cfg.field_modules["relay"] == "10.10.1.30"


def test_post_init_fills_field_modules_for_simulated_constructor() -> None:
    cfg = GatewayConfig(simulated_mode=True)

    assert cfg.field_modules == {
        "relay": "10.10.1.30",
        "dimmer": "10.10.1.40",
        "input": "10.10.1.50",
    }
