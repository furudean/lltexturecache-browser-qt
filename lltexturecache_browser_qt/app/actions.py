import sys
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Qt, Signal, SignalInstance
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import QMainWindow, QMenu, QMenuBar, QWidget

from lltexturecache_browser_qt import APP_DISPLAY_NAME
from lltexturecache_browser_qt.cache.export import DEFAULT_FORMAT, FORMATS, Format
from lltexturecache_browser_qt.cache.recents import RecentCaches
from lltexturecache_browser_qt.cache.suggested import paths as suggested_paths
from lltexturecache_browser_qt.view.checkerboard import CheckerboardChanges, CheckerTone, grid_tone, set_grid_tone
from lltexturecache_browser_qt.view.formatting import format_count

PREVIEW_KEY = "showPreview"
INSPECTOR_KEY = "showInspector"
FILTERS_KEY = "showColorFilters"
INCOMPLETE_KEY = "showIncomplete"
SIMPLE_KEY = "showSimple"

TONES = {
    CheckerTone.AUTO: ("&Automatic", "Match the checkerboard to the window's own colours"),
    CheckerTone.LIGHT: ("&Checkerboard (Light)", "Draw a light checkerboard behind the transparent parts of a texture"),
    CheckerTone.DARK: ("&Checkerboard (Dark)", "Draw a dark checkerboard behind the transparent parts of a texture"),
    CheckerTone.NONE: ("&None", "Leave the transparent parts of a texture as they are"),
}


def store_toggle(key: str, shown: bool) -> None:
    """Remember where a tick was left

    `shown` is positional because this is connected to `QAction.toggled`,
    which hands its argument over that way.
    """

    QSettings().setValue(key, shown)


def stored_toggle(key: str, *, default: bool) -> bool:
    return bool(QSettings().value(key, default, type=bool))


@dataclass(frozen=True)
class Toggle:
    """One tick under the View menu

    They are all the same entry with a different label: checkable, put away
    and read back under a key of its own, and reported to the window that has
    to act on it.
    """

    key: str
    label: str
    tip: str
    on: bool = False
    shortcut: str | None = None

    def build(self, window: QMainWindow, reports: SignalInstance) -> QAction:
        entry = QAction(self.label, window)

        if self.shortcut is not None:
            entry.setShortcut(QKeySequence(self.shortcut))

        entry.setStatusTip(self.tip)
        entry.setCheckable(True)
        entry.setChecked(stored_toggle(self.key, default=self.on))

        # a partial rather than a bound method of this Toggle: Qt keeps only a
        # weak reference to a bound method's object, and the table these are
        # built from is gone by the time the first tick is moved
        entry.toggled.connect(partial(store_toggle, self.key))
        entry.toggled.connect(reports)

        return entry


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
    color_picked = Signal()
    picture_picked = Signal()
    picture_pasted = Signal()
    filters_disabled = Signal()
    inspected = Signal(bool)
    filtered = Signal(bool)
    previewed = Signal(bool)
    preview_toggled = Signal()
    incompleted = Signal(bool)
    simple_shown = Signal(bool)
    abouted = Signal()

    def __init__(self, window: QMainWindow) -> None:
        super().__init__(window)

        # the entries belong to the window rather than to this, since a shortcut
        # is only answered by a window the action can be reached from
        menu = window.menuBar()

        self.build_file_menu(window, menu.addMenu("&File"))
        self.build_export_menu(menu.addMenu("&Export"))
        self.build_find_menu(window, menu.addMenu("Fi&nd"))
        self.build_view_menu(window, menu.addMenu("&View"))
        self.build_app_menu(menu.addMenu("About"))

    def build_file_menu(self, window: QMainWindow, file_menu: QMenu) -> None:
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

    def build_export_menu(self, exports: QMenu) -> None:
        self.exports = exports

        self._selected_export = self.format_menu(exports, "Export Selected As...", everything=False)
        self._all_export = self.format_menu(exports, "Export Full Cache As...", everything=True)

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

    def build_find_menu(self, window: QMainWindow, find_menu: QMenu) -> None:
        self.filter_color = QAction("Filter &Color...", window)
        self.filter_color.setStatusTip("Add a color to filter textures by")
        self.filter_color.setEnabled(False)
        triggers(self.filter_color, self.color_picked.emit)

        self.match = QAction("Match &Image...", window)
        self.match.setShortcut(QKeySequence(QKeySequence.StandardKey.Find))
        self.match.setStatusTip("Show the textures that look like a picture on disk")
        self.match.setEnabled(False)
        triggers(self.match, self.picture_picked.emit)

        self.paste = QAction("Match Clipboard Image", window)
        self.paste.setShortcut(QKeySequence(QKeySequence.StandardKey.Paste))
        self.paste.setStatusTip("Show the textures that look like the picture in the clipboard")
        self.paste.setEnabled(False)
        triggers(self.paste, self.picture_pasted.emit)

        self.disable = QAction("&Disable Filters", window)
        self.disable.setStatusTip("Put down whatever the grid is being asked for")
        self.disable.setEnabled(False)
        triggers(self.disable, self.filters_disabled.emit)

        find_menu.addAction(self.filter_color)

        # a colour and a picture are two ways of asking, and taking one up puts
        # the other down, so the menu keeps them apart the way the bar does
        find_menu.addSeparator()
        find_menu.addAction(self.match)
        find_menu.addAction(self.paste)

        find_menu.addSeparator()
        find_menu.addAction(self.disable)

    def build_view_menu(self, window: QMainWindow, view_menu: QMenu) -> None:
        self.build_toggles(window)
        self.build_tones(window)

        view_menu.addAction(self.preview)
        view_menu.addAction(self.inspector)
        view_menu.addAction(self.filters)

        # what the grid holds rather than which panes are up, so it sits apart
        # from the three entries above it
        view_menu.addSeparator()
        view_menu.addAction(self.incomplete)
        view_menu.addAction(self.simple)

        view_menu.addSeparator()
        checkerboard = view_menu.addMenu("&Alpha Mode")
        checkerboard.addActions(list(self._tones.values()))

        view_menu.addSeparator()
        # any native system menus under here

    def build_toggles(self, window: QMainWindow) -> None:
        # the command key "Ctrl" on mac and hands "Meta" to control
        inspector_key = "Shift+Ctrl+I" if sys.platform == "darwin" else "Shift+Alt+I"

        toggles = (
            Toggle(PREVIEW_KEY, "Show &Preview Pane", "Show the selected texture in a window of its own"),
            Toggle(
                INSPECTOR_KEY,
                "Show &Inspector",
                "Show details of the selected texture beside the grid",
                on=True,
                shortcut=inspector_key,
            ),
            Toggle(FILTERS_KEY, "Show &Filters", "Show the color filter bar", on=True),
            Toggle(
                INCOMPLETE_KEY,
                "Show &Incomplete Textures",
                "List entries the cache never finished downloading",
            ),
            Toggle(
                SIMPLE_KEY,
                "Show &Simple Textures",
                "List textures that are one solid color or fully transparent",
            ),
        )

        reports = {
            PREVIEW_KEY: self.previewed,
            INSPECTOR_KEY: self.inspected,
            FILTERS_KEY: self.filtered,
            INCOMPLETE_KEY: self.incompleted,
            SIMPLE_KEY: self.simple_shown,
        }

        self._toggles = {toggle.key: toggle.build(window, reports[toggle.key]) for toggle in toggles}

        self.preview = self._toggles[PREVIEW_KEY]
        self.inspector = self._toggles[INSPECTOR_KEY]
        self.filters = self._toggles[FILTERS_KEY]
        self.incomplete = self._toggles[INCOMPLETE_KEY]
        self.simple = self._toggles[SIMPLE_KEY]

    def build_tones(self, window: QMainWindow) -> None:
        self._tones = {}

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

    def build_app_menu(self, app_menu: QMenu) -> None:
        # the label does not matter on macOS, where the role decides where it goes
        about = app_menu.addAction(f"About {APP_DISPLAY_NAME}")
        about.setMenuRole(QAction.MenuRole.AboutRole)
        about.triggered.connect(self.abouted.emit)

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

    def context_menu(self, parent: QWidget, selected: int, *, idle: bool, previewing: bool) -> QMenu:
        menu = QMenu(parent)

        preview = menu.addAction("Hide Preview" if previewing else "Preview")
        preview.setShortcut(QKeySequence(Qt.Key.Key_Space))
        preview.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        preview.setShortcutVisibleInContextMenu(True)

        triggers(preview, self.preview_toggled.emit)

        checkerboard = menu.addMenu("&Alpha Mode")
        checkerboard.addActions(list(self._tones.values()))

        menu.addSeparator()

        entries = self.format_menu(menu, export_title(selected, everything=False), everything=False)
        entries.setEnabled(idle)

        return menu

    def sync_find(self, *, opened: bool, asking: bool) -> None:
        """Nothing can be asked of a cache that is not open, or put down unless it was asked"""

        self.filter_color.setEnabled(opened)
        self.match.setEnabled(opened)
        self.paste.setEnabled(opened)
        self.disable.setEnabled(asking)

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
        """Put the preview's tick away without a menu to hand

        The preview belongs to the app rather than to a window, so what it is
        doing is settled somewhere no one WindowActions is in scope.
        """

        store_toggle(PREVIEW_KEY, shown)


def fallback_menu(new_window: Callable[[], object]) -> QMenuBar:
    bar = QMenuBar()

    # only the one entry: everything else an app can do it does to a cache or
    # to a window, and both of those are a new window away
    new = bar.addMenu("&File").addAction("&New Window")
    new.setShortcut(QKeySequence(QKeySequence.StandardKey.New))
    triggers(new, new_window)

    return bar
