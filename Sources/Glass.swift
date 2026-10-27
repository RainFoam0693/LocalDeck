import SwiftUI

struct DeckGlassGroup<Content: View>: View {
    var spacing: CGFloat = 12
    @ViewBuilder var content: () -> Content
    @ViewBuilder var body: some View {
        if #available(macOS 26.0, *) { GlassEffectContainer(spacing: spacing, content: content) }
        else { content() }
    }
}
