"""Push-to-talk hotkey daemon. Hold the configured key → record. Release → transcribe.

Requires Accessibility permission on macOS (System Settings → Privacy & Security →
Accessibility, add Terminal/iTerm).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from rich.console import Console

from .config import Config
from .output import copy_to_clipboard, send_paste_keystroke
from .recorder import start_recording, stop_recording
from .transcribe import build_backend

console = Console()


def _resolve_pynput_key(name: str):
    """Map config key names to pynput Key/KeyCode."""
    from pynput.keyboard import Key
    name = name.strip().lower()
    if hasattr(Key, name):
        return getattr(Key, name)
    # Single character key
    if len(name) == 1:
        return name
    raise ValueError(f"Unknown hotkey: {name!r}")


def run_listener(cfg: Config) -> None:
    """Block forever. Hold-to-record, release-to-transcribe."""
    from pynput.keyboard import Listener

    target_key = _resolve_pynput_key(cfg.hotkey.key)
    backend = build_backend(
        cfg.transcription.backend,
        whisper_cpp_binary=cfg.paths.whisper_cpp,
        models_dir=cfg.paths.models_dir_path,
    )

    state: dict = {"proc": None, "wav": None, "pressed": False, "lock": threading.Lock()}

    def begin():
        with state["lock"]:
            if state["proc"] is not None:
                return
            console.print("[bold red]● REC[/bold red]")
            proc, wav = start_recording(cfg.recording.device, cfg.recording.sample_rate)
            state["proc"] = proc
            state["wav"] = wav

    def end():
        with state["lock"]:
            proc = state["proc"]
            wav: Path | None = state["wav"]
            state["proc"] = None
            state["wav"] = None
        if proc is None or wav is None:
            return
        stop_recording(proc)
        console.print("[dim]transcribing…[/dim]")
        try:
            result = backend.transcribe(wav, model=cfg.transcription.model, language=cfg.transcription.language)
        except Exception as e:
            console.print(f"[red]transcription failed:[/red] {e}")
            return
        finally:
            wav.unlink(missing_ok=True)
        text = result.text
        if not text:
            console.print("[yellow](no speech detected)[/yellow]")
            return
        console.print(f"[green]✔[/green] {text}  [dim]({result.backend}, {result.duration_ms} ms)[/dim]")
        if cfg.output.copy_to_clipboard:
            copy_to_clipboard(text)
        if cfg.output.auto_paste:
            # tiny delay so the user's release keystroke doesn't collide
            time.sleep(0.08)
            send_paste_keystroke()

    def on_press(key):
        if key == target_key and not state["pressed"]:
            state["pressed"] = True
            begin()

    def on_release(key):
        if key == target_key and state["pressed"]:
            state["pressed"] = False
            end()

    console.print(
        f"[bold]laptop-dictation[/bold] listening. "
        f"Hold [cyan]{cfg.hotkey.key}[/cyan] to talk. ctrl-c to quit."
    )
    with Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()
