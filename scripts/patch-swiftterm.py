"""Apply the pinned SwiftTerm scrollback fix before compiling (idempotent)."""
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
