"""Render real Qt widgets at several scales and check navigation and selection."""
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from windows.app import App
from windows.fluent import setup_theme

qt = QApplication([]); setup_theme(qt); app = App(preview=True); app.appearance.set_mode('dark'); app.show(); qt.processEvents()
assert app.live_list.count() == 5
app.search.setText('8000'); assert app.live_list.count() == 1 and app.detail_name.text() == 'python.exe'
app.search.setText('does-not-exist'); assert app.live_list.count() == 0 and not app.stop_button.isEnabled()
app.search.clear(); app.toggle_sort(); assert app.selected_listener()['name'] == 'node.exe'
output = Path(os.environ.get('LOCALDECK_UI_OUTPUT', 'dist/windows-preview')); output.mkdir(parents=True, exist_ok=True)
for width, height in [(1320, 860), (1050, 700)]:
    app.resize(width, height); qt.processEvents()
    for index, page in enumerate(['services', 'tasks', 'terminals', 'ssh']):
        app.select_page(index); qt.processEvents()
        assert app.tabs.currentIndex() == index
        assert app.centralWidget().width() >= 1000
        app.grab().save(str(output/f'{page}-{width}.png'))
app.select_page(0); app.search.setText('8000'); qt.processEvents(); app.grab().save(str(output/'services-detail.png'))
app.search.clear(); app.resize(1320, 860)
for mode in ['light', 'dark', 'system']:
    app.appearance.set_mode(mode); QTest.qWait(220); qt.processEvents()
    assert sum(button.isChecked() for button in app.appearance_capsule.buttons) == 1
    assert app.appearance_capsule.buttons[['light','dark','system'].index(mode)].isChecked()
    for index, page in enumerate(['services','tasks','terminals','ssh']):
        app.select_page(index); qt.processEvents(); app.grab().save(str(output/f'{page}-{mode}.png'))
# A system change must update only the follow-system mode, without changing OS settings.
app.appearance.system_dark = lambda:False; app.appearance.set_mode('system'); assert not app.appearance.dark
app.appearance.system_dark = lambda:True; app.appearance.refresh(); assert app.appearance.dark
app.appearance.set_mode('light'); app.appearance.refresh(); assert not app.appearance.dark
from windows.fluent import AppearanceManager
from tempfile import TemporaryDirectory
with TemporaryDirectory() as directory:
    settings_path = str(Path(directory)/'appearance.ini')
    first = AppearanceManager(qt, settings_path=settings_path); first.set_mode('dark')
    second = AppearanceManager(qt, settings_path=settings_path); assert second.mode == 'dark'
    first.timer.stop(); second.timer.stop()
app.appearance.set_mode('dark')
# Render a VT screen in both themes without requiring Windows ConPTY on the preview host.
import pyte
class PreviewSession:
    directory = r'C:\Projects\LocalDeck'
    running = True
    error = ''
    def __init__(self):
        self.screen = pyte.HistoryScreen(80, 16, history=100)
        pyte.Stream(self.screen).feed('Windows PowerShell\r\nPS C:\\Projects\\LocalDeck> npm run dev\r\n\x1b[32mServer ready\x1b[0m on http://localhost:3000\r\n')
    def snapshot(self): return 1, [dict(self.screen.buffer[y]) for y in range(self.screen.lines)], (3,0,False), True, 80
    def resize(self, rows, columns): pass
    def write(self, text): pass
session = PreviewSession(); terminal = app.terminals.attach(session, 'powershell'); app.select_page(2)
for mode in ['light', 'dark']:
    app.appearance.set_mode(mode); QTest.qWait(220); qt.processEvents(); app.terminals.paint()
    assert 'Server ready' in terminal.toPlainText()
    assert app.terminals.sessions[terminal][0] is session
    app.grab().save(str(output/f'terminal-running-{mode}.png'))
app.terminals.sessions.clear()
app.closed = True; app.executor.shutdown(); app.close()
print('Qt UI: search, selection, CPU sort, empty states, 4 pages 2 sizes, 3 themes, system changes and persistence passed')
