"""LocalDeck Windows desktop. Tk/Tcl and Python are bundled in the release EXE."""
import concurrent.futures
import json
import os
from pathlib import Path
import queue
import secrets
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import urllib.request
import urllib.error
import webbrowser

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import server
from windows.terminal import TerminalWorkspace

BG = '#10151e'
PANEL = '#1b2432'
TEXT = '#e7edf6'
MUTED = '#9aaabd'
ACCENT = '#34dfbd'


class App(tk.Tk):
    def __init__(self, smoke=False):
        super().__init__()
        self.title('LocalDeck · Windows')
        self.geometry('1180x780'); self.minsize(960, 640)
        self.configure(bg=BG)
        self.smoke = smoke
        self.closing = False
        self.busy = False
        self.selected_log = None
        self.data = {'services': [], 'listeners': []}
        self.results = queue.Queue()
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.api = server.make_server()
        threading.Thread(target=self.api.serve_forever, daemon=True).start()
        self.base = 'http://127.0.0.1:' + str(self.api.server_port)
        self.search = tk.StringVar()
        self.search.trace_add('write', lambda *_: self.render_listeners())
        icon = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'assets/LocalDeck.ico'
        if icon.exists(): self.iconbitmap(str(icon))
        self.build_ui()
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(80, self.poll)
        self.refresh()
        self.after(4000, self.tick)

    def build_ui(self):
        style = ttk.Style(self); style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10), background=BG, foreground=TEXT)
        style.configure('TFrame', background=BG)
        style.configure('TLabel', background=BG, foreground=TEXT)
        style.configure('Muted.TLabel', foreground=MUTED)
        style.configure('Title.TLabel', font=('Segoe UI', 26, 'bold'))
        style.configure('TButton', background=PANEL, foreground=TEXT, padding=(14, 9), borderwidth=0)
        style.map('TButton', background=[('active', '#2b3c50'), ('disabled', '#19202b')], foreground=[('disabled', MUTED)])
        style.configure('Accent.TButton', background=ACCENT, foreground='#0c2420')
        style.map('Accent.TButton', background=[('active', '#73efdb')])
        style.configure('Treeview', background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=38, borderwidth=0)
        style.configure('Treeview.Heading', background='#243144', foreground=MUTED, padding=10)
        style.map('Treeview', background=[('selected', '#20594f')])
        style.configure('TNotebook', background=BG, borderwidth=0)
        style.configure('TNotebook.Tab', background=PANEL, foreground=MUTED, padding=(20, 12))
        style.map('TNotebook.Tab', background=[('selected', '#20594f')], foreground=[('selected', TEXT)])
        style.configure('TEntry', fieldbackground=PANEL, foreground=TEXT, insertcolor=TEXT, padding=8)
        outer = ttk.Frame(self, padding=26); outer.pack(fill='both', expand=True)
        heading = ttk.Frame(outer); heading.pack(fill='x')
        ttk.Label(heading, text='LocalDeck', style='Title.TLabel').pack(side='left')
        ttk.Button(heading, text='＋ 添加启动项', style='Accent.TButton', command=self.add_dialog).pack(side='right')
        self.refresh_button = ttk.Button(heading, text='刷新', command=self.refresh); self.refresh_button.pack(side='right', padx=10)
        ttk.Label(outer, text='本机开发工作台 · API、前端服务与终端任务', style='Muted.TLabel').pack(anchor='w', pady=(5, 20))
        self.stats = ttk.Label(outer, text='正在连接本机 API…', font=('Segoe UI', 13, 'bold'))
        self.stats.pack(fill='x', pady=(0, 20))
        self.tabs = ttk.Notebook(outer); self.tabs.pack(fill='both', expand=True)
        live = ttk.Frame(self.tabs, padding=(0, 16)); managed = ttk.Frame(self.tabs, padding=(0, 16))
        self.tabs.add(live, text='运行中的服务'); self.tabs.add(managed, text='我的启动项 / 日志')
        self.terminals = TerminalWorkspace(self.tabs)
        self.tabs.add(self.terminals, text='应用内终端')
        ttk.Entry(live, textvariable=self.search).pack(fill='x', pady=(0, 12))
        self.live_tree = self.tree(live, [('name', '进程', 155), ('pid', 'PID', 75), ('ports', '端口', 130), ('command', '命令', 480)])
        self.live_tree.bind('<<TreeviewSelect>>', self.show_directory)
        self.live_tree.bind('<Double-1>', lambda _: self.open_port())
        self.directory_text = ttk.Label(live, text='选择进程查看目录；双击可打开首个端口。', style='Muted.TLabel', wraplength=950)
        self.directory_text.pack(anchor='w', pady=12)
        actions = ttk.Frame(live); actions.pack(fill='x')
        ttk.Button(actions, text='浏览器打开', command=self.open_port).pack(side='left')
        ttk.Button(actions, text='打开目录', command=self.open_directory).pack(side='left', padx=8)
        ttk.Button(actions, text='停止进程…', command=self.stop_external).pack(side='right')
        panes = ttk.Panedwindow(managed, orient='vertical'); panes.pack(fill='both', expand=True)
        task_panel = ttk.Frame(panes); log_panel = ttk.Frame(panes)
        panes.add(task_panel, weight=1); panes.add(log_panel, weight=1)
        self.task_tree = self.tree(task_panel, [('name', '启动项', 160), ('state', '状态', 90), ('command', '命令', 480)])
        self.task_tree.bind('<<TreeviewSelect>>', self.select_log)
        task_actions = ttk.Frame(task_panel); task_actions.pack(fill='x', pady=10)
        for text, verb in [('启动', 'start'), ('停止', 'stop'), ('重启', 'restart'), ('删除…', 'delete')]:
            ttk.Button(task_actions, text=text, command=lambda v=verb: self.service_action(v)).pack(side='left', padx=(0, 8))
        ttk.Label(log_panel, text='终端输出 · 最近 100 KB', style='Muted.TLabel').pack(anchor='w', pady=8)
        self.log = tk.Text(log_panel, bg='#090e16', fg=TEXT, insertbackground=TEXT, font=('Consolas', 10), wrap='none', relief='flat', height=9, padx=14, pady=12, state='disabled')
        scrollbar = ttk.Scrollbar(log_panel, command=self.log.yview); scrollbar.pack(side='right', fill='y')
        self.log.configure(yscrollcommand=scrollbar.set); self.log.pack(fill='both', expand=True)
        self.status = ttk.Label(outer, text='每 4 秒刷新 · 退出会停止本应用启动的任务 · 应用内终端支持独立多标签', style='Muted.TLabel')
        self.status.pack(anchor='w', pady=(15, 0))

    def tree(self, parent, columns):
        frame = ttk.Frame(parent); frame.pack(fill='both', expand=True)
        tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show='headings', selectmode='browse', height=7)
        for key, label, width in columns:
            tree.heading(key, text=label); tree.column(key, width=width, minwidth=65, stretch=key == 'command')
        vertical = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        frame.columnconfigure(0, weight=1); frame.rowconfigure(0, weight=1)
        tree.grid(row=0, column=0, sticky='nsew'); vertical.grid(row=0, column=1, sticky='ns'); horizontal.grid(row=1, column=0, sticky='ew')
        return tree

    def request(self, path, body=None):
        request = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None,
                                        headers={'Authorization': 'Bearer ' + self.api.token, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response: return json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError(json.load(error).get('error', str(error))) from error

    def submit(self, operation, success):
        if self.closing or self.busy: return
        self.busy = True
        self.refresh_button.configure(state='disabled')
        def work():
            try: self.results.put((success, operation(), None))
            except Exception as error: self.results.put((success, None, str(error)))
        self.executor.submit(work)

    def poll(self):
        if self.closing: return
        try:
            success, data, error = self.results.get_nowait()
            self.busy = False; self.refresh_button.configure(state='normal')
            if error:
                self.status.configure(text='操作失败：' + error)
                if self.smoke: raise RuntimeError(error)
            else: success(data)
        except queue.Empty: pass
        self.after(80, self.poll)

    def tick(self):
        if not self.closing:
            self.refresh(); self.after(4000, self.tick)

    def refresh(self):
        selected = self.selected_log
        def fetch():
            data = self.request('/state')
            if selected and any(item['id'] == selected for item in data['services']):
                data['log'] = self.request('/logs/' + selected)['text']
            return data
        self.submit(fetch, self.render)

    @staticmethod
    def replace_rows(tree, rows):
        selection = tree.selection()
        selected = selection[0] if selection else None
        for key in tree.get_children():
            if key not in rows: tree.delete(key)
        for key, values in rows.items():
            if tree.exists(key): tree.item(key, values=values)
            else: tree.insert('', 'end', iid=key, values=values)
        if selected in rows: tree.selection_set(selected)

    def render(self, data):
        self.data = data
        self.render_listeners()
        self.replace_rows(self.task_tree, {item['id']: (item['name'], '运行中' if item['running'] else '已停止', item['command']) for item in data['services']})
        ports = {port for item in data['listeners'] for port in item['ports']}
        running = sum(item['running'] for item in data['services'])
        self.stats.configure(text=f"监听进程  {len(data['listeners'])}     ·     开放端口  {len(ports)}     ·     托管任务  {running} / {len(data['services'])}")
        self.status.configure(text='本机 API 已连接 · 每 4 秒刷新 · 退出会停止本应用启动的任务')
        if 'log' in data: self.set_log(data['log'])
        if self.smoke:
            (server.ROOT / 'smoke-result.json').write_text(json.dumps({'ok': True, 'listeners': len(data['listeners']), 'api': self.base}), encoding='utf-8')
            self.after(300, self.close)

    def render_listeners(self):
        query = self.search.get().casefold()
        self.replace_rows(self.live_tree, {str(item['pid']): (item['name'], item['pid'], ', '.join(map(str, item['ports'])), item['command'] or '无权限读取') for item in self.data['listeners'] if query in str(item).casefold()})

    def selected_listener(self):
        selected = self.live_tree.selection()
        return next((item for item in self.data['listeners'] if selected and str(item['pid']) == selected[0]), None)

    def show_directory(self, _=None):
        item = self.selected_listener()
        self.directory_text.configure(text=(item['directory'] or '无法读取此进程的工作目录') if item else '选择进程查看目录。')

    def open_port(self):
        item = self.selected_listener()
        if item and item['ports']: webbrowser.open('http://localhost:' + str(item['ports'][0]))

    def open_directory(self):
        item = self.selected_listener()
        if item and item['directory']:
            try: os.startfile(item['directory'])
            except OSError as error: messagebox.showerror('无法打开目录', str(error), parent=self)

    def stop_external(self):
        if self.busy: return
        item = self.selected_listener()
        if not item: return
        if not item['command']:
            messagebox.showinfo('无法停止', '此进程无权读取，不能安全确认身份。', parent=self); return
        if messagebox.askyesno('停止进程', f"停止 {item['name']}（PID {item['pid']}）？\n未保存的工作可能丢失。", parent=self):
            self.submit(lambda: self.request('/processes/stop', {'pid': item['pid'], 'command': item['command']}), lambda _: self.refresh())

    def set_log(self, text):
        bottom = self.log.yview()[1] >= 0.99
        self.log.configure(state='normal'); self.log.delete('1.0', 'end'); self.log.insert('1.0', text); self.log.configure(state='disabled')
        if bottom: self.log.see('end')

    def select_log(self, _=None):
        selection = self.task_tree.selection()
        key = selection[0] if selection else None
        if key != self.selected_log:
            self.selected_log = key
            self.set_log('正在读取日志…' if key else '选择启动项查看日志。')
            if key: self.refresh()

    def service_action(self, verb):
        if self.busy: return
        selected = self.task_tree.selection()
        if not selected: return
        if verb == 'delete' and not messagebox.askyesno('删除启动项', '停止并删除此启动项？', parent=self): return
        key = selected[0]
        if verb == 'delete': self.selected_log = None; self.set_log('选择启动项查看日志。')
        self.submit(lambda: self.request('/services/' + key + '/' + verb, {}), lambda _: self.refresh())

    def add_dialog(self):
        if self.busy: return
        dialog = tk.Toplevel(self); dialog.title('添加启动项'); dialog.configure(bg=BG); dialog.geometry('600x350'); dialog.transient(self); dialog.grab_set()
        frame = ttk.Frame(dialog, padding=24); frame.pack(fill='both', expand=True)
        values = [tk.StringVar(), tk.StringVar(), tk.StringVar(value=str(Path.home()))]
        for text, value in zip(['名称', '命令（通过 cmd.exe 执行，例如 npm run dev）', '工作目录'], values):
            ttk.Label(frame, text=text).pack(anchor='w', pady=(8, 4)); ttk.Entry(frame, textvariable=value).pack(fill='x')
        def choose():
            directory = filedialog.askdirectory(parent=dialog)
            if directory: values[2].set(directory)
        ttk.Button(frame, text='选择目录…', command=choose).pack(anchor='w', pady=8)
        def save():
            body = dict(zip(['name', 'command', 'directory'], [value.get().strip() for value in values]))
            if not all(body.values()) or not Path(body['directory']).is_dir():
                messagebox.showerror('请检查输入', '请填写名称、命令和有效目录。', parent=dialog); return
            dialog.destroy(); self.tabs.select(1)
            self.submit(lambda: self.request('/services', body), lambda _: self.refresh())
        ttk.Button(frame, text='保存', style='Accent.TButton', command=save).pack(anchor='e')

    def close(self):
        if self.closing: return
        self.closing = True
        self.status.configure(text='正在停止托管任务…')
        self.executor.shutdown(wait=False, cancel_futures=True)
        def shutdown():
            try:
                self.terminals.shutdown(); server.stop_all(); self.api.shutdown(); self.api.server_close()
                self.results.put(('closed', None, None))
            except Exception as error: self.results.put(('closed', None, str(error)))
        threading.Thread(target=shutdown, daemon=True).start()
        self.after(100, self.finish_close)

    def finish_close(self):
        try:
            while True:
                kind, _, error = self.results.get_nowait()
                if kind == 'closed':
                    if error and not self.smoke: messagebox.showerror('停止任务失败', error, parent=self)
                    self.destroy(); return
        except queue.Empty: self.after(100, self.finish_close)


if __name__ == '__main__':
    smoke = '--smoke-test' in sys.argv
    terminal_smoke = '--terminal-smoke-test' in sys.argv
    try:
        application = App(smoke=smoke)
        if smoke:
            def fail_timeout():
                application.destroy(); os._exit(2)
            application.after(30000, fail_timeout)
        if terminal_smoke:
            from windows.terminal_smoke import run
            result = run(application)
            (server.ROOT / 'terminal-smoke-result.json').write_text(json.dumps(result), encoding='utf-8')
        else:
            application.mainloop()
    except Exception as error:
        if not smoke and not terminal_smoke: messagebox.showerror('LocalDeck 无法启动', str(error))
        raise
