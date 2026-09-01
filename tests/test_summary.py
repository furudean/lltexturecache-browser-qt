"""The line the status bar rests on"""

from collections.abc import Iterator

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from lltexturecache_browser_qt.cache.color import ColorIndex, Signature, to_lab
from lltexturecache_browser_qt.grid.model import TextureModel
from lltexturecache_browser_qt.grid.summary import empty_message, grid_summary, narrowed_summary
from tests import fakes


@pytest.fixture
def model(app: QApplication, quiet_scan: None) -> Iterator[TextureModel]:
    built = TextureModel(fakes.textures(10), fakes.cache())

    yield built

    built.shutdown()


@pytest.fixture
def partial(app: QApplication, quiet_scan: None) -> Iterator[TextureModel]:
    textures = [*fakes.textures(6), fakes.texture(uuid="half", complete=False)]

    built = TextureModel(textures, fakes.cache())

    yield built

    built.shutdown()


class TestGridSummary:
    def test_what_the_grid_holds_is_counted_against_the_cache(self, model: TextureModel) -> None:
        line = grid_summary(model, 40, counting_incomplete=False)

        assert "10 textures" in line
        assert "40 entries" in line

    def test_incomplete_entries_are_counted_when_they_are_being_shown(self, partial: TextureModel) -> None:
        assert "1 incomplete" in grid_summary(partial, 40, counting_incomplete=True)

    def test_they_are_not_counted_when_they_are_not(self, partial: TextureModel) -> None:
        assert "incomplete" not in grid_summary(partial, 40, counting_incomplete=False)

    def test_a_grid_with_nothing_left_out_says_nothing_about_it(self, model: TextureModel) -> None:
        line = grid_summary(model, 40, counting_incomplete=True)

        assert "incomplete" not in line
        assert "hidden" not in line

    def test_hidden_simple_textures_are_counted(self, model: TextureModel) -> None:
        index = ColorIndex(10)
        index.add(0, Signature(flat=True))
        index.add(1, Signature(flat=True))

        model.scanned(index)
        model.set_simple_hidden(True)

        assert "2 simple textures hidden" in grid_summary(model, 40, counting_incomplete=False)

    def test_large_counts_are_written_out_grouped(self, model: TextureModel) -> None:
        assert "20000 entries" not in grid_summary(model, 20000, counting_incomplete=False)


class TestNarrowedSummary:
    def test_what_matched_is_counted_against_the_whole_cache(self, model: TextureModel) -> None:
        index = ColorIndex(10)
        index.add(0, Signature(colors=[(to_lab(0xFF0000), 1.0)]))

        model.scanned(index)
        model.set_filters([QColor("red")])

        line = narrowed_summary(model)

        assert "matching filters" in line
        assert "of 10 textures" in line


class TestEmptyMessage:
    def test_a_grid_with_no_model_is_an_empty_cache(self) -> None:
        assert empty_message(None) == "Cache is empty"

    def test_a_cache_holding_nothing_says_so(self, app: QApplication, quiet_scan: None) -> None:
        built = TextureModel([], fakes.cache())

        try:
            assert empty_message(built) == "Cache is empty"
        finally:
            built.shutdown()

    def test_a_grid_emptied_by_filters_says_so_instead(self, model: TextureModel) -> None:
        index = ColorIndex(10)
        index.add(0, Signature(colors=[(to_lab(0x0000FF), 1.0)]))

        model.scanned(index)
        model.set_filters([QColor("red")])

        assert empty_message(model) == "No textures match filters"

    def test_a_grid_emptied_by_hiding_simple_textures_says_so(self, model: TextureModel) -> None:
        index = ColorIndex(10)

        for row in range(10):
            index.add(row, Signature(flat=True))

        model.scanned(index)
        model.set_simple_hidden(True)

        assert empty_message(model) == "No textures match filters"
