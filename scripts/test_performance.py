"""Resource math, PID reuse, protected processes and live collector regression."""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.performance import process_usage, aggregate, Sampler

base = {'identity': 'first', 'cpuTime': 10}
assert process_usage({'identity':'first','cpuTime':12},base,2,4) == 25
assert process_usage({'identity':'new','cpuTime':300},base,2,4) is None
assert process_usage({'identity':'first','cpuTime':None},base,2,4) is None
assert process_usage({'identity':'first','cpuTime':9},base,2,4) == 0
rows = {1:{'parent':0,'cpuPercent':10,'memoryBytes':100},2:{'parent':1,'cpuPercent':20,'memoryBytes':200},3:{'parent':2,'cpuPercent':5,'memoryBytes':50},4:{'parent':0,'cpuPercent':8,'memoryBytes':80}}
assert aggregate(rows,[1],1000,True) == {'cpuPercent':35,'memoryBytes':350,'memoryPercent':35}
assert aggregate(rows,[1],1000,False)['cpuPercent'] == 10
assert aggregate(rows,[9],1000)['memoryBytes'] is None
collector=Sampler()
try:
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        data=collector.snapshot()
        if data['available'] and data['system']['cpuPercent'] is not None: break
        time.sleep(.2)
    assert data['available'], data
    assert 0 <= data['system']['cpuPercent'] <= 100, data
    assert 0 < data['system']['memoryPercent'] <= 100, data
    assert data['system']['memoryTotal'] > 0
    assert data['app']['memoryBytes'] > 0, data
    assert len(data['history']) >= 2
    print('PASS: CPU normalization, PID reuse, missing permissions, tree aggregation, live CPU/memory/application sampling')
finally: collector.stop_event.set(); collector.thread.join(timeout=6)
