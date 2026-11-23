"""Qt update state; all network and disk work stays off the UI thread."""
from datetime import datetime
import base64
import json
import os
from pathlib import Path
import queue
import threading
import subprocess
import sys
import webbrowser
from PySide6.QtCore import QObject, Signal, QSettings, QTimer, QStandardPaths, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox
from backend import updates
from windows.fluent import VERSION
from windows.update_migration import clear_legacy_update_credential


class AppUpdater(QObject):
    changed = Signal()

    def __init__(self, parent=None, automatic=True):
        super().__init__(parent)
        directory = Path(os.environ.get('LOCALDECK_DATA_DIR') or Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'.local/share')))/'LocalDeck')
        directory.mkdir(parents=True, exist_ok=True)
        self.settings = QSettings(str(directory/'updates.ini'), QSettings.IniFormat)
        self.settings.remove('authorized')
        clear_legacy_update_credential()
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
            try: self.queue.put(('checked', updates.check(VERSION, 'windows', 'x64')))
            except Exception as error: self.queue.put(('error', str(error) if isinstance(error, updates.UpdateError) else '检查失败，请检查网络后重试。'))
        threading.Thread(target=work, daemon=True).start()

    def confirm_download(self, parent):
        if self.busy or not self.release: return
        box = QMessageBox(parent); box.setWindowTitle('LocalDeck 软件更新'); box.setIcon(QMessageBox.Information)
        box.setText('LocalDeck '+self.release['version'])
        box.setInformativeText('下载完成后，可选择安装并重启。配置会保留，终端任务不会迁移。')
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
            try: self.queue.put(('downloaded', updates.download(release, destination, progress)))
            except Exception as error: self.queue.put(('error', str(error) if isinstance(error, updates.UpdateError) else '下载失败，请检查网络与下载目录权限。'))
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

    def dismiss(self): self.dismissed = True; self.changed.emit()
    def open_download(self):
        if not self.path or self.busy:
            return
        if not getattr(sys, 'frozen', False):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.path).parent)))
            return
        self.parent().quit_from_tray(install=True)

    def launch_installer(self):
        # A separate process waits for the packaged EXE to release its file lock.
        script = r"""
$ErrorActionPreference = 'Stop'
$env:PYINSTALLER_RESET_ENVIRONMENT = '1'
$target = $env:LOCALDECK_INSTALL_TARGET
$staged = "$target.update-$([guid]::NewGuid()).exe"
$backup = "$staged.previous"
try {
    Copy-Item -LiteralPath $env:LOCALDECK_INSTALL_SOURCE -Destination $staged
    Wait-Process -Id ([int]$env:LOCALDECK_INSTALL_PID) -Timeout 120 -ErrorAction SilentlyContinue
    if (Get-Process -Id ([int]$env:LOCALDECK_INSTALL_PID) -ErrorAction SilentlyContinue) { throw 'LocalDeck did not exit' }
    [IO.File]::Replace($staged, $target, $backup)
    try { Start-Process -FilePath $target }
    catch {
        [IO.File]::Replace($backup, $target, $null)
        throw
    }
    Remove-Item -LiteralPath $backup -ErrorAction SilentlyContinue
} catch {
    if (-not (Get-Process -Id ([int]$env:LOCALDECK_INSTALL_PID) -ErrorAction SilentlyContinue)) {
        try { Start-Process -FilePath $target } catch {}
    }
    Add-Type -AssemblyName System.Windows.Forms
    [void][Windows.Forms.MessageBox]::Show('无法自动安装。请检查安装目录权限，或手动替换应用。', 'LocalDeck')
} finally {
    Remove-Item -LiteralPath $staged -ErrorAction SilentlyContinue
}
"""
        env = dict(os.environ, LOCALDECK_INSTALL_TARGET=sys.executable,
                   LOCALDECK_INSTALL_SOURCE=self.path, LOCALDECK_INSTALL_PID=str(os.getpid()))
        encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
        host = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        try:
            subprocess.Popen([str(host), '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                             env=env, creationflags=subprocess.CREATE_NO_WINDOW)
            return True
        except OSError as error:
            self.message = '无法启动安装程序：' + str(error)
            self.changed.emit()
            return False

    def open_releases(self): webbrowser.open(updates.RELEASES_URL)
    def shutdown(self): self.stop.set(); self.schedule.stop(); self.timer.stop()
