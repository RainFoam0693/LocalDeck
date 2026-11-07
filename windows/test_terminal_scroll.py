"""Regression: asynchronous output must not pull history readers to the bottom."""
import sys
import threading
from pathlib import Path
from types import ModuleType
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# ConPTY is Windows-only; these tests run the real screen/snapshot/render path.
if sys.platform != 'win32':
    stub = ModuleType('winpty'); stub.PtyProcess = None; sys.modules['winpty'] = stub
from PySide6.QtWidgets import QApplication
from windows.terminal_session import TerminalSession, ReplyScreen
from windows.terminal import TerminalView
import pyte
app = QApplication([])
session = TerminalSession.__new__(TerminalSession)
session.lock = threading.RLock(); session.version = 0; session.running = True
session.screen = ReplyScreen(80, 12, history=80); stream = pyte.Stream(session.screen)
session.resize = lambda *args:None
view = TerminalView(session); view.resize(700, 220); view.show(); app.processEvents()
def feed(start, count):
    stream.feed(''.join(f'LOG_{i:04d}\r\n' for i in range(start, start+count)))
    session.version += 1; view.paint_screen(); app.processEvents()
feed(0, 50)
bar = view.verticalScrollBar(); assert bar.value() == bar.maximum()
bar.setValue(bar.maximum()-15)
anchor = view.row_origins[bar.value()]
feed(50, 5)
assert view.row_origins[bar.value()] is anchor, 'new output moved the reading position'
feed(55, 45)
assert view.row_origins[bar.value()] is anchor, 'history eviction moved the reading position'
bar.setValue(bar.maximum()); feed(100, 10)
assert bar.value() == bar.maximum(), 'returning to bottom did not restore following'
bar.setValue(bar.maximum()-1); anchor = view.row_origins[bar.value()]; feed(110, 1)
assert view.row_origins[bar.value()] is anchor, 'one line above bottom must also pause following'
# A wheel notch is one row; high-resolution pixel input accumulates.
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
bar.setValue(bar.maximum()-20)
def wheel(angle=0, pixels=0):
    event = QWheelEvent(QPointF(100,100), QPointF(view.mapToGlobal(QPoint(100,100))),
                        QPoint(0,pixels), QPoint(0,angle), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    view.wheelEvent(event)
initial = bar.value(); wheel(120); assert bar.value() == initial-1
initial = bar.value()
for _ in range(3): wheel(pixels=1)
assert bar.value() == initial, 'small deltas jumped a row each'
for _ in range(view.fontMetrics().lineSpacing()): wheel(pixels=1)
assert bar.value() == initial-1, 'pixel deltas were not accumulated'
wheel(-120); assert bar.value() == initial, 'direction reversal was delayed'
# Hold a selection at either edge: the timer must move and extend it while stationary.
viewport = view.viewport()
QTest.mousePress(viewport, Qt.LeftButton, Qt.NoModifier, QPoint(80,100))
QTest.mouseMove(viewport, QPoint(160,1))
initial = bar.value(); QTest.qWait(160)
assert bar.value() < initial, 'top-edge drag failed to scroll up'
assert view.textCursor().hasSelection(), 'edge drag lost the selection'
QTest.mouseMove(viewport, QPoint(160,viewport.height()-2))
initial = bar.value(); QTest.qWait(160)
assert bar.value() > initial, 'bottom-edge drag failed to scroll down'
selected = view.textCursor().selectedText(); rendered = view.toPlainText()
feed(120,3)
assert view.toPlainText() == rendered and view.textCursor().selectedText() == selected, 'output interrupted drag selection'
QTest.mouseRelease(viewport, Qt.LeftButton, Qt.NoModifier, QPoint(160,viewport.height()-2))
assert not view.selection_timer.isActive()
view.paint_screen()
assert view.version == session.version, 'output failed to catch up after drag'
view.close()
print('Terminal input: fine wheel, pixel deltas, edge drag, selection stability; scroll: live following, history reading, bounded history and resume passed')
