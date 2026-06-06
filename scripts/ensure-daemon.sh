#!/bin/bash
# ensure-daemon.sh — idempotent: start the dictation daemons if not running.
#
# Two daemons, same trusted-terminal mechanism:
#   • `dictate listen`  — ctrl+3 push-to-talk → transcript PASTED at the cursor
#   • `dictate command` — ctrl+0 push-to-talk → spoken command applied LIVE
#                         (e.g. "notch white" recolors the ledge notch instantly)
#
# WHY TERMINAL-SPAWNED, NOT LAUNCHD: macOS TCC attributes Accessibility / Input
# Monitoring / Microphone to the daemon's *responsible process*. Spawned from a
# terminal (Terminal.app / iTerm / VS Code / Ghostty — apps you've already
# granted and that macOS honors), the daemon inherits a trusted identity: the
# active event tap (chord-key suppression), synthetic cmd+V paste, and ffmpeg
# mic capture all work. Spawned from launchd via an ad-hoc-signed wrapper app,
# the System Settings toggles show ON but are NOT honored (AXIsProcessTrusted()
# returns False from the granted app itself — verified on macOS 26).
#
# Install: add to ~/.zshrc —
#   case "$TERM_PROGRAM" in
#     Apple_Terminal|iTerm.app|vscode)
#       (~/.local/share/laptop-dictation/ensure-daemon.sh >/dev/null 2>&1 &)
#       ;;
#   esac
# Each daemon nohup+disowns (PPID 1, survives the shell) and self-heals on every
# new terminal window — including the first one after a reboot.
#
# Logs: ~/Library/Logs/laptop-dictation.log (daemon trace; first line shows
#       AXIsProcessTrusted) and laptop-dictation.out.log (stdout/stderr).

DICTATE="$HOME/.local/share/laptop-dictation/venv/bin/dictate"
OUT_LOG="$HOME/Library/Logs/laptop-dictation.out.log"
LOG="$HOME/Library/Logs/laptop-dictation.log"

[ -x "$DICTATE" ] || exit 0

# ensure_daemon <subcommand> [extra args...]
# Health-check, NOT just liveness. A daemon spawned from an untrusted context
# (a terminal that lost its grant, or a headless overnight run) comes up
# AXIsProcessTrusted=False: its active tap is killed by macOS every ~2s, so the
# chord never suppresses — yet pgrep still sees it "running". So: if the running
# pid self-reported untrusted, REPLACE it from this (trusted) shell.
ensure_daemon() {
    local sub="$1"; shift
    local match="laptop-dictation/venv/bin/dictate $sub"
    local pid
    pid="$(pgrep -f "$match" | head -1)"
    if [ -n "$pid" ]; then
        if grep -q "AXIsProcessTrusted=False pid=$pid" "$LOG" 2>/dev/null; then
            kill "$pid" 2>/dev/null            # untrusted → tap dead-loops → replace
            for _ in 1 2 3 4 5; do
                pgrep -qf "$match" || break
                sleep 0.3
            done
        else
            return 0                           # trusted, or too fresh to have logged — leave it
        fi
    fi
    nohup "$DICTATE" "$sub" "$@" >> "$OUT_LOG" 2>&1 &
    disown
}

ensure_daemon listen
ensure_daemon command --hotkey ctrl+0
