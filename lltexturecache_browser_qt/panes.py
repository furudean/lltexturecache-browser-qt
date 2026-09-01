"""Filling the inspector's sidebar from a selection

The pane shows a pile of cards standing for whatever is selected, drawn from
the best decode of each texture that has landed so far and repainted as better
ones arrive. Which cards those are, how the pile is measured, and which of
them the automatic checkerboard is taken from is all one job, kept here rather
than spread across the window that holds the pane.
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from texture_courier import Texture

from lltexturecache_browser_qt.cards import Card
from lltexturecache_browser_qt.checkerboard import pixmap_lightness, set_picked_lightness
from lltexturecache_browser_qt.inspector import InspectorPane
from lltexturecache_browser_qt.model import TextureModel, full_size
from lltexturecache_browser_qt.stack import stack_pixmap


def laid_card(pixmap: QPixmap, natural: QSize) -> QPixmap:
    """A stand-in drawn at the size the real decode will be

    Otherwise the pile is laid out at whatever size the stand-in happened to
    be kept at and jumps when the decode lands.
    """

    laid = full_size(natural)

    if natural.isEmpty() or laid == pixmap.size():
        return pixmap

    # the stand-in is a picture of the same texture, so any shape it has that
    # the texture does not is rounding from the size it was kept at
    return pixmap.scaled(laid, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)


def shape(model: TextureModel, texture: Texture) -> QSize | None:
    """The size a texture was drawn at, an empty size if it would not decode

    Nothing at all while the decode is still out, which is what the pane shows
    as "Decoding..." rather than as a shape it does not know yet.
    """

    natural = model.natural(texture)

    if not natural.isEmpty():
        return natural

    return QSize() if model.full(texture, decode=False) is not None else None


def standing_cards(model: TextureModel, textures: list[Texture]) -> list[Card]:
    """The best decode of each texture that has landed, laid out to size"""

    cards = []

    for texture in textures:
        # a card goes in with whatever the grid or an earlier selection left
        # behind, until the selection settles and it is decoded properly
        ready = model.standing(texture)

        if ready is not None:
            cards.append((texture.uuid, laid_card(*ready)))

    return cards


def paint(pane: InspectorPane, model: TextureModel, textures: list[Texture]) -> None:
    """Repaint the sidebar from whatever decodes are in hand"""

    if not textures:
        return

    # only the texture on top is worth a decode on the spot
    model.full(textures[-1])

    cards = standing_cards(model, textures)

    # a hidden pane is repainted with whatever the last visible one was left on,
    # which is not what the preview beside it is showing
    if cards and pane.isVisible():
        # the card on top is the one the pane is really about, so the automatic
        # checkerboard behind that one is where a click in the pane carries on from
        set_picked_lightness(pixmap_lightness(cards[-1][1]))

    pane.set_sidebar(
        stack_pixmap(cards, pane.sidebar_room()),
        shape(model, textures[-1]),
        transparent=any(card.hasAlphaChannel() for _, card in cards),
    )
