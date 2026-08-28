from PySide6.QtCore import QAbstractItemModel, QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QIcon,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPalette,
    QPen,
    QResizeEvent,
    QShowEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)

from lltexturecache_browser_qt.images import THUMBNAIL_SIZE
from lltexturecache_browser_qt.model import INCOMPLETE_ROLE, SIMPLE_ROLE, Index

CELL_PADDING = 14

# how far the empty grid's message may run before it wraps, so a window dragged
# wide reads as a line of text in the middle of it rather than as a banner
MESSAGE_WIDTH = 320

# the ring an entry the cache never finished downloading is picked out with. an
# amber saturated enough to hold its own against a texture of any lightness,
# since it is drawn over the image rather than over the background
INCOMPLETE_COLOR = QColor(0xEF, 0x7C, 0x14)
INCOMPLETE_WEIGHT = 2

SIMPLE_COLOR = QColor(0x33, 0x33, 0x33)
SIMPLE_GROUND = QColor(0xFF, 0xFF, 0xFF, 0xB0)
SIMPLE_WEIGHT = 2
SIMPLE_DASH = 2.5


def icon_mode(state: QStyle.StateFlag) -> QIcon.Mode:
    if not (state & QStyle.StateFlag.State_Enabled):
        return QIcon.Mode.Disabled

    return QIcon.Mode.Selected if state & QStyle.StateFlag.State_Selected else QIcon.Mode.Normal


class CellDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: Index) -> None:
        cell = QStyleOptionViewItem(option)
        self.initStyleOption(cell, index)

        icon = QIcon(cell.icon)
        cell.icon = QIcon()
        cell.showDecorationSelected = True

        style = cell.widget.style() if cell.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, cell, painter, cell.widget)

        icon.paint(painter, option.rect, Qt.AlignmentFlag.AlignCenter, icon_mode(cell.state))

        incomplete = bool(index.data(INCOMPLETE_ROLE))

        if index.data(SIMPLE_ROLE):
            self.mark_simple(painter, icon, option.rect, INCOMPLETE_WEIGHT if incomplete else 0)

        if incomplete:
            self.mark_incomplete(painter, icon, option.rect)

    def image_rect(self, icon: QIcon, rect: QRect, weight: float, inset: float) -> QRectF | None:
        drawn = QRect(QPoint(), icon.actualSize(rect.size()))

        if drawn.isEmpty():
            return None

        drawn.moveCenter(rect.center())

        room = inset + weight / 2

        return QRectF(drawn).adjusted(room, room, -room, -room)

    def mark_incomplete(self, painter: QPainter, icon: QIcon, rect: QRect) -> None:
        box = self.image_rect(icon, rect, INCOMPLETE_WEIGHT, 0)

        if box is None:
            return

        painter.save()
        painter.setPen(QPen(INCOMPLETE_COLOR, INCOMPLETE_WEIGHT))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(box)
        painter.restore()

    def mark_simple(self, painter: QPainter, icon: QIcon, rect: QRect, inset: float) -> None:
        box = self.image_rect(icon, rect, SIMPLE_WEIGHT, inset)

        if box is None:
            return

        dashed = QPen(SIMPLE_COLOR, SIMPLE_WEIGHT, Qt.PenStyle.CustomDashLine)
        dashed.setDashPattern([SIMPLE_DASH, SIMPLE_DASH])

        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # the pale ring goes down whole and the dark one dashes over it, so a
        # blank of any lightness has one of the two to show it against
        painter.setPen(QPen(SIMPLE_GROUND, SIMPLE_WEIGHT))
        painter.drawRect(box)

        painter.setPen(dashed)
        painter.drawRect(box)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: Index) -> QSize:
        return QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE)


class EmptyState(QLabel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.setForegroundRole(QPalette.ColorRole.Text)

    def set_message(self, message: str) -> None:
        self.setText(message)

        self.setWordWrap(False)

        width = self.sizeHint().width()
        wraps = width > MESSAGE_WIDTH

        self.setWordWrap(wraps)
        self.setFixedWidth(MESSAGE_WIDTH if wraps else width)

        self.adjustSize()


class TextureGrid(QListView):
    dragged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._pin: int | None = None
        self._dragged = False

        # the splitter the grid sits in makes it draw its frame, which on macOS
        # lands as a hard line across the top of the window under the title bar
        self.setFrameShape(QFrame.Shape.NoFrame)

        # a child of the viewport rather than of the view, so it is clipped to
        # the area the textures are drawn in and not to the frame around it
        self._empty = EmptyState(self.viewport())
        self.verticalScrollBar().rangeChanged.connect(self.apply_pin)
        self.verticalScrollBar().actionTriggered.connect(self.unpin)

        self.sync_empty()

    def set_message(self, message: str) -> None:
        self._empty.set_message(message)

        self.centre_empty()

    def is_empty(self) -> bool:
        model = self.model()

        return model is None or model.rowCount() == 0

    def setModel(self, model: QAbstractItemModel | None) -> None:
        old = self.model()

        if old is not None:
            old.modelReset.disconnect(self.sync_empty)
            old.rowsInserted.disconnect(self.sync_empty)
            old.rowsRemoved.disconnect(self.sync_empty)

        super().setModel(model)

        if model is not None:
            model.modelReset.connect(self.sync_empty)
            model.rowsInserted.connect(self.sync_empty)
            model.rowsRemoved.connect(self.sync_empty)

        self.sync_empty()

    def sync_empty(self) -> None:
        # a grid with textures in it says what it holds by showing them, and
        # the panel would only be laid over the top of them
        self._empty.setVisible(self.is_empty())

    def pin_to_bottom(self) -> None:
        self.pin_to(-1)

    def pin_to(self, place: int) -> None:
        self._pin = place

        self.apply_pin()

    def apply_pin(self) -> None:
        if self._pin is None:
            return

        if self._pin == -1:
            self.scrollToBottom()
        else:
            self.verticalScrollBar().setValue(self._pin)

    def unpin(self) -> None:
        self._pin = None

    def place(self) -> int:
        return self.verticalScrollBar().value()

    def scrollTo(self, index: Index, hint: QListView.ScrollHint = QListView.ScrollHint.EnsureVisible) -> None:
        # something has a particular texture it wants in view, which outranks
        # the standing wish for the end of the grid
        self.unpin()

        super().scrollTo(index, hint)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)

        self.apply_pin()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)

        self.apply_pin()
        self.centre_empty()

    def centre_empty(self) -> None:
        viewport = self.viewport().rect()

        # a viewport too small to hold the panel crops it rather than letting
        # it hang off the edges, so what is left of it stays in the middle
        box = QRect(QPoint(), self._empty.sizeHint().boundedTo(viewport.size()))
        box.moveCenter(viewport.center())

        self._empty.setGeometry(box)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._dragged = False

        self.unpin()

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragged and event.buttons() != Qt.MouseButton.NoButton:
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        dragged, self._dragged = self._dragged, False

        if dragged:
            return

        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        self.unpin()

        super().wheelEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        self.unpin()

        super().keyPressEvent(event)

    def startDrag(self, actions: Qt.DropAction) -> None:
        self._dragged = True

        self.dragged.emit()
