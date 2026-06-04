# laptop-dictation

**[▶ Live demo](https://casterlygit.github.io/laptop-dictation/)** — interactive: hold the mic button, see a live waveform, release for a transcribed result in a clipboard-style box.

> Hold a hotkey, speak, get the text in your clipboard. Local Whisper, no cloud round-trip. Built so I can brainstorm with Claude Code on my laptop the same way I do on my phone.

**Status:** v0.4 — Wispr-Flow-style insertion: hold `ctrl+3`, speak, release — the text lands wherever your cursor is. Works on macOS (Apple Silicon, Intel). Linux is best-effort.

> **New in v0.4:** **system-wide key suppression** for chord hotkeys. Terminals map `ctrl+3` → ESC — which would interrupt a running Claude Code session. The daemon now swallows the chord's non-modifier keys at the Quartz event-tap level while push-to-talk is held, so nothing leaks into the focused app. Plus: transcription moved off the event-tap thread (keyboard can never freeze), a `min_hold_ms` accidental-tap guard, sound cues, and whisper vocab `prompt` + greedy `beam_size` for ~2× faster CPU decoding.
>
> **v0.3:** chord hotkeys like `ctrl+shift+l`. Hold all the keys at once to record, release any one to stop. Combine with `auto_paste` + `auto_submit` for a true voice interface to Claude Code / any chat box.

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

### Always-on daemon (macOS): spawn from your terminal, not launchd

macOS TCC attributes Accessibility/Input-Monitoring/Microphone to the daemon's
*responsible process*. Launched from a terminal you've already granted
(Terminal, iTerm, VS Code), everything works. Launched from launchd via an
ad-hoc-signed wrapper app, the System Settings toggles show ON but are **not
honored** — the active tap and synthetic paste silently fail. The reliable
pattern is a tiny idempotent hook in `~/.zshrc`:

```sh
case "$TERM_PROGRAM" in
  Apple_Terminal|iTerm.app|vscode)
    (~/.local/share/laptop-dictation/ensure-daemon.sh >/dev/null 2>&1 &)
    ;;
esac
```

See `scripts/ensure-daemon.sh`. The daemon detaches (survives the shell) and
self-heals on every new terminal window — including the first one after a
reboot.

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
key = "ctrl+3"         # single key (pynput name) — e.g. "alt_r", "ctrl_r", "f9"
                       # or a chord with "+": "ctrl+3", "ctrl+shift+l", "cmd+opt+space"
min_hold_ms = 250      # discard recordings shorter than this (accidental taps)

[recording]
sample_rate = 16000
device = "default"     # macOS: "AVFoundation default", or device index

[transcription]
backend = "whisper-cpp"   # whisper-cpp | openai
model = "small"           # tiny | base | small | medium | large (.en variants: faster, English-only)
language = "en"           # ISO code; "auto" for detection
beam_size = 0             # 1 = greedy decode (~2x faster on CPU); 0 = engine default
prompt = ""               # vocabulary bias, e.g. "Claude Code, pytest, MCP" — fixes jargon misses

[output]
copy_to_clipboard = true
auto_paste = false        # also send cmd+V after copying — text lands at the cursor
auto_submit = false       # press Enter after paste (great for Claude Code / chat boxes)
submit_delay_ms = 40      # gap between paste and Enter
sound_cues = false        # Pop on REC start, Basso on failure (headless REC feedback)
preserve_clipboard = false # restore the previous clipboard after auto-paste

[paths]
whisper_cpp = "/opt/homebrew/bin/whisper-cli"
models_dir = "~/.cache/whisper-cpp"
```

### Picking a model for your hardware

Whisper latency is what makes dictation feel instant or broken. Measured on an
Intel i5-1038NG7 (2020 13" MBP) with an 8-second utterance:

| model · settings | wall time | verdict |
|---|---|---|
| `small`, defaults | ~28 s | unusable on Intel |
| `base.en`, `beam_size = 1` | ~9.5 s | borderline |
| `tiny.en`, `beam_size = 1` + vocab `prompt` | **~3 s** | ships — jargon stays correct via the prompt |

On Apple Silicon, `small` runs ~10× faster and is the better default. The vocab
`prompt` is the cheap accuracy lever: `tiny.en` alone wrote "pie test"; with
`prompt = "Claude Code, pytest, …"` it writes "pytest".

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

### Chord hotkeys (v0.3+)

Combine modifiers with `+` to require multiple keys held simultaneously:

```toml
[hotkey]
key = "ctrl+shift+l"   # hold all three at once to record; release any to stop
```

Generic modifier names (`ctrl`, `shift`, `alt`/`opt`, `cmd`) accept either left or right variant. Use a specific variant (`shift_r`, `alt_l`) to pin one side. Aliases: `option`→`alt`, `command`/`meta`/`super`→`cmd`.

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

- [x] Direct Claude Code integration — `ctrl+3` pastes into the active terminal, ESC suppressed (v0.4)
- [ ] Inline punctuation (whisper.cpp doesn't add commas reliably for streamed audio)
- [ ] Visual feedback (menu bar icon shows REC state — sound cues shipped in v0.4)
- [ ] Windows support
- [ ] Streaming transcription (start writing before you stop talking)

## Companion projects

- [emergency-ai](https://github.com/CasterlyGit/emergency-ai) — same author. Voice input there will reuse this tool's recording + transcription layer.
