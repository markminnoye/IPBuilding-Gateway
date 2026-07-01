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
    options = set(cfg.get("options", {}).keys())
    schema = set(cfg.get("schema", {}).keys())
    assert options == schema, (
        f"options/schema key mismatch: "
        f"only in options={options - schema}, only in schema={schema - options}"
    )


def test_required_manifest_fields() -> None:
    cfg = _load_config()
    for key in ("name", "version", "slug", "description", "arch"):
        assert cfg.get(key), f"required config.yaml field missing: {key}"
    assert cfg["slug"] == "ipbuilding_gateway"
    assert "ha_ipbuilding_gateway" in cfg.get("discovery", [])
