"""The list model behind the grid: what it holds, what it hides, what it ranks"""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QImage, QPixmap, QPixmapCache
from PySide6.QtWidgets import QApplication
from texture_courier import Texture

from lltexturecache_browser_qt import model as module
from lltexturecache_browser_qt.color import ColorIndex, Signature, to_lab
from lltexturecache_browser_qt.model import (
    AHEAD_PRIORITY,
    CELL_PRIORITY,
    FULL_SIZE,
    INCOMPLETE_ROLE,
    SIMPLE_ROLE,
    TextureModel,
    alpha_key,
    full_size,
    sidebar_key,
)
from tests import fakes


@pytest.fixture
def textures() -> list[Texture]:
    return fakes.textures(5)


@pytest.fixture
def model(app: QApplication, quiet_scan: None, textures: list[Texture]) -> Iterator[TextureModel]:
    QPixmapCache.clear()

    built = TextureModel(textures, fakes.cache())

    yield built

    built.shutdown()


class TestKeys:
    def test_a_texture_has_its_own_key_for_each_kind_of_decode(self) -> None:
        assert len({"uuid", sidebar_key("uuid"), alpha_key("uuid")}) == 3

    def test_two_textures_never_share_a_key(self) -> None:
        assert sidebar_key("one") != sidebar_key("two")
        assert alpha_key("one") != alpha_key("two")


class TestFullSize:
    def test_a_large_texture_is_brought_down_to_the_inspector_box(self) -> None:
        assert full_size(QSize(4000, 2000)) == QSize(FULL_SIZE, FULL_SIZE // 2)

    def test_a_small_texture_is_left_at_its_own_size(self) -> None:
        assert full_size(QSize(64, 32)) == QSize(64, 32)

    def test_a_texture_exactly_the_box_size_is_left_alone(self) -> None:
        assert full_size(QSize(FULL_SIZE, FULL_SIZE)) == QSize(FULL_SIZE, FULL_SIZE)


class TestRows:
    def test_every_texture_gets_a_row(self, model: TextureModel, textures: list[Texture]) -> None:
        assert model.rowCount() == len(textures)
        assert model.total() == len(textures)

    def test_a_list_model_has_no_rows_under_a_row(self, model: TextureModel) -> None:
        assert model.rowCount(model.index(0, 0)) == 0

    def test_a_row_can_be_found_by_uuid(self, model: TextureModel) -> None:
        assert model.row("texture-2") == 2

    def test_a_uuid_that_is_not_showing_has_no_row(self, model: TextureModel) -> None:
        assert model.row("not-in-the-cache") is None

    def test_a_row_hands_back_its_texture(self, model: TextureModel) -> None:
        assert model.texture(2).uuid == "texture-2"

    def test_nothing_is_narrowed_to_begin_with(self, model: TextureModel) -> None:
        assert model.narrowed is False
        assert model.colors == []
        assert model.hidden() == 0


class TestData:
    def test_an_invalid_index_holds_nothing(self, model: TextureModel) -> None:
        assert model.data(module.ROOT) is None

    def test_a_role_the_model_does_not_answer_for_holds_nothing(self, model: TextureModel) -> None:
        assert model.data(model.index(0, 0), Qt.ItemDataRole.EditRole) is None

    def test_a_complete_texture_is_not_marked_incomplete(self, model: TextureModel) -> None:
        assert model.data(model.index(0, 0), INCOMPLETE_ROLE) is False

    def test_an_incomplete_texture_is_marked(self, app: QApplication, quiet_scan: None) -> None:
        built = TextureModel([fakes.texture(uuid="partial", complete=False)], fakes.cache())

        try:
            assert built.data(built.index(0, 0), INCOMPLETE_ROLE) is True
        finally:
            built.shutdown()

    def test_the_tip_names_the_texture_and_when_it_was_cached(self, model: TextureModel) -> None:
        tip = model.data(model.index(0, 0), Qt.ItemDataRole.ToolTipRole)

        assert isinstance(tip, str)
        assert "texture-0" in tip
        assert len(tip.splitlines()) == 2

    def test_an_incomplete_texture_says_how_much_of_it_arrived(self, app: QApplication, quiet_scan: None) -> None:
        built = TextureModel([fakes.texture(uuid="partial", complete=False)], fakes.cache())

        try:
            tip = built.data(built.index(0, 0), Qt.ItemDataRole.ToolTipRole)

            assert isinstance(tip, str)
            assert "Incomplete" in tip
        finally:
            built.shutdown()

    def test_a_row_can_be_dragged_out(self, model: TextureModel) -> None:
        assert model.flags(model.index(0, 0)) & Qt.ItemFlag.ItemIsDragEnabled

    def test_the_root_cannot_be_dragged(self, model: TextureModel) -> None:
        assert not model.flags(module.ROOT) & Qt.ItemFlag.ItemIsDragEnabled


class TestWanted:
    def test_an_undecoded_texture_is_wanted(self, model: TextureModel) -> None:
        assert model.wanted(model.texture(0)) is True

    def test_an_incomplete_texture_is_never_decoded(self, app: QApplication, quiet_scan: None) -> None:
        built = TextureModel([fakes.texture(uuid="partial", complete=False)], fakes.cache())

        try:
            assert built.wanted(built.texture(0)) is False
        finally:
            built.shutdown()

    def test_a_texture_already_decoded_is_not_wanted_again(self, model: TextureModel) -> None:
        pixmap = QPixmap(4, 4)
        pixmap.fill(QColor("red"))

        QPixmapCache.insert("texture-0", pixmap)

        assert model.wanted(model.texture(0)) is False

    def test_a_texture_that_failed_is_not_asked_for_again(self, model: TextureModel) -> None:
        model.decoded("texture-0", QImage(), QSize())

        assert model.wanted(model.texture(0)) is False


class TestQueue:
    def test_a_texture_is_queued_once(self, model: TextureModel) -> None:
        assert model.enqueue(model.texture(0), CELL_PRIORITY) is True
        assert model.enqueue(model.texture(0), CELL_PRIORITY) is False

    def test_a_more_urgent_ask_moves_a_queued_texture_up(self, model: TextureModel) -> None:
        model.enqueue(model.texture(0), AHEAD_PRIORITY)

        assert model.enqueue(model.texture(0), CELL_PRIORITY) is True

    def test_a_less_urgent_ask_leaves_a_queued_texture_where_it_is(self, model: TextureModel) -> None:
        model.enqueue(model.texture(0), CELL_PRIORITY)

        assert model.enqueue(model.texture(0), AHEAD_PRIORITY) is False

    def test_prefetching_puts_what_is_on_screen_first(
        self, model: TextureModel, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        started: dict[str, int] = {}

        # the queue drains straight into the pool, so the order it was in is
        # only visible in the priority each decode was handed
        monkeypatch.setattr(
            model._pool,
            "start",
            lambda task, priority: started.__setitem__(task._texture.uuid, priority),
        )

        model.prefetch(range(5), (2, 3))

        assert started["texture-2"] == CELL_PRIORITY
        assert started["texture-3"] == CELL_PRIORITY
        assert started["texture-0"] == AHEAD_PRIORITY

    def test_prefetching_leaves_out_what_is_already_decoded(
        self, model: TextureModel, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pixmap = QPixmap(4, 4)
        pixmap.fill(QColor("red"))

        QPixmapCache.insert("texture-0", pixmap)

        started: list[str] = []

        monkeypatch.setattr(
            model._pool,
            "start",
            lambda task, priority: started.append(task._texture.uuid),
        )

        model.prefetch(range(5), ())

        assert "texture-0" not in started


class TestDecoded:
    def test_a_decoded_texture_lands_in_the_cache(self, model: TextureModel) -> None:
        image = QImage(4, 4, QImage.Format.Format_RGB32)
        image.fill(QColor("red"))

        model.decoded("texture-0", image, QSize(64, 64))

        assert QPixmapCache.find("texture-0", QPixmap()) is True

    def test_a_decode_reports_the_size_the_texture_was_stored_at(self, model: TextureModel) -> None:
        image = QImage(4, 4, QImage.Format.Format_RGB32)
        image.fill(QColor("red"))

        model.decoded("texture-0", image, QSize(64, 64))

        assert model.natural(model.texture(0)) == QSize(64, 64)

    def test_a_decode_that_learned_nothing_leaves_the_size_unknown(self, model: TextureModel) -> None:
        model.decoded("texture-0", QImage(), QSize())

        assert model.natural(model.texture(0)) == QSize()

    def test_the_real_decode_retires_the_sidebar_thumbnail(self, model: TextureModel) -> None:
        stand_in = QPixmap(4, 4)
        stand_in.fill(QColor("blue"))

        QPixmapCache.insert(sidebar_key("texture-0"), stand_in)

        image = QImage(4, 4, QImage.Format.Format_RGB32)
        image.fill(QColor("red"))

        model.decoded("texture-0", image, QSize(64, 64))

        assert QPixmapCache.find(sidebar_key("texture-0"), QPixmap()) is False

    def test_a_decode_announces_the_row_it_landed_on(self, model: TextureModel) -> None:
        seen: list[int] = []
        model.dataChanged.connect(lambda top, bottom, roles: seen.append(top.row()))

        image = QImage(4, 4, QImage.Format.Format_RGB32)
        image.fill(QColor("red"))

        model.decoded("texture-1", image, QSize(64, 64))

        assert seen == [1]

    def test_a_decode_for_a_row_no_longer_showing_announces_nothing(self, model: TextureModel) -> None:
        seen: list[object] = []
        model.dataChanged.connect(lambda *args: seen.append(args))

        model.decoded("not-in-the-cache", QImage(), QSize())

        assert seen == []


class TestFilters:
    def test_with_no_scan_in_yet_a_filter_cannot_be_applied(self, model: TextureModel) -> None:
        assert model.set_filters([QColor("red")]) is False

    def test_clearing_the_filters_always_applies(self, model: TextureModel) -> None:
        assert model.set_filters([]) is True
        assert model.rowCount() == 5

    def test_a_filter_narrows_the_rows_to_what_answers(self, model: TextureModel) -> None:
        index = ColorIndex(5)
        index.add(0, Signature(colors=[(to_lab(0xFF0000), 1.0)]))
        index.add(1, Signature(colors=[(to_lab(0x0000FF), 1.0)]))

        model.scanned(index)

        assert model.set_filters([QColor("red")]) is True
        assert model.narrowed is True
        assert model.texture(0).uuid == "texture-0"
        assert model.rowCount() < 5

    def test_clearing_a_filter_puts_every_row_back(self, model: TextureModel) -> None:
        index = ColorIndex(5)
        index.add(0, Signature(colors=[(to_lab(0xFF0000), 1.0)]))

        model.scanned(index)
        model.set_filters([QColor("red")])
        model.set_filters([])

        assert model.rowCount() == 5
        assert model.narrowed is False

    def test_hiding_flat_textures_leaves_them_out(self, model: TextureModel) -> None:
        index = ColorIndex(5)
        index.add(0, Signature(flat=True))
        index.add(1, Signature(colors=[(to_lab(0x0000FF), 1.0)]))

        model.scanned(index)

        assert model.set_simple_hidden(True) is True
        assert model.rowCount() == 4
        assert model.hidden() == 1
        assert model.row("texture-0") is None

    def test_showing_flat_textures_again_puts_them_back(self, model: TextureModel) -> None:
        index = ColorIndex(5)
        index.add(0, Signature(flat=True))

        model.scanned(index)
        model.set_simple_hidden(True)
        model.set_simple_hidden(False)

        assert model.rowCount() == 5
        assert model.hidden() == 0

    def test_a_flat_texture_is_marked_when_it_is_shown(self, model: TextureModel) -> None:
        index = ColorIndex(5)
        index.add(0, Signature(flat=True))

        model.scanned(index)

        assert model.data(model.index(0, 0), SIMPLE_ROLE) is True
        assert model.data(model.index(1, 0), SIMPLE_ROLE) is False

    def test_a_scan_that_narrows_the_grid_says_so(self, model: TextureModel) -> None:
        ranked: list[None] = []
        model.ranked.connect(lambda: ranked.append(None))

        model.set_simple_hidden(True)

        index = ColorIndex(5)
        index.add(0, Signature(flat=True))

        model.scanned(index)

        assert len(ranked) == 1

    def test_reordering_to_what_is_already_showing_does_nothing(self, model: TextureModel) -> None:
        resets: list[None] = []
        model.modelReset.connect(lambda: resets.append(None))

        model.reorder(list(model._filtered_textures))

        assert resets == []


class TestRestyle:
    def test_a_checkerboard_that_has_not_moved_needs_no_notice(self, model: TextureModel) -> None:
        assert model.restyle() is False

    def test_a_moved_checkerboard_stales_the_decodes_already_out(
        self, model: TextureModel, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        model._running = {"texture-0"}

        monkeypatch.setattr(module, "checkerboard_generation", lambda: 10_000)

        assert model.restyle() is True
        assert model._stale == {"texture-0"}

    def test_a_stale_decode_is_thrown_away_rather_than_cached(
        self, model: TextureModel, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        model._running = {"texture-0"}

        monkeypatch.setattr(module, "checkerboard_generation", lambda: 10_000)

        model.restyle()

        image = QImage(4, 4, QImage.Format.Format_RGB32)
        image.fill(QColor("red"))

        model.decoded("texture-0", image, QSize(64, 64))

        assert QPixmapCache.find("texture-0", QPixmap()) is False
