from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QCloseEvent,
    QKeyEvent,
    QPainter,
    QPaintEvent,
    QPalette,
    QPixmap,
)
from PySide6.QtWidgets import QWidget
from texture_courier import Texture

from lltexturecache_browser_qt.checkerboard import checkerboard
from lltexturecache_browser_qt.formatting import format_count, format_size

WINDOW_SIZE = 480

# what the title says with nothing to say anything about
WINDOW_TITLE = "Preview"


def preview_title(texture: Texture, natural: QSize) -> str:
    dimensions = f"{format_count(natural.width())} × {format_count(natural.height())}"

    # the shape of a texture is not known until it has been decoded
    about = ", ".join(
        part for part in (dimensions if not natural.isEmpty() else "", format_size(texture.image_size)) if part
    )

    return f"{texture.uuid} ({about})"


class PreviewWindow(QWidget):
    closed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Tool)

        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAutoFillBackground(True)
        self.setBackgroundRole(QPalette.ColorRole.Base)

        # what the window opens at with no geometry of its own to restore
        self.resize(WINDOW_SIZE, WINDOW_SIZE)

        self._pixmap = QPixmap()
        self._natural = QSize()
        self._message = ""

        self.setWindowTitle(WINDOW_TITLE)

    def present(self) -> None:
        self.show()
        self.raise_()

    def closeEvent(self, event: QCloseEvent) -> None:
        super().closeEvent(event)

        self.closed.emit()

    def clear(self) -> None:
        self.setWindowTitle(WINDOW_TITLE)
        self.set_image(QPixmap(), QSize(), "No selection")

    def show_texture(
        self,
        texture: Texture,
        decoded: tuple[QPixmap, QSize] | None,
        standing: tuple[QPixmap, QSize] | None,
    ) -> None:
        pixmap, natural = (decoded or standing) or (QPixmap(), QSize())

        self.setWindowTitle(preview_title(texture, natural))

        message = "Could not decode" if decoded is not None else "Decoding..."

        self.set_image(pixmap, natural, message)

    def set_image(self, pixmap: QPixmap, natural: QSize, message: str) -> None:
        self._pixmap = pixmap
        self._natural = natural
        self._message = message

        self.update()

    def image_rect(self) -> QRect:
        shape = self._natural if not self._natural.isEmpty() else self._pixmap.size()

        fitted = shape.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)

        rect = QRect(0, 0, fitted.width(), fitted.height())
        rect.moveCenter(self.rect().center())

        return rect

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)

        if self._pixmap.isNull():
            painter.setPen(self.palette().placeholderText().color())
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._message)
        else:
            target = self.image_rect()

            if self._pixmap.hasAlphaChannel():
                painter.fillRect(target, QBrush(checkerboard()))

            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(target, self._pixmap)

        painter.end()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Escape):
            self.close()
            return

        super().keyPressEvent(event)
