from pathlib import Path

from PySide6.QtCore import QObject, QSettings

from texturefriend.settings import SettingsWatcher

RECENT_LIMIT = 10
RECENT_KEY = "recentCaches"


class RecentCaches(SettingsWatcher):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._paths = self.load()

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
