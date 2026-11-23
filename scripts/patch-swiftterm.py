"""Apply pinned SwiftTerm scrollback and input fixes before compiling (idempotent)."""
from pathlib import Path
import stat
source = Path(__file__).resolve().parents[1]/'.build/checkouts/SwiftTerm/Sources/SwiftTerm/Terminal.swift'
text = source.read_text()
old = '''    public func scroll (isWrapped: Bool = false)
    {
        let buffer = self.buffer
'''
new = old + '''        // LocalDeck: preserve a history viewport until the user returns to live output.
        userScrolling = buffer.yDisp < buffer.yBase
'''
if new not in text:
    if text.count(old) != 1:
        raise SystemExit('SwiftTerm scroll patch no longer matches; review dependency before building.')
    source.chmod(source.stat().st_mode | stat.S_IWUSR)
    source.write_text(text.replace(old, new, 1))

# Keep terminal-specific input fixes reproducible with the pinned checkout.
source = source.parent/'Mac/MacTerminalView.swift'
text = source.read_text()
def replace_once(old, new):
    global text
    if new in text: return
    # The pixel renderer supersedes the earlier row-only wheel patch.
    if 'deckSmoothPixelScroll' in text and ('public override func scrollWheel(with event: NSEvent)' in old or 'public override func mouseDown(with event: NSEvent)' in old): return
    if text.count(old) != 1:
        raise SystemExit('SwiftTerm input patch no longer matches; review dependency before building.')
    text = text.replace(old, new, 1)

def replace_legacy_once(variants, new):
    global text
    if new in text: return
    matches = [old for old in variants if old in text]
    if len(matches) != 1:
        raise SystemExit('SwiftTerm selection patch no longer matches; review dependency before building.')
    text = text.replace(matches[0], new, 1)

replace_once('    private var autoScrollDelta = 0\n', '''    private var autoScrollDelta = 0
    private var deckSelectionTimer: Timer?
    private var deckSelectionPoint = CGPoint.zero
    private var deckWheelRemainder: CGFloat = 0

    private func deckStopSelectionScroll() {
        deckSelectionTimer?.invalidate()
        deckSelectionTimer = nil
        autoScrollDelta = 0
    }

    private func deckUpdateSelectionScroll(at point: CGPoint) {
        deckSelectionPoint = point
        let margin: CGFloat = min(24, bounds.height / 4)
        if point.y >= bounds.maxY - margin {
            autoScrollDelta = -min(4, max(1, Int((point.y - bounds.maxY + margin) / max(1, cellDimension.height)) + 1))
        } else if point.y <= bounds.minY + margin {
            autoScrollDelta = min(4, max(1, Int((bounds.minY + margin - point.y) / max(1, cellDimension.height)) + 1))
        } else {
            deckStopSelectionScroll()
            return
        }
        guard deckSelectionTimer == nil else { return }
        let timer = Timer(timeInterval: 0.05, repeats: true) { [weak self] timer in
            guard let self else { timer.invalidate(); return }
            self.scrollingTimerElapsed(source: timer)
        }
        deckSelectionTimer = timer
        RunLoop.main.add(timer, forMode: .common)
    }
''')
replace_once('''        if autoScrollDelta == 0 {
            return
        }
        if autoScrollDelta < 0 {
            scrollUp(lines: autoScrollDelta * -1)
        } else {
            scrollUp(lines: autoScrollDelta)
        }
''', '''        guard selection.active, window != nil, NSEvent.pressedMouseButtons & 1 != 0 else {
            deckStopSelectionScroll()
            return
        }
        if autoScrollDelta < 0 { scrollUp(lines: -autoScrollDelta) }
        else if autoScrollDelta > 0 { scrollDown(lines: autoScrollDelta) }
        let point = CGPoint(x: deckSelectionPoint.x, y: min(bounds.maxY - 1, max(bounds.minY + 1, deckSelectionPoint.y)))
        let hit = calculateMouseHit(at: point).grid
        selection.dragExtend(bufferPosition: hit)
        setNeedsDisplay(bounds)
''')
replace_once('''    public override func mouseDown(with event: NSEvent) {
''','''    public override func mouseDown(with event: NSEvent) {
        deckStopSelectionScroll()
''')
replace_once('''        case 2:
            let displayBuffer = terminal.displayBuffer
''','''            if !selection.active { selection.setSoftStart(bufferPosition: hit); selection.startSelection() }
        case 2:
            let displayBuffer = terminal.displayBuffer
''')
replace_once('''    public override func mouseUp(with event: NSEvent) {
''','''    public override func mouseUp(with event: NSEvent) {
        deckStopSelectionScroll()
''')
replace_once('''            selection.setSoftStart(bufferPosition: Position(col: hit.col, row: hit.row))
            selection.startSelection()
''','''            selection.startSelection()
            selection.dragExtend(bufferPosition: hit)
''')
replace_once('''        autoScrollDelta = 0
        let screenRow = hit.row - displayBuffer.yDisp
        if selection.active {
            if screenRow <= 0 {
                autoScrollDelta = calcScrollingVelocity(delta: screenRow * -1) * -1
            } else if screenRow >= displayBuffer.rows {
                autoScrollDelta = calcScrollingVelocity(delta: screenRow - displayBuffer.rows)
            }
        }
''','''        deckUpdateSelectionScroll(at: convert(event.locationInWindow, from: nil))
''')
replace_once('''    public override func scrollWheel(with event: NSEvent) {
        if event.deltaY == 0 {
            return
        }
        let velocity = calcScrollingVelocity(delta: Int (abs (event.deltaY)))
        if event.deltaY > 0 {
            scrollUp (lines: velocity)
        } else {
            scrollDown(lines: velocity)
        }
    }
''','''    public override func scrollWheel(with event: NSEvent) {
        // Precise input is measured in points; a wheel detent moves one row.
        let delta = event.hasPreciseScrollingDeltas
            ? event.scrollingDeltaY / max(1, cellDimension.height)
            : event.scrollingDeltaY / 3
        guard delta != 0 else { return }
        if event.phase == .began || (deckWheelRemainder * delta < 0) { deckWheelRemainder = 0 }
        deckWheelRemainder += delta
        let rows = Int(deckWheelRemainder)
        deckWheelRemainder -= CGFloat(rows)
        if rows > 0 { scrollUp(lines: rows) }
        else if rows < 0 { scrollDown(lines: -rows) }
        if NSEvent.pressedMouseButtons & 1 != 0, selection.active {
            let point = convert(event.locationInWindow, from: nil)
            selection.dragExtend(bufferPosition: calculateMouseHit(at: point).grid)
            setNeedsDisplay(bounds)
        }
    }
''')
if source.read_text() != text:
    source.chmod(source.stat().st_mode | stat.S_IWUSR)
    source.write_text(text)

# Keep selections while new output arrives, including after the drag has ended.
replace_legacy_once([
    '''    open func linefeed(source: Terminal) {
        selection.selectNone()
    }
''',
    '''    open func linefeed(source: Terminal) {
        if !didSelectionDrag { selection.selectNone() }
    }
'''
], '''    open func linefeed(source: Terminal) {
        // LocalDeck: streamed output must not clear a user's existing selection.
    }
''')
if source.read_text() != text:
    source.chmod(source.stat().st_mode | stat.S_IWUSR)
    source.write_text(text)

# New terminal output must not cancel a user's selection.
source = source.parent.parent/'Apple/AppleTerminalView.swift'
text = source.read_text()
replace_legacy_once([
    '''        search.invalidate()
        selection.active = false
        startDisplayUpdates()
''',
    '''        search.invalidate()
        #if os(macOS)
        if !didSelectionDrag { selection.active = false }
        #else
        selection.active = false
        #endif
        startDisplayUpdates()
'''
], '''        search.invalidate()
        #if os(macOS)
        // LocalDeck: keep the existing text selection during streamed output.
        #else
        selection.active = false
        #endif
        startDisplayUpdates()
''')
if source.read_text() != text:
    source.chmod(source.stat().st_mode | stat.S_IWUSR)
    source.write_text(text)

# Pixel scrolling keeps fractional rows in the renderer and eases only the viewport.
source = source.parent.parent/'Mac/MacTerminalView.swift'
text = source.read_text()
replace_once('import CoreGraphics\n', '''import CoreGraphics
import QuartzCore

// CADisplayLink owns this proxy, which never retains its terminal view.
@available(macOS 14.0, *)
private final class DeckTerminalFrameTarget: NSObject {
    weak var owner: TerminalView?
    init(_ owner: TerminalView) { self.owner = owner }
    @objc func frame(_ link: CADisplayLink) { owner?.deckSmoothFrame() }
}
''')
replace_once('    private var autoScrollDelta = 0\n', '''    // deckSmoothPixelScroll: position in fractional rows, independent of terminal output.
    public private(set) var deckScrollPixelOffset: CGFloat = 0
    private var deckSmoothTarget: CGFloat?
    private var deckSmoothPosition: CGFloat = 0
    private var deckSmoothLastTime: CFTimeInterval = 0
    private var deckSmoothTimeConstant: Double = 0.055
    private var deckFrameDriver: AnyObject?

    private func deckStopFrameDriver() {
        if #available(macOS 14.0, *), let link = deckFrameDriver as? CADisplayLink { link.invalidate() }
        (deckFrameDriver as? Timer)?.invalidate()
        deckFrameDriver = nil
        deckSmoothLastTime = 0
    }

    private func deckStartFrameDriver() {
        guard deckFrameDriver == nil else { return }
        deckSmoothLastTime = CACurrentMediaTime()
        if #available(macOS 14.0, *), window != nil {
            let target = DeckTerminalFrameTarget(self)
            let link = displayLink(target: target, selector: #selector(DeckTerminalFrameTarget.frame(_:)))
            let fps = Float(window?.screen?.maximumFramesPerSecond ?? 60)
            link.preferredFrameRateRange = CAFrameRateRange(minimum: min(30, fps), maximum: fps, preferred: fps)
            link.add(to: .main, forMode: .common)
            deckFrameDriver = link
        } else {
            let timer = Timer(timeInterval: 1.0 / 120, repeats: true) { [weak self] timer in
                guard let self else { timer.invalidate(); return }
                self.deckSmoothFrame()
            }
            RunLoop.main.add(timer, forMode: .common)
            deckFrameDriver = timer
        }
    }

    fileprivate func deckSmoothFrame() {
        guard let target = deckSmoothTarget else { deckStopFrameDriver(); return }
        let now = CACurrentMediaTime()
        let dt = min(0.05, max(0.001, now - deckSmoothLastTime))
        deckSmoothLastTime = now
        let difference = target - deckSmoothPosition
        let reduceMotion = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
        if abs(difference) * max(1, cellDimension.height) < 0.08 || reduceMotion || (window != nil && isHiddenOrHasHiddenAncestor) {
            deckSmoothPosition = target
            deckApplyPixelPosition()
            deckSmoothTarget = nil
            deckStopFrameDriver()
        } else {
            deckSmoothPosition += difference * CGFloat(1 - exp(-dt / deckSmoothTimeConstant))
            deckApplyPixelPosition()
        }
    }

    private func deckApplyPixelPosition() {
        let buffer = terminal.displayBuffer
        let maximum = CGFloat(max(0, buffer.lines.count - buffer.rows))
        deckSmoothPosition = min(maximum, max(0, deckSmoothPosition))
        let row = Int(floor(deckSmoothPosition))
        deckScrollPixelOffset = (deckSmoothPosition - CGFloat(row)) * cellDimension.height
        scrollTo(row: row)
        updateCursorPosition()
        setNeedsDisplay(bounds)
    }

    func deckSnapPixelScroll() {
        deckStopFrameDriver()
        deckSmoothTarget = nil
        deckScrollPixelOffset = 0
        updateCursorPosition()
        setNeedsDisplay(bounds)
    }

    private var autoScrollDelta = 0
''')
replace_once('''        drawTerminalContents (dirtyRect: dirtyRect, context: currentContext, bufferOffset: terminal.displayBuffer.yDisp)
''','''        // Fill before drawing an extra partial row, so neither edge exposes stale pixels.
        nativeBackgroundColor.setFill()
        bounds.fill()
        drawTerminalContents (dirtyRect: bounds, context: currentContext, bufferOffset: terminal.displayBuffer.yDisp)
''')
replace_once('''        let row = Int ((frame.height-point.y) / cellDimension.height)
''','''        let row = Int (floor((frame.height - point.y + deckScrollPixelOffset) / cellDimension.height))
''')
replace_once('''    public override func mouseDown(with event: NSEvent) {
        deckStopSelectionScroll()
''','''    public override func mouseDown(with event: NSEvent) {
        // Freeze at the visible fractional position before establishing the drag anchor.
        deckStopFrameDriver()
        deckSmoothTarget = nil
        deckStopSelectionScroll()
''')
replace_once('''        progressReportTimer?.invalidate()
    }''','''        progressReportTimer?.invalidate()
        deckStopFrameDriver()
        deckSelectionTimer?.invalidate()
    }''')
# Replace by bounded function span to retain all the earlier drag fixes.
start = text.index('    public override func scrollWheel(with event: NSEvent) {')
end = text.index('    private func calcScrollingVelocity', start)
if 'deckSmoothPixelScroll wheel' not in text[start:end]:
    text = text[:start] + '''    public override func scrollWheel(with event: NSEvent) {
        // deckSmoothPixelScroll wheel: keep every sub-row delta, including native momentum.
        let height = max(1, cellDimension.height)
        let delta = event.hasPreciseScrollingDeltas ? event.scrollingDeltaY / height : event.scrollingDeltaY / 3
        guard delta != 0, canScroll else { return }
        if deckSmoothTarget == nil {
            deckSmoothPosition = CGFloat(terminal.displayBuffer.yDisp) + deckScrollPixelOffset / height
        }
        let maximum = CGFloat(max(0, terminal.displayBuffer.lines.count - terminal.displayBuffer.rows))
        deckSmoothTarget = min(maximum, max(0, (deckSmoothTarget ?? deckSmoothPosition) - delta))
        deckSmoothTimeConstant = event.hasPreciseScrollingDeltas ? 0.018 : 0.055
        if NSWorkspace.shared.accessibilityDisplayShouldReduceMotion {
            deckSmoothPosition = deckSmoothTarget!
            deckApplyPixelPosition()
            deckSmoothTarget = nil
            deckStopFrameDriver()
        } else {
            deckStartFrameDriver()
        }
    }

''' + text[end:]
if source.read_text() != text:
    source.chmod(source.stat().st_mode | stat.S_IWUSR)
    source.write_text(text)

source = source.parent.parent/'Apple/AppleTerminalView.swift'
text = source.read_text()
replace_once('''        let yOffset = ceil(lineDescent+lineLeading)
        let displayBuffer = terminal.displayBuffer
''','''        let yOffset = ceil(lineDescent+lineLeading)
        let displayBuffer = terminal.displayBuffer
        #if os(macOS)
        let pixelOffset = deckScrollPixelOffset
        #else
        let pixelOffset: CGFloat = 0
        #endif
''')
replace_once('''            cellDimension.height * CGFloat (forRow-bufferOffset+1)
''','''            cellDimension.height * CGFloat (forRow-bufferOffset+1) - pixelOffset
''')
replace_once('''        let firstRow = displayBuffer.yDisp+Int ((boundsMaxY-dirtyRect.maxY)/cellHeight)
        let lastRow = displayBuffer.yDisp+Int((boundsMaxY-dirtyRect.minY)/cellHeight)
''','''        let firstRow = displayBuffer.yDisp + Int(floor((boundsMaxY - dirtyRect.maxY + pixelOffset) / cellHeight))
        let lastRow = displayBuffer.yDisp + Int(ceil((boundsMaxY - dirtyRect.minY + pixelOffset) / cellHeight))
''')
replace_once('''        if dirtyRect.intersects(box) {
''','''        if deckScrollPixelOffset == 0 && dirtyRect.intersects(box) {
''')
replace_once('''        let lineOrigin = CGPoint(x: 0, y: frame.height - offset)
        #endif
''','''        let lineOrigin = CGPoint(x: 0, y: frame.height - offset + deckScrollPixelOffset)
        #endif
''')
# Explicit row navigation (scrollbar, keys, selection autoscroll) cancels fractional easing.
replace_once('''    public func scroll (toPosition: Double)
    {
        userScrolling = true
''','''    public func scroll (toPosition: Double)
    {
        #if os(macOS)
        deckSnapPixelScroll()
        #endif
        userScrolling = true
''')
replace_once('''    public func scrollUp (lines: Int)
    {
''','''    public func scrollUp (lines: Int)
    {
        #if os(macOS)
        deckSnapPixelScroll()
        #endif
''')
replace_once('''    public func scrollDown (lines: Int)
    {
''','''    public func scrollDown (lines: Int)
    {
        #if os(macOS)
        deckSnapPixelScroll()
        #endif
''')
if source.read_text() != text:
    source.chmod(source.stat().st_mode | stat.S_IWUSR)
    source.write_text(text)
