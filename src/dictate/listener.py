"""Push-to-talk hotkey daemon. Hold the configured key(s) → record. Release → transcribe.

Supports single keys (`alt_r`, `f9`) and chord hotkeys (`ctrl+shift+l`).
For chords, recording begins when all keys in the chord are held simultaneously
and ends as soon as any one of them is released.

Requires Accessibility permission on macOS (System Settings → Privacy & Security →
Accessibility, add Terminal/iTerm).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from rich.console import Console

from .config import Config
from .output import copy_to_clipboard, send_enter_keystroke, send_paste_keystroke
from .recorder import start_recording, stop_recording
from .transcribe import build_backend

console = Console()


_MODIFIER_ALIASES: dict[str, frozenset[str]] = {
    "ctrl": frozenset({"ctrl", "ctrl_l", "ctrl_r"}),
    "control": frozenset({"ctrl", "ctrl_l", "ctrl_r"}),
    "shift": frozenset({"shift", "shift_l", "shift_r"}),
    "alt": frozenset({"alt", "alt_l", "alt_r"}),
    "opt": frozenset({"alt", "alt_l", "alt_r"}),
    "option": frozenset({"alt", "alt_l", "alt_r"}),
    "cmd": frozenset({"cmd", "cmd_l", "cmd_r"}),
    "command": frozenset({"cmd", "cmd_l", "cmd_r"}),
    "meta": frozenset({"cmd", "cmd_l", "cmd_r"}),
    "super": frozenset({"cmd", "cmd_l", "cmd_r"}),
    "win": frozenset({"cmd", "cmd_l", "cmd_r"}),
}


def parse_hotkey(spec: str) -> list[frozenset[str]]:
    """Parse a hotkey spec like 'alt_r' or 'ctrl+shift+l' into a list of slots.

    Each slot is a frozenset of normalized pynput key names that satisfy that
    slot. A generic 'shift' slot is satisfied by either 'shift_l' or 'shift_r';
    a specific 'shift_r' slot is satisfied only by 'shift_r'.
    """
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if not parts:
        raise ValueError(f"Empty hotkey spec: {spec!r}")
    slots: list[frozenset[str]] = []
    for p in parts:
        if p in _MODIFIER_ALIASES:
            slots.append(_MODIFIER_ALIASES[p])
        elif len(p) == 1 or p.startswith("f") and p[1:].isdigit():
            slots.append(frozenset({p}))
        elif _is_known_special(p):
            slots.append(frozenset({p}))
        else:
            raise ValueError(f"Unknown hotkey part: {p!r} (in spec {spec!r})")
    return slots


def _is_known_special(name: str) -> bool:
    """True if `name` is a pynput Key attribute (e.g. 'space', 'tab', 'alt_r')."""
    from pynput.keyboard import Key
    return hasattr(Key, name)


def normalize_key(key) -> str | None:
    """Normalize a pynput key event into a lowercase string we can match.

    Returns None for keys we can't represent (dead keys, etc).
    """
    from pynput.keyboard import Key, KeyCode
    if isinstance(key, Key):
        return key.name
    if isinstance(key, KeyCode):
        if key.char:
            return key.char.lower()
        if key.vk is not None:
            return f"vk{key.vk}"
    return None


def chord_satisfied(slots: list[frozenset[str]], held: set[str]) -> bool:
    """True iff every slot has at least one of its acceptable names in `held`."""
    return all(any(name in held for name in slot) for slot in slots)


def run_listener(cfg: Config) -> None:
    """Block forever. Hold-to-record, release-to-transcribe."""
    from pynput.keyboard import Listener

    slots = parse_hotkey(cfg.hotkey.key)
    backend = build_backend(
        cfg.transcription.backend,
        whisper_cpp_binary=cfg.paths.whisper_cpp,
        models_dir=cfg.paths.models_dir_path,
    )

    state: dict = {
        "proc": None,
        "wav": None,
        "active": False,
        "held": set(),
        "lock": threading.Lock(),
    }

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
            time.sleep(0.08)
            send_paste_keystroke()
            if cfg.output.auto_submit:
                time.sleep(cfg.output.submit_delay_ms / 1000.0)
                send_enter_keystroke()

    def on_press(key):
        name = normalize_key(key)
        if name is None:
            return
        state["held"].add(name)
        if chord_satisfied(slots, state["held"]) and not state["active"]:
            state["active"] = True
            begin()

    def on_release(key):
        name = normalize_key(key)
        if name is None:
            return
        state["held"].discard(name)
        if state["active"] and not chord_satisfied(slots, state["held"]):
            state["active"] = False
            end()

    console.print(
        f"[bold]laptop-dictation[/bold] listening. "
        f"Hold [cyan]{cfg.hotkey.key}[/cyan] to talk. ctrl-c to quit."
    )
    with Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()
