import SwiftUI
import AppKit
import SwiftTerm
import Darwin

@MainActor final class TerminalSession: NSObject, ObservableObject, Identifiable, LocalProcessTerminalViewDelegate {
    let id = UUID()
    @Published var title: String
    @Published var running = true
    @Published var directory: String
    let view: LocalProcessTerminalView
    init(number: Int, directory: String) {
        self.title = "终端 \(number)"
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
        view.startProcess(executable: "/bin/zsh", args: ["-l"], environment: env.map { "\($0.key)=\($0.value)" }, currentDirectory: directory)
    }
    nonisolated func sizeChanged(source: LocalProcessTerminalView, newCols: Int, newRows: Int) {}
    nonisolated func setTerminalTitle(source: LocalProcessTerminalView, title: String) {
        if !title.isEmpty { Task { @MainActor [weak self] in self?.title = String(title.prefix(80)) } }
    }
    nonisolated func hostCurrentDirectoryUpdate(source: TerminalView, directory: String?) {
        if let directory { Task { @MainActor [weak self] in self?.directory = URL(string: directory)?.path ?? directory } }
    }
    nonisolated func processTerminated(source: TerminalView, exitCode: Int32?) { Task { @MainActor [weak self] in self?.running = false } }
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
    private var nextNumber = 1
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
    func updateNSView(_ nsView: NSView, context: Context) {}
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
                Button { let panel = NSOpenPanel(); panel.canChooseFiles = false; panel.canChooseDirectories = true; if panel.runModal() == .OK, let url = panel.url { workspace.add(directory: url.path) } } label: { Label("从目录新建", systemImage: "folder.badge.plus") }
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
        }.padding(28)
        .confirmationDialog("关闭这个终端？其中运行的命令也会结束。", isPresented: Binding(get: { pending != nil }, set: { if !$0 { pending = nil } })) {
            Button("关闭终端", role: .destructive) { if let pending { workspace.close(pending) }; pending = nil }
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
            Button(action: select) { HStack { Circle().fill(session.running ? Color.mint : .gray).frame(width: 7, height: 7); Text(session.title).lineLimit(1) } }.buttonStyle(.plain)
            Button(action: close) { Image(systemName: "xmark").font(.caption) }.buttonStyle(.plain).help("关闭会话")
        }.padding(.horizontal, 14).padding(.vertical, 10).background(selected ? Deck.accent.opacity(0.18) : Deck.panel, in: RoundedRectangle(cornerRadius: 8))
    }
}
