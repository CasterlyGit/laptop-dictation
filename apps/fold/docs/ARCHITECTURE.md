# Architecture

Fold is an unsandboxed menu-bar app built with Swift Package Manager, SwiftUI/AppKit, ScreenCaptureKit, Metal, AVAudioEngine, and a small C11 core. It has no package dependencies or network client.

## Runtime

The HID reader runs on a serial background queue at 30 Hz while enabled. It matches only Apple's known lid sensor VID/PID, checks the standard orientation usage, and reads feature report 1. It validates the report ID, length, and plausible physical angle before use. It does not attempt vendor-specific interfaces, root access, device configuration writes, or input-monitoring hooks. A one-shot probe runs at launch.

The C motion filter uses monotonic timestamps, smoothing, stationary velocity decay, and an open-click latch with hysteresis. A long sampling gap resets history. Progress is zero above the configurable clear angle and one at 15 degrees or below. macOS still controls ordinary lid sleep.

Only nonzero bend progress starts desktop capture. ScreenCaptureKit captures the built-in display at up to 60 fps and a maximum width of 1920 pixels, with a queue depth of three. It excludes the whole Fold process, including the overlay. Capturing audio and the cursor is disabled. The overlay is a borderless, nonactivating, click-through panel. Screen frames are uploaded through CVMetalTextureCache without a screenshot-file round trip.

An 8-by-56 triangle grid maps a curved sheet into screen coordinates, anchored to the bottom edge. The Metal fragment shader adds a bounded nine-sample blur that grows toward the top, and adjustable edge shadow. The manual preview uses the same renderer and geometry with an original sample desktop.

AVAudioSourceNode pulls mono floating-point samples from the C DSP. UI controls are atomic; the render callback uses no locks or allocation. Elastic mode varies pitch with angle, speed, and direction. Its amplitude follows speed and decays when still. Both sound modes can play an original short synthesized click after a real opening transition. No microphone or system-audio capture is involved.

## Cleanup

- Pausing hides the overlay synchronously, stops the sensor and audio, invalidates asynchronous capture generations, and releases retained frames.
- Reaching the clear angle hides the overlay and stops capture; the one-shot audio may finish.
- A 750 ms sensor watchdog, repeated invalid HID reports, capture failure, or a missing first frame clears the effect.
- Independent suspension reasons track system sleep, display sleep, lock, and inactive login session. Monitoring resumes only after all reasons clear.
- Display reconfiguration pauses the app until it is enabled again on the built-in screen.
- Control–Option–Command–F is registered through Carbon as a global emergency pause. Escape is local to Fold's focused controls, not claimed as a system-wide shortcut.

## Deliberate limits

The overlay is a visual illusion, not a transformed interactive desktop. Mouse coordinates continue to address underlying apps. The effect is intended for opening and closing the lid; pause it before interacting with a deeply bent desktop.

The first bend may have a short capture startup delay because capture stops when the desktop is clear. There is no measured latency, power, or compatibility guarantee yet. Capture downsampling and SDR output may look different on HDR or high-resolution displays.

The C decoder supports only the verified whole-degree standard report layout. Unsupported hardware falls back to a manual preview; it never guesses a hardware angle from an open/closed switch.

## Research references

- [Bendy's product page](https://trybendy.app/), inspected September 10, 2026: live Metal rendering, perspective/blur/shadow controls, three presets, and a soft open click described as new in v0.3. Its downloadable web demo had a video stream and no audio stream, so the exact sound in the social post could not be compared.
- [Sam Gold's sensor implementation](https://github.com/samhenrigold/LidAngleSensor/blob/main/LidAngleSensor/LidAngleSensor.swift): feature report layout and whole-degree decoding.
- [Sensor compatibility notes](https://github.com/samhenrigold/LidAngleSensor/blob/main/README.md): model-specific limitations; physical hardware does not guarantee an accessible standard interface.
- [Apple: Capturing screen content in macOS](https://developer.apple.com/documentation/screencapturekit/capturing-screen-content-in-macos): capture lifecycle, complete-frame validation, and excluding the capturing application.

References inform behavior and protocol facts. Third-party app assets and source files are not distributed in Fold.
