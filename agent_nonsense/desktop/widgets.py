from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QStyle, QStyleOptionButton, QVBoxLayout, QWidget


def label(text, name="", muted=False):
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    if muted:
        widget.setProperty("muted", True)
    return widget


def button(text, callback=None, primary=False):
    widget = QPushButton(text)
    widget.setProperty("primary", primary)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if callback:
        widget.clicked.connect(callback)
    return widget


def row(*widgets):
    layout = QHBoxLayout()
    layout.setSpacing(12)
    for widget in widgets:
        if widget is None:
            layout.addStretch()
        else:
            layout.addWidget(widget)
    return layout


class Card(QFrame):
    def __init__(self, title="", subtitle="", hero=False):
        super().__init__()
        self.setObjectName("heroCard" if hero else "card")
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(22, 20, 22, 20)
        self.box.setSpacing(14)
        if title:
            self.box.addWidget(label(title, "cardTitle"))
        if subtitle:
            text = label(subtitle, muted=True)
            text.setWordWrap(True)
            self.box.addWidget(text)


class CheckBox(QCheckBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        if self.isChecked():
            option = QStyleOptionButton()
            self.initStyleOption(option)
            rect = self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, self)
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor("white"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            path = QPainterPath()
            path.moveTo(rect.left() + 4, rect.center().y())
            path.lineTo(rect.left() + 8, rect.bottom() - 5)
            path.lineTo(rect.right() - 4, rect.top() + 5)
            painter.drawPath(path)


ORIGINAL_ICON = Path(__file__).with_name("assets") / "agent-nonsense.ico"


class ProjectLogo(QWidget):
    """Display the repository's original icon without recoloring or redrawing it."""
    def __init__(self, size=150, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.live = False
        self.pixmap = app_icon().pixmap(size, size)
        self.setAccessibleName("豆皮原版标志")

    def set_live(self, live):
        self.live = live
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(4, 4, self.width() - 8, self.height() - 8, self.pixmap)
        if self.live:
            painter.setPen(QPen(QColor("white"), 2))
            painter.setBrush(QColor("#68af91"))
            painter.drawEllipse(QRectF(self.width() - 15, self.height() - 15, 12, 12))


def app_icon():
    return QIcon(str(ORIGINAL_ICON))


def nav_icon(kind):
    pixmap = QPixmap(40, 40)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(2, 2)
    painter.setPen(QPen(QColor("#8978aa"), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    if kind == 0:
        for x, y in ((3, 3), (12, 3), (3, 12), (12, 12)):
            painter.drawRoundedRect(QRectF(x, y, 5, 5), 1, 1)
    elif kind == 1:
        painter.drawLine(3, 7, 7, 10)
        painter.drawLine(7, 10, 3, 13)
        painter.drawLine(11, 13, 17, 13)
    elif kind == 2:
        painter.drawRoundedRect(QRectF(3, 5, 14, 12), 2, 2)
        painter.drawLine(7, 3, 13, 3)
        painter.drawLine(6, 9, 14, 9)
        painter.drawLine(6, 13, 11, 13)
    elif kind == 3:
        painter.drawRoundedRect(QRectF(3, 3, 11, 13), 1, 1)
        painter.drawLine(7, 7, 11, 7)
        painter.drawLine(7, 11, 11, 11)
        painter.drawLine(7, 18, 17, 18)
    elif kind == 4:
        for y, x in ((5, 7), (10, 13), (15, 8)):
            painter.drawLine(3, y, 17, y)
            painter.setBrush(QColor("#fcfcff"))
            painter.drawEllipse(QRectF(x - 2, y - 2, 4, 4))
    else:
        for y, end in ((5, 17), (10, 13), (15, 16)):
            painter.drawLine(4, y, end, y)
    painter.end()
    return QIcon(pixmap)
