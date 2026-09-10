import Foundation
import IOKit.hid
import FoldCore

/// Read-only, sensor-specific HID access. Discovery and polling never run on the UI thread.
final class LidSensor {
    var onReading: ((Double, Double) -> Void)?
    var onStatus: ((Bool, String) -> Void)?
    private let queue = DispatchQueue(label: "org.fold.sensor", qos: .userInitiated)
    private var timer: DispatchSourceTimer?
    private var device: IOHIDDevice?
    private var failures = 0

    func start(continuous: Bool) {
        queue.async { [weak self] in
            guard let self else { return }
            self.close()
            let manager = IOHIDManagerCreate(kCFAllocatorDefault, 0)
            // Restrict enumeration to Apple's lid sensor, never keyboards or general input.
            let match: [String: Any] = [kIOHIDVendorIDKey as String: 0x05AC, kIOHIDProductIDKey as String: 0x8104]
            IOHIDManagerSetDeviceMatching(manager, match as CFDictionary)
            let result = IOHIDManagerOpen(manager, 0)
            guard result == kIOReturnSuccess else {
                self.status(false, "Sensor access unavailable (\(result)). Manual preview still works.")
                return
            }
            defer { IOHIDManagerClose(manager, 0) }
            let devices = IOHIDManagerCopyDevices(manager) as? Set<IOHIDDevice> ?? []
            for candidate in devices {
                let page = IOHIDDeviceGetProperty(candidate, kIOHIDPrimaryUsagePageKey as CFString) as? NSNumber
                let usage = IOHIDDeviceGetProperty(candidate, kIOHIDPrimaryUsageKey as CFString) as? NSNumber
                guard page?.intValue == 0x20, usage?.intValue == 0x8A else { continue }
                guard IOHIDDeviceOpen(candidate, 0) == kIOReturnSuccess else { continue }
                self.device = candidate
                if self.poll() {
                    self.status(true, "Lid sensor connected")
                    if continuous {
                        let timer = DispatchSource.makeTimerSource(queue: self.queue)
                        timer.schedule(deadline: .now(), repeating: 1.0 / 30, leeway: .milliseconds(3))
                        timer.setEventHandler { [weak self] in
                            guard let self else { return }
                            if self.poll() { self.failures = 0 }
                            else {
                                self.failures += 1
                                if self.failures >= 12 {
                                    self.close()
                                    self.status(false, "Lost the lid sensor. The desktop effect has stopped.")
                                }
                            }
                        }
                        self.timer = timer
                        timer.resume()
                    } else { self.close() }
                    return
                }
                self.close()
            }
            self.status(false, devices.isEmpty
                ? "No supported lid sensor detected. Try the manual preview."
                : "A sensor exists, but its angle report isn't supported. Try the manual preview.")
        }
    }

    func stop() { queue.async { [weak self] in self?.close() } }

    @discardableResult private func poll() -> Bool {
        guard let device else { return false }
        var report = [UInt8](repeating: 0, count: 8)
        var length = report.count
        let result = report.withUnsafeMutableBufferPointer { bytes in
            IOHIDDeviceGetReport(device, kIOHIDReportTypeFeature, 1, bytes.baseAddress!, &length)
        }
        var angle = 0.0
        guard result == kIOReturnSuccess,
              report.withUnsafeBufferPointer({ fold_decode_report($0.baseAddress, length, &angle) }) else { return false }
        let time = ProcessInfo.processInfo.systemUptime
        let callback = onReading
        DispatchQueue.main.async { callback?(angle, time) }
        return true
    }

    private func status(_ available: Bool, _ message: String) {
        let callback = onStatus
        DispatchQueue.main.async { callback?(available, message) }
    }

    private func close() {
        timer?.cancel(); timer = nil
        if let device { IOHIDDeviceClose(device, 0) }
        device = nil; failures = 0
    }
}
