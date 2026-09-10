import AppKit
import Combine
import FoldCore

enum SoundChoice: Int, Codable, CaseIterable, Identifiable {
    case off = 0, elastic = 1, click = 2
    var id: Int { rawValue }
    var label: String { switch self { case .off: return "Off"; case .elastic: return "Elastic"; case .click: return "Open click" } }
}

struct FoldSettings: Codable {
    var perspective = 0.9
    var blur = 0.5
    var shadow = 0.45
    var clearAngle = 105.0
    var volume = 0.3
    var sound = SoundChoice.elastic
    mutating func normalize() {
        perspective = Self.clamp(perspective, 0...1, fallback: 0.9)
        blur = Self.clamp(blur, 0...1, fallback: 0.5)
        shadow = Self.clamp(shadow, 0...1, fallback: 0.45)
        clearAngle = Self.clamp(clearAngle, 65...135, fallback: 105)
        volume = Self.clamp(volume, 0...1, fallback: 0.3)
    }
    private static func clamp(_ value: Double, _ range: ClosedRange<Double>, fallback: Double) -> Double {
        value.isFinite ? min(range.upperBound, max(range.lowerBound, value)) : fallback
    }
}

private final class OverlayPanel: NSPanel {
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}

@MainActor final class FoldModel: ObservableObject {
    @Published private(set) var enabled = false
    @Published private(set) var sensorAvailable = false
    @Published private(set) var sensorStatus = "Checking the lid sensor…"
    @Published private(set) var angle = 115.0
    @Published var message: String?
    @Published var previewAngle = 115.0
    @Published private(set) var previewPlaying = false
    @Published var settings: FoldSettings {
        didSet {
            if let data = try? JSONEncoder().encode(settings) { UserDefaults.standard.set(data, forKey: "Fold.settings.v1") }
            refreshAppearance()
            if settings.sound == .off { sound.silence() }
        }
    }
    let previewRenderer: FoldRenderer?
    private var desktopRenderer: FoldRenderer?
    private let sensor = LidSensor()
    private let capture = DesktopCapture()
    private let sound = MovementSound()
    private var overlay: OverlayPanel?
    private var displayID: CGDirectDisplayID?
    private var motion = FoldMotion()
    private var previewMotion = FoldMotion()
    private var progress = 0.0
    private var lastSensorTime = 0.0
    private var watchdog: Timer?
    private var previewTimer: Timer?
    private var previewStarted = 0.0
    private var previewSilence: Task<Void, Never>?
    private var suspensionReasons = Set<String>()
    var stateDidChange: (() -> Void)?

    init() {
        var loaded = UserDefaults.standard.data(forKey: "Fold.settings.v1")
            .flatMap { try? JSONDecoder().decode(FoldSettings.self, from: $0) } ?? FoldSettings()
        loaded.normalize(); settings = loaded
        var startupError: String?
        do { previewRenderer = try FoldRenderer(demo: true) }
        catch { previewRenderer = nil; startupError = error.localizedDescription }
        if let startupError { message = startupError }
        sensor.onReading = { [weak self] raw, time in self?.received(raw, time: time) }
        sensor.onStatus = { [weak self] available, text in
            guard let self else { return }
            self.sensorAvailable = available; self.sensorStatus = text
            if !available && self.enabled { self.pause(); self.message = text }
        }
        capture.onFrame = { [weak self] buffer in
            guard let self, self.enabled, self.suspensionReasons.isEmpty, self.progress > 0.003 else { return }
            guard self.desktopRenderer?.setFrame(buffer) == true else {
                self.pause(); self.message = "Couldn't render the desktop frame. Fold has paused."; return
            }
            self.overlay?.orderFrontRegardless()
        }
        capture.onFailure = { [weak self] error in
            self?.pause(); self?.message = "Screen capture stopped: \(error)"
        }
        refreshAppearance()
        sensor.start(continuous: false)
    }

    func toggle() { enabled ? pause() : enable() }

    func enable() {
        guard !enabled else { return }
        guard sensorAvailable else { message = sensorStatus; return }
        guard CGPreflightScreenCaptureAccess() || CGRequestScreenCaptureAccess() else {
            message = "Allow Fold in System Settings → Privacy & Security → Screen Recording, then quit and reopen Fold."
            return
        }
        guard let screen = NSScreen.screens.first(where: { screen in
            guard let id = screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber else { return false }
            return CGDisplayIsBuiltin(id.uint32Value) != 0
        }), let id = screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber else {
            message = "Open the MacBook's built-in display to use the live effect."
            return
        }
        do {
            let renderer = try FoldRenderer(demo: false)
            let panel = OverlayPanel(contentRect: screen.frame, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
            panel.level = NSWindow.Level(rawValue: NSWindow.Level.statusBar.rawValue + 1)
            panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]
            panel.isOpaque = true; panel.backgroundColor = .black
            panel.hasShadow = false; panel.ignoresMouseEvents = true
            panel.hidesOnDeactivate = false; panel.isReleasedWhenClosed = false
            panel.sharingType = .none
            renderer.view.frame = NSRect(origin: .zero, size: screen.frame.size)
            renderer.view.autoresizingMask = [.width, .height]
            panel.contentView = renderer.view
            desktopRenderer = renderer; overlay = panel; displayID = id.uint32Value
        } catch { message = error.localizedDescription; return }
        stopPreview()
        enabled = true; message = nil
        refreshAppearance()
        if suspensionReasons.isEmpty { resumeMonitoring() }
        stateDidChange?()
    }

    func pause() {
        enabled = false
        stopMonitoring()
        overlay?.close(); overlay = nil; desktopRenderer = nil; displayID = nil
        stopPreview()
        stateDidChange?()
    }

    func retrySensor() {
        pause(); sensorStatus = "Checking the lid sensor…"
        sensor.start(continuous: false)
    }

    func suspend(_ reason: String) {
        suspensionReasons.insert(reason)
        stopMonitoring(); stopPreview()
    }

    func resume(_ reason: String) {
        suspensionReasons.remove(reason)
        if enabled && suspensionReasons.isEmpty { resumeMonitoring() }
    }

    func displaysChanged() {
        if enabled { pause(); message = "Displays changed. Enable Fold again on the built-in screen." }
    }

    func openPermissions() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture") {
            NSWorkspace.shared.open(url)
        }
    }

    func setPreviewAngle(_ value: Double) {
        if previewPlaying { stopPreview() }
        previewAngle = value
        previewStep()
        previewSilence?.cancel()
        previewSilence = Task { [weak self] in
            do { try await Task.sleep(nanoseconds: 160_000_000) } catch { return }
            guard let self, !self.enabled, !self.previewPlaying else { return }
            self.sound.silence()
        }
    }

    func togglePreview() {
        if previewPlaying { stopPreview(); return }
        guard suspensionReasons.isEmpty else { return }
        previewSilence?.cancel()
        previewPlaying = true
        fold_motion_reset(&previewMotion)
        previewStarted = ProcessInfo.processInfo.systemUptime
        let timer = Timer(timeInterval: 1.0 / 60, repeats: true) { [weak self] _ in
            guard let self else { return }
            let t = ProcessInfo.processInfo.systemUptime - self.previewStarted
            if t >= 5 { self.previewAngle = 120; self.previewStep(); self.stopPreview(); return }
            self.previewAngle = 120 - 96 * pow(sin(.pi * t / 5), 2)
            self.previewStep()
        }
        previewTimer = timer
        RunLoop.main.add(timer, forMode: .common)
    }

    func stopPreview() {
        previewPlaying = false
        previewTimer?.invalidate(); previewTimer = nil
        previewSilence?.cancel(); previewSilence = nil
        fold_motion_reset(&previewMotion)
        if !enabled { sound.stop() }
    }

    func usePreset(_ preset: Int) {
        var next = settings
        switch preset {
        case 1: next.perspective = 1; next.blur = 0.1; next.shadow = 0.75
        case 2: next.perspective = 0.65; next.blur = 1; next.shadow = 0.2
        default: next.perspective = 0.9; next.blur = 0.5; next.shadow = 0.45
        }
        settings = next
    }

    private func resumeMonitoring() {
        watchdog?.invalidate()
        fold_motion_reset(&motion)
        lastSensorTime = ProcessInfo.processInfo.systemUptime
        sensor.start(continuous: true)
        let timer = Timer(timeInterval: 0.1, repeats: true) { [weak self] _ in
            guard let self, self.enabled else { return }
            if ProcessInfo.processInfo.systemUptime - self.lastSensorTime > 0.75 {
                self.pause(); self.message = "Lid readings stopped. Fold has cleared the desktop."
            }
        }
        watchdog = timer; RunLoop.main.add(timer, forMode: .common)
    }

    private func stopMonitoring() {
        watchdog?.invalidate(); watchdog = nil
        sensor.stop()
        clearDesktop()
        sound.stop()
        fold_motion_reset(&motion)
    }

    private func clearDesktop() {
        progress = 0
        overlay?.orderOut(nil)
        capture.stop()
        desktopRenderer?.clearFrame()
    }

    private func received(_ raw: Double, time: Double) {
        angle = raw
        guard enabled, suspensionReasons.isEmpty else { return }
        lastSensorTime = time
        let reading = fold_motion_update(&motion, raw, time, settings.clearAngle)
        progress = reading.progress
        desktopRenderer?.progress = Float(progress)
        desktopRenderer?.redraw()
        playSound(reading)
        if progress > 0.003, let displayID {
            Task { [weak self] in
                guard let self, self.enabled, self.progress > 0.003, self.suspensionReasons.isEmpty else { return }
                await self.capture.start(displayID: displayID)
            }
        } else { clearDesktop() }
    }

    private func playSound(_ reading: FoldReading) {
        if settings.sound == .off { sound.silence(); return }
        do { try sound.start() }
        catch { message = "Sound is unavailable: \(error.localizedDescription)"; return }
        sound.update(progress: reading.progress, velocity: reading.velocity, volume: settings.volume,
                     mode: settings.sound.rawValue, click: reading.opened)
    }

    private func previewStep() {
        refreshAppearance()
        let reading = fold_motion_update(&previewMotion, previewAngle, ProcessInfo.processInfo.systemUptime, settings.clearAngle)
        if !enabled && suspensionReasons.isEmpty { playSound(reading) }
    }

    private func refreshAppearance() {
        for renderer in [previewRenderer, desktopRenderer].compactMap({ $0 }) {
            renderer.perspective = Float(settings.perspective)
            renderer.blur = Float(settings.blur)
            renderer.shadow = Float(settings.shadow)
        }
        previewRenderer?.progress = Float(fold_progress(previewAngle, settings.clearAngle))
        previewRenderer?.redraw()
        desktopRenderer?.redraw()
    }
}
