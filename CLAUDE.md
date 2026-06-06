# laptop-dictation

Push-to-talk dictation daemon: hold a hotkey → ffmpeg records mic → whisper.cpp transcribes → text pastes at the cursor. Status: v0.4 — ctrl+3 PTT with system-wide key suppression; runs as a terminal-spawned daemon (NOT launchd — see TCC note below).

## Key files
- `src/dictate/listener.py` — hotkey daemon: chord parsing, vk-first normalization, Quartz suppression intercept, worker-thread pipeline
- `src/dictate/recorder.py` — ffmpeg AVFoundation mic capture (16 kHz mono WAV)
- `src/dictate/transcribe.py` — whisper.cpp / Moonshine ONNX / OpenAI backends; beam_size + vocab prompt passthrough (whisper-only)
- `src/dictate/output.py` — clipboard copy/read, synthetic cmd+V / Enter
- `src/dictate/config.py` — `~/.config/laptop-dictation/config.toml` loader + defaults
- `src/dictate/cli.py` — `dictate init|once|listen|config|model download`
- `scripts/ensure-daemon.sh` — idempotent daemon starter for the ~/.zshrc hook (deployed copy: `~/.local/share/laptop-dictation/ensure-daemon.sh`)

## Architecture / patterns (do NOT break)
- **TCC requires a TERMINAL-spawned daemon, NOT launchd.** Verified 2026-06-04: an ad-hoc-signed app's Accessibility grant is *shown enabled in System Settings but NOT honored* (the app's own `AXIsProcessTrusted()` returns False). TCC keys Accessibility off the **responsible process**. Spawned from a terminal (Terminal/iTerm/VS Code — all granted + honored), the daemon inherits a trusted identity, so the active tap + synthetic paste + ffmpeg mic all work. Self-signed cert would fix launchd too, but trusting it needs interactive Touch ID. So: `ensure-daemon.sh` is invoked from a `~/.zshrc` hook; the daemon `nohup`+`disown`s (PPID 1, survives the shell) and self-heals on every new terminal.
- **Tap callbacks never block.** `darwin_intercept` makes the event tap ACTIVE — a blocked callback freezes all keyboard input until macOS kills the tap (~1 s) and suppression silently dies. on_press/on_release only mutate sets and enqueue; recording/transcription/paste run on the worker thread.
- **Paste must pause the daemon's own tap.** A process posting synthetic keystrokes while holding an ACTIVE tap has its own events mangled (cmd modifier stripped → paste does nothing). `paste_text()` does `CGEventTapEnable(tap, False)` around `send_paste_keystroke()`, then re-enables. Verified: separate-process paste lands, in-process-without-pause does not.
- **Suppression is correctness-critical.** Terminals map ctrl+3 → ESC, which interrupts Claude Code. The intercept swallows the chord's non-modifier vks (key-up swallowed iff its key-down was). Pure decision logic in `should_suppress()` — keep it pure, it's unit-tested.
- **vk-first key matching on macOS** (`_DARWIN_VK_TO_NAME`): under ctrl the event char is unreliable; the vk never lies. US-ANSI table.
- **Capture paste target at release, refocus before paste.** Transcription takes seconds; `end()` snapshots `frontmost_app()` at release and `refocus()`es it before pasting, so the text lands where dictation started even if focus drifted.
- **clean_transcript** strips whisper's non-speech markers (`[BLANK_AUDIO]`, `(wind)`, `*music*`, `♪`) so silence never pastes garbage.
- pynput 1.8.2 quirks (verified in source): on_press runs BEFORE intercept for the same event; no re-enable after `kCGEventTapDisabledByTimeout` → a watchdog thread re-arms the tap every 2 s (survives sleep/wake).

## Run / test
```bash
.venv/bin/python -m pytest -q                       # unit tests (pure logic, no tap)
dictate once --seconds 5                             # one-shot mic → text sanity check
# deploy to the live daemon (must run FROM A TERMINAL for TCC trust):
~/.local/share/laptop-dictation/venv/bin/pip install --force-reinstall --no-deps .
pkill -f "dictate listen"; ~/.local/share/laptop-dictation/ensure-daemon.sh
tail -f ~/Library/Logs/laptop-dictation.log         # trace; first line logs AXIsProcessTrusted
```

## Current state & active work
- LIVE: terminal-spawned daemon. `~/.zshrc` hook → `~/.local/share/laptop-dictation/ensure-daemon.sh` → `dictate listen` (nohup, PPID 1). Hotkey ctrl+3, auto_paste on, auto_submit off. **Verified end-to-end 2026-06-04** (acoustic: spoke → transcribed → pasted into TextEdit; AXIsProcessTrusted=True; tap re-arm spam=0).
- The old launchd agent + `~/Applications/LaptopDictation.app` wrapper are ABANDONED (ad-hoc TCC not honored; tried bash-exec stub, compiled exec launcher, compiled fork launcher, manual TCC re-adds, tccutil resets — all FALSE; self-signed cert blocked on interactive keychain auth). The full rationale lives in `scripts/ensure-daemon.sh`.
- Perf (Intel i5-1038NG7, benchmarked 2026-06-04): **moonshine base/int8 (the live config) = 0.87s for a 4.5s utterance (~0.18× realtime) vs whisper.cpp tiny.en 3.54s (4× faster), at better published WER.** Whisper pads every clip to 30s so it barely speeds up on short utterances; Moonshine scales with clip length. whisper.cpp numbers: tiny.en+greedy ≈ 0.45×; base.en ≈ 1.2×; small ≈ 3.5× (unusable). On Apple Silicon, whisper small would be fine.
- **Moonshine backend install caveat**: `useful-moonshine-onnx` hard-depends on librosa → numba, which does not build on Intel macs. Install with `pip install --no-deps useful-moonshine-onnx && pip install onnxruntime tokenizers huggingface_hub numpy` (librosa is only lazy-imported for path inputs; we pass numpy arrays). The official `moonshine-voice` C-lib wheel is arm64-only — unusable here; its v2 streaming models (small/medium-streaming, WER 6.65%) need an x86_64 source build of libmoonshine — that's the phase-2 streaming path.
- Moonshine models are English-only, ≤64s per call (backend chunks longer clips at quietest window), and ignore beam_size/prompt. Vocab prompt still applies to the whisper-cpp fallback ("pie test" → "pytest"); moonshine base got "PyTest" right natively in the bench.
- Daemon preloads the moonshine model on a warmup thread at startup (`moonshine model warm` in out.log) so the first dictation doesn't stall.
- Roadmap: streaming transcription (start decoding before release — Moonshine v2 streaming models via x86_64 libmoonshine build, partials → notch via existing ledge bridge), menu-bar REC indicator.
