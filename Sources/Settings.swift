import SwiftUI
import AppKit

struct DeckSettingsView: View {
    @ObservedObject var workspace: TerminalWorkspace
    @ObservedObject var files: TerminalFileBrowser
    @ObservedObject var updater: AppUpdater
    @Environment(\.dismiss) private var dismiss
    @AppStorage("appearanceMode") private var appearance = DeckAppearance.system.rawValue
    @State private var accessResult = "未检查。检查只读取你选择的目录，不会修改文件。"
    @State private var checking = false
    @State private var updateToken = ""
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack { Label("设置", systemImage: "gearshape").font(.title2.bold()); Spacer(); Button("完成") { dismiss() }.buttonStyle(DeckButton()) }
            Form {
                Section("软件更新") {
                    HStack { Text("当前版本 " + updater.currentVersion); Spacer(); if updater.busy { ProgressView().controlSize(.small) } }
                    Text(updater.message).font(.callout).textSelection(.enabled)
                    Text("上次成功检查：" + updater.lastChecked).font(.caption).foregroundStyle(.secondary)
                    Toggle("每周一、三、五自动检查更新", isOn: $updater.automatic)
                    Text("应用运行时每天检查一次。只提示新版本，下载与替换由你确认。").font(.caption).foregroundStyle(.secondary)
                    HStack {
                        Button("检查更新") { updater.check() }.buttonStyle(DeckButton()).disabled(updater.busy)
                        if updater.release != nil {
                            Button(updater.downloaded == nil ? "下载更新" : "打开安装包") {
                                if updater.downloaded != nil { updater.openDownload() } else { updater.confirmDownload() }
                            }.buttonStyle(DeckButton(primary: true)).disabled(updater.busy)
                        }
                        Button("GitHub 发行页") { updater.openReleases() }.buttonStyle(DeckButton())
                    }
                }
                Section("私有仓库授权（可选）") {
                    Text(updater.authorized ? "已保存到系统钥匙串" : "公开仓库无需授权；私有仓库需要 GitHub 访问令牌。")
                        .font(.caption).foregroundStyle(.secondary)
                    SecureField("GitHub 访问令牌", text: $updateToken)
                    HStack {
                        Button("保存授权") { updater.saveAuthorization(updateToken); updateToken = "" }.disabled(updater.busy || updateToken.isEmpty).buttonStyle(DeckButton())
                        if updater.authorized { Button("移除授权") { updater.saveAuthorization("") }.disabled(updater.busy).buttonStyle(DeckButton()) }
                        Link("创建只读令牌", destination: URL(string: "https://github.com/settings/personal-access-tokens/new")!)
                    }
                    Text("选择 LocalDeck 仓库，仅开启 Contents → Read-only。令牌仅用于 GitHub 更新请求。").font(.caption).foregroundStyle(.secondary)
                }
                Section("文件访问") {
                    Text("允许访问所有文件").font(.headline)
                    Text("在 macOS 的“隐私与安全性 → 完全磁盘访问权限”中添加并开启 LocalDeck。授权后，如果系统提示，请退出并重新打开软件。")
                        .font(.callout).foregroundStyle(.secondary)
                    HStack {
                        Button("打开完全磁盘访问权限") { openPrivacy("Privacy_AllFiles") }.buttonStyle(DeckButton(primary: true))
                        Button("在 Finder 中显示本软件") { NSWorkspace.shared.activateFileViewerSelecting([Bundle.main.bundleURL]) }.buttonStyle(DeckButton())
                    }
                    Button("管理桌面、文稿等文件夹权限") { openPrivacy("Privacy_FilesAndFolders") }.buttonStyle(DeckButton())
                    Text("权限由系统管理；LocalDeck 不会自行开启权限，也不扫描无关目录。文件的读写仍受当前账户权限限制。")
                        .font(.caption).foregroundStyle(.secondary)
                    HStack {
                        Button(checking ? "正在检查…" : "选择目录并检查访问") { checkAccess() }.disabled(checking).buttonStyle(DeckButton())
                        Text(accessResult).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                    }
                }
                Section("外观") {
                    Picker("显示模式", selection: $appearance) { ForEach(DeckAppearance.allCases, id: \.rawValue) { mode in Text(mode.title).tag(mode.rawValue) } }
                        .pickerStyle(.segmented)
                }
                Section("终端与文件") {
                    Toggle("显示文件面板", isOn: $workspace.showFiles)
                    Toggle("显示隐藏文件", isOn: $files.showHidden)
                    Text("向上翻阅日志时暂停跟随，回到底部自动恢复。收起文件面板不会结束终端会话。")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Section("关于") {
                    Text("LocalDeck · \(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "开发版")")
                    Text("服务、文件与终端都在本机运行。").font(.caption).foregroundStyle(.secondary)
                    Link(destination: URL(string: "https://github.com/RainFoam0693")!) {
                        HStack(spacing: 12) {
                            Image(systemName: "person.crop.circle.fill").font(.system(size: 30)).foregroundStyle(Deck.accent)
                            VStack(alignment: .leading, spacing: 4) {
                                Text("RainFoam0693").font(.system(size: 14, weight: .semibold)).foregroundStyle(Deck.text)
                                Text("GitHub · 开发者主页").font(.caption).foregroundStyle(Deck.muted)
                            }
                            Spacer()
                            Image(systemName: "arrow.up.right").font(.system(size: 13, weight: .medium)).foregroundStyle(Deck.muted)
                        }.padding(12).background(Deck.accent.opacity(0.07), in: RoundedRectangle(cornerRadius: 12))
                            .contentShape(RoundedRectangle(cornerRadius: 12))
                    }.buttonStyle(.plain).accessibilityLabel("RainFoam0693 的 GitHub 主页")
                }
            }.formStyle(.grouped)
        }.padding(24).frame(width: 640, height: 640)
    }
    func openPrivacy(_ anchor: String) {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?" + anchor), NSWorkspace.shared.open(url) { return }
        NSWorkspace.shared.open(URL(fileURLWithPath: "/System/Applications/System Settings.app"))
    }
    func checkAccess() {
        chooseTerminalDirectory { url in
            checking = true
            Task {
                let message = await Task.detached(priority: .userInitiated) {
                    do { _ = try FileManager.default.contentsOfDirectory(at: url, includingPropertiesForKeys: nil); return "可读取：" + url.path }
                    catch { return "无法读取：" + error.localizedDescription }
                }.value
                accessResult = message; checking = false
            }
        }
    }
}

/// A sheet keeps terminal rendering and the rest of the app responsive during selection.
@MainActor func chooseTerminalDirectory(start: URL? = nil, completion: @escaping (URL) -> Void) {
    let panel = NSOpenPanel(); panel.canChooseFiles = false; panel.canChooseDirectories = true
    panel.allowsMultipleSelection = false; panel.canCreateDirectories = true
    if let start { panel.directoryURL = start }
    let callback: (NSApplication.ModalResponse) -> Void = { response in
        if response == .OK, let url = panel.url { completion(url) }
    }
    if let window = NSApp.keyWindow { panel.beginSheetModal(for: window, completionHandler: callback) }
    else { panel.begin(completionHandler: callback) }
}

struct SettingsGearButtonStyle: PrimitiveButtonStyle {
    @ViewBuilder func makeBody(configuration: Configuration) -> some View {
        if #available(macOS 26.0, *) {
            Button(configuration).buttonStyle(.glass).buttonBorderShape(.circle).controlSize(.large)
        } else {
            Button(configuration).buttonStyle(.borderless).padding(8).background(.quaternary, in: Circle())
        }
    }
}
