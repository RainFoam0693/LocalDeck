import SwiftUI

struct SSHProfile: Codable, Identifiable {
    var id = UUID()
    var name = ""
    var host = ""
    var user = "root"
    var port = "22"
    var key = ""
    var arguments: [String] {
        var args = ["-tt", "-p", port, "-l", user, "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3"]
        if !key.isEmpty { args += ["-i", NSString(string: key).expandingTildeInPath] }
        return args + [host]
    }
    var valid: Bool {
        !name.trimmingCharacters(in: .whitespaces).isEmpty && !host.isEmpty && !host.hasPrefix("-") && !user.isEmpty && !user.hasPrefix("-") &&
        !host.unicodeScalars.contains(where: { CharacterSet.whitespacesAndNewlines.union(.controlCharacters).contains($0) }) && !user.unicodeScalars.contains(where: { CharacterSet.whitespacesAndNewlines.union(.controlCharacters).contains($0) }) &&
        (Int(port).map { (1...65535).contains($0) } ?? false) && !key.contains("\n")
    }
}

struct SSHServersView: View {
    var connect: (SSHProfile) -> Void
    @AppStorage("sshProfiles") private var data = Data()
    @State private var profiles: [SSHProfile] = []
    @State private var draft = SSHProfile()
    @State private var editing = false
    @State private var deleting: SSHProfile?
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack {
                Text("SSH 服务器").font(.system(size: 25, weight: .semibold))
                Spacer()
                Button { draft = SSHProfile(); editing = true } label: { Label("添加服务器", systemImage: "plus") }.buttonStyle(DeckButton(primary: true))
            }
            Text("保存连接配置，下次一键连接。密码和私钥口令在终端内输入，不会保存到配置中。首次连接请核对服务器指纹。").font(.callout).foregroundStyle(.secondary)
            if profiles.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "server.rack").font(.system(size: 40))
                    Text("添加你的第一台 Linux 服务器").font(.title3)
                    Text("支持密码登录、SSH 密钥和系统 SSH Agent").foregroundStyle(.secondary)
                }.frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVStack(spacing: 12) {
                        ForEach(profiles) { profile in
                            HStack(spacing: 16) {
                                Image(systemName: "server.rack").font(.title2).foregroundStyle(Deck.mint)
                                VStack(alignment: .leading, spacing: 5) {
                                    Text(profile.name).font(.headline)
                                    Text("\(profile.user)@\(profile.host) : \(profile.port)").foregroundStyle(.secondary).textSelection(.enabled)
                                    Text(profile.key.isEmpty ? "系统 SSH 配置 / 密码 / Agent" : "指定 SSH 密钥").font(.caption).foregroundStyle(.secondary)
                                }
                                Spacer()
                                Button("编辑") { draft = profile; editing = true }.buttonStyle(DeckButton())
                                Button { deleting = profile } label: { Image(systemName: "trash") }.buttonStyle(DeckButton()).help("删除配置")
                                Button("连接") { connect(profile) }.buttonStyle(DeckButton(primary: true))
                            }.padding(20).background(Deck.panel, in: RoundedRectangle(cornerRadius: 14))
                        }
                    }
                }
            }
        }.padding(28)
        .onAppear { profiles = (try? JSONDecoder().decode([SSHProfile].self, from: data)) ?? [] }
        .sheet(isPresented: $editing) {
            VStack(alignment: .leading, spacing: 18) {
                Text("SSH 服务器配置").font(.title2.bold())
                Form {
                    TextField("名称", text: $draft.name)
                    TextField("主机 / IP / SSH 配置别名", text: $draft.host)
                    TextField("用户名", text: $draft.user)
                    TextField("端口", text: $draft.port)
                    HStack {
                        TextField("私钥路径（可选）", text: $draft.key)
                        Button("选择") {
                            let panel = NSOpenPanel(); panel.canChooseDirectories = false; panel.showsHiddenFiles = true
                            panel.begin { response in if response == .OK { draft.key = panel.url?.path ?? "" } }
                        }
                    }
                }
                Text("使用系统 OpenSSH，保留 known_hosts 校验。私钥文件只保存路径。").font(.caption).foregroundStyle(.secondary)
                HStack { Spacer(); Button("取消") { editing = false }; Button("保存") {
                    if let index = profiles.firstIndex(where: { $0.id == draft.id }) { profiles[index] = draft } else { profiles.append(draft) }
                    persist(); editing = false
                }.disabled(!draft.valid).buttonStyle(DeckButton(primary: true)) }
            }.padding(28).frame(width: 540)
        }
        .confirmationDialog("删除服务器配置？已打开的连接会继续运行。", isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } })) {
            Button("删除", role: .destructive) { profiles.removeAll { $0.id == deleting?.id }; persist(); deleting = nil }
        }
    }
    private func persist() { if let encoded = try? JSONEncoder().encode(profiles) { data = encoded } }
}
