import AppKit
import ScreenCaptureKit
import CoreMedia
import CoreVideo

private final class FrameSink: NSObject, SCStreamOutput, SCStreamDelegate {
    let receive: (CVPixelBuffer) -> Void
    let failed: (Error) -> Void
    init(receive: @escaping (CVPixelBuffer) -> Void, failed: @escaping (Error) -> Void) {
        self.receive = receive; self.failed = failed
    }
    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .screen, sampleBuffer.isValid,
              let attachments = CMSampleBufferGetSampleAttachmentsArray(sampleBuffer, createIfNecessary: false) as? [[SCStreamFrameInfo: Any]],
              let status = attachments.first?[.status] as? Int,
              status == SCFrameStatus.complete.rawValue,
              let pixelBuffer = sampleBuffer.imageBuffer else { return }
        receive(pixelBuffer)
    }
    func stream(_ stream: SCStream, didStopWithError error: Error) { failed(error) }
}

@MainActor final class DesktopCapture {
    var onFrame: ((CVPixelBuffer) -> Void)?
    var onFailure: ((String) -> Void)?
    private var stream: SCStream?
    private var sink: FrameSink?
    private var generation = 0
    private var starting = false
    private var receivedFrame = false
    private var firstFrameTimeout: Task<Void, Never>?
    private let videoQueue = DispatchQueue(label: "org.fold.frames", qos: .userInteractive)

    func start(displayID: CGDirectDisplayID) async {
        guard stream == nil, !starting else { return }
        starting = true
        receivedFrame = false
        generation += 1
        let current = generation
        do {
            let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
            guard current == generation else { return }
            guard let display = content.displays.first(where: { $0.displayID == displayID }) else {
                throw failure("The built-in display is unavailable.")
            }
            let ownApps = content.applications.filter { $0.processID == ProcessInfo.processInfo.processIdentifier }
            guard !ownApps.isEmpty else {
                throw failure("Open Fold's controls and try again so the overlay can be excluded from capture.")
            }
            // Excluding the entire process prevents recursive screen-within-screen feedback.
            let filter = SCContentFilter(display: display, excludingApplications: ownApps, exceptingWindows: [])
            let configuration = SCStreamConfiguration()
            let scale = min(1.0, 1920.0 / Double(display.width))
            configuration.width = max(2, Int(Double(display.width) * scale) / 2 * 2)
            configuration.height = max(2, Int(Double(display.height) * scale) / 2 * 2)
            configuration.minimumFrameInterval = CMTime(value: 1, timescale: 60)
            configuration.queueDepth = 3
            configuration.pixelFormat = kCVPixelFormatType_32BGRA
            configuration.showsCursor = false
            configuration.capturesAudio = false
            let receiver = FrameSink(receive: { [weak self] buffer in
                Task { @MainActor [weak self] in
                    guard let self, self.generation == current else { return }
                    self.receivedFrame = true
                    self.firstFrameTimeout?.cancel(); self.firstFrameTimeout = nil
                    self.onFrame?(buffer)
                }
            }, failed: { [weak self] error in
                Task { @MainActor [weak self] in
                    guard let self, self.generation == current else { return }
                    self.stop()
                    self.onFailure?(error.localizedDescription)
                }
            })
            let newStream = SCStream(filter: filter, configuration: configuration, delegate: receiver)
            try newStream.addStreamOutput(receiver, type: .screen, sampleHandlerQueue: videoQueue)
            sink = receiver; stream = newStream
            try await newStream.startCapture()
            guard current == generation else {
                try? await newStream.stopCapture()
                return
            }
            starting = false
            firstFrameTimeout = Task { [weak self] in
                do { try await Task.sleep(nanoseconds: 2_000_000_000) } catch { return }
                guard let self, self.generation == current, !self.receivedFrame else { return }
                self.stop()
                self.onFailure?("No desktop frames arrived. Check Screen Recording permission and reopen Fold.")
            }
        } catch {
            guard current == generation else { return }
            stop()
            onFailure?(error.localizedDescription)
        }
    }

    func stop() {
        generation += 1
        starting = false
        firstFrameTimeout?.cancel(); firstFrameTimeout = nil
        let old = stream
        stream = nil; sink = nil
        if let old { Task { try? await old.stopCapture() } }
    }

    private func failure(_ message: String) -> NSError {
        NSError(domain: "Fold", code: 2, userInfo: [NSLocalizedDescriptionKey: message])
    }
}
