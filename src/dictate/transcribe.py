"""Transcription backends: local whisper.cpp, local Moonshine ONNX, or OpenAI Whisper API."""

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

    def transcribe(self, wav: Path, *, model: str, language: str,
                   beam_size: int = 0, prompt: str = "") -> TranscriptionResult:
        ...


class WhisperCppBackend:
    """Local whisper.cpp binary. Fast on Apple Silicon."""

    name = "whisper-cpp"

    def __init__(self, binary: str, models_dir: Path) -> None:
        self.binary = binary
        self.models_dir = Path(models_dir).expanduser()

    def model_path(self, model: str) -> Path:
        return self.models_dir / f"ggml-{model}.bin"

    def transcribe(self, wav: Path, *, model: str, language: str,
                   beam_size: int = 0, prompt: str = "") -> TranscriptionResult:
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
        if beam_size > 0:
            cmd += ["-bs", str(beam_size)]  # 1 = greedy decode, ~2x faster on CPU
        if prompt:
            cmd += ["--prompt", prompt]     # bias decoding toward domain vocabulary
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


_MOONSHINE_INSTALL_HINT = (
    "Moonshine deps missing. Install WITHOUT librosa (its numba dep does not build "
    "on Intel macs): `pip install --no-deps useful-moonshine-onnx && "
    "pip install onnxruntime tokenizers huggingface_hub numpy`"
)


def moonshine_model_name(model: str) -> str:
    """Map config model names to Moonshine ONNX names. tiny/base only (v1)."""
    m = model.strip().lower().removesuffix(".en")
    if m.startswith("moonshine/"):
        m = m.split("/", 1)[1]
    if m not in ("tiny", "base"):
        raise TranscribeError(
            f"moonshine backend supports models tiny|base, got {model!r}."
        )
    return f"moonshine/{m}"


def chunk_spans(audio, sample_rate: int, max_s: float = 60.0,
                search_s: float = 10.0, win_s: float = 0.25) -> list[tuple[int, int]]:
    """Split audio into spans ≤ max_s (Moonshine hard limit is 64s per call).

    Cuts at the quietest win_s window within the last search_s of each chunk,
    so long toggle-mode recordings don't get sliced mid-word.
    """
    import numpy as np

    n = len(audio)
    max_n = int(max_s * sample_rate)
    if n <= max_n:
        return [(0, n)]
    win = max(1, int(win_s * sample_rate))
    spans: list[tuple[int, int]] = []
    start = 0
    while n - start > max_n:
        lo, hi = start + max_n - int(search_s * sample_rate), start + max_n
        seg = np.asarray(audio[lo:hi], dtype=np.float64)
        energy = np.cumsum(seg * seg)
        sums = energy[win:] - energy[:-win]  # sliding-window energy
        cut = lo + int(np.argmin(sums)) + win // 2
        spans.append((start, cut))
        start = cut
    spans.append((start, n))
    return spans


class MoonshineBackend:
    """Local Moonshine ONNX models (UsefulSensors, MIT). No 30s padding like
    whisper, so decode time scales with clip length — benchmarked 2026-06-04 on
    the i5-1038NG7: base/quantized 0.87s for a 4.5s utterance vs 3.54s for
    whisper.cpp tiny.en (4x), at better published WER. English-only (v1).
    beam_size and prompt are whisper-only and ignored here.
    """

    name = "moonshine"
    PRECISION = "quantized"  # int8: 1.7x faster than float on this CPU, same output

    def __init__(self) -> None:
        self._model = None
        self._model_name: str | None = None

    def warmup(self, model: str) -> None:
        """Load the model ahead of the first dictation (daemon startup)."""
        self._ensure_model(model)

    def _ensure_model(self, model: str):
        name = moonshine_model_name(model)
        if self._model is None or self._model_name != name:
            try:
                from moonshine_onnx import MoonshineOnnxModel
            except ImportError as e:
                raise TranscribeError(_MOONSHINE_INSTALL_HINT) from e
            self._model = MoonshineOnnxModel(model_name=name, model_precision=self.PRECISION)
            self._model_name = name
        return self._model

    @staticmethod
    def _load_wav(wav: Path):
        """16 kHz mono 16-bit PCM (what recorder.py produces) -> float32 [-1, 1]."""
        import wave as _wave

        import numpy as np

        with _wave.open(str(wav)) as w:
            if w.getframerate() != 16000 or w.getnchannels() != 1 or w.getsampwidth() != 2:
                raise TranscribeError(
                    f"moonshine backend needs 16kHz mono 16-bit WAV, got "
                    f"{w.getframerate()}Hz/{w.getnchannels()}ch/{8 * w.getsampwidth()}bit: {wav}"
                )
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        return (pcm / 32768.0).astype(np.float32)

    def transcribe(self, wav: Path, *, model: str, language: str,
                   beam_size: int = 0, prompt: str = "") -> TranscriptionResult:
        import time

        if language not in ("en", "auto"):
            raise TranscribeError("moonshine v1 models are English-only; set language to 'en'.")
        mdl = self._ensure_model(model)
        from moonshine_onnx import transcribe as mo_transcribe

        audio = self._load_wav(wav)
        start = time.monotonic()
        parts = []
        for lo, hi in chunk_spans(audio, 16000):
            parts.append(" ".join(mo_transcribe(audio[lo:hi], mdl)).strip())
        elapsed_ms = int((time.monotonic() - start) * 1000)
        text = " ".join(p for p in parts if p).strip()
        return TranscriptionResult(text=text, backend=self.name, duration_ms=elapsed_ms)


class OpenAIBackend:
    """OpenAI Whisper API. Slower (network roundtrip) but no local model needed."""

    name = "openai"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise TranscribeError("OPENAI_API_KEY not set for openai backend.")

    def transcribe(self, wav: Path, *, model: str, language: str,
                   beam_size: int = 0, prompt: str = "") -> TranscriptionResult:
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
                prompt=prompt or None,  # beam_size is whisper.cpp-only
            )
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return TranscriptionResult(text=resp.text.strip(), backend=self.name, duration_ms=elapsed_ms)


def build_backend(backend_name: str, *, whisper_cpp_binary: str, models_dir: Path) -> Backend:
    if backend_name == "whisper-cpp":
        return WhisperCppBackend(binary=whisper_cpp_binary, models_dir=models_dir)
    if backend_name == "moonshine":
        return MoonshineBackend()
    if backend_name == "openai":
        return OpenAIBackend()
    raise TranscribeError(f"Unknown backend: {backend_name}")
