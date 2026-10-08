"""Report template, privacy notice, and the mailto draft."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path

import pytest

from ipbuilding_debug.installation_id import installation_id
from ipbuilding_debug.privacy import (
    CONTACT_ADDRESS,
    FEEDBACK_WARNING,
    RETENTION,
    privacy_notice,
)
from ipbuilding_debug.redact import mask_stem, name_masks, redact_text
from ipbuilding_debug.report import parse_mailto, report_send_enabled
from ipbuilding_debug.server import build_server
from ipbuilding_debug.session import GatewaySession
from ipbuilding_debug.tools import (
    capture_frames,
    connection_status,
    decode_test,
    export_session,
    send_report,
)
from fake_gateway import FakeGateway
from test_package import TOOLKIT, file_version, stage

_EMAIL = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)
_ALLOWED_EMAILS = {CONTACT_ADDRESS}
_SKIP_PARTS = {".git", "__pycache__", ".build", "dist", ".pytest_cache"}


def test_privacy_notice_has_retention_and_contact_and_no_statement() -> None:
    notice = privacy_notice()
    assert RETENTION in notice
    assert "volledige ticket verwijderd" in notice
    assert "e-mailadres verwijderd" not in notice
    assert CONTACT_ADDRESS in notice
    assert "[NOG TE BEVESTIGEN]" not in notice
    assert "http" not in notice.lower()
    assert "privacyverklaring" not in notice.lower()
    assert "T" + "riage" not in notice


def test_installation_id_is_a_stable_random_uuid4(
    installation_id_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("IPBUILDING_INSTALLATION_ID_FILE", str(installation_id_file))
    first = installation_id()
    second = installation_id()
    assert first == second
    parsed = uuid.UUID(first)
    assert parsed.version == 4
    installation_id_file.write_text("aa:bb:cc:dd:ee:ff\n", encoding="utf-8")
    fresh = installation_id()
    assert fresh != first
    assert uuid.UUID(fresh).version == 4
    assert "aabbccddeeff" not in fresh.replace("-", "")
    other = installation_id_file.parent / "other-id"
    monkeypatch.setenv("IPBUILDING_INSTALLATION_ID_FILE", str(other))
    assert installation_id() != fresh


@pytest.mark.asyncio
async def test_export_report_splits_evidence_and_redacts_free_text() -> None:
    session = GatewaySession("192.0.2.10:9", backoff_start=30, backoff_max=30)
    session.status = {
        "version": "1.8.0-dev.10",
        "hub_role": "master",
        "remote_debugging": True,
        "capabilities": ["udp_frame", "log_stream"],
        "instance_id": "11111111-1111-1111-1111-111111111111",
    }
    session.modules = {
        "mod-1": {
            "id": "mod-1",
            "type": "relay",
            "model": "IP0200PoE",
            "name": "keukenlamp",
        }
    }
    await session.buffer.append(
        {
            "type": "udp_frame",
            "direction": "rx",
            "hex": "5330303030",
            "src": "192.0.2.10",
            "dst": "192.0.2.20",
        }
    )
    await session.buffer.append(
        {"type": "button_event", "message": "knop-alleen-vermoeden"}
    )
    await session.buffer.append(
        {"type": "gap", "message": "onderbreking-open-vraag"}
    )
    note = (
        "192.0.2.55 2001:db8::1 aa:bb:cc:dd:ee:ff tester@example.invalid"
    )
    hidden = await export_session(session, note=note)
    report = hidden.data["report"]
    assert report.startswith(FEEDBACK_WARNING)
    for heading in (
        "1. Samenvatting",
        "2. Omgeving",
        "3. Wat getest werd",
        "4. Bevindingen",
        "5. Open vragen",
        "6. Feedback over de tool",
        "7. Bijlage",
    ):
        assert heading in report
    confirmed = report.split("Bevestigd", 1)[1].split("Vermoeden", 1)[0]
    suspected = report.split("Vermoeden", 1)[1].split("5. Open vragen", 1)[0]
    tested = report.split("3. Wat getest werd", 1)[1].split("4. Bevindingen", 1)[0]
    assert "5330303030" in confirmed
    assert "knop-alleen-vermoeden" not in confirmed
    assert "knop-alleen-vermoeden" in suspected
    assert "5330303030" not in suspected
    assert "local_time" not in tested
    assert re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", tested)
    assert "onderbreking-open-vraag" in report.split("5. Open vragen", 1)[1]
    assert "[adres]" in report
    assert "[mac]" in report
    assert "[e-mail]" in report
    assert "192.0.2.55" not in report
    assert "2001:db8::1" not in report
    assert "aa:bb:cc:dd:ee:ff" not in report
    assert "tester@example.invalid" not in report
    assert "keukenlamp" not in report
    assert "IP0200PoE" in report
    assert "11111111-1111-1111-1111-111111111111" not in report
    stored = installation_id()
    assert hidden.data["installatie_id"] == stored
    assert f"installatie_id: {stored}" in hidden.data["frontmatter"]
    assert hidden.data["frontmatter"].splitlines()[0] == "---"

    raw_session = GatewaySession("192.0.2.10:9", backoff_start=30, backoff_max=30)
    shown = await export_session(raw_session, note=note, redact=False)
    assert "192.0.2.55" in shown.data["report"]
    assert "tester@example.invalid" in shown.data["report"]
    assert "aa:bb:cc:dd:ee:ff" in shown.data["report"]


@pytest.mark.asyncio
async def test_send_report_waits_for_confirmation_and_never_sends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("IPBUILDING_REPORT_SEND", raising=False)
    monkeypatch.delenv("IPBUILDING_REPORT_INTAKE", raising=False)
    assert report_send_enabled() is True
    session = GatewaySession("127.0.0.1:9", backoff_start=30, backoff_max=30)
    missing = await send_report(session, korte_fout="lamp uit")
    assert missing.data["mailto"] is None
    assert "mailto:" not in missing.message
    assert "niet beschikbaar" in missing.message

    monkeypatch.setenv("IPBUILDING_REPORT_INTAKE", "intake@example.invalid")
    preview = await send_report(session, confirmed=False, korte_fout="lamp uit")
    assert RETENTION in preview.message
    assert CONTACT_ADDRESS in preview.message
    assert FEEDBACK_WARNING in preview.message
    assert preview.data["mailto"] is None
    assert "mailto:" not in preview.message
    assert "Bevestig" in preview.message

    sent = await send_report(session, confirmed=True, korte_fout="lamp uit")
    assert sent.data["sent"] is False
    link = sent.data["mailto"]
    parsed = parse_mailto(link)
    assert parsed["address"] == "intake@example.invalid"
    assert parsed["subject"].startswith(f"[DEBUG] {installation_id()} | lamp uit | ")
    assert re.search(r"\d{4}-\d{2}-\d{2}T", parsed["subject"])
    assert parsed["body"].startswith(FEEDBACK_WARNING)
    for key in (
        "Samenvatting:",
        "Omgeving:",
        "Wat getest werd:",
        "Bevestigd:",
        "Vermoeden:",
        "Open vragen:",
        "Feedback over de tool:",
        "Bijlage:",
        "installatie_id:",
    ):
        assert key in parsed["body"]
    assert CONTACT_ADDRESS not in parsed["body"]
    assert "niet verstuurd" in sent.message
    assert "geen bevestiging" in sent.message
    assert "intake@example.invalid" not in sent.message.split("mailto:", 1)[0]

    monkeypatch.setenv("IPBUILDING_REPORT_SEND", "0")
    assert report_send_enabled() is False
    disabled = await send_report(session, confirmed=True, korte_fout="lamp uit")
    assert disabled.data["mailto"] is None
    assert "mailto:" not in disabled.message
    assert "intake@example.invalid" not in disabled.message
    assert "staat uit" in disabled.message


@pytest.mark.asyncio
async def test_send_report_tool_follows_the_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IPBUILDING_REPORT_SEND", raising=False)
    session = GatewaySession("127.0.0.1:9", backoff_start=30, backoff_max=30)
    try:
        enabled = build_server(session)
        names = [tool.name for tool in await enabled.list_tools()]
        assert "send_report" in names
        monkeypatch.setenv("IPBUILDING_REPORT_SEND", "off")
        disabled = build_server(session)
        hidden = [tool.name for tool in await disabled.list_tools()]
        assert "send_report" not in hidden
    finally:
        await session.stop()


@pytest.mark.asyncio
async def test_connection_status_says_when_the_log_level_is_unknown() -> None:
    gateway = FakeGateway(remote_debugging=True, capabilities=["log_stream"])
    await gateway.start()
    session = GatewaySession(f"127.0.0.1:{gateway.port}", backoff_start=0.05)
    try:
        result = await connection_status(session)
    finally:
        await session.stop()
        await gateway.stop()
    assert "Het actuele logniveau en de terugvaltijd zijn niet gemeld." in result.message
    assert "Logniveau is nu" not in result.message
    assert not any(item.get("type") == "set_log_level" for item in gateway.received)


@pytest.mark.asyncio
async def test_second_capture_includes_the_pause_and_skips_old_frames() -> None:
    gateway = FakeGateway(remote_debugging=True, capabilities=["udp_frame"])
    gateway.frame_on_subscribe = {
        "type": "udp_frame",
        "direction": "rx",
        "hex": "5330303030",
        "src": "module",
        "dst": "gateway",
        "port": 1001,
    }
    await gateway.start()
    session = GatewaySession(f"127.0.0.1:{gateway.port}", backoff_start=0.05)
    try:
        await session.ensure_started()
        assert await session.wait_until_connected(3)
        await session.buffer.append(
            {
                "type": "udp_frame",
                "direction": "rx",
                "hex": "00",
                "src": "old",
                "dst": "gateway",
                "port": 1001,
            }
        )
        first = await capture_frames(session, seconds=5, direction="rx", limit=1)
        gateway.frame_on_subscribe = None
        await session.buffer.append(
            {
                "type": "udp_frame",
                "direction": "rx",
                "hex": "4330303030",
                "src": "module",
                "dst": "gateway",
                "port": 1001,
            }
        )
        second = await capture_frames(session, seconds=0.2, direction="rx", limit=1)
    finally:
        await session.stop()
        await gateway.stop()
    assert first.data["continued"] is False
    assert [frame["hex"] for frame in first.data["frames"]] == ["5330303030"]
    assert second.data["continued"] is True
    assert "4330303030" in [frame["hex"] for frame in second.data["frames"]]
    assert "5330303030" not in [frame["hex"] for frame in second.data["frames"]]
    assert "00" not in [frame["hex"] for frame in second.data["frames"]]
    assert "verder waar de vorige stopte" in second.message


def test_decode_test_names_a_relay_without_a_dialect_and_a_total_miss() -> None:
    matched = decode_test("S0000")
    assert matched.data["matched"] is True
    assert matched.data["matches"][0]["decoder"] == "relay"
    assert "geen dialect-id" in matched.message
    assert "Kessel-Lo" in matched.message
    assert "Torhout" in matched.message
    missed = decode_test("I0100")
    assert missed.data["matched"] is False
    assert "Geen enkele decoder herkent dit frame." in missed.message
    assert "dialect-id" not in missed.message
    # Channel 0 of the relay poll is the same five bytes as the input poll.
    collision = decode_test("I0000")
    assert collision.data["matched"] is True
    assert collision.data["matches"][0]["decoder"] == "input"
    assert "geen dialect-id" not in collision.message


def test_name_masks_keep_the_first_character_and_number_collisions() -> None:
    assert mask_stem("Traphal") == "Txxxxxx"
    assert mask_stem("Kamer links") == "K" + ("x" * 10)
    assert name_masks(["Traphal"], "Traphal") == {"Traphal": "Txxxxxx"}
    ordered = name_masks(["Traphek", "Traphal"], "Traphal komt voor Traphek")
    assert ordered == {"Traphal": "Txxxxxx-1", "Traphek": "Txxxxxx-2"}
    parked = name_masks(["Traphek", "Traphal"], "")
    assert parked == {"Traphek": "Txxxxxx-1", "Traphal": "Txxxxxx-2"}
    assert name_masks(["Traphal", "traphal", "TRAPHAL"], "traphal") == {"Traphal": "Txxxxxx"}
    room = "K" + ("x" * 10)
    text = "TRAPHAL en traphal en Traphallamp en traphallamp en kamer links en Kamer linksom"
    masked = redact_text(text, masks={"Traphal": "Txxxxxx", "Kamer links": room})
    assert masked == f"Txxxxxx en Txxxxxx en Traphallamp en traphallamp en {room} en Kamer linksom"


@pytest.mark.asyncio
async def test_report_masks_room_lamp_and_button_names() -> None:
    session = GatewaySession("127.0.0.1:9", backoff_start=30, backoff_max=30)
    session.devices = {
        "dev-hek": {
            "id": "dev-hek",
            "name": "Traphek",
            "room": "Kamer links",
            "device_type": "relay",
        },
        "dev-hal": {
            "id": "dev-hal",
            "name": "Traphal",
            "room": "Kamer links",
            "device_type": "relay",
        },
        "dev-knop": {
            "id": "dev-knop",
            "name": "Knop hal",
            "room": "Bijkeuken",
            "device_type": "input",
        },
    }
    session.modules = {
        "mod-1": {"id": "mod-1", "type": "input", "model": "IP1100PoE", "name": "Meterkast"}
    }
    await session.buffer.append(
        {
            "type": "button_event",
            "name": "knop hal",
            "room": "kamer links",
            "message": "Knop hal ingedrukt",
        }
    )
    await session.buffer.append(
        {
            "type": "log",
            "ts": "2026-07-02T03:04:05Z",
            "level": "info",
            "logger": "gw",
            "message": "log: traphal en TRAPHAL",
        }
    )
    note = (
        "1. traphal\n"
        "TRAPHAL komt voor traphek. kamer links blijft donker en knop hal ook. "
        "bijkeuken en meterkast blijven buiten de test. "
        "Traphallamp en Kamer linksom blijven. "
        "zag 2001:db8::9"
    )
    hidden = await export_session(session, note=note)
    report = hidden.data["report"]
    assert "Txxxxxx-1" in report
    assert "Txxxxxx-2" in report
    assert "K" + ("x" * 10) in report
    assert re.search(r"(?<![A-Za-z0-9])Kxxxxxxx(?!x)", report)
    assert "Mxxxxxxxx" in report
    assert "Bxxxxxxxx" in report
    for secret in ("Traphal", "Traphek", "Kamer links", "Knop hal", "Meterkast", "Bijkeuken"):
        assert re.search(
            rf"(?<![A-Za-z0-9_-]){re.escape(secret)}(?![A-Za-z0-9_-])",
            report,
        ) is None
    assert "2001:db8" not in report
    assert re.search(r"(?<![A-Za-z0-9_-])traphal(?![A-Za-z0-9_-])", report, re.IGNORECASE) is None
    assert "Traphallamp" in report
    assert "Kamer linksom" in report
    assert "[naam]" not in report
    logs = [event for event in hidden.data["events"] if event.get("type") == "log"]
    assert logs[0]["message"] == "log: Txxxxxx-1 en Txxxxxx-1"
    assert "1. Samenvatting" in report
    assert "6. Feedback over de tool" in report
    assert hidden.message.startswith(report)
    assert "gemaskeerd" in hidden.data["sharing"]
    buttons = [event for event in hidden.data["events"] if event.get("type") == "button_event"]
    assert buttons[0]["name"] == "Kxxxxxxx"
    assert buttons[0]["room"] == "K" + ("x" * 10)
    assert "txxxxxx" not in report
    assert hidden.data["modules"][0]["name"] == "Mxxxxxxxx"
    assert "dev-hal" not in report
    raw = await export_session(session, redact=False)
    assert "Traphal" in raw.data["report"]
    assert "Kamer links" in raw.data["report"]
    assert raw.data["redacted"] is False


@pytest.mark.asyncio
async def test_report_subject_uses_the_same_name_masks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("IPBUILDING_REPORT_SEND", raising=False)
    monkeypatch.setenv("IPBUILDING_REPORT_INTAKE", "intake@example.invalid")
    session = GatewaySession("127.0.0.1:9", backoff_start=30, backoff_max=30)
    session.devices = {
        "dev-hek": {"id": "dev-hek", "name": "Traphek", "room": "Hal", "device_type": "relay"},
        "dev-hal": {"id": "dev-hal", "name": "Traphal", "room": "Hal", "device_type": "relay"},
    }
    await session.annotate("Traphal komt voor Traphek")
    sent = await send_report(session, confirmed=True, korte_fout="Traphal en Traphek")
    parsed = parse_mailto(sent.data["mailto"])
    assert "Traphal" not in parsed["subject"]
    assert "Traphek" not in parsed["subject"]
    assert "Txxxxxx-1 en Txxxxxx-2" in parsed["subject"]
    assert "masks" not in sent.data
    assert "Traphal" not in sent.message


@pytest.mark.asyncio
async def test_report_times_are_local_and_the_template_is_complete() -> None:
    previous = os.environ.get("TZ")
    os.environ["TZ"] = "Europe/Brussels"
    time.tzset()
    try:
        session = GatewaySession("127.0.0.1:9", backoff_start=30, backoff_max=30)
        await session.buffer.append(
            {
                "type": "log",
                "ts": "2026-07-02T03:04:05Z",
                "level": "info",
                "logger": "gw",
                "message": "geen verbinding van 2026-07-02T03:04:05Z tot 2026-07-02T03:04:20Z",
            }
        )
        result = await export_session(session, note="lamp bleef aan")
    finally:
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
        time.tzset()
    report = result.data["report"]
    assert "2026-07-02T05:04:05+02:00" in report
    assert not re.search(r"\d{2}:\d{2}:\d{2}Z", report)
    for heading in (
        "1. Samenvatting",
        "2. Omgeving",
        "3. Wat getest werd",
        "4. Bevindingen",
        "5. Open vragen",
        "6. Feedback over de tool",
        "7. Bijlage",
    ):
        assert heading in report
    assert report.splitlines()[0] == FEEDBACK_WARNING
    assert report.splitlines()[2] == "---"
    assert "installatie_id:" in result.data["frontmatter"]
    assert result.message.startswith(report)


def test_skill_describes_the_report_and_the_backlog() -> None:
    text = (TOOLKIT / "skills" / "ipbuilding-gateway-tools" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "niet verdacht" in text
    assert "Bevestigd" in text
    assert "Vermoeden" in text
    assert FEEDBACK_WARNING in text
    assert "Gmail" in text
    assert "Outlook" in text
    assert "mailto" in text
    assert "confirmed=true" in text
    assert "Linear-backlog" in text
    assert "Agent" in text
    assert "letterlijk" in text
    assert "Txxxxxx" in text
    assert "Txxxxxx-1" in text
    assert "hoofdletterongevoelig" in text
    assert "spelling in de inventaris" in text
    assert "Toegang op afstand" in text
    assert "Debuggen en bedienen op afstand" not in text
    assert "onder Debug" not in text
    assert "T" + "riage" not in text
    readme = (TOOLKIT / "README.md").read_text(encoding="utf-8")
    guide = (TOOLKIT / "HANDLEIDING.md").read_text(encoding="utf-8")
    assert readme.startswith(guide)
    for blob in (text, readme, guide, privacy_notice()):
        assert "T" + "riage" not in blob


def test_default_tree_has_no_intake_address() -> None:
    roots = [TOOLKIT, TOOLKIT.parent / ".github" / "workflows"]
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".md", ".yml", ".yaml", ".json", ".toml"}:
                continue
            if _SKIP_PARTS.intersection(path.parts):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for found in _EMAIL.findall(text):
                assert found in _ALLOWED_EMAILS or found.endswith(".invalid"), found


def test_stage_embeds_the_intake_address_only_when_sending_is_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("IPBUILDING_REPORT_SEND", raising=False)
    monkeypatch.setenv("IPBUILDING_REPORT_INTAKE", "intake@example.invalid")
    staged = stage(file_version(), dest=tmp_path / "with-intake")
    manifest = json.loads((staged / "manifest.json").read_text(encoding="utf-8"))
    env = manifest["server"]["mcp_config"]["env"]
    assert env["IPBUILDING_REPORT_INTAKE"] == "intake@example.invalid"
    assert "send_report" in [tool["name"] for tool in manifest["tools"]]

    monkeypatch.setenv("IPBUILDING_REPORT_SEND", "off")
    quiet = stage(file_version(), dest=tmp_path / "flag-off")
    hidden = json.loads((quiet / "manifest.json").read_text(encoding="utf-8"))
    assert "IPBUILDING_REPORT_INTAKE" not in hidden["server"]["mcp_config"]["env"]
    assert "send_report" not in [tool["name"] for tool in hidden["tools"]]
