import SwiftUI
import AppKit
import Combine

struct Service: Codable, Identifiable {
    var id: String; var name: String; var command: String; var directory: String
    var running: Bool; var pid: Int?; var exitCode: Int?
}
struct Listener: Codable, Identifiable {
    var pid: Int; var name: String; var ports: [Int]; var command: String; var directory: String
    var id: Int { pid }
}
struct ServiceSnapshot: Codable { var services: [Service]; var listeners: [Listener] }

@MainActor final class Store: ObservableObject {
    let terminals = TerminalWorkspace()
    @Published var state = ServiceSnapshot(services: [], listeners: [])
    @Published var error = ""
    @Published var ready = false
    @Published var log = "选择一个服务查看日志"
    @Published var selected: String?
    private var process: Process?
    private var port = 0
    private var token = ""
    private var refreshing = false
    init() { Task { await boot() } }
    func boot() async {
        do {
            guard let script = Bundle.main.path(forResource: "server", ofType: "py") else { throw NSError(domain: "缺少后端文件", code: 1) }
            let p = Process(); let pipe = Pipe()
            p.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            p.arguments = ["python3", "-u", script]
            p.standardOutput = pipe
            try p.run(); process = p
            let data = await Task.detached { () -> Data in
                var result = Data()
                while let byte = try? pipe.fileHandleForReading.read(upToCount: 1), !byte.isEmpty {
                    if byte[0] == 10 { break }; result.append(byte)
                }
                return result
            }.value
            guard let info = try JSONSerialization.jsonObject(with: data) as? [String: Any], let port = info["port"] as? Int, let token = info["token"] as? String else { throw NSError(domain: "后端启动失败，请确认已安装 Python 3", code: 1) }
            self.port = port; self.token = token; ready = true
            await refresh()
        } catch { self.error = error.localizedDescription }
    }
    func request(_ path: String, body: [String: Any]? = nil) async throws -> Data {
        guard ready else { throw NSError(domain: "后端尚未就绪", code: 1) }
        var req = URLRequest(url: URL(string: "http://127.0.0.1:\(port)\(path)")!)
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.timeoutInterval = 20
        if let body { req.httpMethod = "POST"; req.httpBody = try JSONSerialization.data(withJSONObject: body); req.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        let (data, response) = try await URLSession.shared.data(for: req)
        if (response as? HTTPURLResponse)?.statusCode != 200 {
            let msg = (try? JSONSerialization.jsonObject(with: data) as? [String: String])?["error"] ?? "请求失败"
            throw NSError(domain: msg, code: 1, userInfo: [NSLocalizedDescriptionKey: msg])
        }
        return data
    }
    func refresh() async {
        guard ready, !refreshing else { return }; refreshing = true
        defer { refreshing = false }
        do {
            state = try JSONDecoder().decode(ServiceSnapshot.self, from: await request("/state"))
            if let selected {
                let data = try await request("/logs/\(selected)")
                log = (try JSONSerialization.jsonObject(with: data) as? [String: String])?["text"] ?? ""
            }
        } catch { self.error = error.localizedDescription }
    }
    func act(_ path: String, body: [String: Any] = [:]) async {
        do { _ = try await request(path, body: body); await refresh() }
        catch { self.error = error.localizedDescription }
    }
    func shutdown() { terminals.shutdown(); process?.terminate() }
}

struct ContentView: View {
    @ObservedObject var store: Store
    @State private var smokeStarted = false
    @State private var section = "overview"
    @State private var search = ""
    @State private var adding = false
    @State private var pending: Listener?
    @State private var name = ""
    @State private var command = ""
    @State private var directory = NSHomeDirectory()
    let timer = Timer.publish(every: 4, on: .main, in: .common).autoconnect()
    var listeners: [Listener] { store.state.listeners.filter { search.isEmpty || "\($0.name) \($0.command) \($0.ports)".localizedCaseInsensitiveContains(search) } }
    var body: some View {
        NavigationSplitView {
            VStack(alignment: .leading, spacing: 26) {
                HStack { Image(systemName: "square.stack.3d.up.fill").font(.title).foregroundStyle(.mint); Text("LocalDeck").font(.title2.bold()) }.padding(.top, 20)
                Text("本机开发工作台").foregroundStyle(.secondary)
                Button { section = "overview" } label: { Label("运行中的服务", systemImage: "network").frame(maxWidth: .infinity, alignment: .leading) }.buttonStyle(.bordered)
                Button { section = "managed" } label: { Label("我的启动项", systemImage: "terminal").frame(maxWidth: .infinity, alignment: .leading) }.buttonStyle(.bordered)
                Button { section = "terminals" } label: { Label("应用内终端", systemImage: "rectangle.split.3x1").frame(maxWidth: .infinity, alignment: .leading) }.buttonStyle(.bordered)
                Spacer()
                Label(store.ready ? "本机 API 已连接" : "正在连接 API", systemImage: "circle.fill").font(.caption).foregroundStyle(store.ready ? .mint : .orange)
                Text("退出应用会停止由本应用启动的服务。").font(.caption).foregroundStyle(.secondary)
            }.padding(20).frame(minWidth: 190)
        } detail: {
            if section == "terminals" {
                TerminalWorkspaceView(workspace: store.terminals).background(Color(red: 0.065, green: 0.08, blue: 0.10))
            } else {
            VStack(alignment: .leading, spacing: 22) {
                HStack {
                    VStack(alignment: .leading, spacing: 7) {
                        Text(section == "overview" ? "运行中的服务" : "我的启动项").font(.largeTitle.bold())
                        Text(section == "overview" ? "查看本机监听端口的 API、前端和开发工具" : "保存启动命令，集中管理服务与终端任务").foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button { Task { await store.refresh() } } label: { Image(systemName: "arrow.clockwise") }
                    Button { adding = true } label: { Label("添加启动项", systemImage: "plus") }.buttonStyle(.borderedProminent).tint(.mint)
                }
                HStack(spacing: 16) {
                    metric("监听进程", value: "\(store.state.listeners.count)", icon: "network")
                    metric("开放端口", value: "\(Set(store.state.listeners.flatMap(\.ports)).count)", icon: "point.3.connected.trianglepath.dotted")
                    metric("托管任务", value: "\(store.state.services.filter(\.running).count) / \(store.state.services.count)", icon: "terminal")
                }
                if section == "overview" {
                    TextField("搜索名称、命令或端口…", text: $search).textFieldStyle(.roundedBorder)
                    ScrollView {
                        LazyVStack(spacing: 10) {
                            if listeners.isEmpty { empty("没有找到监听端口的进程", subtitle: "启动 API 或前端服务后，会自动出现在这里。") }
                            ForEach(listeners) { item in
                                VStack(alignment: .leading, spacing: 12) {
                                    HStack {
                                        Image(systemName: "circle.fill").font(.system(size: 8)).foregroundStyle(.mint)
                                        Text(item.name).font(.headline)
                                        Text("PID \(String(item.pid))").font(.caption.monospaced()).foregroundStyle(.secondary)
                                        Spacer()
                                        ForEach(item.ports, id: \.self) { port in
                                            Button(":\(String(port))") { NSWorkspace.shared.open(URL(string: "http://localhost:\(port)")!) }.font(.system(.body, design: .monospaced)).help("使用 HTTP 在浏览器打开，非 HTTP 服务可能无法显示")
                                        }
                                        Button("停止", role: .destructive) { pending = item }
                                    }
                                    Text(item.command).font(.system(.caption, design: .monospaced)).foregroundStyle(.secondary).textSelection(.enabled).lineLimit(2)
                                    if !item.directory.isEmpty { Button { NSWorkspace.shared.open(URL(fileURLWithPath: item.directory)) } label: { Label(item.directory, systemImage: "folder") }.buttonStyle(.plain).font(.caption).foregroundStyle(.secondary) }
                                }.padding(16).background(.white.opacity(0.045), in: RoundedRectangle(cornerRadius: 12))
                            }
                        }
                    }
                } else {
                    HSplitView {
                        ScrollView {
                            VStack(spacing: 12) {
                                if store.state.services.isEmpty { empty("添加你的第一个启动项", subtitle: "例如 npm run dev、python3 main.py 或终端脚本。") }
                                ForEach(store.state.services) { item in
                                    VStack(alignment: .leading, spacing: 12) {
                                        HStack { Circle().fill(item.running ? Color.mint : Color.gray).frame(width: 8, height: 8); Text(item.name).bold(); Spacer(); Text(item.running ? "运行中" : "已停止").font(.caption).foregroundStyle(.secondary) }
                                        Text(item.command).font(.system(.caption, design: .monospaced)).lineLimit(2).textSelection(.enabled)
                                        HStack {
                                            Button(item.running ? "停止" : "启动") { Task { await store.act("/services/\(item.id)/\(item.running ? "stop" : "start")") } }
                                            Button("重启") { Task { await store.act("/services/\(item.id)/restart") } }
                                            Button("日志") { store.selected = item.id; Task { await store.refresh() } }
                                            Spacer()
                                            Button { Task { await store.act("/services/\(item.id)/delete") } } label: { Image(systemName: "trash") }.disabled(item.running)
                                        }
                                    }.padding(16).background(store.selected == item.id ? Color.mint.opacity(0.12) : .white.opacity(0.045), in: RoundedRectangle(cornerRadius: 12))
                                }
                            }.padding(.trailing, 10)
                        }.frame(minWidth: 340)
                        VStack(alignment: .leading) {
                            Label("终端输出 · 最近 100 KB", systemImage: "terminal").font(.headline)
                            ScrollView([.vertical, .horizontal]) { Text(store.log).font(.system(size: 12, design: .monospaced)).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .topLeading) }.padding(12).background(.black.opacity(0.3), in: RoundedRectangle(cornerRadius: 10))
                        }.padding(.leading, 16).frame(minWidth: 320)
                    }
                }
                Text("每 4 秒自动刷新 · 仅显示当前用户可访问的进程 · 任意终端任务可通过启动项托管").font(.caption).foregroundStyle(.secondary)
            }.padding(28).background(Color(red: 0.065, green: 0.08, blue: 0.10))
            }
        }.preferredColorScheme(.dark).frame(minWidth: 1060, minHeight: 700)
        .task { if CommandLine.arguments.contains("--terminal-smoke-test") && !smokeStarted { smokeStarted = true; await terminalSmokeTest() } }
        .onReceive(timer) { _ in Task { await store.refresh() } }
        .alert("操作失败", isPresented: Binding(get: { !store.error.isEmpty }, set: { if !$0 { store.error = "" } })) { Button("好") { store.error = "" } } message: { Text(store.error) }
        .confirmationDialog("停止 \(pending?.name ?? "")？未保存的工作可能丢失。", isPresented: Binding(get: { pending != nil }, set: { if !$0 { pending = nil } })) {
            Button("停止进程", role: .destructive) { if let item = pending { Task { await store.act("/processes/stop", body: ["pid": item.pid, "command": item.command]) } }; pending = nil }
        }
        .sheet(isPresented: $adding) {
            VStack(alignment: .leading, spacing: 18) {
                Text("添加启动项").font(.title2.bold())
                TextField("名称，例如我的 API", text: $name)
                TextField("启动命令，例如 npm run dev", text: $command)
                HStack {
                    TextField("工作目录（绝对路径）", text: $directory)
                    Button("选择…") { let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = false; if panel.runModal() == .OK { directory = panel.url?.path ?? directory } }
                }
                Text("命令通过 zsh 执行，输出保存为日志。交互命令请使用「应用内终端」。").font(.caption).foregroundStyle(.secondary)
                HStack { Spacer(); Button("取消") { adding = false }; Button("保存") { let body = ["name": name, "command": command, "directory": directory]; Task { await store.act("/services", body: body) }; adding = false; section = "managed"; name = ""; command = "" }.buttonStyle(.borderedProminent).disabled(name.isEmpty || command.isEmpty || directory.isEmpty) }
            }.textFieldStyle(.roundedBorder).padding(28).frame(width: 540)
        }
    }
    @MainActor func terminalSmokeTest() async {
        let workspace = store.terminals
        var result: [String: Any] = ["ok": false]
        do {
            section = "terminals"
            workspace.add(); workspace.add()
            let first = workspace.sessions[0], second = workspace.sessions[1]
            try await Task.sleep(nanoseconds: 500_000_000)
            first.view.send(txt: "export LOCALDECK_TAB=ONE; sleep 1; printf '%s_BACKGROUND\\n' \"$LOCALDECK_TAB\"\r")
            second.view.send(txt: "export LOCALDECK_TAB=TWO; sleep 1; printf '%s_BACKGROUND\\n' \"$LOCALDECK_TAB\"\r")
            section = "overview"
            func output(_ session: TerminalSession) -> String { String(data: session.view.getTerminal().getBufferAsData(), encoding: .utf8) ?? "" }
            for _ in 0..<100 {
                if output(first).contains("ONE_BACKGROUND") && output(second).contains("TWO_BACKGROUND") { break }
                try await Task.sleep(nanoseconds: 100_000_000)
            }
            guard output(first).contains("ONE_BACKGROUND"), output(second).contains("TWO_BACKGROUND"), !output(first).contains("TWO_BACKGROUND") else { throw NSError(domain: "Background terminal continuity failed", code: 1) }
            section = "managed"
            first.view.send(txt: "sleep 30\r")
            try await Task.sleep(nanoseconds: 300_000_000)
            first.view.send(txt: "\u{03}")
            try await Task.sleep(nanoseconds: 300_000_000)
            first.view.send(txt: "printf '%s_INTERRUPT\\n' \"$LOCALDECK_TAB\"\r")
            for _ in 0..<50 {
                if output(first).contains("ONE_INTERRUPT") { break }
                try await Task.sleep(nanoseconds: 100_000_000)
            }
            guard output(first).contains("ONE_INTERRUPT") else { throw NSError(domain: "Ctrl+C failed", code: 2) }
            section = "terminals"; workspace.selected = first.id
            try await Task.sleep(nanoseconds: 300_000_000)
            let firstPID = first.view.process.shellPid, secondPID = second.view.process.shellPid
            workspace.close(first)
            try await Task.sleep(nanoseconds: 500_000_000)
            guard kill(firstPID, 0) != 0, kill(secondPID, 0) == 0 else { throw NSError(domain: "Tab cleanup isolation failed", code: 3) }
            workspace.shutdown()
            try await Task.sleep(nanoseconds: 500_000_000)
            guard kill(secondPID, 0) != 0 else { throw NSError(domain: "Terminal shutdown failed", code: 4) }
            result = ["ok": true, "tabs": 2, "pageSwitch": true, "ctrlC": true, "closeIsolation": true, "exitCleanup": true]
        } catch { result["error"] = String(describing: error) }
        workspace.shutdown()
        if let data = try? JSONSerialization.data(withJSONObject: result, options: .prettyPrinted) { try? data.write(to: URL(fileURLWithPath: "/tmp/localdeck-mac-terminal-smoke.json")) }
        NSApp.terminate(nil)
    }
    func metric(_ title: String, value: String, icon: String) -> some View {
        HStack { VStack(alignment: .leading, spacing: 10) { Text(title).foregroundStyle(.secondary); Text(value).font(.system(size: 28, weight: .semibold, design: .rounded)) }; Spacer(); Image(systemName: icon).font(.title).foregroundStyle(.mint.opacity(0.7)) }.padding(20).frame(maxWidth: .infinity).background(.white.opacity(0.045), in: RoundedRectangle(cornerRadius: 14))
    }
    func empty(_ title: String, subtitle: String) -> some View {
        VStack(spacing: 12) { Image(systemName: "terminal").font(.largeTitle).foregroundStyle(.mint); Text(title).font(.headline); Text(subtitle).foregroundStyle(.secondary) }.frame(maxWidth: .infinity).padding(50)
    }
}
final class AppDelegate: NSObject, NSApplicationDelegate {
    var store: Store?
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) { MainActor.assumeIsolated { store?.shutdown() } }
}
@main struct LocalDeckApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate
    @StateObject private var store = Store()
    var body: some Scene {
        WindowGroup { ContentView(store: store).onAppear { delegate.store = store; NSApp.activate(ignoringOtherApps: true) } }.windowStyle(.hiddenTitleBar)
    }
}
