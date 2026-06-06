"""Parsing tests for the voice-command bridge (dictate.command).

Pure parsing only — no mic, no notification center. Covers the phrasings a
real dictation will throw at "make the notch <color>".
"""

import pytest

from dictate.command import parse_notch_color


@pytest.mark.parametrize(
    "utterance,expected",
    [
        ("notch white", "white"),
        ("make the notch white", "white"),
        ("make the notch white.", "white"),
        ("Make the notch white.", "white"),
        ("turn the notch white", "white"),
        ("set the notch to white", "white"),
        ("change the notch to electric blue", "electric blue"),
        ("notch electric blue", "electric blue"),
        ("please make the notch red", "red"),
        ("ok make the ledge cyan", "cyan"),
        ("notch #0af", "#0af"),
        ("make the notch reset", "reset"),
        ("notch to green", "green"),
        ("color the notch purple", "purple"),
    ],
)
def test_parses_color(utterance, expected):
    assert parse_notch_color(utterance) == expected


@pytest.mark.parametrize(
    "utterance",
    [
        "",
        "what time is it",
        "open the terminal",
        "hello there how are you",
    ],
)
def test_non_commands_return_none(utterance):
    assert parse_notch_color(utterance) is None


def test_color_first_phrasing():
    # "white notch" — color precedes the noun
    assert parse_notch_color("white notch") == "white"


@pytest.mark.parametrize(
    "utterance",
    [
        "make the notch bigger",
        "make the notch smaller",
        "add an arrow inside the notch",
        "add a small globe at the bottom left of the notch with live time",
        "put a crop icon in the notch",
    ],
)
def test_notch_non_color_is_not_fast_path(utterance):
    # These are real work (geometry / new features), NOT a color tweak — they
    # must fall through (None) so handle() routes them to Conductor.
    assert parse_notch_color(utterance) is None


def test_handle_routes_non_color_to_caster(monkeypatch):
    import dictate.command as cmd

    sent = {}

    def fake_send(text, sock_path=None):
        sent["text"] = text
        return True

    monkeypatch.setattr(cmd, "send_to_conductor", fake_send)
    out = cmd.handle("add a globe to the notch with live time")
    assert out == "caster: add a globe to the notch with live time"
    assert sent["text"] == "add a globe to the notch with live time"


def test_send_to_conductor_sends_caster_run_and_waits_for_ack(tmp_path):
    """The frame must be op:caster.run and the client must block for the ack
    (fire-and-forget raced the replay and got silently dropped — the original
    '⌃0 does nothing' bug)."""
    import json
    import socket
    import tempfile
    import threading

    import dictate.command as cmd

    # macOS tmp_path is too deep for AF_UNIX's 104-byte sun_path — use /tmp.
    sock_path = tempfile.mktemp(suffix=".sock", dir="/tmp")
    got = {}
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock_path)
    srv.listen(1)

    def server():
        conn, _ = srv.accept()
        buf = b""
        while b"\n" not in buf:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
        got["msg"] = json.loads(buf.split(b"\n")[0])
        conn.sendall(b'{"ok": true, "ctrl": "control.stage"}\n')
        conn.close()

    t = threading.Thread(target=server, daemon=True)
    t.start()
    assert cmd.send_to_conductor("test the entrance", sock_path=sock_path) is True
    t.join(timeout=3)
    srv.close()
    assert got["msg"]["ctrl"] == "control.stage"
    assert got["msg"]["payload"]["op"] == "caster.run"
    assert got["msg"]["payload"]["utterance"] == "test the entrance"


def test_handle_color_takes_fast_path(monkeypatch):
    import dictate.command as cmd

    monkeypatch.setattr(cmd, "post_notch_color", lambda c: True)
    # must NOT touch conductor for a plain color
    monkeypatch.setattr(
        cmd, "send_to_conductor",
        lambda *a, **k: pytest.fail("color should not reach conductor"))
    assert cmd.handle("notch white") == "notch → white"


def test_handle_reports_unreachable_when_daemon_down(monkeypatch):
    import dictate.command as cmd

    monkeypatch.setattr(cmd, "send_to_conductor", lambda *a, **k: False)
    assert cmd.handle("open the terminal") == "unreachable: open the terminal"


def test_send_to_conductor_missing_socket_is_false(tmp_path):
    from dictate.command import send_to_conductor

    missing = str(tmp_path / "nope.sock")
    assert send_to_conductor("anything", sock_path=missing) is False
