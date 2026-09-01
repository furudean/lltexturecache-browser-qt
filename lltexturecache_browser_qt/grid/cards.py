"""The pile of cards that stands for a selection

Both the inspector's sidebar and the pixmap under a drag show a selection as a
stack of textures rather than as whichever one happens to be current. Which
textures go on the pile, and what each of them is drawn from, is the same
question in both places, so it is answered here.
"""

from PySide6.QtCore import QModelIndex
from PySide6.QtGui import QPixmap
from texture_courier import Texture

from lltexturecache_browser_qt.grid.model import TextureModel
from lltexturecache_browser_qt.view.stack import STACK_CARDS

type Card = tuple[str, QPixmap]


def stack_textures(model: TextureModel, index: QModelIndex, selected: list[QModelIndex]) -> list[Texture]:
    """The textures a selection is shown as, the current one last

    A pile is a handful of cards however much is selected, so the rest are
    sampled at an even stride through the selection rather than taken off the
    front of it: a thousand textures picked in one drag still reads as a look
    at what was picked rather than at its first four rows.
    """

    top = model.texture(index.row())
    others = [model.texture(other.row()) for other in selected if other.row() != index.row()]

    if not others:
        return [top]

    step = max(1, len(others) // (STACK_CARDS - 1))

    return [*others[::step][: STACK_CARDS - 1], top]


def grid_cards(model: TextureModel, textures: list[Texture]) -> list[Card]:
    """Cards drawn from what the grid already holds, for a drag

    A drag has to be laid out on the spot, so nothing is decoded for it: a
    texture with no cell yet falls back to the thumbnail beside it in the
    cache, and one with neither is left off the pile.
    """

    cards = []

    for texture in textures:
        cell = model.cell(texture)
        card = model.sidebar(texture) if cell.isNull() else cell

        if not card.isNull():
            cards.append((texture.uuid, card))

    return cards
