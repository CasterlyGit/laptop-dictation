"""Parsing tests for the voice-command bridge (dictate.command).

Pure parsing only — no mic, no notification center. Covers the phrasings a
real dictation will throw at "make the notch <color>".
"""

import pytest

from dictate.command import parse_notch_color


@pytest.mark.parametrize(
    "utterance,expected",
    [
        ("notch white", "white"),
        ("make the notch white", "white"),
        ("make the notch white.", "white"),
        ("Make the notch white.", "white"),
        ("turn the notch white", "white"),
        ("set the notch to white", "white"),
        ("change the notch to electric blue", "electric blue"),
        ("notch electric blue", "electric blue"),
        ("please make the notch red", "red"),
        ("ok make the ledge cyan", "cyan"),
        ("notch #0af", "#0af"),
        ("make the notch reset", "reset"),
        ("notch to green", "green"),
        ("color the notch purple", "purple"),
    ],
)
def test_parses_color(utterance, expected):
    assert parse_notch_color(utterance) == expected


@pytest.mark.parametrize(
    "utterance",
    [
        "",
        "what time is it",
        "open the terminal",
        "hello there how are you",
    ],
)
def test_non_commands_return_none(utterance):
    assert parse_notch_color(utterance) is None


def test_color_first_phrasing():
    # "white notch" — color precedes the noun
    assert parse_notch_color("white notch") == "white"
