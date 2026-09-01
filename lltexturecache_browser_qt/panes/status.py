from PySide6.QtCore import QObject
from PySide6.QtWidgets import QMainWindow, QStatusBar

from lltexturecache_browser_qt.view.formatting import format_count

NOTICE_DURATION_MS = 5000


class WindowStatus(QObject):
    """The one line a window has to report what it is holding and what it did

    Three messages are in play at once and only one of them is on the bar: a
    notice that expires on its own, the resting message the bar returns to
    once it does, and the summary the grid left behind, which is what a
    selection is written over the top of.
    """

    def __init__(self, window: QMainWindow) -> None:
        super().__init__(window)

        self._bar = QStatusBar(window)
        window.setStatusBar(self._bar)

        self._resting = ""
        self._summary = ""

        self._opened = False

        self._bar.messageChanged.connect(self.changed)

        # an empty window has nothing to report, and the bar is not up yet
        self.sync()

    def set_opened(self, opened: bool) -> None:
        self._opened = opened

        self.sync()

    def rest(self, message: str) -> None:
        self._resting = message

        self._bar.showMessage(message)

    def flash(self, message: str) -> None:
        self._bar.showMessage(message, NOTICE_DURATION_MS)

    def set_summary(self, summary: str) -> None:
        self._summary = summary

        self.rest(summary)

    def show_selection(self, selected: int, total: int) -> None:
        self.rest(f"Selected {format_count(selected)} of {format_count(total)} textures" if selected else self._summary)

    def changed(self, message: str) -> None:
        if not message and self._resting:
            self._bar.showMessage(self._resting)
            return

        self.sync()

    def sync(self) -> None:
        # a window with nothing open in it can still have something to say, and
        # the bar comes up under the message for as long as it is there
        self._bar.setVisible(self._opened or bool(self._bar.currentMessage()))
