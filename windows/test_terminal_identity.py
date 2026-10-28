import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from windows.terminal_identity import process_label, task_identity

for name, args, expected in [
    ('node.exe', ['node', r'C:\TRSS-Yunzai\app.js'], 'Yunzai'),
    ('node.exe', ['node', r'C:\project\node_modules\vite\bin\vite.js'], 'Vite'),
    ('node', ['node', '/project/node_modules/next/dist/bin/next', 'dev'], 'Next.js'),
    ('Yunzai', ['Yunzai v3.1.7 © 2025–2026 Aozaki Arina'], 'Yunzai'),
    ('python.exe', ['python', r'C:\project\server.py', '--token=private'], 'server.py'),
    ('node', ['node', '/project/invited.js'], 'invited.js'),
    ('sleep', ['sleep', '30'], 'sleep'),
]: assert process_label(name, args) == expected, (name, args)
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
try:
    found = task_identity(os.getpid())
    assert found and found[1] == child.pid, found
finally: child.terminate(); child.wait(timeout=10)
assert task_identity(99999999) is None
print('Terminal identity classification and live process detection passed')
