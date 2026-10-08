"""The skill, the tester guide, and the bundle manifest stay free of install data."""

from __future__ import annotations

import importlib.util
import json
import re
import struct
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "toolkit_build",
    Path(__file__).resolve().parents[1] / "scripts" / "build.py",
)
assert _SPEC and _SPEC.loader
_build = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_build)
file_version = _build.file_version
stage = _build.stage
versions_agree = _build.versions_agree

TOOLKIT = Path(__file__).resolve().parents[1]
PRIVATE_IP = re.compile(
    r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|192\.168\.\d{1,3}\.\d{1,3}"
    r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"
)


def _text_files() -> list[Path]:
    skip = {".build", "dist", "__pycache__", ".pytest_cache"}
    found = []
    for path in TOOLKIT.rglob("*"):
        if not path.is_file():
            continue
        if skip.intersection(path.relative_to(TOOLKIT).parts):
            continue
        if path.suffix in {".pyc"}:
            continue
        found.append(path)
    return found


def test_toolkit_sources_have_no_private_addresses() -> None:
    offenders = []
    for path in _text_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        match = PRIVATE_IP.search(text)
        if match:
            offenders.append(f"{path}: {match.group(0)}")
    assert offenders == []


def test_versions_match() -> None:
    versions_agree()
    assert re.fullmatch(r"0\.1\.0-rc\.[1-9]\d*", file_version())
    plugin = json.loads((TOOLKIT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    setting = plugin["userConfig"]["gateway_address"]
    assert setting["required"] is False
    assert setting["default"] == "homeassistant.local"


def test_skill_mentions_the_switch_up_front_and_at_the_end() -> None:
    text = (TOOLKIT / "skills" / "ipbuilding-gateway-tools" / "SKILL.md").read_text(encoding="utf-8")
    assert "Remote debugging and control" in text
    assert "Debuggen en bedienen op afstand" in text
    assert "Instellingen" in text
    assert "blijvende melding" in text
    assert "blijft aan" in text
    assert "Aan het begin" in text
    assert "connection_status" in text
    assert "Aan het eind" in text
    assert "niet pas na een fout" in text
    assert "Nederlands" in text
    assert "not available in this gateway version yet" in text


def test_tester_guide_is_plain_dutch_without_a_terminal() -> None:
    text = (TOOLKIT / "HANDLEIDING.md").read_text(encoding="utf-8")
    assert "Dubbelklik" in text
    assert "homeassistant.local" in text
    assert "Remote debugging and control" in text
    assert "Debuggen en bedienen op afstand" in text
    assert "Een lamp gaat niet uit" in text
    assert "weer uit" in text
    assert "0.1.0-rc.1" in text
    assert "Update" in text
    assert "Install" in text
    assert "IPBuilding Gateway Tools" in text
    assert "ipbuilding-gateway-tools.mcpb" in text
    assert "debug" not in text.lower().replace("remote debugging and control", "").replace("debuggen en bedienen op afstand", "").replace("onder **debug**", "")
    lowered = text.lower()
    for banned in ("git ", "terminal", "pip ", "ssh ", "npm "):
        assert banned not in lowered


def test_staged_manifest_asks_for_the_gateway_address(tmp_path: Path) -> None:
    staged = stage(file_version(), dest=tmp_path / "bundle")
    manifest = json.loads((staged / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == file_version()
    assert manifest["name"] == "ipbuilding-gateway-tools"
    assert manifest["display_name"] == "IPBuilding Gateway Tools"
    assert "debug" not in manifest["name"]
    assert "debug" not in manifest["display_name"].lower()
    assert manifest["server"]["type"] == "uv"
    setting = manifest["user_config"]["gateway_address"]
    assert setting["required"] is False
    assert setting["default"] == "homeassistant.local"
    env = manifest["server"]["mcp_config"]["env"]["IPBUILDING_GATEWAY_ADDRESS"]
    assert env == "${user_config.gateway_address}"
    names = [tool["name"] for tool in manifest["tools"]]
    assert names == [
        "connection_status",
        "gateway_health",
        "list_devices",
        "recent_events",
        "read_logs",
        "discover",
        "device_command",
        "probe_generation",
        "capture_frames",
        "send_raw",
        "decode_test",
        "export_session",
    ]
    assert (staged / "gateway" / "payloads" / "relay.py").is_file()
    assert manifest["icon"] == "icon.png"
    icon = staged / "icon.png"
    addon_icon = TOOLKIT.parent / "ipbuilding_gateway" / "icon.png"
    assert icon.read_bytes() == addon_icon.read_bytes()
    raw = icon.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", raw[16:24])
    assert (width, height) == (512, 512)
