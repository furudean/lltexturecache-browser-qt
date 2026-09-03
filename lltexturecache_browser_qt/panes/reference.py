"""The picture the cache is being searched for, as a chip on the filter bar

A colour beside it says what a texture has to hold; the picture says what one
has to look like. The chip is what says a picture is being asked for at all,
and which picture it is.
"""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from lltexturecache_browser_qt.panes.chips import CHIP_RADIUS, CHIP_SIZE, FADED, Chip


class ReferenceChip(Chip):
    """The picture being searched for, cut to the same square a colour sits in"""

    def __init__(self, image: QImage, name: str, parent: QWidget | None = None, *, on: bool = True) -> None:
        super().__init__(parent, on=on)

        self._image = image
        self._name = name
        self._preview = self.previewed(image)

        self.sync_tip()

    @property
    def image(self) -> QImage:
        return self._image

    @property
    def name(self) -> str:
        return self._name

    def set_picture(self, image: QImage, name: str) -> None:
        self._image = image
        self._name = name
        self._preview = self.previewed(image)

        self.sync_tip()
        self.update()

    def previewed(self, image: QImage) -> QPixmap:
        """The picture at the size the chip draws it, cut to the square the chip is

        Kept, since the picture handed over is a screenshot at whatever size
        the screen is and the chip is repainted on every pass of the pointer.
        """

        ratio = self.devicePixelRatioF()
        side = round(CHIP_SIZE * ratio)

        scaled = image.scaled(
            side,
            side,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )

        middle = scaled.copy(
            (scaled.width() - side) // 2,
            (scaled.height() - side) // 2,
            side,
            side,
        )

        pixmap = QPixmap.fromImage(middle)
        pixmap.setDevicePixelRatio(ratio)

        return pixmap

    def title(self) -> str:
        return f"Matching {self._name}"

    def change_label(self) -> str:
        return "Change Image..."

    def paint_body(self, painter: QPainter, box: QRectF) -> None:
        rounded = QPainterPath()
        rounded.addRoundedRect(box, CHIP_RADIUS, CHIP_RADIUS)

        painter.save()
        painter.setClipPath(rounded)
        painter.setOpacity(1.0 if self.isChecked() else FADED)
        painter.drawPixmap(box, self._preview, QRectF(self._preview.rect()))
        painter.restore()

        # the outline is what a picture as pale as the bar behind it has to show
        # for itself, and it is also what is left of a disabled one
        painter.setPen(QPen(self.palette().color(QPalette.ColorRole.Mid), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        self.stroked(painter, box, 1)
