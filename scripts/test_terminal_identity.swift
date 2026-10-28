import Foundation

// Compile alongside Sources/TerminalIdentity.swift to exercise the real scanner.
@main struct TerminalIdentityTests {
static func main() throws {
let cases = [("node /project/TRSS-Yunzai/app.js", "Yunzai"), ("node /project/node_modules/vite/bin/vite.js", "Vite"), ("python3 /project/server.py --token=secret", "server.py"), ("Yunzai v3.1.7 © 2025", "Yunzai"), ("node /project/invited.js", "invited.js")]
for (command, expected) in cases { precondition(TerminalIdentity.name(command: command) == expected) }
let child = Process(); child.executableURL = URL(fileURLWithPath: "/bin/sleep"); child.arguments = ["30"]
try child.run()
let identity = TerminalIdentity.scan(shells: [getpid()])[getpid()]
precondition(identity?.name == "sleep" && identity?.pid == child.processIdentifier)
child.terminate(); child.waitUntilExit()
precondition(TerminalIdentity.scan(shells: [getpid()])[getpid()] == nil)
print("macOS identity classification, live task and idle restoration passed")

}
}
