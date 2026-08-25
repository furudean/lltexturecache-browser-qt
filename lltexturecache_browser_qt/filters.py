from functools import partial

from PySide6.QtCore import QEvent, QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QEnterEvent, QIcon, QMouseEvent, QPainter, QPaintEvent, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QColorDialog,
    QHBoxLayout,
    QMenu,
    QToolBar,
    QToolButton,
    QWidget,
)

SWATCH_SIZE = 16
SWATCH_MARGIN = 4
SWATCH_RADIUS = 3

BADGE_SIZE = 10
BADGE_INSET = 3

ADD_ICON_SIZE = 16


class Swatch(QAbstractButton):
    removed = Signal()
    recolored = Signal()

    def __init__(self, color: QColor, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._color = color
        self._hovered = False

        self.setFixedSize(self.sizeHint())
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.menu_action)
        self.clicked.connect(lambda _checked=False: self.recolored.emit())

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
        self.setToolTip(f"{self._color.name().upper()}\nClick to change")

    def badge(self) -> QRectF:
        return QRectF(self.width() - BADGE_SIZE, 0, BADGE_SIZE, BADGE_SIZE)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        colors = self.palette()
        box = QRectF(self.rect()).adjusted(SWATCH_MARGIN, SWATCH_MARGIN, -SWATCH_MARGIN, -SWATCH_MARGIN)

        # the outline is what a pale color has to show for itself against a
        # pale background, so it goes on whatever the fill turns out to be
        painter.setPen(QPen(colors.color(QPalette.ColorRole.Mid), 1))
        painter.setBrush(self._color)
        painter.drawRoundedRect(box, SWATCH_RADIUS, SWATCH_RADIUS)

        if self._hovered:
            self.paint_badge(painter)

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

        change = menu.addAction("Change Color...")
        change.triggered.connect(lambda _checked=False: self.recolored.emit())

        menu.addSeparator()

        drop = menu.addAction("Remove")
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

        body = QWidget(self)

        row = QHBoxLayout(body)
        row.setContentsMargins(6, 2, 6, 2)
        row.setSpacing(6)

        self._add = QToolButton(body)
        self._add.setText("Color Filter...")
        self._add.setIcon(QIcon.fromTheme(QIcon.ThemeIcon.ListAdd))
        self._add.setIconSize(QSize(ADD_ICON_SIZE, ADD_ICON_SIZE))
        self._add.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._add.setStatusTip("Add a color to filter the textures by")
        self._add.clicked.connect(self.add_action)

        self._chips = QHBoxLayout()
        self._chips.setContentsMargins(0, 0, 0, 0)
        self._chips.setSpacing(2)

        self._clear = QToolButton(body)
        self._clear.setText("Clear filters")
        self._clear.setStatusTip("Clear all filters")
        self._clear.clicked.connect(self.clear_action)

        row.addWidget(self._add)
        row.addLayout(self._chips)
        row.addStretch(1)
        row.addWidget(self._clear)

        self.addWidget(body)

        self.sync()

    def colors(self) -> list[QColor]:
        return [swatch.color for swatch in self._swatches]

    def suggestion(self) -> QColor:
        # a second color is usually picked somewhere near the first, so the
        # picker opens on the last one rather than on wherever it was left
        return self._swatches[-1].color if self._swatches else QColor(Qt.GlobalColor.white)

    def add_action(self) -> None:
        picked = QColorDialog.getColor(self.suggestion(), self, "Filter by Color")

        if picked.isValid():
            self.add(picked)

    def add(self, color: QColor) -> None:
        # a color already on the strip is already being applied, so picking it
        # a second time asks for nothing that is not already the case
        if any(swatch.color == color for swatch in self._swatches):
            return

        swatch = Swatch(color, self)
        swatch.removed.connect(partial(self.remove, swatch))
        swatch.recolored.connect(partial(self.recolor, swatch))

        self._swatches.append(swatch)
        self._chips.addWidget(swatch)

        self.changed_action()

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

    def clear_action(self) -> None:
        if not self._swatches:
            return

        for swatch in self._swatches:
            self.retire(swatch)

        self._swatches = []

        self.changed_action()

    def retire(self, swatch: Swatch) -> None:
        self._chips.removeWidget(swatch)

        swatch.setParent(None)
        swatch.deleteLater()

    def changed_action(self) -> None:
        self.sync()

        self.changed.emit(self.colors())

    def sync(self) -> None:
        self._clear.setVisible(bool(self._swatches))
