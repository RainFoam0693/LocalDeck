import SwiftUI
import SwiftTerm
import AppKit
import Combine

struct Service: Codable, Identifiable {
    var id: String; var name: String; var command: String; var directory: String
    var usage: ResourceUsage? = nil
    var running: Bool; var pid: Int?; var exitCode: Int?
}
struct Listener: Codable, Identifiable {
    var pid: Int; var name: String; var ports: [Int]; var command: String; var directory: String
    var usage: ResourceUsage? = nil
    var id: Int { pid }
}
struct ServiceSnapshot: Codable { var services: [Service]; var listeners: [Listener]; var performance: PerformanceData? = nil }

@MainActor final class Store: ObservableObject {
    let terminals = TerminalWorkspace()
    @Published var state = ServiceSnapshot(services: [], listeners: [])
    @Published var performance: PerformanceData?
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
            performance = state.performance
            if let selected {
                let data = try await request("/logs/\(selected)")
                log = (try JSONSerialization.jsonObject(with: data) as? [String: String])?["text"] ?? ""
            }
        } catch { self.error = error.localizedDescription }
    }
    func refreshMetrics() async {
        guard ready else { return }
        if let data = try? await request("/metrics"), let metrics = try? JSONDecoder().decode(PerformanceData.self, from: data) { performance = metrics }
    }
    func act(_ path: String, body: [String: Any] = [:]) async {
        do { _ = try await request(path, body: body); await refresh() }
        catch { self.error = error.localizedDescription }
    }
    func shutdown() { terminals.shutdown(); process?.terminate() }
}

struct ContentView: View {
    @ObservedObject var store: Store
    @AppStorage("appearanceMode") private var appearanceMode = DeckAppearance.system.rawValue
    @State private var smokeStarted = false
    @State private var section = "overview"
    @State private var search = ""
    @State private var selectedPID: Int?
    @State private var sortByCPU = false
    @State private var adding = false
    @State private var showingSettings = false
    @State private var pending: Listener?
    @State private var name = ""
    @State private var command = ""
    @State private var directory = NSHomeDirectory()
    @State private var ticks = 0
    let timer = Timer.publish(every: 2, on: .main, in: .common).autoconnect()
    var listeners: [Listener] {
        let rows = store.state.listeners.filter { search.isEmpty || "\($0.name) \($0.command) \($0.ports)".localizedCaseInsensitiveContains(search) }
        return sortByCPU ? rows.sorted { ($0.usage?.cpuPercent ?? -1) > ($1.usage?.cpuPercent ?? -1) } : rows
    }
    var selectedListener: Listener? { listeners.first(where: { $0.pid == selectedPID }) ?? listeners.first }
    var body: some View {
        VStack(spacing: 0) {
            workspaceBar
            VStack(spacing: 0) {
                if section == "terminals" {
                    TerminalWorkspaceView(workspace: store.terminals)
                } else {
                    VStack(alignment: .leading, spacing: 22) {
                        header
                        PerformanceStrip(data: store.performance)
                        if section == "overview" { servicesPage } else { managedPage }
                    }.padding(.horizontal, 28).padding(.vertical, 20)
                }
                HStack(spacing: 8) {
                    Circle().fill(store.ready ? Deck.mint : .orange).frame(width: 5, height: 5)
                    Text(store.ready ? "此 Mac 已连接" : "正在连接")
                    Text("·").foregroundStyle(Deck.muted)
                    Text("CPU 按整机容量计 · 每 2 秒采样")
                    Spacer()
                    Text("LOCALDECK  /  \(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "DEV")").tracking(1)
                }.font(.system(size: 10)).foregroundStyle(Deck.muted).padding(.horizontal, 28).padding(.vertical, 12)
            }.background(Deck.background)
        }.background(Deck.sidebar).foregroundStyle(Deck.text).preferredColorScheme((DeckAppearance(rawValue: appearanceMode) ?? .system).scheme).frame(minWidth: 1120, minHeight: 760)
        .task { if CommandLine.arguments.contains("--terminal-smoke-test") && !smokeStarted { smokeStarted = true; await terminalSmokeTest() } }
        .onReceive(timer) { _ in ticks += 1; Task { await store.refreshMetrics(); if ticks % 2 == 0 { await store.refresh() } } }
        .alert("操作失败", isPresented: Binding(get: { !store.error.isEmpty }, set: { if !$0 { store.error = "" } })) { Button("好") { store.error = "" } } message: { Text(store.error) }
        .confirmationDialog("停止 \(pending?.name ?? "")？未保存的工作可能丢失。", isPresented: Binding(get: { pending != nil }, set: { if !$0 { pending = nil } })) {
            Button("停止进程", role: .destructive) { if let item = pending { Task { await store.act("/processes/stop", body: ["pid": item.pid, "command": item.command]) } }; pending = nil }
        }
        .sheet(isPresented: $adding) { addSheet }
        .sheet(isPresented: $showingSettings) { DeckSettingsView(workspace: store.terminals, files: store.terminals.files) }
    }
    var workspaceBar: some View {
        HStack(spacing: 20) {
            HStack(spacing: 10) {
                Image(systemName: "square.stack.3d.up.fill").font(.system(size: 23)).foregroundStyle(Deck.mint)
                Text("LocalDeck").font(.system(size: 18, weight: .semibold))
            }
            Spacer(minLength: 0)
            WorkspaceNavigation(selection: $section, terminals: store.terminals,
                                listenerCount: store.state.listeners.count, serviceCount: store.state.services.count)
                .frame(width: 480, height: 44)
            Spacer(minLength: 0)
            AppearanceControl()
            Button { showingSettings = true } label: { Image(systemName: "gearshape").font(.system(size: 17, weight: .medium)).frame(width: 22, height: 22) }
                .buttonStyle(SettingsGearButtonStyle()).help("设置").accessibilityLabel("设置")
        }
        .padding(.horizontal, 28).padding(.top, 30).padding(.bottom, 14)
        .background(.bar)
    }
    var header: some View {
        HStack(alignment: .center) {
            VStack(alignment: .leading, spacing: 8) {
                Text("工作空间  /  \(section == "overview" ? "服务概览" : "启动项")").font(.system(size: 10)).foregroundStyle(Deck.muted)
                Text(section == "overview" ? "服务概览" : "启动项").font(.system(size: 25, weight: .semibold))
            }
            Spacer()
            DeckGlassGroup { HStack(spacing: 10) {
            Button { Task { await store.refresh(); await store.refreshMetrics() } } label: { Image(systemName: "arrow.clockwise") }.buttonStyle(DeckButton())
            Button { adding = true } label: { Label("添加启动项", systemImage: "plus") }.buttonStyle(DeckButton(primary: true))
            } }
        }
    }
    var servicesPage: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("运行中的服务").font(.system(size: 15, weight: .semibold))
                Text("\(store.state.listeners.count) 个进程").font(.system(size: 10)).foregroundStyle(Deck.muted)
                Spacer()
                HStack { Image(systemName: "magnifyingglass").foregroundStyle(Deck.muted); TextField("搜索名称、端口或命令", text: $search).textFieldStyle(.plain) }.font(.system(size: 11)).padding(10).frame(width: 220).background(Deck.panel, in: RoundedRectangle(cornerRadius: 9))
                Button { sortByCPU.toggle() } label: { Label(sortByCPU ? "CPU 优先" : "默认排序", systemImage: "arrow.up.arrow.down") }.buttonStyle(DeckButton())
            }
            HStack(alignment: .top, spacing: 16) {
                ScrollView {
                    LazyVStack(spacing: 9) {
                        if listeners.isEmpty { DeckEmpty(title: "还没有找到服务", subtitle: "启动 API 或前端服务后，会自动出现在这里。") }
                        ForEach(listeners) { item in
                            ServiceRow(item: item, selected: selectedListener?.pid == item.pid) { selectedPID = item.pid }
                        }
                    }.padding(.bottom, 4)
                }.frame(maxWidth: .infinity)
                if let item = selectedListener {
                    ServiceInspector(item: item, stop: { pending = item }).frame(width: 260)
                }
            }.frame(maxHeight: .infinity)
        }
    }
    var managedPage: some View {
        HStack(alignment: .top, spacing: 18) {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    Text("已保存的启动项").font(.system(size: 14, weight: .semibold)).padding(.bottom, 4)
                    if store.state.services.isEmpty { DeckEmpty(title: "准备好第一个任务", subtitle: "保存目录与命令，下次一键启动。") }
                    ForEach(store.state.services) { item in
                        VStack(alignment: .leading, spacing: 14) {
                            HStack { Circle().fill(item.running ? Deck.mint : Deck.muted).frame(width: 6, height: 6); Text(item.name).font(.system(size: 13, weight: .semibold)); Spacer(); Text(item.running ? "运行中" : "已停止").font(.system(size: 10)).foregroundStyle(Deck.muted) }
                            Text(item.command).font(.system(size: 11, design: .monospaced)).foregroundStyle(Deck.muted).lineLimit(2)
                            UsageLine(usage: item.usage)
                            HStack(spacing: 8) {
                                Button(item.running ? "停止" : "启动") { Task { await store.act("/services/\(item.id)/\(item.running ? "stop" : "start")") } }.buttonStyle(DeckButton(primary: !item.running))
                                Button("重启") { Task { await store.act("/services/\(item.id)/restart") } }.buttonStyle(DeckButton())
                                Button("日志") { store.selected = item.id; Task { await store.refresh() } }.buttonStyle(DeckButton())
                                Spacer()
                                Button { Task { await store.act("/services/\(item.id)/delete") } } label: { Image(systemName: "trash") }.buttonStyle(.plain).foregroundStyle(Deck.muted).disabled(item.running)
                            }
                        }.padding(18).background(store.selected == item.id ? Deck.accent.opacity(0.10) : Deck.panel, in: RoundedRectangle(cornerRadius: 14)).overlay(RoundedRectangle(cornerRadius: 14).stroke(store.selected == item.id ? Deck.accent.opacity(0.4) : Deck.border))
                    }
                }
            }.frame(width: 345)
            VStack(alignment: .leading, spacing: 0) {
                HStack { Image(systemName: "terminal").foregroundStyle(Deck.mint); Text("实时日志").font(.system(size: 12, weight: .medium)); Spacer(); Text("最近 100 KB").font(.system(size: 10)).foregroundStyle(Deck.muted) }.padding(18)
                Rectangle().fill(Deck.border).frame(height: 1)
                ScrollView([.vertical, .horizontal]) { Text(store.log).font(.system(size: 11, design: .monospaced)).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .topLeading).padding(18) }
            }.background(Deck.console, in: RoundedRectangle(cornerRadius: 14)).overlay(RoundedRectangle(cornerRadius: 14).stroke(Deck.border))
        }.frame(maxHeight: .infinity)
    }
    var addSheet: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("添加启动项").font(.title2.bold())
            Text("为服务保存一个固定的启动方式。").foregroundStyle(Deck.muted)
            TextField("名称，例如我的 API", text: $name)
            TextField("启动命令，例如 npm run dev", text: $command)
            HStack { TextField("工作目录", text: $directory); Button("选择目录") { chooseTerminalDirectory { directory = $0.path } } }
            Text("交互式命令也可以直接在终端工作区运行。").font(.caption).foregroundStyle(Deck.muted)
            HStack { Spacer(); Button("取消") { adding = false }.buttonStyle(DeckButton()); Button("保存启动项") { let body = ["name": name, "command": command, "directory": directory]; Task { await store.act("/services", body: body) }; adding = false; section = "managed"; name = ""; command = "" }.buttonStyle(DeckButton(primary: true)).disabled(name.isEmpty || command.isEmpty || directory.isEmpty) }
        }.textFieldStyle(.roundedBorder).padding(30).frame(width: 540)
    }
    @MainActor func terminalSmokeTest() async {
        let workspace = store.terminals
        let previousAppearance = appearanceMode
        defer { appearanceMode = previousAppearance }
        var result: [String: Any] = ["ok": false]
        do {
            section = "terminals"
            workspace.add(); workspace.add()
            let first = workspace.sessions[0], second = workspace.sessions[1]
            try await Task.sleep(nanoseconds: 500_000_000)
            first.view.send(txt: "export LOCALDECK_TAB=ONE; sleep 1; printf '%s_BACKGROUND\\n' \"$LOCALDECK_TAB\"\r")
            second.view.send(txt: "export LOCALDECK_TAB=TWO; sleep 1; printf '%s_BACKGROUND\\n' \"$LOCALDECK_TAB\"\r")
            section = "overview"
            let originalPIDs = workspace.sessions.map { $0.view.process.shellPid }
            for mode in DeckAppearance.allCases {
                appearanceMode = mode.rawValue
                try await Task.sleep(nanoseconds: 200_000_000)
            }
            guard workspace.sessions.map({ $0.view.process.shellPid }) == originalPIDs else { throw NSError(domain: "Theme changed terminal identity", code: 5) }
            func output(_ session: TerminalSession) -> String { String(data: session.view.getTerminal().getBufferAsData(), encoding: .utf8) ?? "" }
            for _ in 0..<100 {
                if output(first).contains("ONE_BACKGROUND") && output(second).contains("TWO_BACKGROUND") { break }
                try await Task.sleep(nanoseconds: 100_000_000)
            }
            guard output(first).contains("ONE_BACKGROUND"), output(second).contains("TWO_BACKGROUND"), !output(first).contains("TWO_BACKGROUND") else { throw NSError(domain: "Background terminal continuity failed", code: 1) }
            // Feed many independent output chunks, including beyond the history limit.
            let scrolling = LocalProcessTerminalView(frame: NSRect(x: 0, y: 0, width: 800, height: 400))
            scrolling.getTerminal().changeHistorySize(100)
            scrolling.feed(text: (0..<200).map { "LOG_\($0)\r\n" }.joined())
            scrolling.scrollUp(lines: 20)
            let pinned = scrolling.getTerminal().getTopVisibleRow()
            let visibleLine = scrolling.getTerminal().getLine(row: 0)
            for number in 200..<205 { scrolling.feed(text: "LOG_\(number)\r\n") }
            guard scrolling.getTerminal().getTopVisibleRow() == pinned - 5,
                  scrolling.getTerminal().getLine(row: 0) === visibleLine else { throw NSError(domain: "History viewport jumped", code: 20) }
            scrolling.scroll(toPosition: 1)
            scrolling.feed(text: "LATEST\r\n")
            guard scrolling.scrollPosition == 1 else { throw NSError(domain: "Live output did not resume", code: 21) }
            let fileRoot = FileManager.default.temporaryDirectory.appendingPathComponent("LocalDeck Files " + UUID().uuidString)
            try FileManager.default.createDirectory(at: fileRoot, withIntermediateDirectories: false)
            defer { try? FileManager.default.removeItem(at: fileRoot) }
            let folderName = "目录 ' $(); & space"
            try TerminalFileOperations.create(in: fileRoot, name: folderName, folder: true)
            try TerminalFileOperations.create(in: fileRoot, name: "sample.txt", folder: false)
            try TerminalFileOperations.rename(fileRoot.appendingPathComponent("sample.txt"), name: "renamed.txt")
            do { try TerminalFileOperations.create(in: fileRoot, name: "renamed.txt", folder: false); throw NSError(domain: "Overwrite allowed", code: 10) }
            catch TerminalFileError.alreadyExists { }
            await workspace.files.navigate(fileRoot)
            guard workspace.files.entries.count == 2 else { throw NSError(domain: "File listing failed", code: 11) }
            workspace.selected = first.id
            let targetDirectory = fileRoot.appendingPathComponent(folderName)
            try workspace.changeDirectory(targetDirectory)
            try await Task.sleep(nanoseconds: 300_000_000)
            guard await first.currentDirectory()?.resolvingSymlinksInPath().path == targetDirectory.resolvingSymlinksInPath().path else { throw NSError(domain: "Quoted cd failed", code: 12) }
            guard await second.currentDirectory()?.resolvingSymlinksInPath().path != targetDirectory.resolvingSymlinksInPath().path else { throw NSError(domain: "cd changed other tab", code: 13) }
            section = "managed"
            first.view.send(txt: "sleep 30\r")
            try await Task.sleep(nanoseconds: 300_000_000)
            do { try workspace.changeDirectory(fileRoot); throw NSError(domain: "Busy terminal accepted cd", code: 14) }
            catch TerminalFileError.busyTerminal { }
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
            result = ["ok": true, "tabs": 2, "pageSwitch": true, "ctrlC": true, "closeIsolation": true, "exitCleanup": true, "themeContinuity": true, "fileListing": true, "fileOperations": true, "quotedCD": true, "busyCDGuard": true, "historyScroll": true]
        } catch { result["error"] = String(describing: error) }
        workspace.shutdown()
        if let data = try? JSONSerialization.data(withJSONObject: result, options: .prettyPrinted) { try? data.write(to: URL(fileURLWithPath: "/tmp/localdeck-mac-terminal-smoke.json")) }
        NSApp.terminate(nil)
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
