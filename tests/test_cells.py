"""How a cell's texture is fitted, baked and drawn"""

import pytest
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from texturefriend.grid.cells import (
    BakedCells,
    image_box,
    image_pixels,
    paint_stand_in,
    slot_size,
    texture_room,
)
from texturefriend.grid.model import cell_pixels
from texturefriend.view import cellsize
from texturefriend.view.cellsize import CELL_SIZES

RATIOS = (1.0, 1.25, 1.5, 2.0)

SHAPES = [(1024, side) for side in (1024, 512, 256, 128, 64)] + [(side, 1024) for side in (512, 256, 128, 64)]

BORDER = QColor(0x80, 0x80, 0x80)


def decoded(shape: tuple[int, int], pixels: int) -> QPixmap:
    """A pixmap the size a cell decode of that shape comes back at"""

    return QPixmap(QSize(*shape).scaled(QSize(pixels, pixels), Qt.AspectRatioMode.KeepAspectRatio))


class TestSettledCells:
    @pytest.mark.parametrize("ratio", RATIOS)
    @pytest.mark.parametrize("size", CELL_SIZES)
    def test_a_decode_is_drawn_at_its_own_size(
        self, app: QApplication, monkeypatch: pytest.MonkeyPatch, ratio: float, size: float
    ) -> None:
        monkeypatch.setattr(cellsize, "_size", size)

        cell = QRect(0, 0, slot_size(), slot_size())
        baked = BakedCells()

        for shape in SHAPES:
            pixmap = decoded(shape, cell_pixels(ratio))

            assert image_pixels(pixmap, cell, ratio) == pixmap.size(), shape
            assert baked.cell(pixmap, ratio, BORDER).size() == pixmap.size(), shape

    @pytest.mark.parametrize("ratio", RATIOS)
    @pytest.mark.parametrize("size", CELL_SIZES)
    def test_the_box_stays_in_the_room(
        self, app: QApplication, monkeypatch: pytest.MonkeyPatch, ratio: float, size: float
    ) -> None:
        monkeypatch.setattr(cellsize, "_size", size)

        cell = QRect(0, 0, slot_size(), slot_size())

        # the decode is rounded to whole device pixels and so is where it
        # lands, and neither may cost more than one of them
        room = texture_room(cell).toRectF().adjusted(-1 / ratio, -1 / ratio, 1 / ratio, 1 / ratio)

        for shape in SHAPES:
            box = image_box(image_pixels(decoded(shape, cell_pixels(ratio)), cell, ratio), cell, ratio)

            assert box is not None
            assert room.contains(box), shape

    @pytest.mark.parametrize("ratio", RATIOS)
    def test_the_box_starts_on_a_device_pixel(self, app: QApplication, ratio: float) -> None:
        cell = QRect(17, 23, 106, 106)
        box = image_box(QSize(125, 31), cell, ratio)

        assert box is not None
        assert box.left() * ratio == pytest.approx(round(box.left() * ratio))
        assert box.top() * ratio == pytest.approx(round(box.top() * ratio))


class TestStandIns:
    def test_one_bake_serves_every_step_of_a_zoom(self, app: QApplication) -> None:
        ratio = 2.0
        screen = QPixmap(800, 800)
        screen.setDevicePixelRatio(ratio)

        baked = BakedCells()
        stand_in = QPixmap(200, 100)
        stand_in.fill(QColor(0x20, 0x60, 0xA0))

        painter = QPainter(screen)

        for side in range(100, 140):
            cell = QRect(0, 0, side, side)
            box = image_box(image_pixels(stand_in, cell, ratio), cell, ratio)

            assert box is not None

            paint_stand_in(painter, baked, stand_in, box, BORDER)

        painter.end()

        assert len(baked) == 1
