"""Qt update state; all network and disk work stays off the UI thread."""
from datetime import datetime
import json
import os
from pathlib import Path
import queue
import threading
import webbrowser
from PySide6.QtCore import QObject, Signal, QSettings, QTimer, QStandardPaths, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox
from backend import updates
from windows.fluent import VERSION
from windows.update_credentials import read_token, save_token, CredentialError


class AppUpdater(QObject):
    changed = Signal()

    def __init__(self, parent=None, automatic=True):
        super().__init__(parent)
        directory = Path(os.environ.get('LOCALDECK_DATA_DIR') or Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'.local/share')))/'LocalDeck')
        directory.mkdir(parents=True, exist_ok=True)
        self.settings = QSettings(str(directory/'updates.ini'), QSettings.IniFormat)
        self.authorized = self.settings.value('authorized', False, type=bool)
        self.enabled = self.settings.value('automatic', True, type=bool)
        self.busy = False; self.downloading = False; self.progress = 0; self.path = ''; self.dismissed = False
        self.message = '尚未检查更新'; self.release = None
        self.queue = queue.Queue(); self.stop = threading.Event()
        try:
            cached = json.loads(self.settings.value('available', 'null'))
            if cached and updates.version_tuple(cached['version']) > updates.version_tuple(VERSION) and updates.safe_url(cached['page']): self.release = cached; self.message = '发现新版本 '+cached['version']
        except (ValueError, KeyError, TypeError): pass
        self.timer = QTimer(self); self.timer.timeout.connect(self.drain); self.timer.start(100)
        self.schedule = QTimer(self); self.schedule.timeout.connect(self.scheduled_check)
        if automatic: self.schedule.start(60000); QTimer.singleShot(1500, self.scheduled_check)

    @property
    def last_checked(self): return self.settings.value('lastChecked', '尚无成功检查记录')

    def set_enabled(self, value):
        self.enabled = value; self.settings.setValue('automatic', value); self.settings.sync(); self.changed.emit()

    def scheduled_check(self):
        if not self.busy and updates.scheduled_today(datetime.now(), self.settings.value('lastAttemptDay', ''), self.enabled): self.check()

    def check(self):
        if self.busy or self.stop.is_set(): return
        self.busy = True; self.message = '正在检查更新…'
        self.settings.setValue('lastAttemptDay', datetime.now().date().isoformat()); self.settings.sync(); self.changed.emit()
        def work():
            try: self.queue.put(('checked', updates.check(VERSION, 'windows', 'x64', read_token() if self.authorized else '')))
            except Exception as error: self.queue.put(('error', str(error) if isinstance(error, (updates.UpdateError, CredentialError)) else '检查失败，请检查网络后重试。'))
        threading.Thread(target=work, daemon=True).start()

    def confirm_download(self, parent):
        if self.busy or not self.release: return
        box = QMessageBox(parent); box.setWindowTitle('LocalDeck 软件更新'); box.setIcon(QMessageBox.Information)
        box.setText('LocalDeck '+self.release['version'])
        box.setInformativeText('下载完成后，请退出当前版本，再用新版 EXE 替换原文件。配置会保留，终端任务不会迁移。')
        box.setDetailedText(self.release['notes'])
        cancel = box.addButton('稍后', QMessageBox.RejectRole); download = box.addButton('下载更新', QMessageBox.AcceptRole)
        box.setDefaultButton(cancel); box.exec()
        if box.clickedButton() is download: self.download()

    def download(self):
        if self.busy or not self.release: return
        self.busy = True; self.downloading = True; self.progress = 0; self.message = '正在下载更新…'; self.changed.emit()
        release = dict(self.release)
        destination = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation) or str(Path.home()/'Downloads')
        def progress(value):
            if self.stop.is_set(): raise updates.UpdateError('下载已取消。')
            self.queue.put(('progress', value))
        def work():
            try: self.queue.put(('downloaded', updates.download(release, destination, progress, read_token() if self.authorized else '')))
            except Exception as error: self.queue.put(('error', str(error) if isinstance(error, (updates.UpdateError, CredentialError)) else '下载失败，请检查网络与下载目录权限。'))
        threading.Thread(target=work, daemon=True).start()

    def drain(self):
        dirty = False
        try:
            while True:
                kind, value = self.queue.get_nowait(); dirty = True
                if self.stop.is_set(): continue
                if kind == 'progress': self.progress = value; self.message = f'正在下载更新… {value}%'
                elif kind == 'checked':
                    self.busy = False; self.release = value; self.dismissed = False; self.path = ''
                    self.message = '发现新版本 '+value['version'] if value else '当前已是最新正式版本'
                    self.settings.setValue('lastChecked', datetime.now().strftime('%Y-%m-%d %H:%M'))
                    self.settings.setValue('available', json.dumps(value)); self.settings.sync()
                elif kind == 'downloaded':
                    self.busy = self.downloading = False; self.path = value; self.message = '下载完成，SHA-256 校验通过'
                elif kind == 'error': self.busy = self.downloading = False; self.message = value
        except queue.Empty: pass
        if dirty: self.changed.emit()

    def save_authorization(self, value):
        if self.busy: return
        token = value.strip()
        if token and (len(token.encode('utf-8')) > 2560 or not all(33 <= ord(c) <= 126 for c in token)):
            self.message = '访问令牌格式无效。'; self.changed.emit(); return
        try:
            save_token(token); self.authorized = bool(token)
            self.settings.setValue('authorized', self.authorized); self.settings.sync()
            self.message = '授权已保存到 Windows 凭据管理器，可手动检查更新' if token else '私有仓库授权已移除'
        except CredentialError as error: self.message = str(error)
        self.changed.emit()

    def dismiss(self): self.dismissed = True; self.changed.emit()
    def open_download(self):
        if self.path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.path).parent)))
    def open_releases(self): webbrowser.open(updates.RELEASES_URL)
    def shutdown(self): self.stop.set(); self.schedule.stop(); self.timer.stop()
