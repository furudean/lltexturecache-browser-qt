from collections.abc import Callable, Iterable
from functools import partial

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QColorDialog,
    QHBoxLayout,
    QToolBar,
    QToolButton,
    QWidget,
)

from lltexturecache_browser_qt.panes.chips import CHIP_GAP, CHIP_MARGIN, CHIP_SIZE, Chip
from lltexturecache_browser_qt.panes.reference import ReferenceChip

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

# how heavy the ring a disabled color is left as
OFF_WEIGHT = 2


class Swatch(Chip):
    """One color a texture has to hold to be shown"""

    def __init__(self, color: QColor, parent: QWidget | None = None, *, on: bool = True) -> None:
        super().__init__(parent, on=on)

        self._color = color

        self.sync_tip()

    @property
    def color(self) -> QColor:
        return self._color

    def set_color(self, color: QColor) -> None:
        self._color = color

        self.sync_tip()
        self.update()

    def title(self) -> str:
        return self._color.name().upper()

    def change_label(self) -> str:
        return "Change Color..."

    def paint_body(self, painter: QPainter, box: QRectF) -> None:
        colors = self.palette()

        # the edge belongs to the chip rather than to what it is holding, so it
        # is drawn either way. a color no darker than the bar behind it has
        # nothing else to show for itself, and white is on the strip by default
        painter.setPen(QPen(colors.color(QPalette.ColorRole.Mid), 1))
        painter.setBrush(self._color if self.isChecked() else colors.color(QPalette.ColorRole.Window))

        self.stroked(painter, box, 1)

        if not self.isChecked():
            # a disabled color is left as a ring inside that edge, so the strip
            # still says which color it is while showing none of it is asked for
            painter.setPen(QPen(self._color, OFF_WEIGHT))
            painter.setBrush(Qt.BrushStyle.NoBrush)

            self.stroked(painter, box, OFF_WEIGHT, inset=1)


class FilterBar(QToolBar):
    """The two ways of asking the grid for a texture, side by side

    A colour says what a texture has to hold and a picture says what it has to
    look like, which are different enough questions that asking one of them is
    dropping the other. They stand next to each other on the bar, and taking up
    either puts the other down.
    """

    changed = Signal(list)
    matched = Signal()
    picking = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Filters", parent)

        self.setMovable(False)
        self.setFloatable(False)

        self._swatches: list[Swatch] = []

        # the picture the cache is being searched for, which there is none of
        # until one is handed over
        self._reference: ReferenceChip | None = None
        self._quiet = False

        body = QWidget(self)

        row = QHBoxLayout(body)
        row.setContentsMargins(6, 2, 6, 2)

        row.setSpacing(CHIP_GAP)

        self._add = QToolButton(body)
        self._add.setText("Filter Color...")
        self._add.setToolTip("Add a color to filter textures by")
        self._add.clicked.connect(self.add_action)

        self._chips = QHBoxLayout()
        self._chips.setContentsMargins(0, 0, 0, 0)
        self._chips.setSpacing(CHIP_GAP)

        # where the picture goes once there is one, which is beside the colours
        # rather than among them. the row stands as tall as a chip whether there
        # is one on it or not, so the bar does not grow under one
        self._picture = QHBoxLayout()
        self._picture.setContentsMargins(0, 0, 0, 0)
        self._picture.setSpacing(CHIP_GAP)
        self._picture.addStrut(CHIP_SIZE + 2 * CHIP_MARGIN)

        self._match = QToolButton(body)
        self._match.setText("Match Image...")
        self._match.setToolTip("Show the textures that look like a picture")
        self._match.clicked.connect(self.picking)

        row.addLayout(self._chips)
        row.addWidget(self._add)
        row.addLayout(self._picture)
        row.addWidget(self._match)
        row.addStretch(1)

        self.addWidget(body)

        self.restore()

    def colors(self) -> list[QColor]:
        return [swatch.color for swatch in self._swatches if swatch.isChecked()]

    def reference(self) -> QImage | None:
        """The picture being asked for, and nothing while there is none or it is off"""

        if self._reference is None or not self._reference.isChecked():
            return None

        return self._reference.image

    def reference_name(self) -> str | None:
        """What the picture being asked for is called, and nothing while there is none"""

        if self._reference is None or not self._reference.isChecked():
            return None

        return self._reference.name

    def set_reference(self, image: QImage, name: str) -> None:
        """Ask for a picture, in place of whatever was being asked for before"""

        if self._reference is not None:
            # the chip would report being switched back on, and this is a new
            # picture whether it was on already or not, so the one report of it
            # is the one made at the end of this
            self._reference.blockSignals(True)
            self._reference.setChecked(True)
            self._reference.blockSignals(False)

            self._reference.set_picture(image, name)
        else:
            chip = ReferenceChip(image, name, self)
            chip.removed.connect(self.drop_reference)
            chip.edited.connect(self.picking)
            chip.toggled.connect(self.matched_action)

            self._reference = chip

            self._picture.addWidget(chip)

        self.matched_action()

    def drop_reference(self) -> None:
        chip = self._reference

        if chip is None:
            return

        self._reference = None

        self._picture.removeWidget(chip)

        chip.setParent(None)
        chip.deleteLater()

        self.matched_action()

    def suggestion(self) -> QColor:
        # a second color is usually picked somewhere near the first, so the
        # picker opens on the last one asked for rather than on wherever it was
        # left. the strip is never empty, but until something on it is enabled
        # none of it has been asked for and there is nothing to open near
        asked = self.colors()

        return asked[-1] if asked else QColor(Qt.GlobalColor.white)

    def add_action(self) -> bool:
        """Ask the picker for a colour, and say whether one came back"""

        picked = QColorDialog.getColor(self.suggestion(), self, "Filter by Color")

        if not picked.isValid():
            return False

        self.add(picked)

        return True

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
        swatch.edited.connect(partial(self.recolor, swatch))
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
        if stored is None:
            self.restore()
            return

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

        self.replace(remembered)

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
        """Put down whatever is being asked for, whichever end of the bar it is on"""

        colors = self.quietly(self.disable_colors)
        picture = self.quietly(self.disable_picture)

        if colors:
            self.changed_action()

        if picture:
            self.matched_action()

    def retire(self, swatch: Swatch) -> None:
        self._chips.removeWidget(swatch)

        swatch.setParent(None)
        swatch.deleteLater()

    def changed_action(self) -> None:
        if self._quiet:
            return

        # asking for a colour is not asking for it inside the picture, it is
        # asking for it instead, so the picture is put down here
        dropped = bool(self.colors()) and self.quietly(self.disable_picture)

        self.changed.emit(self.colors())

        if dropped:
            self.matched.emit()

    def matched_action(self) -> None:
        if self._quiet:
            return

        dropped = self.reference() is not None and self.quietly(self.disable_colors)

        if dropped:
            self.changed.emit(self.colors())

        self.matched.emit()

    def quietly(self, put_down: Callable[[], bool]) -> bool:
        """Put the other ask down without it reporting the change itself"""

        self._quiet = True

        try:
            return put_down()
        finally:
            self._quiet = False

    def disable_colors(self) -> bool:
        """Turn every colour off, and say whether any of them was on"""

        asked = [swatch for swatch in self._swatches if swatch.isChecked()]

        for swatch in asked:
            swatch.setChecked(False)

        return bool(asked)

    def disable_picture(self) -> bool:
        """Turn the picture off, and say whether it was on"""

        if self._reference is None or not self._reference.isChecked():
            return False

        self._reference.setChecked(False)

        return True

    def asking(self) -> bool:
        """Whether anything on the bar is enabled, which is when there is something to turn off"""

        return bool(self.colors()) or self.reference() is not None
