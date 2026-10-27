"""File browser shared by terminal sessions; all deletion goes through the recycle bin."""
import os
from pathlib import Path
from PySide6.QtCore import Qt, QDir, QFile, QIODevice, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QFileSystemModel, QTreeView, QMenu, QCheckBox, QFileDialog, QInputDialog, QMessageBox, QApplication)


def cd_command(path, shell):
    if any(ord(c) < 32 or ord(c) == 127 for c in path):
        raise ValueError('路径含控制字符，无法发送到终端。')
    if shell == 'powershell':
        return "Set-Location -LiteralPath '" + path.replace("'", "''") + "'\r"
    if any(c in path for c in '%!"') or path.startswith('\\\\'):
        raise ValueError('此路径请使用 PowerShell，或选择“在此目录新建终端”。')
    return 'cd /d "' + path + '"\r'


class TerminalFiles(QWidget):
    cdRequested = Signal(str)
    newTerminalRequested = Signal(str)
    locateRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent); self.directory = str(Path.home()); self.history = []
        layout = QVBoxLayout(self); layout.setContentsMargins(12, 12, 12, 12)
        bar = QHBoxLayout()
        for title, callback in [('后退', self.back), ('上级', lambda:self.navigate(str(Path(self.directory).parent))),
                                ('选择', self.choose), ('刷新', self.refresh)]:
            button = QPushButton(title); button.clicked.connect(callback); bar.addWidget(button)
        layout.addLayout(bar)
        self.path = QLineEdit(self.directory); self.path.setPlaceholderText('输入路径，回车前往')
        self.path.returnPressed.connect(lambda:self.navigate(os.path.expanduser(self.path.text())))
        layout.addWidget(self.path)
        self.tree = QTreeView(); self.tree.setRootIsDecorated(False); self.tree.setSortingEnabled(True)
        self.tree.setHeaderHidden(True); self.tree.setUniformRowHeights(True)
        self.tree.setStyleSheet('QTreeView { border: none; border-radius: 8px; background: transparent; outline: none; } QTreeView::item { padding: 5px 3px; min-height: 22px; border-radius: 4px; } QTreeView::item:selected { background: rgba(110,170,225,0.25); }')
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu); self.tree.customContextMenuRequested.connect(self.context_menu)
        self.tree.doubleClicked.connect(self.open_index); layout.addWidget(self.tree, 1)
        self.hidden = QCheckBox('显示隐藏项目'); self.hidden.toggled.connect(self.refresh); layout.addWidget(self.hidden)
        for title, callback in [('定位终端目录', self.locateRequested.emit), ('cd 到此目录', lambda:self.cdRequested.emit(self.directory))]:
            button = QPushButton(title); button.clicked.connect(callback); layout.addWidget(button)
        self.refresh()

    def refresh(self):
        old = getattr(self, 'model', None)
        self.model = QFileSystemModel(self); self.model.setReadOnly(True)
        self.model.setOption(QFileSystemModel.DontUseCustomDirectoryIcons, True)
        flags = QDir.AllEntries | QDir.NoDotAndDotDot
        if self.hidden.isChecked(): flags |= QDir.Hidden
        self.model.setFilter(flags); self.model.setRootPath(self.directory)
        self.tree.setModel(self.model); self.tree.setRootIndex(self.model.index(self.directory))
        for column in (1, 2, 3): self.tree.hideColumn(column)
        self.tree.sortByColumn(0, Qt.AscendingOrder)
        if old: old.deleteLater()

    def navigate(self, path, record=True):
        path = os.path.abspath(os.path.join(self.directory, path))
        if not os.path.isdir(path):
            self.error('目录不存在或无法访问。'); return
        if record and path != self.directory: self.history.append(self.directory)
        self.directory = path; self.path.setText(path); self.refresh()

    def back(self):
        if self.history: self.navigate(self.history.pop(), record=False)

    def choose(self):
        path = QFileDialog.getExistingDirectory(self, '选择目录', self.directory)
        if path: self.navigate(path)

    def open_index(self, index):
        path = self.model.filePath(index)
        if os.path.isdir(path): self.navigate(path)
        else: QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def error(self, text): QMessageBox.warning(self, '文件操作', str(text))

    def context_menu(self, point):
        index = self.tree.indexAt(point)
        path = self.model.filePath(index) if index.isValid() else self.directory
        if index.isValid(): self.tree.setCurrentIndex(index)
        folder = path if os.path.isdir(path) else os.path.dirname(path)
        menu = QMenu(self)
        menu.addAction('打开', lambda:self.navigate(path) if os.path.isdir(path) else QDesktopServices.openUrl(QUrl.fromLocalFile(path)))
        menu.addAction('在当前终端 cd 到此目录', lambda:self.cdRequested.emit(folder))
        menu.addAction('在此目录新建终端', lambda:self.newTerminalRequested.emit(folder))
        menu.addSeparator()
        menu.addAction('复制完整路径', lambda:QApplication.clipboard().setText(path))
        menu.addAction('复制名称', lambda:QApplication.clipboard().setText(os.path.basename(path)))
        menu.addAction('在文件管理器中打开', lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(folder)))
        menu.addSeparator()
        menu.addAction('新建文件夹…', lambda:self.edit(folder, folder=True))
        menu.addAction('新建文件…', lambda:self.edit(folder))
        if index.isValid():
            menu.addAction('重命名…', lambda:self.edit(folder, source=path))
            menu.addAction('移到回收站…', lambda:self.trash(path))
        menu.addSeparator(); menu.addAction('刷新', self.refresh)
        menu.exec(self.tree.viewport().mapToGlobal(point))

    def edit(self, directory, folder=False, source=None):
        name, ok = QInputDialog.getText(self, '重命名' if source else '新建文件夹' if folder else '新建文件', '名称', text=os.path.basename(source) if source else '')
        if not ok: return
        try:
            if not name or name in ('.', '..') or any(c in name for c in '/\\') or any(ord(c)<32 for c in name): raise ValueError('请输入有效名称。')
            target = os.path.join(directory, name)
            if source and target == source: return
            if os.path.lexists(target): raise ValueError('名称已存在。')
            if source:
                if not QDir().rename(source, target): raise OSError('无法重命名，请检查权限。')
            elif folder: os.mkdir(target)
            else:
                with open(target, 'xb'): pass
            self.refresh()
        except (OSError, ValueError) as error: self.error(error)

    def trash(self, path):
        if QMessageBox.question(self, '移到回收站', '将“' + os.path.basename(path) + '”移到回收站？') != QMessageBox.Yes: return
        result = QFile.moveToTrash(path)
        success = result[0] if isinstance(result, tuple) else result
        if not success: self.error('无法移到回收站，请检查权限。')
        self.refresh()
