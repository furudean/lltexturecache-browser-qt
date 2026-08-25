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
        except (FileNotFoundError, TextureCacheError):
            # a cache cleared out or unplugged
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


def main() -> None:
    app = QApplication(sys.argv)

    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
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

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
