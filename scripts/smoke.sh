#!/usr/bin/env bash
# laptop-dictation smoke test: tests + doctor + (if model present) one-shot transcription
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ ! -d .venv ]; then
  echo "▸ creating venv (one time, ~30 s)"
  /usr/local/bin/python3.12 -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet -e ".[dev]"
fi

echo
echo "════════════════════════════════════════════════════════════════"
echo "  laptop-dictation smoke test"
echo "════════════════════════════════════════════════════════════════"
echo

echo "▸ pytest (16 tests)"
./.venv/bin/pytest -q --tb=short
echo

echo "▸ dictate doctor"
./.venv/bin/dictate doctor
echo

# Detect whether the doctor table flagged anything as missing
status="$(./.venv/bin/dictate doctor 2>&1 || true)"
if echo "$status" | grep -q "missing"; then
  echo "✗ doctor shows missing pieces. Fix the 'missing' rows above before running 'dictate once':"
  echo "      brew install whisper-cpp"
  echo "      ./.venv/bin/dictate model download small"
  echo "      System Settings → Privacy & Security → Microphone (grant your terminal)"
  exit 0
fi

echo "▸ all green. Try 'dictate once' to record 5s and transcribe."
echo "✓ done."
