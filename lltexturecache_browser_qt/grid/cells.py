from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field

from PySide6.QtCore import (
    QAbstractItemModel,
    QItemSelection,
    QItemSelectionModel,
    QModelIndex,
    QPersistentModelIndex,
    QPoint,
    QPointF,
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
    QPainterPath,
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

CELL_PADDING = 12

SELECTION_INSET = 3
SELECTION_RADIUS = 6

TEXTURE_RADIUS = SELECTION_RADIUS - SELECTION_INSET

# the least a texture's click target spans either way, so a strip a few pixels
# thin still takes a click as easily as a button does
TARGET_MIN = 24

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
    return QIcon.Mode.Normal if state & QStyle.StateFlag.State_Enabled else QIcon.Mode.Disabled


def slot_size() -> int:
    return cell_size() + SELECTION_INSET * 2


def texture_room(cell: QRect) -> QRect:
    return cell.adjusted(SELECTION_INSET, SELECTION_INSET, -SELECTION_INSET, -SELECTION_INSET)


def image_box(icon: QIcon, cell: QRect) -> QRect | None:
    room = texture_room(cell)
    size = icon.actualSize(room.size())

    if size.isEmpty():
        return None

    # the placement QIcon.paint uses, which moveCenter misses by a pixel
    return QStyle.alignedRect(Qt.LayoutDirection.LeftToRight, Qt.AlignmentFlag.AlignCenter, size, room)


def target_box(box: QRect, cell: QRect) -> QRect:
    grow_x = max(TARGET_MIN - box.width(), 0) // 2
    grow_y = max(TARGET_MIN - box.height(), 0) // 2

    return box.adjusted(-grow_x, -grow_y, grow_x, grow_y) & cell


def frame_box(box: QRect | None, cell: QRect) -> QRect:
    if box is None:
        return cell

    return box.adjusted(-SELECTION_INSET, -SELECTION_INSET, SELECTION_INSET, SELECTION_INSET)


def rounded(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)

    return path


def ring(box: QRect, weight: float, inset: float) -> QPainterPath:
    room = inset + weight / 2

    return rounded(QRectF(box).adjusted(room, room, -room, -room), max(TEXTURE_RADIUS - room, 0))


class CellDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: Index) -> None:
        cell = QStyleOptionViewItem(option)
        self.initStyleOption(cell, index)

        icon = QIcon(cell.icon)
        cell.icon = QIcon()
        cell.showDecorationSelected = True

        selected = bool(cell.state & QStyle.StateFlag.State_Selected)

        # the style's highlight is a square block the texture covers, so the
        # selection is drawn here instead, in the margin around the texture
        cell.state &= ~QStyle.StateFlag.State_Selected

        style = cell.widget.style() if cell.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, cell, painter, cell.widget)

        box = image_box(icon, option.rect)

        if selected:
            self.mark_selected(painter, frame_box(box, option.rect), cell)

        if box is None:
            return

        self.paint_texture(painter, icon, box, icon_mode(cell.state))

        self.mark_border(painter, box, cell.palette)

        incomplete = bool(index.data(INCOMPLETE_ROLE))

        if index.data(SIMPLE_ROLE):
            self.mark_simple(painter, box, INCOMPLETE_WEIGHT if incomplete else 0)

        if incomplete:
            self.mark_incomplete(painter, box)

    def paint_texture(self, painter: QPainter, icon: QIcon, box: QRect, mode: QIcon.Mode) -> None:
        pixmap = icon.pixmap(box.size(), painter.device().devicePixelRatioF(), mode)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        # the brush tiles from its origin, so the pixmap lands where
        # QIcon.paint would put it
        painter.setBrushOrigin(box.topLeft())
        painter.setBrush(pixmap)
        painter.drawPath(rounded(QRectF(box), TEXTURE_RADIUS))
        painter.restore()

    def mark_selected(self, painter: QPainter, rect: QRect, cell: QStyleOptionViewItem) -> None:
        active = cell.state & QStyle.StateFlag.State_Active
        group = QPalette.ColorGroup.Active if active else QPalette.ColorGroup.Inactive

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(cell.palette.color(group, QPalette.ColorRole.Highlight))
        painter.drawRoundedRect(QRectF(rect), SELECTION_RADIUS, SELECTION_RADIUS)
        painter.restore()

    def mark_border(self, painter: QPainter, box: QRect, palette: QPalette) -> None:
        weight = BORDER_WEIGHT / painter.device().devicePixelRatioF()

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(border_color(palette), weight))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(ring(box, weight, 0))
        painter.restore()

    def mark_incomplete(self, painter: QPainter, box: QRect) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(INCOMPLETE_COLOR, INCOMPLETE_WEIGHT))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(ring(box, INCOMPLETE_WEIGHT, 0))
        painter.restore()

    def mark_simple(self, painter: QPainter, box: QRect, inset: float) -> None:
        path = ring(box, SIMPLE_WEIGHT, inset)
        dashed = QPen(SIMPLE_COLOR, SIMPLE_WEIGHT, Qt.PenStyle.CustomDashLine)
        dashed.setDashPattern([SIMPLE_DASH, SIMPLE_DASH])

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # the pale ring goes down whole and the dark one dashes over it, so a
        # blank of any lightness has one of the two to show it against
        painter.setPen(QPen(SIMPLE_GROUND, SIMPLE_WEIGHT))
        painter.drawPath(path)

        painter.setPen(dashed)
        painter.drawPath(path)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: Index) -> QSize:
        size = slot_size()

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
        self._pressed = QPointF()

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
        reach = slot_size() + stride

        for y in range(viewport.top(), viewport.top() + reach, stride):
            for x in range(viewport.left(), viewport.left() + reach, stride):
                index = super().indexAt(QPoint(x, y))

                if index.isValid():
                    return index

        return QModelIndex()

    def indexAt(self, point: QPoint) -> QModelIndex:
        index = super().indexAt(point)

        if not index.isValid():
            return index

        return index if self.target(index).contains(point) else QModelIndex()

    def target(self, index: Index) -> QRect:
        cell = self.visualRect(index)
        box = image_box(QIcon(index.data(Qt.ItemDataRole.DecorationRole)), cell)

        return cell if box is None else target_box(box, cell)

    def setSelection(self, rect: QRect, command: QItemSelectionModel.SelectionFlag) -> None:
        box = rect.normalized()
        reach = QApplication.startDragDistance()

        if box.width() > reach or box.height() > reach:
            selection = self.touched(box)
        else:
            pressed = self.indexAt(rect.topLeft())
            selection = QItemSelection(pressed, pressed) if pressed.isValid() else QItemSelection()

        self.selectionModel().select(selection, command)

    def touched(self, box: QRect) -> QItemSelection:
        model = self.model()
        selection = QItemSelection()

        if model is None:
            return selection

        rows = range(model.rowCount())

        # the grid lays rows out in order, so the cells level with the box are
        # one run of them
        first = bisect_left(rows, box.top(), key=lambda row: self.visualRect(model.index(row, 0)).bottom())
        last = bisect_right(rows, box.bottom(), key=lambda row: self.visualRect(model.index(row, 0)).top())

        start: Index | None = None
        end: Index | None = None

        for row in range(first, last):
            index = model.index(row, 0)
            cell = self.visualRect(index)

            # only a cell the box's edge cuts through needs its target measured
            if not box.contains(cell) and not self.target(index).intersects(box):
                continue

            if end is not None and end.row() == row - 1:
                end = index
                continue

            if start is not None and end is not None:
                selection.select(start, end)

            start = end = index

        if start is not None and end is not None:
            selection.select(start, end)

        return selection

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
        self._pressed = event.position()

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

        drift = event.position() - self._pressed

        if drift.manhattanLength() < QApplication.startDragDistance():
            event = QMouseEvent(
                event.type(),
                self._pressed,
                event.scenePosition() - drift,
                event.globalPosition() - drift,
                event.button(),
                event.buttons(),
                event.modifiers(),
                event.pointingDevice(),
            )

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
