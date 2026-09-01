from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QCloseEvent,
    QKeyEvent,
    QMouseEvent,
    QMoveEvent,
    QPainter,
    QPaintEvent,
    QPalette,
    QPixmap,
    QResizeEvent,
)
from PySide6.QtWidgets import QWidget
from texture_courier import Texture

from lltexturecache_browser_qt.view.checkerboard import (
    cycle_pane_tone,
    pane_checkerboard,
    pixmap_lightness,
    set_picked_lightness,
)
from lltexturecache_browser_qt.view.formatting import format_count, format_size
from lltexturecache_browser_qt.view.widgets import ClickTracker

WINDOW_SIZE = 480
MIN_PANE_SIZE = 32

# what the title says with nothing to say anything about
WINDOW_TITLE = "Preview"


def nearest(edge: int, length: int, low: int, high: int) -> int:
    return min(max(edge, low), max(high - length + 1, low))


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
        self.setMinimumSize(MIN_PANE_SIZE, MIN_PANE_SIZE)

        # what the window opens at with no geometry of its own to restore
        self.resize(WINDOW_SIZE, WINDOW_SIZE)

        self._pixmap = QPixmap()
        self._message = ""
        self._lightness: float | None = None
        self._click = ClickTracker()

        # the texture the window has been shaped to, which is what keeps a
        # decode landing on top of the stand-in for the same texture from
        # shaping the window a second time
        self._shaped_for: str | None = None

        # the room every shape is given, which is the area the window was last
        # put at by hand rather than anything a texture has asked for, and the
        # middle of that area, which every shape is kept over
        self._box = QSize(WINDOW_SIZE, WINDOW_SIZE)
        self._middle: QPoint | None = None
        self._shaping = False

        self.setWindowTitle(WINDOW_TITLE)

    def present(self) -> None:
        self.show()
        self.raise_()

    def closeEvent(self, event: QCloseEvent) -> None:
        super().closeEvent(event)

        self.closed.emit()

    def clear(self) -> None:
        self.setWindowTitle(WINDOW_TITLE)

        self._shaped_for = None

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

        # a texture is shown in the shape it was drawn in, which is not known
        # until a decode has landed, and is taken once, leaving whatever the
        # window is put at by hand afterwards to stand
        if not natural.isEmpty() and texture.uuid != self._shaped_for:
            self._shaped_for = texture.uuid

            self.shape_window(natural)

    def set_image(self, pixmap: QPixmap, message: str) -> None:
        self._pixmap = pixmap
        self._message = message
        self._lightness = pixmap_lightness(pixmap)

        set_picked_lightness(self._lightness)

        self.update()

    def room(self) -> QRect | None:
        screen = self.screen()

        return screen.availableGeometry() if screen is not None else None

    def shape_window(self, natural: QSize) -> None:
        # the title bar and the border take room the pane never gets, so what
        # the screen has for a shape is what is left once they have had theirs
        chrome = self.frameGeometry().size() - self.size()
        room = self.room()

        # the area the window was last put at by hand is as much room across and
        # down as any shape is given, and a shape is laid inside it the way a
        # letterbox lays a picture inside a screen: as large as it goes without
        # passing either edge, which is the window's own shape here rather than
        # bars, since the texture is stretched over whatever pane it is given
        box = self._box if room is None else self._box.boundedTo(room.size() - chrome)

        # the box is the one asked for by hand, so a shape that will not go in it
        # is shown as near as it goes without moving it, and one too slight to
        # take hold of is held open by the smallest pane there is
        self._shaping = True

        try:
            self.resize(natural.scaled(box, Qt.AspectRatioMode.KeepAspectRatio))
            self.centre()
        finally:
            self._shaping = False

    def centre(self) -> None:
        frame = self.frameGeometry()
        middle = self._middle if self._middle is not None else frame.center()

        left = middle.x() - frame.width() // 2
        top = middle.y() - frame.height() // 2

        room = self.room()

        # a shape too big to be held over the middle by this is left on the
        # screen instead, which is worth more than the middle of the box
        if room is not None:
            left = nearest(left, frame.width(), room.left(), room.right())
            top = nearest(top, frame.height(), room.top(), room.bottom())

        self.move(left, top)

    def remember_box(self) -> None:
        if self._shaping:
            return

        self._box = self.size()
        self._middle = self.frameGeometry().center()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)

        self.remember_box()

    def moveEvent(self, event: QMoveEvent) -> None:
        super().moveEvent(event)

        self.remember_box()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)

        if self._pixmap.isNull():
            painter.setPen(self.palette().placeholderText().color())
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._message)
        else:
            # the texture is given the whole window, which is kept in the shape
            # the texture was drawn in so that filling it holds that shape
            target = self.rect()

            checkerboard = pane_checkerboard(self._lightness) if self._pixmap.hasAlphaChannel() else None

            if checkerboard is not None:
                painter.fillRect(target, QBrush(checkerboard))

            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(target, self._pixmap)

        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        # an empty window has no texture to cycle the checkerboard behind
        if self._click.press(event, taking=not self._pixmap.isNull()):
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._click.release(event, self.rect()):
            cycle_pane_tone()
            return

        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Escape):
            self.close()
            return

        super().keyPressEvent(event)
