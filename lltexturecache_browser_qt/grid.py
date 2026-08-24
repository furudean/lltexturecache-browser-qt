from PySide6.QtCore import QAbstractItemModel, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QMouseEvent, QPainter, QPalette, QResizeEvent
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

    def set_message(self, message: str) -> None:
        self._message.setText(message)

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

        # a child of the viewport rather than of the view, so it is clipped to
        # the area the textures are drawn in and not to the frame around it
        self._empty = EmptyState(self.viewport())
        self._empty.opened.connect(self.opened)

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

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)

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

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._banding:
            return

        super().mouseMoveEvent(event)
