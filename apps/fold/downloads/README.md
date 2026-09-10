# Fold for macOS

[Download Fold-macOS.zip](https://raw.githubusercontent.com/CasterlyGit/laptop-dictation/fold/apps/fold/downloads/Fold-macOS.zip)

Experimental 0.1.0 · macOS 14 or later · universal Apple silicon / Intel binary · $0 · MIT license.

1. Unzip and move **Fold.app** to Applications.
2. Open the app. It is ad-hoc signed, not notarized; see the [installation notes](../README.md#downloadable-builds) if macOS displays an approval prompt.
3. Try **Play with sound**, or enable the real effect and allow Screen Recording.

Physical tracking needs a supported MacBook lid sensor. It has not yet been tested on a physical MacBook. The manual preview does not need a sensor or Screen Recording permission.

The app was compiled for both architectures on GitHub's macOS runner. The shader, packaged resources, C regression tests, and signature validation passed. [Build provenance](BUILD.json) identifies the exact source commit and workflow run. [SHA256SUMS.txt](SHA256SUMS.txt) contains the download checksum.

This ZIP is copied unchanged from the successful CI artifact. No telemetry, license activation, microphone input, or paid API is used. The underlying desktop remains interactive at its original coordinates while bent; pause Fold to use it normally.
