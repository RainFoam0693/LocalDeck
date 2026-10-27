"""Exercise the asynchronous file model and shell quoting without ConPTY."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from windows.files import TerminalFiles, cd_command
app = QApplication([])
with TemporaryDirectory() as root:
    base = Path(root); (base / "目录 ' & space").mkdir(); (base / 'sample.txt').write_text('hello')
    (base / '.hidden').write_text('hidden')
    if sys.platform == 'win32':
        import ctypes
        assert ctypes.windll.kernel32.SetFileAttributesW(str(base / '.hidden'), 0x2)
    pane = TerminalFiles(); pane.navigate(root); pane.show()
    for _ in range(50):
        app.processEvents(); QTest.qWait(20)
        if pane.model.rowCount(pane.tree.rootIndex()) == 2: break
    assert pane.model.rowCount(pane.tree.rootIndex()) == 2
    pane.hidden.setChecked(True)
    for _ in range(50):
        app.processEvents(); QTest.qWait(20)
        if pane.model.rowCount(pane.tree.rootIndex()) == 3: break
    assert pane.model.rowCount(pane.tree.rootIndex()) == 3
    pane.navigate(str(base / "目录 ' & space")); pane.back(); assert pane.directory == root
    pane.close()
assert cd_command("C:\\a'b & x", 'powershell') == "Set-Location -LiteralPath 'C:\\a''b & x'\r"
assert cd_command('D:\\my folder', 'cmd') == 'cd /d "D:\\my folder"\r'
for path, shell in [('C:\\bad\npath', 'powershell'), ('C:\\%TEMP%', 'cmd'), ('C:\\!x!', 'cmd'), ('\\\\host\\share', 'cmd')]:
    try: cd_command(path, shell)
    except ValueError: pass
    else: raise AssertionError((path, shell))
print('File browser: directory navigation, back, hidden files and shell escaping passed')
