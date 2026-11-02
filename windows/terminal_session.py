"""Windows ConPTY lifecycle, independent from the desktop widgets."""
import os
import re
import threading
import pyte
from winpty import PtyProcess
from backend.windows_platform import stop_tree
from windows.terminal_activity import PromptActivity, has_child_jobs
from windows.terminal_identity import task_identity


class ReplyScreen(pyte.HistoryScreen):
    def write_process_input(self, data):
        callback = getattr(self, 'reply', None)
        if callback: callback(data)


class TerminalSession:
    def __init__(self, directory, shell='cmd', ssh=None):
        self.is_ssh = ssh is not None
        self.ssh_title = (ssh['name'] + ' · SSH') if ssh else None
        self.directory = directory
        self.shell = shell
        self.lock = threading.RLock()
        self.close_lock = threading.Lock()
        self.error = ''
        self.running = True
        self.version = 0
        self.closed = False
        self.identity = None
        self.identity_stop = threading.Event()
        self.activity = PromptActivity()
        self.screen = ReplyScreen(100, 28, history=1500)
        self.stream = pyte.Stream(self.screen)
        args, environment = self.activity.shell_options(shell, dict(os.environ, TERM='xterm-256color', COLORTERM='truecolor'))
        if ssh:
            import shutil
            from windows.ssh import ssh_arguments
            executable = shutil.which('ssh.exe')
            if not executable: raise RuntimeError('未找到 OpenSSH 客户端，请在 Windows 设置 → 系统 → 可选功能中安装 OpenSSH 客户端。')
            args = ssh_arguments(ssh); args[0] = executable
        self.process = PtyProcess.spawn(args, cwd=directory, dimensions=(28, 100), env=environment)
        self.screen.reply = self.write
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        threading.Thread(target=self._identify, daemon=True).start()

    def _identify(self):
        while not self.closed and self.running:
            identity = task_identity(self.process.pid)
            with self.lock: self.identity = identity if self.running and not self.closed else None
            if self.identity_stop.wait(1): break

    def _read(self):
        try:
            while not self.closed:
                output = self.process.read(32768)
                if output:
                    with self.lock:
                        self.activity.output(output)
                        self.stream.feed(output)
                        self.version += 1
        except (EOFError, OSError): pass
        except Exception as error: self.error = str(error)
        finally:
            self.running = False
            with self.lock: self.version += 1

    def prompt_directory(self):
        with self.lock:
            row = self.screen.buffer[self.screen.cursor.y]
            line = ''.join(row[x].data if x in row else ' ' for x in range(self.screen.cursor.x))
            match = re.fullmatch(r'(?:PS )?((?:[A-Za-z]:\\|\\\\)[^>\r\n]*)> ?', line)
            if match:
                self.directory = match.group(1)
                return self.directory
        return None

    def has_active_jobs(self):
        if self.closed or not self.running: return False
        if self.is_ssh: return True
        with self.lock:
            executing = self.activity.executing
        return executing or has_child_jobs(self.process.pid)

    def write(self, text):
        if not self.closed and self.running:
            try:
                with self.lock: self.activity.input(text)
                self.process.write(text)
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

    def snapshot_for_view(self):
        with self.lock:
            origins = list(self.screen.history.top) + [self.screen.buffer[y] for y in range(self.screen.lines)]
            return (*self.snapshot(), origins)

    def text(self):
        _, lines, _, _, columns = self.snapshot()
        return '\n'.join(''.join(line[x].data if x in line else ' ' for x in range(columns)).rstrip() for line in lines)

    def close(self):
        # A tab-close worker and application shutdown can reach this concurrently.
        with self.close_lock:
            if self.closed: return
            self.closed = True
            self.identity_stop.set()
            try: stop_tree(self.process.pid)
            finally:
                self.running = False
                try: self.process.close(force=True)
                finally:
                    self.process.fileobj.close()
                    self.process._server.close()


