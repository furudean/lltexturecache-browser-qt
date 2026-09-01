"""The line the status bar rests on

What a window has to say about itself when nothing has happened lately: how
much of the cache is in the grid, and what is being left out of it.
"""

from lltexturecache_browser_qt.grid.model import TextureModel
from lltexturecache_browser_qt.view.formatting import format_count


def narrowed_summary(model: TextureModel) -> str:
    return f"Showing {format_count(model.rowCount())} of {format_count(model.total())} textures matching filters"


def grid_summary(model: TextureModel, entries: int, *, counting_incomplete: bool) -> str:
    """What the grid holds, out of what the cache does"""

    shown = model.rowCount()

    summary = f"Showing {format_count(shown)} textures of {format_count(entries)} entries in cache"

    # both counts are of the rows the grid ended up with rather than of the
    # cache, since an entry left out of it is neither shown nor news
    unfinished = sum(1 for row in range(shown) if not model.texture(row).whole()) if counting_incomplete else 0

    if unfinished:
        summary += f", {format_count(unfinished)} incomplete"

    hidden = model.hidden()

    if hidden:
        summary += f", {format_count(hidden)} simple textures hidden"

    return summary


def empty_message(model: TextureModel | None) -> str:
    """What an empty grid says, which turns on why it is empty"""

    if model is None or not (model.narrowed or model.hidden()):
        return "Cache is empty"

    return "No textures match filters"
