import SwiftUI
import AppKit

struct ResourceUsage: Codable {
    var cpuPercent: Double?
    var memoryBytes: Double?
    var memoryPercent: Double?
    var memoryTotal: Double?
}
struct PerformancePoint: Codable { var time: Double; var cpu: Double?; var memory: Double? }
struct PerformanceData: Codable {
    var available: Bool
    var system: ResourceUsage
    var app: ResourceUsage
    var history: [PerformancePoint]
    var cpuCores: Int
    var updatedAt: Double?
    var error: String?
}

enum Deck {
    static func adaptive(_ dark: (Double, Double, Double), _ light: (Double, Double, Double)) -> Color {
        Color(nsColor: NSColor(name: nil) { appearance in
            let c = appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? dark : light
            return NSColor(calibratedRed: c.0, green: c.1, blue: c.2, alpha: 1)
        })
    }
    static let background = adaptive((0.055, 0.064, 0.09), (0.96, 0.965, 0.98))
    static let sidebar = adaptive((0.075, 0.085, 0.115), (0.925, 0.935, 0.96))
    static let panel = adaptive((0.085, 0.10, 0.14), (1, 1, 1))
    static let console = adaptive((0.035, 0.045, 0.065), (0.97, 0.975, 0.985))
    static let text = adaptive((0.91, 0.93, 0.97), (0.10, 0.13, 0.20))
    static let muted = adaptive((0.48, 0.53, 0.63), (0.38, 0.42, 0.50))
    static let mint = adaptive((0.30, 0.87, 0.72), (0.02, 0.48, 0.36))
    static let accent = adaptive((0.62, 0.57, 0.98), (0.40, 0.31, 0.80))
    static let border = adaptive((0.135, 0.15, 0.19), (0.86, 0.88, 0.92))
    static let button = adaptive((0.13, 0.14, 0.18), (0.92, 0.935, 0.96))
    static func percent(_ number: Double?) -> String { number.map { String(format: "%.1f%%", $0) } ?? "—" }
    static func bytes(_ number: Double?) -> String {
        guard let number else { return "—" }
        if number >= 1_073_741_824 { return String(format: "%.1f GB", number / 1_073_741_824) }
        return String(format: "%.0f MB", number / 1_048_576)
    }
}
struct DeckButton: PrimitiveButtonStyle {
    var primary = false
    @ViewBuilder func makeBody(configuration: Configuration) -> some View {
        if #available(macOS 26.0, *) {
            if primary {
                Button(configuration).buttonStyle(.glassProminent).tint(Deck.accent).controlSize(.regular)
            } else {
                Button(configuration).buttonStyle(.glass).controlSize(.regular)
            }
        } else {
            if primary {
                Button(configuration).buttonStyle(.borderedProminent).tint(Deck.accent).controlSize(.regular)
            } else {
                Button(configuration).buttonStyle(.bordered).controlSize(.regular)
            }
        }
    }
}
struct Sparkline: Shape {
    var values: [Double]
    func path(in rect: CGRect) -> Path {
        var path = Path()
        guard values.count > 1 else { return path }
        for (index, value) in values.enumerated() {
            let point = CGPoint(x: rect.width * CGFloat(index) / CGFloat(values.count - 1), y: rect.height * (1 - CGFloat(min(100, max(0, value))) / 100))
            if index == 0 { path.move(to: point) } else { path.addLine(to: point) }
        }
        return path
    }
}
struct PerformanceStrip: View {
    let data: PerformanceData?
    var valid: Bool { data?.available == true && Date().timeIntervalSince1970 - (data?.updatedAt ?? 0) < 10 }
    var body: some View {
        HStack(spacing: 14) {
            card(title: "系统 CPU", value: valid ? data?.system.cpuPercent : nil, icon: "cpu", color: Deck.mint,
                 detail: "\(data?.cpuCores ?? 0) 个逻辑核心 · 整机容量", history: data?.history.compactMap(\.cpu) ?? [])
            card(title: "物理内存", value: valid ? data?.system.memoryPercent : nil, icon: "memorychip", color: Deck.accent,
                 detail: "\(Deck.bytes(data?.system.memoryBytes)) / \(Deck.bytes(data?.system.memoryTotal))", history: data?.history.compactMap(\.memory) ?? [])
            card(title: "LocalDeck 自身", value: valid ? data?.app.cpuPercent : nil, icon: "square.stack.3d.up", color: Color(red: 0.42, green: 0.65, blue: 0.98),
                 detail: "内存 \(Deck.bytes(data?.app.memoryBytes)) · \(Deck.percent(data?.app.memoryPercent))", history: [])
        }.help(data?.error ?? "CPU 按整机总容量归一化到 0–100%；内存采用物理内存占比。LocalDeck 自身不包含用户的任务与终端。")
    }
    func card(title: String, value: Double?, icon: String, color: Color, detail: String, history: [Double]) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack { Label(title, systemImage: icon).font(.system(size: 11, weight: .medium)).foregroundStyle(Deck.muted); Spacer(); Circle().fill(value == nil ? Deck.muted : color).frame(width: 5, height: 5) }
            HStack(alignment: .center) {
                Text(Deck.percent(value)).font(.system(size: 31, weight: .semibold, design: .rounded)).tracking(-0.8)
                Spacer()
                if history.count > 1 { Sparkline(values: history).stroke(color.opacity(0.8), style: StrokeStyle(lineWidth: 1.7, lineJoin: .round)).frame(width: 70, height: 28) }
                else { ZStack { Circle().stroke(color.opacity(0.12), lineWidth: 4); Circle().trim(from: 0, to: CGFloat(value ?? 0) / 100).stroke(color, style: StrokeStyle(lineWidth: 4, lineCap: .round)).rotationEffect(.degrees(-90)) }.frame(width: 34, height: 34) }
            }
            Text(value == nil ? (valid ? "正在采样…" : "等待性能数据…") : detail).font(.system(size: 10)).foregroundStyle(Deck.muted).lineLimit(1)
        }.padding(19).frame(maxWidth: .infinity, alignment: .leading).background(Deck.panel, in: RoundedRectangle(cornerRadius: 15)).overlay(RoundedRectangle(cornerRadius: 15).stroke(Deck.border))
    }
}
struct UsageLine: View {
    var usage: ResourceUsage?
    var body: some View {
        HStack(spacing: 16) {
            Label("CPU \(Deck.percent(usage?.cpuPercent))", systemImage: "cpu")
            Label("\(Deck.bytes(usage?.memoryBytes)) · \(Deck.percent(usage?.memoryPercent))", systemImage: "memorychip")
        }.font(.system(size: 10, design: .monospaced)).foregroundStyle(Deck.muted)
    }
}
struct ServiceRow: View {
    let item: Listener
    let selected: Bool
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 13) {
                ZStack { RoundedRectangle(cornerRadius: 10).fill(Deck.mint.opacity(0.09)); Image(systemName: "server.rack").font(.system(size: 16)).foregroundStyle(Deck.mint) }.frame(width: 39, height: 42)
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 8) { Text(item.name).font(.system(size: 12, weight: .semibold)).lineLimit(1); Text("PID \(String(item.pid))").font(.system(size: 9, design: .monospaced)).foregroundStyle(Deck.muted) }
                    HStack(spacing: 7) { Circle().fill(Deck.mint).frame(width: 4, height: 4); Text(item.ports.prefix(3).map { ":\($0)" }.joined(separator: "  ")).font(.system(size: 10, design: .monospaced)).foregroundStyle(Deck.mint); if item.ports.count > 3 { Text("+\(item.ports.count - 3)").font(.system(size: 9)).foregroundStyle(Deck.muted) } }
                }
                Spacer(minLength: 8)
                VStack(alignment: .trailing, spacing: 8) { Text(Deck.percent(item.usage?.cpuPercent)).font(.system(size: 12, weight: .medium, design: .rounded)); Text(Deck.bytes(item.usage?.memoryBytes)).font(.system(size: 10, design: .monospaced)).foregroundStyle(Deck.muted) }
                Image(systemName: "chevron.right").font(.system(size: 9)).foregroundStyle(selected ? Deck.accent : Deck.muted.opacity(0.4))
            }.foregroundStyle(Deck.text).padding(14).background(selected ? Deck.accent.opacity(0.09) : Deck.panel, in: RoundedRectangle(cornerRadius: 13)).overlay(RoundedRectangle(cornerRadius: 13).stroke(selected ? Deck.accent.opacity(0.35) : Deck.border))
        }.buttonStyle(.plain)
    }
}
struct ServiceInspector: View {
    let item: Listener
    let stop: () -> Void
    var body: some View {
        VStack(spacing: 0) { ScrollView { VStack(alignment: .leading, spacing: 20) {
            HStack { Text("服务详情").font(.system(size: 11, weight: .medium)).foregroundStyle(Deck.muted); Spacer(); Text("RUNNING").font(.system(size: 8, weight: .medium)).tracking(1).foregroundStyle(Deck.mint) }
            VStack(alignment: .leading, spacing: 7) { Text(item.name).font(.system(size: 21, weight: .semibold)).textSelection(.enabled); Text("进程 \(String(item.pid))").font(.system(size: 10, design: .monospaced)).foregroundStyle(Deck.muted) }
            HStack {
                VStack(alignment: .leading, spacing: 6) { Text("CPU").font(.system(size: 9)).foregroundStyle(Deck.muted); Text(Deck.percent(item.usage?.cpuPercent)).font(.system(size: 20, weight: .medium, design: .rounded)) }
                Spacer()
                VStack(alignment: .leading, spacing: 6) { Text("内存 · \(Deck.percent(item.usage?.memoryPercent))").font(.system(size: 9)).foregroundStyle(Deck.muted); Text(Deck.bytes(item.usage?.memoryBytes)).font(.system(size: 20, weight: .medium, design: .rounded)) }
            }
            Rectangle().fill(Deck.border).frame(height: 1)
            VStack(alignment: .leading, spacing: 9) { caption("监听端口"); ScrollView(.horizontal, showsIndicators: false) { HStack(spacing: 6) { ForEach(item.ports, id: \.self) { port in Button(":\(String(port))") { NSWorkspace.shared.open(URL(string: "http://localhost:\(port)")!) }.buttonStyle(DeckButton()) } } } }
            VStack(alignment: .leading, spacing: 9) { caption("工作目录"); Text(item.directory.isEmpty ? "无法读取目录" : item.directory).font(.system(size: 10)).foregroundStyle(Deck.text.opacity(0.75)).textSelection(.enabled).lineLimit(3) }
            VStack(alignment: .leading, spacing: 9) { caption("启动命令"); ScrollView { Text(item.command).font(.system(size: 10, design: .monospaced)).foregroundStyle(Deck.muted).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }.frame(maxHeight: 115).padding(12).background(Deck.console, in: RoundedRectangle(cornerRadius: 9)) }

        }.padding(20) }
            Rectangle().fill(Deck.border).frame(height: 1)
HStack { Button { NSWorkspace.shared.open(URL(fileURLWithPath: item.directory)) } label: { Label("目录", systemImage: "folder") }.buttonStyle(DeckButton()).disabled(item.directory.isEmpty); Spacer(); Button(action: stop) { Label("停止", systemImage: "stop") }.buttonStyle(DeckButton()) }.padding(16)
        }.background(Deck.panel, in: RoundedRectangle(cornerRadius: 15)).overlay(RoundedRectangle(cornerRadius: 15).stroke(Deck.border))
    }
    func caption(_ title: String) -> some View { Text(title).font(.system(size: 10, weight: .medium)).foregroundStyle(Deck.muted) }
}
struct DeckEmpty: View {
    let title: String; let subtitle: String
    var body: some View {
        VStack(spacing: 12) { Image(systemName: "square.stack.3d.up").font(.system(size: 30)).foregroundStyle(Deck.accent); Text(title).font(.system(size: 14, weight: .medium)); Text(subtitle).font(.system(size: 11)).foregroundStyle(Deck.muted).multilineTextAlignment(.center) }.padding(35).frame(maxWidth: .infinity)
    }
}
