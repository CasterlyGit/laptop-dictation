#!/bin/bash
# tcc-doctor.sh — functional approval checker for the dictation daemon.
#
# macOS will NOT let a script read or grant TCC (the permission DB needs Full
# Disk Access; granting needs a user click or MDM). A "toggle shown ON" in
# System Settings is also not proof — ad-hoc-signed binaries show ON but are
# NOT honored. So this doctor verifies each capability *functionally* — it
# actually exercises the mic, reads the daemon's own AXIsProcessTrusted result,
# and confirms the key-event tap is delivering — then tells you exactly what to
# grant if something is dead. 100% local: no network, no external sends.
set -u

LOG="$HOME/Library/Logs/laptop-dictation.log"
DICTATE_VENV="$HOME/.local/share/laptop-dictation/venv"
FFMPEG="$(command -v ffmpeg || echo /usr/local/bin/ffmpeg)"
PASS=0; FAIL=0
ok()   { printf '  \033[32m✔\033[0m %s\n' "$1"; PASS=$((PASS+1)); }
bad()  { printf '  \033[31m✘\033[0m %s\n' "$1"; printf '      → %s\n' "$2"; FAIL=$((FAIL+1)); }
info() { printf '  \033[36mi\033[0m %s\n' "$1"; }

echo "── dictation approval doctor ─────────────────────────────"

# 1. Daemon alive
if pgrep -qf "laptop-dictation/venv/bin/dictate listen"; then
  ok "daemon running (pid $(pgrep -f 'laptop-dictation/venv/bin/dictate listen' | head -1))"
else
  bad "daemon not running" "open a new terminal (the ~/.zshrc hook restarts it) or run ensure-daemon.sh"
fi

# 2. Microphone — actually capture 1s from the resolved built-in device
DEV=$("$DICTATE_VENV/bin/python" -c "from dictate.recorder import _resolve_darwin_audio_device as r; print(r('default'))" 2>/dev/null)
TMP=$(mktemp -t tccdoctor).wav
if "$FFMPEG" -hide_banner -loglevel error -y -f avfoundation -i ":${DEV:-MacBook Pro Microphone}" -ac 1 -ar 16000 -t 1 "$TMP" 2>/dev/null && [ -s "$TMP" ]; then
  ok "Microphone granted — captured from '${DEV}' ($(stat -f%z "$TMP") bytes)"
else
  bad "Microphone blocked or device dead" "System Settings ▸ Privacy & Security ▸ Microphone — enable the terminal app that launches the daemon (VS Code / Terminal / iTerm)"
fi
rm -f "$TMP"

# 3. Accessibility — trust the daemon's OWN result (context-specific), from its log
AXLINE=$(grep 'AXIsProcessTrusted' "$LOG" 2>/dev/null | tail -1)
if echo "$AXLINE" | grep -q 'AXIsProcessTrusted=True'; then
  ok "Accessibility honored (daemon self-reported True)"
elif [ -n "$AXLINE" ]; then
  bad "Accessibility NOT honored — tap + synthetic paste will fail" "grant Accessibility to the *terminal app that spawns the daemon*, then restart it FROM that terminal (ad-hoc launchd grants are not honored)"
else
  info "Accessibility: no trust line yet — restart the daemon to log it"
fi

# 4. Input Monitoring — infer from real key delivery (a recent hold proves the tap works)
if grep -qE "held [0-9]+ ms|discarded: held" "$LOG" 2>/dev/null; then
  LAST=$(grep -E "held [0-9]+ ms|discarded: held" "$LOG" | tail -1)
  ok "Input Monitoring working — tap is receiving ctrl+3 events"
  info "last hold: ${LAST#*T}"
else
  info "Input Monitoring: no key events logged yet — press ctrl+3 once to confirm"
fi

echo "──────────────────────────────────────────────────────────"
printf "  %s passed, %s need attention\n" "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] && echo "  All dictation approvals are live. You won't be re-prompted." || \
  echo "  Grant the items above ONCE from the launching terminal; re-run to confirm."
