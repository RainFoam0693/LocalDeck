import SwiftUI

struct WorkspaceNavigation: View {
    @Binding var selection: String
    @ObservedObject var terminals: TerminalWorkspace
    var listenerCount: Int
    var serviceCount: Int
    @ViewBuilder var body: some View {
        if #available(macOS 27.0, *) {
            picker.pickerStyle(.tabs).controlSize(.extraLarge)
        } else if #available(macOS 26.0, *) {
            picker.pickerStyle(.segmented).controlSize(.extraLarge)
        } else {
            picker.pickerStyle(.segmented).controlSize(.large)
        }
    }
    private var picker: some View {
        Picker("工作空间页面", selection: $selection) {
            Label("服务概览  \(listenerCount)", systemImage: "square.grid.2x2").tag("overview")
            Label("启动项  \(serviceCount)", systemImage: "play.rectangle").tag("managed")
            Label("终端工作区  \(terminals.sessions.count)", systemImage: "terminal").tag("terminals")
            Label("SSH 服务器", systemImage: "server.rack").tag("ssh")
        }
        .labelsHidden()
        .labelStyle(.titleAndIcon)
        .accessibilityLabel("工作空间页面")
    }
}
