"""Which rows of a grid to decode, and in what order

The grid asks for a band of rows around the viewport rather than only the ones
on screen, so a scroll lands on cells that are already in. Working out that
band is geometry over the view and the model, and nothing about the window it
sits in, so it is worked out here.
"""

from bisect import bisect_left, bisect_right

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QListView

from lltexturecache_browser_qt.grid.model import TextureModel

# how far past the viewport, in screenfuls, cells are decoded ahead
PREFETCH_SCREENS = 2


def reach(view: QListView) -> int:
    """How far past the viewport, in pixels, cells are decoded ahead"""

    return round(view.viewport().height() * PREFETCH_SCREENS)


def rows_within(view: QListView, model: TextureModel, margin: int) -> tuple[int, int] | None:
    """The rows of the band the viewport sits in the middle of

    A grid lays its rows out in order down the viewport, so where a row sits is
    monotonic in the row number and the two edges of the band can be found by
    bisection rather than by walking a cache of many thousand cells.
    """

    count = model.rowCount()
    height = view.viewport().height()

    def cell(row: int) -> QRect:
        return view.visualRect(model.index(row, 0))

    first = bisect_left(range(count), -margin, key=lambda row: cell(row).bottom())
    last = bisect_right(range(count), height + margin, key=lambda row: cell(row).top()) - 1

    return (first, last) if first <= last < count else None


def visible_rows(view: QListView, model: TextureModel) -> tuple[int, int] | None:
    return rows_within(view, model, 0)


def outward(band: tuple[int, int], visible: tuple[int, int]) -> list[int]:
    """The rows of the band, the furthest from what is on screen first

    The model decodes the last of these first, so the order runs backwards.
    Sorting on the distance from the middle of the viewport puts every row
    that is on screen after every row that is not, since none of the ones
    on screen can be further from its middle than its own edges are: what
    the user is looking at is decoded first, from the middle out, and only
    then does the band either side of it get a turn.
    """

    first, last = band
    middle = sum(visible) / 2

    return sorted(range(first, last + 1), key=lambda row: -abs(row - middle))


def prefetch(view: QListView, model: TextureModel) -> None:
    visible = visible_rows(view, model)
    band = rows_within(view, model, reach(view))

    if visible is None or band is None:
        return

    model.prefetch(outward(band, visible), range(visible[0], visible[1] + 1))
