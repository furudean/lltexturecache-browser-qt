from pathlib import Path
from typing import ClassVar

from PySide6.QtCore import QObject, QSettings, Signal

RECENT_LIMIT = 10
RECENT_KEY = "recentCaches"


class RecentCaches(QObject):
    changed = Signal()

    _shared: ClassVar[RecentCaches | None] = None

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._paths = self.load()

    @classmethod
    def shared(cls) -> RecentCaches:
        if cls._shared is None:
            cls._shared = cls()

        return cls._shared

    def load(self) -> list[Path]:
        stored = QSettings().value(RECENT_KEY) or []

        if isinstance(stored, str):
            stored = [stored]

        return [Path(path) for path in stored]

    def save(self) -> None:
        QSettings().setValue(RECENT_KEY, [str(path) for path in self._paths])

    def paths(self) -> list[Path]:
        return list(self._paths)

    def remember(self, cache_dir: Path) -> None:
        # an opening moves a cache back to the front whether or not it was
        # already listed, so the menu is in the order they were last visited
        self._paths = [cache_dir, *(path for path in self._paths if path != cache_dir)][:RECENT_LIMIT]

        self.save()
        self.changed.emit()

    def clear(self) -> None:
        self._paths = []

        self.save()
        self.changed.emit()
