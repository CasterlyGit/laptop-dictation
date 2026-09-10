# Verification record

## Checked in this development environment

The shared C core passed its regression suite on Linux with GCC, `-Wall -Wextra -Werror -pedantic`, AddressSanitizer, and UndefinedBehaviorSanitizer. LeakSanitizer was disabled for the Linux container because its process-inspection mechanism is unavailable there; memory/address and undefined-behavior instrumentation remained enabled.

The suite checks report lengths/IDs/units/ranges, invalid numerical inputs, monotonic bend progress, signed movement, stationary velocity decay, exactly one open click per cycle, stale-history reset, all mesh positions and triangle winding across 101 fold amounts, and audio silence/output bounds at 44.1, 48, and 96 kHz.

**Native macOS build: passed.** [GitHub Actions run 34522291951](https://github.com/CasterlyGit/laptop-dictation/actions/runs/34522291951) built commit `2852380513e40b233d7cf426b7c471e83ab417e6` on a macOS 15 ARM64 runner using Xcode 16.4 and the macOS 15.5 SDK. Both `arm64` and `x86_64` app slices compiled and linked with a macOS 14 deployment target. The Metal compiler, sanitizer tests, ad-hoc signing, signature verification, and ZIP packaging all passed. The compiler flagged two main-run-loop timer closures for future Swift 6 isolation; the follow-up explicitly marks their main-actor context.

This validates compilation and packaging, not physical MacBook behavior. Subsequent builds also run the packaged executable's `--check-resources` path to ensure its resources can be located.

## Physical checks still required

These require a MacBook and cannot be established by a cloud compiler:

| Check | Expected behavior | Status |
| --- | --- | --- |
| Fresh launch | Controls appear; desktop capture stays off until enabled | Not run |
| Permission denial/grant | Clear guidance; no stranded overlay; reopen works | Not run |
| Real hinge movement | Plausible angle, smooth effect, no recursive capture | Not run |
| Elastic and click modes | Movement sound tracks the hinge; one click on clearing | Not run |
| Stationary lid | No sustained movement sound | Not run |
| Emergency pause | Global shortcut immediately removes effect and sound | Not run |
| Sleep/wake and session lock | No old desktop frame remains; no stale click | Not run |
| Full screen and Spaces | Built-in display effect follows supported spaces | Not run |
| External display / clamshell | No warping of an unrelated display; change pauses | Not run |
| Unsupported sensor | Clear status; manual preview remains usable | Not run |
| Quit and reopen | No lingering overlay or audio; preferences persist | Not run |

Until these are exercised, describe Fold as an experimental build. Report actual model and macOS details, rather than broad family-level compatibility claims.
