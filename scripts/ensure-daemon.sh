#!/bin/bash
# ensure-daemon.sh — idempotent: start the dictation PTT daemon if not running.
#
# WHY TERMINAL-SPAWNED, NOT LAUNCHD: macOS TCC attributes Accessibility /
# Input Monitoring / Microphone to the daemon's *responsible process*. Spawned
# from a terminal (Terminal.app / iTerm / VS Code — apps you've already granted
# and that macOS honors), the daemon inherits a trusted identity: the active
# event tap (chord-key suppression), synthetic cmd+V paste, and ffmpeg mic
# capture all work. Spawned from launchd via an ad-hoc-signed wrapper app, the
# System Settings toggles show ON but are NOT honored (AXIsProcessTrusted()
# returns False from the granted app itself — verified on macOS 26).
#
# Install: add to ~/.zshrc —
#   case "$TERM_PROGRAM" in
#     Apple_Terminal|iTerm.app|vscode)
#       (~/.local/share/laptop-dictation/ensure-daemon.sh >/dev/null 2>&1 &)
#       ;;
#   esac
# The daemon nohup+disowns (PPID 1, survives the shell) and self-heals on
# every new terminal window — including the first one after a reboot.
#
# Logs: ~/Library/Logs/laptop-dictation.log (daemon trace; first line shows
#       AXIsProcessTrusted) and laptop-dictation.out.log (stdout/stderr).

DICTATE="$HOME/.local/share/laptop-dictation/venv/bin/dictate"
OUT_LOG="$HOME/Library/Logs/laptop-dictation.out.log"

# Already running? (match the venv path so unrelated processes don't count)
if pgrep -qf "laptop-dictation/venv/bin/dictate listen"; then
    exit 0
fi

[ -x "$DICTATE" ] || exit 0

nohup "$DICTATE" listen >> "$OUT_LOG" 2>&1 &
disown
