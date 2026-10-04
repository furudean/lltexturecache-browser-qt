from dataclasses import dataclass, field

from PySide6.QtCore import (
    QAbstractItemModel,
    QModelIndex,
    QPersistentModelIndex,
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    Signal,
)
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

from lltexturecache_browser_qt.grid.model import INCOMPLETE_ROLE, SIMPLE_ROLE, Index, TextureModel
from lltexturecache_browser_qt.view.cellsize import cell_size
from lltexturecache_browser_qt.view.widgets import BORDER_WEIGHT, border_color

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

        self.mark_border(painter, icon, option.rect, cell.palette)

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

    def mark_border(self, painter: QPainter, icon: QIcon, rect: QRect, palette: QPalette) -> None:
        weight = BORDER_WEIGHT / painter.device().devicePixelRatioF()
        box = self.image_rect(icon, rect, weight, 0)

        if box is None:
            return

        painter.save()
        painter.setPen(QPen(border_color(palette), weight))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(box)
        painter.restore()

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
        size = cell_size()

        return QSize(size, size)


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


@dataclass(frozen=True)
class Anchor:
    index: Index
    offset: int


# the scroll bar's value is a pixel offset, and once rows are hidden or let
# back in it points at other textures, or past the end. the scroll is kept by
# the texture at the top of the view instead, and when that texture is gone
# too, the nearest one after it that is still shown takes its place
@dataclass
class KeptScroll:
    # the texture at the top of the view, then every texture after it in order
    uuids: list[str] = field(default_factory=list)

    # how far down the viewport the first of them sat
    offset: int = 0

    # held on the end, which follows new rows rather than any one texture
    at_end: bool = False

    @classmethod
    def taken(cls, model: TextureModel, row: int, offset: int) -> "KeptScroll":
        return cls([model.texture(after).uuid for after in range(row, model.rowCount())], offset)

    def row(self, model: TextureModel) -> int | None:
        return next((row for uuid in self.uuids if (row := model.row(uuid)) is not None), None)


class TextureGrid(QListView):
    dragged = Signal()
    previewed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._pinned = False
        self._anchor: Anchor | None = None
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
        self._pinned = True

        self.apply_pin()

    def apply_pin(self) -> None:
        if self._pinned:
            self.scrollToBottom()

    def unpin(self) -> None:
        # the view has been moved on purpose, so neither the place it was held
        # at nor the cell it was looking at describes it any more
        self._pinned = False
        self._anchor = None

    def kept_scroll(self) -> KeptScroll:
        if self._pinned:
            return KeptScroll(at_end=True)

        model = self.model()
        index = self.topmost()

        if not (isinstance(model, TextureModel) and index.isValid()):
            return KeptScroll()

        return KeptScroll.taken(model, index.row(), self.visualRect(index).top() - self.viewport().rect().top())

    def restore_scroll(self, kept: KeptScroll) -> None:
        if kept.at_end:
            self.pin_to_bottom()
            return

        model = self.model()

        if not isinstance(model, TextureModel):
            return

        row = kept.row(model)

        if row is None:
            return

        self.unpin()

        # the rows are laid out lazily, and the row's place is not known until they are
        self.executeDelayedItemsLayout()
        self.restore_anchor(Anchor(QPersistentModelIndex(model.index(row, 0)), kept.offset))

    def anchor(self) -> Anchor | None:
        if self._pinned:
            return None

        if self._anchor is None or not self._anchor.index.isValid():
            self._anchor = self.take_anchor()

        return self._anchor

    def take_anchor(self) -> Anchor | None:
        if self.model() is None:
            return None

        index: Index = self.currentIndex()
        viewport = self.viewport().rect()

        if not (index.isValid() and viewport.intersects(self.visualRect(index))):
            index = self.topmost()

        if not index.isValid():
            return None

        return Anchor(QPersistentModelIndex(index), self.visualRect(index).top() - viewport.top())

    def restore_anchor(self, anchor: Anchor | None) -> None:
        if anchor is None or not anchor.index.isValid():
            return

        bar = self.verticalScrollBar()
        top = self.visualRect(anchor.index).top() - self.viewport().rect().top()

        bar.setValue(bar.value() + top - anchor.offset)

    def topmost(self) -> Index:
        viewport = self.viewport().rect()
        stride = self.spacing() + 1
        reach = cell_size() + stride

        for y in range(viewport.top(), viewport.top() + reach, stride):
            for x in range(viewport.left(), viewport.left() + reach, stride):
                index = self.indexAt(QPoint(x, y))

                if index.isValid():
                    return index

        return QModelIndex()

    def scrollTo(self, index: Index, hint: QListView.ScrollHint = QListView.ScrollHint.EnsureVisible) -> None:
        # something has a particular texture it wants in view, which outranks
        # the standing wish for the end of the grid
        self.unpin()

        super().scrollTo(index, hint)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)

        self.apply_pin()

    def resizeEvent(self, event: QResizeEvent) -> None:
        anchor = self.anchor()

        super().resizeEvent(event)

        self.executeDelayedItemsLayout()
        self.restore_anchor(anchor)

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

        if event.key() == Qt.Key.Key_Space:
            self.previewed.emit()
            return

        super().keyPressEvent(event)

    def has_selection(self) -> bool:
        selection = self.selectionModel()

        return selection is not None and bool(selection.selectedIndexes())

    def startDrag(self, actions: Qt.DropAction) -> None:
        self._dragged = True

        self.dragged.emit()
