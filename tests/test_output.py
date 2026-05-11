"""Clipboard output tests — uses pyperclip or a subprocess fallback."""

from __future__ import annotations

import sys

import pytest

from dictate.output import copy_to_clipboard


@pytest.mark.skipif(
    sys.platform != "darwin",
    reason="pbcopy fallback path tested only on macOS where pbcopy exists",
)
def test_copy_to_clipboard_roundtrip():
    """Copy then read via pbpaste — proves the copy actually happened."""
    import subprocess
    text = "laptop-dictation clipboard test 12345"
    copy_to_clipboard(text)
    out = subprocess.check_output(["pbpaste"], text=True)
    assert out == text
