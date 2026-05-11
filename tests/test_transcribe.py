"""Backend selection + error paths. No real audio is transcribed in tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from dictate.transcribe import (
    OpenAIBackend,
    TranscribeError,
    WhisperCppBackend,
    build_backend,
)


def test_build_backend_whispercpp(tmp_path: Path):
    be = build_backend("whisper-cpp", whisper_cpp_binary="/nonexistent", models_dir=tmp_path)
    assert isinstance(be, WhisperCppBackend)
    assert be.name == "whisper-cpp"


def test_build_backend_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    be = build_backend("openai", whisper_cpp_binary="/x", models_dir=Path("/x"))
    assert isinstance(be, OpenAIBackend)


def test_build_backend_openai_missing_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(TranscribeError, match="OPENAI_API_KEY"):
        build_backend("openai", whisper_cpp_binary="/x", models_dir=Path("/x"))


def test_build_backend_unknown():
    with pytest.raises(TranscribeError, match="Unknown backend"):
        build_backend("magic", whisper_cpp_binary="/x", models_dir=Path("/x"))


def test_whispercpp_model_path(tmp_path: Path):
    be = WhisperCppBackend(binary="/x", models_dir=tmp_path)
    assert be.model_path("small") == tmp_path / "ggml-small.bin"


def test_whispercpp_missing_binary_raises(tmp_path):
    """If the binary is missing and no PATH fallback, transcribe should raise."""
    be = WhisperCppBackend(binary="/nonexistent/whisper-cli", models_dir=tmp_path)
    fake_wav = tmp_path / "fake.wav"
    fake_wav.write_bytes(b"riff-fake")
    # The fallback in transcribe() uses shutil.which — if it finds one on PATH, the
    # test would proceed. We exercise the "no binary anywhere" path by patching.
    import shutil
    orig_which = shutil.which
    shutil.which = lambda name: None
    try:
        with pytest.raises(TranscribeError, match="whisper.cpp binary not found"):
            be.transcribe(fake_wav, model="small", language="en")
    finally:
        shutil.which = orig_which
