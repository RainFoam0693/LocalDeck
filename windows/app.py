"""LocalDeck for Windows 11: Qt desktop with native DWM window chrome."""
import concurrent.futures
import json
import os
from pathlib import Path
import queue
import sys
import threading
import webbrowser

if not getattr(sys, 'frozen', False): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QPushButton, QLineEdit, QListWidget, QListWidgetItem, QSplitter,
    QPlainTextEdit, QFileDialog, QMessageBox, QDialog, QFormLayout, QDialogButtonBox,
    QScrollArea, QSizePolicy, QTabBar, QComboBox, QCheckBox)
from windows.fluent import themed, appearance_icon, VERSION, AppearanceManager, AppearanceCapsule, setup_theme, apply_native_window, label, panel, MetricCard, ServiceDelegate, percent, memory
from windows.terminal import TerminalWorkspace
from windows.api_client import LocalAPIClient
from windows.updates import AppUpdater


class App(QMainWindow):
    def __init__(self, smoke=False, preview=False):
        super().__init__()
        self.smoke = smoke; self.preview = preview; self.closing = False; self.closed = False; self.confirming_quit = False
        self.data = {'services': [], 'listeners': []}; self.selected_log = None; self.sort_cpu = False
        self.results = queue.Queue(); self.pending = set(); self.errors = []
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self.setWindowTitle('LocalDeck'); self.resize(1320, 860); self.setMinimumSize(1050, 700)
        icon = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'assets/LocalDeck.ico'
        if icon.exists(): self.setWindowIcon(QIcon(str(icon)))
        if not preview:
            from backend import server
            self.api = server.make_server(); self.client = LocalAPIClient(self.api.server_port, self.api.token)
            threading.Thread(target=self.api.serve_forever, daemon=True).start()
        self.appearance = AppearanceManager(QApplication.instance(), persist=not preview)
        self.updater = AppUpdater(self, automatic=not preview and not smoke and "--terminal-smoke-test" not in sys.argv)
        self.build_ui()
        self.updater.changed.connect(self.update_update_banner)
        self.update_update_banner()
        self.appearance.changed.connect(self.theme_changed)
        self.poll_timer = QTimer(self); self.poll_timer.timeout.connect(self.poll); self.poll_timer.start(60)
        self.refresh_timer = QTimer(self); self.refresh_timer.timeout.connect(self.refresh); self.refresh_timer.start(4000)
        self.metric_timer = QTimer(self); self.metric_timer.timeout.connect(self.metrics_tick); self.metric_timer.start(2000)
        self.native_attributes = apply_native_window(self)
        if preview:
            from windows.preview import fixture
            self.render(fixture())
        else: self.refresh()

    def theme_changed(self, dark):
        self.native_attributes = apply_native_window(self)
        self.settings_button.setIcon(appearance_icon('settings', themed('#b0b0b0')))
        for session, view in self.terminals.sessions.values():
            view.version = -1
            close = self.terminals.tabs.tabBar().tabButton(self.terminals.tabs.indexOf(view), QTabBar.RightSide)
            if close: close.setIcon(appearance_icon('close', themed('#b0b0b0')))
        self.live_list.viewport().update(); self.task_list.viewport().update()

    def button(self, text, callback, name=None):
        widget = QPushButton(text)
        if name: widget.setObjectName(name)
        widget.clicked.connect(lambda checked=False:callback()); return widget

    def build_ui(self):
        root = QWidget(); self.setCentralWidget(root)
        layout = QHBoxLayout(root); layout.setContentsMargins(12, 12, 16, 12); layout.setSpacing(16)
        sidebar = QWidget(); sidebar.setObjectName('sidebar'); sidebar.setFixedWidth(210)
        nav = QVBoxLayout(sidebar); nav.setContentsMargins(6, 16, 6, 8); nav.setSpacing(6)
        brand = QHBoxLayout(); logo = label('◈'); logo.setStyleSheet('color: #76b9ed; font-size: 25px;'); brand.addWidget(logo); brand.addWidget(label('LocalDeck', 'brand')); brand.addStretch()
        nav.addLayout(brand); nav.addSpacing(26); nav.addWidget(label('工作空间', 'muted')); nav.addSpacing(6)
        self.nav_buttons = []
        for index, title in enumerate(['服务概览', '启动项', '终端工作区']):
            button = self.button(title, lambda i=index:self.select_page(i), 'nav'); button.setCheckable(True)
            button.setAccessibleName(title); nav.addWidget(button); self.nav_buttons.append(button)
        nav.addStretch(); self.appearance_capsule = AppearanceCapsule(self.appearance); nav.addWidget(self.appearance_capsule); nav.addSpacing(14); nav.addWidget(label('●  此 Windows PC', 'muted')); nav.addSpacing(8)
        nav.addWidget(label('LocalDeck '+VERSION, 'muted')); layout.addWidget(sidebar)
        content = QWidget(); content_layout = QVBoxLayout(content); content_layout.setContentsMargins(10, 12, 0, 0); content_layout.setSpacing(18)
        top = QHBoxLayout(); self.title_label = label('服务概览', 'heading'); top.addWidget(self.title_label); top.addStretch()
        self.settings_button = self.button('', self.settings_dialog)
        self.settings_button.setIcon(appearance_icon('settings', themed('#b0b0b0')))
        self.settings_button.setFixedSize(38, 38)
        self.settings_button.setStyleSheet('QPushButton { min-width: 0; padding: 0; border-radius: 19px; }')
        self.settings_button.setAccessibleName('设置'); self.settings_button.setToolTip('设置'); top.addWidget(self.settings_button)
        self.refresh_button = self.button('刷新', self.refresh); top.addWidget(self.refresh_button)
        top.addWidget(self.button('＋ 添加启动项', self.add_dialog, 'primary')); content_layout.addLayout(top)
        self.update_banner = panel(); update_layout = QHBoxLayout(self.update_banner)
        self.update_label = label(''); self.update_label.setWordWrap(True); update_layout.addWidget(self.update_label, 1)
        self.update_action = self.button('查看更新', lambda:self.updater.open_download() if self.updater.path else self.updater.confirm_download(self), 'primary')
        update_layout.addWidget(self.update_action); update_layout.addWidget(self.button('稍后', self.updater.dismiss))
        content_layout.addWidget(self.update_banner)
        caption = label('在一个工作空间，管理本机服务与终端。', 'muted'); content_layout.addWidget(caption)
        metrics = QHBoxLayout(); metrics.setSpacing(12); self.cards = []
        for title, color in [('系统 CPU', '#76b9ed'), ('物理内存', '#c0a4ed'), ('LocalDeck 自身', '#87d4bb')]:
            card = MetricCard(title, color); metrics.addWidget(card, 1); self.cards.append(card)
        content_layout.addLayout(metrics)
        self.tabs = QStackedWidget(); content_layout.addWidget(self.tabs, 1)
        self.build_live(); self.build_managed(); self.terminals = TerminalWorkspace(); self.tabs.addWidget(self.terminals)
        self.status = label('正在连接本机服务…', 'muted'); content_layout.addWidget(self.status)
        layout.addWidget(content, 1); self.select_page(0)

    def update_update_banner(self):
        updater = self.updater
        self.update_banner.setVisible(bool(updater.release) and not updater.dismissed)
        self.update_label.setText(('LocalDeck '+updater.release['version']+' 可用 · ' if updater.release else '') + ('查看更新说明，由你决定何时下载。' if updater.message.startswith('发现新版本') else updater.message))
        self.update_action.setText('打开下载位置' if updater.path else ('正在下载…' if updater.downloading else '查看更新'))
        self.update_action.setEnabled(not updater.busy)

    def settings_dialog(self):
        dialog = QDialog(self); dialog.setWindowTitle('设置')
        available = self.screen().availableGeometry()
        dialog.resize(min(620, max(320, available.width()-40)), min(760, max(400, available.height()-60)))
        outer = QVBoxLayout(dialog)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.NoFrame); scroll.setStyleSheet('QScrollArea { background: transparent; border: none; }')
        body = QWidget(); layout = QVBoxLayout(body); layout.setSpacing(16); scroll.setWidget(body); outer.addWidget(scroll, 1)
        layout.addWidget(label('设置', 'section'))
        layout.addWidget(label('软件更新', 'section'))
        update_status = label(self.updater.message); update_status.setWordWrap(True); layout.addWidget(update_status)
        checked = label('上次成功检查：'+self.updater.last_checked, 'muted'); layout.addWidget(checked)
        auto = QCheckBox('每周一、三、五自动检查更新'); auto.setChecked(self.updater.enabled); auto.toggled.connect(self.updater.set_enabled); layout.addWidget(auto)
        schedule_tip = label('应用运行时每天检查一次。只提示新版本，下载与替换由你确认。', 'muted'); schedule_tip.setWordWrap(True); layout.addWidget(schedule_tip)
        update_buttons = QHBoxLayout()
        check = self.button('检查更新', self.updater.check); update_buttons.addWidget(check)
        install = self.button('下载更新', lambda:self.updater.open_download() if self.updater.path else self.updater.confirm_download(dialog), 'primary'); update_buttons.addWidget(install)
        update_buttons.addWidget(self.button('GitHub 发行页', self.updater.open_releases)); layout.addLayout(update_buttons)
        def update_settings():
            auth_status.setText('已保存到 Windows 凭据管理器' if self.updater.authorized else '公开仓库无需授权；私有仓库需要只读令牌。')
            update_status.setText(self.updater.message); checked.setText('上次成功检查：'+self.updater.last_checked)
            check.setEnabled(not self.updater.busy); check.setText('正在检查…' if self.updater.busy and not self.updater.downloading else '检查更新')
            install.setVisible(bool(self.updater.release)); install.setEnabled(not self.updater.busy); install.setText('打开下载位置' if self.updater.path else '下载更新')
        layout.addWidget(label('私有仓库授权（可选）', 'section'))
        auth_status = label('', 'muted'); layout.addWidget(auth_status)
        token = QLineEdit(); token.setEchoMode(QLineEdit.Password); token.setPlaceholderText('私有仓库访问令牌（公开仓库可留空）'); layout.addWidget(token)
        auth_actions = QHBoxLayout()
        def save_auth(): self.updater.save_authorization(token.text()); token.clear()
        auth_actions.addWidget(self.button('保存授权', save_auth)); auth_actions.addWidget(self.button('移除授权', lambda:self.updater.save_authorization('')))
        auth_actions.addWidget(self.button('创建只读令牌', lambda:webbrowser.open('https://github.com/settings/personal-access-tokens/new'))); layout.addLayout(auth_actions)
        auth_tip = label('选择 LocalDeck 仓库，仅开启 Contents → Read-only。授权保存在 Windows 凭据管理器。', 'muted'); auth_tip.setWordWrap(True); layout.addWidget(auth_tip)
        self.updater.changed.connect(update_settings); update_settings()
        layout.addWidget(label('文件访问', 'section'))
        text = label('Windows 使用当前账户的文件访问权限，无需开启 macOS 的“完全磁盘访问”。受保护的系统目录和其他账户文件仍按系统权限管理。', 'muted')
        text.setWordWrap(True); layout.addWidget(text)
        form = QFormLayout()
        appearance = QComboBox(); appearance.addItems(['浅色', '深色', '跟随系统'])
        appearance.setCurrentIndex(['light','dark','system'].index(self.appearance.mode))
        appearance.currentIndexChanged.connect(lambda i:self.appearance.set_mode(['light','dark','system'][i])); form.addRow('外观', appearance)
        visible = QCheckBox('显示终端文件面板'); visible.setChecked(self.terminals.files_toggle.isChecked())
        visible.toggled.connect(self.terminals.files_toggle.setChecked); form.addRow(visible)
        hidden = QCheckBox('显示隐藏文件'); hidden.setChecked(self.terminals.files.hidden.isChecked())
        hidden.toggled.connect(self.terminals.files.hidden.setChecked); form.addRow(hidden)
        layout.addLayout(form)
        tip = label('向上翻阅日志时暂停跟随，回到底部自动恢复。收起文件面板不会结束会话。', 'muted'); tip.setWordWrap(True); layout.addWidget(tip)
        layout.addStretch(); layout.addWidget(label('关于', 'section'))
        layout.addWidget(label('LocalDeck '+VERSION, 'muted'))
        author = panel(); author_layout = QHBoxLayout(author); author_layout.setContentsMargins(16, 12, 16, 12)
        identity = QVBoxLayout(); identity.addWidget(label('RainFoam0693', 'section')); identity.addWidget(label('GitHub · 开发者主页', 'muted'))
        author_layout.addLayout(identity); author_layout.addStretch()
        author_layout.addWidget(self.button('访问主页', lambda:webbrowser.open('https://github.com/RainFoam0693')))
        layout.addWidget(author)
        done = QDialogButtonBox(QDialogButtonBox.Close); done.button(QDialogButtonBox.Close).setText('完成'); done.rejected.connect(dialog.reject); outer.addWidget(done)
        apply_native_window(dialog)
        try: dialog.exec()
        finally: self.updater.changed.disconnect(update_settings); dialog.deleteLater()

    def build_live(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(12)
        toolbar = QHBoxLayout(); toolbar.addWidget(label('运行中的服务', 'section')); self.stats = label('', 'muted'); toolbar.addWidget(self.stats); toolbar.addStretch()
        self.search = QLineEdit(); self.search.setPlaceholderText('搜索名称、PID 或端口'); self.search.setClearButtonEnabled(True); self.search.setMaximumWidth(250); self.search.textChanged.connect(self.render_listeners); toolbar.addWidget(self.search)
        self.sort_button = self.button('按 CPU 排序', self.toggle_sort); toolbar.addWidget(self.sort_button); layout.addLayout(toolbar)
        split = QSplitter(); split.setChildrenCollapsible(False); self.live_list = QListWidget(); self.live_list.setItemDelegate(ServiceDelegate(self.live_list)); self.live_list.setAccessibleName('运行中的服务'); self.live_list.currentItemChanged.connect(self.show_details); self.live_list.itemDoubleClicked.connect(lambda _:self.open_port()); split.addWidget(self.live_list)
        self.inspector = panel(); detail = QVBoxLayout(self.inspector); detail.setContentsMargins(20, 20, 20, 16); detail.setSpacing(14)
        detail.addWidget(label('服务详情', 'muted')); self.detail_name = label('选择一个服务', 'section'); self.detail_name.setWordWrap(True); detail.addWidget(self.detail_name)
        self.detail_pid = label('', 'muted'); detail.addWidget(self.detail_pid)
        usage = QHBoxLayout(); self.detail_cpu = label('CPU  —'); self.detail_memory = label('内存  —'); usage.addWidget(self.detail_cpu); usage.addWidget(self.detail_memory); detail.addLayout(usage)
        area = QScrollArea(); area.setWidgetResizable(True); area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); area.setFrameShape(QScrollArea.NoFrame); area.setStyleSheet('QScrollArea { background: transparent; border: none; }')
        info = QWidget(); info.setStyleSheet('background: transparent;'); fields = QVBoxLayout(info); fields.setContentsMargins(0, 8, 0, 0); fields.setSpacing(10)
        self.detail_ports = label('—'); self.detail_directory = label('—'); self.detail_command = label('—')
        for name, widget in [('监听端口', self.detail_ports), ('工作目录', self.detail_directory), ('启动命令', self.detail_command)]:
            fields.addWidget(label(name, 'muted')); widget.setWordWrap(True); widget.setMinimumWidth(0); widget.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred); widget.setTextInteractionFlags(Qt.TextSelectableByMouse); fields.addWidget(widget); fields.addSpacing(10)
        fields.addStretch(); area.setWidget(info); detail.addWidget(area, 1)
        detail.addWidget(self.button('复制启动命令', self.copy_command))
        actions = QHBoxLayout(); self.open_button = self.button('打开服务', self.open_port); self.dir_button = self.button('目录', self.open_directory)
        actions.addWidget(self.open_button); actions.addWidget(self.dir_button); detail.addLayout(actions)
        self.stop_button = self.button('停止进程…', self.stop_external, 'danger'); detail.addWidget(self.stop_button)
        self.inspector.setMinimumWidth(280); split.addWidget(self.inspector); split.setSizes([650, 300]); layout.addWidget(split, 1)
        self.tabs.addWidget(page)

    def build_managed(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(12)
        layout.addWidget(label('已保存的启动项', 'section'))
        split = QSplitter(); split.setChildrenCollapsible(False)
        left = QWidget(); left.setMinimumWidth(330); left_layout = QVBoxLayout(left); left_layout.setContentsMargins(0, 0, 0, 0)
        self.task_list = QListWidget(); self.task_list.setItemDelegate(ServiceDelegate(self.task_list)); self.task_list.setAccessibleName('已保存的启动项'); self.task_list.currentItemChanged.connect(self.select_log); left_layout.addWidget(self.task_list, 1)
        self.task_empty = label('还没有启动项\n点击右上角「添加启动项」开始。', 'muted'); self.task_empty.setAlignment(Qt.AlignCenter); left_layout.addWidget(self.task_empty)
        actions = QHBoxLayout(); self.task_buttons = []
        for title, verb in [('启动', 'start'), ('停止', 'stop'), ('重启', 'restart'), ('删除', 'delete')]:
            button = self.button(title, lambda v=verb:self.service_action(v)); actions.addWidget(button); self.task_buttons.append(button)
        left_layout.addLayout(actions); split.addWidget(left)
        right = panel(); right_layout = QVBoxLayout(right); right_layout.setContentsMargins(16, 14, 16, 16)
        heading = QHBoxLayout(); heading.addWidget(label('实时日志', 'section')); heading.addStretch(); heading.addWidget(label('最近 100 KB', 'muted')); right_layout.addLayout(heading)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setPlaceholderText('选择一个启动项，查看运行日志。'); self.log.setLineWrapMode(QPlainTextEdit.NoWrap); self.log.setStyleSheet('font-family: "Cascadia Mono", "Consolas", "Menlo", monospace; font-size: 13px;'); right_layout.addWidget(self.log)
        split.addWidget(right); split.setSizes([380, 600]); layout.addWidget(split, 1); self.tabs.addWidget(page)

    def select_page(self, index):
        self.tabs.setCurrentIndex(index); self.title_label.setText(['服务概览', '启动项', '终端工作区'][index])
        for i, button in enumerate(self.nav_buttons): button.setChecked(i == index)

    def toggle_sort(self):
        self.sort_cpu = not self.sort_cpu; self.sort_button.setText('默认顺序' if self.sort_cpu else '按 CPU 排序'); self.render_listeners()

    def request(self, path, body=None):
        return self.client.request(path, body)

    def submit(self, operation, callback, key='action'):
        if self.closing or self.preview or key in self.pending: return
        self.pending.add(key)
        def work():
            try: self.results.put((key, callback, operation(), None))
            except Exception as error: self.results.put((key, callback, None, str(error)))
        self.executor.submit(work)

    def poll(self):
        try:
            while True:
                key, callback, data, error = self.results.get_nowait()
                if key == 'closed':
                    self.closed = True
                    if error: self.errors.append(error)
                    self.close(); return
                self.pending.discard(key)
                if error:
                    self.errors.append(error); self.status.setText('操作失败：'+error)
                    if self.smoke: QApplication.exit(1)
                elif not self.closing: callback(data)
        except queue.Empty: pass

    def refresh(self):
        selected = self.selected_log
        def fetch():
            data = self.request('/state')
            if selected and any(item['id'] == selected for item in data['services']): data['log'] = (selected, self.request('/logs/'+selected)['text'])
            return data
        self.submit(fetch, self.render, 'state')

    def metrics_tick(self): self.submit(lambda:self.request('/metrics'), self.update_metrics, 'metrics')

    def update_metrics(self, data):
        data = data or {}; system = data.get('system', {}); app = data.get('app', {}); history = data.get('history', [])
        self.cards[0].update_value(system.get('cpuPercent'), f"{data.get('cpuCores', 0)} 个逻辑核心 · 整机容量", [p['cpu'] for p in history if p.get('cpu') is not None])
        self.cards[1].update_value(system.get('memoryPercent'), memory(system.get('memoryBytes'))+' / '+memory(system.get('memoryTotal')), [p['memory'] for p in history if p.get('memory') is not None])
        self.cards[2].update_value(app.get('cpuPercent'), '内存 '+memory(app.get('memoryBytes'))+' · '+percent(app.get('memoryPercent')), [])

    @staticmethod
    def selected_key(widget):
        item = widget.currentItem(); return item.data(Qt.UserRole) if item else None

    def populate(self, widget, rows):
        selected = self.selected_key(widget); scroll = widget.verticalScrollBar().value()
        widget.blockSignals(True); widget.clear()
        for key, title, caption, usage in rows:
            text = title+'\n'+caption+'\nCPU  '+percent((usage or {}).get('cpuPercent'))+'     内存  '+memory((usage or {}).get('memoryBytes'))
            item = QListWidgetItem(text); item.setData(Qt.UserRole, key); item.setData(Qt.UserRole+1, dict(title=title, caption=caption, usage=usage)); item.setToolTip(caption); item.setSizeHint(QSize(150, 80)); widget.addItem(item)
            if key == selected: widget.setCurrentItem(item)
        if widget.currentRow() < 0 and widget.count(): widget.setCurrentRow(0)
        widget.blockSignals(False); widget.verticalScrollBar().setValue(scroll)

    def render(self, data):
        self.data = data; self.update_metrics(data.get('performance')); self.render_listeners()
        self.populate(self.task_list, [(i['id'], i['name']+('  ·  运行中' if i['running'] else '  ·  已停止'), i['command'], i.get('usage')) for i in data['services']])
        self.task_empty.setVisible(not data['services']); self.task_list.setVisible(bool(data['services']))
        for button in self.task_buttons: button.setEnabled(bool(data['services']))
        self.select_log()
        if 'log' in data and data['log'][0] == self.selected_log: self.set_log(data['log'][1])
        ports = {port for item in data['listeners'] for port in item['ports']}
        self.stats.setText(f"{len(data['listeners'])} 个进程 · {len(ports)} 个端口")
        self.status.setText('● 本机已连接   ·   性能每 2 秒采样   ·   CPU 按整机容量计算')
        if self.smoke and (data.get('performance') or {}).get('system', {}).get('cpuPercent') is not None:
            from backend import server
            (server.ROOT/'smoke-result.json').write_text(json.dumps({'ok':True, 'listeners':len(data['listeners']), 'metrics':True, 'ui':'Qt Fluent', 'native':self.native_attributes}), encoding='utf-8')
            QTimer.singleShot(300, self.close)

    def render_listeners(self, *_):
        query = self.search.text().casefold(); rows = [i for i in self.data['listeners'] if query in str(i).casefold()]
        if self.sort_cpu: rows.sort(key=lambda i:(i.get('usage') or {}).get('cpuPercent') or 0, reverse=True)
        self.populate(self.live_list, [(str(i['pid']), i['name'], 'PID '+str(i['pid'])+'  ·  '+', '.join(':'+str(p) for p in i['ports']), i.get('usage')) for i in rows]); self.show_details()

    def selected_listener(self):
        key = self.selected_key(self.live_list)
        return next((i for i in self.data['listeners'] if str(i['pid']) == key), None)

    def show_details(self, *_):
        item = self.selected_listener() or {}; usage = item.get('usage') or {}
        self.detail_name.setText(item.get('name', '未找到匹配的服务')); self.detail_pid.setText('PID '+str(item['pid']) if item else '调整搜索条件后重试。')
        self.detail_cpu.setText('CPU  '+percent(usage.get('cpuPercent'))); self.detail_memory.setText('内存  '+memory(usage.get('memoryBytes')))
        self.detail_ports.setText('  '.join(':'+str(p) for p in item.get('ports', [])) or '—')
        self.detail_directory.setText(item.get('directory') or '无法读取此进程目录'); self.detail_command.setText(item.get('command') or '无法读取启动命令')
        self.open_button.setEnabled(bool(item.get('ports'))); self.dir_button.setEnabled(bool(item.get('directory'))); self.stop_button.setEnabled(bool(item.get('command')))

    def copy_command(self):
        item = self.selected_listener()
        if item and item.get('command'): QApplication.clipboard().setText(item['command'])
    def open_port(self):
        item = self.selected_listener()
        if item and item['ports']: webbrowser.open('http://localhost:'+str(item['ports'][0]))
    def open_directory(self):
        item = self.selected_listener()
        if item and item.get('directory'):
            try: os.startfile(item['directory'])
            except OSError as error: QMessageBox.warning(self, '无法打开目录', str(error))
    def stop_external(self):
        item = self.selected_listener()
        if not item or not item.get('command'): return
        if QMessageBox.question(self, '停止进程', f"停止 {item['name']}（PID {item['pid']}）？\n请先保存该进程中的工作。") == QMessageBox.Yes:
            self.submit(lambda:self.request('/processes/stop', {'pid':item['pid'], 'command':item['command']}), lambda _:self.refresh())
    def set_log(self, text):
        bar = self.log.verticalScrollBar(); bottom = bar.value() >= bar.maximum()-3; old = bar.value()
        if self.log.toPlainText() == text: return
        self.log.setPlainText(text); bar.setValue(bar.maximum() if bottom else old)
    def select_log(self, *_):
        key = self.selected_key(self.task_list)
        if key != self.selected_log:
            self.selected_log = key; self.set_log('正在读取日志…' if key else '')
            if key: QTimer.singleShot(0, self.refresh)
    def service_action(self, verb):
        key = self.selected_key(self.task_list)
        if not key: return
        if verb == 'delete' and QMessageBox.question(self, '删除启动项', '停止并删除此启动项？') != QMessageBox.Yes: return
        self.submit(lambda:self.request('/services/'+key+'/'+verb, {}), lambda _:self.refresh())

    def add_dialog(self):
        dialog = QDialog(self); dialog.setWindowTitle('添加启动项'); dialog.setMinimumWidth(560)
        layout = QVBoxLayout(dialog); layout.setContentsMargins(24, 24, 24, 24); layout.setSpacing(18); layout.addWidget(label('添加启动项', 'section'))
        form = QFormLayout(); form.setSpacing(12); name = QLineEdit(); name.setPlaceholderText('例如：前端开发服务'); command = QLineEdit(); command.setPlaceholderText('例如：npm run dev'); directory = QLineEdit(str(Path.home()))
        form.addRow('名称', name); form.addRow('启动命令', command); form.addRow('工作目录', directory); layout.addLayout(form)
        def choose():
            value = QFileDialog.getExistingDirectory(dialog, '工作目录', directory.text())
            if value: directory.setText(value)
        layout.addWidget(self.button('选择目录', choose)); layout.addWidget(label('命令通过 cmd.exe 执行，使用当前用户的 PATH。', 'muted'))
        actions = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel); actions.button(QDialogButtonBox.Save).setText('保存'); actions.button(QDialogButtonBox.Save).setObjectName('primary'); actions.button(QDialogButtonBox.Cancel).setText('取消'); actions.rejected.connect(dialog.reject)
        def save():
            body = {'name':name.text().strip(), 'command':command.text().strip(), 'directory':directory.text().strip()}
            if not all(body.values()) or not Path(body['directory']).is_dir(): QMessageBox.warning(dialog, '请检查输入', '请填写名称、命令和有效目录。'); return
            dialog.accept(); self.select_page(1); self.submit(lambda:self.request('/services', body), lambda _:self.refresh())
        actions.accepted.connect(save); layout.addWidget(actions); apply_native_window(dialog); dialog.exec()

    def confirm_terminal_exit(self, active):
        dialog = QMessageBox(self); dialog.setWindowTitle('退出 LocalDeck'); dialog.setIcon(QMessageBox.Warning)
        dialog.setText(f'仍有 {len(active)} 个终端正在运行任务')
        dialog.setInformativeText('退出会结束这些终端中的任务。是否仍要退出？')
        cancel = dialog.addButton('取消', QMessageBox.RejectRole)
        stop = dialog.addButton('结束任务并退出', QMessageBox.DestructiveRole)
        dialog.setDefaultButton(cancel); dialog.setEscapeButton(cancel)
        dialog.exec()
        return dialog.clickedButton() is stop

    def closeEvent(self, event):
        if self.closed: event.accept(); return
        event.ignore()
        if self.closing or self.confirming_quit: return
        active = self.terminals.active_sessions()
        if active:
            self.confirming_quit = True
            try: confirmed = self.confirm_terminal_exit(active)
            finally: self.confirming_quit = False
            if not confirmed: return
        self.updater.shutdown()
        self.closing = True; self.terminals.closing = True; self.centralWidget().setEnabled(False); self.status.setText('正在停止托管任务与终端…'); self.refresh_timer.stop(); self.metric_timer.stop(); self.terminals.timer.stop()
        def shutdown():
            error = None
            try:
                # Let active API operations finish before stopping managed tasks.
                self.executor.shutdown(wait=True, cancel_futures=True); self.terminals.shutdown()
                if not self.preview:
                    from backend import server
                    server.stop_all(); self.api.shutdown(); self.api.server_close()
            except Exception as exc: error = str(exc)
            self.results.put(('closed', None, None, error))
        threading.Thread(target=shutdown, daemon=True).start()


def main():
    preview = '--preview' in sys.argv; smoke = '--smoke-test' in sys.argv; terminal_smoke = '--terminal-smoke-test' in sys.argv
    qt = QApplication(sys.argv); qt.setApplicationName('LocalDeck'); setup_theme(qt)
    if not preview and (sys.platform != 'win32' or sys.getwindowsversion().build < 22000):
        QMessageBox.critical(None, '需要 Windows 11', 'LocalDeck Windows 版需要 Windows 11 x64（内部版本 22000 或更新）。'); return 1
    app = App(smoke=smoke, preview=preview); app.show()
    if terminal_smoke:
        from windows.terminal_smoke import run
        from backend import server
        result = run(app); (server.ROOT/'terminal-smoke-result.json').write_text(json.dumps(result), encoding='utf-8'); return 0
    if smoke: QTimer.singleShot(45000, lambda:qt.exit(1))
    return qt.exec()


if __name__ == '__main__': sys.exit(main())
