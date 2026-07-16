"""Validate ipbuilding_gateway/config.yaml against Supervisor rules.

The add-on store reads this manifest from the git repository on every
refresh. An invalid ``watchdog`` URL prevents the add-on from appearing
in the store, which surfaces as errors like "App 3059e002_ipbuilding_gateway
does not exist in the store" even though the repository URL is correct.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_CONFIG = Path(__file__).resolve().parent.parent / "ipbuilding_gateway" / "config.yaml"

# supervisor/addons/addon.py — RE_WATCHDOG (2026 supervisor)
RE_WATCHDOG = re.compile(
    r"^(?:(?P<s_prefix>https?|tcp)|\[PROTO:(?P<t_proto>\w+)\])"
    r":\/\/\[HOST\]:(?:\[PORT:)?(?P<t_port>\d+)\]?(?P<s_suffix>.*)$"
)


def _load_config() -> dict:
    return yaml.safe_load(_CONFIG.read_text(encoding="utf-8"))


def _schema_keys(schema: dict, prefix: str = "") -> set[str]:
    """Flatten nested schema keys to dotted paths."""
    keys: set[str] = set()
    for key, value in schema.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            keys.update(_schema_keys(value, path))
        else:
            keys.add(path)
    return keys


def _options_keys(options: dict, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for key, value in options.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            keys.update(_options_keys(value, path))
        else:
            keys.add(path)
    return keys


def test_watchdog_matches_supervisor_regex() -> None:
    """Watchdog must use [PORT:<container-port>], not bare [PORT].

    Official HA docs:
    https://developers.home-assistant.io/docs/apps/configuration#optional-configuration-options
    """
    cfg = _load_config()
    watchdog = cfg["watchdog"]
    assert RE_WATCHDOG.match(watchdog), (
        f"watchdog {watchdog!r} does not match Supervisor RE_WATCHDOG. "
        "Use http://[HOST]:[PORT:8080]/health (internal container port)."
    )
    assert "8080" in watchdog, (
        "watchdog must reference the internal api_port (8080/tcp)."
    )


def test_options_and_schema_keys_match() -> None:
    cfg = _load_config()
    options = _options_keys(cfg.get("options", {}))
    schema = _schema_keys(cfg.get("schema", {}))
    assert options == schema, (
        f"options/schema key mismatch: "
        f"only in options={options - schema}, only in schema={schema - options}"
    )


def test_fieldbus_hub_role_schema() -> None:
    cfg = _load_config()
    assert cfg["schema"]["fieldbus"]["hub_role"] == "list(slave|master)"
    assert cfg["options"]["fieldbus"]["hub_role"] == "slave"


def test_installation_group_is_first() -> None:
    """'Installatie' should be the first group shown in the Configuration UI."""
    cfg = _load_config()
    assert next(iter(cfg["options"])) == "installation"
    assert next(iter(cfg["schema"])) == "installation"


def test_installation_multi_press_schema() -> None:
    cfg = _load_config()
    assert cfg["schema"]["installation"]["multi_press"] == "bool"
    assert cfg["schema"]["installation"]["multi_press_window_ms"] == "int(1,)"
    assert cfg["options"]["installation"]["multi_press"] is False
    assert cfg["options"]["installation"]["multi_press_window_ms"] == 350
    inst = cfg["options"]["installation"]
    assert list(inst.keys()) == [
        "expose_inactive_channels",
        "multi_press",
        "multi_press_window_ms",
        "devices_file",
    ]


def test_hub_ip_removed() -> None:
    """hub_ip was never used for actual UDP binding — removed as misleading."""
    cfg = _load_config()
    assert "hub_ip" not in cfg["options"].get("network", {})
    assert "hub_ip" not in cfg["schema"].get("network", {})


def test_api_port_not_in_gui() -> None:
    """API port is fixed at 8080; documented via native network: port descriptions instead."""
    cfg = _load_config()
    assert "api_port" not in cfg["options"].get("network", {})
    assert "api_port" not in cfg["schema"].get("network", {})


def test_bind_ip_schema() -> None:
    cfg = _load_config()
    assert cfg["schema"]["network"]["bind_ip"] == "str"
    assert cfg["options"]["network"]["bind_ip"] == "0.0.0.0"


def test_translations_present_for_bind_ip() -> None:
    for lang in ("nl", "en"):
        path = _CONFIG.parent / "translations" / f"{lang}.yaml"
        trans = yaml.safe_load(path.read_text(encoding="utf-8"))
        bind = trans["configuration"]["network"]["fields"]["bind_ip"]
        assert bind.get("name")
        assert bind.get("description")


def test_native_network_port_descriptions() -> None:
    """Port descriptions live under the top-level `network:` translation key,
    matching the `ports:` entries in config.yaml — not under our own
    `configuration.network` options group."""
    cfg = _load_config()
    port_keys = set(cfg["ports"].keys())
    for lang in ("nl", "en"):
        path = _CONFIG.parent / "translations" / f"{lang}.yaml"
        trans = yaml.safe_load(path.read_text(encoding="utf-8"))
        network_translations = trans.get("network", {})
        assert set(network_translations.keys()) == port_keys
        for description in network_translations.values():
            assert description


def test_translations_present_for_hub_role() -> None:
    for lang in ("nl", "en"):
        path = _CONFIG.parent / "translations" / f"{lang}.yaml"
        assert path.is_file(), f"missing translation file: {path}"
        trans = yaml.safe_load(path.read_text(encoding="utf-8"))
        hub = trans["configuration"]["fieldbus"]["fields"]["hub_role"]
        assert hub.get("name")
        assert hub.get("description")
        assert "Slave" in hub["description"] or "slave" in hub["description"].lower()


def test_translations_present_for_multi_press() -> None:
    for lang in ("nl", "en"):
        path = _CONFIG.parent / "translations" / f"{lang}.yaml"
        trans = yaml.safe_load(path.read_text(encoding="utf-8"))
        fields = trans["configuration"]["installation"]["fields"]
        for key in ("multi_press", "multi_press_window_ms", "expose_inactive_channels"):
            assert fields[key].get("name")
            assert fields[key].get("description")


def test_required_manifest_fields() -> None:
    cfg = _load_config()
    for key in ("name", "version", "slug", "description", "arch"):
        assert cfg.get(key), f"required config.yaml field missing: {key}"
    assert cfg["slug"] == "ipbuilding_gateway"
    assert "ha_ipbuilding_gateway" in cfg.get("discovery", [])


def test_readme_present_for_supervisor_intro() -> None:
    """HA renders the add-on About/intro from ipbuilding_gateway/README.md."""
    readme = _CONFIG.parent / "README.md"
    assert readme.is_file(), (
        f"{readme} must exist — Supervisor uses it for the add-on info page."
    )
    text = readme.read_text(encoding="utf-8")
    assert "companion" in text.lower()
    assert "my.home-assistant.io/redirect/hacs_repository" in text


def test_icon_png_present() -> None:
    icon = _CONFIG.parent / "icon.png"
    assert icon.is_file(), f"{icon} required for add-on presentation in Supervisor UI."
