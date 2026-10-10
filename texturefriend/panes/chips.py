"""One thing the grid is being asked for, as a box on the filter bar

A colour and a picture are asked for differently and drawn differently, but
they stand for the same kind of thing: one ask, turned off and on again with a
click, changed from a right click menu, and dropped from the strip through the
cross that comes up over it while the pointer is on it. All of that is here,
and what goes on inside the box is left to whichever kind of chip it is.
"""

from PySide6.QtCore import QEvent, QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QEnterEvent, QMouseEvent, QPainter, QPaintEvent, QPalette, QPen
from PySide6.QtWidgets import QAbstractButton, QMenu, QWidget

CHIP_SIZE = 16
CHIP_MARGIN = 4
CHIP_RADIUS = 5

FADED = 0.35

# what one chip stands off the next, on top of the margin each of them carries
CHIP_GAP = 2

BADGE_SIZE = 10
BADGE_INSET = 3


class Chip(QAbstractButton):
    removed = Signal()
    edited = Signal()

    def __init__(self, parent: QWidget | None = None, *, on: bool = True) -> None:
        super().__init__(parent)

        self._hovered = False

        self.setFixedSize(self.sizeHint())
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.menu_action)

        # a click disables the ask and enables it again, which is the one thing
        # worth doing to a filter often enough to spend the click on
        self.setCheckable(True)
        self.setChecked(on)
        self.toggled.connect(self.sync_tip)

    def sizeHint(self) -> QSize:
        side = CHIP_SIZE + 2 * CHIP_MARGIN

        return QSize(side, side)

    def title(self) -> str:
        """What the chip stands for, as the first line of its tooltip"""

        raise NotImplementedError

    def change_label(self) -> str:
        """The right click entry that swaps out what the chip stands for"""

        raise NotImplementedError

    def paint_body(self, painter: QPainter, box: QRectF) -> None:
        """Whatever the chip has to show for itself, inside the box it was given"""

        raise NotImplementedError

    def sync_tip(self) -> None:
        action = "Click to disable" if self.isChecked() else "Click to enable"

        self.setToolTip(f"{self.title()}\n{action}\nRight-click to change")

    def badge(self) -> QRectF:
        return QRectF(self.width() - BADGE_SIZE, 0, BADGE_SIZE, BADGE_SIZE)

    def body(self) -> QRectF:
        return QRectF(self.rect()).adjusted(CHIP_MARGIN, CHIP_MARGIN, -CHIP_MARGIN, -CHIP_MARGIN)

    def stroked(self, painter: QPainter, box: QRectF, width: float, *, inset: float = 0.0) -> None:
        """Draw the rounded rect a pen of this weight leaves inside the box

        Every chip is meant to take up the same square, and a pen is centred on
        the line it is given, so half its weight would hang outside one. The
        chips do not all carry the same pen, so where the line goes has to move
        with it. `inset` is for a line that sits further in again, behind
        whatever is already drawn at the edge.
        """

        reach = inset + width / 2

        painter.drawRoundedRect(
            box.adjusted(reach, reach, -reach, -reach),
            CHIP_RADIUS - reach,
            CHIP_RADIUS - reach,
        )

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        self.paint_body(painter, self.body())

        if self._hovered:
            self.paint_badge(painter)

    def paint_badge(self, painter: QPainter) -> None:
        colors = self.palette()
        box = self.badge()

        painter.setOpacity(1.0)
        painter.setPen(QPen(colors.color(QPalette.ColorRole.Mid), 1))
        painter.setBrush(colors.color(QPalette.ColorRole.Window))
        painter.drawEllipse(box)

        cross = box.adjusted(BADGE_INSET, BADGE_INSET, -BADGE_INSET, -BADGE_INSET)

        painter.setPen(QPen(colors.color(QPalette.ColorRole.Text), 1.2))
        painter.drawLine(cross.topLeft(), cross.bottomRight())
        painter.drawLine(cross.topRight(), cross.bottomLeft())

    def enterEvent(self, event: QEnterEvent) -> None:
        self._hovered = True

        self.update()

        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._hovered = False

        self.update()

        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.badge().contains(event.position()):
            self.removed.emit()
            return

        super().mousePressEvent(event)

    def menu_action(self, at: QPoint) -> None:
        menu = QMenu(self)

        turn = menu.addAction("Disable" if self.isChecked() else "Enable")
        turn.triggered.connect(lambda _checked=False: self.setChecked(not self.isChecked()))

        change = menu.addAction(self.change_label())
        change.triggered.connect(lambda _checked=False: self.edited.emit())

        menu.addSeparator()

        drop = menu.addAction("Remove filter")
        drop.triggered.connect(lambda _checked=False: self.removed.emit())

        menu.exec(self.mapToGlobal(at))
        menu.deleteLater()
