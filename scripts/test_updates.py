"""Release selection, schedule, package integrity and failure handling."""
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.request import Request
from urllib.error import HTTPError
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import updates


def release(version='0.6.0', tag=None, platform='Windows-x64', suffix='exe'):
    name = f'LocalDeck-{version}-{platform}.{suffix}'
    tag = tag or 'v'+version
    return {'tag_name': tag, 'html_url': updates.RELEASES_URL+'/tag/'+tag,
            'body': 'Release notes', 'draft': False, 'prerelease': False,
            'assets': [{'name': name, 'browser_download_url': updates.RELEASES_URL+'/download/'+tag+'/'+name,
                        'state': 'uploaded', 'digest': 'sha256:'+hashlib.sha256(b'package').hexdigest(), 'size': 7}]}


class UpdatesTests(unittest.TestCase):
    def test_platform_version_and_stable(self):
        windows = release('0.6.0', 'windows-v0.6.0')
        mac = release('0.7.0', 'macos-v0.7.0', 'macOS-arm64', 'dmg')
        beta = release('9.0.0'); beta['prerelease'] = True
        draft = release('8.0.0'); draft['draft'] = True
        all_releases = [mac, beta, draft, release('0.5.0'), windows, release('0.5.10')]
        self.assertEqual(updates.select_release(all_releases, '0.5.9', 'windows', 'x64')['version'], '0.6.0')
        self.assertEqual(updates.select_release(all_releases, '0.5.0', 'macos', 'arm64')['version'], '0.7.0')
        self.assertIsNone(updates.select_release(all_releases, '0.5.0', 'macos', 'x64'))
        self.assertIsNone(updates.select_release(all_releases, '10.0.0', 'windows', 'x64'))
        self.assertEqual(updates.select_release([release('0.5.10')], '0.5.9', 'windows', 'x64')['version'], '0.5.10')
        self.assertIsNone(updates.select_release([release('0.6.0')], '0.6.0', 'windows', 'x64'))

    def test_dont_use_wrong_package_or_external_url(self):
        for modify in [lambda r:r['assets'][0].update(name='Source.zip'),
                       lambda r:r['assets'][0].update(browser_download_url='https://attacker.example/file.exe'),
                       lambda r:r.update(html_url='https://github.com.evil.example/release'),
                       lambda r:r['assets'][0].update(name='LocalDeck-0.9.0-Windows-x64.exe')]:
            value = release(); modify(value)
            self.assertIsNone(updates.select_release([value], '0.5.1', 'windows', 'x64'))

    def test_schedule_local_calendar_and_once_per_day(self):
        monday = datetime(2026, 10, 26, 12)
        for offset in range(7):
            now = monday + timedelta(days=offset)
            self.assertEqual(updates.scheduled_today(now, ''), offset in (0, 2, 4))
            self.assertFalse(updates.scheduled_today(now, now.date().isoformat()))
            self.assertFalse(updates.scheduled_today(now, '', False))

    def test_verified_download_and_cleanup(self):
        selected = updates.select_release([release()], '0.5.1', 'windows', 'x64')
        with tempfile.TemporaryDirectory() as folder:
            progress = []
            with patch.object(updates, 'open_remote', return_value=io.BytesIO(b'package')):
                path = updates.download(selected, folder, progress.append)
            self.assertEqual(Path(path).read_bytes(), b'package'); self.assertEqual(progress[-1], 100)
            # Corrupt transfers leave no partial package and preserve an existing valid download.
            with patch.object(updates, 'open_remote', return_value=io.BytesIO(b'corrupt')):
                with self.assertRaises(updates.UpdateError): updates.download(selected, folder)
            self.assertEqual(Path(path).read_bytes(), b'package')
            self.assertEqual(list((Path(folder)/'LocalDeck Updates').iterdir()), [Path(path)])

    def test_manifest_fallback_and_size(self):
        selected = updates.select_release([release()], '0.5.1', 'windows', 'x64')
        selected['digest'] = ''; selected['checksum'] = updates.RELEASES_URL+'/download/v0.6.0/SHA256SUMS-Windows.txt'
        manifest = hashlib.sha256(b'package').hexdigest()+'  '+selected['name']+'\n'
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(updates, 'open_remote', side_effect=[io.BytesIO(manifest.encode()), io.BytesIO(b'package')]):
                self.assertTrue(Path(updates.download(selected, folder)).is_file())
            selected['size'] = 8
            with patch.object(updates, 'open_remote', side_effect=[io.BytesIO(manifest.encode()), io.BytesIO(b'package')]):
                with self.assertRaises(updates.UpdateError): updates.download(selected, folder)

    def test_missing_checksum_and_path_traversal(self):
        selected = updates.select_release([release()], '0.5.1', 'windows', 'x64')
        with tempfile.TemporaryDirectory() as folder, patch.object(updates, 'open_remote') as network:
            selected['name'] = '../../LocalDeck.exe'
            with self.assertRaises(updates.UpdateError): updates.download(selected, folder)
            network.assert_not_called()
            selected['name'] = 'LocalDeck-0.6.0-Windows-x64.exe'; selected['digest'] = ''
            with self.assertRaises(updates.UpdateError): updates.download(selected, folder)
            network.assert_not_called()

    def test_private_asset_uses_api_and_redirect_drops_token(self):
        source = release(); source['assets'][0]['url'] = 'https://api.github.com/repos/'+updates.REPOSITORY+'/releases/assets/123'
        selected = updates.select_release([source], '0.5.1', 'windows', 'x64')
        with tempfile.TemporaryDirectory() as folder, patch.object(updates, 'open_remote', return_value=io.BytesIO(b'package')) as network:
            updates.download(selected, folder, token='test-only-token')
            network.assert_called_once_with(selected['api'], 'test-only-token')
        request = Request(selected['api'], headers={'Authorization': 'Bearer test-only-token'})
        redirected = updates.GitHubRedirect().redirect_request(request, None, 302, 'Found', {}, 'https://release-assets.githubusercontent.com/package')
        self.assertFalse(redirected.has_header('Authorization'))
        with self.assertRaises(updates.UpdateError):
            updates.GitHubRedirect().redirect_request(request, None, 302, 'Found', {}, 'https://example.com/package')
        with self.assertRaises(updates.UpdateError):
            updates.GitHubRedirect().redirect_request(request, None, 302, 'Found', {}, 'http://github.com/package')

    def test_private_authorization_errors_are_explicit(self):
        for code in (401, 403, 404, 429):
            with patch.object(updates, 'build_opener') as opener:
                opener.return_value.open.side_effect = HTTPError(updates.API_URL, code, 'unavailable', {}, None)
                with self.assertRaises(updates.UpdateError) as context: updates.check('0.5.1', 'windows', 'x64', 'test-only-token')
                self.assertNotIn('test-only-token', str(context.exception))
                request = opener.return_value.open.call_args.args[0]
                self.assertEqual(request.get_header('Authorization'), 'Bearer test-only-token')

    def test_proxy_html_is_error_not_latest(self):
        with patch.object(updates, 'open_remote', return_value=io.BytesIO(b'<html>proxy error</html>')):
            with self.assertRaises(updates.UpdateError): updates.check('0.5.1', 'windows', 'x64')

if __name__ == '__main__': unittest.main()
