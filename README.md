# laptop-dictation

> Hold a hotkey, speak, get the text in your clipboard. Local Whisper, no cloud round-trip. Built so I can brainstorm with Claude Code on my laptop the same way I do on my phone.

**Status:** v0.2 — push-to-talk + **auto-submit into the focused app**. Works on macOS (Apple Silicon, Intel). Linux is best-effort.

> **New in v0.2:** turn on `auto_paste` + `auto_submit` and dictation becomes a true voice interface for Claude Code / chat boxes: hold the hotkey, talk, release — text is transcribed, pasted, and Enter is pressed for you.

---

## Why this exists

Dictation on phones is great. Typing kills the flow when you're trying to think out loud. macOS's built-in dictation is fine for one sentence but fumbles on technical vocab and long-form thinking. I wanted:

1. **Push-to-talk** — hold a key, talk, release. No "Hey computer". No five-second timeout that cuts you off mid-thought.
2. **Local** — Whisper running on my own machine. No API key, no network round-trip.
3. **Clipboard-paste pattern** — works in any app (Claude Code terminal, Obsidian, browser, anywhere `cmd+V` works).
4. **Decent on programming/Claude-jargon** — Whisper-small or Whisper-medium handles this far better than built-in dictation.

---

## How it works

```
[ hold hotkey ] ──▶ ffmpeg records mic to WAV
       │                       │
       │                       ▼
[ release hotkey ] ──▶ whisper-cli transcribes WAV
                               │
                               ▼
                       pyperclip → clipboard
                               │
                               ▼
                  (optional) auto-paste keystroke
```

- **Hotkey**: global, via `pynput`. Default: hold the Right Option key. Configurable in `~/.config/laptop-dictation/config.toml`.
- **Recording**: ffmpeg, AVFoundation on macOS, ALSA on Linux. Outputs 16 kHz mono WAV (the format Whisper expects).
- **Transcription**: pluggable backends. Default is `whisper.cpp` running locally (~250 ms for a 5-second clip on M2). OpenAI Whisper API is a fallback.
- **Paste**: by default the text lands on your clipboard. With `auto_paste = true` in the config, the tool also types `cmd+V` for you.

---

## Setup

```bash
# 1. Clone + install deps
git clone https://github.com/CasterlyGit/laptop-dictation.git
cd laptop-dictation
./scripts/setup.sh              # installs ffmpeg + whisper.cpp + python deps

# 2. macOS only: grant Accessibility + Microphone permissions
#    System Settings → Privacy & Security → Accessibility / Microphone
#    Add: Terminal (or whichever shell you run dictate from)

# 3. First-run config (writes ~/.config/laptop-dictation/config.toml)
dictate init

# 4. Test it
dictate once                    # records 5 seconds, transcribes, copies to clipboard

# 5. Start the daemon
dictate listen                  # holds the hotkey to record; ctrl-c to stop
```

## Usage

```bash
# Daemon mode — hold Right Option, talk, release. Text lands on clipboard.
dictate listen

# One-shot — useful for testing or for a non-hotkey integration
dictate once --seconds 10

# Override the model on the fly
dictate listen --model medium

# Use OpenAI's API instead of local whisper.cpp
dictate listen --backend openai

# Show your current config
dictate config
```

## Config file

`~/.config/laptop-dictation/config.toml`:

```toml
[hotkey]
key = "alt_r"          # pynput key name; e.g. "alt_r", "ctrl_r", "f9"

[recording]
sample_rate = 16000
device = "default"     # macOS: "AVFoundation default", or device index

[transcription]
backend = "whisper-cpp"   # whisper-cpp | openai
model = "small"           # tiny | base | small | medium | large
language = "en"           # ISO code; "auto" for detection

[output]
copy_to_clipboard = true
auto_paste = false        # also send cmd+V after copying
auto_submit = false       # press Enter after paste (great for Claude Code / chat boxes)
submit_delay_ms = 40      # gap between paste and Enter

[paths]
whisper_cpp = "/opt/homebrew/bin/whisper-cli"
models_dir = "~/.cache/whisper-cpp"
```

### Voice-driving Claude Code (or any chat box)

Set both flags on and pick a hotkey that doesn't conflict with your editor:

```toml
[hotkey]
key = "alt_r"             # hold right-option to talk

[output]
copy_to_clipboard = true
auto_paste = true
auto_submit = true
```

Now: focus the Claude chat box in VSCode → hold right-option → speak → release → message appears and sends. No keyboard, no clicks.

**Note for Mac users:** there's no "Windows" key on macOS. The available hold-keys are `alt_r` / `alt_l` (option), `ctrl_r` / `ctrl_l`, `cmd_r` / `cmd_l`, or function keys like `f9`. Pick one your editor doesn't capture.

## Models

- **tiny** — 75 MB, fastest, OK for clear speech. Use when speed matters.
- **base** — 142 MB, noticeably better on technical words.
- **small** — 466 MB, good default. ~250 ms per second of audio on M2.
- **medium** — 1.5 GB, best balance for programming / Claude vocabulary.
- **large** — 3 GB, slowest, marginal gain over medium.

The setup script downloads `small` by default. To switch:

```bash
dictate model download medium
```

## Why not the macOS built-in dictation?

I tried. It mangles "Claude", "MCP", "TypeScript", and any name with mixed case. It also has a hard 60-second cutoff and reformats your text mid-sentence. For long-form thinking-out-loud, it's a no.

## Roadmap

- [ ] Direct Claude Code integration (auto-paste into the active terminal)
- [ ] Inline punctuation (whisper.cpp doesn't add commas reliably for streamed audio)
- [ ] Visual feedback (menu bar icon shows REC state)
- [ ] Windows support
- [ ] Streaming transcription (start writing before you stop talking)

## Companion projects

- [emergency-ai](https://github.com/CasterlyGit/emergency-ai) — same author. Voice input there will reuse this tool's recording + transcription layer.
