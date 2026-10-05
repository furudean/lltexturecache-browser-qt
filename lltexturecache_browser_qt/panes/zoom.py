from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QSlider, QWidget

from lltexturecache_browser_qt.view.cellsize import CELL_SIZES, CellSizeChanges, cell_size, set_cell_size

SLIDER_WIDTH = 72

# the bar's message sits this far in from the left edge, and the slider keeps
# the same distance from the right one
EDGE_INSET = 6

# room above and below the slider, which holds the bar at the height it stands
# at with only a message on it
EDGE_PADDING = 4


class ZoomControl(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, EDGE_PADDING, EDGE_INSET, EDGE_PADDING)

        self._slider = QSlider(Qt.Orientation.Horizontal, self)
        self._slider.setRange(0, len(CELL_SIZES) - 1)
        self._slider.setPageStep(1)
        self._slider.setFixedWidth(SLIDER_WIDTH)
        self._slider.setAttribute(Qt.WidgetAttribute.WA_MacMiniSize)
        self._slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._slider.setToolTip("Texture size")
        self._slider.valueChanged.connect(self.slid_action)

        row.addWidget(self._slider)

        CellSizeChanges.shared().changed.connect(self.sync)

        self.sync()

    def slid_action(self, place: int) -> None:
        set_cell_size(CELL_SIZES[place])

    def sync(self) -> None:
        # the ladder moves under the slider from the menu and the keyboard too
        self._slider.blockSignals(True)
        self._slider.setValue(CELL_SIZES.index(cell_size()))
        self._slider.blockSignals(False)

    def shutdown(self) -> None:
        CellSizeChanges.shared().changed.disconnect(self.sync)
