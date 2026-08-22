import signal
import sys
from bisect import bisect_left, bisect_right
from functools import partial
from pathlib import Path
from threading import Lock
from typing import ClassVar

from PySide6.QtCore import (
    QByteArray,
    QEvent,
    QItemSelectionModel,
    QModelIndex,
    QObject,
    QPoint,
    QRect,
    QSettings,
    QSize,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import QCloseEvent, QDesktopServices, QPixmapCache
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QListView,
    QMainWindow,
    QProgressDialog,
    QSplitter,
    QStatusBar,
)
from texture_courier import Texture, TextureCache
from texture_courier.core import TextureCacheError

from lltexturecache_viewer_gui.actions import WindowActions, fallback_menu
from lltexturecache_viewer_gui.checkerboard import sync_checkerboard
from lltexturecache_viewer_gui.export import ExportJob, Format
from lltexturecache_viewer_gui.formatting import format_count
from lltexturecache_viewer_gui.inspector import (
    INSPECTOR_WIDTH,
    STACK_CARDS,
    InspectorPane,
    stack_pixmap,
)
from lltexturecache_viewer_gui.recents import RecentCaches
from lltexturecache_viewer_gui.reveal import reveal
from lltexturecache_viewer_gui.signals import SignalWatcher
from lltexturecache_viewer_gui.tiles import (
    CELL_PADDING,
    PIXMAP_CACHE_KB,
    THUMBNAIL_SIZE,
    CellDelegate,
    TextureGrid,
    TextureModel,
    sidebar_key,
)

APP_NAME = "lltexturecache-viewer-gui"


# keys to track how the last window was left so it can be restored
SESSION_KEY = "openCaches"
GEOMETRY_KEY = "windowGeometry"
SPLITTER_KEY = "windowSplitter"

NEW_WINDOW_OFFSET = QPoint(32, 32)

DELAY_MESSAGE_DURATION_MS = 250
NOTICE_DURATION_MS = 5000


def stored_blob(settings: QSettings, key: str) -> QByteArray:
    stored = settings.value(key)

    return stored if isinstance(stored, QByteArray) else QByteArray()


class MainWindow(QMainWindow):
    _windows: ClassVar[list[MainWindow]] = []
    _quitting: ClassVar[bool] = False

    def __init__(self) -> None:
        super().__init__()

        MainWindow._windows.append(self)

        settings = QSettings()

        self.setWindowTitle(APP_NAME)

        # default window size
        self.resize(800, 600)

        self.restoreGeometry(stored_blob(settings, GEOMETRY_KEY))

        self._cache: TextureCache | None = None
        self._stack: list[Texture] = []
        self._job: ExportJob | None = None

        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(150) # wait for layout to settle
        self._settle.timeout.connect(self.settle_action)

        self._view = TextureGrid()
        self._view.setViewMode(QListView.ViewMode.IconMode)
        self._view.setIconSize(QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE))
        self._view.setSpacing(CELL_PADDING // 2)
        self._view.setItemDelegate(CellDelegate(self._view))
        self._view.setResizeMode(QListView.ResizeMode.Adjust)
        self._view.setMovement(QListView.Movement.Static)
        # disable drag action on icons. only valid on bg
        self._view.setDragDropMode(QListView.DragDropMode.NoDragDrop)
        self._view.setUniformItemSizes(True)
        self._view.setSelectionMode(QListView.SelectionMode.ExtendedSelection)
        self._view.setSelectionRectVisible(True)
        self._view.set_message("No texture cache selected")
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._view.opened.connect(self.open_action)
        self._view.customContextMenuRequested.connect(self.context_action)
        self._view.verticalScrollBar().valueChanged.connect(self.drain_action)

        self._inspector = InspectorPane()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._view)
        splitter.addWidget(self._inspector)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setCollapsible(0, False)
        splitter.setSizes([self.width() - INSPECTOR_WIDTH, INSPECTOR_WIDTH])

        splitter.restoreState(stored_blob(settings, SPLITTER_KEY))

        self._splitter = splitter

        self.setCentralWidget(splitter)

        self.setStatusBar(QStatusBar(self))

        self._resting = ""

        # what the bar falls back to once nothing is selected and no notice
        # is up, kept apart from the resting message the selection writes over
        self._showing = ""

        self.statusBar().messageChanged.connect(self.status_action)

        # an empty window has nothing to report, and the bar is not up yet
        self.sync_status()

        self._actions = WindowActions(self)
        self._actions.new_window.connect(self.new_window)
        self._actions.opened.connect(self.open_action)
        self._actions.reopened.connect(self.open_cache)
        self._actions.reloaded.connect(self.refresh_action)
        self._actions.exported.connect(self.export_action)
        self._actions.previewed.connect(self.sidebar_action)

        # how much is selected and how much is in the cache both move around
        # under the menu, and only this end knows either of them
        self._actions.exports.aboutToShow.connect(self.sync_export)

        # the preview entry comes up checked out of the stored setting, before
        # anything is listening to it, so the pane is put where it wants it here
        self.sync_preview()

    @classmethod
    def session(cls) -> list[Path]:
        stored = QSettings().value(SESSION_KEY) or []

        # a list of one comes back out of the store as the string it held
        if isinstance(stored, str):
            stored = [stored]

        return [Path(path) for path in stored]

    @classmethod
    def save_session(cls) -> None:
        QSettings().setValue(
            SESSION_KEY,
            [str(window._cache.cache_dir) for window in cls._windows if window._cache is not None],
        )

    @classmethod
    def quitting(cls) -> None:
        if cls._quitting:
            return

        cls.save_session()

        cls._quitting = True

    def save_layout(self) -> None:
        settings = QSettings()

        settings.setValue(GEOMETRY_KEY, self.saveGeometry())
        settings.setValue(SPLITTER_KEY, self._splitter.saveState())

    def closeEvent(self, event: QCloseEvent) -> None:
        self.save_layout()

        self._actions.shutdown()

        if self._job is not None:
            self._job.shutdown()

        model = self._view.model()

        if isinstance(model, TextureModel):
            model.shutdown()

        if self in MainWindow._windows:
            MainWindow._windows.remove(self)

        if not MainWindow._quitting:
            MainWindow.save_session()

        super().closeEvent(event)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)

        if event.type() == QEvent.Type.PaletteChange:
            self.restyle()

    def restyle(self) -> None:
        sync_checkerboard()

        model = self._view.model()

        if not isinstance(model, TextureModel) or not model.restyle():
            return

        self._view.viewport().update()

        self.paint_inspector()
        self._settle.start()

    def open_action(self) -> None:
        dialog = QFileDialog(self)
        dialog.setFileMode(QFileDialog.FileMode.Directory)

        if dialog.exec():
            self.open_cache(Path(dialog.selectedFiles()[0]))

    def refresh_action(self) -> None:
        if self._cache is None:
            return

        sizes = {texture.uuid: (texture.image_size, texture.body_size) for texture in self._cache}

        try:
            changed = list(self._cache.refresh())
        except (FileNotFoundError, TextureCacheError) as e:
            self.show_status(f"could not refresh {self._cache.cache_dir}: {e}")
            return

        added = [texture for texture in changed if texture.uuid not in sizes]
        rewritten = [
            texture
            for texture in changed
            if texture.uuid in sizes and sizes[texture.uuid] != (texture.image_size, texture.body_size)
        ]

        for texture in rewritten:
            QPixmapCache.remove(texture.uuid)
            QPixmapCache.remove(sidebar_key(texture.uuid))

        shown = self._inspector.texture

        if added or rewritten:
            self.populate_grid(
                f"Reloaded {format_count(len(added))} new and {format_count(len(rewritten))} changed textures"
            )
        else:
            self.flash_status("No new textures found after reload")

        if shown is not None:
            self.select_texture(shown.uuid)
            self.scroll_to_end()


    def export_action(self, format: Format, everything: bool) -> None:
        model = self._view.model()

        if not isinstance(model, TextureModel) or self._job is not None:
            return

        textures = self.export_textures(model, everything)

        if not textures:
            return

        dialog = QFileDialog(self, f"Export {format_count(len(textures))} textures as {format.label}")
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setLabelText(QFileDialog.DialogLabel.Accept, "Export")

        if dialog.exec():
            self.export(textures, Path(dialog.selectedFiles()[0]), format, model.reads)

    def context_action(self, at: QPoint) -> None:
        model = self._view.model()

        if not isinstance(model, TextureModel):
            return

        selection = self._view.selectionModel()
        index = self._view.indexAt(at)

        if index.isValid() and not selection.isSelected(index):
            selection.setCurrentIndex(index, QItemSelectionModel.SelectionFlag.ClearAndSelect)

        selected = len(selection.selectedIndexes())

        if not selected:
            return

        menu = self._actions.context_menu(self._view, selected, idle=self._job is None)

        menu.exec(self._view.viewport().mapToGlobal(at))
        menu.deleteLater()

    def sync_export(self) -> None:
        model = self._view.model()
        showing = isinstance(model, TextureModel)

        selected = len(self._view.selectionModel().selectedIndexes()) if showing else 0
        total = model.rowCount() if showing else 0

        self._actions.sync_export(selected, total, idle=self._job is None)

    def export_textures(self, model: TextureModel, everything: bool) -> list[Texture]:
        if everything:
            return [model.texture(row) for row in range(model.rowCount())]

        rows = sorted(index.row() for index in self._view.selectionModel().selectedIndexes())

        return [model.texture(row) for row in rows]

    def export(self, textures: list[Texture], out_dir: Path, format: Format, reads: Lock) -> None:
        progress = QProgressDialog(
            f"Exporting {format_count(len(textures))} textures as {format.label}...",
            "Cancel",
            0,
            len(textures),
            self,
        )
        progress.setWindowTitle("Export")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(DELAY_MESSAGE_DURATION_MS)
        progress.setValue(0)

        job = ExportJob(textures, out_dir, format, reads, self)
        job.progressed.connect(progress.setValue)
        job.finished.connect(partial(self.exported, out_dir, progress))

        progress.canceled.connect(job.cancel)

        self._job = job

        # a refresh reads the cache's files in again and puts the new ones in
        # place of the ones the export is halfway through reading
        self._actions.reload.setEnabled(False)
        self.sync_export()

        job.start()

    def exported(self, out_dir: Path, progress: QProgressDialog, written: int, failed: int, cancelled: bool) -> None:
        progress.reset()
        progress.deleteLater()

        written_paths = self._job.written_paths if self._job is not None else []

        if self._job is not None:
            self._job.deleteLater()
            self._job = None

        self._actions.reload.setEnabled(self._cache is not None)
        self.sync_export()

        note = "Cancelled export of" if cancelled else "Exported"
        summary = f"{note} {format_count(written)} texture(s) to {out_dir}"

        self.flash_status(f"{summary} ({format_count(failed)} could not be written)" if failed else summary)

        if written and not cancelled and not reveal(written_paths):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(out_dir)))

    def sidebar_action(self, shown: bool) -> None:
        self.sync_preview()

        if shown:
            self.sync_inspector()

    def sync_preview(self) -> None:
        opened = self._cache is not None

        self._actions.preview.setEnabled(opened)
        self._inspector.setVisible(opened and self._actions.preview.isChecked())

    def selection_action(self, *_: object) -> None:
        self.sync_inspector()
        self.sync_export()
        self.sync_selection()

    def ready_action(self, uuid: str) -> None:
        if any(texture.uuid == uuid for texture in self._stack):
            self.paint_inspector()

    def settle_action(self) -> None:
        model = self._view.model()

        if not isinstance(model, TextureModel):
            return

        for texture in self._stack:
            model.full(texture)

        self.paint_inspector()

    def sync_inspector(self) -> None:
        model = self._view.model()

        if not self._inspector.isVisible() or not isinstance(model, TextureModel):
            return

        index = self.selected_index()

        if not index.isValid():
            self._stack = []
            self._inspector.clear()
            return

        selected = self._view.selectionModel().selectedIndexes()

        self._inspector.show_texture(
            model.texture(index.row()),
            len(selected),
            sum(model.texture(other.row()).image_size for other in selected),
        )

        self._stack = self.stack_textures(model, index, selected)
        self._settle.start()

        self.paint_inspector()

    def stack_textures(self, model: TextureModel, index: QModelIndex, selected: list[QModelIndex]) -> list[Texture]:

        top = model.texture(index.row())
        others = [model.texture(other.row()) for other in selected if other.row() != index.row()]

        if not others:
            return [top]

        # sample selection
        step = max(1, len(others) // (STACK_CARDS - 1))

        return [*others[::step][: STACK_CARDS - 1], top]

    def paint_inspector(self) -> None:
        model = self._view.model()

        if not isinstance(model, TextureModel) or not self._stack:
            return

        top = model.full(self._stack[-1])
        cards = []

        for texture in self._stack:
            # only the texture on top is worth a decode on the spot. the rest go
            # in with whatever the grid or an earlier selection left behind,
            # until the selection settles and they are decoded properly
            ready = model.full(texture, decode=False)
            pixmap = ready[0] if ready is not None else model.cell(texture)

            if not pixmap.isNull():
                cards.append((texture.uuid, pixmap))

        self._inspector.set_sidebar(stack_pixmap(cards), top[1] if top is not None else None)

    def selected_index(self) -> QModelIndex:
        selection = self._view.selectionModel()
        current = self._view.currentIndex()

        if current.isValid() and selection.isSelected(current):
            return current

        selected = selection.selectedIndexes()

        return selected[-1] if selected else QModelIndex()

    def drain_action(self) -> None:
        model = self._view.model()

        if not isinstance(model, TextureModel):
            return

        rows = self.visible_rows(model)

        if rows is not None:
            model.drain(*rows)

    def visible_rows(self, model: TextureModel) -> tuple[int, int] | None:
        count = model.rowCount()
        height = self._view.viewport().height()

        def cell(row: int) -> QRect:
            return self._view.visualRect(model.index(row, 0))

        first = bisect_left(range(count), 0, key=lambda row: cell(row).bottom())
        last = bisect_right(range(count), height, key=lambda row: cell(row).top()) - 1

        return (first, last) if first <= last < count else None

    def select_texture(self, uuid: str) -> None:
        model = self._view.model()

        if not isinstance(model, TextureModel):
            return

        row = model.row(uuid)

        if row is None:
            return

        self._view.selectionModel().setCurrentIndex(
            model.index(row, 0),
            QItemSelectionModel.SelectionFlag.ClearAndSelect,
        )

    def scroll_to_end(self) -> None:
        self._view.scrollToBottom()

    def open_cache(self, cache_dir: Path) -> None:
        try:
            cache = TextureCache(cache_dir)
        except (FileNotFoundError, TextureCacheError) as e:
            self.show_status(f"Could not open {cache_dir}: {e}")
            return

        RecentCaches.shared().remember(cache.cache_dir)

        if self._cache is None:
            self.set_cache(cache)
        else:
            self.new_window(cache)

    def new_window(self, cache: TextureCache | None = None) -> MainWindow:
        window = MainWindow()

        window.move(self.pos() + NEW_WINDOW_OFFSET)

        if cache is not None:
            window.set_cache(cache)

        window.show()

        return window

    def set_cache(self, cache: TextureCache) -> None:
        self._cache = cache

        self._actions.reload.setEnabled(True)
        self.sync_preview()
        self.sync_status()

        MainWindow.save_session()

        self.setWindowTitle(f"{cache.cache_dir} - {APP_NAME}")
        self.setWindowFilePath(str(cache.cache_dir))
        self.populate_grid()

    def status_action(self, message: str) -> None:
        if not message and self._resting:
            self.statusBar().showMessage(self._resting)
            return

        self.sync_status()

    def sync_status(self) -> None:
        """Keep the bar down until there is a cache open to report on"""

        # a window with nothing open in it can still have something to say, and
        # the bar comes up under the message for as long as it is there
        self.statusBar().setVisible(self._cache is not None or bool(self.statusBar().currentMessage()))

    def show_status(self, message: str) -> None:
        self._resting = message
        self.statusBar().showMessage(message)

    def sync_selection(self) -> None:
        """Report how much of the grid is picked out, or fall back to the grid"""

        model = self._view.model()

        if not isinstance(model, TextureModel):
            return

        selected = len(self._view.selectionModel().selectedIndexes())

        self.show_status(
            f"Selected {format_count(selected)} of {format_count(model.rowCount())} textures"
            if selected
            else self._showing
        )

    def flash_status(self, message: str) -> None:
        self.statusBar().showMessage(message, NOTICE_DURATION_MS)

    def populate_grid(self, note: str | None = None) -> None:
        if self._cache is None:
            return

        textures = [texture for texture in self._cache if texture.whole()]

        self._view.set_message("Cache is empty")

        old_model = self._view.model()

        if isinstance(old_model, TextureModel):
            old_model.shutdown()

        model = TextureModel(textures, self)
        model.full_ready.connect(self.ready_action)

        self._view.setModel(model)

        if old_model is not None:
            old_model.deleteLater()

        selection = self._view.selectionModel()
        selection.selectionChanged.connect(self.selection_action)
        selection.currentChanged.connect(self.selection_action)

        self._stack = []
        self._inspector.clear()

        self.sync_export()
        self.scroll_to_end()

        shown = f"Showing {format_count(len(textures))} textures of {format_count(len(self._cache))} entries in cache"

        self._showing = note if note else shown

        self.show_status(self._showing)


class AppWatcher(QObject):
    """Catches what happens to the app rather than to any one of its windows"""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Quit:
            MainWindow.quitting()

        if event.type() == QEvent.Type.ApplicationStateChange:
            active = QApplication.applicationState() == Qt.ApplicationState.ApplicationActive

            if active and not MainWindow._windows:
                MainWindow().show()

        return super().eventFilter(watched, event)


def restore(paths: list[Path]) -> list[MainWindow]:
    """Put the windows of a session back up, one to a cache"""

    windows: list[MainWindow] = []

    for path in paths:
        try:
            cache = TextureCache(path)
        except FileNotFoundError, TextureCacheError:
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


def main() -> None:
    app = QApplication(sys.argv)

    app.setOrganizationName(APP_NAME)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)

    QPixmapCache.setCacheLimit(PIXMAP_CACHE_KB)

    sync_checkerboard()

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

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
