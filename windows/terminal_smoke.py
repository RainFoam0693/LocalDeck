"""End-to-end regression: tabs keep running when the service page is selected."""
import json
import time
from pathlib import Path
from unittest.mock import patch
import psutil
from windows.terminal import TerminalSession


def run(app):
    def pump(check, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.update()
            if check(): return
            time.sleep(0.03)
        raise AssertionError('Terminal smoke test timed out')

    workspace = app.terminals
    sessions = []
    try:
        for label in ('ONE', 'TWO'):
            session = TerminalSession(str(Path.home()))
            sessions.append(session)
            workspace.attach(session)
            session.write('set "LOCALDECK_TAB=' + label + '"\r')
            session.write('echo %LOCALDECK_TAB%_READY\r')
            pump(lambda: label + '_READY' in session.text())
        assert 'ONE_READY' not in sessions[1].text()
        assert 'TWO_READY' not in sessions[0].text()
        # Run after a delay while the terminal workspace and the first terminal are hidden.
        app.tabs.select(2)
        app.update()
        for session in sessions:
            session.write('ping -n 3 127.0.0.1 >nul & echo %LOCALDECK_TAB%_BACKGROUND\r')
        app.tabs.select(0)
        pump(lambda: 'ONE_BACKGROUND' in sessions[0].text() and 'TWO_BACKGROUND' in sessions[1].text())
        app.tabs.select(1)
        sessions[0].resize(25, 90)
        assert sessions[0].process.getwinsize() == (25, 90)
        sessions[0].write('echo %LOCALDECK_TAB%_RESIZED\r')
        pump(lambda: 'ONE_RESIZED' in sessions[0].text())
        sessions[1].write('ping -t 127.0.0.1\r')
        end = time.monotonic() + 0.5
        while time.monotonic() < end: app.update(); time.sleep(0.03)
        sessions[1].write('\x03')
        sessions[1].write('echo %LOCALDECK_TAB%_INTERRUPTED\r')
        pump(lambda: 'TWO_INTERRUPTED' in sessions[1].text())
        app.tabs.select(2)
        first_key = next(key for key, pair in workspace.sessions.items() if pair[0] is sessions[0])
        workspace.tabs.select(first_key)
        with patch('windows.terminal.messagebox.askyesno', return_value=True): workspace.close_selected()
        pump(lambda: not psutil.pid_exists(sessions[0].process.pid))
        assert sessions[1].process.isalive(), 'Closing one tab stopped another tab'
        # Exercise immediate exit while another tab is closing and a shell is starting.
        third = TerminalSession(str(Path.home()))
        sessions.append(third)
        workspace.attach(third)
        with patch('windows.terminal.messagebox.askyesno', return_value=True): workspace.close_selected()
        workspace.add()
        app.tabs.select(0)
        app.close()
        end = time.monotonic() + 20
        while time.monotonic() < end:
            try:
                app.update()
                if not app.winfo_exists(): break
            except Exception: break
            time.sleep(0.03)
        assert not psutil.pid_exists(sessions[1].process.pid), 'Terminal shell survived application exit'
        assert not psutil.pid_exists(sessions[2].process.pid), 'Closing tab survived immediate application exit'
        result = {'ok': True, 'tabs': 2, 'pageSwitch': True, 'resize': True, 'ctrlC': True, 'closeIsolation': True, 'exitCleanup': True}
        return result
    finally:
        for session in sessions:
            if not session.closed: session.close()
