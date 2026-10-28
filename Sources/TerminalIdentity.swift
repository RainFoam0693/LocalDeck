import Foundation

struct TerminalIdentity: Sendable {
    let name: String
    let pid: Int32
    static func name(command: String) -> String {
        let words = command.split(whereSeparator: { $0.isWhitespace }).map(String.init)
        let executable = (words.first ?? "进程").split(separator: "/").last.map(String.init) ?? "进程"
        let lower = command.lowercased()
        for (token, label) in [("yunzai", "Yunzai"), ("vite", "Vite"), ("next", "Next.js"), ("nuxt", "Nuxt")] {
            if lower.range(of: "(^|[/ @:_-])" + token + "([/ .:@_-]|$)", options: .regularExpression) != nil { return label }
        }
        let runtime = executable.lowercased()
        if !words.contains("-c"), !words.contains("-e"), !words.contains("--eval"),
           (["node", "python", "python3", "ruby", "java", "deno", "bun"].contains(runtime) || runtime.hasPrefix("python3.")),
           let script = words.dropFirst().first(where: { !$0.hasPrefix("-") && $0 != "run" }) {
            // Only expose an entrypoint filename, never full command arguments.
            if script.contains("/") || [".js", ".mjs", ".py", ".jar", ".rb", ".ts"].contains(where: { script.hasSuffix($0) }) {
                return String((script as NSString).lastPathComponent.prefix(40))
            }
        }
        return String(executable.filter { !$0.isNewline && !$0.isASCIIControl }.prefix(40))
    }
    static func scan(shells: [Int32]) -> [Int32: TerminalIdentity] {
        guard !shells.isEmpty else { return [:] }
        let process = Process(); process.executableURL = URL(fileURLWithPath: "/bin/ps")
        process.arguments = ["-axo", "pid=,ppid=,stat=,args="]
        let pipe = Pipe(); process.standardOutput = pipe; process.standardError = FileHandle.nullDevice
        do { try process.run() } catch { return [:] }
        let data = pipe.fileHandleForReading.readDataToEndOfFile(); process.waitUntilExit()
        let rows = (String(data: data, encoding: .utf8) ?? "").split(separator: "\n").compactMap { line -> (Int32, Int32, String)? in
            let fields = line.split(maxSplits: 3, whereSeparator: { $0.isWhitespace })
            guard fields.count == 4, let pid = Int32(fields[0]), let parent = Int32(fields[1]), !fields[2].contains("Z") else { return nil }
            return (pid, parent, String(fields[3]))
        }
        var result: [Int32: TerminalIdentity] = [:]
        for shell in shells {
            var parents: Set<Int32> = [shell]; var candidates: [(Int32, Int32, String)] = []
            for _ in 0..<24 {
                let children = rows.filter { parents.contains($0.1) && !parents.contains($0.0) }
                if children.isEmpty { break }
                candidates += children; parents.formUnion(children.map { $0.0 })
            }
            let excluded: Set<String> = ["zsh", "bash", "sh", "env", "ps"]
            let usable = candidates.filter { !excluded.contains(name(command: $0.2)) }
            // Prefer recognizable application names over their helper processes.
            let known: Set<String> = ["Yunzai", "Vite", "Next.js", "Nuxt"]
            if let row = usable.first(where: { known.contains(name(command: $0.2)) }) ?? usable.last {
                result[shell] = TerminalIdentity(name: name(command: row.2), pid: row.0)
            }
        }
        return result
    }
}
private extension Character {
    var isASCIIControl: Bool { unicodeScalars.contains { $0.value < 32 || $0.value == 127 } }
}
