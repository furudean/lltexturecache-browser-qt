import struct

import pytest
from PySide6.QtCore import QSize

from lltexturecache_browser_qt.cache.decode import skipped_resolutions


def header(width: int, height: int, levels: int = 5) -> bytes:
    """The main header of a one component codestream, up to its first tile"""

    siz = struct.pack(">HHIIIIIIIIH", 41, 0, width, height, 0, 0, width, height, 0, 0, 1) + b"\x07\x01\x01"
    cod = struct.pack(">HBBHBBBBBB", 12, 0, 0, 1, 0, levels, 4, 4, 0, 0)

    return b"\xff\x4f\xff\x51" + siz + b"\xff\x52" + cod + b"\xff\x90"


class TestSkippedResolutions:
    @pytest.mark.parametrize(
        ("texture", "fit", "skipped"),
        [
            # a square box fills on the texture's longer side
            ((1024, 1024), QSize(200, 200), 2),
            ((1024, 256), QSize(200, 200), 2),
            ((256, 1024), QSize(256, 256), 2),
            ((512, 512), QSize(256, 256), 1),
            ((256, 256), QSize(200, 200), 0),
            # a tall room is filled across its width
            ((1024, 1024), QSize(456, 800), 1),
            ((1024, 256), QSize(456, 800), 1),
            ((2048, 2048), QSize(456, 800), 2),
            # and a wide one down its height
            ((1024, 1024), QSize(800, 300), 1),
            # a box bigger than the texture asks for all of it
            ((512, 512), QSize(800, 800), 0),
        ],
    )
    def test_it_stops_at_the_smallest_level_that_fills_the_fit(
        self, texture: tuple[int, int], fit: QSize, skipped: int
    ) -> None:
        assert skipped_resolutions(header(*texture), fit) == skipped

    def test_it_keeps_a_level_back_from_openjpeg(self) -> None:
        assert skipped_resolutions(header(1024, 1024, levels=2), QSize(16, 16)) == 2

    def test_a_box_the_texture_fits_exactly_is_not_a_level_short(self) -> None:
        assert skipped_resolutions(header(768, 1024), QSize(384, 512)) == 1
        assert skipped_resolutions(header(768, 1024), QSize(385, 513)) == 0

    def test_a_stream_without_a_size_is_decoded_whole(self) -> None:
        assert skipped_resolutions(b"\x00" * 64, QSize(16, 16)) == 0
