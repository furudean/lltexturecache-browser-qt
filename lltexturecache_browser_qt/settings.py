from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings

# how the last session and the shape it was left in are put away
SESSION_KEY = "openCaches"
GEOMETRY_KEY = "windowGeometry"
SPLITTER_KEY = "windowSplitter"
FILTERS_KEY = "colorFilters"


def stored_blob(settings: QSettings, key: str) -> QByteArray:
    stored = settings.value(key)

    return stored if isinstance(stored, QByteArray) else QByteArray()


def stored_paths(settings: QSettings, key: str) -> list[Path]:
    stored = settings.value(key) or []

    if isinstance(stored, str):
        stored = [stored]

    return [Path(path) for path in stored]
