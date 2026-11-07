import AppKit
import SwiftTerm

/// Native context actions operate on the terminal buffer, never on the shell command line.
final class DeckTerminalView: LocalProcessTerminalView {
    override func menu(for event: NSEvent) -> NSMenu? {
        makeContextMenu()
    }

    func makeContextMenu() -> NSMenu {
        let menu = NSMenu(title: "终端")
        menu.autoenablesItems = false
        func item(_ title: String, _ action: Selector, enabled: Bool = true) {
            let value = NSMenuItem(title: title, action: action, keyEquivalent: "")
            value.target = self; value.isEnabled = enabled; menu.addItem(value)
        }
        item("复制", #selector(copy(_:)), enabled: !(getSelection()?.isEmpty ?? true))
        item("粘贴", #selector(paste(_:)), enabled: process.running && !(NSPasteboard.general.string(forType: .string)?.isEmpty ?? true))
        menu.addItem(.separator())
        item("全选", #selector(selectAll(_:)))
        item("取消选择", #selector(clearTerminalSelection(_:)), enabled: selectionActive)
        item("复制全部文本", #selector(copyTerminalBuffer(_:)))
        menu.addItem(.separator())
        item("回到最新输出", #selector(showLatestOutput(_:)))
        return menu
    }

    override func paste(_ sender: Any) {
        guard process.running, let text = NSPasteboard.general.string(forType: .string), !text.isEmpty else { return }
        if text.contains("\n") || text.contains("\r") {
            let alert = NSAlert()
            alert.messageText = "粘贴多行命令？"
            alert.informativeText = "内容包含换行，可能立即执行命令。确认后粘贴到当前终端。"
            alert.addButton(withTitle: "取消")
            alert.addButton(withTitle: "粘贴")
            guard alert.runModal() == .alertSecondButtonReturn else { return }
        }
        // Keep SwiftTerm's bracketed-paste handling and use exactly the confirmed text.
        let bracketed = getTerminal().bracketedPasteMode
        send(txt: (bracketed ? "\u{1b}[200~" : "") + text + (bracketed ? "\u{1b}[201~" : ""))
    }

    override func validateUserInterfaceItem(_ item: NSValidatedUserInterfaceItem) -> Bool {
        switch item.action {
        case #selector(paste(_:)): return process.running && !(NSPasteboard.general.string(forType: .string)?.isEmpty ?? true)
        case #selector(copy(_:)): return !(getSelection()?.isEmpty ?? true)
        default: return super.validateUserInterfaceItem(item)
        }
    }

    @objc private func clearTerminalSelection(_ sender: Any?) { selectNone() }
    @objc private func copyTerminalBuffer(_ sender: Any?) {
        let text = String(decoding: getTerminal().getBufferAsData(), as: UTF8.self)
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }
    @objc private func showLatestOutput(_ sender: Any?) { scroll(toPosition: 1) }
}
