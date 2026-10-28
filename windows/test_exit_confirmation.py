"""Idle shells close directly; tasks require cancel/confirm without losing sessions."""
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from windows.terminal_activity import PromptActivity, has_child_jobs
from windows.app import App
from windows.fluent import setup_theme

activity = PromptActivity(); activity.input('not submitted'); assert not activity.executing
activity.input('\r'); assert activity.executing
activity.output('command output\r\n'); assert activity.executing
for split in range(len(activity.marker)+1):
    activity.input('\r'); activity.output(activity.marker[:split]); activity.output(activity.marker[split:])
    assert not activity.executing
args, env = activity.shell_options('cmd', {'COMSPEC':'cmd.exe','PROMPT':'custom$G'})
assert args == ['cmd.exe','/d'] and env['PROMPT'].endswith('custom$G') and '$E]133;A;' in env['PROMPT']
args, env = activity.shell_options('powershell', {})
assert '-NoExit' in args and '$function:prompt' in args[-1] and activity.tag in args[-1]
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
try: assert has_child_jobs(os.getpid())
finally: child.terminate(); child.wait(timeout=10)
with patch('windows.terminal_activity.psutil.Process', return_value=SimpleNamespace(children=lambda recursive:[SimpleNamespace(status=lambda:'running', name=lambda:'conhost.exe')])):
    assert not has_child_jobs(1)

qt = QApplication([]); setup_theme(qt)
class Session:
    directory = 'test'; error = ''; running = True; closed = False
    def __init__(self, busy=False): self.busy = busy
    def has_active_jobs(self): return self.running and self.busy
    def close(self): self.closed = True; self.running = False
    def resize(self, *args): pass
    def write(self, text): pass
    def snapshot(self): return (0, [], (0,0,True), self.running, 80)

def pump_closed(app):
    for _ in range(100):
        qt.processEvents(); QTest.qWait(20)
        if app.closed: break
    assert app.closed, 'App did not finish closing'

app = App(preview=True); session = Session(True); app.terminals.attach(session); app.show(); qt.processEvents()
session.identity = ('Yunzai', 1234); app.terminals.paint()
index = app.terminals.tabs.currentIndex()
assert app.terminals.tabs.tabText(index) == 'Yunzai · 1'
assert 'PID 1234' in app.terminals.tabs.tabToolTip(index)
session.identity = None; app.terminals.paint()
assert app.terminals.tabs.tabText(index) == 'CMD 1'
seen = []
def cancel():
    dialog = qt.activeModalWidget(); assert isinstance(dialog, QMessageBox)
    assert dialog.defaultButton().text() == '取消'
    seen.append(True); dialog.reject()
QTimer.singleShot(0, cancel); app.close()
assert seen and app.isVisible() and not app.closing and not app.terminals.closing
assert app.centralWidget().isEnabled() and app.terminals.timer.isActive() and not session.closed
assert len(app.terminals.sessions) == 1
# The exact same open terminal, now idle, must close without showing a dialog.
session.busy = False
app.confirm_terminal_exit = lambda active: (_ for _ in ()).throw(AssertionError('Idle shell prompted'))
app.close(); pump_closed(app); assert session.closed

app = App(preview=True); session = Session(True); app.terminals.attach(session); app.show(); qt.processEvents()
def confirm():
    dialog = qt.activeModalWidget(); assert isinstance(dialog, QMessageBox)
    next(button for button in dialog.buttons() if button.text() == '结束任务并退出').click()
QTimer.singleShot(0, confirm); app.close(); pump_closed(app); assert session.closed
app = App(preview=True); app.close(); pump_closed(app)
print('Exit confirmation: prompt boundaries, child tasks, cancel preserves work, idle/no tabs and confirmed cleanup passed')
