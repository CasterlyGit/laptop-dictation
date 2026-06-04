"""Push-to-talk hotkey daemon. Hold the configured key(s) → record. Release → transcribe.

Supports single keys (`alt_r`, `f9`) and chord hotkeys (`ctrl+shift+l`, `ctrl+3`).
For chords, recording begins when all keys in the chord are held simultaneously
and ends as soon as any one of them is released.

On macOS the non-modifier keys of a chord are *suppressed* while the chord is
active, so e.g. `ctrl+3` never leaks an ESC into the focused terminal (terminals
map ctrl+3 → ESC, which would interrupt a running Claude Code session). This uses
an active Quartz event tap via pynput's `darwin_intercept`.

Threading model: the event-tap callbacks must return in microseconds — an active
(suppressing) tap that blocks freezes *all* keyboard input until macOS disables
the tap (~1 s). So callbacks only mutate the held-set and enqueue jobs; recording
start/stop, transcription, and pasting all happen on a single worker thread.

Requires Accessibility permission on macOS (System Settings → Privacy & Security →
Accessibility). The deployed daemon inherits it from LaptopDictation.app.
"""

from __future__ import annotations

import os
import platform
import queue
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console

import re

from .config import Config
from .output import copy_to_clipboard, read_clipboard, send_enter_keystroke, send_paste_keystroke
from .recorder import start_recording, stop_recording
from .transcribe import build_backend

console = Console()

LOG_PATH = Path("~/Library/Logs/laptop-dictation.log").expanduser()


_LOG_MAX_BYTES = 5 * 1024 * 1024  # trim head when exceeded — no newsyslog config needed


def _log(msg: str) -> None:
    """Append to the daemon log. The .app wrapper detaches stdout, so this file
    is the only diagnosable trace when running headless under launchd."""
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > _LOG_MAX_BYTES:
            LOG_PATH.write_bytes(LOG_PATH.read_bytes()[-2 * 1024 * 1024:])
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")
    except OSError:
        pass


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

#: Every name a modifier slot can contain — used to tell modifier slots apart
#: from regular-key slots when deciding what to suppress.
_MODIFIER_NAMES: frozenset[str] = frozenset().union(*_MODIFIER_ALIASES.values())

#: macOS ANSI virtual keycodes for the printable keys we may need to match or
#: suppress. vk-first matching makes chord detection immune to the character
#: mangling that modifiers cause (ctrl+key often reports a control char, not
#: the key's own character). US-ANSI layout.
_DARWIN_VK_TO_NAME: dict[int, str] = {
    0: "a", 1: "s", 2: "d", 3: "f", 4: "h", 5: "g", 6: "z", 7: "x",
    8: "c", 9: "v", 11: "b", 12: "q", 13: "w", 14: "e", 15: "r",
    16: "y", 17: "t", 18: "1", 19: "2", 20: "3", 21: "4", 22: "6",
    23: "5", 25: "9", 26: "7", 28: "8", 29: "0", 31: "o", 32: "u",
    34: "i", 35: "p", 37: "l", 38: "j", 40: "k", 45: "n", 46: "m",
    # punctuation — without these a chord like ctrl+= silently never matches
    # (ctrl mangles the char and there's no vk to fall back on)
    24: "=", 27: "-", 30: "]", 33: "[", 39: "'", 41: ";", 42: "\\",
    43: ",", 44: "/", 47: ".", 50: "`",
}
_DARWIN_NAME_TO_VK: dict[str, int] = {v: k for k, v in _DARWIN_VK_TO_NAME.items()}


def parse_hotkey(spec: str) -> list[frozenset[str]]:
    """Parse a hotkey spec like 'alt_r' or 'ctrl+3' into a list of slots.

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

    On macOS, prefer the virtual keycode over the reported character: with a
    modifier held the event's character is often a control code ('3' under
    ctrl can arrive as something other than '3'), but the vk never lies.
    Returns None for keys we can't represent (dead keys, etc).
    """
    from pynput.keyboard import Key, KeyCode
    if isinstance(key, Key):
        return key.name
    if isinstance(key, KeyCode):
        if platform.system() == "Darwin" and key.vk in _DARWIN_VK_TO_NAME:
            return _DARWIN_VK_TO_NAME[key.vk]
        if key.char:
            return key.char.lower()
        if key.vk is not None:
            return f"vk{key.vk}"
    return None


def chord_satisfied(slots: list[frozenset[str]], held: set[str]) -> bool:
    """True iff every slot has at least one of its acceptable names in `held`."""
    return all(any(name in held for name in slot) for slot in slots)


#: whisper emits bracketed non-speech markers for silence/noise — never paste
#: them: "[BLANK_AUDIO]", "[ Silence ]", "(wind blowing)", "*music*", "♪ ♪"…
_NON_SPEECH_RE = re.compile(r"\[[^\]]*\]|\([^)]*\)|\*[^*]*\*|♪[^♪]*♪?")


def clean_transcript(text: str) -> str:
    """Strip whisper's non-speech markers; returns "" for pure silence/noise."""
    return _NON_SPEECH_RE.sub("", text).strip()


def suppress_vks(slots: list[frozenset[str]]) -> set[int]:
    """macOS virtual keycodes of the chord's *non-modifier* keys.

    These are the keys that would leak a character (or worse — ctrl+3 is ESC in
    terminals) into the focused app while push-to-talk is held, so the event tap
    swallows them whenever the full chord is down. Modifier keys pass through:
    a bare ctrl/shift/cmd press is inert in every app.
    """
    from pynput.keyboard import Key
    vks: set[int] = set()
    for slot in slots:
        if slot & _MODIFIER_NAMES:
            continue
        for name in slot:
            vk = _DARWIN_NAME_TO_VK.get(name)
            if vk is None and hasattr(Key, name):
                vk = getattr(Key, name).value.vk
            if vk is not None:
                vks.add(vk)
    return vks


def should_suppress(
    slots: list[frozenset[str]],
    suppressed_now: set[int],
    held: set[str],
    vk: int,
    is_down: bool,
) -> bool:
    """Pure suppression decision for one key event of a suppressible vk.

    Key-down: swallow iff the full chord is held (the event's own key included —
    on_press has already added it, but we re-add defensively so the decision
    does not depend on callback ordering). Key-up: swallow iff we swallowed the
    matching key-down, so apps never see an orphan key-up.
    """
    name = _DARWIN_VK_TO_NAME.get(vk, f"vk{vk}")
    if is_down:
        return chord_satisfied(slots, held | {name})
    return vk in suppressed_now


def _make_darwin_intercept(slots: list[frozenset[str]], state: dict, vks: set[int]):
    """Build the Quartz-level intercept that suppresses the chord's regular keys.

    Runs inside the event-tap callback for every keyboard event system-wide:
    must stay allocation-light and NEVER block. Returning None swallows the
    event; returning the event passes it through unchanged.
    """
    import Quartz

    key_down = Quartz.kCGEventKeyDown
    key_up = Quartz.kCGEventKeyUp
    get_field = Quartz.CGEventGetIntegerValueField
    vk_field = Quartz.kCGKeyboardEventKeycode

    def intercept(event_type, event):
        if event_type != key_down and event_type != key_up:
            return event  # flagsChanged, tap-timeout notices, etc.
        vk = get_field(event, vk_field)
        if vk not in vks:
            return event
        if should_suppress(slots, state["suppressed_vks"], state["held"], vk, event_type == key_down):
            if event_type == key_down:
                state["suppressed_vks"].add(vk)
            else:
                state["suppressed_vks"].discard(vk)
            return None
        return event

    return intercept


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
        "started_at": 0.0,
        "held": set(),
        "suppressed_vks": set(),
        "suppress_failed": False,
        "tap": None,  # the active Quartz tap, set once the listener starts
        "lock": threading.Lock(),
    }
    jobs: queue.Queue[str] = queue.Queue()

    def sound(name: str) -> None:
        """Fire-and-forget UI sound cue (headless daemon has no visible REC state).
        Played quiet (-v 0.4) so the built-in mic barely picks it up — a loud cue
        at recording onset can make whisper hallucinate phantom words."""
        if not cfg.output.sound_cues:
            return
        try:
            subprocess.Popen(
                ["afplay", "-v", "0.4", f"/System/Library/Sounds/{name}.aiff"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass

    def frontmost_app():
        """The NSRunningApplication that holds focus right now, or None."""
        try:
            from AppKit import NSWorkspace
            return NSWorkspace.sharedWorkspace().frontmostApplication()
        except Exception:
            return None

    def paste_text() -> None:
        """Send cmd+V with the daemon's own event tap momentarily disabled.

        A process that posts synthetic keystrokes while holding an ACTIVE
        (suppressing) Quartz tap has those events mangled by its own tap — the
        cmd modifier is stripped and the paste silently does nothing (verified
        2026-06-04: separate-process paste lands, in-process paste does not).
        Disabling the tap for the ~80 ms of the paste avoids the self-capture;
        the user has already released the chord, so suppression isn't needed."""
        tap = state["tap"]
        if tap is not None:
            try:
                import Quartz
                Quartz.CGEventTapEnable(tap, False)
            except Exception:
                tap = None
        try:
            send_paste_keystroke()
            if cfg.output.auto_submit:
                time.sleep(cfg.output.submit_delay_ms / 1000.0)
                send_enter_keystroke()
        finally:
            if tap is not None:
                try:
                    import Quartz
                    Quartz.CGEventTapEnable(tap, True)
                except Exception:
                    pass

    def refocus(target) -> None:
        """If focus moved while we were transcribing, put it back on the app the
        user was dictating into before firing the paste keystroke."""
        if target is None:
            return
        try:
            from AppKit import NSApplicationActivateIgnoringOtherApps
            front = frontmost_app()
            if front is not None and front.processIdentifier() == target.processIdentifier():
                return
            target.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
            time.sleep(0.3)  # give the window server time to actually switch
            _log(f"focus moved during transcription — refocused {target.localizedName()} before paste")
        except Exception as e:
            _log(f"refocus failed: {e!r}")

    def begin():
        with state["lock"]:
            if state["proc"] is not None:
                return
            if state["suppress_failed"]:
                _log("WARNING: suppression=off (active tap failed) — chord keys leak to the focused app")
            console.print("[bold red]● REC[/bold red]")
            sound("Pop")
            proc, wav = start_recording(cfg.recording.device, cfg.recording.sample_rate)
            state["proc"] = proc
            state["wav"] = wav
            state["started_at"] = time.monotonic()

    def end():
        # Capture the paste target NOW — transcription takes seconds and the user
        # may alt-tab away; the text must land where they were dictating.
        target = frontmost_app() if cfg.output.auto_paste else None
        with state["lock"]:
            proc = state["proc"]
            wav: Path | None = state["wav"]
            held_ms = int((time.monotonic() - state["started_at"]) * 1000)
            state["proc"] = None
            state["wav"] = None
        if proc is None or wav is None:
            return
        stop_recording(proc)
        if held_ms < cfg.hotkey.min_hold_ms:
            console.print(f"[dim](tap too short — {held_ms} ms, discarded)[/dim]")
            _log(f"discarded: held {held_ms} ms < min {cfg.hotkey.min_hold_ms} ms")
            wav.unlink(missing_ok=True)
            return
        console.print("[dim]transcribing…[/dim]")
        try:
            result = backend.transcribe(
                wav, model=cfg.transcription.model, language=cfg.transcription.language,
                beam_size=cfg.transcription.beam_size, prompt=cfg.transcription.prompt,
            )
        except Exception as e:
            console.print(f"[red]transcription failed:[/red] {e}")
            _log(f"transcription failed: {e!r}")
            sound("Basso")
            return
        finally:
            wav.unlink(missing_ok=True)
        text = clean_transcript(result.text)
        if not text:
            console.print("[yellow](no speech detected)[/yellow]")
            _log(f"no speech (held {held_ms} ms, raw={result.text!r})")
            return
        console.print(f"[green]✔[/green] {text}  [dim]({result.backend}, {result.duration_ms} ms)[/dim]")
        _log(f"✔ {text!r} ({result.backend}, {result.duration_ms} ms, held {held_ms} ms)")
        prev_clip = read_clipboard() if cfg.output.preserve_clipboard else None
        if cfg.output.copy_to_clipboard or cfg.output.auto_paste:
            copy_to_clipboard(text)
        if cfg.output.auto_paste:
            refocus(target)
            time.sleep(0.08)
            paste_text()
            if prev_clip is not None:
                time.sleep(0.35)  # let the focused app consume the paste first
                copy_to_clipboard(prev_clip)

    def worker():
        while True:
            job = jobs.get()
            try:
                if job == "begin":
                    begin()
                elif job == "end":
                    end()
            except Exception as e:  # daemon must survive any one bad cycle
                console.print(f"[red]error:[/red] {e}")
                _log(f"worker error: {e!r}")
                sound("Basso")
                if job == "begin":
                    # begin() failed before recording started: clear the active
                    # latch or the next chord press would be silently ignored.
                    state["active"] = False

    threading.Thread(target=worker, daemon=True, name="dictate-worker").start()

    # Callbacks run inside the event-tap callback: set ops + queue put ONLY.
    def on_press(key):
        name = normalize_key(key)
        if name is None:
            return
        state["held"].add(name)
        if not state["active"] and chord_satisfied(slots, state["held"]):
            state["active"] = True
            jobs.put("begin")

    def on_release(key):
        name = normalize_key(key)
        if name is None:
            return
        state["held"].discard(name)
        if state["active"] and not chord_satisfied(slots, state["held"]):
            state["active"] = False
            jobs.put("end")

    listener_kwargs: dict = {}
    if platform.system() == "Darwin":
        vks = suppress_vks(slots)
        if vks:
            listener_kwargs["darwin_intercept"] = _make_darwin_intercept(slots, state, vks)

    if platform.system() == "Darwin":
        class _ResilientListener(Listener):
            """Stock pynput Listener + a handle on the Quartz tap.

            pynput 1.8.2 calls CGEventTapEnable exactly once; macOS disables the
            tap on every sleep/wake (kCGEventTapDisabledByTimeout) and pynput
            never re-arms it — the daemon would go silently deaf after a lid
            close. We capture the tap here so a watchdog thread can re-enable it.
            """

            def _create_event_tap(self):
                tap = super()._create_event_tap()
                self._dictate_tap = tap
                return tap

        listener_cls = _ResilientListener
    else:
        listener_cls = Listener

    def start_listener(kwargs: dict):
        lst = listener_cls(on_press=on_press, on_release=on_release, **kwargs)
        lst.start()
        lst.wait()  # blocks until the tap result is known
        if platform.system() == "Darwin" and getattr(lst, "_dictate_tap", None) is None:
            lst.stop()
            raise RuntimeError("event tap creation returned None — Accessibility/Input Monitoring revoked?")
        return lst

    console.print(
        f"[bold]laptop-dictation[/bold] listening. "
        f"Hold [cyan]{cfg.hotkey.key}[/cyan] to talk. ctrl-c to quit."
    )
    suppression = "on" if listener_kwargs else "off"
    if platform.system() == "Darwin":
        # Log trust state at startup: if False, this daemon was spawned from an
        # untrusted context (e.g. launchd + ad-hoc app) — the active tap and
        # paste will silently fail. Spawn it from a terminal instead.
        try:
            from ApplicationServices import AXIsProcessTrusted
            trusted = bool(AXIsProcessTrusted())
            _log(f"AXIsProcessTrusted={trusted} pid={os.getpid()}")
            if not trusted:
                _log("WARNING: not trusted — spawn from a terminal (Terminal/iTerm/VS Code), not launchd")
        except Exception as e:
            _log(f"AXIsProcessTrusted probe failed: {e!r}")
    _log(f"listening: hotkey={cfg.hotkey.key} suppression={suppression} "
         f"model={cfg.transcription.model} paste={cfg.output.auto_paste} submit={cfg.output.auto_submit}")

    try:
        listener = start_listener(listener_kwargs)
    except Exception as e:
        if not listener_kwargs:
            raise
        # The active (suppressing) tap needs Accessibility. If creation failed,
        # stay alive in listen-only mode rather than crash-looping under launchd
        # — dictation still works, the chord's key just leaks to the app.
        # begin() logs a WARNING on every recording while in this mode.
        console.print(f"[yellow]active tap failed ({type(e).__name__}: {e}); "
                      f"falling back to listen-only — no key suppression[/yellow]")
        _log(f"active tap failed ({type(e).__name__}: {e!r}); listen-only fallback, suppression=off")
        state["suppress_failed"] = True
        listener = start_listener({})

    state["tap"] = getattr(listener, "_dictate_tap", None)

    if platform.system() == "Darwin":
        def rearm_watchdog():
            import Quartz
            while listener.running:
                time.sleep(2.0)
                tap = getattr(listener, "_dictate_tap", None)
                try:
                    if tap is not None and not Quartz.CGEventTapIsEnabled(tap):
                        Quartz.CGEventTapEnable(tap, True)
                        _log("event tap was disabled (sleep/wake or timeout) — re-enabled")
                except Exception as e:
                    _log(f"tap re-arm failed: {e!r}")
                    return

        threading.Thread(target=rearm_watchdog, daemon=True, name="dictate-tap-rearm").start()

    # join() stays OUTSIDE the fallback try: a runtime exception from the tap
    # thread should crash the process (launchd KeepAlive restarts it with clean
    # state + suppression) rather than silently demote to listen-only mode.
    try:
        listener.join()
    finally:
        listener.stop()
