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
view.close()
print('Terminal scroll: live following, history reading, bounded history and resume passed')
