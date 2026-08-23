from PySide6.QtCore import QByteArray, QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QCloseEvent,
    QGuiApplication,
    QKeyEvent,
    QPainter,
    QPaintEvent,
    QPalette,
    QPixmap,
)
from PySide6.QtWidgets import QWidget
from texture_courier import Texture

from lltexturecache_viewer_gui.checkerboard import checkerboard
from lltexturecache_viewer_gui.formatting import format_count, format_size

WINDOW_SIZE = 480
WINDOW_MIN_SIZE = 320

# how much of the screen a window may take when it sizes itself to a texture
# larger than the screen it opened on
SCREEN_SHARE = 0.8

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

        self.resize(WINDOW_SIZE, WINDOW_SIZE)

        self._pixmap = QPixmap()
        self._natural = QSize()
        self._message = ""

        # whether the window has already been sized to what it is showing. it
        # is only owed that once a showing, or every arrow key would yank the
        # window out from under a size the user had picked for it
        self._sized = True

        # whether the window has a place of its own yet, either one restored
        # from the last session or one it took from the first texture it was
        # given. a window that has one is never sized to a texture again
        self._placed = False

        self.setWindowTitle(WINDOW_TITLE)

    def restore(self, geometry: QByteArray) -> None:
        self._placed = self.restoreGeometry(geometry)

    def present(self) -> None:
        if not self.isVisible():
            self._sized = self._placed

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

        if not self._sized and not natural.isEmpty():
            self._sized = True

            self.fit_window(natural)

        self.update()

    def fit_window(self, natural: QSize) -> None:
        screen = self.screen() or QGuiApplication.primaryScreen()

        if screen is None:
            return

        room = screen.availableGeometry().size() * SCREEN_SHARE
        box = natural

        if box.width() > room.width() or box.height() > room.height():
            box = box.scaled(room, Qt.AspectRatioMode.KeepAspectRatio)

        box = box.expandedTo(QSize(WINDOW_MIN_SIZE, WINDOW_MIN_SIZE))

        parent = self.parentWidget()
        centre = (parent.frameGeometry() if parent is not None else screen.availableGeometry()).center()

        frame = QRect(self.frameGeometry())
        frame.setSize(box + (frame.size() - self.size()))
        frame.moveCenter(centre)

        self.move(frame.topLeft())
        self.resize(box)

        self._placed = True

    def image_rect(self) -> QRect:
        fitted = self._pixmap.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)

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
