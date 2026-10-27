// swift-tools-version: 5.9
import PackageDescription
let package = Package(
    name: "LocalDeck",
    platforms: [.macOS(.v13)],
    dependencies: [.package(url: "https://github.com/migueldeicaza/SwiftTerm.git", exact: "1.10.1")],
    targets: [.executableTarget(name: "LocalDeck", dependencies: ["SwiftTerm"], path: "Sources")]
)
