"""Dimmer read-back, logged test packets, saved reports, and record-until-done."""

from __future__ import annotations

from pathlib import Path

import pytest

import ipbuilding_debug.tools as tools
from ipbuilding_debug.session import GatewaySession
from ipbuilding_debug.tools import capture_frames, device_command, export_session, send_raw
from fake_gateway import FakeGateway

DIMMER_IP = "192.0.2.42"


def _hex(text: str) -> str:
    return text.encode("ascii").hex()


def _dimmer_gateway(capabilities: list[str]) -> FakeGateway:
    gateway = FakeGateway(remote_debugging=True, capabilities=capabilities)
    gateway.devices = [
        {
            "id": f"{DIMMER_IP}-1",
            "device_type": "dimmer",
            "name": "Lamp Zuid",
            "module_id": DIMMER_IP,
            "channel": 1,
        }
    ]
    gateway.modules = [
        {"id": DIMMER_IP, "type": "dimmer", "model": "IP0300PoE", "name": "dimmer"}
    ]
    # Torhout dimmers echo the command; the gateway reports that as confirmed.
    gateway.command_body = {
        "ok": True,
        "module_confirmed": True,
        "confirm_ms": 13,
        "reported": {"level_percent": 50},
    }
    return gateway


@pytest.fixture(autouse=True)
def no_readback_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools, "READBACK_DELAY_S", 0)


async def _dim(gateway: FakeGateway, **kwargs):
    await gateway.start()
    session = GatewaySession(f"127.0.0.1:{gateway.port}", backoff_start=0.05)
    try:
        result = await device_command(
            session, device_id=f"{DIMMER_IP}-1", action="DIM", value=50, confirmed=True, **kwargs
        )
        events = session.buffer.snapshot()
    finally:
        await session.stop()
        await gateway.stop()
    return result, events


@pytest.mark.asyncio
async def test_readback_flags_an_echo_that_was_not_carried_out() -> None:
    gateway = _dimmer_gateway(["raw_send"])
    gateway.replies = [{"hex": _hex("I0115199"), "delay_ms": 13}]
    result, events = await _dim(gateway)
    assert [call["payload_hex"] for call in gateway.raw_calls] == [_hex("I1000000")]
    assert gateway.raw_calls[0]["module_ip"] == DIMMER_IP
    readback = result.data["readback"]
    assert readback["answered"] is True
    assert readback["level_percent"] == 100
    assert readback["matches_request"] is False
    assert readback["dialect_id"] == "dimmer.torhout.status_reply"
    assert "niet uitgevoerd" in result.message
    assert "Torhout" in result.message
    recorded = [event for event in events if event.get("type") == "command_result"]
    assert len(recorded) == 1
    assert "nagelezen 100%" in recorded[0]["message"]
    assert "WIJKT AF" in recorded[0]["message"]


@pytest.mark.asyncio
async def test_readback_that_matches_still_asks_what_the_lamp_does() -> None:
    gateway = _dimmer_gateway(["raw_send"])
    gateway.replies = [{"hex": _hex("I0154150"), "delay_ms": 10}]
    result, _ = await _dim(gateway)
    readback = result.data["readback"]
    assert readback["matches_request"] is True
    assert readback["level_percent"] == 50
    assert "Torhout" not in result.message
    assert "Vraag de tester" in result.message


@pytest.mark.asyncio
async def test_readback_can_be_turned_off_and_needs_raw_send() -> None:
    off_gateway = _dimmer_gateway(["raw_send"])
    off, _ = await _dim(off_gateway, verify=False)
    assert off_gateway.raw_calls == []
    assert off.data["readback"] is None

    missing_gateway = _dimmer_gateway([])
    missing, _ = await _dim(missing_gateway)
    assert missing_gateway.raw_calls == []
    assert missing.data["readback"]["available"] is False
    assert "Nalezen van de stand lukte niet" in missing.message


@pytest.mark.asyncio
async def test_readback_without_an_answer_says_so() -> None:
    gateway = _dimmer_gateway(["raw_send"])
    gateway.replies = []
    result, _ = await _dim(gateway)
    assert result.data["readback"]["answered"] is False
    assert "geen stand terug" in result.message


@pytest.mark.asyncio
async def test_send_raw_is_logged_and_lands_in_the_saved_report(report_dir: Path) -> None:
    gateway = FakeGateway(remote_debugging=True, capabilities=["raw_send"])
    gateway.replies = [{"hex": _hex("S1501030"), "delay_ms": 13}]
    await gateway.start()
    session = GatewaySession(f"127.0.0.1:{gateway.port}", backoff_start=0.05)
    try:
        await send_raw(
            session, module_ip=DIMMER_IP, payload_hex=_hex("S1501030"), confirmed=True
        )
        exported = await export_session(session, note="dimmertest")
        raw_export = await export_session(session, redact=False)
    finally:
        await session.stop()
        await gateway.stop()
    logged = [
        event for event in session.buffer.snapshot() if event.get("type") == "raw_send_result"
    ]
    assert len(logged) == 1
    assert "testpakket S1501030" in logged[0]["message"]
    report = exported.data["report"]
    tested = report.split("3. Wat getest werd", 1)[1].split("4. Bevindingen", 1)[0]
    assert "testpakket S1501030" in tested
    assert DIMMER_IP not in report
    path = Path(exported.data["file_path"])
    assert path.parent == report_dir
    assert path.read_text(encoding="utf-8") == report
    assert "ongewijzigd" in exported.message
    # A raw local report is never written to disk.
    assert raw_export.data["file_path"] == ""
    assert len(list(report_dir.iterdir())) == 1


@pytest.mark.asyncio
async def test_capture_until_done_returns_what_arrived_and_skips_polls() -> None:
    gateway = FakeGateway(remote_debugging=True, capabilities=["udp_frame"])
    await gateway.start()
    session = GatewaySession(f"127.0.0.1:{gateway.port}", backoff_start=0.05)
    try:
        await session.ensure_started()
        assert await session.wait_until_connected(3)
        start = await capture_frames(session, seconds=0)
        for text in ("I0115000", "D1001003"):
            await session.buffer.append(
                {
                    "type": "udp_frame",
                    "direction": "rx",
                    "hex": _hex(text),
                    "src": DIMMER_IP,
                    "dst": "gateway",
                    "port": 1001,
                }
            )
        done = await capture_frames(session, seconds=0)
    finally:
        await session.stop()
        await gateway.stop()
    assert start.data["ok"] is True
    assert start.data["continued"] is False
    assert "zodra hij klaar zegt" in start.message
    assert done.data["continued"] is True
    assert [frame["hex"] for frame in done.data["frames"]] == [_hex("D1001003")]
    assert done.data["polls_skipped"] == 1
    assert "routinepoll" in done.message
