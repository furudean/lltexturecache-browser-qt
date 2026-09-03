import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication
from texture_courier import Entry, Texture, Thumbnail

from lltexturecache_browser_qt.cache.color import FLAT_BASE_BYTES
from lltexturecache_browser_qt.cache.scan import PLACEHOLDER_BYTE, CacheScan, ScanSignals, placeholder


def entry(image_size: int) -> Texture:
    return Texture(
        index=0,
        entry=Entry(uuid="0" * 36, image_size=image_size, body_size=0, time=datetime.now()),  # noqa: DTZ005
        body_path=Path("nowhere"),
        read_head=bytes,
        read_thumbnail=lambda: None,
    )


def scan() -> CacheScan:
    return CacheScan([], threading.Lock(), ScanSignals())


def kept(width: int = 16, height: int = 16, discard_level: int = 2, fill: int = 0) -> Thumbnail:
    return Thumbnail(
        width=width,
        height=height,
        components=4,
        discard_level=discard_level,
        pixels=bytes([fill]) * (width * height * 4),
    )


def filled(color: QColor) -> QImage:
    image = QImage(16, 16, QImage.Format.Format_ARGB32)
    image.fill(color)

    return image


class TestDense:
    def test_a_texture_paying_for_a_picture_is_dense(self, app: QApplication) -> None:
        assert scan().dense(entry(FLAT_BASE_BYTES * 8), kept()) is True

    def test_a_texture_that_is_all_header_is_not(self, app: QApplication) -> None:
        assert scan().dense(entry(FLAT_BASE_BYTES // 2), kept()) is False

    def test_a_thumbnail_with_no_size_cannot_answer(self, app: QApplication) -> None:
        assert scan().dense(entry(FLAT_BASE_BYTES * 8), kept(width=0)) is False


class TestSignature:
    def test_the_bytes_overrule_a_thumbnail_that_reports_one_colour(self, app: QApplication) -> None:
        found = scan().signature(entry(FLAT_BASE_BYTES * 8), kept(), filled(QColor("red")))

        assert found is not None
        assert found.flat is False

    def test_a_small_texture_keeps_the_one_colour_its_thumbnail_reports(self, app: QApplication) -> None:
        found = scan().signature(entry(FLAT_BASE_BYTES // 2), kept(), filled(QColor("red")))

        assert found is not None
        assert found.flat is True

    def test_the_bytes_do_not_overrule_a_texture_nobody_can_see(self, app: QApplication) -> None:
        # the colors are in the codestream and were paid for at full price, but
        # they are under an opacity plane that shows none of them
        found = scan().signature(entry(FLAT_BASE_BYTES * 8), kept(), filled(QColor(0xFF, 0x00, 0x00, 0x00)))

        assert found is not None
        assert found.clear is True
        assert found.flat is True

    def test_a_thumbnail_that_cannot_be_read_has_no_signature(self, app: QApplication) -> None:
        assert scan().signature(entry(FLAT_BASE_BYTES * 8), kept(), QImage()) is None


class TestPlaceholder:
    def test_a_slot_of_nothing_but_the_fill_is_a_placeholder(self) -> None:
        assert placeholder(kept(fill=PLACEHOLDER_BYTE)) is True

    def test_a_thumbnail_with_a_picture_in_it_is_not(self) -> None:
        grey = kept(fill=PLACEHOLDER_BYTE)
        marked = Thumbnail(
            width=grey.width,
            height=grey.height,
            components=grey.components,
            discard_level=grey.discard_level,
            pixels=grey.pixels[:-1] + b"\x81",
        )

        assert placeholder(marked) is False

    def test_a_slot_of_another_fill_is_not(self) -> None:
        # black and white thumbnails are written by the viewer and mean it
        assert placeholder(kept(fill=0x00)) is False
        assert placeholder(kept(fill=0xFF)) is False

    def test_a_thumbnail_with_no_pixels_is_not(self) -> None:
        assert placeholder(kept(width=0)) is False
