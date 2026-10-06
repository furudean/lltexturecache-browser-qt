from math import exp, log

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QHBoxLayout, QSizePolicy, QSlider, QWidget

from lltexturecache_browser_qt.view.cellsize import (
    CELL_SIZES,
    LARGEST_CELL_SIZE,
    SMALLEST_CELL_SIZE,
    CellSizeChanges,
    cell_size,
    set_cell_size,
)

SLIDER_WIDTH = 72
SLIDER_STEPS = 600

SPAN = log(LARGEST_CELL_SIZE / SMALLEST_CELL_SIZE)

EDGE_INSET = 6
EDGE_PADDING = 4


def size_at(place: int) -> float:
    return SMALLEST_CELL_SIZE * exp(SPAN * place / SLIDER_STEPS)


def place_of(size: float) -> int:
    return round(log(size / SMALLEST_CELL_SIZE) / SPAN * SLIDER_STEPS)


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
