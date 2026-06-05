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

    def __init__(self, *, config, devices_file, broadcast, installation) -> None:
        self.config = config
        self.devices_file = devices_file
        self.broadcast = broadcast
        self.installation = installation
        self.started = False
        type(self).instances.append(self)

    async def start(self) -> None:
        self.started = True


class _StubAPI:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def set_orchestrator(self, orch) -> None:
        self.orchestrator = orch

    async def start(self) -> None:
        return None


class _StubShim:
    def __init__(self, *args, **kwargs) -> None:
        pass


@contextlib.asynccontextmanager
async def _cancel_after_start():
    """Run run_gateway in a task and cancel it shortly after start."""
    task = asyncio.create_task(run_gateway())
    # Yield control so the coroutine reaches its first awaitable.
    await asyncio.sleep(0)
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(BaseException):
            await task


@pytest.mark.asyncio
async def test_run_gateway_discovery_path_does_not_nameerror(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """run_gateway must not raise NameError when discovery is enabled."""
    devices_file = tmp_path / "devices.json"
    devices_file.write_text('{"modules":[]}', encoding="utf-8")

    cfg = GatewayConfig(
        simulated_mode=True,
        poll_interval_s=3600.0,  # don't actually start a poll loop
        discovery=DiscoveryConfig(),
        installation=None,
    )

    # The devices_file path should be sourced from GATEWAY_DEVICES_FILE, which
    # the runbook / add-on options set to /data/devices.json.
    monkeypatch.setenv("GATEWAY_DEVICES_FILE", str(devices_file))

    # Stub the network and orchestrator side-effects.
    monkeypatch.setattr("gateway.main.UDPBus", _StubBus)
    monkeypatch.setattr("gateway.main.GatewayAPI", _StubAPI)
    monkeypatch.setattr("gateway.main.RESTShim", _StubShim)
    monkeypatch.setattr("gateway.main.DiscoveryOrchestrator", _StubOrchestrator)

    _StubOrchestrator.instances.clear()

    # The DiscoveryOrchestrator constructor + .start() must be reached. We cancel
    # the task immediately after the first sleep so the test returns quickly.
    async with _cancel_after_start():
        # Give the coroutine a chance to reach orchestrator.start().
        await asyncio.sleep(0.05)

    # If the bug is present, asyncio will surface NameError as a task exception
    # and the orchestrator will never have been constructed. After the fix, the
    # orchestrator must be constructed and start() called.
    assert _StubOrchestrator.instances, (
        "DiscoveryOrchestrator was never constructed \u2014 "
        "run_gateway crashed before reaching the discovery branch"
    )
    orch = _StubOrchestrator.instances[-1]
    assert orch.started, "orchestrator.start() was never called"
    assert orch.devices_file == str(devices_file), (
        f"orchestrator.devices_file mismatch: {orch.devices_file!r} != {str(devices_file)!r}"
    )
