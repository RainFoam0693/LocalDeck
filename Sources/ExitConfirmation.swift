import SwiftUI
import AppKit

/// Keep the last window visible if the application quit confirmation is cancelled.
struct ExitAwareWindow: NSViewRepresentable {
    func makeNSView(context: Context) -> ExitAwareView { ExitAwareView() }
    func updateNSView(_ view: ExitAwareView, context: Context) { view.closeDelegate.attach(view.window) }
}

@MainActor final class ExitAwareView: NSView {
    let closeDelegate = ExitWindowDelegate()
    override func viewDidMoveToWindow() { super.viewDidMoveToWindow(); closeDelegate.attach(window) }
}

@MainActor final class ExitWindowDelegate: NSObject, NSWindowDelegate {
    weak var previous: (any NSWindowDelegate)?
    weak var window: NSWindow?
    func attach(_ window: NSWindow?) {
        if self.window === window, window?.delegate === self { return }
        if let old = self.window, old.delegate === self { old.delegate = previous }
        self.window = window
        guard let window else { previous = nil; return }
        previous = window.delegate; window.delegate = self
    }
    func windowShouldClose(_ sender: NSWindow) -> Bool {
        if previous?.windowShouldClose?(sender) == false { return false }
        if NSApp.windows.contains(where: { $0 !== sender && $0.isVisible && $0.canBecomeMain }) { return true }
        // Closing the last window hides LocalDeck; the status item keeps it reachable.
        NSApp.hide(nil)
        return false
    }
    override func responds(to selector: Selector!) -> Bool { super.responds(to: selector) || previous?.responds(to: selector) == true }
    override func forwardingTarget(for selector: Selector!) -> Any? { previous ?? super.forwardingTarget(for: selector) }
}
