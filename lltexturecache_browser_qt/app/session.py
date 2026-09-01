"""The windows the app has open, and the session they make up

Which windows exist, which caches they are on, and whether the app is on its
way out are facts about the app rather than about any one window. They are
kept here so that a window can be asked about itself without being the place
every other window is looked up from.
"""

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from PySide6.QtCore import QSettings

from lltexturecache_browser_qt.panes.previewing import PreviewClient, PreviewHost
from lltexturecache_browser_qt.settings import SESSION_KEY, stored_paths

if TYPE_CHECKING:
    from lltexturecache_browser_qt.app.about import AboutDialog
    from lltexturecache_browser_qt.app.actions import AppMenu


class SessionWindow(PreviewClient, Protocol):
    """
    A window is also what the preview follows, so a session window is a
    preview client too rather than the two being tracked separately.
    """

    def opened_cache(self) -> Path | None: ...


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
        return stored_paths(QSettings(), SESSION_KEY)

    def save(self) -> None:
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


class AppState:
    """The open windows, the preview they share, the about box and the app-wide
    menu bar"""

    def __init__(self) -> None:
        self.session = AppSession()

        # what the app does when the preview is closed by hand, which is to put
        # every window's menu tick down. set by whoever owns the windows, since
        # the tick belongs to a menu this knows nothing about
        self.preview_closed: Callable[[], None] = lambda: None

        # looked up when the preview is closed rather than bound here, so the
        # window class can set it after this is built
        self.preview = PreviewHost(
            clients=lambda: list(self.session),
            closed=lambda: self.preview_closed(),
        )

        # the bar macOS falls back on when the window in front has none of
        # its own, handed over by whoever builds it. there is no such bar on the
        # platforms that keep a menu inside every window
        self.menu: AppMenu | None = None

        self._about: AboutDialog | None = None

    def show_about(self, build: Callable[[], "AboutDialog"]) -> None:
        if self._about is None:
            self._about = build()

        self._about.show()
        self._about.raise_()
        self._about.activateWindow()
