"""Transcription backends: local whisper.cpp or OpenAI Whisper API."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class TranscribeError(RuntimeError):
    pass


@dataclass
class TranscriptionResult:
    text: str
    backend: str
    duration_ms: int


class Backend(Protocol):
    name: str

    def transcribe(self, wav: Path, *, model: str, language: str) -> TranscriptionResult:
        ...


class WhisperCppBackend:
    """Local whisper.cpp binary. Fast on Apple Silicon."""

    name = "whisper-cpp"

    def __init__(self, binary: str, models_dir: Path) -> None:
        self.binary = binary
        self.models_dir = Path(models_dir).expanduser()

    def model_path(self, model: str) -> Path:
        return self.models_dir / f"ggml-{model}.bin"

    def transcribe(self, wav: Path, *, model: str, language: str) -> TranscriptionResult:
        import time

        if not Path(self.binary).exists():
            # Try PATH lookup
            found = shutil.which("whisper-cli") or shutil.which("whisper-cpp")
            if not found:
                raise TranscribeError(
                    f"whisper.cpp binary not found at {self.binary}. "
                    "Install with `brew install whisper-cpp` and update config."
                )
            self.binary = found
        mp = self.model_path(model)
        if not mp.exists():
            raise TranscribeError(
                f"Model file missing: {mp}. Download with `dictate model download {model}`."
            )
        cmd = [
            self.binary,
            "-m", str(mp),
            "-f", str(wav),
            "-l", language if language != "auto" else "auto",
            "-nt",        # no timestamps
            "-otxt",      # write .txt next to wav
        ]
        start = time.monotonic()
        r = subprocess.run(cmd, check=False, capture_output=True, text=True)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        if r.returncode != 0:
            raise TranscribeError(
                f"whisper.cpp failed (exit {r.returncode}): {r.stderr.strip()}"
            )
        # Read the produced .txt file
        txt_path = wav.with_suffix(wav.suffix + ".txt")
        if not txt_path.exists():
            # Fall back to stdout parsing
            text = r.stdout.strip()
        else:
            text = txt_path.read_text(encoding="utf-8").strip()
            txt_path.unlink(missing_ok=True)
        return TranscriptionResult(text=text, backend=self.name, duration_ms=elapsed_ms)


class OpenAIBackend:
    """OpenAI Whisper API. Slower (network roundtrip) but no local model needed."""

    name = "openai"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise TranscribeError("OPENAI_API_KEY not set for openai backend.")

    def transcribe(self, wav: Path, *, model: str, language: str) -> TranscriptionResult:
        import time
        try:
            from openai import OpenAI
        except ImportError as e:
            raise TranscribeError("openai SDK not installed. `pip install 'laptop-dictation[api]'`") from e
        client = OpenAI(api_key=self.api_key)
        start = time.monotonic()
        with wav.open("rb") as f:
            resp = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language=language if language != "auto" else None,
            )
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return TranscriptionResult(text=resp.text.strip(), backend=self.name, duration_ms=elapsed_ms)


def build_backend(backend_name: str, *, whisper_cpp_binary: str, models_dir: Path) -> Backend:
    if backend_name == "whisper-cpp":
        return WhisperCppBackend(binary=whisper_cpp_binary, models_dir=models_dir)
    if backend_name == "openai":
        return OpenAIBackend()
    raise TranscribeError(f"Unknown backend: {backend_name}")
