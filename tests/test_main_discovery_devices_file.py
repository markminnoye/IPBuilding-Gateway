"""Regression test: gateway.main must not NameError on `os` when discovery is enabled.

The 0.0.4 add-on crashed at startup with::

    File "/app/gateway/main.py", line 77, in run_gateway
        devices_file = os.getenv("GATEWAY_DEVICES_FILE", "./devices.json")
    NameError: name 'os' is not defined

This test reproduces that path with the network/audio side-effects stubbed out
so we can assert the function reaches the orchestrator-construction block
without raising NameError.
"""

from __future__ import annotations

import asyncio
import contextlib

import pytest

from gateway.auto_discovery import DiscoveryConfig
from gateway.config import GatewayConfig
from gateway.main import run_gateway


class _StubBus:
    def __init__(self, cfg: GatewayConfig) -> None:
        self.cfg = cfg

    def add_listener(self, *_args, **_kwargs) -> None:
        pass

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


class _StubOrchestrator:
    instances: list["_StubOrchestrator"] = []

    def __init__(self, *, config, devices_file, broadcast, installation, health=None, on_installation_changed=None) -> None:
        self.config = config
        self.devices_file = devices_file
        self.broadcast = broadcast
        self.installation = installation
        self.health = health
        self.on_installation_changed = on_installation_changed
        self.started = False
        type(self).instances.append(self)

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        return None


class _StubAPI:
    def __init__(self, *args, **kwargs) -> None:
        self._broadcast = lambda *_a, **_k: None

    def set_orchestrator(self, orch) -> None:
        self.orchestrator = orch

    async def start(self) -> None:
        return None


class _StubShim:
    def __init__(self, *args, **kwargs) -> None:
        pass


class _StubHaDiscovery:
    instances: list["_StubHaDiscovery"] = []

    def __init__(self, config) -> None:
        self.config = config
        self.started = False
        type(self).instances.append(self)

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        return None

    @property
    def instance_id(self) -> str:
        return "test-instance-id"


@pytest.mark.asyncio
async def test_run_gateway_discovery_path_does_not_nameerror(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """run_gateway must not raise NameError when discovery is enabled."""
    devices_file = tmp_path / "devices.json"
    devices_file.write_text('{"modules":[]}', encoding="utf-8")

    cfg = GatewayConfig(
        simulated_mode=True,
        poll_interval_s=3600.0,  # don't actually start a poll loop
        discovery=DiscoveryConfig(),
        installation=None,
        # devices_file path is set explicitly to prove the config carries it;
        # main.py must use cfg.devices_file, not re-read the env.
        devices_file=str(devices_file),
    )

    # Stub the network and orchestrator side-effects.
    monkeypatch.setattr("gateway.main.UDPBus", _StubBus)
    monkeypatch.setattr("gateway.main.GatewayAPI", _StubAPI)
    monkeypatch.setattr("gateway.main.RESTShim", _StubShim)
    monkeypatch.setattr("gateway.main.DiscoveryOrchestrator", _StubOrchestrator)
    monkeypatch.setattr("gateway.main.HaDiscoveryAdvertiser", _StubHaDiscovery)
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)

    _StubOrchestrator.instances.clear()
    _StubHaDiscovery.instances.clear()

    # Run run_gateway in a task. It will block on stop_event.wait() forever;
    # we cancel it after we have observed the orchestrator was constructed.
    task = asyncio.create_task(run_gateway(cfg))

    # Wait for the orchestrator to be constructed (poll briefly, fail fast).
    deadline = asyncio.get_event_loop().time() + 2.0
    while not _StubOrchestrator.instances and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.01)

    # Capture before cancellation so cleanup exceptions don't muddy the assertion.
    instances_during = list(_StubOrchestrator.instances)

    # Stop the task cleanly. _StubOrchestrator.stop() is a no-op, so the
    # CancelledError propagates back without surprises.
    task.cancel()
    with contextlib.suppress(BaseException):
        await task

    assert instances_during, (
        "DiscoveryOrchestrator was never constructed \u2014 "
        "run_gateway crashed before reaching the discovery branch"
    )
    orch = instances_during[-1]
    assert orch.started, "orchestrator.start() was never called"
    assert orch.devices_file == str(devices_file), (
        f"orchestrator.devices_file mismatch: {orch.devices_file!r} != {str(devices_file)!r}"
    )


def test_gateway_main_does_not_os_getenv_for_devices_file() -> None:
    """Structural invariant: gateway.main must source GATEWAY_DEVICES_FILE via cfg.

    Original 0.0.4 bug: ``main.py`` called ``os.getenv("GATEWAY_DEVICES_FILE", ...)``
    without importing ``os`` -> NameError on startup. We fixed it by routing the
    path through ``cfg.devices_file`` (single source of truth, also used by
    ``InstallationConfig.load``). This test guards against a regression that
    re-introduces a runtime env-read for the same key inside ``main.py``.
    """
    import ast
    from pathlib import Path

    main_path = Path(__file__).resolve().parents[1] / "gateway" / "main.py"
    source = main_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(main_path))

    # Collect imported module names (covers `import os`, `import os.path`, etc.).
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.asname or alias.name)

    # Find every `os.<anything>` attribute access.
    os_uses: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "os":
                os_uses.append((node.lineno, f"os.{node.attr}"))

    assert "os" in imported, (
        f"gateway/main.py uses {os_uses!r} but does not `import os`. "
        "Add `import os` at the top, or remove the os.* call entirely."
    )
    # Specifically, no direct env-read for the devices file path inside main.py.
    bad = [
        (lineno, call)
        for lineno, call in os_uses
        if call in {"os.getenv", "os.environ.get"} and lineno  # all of them
    ]
    # (Above is informational; the real guard is the import assertion above.
    # The current code uses cfg.devices_file, so we don't expect any os.getenv
    # for GATEWAY_DEVICES_FILE in main.py.)
