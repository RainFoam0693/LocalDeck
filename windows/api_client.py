"""Authenticated loopback API requests must never use the system web proxy."""
import json
import urllib.error
import urllib.request


class LocalAPIClient:
    def __init__(self, port, token):
        if not isinstance(port, int) or not 0 < port < 65536:
            raise ValueError('Invalid local API port')
        self.base = 'http://127.0.0.1:' + str(port)
        self.token = token
        # Python otherwise inherits HTTP_PROXY and Windows Internet Settings.
        # This opener is private to LocalDeck's loopback API; OS settings stay intact.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, path, body=None):
        if not path.startswith('/') or path.startswith('//'):
            raise ValueError('Invalid local API path')
        request = urllib.request.Request(self.base + path,
            data=json.dumps(body).encode('utf-8') if body is not None else None,
            headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=30) as response:
                try:
                    result = json.load(response)
                except (ValueError, UnicodeError) as error:
                    raise RuntimeError('本机 API 返回了无效数据，请检查是否有软件拦截本机连接。') from error
                if not isinstance(result, dict):
                    raise RuntimeError('本机 API 返回的数据格式不正确。')
                return result
        except urllib.error.HTTPError as error:
            message = '本机 API 请求失败（HTTP ' + str(error.code) + '）。'
            try:
                details = json.load(error)
                if isinstance(details, dict) and isinstance(details.get('error'), str):
                    message = details['error']
            except (ValueError, UnicodeError):
                pass
            raise RuntimeError(message) from error
        except urllib.error.URLError as error:
            raise RuntimeError('无法连接本机 API，请重新打开 LocalDeck。') from error
