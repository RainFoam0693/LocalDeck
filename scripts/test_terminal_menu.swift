import AppKit
import SwiftTerm

@main struct TerminalMenuTests {
    static func main() {
        _ = NSApplication.shared
        let clipboard = NSPasteboard.general
        let saved = (clipboard.pasteboardItems ?? []).map { item in item.types.compactMap { type in item.data(forType: type).map { (type, $0) } } }
        defer {
            clipboard.clearContents()
            let restored = saved.map { values in
                let item = NSPasteboardItem()
                for (type, data) in values { item.setData(data, forType: type) }
                return item
            }
            clipboard.writeObjects(restored)
        }
        let view = DeckTerminalView(frame: NSRect(x: 0, y: 0, width: 800, height: 320))
        view.feed(text: (0..<100).map { "MENU_LOG_\($0)\r\n" }.joined())
        func item(_ title: String) -> NSMenuItem { view.makeContextMenu().items.first { $0.title == title }! }
        precondition(!item("复制").isEnabled)
        precondition(!item("粘贴").isEnabled, "ended sessions cannot receive paste")
        view.selectAll(nil)
        let selected = view.getSelection()
        precondition(item("复制").isEnabled)
        _ = view.makeContextMenu()
        precondition(view.getSelection() == selected, "opening menu must preserve selection")
        view.perform(item("复制").action, with: nil)
        precondition(clipboard.string(forType: .string)?.contains("MENU_LOG_0") == true)
        view.perform(item("复制全部文本").action, with: nil)
        precondition(clipboard.string(forType: .string)?.contains("MENU_LOG_99") == true)
        precondition(view.getSelection() == selected)
        view.perform(item("取消选择").action, with: nil)
        precondition(!item("复制").isEnabled)
        view.scroll(toPosition: 0)
        view.perform(item("回到最新输出").action, with: nil)
        precondition(view.scrollPosition == 1)
        print("macOS terminal menu: enablement, selection preservation, copy, copy all, deselect and latest output passed")
    }
}
