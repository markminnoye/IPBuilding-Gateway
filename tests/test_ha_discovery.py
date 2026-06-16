"""Tests for gateway.ha_discovery — Home Assistant discovery advertiser.

The advertiser runs two parallel channels (Zeroconf + HassIO Supervisor).
These tests cover the unit-level building blocks and lifecycle transitions
without binding real sockets or making real HTTP calls.
"""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gateway.ha_discovery import (
    DISCOVERY_SCHEMA_VERSION,
    SERVICE_TYPE,
    HaDiscoveryAdvertiser,
    HaDiscoveryConfig,
    _build_txt_properties,
    _load_or_create_instance_id,
    _pick_publish_ip,
    _running_as_hass_addon,
)
from gateway import __version__


# ---------------------------------------------------------------------------
# Service type + version
# ---------------------------------------------------------------------------


def test_service_type_constant():
    # The label after the leading underscore must be ≤ 15 bytes
    # (RFC 6763 §7.2 + zeroconf's strict validator).
    assert SERVICE_TYPE == "_ipbgw._tcp.local."
    label = SERVICE_TYPE[1:].split(".")[0]
    assert len(label.encode("utf-8")) <= 15, (
        f"service type label {label!r} is {len(label)} bytes; "
        "RFC 6763 §7.2 limits it to 15"
    )


def test_discovery_schema_version_positive():
    assert DISCOVERY_SCHEMA_VERSION >= 1


# ---------------------------------------------------------------------------
# HaDiscoveryConfig
# ---------------------------------------------------------------------------


def test_config_from_env_defaults(monkeypatch):
    monkeypatch.delenv("GATEWAY_HA_DISCOVERY_ENABLED", raising=False)
    monkeypatch.delenv("GATEWAY_HA_DISCOVERY_ZEROCONF", raising=False)
    monkeypatch.delenv("GATEWAY_HA_DISCOVERY_HASSIO", raising=False)
    monkeypatch.delenv("GATEWAY_DATA_DIR", raising=False)
    monkeypatch.delenv("GATEWAY_API_HOST", raising=False)
    monkeypatch.delenv("GATEWAY_API_PORT", raising=False)
    cfg = HaDiscoveryConfig.from_env()
    assert cfg.enabled is True
    assert cfg.zeroconf_enabled is True
    assert cfg.hassio_enabled is True
    assert cfg.data_dir == "/data"
    assert cfg.api_host == "0.0.0.0"
    assert cfg.api_port == 8080


def test_config_from_env_disabled(monkeypatch):
    monkeypatch.setenv("GATEWAY_HA_DISCOVERY_ENABLED", "0")
    monkeypatch.setenv("GATEWAY_HA_DISCOVERY_ZEROCONF", "0")
    monkeypatch.setenv("GATEWAY_HA_DISCOVERY_HASSIO", "0")
    cfg = HaDiscoveryConfig.from_env()
    assert cfg.enabled is False
    assert cfg.zeroconf_enabled is False
    assert cfg.hassio_enabled is False


def test_config_from_env_overrides(monkeypatch):
    monkeypatch.setenv("GATEWAY_HA_DISCOVERY_ENABLED", "true")
    monkeypatch.setenv("GATEWAY_API_PORT", "9999")
    monkeypatch.setenv("GATEWAY_DATA_DIR", "/tmp/data")
    cfg = HaDiscoveryConfig.from_env()
    assert cfg.enabled is True
    assert cfg.api_port == 9999
    assert cfg.data_dir == "/tmp/data"


# ---------------------------------------------------------------------------
# instance_id persistence
# ---------------------------------------------------------------------------


def test_instance_id_created_when_missing(tmp_path: Path):
    instance_id = _load_or_create_instance_id(str(tmp_path))
    assert instance_id
    assert (tmp_path / "instance_id").read_text(encoding="utf-8") == instance_id


def test_instance_id_reused_when_present(tmp_path: Path):
    (tmp_path / "instance_id").write_text("deadbeef", encoding="utf-8")
    assert _load_or_create_instance_id(str(tmp_path)) == "deadbeef"


def test_instance_id_regenerated_when_file_empty(tmp_path: Path):
    (tmp_path / "instance_id").write_text("   \n", encoding="utf-8")
    instance_id = _load_or_create_instance_id(str(tmp_path))
    assert instance_id
    assert instance_id != ""


# ---------------------------------------------------------------------------
# Publish IP
# ---------------------------------------------------------------------------


def test_pick_publish_ip_explicit(monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    assert _pick_publish_ip("192.168.1.10") == "192.168.1.10"


def test_pick_publish_ip_addon(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "x")
    assert _pick_publish_ip("0.0.0.0") == "127.0.0.1"


def test_pick_publish_ip_standalone(monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    # Standalone: connect-trick should return *something*; we don't pin the IP.
    ip = _pick_publish_ip("0.0.0.0")
    assert ip != "0.0.0.0"


# ---------------------------------------------------------------------------
# TXT properties
# ---------------------------------------------------------------------------


def test_txt_properties_addon_true():
    props = _build_txt_properties("inst1", "http://192.168.1.10:8080", True)
    assert props["instance_id"] == "inst1"
    assert props["base_url"] == "http://192.168.1.10:8080"
    assert props["homeassistant_addon"] == "true"
    assert props["version"] == __version__
    assert props["schema_version"] == str(DISCOVERY_SCHEMA_VERSION)
    # All values are strings (RFC 6763)
    assert all(isinstance(v, str) for v in props.values())


def test_txt_properties_addon_false():
    props = _build_txt_properties("inst2", "http://10.0.0.5:8080", False)
    assert props["homeassistant_addon"] == "false"


# ---------------------------------------------------------------------------
# Addon detection
# ---------------------------------------------------------------------------


def test_running_as_hass_addon_false(monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    assert _running_as_hass_addon() is False


def test_running_as_hass_addon_true(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "abc")
    assert _running_as_hass_addon() is True


# ---------------------------------------------------------------------------
# Advertiser
# ---------------------------------------------------------------------------


def test_advertiser_explicit_instance_id(tmp_path: Path):
    cfg = HaDiscoveryConfig(
        enabled=True,
        zeroconf_enabled=False,
        hassio_enabled=False,
        data_dir=str(tmp_path),
        api_host="127.0.0.1",
        api_port=8080,
    )
    adv = HaDiscoveryAdvertiser(cfg, instance_id="myinstance")
    assert adv.instance_id == "myinstance"
    assert adv.is_addon is False
    assert adv.base_url == "http://127.0.0.1:8080"


def test_advertiser_txt_exposes_full_props(tmp_path: Path):
    cfg = HaDiscoveryConfig(
        enabled=True,
        zeroconf_enabled=False,
        hassio_enabled=False,
        data_dir=str(tmp_path),
        api_host="192.168.1.42",
        api_port=9090,
    )
    adv = HaDiscoveryAdvertiser(cfg, instance_id="abc")
    props = adv.txt_properties
    assert props["instance_id"] == "abc"
    assert props["base_url"] == "http://192.168.1.42:9090"
    assert props["homeassistant_addon"] == "false"


@pytest.mark.asyncio
async def test_advertiser_start_disabled_does_nothing(tmp_path: Path):
    cfg = HaDiscoveryConfig(
        enabled=False,
        zeroconf_enabled=True,
        hassio_enabled=True,
        data_dir=str(tmp_path),
        api_host="127.0.0.1",
        api_port=8080,
    )
    adv = HaDiscoveryAdvertiser(cfg, instance_id="x")
    await adv.start()
    await adv.stop()
    # No HTTP session / aiozc was created
    assert adv._aiozc is None
    assert adv._http is None


@pytest.mark.asyncio
async def test_advertiser_hassio_skipped_without_token(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    cfg = HaDiscoveryConfig(
        enabled=True,
        zeroconf_enabled=False,
        hassio_enabled=True,
        data_dir=str(tmp_path),
        api_host="127.0.0.1",
        api_port=8080,
    )
    adv = HaDiscoveryAdvertiser(cfg, instance_id="x")
    await adv.start()
    # No HTTP session was created because we are not running as a Supervisor add-on
    assert adv._http is None
    assert adv._hassio_task is None
    await adv.stop()


# ---------------------------------------------------------------------------
# mDNS naming (RFC 6762 §6.7: server label <= 15 bytes)
# ---------------------------------------------------------------------------


def test_zeroconf_server_label_within_rfc_limit(monkeypatch):
    """The mDNS host label passed to AsyncServiceInfo(server=…) must be
    at most 15 bytes. Otherwise zeroconf rejects the registration
    ("Service name must be <= 15 bytes") and the gateway goes silent on
    the LAN even though the rest of the gateway works.
    """
    from unittest.mock import AsyncMock, MagicMock, patch

    cfg = HaDiscoveryConfig(
        enabled=True,
        zeroconf_enabled=True,
        hassio_enabled=False,
        data_dir="/tmp",
        api_host="127.0.0.1",
        api_port=8080,
    )
    adv = HaDiscoveryAdvertiser(cfg, instance_id="a" * 32)

    fake_aiozc = MagicMock()
    fake_aiozc.async_register_service = AsyncMock(return_value=None)
    fake_aiozc_class = MagicMock(return_value=fake_aiozc)

    monkeypatch.setattr("gateway.ha_discovery.AsyncZeroconf", fake_aiozc_class)

    import asyncio
    asyncio.run(adv._start_zeroconf())

    assert adv._service_info is not None, "service info was never built"
    server = adv._service_info.server
    assert server is not None
    # Strip the trailing dot — only the label portion is constrained.
    label = server.rstrip(".")
    assert len(label.encode("utf-8")) <= 15, (
        f"mDNS server label {label!r} is {len(label)} bytes; "
        "RFC 6762 §6.7 limits it to 15"
    )
    # And it must not include the (long) raw instance id verbatim.
    assert "a" * 32 not in label


def test_zeroconf_service_instance_name_under_63_bytes(monkeypatch):
    """Service instance names (RFC 6763 §7.2) must be <= 63 bytes."""
    from unittest.mock import AsyncMock, MagicMock

    cfg = HaDiscoveryConfig(
        enabled=True,
        zeroconf_enabled=True,
        hassio_enabled=False,
        data_dir="/tmp",
        api_host="127.0.0.1",
        api_port=8080,
    )
    adv = HaDiscoveryAdvertiser(cfg, instance_id="a" * 32)

    fake_aiozc = MagicMock()
    fake_aiozc.async_register_service = AsyncMock(return_value=None)
    fake_aiozc_class = MagicMock(return_value=fake_aiozc)
    monkeypatch.setattr("gateway.ha_discovery.AsyncZeroconf", fake_aiozc_class)

    import asyncio
    asyncio.run(adv._start_zeroconf())

    name = adv._service_info.name
    # name is bytes in zeroconf, str in mocks; normalise.
    encoded = name.encode("utf-8") if isinstance(name, str) else name
    assert len(encoded) <= 63
