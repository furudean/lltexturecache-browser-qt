from pathlib import Path
from typing import ClassVar, Self

from PySide6.QtCore import QByteArray, QObject, QSettings, Signal

# how the last session and the shape it was left in are put away
SESSION_KEY = "openCaches"
GEOMETRY_KEY = "windowGeometry"
SPLITTER_KEY = "windowSplitter"
FILTERS_KEY = "colorFilters"


class SettingsWatcher(QObject):
    changed = Signal()

    _shared: ClassVar[Self | None] = None

    @classmethod
    def shared(cls) -> Self:
        if cls._shared is None:
            cls._shared = cls()

        return cls._shared


def stored_blob(settings: QSettings, key: str) -> QByteArray:
    stored = settings.value(key)

    return stored if isinstance(stored, QByteArray) else QByteArray()


def stored_paths(settings: QSettings, key: str) -> list[Path]:
    stored = settings.value(key) or []

    if isinstance(stored, str):
        stored = [stored]

    return [Path(path) for path in stored]
