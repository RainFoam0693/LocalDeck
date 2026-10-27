"""Qt terminal tabs. Hidden pages retain their independent ConPTY sessions."""
import os
import queue
import threading
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor, QKeySequence
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPlainTextEdit, QTabWidget, QPushButton, QFileDialog, QMessageBox, QMenu)
from windows.fluent import label

COLORS = {'black':'#181818', 'red':'#e87575', 'green':'#83cd9b', 'brown':'#e6c078',
          'blue':'#7aaef3', 'magenta':'#c694e8', 'cyan':'#6bd3ce', 'white':'#e5ebf4',
          'brightblack':'#87909c', 'brightred':'#ff9999', 'brightgreen':'#a4efbc',
          'brightbrown':'#ffe1a1', 'brightblue':'#a3c7ff', 'brightmagenta':'#e3baff',
          'brightcyan':'#9aeee8', 'brightwhite':'#ffffff'}


def color(value, default):
    return COLORS.get(value, '#' + value if len(value) == 6 else default)


class TerminalView(QPlainTextEdit):
    def __init__(self, session):
        super().__init__(); self.session = session; self.version = -1
        self.setReadOnly(True); self.setUndoRedoEnabled(False)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        font = QFont('Cascadia Mono', 11); font.setFamilies(['Cascadia Mono', 'Consolas', 'monospace'])
        self.setFont(font)
        self.setStyleSheet('QPlainTextEdit { font-family: "Cascadia Mono", "Consolas", monospace; font-size: 14px; padding: 14px; }')
        self.setAttribute(Qt.WA_InputMethodEnabled, True)
        self.setAccessibleName('交互终端')

    def paste_terminal(self):
        text = QApplication.clipboard().text()
        if ('\n' in text or '\r' in text) and QMessageBox.question(self, '粘贴多行命令', '内容包含换行，可能立即执行命令。继续粘贴？') != QMessageBox.Yes: return
        self.session.write(text.replace('\r\n', '\r').replace('\n', '\r'))

    def keyPressEvent(self, event):
        ctrl = bool(event.modifiers() & Qt.ControlModifier)
        shift = bool(event.modifiers() & Qt.ShiftModifier)
        key = event.key()
        if ctrl and shift and key == Qt.Key_C: self.copy(); return
        if (ctrl and shift and key == Qt.Key_V) or (shift and key == Qt.Key_Insert): self.paste_terminal(); return
        if ctrl and key == Qt.Key_Insert: self.copy(); return
        keys = {Qt.Key_Return:'\r', Qt.Key_Enter:'\r', Qt.Key_Backspace:'\x7f', Qt.Key_Tab:'\t', Qt.Key_Backtab:'\x1b[Z',
                Qt.Key_Escape:'\x1b', Qt.Key_Up:'\x1b[A', Qt.Key_Down:'\x1b[B', Qt.Key_Right:'\x1b[C', Qt.Key_Left:'\x1b[D',
                Qt.Key_Home:'\x1b[H', Qt.Key_End:'\x1b[F', Qt.Key_Delete:'\x1b[3~', Qt.Key_Insert:'\x1b[2~',
                Qt.Key_PageUp:'\x1b[5~', Qt.Key_PageDown:'\x1b[6~'}
        for i, value in enumerate(['OP','OQ','OR','OS','[15~','[17~','[18~','[19~','[20~','[21~','[23~','[24~']): keys[Qt.Key_F1 + i] = '\x1b' + value
        if ctrl and Qt.Key_A <= key <= Qt.Key_Z: value = chr(key - Qt.Key_A + 1)
        else: value = keys.get(key, event.text())
        if value:
            if event.modifiers() & Qt.AltModifier: value = '\x1b' + value
            self.session.write(value)
            self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def inputMethodEvent(self, event):
        if event.commitString(): self.session.write(event.commitString())
        event.accept()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        copy = menu.addAction('复制  Ctrl+Shift+C'); copy.setEnabled(self.textCursor().hasSelection()); copy.triggered.connect(self.copy)
        menu.addAction('粘贴  Ctrl+Shift+V', self.paste_terminal)
        menu.exec(event.globalPos())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.viewport().width() < 60: return
        fm = self.fontMetrics()
        try: self.session.resize(max(5, min(150, (self.viewport().height()-28)//fm.lineSpacing())), max(20, min(300, (self.viewport().width()-28)//max(1, fm.horizontalAdvance('M')))))
        except (OSError, EOFError): pass

    def paint_screen(self):
        version, lines, cursor, running, columns = self.session.snapshot()
        if version == self.version: return running
        self.version = version
        scrollbar = self.verticalScrollBar(); bottom = scrollbar.value() >= scrollbar.maximum()-3; scroll = scrollbar.value()
        selected = self.textCursor(); start, end = selected.selectionStart(), selected.selectionEnd()
        self.setUpdatesEnabled(False)
        try:
            doc = self.document(); doc.clear(); writer = QTextCursor(doc)
            for row, line in enumerate(lines):
                segment = ''; previous = None
                for col in range(columns):
                    cell = line.get(col)
                    fg = color(cell.fg, '#e5ebf4') if cell else '#e5ebf4'
                    bg = color(cell.bg, '#1c1c1c') if cell else '#1c1c1c'
                    if cell and cell.reverse: fg, bg = bg, fg
                    if row == cursor[0] and col == cursor[1] and not cursor[2]: fg, bg = '#181818', '#76b9ed'
                    style = (fg, bg, bool(cell and cell.bold), bool(cell and cell.underscore))
                    if previous is not None and style != previous:
                        writer.insertText(segment, self.char_format(previous)); segment = ''
                    segment += cell.data if cell else ' '; previous = style
                if segment: writer.insertText(segment, self.char_format(previous))
                if row != len(lines)-1: writer.insertText('\n')
            if end > start:
                selected = QTextCursor(doc); selected.setPosition(min(start, doc.characterCount()-1)); selected.setPosition(min(end, doc.characterCount()-1), QTextCursor.KeepAnchor); self.setTextCursor(selected)
            scrollbar.setValue(scrollbar.maximum() if bottom else scroll)
        finally: self.setUpdatesEnabled(True)
        return running

    @staticmethod
    def char_format(style):
        fmt = QTextCharFormat(); fmt.setForeground(QColor(style[0])); fmt.setBackground(QColor(style[1]))
        fmt.setFontWeight(QFont.Bold if style[2] else QFont.Normal); fmt.setFontUnderline(style[3]); return fmt


class TerminalWorkspace(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.sessions = {}; self.retired = []; self.spawn_threads = []; self.pending = queue.Queue()
        self.next_number = 1; self.closing = False
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(12)
        bar = QHBoxLayout(); bar.addWidget(label('独立会话 · 切换页面继续运行', 'muted')); bar.addStretch()
        for title, callback in [('选择目录', self.choose_directory), ('＋ PowerShell', lambda:self.add(shell='powershell')), ('＋ CMD', self.add)]:
            button = QPushButton(title); button.clicked.connect(lambda checked=False, fn=callback:fn()); bar.addWidget(button)
        layout.addLayout(bar)
        self.tabs = QTabWidget(); self.tabs.setTabsClosable(True); self.tabs.setMovable(True); self.tabs.tabCloseRequested.connect(self.close_index)
        self.tabs.currentChanged.connect(self.focus_terminal); layout.addWidget(self.tabs, 1)
        self.empty = label('准备好开始工作了吗？\n\n选择 PowerShell 或 CMD，创建第一个终端。'); self.empty.setAlignment(Qt.AlignCenter)
        self.tabs.addTab(self.empty, '终端工作区'); self.tabs.tabBar().hide()
        footer = QHBoxLayout(); self.status = label('Ctrl+C 中断命令 · Ctrl+Shift+C / V 复制粘贴', 'muted'); footer.addWidget(self.status, 1)
        layout.addLayout(footer)
        self.timer = QTimer(self); self.timer.timeout.connect(self.paint); self.timer.start(80)

    def choose_directory(self):
        directory = QFileDialog.getExistingDirectory(self, '终端工作目录', os.path.expanduser('~'))
        if directory: self.add(directory=directory, shell='powershell')

    def add(self, directory=None, shell='cmd'):
        if self.closing: return
        directory = directory or os.path.expanduser('~'); self.status.setText('正在创建终端…')
        def spawn():
            try:
                from windows.terminal_session import TerminalSession
                session = TerminalSession(directory, shell)
                if self.closing: session.close()
                else: self.pending.put((session, shell, None))
            except Exception as error: self.pending.put((None, shell, str(error)))
        worker = threading.Thread(target=spawn, daemon=True); self.spawn_threads.append(worker); worker.start()

    def attach(self, session, shell='cmd'):
        if self.tabs.indexOf(self.empty) >= 0: self.tabs.removeTab(self.tabs.indexOf(self.empty))
        self.tabs.tabBar().show()
        view = TerminalView(session); self.sessions[view] = (session, view)
        index = self.tabs.addTab(view, f'{"PowerShell" if shell == "powershell" else "CMD"} {self.next_number}'); self.next_number += 1
        self.tabs.setTabToolTip(index, session.directory); self.tabs.setCurrentIndex(index); view.setFocus()
        return view

    def focus_terminal(self, index):
        widget = self.tabs.widget(index)
        if widget: widget.setFocus()

    def paint(self):
        if self.closing: return
        try:
            while True:
                session, shell, error = self.pending.get_nowait()
                if error: self.status.setText('终端启动失败：' + error)
                else: self.attach(session, shell)
        except queue.Empty: pass
        view = self.tabs.currentWidget()
        if view in self.sessions:
            session, _ = self.sessions[view]
            running = view.paint_screen()
            self.status.setText(session.directory + (' · 运行中' if session.running else ' · 会话已结束') + ((' · '+session.error) if session.error else ''))

    def close_index(self, index, confirm=True):
        view = self.tabs.widget(index)
        if view not in self.sessions: return
        if confirm and QMessageBox.question(self, '关闭终端', '关闭此终端及其中运行的命令？') != QMessageBox.Yes: return
        session, _ = self.sessions.pop(view); self.retired.append(session)
        self.tabs.removeTab(index); view.deleteLater()
        threading.Thread(target=session.close, daemon=True).start()
        if not self.sessions:
            self.tabs.addTab(self.empty, '终端工作区'); self.tabs.tabBar().hide()
            self.status.setText('Ctrl+C 中断命令 · Ctrl+Shift+C / V 复制粘贴')

    def shutdown(self):
        self.closing = True
        for worker in self.spawn_threads: worker.join()
        for session in self.retired: session.close()
        for session, _ in list(self.sessions.values()): session.close()
        try:
            while True:
                session, _, _ = self.pending.get_nowait()
                if session: session.close()
        except queue.Empty: pass
