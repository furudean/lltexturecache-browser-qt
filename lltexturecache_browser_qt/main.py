import logging
import os
import signal
import sys
import traceback
from pathlib import Path
from types import TracebackType

from PySide6.QtCore import QEvent, QObject, Qt, Signal, Slot
from PySide6.QtGui import QPixmapCache
from PySide6.QtWidgets import QApplication, QMessageBox
from texture_courier import TextureCache, TextureCacheError

from lltexturecache_browser_qt import APP_DISPLAY_NAME, APP_NAME, __version__
from lltexturecache_browser_qt.actions import fallback_menu
from lltexturecache_browser_qt.checkerboard import sync_checkerboard
from lltexturecache_browser_qt.model import PIXMAP_CACHE_KB
from lltexturecache_browser_qt.signals import SignalWatcher
from lltexturecache_browser_qt.suggested import resolve as resolve_suggested
from lltexturecache_browser_qt.window import MainWindow

log = logging.getLogger(__name__)

# what the app says about itself when nothing has asked for more. a viewer's
# texture cache is full of half-written entries, so the ones the app steps
# around are only worth a line when something has gone looking for them
LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"
LOG_LEVEL_VAR = "LLTEXTURECACHE_LOG"


class AppWatcher(QObject):
    """Catches what happens to the app rather than to any one of its windows"""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Quit:
            MainWindow.quitting()

        if event.type() == QEvent.Type.ApplicationStateChange:
            active = QApplication.applicationState() == Qt.ApplicationState.ApplicationActive

            if active and not MainWindow.any_open():
                MainWindow().show()

        return super().eventFilter(watched, event)


def restore(paths: list[Path]) -> list[MainWindow]:
    """Put the windows of a session back up, one to a cache"""

    windows: list[MainWindow] = []

    for path in paths:
        try:
            cache = TextureCache(path)
        except (FileNotFoundError, TextureCacheError) as e:
            # a cache cleared out or unplugged, which is nothing to stop the
            # session over: the rest of it still opens
            log.info("leaving %s out of the restored session: %s", path, e)
            continue

        if windows:
            window = windows[-1].new_window(cache)
        else:
            window = MainWindow()
            window.set_cache(cache)
            window.show()

        windows.append(window)

    return windows


def stop(app: QApplication) -> None:
    MainWindow.quitting()

    app.closeAllWindows()
    app.quit()


class ErrorReporter(QObject):
    error_occurred = Signal(str, str)  # (title, message)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.error_occurred.connect(
            self._show_error,
            Qt.ConnectionType.AutoConnection,
        )

    @Slot(str, str)
    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.critical(None, title, message)


def start_logging() -> None:
    """Send the app's own reports to stderr, at the level asked for"""

    level = os.environ.get(LOG_LEVEL_VAR, "WARNING").upper()

    logging.basicConfig(
        level=getattr(logging, level, logging.WARNING),
        format=LOG_FORMAT,
        stream=sys.stderr,
    )


def main() -> int:
    """Run the app, and hand back what it exited with

    The console script and the module entry point below both turn this into
    the process's exit status, so nothing in here has to reach for one.
    """

    start_logging()

    app = QApplication(sys.argv)

    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setDesktopFileName(APP_NAME)
    app.setOrganizationName("paisley softworks")
    app.setApplicationVersion(__version__)

    QPixmapCache.setCacheLimit(PIXMAP_CACHE_KB)

    sync_checkerboard()
    resolve_suggested()

    # on mac the app can be alive without a window
    mac = sys.platform == "darwin"

    app.setQuitOnLastWindowClosed(not mac)

    _menu = fallback_menu(lambda: MainWindow().show()) if mac else None

    watcher = AppWatcher(app)
    app.installEventFilter(watcher)

    paths = MainWindow.session()
    windows = restore(paths)

    if not windows:
        first = MainWindow()
        first.show()
    else:
        first = windows[0]

    signals = SignalWatcher(signal.SIGINT, signal.SIGTERM, parent=app)
    signals.received.connect(lambda _: stop(app))

    reporter = ErrorReporter()

    def excepthook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: TracebackType | None,
    ) -> None:
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        print(tb_text, file=sys.stderr)
        reporter.error_occurred.emit("Unhandled Exception", tb_text)

    sys.excepthook = excepthook

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
