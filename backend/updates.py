"""Shared, read-only GitHub release discovery and verified package downloads.

Invoked by the macOS bridge as JSON over stdin/stdout; imported by Windows.
Never installs packages, runs downloaded code, or contains repository credentials.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, unquote
from urllib.request import Request, build_opener, HTTPRedirectHandler

REPOSITORY = 'RainFoam0693/LocalDeck'
RELEASES_URL = 'https://github.com/' + REPOSITORY + '/releases'
API_URL = 'https://api.github.com/repos/' + REPOSITORY + '/releases?per_page=100'
TRUSTED_HOSTS = {'api.github.com', 'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}
MAX_PACKAGE = 1024 * 1024 * 1024


class UpdateError(Exception): pass


def version_tuple(value):
    match = re.fullmatch(r'(?:macos-|windows-)?v?(\d+)\.(\d+)\.(\d+)', value, re.I)
    return tuple(map(int, match.groups())) if match else None


def safe_url(value, asset=False):
    url = urlsplit(value)
    prefix = '/' + REPOSITORY + ('/releases/download/' if asset else '/releases/tag/')
    return (url.scheme == 'https' and url.netloc == 'github.com' and url.path.startswith(prefix)
            and not url.query and not url.fragment and not url.username)


def safe_api_asset(value):
    return bool(re.fullmatch(r'https://api\.github\.com/repos/' + REPOSITORY + r'/releases/assets/\d+', value))


class GitHubRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        target = urlsplit(new_url)
        if target.scheme != 'https' or target.hostname not in TRUSTED_HOSTS:
            raise UpdateError('更新地址重定向到了不受支持的站点。')
        redirected = super().redirect_request(request, response, code, message, headers, new_url)
        if redirected and target.hostname != urlsplit(request.full_url).hostname:
            redirected.remove_header('Authorization')
        return redirected


def select_release(releases, current, platform, architecture):
    current_version = version_tuple(current)
    if current_version is None: raise UpdateError('无法识别当前版本号。')
    choices = []
    for release in releases:
        if release.get('draft') or release.get('prerelease'): continue
        tag = release.get('tag_name', '')
        version = version_tuple(tag)
        if not version or version <= current_version or not safe_url(release.get('html_url', '')): continue
        if tag.lower().startswith('macos-') and platform != 'macos': continue
        if tag.lower().startswith('windows-') and platform != 'windows': continue
        for asset in release.get('assets', []):
            name = asset.get('name', '')
            # Choose only an explicit OS/architecture package, never a source archive.
            pattern = r'LocalDeck-(\d+\.\d+\.\d+)-' + ('macOS-' + re.escape(architecture) + r'\.dmg' if platform == 'macos' else r'Windows-' + re.escape(architecture) + r'\.exe')
            match = re.fullmatch(pattern, name, re.I)
            if not match or version_tuple(match[1]) != version or asset.get('state', 'uploaded') != 'uploaded': continue
            if not safe_url(asset.get('browser_download_url', ''), asset=True): continue
            choices.append((version, {
                'version': '.'.join(map(str, version)), 'name': name,
                'url': asset['browser_download_url'], 'page': release['html_url'],
                'notes': str(release.get('body') or '此版本未提供更新说明。')[:12000],
                'api': asset.get('url', '') if safe_api_asset(asset.get('url', '')) else '',
                'checksumAPI': next((a.get('url', '') for a in release.get('assets', [])
                    if a.get('name') == ('SHA256SUMS-macOS.txt' if platform == 'macos' else 'SHA256SUMS-Windows.txt')
                    and safe_api_asset(a.get('url', ''))), ''),
                'digest': asset.get('digest') or '', 'size': asset.get('size', 0),
                'checksum': next((a['browser_download_url'] for a in release.get('assets', [])
                    if a.get('name') == ('SHA256SUMS-macOS.txt' if platform == 'macos' else 'SHA256SUMS-Windows.txt')
                    and safe_url(a.get('browser_download_url', ''), asset=True)), '')
            }))
    return max(choices, key=lambda item: item[0])[1] if choices else None


def open_remote(url, token=''):
    if url != API_URL and not safe_api_asset(url) and not safe_url(url, asset=True): raise UpdateError('更新地址无效。')
    headers = {'User-Agent': 'LocalDeck-Updater', 'Accept': 'application/vnd.github+json' if url == API_URL else 'application/octet-stream'}
    if token and urlsplit(url).hostname == 'api.github.com': headers['Authorization'] = 'Bearer ' + token
    try:
        response = build_opener(GitHubRedirect()).open(Request(url, headers=headers), timeout=25)
        final = urlsplit(response.geturl())
        if final.scheme != 'https' or final.hostname not in TRUSTED_HOSTS:
            response.close(); raise UpdateError('更新地址重定向到了不受支持的站点。')
        return response
    except HTTPError as error:
        if error.code == 401: raise UpdateError('GitHub 授权无效或已过期，请在设置中更新访问令牌。') from None
        if error.code == 404: raise UpdateError('无法访问发行版本。私有仓库需要配置具有 Contents 只读权限的 GitHub 访问令牌，也可打开发行页登录查看。') from None
        if error.code in (403, 429): raise UpdateError('GitHub 暂时限制了请求，请稍后重试。') from None
        raise UpdateError('GitHub 请求失败，请稍后重试。') from None
    except (URLError, TimeoutError, OSError): raise UpdateError('无法连接 GitHub，请检查网络后重试。') from None


def check(current, platform, architecture, token=''):
    with open_remote(API_URL, token) as response:
        data = response.read(4 * 1024 * 1024 + 1)
    if len(data) > 4 * 1024 * 1024: raise UpdateError('发行版本数据过大，请打开 GitHub 发行页查看。')
    try: releases = json.loads(data)
    except (ValueError, UnicodeError): raise UpdateError('GitHub 返回了无效数据，请检查网络代理。') from None
    if not isinstance(releases, list): raise UpdateError('GitHub 返回了无效的发行列表。')
    return select_release(releases, current, platform, architecture)


def checksum_for(release, token=''):
    digest = release.get('digest', '')
    if re.fullmatch(r'sha256:[a-fA-F0-9]{64}', digest): return digest[7:].lower()
    manifest = release.get('checksum', '')
    if not safe_url(manifest, asset=True): raise UpdateError('发行包未提供 SHA-256 校验，请从 GitHub 发行页下载。')
    with open_remote(release.get('checksumAPI', '') if token and safe_api_asset(release.get('checksumAPI', '')) else manifest, token) as response: data = response.read(65537)
    if len(data) > 65536: raise UpdateError('更新校验文件无效。')
    for line in data.decode('utf-8').splitlines():
        fields = line.split(maxsplit=1)
        if len(fields) == 2 and fields[1].lstrip('*') == release['name'] and re.fullmatch(r'[a-fA-F0-9]{64}', fields[0]): return fields[0].lower()
    raise UpdateError('更新校验文件中没有对应的安装包。')


def download(release, destination, progress=lambda value: None, token=''):
    name = release.get('name', '')
    if not re.fullmatch(r'LocalDeck-\d+\.\d+\.\d+-(?:macOS-(?:arm64|x64)\.dmg|Windows-(?:x64|arm64)\.exe)', name, re.I): raise UpdateError('更新包名称无效。')
    if not safe_url(release.get('url', ''), asset=True): raise UpdateError('更新包地址无效。')
    if unquote(urlsplit(release['url']).path.rsplit('/', 1)[-1]) != name: raise UpdateError('更新包地址与文件名不匹配。')
    expected = checksum_for(release, token)
    folder = Path(destination) / 'LocalDeck Updates'; folder.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.download-', dir=folder)
    total = 0; digest = hashlib.sha256()
    try:
        with os.fdopen(descriptor, 'wb') as output, open_remote(release.get('api', '') if token and safe_api_asset(release.get('api', '')) else release['url'], token) as response:
            while True:
                chunk = response.read(256 * 1024)
                if not chunk: break
                total += len(chunk)
                if total > MAX_PACKAGE: raise UpdateError('更新包大小异常，下载已停止。')
                output.write(chunk); digest.update(chunk)
                progress(min(99, int(total * 100 / release['size'])) if release.get('size', 0) > 0 else 0)
        if digest.hexdigest() != expected: raise UpdateError('更新包校验失败，文件已丢弃，请重新下载。')
        if release.get('size', 0) > 0 and total != release['size']: raise UpdateError('更新包下载不完整，请重试。')
        target = folder / name
        os.replace(temporary, target); progress(100)
        return str(target)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def scheduled_today(now, last_day, enabled=True):
    return enabled and now.weekday() in (0, 2, 4) and now.date().isoformat() != last_day


def main():
    def interrupted(signum, frame): raise UpdateError('下载已取消。')
    signal.signal(signal.SIGTERM, interrupted)
    try:
        command = json.load(sys.stdin)
        if command['action'] == 'check': result = check(command['current'], command['platform'], command['architecture'], command.get('token', ''))
        elif command['action'] == 'download': result = download(command['release'], command['destination'], token=command.get('token', ''))
        else: raise UpdateError('未知更新操作。')
        print(json.dumps({'ok': True, 'result': result}, ensure_ascii=False))
    except Exception as error:
        message = str(error) if isinstance(error, UpdateError) else '更新操作失败，请检查网络与下载目录权限后重试。'
        print(json.dumps({'ok': False, 'error': message}, ensure_ascii=False))

if __name__ == '__main__': main()
