"""Canvas-based dashboard components with a shared visual language."""
import tkinter as tk
from tkinter import ttk

BG = '#0e1017'
SIDEBAR = '#13161e'
PANEL = '#161b25'
CONSOLE = '#090c12'
TEXT = '#e8edf7'
MUTED = '#7b879f'
MINT = '#4cdeb8'
ACCENT = '#a094fa'
BORDER = '#222938'


def percent(value): return f'{value:.1f}%' if value is not None else '—'
def memory(value):
    if value is None: return '—'
    return f'{value / 1073741824:.1f} GB' if value >= 1073741824 else f'{value / 1048576:.0f} MB'


def rounded(canvas, x, y, width, height, radius=14, **kwargs):
    r = min(radius, width / 2, height / 2)
    return canvas.create_polygon(x+r,y, x+width-r,y, x+width,y, x+width,y+r,
                                 x+width,y+height-r, x+width,y+height, x+width-r,y+height,
                                 x+r,y+height, x,y+height, x,y+height-r, x,y+r, x,y,
                                 smooth=True, splinesteps=24, **kwargs)


class PerformanceStrip(tk.Canvas):
    def __init__(self, parent):
        super().__init__(parent, height=148, bg=BG, highlightthickness=0)
        self.data = {}; self.bind('<Configure>', lambda _: self.draw())
    def update_data(self, data): self.data = data or {}; self.draw()
    def draw(self):
        self.delete('all')
        width = self.winfo_width()
        gap = 14; card = (width - 2 * gap) / 3
        if card < 120: return
        available = self.data.get('available', False)
        system = self.data.get('system', {}); app = self.data.get('app', {})
        history = self.data.get('history', [])
        entries = [('系统 CPU', system.get('cpuPercent'), f"{self.data.get('cpuCores', 0)} 个逻辑核心 · 整机容量", MINT, [p['cpu'] for p in history if p.get('cpu') is not None]),
                   ('物理内存', system.get('memoryPercent'), memory(system.get('memoryBytes')) + ' / ' + memory(system.get('memoryTotal')), ACCENT, [p['memory'] for p in history if p.get('memory') is not None]),
                   ('LocalDeck 自身', app.get('cpuPercent'), '内存 ' + memory(app.get('memoryBytes')) + ' · ' + percent(app.get('memoryPercent')), '#6da7fa', [])]
        for index, (title, value, detail, color, points) in enumerate(entries):
            x = index * (card + gap)
            rounded(self, x, 0, card, 147, fill=PANEL, outline=BORDER)
            self.create_text(x+20, 22, anchor='w', text=title, fill=MUTED, font=('Segoe UI', 10))
            self.create_oval(x+card-25, 20, x+card-20, 25, fill=color if available else MUTED, outline='')
            if not available: value = None
            self.create_text(x+20, 71, anchor='w', text=percent(value), fill=TEXT, font=('Segoe UI', 27, 'bold'))
            self.create_text(x+20, 120, anchor='w', text=detail if value is not None else '等待性能采样…', fill=MUTED, font=('Segoe UI', 9))
            if len(points) > 1:
                coords = []
                for point_index, point in enumerate(points): coords.extend((x+card-95 + point_index*70/(len(points)-1), 89 - min(100, max(0, point))*0.35))
                self.create_line(*coords, fill=color, width=2, smooth=False)
            else:
                self.create_oval(x+card-66, 53, x+card-30, 89, outline=BORDER, width=4)
                if value: self.create_arc(x+card-66, 53, x+card-30, 89, start=90, extent=-min(100, value)*3.6, style='arc', outline=color, width=4)


class ServiceCards(ttk.Frame):
    """Small Treeview-compatible adapter, so selection/lifecycle logic stays intact."""
    def __init__(self, parent, columns):
        super().__init__(parent)
        self.mode = 'live' if any(c[0] == 'pid' for c in columns) else 'task'
        self.rows = {}; self.resources = {}; self.selected = None; self.draw_pending = False
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, width=360)
        scroll = ttk.Scrollbar(self, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y'); self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda _: self.schedule())
        self.canvas.bind('<Button-1>', self.click)
        self.canvas.bind('<MouseWheel>', lambda event: self.canvas.yview_scroll(-int(event.delta / 120), 'units'))
    def bind(self, sequence=None, func=None, add=None):
        if sequence == '<Double-1>': return self.canvas.bind(sequence, func, add)
        return super().bind(sequence, func, add)
    def get_children(self): return tuple(self.rows)
    def selection(self): return (self.selected,) if self.selected in self.rows else ()
    def selection_set(self, key):
        if key not in self.rows or key == self.selected: return
        self.selected = key; self.schedule(); self.event_generate('<<TreeviewSelect>>')
    def exists(self, key): return key in self.rows
    def delete(self, key):
        self.rows.pop(key, None)
        if self.selected == key: self.selected = None
        self.schedule()
    def item(self, key, values=None):
        if values is not None: self.rows[key] = values; self.schedule()
        return {'values': self.rows.get(key)}
    def insert(self, parent, index, iid, values): self.rows[iid] = values; self.schedule()
    def click(self, event):
        index = int(self.canvas.canvasy(event.y) // 91)
        keys = list(self.rows)
        if 0 <= index < len(keys): self.selection_set(keys[index])
    def schedule(self):
        if self.draw_pending: return
        self.draw_pending = True; self.after_idle(self.draw)
    def draw(self):
        self.draw_pending = False; c = self.canvas; c.delete('all')
        width = max(300, c.winfo_width() - 5)
        c.configure(scrollregion=(0,0,width,max(130,len(self.rows)*91)))
        if not self.rows:
            c.create_text(width/2, 75, text='暂无服务，添加启动项开始工作。', fill=MUTED, font=('Segoe UI', 11)); return
        for index, (key, values) in enumerate(self.rows.items()):
            y = index*91
            selected = self.selected == key
            rounded(c, 0, y, width, 81, fill='#222238' if selected else PANEL, outline='#625b96' if selected else BORDER)
            rounded(c, 15, y+18, 40, 44, radius=11, fill='#16332f', outline='')
            c.create_text(35,y+40,text='›_', fill=MINT,font=('Consolas',15,'bold'))
            name = str(values[0])[:26]
            c.create_text(69,y+27,anchor='w',text=name,fill=TEXT,font=('Segoe UI',11,'bold'))
            subtitle = ('PID '+str(values[1])+'  ·  '+str(values[2])) if self.mode == 'live' else str(values[1])+'  ·  '+str(values[2])
            max_chars = max(14, int((width-210) / 7))
            if len(subtitle) > max_chars: subtitle = subtitle[:max_chars]+'…'
            c.create_text(69,y+54,anchor='w',text=subtitle,fill=MUTED,font=('Consolas',9))
            usage = self.resources.get(key) or {}
            c.create_text(width-20,y+28,anchor='e',text=percent(usage.get('cpuPercent')),fill=TEXT,font=('Segoe UI',11))
            c.create_text(width-20,y+54,anchor='e',text=memory(usage.get('memoryBytes')),fill=MUTED,font=('Consolas',9))


class Inspector(tk.Canvas):
    def __init__(self, parent):
        super().__init__(parent, bg=BG, highlightthickness=0, width=274, height=460)
        self.configure(scrollregion=(0,0,274,454))
        self.bind('<MouseWheel>',lambda event:self.yview_scroll(-int(event.delta/120),'units'))
        self.item = None; self.tag_bind('copy-command','<Button-1>',lambda _:self.copy_command()); self.bind('<Configure>', lambda _: self.draw())
    def copy_command(self):
        if self.item:
            self.clipboard_clear(); self.clipboard_append(self.item.get('command',''))
            self.itemconfigure('copy-command',text='已复制')
    def update_item(self, item): self.item = item; self.draw()
    def draw(self):
        self.delete('all'); width = max(250, self.winfo_width())
        rounded(self, 0, 0, width, 454, fill=PANEL, outline=BORDER)
        self.create_text(20,25,anchor='w',text='服务详情',fill=MUTED,font=('Segoe UI',10))
        self.create_text(width-20,25,anchor='e',text='RUNNING' if self.item else 'WORKSPACE',fill=MINT,font=('Segoe UI',8))
        if not self.item:
            self.create_text(width/2,180,text='选择服务\n查看性能与详细信息',justify='center',fill=MUTED,font=('Segoe UI',11)); return
        item = self.item; usage = item.get('usage') or {}
        self.create_text(20,70,anchor='w',text=item['name'][:23],fill=TEXT,font=('Segoe UI',20,'bold'))
        self.create_text(20,100,anchor='w',text='PID '+str(item['pid']),fill=MUTED,font=('Consolas',9))
        for x, label, value in [(20,'CPU',percent(usage.get('cpuPercent'))),(width/2,'内存 · '+percent(usage.get('memoryPercent')),memory(usage.get('memoryBytes')))]:
            self.create_text(x,135,anchor='w',text=label,fill=MUTED,font=('Segoe UI',9))
            self.create_text(x,161,anchor='w',text=value,fill=TEXT,font=('Segoe UI',16))
        self.create_line(20,190,width-20,190,fill=BORDER)
        self.create_text(20,216,anchor='w',text='监听端口',fill=MUTED,font=('Segoe UI',9))
        self.create_text(20,243,anchor='w',text='  '.join(':'+str(p) for p in item['ports']),fill=MINT,font=('Consolas',10),width=width-40)
        self.create_text(20,279,anchor='w',text='工作目录',fill=MUTED,font=('Segoe UI',9))
        directory = item.get('directory') or '无法读取此进程目录'
        self.create_text(20,296,anchor='nw',text=directory,fill=TEXT,font=('Segoe UI',9),width=width-40)
        self.create_text(width-20,355,anchor='e',text='复制完整命令',fill=ACCENT,font=('Segoe UI',8),tags=('copy-command',))
        self.create_text(20,355,anchor='w',text='启动命令',fill=MUTED,font=('Segoe UI',9))
        command = item.get('command') or '无权限读取'
        if len(command)>160: command=command[:160]+'…'
        self.create_text(20,374,anchor='nw',text=command,fill=MUTED,font=('Consolas',9),width=width-40)
