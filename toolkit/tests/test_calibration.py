"""Tests for IP0300PoE dimmer calibration helpers and the calibrate_dimmer MCP tool."""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any

import pytest
from aiohttp import web

from fake_gateway import FakeGateway
from ipbuilding_debug import calibration
from ipbuilding_debug.server import build_server, skill_text
from ipbuilding_debug.session import GatewaySession
from ipbuilding_debug.tools import calibrate_dimmer, list_devices


def _synthetic_samples(
    *,
    steps: list[int],
    sync_on_s: float = 2.0,
    sync_off_s: float = 3.0,
    hold_s: float = 2.5,
    dim_min: int = 16,
    dim_max: int = 70,
    gamma: float = 0.65,
    dark_y: float = 12.0,
    max_y: float = 162.0,
    dt: float = 0.1,
) -> list[tuple[float, float]]:
    """Generate a synthetic 10 Hz video YAVG curve matching a non-linear 0-10V driver."""
    total_s = 1.0 + sync_on_s + sync_off_s + len(steps) * hold_s + 1.5
    samples: list[tuple[float, float]] = []
    t_sync_on = 1.0
    t_sync_off = t_sync_on + sync_on_s
    t_steps_start = t_sync_off + sync_off_s

    n_frames = int(round(total_s / dt))
    for i in range(n_frames + 1):
        t = round(i * dt, 3)
        if t < t_sync_on:
            y = dark_y
        elif t < t_sync_off:
            y = max_y
        elif t < t_steps_start:
            y = dark_y
        else:
            step_idx = int((t - t_steps_start) // hold_s)
            if step_idx >= len(steps):
                y = dark_y
            else:
                pct = steps[step_idx]
                if pct < dim_min:
                    y = dark_y
                elif pct >= dim_max:
                    y = max_y
                else:
                    u = (pct - dim_min) / (dim_max - dim_min)
                    y = dark_y + (max_y - dark_y) * (u ** gamma)
        samples.append((t, round(y, 3)))
    return samples


async def _instant_sleep(_seconds: float) -> None:
    return None


def _dimmer_devices_fixture() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    modules = [
        {
            "id": "192.0.2.40",
            "ip": "192.0.2.40",
            "type": "dimmer",
            "model": "IP0300PoE",
            "name": "Dimmerkast",
            "firmware": "5.4",
            "last_seen": "2026-11-15T12:00:00Z",
        }
    ]
    devices = [
        {
            "id": "192.0.2.40-0",
            "module_id": "192.0.2.40",
            "module_ip": "192.0.2.40",
            "channel": 0,
            "device_type": "dimmer",
            "name": "Zithoek",
            "room": "Woonkamer",
            "active": True,
            "state": "OFF",
            "level": 0,
            "dim_gamma": 1.0,
            "default_fade": 30,
        },
        {
            "id": "192.0.2.40-1",
            "module_id": "192.0.2.40",
            "module_ip": "192.0.2.40",
            "channel": 1,
            "device_type": "dimmer",
            "name": "Bureau",
            "room": "Bureau",
            "active": True,
            "state": "OFF",
            "level": 0,
            "dim_gamma": 2.2,
            "default_fade": 30,
        },
    ]
    return modules, devices


def test_parse_steps_and_format_uitgang() -> None:
    assert calibration.parse_steps(None) == list(calibration.DEFAULT_SWEEP_STEPS)
    assert calibration.parse_steps("20, 5, 10, 20") == [5, 10, 20]
    with pytest.raises(ValueError):
        calibration.parse_steps("50")
    with pytest.raises(ValueError):
        calibration.parse_steps("0,50")
    with pytest.raises(ValueError):
        calibration.parse_steps("10,101")

    assert calibration.format_uitgang("192.0.2.40", 0) == "40.1.1"
    assert calibration.format_uitgang("192.0.2.40", 1) == "40.1.2"
    assert calibration.format_uitgang("192.0.2.40", 7) == "40.1.8"
    assert calibration.format_uitgang("192.0.2.40", 8) == "40.2.1"


def test_analyze_luma_series_computes_bounds_and_log_log_gamma() -> None:
    steps = [5, 10, 14, 16, 18, 25, 40, 55, 70, 85, 100]
    samples = _synthetic_samples(
        steps=steps,
        sync_on_s=2.0,
        sync_off_s=3.0,
        hold_s=2.5,
        dim_min=15,
        dim_max=70,
        gamma=0.65,
    )
    t_off = calibration.detect_sync_off_time(samples, sync_on_s=2.0, sync_off_s=3.0)
    assert abs(t_off - 3.0) <= 0.15

    result = calibration.analyze_luma_series(
        samples,
        steps,
        2.5,
        sync_on_seconds=2.0,
        sync_off_seconds=3.0,
        margin_min=1,
        sat_threshold=0.985,
    )
    assert result["measured_dim_min"] == 16
    assert result["recommended_dim_min"] == 17
    assert result["recommended_dim_max"] == 70
    assert result["recommended_dim_gamma"] >= 2.8
    assert result["recommended_dim_gamma"] <= 3.5

    by_level = {row["level"]: row["state"] for row in result["steps"]}
    assert by_level[5] == "OFF"
    assert by_level[14] == "OFF"
    assert by_level[25] == "ACTIVE"
    assert by_level[70] == "SATURATED"
    assert by_level[100] == "SATURATED"


@pytest.mark.asyncio
async def test_module_http_roundtrip_via_local_server() -> None:
    saved_requests: list[dict[str, str]] = []
    channels = [
        {"ch": 0, "descr": "Zithoek [40.1.1]", "gr": "Woonkamer", "dimMin": 15, "dimMax": 100, "state": 0},
        {"ch": 1, "descr": "Bureau [40.1.2]", "gr": "Bureau", "dimMin": 15, "dimMax": 70, "state": 0},
    ]

    async def handle_api(request: web.Request) -> web.Response:
        method = request.query.get("method", "")
        if method == "statuses":
            return web.json_response(channels)
        if method == "saveChannel":
            saved_requests.append(dict(request.query))
            ch = int(request.query["ch"])
            for row in channels:
                if row["ch"] == ch:
                    row["descr"] = request.query["ds"]
                    row["gr"] = request.query["gr"]
                    row["dimMin"] = int(request.query["dimMin"])
                    row["dimMax"] = int(request.query["dimMax"])
            return web.Response(text="OK")
        return web.Response(status=400, text="unknown")

    app = web.Application()
    app.router.add_get("/api.html", handle_api)
    runner = web.AppRunner(app)
    await runner.setup()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    await web.SockSite(runner, sock).start()
    try:
        rows, err = await calibration.fetch_module_dimmer_statuses(f"127.0.0.1:{port}")
        assert err is None
        assert rows is not None and len(rows) == 2

        ok, save_err = await calibration.save_module_dimmer_channel(
            f"127.0.0.1:{port}",
            1,
            descr="Bureau [40.1.2]",
            gr="Bureau",
            dim_min=17,
            dim_max=68,
        )
        assert ok is True
        assert save_err is None
        assert saved_requests[-1]["ds"] == "Bureau [40.1.2]"
        assert saved_requests[-1]["dimMin"] == "17"
        assert saved_requests[-1]["dimMax"] == "68"

        fresh, _ = await calibration.fetch_module_dimmer_statuses(f"127.0.0.1:{port}")
        assert fresh is not None
        assert fresh[1]["dimMin"] == 17
        assert fresh[1]["dimMax"] == 68
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_calibrate_dimmer_status_and_graceful_http_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = FakeGateway()
    gateway.modules, gateway.devices = _dimmer_devices_fixture()
    await gateway.start()
    session = GatewaySession(f"127.0.0.1:{gateway.port}", sleeper=_instant_sleep)
    try:
        # 1) Module HTTP reachable
        async def ok_statuses(_ip: str, **_kw: Any) -> tuple[list[dict[str, Any]], None]:
            return [
                {"ch": 0, "descr": "Zithoek [40.1.1]", "gr": "Woonkamer", "dimMin": 15, "dimMax": 100, "state": 0},
                {"ch": 1, "descr": "Bureau [40.1.2]", "gr": "Bureau", "dimMin": 15, "dimMax": 70, "state": 0},
            ], None

        monkeypatch.setattr("ipbuilding_debug.tools.fetch_module_dimmer_statuses", ok_statuses)
        res = await calibrate_dimmer(session, mode="status")
        assert res.data["ok"] is True
        assert len(res.data["channels"]) == 2
        ch1 = res.data["channels"][1]
        assert ch1["uitgang"] == "40.1.2"
        assert ch1["dim_min"] == 15
        assert ch1["dim_max"] == 70
        assert ch1["dim_gamma"] == 2.2
        assert ch1["module_http_reachable"] is True

        # Check list_devices also exposes metadata fields
        listed = await list_devices(session)
        assert listed.data["devices"][1]["dim_gamma"] == 2.2
        assert listed.data["devices"][1]["module_ip"] == "192.0.2.40"

        # 2) Module HTTP unreachable fallback
        async def failed_statuses(_ip: str, **_kw: Any) -> tuple[None, str]:
            return None, "timeout"

        monkeypatch.setattr("ipbuilding_debug.tools.fetch_module_dimmer_statuses", failed_statuses)
        res_unreach = await calibrate_dimmer(session, mode="status", channel=1)
        assert res_unreach.data["ok"] is True
        assert len(res_unreach.data["channels"]) == 1
        assert res_unreach.data["channels"][0]["module_http_reachable"] is False
        assert res_unreach.data["channels"][0]["dim_gamma"] == 2.2
    finally:
        await session.stop()
        await gateway.stop()


@pytest.mark.asyncio
async def test_calibrate_dimmer_sweep_analyze_and_apply_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = FakeGateway()
    gateway.modules, gateway.devices = _dimmer_devices_fixture()
    await gateway.start()
    session = GatewaySession(f"127.0.0.1:{gateway.port}", sleeper=_instant_sleep)

    module_channels = {
        1: {"ch": 1, "descr": "Bureau [40.1.2]", "gr": "Bureau", "dimMin": 15, "dimMax": 70, "state": 0}
    }
    module_saves: list[dict[str, Any]] = []

    async def fake_statuses(_ip: str, **_kw: Any) -> tuple[list[dict[str, Any]], None]:
        return [dict(module_channels[1])], None

    async def fake_save(
        _ip: str,
        ch: int,
        *,
        descr: str,
        gr: str,
        dim_min: int,
        dim_max: int,
        **_kw: Any,
    ) -> tuple[bool, None]:
        module_saves.append({"ch": ch, "descr": descr, "gr": gr, "dim_min": dim_min, "dim_max": dim_max})
        module_channels[ch]["dimMin"] = dim_min
        module_channels[ch]["dimMax"] = dim_max
        return True, None

    monkeypatch.setattr("ipbuilding_debug.tools.fetch_module_dimmer_statuses", fake_statuses)
    monkeypatch.setattr("ipbuilding_debug.tools.save_module_dimmer_channel", fake_save)

    sweep_log = tmp_path / "sweep_ch1.json"
    video_file = tmp_path / "test_bureau.mov"
    video_file.write_bytes(b"fake-mov")

    try:
        # 1) Sweep confirmation gate
        preview = await calibrate_dimmer(
            session,
            mode="sweep",
            device_id="192.0.2.40-1",
            steps="10,20,50,100",
            hold_seconds=1.0,
            sync_on_seconds=1.0,
            sync_off_seconds=1.5,
            sweep_log_path=str(sweep_log),
            confirmed=False,
        )
        assert preview.data["ok"] is False
        assert preview.data["kind"] == "confirmation_required"
        assert preview.data["sent"] is False
        assert gateway.command_calls == []
        assert gateway.patch_calls == []

        # 2) Execute sweep
        ran = await calibrate_dimmer(
            session,
            mode="sweep",
            device_id="192.0.2.40-1",
            steps="10,20,50,100",
            hold_seconds=1.0,
            sync_on_seconds=1.0,
            sync_off_seconds=1.5,
            sweep_log_path=str(sweep_log),
            confirmed=True,
        )
        assert ran.data["ok"] is True
        assert ran.data["sent"] is True
        assert ran.data["steps"] == [10, 20, 50, 100]
        assert sweep_log.is_file()

        # Gateway dim_gamma temporarily 1.0 then restored to 2.2
        assert gateway.patch_calls == [
            {"device_id": "192.0.2.40-1", "dim_gamma": 1.0},
            {"device_id": "192.0.2.40-1", "dim_gamma": 2.2},
        ]
        # Module dimMin/dimMax temporarily 0..100 then restored to 15..70
        assert module_saves == [
            {"ch": 1, "descr": "Bureau [40.1.2]", "gr": "Bureau", "dim_min": 0, "dim_max": 100},
            {"ch": 1, "descr": "Bureau [40.1.2]", "gr": "Bureau", "dim_min": 15, "dim_max": 70},
        ]
        # Sync ON, Sync OFF, 4 step commands, final OFF
        assert [c["value"] for c in gateway.command_calls] == [100, 0, 10, 20, 50, 100, 0]

        saved_log = json.loads(sweep_log.read_text(encoding="utf-8"))
        assert saved_log["steps"] == [10, 20, 50, 100]
        assert len(saved_log["step_offsets_seconds"]) == 4

        # 3) Analyze video using mocked ffprobe output
        async def fake_extract(_video: Any, **_kw: Any) -> list[tuple[float, float]]:
            return _synthetic_samples(
                steps=[10, 20, 50, 100],
                sync_on_s=1.0,
                sync_off_s=1.5,
                hold_s=1.0,
                dim_min=18,
                dim_max=50,
                gamma=0.7,
            )

        monkeypatch.setattr("ipbuilding_debug.tools.extract_video_luma_async", fake_extract)
        analyzed = await calibrate_dimmer(
            session,
            mode="analyze",
            video_path=str(video_file),
            sweep_log_path=str(sweep_log),
            margin_min=1,
        )
        assert analyzed.data["ok"] is True
        assert analyzed.data["measured_dim_min"] == 20
        assert analyzed.data["recommended_dim_min"] == 21
        assert analyzed.data["recommended_dim_max"] == 50
        assert 1.0 <= analyzed.data["recommended_dim_gamma"] <= 3.5

        # 4) Apply preview
        apply_preview = await calibrate_dimmer(
            session,
            mode="apply",
            device_id="192.0.2.40-1",
            dim_min=21,
            dim_max=50,
            dim_gamma=2.6,
            default_fade=35,
            confirmed=False,
        )
        assert apply_preview.data["kind"] == "confirmation_required"
        assert apply_preview.data["sent"] is False
        assert apply_preview.data["before"]["dim_min"] == 15
        assert apply_preview.data["after"]["dim_min"] == 21

        # 5) Apply confirmed
        applied = await calibrate_dimmer(
            session,
            mode="apply",
            device_id="192.0.2.40-1",
            dim_min=21,
            dim_max=50,
            dim_gamma=2.6,
            default_fade=35,
            confirmed=True,
        )
        assert applied.data["ok"] is True
        assert applied.data["sent"] is True
        assert applied.data["verified_module"]["dim_min"] == 21
        assert applied.data["verified_module"]["dim_max"] == 50
        assert gateway.patch_calls[-1] == {
            "device_id": "192.0.2.40-1",
            "dim_gamma": 2.6,
            "default_fade": 35,
        }
    finally:
        await session.stop()
        await gateway.stop()


@pytest.mark.asyncio
async def test_calibrate_dimmer_validation_and_server_registration() -> None:
    gateway = FakeGateway()
    gateway.modules, gateway.devices = _dimmer_devices_fixture()
    await gateway.start()
    session = GatewaySession(f"127.0.0.1:{gateway.port}", sleeper=_instant_sleep)
    try:
        bad_mode = await calibrate_dimmer(session, mode="bogus")
        assert bad_mode.data["ok"] is False

        bad_ch = await calibrate_dimmer(session, mode="status", channel=9)
        assert bad_ch.data["ok"] is False

        bad_video = await calibrate_dimmer(session, mode="analyze", video_path="")
        assert bad_video.data["ok"] is False

        bad_bounds = await calibrate_dimmer(
            session,
            mode="apply",
            device_id="192.0.2.40-1",
            dim_min=70,
            dim_max=70,
        )
        assert bad_bounds.data["ok"] is False

        bad_gamma = await calibrate_dimmer(
            session,
            mode="apply",
            device_id="192.0.2.40-1",
            dim_gamma=4.0,
        )
        assert bad_gamma.data["ok"] is False

        bad_fade = await calibrate_dimmer(
            session,
            mode="apply",
            device_id="192.0.2.40-1",
            default_fade=300,
        )
        assert bad_fade.data["ok"] is False

        server = build_server(session)
        tools = await server.list_tools()
        assert "calibrate_dimmer" in {tool.name for tool in tools}
        prompts = await server.list_prompts()
        assert "dimmer-kalibratie" in {prompt.name for prompt in prompts}
        prompt_res = await server.get_prompt("dimmer-kalibratie", {"kanaal": "bureau"})
        prompt_text = "\n".join(
            getattr(msg.content, "text", str(msg.content)) for msg in prompt_res.messages
        )
        assert "bureau" in prompt_text
        assert "calibrate_dimmer" in prompt_text
        assert "dimmer-kalibratie" in skill_text()
    finally:
        await session.stop()
        await gateway.stop()
