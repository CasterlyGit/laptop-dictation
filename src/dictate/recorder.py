"""Microphone recording via ffmpeg.

ffmpeg is preferred over portaudio bindings because it's already installed on most
dev machines and supports macOS AVFoundation + Linux ALSA + Windows DirectShow with
the same invocation surface.
"""

from __future__ import annotations

import functools
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

FFMPEG = shutil.which("ffmpeg") or "/usr/local/bin/ffmpeg"

# AVFoundation index 0 is NOT the macOS default input — it's whatever enumerates
# first, which is routinely a Continuity "iPhone Microphone" (records silence) or
# a conferencing/virtual device. These substrings are never the built-in mic.
_AVF_EXCLUDE = ("iphone", "ipad", "continuity", "teams", "zoom", "webex",
                "virtual", "aggregate", "blackhole", "loopback", "soundflower")


class RecorderError(RuntimeError):
    pass


def ensure_ffmpeg() -> None:
    if not Path(FFMPEG).exists():
        raise RecorderError(
            "ffmpeg not found. Install with `brew install ffmpeg` on macOS or "
            "`apt install ffmpeg` on Linux."
        )


@functools.lru_cache(maxsize=1)
def _list_avf_audio_devices() -> tuple[tuple[int, str], ...]:
    """Return ((index, name), ...) of AVFoundation audio input devices."""
    try:
        r = subprocess.run(
            [FFMPEG, "-hide_banner", "-f", "avfoundation",
             "-list_devices", "true", "-i", ""],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    devices: list[tuple[int, str]] = []
    in_audio = False
    for line in r.stderr.splitlines():
        if "AVFoundation audio devices" in line:
            in_audio = True
            continue
        if not in_audio:
            continue
        m = re.search(r"\]\s*\[(\d+)\]\s+(.+)$", line)
        if m:
            devices.append((int(m.group(1)), m.group(2).strip()))
        elif "AVFoundation" not in line:
            break  # left the audio-device block
    return tuple(devices)


def _resolve_darwin_audio_device(device: str) -> str:
    """Map a config device to an ffmpeg AVFoundation audio spec.

    Non-'default' values pass through (an index like "1" or an exact name).
    'default' resolves to the built-in mic BY NAME (stable across device
    reordering / Continuity hand-off), preferring 'MacBook ... Microphone' and
    otherwise the first input that isn't a phone/virtual/conferencing device.
    Falls back to index 0 only if enumeration fails.
    """
    if device != "default":
        return device
    devices = _list_avf_audio_devices()
    if not devices:
        return "0"
    for _, name in devices:
        low = name.lower()
        if "macbook" in low and "microphone" in low:
            return name
    for _, name in devices:
        if not any(bad in name.lower() for bad in _AVF_EXCLUDE):
            return name
    return str(devices[0][0])


def _input_args(device: str, sample_rate: int) -> list[str]:
    system = platform.system()
    if system == "Darwin":
        spec = _resolve_darwin_audio_device(device)
        return ["-f", "avfoundation", "-i", f":{spec}",
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
