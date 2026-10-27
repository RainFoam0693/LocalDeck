"""Qt terminal tabs. Hidden pages retain their independent ConPTY sessions."""
import os
import queue
import threading
from PySide6.QtCore import Qt, QTimer, QSettings
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor, QKeySequence
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QPlainTextEdit, QTabWidget, QTabBar, QToolButton, QPushButton, QFileDialog, QMessageBox, QMenu)
from windows.fluent import label, is_dark, themed, appearance_icon
from windows.files import TerminalFiles, cd_command

COLORS = {'black':'#181818', 'red':'#e87575', 'green':'#83cd9b', 'brown':'#e6c078',
          'blue':'#7aaef3', 'magenta':'#c694e8', 'cyan':'#6bd3ce', 'white':'#e5ebf4',
          'brightblack':'#87909c', 'brightred':'#ff9999', 'brightgreen':'#a4efbc',
          'brightbrown':'#ffe1a1', 'brightblue':'#a3c7ff', 'brightmagenta':'#e3baff',
          'brightcyan':'#9aeee8', 'brightwhite':'#ffffff'}


def color(value, default):
    base = COLORS.get(value, '#' + value if len(value) == 6 else default)
    if not is_dark() and value in COLORS:
        return {'black':'#202020','red':'#b42324','green':'#14753a','brown':'#946000','blue':'#1756a9','magenta':'#883c9d','cyan':'#007a78','white':'#606060', 'brightblack':'#777777','brightred':'#bf3434','brightgreen':'#14753a','brightbrown':'#946000','brightblue':'#1756a9','brightmagenta':'#883c9d','brightcyan':'#007a78','brightwhite':'#4a4a4a'}.get(value, base)
    return base


class TerminalView(QPlainTextEdit):
    def __init__(self, session):
        super().__init__(); self.session = session; self.version = -1; self.row_origins = []
        self.setReadOnly(True); self.setUndoRedoEnabled(False)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        font = QFont('Cascadia Mono', 11); font.setFamilies(['Cascadia Mono', 'Consolas', 'Menlo', 'monospace'])
        self.setFont(font)
        self.setStyleSheet('QPlainTextEdit { font-family: "Cascadia Mono", "Consolas", "Menlo", monospace; font-size: 14px; padding: 14px; }')
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
        if hasattr(self.session, 'snapshot_for_view'):
            version, lines, cursor, running, columns, origins = self.session.snapshot_for_view()
        else:
            version, lines, cursor, running, columns = self.session.snapshot(); origins = []
        if version == self.version: return running
        self.version = version
        scrollbar = self.verticalScrollBar(); bottom = scrollbar.value() == scrollbar.maximum(); scroll = scrollbar.value()
        anchor = self.row_origins[scroll] if scroll < len(self.row_origins) else None
        if not bottom and anchor is not None and origins:
            # Match the same history row even when the bounded history drops old rows.
            scroll = next((i for i, line in enumerate(origins) if line is anchor), 0)
        self.row_origins = origins
        selected = self.textCursor(); start, end = selected.selectionStart(), selected.selectionEnd()
        self.setUpdatesEnabled(False)
        try:
            doc = self.document(); doc.clear(); writer = QTextCursor(doc)
            for row, line in enumerate(lines):
                segment = ''; previous = None
                for col in range(columns):
                    cell = line.get(col)
                    fg = color(cell.fg, themed('#e5ebf4')) if cell else themed('#e5ebf4')
                    bg = color(cell.bg, themed('#1c1c1c')) if cell else themed('#1c1c1c')
                    if cell and cell.reverse: fg, bg = bg, fg
                    if row == cursor[0] and col == cursor[1] and not cursor[2]: fg, bg = themed('#181818'), themed('#76b9ed')
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
        self.files = TerminalFiles()
        self.files.cdRequested.connect(self.change_directory)
        self.files.newTerminalRequested.connect(lambda path:self.add(directory=path, shell='powershell'))
        self.files.locateRequested.connect(self.locate_directory)
        from pathlib import Path
        settings_dir = Path(os.environ.get('LOCALDECK_DATA_DIR') or Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'.local/share')))/'LocalDeck')
        settings_dir.mkdir(parents=True, exist_ok=True)
        self.file_settings = QSettings(str(settings_dir/'terminal.ini'), QSettings.IniFormat)
        visible = self.file_settings.value('files/visible', True, type=bool)
        self.files.hidden.setChecked(self.file_settings.value('files/hidden', False, type=bool))
        self.files.hidden.toggled.connect(self.save_hidden_files)
        self.files_toggle = QPushButton(); self.files_toggle.setCheckable(True); self.files_toggle.setChecked(visible)
        self.files_toggle.toggled.connect(self.set_files_visible); bar.insertWidget(0, self.files_toggle)
        self.set_files_visible(visible)
        layout.addLayout(bar)
        self.tabs = QTabWidget(); self.tabs.setTabsClosable(False); self.tabs.setMovable(True); self.tabs.tabCloseRequested.connect(self.close_index)
        self.tabs.currentChanged.connect(self.focus_terminal)
        splitter = QSplitter(); splitter.addWidget(self.files); splitter.addWidget(self.tabs)
        self.files.setMinimumWidth(260); self.tabs.setMinimumWidth(340)
        splitter.setSizes([290, 750]); splitter.setStretchFactor(1, 1); layout.addWidget(splitter, 1)
        self.empty = label('准备好开始工作了吗？\n\n选择 PowerShell 或 CMD，创建第一个终端。'); self.empty.setAlignment(Qt.AlignCenter)
        self.tabs.addTab(self.empty, '终端工作区'); self.tabs.tabBar().hide()
        footer = QHBoxLayout(); self.status = label('Ctrl+C 中断命令 · Ctrl+Shift+C / V 复制粘贴', 'muted'); footer.addWidget(self.status, 1)
        layout.addLayout(footer)
        self.timer = QTimer(self); self.timer.timeout.connect(self.paint); self.timer.start(80)

    def save_hidden_files(self, visible):
        self.file_settings.setValue('files/hidden', visible); self.file_settings.sync()

    def set_files_visible(self, visible):
        self.files.setVisible(visible)
        self.files_toggle.setText('收起文件' if visible else '展开文件')
        self.files_toggle.setAccessibleName('收起文件面板' if visible else '展开文件面板')
        self.file_settings.setValue('files/visible', visible); self.file_settings.sync()

    def change_directory(self, path):
        view = self.tabs.currentWidget()
        if view not in self.sessions or not self.sessions[view][0].running:
            self.add(directory=path, shell='powershell'); return
        session = self.sessions[view][0]
        try:
            if not os.path.isdir(path): raise ValueError('目录不存在。')
            command = cd_command(path, session.shell)
            if not session.prompt_directory(): raise ValueError('请先回到空白 Shell 提示符，或在此目录新建终端。')
            session.write(command); view.setFocus()
        except (ValueError, AttributeError) as error: QMessageBox.warning(self, '切换目录', str(error))

    def locate_directory(self):
        view = self.tabs.currentWidget()
        if view in self.sessions:
            session = self.sessions[view][0]
            path = session.prompt_directory() if hasattr(session, 'prompt_directory') else None
            self.files.navigate(path or session.directory)

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
        close = QToolButton(self.tabs.tabBar()); view.close_button = close; close.setAutoRaise(True); close.setAccessibleName('关闭终端'); close.setToolTip('关闭终端')
        close.setIcon(appearance_icon('close', themed('#b0b0b0'))); close.setFixedSize(24,24)
        close.setStyleSheet('QToolButton { background: transparent; border: none; border-radius: 4px; } QToolButton:hover { background: rgba(128,128,128,0.2); }')
        close.clicked.connect(lambda:self.close_index(self.tabs.indexOf(view)))
        self.tabs.tabBar().setTabButton(index, QTabBar.RightSide, close)
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
