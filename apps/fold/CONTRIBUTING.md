# Contributing to Fold

Small, focused changes are welcome. Keep the app free to build and usable offline.

1. Run `bash scripts/test-core.sh` for changes to HID decoding, motion, geometry, or audio.
2. Build with `bash scripts/build-app.sh` on macOS 14+.
3. For rendering, capture, or lifecycle changes, follow the relevant checks in [docs/VERIFICATION.md](docs/VERIFICATION.md).
4. Describe what you actually tested: compiler version, macOS version, Mac model, and behavior. A passing cloud build is not a physical sensor test.

Sensor compatibility reports should include the model identifier (`sysctl -n hw.model`), macOS version, and the status shown by Fold. Do not include serial numbers, desktop screenshots, or unrelated device identifiers.

New sound designs must be original, generated, or explicitly compatible with the MIT distribution. Do not extract sounds from another app or game. Keep volume bounded and stationary output silent.

The public development branch currently lives under `apps/fold` on the `fold` branch of `CasterlyGit/laptop-dictation`. Its package is standalone and can move into a dedicated repository without code changes.
