import SwiftUI
import MetalKit

private struct MetalPreview: NSViewRepresentable {
    let renderer: FoldRenderer
    func makeNSView(context: Context) -> MTKView { renderer.view }
    func updateNSView(_ view: MTKView, context: Context) { renderer.redraw() }
}

struct ControlsView: View {
    @ObservedObject var model: FoldModel
    private let mint = Color(red: 0.69, green: 0.96, blue: 0.76)
    private let ink = Color(red: 0.07, green: 0.08, blue: 0.08)

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 5) {
                    Text("fold").font(.system(size: 46, weight: .bold, design: .rounded)).tracking(-2)
                    Text("A little give in your screen.").foregroundStyle(.secondary).font(.system(size: 15))
                }
                Spacer()
                Text("FREE & OPEN SOURCE").font(.system(size: 10, weight: .semibold, design: .monospaced))
                    .tracking(1).padding(.horizontal, 12).padding(.vertical, 8)
                    .background(mint.opacity(0.12), in: Capsule()).foregroundStyle(mint)
            }
            HStack(alignment: .top, spacing: 28) {
                VStack(alignment: .leading, spacing: 17) {
                    ZStack {
                        RoundedRectangle(cornerRadius: 18).fill(.black)
                        if let renderer = model.previewRenderer {
                            MetalPreview(renderer: renderer).clipShape(RoundedRectangle(cornerRadius: 10)).padding(8)
                        } else { Text("Metal preview unavailable").foregroundStyle(.secondary) }
                    }.frame(width: 422, height: 275)
                    HStack {
                        Text("PREVIEW").font(.system(size: 10, weight: .medium, design: .monospaced)).tracking(1.4).foregroundStyle(.secondary)
                        Spacer()
                        Text("\(Int(model.previewAngle))°").font(.system(.callout, design: .monospaced))
                    }
                    Slider(value: Binding(get: { model.previewAngle }, set: { model.setPreviewAngle($0) }), in: 15...135)
                        .accessibilityLabel("Preview lid angle")
                    HStack {
                        Text("Close").foregroundStyle(.secondary)
                        Spacer()
                        Button { model.togglePreview() } label: {
                            Label(model.previewPlaying ? "Stop preview" : "Play with sound", systemImage: model.previewPlaying ? "stop.fill" : "play.fill")
                        }.buttonStyle(.bordered)
                        Spacer()
                        Text("Open").foregroundStyle(.secondary)
                    }.font(.caption)
                    Text("Drag the angle to feel the effect. Preview uses a sample desktop.")
                        .font(.caption).foregroundStyle(.secondary)
                    HStack(spacing: 8) {
                        Circle().fill(model.sensorAvailable ? mint : Color.orange).frame(width: 6, height: 6)
                        Text(model.sensorStatus).font(.caption).foregroundStyle(.secondary)
                        Spacer(minLength: 0)
                    }.padding(.top, 8)
                }.frame(width: 422)
                VStack(alignment: .leading, spacing: 18) {
                    HStack {
                        Text("The feel").font(.headline)
                        Spacer()
                        Menu("Presets") {
                            Button("Soft") { model.usePreset(0) }
                            Button("Paper") { model.usePreset(1) }
                            Button("Haze") { model.usePreset(2) }
                        }.fixedSize()
                    }
                    control("Perspective", value: $model.settings.perspective)
                    control("Blur", value: $model.settings.blur)
                    control("Shadow", value: $model.settings.shadow)
                    Divider()
                    HStack { Text("Clears at"); Spacer(); Text("\(Int(model.settings.clearAngle))°").monospacedDigit().foregroundStyle(.secondary) }
                    Slider(value: $model.settings.clearAngle, in: 65...135, step: 1).accessibilityLabel("Desktop clears at angle")
                    Divider()
                    Text("The sound").font(.headline)
                    Picker("Sound", selection: $model.settings.sound) {
                        ForEach(SoundChoice.allCases) { choice in Text(choice.label).tag(choice) }
                    }.pickerStyle(.segmented).labelsHidden()
                    control("Volume", value: $model.settings.volume)
                    Text(soundHelp).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                }.frame(width: 272)
            }
            if let message = model.message {
                HStack(alignment: .top) {
                    Image(systemName: "info.circle")
                    Text(message).font(.caption).textSelection(.enabled)
                    Spacer()
                    Button { model.message = nil } label: { Image(systemName: "xmark") }.buttonStyle(.plain)
                }.padding(12).background(Color.orange.opacity(0.1), in: RoundedRectangle(cornerRadius: 9))
            }
            Divider()
            HStack(spacing: 14) {
                Button(model.enabled ? "Pause Fold" : "Enable on my Mac") { model.toggle() }
                    .buttonStyle(.borderedProminent).tint(mint).foregroundStyle(ink).controlSize(.large)
                    .disabled(!model.sensorAvailable && !model.enabled)
                Menu { Button("Check sensor again") { model.retrySensor() }; Button("Screen Recording settings") { model.openPermissions() } }
                    label: { Image(systemName: "ellipsis.circle").font(.title3) }.menuStyle(.borderlessButton).fixedSize()
                Spacer()
                VStack(alignment: .trailing, spacing: 3) {
                    Text("⌃⌥⌘F to pause instantly").font(.caption)
                    Text("On your Mac. No account. No uploads.").font(.caption2).foregroundStyle(.secondary)
                }
            }
        }
        .padding(30).frame(width: 782)
        .background(ink).foregroundStyle(Color.white.opacity(0.94))
        .preferredColorScheme(.dark).tint(mint)
    }

    private var soundHelp: String {
        switch model.settings.sound {
        case .off: return "Just the visual effect."
        case .elastic: return "A soft stretch that follows hinge speed, with a click as the screen clears."
        case .click: return "One quiet click when the lid opens and the desktop clears."
        }
    }
    private func control(_ name: String, value: Binding<Double>) -> some View {
        VStack(spacing: 7) {
            HStack { Text(name); Spacer(); Text("\(Int(value.wrappedValue * 100))%").monospacedDigit().foregroundStyle(.secondary) }
            Slider(value: value, in: 0...1).accessibilityLabel(name)
        }.font(.callout)
    }
}
