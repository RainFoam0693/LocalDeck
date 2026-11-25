import SwiftUI
import AppKit
import Darwin

struct TerminalFileEntry: Identifiable, Sendable, Equatable {
    var url: URL
    var name: String
    var directory: Bool
    var hidden: Bool
    var size: Int
    var id: URL { url }
}

enum TerminalFileError: LocalizedError {
    case invalidName, alreadyExists, invalidDirectory, unsafePath, busyTerminal
    var errorDescription: String? {
        switch self {
        case .invalidName: return "名称不能为空、不能为 . 或 ..，也不能包含斜杠或控制字符。"
        case .alreadyExists: return "此名称已存在，请换一个名称。"
        case .invalidDirectory: return "目录不存在或无法访问。"
        case .unsafePath: return "此路径含有控制字符，无法安全发送到终端。"
        case .busyTerminal: return "当前终端正在运行命令。请先回到 Shell 提示符，或选择“在此目录新建终端”。"
        }
    }
}

struct TerminalFileOperations {
    static func validateName(_ name: String) throws {
        guard !name.isEmpty, name != ".", name != "..", !name.contains("/"),
              !name.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) }) else { throw TerminalFileError.invalidName }
    }
    static func create(in directory: URL, name: String, folder: Bool) throws {
        try validateName(name)
        let target = directory.appendingPathComponent(name)
        guard !FileManager.default.fileExists(atPath: target.path) else { throw TerminalFileError.alreadyExists }
        if folder { try FileManager.default.createDirectory(at: target, withIntermediateDirectories: false) }
        else {
            // O_EXCL prevents replacing an existing file even if it appears after the check.
            let fd = Darwin.open(target.path, O_WRONLY | O_CREAT | O_EXCL, S_IRUSR | S_IWUSR | S_IRGRP | S_IROTH)
            guard fd >= 0 else { throw NSError(domain: NSPOSIXErrorDomain, code: Int(errno)) }
            Darwin.close(fd)
        }
    }
    static func rename(_ source: URL, name: String) throws {
        try validateName(name)
        let target = source.deletingLastPathComponent().appendingPathComponent(name)
        if target == source { return }
        guard !FileManager.default.fileExists(atPath: target.path) else { throw TerminalFileError.alreadyExists }
        try FileManager.default.moveItem(at: source, to: target)
    }
    static func cdCommand(_ path: String) throws -> String {
        guard !path.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) }) else { throw TerminalFileError.unsafePath }
        let quoted = "'" + path.replacingOccurrences(of: "'", with: "'\\''") + "'"
        return "builtin cd -- " + quoted + "\r"
    }
}

@MainActor final class TerminalFileBrowser: ObservableObject {
    @Published var directory = URL(fileURLWithPath: NSHomeDirectory(), isDirectory: true)
    @Published var entries: [TerminalFileEntry] = []
    @Published var showHidden = UserDefaults.standard.bool(forKey: "terminalShowHidden") {
        didSet { UserDefaults.standard.set(showHidden, forKey: "terminalShowHidden") }
    }
    @Published var loading = false
    @Published var error = ""
    @Published var query = ""
    private var history: [URL] = []
    private var generation = UUID()
    var canGoBack: Bool { !history.isEmpty }
    var visible: [TerminalFileEntry] {
        entries.filter { (showHidden || !$0.hidden) && (query.isEmpty || $0.name.localizedCaseInsensitiveContains(query)) }
    }
    private var didLoad = false
    func loadIfNeeded() async {
        guard !didLoad else { return }
        await navigate(directory, record: false)
    }
    func navigate(_ target: URL, record: Bool = true) async {
        didLoad = true
        let target = target.standardizedFileURL
        let request = UUID(); generation = request; loading = true; error = ""
        do {
            let result = try await Task.detached(priority: .userInitiated) {
                let keys: Set<URLResourceKey> = [.isDirectoryKey, .isHiddenKey, .fileSizeKey]
                return try FileManager.default.contentsOfDirectory(at: target, includingPropertiesForKeys: nil).map { url in
                    // The home listing can show these folders without requesting access to them.
                    if target.path == NSHomeDirectory(), ["Desktop", "Documents", "Downloads"].contains(url.lastPathComponent) {
                        return TerminalFileEntry(url: url, name: url.lastPathComponent, directory: true, hidden: false, size: 0)
                    }
                    let info = try? url.resourceValues(forKeys: keys)
                    return TerminalFileEntry(url: url, name: url.lastPathComponent, directory: info?.isDirectory == true,
                                             hidden: info?.isHidden == true || url.lastPathComponent.hasPrefix("."), size: info?.fileSize ?? 0)
                }.sorted { left, right in
                    if left.directory != right.directory { return left.directory }
                    return left.name.localizedStandardCompare(right.name) == .orderedAscending
                }
            }.value
            guard generation == request else { return }
            if record && target != directory { history.append(directory) }
            directory = target; entries = result
        } catch {
            guard generation == request else { return }
            self.error = error.localizedDescription
        }
        if generation == request { loading = false }
    }
    func back() async {
        guard let target = history.popLast() else { return }
        await navigate(target, record: false)
    }
    func refresh() async { await navigate(directory, record: false) }
}

struct TerminalFilesPane: View {
    @ObservedObject var browser: TerminalFileBrowser
    let cd: (URL) throws -> Void
    let newTerminal: (URL) -> Void
    let terminalDirectory: () async -> URL?
    @State private var path = ""
    @State private var editing = false
    @State private var editName = ""
    @State private var renameTarget: URL?
    @State private var createIn: URL?
    @State private var createFolder = false
    @State private var trashTarget: TerminalFileEntry?
    @State private var actionError = ""
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label("文件", systemImage: "folder").font(.system(size: 13, weight: .semibold))
                Spacer()
                Button { chooseDirectory() } label: { Image(systemName: "folder.badge.gearshape") }.help("选择目录")
                Button { Task { await browser.refresh() } } label: { Image(systemName: "arrow.clockwise") }.help("刷新")
            }.buttonStyle(.borderless)
            HStack(spacing: 10) {
                Button { Task { await browser.back() } } label: { Image(systemName: "chevron.left") }.disabled(!browser.canGoBack).help("后退")
                Button { Task { await browser.navigate(browser.directory.deletingLastPathComponent()) } } label: { Image(systemName: "arrow.up") }.help("上一级")
                Button { Task { if let url = await terminalDirectory() { await browser.navigate(url) } } } label: { Label("定位终端目录", systemImage: "scope") }.font(.system(size: 10))
                Spacer(minLength: 0)
            }.buttonStyle(.borderless)
            TextField("目录路径，回车前往", text: $path).textFieldStyle(.roundedBorder).font(.system(size: 11))
                .onSubmit {
                    let expanded = NSString(string: path).expandingTildeInPath
                    let target = expanded.hasPrefix("/") ? URL(fileURLWithPath: expanded) : browser.directory.appendingPathComponent(expanded)
                    Task { await browser.navigate(target) }
                }
            HStack {
                Image(systemName: "magnifyingglass").foregroundStyle(Deck.muted)
                TextField("筛选文件", text: $browser.query).textFieldStyle(.plain)
            }.font(.system(size: 11)).padding(8).background(Deck.console, in: RoundedRectangle(cornerRadius: 7))
            if !browser.error.isEmpty { Text(browser.error).font(.caption).foregroundStyle(.red).textSelection(.enabled) }
            NativeTerminalFilesList(entries: browser.visible, open: open, makeMenu: nativeMenu)
                .overlay { if browser.loading { ProgressView().controlSize(.small) } else if browser.visible.isEmpty { Text("没有匹配的文件").font(.caption).foregroundStyle(Deck.muted).allowsHitTesting(false) } }
            HStack {
                Text("\(browser.visible.count) 项").font(.system(size: 10)).foregroundStyle(Deck.muted)
                Spacer()
                Toggle("隐藏项目", isOn: $browser.showHidden).toggleStyle(.checkbox).font(.system(size: 10))
            }
            Button { performCD(browser.directory) } label: { Label("cd 到此目录", systemImage: "terminal") }
                .buttonStyle(DeckButton()).help("切换当前终端目录；没有终端时自动新建")
        }.padding(14).background(Deck.panel, in: RoundedRectangle(cornerRadius: 12))
        .onAppear { path = browser.directory.path }
        .task { await browser.loadIfNeeded() }
        .onChange(of: browser.directory) { path = $0.path }
        .sheet(isPresented: $editing) { editSheet }
        .alert("文件操作失败", isPresented: Binding(get: { !actionError.isEmpty }, set: { if !$0 { actionError = "" } })) { Button("好") { actionError = "" } } message: { Text(actionError) }
        .confirmationDialog("将“\(trashTarget?.name ?? "")”移到废纸篓？", isPresented: Binding(get: { trashTarget != nil }, set: { if !$0 { trashTarget = nil } })) {
            Button("移到废纸篓", role: .destructive) {
                if let entry = trashTarget { run { _ = try FileManager.default.trashItem(at: entry.url, resultingItemURL: nil) } }
                trashTarget = nil
            }
        }
    }
    func nativeMenu(_ entry: TerminalFileEntry?) -> NSMenu {
        let menu = NSMenu()
        let directory = entry.map { $0.directory ? $0.url : $0.url.deletingLastPathComponent() } ?? browser.directory
        func action(_ title: String, _ handler: @escaping () -> Void) { menu.addItem(FileMenuAction.item(title, handler)) }
        if let entry { action(entry.directory ? "打开文件夹" : "打开文件") { open(entry) } }
        action("在当前终端 cd 到此目录") { performCD(directory) }
        action("在此目录新建终端") { newTerminal(directory) }
        menu.addItem(.separator())
        action("复制完整路径") { copy(entry?.url.path ?? directory.path) }
        if let entry { action("复制名称") { copy(entry.name) } }
        action("在 Finder 中显示") { NSWorkspace.shared.activateFileViewerSelecting([entry?.url ?? directory]) }
        menu.addItem(.separator())
        action("新建文件夹…") { beginCreate(in: directory, folder: true) }
        action("新建文件…") { beginCreate(in: directory, folder: false) }
        if let entry {
            action("重命名…") { renameTarget = entry.url; createIn = nil; editName = entry.name; editing = true }
            action("移到废纸篓…") { trashTarget = entry }
        }
        menu.addItem(.separator()); action("刷新") { Task { await browser.refresh() } }
        return menu
    }
    var editSheet: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text(renameTarget != nil ? "重命名" : createFolder ? "新建文件夹" : "新建文件").font(.headline)
            TextField("名称", text: $editName).textFieldStyle(.roundedBorder).onSubmit { saveEdit() }
            HStack { Spacer(); Button("取消") { editing = false }.buttonStyle(DeckButton()); Button("保存") { saveEdit() }.buttonStyle(DeckButton(primary: true)).disabled(editName.isEmpty) }
        }.padding(24).frame(width: 360)
    }
    func saveEdit() {
        do {
            if let source = renameTarget { try TerminalFileOperations.rename(source, name: editName) }
            else { try TerminalFileOperations.create(in: createIn ?? browser.directory, name: editName, folder: createFolder) }
            editing = false; Task { await browser.refresh() }
        } catch { actionError = error.localizedDescription; editing = false }
    }
    func beginCreate(in directory: URL, folder: Bool) { createIn = directory; renameTarget = nil; createFolder = folder; editName = folder ? "未命名文件夹" : "未命名.txt"; editing = true }
    func run(_ operation: () throws -> Void) { do { try operation(); Task { await browser.refresh() } } catch { actionError = error.localizedDescription } }
    func performCD(_ directory: URL) { do { try cd(directory) } catch { actionError = error.localizedDescription } }
    func copy(_ text: String) { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(text, forType: .string) }
    func open(_ entry: TerminalFileEntry) { if entry.directory { Task { await browser.navigate(entry.url) } } else { NSWorkspace.shared.open(entry.url) } }
    func chooseDirectory() { chooseTerminalDirectory(start: browser.directory) { url in Task { await browser.navigate(url) } } }
}
