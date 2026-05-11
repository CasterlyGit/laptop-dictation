"""Recorder argument-building tests. Doesn't actually record audio."""

from __future__ import annotations

import platform

import pytest

from dictate.recorder import RecorderError, _input_args, ensure_ffmpeg


def test_ensure_ffmpeg_finds_it():
    # On dev machines we expect ffmpeg to be installed. Skip if not.
    import shutil
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed on this machine")
    ensure_ffmpeg()  # should not raise


def test_input_args_darwin():
    if platform.system() != "Darwin":
        pytest.skip("macOS-specific test")
    args = _input_args("default", 16000)
    assert "-f" in args
    assert "avfoundation" in args
    assert "16000" in args


def test_input_args_unknown_platform(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Plan9")
    with pytest.raises(RecorderError, match="Unsupported platform"):
        _input_args("default", 16000)
