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


# --- moonshine backend ---------------------------------------------------


def test_build_backend_moonshine():
    from dictate.transcribe import MoonshineBackend

    be = build_backend("moonshine", whisper_cpp_binary="/x", models_dir=Path("/x"))
    assert isinstance(be, MoonshineBackend)
    assert be.name == "moonshine"


def test_moonshine_model_name_mapping():
    from dictate.transcribe import moonshine_model_name

    assert moonshine_model_name("tiny") == "moonshine/tiny"
    assert moonshine_model_name("tiny.en") == "moonshine/tiny"
    assert moonshine_model_name("Base") == "moonshine/base"
    assert moonshine_model_name("moonshine/base") == "moonshine/base"
    with pytest.raises(TranscribeError, match="tiny|base"):
        moonshine_model_name("small")


def test_moonshine_rejects_non_english(tmp_path: Path):
    from dictate.transcribe import MoonshineBackend

    be = MoonshineBackend()
    with pytest.raises(TranscribeError, match="English-only"):
        be.transcribe(tmp_path / "x.wav", model="base", language="de")


def test_moonshine_missing_dep_message(monkeypatch, tmp_path: Path):
    """Without moonshine_onnx installed, the error must carry install commands."""
    import sys

    from dictate.transcribe import MoonshineBackend

    monkeypatch.setitem(sys.modules, "moonshine_onnx", None)  # forces ImportError
    be = MoonshineBackend()
    with pytest.raises(TranscribeError, match="--no-deps useful-moonshine-onnx"):
        be.transcribe(tmp_path / "x.wav", model="base", language="en")


def test_chunk_spans_short_clip_single_span():
    np = pytest.importorskip("numpy")
    from dictate.transcribe import chunk_spans

    audio = np.zeros(16000 * 10, dtype=np.float32)  # 10s
    assert chunk_spans(audio, 16000) == [(0, len(audio))]


def test_chunk_spans_long_clip_cuts_at_silence():
    np = pytest.importorskip("numpy")
    from dictate.transcribe import chunk_spans

    sr = 16000
    rng = np.random.default_rng(0)
    audio = rng.uniform(-0.5, 0.5, 130 * sr).astype(np.float32)  # 130s of "speech"
    audio[55 * sr:56 * sr] = 0.0    # silence inside chunk 1's search window
    audio[112 * sr:113 * sr] = 0.0  # silence inside chunk 2's search window

    spans = chunk_spans(audio, sr)
    # contiguous full cover
    assert spans[0][0] == 0 and spans[-1][1] == len(audio)
    assert all(a[1] == b[0] for a, b in zip(spans, spans[1:]))
    # every span within the 64s hard limit
    assert all((hi - lo) <= 60 * sr for lo, hi in spans)
    # cuts landed inside the silent second, not mid-speech
    assert 55 * sr <= spans[0][1] <= 56 * sr
    assert 112 * sr <= spans[1][1] <= 113 * sr
