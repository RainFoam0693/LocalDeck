import AppKit
import SwiftTerm

// Link against the patched SwiftTerm objects produced by scripts/build.sh.
@main struct TerminalInputTests {
    static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.prohibited)
        let view = TerminalView(frame: NSRect(x: 0, y: 0, width: 800, height: 320))
        view.feed(text: (0..<250).map { "LOG_\($0)\r\n" }.joined())
        let terminal = view.getTerminal()
        func row() -> Int { terminal.buffer.yDisp }
        func wheel(_ value: Int32, precise: Bool = false) {
            let event = CGEvent(scrollWheelEvent2Source: nil, units: precise ? .pixel : .line, wheelCount: 1, wheel1: value, wheel2: 0, wheel3: 0)!
            view.scrollWheel(with: NSEvent(cgEvent: event)!)
        }
        let height = view.getOptimalFrameSize().height / CGFloat(terminal.rows)
        func position() -> CGFloat { CGFloat(row()) + view.deckScrollPixelOffset / height }
        func pump(_ duration: TimeInterval) { RunLoop.main.run(until: Date().addingTimeInterval(duration)) }
        let initial = position()
        wheel(3)
        pump(0.025)
        let intermediate = position()
        precondition(intermediate < initial && intermediate > initial - 1, "wheel animation must show an intermediate pixel position")
        precondition(view.deckScrollPixelOffset > 0, "text must move between whole rows")
        var frames = Set<Int>()
        for _ in 0..<18 { pump(0.009); frames.insert(Int(position() * height * 100)) }
        precondition(frames.count > 5, "animation must contain multiple distinct frames")
        pump(0.25)
        precondition(abs(initial - position() - 1) < 0.001, "wheel must settle exactly one row away")
        let before = position()
        for _ in 0..<3 { wheel(1, precise: true) }
        pump(0.2)
        precondition(abs((before - position()) * height - 3) < 0.1, "tiny pixel deltas must move exactly three points")
        wheel(-3)
        pump(0.35)
        let down = position()
        wheel(-3)
        pump(0.025)
        precondition(position() > down && position() < down + 1, "direction reversal must animate immediately")
        pump(0.35)
        func mouse(_ type: NSEvent.EventType, x: CGFloat, y: CGFloat) {
            let event = NSEvent.mouseEvent(with: type, location: NSPoint(x: x, y: y), modifierFlags: [], timestamp: 0, windowNumber: 0, context: nil, eventNumber: 0, clickCount: 1, pressure: 1)!
            switch type {
            case .leftMouseDown: view.mouseDown(with: event)
            case .leftMouseDragged: view.mouseDragged(with: event)
            default: view.mouseUp(with: event)
            }
        }
        mouse(.leftMouseDown, x: 15, y: 160)
        mouse(.leftMouseDragged, x: 220, y: 120)
        precondition(!(view.getSelection()?.isEmpty ?? true), "dragging must select from the click anchor")
        let selected = view.getSelection() ?? ""
        wheel(3)
        pump(0.35)
        precondition(view.getSelection() == selected, "scrolling must retain selected text")
        view.feed(text: "MORE_OUTPUT\r\n")
        precondition(view.getSelection() == selected, "new output must not cancel an active drag")
        mouse(.leftMouseDragged, x: 220, y: 2)
        func state(_ name: String) -> Any { Mirror(reflecting: view).children.first { $0.label == name }!.value }
        precondition(!Mirror(reflecting: state("deckSelectionTimer")).children.isEmpty, "edge drag must start an autoscroll timer")
        precondition((state("autoScrollDelta") as! Int) > 0, "bottom edge must scroll down")
        mouse(.leftMouseDragged, x: 220, y: 319)
        precondition((state("autoScrollDelta") as! Int) < 0, "top edge must scroll up")
        mouse(.leftMouseUp, x: 220, y: 319)
        precondition(Mirror(reflecting: state("deckSelectionTimer")).children.isEmpty, "release must stop the timer")
        print("macOS terminal input: fractional pixel frames, exact settling, precise deltas, reversal and drag selection passed")
    }
}
