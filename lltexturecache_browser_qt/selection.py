"""Keeping a selection across a grid that is about to be rebuilt

Filtering, reloading and hiding rows all reset the model, which drops the
selection with it. The textures that were picked are still in the cache
though, so what was selected is remembered by uuid and put back at whatever
rows those textures landed on.
"""

from dataclasses import dataclass, field

from PySide6.QtCore import QItemSelection, QItemSelectionModel

from lltexturecache_browser_qt.model import TextureModel


def row_spans(model: TextureModel, rows: list[int]) -> QItemSelection:
    """Rows gathered into the runs Qt selects in

    A selection is made of spans rather than of rows, and handing over one
    span per row makes Qt merge several thousand of them by hand.
    """

    selection = QItemSelection()
    first = last = rows[0]

    for row in rows[1:]:
        if row == last + 1:
            last = row
            continue

        selection.select(model.index(first, 0), model.index(last, 0))

        first = last = row

    selection.select(model.index(first, 0), model.index(last, 0))

    return selection


@dataclass
class KeptSelection:
    """What was selected before a reset, by uuid rather than by row"""

    uuids: list[str] = field(default_factory=list)

    # the one of them the panes were on, which a reset loses separately from
    # the selection itself
    current: str | None = None

    @classmethod
    def taken(cls, model: TextureModel, selected: list[int], current: int | None) -> "KeptSelection":
        return cls(
            uuids=[model.texture(row).uuid for row in selected],
            current=model.texture(current).uuid if current is not None else None,
        )

    def restore(self, model: TextureModel, selection: QItemSelectionModel) -> None:
        """Put the selection back at whatever rows those textures are on now"""

        rows = sorted(row for uuid in self.uuids if (row := model.row(uuid)) is not None)

        if rows:
            selection.select(row_spans(model, rows), QItemSelectionModel.SelectionFlag.ClearAndSelect)

        standing = model.row(self.current) if self.current is not None else None

        if standing is not None:
            # the selection is already back, and this only says which of it the
            # panes are on, so it is set without touching what is selected
            selection.setCurrentIndex(model.index(standing, 0), QItemSelectionModel.SelectionFlag.NoUpdate)
