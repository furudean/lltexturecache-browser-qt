"""Decoded textures as Qt images, fitted to the boxes the app shows them in"""

from PySide6.QtCore import QBuffer, QByteArray, QSize
from PySide6.QtGui import QColor, QImage, QImageWriter
from PySide6.QtWidgets import QApplication

from lltexturecache_browser_qt.view.checkerboard import CheckerTone, set_grid_tone
from lltexturecache_browser_qt.view.images import (
    THUMBNAIL_SIZE,
    fit_image,
    placeholder,
    read_image,
    thumbnail_image,
)


def png_bytes(width: int, height: int, color: QColor) -> bytes:
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(color)

    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)

    QImageWriter(buffer, QByteArray(b"PNG")).write(image)

    return bytes(data.data())


class TestReadImage:
    def test_an_encoded_image_reads_back_at_its_own_size(self, app: QApplication) -> None:
        image = read_image(QByteArray(png_bytes(12, 7, QColor("red"))))

        assert image.size() == QSize(12, 7)

    def test_bytes_that_are_not_an_image_read_back_null(self, app: QApplication) -> None:
        assert read_image(QByteArray(b"not an image")).isNull()


class TestFitImage:
    def test_a_null_image_is_handed_straight_back(self, app: QApplication) -> None:
        assert fit_image(QImage()).isNull()

    def test_a_large_image_is_brought_down_to_the_box(self, app: QApplication) -> None:
        image = QImage(400, 400, QImage.Format.Format_RGB32)
        image.fill(QColor("red"))

        assert fit_image(image).size() == QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE)

    def test_fitting_keeps_the_shape(self, app: QApplication) -> None:
        image = QImage(400, 200, QImage.Format.Format_RGB32)
        image.fill(QColor("red"))

        fitted = fit_image(image)

        assert fitted.width() == THUMBNAIL_SIZE
        assert fitted.height() == THUMBNAIL_SIZE // 2

    def test_a_small_image_fills_its_square_by_default(self, app: QApplication) -> None:
        image = QImage(32, 32, QImage.Format.Format_RGB32)
        image.fill(QColor("red"))

        assert fit_image(image).width() == THUMBNAIL_SIZE

    def test_a_small_image_can_be_left_at_its_own_size(self, app: QApplication) -> None:
        image = QImage(32, 32, QImage.Format.Format_RGB32)
        image.fill(QColor("red"))

        assert fit_image(image, upscale=False).size() == QSize(32, 32)

    def test_a_large_image_still_comes_down_when_upscaling_is_off(self, app: QApplication) -> None:
        image = QImage(400, 400, QImage.Format.Format_RGB32)
        image.fill(QColor("red"))

        assert fit_image(image, upscale=False).width() == THUMBNAIL_SIZE

    def test_no_box_leaves_the_size_alone(self, app: QApplication) -> None:
        image = QImage(400, 300, QImage.Format.Format_RGB32)
        image.fill(QColor("red"))

        assert fit_image(image, None).size() == QSize(400, 300)

    def test_a_transparent_image_is_backed_by_the_checkerboard(self, app: QApplication) -> None:
        set_grid_tone(CheckerTone.LIGHT)

        image = QImage(40, 40, QImage.Format.Format_ARGB32)
        image.fill(QColor(0xFF, 0x00, 0x00, 0x80))

        assert not fit_image(image).hasAlphaChannel()

    def test_a_caller_drawing_its_own_checkerboard_keeps_the_transparency(self, app: QApplication) -> None:
        image = QImage(40, 40, QImage.Format.Format_ARGB32)
        image.fill(QColor(0xFF, 0x00, 0x00, 0x80))

        assert fit_image(image, checkerboard=False).hasAlphaChannel()


class TestThumbnailImage:
    def test_a_stored_thumbnail_comes_back_fitted(self, app: QApplication) -> None:
        image = thumbnail_image(png_bytes(400, 400, QColor("red")))

        assert image.size() == QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE)

    def test_bytes_that_are_not_a_thumbnail_come_back_null(self, app: QApplication) -> None:
        assert thumbnail_image(b"not a png").isNull()


class TestPlaceholder:
    def test_the_placeholder_fills_a_cell(self, app: QApplication) -> None:
        assert placeholder().size() == QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE)

    def test_the_placeholder_is_built_once(self, app: QApplication) -> None:
        assert placeholder() is placeholder()
