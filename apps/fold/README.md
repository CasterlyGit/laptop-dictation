# Fold

**A little give in your screen. Free, open-source desktop bending for macOS.**

Close your MacBook lid and the desktop bends toward its hinge. Open it and everything settles back. Add a soft movement sound, a quiet open click, or keep it silent.

**Status: experimental 0.1.0.** Native build validation is in progress. Physical lid tracking, permissions, sleep/wake, and perceived audio latency require a real MacBook test before a stable release.

## What it does

- Captures the built-in display with ScreenCaptureKit and bends it using Metal.
- Adjustable perspective, progressive blur, shadow, and clear angle.
- Original procedural Elastic sound follows hinge speed and direction. Open click plays once when the screen clears. Both are optional.
- Menu bar controls, manual preview, and a global pause shortcut: **Control–Option–Command–F**. Escape pauses while Fold's controls are focused.
- Frames stay in memory. No accounts, API keys, analytics, servers, microphone, or desktop recording files.
- Sensor loss, capture errors, sleep, and session locking clear the overlay. Display changes pause the effect.

## Try it

Requires **macOS 14+**, Metal, and a supported lid sensor for the real effect. Preview works without a sensor or Screen Recording permission. Runtime probing decides support; a blanket “all Apple silicon” claim would be inaccurate. Some M1/M2 models expose no usable angle interface.

With the free Xcode Command Line Tools installed, open Terminal in this folder and run:

```sh
bash Install.command
```

The script builds the app locally, installs it to `~/Applications/Fold.app`, and opens it. No administrator password is required. If the tools are missing, install them with `xcode-select --install` and rerun the command.

Choose **Enable on my Mac**. Allow Screen Recording when macOS asks; if requested, quit and reopen Fold after granting it. The permission lets the effect redraw the desktop; the app has no recording or upload feature.

For the sample effect, drag the preview slider or choose **Play with sound**. Physical tracking remains off until you enable it. If no sensor is found, the menu has **Check sensor again**.

### Downloadable builds

Successful **Fold macOS** workflow runs produce a `Fold-macOS` artifact with an ad-hoc-signed universal app ZIP and its SHA-256 digest. These are experimental builds, not notarized releases. Local source builds are the zero-cost installation path. No paid Apple developer membership is needed to build locally.

## Development

```sh
bash scripts/test-core.sh        # C regression tests; macOS or Linux
bash scripts/build-app.sh        # native app; macOS only
FOLD_UNIVERSAL=1 bash scripts/build-app.sh
```

Open `Package.swift` in Xcode to edit. The distributable app needs its bundled resources, so use the build script to package it. There are no third-party package dependencies.

See [CONTRIBUTING.md](CONTRIBUTING.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and [docs/VERIFICATION.md](docs/VERIFICATION.md).

## Inspiration and licensing

[Bendy](https://trybendy.app/) by Adrian Abelarde inspired the effect. This is an independent implementation with its own UI, artwork, renderer, and synthesized audio. Bendy's code, sound files, branding, and demo media are not included.

Sam Gold's [LidAngleSensor](https://github.com/samhenrigold/LidAngleSensor) documents the sensor interface and model limitations. Fold uses the observed Apple VID `0x05AC`, PID `0x8104`, sensor usage page `0x20`, orientation usage `0x8A`, and feature report `1`. Its angle bytes encode whole degrees. Fold's reader is independently written.

**MIT licensed.** Use it, inspect it, change it, and share it. See [LICENSE](LICENSE).
