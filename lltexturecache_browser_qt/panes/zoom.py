from math import exp, log

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QHBoxLayout, QSizePolicy, QSlider, QWidget

from lltexturecache_browser_qt.view.cellsize import (
    CELL_SIZES,
    DEFAULT_CELL_SIZE,
    LARGEST_CELL_SIZE,
    SMALLEST_CELL_SIZE,
    CellSizeChanges,
    cell_size,
    set_cell_size,
)

SLIDER_WIDTH = 72

# the slider's positions, spread evenly over the log of the cell size so each
# rung of the zoom ladder sits the same distance from the next. the default
# size sits in the middle, with each half spread over its own end
SLIDER_STEPS = 600
MIDDLE = SLIDER_STEPS // 2

LOWER_SPAN = log(DEFAULT_CELL_SIZE / SMALLEST_CELL_SIZE)
UPPER_SPAN = log(LARGEST_CELL_SIZE / DEFAULT_CELL_SIZE)

# the bar's message sits this far in from the left edge, and the slider keeps
# the same distance from the right one
EDGE_INSET = 6

# room above and below the slider, which holds the bar at the height it stands
# at with only a message on it
EDGE_PADDING = 4


def size_at(place: int) -> float:
    span = LOWER_SPAN if place < MIDDLE else UPPER_SPAN

    return DEFAULT_CELL_SIZE * exp(span * (place - MIDDLE) / MIDDLE)


def place_of(size: float) -> int:
    span = LOWER_SPAN if size < DEFAULT_CELL_SIZE else UPPER_SPAN

    return MIDDLE + round(log(size / DEFAULT_CELL_SIZE) / span * MIDDLE)


class ZoomControl(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, EDGE_PADDING, EDGE_INSET, EDGE_PADDING)

        self._slider = QSlider(Qt.Orientation.Horizontal, self)
        self._slider.setRange(0, SLIDER_STEPS)
        self._slider.setPageStep(round(SLIDER_STEPS / (len(CELL_SIZES) - 1)))
        # a wheel notch over the slider scrolls this many steps, and moves one rung
        self._slider.setSingleStep(max(1, round(self._slider.pageStep() / QApplication.wheelScrollLines())))
        self._slider.setFixedWidth(SLIDER_WIDTH)
        self._slider.setAttribute(Qt.WidgetAttribute.WA_MacMiniSize)
        self._slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._slider.setToolTip("Texture size")
        self._slider.valueChanged.connect(self.slid_action)

        row.addWidget(self._slider)

        CellSizeChanges.shared().changed.connect(self.sync)

        self.sync()

    def slid_action(self, place: int) -> None:
        set_cell_size(size_at(place))

    def sync(self) -> None:
        # the size moves under the slider from gestures, the menu and the keyboard too
        self._slider.blockSignals(True)
        self._slider.setValue(place_of(cell_size()))
        self._slider.blockSignals(False)

    def shutdown(self) -> None:
        CellSizeChanges.shared().changed.disconnect(self.sync)
