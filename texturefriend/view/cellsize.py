from math import sqrt

from PySide6.QtCore import QSettings

from texturefriend.settings import SettingsWatcher
from texturefriend.view.images import THUMBNAIL_SIZE

CELL_SIZE_KEY = "cellSize"

DEFAULT_CELL_SIZE = THUMBNAIL_SIZE

ZOOM_REACH = sqrt(2) ** 3
ZOOM_RUNGS = 5

RUNG_RATIO: float = ZOOM_REACH ** (1 / ZOOM_RUNGS)

CELL_SIZES = tuple(DEFAULT_CELL_SIZE * RUNG_RATIO**step for step in range(-ZOOM_RUNGS, ZOOM_RUNGS + 1))

SMALLEST_CELL_SIZE = CELL_SIZES[0]
LARGEST_CELL_SIZE = CELL_SIZES[-1]

STEP_MARGIN = 1.05


class CellSizeChanges(SettingsWatcher):
    pass


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

    return clamped(size)


def clamped(size: float) -> float:
    return min(max(size, SMALLEST_CELL_SIZE), LARGEST_CELL_SIZE)


def set_cell_size(size: float) -> None:
    global _size

    size = clamped(size)

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
        return next((rung for rung in CELL_SIZES if rung > size * STEP_MARGIN), LARGEST_CELL_SIZE)

    return next((rung for rung in reversed(CELL_SIZES) if rung < size / STEP_MARGIN), SMALLEST_CELL_SIZE)


def step_cell_size(step: int) -> None:
    set_cell_size(stepped(step))


def can_step(step: int) -> bool:
    return stepped(step) != cell_size()
