from math import sqrt
from typing import ClassVar, Self

from PySide6.QtCore import QObject, QSettings, Signal

from lltexturecache_browser_qt.view.images import THUMBNAIL_SIZE

CELL_SIZE_KEY = "cellSize"

CELL_SIZE_RATIO = sqrt(2)
SMALLEST_STEP = -3
LARGEST_STEP = 3

CELL_SIZES = tuple(round(THUMBNAIL_SIZE * CELL_SIZE_RATIO**step) for step in range(SMALLEST_STEP, LARGEST_STEP + 1))

SMALLEST_CELL_SIZE = CELL_SIZES[0]
LARGEST_CELL_SIZE = CELL_SIZES[-1]

DEFAULT_CELL_SIZE = THUMBNAIL_SIZE

# the finer ladder the zoom actions step along, with a rung between each pair
# of the ones above so every other step lands on one of them
ACTION_STEPS = 2

ACTION_SIZES = tuple(
    round(THUMBNAIL_SIZE * CELL_SIZE_RATIO ** (step / ACTION_STEPS))
    for step in range(SMALLEST_STEP * ACTION_STEPS, LARGEST_STEP * ACTION_STEPS + 1)
)

# how far past the cell size the next rung has to be for a zoom step to land on
# it, so a size a gesture left just short of a rung steps past it
STEP_MARGIN = 1.05


class CellSizeChanges(QObject):
    changed = Signal()

    _shared: ClassVar[Self | None] = None

    @classmethod
    def shared(cls) -> Self:
        if cls._shared is None:
            cls._shared = cls()

        return cls._shared


_size: float | None = None


def cell_size() -> float:
    global _size

    if _size is None:
        stored = to_size(QSettings().value(CELL_SIZE_KEY))

        _size = stored if stored is not None else DEFAULT_CELL_SIZE

    return _size


def to_size(stored: object) -> float | None:
    try:
        size = float(stored)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None

    return size if SMALLEST_CELL_SIZE <= size <= LARGEST_CELL_SIZE else None


def set_cell_size(size: float) -> None:
    global _size

    size = min(max(size, SMALLEST_CELL_SIZE), LARGEST_CELL_SIZE)

    if size == cell_size():
        return

    _size = size

    QSettings().setValue(CELL_SIZE_KEY, size)

    CellSizeChanges.shared().changed.emit()


def scale_cell_size(factor: float) -> None:
    set_cell_size(cell_size() * factor)


def stepped(step: int) -> float:
    size = cell_size()

    if step > 0:
        larger = [rung for rung in ACTION_SIZES if rung > size * STEP_MARGIN]

        return larger[min(step, len(larger)) - 1] if larger else LARGEST_CELL_SIZE

    if step < 0:
        smaller = [rung for rung in ACTION_SIZES if rung < size / STEP_MARGIN]

        return smaller[-min(-step, len(smaller))] if smaller else SMALLEST_CELL_SIZE

    return size


def step_cell_size(step: int) -> None:
    set_cell_size(stepped(step))


def can_step(step: int) -> bool:
    return stepped(step) != cell_size()


def reset(to: float | None = None) -> float | None:
    global _size

    was, _size = _size, to

    return was
