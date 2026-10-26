import json, os, pathlib, signal, subprocess, tempfile, time, urllib.request, urllib.error

with tempfile.TemporaryDirectory(prefix='localdeck-test-') as directory:
    process = subprocess.Popen(['/usr/bin/env', 'python3', '-u', 'backend/server.py'], env=dict(os.environ, LOCALDECK_DATA_DIR=directory), stdout=subprocess.PIPE, text=True)
    try:
        info = json.loads(process.stdout.readline())
        base = 'http://127.0.0.1:' + str(info['port'])
        def request(path, body=None):
            req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers={'Authorization': 'Bearer ' + info['token']})
            with urllib.request.urlopen(req, timeout=20) as res: return json.load(res)
        try:
            urllib.request.urlopen(base + '/state')
            raise AssertionError('Unauthenticated request accepted')
        except urllib.error.HTTPError as error: assert error.code == 401
        initial = request('/state')
        assert isinstance(initial['listeners'], list)
        service = request('/services', dict(name='Integration', command="echo localdeck-test-ok; exec /bin/sleep 60", directory=directory))
        key = service['id']
        request('/services/' + key + '/start', {})
        time.sleep(0.3)
        assert request('/state')['services'][0]['running']
        assert 'localdeck-test-ok' in request('/logs/' + key)['text']
        old_pid = request('/state')['services'][0]['pid']
        request('/services/' + key + '/restart', {})
        assert request('/state')['services'][0]['pid'] != old_pid
        request('/services/' + key + '/stop', {})
        assert not request('/state')['services'][0]['running']
        request('/services/' + key + '/delete', {})
        assert request('/state')['services'] == []
        print('PASS: authentication, scan, create, start, logs, restart, stop, delete')
    finally:
        process.terminate(); process.wait(timeout=10)
