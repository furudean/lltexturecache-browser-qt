from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPalette
from PySide6.QtWidgets import QWidget

SCRIM_ALPHA = 200
MESSAGE_SCALE = 1.2


class DropZone(QWidget):
    """just a visual thing. nothing is actually handled here"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._message = ""

        self.hide()

    def offer(self, message: str, box: QRect) -> None:
        self._message = message

        self.setGeometry(box)
        self.show()
        self.raise_()
        self.update()

    def withdraw(self) -> None:
        self.hide()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)

        scrim = QColor(self.palette().color(QPalette.ColorRole.Base))
        scrim.setAlpha(SCRIM_ALPHA)

        painter.fillRect(self.rect(), scrim)

        font = self.font()
        font.setPointSizeF(font.pointSizeF() * MESSAGE_SCALE)

        painter.setFont(font)
        painter.setPen(self.palette().color(QPalette.ColorRole.Text))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._message)

        painter.end()
