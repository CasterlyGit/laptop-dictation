"""Voice-command bridge: turn a dictated phrase into action.

Two paths, in priority order:

1. **Instant fast-path** (no agent, ~50 ms): a notch *color* utterance is a pure
   runtime tweak — ledge already listens for ``notch:<color>`` on a Darwin
   distributed notification and recolors a state variable with no rebuild. We
   keep that hardwired so "notch white" stays instant.

2. **Caster path** (everything else): ANY other utterance — "make the notch
   bigger", "open my gmail", or something with nothing to do with the notch at
   all — is sent to the Conductor daemon as a ``control.stage
   {op:"caster.run"}`` frame over its UDS bus socket (``~/.conductor/bus.sock``,
   newline-delimited JSON). ⌃0 is THE entrance to the Caster organism: the
   CasterDirector walks the whole body (brain → … → skin), lights the Stage
   rail up with directed views, performs actions instantly, edits code behind a
   diff-gate, and delegates anything else to the conductor's intent lanes. That
   is the "say anything, anywhere" path — it is intent-agnostic by construction.

   The frame is sent with HALF-CLOSE + ACK-WAIT: fire-and-forget writes raced
   the daemon's live-card replay (closing mid-replay poisons its reader and the
   control line was SILENTLY DROPPED — the original "⌃0 does nothing" bug). The
   daemon acks ``{"ok": ...}`` only after dispatch; we block on that ack.

The parsing of the color fast-path stays pure and unit-tested; the *posting*
(both the notch notification and the UDS line) is best-effort I/O that degrades
honestly (returns a status the caller can surface) and never raises.
"""

from __future__ import annotations

import json
import os
import re
import socket
import uuid

# ---------------------------------------------------------------------------
# Path 1 — instant notch-color fast-path (Darwin distributed notification).
# ---------------------------------------------------------------------------

# distributed-notification name ledge already observes for debug/live commands
LEDGE_DEBUG = "com.casterly.ledge.debug"

try:
    from Foundation import NSDistributedNotificationCenter

    _center = NSDistributedNotificationCenter.defaultCenter()
except Exception:  # pyobjc absent / not macOS
    _center = None

# leading verbs/fillers a dictation tends to prepend before "notch ..."
_FILLER = re.compile(
    r"^(please\s+|now\s+|hey\s+|ok(?:ay)?\s+|can you\s+|could you\s+|"
    r"make\s+|set\s+|turn\s+|change\s+|paint\s+|color\s+|colour\s+)+",
    re.IGNORECASE,
)
# the notch noun, with any article, and the trailing "to"/"into"
_NOTCH = re.compile(
    r"\b(the\s+)?(notch|ledge|shelf)\b\s*(to\s+|into\s+)?", re.IGNORECASE
)
# whisper often ends a short command with a period
_TRAIL = re.compile(r"[.!?,\s]+$")

# known color words — so we only fast-path actual COLOR utterances, not every
# sentence that happens to contain "notch" (those go to Conductor as real work).
_COLOR_WORDS = frozenset({
    "black", "white", "red", "green", "blue", "cyan", "electric", "neon",
    "teal", "yellow", "orange", "purple", "violet", "magenta", "pink",
    "gray", "grey", "reset", "default", "normal",
})


def parse_notch_color(transcript: str) -> str | None:
    """Extract the color phrase from a 'make the notch <color>' utterance.

    Returns the color string to hand ledge (e.g. "white", "electric blue",
    "#0af", "reset"), or None if this isn't a notch-*color* command — including
    notch commands that are clearly NOT about color ("make the notch bigger"),
    which must fall through to Conductor.
    """
    if not transcript:
        return None
    text = _TRAIL.sub("", transcript.strip())
    text = _FILLER.sub("", text).strip()
    m = _NOTCH.search(text)
    if not m:
        return None
    after = text[m.end():].strip()
    before = text[: m.start()].strip()
    color = after or before
    color = _FILLER.sub("", color).strip()
    color = re.sub(r"^(to|into|a|the|color|colour)\s+", "", color, flags=re.IGNORECASE).strip()
    if not color:
        return None
    # Only treat as a color fast-path if it actually names a color (or is a
    # #hex). Anything else ("bigger", "an arrow inside it", "a globe") is real
    # work → return None so handle() routes it to Conductor.
    head = color.split()[0].lower()
    if color.startswith("#") or head in _COLOR_WORDS:
        return color
    return None


def post_notch_color(color: str) -> bool:
    """Post 'notch:<color>' to ledge. Best-effort; False if no notif center."""
    if _center is None:
        return False
    try:
        _center.postNotificationName_object_userInfo_deliverImmediately_(
            LEDGE_DEBUG, f"notch:{color}", None, True
        )
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Path 2 — Conductor bus (the universal "say anything, anywhere" path).
# ---------------------------------------------------------------------------

# UDS bus socket the conductord daemon binds (conductor contracts.BUS_SOCK).
CONDUCTOR_SOCK = os.path.expanduser(
    os.environ.get("CONDUCTOR_BUS_SOCK", "~/.conductor/bus.sock")
)
# Stage extension envelope; op caster.run = the Caster organism entrance.
CTRL_STAGE = "control.stage"


def _utterance_id(text: str) -> str:
    """Stable-ish id for an utterance (matches conductord's _utterance_id shape)."""
    return "utt-" + uuid.uuid5(uuid.NAMESPACE_OID, text or "x").hex[:8]


def send_to_conductor(text: str, sock_path: str | None = None) -> bool:
    """Send the utterance into Caster as control.stage {op:"caster.run"}.

    Half-close + ack-wait (see module docstring — a plain sendall+close races
    the daemon's replay and gets SILENTLY DROPPED). Returns True once the
    daemon's {"ok": ...} ack arrives (or the 2 s window closes with the line
    written — daemon slow ≠ dropped); False if the daemon isn't reachable.
    Never raises — a down daemon must not crash the voice listener.
    """
    path = sock_path or CONDUCTOR_SOCK
    if not text or not os.path.exists(path):
        return False
    line = json.dumps({
        "ctrl": CTRL_STAGE,
        "payload": {"op": "caster.run", "utterance": text,
                    "utterance_id": _utterance_id(text)},
    }) + "\n"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(2.0)
            s.connect(path)
            s.sendall(line.encode("utf-8"))
            s.shutdown(socket.SHUT_WR)  # half-close: daemon still writes to us
            buf = b""
            import time as _time
            end = _time.monotonic() + 2.0
            while _time.monotonic() < end:
                try:
                    chunk = s.recv(4096)
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
                for ln in buf.split(b"\n"):
                    try:
                        if "ok" in json.loads(ln):
                            return True
                    except (ValueError, TypeError):
                        continue
        return True  # line written; ack lost in replay noise ≠ dropped
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Top-level sink.
# ---------------------------------------------------------------------------


def handle(transcript: str) -> str | None:
    """Top-level sink for the command daemon.

    Returns a short status string describing what happened:
      - "notch → <color>"  : instant color fast-path applied
      - "caster: <text>"   : routed into the Caster organism (caster.run)
      - "unreachable: <text>": Conductor down/socket missing — nothing happened
    Returns None only for an empty utterance.
    """
    text = (transcript or "").strip()
    if not text:
        return None

    # 1) Instant fast-path: notch color, no agent.
    color = parse_notch_color(text)
    if color is not None:
        post_notch_color(color)
        return f"notch → {color}"

    # 2) Everything else → the Caster organism (⌃0 is THE entrance — the body
    #    acts, edits behind a diff-gate, or delegates to conductor lanes).
    if send_to_conductor(text):
        return f"caster: {text}"
    return f"unreachable: {text}"
