"""Windows process discovery and task cleanup, loaded only on Windows."""
import os
import subprocess
import psutil


def listeners():
    rows = {}
    for connection in psutil.net_connections(kind='tcp'):
        pid = connection.pid
        if connection.status != psutil.CONN_LISTEN or not pid or pid in (0, 4, os.getpid(), os.getppid()):
            continue
        row = rows.setdefault(pid, {'pid': pid, 'name': '进程 ' + str(pid), 'ports': [], 'command': '', 'directory': ''})
        if connection.laddr.port not in row['ports']:
            row['ports'].append(connection.laddr.port)
    for pid in list(rows):
        row = rows[pid]
        try:
            process = psutil.Process(pid)
            row['name'] = process.name()
            try: row['command'] = subprocess.list2cmdline(process.cmdline())
            except psutil.AccessDenied: pass
            try: row['directory'] = process.cwd()
            except psutil.AccessDenied: pass
        except psutil.NoSuchProcess:
            del rows[pid]
        except psutil.AccessDenied:
            pass
        row['ports'].sort()
    return sorted(rows.values(), key=lambda row: row['pid'])


def stop_tree(pid):
    try:
        parent = psutil.Process(pid)
        targets = parent.children(recursive=True)
        # Stop the parent before descendants so the shell cannot create more work.
        targets.insert(0, parent)
        for process in targets:
            try: process.terminate()
            except psutil.NoSuchProcess: pass
        _, alive = psutil.wait_procs(targets, timeout=4)
        for process in alive:
            try: process.kill()
            except psutil.NoSuchProcess: pass
        _, alive = psutil.wait_procs(alive, timeout=2)
        if alive: raise RuntimeError('部分子进程未停止，请检查权限')
    except psutil.NoSuchProcess:
        pass
