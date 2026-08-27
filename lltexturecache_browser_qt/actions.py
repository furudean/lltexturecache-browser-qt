import sys
from collections.abc import Callable
from functools import partial
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import QMainWindow, QMenu, QMenuBar, QWidget

from lltexturecache_browser_qt import APP_DISPLAY_NAME
from lltexturecache_browser_qt.checkerboard import CheckerboardChanges, CheckerTone, grid_tone, set_grid_tone
from lltexturecache_browser_qt.export import DEFAULT_FORMAT, FORMATS, Format
from lltexturecache_browser_qt.formatting import format_count
from lltexturecache_browser_qt.recents import RecentCaches
from lltexturecache_browser_qt.suggested import paths as suggested_paths

PREVIEW_KEY = "showPreview"
INSPECTOR_KEY = "showInspector"
FILTERS_KEY = "showColorFilters"
INCOMPLETE_KEY = "showIncomplete"

TONES = {
    CheckerTone.AUTO: ("&Automatic", "Match the checkerboard to the window's own colours"),
    CheckerTone.LIGHT: ("&Light", "Draw a light checkerboard behind the transparent parts of a texture"),
    CheckerTone.DARK: ("&Dark", "Draw a dark checkerboard behind the transparent parts of a texture"),
    CheckerTone.NONE: ("&None", "Leave the transparent parts of a texture as they are"),
}


def triggers(entry: QAction, call: Callable[[], object]) -> None:
    entry.triggered.connect(lambda _checked=False: call())


def export_title(count: int, *, everything: bool) -> str:
    if everything:
        return "Export Full Cache As..."

    if count == 1:
        return "Export As..."

    return f"Export {format_count(count)} Selected As..." if count else "Export Selected As..."


class WindowActions(QObject):
    new_window = Signal()
    opened = Signal()
    reopened = Signal(Path)
    reloaded = Signal()
    exported = Signal(Format, bool)
    inspected = Signal(bool)
    filtered = Signal(bool)
    previewed = Signal(bool)
    incompleted = Signal(bool)
    abouted = Signal()

    def __init__(self, window: QMainWindow) -> None:
        super().__init__(window)

        # the entries belong to the window rather than to this, since a shortcut
        # is only answered by a window the action can be reached from
        menu = window.menuBar()

        file_menu = menu.addMenu("&File")

        new = QAction("&New Window", window)
        new.setShortcut(QKeySequence(QKeySequence.StandardKey.New))
        new.setStatusTip("Open another window")
        triggers(new, self.new_window.emit)

        open = QAction("&Open...", window)
        open.setShortcut(QKeySequence(QKeySequence.StandardKey.Open))
        open.setStatusTip("Open a texture cache")
        triggers(open, self.opened.emit)

        # the standard refresh key is f5 off mac, which we want to rewrite
        refresh_keys = [*QKeySequence.keyBindings(QKeySequence.StandardKey.Refresh), QKeySequence("Ctrl+R")]

        self.reload = QAction("&Reload", window)
        self.reload.setShortcuts(list(dict.fromkeys(refresh_keys)))
        self.reload.setStatusTip("Reload the open texture cache from disk")
        self.reload.setEnabled(False)
        triggers(self.reload, self.reloaded.emit)

        close = QAction("&Close Window", window)
        close.setShortcut(QKeySequence(QKeySequence.StandardKey.Close))
        close.setStatusTip("Close this window")
        triggers(close, window.close)

        file_menu.addAction(open)

        self._recents = file_menu.addMenu("Open &Recent")

        self._suggested = file_menu.addMenu("Open &Suggested")

        file_menu.addSeparator()
        file_menu.addAction(self.reload)

        file_menu.addSeparator()
        file_menu.addAction(new)
        file_menu.addAction(close)

        RecentCaches.shared().changed.connect(self.populate_recents)

        self.populate_recents()
        self.populate_suggested()

        self.exports = menu.addMenu("&Export")
        self._selected_export = self.format_menu(self.exports, "Export Selected As...", everything=False)
        self._all_export = self.format_menu(self.exports, "Export Full Cache As...", everything=True)

        # the first format wraps the codestream the cache is already holding
        # instead of encoding a new one, which is what a shortcut should reach
        # for. only the entry under the menu bar answers it, since the context
        # menu builds its own copy of these and two answers to a key is none
        quick = self._selected_export.actions()[FORMATS.index(DEFAULT_FORMAT)]
        quick.setShortcut(QKeySequence("Ctrl+E"))

        # how much is selected and how much is in the cache both move around
        # under the menu, so the two entries are named on the way open. there is
        # neither of them to count yet, and the titles are what the entries come
        # up as until a window has something to say about it
        self.sync_export(0, 0, idle=True)

        view_menu = menu.addMenu("&View")

        self.preview = QAction("Show &Preview", window)
        self.preview.setShortcut(QKeySequence(Qt.Key.Key_Space))
        self.preview.setStatusTip("Show the selected texture in a window of its own")
        self.preview.setCheckable(True)
        self.preview.setChecked(bool(QSettings().value(PREVIEW_KEY, False, type=bool)))
        self.preview.toggled.connect(self.store_preview)
        self.preview.toggled.connect(self.previewed)

        # the command key "Ctrl" on mac and hands "Meta" to control
        inspector_key = "Shift+Ctrl+I" if sys.platform == "darwin" else "Shift+Alt+I"

        self.inspector = QAction("Show &Inspector", window)
        self.inspector.setShortcut(QKeySequence(inspector_key))
        self.inspector.setStatusTip("Show details of the selected texture beside the grid")
        self.inspector.setCheckable(True)
        self.inspector.setChecked(bool(QSettings().value(INSPECTOR_KEY, True, type=bool)))
        self.inspector.toggled.connect(self.store_inspector)
        self.inspector.toggled.connect(self.inspected)

        self.filters = QAction("Show &Filters", window)
        self.filters.setStatusTip("Show the color filter bar")
        self.filters.setCheckable(True)
        self.filters.setChecked(bool(QSettings().value(FILTERS_KEY, True, type=bool)))
        self.filters.toggled.connect(self.store_filters)
        self.filters.toggled.connect(self.filtered)

        self.incomplete = QAction("Show &Incomplete Textures", window)
        self.incomplete.setStatusTip("List entries the cache never finished downloading")
        self.incomplete.setCheckable(True)
        self.incomplete.setChecked(bool(QSettings().value(INCOMPLETE_KEY, False, type=bool)))
        self.incomplete.toggled.connect(self.store_incomplete)
        self.incomplete.toggled.connect(self.incompleted)

        self._tones: dict[CheckerTone, QAction] = {}

        tones = QActionGroup(window)
        tones.setExclusive(True)

        for tone, (label, tip) in TONES.items():
            entry = QAction(label, window)
            entry.setStatusTip(tip)
            entry.setCheckable(True)
            entry.setActionGroup(tones)
            triggers(entry, partial(set_grid_tone, tone))

            self._tones[tone] = entry

        CheckerboardChanges.shared().changed.connect(self.sync_checkerboard)

        self.sync_checkerboard()

        app_menu = menu.addMenu("About")  # label doesn't matter on macOS, instead decided by role
        about_action = app_menu.addAction(f"About {APP_DISPLAY_NAME}")
        about_action.setMenuRole(QAction.MenuRole.AboutRole)
        about_action.triggered.connect(self.abouted.emit)

        view_menu.addAction(self.preview)
        view_menu.addAction(self.inspector)
        view_menu.addAction(self.filters)

        # what the grid holds rather than which panes are up, so it sits apart
        # from the three entries above it
        view_menu.addSeparator()
        view_menu.addAction(self.incomplete)

        checkerboard = view_menu.addMenu("&Transparency")
        checkerboard.addActions(list(self._tones.values()))

    def shutdown(self) -> None:
        RecentCaches.shared().changed.disconnect(self.populate_recents)
        CheckerboardChanges.shared().changed.disconnect(self.sync_checkerboard)

    def sync_checkerboard(self) -> None:
        self._tones[grid_tone()].setChecked(True)

    def format_menu(self, parent: QMenu, title: str, *, everything: bool) -> QMenu:
        menu = parent.addMenu(title)

        for format in FORMATS:
            entry = menu.addAction(format.label)
            entry.setStatusTip(
                f"Write every texture in the cache out as {format.label}"
                if everything
                else f"Write the selected textures out as {format.label}"
            )
            triggers(entry, partial(self.exported.emit, format, everything))

        return menu

    def context_menu(self, parent: QWidget, selected: int, *, idle: bool) -> QMenu:
        menu = QMenu(parent)

        entries = self.format_menu(menu, export_title(selected, everything=False), everything=False)
        entries.setEnabled(idle)

        return menu

    def sync_export(self, selected: int, total: int, *, idle: bool) -> None:
        self._selected_export.setTitle(export_title(selected, everything=False))
        self._selected_export.setEnabled(idle and selected > 0)

        self._all_export.setTitle(export_title(total, everything=True))
        self._all_export.setEnabled(idle and total > 0)

    def populate_recents(self) -> None:
        recents = RecentCaches.shared()
        paths = recents.paths()

        self._recents.clear()
        self._recents.setEnabled(bool(paths))

        for path in paths:
            entry = self._recents.addAction(str(path).replace("&", "&&"))
            entry.setStatusTip(f"Open {path}")
            triggers(entry, partial(self.reopened.emit, path))

        self._recents.addSeparator()

        clear = self._recents.addAction("Clear recent file list")
        clear.setStatusTip("Forget the caches opened before")
        triggers(clear, recents.clear)

    def populate_suggested(self) -> None:
        paths = suggested_paths()

        self._suggested.setEnabled(bool(paths))

        for path in paths:
            entry = self._suggested.addAction(str(path).replace("&", "&&"))
            entry.setStatusTip(f"Open {path}")
            triggers(entry, partial(self.reopened.emit, path))

    @staticmethod
    def store_preview(shown: bool) -> None:
        QSettings().setValue(PREVIEW_KEY, shown)

    def store_inspector(self, shown: bool) -> None:
        QSettings().setValue(INSPECTOR_KEY, shown)

    def store_filters(self, shown: bool) -> None:
        QSettings().setValue(FILTERS_KEY, shown)

    def store_incomplete(self, shown: bool) -> None:
        QSettings().setValue(INCOMPLETE_KEY, shown)


def fallback_menu(new_window: Callable[[], object]) -> QMenuBar:
    bar = QMenuBar()

    # only the one entry: everything else an app can do it does to a cache or
    # to a window, and both of those are a new window away
    new = bar.addMenu("&File").addAction("&New Window")
    new.setShortcut(QKeySequence(QKeySequence.StandardKey.New))
    triggers(new, new_window)

    return bar
