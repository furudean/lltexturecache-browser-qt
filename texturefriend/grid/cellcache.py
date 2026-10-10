from PySide6.QtGui import QPixmap, QPixmapCache

_sizes: dict[str, list[int]] = {}


def cell_key(uuid: str, pixels: int) -> str:
    return f"{uuid}@{pixels}"


def has_cell(uuid: str, pixels: int) -> bool:
    return QPixmapCache.find(cell_key(uuid, pixels), QPixmap())


def nearest_cell(uuid: str, pixels: int) -> QPixmap:
    sizes = _sizes.get(uuid)

    if not sizes:
        return QPixmap()

    cell = QPixmap()

    for size in sorted(sizes, key=lambda size: (abs(size - pixels), -size)):
        if QPixmapCache.find(cell_key(uuid, size), cell):
            return cell

        sizes.remove(size)

    del _sizes[uuid]

    return QPixmap()


def insert_cell(uuid: str, pixels: int, cell: QPixmap) -> None:
    QPixmapCache.insert(cell_key(uuid, pixels), cell)

    sizes = _sizes.setdefault(uuid, [])

    if pixels not in sizes:
        sizes.append(pixels)


def remove_cells(uuid: str) -> None:
    for size in _sizes.pop(uuid, []):
        QPixmapCache.remove(cell_key(uuid, size))
