"""Tests for gateway.auto_discovery — runtime auto-discovery components."""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gateway.auto_discovery import (
    ArpMonitor,
    AtomicWriter,
    DiscoveryConfig,
    DiscoveryOrchestrator,
    DiscoveryState,
)


# ---------------------------------------------------------------------------
# DiscoveryConfig
# ---------------------------------------------------------------------------

def test_discovery_config_defaults():
    cfg = DiscoveryConfig()
    assert cfg.subnet == "10.10.1"
    assert cfg.range_start == 0
    assert cfg.range_end == 254
    assert cfg.arp_poll_interval_s == 30.0
    assert cfg.passive_arp_monitor is True
    assert cfg.auto_discover_on_start is False
    assert cfg.http_timeout_s == 2.0
    assert cfg.lock_timeout_s == 15.0
    assert cfg.removed_after_n_polls == 3


def test_discovery_config_from_env(monkeypatch):
    monkeypatch.setenv("GATEWAY_DISCOVERY_SUBNET", "192.168.1")
    monkeypatch.setenv("GATEWAY_DISCOVERY_RANGE_START", "20")
    monkeypatch.setenv("GATEWAY_DISCOVERY_RANGE_END", "100")
    monkeypatch.setenv("GATEWAY_ARP_POLL_INTERVAL_S", "60.0")
    monkeypatch.setenv("GATEWAY_PASSIVE_ARP_MONITOR", "0")
    monkeypatch.setenv("GATEWAY_AUTO_DISCOVER_ON_START", "1")
    monkeypatch.setenv("GATEWAY_HTTP_TIMEOUT_S", "5.0")
    cfg = DiscoveryConfig.from_env()
    assert cfg.subnet == "192.168.1"
    assert cfg.range_start == 20
    assert cfg.range_end == 100
    assert cfg.arp_poll_interval_s == 60.0
    assert cfg.passive_arp_monitor is False
    assert cfg.auto_discover_on_start is True
    assert cfg.http_timeout_s == 5.0


def test_discovery_config_hub_ip_in_subnet():
    cfg = DiscoveryConfig(subnet="10.10.1")
    assert cfg.hub_ip_in_subnet("10.10.1.1") is True
    assert cfg.hub_ip_in_subnet("192.168.1.1") is False
    assert cfg.hub_ip_in_subnet("10.10.2.1") is False
    cfg2 = DiscoveryConfig(subnet="192.168.0")
    assert cfg2.hub_ip_in_subnet("192.168.0.100") is True


# ---------------------------------------------------------------------------
# DiscoveryState
# ---------------------------------------------------------------------------

def test_discovery_state_defaults():
    s = DiscoveryState(mac="00:24:77:52:ac:be", ip="10.10.1.30", last_seen_at="", last_seen_source="")
    assert s.consecutive_misses == 0


# ---------------------------------------------------------------------------
# AtomicWriter
# ---------------------------------------------------------------------------

def test_atomic_writer_write_success(tmp_path: Path):
    devices_file = tmp_path / "devices.json"
    devices_file.write_text('{"modules":[]}', encoding="utf-8")

    writer = AtomicWriter(str(devices_file), lock_timeout_s=1.0)
    data = {"modules": [{"ip": "10.10.1.30", "type": "relay", "name": "Test"}]}
    ok = writer.write(data)
    assert ok is True

    loaded = json.loads(devices_file.read_text(encoding="utf-8"))
    assert len(loaded["modules"]) == 1
    assert loaded["modules"][0]["ip"] == "10.10.1.30"


def test_atomic_writer_write_creates_lock_file(tmp_path: Path):
    devices_file = tmp_path / "devices.json"
    devices_file.write_text('{"modules":[]}', encoding="utf-8")

    writer = AtomicWriter(str(devices_file))
    writer.write({"modules": []})
    assert (tmp_path / "devices.json.lock").exists()


def test_atomic_writer_lock_timeout_on_contention(tmp_path: Path):
    """If flock raises OSError (blocked), writer retries until timeout then returns False."""
    devices_file = tmp_path / "devices.json"
    devices_file.write_text('{"modules":[]}', encoding="utf-8")

    lock_file = tmp_path / "devices.json.lock"
    lock_fd = os.open(str(lock_file), os.O_RDONLY | os.O_CREAT, 0o644)
    try:
        # Acquire exclusive lock so other writers block
        fcntl.flock(lock_fd, fcntl.LOCK_EX)

        writer = AtomicWriter(str(devices_file), lock_timeout_s=0.5)
        ok = writer.write({"modules": [{}]})
        assert ok is False

        # File must be unchanged
        with open(devices_file) as f:
            data = json.load(f)
        assert data == {"modules": []}
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


# ---------------------------------------------------------------------------
# ArpMonitor — mocked parse_arp_table
# ---------------------------------------------------------------------------

ARP_ENTRIES = [
    ("10.10.1.30", "00:24:77:52:ac:be"),
    ("10.10.1.40", "00:24:77:52:9e:a8"),
    ("10.10.1.50", "00:24:77:52:ad:aa"),
]


class TestArpMonitor:
    @pytest.fixture
    def monitor(self):
        return ArpMonitor(subnet="10.10.1", poll_interval_s=30.0, removed_after_n_polls=3)

    @pytest.mark.asyncio
    async def test_new_module_fires_callback(self, monitor):
        new_cbs = []
        monitor.on_new(lambda mac, ip: new_cbs.append((mac, ip)))

        with patch("gateway.auto_discovery.parse_arp_table", return_value=ARP_ENTRIES):
            await monitor._poll()

        assert len(new_cbs) == 3
        macs = {m for m, _ in new_cbs}
        assert "00:24:77:52:ac:be" in macs

    @pytest.mark.asyncio
    async def test_missing_module_fires_after_n_polls(self, monitor):
        missing_cbs = []
        monitor.on_missing(lambda mac: missing_cbs.append(mac))

        # First poll: all present
        with patch("gateway.auto_discovery.parse_arp_table", return_value=ARP_ENTRIES):
            await monitor._poll()
        assert len(missing_cbs) == 0

        # After removed_after_n_polls polls with .30 absent
        for _ in range(monitor._removed_after_n_polls):
            with patch("gateway.auto_discovery.parse_arp_table", return_value=ARP_ENTRIES[1:]):
                await monitor._poll()

        assert len(missing_cbs) == 1
        assert missing_cbs[0] == "00:24:77:52:ac:be"

    @pytest.mark.asyncio
    async def test_ip_changed_fires_callback(self, monitor):
        ip_changed_cbs = []
        monitor.on_ip_changed(lambda mac, old, new: ip_changed_cbs.append((mac, old, new)))

        # First poll: .30 at old IP
        with patch("gateway.auto_discovery.parse_arp_table", return_value=[("10.10.1.30", "00:24:77:52:ac:be")]):
            await monitor._poll()

        # Second poll: .30 moved to new IP
        with patch("gateway.auto_discovery.parse_arp_table", return_value=[("10.10.1.35", "00:24:77:52:ac:be")]):
            await monitor._poll()

        assert len(ip_changed_cbs) == 1
        mac, old_ip, new_ip = ip_changed_cbs[0]
        assert mac == "00:24:77:52:ac:be"
        assert old_ip == "10.10.1.30"
        assert new_ip == "10.10.1.35"

    @pytest.mark.asyncio
    async def test_non_field_module_ignored(self, monitor):
        new_cbs = []
        monitor.on_new(lambda mac, ip: new_cbs.append((mac, ip)))

        with patch(
            "gateway.auto_discovery.parse_arp_table",
            return_value=[("192.168.1.1", "bc:30:5b:e2:8f:01")],
        ):
            await monitor._poll()
        assert len(new_cbs) == 0

    @pytest.mark.asyncio
    async def test_state_accumulates(self, monitor):
        monitor.on_new(lambda mac, ip: None)

        with patch("gateway.auto_discovery.parse_arp_table", return_value=ARP_ENTRIES):
            await monitor._poll()

        assert "00:24:77:52:ac:be" in monitor._state
        assert monitor._state["00:24:77:52:ac:be"].consecutive_misses == 0


# ---------------------------------------------------------------------------
# DiscoveryOrchestrator
# ---------------------------------------------------------------------------

class TestDiscoveryOrchestratorInit:
    def test_init_sets_fields(self):
        cfg = DiscoveryConfig()
        orch = DiscoveryOrchestrator(
            config=cfg,
            devices_file="/tmp/devices.json",
            broadcast=MagicMock(),
            installation=None,
        )
        assert orch._config is cfg
        assert orch._devices_file == "/tmp/devices.json"
        assert orch._writer is not None
        assert orch._arp_monitor is None

    def test_writer_uses_lock_timeout_from_config(self):
        cfg = DiscoveryConfig(lock_timeout_s=10.0)
        orch = DiscoveryOrchestrator(
            config=cfg,
            devices_file="/tmp/dev.json",
            broadcast=MagicMock(),
            installation=None,
        )
        assert orch._writer._lock_timeout_s == 10.0


class TestDiscoveryOrchestratorForcedDiscovery:
    @pytest.mark.asyncio
    async def test_run_forced_discovery_returns_result(self, tmp_path: Path):
        devices_file = tmp_path / "devices.json"
        devices_file.write_text('{"modules":[]}', encoding="utf-8")

        discovered = [
            MagicMock(
                ip="10.10.1.30",
                mac="00:24:77:52:ac:be",
                device_type="relay",
                firmware="5.1",
                model="IP200PoE",
                channels=[],
            )
        ]

        orch = DiscoveryOrchestrator(
            config=DiscoveryConfig(),
            devices_file=str(devices_file),
            broadcast=AsyncMock(),
            installation=None,
        )

        with patch("gateway.auto_discovery.discover_modules", return_value=discovered):
            result = await orch.run_forced_discovery()

        assert result["ok"] is True
        assert "added" in result
        assert "duration_ms" in result
        assert result["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_run_forced_discovery_writes_new_modules(self, tmp_path: Path):
        devices_file = tmp_path / "devices.json"
        devices_file.write_text('{"modules":[]}', encoding="utf-8")

        discovered = [
            MagicMock(
                ip="10.10.1.30",
                mac="00:24:77:52:ac:be",
                device_type="relay",
                firmware="5.1",
                model="IP200PoE",
                channels=[],
            )
        ]

        orch = DiscoveryOrchestrator(
            config=DiscoveryConfig(),
            devices_file=str(devices_file),
            broadcast=AsyncMock(),
            installation=None,
        )

        with patch("gateway.auto_discovery.discover_modules", return_value=discovered):
            await orch.run_forced_discovery()

        loaded = json.loads(devices_file.read_text(encoding="utf-8"))
        assert len(loaded["modules"]) == 1
        assert loaded["modules"][0]["mac"] == "00:24:77:52:ac:be"
        assert loaded["modules"][0]["active"] is False


class TestDiscoveryOrchestratorStartStop:
    @pytest.mark.asyncio
    async def test_start_creates_arp_monitor_when_enabled(self):
        cfg = DiscoveryConfig(passive_arp_monitor=True, arp_poll_interval_s=30.0)
        orch = DiscoveryOrchestrator(
            config=cfg,
            devices_file="/tmp/dev.json",
            broadcast=AsyncMock(),
            installation=None,
        )

        await orch.start()

        assert orch._arp_monitor is not None
        assert orch._arp_task is not None

        await orch.stop()
        assert orch._stopping is True

    @pytest.mark.asyncio
    async def test_start_no_arp_when_disabled(self):
        cfg = DiscoveryConfig(passive_arp_monitor=False)
        orch = DiscoveryOrchestrator(
            config=cfg,
            devices_file="/tmp/dev.json",
            broadcast=AsyncMock(),
            installation=None,
        )

        await orch.start()
        assert orch._arp_monitor is None
        await orch.stop()


class TestDiscoveryOrchestratorCallbacks:
    @pytest.mark.asyncio
    async def test_on_arp_new_emits_device_added(self):
        broadcast = AsyncMock()
        orch = DiscoveryOrchestrator(
            config=DiscoveryConfig(),
            devices_file="/tmp/dev.json",
            broadcast=broadcast,
            installation=None,
        )
        orch._on_arp_new("00:24:77:52:ac:be", "10.10.1.30")
        assert broadcast.call_count == 1
        call_args = broadcast.call_args[0][0]
        assert call_args["type"] == "device_added"
        assert call_args["mac"] == "00:24:77:52:ac:be"

    @pytest.mark.asyncio
    async def test_on_arp_missing_emits_device_removed(self):
        broadcast = AsyncMock()
        orch = DiscoveryOrchestrator(
            config=DiscoveryConfig(),
            devices_file="/tmp/dev.json",
            broadcast=broadcast,
            installation=None,
        )
        orch._on_arp_missing("00:24:77:52:ac:be")
        broadcast.assert_called_once()
        assert broadcast.call_args[0][0]["type"] == "device_removed"

    @pytest.mark.asyncio
    async def test_on_arp_ip_changed_emits_device_ip_changed(self):
        broadcast = AsyncMock()
        orch = DiscoveryOrchestrator(
            config=DiscoveryConfig(),
            devices_file="/tmp/dev.json",
            broadcast=broadcast,
            installation=None,
        )
        orch._on_arp_ip_changed("00:24:77:52:ac:be", "10.10.1.30", "10.10.1.35")
        broadcast.assert_called_once()
        call_args = broadcast.call_args[0][0]
        assert call_args["type"] == "device_ip_changed"
        assert call_args["old_ip"] == "10.10.1.30"
        assert call_args["new_ip"] == "10.10.1.35"

    @pytest.mark.asyncio
    async def test_on_arp_new_skips_known_mac_but_updates_last_seen(self, tmp_path: Path):
        from gateway.installation import InstallationConfig

        devices_file = tmp_path / "devices.json"
        devices_file.write_text(
            '{"modules":[{"ip":"10.10.1.30","type":"relay","mac":"00:24:77:52:ac:be","channels":[]}]}',
            encoding="utf-8",
        )
        installation = InstallationConfig.load(devices_file)

        broadcast = AsyncMock()
        orch = DiscoveryOrchestrator(
            config=DiscoveryConfig(),
            devices_file=str(devices_file),
            broadcast=broadcast,
            installation=installation,
        )
        # Simulate known module
        orch._on_arp_new("00:24:77:52:ac:be", "10.10.1.30")
        # No device_added broadcast for already-known modules
        assert broadcast.call_count == 0
        # But last_seen is updated
        mc = installation.module_by_mac("00:24:77:52:ac:be")
        assert mc.last_seen is not None