"""Windows 11 visual system and public DWM integration for the Qt desktop."""
import ctypes
import sys
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPalette
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout, QWidget

VERSION = '0.5.0'
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
    for name, attribute, value in [('darkCaption', 20, 1), ('roundedCorners', 33, 2), ('mica', 38, 2)]:
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
        painter.setPen(self.color); painter.drawPath(path)


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
        painter.setBrush(QColor('#32414d' if selected else '#333333' if hovered else '#2b2b2b'))
        painter.setPen(QColor('#4b677d' if selected else '#383838')); painter.drawRoundedRect(rect, 6, 6)
        if selected:
            painter.setPen(Qt.NoPen); painter.setBrush(QColor(ACCENT)); painter.drawRoundedRect(QRectF(rect.left()+1, rect.center().y()-12, 3, 24), 1.5, 1.5)
        icon_rect = QRectF(rect.left()+15, rect.center().y()-18, 36, 36)
        painter.setPen(Qt.NoPen); painter.setBrush(QColor('#354857')); painter.drawRoundedRect(icon_rect, 5, 5)
        font = QFont(option.font); font.setPixelSize(15); painter.setFont(font); painter.setPen(QColor(ACCENT)); painter.drawText(icon_rect, Qt.AlignCenter, '>_')
        left = int(rect.left()+65); width = max(15, int(rect.width()-180))
        font.setPixelSize(14); font.setWeight(QFont.DemiBold); painter.setFont(font); painter.setPen(QColor(TEXT))
        painter.drawText(left, int(rect.top()+29), painter.fontMetrics().elidedText(data['title'], Qt.ElideRight, width))
        font.setPixelSize(12); font.setWeight(QFont.Normal); painter.setFont(font); painter.setPen(QColor(MUTED))
        painter.drawText(left, int(rect.top()+51), painter.fontMetrics().elidedText(data['caption'], Qt.ElideRight, width))
        usage = data.get('usage') or {}; painter.setPen(QColor('#b7dfff' if selected else TEXT))
        painter.drawText(QRectF(rect.right()-110, rect.top()+13, 94, 22), Qt.AlignRight | Qt.AlignVCenter, percent(usage.get('cpuPercent')))
        painter.setPen(QColor(MUTED)); painter.drawText(QRectF(rect.right()-110, rect.top()+36, 94, 22), Qt.AlignRight | Qt.AlignVCenter, memory(usage.get('memoryBytes')))
        painter.restore()
