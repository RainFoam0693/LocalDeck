"""Top navigation with a moving lens over a separately rendered content layer."""
import math

from PySide6.QtCore import QEvent, QEasingCurve, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QTabBar

from windows import fluent


class GlassNavigation(QTabBar):
    def __init__(self, titles):
        super().__init__()
        self.setAccessibleName('工作空间页面')
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(488, 48)
        self.setDrawBase(False)
        self.setFocusPolicy(Qt.StrongFocus)
        self._position = 0.0
        self._lift = 0.0
        self._dragging = False
        self._layer = None
        self._layer_key = None
        for title in titles:
            self.addTab(title)
        self._slide = self._animation('_position', 260, QEasingCurve.OutBack)
        self._raise = self._animation('_lift', 180, QEasingCurve.OutCubic)
        self.currentChanged.connect(self._settle)

    def _animation(self, attribute, duration, easing):
        animation = QVariantAnimation(self)
        animation.setDuration(duration)
        animation.setEasingCurve(easing)

        def frame(value):
            setattr(self, attribute, value)
            self.update()

        animation.valueChanged.connect(frame)
        return animation

    def _animate(self, animation, start, end):
        animation.stop()
        animation.setStartValue(float(start))
        animation.setEndValue(float(end))
        animation.start()

    def _settle(self, index):
        if index >= 0:
            self._animate(self._slide, self._position, index)

    def _slot_width(self):
        return (self.width() - 12) / self.count()

    def tabRect(self, index):
        return QRectF(6 + index * self._slot_width(), 6, self._slot_width(), 36).toAlignedRect()

    def _drag_to(self, x):
        self._position = max(0, min(self.count() - 1, (x - 6) / self._slot_width() - .5))
        self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        self.setFocus(Qt.MouseFocusReason)
        self._dragging = True
        self._slide.stop()
        self._drag_to(event.position().x())
        self._animate(self._raise, self._lift, 1)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._drag_to(event.position().x())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            self._drag_to(event.position().x())
            index = round(self._position)
            if index == self.currentIndex():
                self._settle(index)
            else:
                self.setCurrentIndex(index)
            self._animate(self._raise, self._lift, 0)

    def event(self, event):
        if event.type() == QEvent.UngrabMouse and getattr(self, '_dragging', False):
            self._dragging = False
            self._settle(self.currentIndex())
            self._animate(self._raise, self._lift, 0)
        return super().event(event)

    def _scene(self):
        dark = fluent.DARK
        dpr = self.devicePixelRatioF()
        key = (dark, dpr, self.size(), self.font().key(), self.currentIndex())
        if self._layer is not None and key == self._layer_key:
            return self._layer
        scene = QPixmap(round(self.width() * dpr), round(self.height() * dpr))
        scene.setDevicePixelRatio(dpr)
        scene.fill(Qt.transparent)
        painter = QPainter(scene)
        painter.setRenderHint(QPainter.Antialiasing)
        track = QRectF(1, 5, self.width()-2, self.height()-10)
        fill = QLinearGradient(track.topLeft(), track.bottomLeft())
        fill.setColorAt(0, QColor('#343d4c' if dark else '#ffffff'))
        fill.setColorAt(1, QColor('#242933' if dark else '#e2eaf4'))
        painter.setBrush(fill)
        painter.setPen(QColor('#535d6a' if dark else '#cbd6e4'))
        painter.drawRoundedRect(track, 19, 19)
        for index in range(self.count()):
            painter.setPen(QColor(fluent.ACCENT if index == self.currentIndex() else fluent.TEXT))
            icon = ('services', 'launch', 'terminal', 'ssh')[index]
            rect = self.tabRect(index)
            text = self.tabText(index)
            width = self.fontMetrics().horizontalAdvance(text)
            x = rect.center().x() - (width + 22) / 2
            y = rect.center().y()
            self._draw_icon(painter, icon, x, y)
            painter.drawText(QRectF(x + 22, rect.y(), width + 2, rect.height()), Qt.AlignVCenter, text)
        painter.end()
        self._layer_key, self._layer = key, scene
        return scene

    @staticmethod
    def _draw_icon(painter, icon, x, y):
        painter.save()
        painter.translate(x, y-8)
        painter.setBrush(Qt.NoBrush)
        if icon == 'services':
            for dx in (0, 8):
                for dy in (0, 8):
                    painter.drawRoundedRect(QRectF(dx+1, dy+1, 5, 5), 1, 1)
        elif icon == 'ssh':
            for dy in (1, 9):
                painter.drawRoundedRect(QRectF(1, dy, 14, 5), 1, 1)
                painter.drawPoint(4, dy+2)
        else:
            painter.drawRoundedRect(QRectF(1, 2, 14, 12), 2, 2)
            painter.drawLine(5, 5, 8, 8)
            painter.drawLine(8, 8, 5, 11)
            if icon == 'terminal':
                painter.drawLine(9, 11, 12, 11)
        painter.restore()

    def paintEvent(self, event):
        scene = self._scene()
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        painter.drawPixmap(0, 0, scene)
        slot = self._slot_width()
        width = slot - 5 + 7 * self._lift
        height = 31 + 15 * self._lift
        center = 6 + (self._position + .5) * slot
        lens = QRectF(center - width / 2, (self.height()-height)/2, width, height)
        path = QPainterPath()
        path.addRoundedRect(lens, height/2, height/2)
        painter.save()
        painter.setClipPath(path)
        painter.fillRect(lens, QColor('#252b36' if fluent.DARK else '#edf3fb'))
        dpr = scene.devicePixelRatio()
        # Each strip samples the scene with a different magnification. The
        # change near the rim bends details beneath a lens crossing a tab.
        for row in range(math.ceil(height)):
            v = (row + .5) / height * 2 - 1
            zoom = 1 + (.06 + .27*self._lift) * (.65 + .35*v*v)
            sample_width = width / zoom
            sample_y = self.height()/2 + v * height / (2*zoom)
            source = QRectF((center-sample_width/2)*dpr, (sample_y-.5/zoom)*dpr,
                            sample_width*dpr, dpr/zoom)
            painter.drawPixmap(QRectF(lens.x(), lens.y()+row, width, 1), scene, source)
        shine = QLinearGradient(lens.topLeft(), lens.bottomLeft())
        shine.setColorAt(0, QColor(255, 255, 255, 75))
        shine.setColorAt(.46, QColor(255, 255, 255, 7))
        shine.setColorAt(1, QColor(104, 177, 228, 43))
        painter.fillRect(lens, shine)
        painter.restore()
        painter.setPen(QPen(QColor(255, 255, 255, 145), 1.1))
        painter.drawPath(path)
        if self.hasFocus():
            painter.setPen(QPen(QColor(fluent.ACCENT), 1, Qt.DotLine))
            focus = QRectF(self.tabRect(self.currentIndex())).adjusted(3, 3, -3, -3)
            painter.drawRoundedRect(focus, 14, 14)
