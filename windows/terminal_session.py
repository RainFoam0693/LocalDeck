"""Windows ConPTY lifecycle, independent from the desktop widgets."""
import os
import threading
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
        self.close_lock = threading.Lock()
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
        # A tab-close worker and application shutdown can reach this concurrently.
        with self.close_lock:
            if self.closed: return
            self.closed = True
            try: stop_tree(self.process.pid)
            finally:
                self.running = False
                try: self.process.close(force=True)
                finally:
                    self.process.fileobj.close()
                    self.process._server.close()


