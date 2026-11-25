import SwiftUI
import AppKit
import Security

struct DeckUpdateRelease: Codable, Sendable {
    let version: String
    let name: String
    let url: String
    let page: String
    let notes: String
    let digest: String
    let size: Int
    let checksum: String
}
private struct UpdateReply<T: Decodable>: Decodable {
    let ok: Bool
    let result: T?
    let error: String?
}

@MainActor final class AppUpdater: ObservableObject {
    @Published var release: DeckUpdateRelease?
    @Published var busy = false
    @Published var downloading = false
    @Published var downloaded: URL?
    @Published var dismissed = false
    @Published var message = "尚未检查更新"
    @Published var lastChecked: String
    @Published var automatic: Bool { didSet { defaults.set(automatic, forKey: "updatesAutomatic") } }
    let currentVersion = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "1.0.1"
    private let defaults = UserDefaults.standard
    private var timer: Timer?
    private var operation: Process?
    static let releasesURL = URL(string: "https://github.com/RainFoam0693/LocalDeck/releases")!
    init() {
        automatic = defaults.object(forKey: "updatesAutomatic") as? Bool ?? true
        lastChecked = defaults.string(forKey: "updatesLastChecked") ?? "尚无成功检查记录"
        if defaults.bool(forKey: "updatesAuthorized") { Self.removeLegacyUpdateCredential() }
        defaults.removeObject(forKey: "updatesAuthorized")
        if let data = defaults.data(forKey: "updatesAvailable"), let cached = try? JSONDecoder().decode(DeckUpdateRelease.self, from: data),
           cached.version.compare(currentVersion, options: .numeric) == .orderedDescending {
            release = cached; message = "发现新版本 " + cached.version
        }
        guard !CommandLine.arguments.contains("--terminal-smoke-test"), !CommandLine.arguments.contains("--preview") else { return }
        timer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in self?.scheduledCheck() }
        }
        Task { [weak self] in
            try? await Task.sleep(nanoseconds: 1_500_000_000)
            self?.scheduledCheck()
        }
    }
    private static func removeLegacyUpdateCredential() {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                    kSecAttrService as String: "dev.localdeck.github-updates",
                                    kSecAttrAccount as String: "GitHub"]
        SecItemDelete(query as CFDictionary)
    }
    static func dayKey(_ date: Date) -> String {
        let components = Calendar.current.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", components.year ?? 0, components.month ?? 0, components.day ?? 0)
    }
    func scheduledCheck() {
        let now = Date(), weekday = Calendar.current.component(.weekday, from: now)
        guard automatic, !busy, [2, 4, 6].contains(weekday), defaults.string(forKey: "updatesAttemptDay") != Self.dayKey(now) else { return }
        check()
    }
    func check() {
        guard !busy else { return }
        busy = true; message = "正在检查更新…"
        defaults.set(Self.dayKey(Date()), forKey: "updatesAttemptDay")
        Task {
            defer { busy = false }
            do {
                #if arch(arm64)
                let architecture = "arm64"
                #else
                let architecture = "x64"
                #endif
                let response: UpdateReply<DeckUpdateRelease> = try await invoke(["action": "check", "current": currentVersion, "platform": "macos", "architecture": architecture])
                release = response.result; dismissed = false; downloaded = nil
                message = release.map { "发现新版本 " + $0.version } ?? "当前已是最新正式版本"
                lastChecked = DateFormatter.localizedString(from: Date(), dateStyle: .short, timeStyle: .short)
                defaults.set(lastChecked, forKey: "updatesLastChecked")
                if let release { defaults.set(try JSONEncoder().encode(release), forKey: "updatesAvailable") }
                else { defaults.removeObject(forKey: "updatesAvailable") }
            } catch { message = error.localizedDescription }
        }
    }
    func confirmDownload() {
        guard !busy, let release else { return }
        let alert = NSAlert(); alert.messageText = "LocalDeck " + release.version
        alert.informativeText = "下载完成后，可选择安装并重启。配置会保留，终端任务不会迁移。\n\n" + String(release.notes.prefix(1800))
        alert.addButton(withTitle: "稍后"); alert.addButton(withTitle: "下载更新")
        if alert.runModal() == .alertSecondButtonReturn { download(release) }
    }
    private func download(_ release: DeckUpdateRelease) {
        guard !busy else { return }
        busy = true; downloading = true; message = "正在下载并校验更新…"
        Task {
            defer { busy = false; downloading = false }
            do {
                let destination = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Downloads")
                let object = try JSONSerialization.jsonObject(with: JSONEncoder().encode(release))
                let response: UpdateReply<String> = try await invoke(["action": "download", "release": object, "destination": destination.path])
                guard let path = response.result else { throw Self.failure("未收到下载文件。") }
                downloaded = URL(fileURLWithPath: path); message = "下载完成，SHA-256 校验通过"
            } catch { message = error.localizedDescription }
        }
    }
    private static func failure(_ message: String) -> NSError { NSError(domain: "LocalDeck.Update", code: 1, userInfo: [NSLocalizedDescriptionKey: message]) }
    private func invoke<T: Decodable>(_ command: [String: Any]) async throws -> UpdateReply<T> {
        guard let script = Bundle.main.path(forResource: "updates", ofType: "py") else { throw Self.failure("缺少更新组件，请重新安装软件。") }
        let input = try JSONSerialization.data(withJSONObject: command)
        let process = Process(); process.executableURL = URL(fileURLWithPath: "/usr/bin/env"); process.arguments = ["python3", "-B", "-u", script]
        let stdin = Pipe(), stdout = Pipe(); process.standardInput = stdin; process.standardOutput = stdout; process.standardError = FileHandle.nullDevice
        operation = process
        defer { operation = nil }
        let data = try await Task.detached(priority: .utility) {
            try process.run()
            try stdin.fileHandleForWriting.write(contentsOf: input); try stdin.fileHandleForWriting.close()
            let data = stdout.fileHandleForReading.readDataToEndOfFile(); process.waitUntilExit()
            return data
        }.value
        guard let response = try? JSONDecoder().decode(UpdateReply<T>.self, from: data) else { throw Self.failure("更新组件未返回有效结果，请稍后重试。") }
        guard response.ok else { throw Self.failure(response.error ?? "更新失败，请稍后重试。") }
        return response
    }
    var installRequested = false

    func openDownload() {
        guard downloaded != nil else { return }
        installRequested = true
        NSApp.terminate(nil)
        installRequested = false
    }

    func launchInstaller() -> Bool {
        guard let downloaded, let release,
              let script = Bundle.main.url(forResource: "install-update", withExtension: "sh") else { return false }
        let target = Bundle.main.bundleURL
        guard target.pathExtension == "app", !target.path.contains("/AppTranslocation/"),
              FileManager.default.isWritableFile(atPath: target.deletingLastPathComponent().path) else {
            message = "此位置无法自动安装。请在下载目录打开安装包，或将应用移到可写目录。"
            return false
        }
        let helper = Process()
        helper.executableURL = URL(fileURLWithPath: "/bin/sh")
        helper.arguments = [script.path, String(ProcessInfo.processInfo.processIdentifier), downloaded.path, target.path, release.version]
        do { try helper.run(); return true }
        catch { message = "无法启动安装程序：" + error.localizedDescription; return false }
    }
    func openReleases() { NSWorkspace.shared.open(Self.releasesURL) }
    func shutdown() { timer?.invalidate(); if operation?.isRunning == true { operation?.terminate() } }
}

struct UpdateBanner: View {
    @ObservedObject var updater: AppUpdater
    var body: some View {
        if let release = updater.release, !updater.dismissed {
            HStack(spacing: 14) {
                Image(systemName: "arrow.down.circle").font(.title2).foregroundStyle(Deck.accent)
                VStack(alignment: .leading, spacing: 3) {
                    Text("LocalDeck \(release.version) 可用").font(.system(size: 13, weight: .semibold))
                    Text(updater.message.hasPrefix("发现新版本") ? "查看更新说明，由你决定何时下载。" : updater.message).font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                if updater.busy { ProgressView().controlSize(.small) }
                Button(updater.downloaded == nil ? "查看更新" : "安装并重启") {
                    if updater.downloaded != nil { updater.openDownload() } else { updater.confirmDownload() }
                }.buttonStyle(DeckButton(primary: true)).disabled(updater.busy)
                Button("稍后") { updater.dismissed = true }.buttonStyle(DeckButton())
            }.padding(14).background(Deck.accent.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
                .padding(.horizontal, 28).padding(.top, 12)
        }
    }
}
