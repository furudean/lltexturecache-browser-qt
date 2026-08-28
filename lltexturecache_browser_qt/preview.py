from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QCloseEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPalette,
    QPixmap,
)
from PySide6.QtWidgets import QWidget
from texture_courier import Texture

from lltexturecache_browser_qt.checkerboard import (
    cycle_pane_tone,
    pane_checkerboard,
    pixmap_lightness,
    set_picked_lightness,
)
from lltexturecache_browser_qt.formatting import format_count, format_size

WINDOW_SIZE = 480

# what the title says with nothing to say anything about
WINDOW_TITLE = "Preview"


def preview_title(texture: Texture, natural: QSize) -> str:
    dimensions = f"{format_count(natural.width())} × {format_count(natural.height())}"

    # the shape of a texture is not known until it has been decoded
    about = ", ".join(
        part
        for part in (
            dimensions if not natural.isEmpty() else "",
            format_size(texture.image_size),
            "" if texture.whole() else "incomplete",
        )
        if part
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
        self._message = ""
        self._lightness: float | None = None
        self._pressed = False

        self.setWindowTitle(WINDOW_TITLE)

    def present(self) -> None:
        self.show()
        self.raise_()

    def closeEvent(self, event: QCloseEvent) -> None:
        super().closeEvent(event)

        self.closed.emit()

    def clear(self) -> None:
        self.setWindowTitle(WINDOW_TITLE)
        self.set_image(QPixmap(), "No selection")

    def show_texture(
        self,
        texture: Texture,
        decoded: tuple[QPixmap, QSize] | None,
        standing: tuple[QPixmap, QSize] | None,
    ) -> None:
        pixmap, natural = (decoded or standing) or (QPixmap(), QSize())

        self.setWindowTitle(preview_title(texture, natural))

        if not texture.whole():
            message = "Texture incomplete"
        else:
            message = "Could not decode" if decoded is not None else "Decoding..."

        self.set_image(pixmap, message)

    def set_image(self, pixmap: QPixmap, message: str) -> None:
        self._pixmap = pixmap
        self._message = message
        self._lightness = pixmap_lightness(pixmap)

        set_picked_lightness(self._lightness)

        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)

        if self._pixmap.isNull():
            painter.setPen(self.palette().placeholderText().color())
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._message)
        else:
            target = self.rect()

            checkerboard = pane_checkerboard(self._lightness) if self._pixmap.hasAlphaChannel() else None

            if checkerboard is not None:
                painter.fillRect(target, QBrush(checkerboard))

            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(target, self._pixmap)

        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._pressed = event.button() == Qt.MouseButton.LeftButton and not self._pixmap.isNull()

        if self._pressed:
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        pressed, self._pressed = self._pressed, False

        if pressed and event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            cycle_pane_tone()
            return

        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Escape):
            self.close()
            return

        super().keyPressEvent(event)
