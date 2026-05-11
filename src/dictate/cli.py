"""Click-based CLI."""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import CONFIG_PATH, load_config, write_default_config
from .output import copy_to_clipboard
from .recorder import record_fixed
from .transcribe import build_backend

console = Console()

WHISPER_MODELS = {
    "tiny": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin",
    "base": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin",
    "small": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin",
    "medium": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin",
    "large": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin",
}


@click.group()
@click.version_option(__version__)
def cli() -> None:
    """laptop-dictation — push-to-talk dictation. Hold a key, talk, get text on clipboard."""


@cli.command()
def init() -> None:
    """Write a default config file to ~/.config/laptop-dictation/config.toml."""
    path = write_default_config()
    console.print(f"[green]✔[/green] config at [cyan]{path}[/cyan]")
    console.print("Edit it to change hotkey, model, or backend.")


@cli.command()
def config() -> None:
    """Show resolved config (defaults + overrides)."""
    cfg = load_config()
    t = Table(title=f"config — {CONFIG_PATH}")
    t.add_column("section"); t.add_column("key"); t.add_column("value")
    for section_name in ("hotkey", "recording", "transcription", "output", "paths"):
        section = getattr(cfg, section_name)
        for k, v in section.__dict__.items():
            t.add_row(section_name, k, str(v))
    console.print(t)


@cli.command()
@click.option("--seconds", default=5.0, show_default=True, help="Record duration.")
@click.option("--model", default=None, help="Override model name (e.g. small, medium).")
@click.option("--backend", default=None, help="Override backend (whisper-cpp | openai).")
@click.option("--no-copy", is_flag=True, help="Don't copy to clipboard.")
def once(seconds: float, model: str | None, backend: str | None, no_copy: bool) -> None:
    """Record fixed duration, transcribe, print + copy to clipboard."""
    cfg = load_config()
    if model:
        cfg.transcription.model = model
    if backend:
        cfg.transcription.backend = backend

    console.print(f"[bold red]● REC[/bold red] for {seconds:.1f}s — speak now")
    wav = record_fixed(cfg.recording.device, cfg.recording.sample_rate, seconds)
    console.print("[dim]transcribing…[/dim]")
    be = build_backend(
        cfg.transcription.backend,
        whisper_cpp_binary=cfg.paths.whisper_cpp,
        models_dir=cfg.paths.models_dir_path,
    )
    try:
        result = be.transcribe(wav, model=cfg.transcription.model, language=cfg.transcription.language)
    finally:
        wav.unlink(missing_ok=True)
    console.print(f"\n[bold]{result.text}[/bold]\n")
    console.print(f"[dim]{result.backend} · {result.duration_ms} ms[/dim]")
    if not no_copy and cfg.output.copy_to_clipboard:
        copy_to_clipboard(result.text)
        console.print("[green]✔[/green] copied to clipboard")


@cli.command()
@click.option("--model", default=None, help="Override model name.")
@click.option("--backend", default=None, help="Override backend.")
def listen(model: str | None, backend: str | None) -> None:
    """Start the push-to-talk daemon. Hold the configured hotkey to record."""
    cfg = load_config()
    if model:
        cfg.transcription.model = model
    if backend:
        cfg.transcription.backend = backend
    from .listener import run_listener
    try:
        run_listener(cfg)
    except KeyboardInterrupt:
        console.print("\n[dim]bye[/dim]")


@cli.group()
def model() -> None:
    """Manage whisper.cpp models."""


@model.command("download")
@click.argument("name", type=click.Choice(list(WHISPER_MODELS)))
def model_download(name: str) -> None:
    """Download a whisper.cpp model into the configured models_dir."""
    cfg = load_config()
    target_dir = cfg.paths.models_dir_path
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"ggml-{name}.bin"
    if target.exists():
        console.print(f"[yellow]already exists:[/yellow] {target}")
        return
    url = WHISPER_MODELS[name]
    console.print(f"downloading {name} → {target}")
    _download(url, target)
    console.print(f"[green]✔[/green] {target}")


def _download(url: str, target: Path) -> None:
    """Stream download with progress dots."""
    req = urllib.request.Request(url, headers={"User-Agent": "laptop-dictation/0.1"})
    with urllib.request.urlopen(req) as resp, target.open("wb") as f:
        total = int(resp.headers.get("content-length", 0))
        written = 0
        chunk = 1 << 20
        while True:
            buf = resp.read(chunk)
            if not buf:
                break
            f.write(buf)
            written += len(buf)
            if total:
                pct = int(100 * written / total)
                sys.stderr.write(f"\r  {pct:3d}%  {written/1e6:.1f}/{total/1e6:.1f} MB")
                sys.stderr.flush()
    sys.stderr.write("\n")


@cli.command()
def doctor() -> None:
    """Diagnose setup: ffmpeg, whisper-cli, model file, permissions."""
    import shutil as _sh
    cfg = load_config()
    t = Table(title="laptop-dictation doctor")
    t.add_column("check"); t.add_column("status"); t.add_column("note")

    def row(label, ok, note=""):
        t.add_row(label, "[green]ok[/green]" if ok else "[red]missing[/red]", note)

    ff = _sh.which("ffmpeg")
    row("ffmpeg", bool(ff), ff or "brew install ffmpeg")

    wcpp = Path(cfg.paths.whisper_cpp)
    if not wcpp.exists():
        wcpp_fallback = _sh.which("whisper-cli") or _sh.which("whisper-cpp")
        row("whisper-cli", bool(wcpp_fallback),
            wcpp_fallback or "brew install whisper-cpp; or set paths.whisper_cpp")
    else:
        row("whisper-cli", True, str(wcpp))

    mp = cfg.model_file()
    row(f"model ({cfg.transcription.model})", mp.exists(),
        str(mp) if mp.exists() else f"dictate model download {cfg.transcription.model}")

    try:
        import pynput  # noqa: F401
        row("pynput", True)
    except ImportError:
        row("pynput", False, "pip install pynput")

    console.print(t)


if __name__ == "__main__":
    cli()
