"""Error classification: unreachable, switch off, missing capability, other."""

from __future__ import annotations

import socket

import pytest

from ipbuilding_debug.errors import (
    KIND_LOG_LEVEL_RATE_LIMITED,
    KIND_NOT_AVAILABLE,
    KIND_OTHER,
    KIND_REMOTE_DEBUGGING_OFF,
    KIND_UNREACHABLE,
    MSG_LOG_LEVEL_RATE_LIMITED,
    MSG_NOT_AVAILABLE,
    MSG_REMOTE_DEBUGGING_OFF,
    MSG_UNREACHABLE,
    NOT_AVAILABLE_PHRASE,
    SWITCH_NAME,
    SWITCH_NAME_NL,
    SWITCH_WHERE,
    classify_http,
    classify_transport,
    gate_feature,
    is_remote_debugging_disabled,
    msg_not_available,
)


def test_unreachable_message_tells_the_tester_what_to_check() -> None:
    assert "IPBuilding Gateway" in MSG_UNREACHABLE
    assert "homeassistant.local" in MSG_UNREACHABLE
    assert "volstaat meestal" in MSG_UNREACHABLE
    assert "schakelaar" in MSG_UNREACHABLE
    assert "browser" in MSG_UNREACHABLE
    assert "Configure" in MSG_UNREACHABLE
    assert "Instellingen > Add-ons > IPBuilding Gateway" in MSG_UNREACHABLE


def test_switch_off_message_names_the_control_and_where_it_is() -> None:
    assert SWITCH_NAME in MSG_REMOTE_DEBUGGING_OFF
    assert SWITCH_WHERE in MSG_REMOTE_DEBUGGING_OFF
    assert SWITCH_NAME_NL in MSG_REMOTE_DEBUGGING_OFF
    assert "Remote debugging and control" not in MSG_REMOTE_DEBUGGING_OFF
    assert "Debuggen en bedienen op afstand" not in MSG_REMOTE_DEBUGGING_OFF
    assert "Toegang op afstand" in MSG_REMOTE_DEBUGGING_OFF
    assert "onder Debug" not in MSG_REMOTE_DEBUGGING_OFF
    assert "blijft aan" in MSG_REMOTE_DEBUGGING_OFF
    assert "blijvende melding" in MSG_REMOTE_DEBUGGING_OFF


def test_not_available_phrase_is_exact() -> None:
    assert NOT_AVAILABLE_PHRASE in MSG_NOT_AVAILABLE
    assert NOT_AVAILABLE_PHRASE in msg_not_available("udp_frame")


@pytest.mark.parametrize(
    "body",
    [
        {"error": "remote_debugging_disabled"},
        {"error": "remote_debugging_disabled", "message": "uit"},
        {"ok": False, "error": "remote_debugging_disabled"},
        {"code": "remote_debugging_disabled"},
        {"error": {"code": "remote_debugging_disabled"}},
    ],
)
def test_disabled_error_code_is_the_switch(body: dict) -> None:
    assert is_remote_debugging_disabled(body)
    classified = classify_http(403, body)
    assert classified.kind == KIND_REMOTE_DEBUGGING_OFF
    assert classified.message == MSG_REMOTE_DEBUGGING_OFF


def test_log_level_rate_limit_asks_the_tester_to_wait() -> None:
    body = {
        "error": "log_level_rate_limited",
        "message": "Too many log level changes. Wait and try again.",
    }
    classified = classify_http(429, body)
    assert classified.kind == KIND_LOG_LEVEL_RATE_LIMITED
    assert classified.message == MSG_LOG_LEVEL_RATE_LIMITED
    assert "10" in classified.message
    assert "minuut" in classified.message


def test_transport_failures_are_unreachable() -> None:
    for exc in (
        ConnectionRefusedError("refused"),
        TimeoutError("timed out"),
        socket.gaierror("name"),
        OSError("down"),
    ):
        classified = classify_transport(exc)
        assert classified.kind == KIND_UNREACHABLE
        assert classified.message == MSG_UNREACHABLE


def test_missing_route_is_not_this_version() -> None:
    for status in (404, 501):
        classified = classify_http(status, {"error": "not_found"})
        assert classified.kind == KIND_NOT_AVAILABLE
        assert NOT_AVAILABLE_PHRASE in classified.message


def test_other_http_error_stays_plain() -> None:
    classified = classify_http(500, {"error": "internal", "message": "kapot"})
    assert classified.kind == KIND_OTHER
    assert "kapot" in classified.message
    assert "IPBuilding Gateway" in classified.message
    assert "Traceback" not in classified.message


def test_missing_capability_wins_over_switch_off() -> None:
    """Turning the switch on does not add a feature this build lacks."""
    gated = gate_feature(
        {"remote_debugging": False, "capabilities": []},
        "udp_frame",
    )
    assert gated is not None
    assert gated.kind == KIND_NOT_AVAILABLE
    assert NOT_AVAILABLE_PHRASE in gated.message


def test_switch_off_when_the_feature_exists() -> None:
    gated = gate_feature(
        {"remote_debugging": False, "capabilities": ["raw_send"]},
        "raw_send",
    )
    assert gated is not None
    assert gated.kind == KIND_REMOTE_DEBUGGING_OFF
    assert gated.message == MSG_REMOTE_DEBUGGING_OFF


def test_explicit_disabled_code_on_the_wire_is_the_switch() -> None:
    from ipbuilding_debug.errors import ClassifiedError

    gated = gate_feature(
        {"remote_debugging": True, "capabilities": ["udp_frame"]},
        "udp_frame",
        ClassifiedError(
            KIND_REMOTE_DEBUGGING_OFF,
            MSG_REMOTE_DEBUGGING_OFF,
            "remote_debugging_disabled",
        ),
    )
    assert gated is not None
    assert gated.kind == KIND_REMOTE_DEBUGGING_OFF


def test_feature_allowed_only_when_listed_and_switch_on() -> None:
    assert (
        gate_feature(
            {"remote_debugging": True, "capabilities": ["udp_frame"]},
            "udp_frame",
        )
        is None
    )
