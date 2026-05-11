"""Microphone recording via ffmpeg.

ffmpeg is preferred over portaudio bindings because it's already installed on most
dev machines and supports macOS AVFoundation + Linux ALSA + Windows DirectShow with
the same invocation surface.
"""

from __future__ import annotations

import os
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

FFMPEG = shutil.which("ffmpeg") or "/usr/local/bin/ffmpeg"


class RecorderError(RuntimeError):
    pass


def ensure_ffmpeg() -> None:
    if not Path(FFMPEG).exists():
        raise RecorderError(
            "ffmpeg not found. Install with `brew install ffmpeg` on macOS or "
            "`apt install ffmpeg` on Linux."
        )


def _input_args(device: str, sample_rate: int) -> list[str]:
    system = platform.system()
    if system == "Darwin":
        # AVFoundation. ":0" is "default audio input". Override with device for index.
        return ["-f", "avfoundation", "-i", f":{device if device != 'default' else '0'}",
                "-ac", "1", "-ar", str(sample_rate)]
    if system == "Linux":
        return ["-f", "alsa", "-i", device if device != "default" else "default",
                "-ac", "1", "-ar", str(sample_rate)]
    if system == "Windows":
        return ["-f", "dshow", "-i", f"audio={device}",
                "-ac", "1", "-ar", str(sample_rate)]
    raise RecorderError(f"Unsupported platform: {system}")


def start_recording(device: str, sample_rate: int, output: Path | None = None) -> tuple[subprocess.Popen, Path]:
    """Start an ffmpeg process recording to a temp WAV. Returns (proc, path).

    Call stop_recording(proc) to gracefully end and finalize the file.
    """
    ensure_ffmpeg()
    if output is None:
        fd, name = tempfile.mkstemp(prefix="dictate-", suffix=".wav")
        os.close(fd)
        output = Path(name)
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *_input_args(device, sample_rate), str(output)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return proc, output


def stop_recording(proc: subprocess.Popen, timeout: float = 3.0) -> int:
    """Send 'q' to ffmpeg to flush + close gracefully; fall back to SIGTERM."""
    try:
        if proc.stdin and not proc.stdin.closed:
            proc.stdin.write(b"q")
            proc.stdin.flush()
        return proc.wait(timeout=timeout)
    except (BrokenPipeError, ValueError, subprocess.TimeoutExpired):
        proc.send_signal(signal.SIGTERM)
        try:
            return proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            return proc.wait(timeout=timeout)


def record_fixed(device: str, sample_rate: int, seconds: float, output: Path | None = None) -> Path:
    """Blocking record for `seconds` then return the WAV path."""
    ensure_ffmpeg()
    if output is None:
        fd, name = tempfile.mkstemp(prefix="dictate-", suffix=".wav")
        os.close(fd)
        output = Path(name)
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
           *_input_args(device, sample_rate), "-t", str(seconds), str(output)]
    r = subprocess.run(cmd, check=False, capture_output=True)
    if r.returncode != 0:
        raise RecorderError(
            f"ffmpeg failed (exit {r.returncode}): {r.stderr.decode(errors='ignore')}"
        )
    if output.stat().st_size == 0:
        raise RecorderError("Recording produced an empty WAV — mic permission denied?")
    return output
