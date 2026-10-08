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
    assert "Remote control (for debugging)" in text
    assert "Bediening op afstand (voor debuggen)" in text
    assert "Remote debugging and control" not in text
    assert "Debuggen en bedienen op afstand" not in text
    assert "debug-toolkit" not in text.lower()
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
    approved = text[text.index("## IPBuilding Gateway Tools") :]
    assert approved.startswith("## IPBuilding Gateway Tools\n")
    assert "te debuggen" in approved
    assert "Zet de lamp in de keuken aan en controleer of de module dat bevestigt." in approved
    assert "testpakketjes sturen" in approved
    assert text.startswith("## Installeren\n")
    assert "Dubbelklik" in text
    assert "homeassistant.local" in text
    assert "Remote control (for debugging)" in text
    assert "Bediening op afstand (voor debuggen)" in text
    assert "Remote debugging and control" not in text
    assert "Debuggen en bedienen op afstand" not in text
    assert "debug-toolkit" not in text.lower()
    assert "weer uit" in text
    assert "1.8.0-dev.5" in text
    assert "Update" in text
    assert "Install" in text
    assert "IPBuilding Gateway Tools" in text
    assert "ipbuilding-gateway-tools.mcpb" in text
    lowered_for_debug = text.lower()
    for allowed in (
        "remote control (for debugging)",
        "bediening op afstand (voor debuggen)",
        "te debuggen",
        "onder debug",
    ):
        lowered_for_debug = lowered_for_debug.replace(allowed, "")
    assert "debug" not in lowered_for_debug
    assert "volstaat meestal" in text
    assert "niet bereikbaar" in text.lower()
    assert "meelezen" in text
    lowered = text.lower()
    for banned in ("git ", "terminal", "pip ", "ssh ", "npm "):
        assert banned not in lowered
    readme = (TOOLKIT / "README.md").read_text(encoding="utf-8")
    assert readme.startswith(text)


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
    description = manifest["long_description"]
    expected = (
        "IPBuilding Gateway Tools helpt je samen met een assistent problemen in je IPBuilding-installatie op te sporen. "
        "Wat jullie vinden, kun je als rapport naar ons sturen, zodat we de gateway kunnen verbeteren.\n"
        "\n"
        "De tool werkt met de IPBuilding Gateway in je eigen netwerk. "
        'Om mee te kijken zet je in de gateway "Bediening op afstand (voor debuggen)" aan. '
        "Als het debuggen klaar is, zet je het weer uit.\n"
        "\n"
        "Persoonsgegevens, zoals adressen en namen van lampen en ruimtes, "
        "worden standaard weggefilterd uit het rapport dat je naar ons stuurt."
    )
    assert description == expected
    assert len(description) <= 800
    lowered = description.lower()
    assert "add-on" not in lowered
    assert "handleiding" not in lowered
    assert "eigen netwerk" in lowered
    assert "persoonsgegevens" in lowered
    assert "weggefilterd" in lowered
    assert "uit het rapport dat je naar ons stuurt" in lowered
    for technical in ("websocket", "capability", "udp", "payload", "mdns"):
        assert technical not in lowered
    assert manifest["description"] == (
        "Meekijken en testen via de IPBuilding Gateway in je thuisnetwerk."
    )
    plugin = json.loads((TOOLKIT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert plugin["description"] == expected.split(". ")[0] + "."
    assert "add-on" not in plugin["description"].lower()
    blob = json.dumps(manifest)
    assert "debug-toolkit" not in blob.lower()
    assert "Remote debugging and control" not in blob
    readme = (TOOLKIT / "README.md").read_text(encoding="utf-8")
    assert "debug-toolkit" not in readme.lower()
    assert "Remote debugging and control" not in readme
    assert "Remote control (for debugging)" in readme
    assert "Bediening op afstand (voor debuggen)" in readme
    assert manifest["icon"] == "icon.png"
    icon = staged / "icon.png"
    addon_icon = TOOLKIT.parent / "ipbuilding_gateway" / "icon.png"
    assert icon.read_bytes() == addon_icon.read_bytes()
    raw = icon.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", raw[16:24])
    assert (width, height) == (512, 512)
