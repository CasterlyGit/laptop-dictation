"""Clipboard output tests — uses pyperclip or a subprocess fallback."""

from __future__ import annotations

import sys

import pytest

from dictate.output import copy_to_clipboard, send_enter_keystroke, send_paste_keystroke


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


def test_send_paste_keystroke_uses_platform_modifier(monkeypatch):
    """Paste shortcut: cmd+V on Darwin, ctrl+V elsewhere. Verify via a fake controller."""
    pressed: list = []

    class FakeCtx:
        def __init__(self, kb, mod): self.mod = mod; self.kb = kb
        def __enter__(self): pressed.append(("hold", self.mod)); return self
        def __exit__(self, *a): pressed.append(("release-mod", self.mod))

    class FakeController:
        def pressed(self, mod): return FakeCtx(self, mod)
        def press(self, k): pressed.append(("press", k))
        def release(self, k): pressed.append(("release", k))

    fake_key = type("Key", (), {"cmd": "CMD", "ctrl": "CTRL", "enter": "ENTER"})
    import sys as _sys
    fake_mod = type(_sys)("pynput.keyboard")
    fake_mod.Controller = FakeController
    fake_mod.Key = fake_key
    monkeypatch.setitem(_sys.modules, "pynput", type(_sys)("pynput"))
    monkeypatch.setitem(_sys.modules, "pynput.keyboard", fake_mod)

    send_paste_keystroke()
    # On macOS the held modifier should be CMD; otherwise CTRL.
    expected_mod = "CMD" if sys.platform == "darwin" else "CTRL"
    assert ("hold", expected_mod) in pressed
    assert ("press", "v") in pressed


def test_send_enter_keystroke(monkeypatch):
    """Enter keystroke presses and releases Key.enter exactly once."""
    events: list = []

    class FakeController:
        def press(self, k): events.append(("press", k))
        def release(self, k): events.append(("release", k))

    fake_key = type("Key", (), {"cmd": "CMD", "ctrl": "CTRL", "enter": "ENTER"})
    import sys as _sys
    fake_mod = type(_sys)("pynput.keyboard")
    fake_mod.Controller = FakeController
    fake_mod.Key = fake_key
    monkeypatch.setitem(_sys.modules, "pynput", type(_sys)("pynput"))
    monkeypatch.setitem(_sys.modules, "pynput.keyboard", fake_mod)

    send_enter_keystroke()
    assert events == [("press", "ENTER"), ("release", "ENTER")]
