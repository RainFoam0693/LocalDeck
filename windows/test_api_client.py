"""Reproduce proxy HTML responses, and verify LocalDeck stays on loopback."""
import json
import os
from pathlib import Path
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from windows.api_client import LocalAPIClient

proxy_calls = []
requests = []
class API(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        requests.append((self.path, self.headers.get('Authorization')))
        status = 200
        if self.path == '/bad': payload = b'<html>not JSON</html>'
        elif self.path == '/error-html': status = 502; payload = b'<html>bad gateway</html>'
        elif self.path == '/error-json': status = 400; payload = b'{"error":"expected message"}'
        else: payload = json.dumps({'ok': True, 'listeners': [{'pid': 123, 'ports': [3000]}], 'system': {'cpuPercent': 12.5}}).encode()
        self.send_response(status); self.end_headers(); self.wfile.write(payload)
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.send_response(200); self.end_headers(); self.wfile.write(json.dumps({'body': body}).encode())
class Proxy(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        proxy_calls.append(self.path); self.send_response(200); self.end_headers(); self.wfile.write(b'<html>proxy intercepted</html>')

api = ThreadingHTTPServer(('127.0.0.1', 0), API)
proxy = ThreadingHTTPServer(('127.0.0.1', 0), Proxy)
for server in (api, proxy): threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    proxy_url = 'http://127.0.0.1:' + str(proxy.server_port)
    with patch.dict(os.environ, {'HTTP_PROXY': proxy_url, 'http_proxy': proxy_url, 'NO_PROXY': '', 'no_proxy': ''}), patch('urllib.request.proxy_bypass', return_value=False):
        # A default proxy-aware client reproduces the user's JSON parse failure.
        inherited = urllib.request.build_opener(urllib.request.ProxyHandler({'http': proxy_url}))
        try:
            with inherited.open('http://127.0.0.1:' + str(api.server_port) + '/state', timeout=5) as response: json.load(response)
        except ValueError: pass
        else: raise AssertionError('Proxy fixture did not reproduce the failure')
        count = len(proxy_calls)
        client = LocalAPIClient(api.server_port, 'test-token')
        assert client.request('/state')['listeners'][0]['ports'] == [3000]
        assert client.request('/metrics')['system']['cpuPercent'] == 12.5
        assert client.request('/services', {'name': 'hello'})['body'] == {'name': 'hello'}
        assert len(proxy_calls) == count, 'Loopback API leaked to the web proxy'
        assert requests[:2] == [('/state', 'Bearer test-token'), ('/metrics', 'Bearer test-token')]
        for path, expected in [('/bad', '无效数据'), ('/error-html', 'HTTP 502'), ('/error-json', 'expected message')]:
            try: client.request(path)
            except RuntimeError as error: assert expected in str(error), (path, error)
            else: raise AssertionError('Invalid response accepted')
        assert os.environ['http_proxy'] == proxy_url
    print('Local API: proxy failure reproduced; direct state/metrics/actions, authentication and errors passed')
finally:
    for server in (api, proxy): server.shutdown(); server.server_close()
