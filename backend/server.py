#!/usr/bin/env python3
"""Local service supervisor. Standard library only; authenticated loopback API."""
import argparse, json, os, pathlib, secrets, signal, subprocess, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from backend.performance import Sampler
except ModuleNotFoundError:
    from performance import Sampler

METRICS = None
IS_WINDOWS = os.name == 'nt'
if IS_WINDOWS:
    try:
        from backend import windows_platform
    except ModuleNotFoundError:
        import windows_platform
DEFAULT_ROOT = (pathlib.Path(os.environ.get('LOCALAPPDATA', str(pathlib.Path.home() / 'AppData/Local'))) / 'LocalDeck'
                if IS_WINDOWS else pathlib.Path.home() / 'Library/Application Support/LocalDeck')
ROOT = pathlib.Path(os.environ.get('LOCALDECK_DATA_DIR', str(DEFAULT_ROOT)))
ROOT.mkdir(parents=True, exist_ok=True)
os.chmod(ROOT, 0o700)
CONFIG = ROOT / 'services.json'
LOCK = threading.RLock()
CHILDREN = {}

def configured():
    try: return json.loads(CONFIG.read_text(encoding='utf-8'))
    except FileNotFoundError: return []

def save(items):
    temp = CONFIG.with_suffix('.tmp')
    temp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(CONFIG)

def run(args):
    try: return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL, timeout=5)
    except (subprocess.SubprocessError, OSError): return ''

def listeners():
    if IS_WINDOWS: return windows_platform.listeners()
    data = run(['/usr/sbin/lsof', '-nP', '-iTCP', '-sTCP:LISTEN', '-Fpcn'])
    rows, current = {}, {}
    for line in data.splitlines():
        if line.startswith('p'): current = {'pid': int(line[1:]), 'name': '', 'ports': []}
        elif line.startswith('c'): current['name'] = line[1:]
        elif line.startswith('n') and 'pid' in current:
            port = line.rsplit(':', 1)[-1]
            if not port.isdigit(): continue
            pid = current['pid']
            row = rows.setdefault(pid, dict(current, ports=[]))
            if int(port) not in row['ports']: row['ports'].append(int(port))
    for pid, row in rows.items():
        row['command'] = run(['/bin/ps', '-p', str(pid), '-o', 'command=']).strip()
        cwd = run(['/usr/sbin/lsof', '-a', '-p', str(pid), '-d', 'cwd', '-Fn'])
        row['directory'] = next((x[1:] for x in cwd.splitlines() if x.startswith('n')), '')
    return sorted((row for row in rows.values() if row['pid'] not in (os.getpid(), os.getppid())), key=lambda row: row['pid'])

def snapshot():
    with LOCK:
        services = configured()
        for item in services:
            p = CHILDREN.get(item['id'])
            item['running'] = p is not None and p.poll() is None
            item['pid'] = p.pid if item['running'] else None
            item['exitCode'] = p.poll() if p else None
        live = listeners()
        if METRICS:
            for item in services: item['usage'] = METRICS.usage(item['pid'], descendants=True)
            for item in live: item['usage'] = METRICS.usage(item['pid'])
        return {'services': services, 'listeners': live, 'performance': METRICS.snapshot() if METRICS else None}

def stop(item_id):
    p = CHILDREN.get(item_id)
    if p and p.poll() is None:
        if IS_WINDOWS:
            windows_platform.stop_tree(p.pid)
            p.wait(timeout=6)
            return
        os.killpg(p.pid, signal.SIGTERM)
        try: p.wait(timeout=4)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait(timeout=2)

def action(path, body):
    with LOCK:
        items = configured()
        if path == '/services':
            name, command = str(body.get('name', '')).strip(), str(body.get('command', '')).strip()
            directory = os.path.expanduser(str(body.get('directory', '')).strip())
            if not name or not command or not os.path.isdir(directory): raise ValueError('请填写名称、命令和有效的绝对目录')
            item = dict(id=secrets.token_hex(8), name=name, command=command, directory=directory)
            items.append(item); save(items)
            return item
        parts = path.strip('/').split('/')
        if len(parts) == 3 and parts[0] == 'services':
            item = next((x for x in items if x['id'] == parts[1]), None)
            if not item: raise ValueError('服务不存在')
            verb = parts[2]
            if verb in ('stop', 'restart', 'delete'): stop(item['id'])
            if verb in ('start', 'restart'):
                p = CHILDREN.get(item['id'])
                if p and p.poll() is None: return {'ok': True}
                with open(ROOT / (item['id'] + '.log'), 'ab') as log:
                    log.write(('\n--- ' + time.ctime() + ' ---\n').encode())
                    args = (subprocess.list2cmdline([os.environ.get('COMSPEC', 'cmd.exe')]) + ' /d /s /c \"' + item['command'] + '\"') if IS_WINDOWS else ['/bin/zsh', '-lc', item['command']]
                    options = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {'start_new_session': True}
                    environment = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
                    CHILDREN[item['id']] = subprocess.Popen(args, cwd=item['directory'], stdout=log, stderr=log, env=environment, **options)
            elif verb == 'delete': save([x for x in items if x['id'] != item['id']])
            elif verb != 'stop': raise ValueError('不支持的操作')
            return {'ok': True}
        if path == '/processes/stop':
            pid = int(body['pid'])
            match = next((x for x in listeners() if x['pid'] == pid), None)
            if not match or not match['command'] or match['command'] != body.get('command') or pid in (os.getpid(), os.getppid()):
                raise ValueError('进程已变化或不可停止，请刷新')
            os.kill(pid, signal.SIGTERM)
            return {'ok': True}
        raise ValueError('未知接口')

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def respond(self, code, data):
        payload = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers(); self.wfile.write(payload)
    def authorized(self):
        return secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + self.server.token)
    def do_GET(self):
        if not self.authorized(): return self.respond(401, {'error': 'Unauthorized'})
        try:
            if self.path == '/metrics': return self.respond(200, METRICS.snapshot())
            if self.path == '/state': return self.respond(200, snapshot())
            if self.path.startswith('/logs/'):
                key = self.path.split('/')[-1]
                if not any(x['id'] == key for x in configured()): raise ValueError('服务不存在')
                file = ROOT / (key + '.log')
                if file.exists():
                    with file.open('rb') as f:
                        f.seek(max(0, file.stat().st_size - 100000)); content = f.read().decode('utf-8', 'replace')
                else: content = '尚无日志。启动服务后会在这里显示。'
                return self.respond(200, {'text': content})
            self.respond(404, {'error': 'Not found'})
        except Exception as e: self.respond(400, {'error': str(e)})
    def do_POST(self):
        if not self.authorized(): return self.respond(401, {'error': 'Unauthorized'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length > 65536: raise ValueError('请求过大')
            self.respond(200, action(self.path, json.loads(self.rfile.read(length) or b'{}')))
        except Exception as e: self.respond(400, {'error': str(e)})

def make_server(port=0):
    global METRICS
    if METRICS is None: METRICS = Sampler()
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.token = secrets.token_urlsafe(32)
    return server

def stop_all():
    with LOCK:
        for key in list(CHILDREN): stop(key)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    server = make_server(args.port); token = server.token
    print(json.dumps({'port': server.server_port, 'token': token}), flush=True)
    def shutdown(*_):
        with LOCK:
            for key in list(CHILDREN): stop(key)
        os._exit(0)
    signal.signal(signal.SIGTERM, shutdown); signal.signal(signal.SIGINT, shutdown)
    server.serve_forever()
