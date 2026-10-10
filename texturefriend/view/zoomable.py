from math import sqrt

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent, QNativeGestureEvent, QResizeEvent, QTransform, QWheelEvent
from PySide6.QtWidgets import QApplication, QScrollBar, QStyle, QWidget

from texturefriend.view.gestures import WHEEL_STEP, pinch_scale, wheel_scale, wheel_zooms

MAX_ZOOM = 32
ZOOM_STEP = sqrt(2)

WHEEL_PAN = 60

SCROLL_STEPS = 10_000


# the visible part is how much of the content the view spans, as a fraction of
# its width and height
def clamped_offset(offset: QPointF, visible: QPointF) -> QPointF:
    return QPointF(
        min(max(offset.x(), 0.0), max(1 - visible.x(), 0.0)),
        min(max(offset.y(), 0.0), max(1 - visible.y(), 0.0)),
    )


def zoomed_offset(offset: QPointF, zoom: float, new_zoom: float, anchor: QPointF, visible: QPointF) -> QPointF:
    under = offset + anchor / zoom

    return clamped_offset(under - anchor / new_zoom, visible)


def zoom_key(event: QKeyEvent) -> int | None:
    match event.key():
        case Qt.Key.Key_Plus | Qt.Key.Key_Equal:
            return 1
        case Qt.Key.Key_Minus:
            return -1
        case Qt.Key.Key_0:
            return 0

    return None


def wheel_pan(event: QWheelEvent) -> QPointF:
    # a trackpad scrolls by pixels, and a mouse wheel by notches
    if not event.pixelDelta().isNull():
        return event.pixelDelta().toPointF()

    return event.angleDelta().toPointF() * (WHEEL_PAN / WHEEL_STEP)


class ZoomableView(QWidget):
    def __init__(self, parent: QWidget | None = None, flags: Qt.WindowType = Qt.WindowType.Widget) -> None:
        super().__init__(parent, flags)

        self._zoom = 1.0
        self._offset = QPointF()
        self._grab: QPointF | None = None
        self._panning = False

        # the bars take strips of their own along the far edges while zoomed,
        # so they never cover the content
        self._across = QScrollBar(Qt.Orientation.Horizontal, self)
        self._down = QScrollBar(Qt.Orientation.Vertical, self)

        for bar in (self._across, self._down):
            bar.hide()
            bar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            bar.setCursor(Qt.CursorShape.ArrowCursor)
            bar.valueChanged.connect(self.scrolled_action)

    @property
    def zoom(self) -> float:
        return self._zoom

    @property
    def panning(self) -> bool:
        return self._panning

    def can_zoom(self) -> bool:
        return True

    def zoom_changed(self) -> None:
        pass

    def zoom_transform(self) -> QTransform:
        return (
            QTransform()
            .translate(-self._offset.x() * self.width() * self._zoom, -self._offset.y() * self.height() * self._zoom)
            .scale(self._zoom, self._zoom)
        )

    def zoomed_source(self, size: QSize) -> QRectF:
        visible = self.visible()

        return QRectF(
            self._offset.x() * size.width(),
            self._offset.y() * size.height(),
            visible.x() * size.width(),
            visible.y() * size.height(),
        )

    def bar_extent(self) -> int:
        return self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent, None, self._down)

    def view(self) -> QRect:
        if self._zoom == 1.0:
            return self.rect()

        extent = self.bar_extent()

        return self.rect().adjusted(0, 0, -extent, -extent)

    def visible(self) -> QPointF:
        view = self.view()

        return QPointF(view.width() / (self.width() * self._zoom), view.height() / (self.height() * self._zoom))

    def zoom_by(self, factor: float, anchor: QPointF | None = None) -> None:
        if not self.can_zoom():
            return

        zoom = min(max(self._zoom * factor, 1.0), MAX_ZOOM)

        if zoom == self._zoom:
            return

        at = anchor if anchor is not None else QRectF(self.view()).center()
        was, self._zoom = self._zoom, zoom

        self._offset = zoomed_offset(
            self._offset, was, zoom, QPointF(at.x() / self.width(), at.y() / self.height()), self.visible()
        )

        self.sync_cursor()
        self.sync_bars()
        self.update()
        self.zoom_changed()

    def reset_zoom(self) -> None:
        self._zoom = 1.0
        self._offset = QPointF()
        self._grab = None
        self._panning = False

        self.sync_cursor()
        self.sync_bars()
        self.update()
        self.zoom_changed()

    def pan_by(self, moved: QPointF) -> None:
        # the content follows the pointer, so the offset moves against it
        across = self.width() * self._zoom
        down = self.height() * self._zoom

        self._offset = clamped_offset(self._offset - QPointF(moved.x() / across, moved.y() / down), self.visible())

        self.sync_bars()
        self.update()

    def sync_bars(self) -> None:
        view = self.view()

        self._across.setGeometry(0, view.bottom() + 1, view.width(), self.height() - view.height())
        self._down.setGeometry(view.right() + 1, 0, self.width() - view.width(), view.height())

        visible = self.visible()

        for bar, start, seen in (
            (self._across, self._offset.x(), visible.x()),
            (self._down, self._offset.y(), visible.y()),
        ):
            page = round(seen * SCROLL_STEPS)

            # the bars follow the offset here, and only move it when dragged
            held = bar.blockSignals(True)
            bar.setRange(0, SCROLL_STEPS - page)
            bar.setPageStep(page)
            bar.setSingleStep(max(1, page // 10))
            bar.setValue(round(start * SCROLL_STEPS))
            bar.blockSignals(held)

            bar.setVisible(self._zoom > 1.0)

    def scrolled_action(self) -> None:
        offset = QPointF(self._across.value() / SCROLL_STEPS, self._down.value() / SCROLL_STEPS)

        self._offset = clamped_offset(offset, self.visible())

        self.update()

    def sync_cursor(self) -> None:
        if self._zoom == 1.0:
            self.unsetCursor()
        elif self._grab is not None:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        else:
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)

        self._offset = clamped_offset(self._offset, self.visible())

        self.sync_bars()

    def event(self, event: QEvent) -> bool:
        if isinstance(event, QNativeGestureEvent) and (scale := pinch_scale(event)) is not None:
            self.zoom_by(scale, event.position())
            return True

        # the zoom keys belong to the view while it has the keyboard, rather
        # than to any zoom in the menus
        if (
            isinstance(event, QKeyEvent)
            and event.type() == QEvent.Type.ShortcutOverride
            and zoom_key(event) is not None
        ):
            event.accept()
            return True

        return super().event(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if wheel_zooms(event):
            event.accept()
            self.zoom_by(wheel_scale(event, ZOOM_STEP), event.position())
            return

        if self._zoom > 1.0:
            event.accept()
            self.pan_by(wheel_pan(event))
            return

        super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._zoom > 1.0 and event.button() == Qt.MouseButton.LeftButton:
            self._grab = event.position()
            self.sync_cursor()

            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._grab is None:
            super().mouseMoveEvent(event)
            return

        moved = event.position() - self._grab

        # a twitch on the way to a click leaves the content where it is
        if not self._panning and moved.manhattanLength() < QApplication.startDragDistance():
            return

        self._panning = True
        self._grab = event.position()

        self.pan_by(moved)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._grab is not None:
            self._grab = None
            self._panning = False

            self.sync_cursor()

        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        step = zoom_key(event)

        if step == 0:
            self.reset_zoom()
            return

        if step is not None:
            self.zoom_by(ZOOM_STEP**step)
            return

        super().keyPressEvent(event)
