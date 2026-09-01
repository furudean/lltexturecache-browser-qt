"""Keeping a selection across a grid that is rebuilt under it"""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QItemSelectionModel
from PySide6.QtWidgets import QApplication

from lltexturecache_browser_qt.model import TextureModel
from lltexturecache_browser_qt.selection import KeptSelection, row_spans
from tests import fakes


@pytest.fixture
def model(app: QApplication, quiet_scan: None) -> Iterator[TextureModel]:
    built = TextureModel(fakes.textures(10), fakes.cache())

    yield built

    built.shutdown()


@pytest.fixture
def selection(model: TextureModel) -> QItemSelectionModel:
    return QItemSelectionModel(model)


class TestRowSpans:
    def test_one_row_is_one_span(self, model: TextureModel) -> None:
        spans = row_spans(model, [2])

        assert spans.count() == 1
        assert (spans.at(0).top(), spans.at(0).bottom()) == (2, 2)

    def test_rows_running_together_are_one_span(self, model: TextureModel) -> None:
        spans = row_spans(model, [1, 2, 3])

        assert spans.count() == 1
        assert (spans.at(0).top(), spans.at(0).bottom()) == (1, 3)

    def test_a_gap_starts_a_new_span(self, model: TextureModel) -> None:
        spans = row_spans(model, [0, 1, 4, 5])

        assert [(spans.at(at).top(), spans.at(at).bottom()) for at in range(spans.count())] == [(0, 1), (4, 5)]

    def test_scattered_rows_are_each_their_own_span(self, model: TextureModel) -> None:
        assert row_spans(model, [0, 2, 4, 6]).count() == 4

    def test_every_row_asked_for_is_covered(self, model: TextureModel) -> None:
        rows = [0, 1, 2, 5, 8, 9]

        spans = row_spans(model, rows)
        covered = {index.row() for index in spans.indexes()}

        assert covered == set(rows)


class TestKeptSelection:
    def test_nothing_kept_restores_nothing(self, model: TextureModel, selection: QItemSelectionModel) -> None:
        KeptSelection().restore(model, selection)

        assert selection.selectedIndexes() == []

    def test_what_was_selected_is_taken_by_uuid(self, model: TextureModel) -> None:
        kept = KeptSelection.taken(model, [1, 3], 3)

        assert kept.uuids == ["texture-1", "texture-3"]
        assert kept.current == "texture-3"

    def test_nothing_current_is_kept_as_nothing(self, model: TextureModel) -> None:
        assert KeptSelection.taken(model, [1], None).current is None

    def test_a_selection_comes_back_at_the_same_rows(self, model: TextureModel, selection: QItemSelectionModel) -> None:
        KeptSelection.taken(model, [1, 3], 3).restore(model, selection)

        assert sorted(index.row() for index in selection.selectedIndexes()) == [1, 3]

    def test_the_texture_the_panes_were_on_comes_back_too(
        self, model: TextureModel, selection: QItemSelectionModel
    ) -> None:
        KeptSelection.taken(model, [1, 3], 3).restore(model, selection)

        assert selection.currentIndex().row() == 3

    def test_a_texture_the_grid_no_longer_shows_is_dropped(
        self, model: TextureModel, selection: QItemSelectionModel
    ) -> None:
        KeptSelection(uuids=["texture-1", "gone"]).restore(model, selection)

        assert sorted(index.row() for index in selection.selectedIndexes()) == [1]

    def test_a_current_texture_the_grid_no_longer_shows_leaves_it_unset(
        self, model: TextureModel, selection: QItemSelectionModel
    ) -> None:
        KeptSelection(uuids=["texture-1"], current="gone").restore(model, selection)

        assert selection.currentIndex().isValid() is False

    def test_a_selection_that_moved_rows_follows_its_textures(
        self, model: TextureModel, selection: QItemSelectionModel
    ) -> None:
        kept = KeptSelection.taken(model, [8], 8)

        # the grid is rebuilt with the rows in another order
        model.reorder([model.texture(row) for row in reversed(range(10))])

        kept.restore(model, selection)

        assert [index.row() for index in selection.selectedIndexes()] == [1]
