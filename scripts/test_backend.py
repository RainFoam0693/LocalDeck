"""Integration test: real authenticated API, real HTTP task, process-tree cleanup."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error


def wait_until(check, timeout=15):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = check()
        if result: return result
        time.sleep(0.2)
    raise AssertionError('Timed out waiting for expected process state')


with tempfile.TemporaryDirectory(prefix='localdeck-test-') as directory:
    fixture = Path(directory) / 'http task.py'
    fixture.write_text("from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler\nimport json\ns = ThreadingHTTPServer(('127.0.0.1', 0), SimpleHTTPRequestHandler)\nprint('localdeck-test-ok', flush=True)\nprint(json.dumps({'port': s.server_port}), flush=True)\ns.serve_forever()\n", encoding='utf-8')
    process = subprocess.Popen([sys.executable, '-u', 'backend/server.py'], env=dict(os.environ, LOCALDECK_DATA_DIR=directory), stdout=subprocess.PIPE, text=True, encoding='utf-8')
    key = None
    try:
        info = json.loads(process.stdout.readline())
        base = 'http://127.0.0.1:' + str(info['port'])
        def request(path, body=None):
            req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers={'Authorization': 'Bearer ' + info['token']})
            with urllib.request.urlopen(req, timeout=30) as res: return json.load(res)
        try:
            urllib.request.urlopen(base + '/state')
            raise AssertionError('Unauthenticated request accepted')
        except urllib.error.HTTPError as error: assert error.code == 401
        assert isinstance(request('/state')['listeners'], list)
        args = [sys.executable, '-u', str(fixture)]
        command = subprocess.list2cmdline(args) if os.name == 'nt' else 'exec ' + shlex.join(args)
        service = request('/services', dict(name='中文 HTTP task', command=command, directory=directory))
        key = service['id']
        request('/services/' + key + '/start', {})
        def find_listener():
            data = request('/state')
            return next((item for item in data['listeners'] if str(fixture) in item['command']), None)
        listener = wait_until(find_listener)
        assert request('/state')['services'][0]['running']
        assert 'localdeck-test-ok' in request('/logs/' + key)['text']
        try:
            request('/processes/stop', {'pid': listener['pid'], 'command': 'stale-command'})
            raise AssertionError('Mismatched process identity was accepted')
        except urllib.error.HTTPError as error: assert error.code == 400
        old_pid = request('/state')['services'][0]['pid']
        old_listener_pid = listener['pid']
        request('/services/' + key + '/restart', {})
        assert request('/state')['services'][0]['pid'] != old_pid
        listener = wait_until(find_listener)
        assert listener['pid'] != old_listener_pid
        request('/services/' + key + '/stop', {})
        assert not request('/state')['services'][0]['running']
        assert not find_listener(), 'Child HTTP process survived stop'
        request('/services/' + key + '/delete', {})
        assert request('/state')['services'] == []
        print('PASS: auth, real TCP discovery, Unicode config, PID guard, start, logs, restart, tree stop, delete')
    finally:
        if key:
            try: request('/services/' + key + '/stop', {})
            except Exception: pass
        process.terminate(); process.wait(timeout=10)
