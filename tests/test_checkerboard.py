"""The checkerboard laid behind textures that carry transparency"""

from collections.abc import Iterator

import pytest
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QApplication

from lltexturecache_browser_qt.view.checkerboard import (
    CHECKERBOARD_SIZE,
    DARK_SHADES,
    GRID_KEY,
    LIGHT_SHADES,
    LIGHTNESS_THRESHOLD,
    TONE_CYCLE,
    CheckerTone,
    checker_tile,
    checkerboard_generation,
    checkerboard_key,
    cycle_pane_tone,
    grid_tone,
    opposing_tone,
    over_checkerboard,
    pane_checkerboard,
    pane_colors,
    pane_lightness,
    pane_tone,
    pixmap_lightness,
    predominant_lightness,
    reset,
    reset_pane_tone,
    set_grid_tone,
    set_pane_tone,
    set_picked_lightness,
    shaded,
    shades,
    standing_tone,
    state,
    sync_checkerboard,
)


@pytest.fixture
def tones(settings: None) -> Iterator[None]:
    """Put the checkerboard back the way the test found it

    It is app-wide state by design — every pane and cell reads the one
    setting — so a test that moves it has to move it back.
    """

    was = reset()

    yield

    reset(was)


class TestShades:
    def test_a_dark_background_is_shaded_lighter(self, app: QApplication) -> None:
        base = QColor(0x20, 0x20, 0x20)

        assert shaded(base, 30).lightness() > base.lightness()

    def test_a_light_background_is_shaded_darker(self, app: QApplication) -> None:
        base = QColor(0xF0, 0xF0, 0xF0)

        assert shaded(base, 30).lightness() < base.lightness()

    def test_shading_stays_inside_the_range(self, app: QApplication) -> None:
        assert 0 <= shaded(QColor(0, 0, 0), 255).lightness() <= 255
        assert 0 <= shaded(QColor(255, 255, 255), 255).lightness() <= 255

    def test_a_tinted_background_keeps_its_hue(self, app: QApplication) -> None:
        base = QColor(0x20, 0x30, 0x50)

        assert shaded(base, 20).hue() == base.hue()

    def test_shades_returns_the_base_first(self, app: QApplication) -> None:
        base = QColor(0xF0, 0xF0, 0xF0)

        assert shades(base)[0] == base

    def test_the_two_fixed_checkerboards_differ(self, app: QApplication) -> None:
        assert checkerboard_key(LIGHT_SHADES) != checkerboard_key(DARK_SHADES)


class TestPredominantLightness:
    def test_a_fully_clear_image_weighs_nothing(self, app: QApplication) -> None:
        image = QImage(8, 8, QImage.Format.Format_ARGB32)
        image.fill(QColor(0xFF, 0xFF, 0xFF, 0x00))

        assert predominant_lightness(image) is None

    def test_a_white_image_reads_light(self, app: QApplication) -> None:
        image = QImage(8, 8, QImage.Format.Format_ARGB32)
        image.fill(QColor(0xFF, 0xFF, 0xFF))

        assert predominant_lightness(image) == pytest.approx(255.0, abs=1.0)

    def test_a_black_image_reads_dark(self, app: QApplication) -> None:
        image = QImage(8, 8, QImage.Format.Format_ARGB32)
        image.fill(QColor(0x00, 0x00, 0x00))

        assert predominant_lightness(image) == pytest.approx(0.0, abs=1.0)

    def test_clear_pixels_are_left_out_of_the_weighing(self, app: QApplication) -> None:
        image = QImage(8, 8, QImage.Format.Format_ARGB32)
        image.fill(QColor(0x00, 0x00, 0x00, 0x00))

        for y in range(8):
            image.setPixelColor(0, y, QColor(0xFF, 0xFF, 0xFF, 0xFF))

        # only the opaque column counts, so a mostly-clear image still reads white
        assert predominant_lightness(image) == pytest.approx(255.0, abs=1.0)

    def test_a_faint_white_is_not_read_as_a_dark_grey(self, app: QApplication) -> None:
        image = QImage(8, 8, QImage.Format.Format_ARGB32)
        image.fill(QColor(0xFF, 0xFF, 0xFF, 0x20))

        # premultiplication would scale the white down towards black
        assert predominant_lightness(image) == pytest.approx(255.0, abs=1.0)

    def test_an_opaque_pixmap_is_not_measured(self, app: QApplication) -> None:
        pixmap = QPixmap(8, 8)
        pixmap.fill(QColor(0xFF, 0xFF, 0xFF))

        assert pixmap_lightness(pixmap) is None

    def test_a_null_pixmap_is_not_measured(self, app: QApplication) -> None:
        assert pixmap_lightness(QPixmap()) is None


class TestOpposingTone:
    def test_nothing_measured_opposes_nothing(self) -> None:
        assert opposing_tone(None) is None

    def test_a_light_texture_is_stood_on_the_dark_checkerboard(self) -> None:
        assert opposing_tone(LIGHTNESS_THRESHOLD) is CheckerTone.DARK
        assert opposing_tone(255.0) is CheckerTone.DARK

    def test_a_dark_texture_is_stood_on_the_light_checkerboard(self) -> None:
        assert opposing_tone(LIGHTNESS_THRESHOLD - 1) is CheckerTone.LIGHT
        assert opposing_tone(0.0) is CheckerTone.LIGHT


class TestTones:
    def test_an_unset_store_opens_on_the_automatic_checkerboard(self, tones: None) -> None:
        state().grid = None

        assert grid_tone() is CheckerTone.AUTO

    def test_a_stored_tone_is_read_back(self, tones: None) -> None:
        set_grid_tone(CheckerTone.DARK)
        state().grid = None

        assert grid_tone() is CheckerTone.DARK

    def test_a_tone_the_app_does_not_know_falls_back_to_automatic(self, tones: None) -> None:
        from PySide6.QtCore import QSettings

        QSettings().setValue(GRID_KEY, "chartreuse")
        state().grid = None

        assert grid_tone() is CheckerTone.AUTO

    def test_setting_the_grid_tone_moves_the_panes_with_it(self, tones: None) -> None:
        set_grid_tone(CheckerTone.LIGHT)

        assert pane_tone() is CheckerTone.LIGHT

    def test_a_pane_can_be_clicked_off_the_grid_tone(self, tones: None) -> None:
        set_grid_tone(CheckerTone.LIGHT)
        set_pane_tone(CheckerTone.NONE)

        assert pane_tone() is CheckerTone.NONE
        assert grid_tone() is CheckerTone.LIGHT

    def test_resetting_calls_a_pane_back_to_the_grid_tone(self, tones: None) -> None:
        set_grid_tone(CheckerTone.DARK)
        set_pane_tone(CheckerTone.NONE)
        reset_pane_tone()

        assert pane_tone() is CheckerTone.DARK

    def test_cycling_walks_the_three_tones_and_comes_back(self, tones: None) -> None:
        set_pane_tone(TONE_CYCLE[0])

        walked = [standing_tone()]

        for _ in TONE_CYCLE:
            cycle_pane_tone()
            walked.append(standing_tone())

        assert walked[:-1] == list(TONE_CYCLE)
        assert walked[-1] == TONE_CYCLE[0]

    def test_the_automatic_tone_follows_what_is_selected(self, tones: None) -> None:
        set_pane_tone(CheckerTone.AUTO)
        set_picked_lightness(255.0)

        assert standing_tone() is CheckerTone.DARK

        set_picked_lightness(0.0)

        assert standing_tone() is CheckerTone.LIGHT

    def test_a_fixed_tone_ignores_what_is_selected(self, tones: None) -> None:
        set_pane_tone(CheckerTone.LIGHT)
        set_picked_lightness(255.0)

        assert standing_tone() is CheckerTone.LIGHT

    def test_only_the_automatic_tone_measures_a_texture(self, tones: None) -> None:
        pixmap = QPixmap(8, 8)
        pixmap.fill(QColor(0xFF, 0xFF, 0xFF, 0x80))

        set_pane_tone(CheckerTone.AUTO)

        assert pane_lightness(pixmap) is not None

        set_pane_tone(CheckerTone.DARK)

        assert pane_lightness(pixmap) is None

    def test_no_checkerboard_means_no_colours_to_paint(self, tones: None) -> None:
        set_pane_tone(CheckerTone.NONE)

        assert pane_colors() is None
        assert pane_checkerboard() is None


class TestTiles:
    def test_a_tile_is_two_squares_on_a_side(self, app: QApplication) -> None:
        tile = checker_tile(QColor("white"), QColor("black"))

        assert tile.width() == CHECKERBOARD_SIZE * 2
        assert tile.height() == CHECKERBOARD_SIZE * 2

    def test_the_squares_alternate(self, app: QApplication) -> None:
        tile = checker_tile(QColor("white"), QColor("black"))

        assert tile.pixelColor(0, 0) == QColor("black")
        assert tile.pixelColor(CHECKERBOARD_SIZE, 0) == QColor("white")
        assert tile.pixelColor(0, CHECKERBOARD_SIZE) == QColor("white")
        assert tile.pixelColor(CHECKERBOARD_SIZE, CHECKERBOARD_SIZE) == QColor("black")

    def test_a_tile_can_be_asked_for_at_another_size(self, app: QApplication) -> None:
        assert checker_tile(QColor("white"), QColor("black"), 3).width() == 6


class TestOverCheckerboard:
    def test_an_opaque_image_is_handed_straight_back(self, tones: None) -> None:
        image = QImage(4, 4, QImage.Format.Format_RGB32)
        image.fill(QColor("red"))

        assert over_checkerboard(image) is image

    def test_a_transparent_image_comes_back_opaque(self, tones: None) -> None:
        set_grid_tone(CheckerTone.LIGHT)

        image = QImage(4, 4, QImage.Format.Format_ARGB32)
        image.fill(QColor(0xFF, 0x00, 0x00, 0x80))

        assert not over_checkerboard(image).hasAlphaChannel()

    def test_with_the_checkerboard_off_the_transparency_is_left_alone(self, tones: None) -> None:
        set_grid_tone(CheckerTone.NONE)

        image = QImage(4, 4, QImage.Format.Format_ARGB32)
        image.fill(QColor(0xFF, 0x00, 0x00, 0x80))

        assert over_checkerboard(image) is image


class TestSync:
    def test_the_generation_moves_when_the_grid_tone_does(self, tones: None) -> None:
        set_grid_tone(CheckerTone.LIGHT)

        before = checkerboard_generation()

        state().grid = CheckerTone.DARK

        assert sync_checkerboard() is True
        assert checkerboard_generation() > before

    def test_a_sync_that_changes_nothing_leaves_the_cells_alone(self, tones: None) -> None:
        set_grid_tone(CheckerTone.LIGHT)
        sync_checkerboard()

        before = checkerboard_generation()

        assert sync_checkerboard() is False
        assert checkerboard_generation() == before
