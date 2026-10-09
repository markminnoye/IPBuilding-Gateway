"""Dialect ids and display names have a single source."""

from pathlib import Path

from gateway.payloads.dialects import DIALECTS

_REGISTRY = Path("resources_and_docs/reference/veldbus_dialect_registry.md")
_GATEWAY = Path("gateway")


def test_registry_quotes_each_dialect() -> None:
    text = _REGISTRY.read_text(encoding="utf-8")
    assert "willekeurige stad" in text
    assert "gateway/payloads/dialects.py" in text
    for dialect in DIALECTS:
        assert dialect.id in text
        assert dialect.display_name in text
        assert f"dimmer.{dialect.id}." in text
        assert f"input.{dialect.id}." in text


def test_message_type_uses_only_the_central_id() -> None:
    for dialect in DIALECTS:
        assert dialect.message_type("relay", "command") == f"relay.{dialect.id}.command"


def test_gateway_code_does_not_hardcode_dialect_ids() -> None:
    for path in _GATEWAY.rglob("*.py"):
        if path.name == "dialects.py":
            continue
        text = path.read_text(encoding="utf-8")
        for dialect in DIALECTS:
            assert dialect.id not in text, path
