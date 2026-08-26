from PySide6.QtCore import QAbstractItemModel, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QKeyEvent, QMouseEvent, QPainter, QPalette, QResizeEvent, QShowEvent, QWheelEvent
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QListView,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from lltexturecache_browser_qt.images import THUMBNAIL_SIZE
from lltexturecache_browser_qt.model import Index

CELL_PADDING = 14

# how far the empty grid's message may run before it wraps, so a window dragged
# wide reads as a line of text in the middle of it rather than as a banner
MESSAGE_WIDTH = 320


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

    def sizeHint(self, option: QStyleOptionViewItem, index: Index) -> QSize:
        return QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE)


class EmptyState(QWidget):
    opened = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._message = QLabel()
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._message.setForegroundRole(QPalette.ColorRole.Text)

        self._open = QPushButton("Open...")
        self._open.clicked.connect(self.opened)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(self._message, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._open, 0, Qt.AlignmentFlag.AlignHCenter)

    def set_message(self, message: str, may_open: bool = False) -> None:
        self._message.setText(message)

        self._open.setVisible(may_open)

        self._message.setWordWrap(False)

        width = self._message.sizeHint().width()
        wraps = width > MESSAGE_WIDTH

        self._message.setWordWrap(wraps)
        self._message.setFixedWidth(MESSAGE_WIDTH if wraps else width)

        self.adjustSize()


class TextureGrid(QListView):
    opened = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._banding = False
        self._pin: int | None = None

        # a child of the viewport rather than of the view, so it is clipped to
        # the area the textures are drawn in and not to the frame around it
        self._empty = EmptyState(self.viewport())
        self._empty.opened.connect(self.opened)
        self.verticalScrollBar().rangeChanged.connect(self.apply_pin)
        self.verticalScrollBar().actionTriggered.connect(self.unpin)

        self.sync_empty()

    def set_message(self, message: str, may_open: bool = False) -> None:
        self._empty.set_message(message, may_open)

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
        self._banding = not self.indexAt(event.position().toPoint()).isValid()

        self.unpin()

        super().mousePressEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        self.unpin()

        super().wheelEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        self.unpin()

        super().keyPressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._banding:
            return

        super().mouseMoveEvent(event)
