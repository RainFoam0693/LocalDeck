"""Qt updater state, consent, caching and settings layout; no GitHub credentials used."""
from datetime import datetime
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from windows.app import App
from windows.fluent import setup_theme
from windows.updates import AppUpdater
from backend import updates

qt = QApplication([]); setup_theme(qt)
output = Path(os.environ.get('LOCALDECK_UPDATE_UI_OUTPUT', str(Path(tempfile.gettempdir())/'localdeck-update-preview')))
output.mkdir(parents=True, exist_ok=True)
release = {'version': '1.1.0', 'name': 'LocalDeck-1.1.0-Windows-x64.exe',
           'url': updates.RELEASES_URL+'/download/v1.1.0/LocalDeck-1.1.0-Windows-x64.exe',
           'page': updates.RELEASES_URL+'/tag/v1.1.0', 'notes': '新增退出确认、进程名称识别和应用内更新。',
           'digest': 'sha256:'+hashlib.sha256(b'package').hexdigest(), 'size': 7, 'checksum': ''}


def pump(predicate):
    for _ in range(200):
        qt.processEvents(); QTest.qWait(10)
        if predicate(): return
    raise AssertionError('Update operation timed out')

with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, LOCALDECK_DATA_DIR=directory):
    updater = AppUpdater(automatic=False)
    with patch('windows.updates.updates.check', return_value=release) as network:
        updater.check(); updater.check()
        pump(lambda:not updater.busy)
        assert network.call_count == 1
    assert updater.release['version'] == '1.1.0' and updater.path == ''
    assert updater.last_checked != '尚无成功检查记录'
    cached = AppUpdater(automatic=False); assert cached.release == release
    # A default/cancel dialog must never initiate a download.
    with patch.object(updater, 'download') as download:
        QTimer.singleShot(10, lambda:qt.activeModalWidget().reject())
        updater.confirm_download(None); download.assert_not_called()
    # Once consent is explicit, download may start.
    with patch.object(updater, 'download') as download:
        def consent():
            box = qt.activeModalWidget()
            next(button for button in box.buttons() if button.text() == '下载更新').click()
        QTimer.singleShot(10, consent); updater.confirm_download(None); download.assert_called_once()
    with patch('windows.updates.updates.download', return_value=directory+'/LocalDeck.exe'):
        updater.download(); pump(lambda:not updater.busy)
    assert updater.path.endswith('LocalDeck.exe') and '校验通过' in updater.message
    with patch('windows.updates.updates.check', side_effect=updates.UpdateError('网络连接失败')):
        updater.check(); pump(lambda:not updater.busy)
    assert updater.message == '网络连接失败' and updater.release == release
    with patch('windows.updates.updates.check', return_value=None):
        updater.check(); pump(lambda:not updater.busy)
    assert updater.release is None and updater.path == '' and '最新' in updater.message
    updater.dismiss(); assert updater.dismissed
    updater.set_enabled(False)
    assert not updater.enabled
    # The UI stays usable and the settings content scrolls on smaller displays.
    app = App(preview=True); app.updater.release = release; app.updater.message = '发现新版本 1.1.0'; app.updater.changed.emit()
    app.show(); qt.processEvents(); assert app.update_banner.isVisible()
    app.grab().save(str(output/'update-banner.png'))
    failures = []
    def inspect_settings():
        dialog = qt.activeModalWidget()
        try:
            assert isinstance(dialog, QDialog)
            assert dialog.height() <= qt.primaryScreen().availableGeometry().height(), f'Settings height {dialog.height()} exceeds screen {qt.primaryScreen().availableGeometry().height()}'
            from PySide6.QtWidgets import QCheckBox, QScrollArea
            assert any('每周一、三、五' in item.text() for item in dialog.findChildren(QCheckBox))
            assert dialog.findChild(QScrollArea).verticalScrollBar().maximum() > 0, 'Settings content cannot scroll'
            dialog.grab().save(str(output/'update-settings.png'))
        except Exception as error:
            dialog.grab().save(str(output/'update-settings-failure.png')); failures.append(error)
        finally: dialog.reject()
    QTimer.singleShot(100, inspect_settings); app.settings_dialog()
    assert not failures, failures
    app.close(); pump(lambda:app.closed)
    updater.shutdown(); cached.shutdown()

print('Update UI: async checks, explicit consent, verified download state, cache, errors and scrollable settings passed')
