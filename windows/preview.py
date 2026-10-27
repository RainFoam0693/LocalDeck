"""Explicit demo data for visual review; never used in a production session."""
import math


def fixture():
    def usage(cpu, mb): return {'cpuPercent':cpu, 'memoryBytes':mb*1048576, 'memoryPercent':mb/16384*100}
    listeners = []
    for name, pid, ports, cpu, mb, directory, command in [
        ('node.exe', 15420, [3000], 2.4, 184, r'C:\Users\Developer\Projects\dashboard', 'node node_modules/vite/bin/vite.js --host'),
        ('python.exe', 9284, [8000], 1.1, 96, r'C:\Users\Developer\Projects\api', 'python -m uvicorn main:app --reload'),
        ('node.exe', 17680, [5173], 0.8, 132, r'C:\Users\Developer\Projects\website', 'npm run dev'),
        ('postgres.exe', 6048, [5432], 0.2, 48, r'C:\Program Files\PostgreSQL\data', 'postgres -D data'),
        ('redis-server.exe', 7216, [6379], 0.1, 24, r'C:\Tools\Redis', 'redis-server redis.conf')]:
        listeners.append(dict(name=name, pid=pid, ports=ports, directory=directory, command=command, usage=usage(cpu, mb)))
    return {'listeners':listeners, 'services':[], 'performance':{'available':True, 'cpuCores':16,
        'system':dict(usage(18.6, 7340), memoryTotal=16384*1048576, memoryPercent=44.8), 'app':usage(0.7, 84),
        'history':[{'cpu':18+math.sin(i*.65)*6, 'memory':44.8+math.sin(i*.1)*.4} for i in range(60)]}}
