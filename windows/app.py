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
from windows.dashboard import *

BG = '#0e1017'
PANEL = '#161b25'
TEXT = '#e7edf6'
MUTED = '#7b879f'
ACCENT = '#a094fa'


class App(tk.Tk):
    def __init__(self, smoke=False):
        super().__init__()
        self.title('LocalDeck · Windows')
        self.geometry('1310x850'); self.minsize(1160, 760)
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
        style.configure('TButton', background='#252b3a', foreground=TEXT, padding=(15, 10), borderwidth=0, relief='flat')
        style.map('TButton', background=[('active', '#343c51'), ('disabled', '#19202b')], foreground=[('disabled', MUTED)])
        style.configure('Accent.TButton', background=ACCENT, foreground='#141324')
        style.map('Accent.TButton', background=[('active', '#b6adff')])
        style.configure('TEntry', fieldbackground=PANEL, foreground=TEXT, insertcolor=TEXT, padding=10, borderwidth=0)
        style.configure('TNotebook', background=BG, borderwidth=0)
        style.configure('TNotebook.Tab', background=PANEL, foreground=MUTED, padding=(17, 11))
        style.map('TNotebook.Tab', background=[('selected', '#2c2a46')], foreground=[('selected', TEXT)])
        style.layout('Pages.TNotebook.Tab', [])
        style.configure('Vertical.TScrollbar', background='#293245', troughcolor=BG, borderwidth=0, arrowsize=8)
        sidebar = tk.Frame(self, bg=SIDEBAR, width=206); sidebar.pack(side='left', fill='y'); sidebar.pack_propagate(False)
        brand = tk.Frame(sidebar, bg=SIDEBAR); brand.pack(fill='x', padx=22, pady=(40, 3))
        tk.Label(brand, text='◈', bg=SIDEBAR, fg=MINT, font=('Segoe UI', 26)).pack(side='left', padx=(0,9))
        tk.Label(brand, text='LocalDeck', bg=SIDEBAR, fg=TEXT, font=('Segoe UI', 17, 'bold')).pack(side='left')
        tk.Label(sidebar, text='D E V E L O P E R  S P A C E', bg=SIDEBAR, fg=MUTED, font=('Segoe UI',7)).pack(anchor='w', padx=27)
        tk.Label(sidebar, text='工作空间', bg=SIDEBAR, fg=MUTED, font=('Segoe UI',9)).pack(anchor='w', padx=30, pady=(38,13))
        self.nav_buttons = []
        for index, title in enumerate(['▦   服务概览', '▷   启动项', '›_   终端工作区']):
            button = tk.Button(sidebar, text=title, font=('Segoe UI',11), anchor='w', bg=SIDEBAR, fg=MUTED, activebackground='#29263f', activeforeground=TEXT, relief='flat', bd=0, padx=16, pady=13, cursor='hand2', command=lambda i=index:self.tabs.select(i))
            button.pack(fill='x', padx=16, pady=3); self.nav_buttons.append(button)
        tk.Label(sidebar, text='LOCALDECK  /  0.4.0', bg=SIDEBAR, fg=MUTED, font=('Consolas',8)).pack(side='bottom', anchor='w', padx=25, pady=25)
        tk.Label(sidebar, text='●  此 Windows PC\n\n服务、性能和终端\n都在一个工作空间。', justify='left', bg=SIDEBAR, fg=MUTED, font=('Segoe UI',10)).pack(side='bottom', anchor='w', padx=27, pady=15)
        outer = ttk.Frame(self, padding=(28,28,28,0)); outer.pack(fill='both', expand=True)
        heading = ttk.Frame(outer); heading.pack(fill='x')
        titles = ttk.Frame(heading); titles.pack(side='left')
        self.breadcrumb = ttk.Label(titles, text='工作空间  /  服务概览', style='Muted.TLabel', font=('Segoe UI',9)); self.breadcrumb.pack(anchor='w')
        self.page_title = ttk.Label(titles, text='服务概览', font=('Segoe UI',23,'bold')); self.page_title.pack(anchor='w', pady=(8,0))
        ttk.Button(heading,text='＋ 添加启动项',style='Accent.TButton',command=self.add_dialog).pack(side='right')
        self.refresh_button=ttk.Button(heading,text='↻',command=self.refresh);self.refresh_button.pack(side='right',padx=10)
        self.performance = PerformanceStrip(outer); self.performance.pack(fill='x', pady=(24,22))
        self.tabs = ttk.Notebook(outer, style='Pages.TNotebook'); self.tabs.pack(fill='both',expand=True)
        live = ttk.Frame(self.tabs); managed = ttk.Frame(self.tabs)
        self.tabs.add(live,text='服务概览'); self.tabs.add(managed,text='启动项')
        self.terminals = TerminalWorkspace(self.tabs); self.tabs.add(self.terminals,text='终端工作区')
        self.tabs.bind('<<NotebookTabChanged>>', self.page_changed)
        toolbar=ttk.Frame(live);toolbar.pack(fill='x',pady=(0,14))
        ttk.Label(toolbar,text='运行中的服务',font=('Segoe UI',12,'bold')).pack(side='left')
        self.stats=ttk.Label(toolbar,text='正在扫描…',style='Muted.TLabel',font=('Segoe UI',9));self.stats.pack(side='left',padx=12)
        self.sort_cpu = False
        ttk.Button(toolbar,text='CPU 排序',command=self.toggle_sort).pack(side='right')
        ttk.Entry(toolbar,textvariable=self.search,width=28).pack(side='right',padx=10)
        body=ttk.Frame(live);body.pack(fill='both',expand=True)
        detail=ttk.Frame(body);detail.pack(side='right',fill='y',padx=(16,0))
        self.inspector=Inspector(detail)
        detail_actions=ttk.Frame(detail);detail_actions.pack(side='bottom',fill='x',pady=10)
        ttk.Button(detail_actions,text='打开服务',command=self.open_port).pack(side='left')
        ttk.Button(detail_actions,text='目录',command=self.open_directory).pack(side='left',padx=7)
        ttk.Button(detail_actions,text='停止…',command=self.stop_external).pack(side='right')
        self.inspector.pack(fill='both',expand=True)
        self.live_tree=self.tree(body,[('name','进程',155),('pid','PID',75),('ports','端口',130),('command','命令',480)])
        self.live_tree.bind('<<TreeviewSelect>>',self.show_directory);self.live_tree.bind('<Double-1>',lambda _:self.open_port())
        self.directory_text=ttk.Label(live,text='',style='Muted.TLabel')
        task_left=ttk.Frame(managed,width=360);task_left.pack(side='left',fill='both',padx=(0,18));task_left.pack_propagate(False)
        ttk.Label(task_left,text='已保存的启动项',font=('Segoe UI',12,'bold')).pack(anchor='w',pady=(0,14))
        self.task_tree=self.tree(task_left,[('name','启动项',160),('state','状态',90),('command','命令',480)])
        self.task_tree.bind('<<TreeviewSelect>>',self.select_log)
        task_actions=ttk.Frame(task_left);task_actions.pack(fill='x',pady=12)
        for text,verb in [('启动','start'),('停止','stop'),('重启','restart'),('删除…','delete')]:
            ttk.Button(task_actions,text=text,command=lambda v=verb:self.service_action(v)).pack(side='left',padx=(0,6))
        log_panel=ttk.Frame(managed);log_panel.pack(fill='both',expand=True)
        log_heading=ttk.Frame(log_panel);log_heading.pack(fill='x',pady=(0,14))
        ttk.Label(log_heading,text='›_  实时日志',font=('Segoe UI',12,'bold')).pack(side='left')
        ttk.Label(log_heading,text='最近 100 KB',style='Muted.TLabel',font=('Segoe UI',9)).pack(side='right')
        self.log=tk.Text(log_panel,bg=CONSOLE,fg=TEXT,insertbackground=TEXT,font=('Consolas',10),wrap='none',relief='flat',height=9,padx=18,pady=18,state='disabled')
        scrollbar=ttk.Scrollbar(log_panel,command=self.log.yview);scrollbar.pack(side='right',fill='y');self.log.configure(yscrollcommand=scrollbar.set);self.log.pack(fill='both',expand=True)
        self.status=ttk.Label(outer,text='本机已连接 · CPU 按整机容量计 · 每 2 秒采样',style='Muted.TLabel',font=('Segoe UI',9));self.status.pack(anchor='w',pady=15)
        self.after(1000,self.metrics_tick)

    def page_changed(self, _=None):
        index=self.tabs.index(self.tabs.select())
        for i,button in enumerate(self.nav_buttons):button.configure(bg='#29263f' if i==index else SIDEBAR,fg=TEXT if i==index else MUTED)
        self.breadcrumb.configure(text='工作空间  /  '+['服务概览','启动项','终端工作区'][index])
        self.page_title.configure(text=['服务概览','启动项','终端工作区'][index])

    def toggle_sort(self):self.sort_cpu=not self.sort_cpu;self.render_listeners()

    def metrics_tick(self):
        if self.closing:return
        self.submit(lambda:self.request('/metrics'), self.performance.update_data)
        self.after(2000,self.metrics_tick)

    def tree(self,parent,columns):
        cards=ServiceCards(parent,columns);cards.pack(fill='both',expand=True);return cards

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
        self.performance.update_data(data.get('performance'))
        self.live_tree.resources = {str(item['pid']): item.get('usage') for item in data['listeners']}
        self.task_tree.resources = {item['id']: item.get('usage') for item in data['services']}
        self.render_listeners()
        self.replace_rows(self.task_tree, {item['id']: (item['name'], '运行中' if item['running'] else '已停止', item['command']) for item in data['services']})
        ports = {port for item in data['listeners'] for port in item['ports']}
        running = sum(item['running'] for item in data['services'])
        self.stats.configure(text=f"{len(data['listeners'])} 个进程 · {len(ports)} 个端口")
        self.status.configure(text='● 本机已连接 · CPU 按整机容量计 · 每 2 秒采样')
        if 'log' in data: self.set_log(data['log'])
        if self.smoke:
            metrics = data.get('performance') or {}
            if not metrics.get('available') or metrics.get('system', {}).get('cpuPercent') is None:
                self.after(400, self.refresh)
                return
            (server.ROOT / 'smoke-result.json').write_text(json.dumps({'ok': True, 'listeners': len(data['listeners']), 'api': self.base, 'metrics': True}), encoding='utf-8')
            self.after(300, self.close)

    def render_listeners(self):
        if not hasattr(self, 'live_tree'): return
        query = self.search.get().casefold()
        rows = [item for item in self.data['listeners'] if query in str(item).casefold()]
        if self.sort_cpu: rows.sort(key=lambda item:(item.get('usage') or {}).get('cpuPercent') or 0, reverse=True)
        self.replace_rows(self.live_tree, {str(item['pid']):(item['name'],item['pid'],', '.join(map(str,item['ports'])),item['command'] or '无权限读取') for item in rows})
        # Keep ordering stable across updates and reflect resource-based sorting.
        keys=[str(item['pid']) for item in rows]
        self.live_tree.rows={key:self.live_tree.rows[key] for key in keys}
        if not self.live_tree.selection() and keys:self.live_tree.selection_set(keys[0])
        self.live_tree.schedule()
        self.show_directory()

    def selected_listener(self):
        selected = self.live_tree.selection()
        return next((item for item in self.data['listeners'] if selected and str(item['pid']) == selected[0]), None)

    def show_directory(self, _=None):
        item = self.selected_listener()
        self.directory_text.configure(text=(item['directory'] or '无法读取此进程的工作目录') if item else '选择进程查看目录。')
        self.inspector.update_item(item)

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
