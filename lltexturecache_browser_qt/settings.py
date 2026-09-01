"""Reading back what the app put away

QSettings hands back whatever was stored under a key, including whatever a
store written by another version or edited by hand happens to hold, so nothing
read out of it can be taken at its word without being checked first.
"""

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
    """A stored list of paths

    A list of one comes back out of the store as the string it held rather
    than as a list, which is Qt's own doing and has to be undone here.
    """

    stored = settings.value(key) or []

    if isinstance(stored, str):
        stored = [stored]

    return [Path(path) for path in stored]
