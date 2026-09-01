"""Which window the one preview belongs to

The preview is the app's rather than any one window's: there is a single tool
window, and it shows whatever is selected in whichever window is being worked
in. Keeping track of which that is, of the windows that would take it if that
one went away, and of the menu tick every window carries for it, is a job of
its own and does not belong to any of the windows it is about.
"""

from collections.abc import Callable
from typing import Protocol

from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction

from lltexturecache_browser_qt.panes.preview import PreviewWindow
from lltexturecache_browser_qt.settings import stored_blob

PREVIEW_GEOMETRY_KEY = "previewGeometry"


class PreviewClient(Protocol):
    def wants_preview(self) -> bool: ...

    def fill_preview(self) -> None: ...

    def preview_menu_entry(self) -> QAction: ...


class PreviewHost:
    """The one preview window, and the window it is currently following

    `clients` is asked for the windows open right now rather than handed a
    list, since windows come and go under the host and a list taken once would
    be stale by the time the preview needed rehoming.
    """

    def __init__(self, clients: Callable[[], list[PreviewClient]], closed: Callable[[], None]) -> None:
        self._clients = clients
        self._closed = closed

        self._window: PreviewWindow | None = None
        self._following: PreviewClient | None = None

    @property
    def window(self) -> PreviewWindow | None:
        return self._window

    def followed_by(self, client: PreviewClient) -> bool:
        return self._following is client

    def shared(self) -> PreviewWindow:
        if self._window is None:
            self._window = PreviewWindow()
            self._window.closed.connect(self.was_closed)
            self._window.restoreGeometry(stored_blob(QSettings(), PREVIEW_GEOMETRY_KEY))

        return self._window

    def save_geometry(self, settings: QSettings) -> None:
        if self._window is not None:
            settings.setValue(PREVIEW_GEOMETRY_KEY, self._window.saveGeometry())

    def sync_ticks(self, *, shown: bool) -> None:
        """Put every window's menu tick where the preview really is

        The ticks are moved rather than clicked, so each one is set with its
        signals held: a window told the preview is up has not asked for it and
        must not go on to ask every other window for it in turn.
        """

        for client in self._clients():
            entry = client.preview_menu_entry()

            if entry.isChecked() == shown:
                continue

            was = entry.blockSignals(True)
            entry.setChecked(shown)
            entry.blockSignals(was)

    def follow(self, client: PreviewClient | None = None) -> None:
        if client is not None and not client.wants_preview():
            # the window asking has nothing to put there, so the preview stays
            # where it is unless where it is happens to be that same window
            client = None if client is self._following else self._following

        if client is None:
            client = next((other for other in self._clients() if other.wants_preview()), None)

        self._following = client

        if client is None:
            if self._window is not None:
                self._window.hide()

            return

        preview = self.shared()

        # the window it follows changes as windows are clicked between, which is
        # no reason to keep pulling the preview back in front of them
        if not preview.isVisible():
            preview.present()

        client.fill_preview()

    def release(self, client: PreviewClient) -> bool:
        if self._following is not client:
            return False

        self._following = None

        return True

    def was_closed(self) -> None:
        self._following = None

        self._closed()
