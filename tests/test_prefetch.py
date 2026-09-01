"""Which rows of the grid are decoded ahead, and in what order"""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication, QListView

from lltexturecache_browser_qt.images import THUMBNAIL_SIZE
from lltexturecache_browser_qt.model import TextureModel
from lltexturecache_browser_qt.prefetch import (
    PREFETCH_SCREENS,
    outward,
    prefetch,
    reach,
    rows_within,
    visible_rows,
)
from tests import fakes


@pytest.fixture
def model(app: QApplication, quiet_scan: None) -> Iterator[TextureModel]:
    built = TextureModel(fakes.textures(200), fakes.cache())

    yield built

    built.shutdown()


@pytest.fixture
def view(app: QApplication, model: TextureModel) -> Iterator[QListView]:
    built = QListView()
    built.setViewMode(QListView.ViewMode.IconMode)
    built.setIconSize(QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE))
    built.setResizeMode(QListView.ResizeMode.Adjust)
    built.setUniformItemSizes(True)
    built.setModel(model)
    built.resize(400, 300)
    built.show()

    app.processEvents()

    yield built

    built.close()


class TestOutward:
    def test_a_band_of_one_row_is_that_row(self) -> None:
        assert outward((5, 5), (5, 5)) == [5]

    def test_the_row_in_the_middle_of_the_viewport_comes_last(self) -> None:
        assert outward((0, 10), (4, 6))[-1] == 5

    def test_the_furthest_row_comes_first(self) -> None:
        walked = outward((0, 20), (10, 10))

        assert walked[0] in (0, 20)

    def test_every_row_of_the_band_is_walked_once(self) -> None:
        walked = outward((3, 12), (7, 9))

        assert sorted(walked) == list(range(3, 13))

    def test_nothing_on_screen_is_decoded_before_anything_off_it(self) -> None:
        band, visible = (0, 20), (8, 12)

        walked = outward(band, visible)
        showing = {row for row in range(visible[0], visible[1] + 1)}

        # the on-screen rows are drained last, so they are a run at the end
        assert all(row in showing for row in walked[-len(showing) :])


class TestReach:
    def test_the_band_runs_a_few_screenfuls_past_the_viewport(self, view: QListView) -> None:
        assert reach(view) == round(view.viewport().height() * PREFETCH_SCREENS)

    def test_a_taller_viewport_reaches_further(self, view: QListView, app: QApplication) -> None:
        shorter = reach(view)

        view.resize(400, 900)
        app.processEvents()

        assert reach(view) > shorter


class TestRowsWithin:
    def test_the_first_rows_are_the_ones_on_screen(self, view: QListView, model: TextureModel) -> None:
        band = visible_rows(view, model)

        assert band is not None
        assert band[0] == 0
        assert band[1] < model.rowCount()

    def test_a_margin_takes_in_more_rows(self, view: QListView, model: TextureModel) -> None:
        near = visible_rows(view, model)
        wide = rows_within(view, model, reach(view))

        assert near is not None and wide is not None
        assert wide[1] >= near[1]

    def test_an_empty_model_has_no_band(self, view: QListView, app: QApplication, quiet_scan: None) -> None:
        empty = TextureModel([], fakes.cache())

        try:
            view.setModel(empty)
            app.processEvents()

            assert visible_rows(view, empty) is None
        finally:
            empty.shutdown()


class TestPrefetch:
    def test_the_band_is_handed_to_the_model(
        self, view: QListView, model: TextureModel, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked: list[tuple[list[int], range]] = []

        monkeypatch.setattr(model, "prefetch", lambda rows, showing: asked.append((list(rows), showing)))

        prefetch(view, model)

        assert len(asked) == 1
        assert asked[0][0]

    def test_a_grid_with_no_rows_asks_for_nothing(
        self, view: QListView, app: QApplication, quiet_scan: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        empty = TextureModel([], fakes.cache())

        try:
            view.setModel(empty)
            app.processEvents()

            asked: list[object] = []

            monkeypatch.setattr(empty, "prefetch", lambda rows, showing: asked.append(rows))

            prefetch(view, empty)

            assert asked == []
        finally:
            empty.shutdown()
