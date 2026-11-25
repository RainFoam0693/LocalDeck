"""Windows 11 visual system and public DWM integration for the Qt desktop."""
import ctypes
import sys
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPalette
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout, QWidget

VERSION = '1.0.1'
BG = '#202020'
PANEL = '#2b2b2b'
TEXT = '#f5f5f5'
MUTED = '#b0b0b0'
ACCENT = '#76b9ed'

STYLE = '''
QWidget { color: #f5f5f5; font-family: "Segoe UI Variable", "Segoe UI", "Microsoft YaHei UI", sans-serif; font-size: 14px; }
QMainWindow, QDialog { background: #202020; }
QWidget#sidebar { background: transparent; }
QFrame#surface { background: #272727; border: 1px solid #353535; border-radius: 8px; }
QFrame#metric { background: #2b2b2b; border: 1px solid #383838; border-radius: 8px; }
QLabel { background: transparent; border: none; }
QLabel#muted { color: #b0b0b0; font-size: 12px; }
QLabel#heading { font-size: 28px; font-weight: 600; }
QLabel#section { font-size: 16px; font-weight: 600; }
QLabel#value { font-size: 30px; font-weight: 600; }
QLabel#brand { font-size: 18px; font-weight: 600; }
QPushButton { background: #373737; border: 1px solid #484848; border-bottom-color: #303030; border-radius: 5px; padding: 7px 16px; min-height: 20px; }
QPushButton:hover { background: #414141; }
QPushButton:pressed { background: #303030; color: #c7c7c7; }
QPushButton:disabled { background: #2b2b2b; color: #777; border-color: #353535; }
QPushButton:focus { border-color: #76b9ed; }
QPushButton#primary { background: #76b9ed; color: #092438; border-color: #76b9ed; }
QPushButton#primary:hover { background: #90c7f1; }
QPushButton#danger { color: #ffb4ab; }
QPushButton#nav { text-align: left; padding: 10px 16px; background: transparent; border: none; border-radius: 5px; }
QPushButton#nav:hover { background: #303030; }
QPushButton#nav:checked { background: #383838; color: #8dcbfb; border-left: 3px solid #76b9ed; padding-left: 13px; }
QLineEdit { background: #303030; border: 1px solid #454545; border-bottom: 1px solid #aaa; border-radius: 5px; padding: 8px 12px; selection-background-color: #315c7c; }
QLineEdit:focus { background: #202020; border-bottom: 2px solid #76b9ed; padding-bottom: 7px; }
QPlainTextEdit { background: #1c1c1c; border: none; border-radius: 6px; padding: 12px; selection-background-color: #315c7c; }
QListWidget { background: transparent; border: none; outline: 0; padding: 3px; }
QListWidget::item { background: #2e2e2e; border: 1px solid #383838; border-radius: 6px; padding: 12px; margin-bottom: 7px; }
QListWidget::item:hover { background: #353535; }
QListWidget::item:selected { background: #32414d; border: 1px solid #51718a; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 5px 2px; }
QScrollBar::handle:vertical { background: #737373; min-height: 32px; border-radius: 3px; }
QScrollBar::handle:vertical:hover { background: #a0a0a0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px 5px; }
QScrollBar::handle:horizontal { background: #737373; min-width: 32px; border-radius: 3px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QSplitter::handle { background: transparent; width: 12px; }
QTabWidget::pane { border: 1px solid #353535; border-radius: 8px; background: #1c1c1c; top: -1px; }
QTabBar::tab { background: #262626; color: #b0b0b0; border: none; border-radius: 5px; padding: 10px 20px; margin: 0 5px 6px 0; }
QTabBar::tab:selected { background: #3a3a3a; color: #f5f5f5; }
QTabBar::tab:hover { background: #333; }
QMenu { background: #2b2b2b; border: 1px solid #454545; border-radius: 6px; padding: 5px; }
QMenu::item { padding: 7px 24px; border-radius: 4px; }
QMenu::item:selected { background: #414141; }
QToolTip { color: #fff; background: #333; border: 1px solid #555; padding: 6px; }
'''


def setup_theme(app):
    app.setStyle('Fusion')
    font = QFont('Segoe UI Variable', 10)
    font.setFamilies(['Segoe UI Variable', 'Segoe UI', 'Microsoft YaHei UI', 'sans-serif'])
    app.setFont(font)
    palette = QPalette()
    for role, color in [(QPalette.Window, BG), (QPalette.WindowText, TEXT),
                        (QPalette.Base, '#1c1c1c'), (QPalette.AlternateBase, PANEL),
                        (QPalette.Text, TEXT), (QPalette.Button, '#373737'),
                        (QPalette.ButtonText, TEXT), (QPalette.Highlight, '#315c7c'),
                        (QPalette.HighlightedText, TEXT), (QPalette.ToolTipBase, PANEL),
                        (QPalette.ToolTipText, TEXT)]:
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)


def apply_native_window(window):
    """Keep the real non-client frame: Snap Layouts, resize, shadows, caption buttons."""
    if sys.platform != 'win32': return {}
    from ctypes import wintypes
    dwm = ctypes.WinDLL('dwmapi')
    dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    dwm.DwmSetWindowAttribute.restype = ctypes.c_long
    hwnd = int(window.winId())
    results = {}
    # Public Windows 11 attributes; backdrop is available on 22H2 and newer.
    for name, attribute, value in [('darkCaption', 20, int(is_dark())), ('roundedCorners', 33, 2), ('mica', 38, 2)]:
        data = ctypes.c_int(value)
        results[name] = dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(data), ctypes.sizeof(data))
    return results


def label(text='', name=None):
    widget = QLabel(text)
    if name: widget.setObjectName(name)
    widget.setTextFormat(Qt.PlainText)
    return widget


def panel():
    result = QFrame(); result.setObjectName('surface')
    return result


def percent(value): return f'{value:.1f}%' if value is not None else '—'
def memory(value):
    if value is None: return '—'
    return f'{value / 1073741824:.1f} GB' if value >= 1073741824 else f'{value / 1048576:.0f} MB'


class Sparkline(QWidget):
    def __init__(self, color):
        super().__init__(); self.points = []; self.color = QColor(color); self.setFixedHeight(24)
    def paintEvent(self, event):
        if len(self.points) < 2: return
        painter = QPainter(self); painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        for i, point in enumerate(self.points):
            x = i * self.width() / (len(self.points) - 1)
            y = self.height() - 2 - max(0, min(100, point)) / 100 * (self.height() - 4)
            if i: path.lineTo(x, y)
            else: path.moveTo(x, y)
        painter.setPen(QColor(themed(self.color.name()))); painter.drawPath(path)


class MetricCard(QFrame):
    def __init__(self, title, color):
        super().__init__(); self.setObjectName('metric')
        layout = QVBoxLayout(self); layout.setContentsMargins(20, 16, 20, 14); layout.setSpacing(6)
        layout.addWidget(label(title, 'muted'))
        self.value = label('—', 'value'); layout.addWidget(self.value)
        self.caption = label('等待性能采样…', 'muted'); layout.addWidget(self.caption)
        self.chart = Sparkline(color); layout.addWidget(self.chart)
    def update_value(self, value, caption, points):
        self.value.setText(percent(value)); self.caption.setText(caption)
        self.chart.points = points; self.chart.update()


from PySide6.QtWidgets import QStyledItemDelegate, QStyle
from PySide6.QtGui import QPen


class ServiceDelegate(QStyledItemDelegate):
    """Keep accessible list items and keyboard selection, paint a quiet Fluent row."""
    def paint(self, painter, option, index):
        data = index.data(Qt.UserRole+1)
        if not data: return super().paint(painter, option, index)
        painter.save(); painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(option.rect).adjusted(0, 0, -2, -7)
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)
        painter.setBrush(QColor(themed('#32414d' if selected else '#333333' if hovered else '#2b2b2b')))
        painter.setPen(QColor(themed('#4b677d' if selected else '#383838'))); painter.drawRoundedRect(rect, 6, 6)
        if selected:
            painter.setPen(Qt.NoPen); painter.setBrush(QColor(ACCENT)); painter.drawRoundedRect(QRectF(rect.left()+1, rect.center().y()-12, 3, 24), 1.5, 1.5)
        icon_rect = QRectF(rect.left()+15, rect.center().y()-18, 36, 36)
        painter.setPen(Qt.NoPen); painter.setBrush(QColor(themed('#354857'))); painter.drawRoundedRect(icon_rect, 5, 5)
        font = QFont(option.font); font.setPixelSize(15); painter.setFont(font); painter.setPen(QColor(ACCENT)); painter.drawText(icon_rect, Qt.AlignCenter, '>_')
        left = int(rect.left()+65); width = max(15, int(rect.width()-180))
        font.setPixelSize(14); font.setWeight(QFont.DemiBold); painter.setFont(font); painter.setPen(QColor(TEXT))
        painter.drawText(left, int(rect.top()+29), painter.fontMetrics().elidedText(data['title'], Qt.ElideRight, width))
        font.setPixelSize(12); font.setWeight(QFont.Normal); painter.setFont(font); painter.setPen(QColor(MUTED))
        painter.drawText(left, int(rect.top()+51), painter.fontMetrics().elidedText(data['caption'], Qt.ElideRight, width))
        usage = data.get('usage') or {}; painter.setPen(QColor(themed('#b7dfff' if selected else TEXT)))
        painter.drawText(QRectF(rect.right()-110, rect.top()+13, 94, 22), Qt.AlignRight | Qt.AlignVCenter, percent(usage.get('cpuPercent')))
        painter.setPen(QColor(MUTED)); painter.drawText(QRectF(rect.right()-110, rect.top()+36, 94, 22), Qt.AlignRight | Qt.AlignVCenter, memory(usage.get('memoryBytes')))
        painter.restore()


# One token mapping drives widgets, custom painters and the terminal together.
import os
import re
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QSettings, QTimer, Property, QPropertyAnimation, QEasingCurve, QPointF
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QPushButton

DARK = True
LIGHT = {
    '#202020':'#f3f3f3', '#272727':'#ffffff', '#2b2b2b':'#ffffff', '#353535':'#e2e2e2',
    '#383838':'#e5e5e5', '#f5f5f5':'#1a1a1a', '#b0b0b0':'#646464', '#373737':'#ffffff',
    '#484848':'#d6d6d6', '#303030':'#e9e9e9', '#414141':'#f0f0f0', '#c7c7c7':'#777777',
    '#777':'#999999', '#76b9ed':'#0067c0', '#092438':'#ffffff', '#90c7f1':'#1975c5',
    '#ffb4ab':'#b3261e', '#8dcbfb':'#005a9e', '#454545':'#d1d1d1', '#aaa':'#929292',
    '#315c7c':'#cce4f7', '#1c1c1c':'#fafafa', '#2e2e2e':'#ffffff', '#32414d':'#e3effa',
    '#51718a':'#9abfdf', '#737373':'#909090', '#a0a0a0':'#606060', '#262626':'#ececec',
    '#3a3a3a':'#ffffff', '#333':'#eeeeee', '#fff':'#202020', '#555':'#cccccc',
    '#333333':'#f4f4f4', '#4b677d':'#9abfdf', '#354857':'#dceafb', '#b7dfff':'#005a9e',
    '#c0a4ed':'#7651a8', '#87d4bb':'#137c62', '#e5ebf4':'#202020', '#181818':'#fafafa',
}


def themed(color): return color if DARK else LIGHT.get(color, color)
def is_dark(): return DARK


def apply_theme(app, dark):
    global DARK, BG, PANEL, TEXT, MUTED, ACCENT
    DARK = dark
    BG, PANEL, TEXT, MUTED, ACCENT = [themed(c) for c in ['#202020','#2b2b2b','#f5f5f5','#b0b0b0','#76b9ed']]
    palette = QPalette()
    for role, color in [(QPalette.Window, BG), (QPalette.WindowText, TEXT), (QPalette.Base, themed('#1c1c1c')),
                        (QPalette.Text, TEXT), (QPalette.Button, themed('#373737')), (QPalette.ButtonText, TEXT),
                        (QPalette.Highlight, themed('#315c7c')), (QPalette.HighlightedText, TEXT),
                        (QPalette.ToolTipBase, PANEL), (QPalette.ToolTipText, TEXT)]: palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(re.sub(r'#[0-9a-fA-F]{3,6}\b', lambda m:themed(m.group()), STYLE))
    for widget in app.topLevelWidgets():
        if widget.isWindow(): apply_native_window(widget)
        widget.update()


class AppearanceManager(QObject):
    changed = Signal(bool)
    modeChanged = Signal(str)
    def __init__(self, app, persist=True, settings_path=None):
        super().__init__(app); self.app = app
        if persist:
            path = Path(settings_path) if settings_path else Path(os.environ.get('LOCALDECK_DATA_DIR') or Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'.local/share')))/'LocalDeck')/'appearance.ini'
            path.parent.mkdir(parents=True, exist_ok=True)
            self.settings = QSettings(str(path), QSettings.IniFormat)
        else: self.settings = None
        value = self.settings.value('appearance/mode', 'system') if self.settings else 'system'
        self.mode = value if value in ('light','dark','system') else 'system'; self.dark = None
        app.styleHints().colorSchemeChanged.connect(lambda _:self.refresh())
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh); self.timer.start(1500)
        self.refresh()

    def system_dark(self):
        if sys.platform == 'win32':
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
                    return winreg.QueryValueEx(key, 'AppsUseLightTheme')[0] == 0
            except OSError: pass
        return self.app.styleHints().colorScheme() == Qt.ColorScheme.Dark

    def set_mode(self, mode):
        if mode not in ('light','dark','system'): return
        self.mode = mode
        if self.settings: self.settings.setValue('appearance/mode', mode); self.settings.sync()
        self.refresh(); self.modeChanged.emit(mode)

    def refresh(self):
        dark = self.system_dark() if self.mode == 'system' else self.mode == 'dark'
        if dark != self.dark:
            self.dark = dark; apply_theme(self.app, dark); self.changed.emit(dark)


def appearance_icon(kind, color):
    pixmap = QPixmap(40, 40); pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap); painter.setRenderHint(QPainter.Antialiasing); painter.scale(2, 2)
    painter.setPen(QPen(QColor(color), 1.35, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)); painter.setBrush(Qt.NoBrush)
    if kind == 'light':
        import math
        painter.drawEllipse(QRectF(6.5,6.5,7,7))
        for i in range(8):
            a = i*math.pi/4
            painter.drawLine(QPointF(10+6*math.cos(a),10+6*math.sin(a)),QPointF(10+8*math.cos(a),10+8*math.sin(a)))
    elif kind == 'dark':
        path = QPainterPath(); path.moveTo(13.5,3); path.cubicTo(3,-1,0,15,10,17); path.cubicTo(15,18,18,14,17,11); path.cubicTo(10,15,6,7,13.5,3); painter.drawPath(path)
    elif kind == 'settings':
        import math
        points = []
        for i in range(32):
            a = i*math.pi/16; radius = 8 if i % 4 in (1,2) else 6.2
            points.append(QPointF(10+radius*math.cos(a), 10+radius*math.sin(a)))
        path = QPainterPath(); path.moveTo(points[0])
        for point in points[1:]: path.lineTo(point)
        path.closeSubpath(); painter.drawPath(path); painter.drawEllipse(QRectF(7,7,6,6))
    elif kind == 'close':
        painter.drawLine(6,6,14,14); painter.drawLine(14,6,6,14)
    else:
        painter.drawRoundedRect(QRectF(2,3,16,11), 2, 2); painter.drawLine(10,14,10,17); painter.drawLine(6,17,14,17)
    painter.end(); pixmap.setDevicePixelRatio(2); return QIcon(pixmap)


class AppearanceCapsule(QWidget):
    """Three real accessible buttons over one animated, pill-shaped indicator."""
    def __init__(self, manager):
        super().__init__(); self.manager = manager; self.modes = ['light','dark','system']; self._position = float(self.modes.index(manager.mode))
        self.setFixedHeight(38); self.setAccessibleName('外观')
        layout = QHBoxLayout(self); layout.setContentsMargins(4,4,4,4); layout.setSpacing(0); self.buttons = []
        for mode, title in zip(self.modes, ['浅色','深色','跟随系统']):
            button = QPushButton('系统' if mode == 'system' else ''); button.setObjectName('appearanceButton')
            button.setCheckable(True); button.setToolTip(title); button.setAccessibleName(title); button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda checked=False, m=mode:manager.set_mode(m)); layout.addWidget(button, 1); self.buttons.append(button)
        self.animation = QPropertyAnimation(self, b'position', self); self.animation.setDuration(160); self.animation.setEasingCurve(QEasingCurve.OutCubic)
        manager.modeChanged.connect(self.select); manager.changed.connect(lambda _:self.recolor()); self.recolor()
    def get_position(self): return self._position
    def set_position(self, value): self._position = value; self.update()
    position = Property(float, get_position, set_position)
    def select(self, mode):
        self.animation.stop(); self.animation.setStartValue(self._position); self.animation.setEndValue(float(self.modes.index(mode))); self.animation.start(); self.recolor()
    def recolor(self):
        for mode, button in zip(self.modes, self.buttons):
            selected = mode == self.manager.mode; button.setChecked(selected)
            button.setIcon(appearance_icon(mode, ACCENT if selected else MUTED))
            button.setStyleSheet('QPushButton#appearanceButton { background: transparent; border: none; border-radius: 15px; min-height: 0; padding: 3px 1px; color: '+(ACCENT if selected else MUTED)+'; font-size: 11px; } QPushButton#appearanceButton:hover { background: '+themed('#383838')+'; }')
        self.update()
    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.Antialiasing); painter.setPen(QColor(themed('#383838'))); painter.setBrush(QColor(themed('#262626')))
        painter.drawRoundedRect(QRectF(.5,.5,self.width()-1,self.height()-1), self.height()/2, self.height()/2)
        width = (self.width()-8)/3
        painter.setPen(QColor(themed('#484848'))); painter.setBrush(QColor(themed('#3a3a3a')))
        painter.drawRoundedRect(QRectF(4+self._position*width,4,width,self.height()-8), (self.height()-8)/2, (self.height()-8)/2)
