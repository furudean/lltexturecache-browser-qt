"""The pile of cards that stands for a selection"""

from collections.abc import Iterator

import pytest
from PySide6.QtGui import QPixmap, QPixmapCache
from PySide6.QtWidgets import QApplication

from lltexturecache_browser_qt.grid.cards import grid_cards, stack_textures
from lltexturecache_browser_qt.grid.model import TextureModel, sidebar_key
from lltexturecache_browser_qt.view.stack import STACK_CARDS
from tests import fakes


@pytest.fixture
def model(app: QApplication, quiet_scan: None) -> Iterator[TextureModel]:
    QPixmapCache.clear()

    built = TextureModel(fakes.textures(40), fakes.cache())

    yield built

    built.shutdown()


def swatch(color: str = "red") -> QPixmap:
    """A card of a nameable colour, so two of them can be told apart"""

    return fakes.card(color=color)


class TestStackTextures:
    def test_one_texture_makes_a_pile_of_one(self, model: TextureModel) -> None:
        index = model.index(3, 0)

        assert [texture.uuid for texture in stack_textures(model, index, [index])] == ["texture-3"]

    def test_the_current_texture_is_the_card_on_top(self, model: TextureModel) -> None:
        index = model.index(3, 0)
        selected = [model.index(row, 0) for row in (1, 3, 5)]

        assert stack_textures(model, index, selected)[-1].uuid == "texture-3"

    def test_a_pile_is_never_deeper_than_the_stack_holds(self, model: TextureModel) -> None:
        index = model.index(0, 0)
        selected = [model.index(row, 0) for row in range(40)]

        assert len(stack_textures(model, index, selected)) == STACK_CARDS

    def test_a_large_selection_is_sampled_across_rather_than_off_the_front(self, model: TextureModel) -> None:
        index = model.index(0, 0)
        selected = [model.index(row, 0) for row in range(40)]

        rows = [int(texture.uuid.removeprefix("texture-")) for texture in stack_textures(model, index, selected)]

        # the cards under the top one come from across the selection
        assert max(rows[:-1]) > STACK_CARDS

    def test_the_current_texture_is_never_dealt_twice(self, model: TextureModel) -> None:
        index = model.index(2, 0)
        selected = [model.index(row, 0) for row in range(6)]

        uuids = [texture.uuid for texture in stack_textures(model, index, selected)]

        assert uuids.count("texture-2") == 1


class TestGridCards:
    def test_a_texture_with_a_cell_is_drawn_from_it(self, model: TextureModel) -> None:
        QPixmapCache.insert("texture-0", swatch("blue"))

        cards = grid_cards(model, [model.texture(0)])

        assert [uuid for uuid, _ in cards] == ["texture-0"]

    def test_a_texture_with_no_cell_falls_back_to_the_thumbnail(self, model: TextureModel) -> None:
        QPixmapCache.insert(sidebar_key("texture-1"), swatch("green"))

        assert [uuid for uuid, _ in grid_cards(model, [model.texture(1)])] == ["texture-1"]

    def test_a_texture_with_neither_is_left_off_the_pile(self, model: TextureModel) -> None:
        # the fake has no thumbnail either, so the sidebar falls to the
        # placeholder, which is a real pixmap and does go on the pile
        cards = grid_cards(model, [model.texture(2)])

        assert all(not pixmap.isNull() for _, pixmap in cards)

    def test_nothing_selected_makes_no_cards(self, model: TextureModel) -> None:
        assert grid_cards(model, []) == []

    def test_every_card_carries_the_uuid_it_was_drawn_for(self, model: TextureModel) -> None:
        textures = [model.texture(row) for row in range(3)]

        assert [uuid for uuid, _ in grid_cards(model, textures)] == [t.uuid for t in textures]
