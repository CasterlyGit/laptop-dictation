"""Final-output side effects: clipboard copy + optional auto-paste keystroke."""

from __future__ import annotations

import platform
import subprocess


def copy_to_clipboard(text: str) -> None:
    """Cross-platform clipboard copy. Prefers pyperclip; falls back to pbcopy/xclip."""
    try:
        import pyperclip
        pyperclip.copy(text)
        return
    except (ImportError, Exception):
        pass
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["pbcopy"], input=text.encode(), check=False)
    elif system == "Linux":
        for cmd in (["xclip", "-selection", "clipboard"], ["xsel", "-b"], ["wl-copy"]):
            try:
                subprocess.run(cmd, input=text.encode(), check=True)
                return
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue
    elif system == "Windows":
        subprocess.run(["clip"], input=text.encode("utf-16-le"), check=False)


def read_clipboard() -> str | None:
    """Read current clipboard text (for preserve-and-restore around auto-paste).

    Returns None when the clipboard can't be read or holds non-text content —
    callers skip restoration in that case rather than clobber it with "".
    """
    try:
        import pyperclip
        text = pyperclip.paste()
        return text if text else None
    except Exception:
        pass
    if platform.system() == "Darwin":
        try:
            r = subprocess.run(["pbpaste"], capture_output=True, timeout=2)
            text = r.stdout.decode(errors="replace")
            return text if text else None
        except (OSError, subprocess.TimeoutExpired):
            return None
    return None


def send_paste_keystroke() -> None:
    """Send cmd+V (macOS) / ctrl+V (others) via pynput. Requires Accessibility on macOS."""
    try:
        from pynput.keyboard import Controller, Key
    except ImportError:
        return
    kb = Controller()
    modifier = Key.cmd if platform.system() == "Darwin" else Key.ctrl
    with kb.pressed(modifier):
        kb.press("v")
        kb.release("v")


def send_enter_keystroke() -> None:
    """Send Enter via pynput. Used to auto-submit after paste."""
    try:
        from pynput.keyboard import Controller, Key
    except ImportError:
        return
    kb = Controller()
    kb.press(Key.enter)
    kb.release(Key.enter)
