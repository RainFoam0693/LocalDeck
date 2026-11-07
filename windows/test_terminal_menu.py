"""Terminal menu actions must preserve selection and never cut/delete shell output."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QMimeData
from PySide6.QtWidgets import QApplication, QMessageBox
from windows.terminal import TerminalView

app = QApplication([])
clipboard = app.clipboard()
mime = clipboard.mimeData()
saved = {kind:mime.data(kind) for kind in mime.formats()} if mime else {}
try:
    writes = []
    session = SimpleNamespace(running=True, resize=lambda *args:None, write=writes.append)
    view = TerminalView(session); view.resize(700,250)
    view.setPlainText('\n'.join(f'MENU_LOG_{i}' for i in range(100)))
    menus = []
    def action(title):
        menu = view.make_context_menu(); menus.append(menu)
        return next(item for item in menu.actions() if item.text().split('  ')[0] == title)
    assert not action('复制').isEnabled()
    view.selectAll(); selected = view.textCursor().selectedText()
    action('复制').trigger(); assert 'MENU_LOG_0' in clipboard.text()
    assert view.textCursor().selectedText() == selected
    action('复制全部文本').trigger(); assert 'MENU_LOG_99' in clipboard.text()
    assert view.textCursor().selectedText() == selected
    action('取消选择').trigger(); assert not view.textCursor().hasSelection()
    clipboard.setText('echo hello'); action('粘贴').trigger(); assert writes == ['echo hello']
    clipboard.setText('echo one\necho two')
    with patch.object(QMessageBox, 'question', return_value=QMessageBox.No): action('粘贴').trigger()
    assert writes == ['echo hello'], 'cancel must not send any command'
    with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes): action('粘贴').trigger()
    assert writes[-1] == 'echo one\recho two'
    session.running = False; assert not action('粘贴').isEnabled()
    view.verticalScrollBar().setValue(0); action('回到最新输出').trigger()
    assert view.verticalScrollBar().value() == view.verticalScrollBar().maximum()
    view.close()
    print('Terminal menu: copying, selection, paste, multiline consent and live output passed')
finally:
    restored = QMimeData()
    for kind, data in saved.items(): restored.setData(kind, data)
    clipboard.setMimeData(restored)
