import AppKit
import SwiftUI
import Carbon

private final class PauseHotKey {
    private var hotKey: EventHotKeyRef?
    private var handler: EventHandlerRef?
    var onPress: (() -> Void)?
    @discardableResult func register() -> Bool {
        var event = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        let installed = InstallEventHandler(GetApplicationEventTarget(), { _, _, context in
            guard let context else { return noErr }
            let owner = Unmanaged<PauseHotKey>.fromOpaque(context).takeUnretainedValue()
            DispatchQueue.main.async { owner.onPress?() }
            return noErr
        }, 1, &event, Unmanaged.passUnretained(self).toOpaque(), &handler)
        guard installed == noErr else { return false }
        let identifier = EventHotKeyID(signature: 0x464F4C44, id: 1)
        return RegisterEventHotKey(UInt32(kVK_ANSI_F), UInt32(controlKey | optionKey | cmdKey),
                                   identifier, GetApplicationEventTarget(), 0, &hotKey) == noErr
    }
    deinit {
        if let hotKey { UnregisterEventHotKey(hotKey) }
        if let handler { RemoveEventHandler(handler) }
    }
}

@MainActor private final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    private let model = FoldModel()
    private let shortcut = PauseHotKey()
    private var item: NSStatusItem?
    private var toggleItem: NSMenuItem?
    private var window: NSWindow?
    private var localKeys: Any?
    private var observers: [(NotificationCenter, NSObjectProtocol)] = []

    func applicationDidFinishLaunching(_ notification: Notification) {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        item.button?.image = NSImage(systemSymbolName: "rectangle.compress.vertical", accessibilityDescription: "Fold")
        item.button?.toolTip = "Fold — desktop and hinge sound"
        let menu = NSMenu()
        menu.addItem(withTitle: "Fold", action: nil, keyEquivalent: "")
        menu.addItem(.separator())
        let toggle = NSMenuItem(title: "Enable Fold", action: #selector(toggleFold), keyEquivalent: "")
        toggle.target = self; menu.addItem(toggle); toggleItem = toggle
        let controls = NSMenuItem(title: "Controls…", action: #selector(showControls), keyEquivalent: ",")
        controls.target = self; menu.addItem(controls)
        let pause = NSMenuItem(title: "Pause instantly     ⌃⌥⌘F", action: #selector(pauseFold), keyEquivalent: "")
        pause.target = self; menu.addItem(pause)
        menu.addItem(.separator())
        let quit = NSMenuItem(title: "Quit Fold", action: #selector(quitFold), keyEquivalent: "q")
        quit.target = self; menu.addItem(quit)
        item.menu = menu; self.item = item
        model.stateDidChange = { [weak self] in
            guard let self else { return }
            self.toggleItem?.title = self.model.enabled ? "Pause Fold" : "Enable Fold"
            self.item?.button?.appearsDisabled = !self.model.enabled
        }
        shortcut.onPress = { [weak self] in self?.model.pause() }
        if !shortcut.register() { model.message = "The global pause shortcut is unavailable. Pause from Fold's menu bar menu." }
        localKeys = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            if event.keyCode == 53 { self?.model.pause(); return nil }
            return event
        }
        observe(NSWorkspace.shared.notificationCenter, NSWorkspace.willSleepNotification) { $0.suspend("sleep") }
        observe(NSWorkspace.shared.notificationCenter, NSWorkspace.didWakeNotification) { $0.resume("sleep") }
        observe(NSWorkspace.shared.notificationCenter, NSWorkspace.screensDidSleepNotification) { $0.suspend("screens") }
        observe(NSWorkspace.shared.notificationCenter, NSWorkspace.screensDidWakeNotification) { $0.resume("screens") }
        observe(NSWorkspace.shared.notificationCenter, NSWorkspace.sessionDidResignActiveNotification) { $0.suspend("session") }
        observe(NSWorkspace.shared.notificationCenter, NSWorkspace.sessionDidBecomeActiveNotification) { $0.resume("session") }
        observe(DistributedNotificationCenter.default(), Notification.Name("com.apple.screenIsLocked")) { $0.suspend("lock") }
        observe(DistributedNotificationCenter.default(), Notification.Name("com.apple.screenIsUnlocked")) { $0.resume("lock") }
        observe(NotificationCenter.default, NSApplication.didChangeScreenParametersNotification) { $0.displaysChanged() }
        showControls()
    }

    private func observe(_ center: NotificationCenter, _ name: Notification.Name, action: @escaping (FoldModel) -> Void) {
        let token = center.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in
            guard let self else { return }; action(self.model)
        }
        observers.append((center, token))
    }
    @objc private func toggleFold() { model.toggle() }
    @objc private func pauseFold() { model.pause() }
    @objc private func quitFold() { NSApp.terminate(nil) }
    @objc private func showControls() {
        if window == nil {
            let controller = NSHostingController(rootView: ControlsView(model: model))
            let window = NSWindow(contentViewController: controller)
            window.title = "Fold"
            window.styleMask = [.titled, .closable, .miniaturizable]
            window.titlebarAppearsTransparent = true
            window.backgroundColor = NSColor(calibratedWhite: 0.075, alpha: 1)
            window.isReleasedWhenClosed = false
            window.delegate = self
            window.center()
            self.window = window
        }
        window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
    func windowWillClose(_ notification: Notification) { model.stopPreview() }
    func applicationWillTerminate(_ notification: Notification) {
        model.pause()
        if let localKeys { NSEvent.removeMonitor(localKeys) }
        for (center, token) in observers { center.removeObserver(token) }
    }
}

@main enum FoldMain {
    @MainActor static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)
        let delegate = AppDelegate()
        app.delegate = delegate
        withExtendedLifetime(delegate) { app.run() }
    }
}
