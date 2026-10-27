"""Low-frequency resource sampler. CPU is normalized to total machine capacity."""
import copy
import ctypes
import os
import re
import subprocess
import threading
import time
from collections import deque


def process_usage(current, previous, elapsed, cores):
    if current.get('cpuTime') is None or not previous or previous.get('cpuTime') is None or current['identity'] != previous['identity'] or elapsed <= 0:
        return None
    return round(max(0.0, min(100.0, (current['cpuTime'] - previous['cpuTime']) / elapsed / max(1, cores) * 100)), 2)


def empty_resource():
    return {'cpuPercent': None, 'memoryBytes': None, 'memoryPercent': None}


def aggregate(rows, roots, total, descendants=False):
    selected = set(roots)
    if descendants:
        while True:
            expanded = selected | {pid for pid, row in rows.items() if row['parent'] in selected}
            if expanded == selected: break
            selected = expanded
    values = [rows[pid] for pid in selected if pid in rows]
    if not values: return empty_resource()
    memory_values = [row['memoryBytes'] for row in values if row['memoryBytes'] is not None]
    cpu_values = [row['cpuPercent'] for row in values if row['cpuPercent'] is not None]
    memory = sum(memory_values) if memory_values else None
    return {'cpuPercent': round(min(100.0, sum(cpu_values)), 2) if cpu_values else None,
            'memoryBytes': memory,
            'memoryPercent': round(memory / total * 100, 2) if memory is not None and total else None}


def output(args):
    return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL, timeout=5, env=dict(os.environ, LC_ALL='C'))


class Reader:
    def __init__(self):
        self.windows = os.name == 'nt'
        self.cores = os.cpu_count() or 1
        self.last_ticks = None
        if self.windows:
            import psutil
            self.psutil = psutil
            self.total = psutil.virtual_memory().total
            self.psutil.cpu_percent()
        else:
            self.total = int(output(['/usr/sbin/sysctl', '-n', 'hw.memsize']))
            self.lib = ctypes.CDLL('/usr/lib/libSystem.B.dylib')
            self.lib.mach_host_self.restype = ctypes.c_uint
            self.host = self.lib.mach_host_self()
            self.lib.host_statistics.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]

    def read(self):
        if self.windows:
            memory = self.psutil.virtual_memory()
            system = {'cpuPercent': self.psutil.cpu_percent(), 'memoryBytes': memory.total - memory.available,
                      'memoryPercent': round((memory.total - memory.available) / memory.total * 100, 2), 'memoryTotal': memory.total}
            rows = {}
            for process in self.psutil.process_iter(['pid', 'ppid', 'name', 'create_time', 'memory_info', 'cpu_times'], ad_value=None):
                info = process.info
                if info['pid'] == 0: continue
                cpu = info['cpu_times']
                rows[info['pid']] = {'parent': info['ppid'], 'name': info['name'], 'identity': info['create_time'],
                                    'memoryBytes': info['memory_info'].rss if info['memory_info'] else None,
                                    'cpuTime': cpu.user + cpu.system if cpu else None}
            return system, rows
        ticks = (ctypes.c_uint * 4)(); count = ctypes.c_uint(4)
        if self.lib.host_statistics(self.host, 3, ticks, ctypes.byref(count)) != 0:
            raise OSError('无法读取系统 CPU 计数')
        current = tuple(ticks)
        cpu = None
        if self.last_ticks:
            delta = [(now - old) & 0xffffffff for now, old in zip(current, self.last_ticks)]
            if sum(delta): cpu = round((sum(delta) - delta[2]) / sum(delta) * 100, 2)
        self.last_ticks = current
        vm = output(['/usr/bin/vm_stat'])
        page_size = int(re.search(r'page size of (\d+)', vm).group(1))
        pages = {name.strip(): int(value) for name, value in re.findall(r'^([^:\n]+):\s+(\d+)\.', vm, re.M)}
        # Available = free + inactive, including the kernel's reclaimable file cache.
        available = (pages.get('Pages free', 0) + pages.get('Pages inactive', 0)) * page_size
        used = max(0, min(self.total, self.total - available))
        system = {'cpuPercent': cpu, 'memoryBytes': used, 'memoryPercent': round(used / self.total * 100, 2), 'memoryTotal': self.total}
        rows = {}
        ps = output(['/bin/ps', '-axo', 'pid=,ppid=,rss=,time=,lstart=,comm='])
        for line in ps.splitlines():
            parts = line.split(None, 9)
            if len(parts) < 9: continue
            try:
                values = parts[3].split(':')
                seconds = sum(float(value) * 60 ** index for index, value in enumerate(reversed(values)))
                rows[int(parts[0])] = {'parent': int(parts[1]), 'identity': ' '.join(parts[4:9]),
                                      'memoryBytes': int(parts[2]) * 1024, 'cpuTime': seconds, 'name': parts[9] if len(parts) > 9 else ''}
            except (ValueError, IndexError): continue
        return system, rows


class Sampler:
    def __init__(self):
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.rows = {}
        self.history = deque(maxlen=60)
        self.cached = {'available': False, 'system': dict(empty_resource(), memoryTotal=None),
                       'app': empty_resource(), 'history': [], 'updatedAt': None, 'cpuCores': os.cpu_count() or 1}
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        try: reader = Reader()
        except Exception as error:
            with self.lock: self.cached['error'] = str(error)
            return
        previous = {}; previous_time = None
        while not self.stop_event.is_set():
            try:
                system, current = reader.read()
                now = time.monotonic()
                elapsed = now - previous_time if previous_time is not None else 0
                for pid, row in current.items():
                    row['cpuPercent'] = process_usage(row, previous.get(pid), elapsed, reader.cores)
                # Only the UI/API belong to "LocalDeck itself", excluding user jobs and shells.
                own = [os.getpid()]
                parent_name = current.get(os.getppid(), {}).get('name') or ''
                if os.path.basename(parent_name).lower() in ('localdeck', 'localdeck.exe'): own.append(os.getppid())
                if previous_time is None: system['cpuPercent'] = None
                app = aggregate(current, own, reader.total)
                stamp = time.time()
                self.history.append({'time': stamp, 'cpu': system['cpuPercent'], 'memory': system['memoryPercent']})
                with self.lock:
                    self.rows = current
                    self.cached = {'available': True, 'system': system, 'app': app, 'history': list(self.history),
                                   'updatedAt': stamp, 'cpuCores': reader.cores}
                previous = current; previous_time = now
            except Exception as error:
                with self.lock: self.cached['error'] = str(error); self.cached['available'] = False
            self.stop_event.wait(2)

    def snapshot(self):
        with self.lock: return copy.deepcopy(self.cached)

    def usage(self, pid, descendants=False):
        with self.lock:
            return aggregate(self.rows, [pid], self.cached['system']['memoryTotal'], descendants) if pid and self.cached['available'] else empty_resource()
