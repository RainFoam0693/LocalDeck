import SwiftUI
import AppKit

@MainActor final class FileMenuAction: NSObject {
    let handler: () -> Void
    init(_ handler: @escaping () -> Void) { self.handler = handler }
    @objc func invoke(_ sender: Any?) { handler() }
    static func item(_ title: String, _ handler: @escaping () -> Void) -> NSMenuItem {
        let target = FileMenuAction(handler)
        let item = NSMenuItem(title: title, action: #selector(invoke(_:)), keyEquivalent: "")
        item.target = target; item.representedObject = target
        return item
    }
}

@MainActor final class FilesTableView: NSTableView {
    var menuForEntry: ((Int) -> NSMenu)?
    override func menu(for event: NSEvent) -> NSMenu? {
        let row = row(at: convert(event.locationInWindow, from: nil))
        if row >= 0 { selectRowIndexes(IndexSet(integer: row), byExtendingSelection: false) }
        return menuForEntry?(row)
    }
}

/// Native selection is immediate; doubleAction does not delay the single click.
struct NativeTerminalFilesList: NSViewRepresentable {
    let entries: [TerminalFileEntry]
    let open: (TerminalFileEntry) -> Void
    let makeMenu: (TerminalFileEntry?) -> NSMenu
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeNSView(context: Context) -> NSScrollView {
        let scroll = NSScrollView(); scroll.hasVerticalScroller = true; scroll.drawsBackground = false
        let table = FilesTableView(); table.headerView = nil; table.backgroundColor = .clear
        table.rowHeight = 32; table.intercellSpacing = NSSize(width: 0, height: 2)
        table.columnAutoresizingStyle = .lastColumnOnlyAutoresizingStyle
        table.selectionHighlightStyle = .regular; table.allowsEmptySelection = true
        let column = NSTableColumn(identifier: NSUserInterfaceItemIdentifier("file")); column.minWidth = 150
        table.addTableColumn(column); table.delegate = context.coordinator; table.dataSource = context.coordinator
        table.target = context.coordinator; table.doubleAction = #selector(Coordinator.openSelected(_:))
        table.setAccessibilityLabel("文件列表")
        table.menuForEntry = { [weak coordinator = context.coordinator] row in
            guard let coordinator else { return NSMenu() }
            return coordinator.parent.makeMenu(coordinator.parent.entries.indices.contains(row) ? coordinator.parent.entries[row] : nil)
        }
        scroll.documentView = table; table.reloadData()
        return scroll
    }
    func updateNSView(_ scroll: NSScrollView, context: Context) {
        let old = context.coordinator.parent.entries
        context.coordinator.parent = self
        guard let table = scroll.documentView as? NSTableView, old != entries else { return }
        let selected = old.indices.contains(table.selectedRow) ? old[table.selectedRow].url : nil
        table.reloadData()
        if let selected, let index = entries.firstIndex(where: { $0.url == selected }) { table.selectRowIndexes(IndexSet(integer: index), byExtendingSelection: false) }
    }
    @MainActor final class Coordinator: NSObject, NSTableViewDataSource, NSTableViewDelegate {
        var parent: NativeTerminalFilesList
        init(_ parent: NativeTerminalFilesList) { self.parent = parent }
        func numberOfRows(in tableView: NSTableView) -> Int { parent.entries.count }
        @objc func openSelected(_ table: NSTableView) {
            guard parent.entries.indices.contains(table.clickedRow) else { return }
            parent.open(parent.entries[table.clickedRow])
        }
        func tableView(_ tableView: NSTableView, viewFor tableColumn: NSTableColumn?, row: Int) -> NSView? {
            guard parent.entries.indices.contains(row) else { return nil }
            let entry = parent.entries[row]
            let identifier = NSUserInterfaceItemIdentifier("fileCell")
            let cell: FileCell
            if let existing = tableView.makeView(withIdentifier: identifier, owner: self) as? FileCell { cell = existing }
            else { cell = FileCell(); cell.identifier = identifier }
            cell.name.stringValue = entry.name
            cell.size.stringValue = entry.directory ? "" : ByteCountFormatter.string(fromByteCount: Int64(entry.size), countStyle: .file)
            cell.icon.image = NSImage(systemSymbolName: entry.directory ? "folder.fill" : "doc", accessibilityDescription: entry.directory ? "文件夹" : "文件")
            cell.icon.contentTintColor = entry.directory ? .controlAccentColor : .secondaryLabelColor
            cell.toolTip = entry.url.path
            return cell
        }
    }
}

@MainActor final class FileCell: NSTableCellView {
    let name = NSTextField(labelWithString: "")
    let size = NSTextField(labelWithString: "")
    let icon = NSImageView()
    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        name.font = .systemFont(ofSize: 12); name.lineBreakMode = .byTruncatingMiddle
        size.font = .systemFont(ofSize: 10); size.textColor = .secondaryLabelColor
        name.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        let stack = NSStackView(views: [icon, name, size]); stack.spacing = 8; stack.alignment = .centerY
        stack.translatesAutoresizingMaskIntoConstraints = false; addSubview(stack)
        textField = name; imageView = icon
        NSLayoutConstraint.activate([
            icon.widthAnchor.constraint(equalToConstant: 18), icon.heightAnchor.constraint(equalToConstant: 18),
            stack.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 6), stack.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -6),
            stack.centerYAnchor.constraint(equalTo: centerYAnchor)
        ])
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
}
