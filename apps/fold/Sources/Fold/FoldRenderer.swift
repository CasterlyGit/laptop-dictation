import AppKit
import MetalKit
import FoldCore

@MainActor final class FoldRenderer: NSObject, MTKViewDelegate {
    struct Look { var progress, blur, shadow, padding: Float }
    let view: MTKView
    var progress: Float = 0
    var perspective: Float = 0.9
    var blur: Float = 0.5
    var shadow: Float = 0.45
    private let gpu: MTLDevice
    private let commands: MTLCommandQueue
    private let pipeline: MTLRenderPipelineState
    private var textureCache: CVMetalTextureCache?
    private var texture: MTLTexture?
    private var cvTexture: CVMetalTexture?
    private var frame: CVPixelBuffer?
    private var vertices = [FoldVertex](repeating: FoldVertex(), count: Int(fold_mesh_count(8, 56)))

    init(demo: Bool) throws {
        guard let gpu = MTLCreateSystemDefaultDevice(), let commands = gpu.makeCommandQueue() else {
            throw Self.failure("Metal isn't available on this Mac.")
        }
        self.gpu = gpu; self.commands = commands
        guard let shaderURL = Bundle.module.url(forResource: "Fold", withExtension: "metal", subdirectory: "Resources") else {
            throw Self.failure("The shader resource is missing. Rebuild with scripts/build-app.sh.")
        }
        let library = try gpu.makeLibrary(source: String(contentsOf: shaderURL), options: nil)
        let descriptor = MTLRenderPipelineDescriptor()
        descriptor.vertexFunction = library.makeFunction(name: "fold_vertex")
        descriptor.fragmentFunction = library.makeFunction(name: "fold_fragment")
        descriptor.colorAttachments[0].pixelFormat = .bgra8Unorm
        pipeline = try gpu.makeRenderPipelineState(descriptor: descriptor)
        view = MTKView(frame: .zero, device: gpu)
        super.init()
        view.colorPixelFormat = .bgra8Unorm
        view.clearColor = MTLClearColor(red: 0.018, green: 0.022, blue: 0.026, alpha: 1)
        view.isPaused = true
        view.enableSetNeedsDisplay = true
        view.framebufferOnly = true
        view.delegate = self
        guard CVMetalTextureCacheCreate(nil, nil, gpu, nil, &textureCache) == kCVReturnSuccess else {
            throw Self.failure("Couldn't prepare desktop textures.")
        }
        if demo {
            guard let url = Bundle.module.url(forResource: "Desktop", withExtension: "png", subdirectory: "Resources") else {
                throw Self.failure("Preview image is missing.")
            }
            texture = try MTKTextureLoader(device: gpu).newTexture(URL: url, options: [.SRGB: false])
        }
    }

    @discardableResult func setFrame(_ pixelBuffer: CVPixelBuffer) -> Bool {
        guard let textureCache else { return false }
        var result: CVMetalTexture?
        let status = CVMetalTextureCacheCreateTextureFromImage(nil, textureCache, pixelBuffer, nil, .bgra8Unorm,
            CVPixelBufferGetWidth(pixelBuffer), CVPixelBufferGetHeight(pixelBuffer), 0, &result)
        guard status == kCVReturnSuccess, let result, let metal = CVMetalTextureGetTexture(result) else { return false }
        cvTexture = result; frame = pixelBuffer; texture = metal
        redraw()
        return true
    }

    func clearFrame() {
        texture = nil; cvTexture = nil; frame = nil
        if let textureCache { CVMetalTextureCacheFlush(textureCache, 0) }
    }
    func redraw() { view.setNeedsDisplay(view.bounds) }
    func mtkView(_ view: MTKView, drawableSizeWillChange size: CGSize) {}

    func draw(in view: MTKView) {
        guard let texture, let pass = view.currentRenderPassDescriptor, let drawable = view.currentDrawable,
              let command = commands.makeCommandBuffer(), let encoder = command.makeRenderCommandEncoder(descriptor: pass) else { return }
        let capacity = vertices.count
        let count = vertices.withUnsafeMutableBufferPointer {
            fold_make_mesh($0.baseAddress, capacity, 8, 56, progress, perspective)
        }
        guard let buffer = vertices.withUnsafeBytes({ gpu.makeBuffer(bytes: $0.baseAddress!, length: $0.count, options: .storageModeShared) }) else {
            encoder.endEncoding(); return
        }
        var look = Look(progress: progress, blur: blur, shadow: shadow, padding: 0)
        encoder.setRenderPipelineState(pipeline)
        encoder.setVertexBuffer(buffer, offset: 0, index: 0)
        encoder.setFragmentTexture(texture, index: 0)
        encoder.setFragmentBytes(&look, length: MemoryLayout<Look>.stride, index: 0)
        encoder.drawPrimitives(type: .triangle, vertexStart: 0, vertexCount: count)
        encoder.endEncoding()
        let keepFrame = frame, keepTexture = cvTexture
        command.addCompletedHandler { _ in withExtendedLifetime((keepFrame, keepTexture)) {} }
        command.present(drawable)
        command.commit()
    }
    private static func failure(_ text: String) -> NSError {
        NSError(domain: "Fold", code: 3, userInfo: [NSLocalizedDescriptionKey: text])
    }
}
