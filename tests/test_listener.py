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

# --- ctrl+3 / suppression logic (v0.4) -------------------------------------

from dictate.listener import should_suppress, suppress_vks


def test_parse_chord_ctrl_digit():
    slots = parse_hotkey("ctrl+3")
    assert len(slots) == 2
    assert "ctrl_l" in slots[0] and "ctrl_r" in slots[0]
    assert slots[1] == frozenset({"3"})


def test_suppress_vks_ctrl_3():
    """Only the non-modifier key of the chord is suppressible — vk 20 is '3'."""
    assert suppress_vks(parse_hotkey("ctrl+3")) == {20}


def test_suppress_vks_modifier_only_chord_is_empty():
    assert suppress_vks(parse_hotkey("ctrl+shift")) == set()


def test_suppress_vks_letter_chord():
    assert suppress_vks(parse_hotkey("ctrl+shift+l")) == {37}  # kVK_ANSI_L


def test_should_suppress_keydown_when_chord_held():
    slots = parse_hotkey("ctrl+3")
    # ctrl held, '3' going down (on_press already added it — pass either way)
    assert should_suppress(slots, set(), {"ctrl_l", "3"}, 20, is_down=True)
    assert should_suppress(slots, set(), {"ctrl_l"}, 20, is_down=True)  # order-independent


def test_should_not_suppress_bare_3():
    """Typing a plain '3' with no ctrl must pass through untouched."""
    slots = parse_hotkey("ctrl+3")
    assert not should_suppress(slots, set(), {"3"}, 20, is_down=True)
    assert not should_suppress(slots, set(), set(), 20, is_down=True)


def test_should_suppress_keyup_only_if_keydown_was_suppressed():
    slots = parse_hotkey("ctrl+3")
    # we swallowed the down → swallow the up, even if ctrl already released
    assert should_suppress(slots, {20}, set(), 20, is_down=False)
    # we never swallowed a down → the up passes through
    assert not should_suppress(slots, set(), {"ctrl_l"}, 20, is_down=False)


def test_should_suppress_autorepeat():
    """Autorepeat key-downs while the chord is held are swallowed too."""
    slots = parse_hotkey("ctrl+3")
    held = {"ctrl_l", "3"}
    for _ in range(5):
        assert should_suppress(slots, {20}, held, 20, is_down=True)


def test_normalize_key_vk_first_on_darwin(monkeypatch):
    """Under ctrl the event char can be mangled — vk lookup must win on macOS."""
    import dictate.listener as mod
    from pynput.keyboard import KeyCode
    monkeypatch.setattr(mod.platform, "system", lambda: "Darwin")
    from dictate.listener import normalize_key
    assert normalize_key(KeyCode.from_char("\x1b", vk=20)) == "3"   # ctrl-mangled '3'
    assert normalize_key(KeyCode.from_char("3", vk=20)) == "3"      # clean '3'
    assert normalize_key(KeyCode.from_char("L", vk=37)) == "l"      # letters too


def test_suppress_vks_punctuation_chord():
    """Punctuation chord keys must resolve to vks (ctrl+= was silently broken)."""
    assert suppress_vks(parse_hotkey("ctrl+=")) == {24}
    assert suppress_vks(parse_hotkey("ctrl+/")) == {44}


def test_normalize_key_punctuation_vk_first(monkeypatch):
    import dictate.listener as mod
    from pynput.keyboard import KeyCode
    monkeypatch.setattr(mod.platform, "system", lambda: "Darwin")
    from dictate.listener import normalize_key
    assert normalize_key(KeyCode.from_char("\x1d", vk=24)) == "="  # ctrl-mangled '='


def test_clean_transcript_strips_non_speech():
    from dictate.listener import clean_transcript
    assert clean_transcript("[BLANK_AUDIO]") == ""
    assert clean_transcript("[ Silence ]") == ""
    assert clean_transcript("(wind blowing)") == ""
    assert clean_transcript("*music playing*") == ""
    assert clean_transcript("♪♪♪") == ""
    assert clean_transcript("  [BLANK_AUDIO]  ") == ""
    # real speech with a trailing marker keeps the speech
    assert clean_transcript("refactor the listener [BLANK_AUDIO]") == "refactor the listener"
    assert clean_transcript("hello world") == "hello world"
