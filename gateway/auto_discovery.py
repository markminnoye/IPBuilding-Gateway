"""Runtime auto-discovery for the IPBuilding gateway.

Coordinates three discovery paths:
1. **Init-sweep**  — on first start if devices.json is empty, run ARP-sweep to
   populate the installation with ``active: false`` entries.
2. **Passive ARP monitor** — periodically reads the kernel ARP table; emits
   ``device_added`` when a new OUI-00:24:77 MAC appears, ``device_removed``
   after N missed polls, and ``device_ip_changed`` when a known MAC relocates.
3. **Forced discovery** — triggered via ``POST /api/v1/discover``; always runs
   regardless of toggles; updates firmware in devices.json.

All discovery results are written back via :class:`AtomicWriter` so that
concurrent readers always see a consistent snapshot.

The module does **not** import from ``gateway.gateway_api`` to avoid circular
imports.  Instead it receives the broadcast callback as a constructor argument.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, TypeVar

from gateway.discovery import (
    discover_modules,
    discovered_module_to_devices_json,
    parse_arp_table,
    resolve_module_model,
)
from gateway.health import GatewayHealthMonitor
from gateway.installation import InstallationConfig, ModuleConfig

log = logging.getLogger(__name__)

# Lock file kept alongside devices.json
_LOCK_SUFFIX = ".lock"

T = TypeVar("T")

_EMPTY_DEVICES_JSON: dict[str, list] = {"modules": []}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class DiscoveryConfig:
    """Runtime discovery behaviour."""

    subnet: str = "10.10.1"
    range_start: int = 0        # default: full /24 sweep
    range_end: int = 254
    arp_poll_interval_s: float = 30.0
    passive_arp_monitor: bool = True   # default: on
    auto_discover_on_start: bool = False   # default: off
    force_discover_on_start: bool = False  # default: off — run_forced_discovery at startup
    http_timeout_s: float = 2.0
    lock_timeout_s: float = 15.0        # AtomicWriter lock acquire timeout
    removed_after_n_polls: int = 3      # N missed ARP polls → "removed"

    def hub_ip_in_subnet(self, hub_ip: str) -> bool:
        """Return True if hub_ip is in the discovery subnet."""
        import ipaddress
        try:
            hub = ipaddress.ip_address(hub_ip)
            net = ipaddress.ip_network(self.subnet + ".0/24", strict=False)
            return hub in net
        except ValueError:
            return False

    @classmethod
    def from_env(cls) -> "DiscoveryConfig":
        import os
        return cls(
            subnet=os.getenv("GATEWAY_DISCOVERY_SUBNET", "10.10.1"),
            range_start=int(os.getenv("GATEWAY_DISCOVERY_RANGE_START", "0")),
            range_end=int(os.getenv("GATEWAY_DISCOVERY_RANGE_END", "254")),
            arp_poll_interval_s=float(os.getenv("GATEWAY_ARP_POLL_INTERVAL_S", "30.0")),
            passive_arp_monitor=os.getenv("GATEWAY_PASSIVE_ARP_MONITOR", "1").lower()
                in ("1", "true", "yes"),
            auto_discover_on_start=os.getenv("GATEWAY_AUTO_DISCOVER_ON_START", "0").lower()
                in ("1", "true", "yes"),
            force_discover_on_start=os.getenv("GATEWAY_FORCE_DISCOVER_ON_START", "0").lower()
                in ("1", "true", "yes"),
            http_timeout_s=float(os.getenv("GATEWAY_HTTP_TIMEOUT_S", "2.0")),
        )


# ---------------------------------------------------------------------------
# Runtime state (per discovered MAC, not persisted)
# ---------------------------------------------------------------------------


@dataclass
class DiscoveryState:
    """Live runtime state for a single MAC tracked by the passive monitor."""

    mac: str
    ip: str
    last_seen_at: str            # ISO timestamp
    last_seen_source: str        # "arp" | "http"
    consecutive_misses: int = 0


# ---------------------------------------------------------------------------
# Atomic writer — safe writes to devices.json with advisory locking
# ---------------------------------------------------------------------------


class AtomicWriter:
    """Write a JSON dict to devices.json atomically (tempfile + rename + flock).

    Acquires an exclusive advisory lock on ``devices_file.lock`` before writing.
    Timeout on lock acquisition is configurable (default 15 s).
    On timeout the old file is left intact and an ERROR is logged.
    """

    def __init__(
        self,
        devices_file: str | os.PathLike,
        lock_timeout_s: float = 15.0,
    ) -> None:
        self._devices_file = str(devices_file)
        self._lock_file = self._devices_file + _LOCK_SUFFIX
        self._lock_timeout_s = lock_timeout_s

    def _run_under_lock(self, work: Callable[[], T]) -> tuple[bool, T | None]:
        """Acquire exclusive lock, run ``work()``, release lock.

        Returns ``(False, None)`` on lock timeout. ``work()`` exceptions
        propagate after the lock is released.
        """
        lock_fd = None
        try:
            lock_fd = os.open(self._lock_file, os.O_RDONLY | os.O_CREAT, 0o644)
            start = os.times().elapsed

            while True:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    elapsed = os.times().elapsed - start
                    if elapsed >= self._lock_timeout_s:
                        log.error(
                            "AtomicWriter: lock acquire timeout after %.1f s on %s",
                            self._lock_timeout_s,
                            self._devices_file,
                        )
                        return False, None
                    import time as _time
                    _time.sleep(0.05)

            return True, work()
        finally:
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                    os.close(lock_fd)
                except OSError:
                    pass
            try:
                os.unlink(self._lock_file)
            except FileNotFoundError:
                pass
            except OSError as exc:
                log.debug("AtomicWriter: could not remove %s: %s", self._lock_file, exc)

    def _read_json_dict(self) -> dict:
        """Load devices.json; missing file yields an empty installation."""
        try:
            with open(self._devices_file, encoding="utf-8") as fh:
                return json.load(fh)
        except FileNotFoundError:
            return dict(_EMPTY_DEVICES_JSON)

    def _write_json_dict(self, data: dict) -> None:
        """Atomically replace devices.json with ``data`` (caller holds lock)."""
        dir_path = os.path.dirname(self._devices_file) or "."
        fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
                fh.write("\n")
            os.rename(tmp_path, self._devices_file)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def write(self, data: dict) -> bool:
        """Atomically replace devices.json with ``data``.

        Returns ``True`` on success, ``False`` on lock-timeout (file unchanged).
        The advisory lock file (``devices_file.lock``) is always removed on
        exit, even on exception, so it does not leak into the working tree
        as an untracked artefact.
        """
        def work() -> bool:
            self._write_json_dict(data)
            log.info(
                "AtomicWriter: wrote %s (%d modules)",
                self._devices_file,
                len(data.get("modules", [])),
            )
            return True

        ok, _ = self._run_under_lock(work)
        return ok

    def read_modify_write(
        self, mutate: Callable[[dict], dict]
    ) -> tuple[bool, dict | None]:
        """Hold the lock across read → mutate → write.

        ``mutate`` receives the parsed JSON dict and must return the new dict
        to persist. It may raise :class:`gateway.device_config.DeviceConfigError`
        to abort without writing. Returns ``(False, None)`` on lock timeout
        (same as :meth:`write`). A missing ``devices.json`` is treated as
        ``{"modules": []}``.
        """
        def work() -> dict:
            raw = self._read_json_dict()
            new_data = mutate(raw)
            self._write_json_dict(new_data)
            modules = new_data.get("modules", [])
            pushbutton_count = sum(len(m.get("pushbuttons", [])) for m in modules)
            log.info(
                "AtomicWriter: read_modify_write %s (%d modules, %d pushbuttons)",
                self._devices_file,
                len(modules),
                pushbutton_count,
            )
            return new_data

        ok, result = self._run_under_lock(work)
        if ok:
            return True, result
        return False, None


# ---------------------------------------------------------------------------
# ARP monitor — passive polling of the kernel ARP table
# ---------------------------------------------------------------------------


class ArpMonitor:
    """Poll the kernel ARP table and emit callbacks on changes.

    Uses :func:`gateway.discovery.parse_arp_table` directly — no duplicate
    ARP parsing logic here.

    Emits ``on_new(mac, ip)``, ``on_missing(mac)``, ``on_ip_changed(mac, old_ip, new_ip)``.
    """

    OUI_FIELD = "00:24:77"

    def __init__(
        self,
        subnet: str,
        poll_interval_s: float = 30.0,
        removed_after_n_polls: int = 3,
    ) -> None:
        self._subnet = subnet
        self._poll_interval_s = poll_interval_s
        self._removed_after_n_polls = removed_after_n_polls

        # MAC → DiscoveryState (live runtime state)
        self._state: dict[str, DiscoveryState] = {}

        # callbacks
        self._on_new: Callable[[str, str], None] | None = None
        self._on_missing: Callable[[str], None] | None = None
        self._on_ip_changed: Callable[[str, str, str], None] | None = None

    def on_new(self, cb: Callable[[str, str], None]) -> None:
        self._on_new = cb

    def on_missing(self, cb: Callable[[str], None]) -> None:
        self._on_missing = cb

    def on_ip_changed(self, cb: Callable[[str, str, str], None]) -> None:
        self._on_ip_changed = cb

    def _is_field_module(self, mac: str) -> bool:
        return mac.lower().startswith(self.OUI_FIELD + ":")

    async def _poll(self) -> None:
        """Read ARP table, update state, fire callbacks."""
        now = datetime.now(timezone.utc).isoformat()
        rows = parse_arp_table(self._subnet)

        # Current snapshot
        current: dict[str, str] = {}  # mac → ip
        for ip, mac in rows:
            if self._is_field_module(mac):
                current[mac] = ip

        # Detect new / IP-changed
        for mac, ip in current.items():
            if mac in self._state:
                old_ip = self._state[mac].ip
                if old_ip != ip:
                    # IP changed for known MAC → DHCP relocation
                    self._state[mac].ip = ip
                    self._state[mac].last_seen_at = now
                    self._state[mac].last_seen_source = "arp"
                    self._state[mac].consecutive_misses = 0
                    if self._on_ip_changed:
                        self._on_ip_changed(mac, old_ip, ip)
                    log.info("ARP: %s moved %s → %s", mac, old_ip, ip)
            else:
                # New module discovered
                self._state[mac] = DiscoveryState(
                    mac=mac,
                    ip=ip,
                    last_seen_at=now,
                    last_seen_source="arp",
                    consecutive_misses=0,
                )
                if self._on_new:
                    self._on_new(mac, ip)
                log.info("ARP: new module %s at %s", mac, ip)

        # Detect missing (missed polls)
        known_macs = set(self._state.keys())
        for mac in known_macs:
            if mac not in current:
                self._state[mac].consecutive_misses += 1
                if self._state[mac].consecutive_misses >= self._removed_after_n_polls:
                    if self._on_missing:
                        self._on_missing(mac)
                    log.info("ARP: %s removed after %d missed polls", mac, self._removed_after_n_polls)
                    del self._state[mac]

    async def run(self) -> None:
        """Periodically poll the ARP table until cancelled."""
        while True:
            await asyncio.sleep(self._poll_interval_s)
            try:
                await self._poll()
            except Exception:
                log.exception("ArpMonitor: poll failed")


# ---------------------------------------------------------------------------
# Orchestrator — coordinates init-sweep, passive monitor, forced discovery
# ---------------------------------------------------------------------------


class DiscoveryOrchestrator:
    """Coordinates all runtime discovery activities.

    Parameters
    ----------
    config : DiscoveryConfig
        Discovery behaviour settings.
    devices_file : str
        Path to devices.json (for init-sweep writing).
    broadcast : Callable[[dict], None]
        Async callback invoked for each discovery event (device_added,
        device_removed, device_ip_changed, device_firmware_changed).
        The callback is responsible for routing the event to WebSocket clients.
    installation : InstallationConfig | None
        Pre-loaded installation (may be None on first start).
    on_installation_changed : Callable[[InstallationConfig], None] | None
        Optional sync callback invoked after each init-sweep or forced
        discovery once the new ``InstallationConfig`` has been reloaded
        from disk. Lets the caller propagate the change to
        ``cfg.installation``, ``DeviceRegistry`` and the metadata cache.
    """

    def __init__(
        self,
        config: DiscoveryConfig,
        devices_file: str,
        broadcast: Callable[[dict], Any],
        installation: InstallationConfig | None = None,
        health: GatewayHealthMonitor | None = None,
        on_installation_changed: "Callable[[InstallationConfig], None] | None" = None,
    ) -> None:
        self._config = config
        self._devices_file = devices_file
        self._broadcast = broadcast
        self._installation = installation
        self._health = health
        self._on_installation_changed = on_installation_changed
        self._writer = AtomicWriter(devices_file, lock_timeout_s=config.lock_timeout_s)

        self._arp_monitor: ArpMonitor | None = None
        self._arp_task: asyncio.Task | None = None
        self._stopping = False

    def _emit(self, msg: dict) -> None:
        """Schedule a WebSocket broadcast (safe from sync and async callers)."""
        result = self._broadcast(msg)
        if asyncio.iscoroutine(result):
            asyncio.create_task(result)

    def _run_forced_discovery_sync(self) -> list[dict]:
        """Synchronous wrapper around discover_modules — runs in thread pool."""
        subnet = self._config.subnet
        start = self._config.range_start
        end = self._config.range_end
        ip_range = range(start, end + 1) if start <= end else range(0, 255)
        return asyncio.run(
            discover_modules(
                subnet=subnet,
                ip_range=ip_range,
                arp_first=True,
                http_timeout=self._config.http_timeout_s,
            )
        )

    async def run_forced_discovery(self) -> dict:
        """Run ARP-sweep + HTTP identify and return result summary.

        Returns ``{"ok", "added", "changed", "removed", "duration_ms"}``.
        Writes new modules to devices.json (active:false), updates firmware
        on existing modules.
        """
        import time
        start = time.monotonic()
        now_iso = datetime.now(timezone.utc).isoformat()

        # Run discovery in thread to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        discovered = await loop.run_in_executor(None, self._run_forced_discovery_sync)

        log.info(
            "DiscoveryOrchestrator: forced discovery returned %d candidate(s)",
            len(discovered),
        )

        added: list[dict] = []
        skipped_unidentified: list[dict] = []
        changed: list[dict] = []
        firmware_changed: list[dict] = []

        # Load current devices.json (may have been written since init)
        installation = None
        try:
            installation = InstallationConfig.load(self._devices_file)
        except Exception:
            pass

        # Build the new modules list
        current_modules: dict[str, dict] = {}
        if installation:
            for mc in installation.modules:
                current_modules[mc.mac] = mc

        all_macs = set(current_modules.keys()) | {m.mac for m in discovered if m.mac}

        modules_to_write: list[dict] = []

        # First: preserve existing modules; backfill SKU where missing.
        if installation:
            for mc in installation.modules:
                d = mc.to_dict()
                # Runtime-only fields (last_seen, last_seen_source) are
                # intentionally NOT written to devices.json. Update them on
                # the in-memory object so the WS-emit and ``_apply_gateway_status``
                # path see the new timestamp, but keep devices.json stable
                # across discovery runs.
                mc.last_seen = now_iso
                mc.last_seen_source = "http"
                # Backfill missing hardware SKU: modules drafted from a
                # pre-provisioned install (e.g. legacy IPBox export) often
                # carry an empty ``model`` and an IP-based ``name``. Replace
                # those with the canonical SKU so the companion shows a
                # stable "Apparaat-info" title across installs.
                resolved_model = resolve_module_model(d.get("model", ""), d.get("type", ""))
                if resolved_model and not d.get("model"):
                    d["model"] = resolved_model
                    d["name"] = resolved_model
                elif resolved_model and d.get("name") == d.get("ip"):
                    d["name"] = resolved_model
                modules_to_write.append(d)

                # Check for IP change
                disc_by_mac = {m.mac: m for m in discovered if m.mac}
                if mc.mac in disc_by_mac:
                    dm = disc_by_mac[mc.mac]
                    if dm.ip != mc.ip:
                        d["ip"] = dm.ip
                        self._emit({
                            "type": "device_ip_changed",
                            "mac": mc.mac,
                            "old_ip": mc.ip,
                            "new_ip": dm.ip,
                        })
                    # Check for firmware change
                    if dm.firmware and dm.firmware != mc.firmware:
                        old_firmware = mc.firmware
                        d["firmware"] = dm.firmware
                        self._emit({
                            "type": "device_firmware_changed",
                            "mac": mc.mac,
                            "old_firmware": old_firmware,
                            "new_firmware": dm.firmware,
                        })
                        firmware_changed.append({
                            "mac": mc.mac,
                            "old_firmware": old_firmware,
                            "new_firmware": dm.firmware,
                        })

        # Add newly discovered modules (not in current)
        existing_macs = set(current_modules.keys())
        for dm in discovered:
            if dm.mac and dm.mac not in existing_macs:
                self._emit({
                    "type": "device_added",
                    "mac": dm.mac,
                    "ip": dm.ip,
                    "device_type": dm.device_type,
                    "firmware": dm.firmware,
                })
                entry = discovered_module_to_devices_json(dm)
                if entry is None:
                    log.info(
                        "DiscoveryOrchestrator: skipping devices.json write for %s "
                        "(unidentified type %r — HTTP getSysSet/backupConfig required)",
                        dm.ip,
                        dm.device_type,
                    )
                    skipped_unidentified.append({
                        "mac": dm.mac,
                        "ip": dm.ip,
                        "device_type": dm.device_type,
                    })
                    continue
                modules_to_write.append(entry)
                added.append({"mac": dm.mac, "ip": dm.ip})

        duration_ms = int((time.monotonic() - start) * 1000)
        result = {
            "ok": True,
            "added": added,
            "changed": changed,
            "firmware_changed": firmware_changed,
            "removed": [],
            "skipped_unidentified": skipped_unidentified,
            "duration_ms": duration_ms,
        }

        # Write updated modules list
        devices_data = {"modules": modules_to_write}
        self._writer.write(devices_data)

        # Reload installation so registry picks up changes
        try:
            self._installation = InstallationConfig.load(self._devices_file)
        except Exception as exc:
            log.warning(
                "DiscoveryOrchestrator: devices.json written (%d module(s) on disk) "
                "but reload failed — runtime installation unchanged: %s",
                len(modules_to_write),
                exc,
            )

        if self._installation is not None and self._on_installation_changed is not None:
            try:
                self._on_installation_changed(self._installation)
                log.info("DiscoveryOrchestrator: on_installation_changed callback invoked (forced discovery)")
            except Exception:
                log.exception("DiscoveryOrchestrator: callback failed (forced discovery)")

        return result

    def _init_sweep_sync(self) -> list[dict]:
        """Run init-sweep synchronously in thread pool."""
        subnet = self._config.subnet
        start = self._config.range_start
        end = self._config.range_end
        ip_range = range(start, end + 1) if start <= end else range(0, 255)
        return asyncio.run(
            discover_modules(
                subnet=subnet,
                ip_range=ip_range,
                arp_first=True,
                http_timeout=self._config.http_timeout_s,
            )
        )

    def _clear_unloadable_devices_file(self) -> None:
        """Replace devices.json with an empty module list when load failed."""
        if self._installation is None and os.path.exists(self._devices_file):
            self._writer.write({"modules": []})
            try:
                self._installation = InstallationConfig.load(self._devices_file)
            except Exception as exc:
                log.warning(
                    "DiscoveryOrchestrator: cleared devices.json but reload failed: %s",
                    exc,
                )
            log.info(
                "DiscoveryOrchestrator: cleared unloadable devices.json at %s",
                self._devices_file,
            )

    async def _run_init_sweep(self) -> None:
        """Run ARP-sweep on startup when devices.json is empty or missing."""
        log.info("DiscoveryOrchestrator: running init-sweep")
        try:
            loop = asyncio.get_running_loop()
            discovered = await loop.run_in_executor(None, self._init_sweep_sync)
        except Exception:
            log.exception("DiscoveryOrchestrator: init-sweep failed")
            return

        if not discovered:
            log.info("DiscoveryOrchestrator: init-sweep found no modules")
            self._clear_unloadable_devices_file()
            return

        modules: list[dict] = []
        skipped = 0
        for dm in discovered:
            self._emit({
                "type": "device_added",
                "mac": dm.mac,
                "ip": dm.ip,
                "device_type": dm.device_type,
                "firmware": dm.firmware,
            })
            entry = discovered_module_to_devices_json(dm)
            if entry is None:
                skipped += 1
                log.info(
                    "DiscoveryOrchestrator: init-sweep skipping %s "
                    "(unidentified type %r — HTTP getSysSet/backupConfig required)",
                    dm.ip,
                    dm.device_type,
                )
                continue
            modules.append(entry)

        if skipped:
            log.info(
                "DiscoveryOrchestrator: init-sweep skipped %d unidentified module(s)",
                skipped,
            )

        if not modules:
            log.info("DiscoveryOrchestrator: init-sweep found no loadable modules")
            self._clear_unloadable_devices_file()
            return

        devices_data = {"modules": modules}
        self._writer.write(devices_data)

        try:
            self._installation = InstallationConfig.load(self._devices_file)
        except Exception as exc:
            log.warning(
                "DiscoveryOrchestrator: init-sweep wrote %d module(s) but reload failed: %s",
                len(modules),
                exc,
            )

        if self._installation is not None and self._on_installation_changed is not None:
            try:
                self._on_installation_changed(self._installation)
                log.info("DiscoveryOrchestrator: on_installation_changed callback invoked (init-sweep)")
            except Exception:
                log.exception("DiscoveryOrchestrator: callback failed (init-sweep)")

        log.info("DiscoveryOrchestrator: init-sweep wrote %d modules", len(modules))

    def _needs_init_sweep(self) -> bool:
        """Return True when an init-sweep should populate devices.json.

        A missing devices.json (fresh add-on install) always triggers a sweep
        so the northbound API exposes modules/channels to the companion. An
        unreadable devices.json (parse/validation error) is treated the same
        way. The ``auto_discover_on_start`` toggle only gates re-sweeps when
        the file already exists, loads cleanly, but contains no modules
        (operator-managed empty file).
        """
        if self._installation is not None and self._installation.modules:
            return False

        if not os.path.exists(self._devices_file):
            return True

        if self._installation is None:
            return True

        if self._config.auto_discover_on_start:
            return True

        return False

    async def start(self) -> None:
        """Start the orchestrator: init-sweep (if needed) + passive ARP monitor.

        If ``force_discover_on_start`` is set, runs :meth:`run_forced_discovery`
        after any init-sweep so the gateway is in sync with the field bus
        immediately on startup (preserves existing names/rooms/active flags).
        """
        if self._needs_init_sweep():
            await self._run_init_sweep()

        if self._config.force_discover_on_start:
            try:
                result = await self.run_forced_discovery()
                log.info("DiscoveryOrchestrator: force-discover on start: %s", result)
            except Exception:
                log.exception("DiscoveryOrchestrator: force-discover on start failed")

        if self._config.passive_arp_monitor:
            self._arp_monitor = ArpMonitor(
                subnet=self._config.subnet,
                poll_interval_s=self._config.arp_poll_interval_s,
                removed_after_n_polls=self._config.removed_after_n_polls,
            )
            self._arp_monitor.on_new(self._on_arp_new)
            self._arp_monitor.on_missing(self._on_arp_missing)
            self._arp_monitor.on_ip_changed(self._on_arp_ip_changed)
            self._arp_task = asyncio.create_task(self._arp_monitor.run())
            log.info(
                "DiscoveryOrchestrator: started (passive ARP every %.0f s)",
                self._config.arp_poll_interval_s,
            )
        else:
            log.info("DiscoveryOrchestrator: started (passive monitor disabled)")

    async def stop(self) -> None:
        """Stop the orchestrator and wait for the ARP task to finish."""
        self._stopping = True
        if self._arp_task:
            self._arp_task.cancel()
            try:
                await self._arp_task
            except asyncio.CancelledError:
                pass
        log.info("DiscoveryOrchestrator: stopped")

    # ------------------------------------------------------------------
    # ARP monitor callbacks
    # ------------------------------------------------------------------

    def _on_arp_new(self, mac: str, ip: str) -> None:
        """Handle a newly seen MAC via passive ARP."""
        if self._stopping:
            return
        if self._health is not None:
            self._health.clear_issue(f"discovery.unreachable.{mac}")
        now_iso = datetime.now(timezone.utc).isoformat()

        # If we already have this MAC in devices.json, just update last_seen
        if self._installation:
            existing = self._installation.module_by_mac(mac)
            if existing:
                # Update last_seen on the in-memory object
                existing.last_seen = now_iso
                existing.last_seen_source = "arp"
                if self._health is not None:
                    self._health.clear_issue(f"discovery.unreachable.{mac}")
                log.debug("ARP: updated last_seen for known module %s", mac)
                return

        # New module not in devices.json — emit device_added
        self._emit({
            "type": "device_added",
            "mac": mac,
            "ip": ip,
            "device_type": "unknown",   # type resolved on forced discovery
        })

    def _on_arp_missing(self, mac: str) -> None:
        """Handle a module that has been absent for too many ARP polls."""
        if self._stopping:
            return
        if self._health is not None:
            self._health.report_issue(
                f"discovery.unreachable.{mac}",
                "discovery.unreachable",
                "warning",
                f"Module {mac} not seen for {self._config.removed_after_n_polls} ARP polls",
                {"mac": mac},
            )
        self._emit({
            "type": "device_removed",
            "mac": mac,
        })

    def _on_arp_ip_changed(self, mac: str, old_ip: str, new_ip: str) -> None:
        """Handle DHCP IP relocation of a known module."""
        if self._stopping:
            return
        self._emit({
            "type": "device_ip_changed",
            "mac": mac,
            "old_ip": old_ip,
            "new_ip": new_ip,
        })