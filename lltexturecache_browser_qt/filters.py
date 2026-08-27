from collections.abc import Iterable
from functools import partial

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QEnterEvent,
    QIcon,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPalette,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QColorDialog,
    QHBoxLayout,
    QMenu,
    QToolBar,
    QToolButton,
    QWidget,
)

DEFAULT_COLORS = (
    "#c0392b",  # red
    "#3f9d3f",  # green
    "#2f6fd0",  # blue
    "#f2f2f2",  # white
    "#8a8a8a",  # grey
    "#1a1a1a",  # black
)

ON_MARK = "+"
OFF_MARK = "-"

SWATCH_SIZE = 16
SWATCH_MARGIN = 4
SWATCH_RADIUS = 3

# what one swatch stands off the next, on top of the margin each of them carries
SWATCH_GAP = 2

BADGE_SIZE = 10
BADGE_INSET = 3

# how heavy the ring a disabled color is left as, and how near in lightness
# that ring has to be to the background before it is lost in it and needs an
# outline of its own to be seen at all. a color picked out of the dialog is
# rarely that pale, but the strip comes up with a white on it every time
OFF_WEIGHT = 2
OFF_FAINT = 32

ADD_ICON_SIZE = 12

# how far an arm of the plus reaches from the middle, as a share of the icon.
# near enough the whole of it, since room left empty inside the icon is room
# the button carries around and cannot be trimmed of afterwards
PLUS_ARM = 0.42
PLUS_WEIGHT = 1.5


def plus_icon(color: QColor, ratio: float) -> QIcon:
    pixmap = QPixmap(round(ADD_ICON_SIZE * ratio), round(ADD_ICON_SIZE * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(color, PLUS_WEIGHT, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))

    middle = ADD_ICON_SIZE / 2
    arm = ADD_ICON_SIZE * PLUS_ARM

    painter.drawLine(QPointF(middle - arm, middle), QPointF(middle + arm, middle))
    painter.drawLine(QPointF(middle, middle - arm), QPointF(middle, middle + arm))
    painter.end()

    return QIcon(pixmap)


class Swatch(QAbstractButton):
    removed = Signal()
    recolored = Signal()

    def __init__(self, color: QColor, parent: QWidget | None = None, *, on: bool = True) -> None:
        super().__init__(parent)

        self._color = color
        self._hovered = False

        self.setFixedSize(self.sizeHint())
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.menu_action)

        # a click disables the color and enables it again, which is the one
        # thing worth doing to a filter often enough to spend the click on
        self.setCheckable(True)
        self.setChecked(on)
        self.toggled.connect(self.sync_tip)

        self.sync_tip()

    @property
    def color(self) -> QColor:
        return self._color

    def set_color(self, color: QColor) -> None:
        self._color = color

        self.sync_tip()
        self.update()

    def sizeHint(self) -> QSize:
        side = SWATCH_SIZE + 2 * SWATCH_MARGIN

        return QSize(side, side)

    def sync_tip(self) -> None:
        action = "Click to disable" if self.isChecked() else "Click to enable"

        self.setToolTip(f"{self._color.name().upper()}\n{action}\nRight-click to change")

    def badge(self) -> QRectF:
        return QRectF(self.width() - BADGE_SIZE, 0, BADGE_SIZE, BADGE_SIZE)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        colors = self.palette()
        box = QRectF(self.rect()).adjusted(SWATCH_MARGIN, SWATCH_MARGIN, -SWATCH_MARGIN, -SWATCH_MARGIN)

        if self.isChecked():
            # the outline is what a pale color has to show for itself against a
            # pale background, so it goes on whatever the fill turns out to be
            painter.setPen(QPen(colors.color(QPalette.ColorRole.Mid), 1))
            painter.setBrush(self._color)
        else:
            # a disabled color keeps itself as a ring, so the strip still says
            # which color it is while showing that none of it is being asked for
            painter.setPen(QPen(self._color, OFF_WEIGHT))
            painter.setBrush(colors.color(QPalette.ColorRole.Window))

        painter.drawRoundedRect(box, SWATCH_RADIUS, SWATCH_RADIUS)

        if not self.isChecked() and self.faint():
            self.paint_edge(painter, box)

        if self._hovered:
            self.paint_badge(painter)

    def faint(self) -> bool:
        window = self.palette().color(QPalette.ColorRole.Window)

        return abs(self._color.lightness() - window.lightness()) < OFF_FAINT

    def paint_edge(self, painter: QPainter, box: QRectF) -> None:
        reach = OFF_WEIGHT / 2
        edge = box.adjusted(-reach, -reach, reach, reach)

        painter.setPen(QPen(self.palette().color(QPalette.ColorRole.Mid), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(edge, SWATCH_RADIUS + reach, SWATCH_RADIUS + reach)

    def paint_badge(self, painter: QPainter) -> None:
        colors = self.palette()
        box = self.badge()

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

        change = menu.addAction("Change Color...")
        change.triggered.connect(lambda _checked=False: self.recolored.emit())

        menu.addSeparator()

        drop = menu.addAction("Remove filter")
        drop.triggered.connect(lambda _checked=False: self.removed.emit())

        menu.exec(self.mapToGlobal(at))
        menu.deleteLater()


class ColorFilterBar(QToolBar):
    changed = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Color Filters", parent)

        self.setMovable(False)
        self.setFloatable(False)

        self._swatches: list[Swatch] = []
        self._quiet = False

        body = QWidget(self)

        row = QHBoxLayout(body)
        row.setContentsMargins(6, 2, 6, 2)

        row.setSpacing(SWATCH_GAP)

        self._add = QToolButton(body)
        self._add.setIconSize(QSize(ADD_ICON_SIZE, ADD_ICON_SIZE))

        self._add.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._add.setStatusTip("Add a color to filter textures by")
        self._add.clicked.connect(self.add_action)

        self._chips = QHBoxLayout()
        self._chips.setContentsMargins(0, 0, 0, 0)
        self._chips.setSpacing(SWATCH_GAP)

        self._off = QToolButton(body)
        self._off.setText("Disable filters")
        self._off.setStatusTip("Disable active filters")
        self._off.clicked.connect(self.disable_action)

        row.addLayout(self._chips)
        row.addWidget(self._add)
        row.addStretch(1)
        row.addWidget(self._off)

        self.addWidget(body)

        self.sync_icon()
        self.restore()
        self.sync()

    def sync_icon(self) -> None:
        color = self._add.palette().color(QPalette.ColorRole.ButtonText)

        self._add.setIcon(plus_icon(color, self.devicePixelRatioF()))

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)

        if event.type() == QEvent.Type.PaletteChange:
            self.sync_icon()

    def colors(self) -> list[QColor]:
        return [swatch.color for swatch in self._swatches if swatch.isChecked()]

    def suggestion(self) -> QColor:
        # a second color is usually picked somewhere near the first, so the
        # picker opens on the last one asked for rather than on wherever it was
        # left. the strip is never empty, but until something on it is enabled
        # none of it has been asked for and there is nothing to open near
        asked = self.colors()

        return asked[-1] if asked else QColor(Qt.GlobalColor.white)

    def add_action(self) -> None:
        picked = QColorDialog.getColor(self.suggestion(), self, "Filter by Color")

        if picked.isValid():
            self.add(picked)

    def add(self, color: QColor) -> None:
        # a color already on the strip asks for nothing new, beyond enabling it
        # again if it is one that had been disabled
        for swatch in self._swatches:
            if swatch.color == color:
                swatch.setChecked(True)
                return

        self.attach(color, on=True)

        self.changed_action()

    def attach(self, color: QColor, *, on: bool) -> None:
        swatch = Swatch(color, self, on=on)
        swatch.removed.connect(partial(self.remove, swatch))
        swatch.recolored.connect(partial(self.recolor, swatch))
        swatch.toggled.connect(self.changed_action)

        self._swatches.append(swatch)
        self._chips.addWidget(swatch)

    def replace(self, swatches: Iterable[tuple[QColor, bool]]) -> None:
        for swatch in self._swatches:
            self.retire(swatch)

        self._swatches = []

        for color, on in swatches:
            self.attach(color, on=on)

    def restore(self) -> None:
        self.replace((QColor(color), False) for color in DEFAULT_COLORS)

    def state(self) -> list[str]:
        return [f"{ON_MARK if swatch.isChecked() else OFF_MARK}{swatch.color.name()}" for swatch in self._swatches]

    def revive(self, stored: object) -> None:
        # a list of one comes back out of the store as the string it held
        if isinstance(stored, str):
            stored = [stored]

        remembered: list[tuple[QColor, bool]] = []

        if isinstance(stored, list):
            for entry in stored:
                if not isinstance(entry, str) or entry[:1] not in (ON_MARK, OFF_MARK):
                    continue

                color = QColor(entry[1:])

                if color.isValid():
                    remembered.append((color, entry[0] == ON_MARK))

        if not remembered:
            self.restore()
        else:
            self.replace(remembered)

        self.sync()

    def remove(self, swatch: Swatch) -> None:
        self._swatches.remove(swatch)
        self.retire(swatch)

        self.changed_action()

    def recolor(self, swatch: Swatch) -> None:
        picked = QColorDialog.getColor(swatch.color, self, "Filter by Color")

        if not picked.isValid() or picked == swatch.color:
            return

        swatch.set_color(picked)

        self.changed_action()

    def disable_action(self) -> None:
        self._quiet = True

        try:
            for swatch in self._swatches:
                swatch.setChecked(False)
        finally:
            self._quiet = False

        self.changed_action()

    def retire(self, swatch: Swatch) -> None:
        self._chips.removeWidget(swatch)

        swatch.setParent(None)
        swatch.deleteLater()

    def changed_action(self) -> None:
        if self._quiet:
            return

        self.sync()

        self.changed.emit(self.colors())

    def asking(self) -> bool:
        """Whether anything on the strip is enabled, which is when there is something to turn off"""

        return bool(self.colors())

    def sync(self) -> None:
        # the button stays where it is once the strip is off, greyed rather
        # than gone, so nothing else on the bar shifts under the pointer
        self._off.setEnabled(self.asking())
