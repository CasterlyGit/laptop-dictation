"""Hotkey parsing + chord matching. No pynput Listener is started — pure logic."""

from __future__ import annotations

import pytest

from dictate.listener import chord_satisfied, parse_hotkey


def test_parse_single_modifier_key():
    slots = parse_hotkey("alt_r")
    assert slots == [frozenset({"alt_r"})]


def test_parse_single_char():
    slots = parse_hotkey("l")
    assert slots == [frozenset({"l"})]


def test_parse_function_key():
    slots = parse_hotkey("f9")
    assert slots == [frozenset({"f9"})]


def test_parse_chord_ctrl_shift_l():
    slots = parse_hotkey("ctrl+shift+l")
    assert len(slots) == 3
    # ctrl accepts ctrl_l or ctrl_r
    assert "ctrl_l" in slots[0] and "ctrl_r" in slots[0]
    assert "shift_l" in slots[1] and "shift_r" in slots[1]
    assert slots[2] == frozenset({"l"})


def test_parse_chord_aliases():
    """opt / option / alt all resolve to the same set."""
    assert parse_hotkey("opt+space") == parse_hotkey("alt+space")
    assert parse_hotkey("cmd+l") == parse_hotkey("command+l")


def test_parse_strips_whitespace_and_case():
    slots = parse_hotkey("  CTRL + Shift + L  ")
    assert len(slots) == 3
    assert "l" in slots[2]


def test_parse_rejects_unknown_part():
    with pytest.raises(ValueError):
        parse_hotkey("ctrl+banana+l")


def test_parse_rejects_empty():
    with pytest.raises(ValueError):
        parse_hotkey("")


def test_chord_satisfied_single_key():
    slots = parse_hotkey("alt_r")
    assert chord_satisfied(slots, {"alt_r"})
    assert not chord_satisfied(slots, {"alt_l"})  # specific variant only
    assert not chord_satisfied(slots, set())


def test_chord_satisfied_generic_modifier():
    slots = parse_hotkey("alt")
    # either variant satisfies the generic alias
    assert chord_satisfied(slots, {"alt_l"})
    assert chord_satisfied(slots, {"alt_r"})


def test_chord_satisfied_three_key_chord():
    slots = parse_hotkey("ctrl+shift+l")
    # all three pressed (left variants)
    assert chord_satisfied(slots, {"ctrl_l", "shift_l", "l"})
    # mixed variants still ok
    assert chord_satisfied(slots, {"ctrl_r", "shift_l", "l"})
    # extra keys held is fine — only required slots must be covered
    assert chord_satisfied(slots, {"ctrl_l", "shift_l", "l", "a"})
    # missing one slot
    assert not chord_satisfied(slots, {"ctrl_l", "shift_l"})
    assert not chord_satisfied(slots, {"shift_l", "l"})
    assert not chord_satisfied(slots, set())


def test_chord_release_breaks_satisfaction():
    """Simulate release: removing one slot's key drops satisfaction."""
    slots = parse_hotkey("ctrl+shift+l")
    held = {"ctrl_l", "shift_l", "l"}
    assert chord_satisfied(slots, held)
    held.discard("l")
    assert not chord_satisfied(slots, held)
