"""Which halving of a texture the preview window draws from"""

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from texturefriend.panes.preview import MIP_FLOOR, mip_level, mip_levels

TEXTURES = [QSize(2048, 2048), QSize(1024, 1024), QSize(1024, 256), QSize(128, 1024), QSize(100, 100)]


class TestMipLevels:
    def test_each_level_halves_the_last(self, app: QApplication) -> None:
        levels = mip_levels(QPixmap(1024, 256))

        assert [level.size() for level in levels] == [QSize(1024 >> step, 256 >> step) for step in range(len(levels))]
        assert max(levels[-1].width(), levels[-1].height()) // 2 < MIP_FLOOR

    def test_a_small_texture_is_not_halved(self, app: QApplication) -> None:
        assert len(mip_levels(QPixmap(MIP_FLOOR, MIP_FLOOR // 2))) == 1

    @pytest.mark.parametrize("texture", TEXTURES)
    @pytest.mark.parametrize("window", [48, 100, 333, 480, 960, 1500, 3000])
    def test_a_level_never_shrinks_more_than_twice_over(self, app: QApplication, texture: QSize, window: int) -> None:
        levels = mip_levels(QPixmap(texture))

        # the window is shaped to the texture it shows
        pixels = texture.scaled(QSize(window, window), Qt.AspectRatioMode.KeepAspectRatio)
        level = mip_level(levels, pixels)

        assert level.width() >= pixels.width() or level is levels[0]
        assert level.height() >= pixels.height() or level is levels[0]

        if level is not levels[-1]:
            assert level.width() <= 2 * pixels.width() + 1
            assert level.height() <= 2 * pixels.height() + 1
