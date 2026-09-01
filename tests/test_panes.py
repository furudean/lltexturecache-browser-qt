"""Filling the inspector's sidebar from a selection"""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QPixmap, QPixmapCache
from PySide6.QtWidgets import QApplication

from lltexturecache_browser_qt.panes.inspector import InspectorPane
from lltexturecache_browser_qt.grid.model import FULL_SIZE, TextureModel, alpha_key
from lltexturecache_browser_qt.panes.sidebar import laid_card, paint, shape, standing_cards
from tests import fakes


@pytest.fixture
def model(app: QApplication, quiet_scan: None) -> Iterator[TextureModel]:
    QPixmapCache.clear()

    built = TextureModel(fakes.textures(5), fakes.cache())

    yield built

    built.shutdown()


@pytest.fixture
def pane(app: QApplication) -> Iterator[InspectorPane]:
    built = InspectorPane()

    yield built

    built.close()


def card(width: int = 8, height: int = 8) -> QPixmap:
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor("red"))

    return pixmap


class TestLaidCard:
    def test_a_card_already_the_right_size_is_handed_straight_back(self, app: QApplication) -> None:
        pixmap = QPixmap(64, 64)

        assert laid_card(pixmap, QSize(64, 64)) is pixmap

    def test_a_texture_with_no_known_shape_leaves_the_card_alone(self, app: QApplication) -> None:
        pixmap = card()

        assert laid_card(pixmap, QSize()) is pixmap

    def test_a_stand_in_is_laid_out_at_the_size_the_texture_will_be(self, app: QApplication) -> None:
        assert laid_card(card(), QSize(400, 200)).size() == QSize(400, 200)

    def test_a_large_texture_is_laid_out_within_the_inspector_box(self, app: QApplication) -> None:
        assert laid_card(card(), QSize(4000, 2000)).size() == QSize(FULL_SIZE, FULL_SIZE // 2)


class TestShape:
    def test_a_texture_still_decoding_has_no_shape_yet(self, model: TextureModel) -> None:
        assert shape(model, model.texture(0)) is None

    def test_a_decoded_texture_reports_the_size_it_was_drawn_at(self, model: TextureModel) -> None:
        model.learn("texture-0", QSize(512, 256))

        assert shape(model, model.texture(0)) == QSize(512, 256)

    def test_a_texture_that_would_not_decode_reports_an_empty_size(self, model: TextureModel) -> None:
        from PySide6.QtGui import QImage

        model.full_decoded("texture-0", QImage(), QSize())

        assert shape(model, model.texture(0)) == QSize()


class TestStandingCards:
    def test_a_texture_with_a_decode_in_hand_makes_a_card(self, model: TextureModel) -> None:
        QPixmapCache.insert(alpha_key("texture-0"), card())

        assert [uuid for uuid, _ in standing_cards(model, [model.texture(0)])] == ["texture-0"]

    def test_nothing_selected_makes_no_cards(self, model: TextureModel) -> None:
        assert standing_cards(model, []) == []

    def test_cards_come_back_in_the_order_they_were_asked_for(self, model: TextureModel) -> None:
        for row in range(3):
            QPixmapCache.insert(alpha_key(f"texture-{row}"), card())

        textures = [model.texture(row) for row in (2, 0, 1)]

        assert [uuid for uuid, _ in standing_cards(model, textures)] == ["texture-2", "texture-0", "texture-1"]


class TestPaint:
    def test_painting_nothing_leaves_the_pane_alone(self, pane: InspectorPane, model: TextureModel) -> None:
        paint(pane, model, [])

        assert pane.texture is None

    def test_a_selection_puts_a_pile_in_the_sidebar(self, pane: InspectorPane, model: TextureModel) -> None:
        for row in range(3):
            QPixmapCache.insert(alpha_key(f"texture-{row}"), card())

        textures = [model.texture(row) for row in range(3)]

        pane.show_texture(textures[-1], len(textures), 3072)
        paint(pane, model, textures)

        assert not pane._sidebar._source.isNull()

    def test_a_texture_still_decoding_says_so_in_the_pane(self, pane: InspectorPane, model: TextureModel) -> None:
        texture = model.texture(0)

        pane.show_texture(texture, 1, 1024)
        paint(pane, model, [texture])

        assert pane._dimensions.text() == "Decoding..."

    def test_a_decoded_texture_reports_its_shape_in_the_pane(self, pane: InspectorPane, model: TextureModel) -> None:
        texture = model.texture(0)

        QPixmapCache.insert(alpha_key("texture-0"), card())
        model.learn("texture-0", QSize(512, 256))

        pane.show_texture(texture, 1, 1024)
        paint(pane, model, [texture])

        assert "512" in pane._dimensions.text()
