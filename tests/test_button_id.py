"""Tests for gateway.button_id.canonical_button_id."""

from gateway.button_id import canonical_button_id

# Four wire↔IPA pairs confirmed on the 2026-08-29 Nolf log.
_CONFIRMED_PAIRS = [
    # wire 14-hex, IPA/config 10-hex, getButtons 16-hex, canonical 8-hex
    ("dac46c100000c3", "dac46cc330", "01dac46c100000c3", "dac46cc3"),
    ("4ff86c1000003c", "4ff86c3c30", "014ff86c1000003c", "4ff86c3c"),
    ("d56c6c100000ea", "d56c6cea42", "01d56c6c100000ea", "d56c6cea"),
    ("9e8a6b100000a7", "9e8a6ba730", "019e8a6b100000a7", "9e8a6ba7"),
]


def test_already_canonical_unchanged() -> None:
    assert canonical_button_id("dac46cc3") == "dac46cc3"


def test_ten_hex_strips_target_octet() -> None:
    assert canonical_button_id("dac46cc330") == "dac46cc3"


def test_fourteen_hex_wire() -> None:
    assert canonical_button_id("dac46c100000c3") == "dac46cc3"


def test_sixteen_hex_strips_type_then_wire() -> None:
    assert canonical_button_id("01dac46c100000c3") == "dac46cc3"
    assert canonical_button_id("2ddac46c100000c3") == "dac46cc3"


def test_confirmed_wire_ipa_pairs() -> None:
    for wire, ipa10, getbuttons, canonical in _CONFIRMED_PAIRS:
        assert canonical_button_id(wire) == canonical
        assert canonical_button_id(ipa10) == canonical
        assert canonical_button_id(getbuttons) == canonical
        assert canonical_button_id(canonical) == canonical


def test_uppercase_and_whitespace() -> None:
    assert canonical_button_id("  DAC46CC330\n") == "dac46cc3"
    assert canonical_button_id("2DDAC46C100000C3") == "dac46cc3"


def test_non_hex_returns_none() -> None:
    assert canonical_button_id("not-hex!!") is None
    assert canonical_button_id("dac46ccg") is None


def test_odd_and_unknown_lengths_return_none() -> None:
    assert canonical_button_id("dac46cc") is None  # 7
    assert canonical_button_id("dac46cc33") is None  # 9
    assert canonical_button_id("dac46c100000c") is None  # 13
    assert canonical_button_id("") is None
    assert canonical_button_id("  ") is None
