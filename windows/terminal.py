"""Persistent Windows pseudoterminal sessions and a VT screen for each tab."""
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font as tkfont
import pyte
from winpty import PtyProcess
from backend.windows_platform import stop_tree


class ReplyScreen(pyte.HistoryScreen):
    def write_process_input(self, data):
        callback = getattr(self, 'reply', None)
        if callback: callback(data)


class TerminalSession:
    def __init__(self, directory, shell='cmd'):
        self.directory = directory
        self.lock = threading.RLock()
        self.error = ''
        self.running = True
        self.version = 0
        self.closed = False
        self.screen = ReplyScreen(100, 28, history=1500)
        self.stream = pyte.Stream(self.screen)
        args = ['powershell.exe', '-NoLogo'] if shell == 'powershell' else [os.environ.get('COMSPEC', 'cmd.exe'), '/d']
        self.process = PtyProcess.spawn(args, cwd=directory, dimensions=(28, 100), env=dict(os.environ, TERM='xterm-256color', COLORTERM='truecolor'))
        self.screen.reply = self.write
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            while not self.closed:
                output = self.process.read(32768)
                if output:
                    with self.lock:
                        self.stream.feed(output)
                        self.version += 1
        except (EOFError, OSError): pass
        except Exception as error: self.error = str(error)
        finally:
            self.running = False
            with self.lock: self.version += 1

    def write(self, text):
        if not self.closed and self.running:
            try: self.process.write(text)
            except (EOFError, OSError): self.running = False

    def resize(self, rows, columns):
        if not self.running or self.closed: return
        with self.lock:
            if (rows, columns) == (self.screen.lines, self.screen.columns): return
            self.process.setwinsize(rows, columns)
            self.screen.resize(lines=rows, columns=columns)
            self.version += 1

    def snapshot(self):
        with self.lock:
            history = list(self.screen.history.top)
            lines = [dict(line) for line in history] + [dict(self.screen.buffer[y]) for y in range(self.screen.lines)]
            cursor = (len(history) + self.screen.cursor.y, self.screen.cursor.x, self.screen.cursor.hidden)
            return self.version, lines, cursor, self.running, self.screen.columns

    def text(self):
        _, lines, _, _, columns = self.snapshot()
        return '\n'.join(''.join(line[x].data if x in line else ' ' for x in range(columns)).rstrip() for line in lines)

    def close(self):
        if self.closed: return
        self.closed = True
        try: stop_tree(self.process.pid)
        finally:
            self.running = False
            # Release sockets even if PtyProcess has already marked itself closed.
            try: self.process.close(force=True)
            finally:
                self.process.fileobj.close()
                self.process._server.close()


class TerminalWorkspace(ttk.Frame):
    COLORS = {'black': '#10151e', 'red': '#ef6c75', 'green': '#76d69c', 'brown': '#e6c078',
              'blue': '#72a7ef', 'magenta': '#c694e8', 'cyan': '#57d8d0', 'white': '#e5ebf4',
              'brightblack': '#66768b', 'brightred': '#ff8990', 'brightgreen': '#a4efbc',
              'brightbrown': '#ffe1a1', 'brightblue': '#a3c7ff', 'brightmagenta': '#e3baff',
              'brightcyan': '#9aeee8', 'brightwhite': '#ffffff'}
    def __init__(self, parent):
        super().__init__(parent, padding=(0, 14))
        self.sessions = {}
        self.pending = queue.Queue()
        self.next_number = 1
        self.closing = False
        self.last_versions = {}
        self.font = tkfont.Font(family='Consolas', size=11)
        bar = ttk.Frame(self); bar.pack(fill='x', pady=(0, 10))
        ttk.Label(bar, text='独立 Shell · 切换页面继续运行 · Ctrl+C 中断 · Ctrl+Shift+C/V 复制粘贴').pack(side='left')
        ttk.Button(bar, text='＋ CMD', command=self.add).pack(side='right')
        ttk.Button(bar, text='＋ PowerShell', command=lambda: self.add(shell='powershell')).pack(side='right', padx=6)
        ttk.Button(bar, text='选择目录…', command=self.choose_directory).pack(side='right')
        self.tabs = ttk.Notebook(self); self.tabs.pack(fill='both', expand=True)
        self.tabs.bind('<<NotebookTabChanged>>', self.focus_terminal)
        footer = ttk.Frame(self); footer.pack(fill='x', pady=(10, 0))
        self.status = ttk.Label(footer, text='点击 ＋ CMD 或 ＋ PowerShell 创建终端。'); self.status.pack(side='left')
        ttk.Button(footer, text='关闭当前终端…', command=self.close_selected).pack(side='right')
        self.after(80, self.paint)

    def choose_directory(self):
        directory = filedialog.askdirectory(parent=self)
        if directory: self.add(directory=directory)

    def add(self, directory=None, shell='cmd'):
        if self.closing: return
        directory = directory or os.path.expanduser('~')
        self.status.configure(text='正在创建终端…')
        # Shell startup must never block the UI, even for a slow PowerShell profile.
        def spawn():
            try:
                session = TerminalSession(directory, shell)
                if self.closing: session.close()
                else: self.pending.put((session, None))
            except Exception as error: self.pending.put((None, str(error)))
        threading.Thread(target=spawn, daemon=True).start()

    def attach(self, session):
        frame = ttk.Frame(self.tabs)
        text = tk.Text(frame, bg='#090e16', fg='#e5ebf4', font=self.font, wrap='none', relief='flat', padx=10, pady=8, insertbackground='#34dfbd', exportselection=False, cursor='xterm', undo=False)
        scroll = ttk.Scrollbar(frame, command=text.yview); scroll.pack(side='right', fill='y')
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=text.xview); horizontal.pack(side='bottom', fill='x')
        text.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set); text.pack(fill='both', expand=True)
        key = str(frame)
        self.sessions[key] = (session, text)
        self.tabs.add(frame, text=f'终端 {self.next_number}')
        self.next_number += 1; self.tabs.select(frame)
        text.bind('<KeyPress>', lambda event: self.key(event, session, text))
        text.bind('<<Paste>>', lambda _: self.paste(session))
        text.bind('<Control-Shift-C>', lambda _: self.copy(text))
        text.bind('<Control-Shift-V>', lambda _: self.paste(session))
        text.bind('<Control-Insert>', lambda _: self.copy(text))
        text.bind('<Shift-Insert>', lambda _: self.paste(session))
        text.bind('<Configure>', lambda _: self.resize(key))
        text.bind('<Button-1>', lambda _: text.focus_set())
        text.focus_set()
        self.after(100, lambda: self.resize(key))
        return key

    def focus_terminal(self, _=None):
        pair = self.sessions.get(self.tabs.select())
        if pair: pair[1].focus_set()

    def resize(self, key):
        pair = self.sessions.get(key)
        if not pair: return
        session, text = pair
        if text.winfo_width() < 40 or text.winfo_height() < 40: return
        columns = max(20, min(300, (text.winfo_width() - 20) // max(1, self.font.measure('M'))))
        rows = max(5, min(150, (text.winfo_height() - 16) // self.font.metrics('linespace')))
        try: session.resize(rows, columns)
        except Exception as error: self.status.configure(text='调整终端尺寸失败：' + str(error))

    def paste(self, session):
        try: value = self.clipboard_get()
        except tk.TclError: return 'break'
        if '\n' in value or '\r' in value:
            if not messagebox.askyesno('粘贴多行命令', '粘贴的内容包含换行，可能立即执行命令。继续粘贴？', parent=self): return 'break'
        session.write(value.replace('\r\n', '\r').replace('\n', '\r'))
        return 'break'

    def copy(self, text):
        try:
            selection = text.get('sel.first', 'sel.last')
            self.clipboard_clear(); self.clipboard_append(selection)
        except tk.TclError: pass
        return 'break'

    def key(self, event, session, text):
        control = bool(event.state & 4)
        shift = bool(event.state & 1)
        name = event.keysym
        if control and shift and name.lower() == 'c': return self.copy(text)
        if control and shift and name.lower() == 'v': return self.paste(session)
        if shift and name == 'Insert': return self.paste(session)
        if control and name == 'Insert': return self.copy(text)
        codes = {'Return': '\r', 'KP_Enter': '\r', 'BackSpace': '\x7f', 'Tab': '\t', 'Escape': '\x1b',
                 'Up': '\x1b[A', 'Down': '\x1b[B', 'Right': '\x1b[C', 'Left': '\x1b[D',
                 'Home': '\x1b[H', 'End': '\x1b[F', 'Delete': '\x1b[3~', 'Insert': '\x1b[2~',
                 'Prior': '\x1b[5~', 'Next': '\x1b[6~', 'F1': '\x1bOP', 'F2': '\x1bOQ', 'F3': '\x1bOR', 'F4': '\x1bOS',
                 'F5': '\x1b[15~', 'F6': '\x1b[17~', 'F7': '\x1b[18~', 'F8': '\x1b[19~', 'F9': '\x1b[20~', 'F10': '\x1b[21~', 'F11': '\x1b[23~', 'F12': '\x1b[24~'}
        if shift and name == 'Tab': value = '\x1b[Z'
        elif control and len(name) == 1 and 'a' <= name.lower() <= 'z': value = chr(ord(name.lower()) - 96)
        else: value = codes.get(name, event.char)
        if value:
            if event.state & 8 and name not in ('Alt_L', 'Alt_R'): value = '\x1b' + value
            session.write(value)
            text.see('end')
        return 'break'

    def color(self, value, default):
        if value == 'default': return default
        return self.COLORS.get(value, '#' + value if len(value) == 6 else default)

    def paint(self):
        if self.closing: return
        try:
            while True:
                session, error = self.pending.get_nowait()
                if error: self.status.configure(text='终端启动失败：' + error)
                else: self.attach(session)
        except queue.Empty: pass
        key = self.tabs.select()
        if key in self.sessions:
            session, text = self.sessions[key]
            version, lines, cursor, running, columns = session.snapshot()
            if self.last_versions.get(key) != version:
                self.last_versions[key] = version
                bottom = text.yview()[1] >= 0.98
                old_scroll = text.yview()[0]
                text.delete('1.0', 'end')
                text.tag_configure('cursor', background='#34dfbd', foreground='#0c2420')
                for row, line in enumerate(lines):
                    pieces = []
                    position = 0
                    cursor_position = cursor[1]
                    spans = []
                    for col in range(columns):
                        cell = line.get(col)
                        value = cell.data if cell else ' '
                        pieces.append(value)
                        if cell and (cell.fg != 'default' or cell.bg != 'default' or cell.reverse):
                            fg = self.color(cell.fg, '#e5ebf4'); bg = self.color(cell.bg, '#090e16')
                            if cell.reverse: fg, bg = bg, fg
                            tag = 'color_' + fg + bg
                            if tag not in text.tag_names(): text.tag_configure(tag, foreground=fg, background=bg)
                            spans.append((tag, position, position + len(value)))
                        if row == cursor[0] and col == cursor[1]: cursor_position = position
                        position += len(value)
                    text.insert('end', ''.join(pieces) + '\n')
                    for tag, start, end in spans: text.tag_add(tag, f'{row+1}.{start}', f'{row+1}.{end}')
                    if row == cursor[0] and not cursor[2]:
                        start = cursor_position
                        text.tag_add('cursor', f'{row+1}.{start}', f'{row+1}.{start+1}')
                if bottom: text.see('end')
                else: text.yview_moveto(old_scroll)
                self.status.configure(text=f'{session.directory} · ' + ('运行中' if running else '会话已结束'))
            self.tabs.tab(key, text=self.tabs.tab(key, 'text').split(' · ')[0] + ('' if running else ' · 已结束'))
        self.after(80, self.paint)

    def close_selected(self):
        key = self.tabs.select()
        if key not in self.sessions: return
        if not messagebox.askyesno('关闭终端', '关闭此终端？其中运行的命令也会结束。', parent=self): return
        session, text = self.sessions.pop(key)
        frame = text.master
        self.tabs.forget(key); frame.destroy()
        self.last_versions.pop(key, None)
        threading.Thread(target=session.close, daemon=True).start()

    def shutdown(self):
        self.closing = True
        for session, _ in list(self.sessions.values()): session.close()
        self.sessions.clear()
        # Include shells that finished starting while shutdown was in progress.
        try:
            while True:
                session, _ = self.pending.get_nowait()
                if session: session.close()
        except queue.Empty: pass
