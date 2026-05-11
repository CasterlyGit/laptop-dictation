#!/usr/bin/env bash
# laptop-dictation — one-shot setup for macOS / Linux.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "▸ laptop-dictation setup"
echo "  repo: $REPO_ROOT"

# ---- 1. OS deps ----
OS="$(uname -s)"
case "$OS" in
  Darwin)
    if ! command -v brew >/dev/null 2>&1; then
      echo "  ✗ Homebrew not found. Install from https://brew.sh first." >&2
      exit 1
    fi
    for pkg in ffmpeg whisper-cpp; do
      if brew list --formula 2>/dev/null | grep -q "^${pkg}$"; then
        echo "  ✓ ${pkg} already installed"
      else
        echo "  ▸ brew install ${pkg}"
        brew install "${pkg}"
      fi
    done
    ;;
  Linux)
    if command -v apt-get >/dev/null 2>&1; then
      echo "  ▸ apt install ffmpeg (whisper.cpp via cargo / build-from-source)"
      sudo apt-get update -qq
      sudo apt-get install -y ffmpeg build-essential cmake
      if ! command -v whisper-cli >/dev/null 2>&1; then
        echo "  ▸ building whisper.cpp from source"
        tmp=$(mktemp -d)
        git clone --depth=1 https://github.com/ggerganov/whisper.cpp "$tmp/wcpp"
        (cd "$tmp/wcpp" && make -j) >/dev/null
        sudo install -m 0755 "$tmp/wcpp/main" /usr/local/bin/whisper-cli
        rm -rf "$tmp"
      fi
    else
      echo "  ✗ Unsupported Linux package manager. Install ffmpeg + whisper.cpp manually." >&2
    fi
    ;;
  *)
    echo "  ✗ Unsupported OS: $OS" >&2
    exit 1
    ;;
esac

# ---- 2. Python venv + deps ----
if [ ! -d ".venv" ]; then
  echo "  ▸ creating .venv"
  python3 -m venv .venv
fi
echo "  ▸ installing python deps"
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -e .

# ---- 3. Default config ----
./.venv/bin/dictate init >/dev/null
CFG="$HOME/.config/laptop-dictation/config.toml"
echo "  ✓ config at ${CFG}"

# ---- 4. Default model ----
MODELS_DIR="$HOME/.cache/whisper-cpp"
if [ ! -f "${MODELS_DIR}/ggml-small.bin" ]; then
  echo "  ▸ downloading whisper small model (~466 MB)"
  ./.venv/bin/dictate model download small
else
  echo "  ✓ small model already present"
fi

# ---- 5. macOS permission reminders ----
if [ "$OS" = "Darwin" ]; then
  cat <<EOF

  ! macOS only — grant these permissions to your shell app:
       System Settings → Privacy & Security → Microphone → (your terminal)
       System Settings → Privacy & Security → Accessibility → (your terminal)
     The first time you record, macOS will prompt; if you decline you'll need
     to add them manually under the settings paths above.
EOF
fi

cat <<EOF

  ✓ setup complete.

  Try:
       source .venv/bin/activate
       dictate doctor          # verify everything
       dictate once            # record 5s, transcribe, copy to clipboard
       dictate listen          # daemon — hold ${HOTKEY:-right-option} to talk

  Config:  ${CFG}
EOF
