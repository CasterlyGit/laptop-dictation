import AVFoundation
import FoldCore

/// Original procedural audio. Atomic controls bridge UI and the real-time audio callback.
final class MovementSound {
    private let engine = AVAudioEngine()
    private var source: AVAudioSourceNode?
    private var dsp: OpaquePointer?

    func start() throws {
        if engine.isRunning { return }
        if source == nil {
            let rate = 48_000.0
            guard let processor = fold_audio_create(rate),
                  let format = AVAudioFormat(standardFormatWithSampleRate: rate, channels: 1) else {
                throw NSError(domain: "Fold", code: 1, userInfo: [NSLocalizedDescriptionKey: "Couldn't prepare sound."])
            }
            dsp = processor
            let node = AVAudioSourceNode(format: format) { _, _, frames, bufferList in
                let buffers = UnsafeMutableAudioBufferListPointer(bufferList)
                guard let first = buffers.first, let data = first.mData else { return noErr }
                let samples = data.assumingMemoryBound(to: Float.self)
                fold_audio_render(processor, samples, Int(frames))
                // Mono source normally has one buffer. Copy if the audio graph supplies more.
                for buffer in buffers.dropFirst() {
                    if let destination = buffer.mData {
                        memcpy(destination, data, min(Int(buffer.mDataByteSize), Int(first.mDataByteSize)))
                    }
                }
                return noErr
            }
            source = node
            engine.attach(node)
            engine.connect(node, to: engine.mainMixerNode, format: format)
        }
        engine.prepare()
        try engine.start()
    }

    func update(progress: Double, velocity: Double, volume: Double, mode: Int, click: Bool = false) {
        fold_audio_set(dsp, progress, velocity, volume, Int32(mode))
        if click { fold_audio_click(dsp) }
    }

    func silence() { fold_audio_set(dsp, 0, 0, 0, 0) }
    func stop() { silence(); engine.stop() }
    deinit {
        engine.stop()
        if let source { engine.detach(source) }
        fold_audio_destroy(dsp)
    }
}
