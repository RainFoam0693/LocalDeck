import SwiftUI
import AppKit

// A nil scheme lets SwiftUI track the user's system appearance in real time.
enum DeckAppearance: String, CaseIterable {
    case light, dark, system
    var scheme: ColorScheme? { self == .system ? nil : self == .light ? .light : .dark }
    var title: String { self == .system ? "跟随系统" : self == .light ? "浅色" : "深色" }
    var icon: String { self == .system ? "desktopcomputer" : self == .light ? "sun.max.fill" : "moon.fill" }
}

struct AppearanceControl: View {
    @AppStorage("appearanceMode") private var mode = DeckAppearance.system.rawValue
    @ViewBuilder var body: some View {
        if #available(macOS 27.0, *) {
            picker.pickerStyle(.tabs).controlSize(.extraLarge)
                .frame(width: 165, height: 44)
        } else if #available(macOS 26.0, *) {
            picker.pickerStyle(.segmented).controlSize(.extraLarge)
                .frame(width: 165, height: 44)
        } else {
            picker.pickerStyle(.segmented).controlSize(.large)
                .frame(width: 165, height: 40)
        }
    }
    private var picker: some View {
        Picker("外观", selection: $mode) {
            ForEach(DeckAppearance.allCases, id: \.rawValue) { appearance in
                Image(systemName: appearance.icon)
                    .accessibilityLabel(appearance.title)
                    .help(appearance.title)
                    .tag(appearance.rawValue)
            }
        }.labelsHidden()
    }
}
