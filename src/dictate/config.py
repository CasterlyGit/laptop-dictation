"""Config file loader: ~/.config/laptop-dictation/config.toml."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]


CONFIG_PATH = Path(os.environ.get("DICTATE_CONFIG", "~/.config/laptop-dictation/config.toml")).expanduser()


@dataclass
class HotkeyConfig:
    key: str = "alt_r"  # pynput key name


@dataclass
class RecordingConfig:
    sample_rate: int = 16000
    device: str = "default"


@dataclass
class TranscriptionConfig:
    backend: str = "whisper-cpp"  # whisper-cpp | openai
    model: str = "small"
    language: str = "en"


@dataclass
class OutputConfig:
    copy_to_clipboard: bool = True
    auto_paste: bool = False
    auto_submit: bool = False  # press Enter after paste (sends the message)
    submit_delay_ms: int = 40  # tiny gap between paste and Enter


@dataclass
class PathsConfig:
    whisper_cpp: str = "/opt/homebrew/bin/whisper-cli"
    models_dir: str = "~/.cache/whisper-cpp"

    @property
    def models_dir_path(self) -> Path:
        return Path(self.models_dir).expanduser()


@dataclass
class Config:
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    recording: RecordingConfig = field(default_factory=RecordingConfig)
    transcription: TranscriptionConfig = field(default_factory=TranscriptionConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)

    def model_file(self) -> Path:
        return self.paths.models_dir_path / f"ggml-{self.transcription.model}.bin"


DEFAULT_TOML = """\
# laptop-dictation config — edit to taste
[hotkey]
key = "alt_r"               # hold-to-talk key. pynput key names; try "f9" or "ctrl_r".

[recording]
sample_rate = 16000
device = "default"

[transcription]
backend = "whisper-cpp"     # whisper-cpp | openai
model = "small"             # tiny | base | small | medium | large
language = "en"             # ISO code; "auto" for detection

[output]
copy_to_clipboard = true
auto_paste = false          # also send cmd+V after copying
auto_submit = false         # press Enter after paste (great for Claude Code / chat boxes)
submit_delay_ms = 40        # gap between paste and Enter

[paths]
whisper_cpp = "/opt/homebrew/bin/whisper-cli"
models_dir = "~/.cache/whisper-cpp"
"""


def load_config(path: Path = CONFIG_PATH) -> Config:
    """Load config from TOML, falling back to defaults for missing sections."""
    if not path.exists():
        return Config()
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    return _from_dict(raw)


def _from_dict(raw: dict[str, Any]) -> Config:
    cfg = Config()
    if "hotkey" in raw:
        cfg.hotkey = HotkeyConfig(**{k: v for k, v in raw["hotkey"].items() if k in HotkeyConfig.__dataclass_fields__})
    if "recording" in raw:
        cfg.recording = RecordingConfig(**{k: v for k, v in raw["recording"].items() if k in RecordingConfig.__dataclass_fields__})
    if "transcription" in raw:
        cfg.transcription = TranscriptionConfig(**{k: v for k, v in raw["transcription"].items() if k in TranscriptionConfig.__dataclass_fields__})
    if "output" in raw:
        cfg.output = OutputConfig(**{k: v for k, v in raw["output"].items() if k in OutputConfig.__dataclass_fields__})
    if "paths" in raw:
        cfg.paths = PathsConfig(**{k: v for k, v in raw["paths"].items() if k in PathsConfig.__dataclass_fields__})
    return cfg


def write_default_config(path: Path = CONFIG_PATH) -> Path:
    """Idempotent: write the default config if not present."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(DEFAULT_TOML, encoding="utf-8")
    return path
