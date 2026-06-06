"""Optional, decoupled bridge: publish dictation state to the ledge notch HUD.

Stable contract (keeps laptop-dictation and ledge separable — either can ship
without the other):

    Darwin distributed notification
        name:   "com.casterly.ledge.status"
        object: "listening" | "transcribing" | "idle"

Any process may observe it; today that's the ledge notch app, which shows a
spinner + one word in the notch strip. If nothing is listening this is a no-op.
This module NEVER raises — dictation must work whether or not the notch is up.
"""

from __future__ import annotations

NOTIFICATION = "com.casterly.ledge.status"

try:
    from Foundation import NSDistributedNotificationCenter

    _center = NSDistributedNotificationCenter.defaultCenter()
except Exception:  # pyobjc absent / not macOS
    _center = None


def set_status(state: str) -> None:
    """Post the current dictation state. Best-effort; failures are swallowed."""
    if _center is None:
        return
    try:
        _center.postNotificationName_object_userInfo_deliverImmediately_(
            NOTIFICATION, state, None, True
        )
    except Exception:
        pass
