"""Thumbnails read straight from the rows the viewer kept"""

import pytest
from PySide6.QtCore import QBuffer, QByteArray
from PySide6.QtGui import QImage, QImageReader
from PySide6.QtWidgets import QApplication
from texture_courier import Thumbnail

from texturefriend.view.images import fit_image, thumbnail_pixels


def kept(width: int, height: int, components: int) -> Thumbnail:
    # every byte different from its neighbours, so a row or a component out of
    # place shows up as a changed pixel
    pixels = bytes((index * 37 + index // 7) % 256 for index in range(width * height * components))

    return Thumbnail(width=width, height=height, components=components, discard_level=4, pixels=pixels)


def png_image(thumbnail: Thumbnail) -> QImage:
    # the buffer reads through the array rather than copying it, so the array
    # is held for as long as the read takes
    data = QByteArray(thumbnail.png())
    buffer = QBuffer(data)
    buffer.open(QBuffer.OpenModeFlag.ReadOnly)

    return QImageReader(buffer).read()


def argb(image: QImage) -> list[int]:
    converted = image.convertToFormat(QImage.Format.Format_ARGB32)

    return [converted.pixel(x, y) for y in range(converted.height()) for x in range(converted.width())]


@pytest.mark.parametrize("components", [1, 2, 3, 4])
@pytest.mark.parametrize("shape", [(16, 16), (16, 4), (3, 16), (1, 1)])
class TestThumbnailPixels:
    def test_it_matches_the_png_the_viewer_would_write(
        self, app: QApplication, components: int, shape: tuple[int, int]
    ) -> None:
        thumbnail = kept(*shape, components)

        assert argb(thumbnail_pixels(thumbnail)) == argb(png_image(thumbnail))

    def test_it_fits_the_same_as_the_png(self, app: QApplication, components: int, shape: tuple[int, int]) -> None:
        thumbnail = kept(*shape, components)

        fitted = fit_image(thumbnail_pixels(thumbnail), 200, checkerboard=False, ratio=2.0)

        assert argb(fitted) == argb(fit_image(png_image(thumbnail), 200, checkerboard=False, ratio=2.0))


def test_a_short_slot_is_no_picture(app: QApplication) -> None:
    thumbnail = kept(16, 16, 3)
    thumbnail.pixels = thumbnail.pixels[:-1]

    assert thumbnail_pixels(thumbnail).isNull()
