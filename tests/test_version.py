"""Gateway version must track ipbuilding_gateway/config.yaml.

The runtime version (``__version__``, exposed via ``/api/v1/status`` and HA
discovery) is read from the add-on manifest in ``ipbuilding_gateway/config.yaml``
at import time. There is no generated ``gateway/_version.py`` and no
build-time stamping. These tests pin that contract down.
"""

from __future__ import annotations

import re
import sys
import types
from pathlib import Path

from gateway import __version__

_CONFIG = Path(__file__).resolve().parent.parent / "ipbuilding_gateway" / "config.yaml"
_VERSION_RE = re.compile(r'^version:\s*"?([^"\n]+)"?\s*$', re.MULTILINE)
_AUTO_UPDATE_RE = re.compile(r'^auto_update:\s*(true|false)\s*$', re.MULTILINE)


def _config_version() -> str:
    match = _VERSION_RE.search(_CONFIG.read_text(encoding="utf-8"))
    assert match, "version: missing from ipbuilding_gateway/config.yaml"
    return match.group(1)


def _auto_update() -> str | None:
    match = _AUTO_UPDATE_RE.search(_CONFIG.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def test_gateway_version_matches_addon_config() -> None:
    assert __version__ == _config_version()


def test_auto_update_enabled() -> None:
    """Supervisor must be allowed to pull new add-on images automatically.

    Regression guard: the v0.3.3 image was published but Supervisor kept
    running v0.3.1 because ``auto_update: false`` requires a manual
    upgrade per release. Keep this ``true`` so 0.3.x patches reach HA
    without an operator action.
    """
    assert _auto_update() == "true"


def test_env_override_takes_precedence(monkeypatch: "object") -> None:
    """``GATEWAY_VERSION`` wins over config.yaml (used by tests and CI)."""
    from gateway import version as version_mod

    monkeypatch.setenv("GATEWAY_VERSION", "9.9.9-test")
    assert version_mod.resolve_version() == "9.9.9-test"


def test_missing_yaml_falls_back_to_dev(monkeypatch: "object") -> None:
    """Without a config.yaml in reach, the resolver reports 0.0.0-dev.

    We invoke ``resolve_version()`` directly with ``_config_yaml_path``
    patched to return ``None``. Going through ``importlib.reload`` is not
    viable: reload restores the file-defined module attributes and
    re-evaluates the body, so any in-process patch is lost.
    """
    from gateway import version as version_mod

    monkeypatch.setattr(version_mod, "_config_yaml_path", lambda: None)
    assert version_mod.resolve_version() == "0.0.0-dev"


def test_no_generated_version_file_is_used(monkeypatch: "object") -> None:
    """Regression guard: a stray ``gateway/_version.py`` must be ignored.

    If a future change reintroduces a generated ``_version.py`` (e.g. by
    accident in ``prepare-build.sh``), the runtime would silently start
    reporting the stamped value instead of the YAML. This test injects
    one with a different value and asserts the resolver still reports the
    YAML's version, proving the import path is no longer consulted.
    """
    from gateway import version as version_mod

    fake = types.ModuleType("gateway._version")
    fake.__version__ = "9.9.9-leak"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "gateway._version", fake)
    assert version_mod.resolve_version() == _config_version()
