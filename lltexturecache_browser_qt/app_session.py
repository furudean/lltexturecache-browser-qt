"""The windows the app has open, and the session they make up

Which windows exist, which caches they are on, and whether the app is on its
way out are facts about the app rather than about any one window. They are
kept here so that a window can be asked about itself without being the place
every other window is looked up from.
"""

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QSettings

from lltexturecache_browser_qt.settings import SESSION_KEY, stored_paths


class SessionWindow(Protocol):
    """What the session needs of a window: the cache it is on, if any"""

    def opened_cache(self) -> Path | None:
        """The cache directory this window is showing, or nothing"""
        ...


class AppSession:
    """The open windows, and the caches they would be reopened on

    Registration is explicit rather than by weak reference: a window that has
    closed has already said so, and one that has not is still the app's to
    save and to hand the preview to.
    """

    def __init__(self) -> None:
        self._windows: list[SessionWindow] = []
        self._quitting = False

    def __len__(self) -> int:
        return len(self._windows)

    def __iter__(self) -> Iterator[SessionWindow]:
        return iter(list(self._windows))

    @property
    def quitting(self) -> bool:
        return self._quitting

    def add(self, window: SessionWindow) -> None:
        self._windows.append(window)

    def remove(self, window: SessionWindow) -> None:
        if window in self._windows:
            self._windows.remove(window)

    def any_open(self) -> bool:
        return bool(self._windows)

    def windows(self) -> list[SessionWindow]:
        return list(self._windows)

    @staticmethod
    def stored() -> list[Path]:
        """The caches the last session was left on"""

        return stored_paths(QSettings(), SESSION_KEY)

    def save(self) -> None:
        """Put away the caches the open windows are on"""

        QSettings().setValue(
            SESSION_KEY,
            [str(opened) for window in self._windows if (opened := window.opened_cache()) is not None],
        )

    def quit(self) -> None:
        """Save the session once, on the way out

        Windows close as the app quits, and each of them would otherwise save
        a session with one fewer window in it than the last, leaving the store
        empty by the time the last one goes.
        """

        if self._quitting:
            return

        self.save()

        self._quitting = True

    def find(self, matches: Callable[[SessionWindow], bool]) -> SessionWindow | None:
        return next((window for window in self._windows if matches(window)), None)
