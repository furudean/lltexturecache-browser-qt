from math import sqrt
from typing import ClassVar, Self

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtGui import QPixmapCache

from lltexturecache_browser_qt.view.images import THUMBNAIL_SIZE

CELL_SIZE_KEY = "cellSize"

CELL_SIZE_RATIO = sqrt(2)
SMALLEST_STEP = -3
LARGEST_STEP = 3

CELL_SIZES = tuple(round(THUMBNAIL_SIZE * CELL_SIZE_RATIO**step) for step in range(SMALLEST_STEP, LARGEST_STEP + 1))

DEFAULT_CELL_SIZE = THUMBNAIL_SIZE


class CellSizeChanges(QObject):
    changed = Signal()

    _shared: ClassVar[Self | None] = None

    @classmethod
    def shared(cls) -> Self:
        if cls._shared is None:
            cls._shared = cls()

        return cls._shared


_size: int | None = None


def cell_size() -> int:
    global _size

    if _size is None:
        stored = to_size(QSettings().value(CELL_SIZE_KEY))

        _size = stored if stored is not None else DEFAULT_CELL_SIZE

    return _size


def to_size(stored: object) -> int | None:
    try:
        size = int(stored)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return None

    return size if size in CELL_SIZES else None


def nearest(size: int) -> int:
    return min(CELL_SIZES, key=lambda rung: abs(rung - size))


def set_cell_size(size: int) -> None:
    global _size

    size = nearest(size)

    if size == cell_size():
        return

    _size = size

    QSettings().setValue(CELL_SIZE_KEY, size)
    QPixmapCache.clear()

    CellSizeChanges.shared().changed.emit()


def stepped(step: int) -> int:
    place = CELL_SIZES.index(cell_size())

    return CELL_SIZES[min(max(place + step, 0), len(CELL_SIZES) - 1)]


def step_cell_size(step: int) -> None:
    set_cell_size(stepped(step))


def can_step(step: int) -> bool:
    return stepped(step) != cell_size()


def reset(to: int | None = None) -> int | None:
    global _size

    was, _size = _size, to

    return was
