"""Connection arguments and saved configuration, without a live server."""
import os
import tempfile
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from windows.ssh import SSHServers, ssh_arguments


class SSHTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def test_arguments(self):
        profile = dict(name='测试', host='2001:db8::1', user='deploy', port='2222', key='/tmp/key with spaces')
        args = ssh_arguments(profile)
        self.assertEqual(args[-1], '2001:db8::1')
        self.assertEqual(args[args.index('-i')+1], '/tmp/key with spaces')
        self.assertEqual(args[args.index('-p')+1], '2222')
        self.assertNotIn('StrictHostKeyChecking=no', args)
        for host in ['-oProxyCommand=bad', 'host\ncommand', 'host name']:
            with self.assertRaises(ValueError): ssh_arguments(dict(profile, host=host))
        for port in ['0', '65536', 'bad']:
            with self.assertRaises(ValueError): ssh_arguments(dict(profile, port=port))

    def test_persistence_and_connect(self):
        with tempfile.TemporaryDirectory() as directory:
            old = os.environ.get('LOCALDECK_DATA_DIR'); os.environ['LOCALDECK_DATA_DIR'] = directory
            try:
                selected = []
                page = SSHServers(selected.append)
                page.profiles = [dict(name='Linux', host='example.org', user='root', port='22', key='')]
                page.persist()
                restored = SSHServers(selected.append)
                self.assertEqual(restored.profiles, page.profiles)
                restored.open(); self.assertEqual(selected, page.profiles)
                self.assertNotIn('password', Path(directory, 'ssh.ini').read_text())
                page.close(); restored.close()
            finally:
                if old is None: os.environ.pop('LOCALDECK_DATA_DIR', None)
                else: os.environ['LOCALDECK_DATA_DIR'] = old

if __name__ == '__main__': unittest.main()
