"""The skill, the tester guide, and the bundle manifest stay free of install data."""

from __future__ import annotations

import importlib.util
import json
import re
import struct
import zipfile
from pathlib import Path

import pytest

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


def test_plugin_evals_stay_out_of_ci() -> None:
    note = (TOOLKIT / "evals" / "README.md").read_text(encoding="utf-8")
    assert "claude plugin eval" in note
    assert "not part of CI" in note
    cases = [
        path
        for path in (TOOLKIT / "evals").iterdir()
        if path.is_dir() and (path / "prompt.md").is_file()
    ]
    assert 6 <= len(cases) <= 8
    prompts = "\n".join((path / "prompt.md").read_text(encoding="utf-8") for path in cases)
    assert "Hoe wordt het weer morgen?" in prompts
    assert "Lamp Noord" in prompts
    workflow = (TOOLKIT.parent / ".github" / "workflows" / "toolkit.yml").read_text(encoding="utf-8")
    assert "plugin eval" not in workflow
    ignore = (TOOLKIT.parent / ".gitignore").read_text(encoding="utf-8")
    assert "toolkit/evals/results/" in ignore


def test_versions_match() -> None:
    versions_agree()
    assert file_version() == "0.1.2-rc.2"
    plugin = json.loads((TOOLKIT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    setting = plugin["userConfig"]["gateway_address"]
    assert setting["required"] is False
    assert setting["default"] == "homeassistant.local"


def test_download_zips_match_the_upload_formats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = "https://intake.example.test/never-embed"
    monkeypatch.setenv("IPBUILDING_REPORT_INTAKE", sentinel)
    plugin_zip = _build.write_download_zips(file_version(), dest=tmp_path)
    assert list(tmp_path.glob("*skill*")) == []
    skill_text = (TOOLKIT / "skills" / "ipbuilding-gateway-tools" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert skill_text.startswith("---\n")
    fields = _build._folded_frontmatter(skill_text)
    assert fields["name"] == "ipbuilding-gateway-tools"
    assert 1 <= len(fields["description"]) <= 1024
    assert "<" not in fields["description"] and ">" not in fields["description"]
    assert "claude" not in fields["name"] and "anthropic" not in fields["name"]

    with zipfile.ZipFile(plugin_zip) as archive:
        plugin_names = archive.namelist()
        mcp = json.loads(archive.read("ipbuilding-gateway-tools/.mcp.json"))
        plugin = json.loads(archive.read("ipbuilding-gateway-tools/.claude-plugin/plugin.json"))
        marketplace = json.loads(
            archive.read("ipbuilding-gateway-tools/.claude-plugin/marketplace.json")
        )
    assert plugin_names[0].startswith("ipbuilding-gateway-tools/")
    assert {name.split("/", 1)[0] for name in plugin_names} == {"ipbuilding-gateway-tools"}
    for required in (
        "ipbuilding-gateway-tools/.mcp.json",
        "ipbuilding-gateway-tools/.claude-plugin/plugin.json",
        "ipbuilding-gateway-tools/.claude-plugin/marketplace.json",
        "ipbuilding-gateway-tools/skills/ipbuilding-gateway-tools/SKILL.md",
        "ipbuilding-gateway-tools/ipbuilding_debug/__main__.py",
        "ipbuilding-gateway-tools/pyproject.toml",
        "ipbuilding-gateway-tools/VERSION",
    ):
        assert required in plugin_names
    assert plugin["version"] == file_version()
    assert marketplace["plugins"] == [
        {
            "name": "ipbuilding-gateway-tools",
            "source": "./",
            "description": plugin["description"],
        }
    ]
    env = mcp["mcpServers"]["ipbuilding-gateway-tools"]["env"]
    assert list(env) == ["IPBUILDING_GATEWAY_ADDRESS"]
    assert sentinel.encode() not in plugin_zip.read_bytes()


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
    assert "toolkit_version" in text
    assert "DIM 100" in text
    assert "Zag je het traag reageren?" in text
    assert "Home Assistant integration" not in (
        TOOLKIT / "ipbuilding_debug" / "server.py"
    ).read_text(encoding="utf-8")


def test_tester_guide_is_plain_dutch_without_a_terminal() -> None:
    text = (TOOLKIT / "HANDLEIDING.md").read_text(encoding="utf-8")
    approved = text[text.index("## IPBuilding Gateway Tools") :]
    assert approved.startswith("## IPBuilding Gateway Tools\n")
    assert "te debuggen" in approved
    assert "Zet de lamp in de keuken aan en controleer of de module dat bevestigt." in approved
    assert "testpakketjes sturen" in approved
    assert text.startswith(
        "IPBuilding Gateway Tools zijn hulpmiddelen voor AI-assistenten zoals Claude:"
    )
    assert "dubbelklik" in text
    assert "homeassistant.local" in text
    assert "Remote control (for debugging)" in text
    assert "Bediening op afstand (voor debuggen)" in text
    assert "Remote debugging and control" not in text
    assert "Debuggen en bedienen op afstand" not in text
    assert "debug-toolkit" not in text.lower()
    assert "weer uit" in text
    assert "IPBuilding Gateway 1.8.0" in text
    assert "Voor ontwikkelaars (Claude Code)" in text
    assert (
        "claude plugin install ipbuilding-gateway-tools --marketplace ./ipbuilding-gateway-tools"
        in text
    )
    assert (
        "claude plugin install ipbuilding-gateway-tools --marketplace markminnoye/IPBuilding-Gateway"
        in text
    )
    assert "~/.claude/skills/" not in text
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
    assert "~/.claude/skills/" not in readme
    assert (
        "claude plugin install ipbuilding-gateway-tools --marketplace ./ipbuilding-gateway-tools"
        in readme
    )
    assert (
        "claude plugin install ipbuilding-gateway-tools --marketplace markminnoye/IPBuilding-Gateway"
        in readme
    )
    plugin = json.loads((TOOLKIT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    root_market = json.loads(
        (TOOLKIT.parent / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )
    assert root_market["owner"]["name"] == "Sonic Rocket"
    assert root_market["description"].startswith(
        "IPBuilding Gateway Tools zijn hulpmiddelen voor AI-assistenten zoals Claude"
    )
    assert root_market["plugins"] == [
        {
            "name": "ipbuilding-gateway-tools",
            "source": "./toolkit",
            "description": plugin["description"],
        }
    ]


def _load_staged_version(path: Path, name: str) -> str:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.__version__


def test_staged_bundle_reports_the_real_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("IPBUILDING_REPORT_INTAKE", raising=False)
    monkeypatch.delenv("IPBUILDING_REPORT_SEND", raising=False)
    staged = stage(file_version(), dest=tmp_path / "bundle")
    assert (staged / "VERSION").read_text(encoding="utf-8").strip() == file_version()
    loaded = _load_staged_version(staged / "ipbuilding_debug" / "version.py", "staged_version_file")
    assert loaded == file_version()
    assert loaded != "0.0.0"
    (staged / "VERSION").unlink()
    from_manifest = _load_staged_version(
        staged / "ipbuilding_debug" / "version.py",
        "staged_version_manifest",
    )
    assert from_manifest == file_version()
    assert from_manifest != "0.0.0"


def test_staged_manifest_asks_for_the_gateway_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("IPBUILDING_REPORT_INTAKE", raising=False)
    monkeypatch.delenv("IPBUILDING_REPORT_SEND", raising=False)
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
        "send_report",
    ]
    assert "IPBUILDING_REPORT_INTAKE" not in manifest["server"]["mcp_config"]["env"]
    assert (staged / "gateway" / "payloads" / "relay.py").is_file()
    description = manifest["long_description"]
    expected = (
        "IPBuilding Gateway Tools zijn hulpmiddelen voor AI-assistenten zoals Claude. "
        "Ze helpen je samen met een assistent problemen in je IPBuilding-installatie te vinden. "
        "Wat jullie vinden, kun je als rapport naar Sonic Rocket sturen.\n"
        "\n"
        "Persoonsgegevens, zoals adressen en namen van lampen en ruimtes, "
        "worden standaard weggefilterd uit het rapport.\n"
        "\n"
        'Om mee te kijken zet je in de gateway "Bediening op afstand (voor debuggen)" aan. '
        "Als je klaar bent, zet je het weer uit."
    )
    assert description == expected
    assert len(description) <= 800
    lowered = description.lower()
    assert "add-on" not in lowered
    assert "handleiding" not in lowered
    assert "dubbelklik" not in lowered
    assert ".mcpb" not in lowered
    assert "download" not in lowered
    assert "persoonsgegevens" in lowered
    assert "weggefilterd" in lowered
    assert "uit het rapport" in lowered
    assert "sonic rocket" in lowered
    for technical in ("websocket", "capability", "udp", "payload", "mdns"):
        assert technical not in lowered
    assert manifest["description"] == "Hulpmiddelen voor AI-assistenten zoals Claude."
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
