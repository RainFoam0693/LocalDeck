import SwiftUI
import AppKit
import SwiftTerm
import Darwin

@MainActor final class TerminalSession: NSObject, ObservableObject, Identifiable, LocalProcessTerminalViewDelegate {
    let id = UUID()
    @Published var title: String
    let number: Int
    @Published var identity: TerminalIdentity?
    var displayTitle: String { if isSSH { return title }; return identity.map { "\($0.name) · \(number)" } ?? title }
    let isSSH: Bool
    @Published var running = true
    @Published var directory: String
    let view: LocalProcessTerminalView
    init(number: Int, directory: String, ssh: SSHProfile? = nil) {
        self.isSSH = ssh != nil
        self.number = number
        self.title = ssh.map { "\($0.name) · SSH" } ?? "终端 \(number)"
        self.directory = directory
        self.view = LocalProcessTerminalView(frame: NSRect(x: 0, y: 0, width: 900, height: 520))
        super.init()
        view.processDelegate = self
        view.font = NSFont.monospacedSystemFont(ofSize: 13, weight: .regular)
        view.nativeBackgroundColor = NSColor(calibratedRed: 0.035, green: 0.05, blue: 0.075, alpha: 1)
        view.nativeForegroundColor = NSColor(calibratedRed: 0.90, green: 0.94, blue: 0.97, alpha: 1)
        var env = ProcessInfo.processInfo.environment
        env["TERM"] = "xterm-256color"
        env["COLORTERM"] = "truecolor"
        env["LANG"] = env["LANG"] ?? "en_US.UTF-8"
        view.startProcess(executable: ssh == nil ? "/bin/zsh" : "/usr/bin/ssh", args: ssh?.arguments ?? ["-l"], environment: env.map { "\($0.key)=\($0.value)" }, currentDirectory: directory)
    }
    nonisolated func sizeChanged(source: LocalProcessTerminalView, newCols: Int, newRows: Int) {}
    nonisolated func setTerminalTitle(source: LocalProcessTerminalView, title: String) {
        // Process identity is refreshed independently; shell OSC titles can remain stale after exit.
    }
    nonisolated func hostCurrentDirectoryUpdate(source: TerminalView, directory: String?) {
        if let directory { Task { @MainActor [weak self] in self?.directory = URL(string: directory)?.path ?? directory } }
    }
    nonisolated func processTerminated(source: TerminalView, exitCode: Int32?) { Task { @MainActor [weak self] in self?.running = false } }
    func currentDirectory() async -> URL? {
        let pid = view.process.shellPid
        let result: String? = await Task.detached {
            let task = Process(); task.executableURL = URL(fileURLWithPath: "/usr/sbin/lsof")
            task.arguments = ["-a", "-p", String(pid), "-d", "cwd", "-Fn"]
            let pipe = Pipe(); task.standardOutput = pipe; task.standardError = FileHandle.nullDevice
            do { try task.run(); let data = pipe.fileHandleForReading.readDataToEndOfFile(); task.waitUntilExit()
                return String(data: data, encoding: .utf8)?.split(separator: "\n").first(where: { $0.hasPrefix("n/") }).map { String($0.dropFirst()) }
            } catch { return nil }
        }.value
        if let result { directory = result }
        return URL(fileURLWithPath: directory, isDirectory: true)
    }
    var hasActiveJobs: Bool {
        running && (isSSH || TerminalActivity.hasJobs(shellPID: view.process.shellPid, terminalFD: view.process.childfd))
    }
    func close() {
        guard running else { return }
        // Kill the foreground command as well as the login shell's process group.
        let pid = view.process.shellPid
        if pid > 0 {
            let foreground = tcgetpgrp(view.process.childfd)
            if foreground > 0 && foreground != getpgrp() { kill(-foreground, SIGHUP) }
            kill(-pid, SIGHUP)
            view.terminate()
        }
        running = false
    }
}

@MainActor final class TerminalWorkspace: ObservableObject {
    @Published var sessions: [TerminalSession] = []
    @Published var selected: UUID?
    let files = TerminalFileBrowser()
    private var identityTimer: Timer?
    private var scanningIdentity = false
    init() {
        identityTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in await self?.refreshIdentities() }
        }
    }
    func refreshIdentities() async {
        guard !scanningIdentity else { return }
        scanningIdentity = true
        defer { scanningIdentity = false }
        let pids = sessions.filter { $0.running }.map { $0.view.process.shellPid }
        let identities = await Task.detached(priority: .utility) { TerminalIdentity.scan(shells: pids) }.value
        for session in sessions { session.identity = session.running ? identities[session.view.process.shellPid] : nil }
    }
    @Published var showFiles = UserDefaults.standard.object(forKey: "terminalFilesVisible") as? Bool ?? true {
        didSet { UserDefaults.standard.set(showFiles, forKey: "terminalFilesVisible") }
    }
    var activeSessions: [TerminalSession] { sessions.filter { $0.hasActiveJobs } }
    var selectedSession: TerminalSession? { sessions.first { $0.id == selected } }
    func changeDirectory(_ url: URL) throws {
        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory), isDirectory.boolValue else { throw TerminalFileError.invalidDirectory }
        let command = try TerminalFileOperations.cdCommand(url.path)
        guard let session = selectedSession, session.running else { add(directory: url.path); return }
        guard !session.isSSH else { throw TerminalFileError.busyTerminal }
        let foreground = tcgetpgrp(session.view.process.childfd)
        guard foreground > 0, foreground == getpgid(session.view.process.shellPid) else { throw TerminalFileError.busyTerminal }
        session.view.send(txt: "\u{15}" + command)
        session.view.window?.makeFirstResponder(session.view)
    }
    private var nextNumber = 1
    func connect(_ profile: SSHProfile) {
        let session = TerminalSession(number: nextNumber, directory: NSHomeDirectory(), ssh: profile)
        nextNumber += 1; sessions.append(session); selected = session.id
    }
    func add(directory: String = NSHomeDirectory()) {
        let session = TerminalSession(number: nextNumber, directory: directory)
        nextNumber += 1
        sessions.append(session); selected = session.id
    }
    func close(_ session: TerminalSession) {
        session.close()
        sessions.removeAll { $0.id == session.id }
        if selected == session.id { selected = sessions.last?.id }
    }
    func shutdown() { for session in sessions { session.close() }; sessions.removeAll() }
}

struct NativeTerminal: NSViewRepresentable {
    @Environment(\.colorScheme) private var colorScheme
    let terminal: LocalProcessTerminalView
    func makeNSView(context: Context) -> NSView {
        let container = NSView()
        terminal.removeFromSuperview()
        terminal.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(terminal)
        NSLayoutConstraint.activate([
            terminal.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            terminal.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            terminal.topAnchor.constraint(equalTo: container.topAnchor),
            terminal.bottomAnchor.constraint(equalTo: container.bottomAnchor)
        ])
        DispatchQueue.main.async { terminal.window?.makeFirstResponder(terminal) }
        return container
    }
    func updateNSView(_ nsView: NSView, context: Context) {
        let dark = colorScheme == .dark
        terminal.nativeBackgroundColor = dark ? NSColor(calibratedRed: 0.035, green: 0.045, blue: 0.065, alpha: 1) : NSColor(calibratedRed: 0.97, green: 0.975, blue: 0.985, alpha: 1)
        terminal.nativeForegroundColor = dark ? NSColor(calibratedRed: 0.90, green: 0.94, blue: 0.97, alpha: 1) : NSColor(calibratedRed: 0.10, green: 0.13, blue: 0.20, alpha: 1)
        terminal.needsDisplay = true
    }
    // Removing a page never terminates its shell. The workspace owns the view.
}

struct TerminalWorkspaceView: View {
    @ObservedObject var workspace: TerminalWorkspace
    @State private var pending: TerminalSession?
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("应用内终端").font(.system(size: 25, weight: .semibold))
                Spacer()
                Button { workspace.showFiles.toggle() } label: { Label(workspace.showFiles ? "收起文件" : "展开文件", systemImage: "sidebar.left") }.buttonStyle(DeckButton())
                Button { chooseTerminalDirectory { workspace.add(directory: $0.path) } } label: { Label("从目录新建", systemImage: "folder.badge.plus") }
                Button { workspace.add() } label: { Label("新终端", systemImage: "plus") }.buttonStyle(DeckButton(primary: true))
            }
            Text("每个标签独立运行 · 切换页面不中断 · ⌘C 复制 / ⌘V 粘贴 / Ctrl+C 中断命令").foregroundStyle(.secondary).font(.caption)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(workspace.sessions) { session in
                        TerminalTab(session: session, selected: workspace.selected == session.id,
                                    select: { workspace.selected = session.id }, close: { pending = session })
                    }
                }
            }.frame(height: 42)
            HSplitView {
                if workspace.showFiles && workspace.selectedSession?.isSSH != true {
                    TerminalFilesPane(browser: workspace.files, cd: { try workspace.changeDirectory($0) }, newTerminal: { workspace.add(directory: $0.path) }, terminalDirectory: { await workspace.selectedSession?.currentDirectory() })
                        .frame(minWidth: 240, idealWidth: 280, maxWidth: 380)
                }
                terminalContent.frame(minWidth: 360, maxWidth: .infinity, maxHeight: .infinity)
            }
        }.padding(28)
        .confirmationDialog("关闭这个终端？其中运行的命令也会结束。", isPresented: Binding(get: { pending != nil }, set: { if !$0 { pending = nil } })) {
            Button("关闭终端", role: .destructive) { if let pending { workspace.close(pending) }; pending = nil }
        }
    }
    var terminalContent: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let session = workspace.sessions.first(where: { $0.id == workspace.selected }) {
                NativeTerminal(terminal: session.view).id(session.id).clipShape(RoundedRectangle(cornerRadius: 10))
                HStack {
                    Text(session.directory).lineLimit(1).textSelection(.enabled)
                    Spacer()
                    Text(session.running ? "运行中" : "会话已结束，可新建终端")
                }.font(.caption).foregroundStyle(.secondary)
            } else {
                VStack(spacing: 16) {
                    Image(systemName: "terminal").font(.system(size: 48)).foregroundStyle(.mint)
                    Text("打开一个终端，开始工作").font(.title2.bold())
                    Text("切换到服务列表或启动项页面后，终端仍会继续运行。").foregroundStyle(.secondary)
                    Button("新建终端") { workspace.add() }.buttonStyle(DeckButton(primary: true))
                }.frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
    }
}
struct TerminalTab: View {
    @ObservedObject var session: TerminalSession
    let selected: Bool
    let select: () -> Void
    let close: () -> Void
    var body: some View {
        HStack(spacing: 10) {
            Button(action: select) { HStack { Circle().fill(session.running ? Color.mint : .gray).frame(width: 7, height: 7); Text(session.displayTitle).lineLimit(1) } }.buttonStyle(.plain).help(session.identity.map { "\($0.name) · PID \($0.pid)\n\(session.directory)" } ?? session.directory)
            Button(action: close) { Image(systemName: "xmark").font(.caption) }.buttonStyle(.plain).help("关闭会话")
        }.padding(.horizontal, 14).padding(.vertical, 10).background(selected ? Deck.accent.opacity(0.18) : Deck.panel, in: RoundedRectangle(cornerRadius: 8))
    }
}
