"""Saved OpenSSH connections. Credentials remain in the interactive terminal/agent."""
import json
import os
from pathlib import Path
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget,
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QFileDialog, QMessageBox)
from windows.fluent import label


def ssh_arguments(profile):
    name, host, user = (profile.get(k, '').strip() for k in ('name', 'host', 'user'))
    port = int(profile.get('port', '22'))
    if not name or not host or not user or host.startswith('-') or user.startswith('-') or any(c.isspace() or ord(c) < 32 for c in host + user) or not 1 <= port <= 65535:
        raise ValueError('请填写名称、有效主机、用户名和 1–65535 的端口。')
    args = ['ssh.exe', '-tt', '-p', str(port), '-l', user, '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=3']
    key = profile.get('key', '').strip()
    if key: args += ['-i', os.path.expanduser(key)]
    return args + [host]


class SSHServers(QWidget):
    def __init__(self, connect, parent=None):
        super().__init__(parent)
        self.connect = connect
        directory = Path(os.environ.get('LOCALDECK_DATA_DIR') or Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'.local/share')))/'LocalDeck')
        directory.mkdir(parents=True, exist_ok=True)
        self.settings = QSettings(str(directory/'ssh.ini'), QSettings.IniFormat)
        try:
            self.profiles = json.loads(self.settings.value('profiles', '[]'))
            if not isinstance(self.profiles, list): self.profiles = []
        except (ValueError, TypeError): self.profiles = []
        layout = QVBoxLayout(self)
        layout.addWidget(label('SSH 服务器', 'section'))
        tip = label('保存配置，下次一键连接 Linux。密码、密钥口令在终端内输入；首次连接请核对服务器指纹。', 'muted'); tip.setWordWrap(True); layout.addWidget(tip)
        self.list = QListWidget(); self.list.itemDoubleClicked.connect(lambda _:self.open()); layout.addWidget(self.list, 1)
        bar = QHBoxLayout()
        for text, fn in [('添加服务器', lambda:self.edit(False)), ('编辑', lambda:self.edit(True)), ('删除', self.remove), ('连接', self.open)]:
            button = QPushButton(text); button.clicked.connect(lambda checked=False, callback=fn:callback()); bar.addWidget(button)
        layout.addLayout(bar); self.refresh()

    def refresh(self):
        self.list.clear()
        for p in self.profiles: self.list.addItem(f"{p['name']}\n{p['user']}@{p['host']} : {p['port']}")
        self.list.setCurrentRow(0 if self.profiles else -1)

    def persist(self):
        self.settings.setValue('profiles', json.dumps(self.profiles, ensure_ascii=False)); self.settings.sync(); self.refresh()

    def edit(self, existing):
        index = self.list.currentRow()
        if existing and index < 0: return
        p = self.profiles[index] if existing else {'name':'', 'host':'', 'user':'root', 'port':'22', 'key':''}
        dialog = QDialog(self); dialog.setWindowTitle('SSH 服务器配置'); dialog.resize(510, 340)
        layout = QVBoxLayout(dialog); form = QFormLayout(); fields = {}
        for key, title in [('name','名称'), ('host','主机 / IP / SSH 别名'), ('user','用户名'), ('port','端口'), ('key','私钥路径（可选）')]:
            fields[key] = QLineEdit(str(p.get(key,''))); form.addRow(title, fields[key])
        layout.addLayout(form)
        choose = QPushButton('选择私钥文件'); choose.clicked.connect(lambda:fields['key'].setText(QFileDialog.getOpenFileName(dialog, '选择私钥')[0] or fields['key'].text())); layout.addWidget(choose)
        tip = label('使用 Windows 11 OpenSSH 客户端，保留服务器指纹校验。只保存密钥路径，不保存密码。', 'muted'); tip.setWordWrap(True); layout.addWidget(tip)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel); buttons.rejected.connect(dialog.reject)
        def save():
            profile = {key:field.text().strip() for key, field in fields.items()}
            try: ssh_arguments(profile)
            except (ValueError, TypeError): QMessageBox.warning(dialog, '配置不完整', '请检查主机、用户名和端口。'); return
            if existing: self.profiles[index] = profile
            else: self.profiles.append(profile)
            self.persist(); dialog.accept()
        buttons.accepted.connect(save); layout.addWidget(buttons); dialog.exec()

    def remove(self):
        index = self.list.currentRow()
        if index >= 0 and QMessageBox.question(self, '删除配置', '删除服务器配置？现有连接会继续运行。') == QMessageBox.Yes:
            self.profiles.pop(index); self.persist()

    def open(self):
        index = self.list.currentRow()
        if index >= 0:
            try: ssh_arguments(self.profiles[index]); self.connect(self.profiles[index])
            except (ValueError, TypeError) as error: QMessageBox.warning(self, '连接失败', str(error))
