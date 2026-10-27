"""Regression tests exercise real ConPTY shells through the Qt workspace."""
import time
from pathlib import Path
import psutil
from PySide6.QtWidgets import QApplication
from windows.terminal_session import TerminalSession


def run(app):
    def pump(check, timeout=20):
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            QApplication.processEvents()
            if check(): return
            time.sleep(.03)
        raise AssertionError('Terminal smoke test timed out')

    workspace = app.terminals; sessions = []
    try:
        for name in ('ONE', 'TWO'):
            session = TerminalSession(str(Path.home())); sessions.append(session); workspace.attach(session)
            session.write('set "LOCALDECK_TAB='+name+'"\r'); session.write('echo %LOCALDECK_TAB%_READY\r')
            pump(lambda:name+'_READY' in session.text())
        assert 'ONE_READY' not in sessions[1].text() and 'TWO_READY' not in sessions[0].text()
        app.select_page(2); QApplication.processEvents()
        for session in sessions: session.write('ping -n 3 127.0.0.1 >nul & echo %LOCALDECK_TAB%_BACKGROUND\r')
        app.select_page(0); pump(lambda:'ONE_BACKGROUND' in sessions[0].text() and 'TWO_BACKGROUND' in sessions[1].text())
        app.select_page(1); sessions[0].resize(25, 90); assert sessions[0].process.getwinsize() == (25, 90)
        sessions[0].write('echo %LOCALDECK_TAB%_RESIZED\r'); pump(lambda:'ONE_RESIZED' in sessions[0].text())
        sessions[1].write('ping -t 127.0.0.1\r'); end = time.monotonic()+.5
        while time.monotonic() < end: QApplication.processEvents(); time.sleep(.03)
        sessions[1].write('\x03'); sessions[1].write('echo %LOCALDECK_TAB%_INTERRUPTED\r'); pump(lambda:'TWO_INTERRUPTED' in sessions[1].text())
        app.select_page(2)
        first = next(view for view, pair in workspace.sessions.items() if pair[0] is sessions[0])
        workspace.close_index(workspace.tabs.indexOf(first), confirm=False)
        pump(lambda:not psutil.pid_exists(sessions[0].process.pid)); assert sessions[1].process.isalive()
        third = TerminalSession(str(Path.home())); sessions.append(third); view = workspace.attach(third)
        workspace.close_index(workspace.tabs.indexOf(view), confirm=False); workspace.add(); app.select_page(0); app.close()
        pump(lambda:app.closed, timeout=35)
        assert not psutil.pid_exists(sessions[1].process.pid), 'Shell survived app exit'
        assert not psutil.pid_exists(sessions[2].process.pid), 'Closing tab survived app exit'
        assert not app.errors, app.errors
        return {'ok':True, 'tabs':2, 'pageSwitch':True, 'resize':True, 'ctrlC':True, 'closeIsolation':True, 'exitCleanup':True, 'ui':'Qt'}
    finally:
        for session in sessions:
            if not session.closed: session.close()
