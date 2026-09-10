// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "Fold",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "Fold", targets: ["Fold"])],
    targets: [
        .target(name: "FoldCore", publicHeadersPath: "include", linkerSettings: [.linkedLibrary("m")]),
        .executableTarget(name: "Fold", dependencies: ["FoldCore"], resources: [.copy("Resources")],
            linkerSettings: [.linkedFramework("Carbon"), .linkedFramework("IOKit")])
    ],
    cLanguageStandard: .c11
)
