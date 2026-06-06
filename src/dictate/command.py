"""Voice-command bridge: turn a dictated phrase into a live notch command.

Separate from the paste pipeline. The ctrl+0 daemon (`dictate command`) wires
its transcript sink here instead of pasting. We keep the *parsing* pure and
unit-tested; the *posting* reuses the same Darwin distributed-notification
contract that `notch.py` already speaks to ledge:

    name:   "com.casterly.ledge.debug"
    object: "notch:<color>"          # e.g. "notch:white", "notch:#0af", "notch:reset"

ledge resolves the color name itself (NamedColor.parse), so this side only has
to (a) recognise that the utterance is a notch-color command and (b) extract the
color words. Anything we don't recognise returns None so the caller can fall
back (today: just log + ignore).
"""

from __future__ import annotations

import re

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


def parse_notch_color(transcript: str) -> str | None:
    """Extract the color phrase from a 'make the notch <color>' utterance.

    Returns the color string to hand ledge (e.g. "white", "electric blue",
    "#0af", "reset"), or None if this isn't a notch-color command.
    """
    if not transcript:
        return None
    text = _TRAIL.sub("", transcript.strip())
    text = _FILLER.sub("", text).strip()
    m = _NOTCH.search(text)
    if not m:
        return None
    # color is whatever follows the notch noun (or, if the phrasing put the
    # color first — "white notch" — whatever preceded it)
    after = text[m.end():].strip()
    before = text[: m.start()].strip()
    color = after or before
    color = _FILLER.sub("", color).strip()
    color = re.sub(r"^(to|into|a|the|color|colour)\s+", "", color, flags=re.IGNORECASE).strip()
    return color or None


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


def handle(transcript: str) -> str | None:
    """Top-level sink for the command daemon. Returns the color it applied, or
    None if the utterance wasn't a recognised command (caller may log/ignore)."""
    color = parse_notch_color(transcript)
    if color is None:
        return None
    post_notch_color(color)
    return color
