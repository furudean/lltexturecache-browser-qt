from bisect import bisect_left, bisect_right
from functools import partial
from pathlib import Path
from threading import Lock
from typing import ClassVar

from PySide6.QtCore import (
    QByteArray,
    QDir,
    QEvent,
    QItemSelection,
    QItemSelectionModel,
    QModelIndex,
    QPoint,
    QRect,
    QSettings,
    QSize,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import QCloseEvent, QColor, QDesktopServices, QPixmap, QPixmapCache
from PySide6.QtWidgets import (
    QFileDialog,
    QListView,
    QMainWindow,
    QProgressDialog,
    QSplitter,
)
from texture_courier import Texture, TextureCache, TextureCacheError

from lltexturecache_browser_qt import APP_DISPLAY_NAME
from lltexturecache_browser_qt.about import AboutDialog
from lltexturecache_browser_qt.actions import WindowActions
from lltexturecache_browser_qt.checkerboard import sync_checkerboard
from lltexturecache_browser_qt.export import ExportJob, Format
from lltexturecache_browser_qt.filters import ColorFilterBar
from lltexturecache_browser_qt.formatting import format_count
from lltexturecache_browser_qt.grid import CELL_PADDING, CellDelegate, TextureGrid
from lltexturecache_browser_qt.images import THUMBNAIL_SIZE
from lltexturecache_browser_qt.inspector import INSPECTOR_WIDTH, InspectorPane
from lltexturecache_browser_qt.model import TextureModel, full_size, sidebar_key
from lltexturecache_browser_qt.preview import PreviewWindow
from lltexturecache_browser_qt.recents import RecentCaches
from lltexturecache_browser_qt.reveal import reveal
from lltexturecache_browser_qt.stack import STACK_CARDS, stack_pixmap
from lltexturecache_browser_qt.status import WindowStatus
from lltexturecache_browser_qt.suggested import paths as suggested_paths

# keys to track how the last window was left so it can be restored
SESSION_KEY = "openCaches"
GEOMETRY_KEY = "windowGeometry"
SPLITTER_KEY = "windowSplitter"
PREVIEW_GEOMETRY_KEY = "previewGeometry"
FILTERS_KEY = "colorFilters"

NEW_WINDOW_OFFSET = QPoint(32, 32)

DELAY_MESSAGE_DURATION_MS = 250


def stored_blob(settings: QSettings, key: str) -> QByteArray:
    stored = settings.value(key)

    return stored if isinstance(stored, QByteArray) else QByteArray()


def color_spans(model: TextureModel, rows: list[int]) -> QItemSelection:
    selection = QItemSelection()
    first = last = rows[0]

    for row in rows[1:]:
        if row == last + 1:
            last = row
            continue

        selection.select(model.index(first, 0), model.index(last, 0))

        first = last = row

    selection.select(model.index(first, 0), model.index(last, 0))

    return selection


def laid_card(pixmap: QPixmap, natural: QSize) -> QPixmap:
    laid = full_size(natural)

    if natural.isEmpty() or laid == pixmap.size():
        return pixmap

    # the stand-in is a picture of the same texture, so any shape it has that
    # the texture does not is rounding from the size it was kept at
    return pixmap.scaled(laid, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)


class MainWindow(QMainWindow):
    _windows: ClassVar[list["MainWindow"]] = []
    _quitting: ClassVar[bool] = False
    _about: ClassVar["AboutDialog | None"] = None

    def __init__(self) -> None:
        super().__init__()

        MainWindow._windows.append(self)

        settings = QSettings()

        self.setWindowTitle(APP_DISPLAY_NAME)

        # default window size
        self.resize(800, 600)

        self.restoreGeometry(stored_blob(settings, GEOMETRY_KEY))

        self._cache: TextureCache | None = None
        self._stack: list[Texture] = []
        self._job: ExportJob | None = None

        self._summary = ""

        # after filters
        self._kept: list[str] = []
        self._current: str | None = None

        # preview window
        self._preview: PreviewWindow | None = None

        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(150)  # wait for layout to settle
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
        self._view.set_message("No texture cache selected", may_open=True)
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

        self._filters = ColorFilterBar(self)

        # the strip comes back up as it was left, before anything is listening,
        # so the colors are already on it when a cache arrives to be ranked
        self._filters.revive(settings.value(FILTERS_KEY))

        self._filters.changed.connect(self.filter_action)
        self._filters.visibilityChanged.connect(self.filters_shown_action)

        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._filters)

        self._status = WindowStatus(self)

        self._actions = WindowActions(self)
        self._actions.new_window.connect(self.new_window)
        self._actions.opened.connect(self.open_action)
        self._actions.reopened.connect(self.open_cache)
        self._actions.reloaded.connect(self.refresh_action)
        self._actions.exported.connect(self.export_action)
        self._actions.previewed.connect(self.preview_action)
        self._actions.inspected.connect(self.inspector_action)
        self._actions.filtered.connect(self.filters_action)
        self._actions.incompleted.connect(self.incomplete_action)
        self._actions.abouted.connect(self.about_action)

        # how much is selected and how much is in the cache both move around
        # under the menu, and only this end knows either of them
        self._actions.exports.aboutToShow.connect(self.sync_export)

        # both entries come up out of their stored settings, before anything is
        # listening to them, so the pane and the window are put where the menu
        # already says they are here
        self.sync_inspector()
        self.sync_preview()
        self.sync_filters()
        self.sync_incomplete()

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
    def any_open(cls) -> bool:
        return bool(cls._windows)

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
        settings.setValue(FILTERS_KEY, self._filters.state())

        if self._preview is not None:
            settings.setValue(PREVIEW_GEOMETRY_KEY, self._preview.saveGeometry())

    def closeEvent(self, event: QCloseEvent) -> None:
        self.save_layout()

        if self._preview is not None:
            self._preview.hide()

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

        # the preview window keeps the texture's alpha and lays the board down
        # behind it, so a new board is a repaint rather than a fresh decode
        if self._preview is not None:
            self._preview.update()

        model = self._view.model()

        if not isinstance(model, TextureModel) or not model.restyle():
            return

        self._view.viewport().update()

        self.paint_inspector()
        self._settle.start()

    def open_action(self) -> None:
        dialog = QFileDialog(self, "Select a texturecache directory")
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly)
        dialog.setFilter(QDir.Filter.AllDirs | QDir.Filter.Hidden | QDir.Filter.NoDotAndDotDot)
        dialog.setLabelText(QFileDialog.DialogLabel.Accept, "Open Cache")

        cache_dirs = [QUrl.fromLocalFile(d.parent) for d in suggested_paths()]
        dialog.setSidebarUrls(cache_dirs)

        if dialog.exec():
            self.open_cache(Path(dialog.selectedFiles()[0]))

    def refresh_action(self) -> None:
        if self._cache is None:
            return

        sizes = {texture.uuid: (texture.image_size, texture.body_size) for texture in self._cache}

        try:
            changed = list(self._cache.refresh())
        except (FileNotFoundError, TextureCacheError) as e:
            self._status.rest(f"could not refresh {self._cache.cache_dir}: {e}")
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

        # an entry the grid is not showing is neither news to report nor a row
        # to scroll to, however much of it the viewer wrote since the last read
        if not self.showing_incomplete():
            added = [texture for texture in added if texture.whole()]
            rewritten = [texture for texture in rewritten if texture.whole()]

        shown = self._inspector.texture
        place = self._view.place()

        if added or rewritten:
            self.populate_grid(
                f"Reloaded {format_count(len(added))} new and {format_count(len(rewritten))} changed textures"
            )
        else:
            self._status.flash("No new textures found after reload")

        if shown is not None:
            self.select_texture(shown.uuid)

        if self.ranking():
            return

        if added:
            self.scroll_to_end()
        elif rewritten:
            self._view.pin_to(place)

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

        self._status.flash(f"{summary} ({format_count(failed)} could not be written)" if failed else summary)

        if written and not cancelled and not reveal(written_paths):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(out_dir)))

    def filters_action(self, shown: bool) -> None:
        self.sync_filters()

    def filters_shown_action(self, shown: bool) -> None:
        # the bar can also be hidden from the context menu the window puts up
        # over its toolbars, and the entry under the menu is what has to say so
        # afterwards. a bar away because no cache is open is not that
        if self._cache is not None:
            self._actions.filters.setChecked(shown)

    def sync_filters(self) -> None:
        opened = self._cache is not None

        self._actions.filters.setEnabled(opened)
        self._filters.setVisible(opened and self._actions.filters.isChecked())

    def incomplete_action(self, shown: bool) -> None:
        if self._cache is None:
            return

        standing = self._inspector.texture
        place = self._view.place()

        self.populate_grid()

        if standing is not None:
            self.select_texture(standing.uuid)

        if self.ranking():
            return

        # letting the rest of the cache in moves every row after the first of
        # them, so there is no place to come back to
        if shown:
            self.scroll_to_end()
        else:
            self._view.pin_to(place)

    def sync_incomplete(self) -> None:
        self._actions.incomplete.setEnabled(self._cache is not None)

    def showing_incomplete(self) -> bool:
        return self._actions.incomplete.isChecked()

    def narrowed(self) -> bool:
        model = self._view.model()

        return isinstance(model, TextureModel) and model.narrowed

    def ranking(self) -> bool:
        return bool(self._filters.colors())

    def filter_action(self, colors: list[QColor]) -> None:
        model = self._view.model()

        if not isinstance(model, TextureModel):
            return

        if model.set_filters(colors):
            self.ranked_action()
        else:
            self._status.flash("Please wait...")

    def ranked_action(self) -> None:
        self.sync_empty()
        self.sync_export()

        self._status.set_summary(self.summary())

        self.scroll_ranked()

    def summary(self) -> str:
        model = self._view.model()

        if not isinstance(model, TextureModel) or not model.narrowed:
            return self._summary

        return f"Showing {format_count(model.rowCount())} of {format_count(model.total())} textures matching filters"

    def sync_empty(self) -> None:
        model = self._view.model()

        if not isinstance(model, TextureModel) or not model.narrowed:
            self._view.set_message("Cache is empty")
        else:
            self._view.set_message("No textures match filters")

    def scroll_ranked(self) -> None:
        current = self._view.currentIndex()

        if current.isValid():
            self._view.unpin()
            self._view.scrollTo(current, QListView.ScrollHint.PositionAtCenter)
        elif self.narrowed():
            self._view.unpin()
            self._view.scrollToTop()
        else:
            self.scroll_to_end()

    def keep_selection(self) -> None:
        model = self._view.model()

        if not isinstance(model, TextureModel):
            return

        selected = self._view.selectionModel().selectedIndexes()
        current = self.selected_index()

        self._kept = [model.texture(index.row()).uuid for index in selected]
        self._current = model.texture(current.row()).uuid if current.isValid() else None

    def restore_selection(self) -> None:
        model = self._view.model()

        if not isinstance(model, TextureModel):
            return

        kept, current = self._kept, self._current

        self._kept, self._current = [], None

        rows = sorted(row for uuid in kept if (row := model.row(uuid)) is not None)
        selection = self._view.selectionModel()

        if rows:
            selection.select(color_spans(model, rows), QItemSelectionModel.SelectionFlag.ClearAndSelect)

        standing = model.row(current) if current is not None else None

        if standing is not None:
            # the selection is already back, and this only says which of it the
            # panes are on, so it is set without touching what is selected
            selection.setCurrentIndex(model.index(standing, 0), QItemSelectionModel.SelectionFlag.NoUpdate)

    def inspector_action(self, shown: bool) -> None:
        self.sync_inspector()

        if shown:
            self.fill_inspector()

    def sync_inspector(self) -> None:
        opened = self._cache is not None

        self._actions.inspector.setEnabled(opened)
        self._inspector.setVisible(opened and self._actions.inspector.isChecked())

    def preview_action(self, shown: bool) -> None:
        self.sync_preview()

        if shown:
            self.fill_preview()

    def preview_closed_action(self) -> None:
        self._actions.preview.setChecked(False)

    def sync_preview(self) -> None:
        opened = self._cache is not None

        self._actions.preview.setEnabled(opened)

        if not (opened and self._actions.preview.isChecked()):
            if self._preview is not None:
                self._preview.hide()

            return

        if self._preview is None:
            self._preview = PreviewWindow(self)
            self._preview.closed.connect(self.preview_closed_action)
            self._preview.restoreGeometry(stored_blob(QSettings(), PREVIEW_GEOMETRY_KEY))

        self._preview.present()

    def preview_ready_action(self, _uuid: str) -> None:
        self.fill_preview()

    def fill_preview(self) -> None:
        """Show whatever is selected in the preview window, if one is up"""

        model = self._view.model()

        if self._preview is None or not self._preview.isVisible() or not isinstance(model, TextureModel):
            return

        index = self.selected_index()

        if not index.isValid():
            self._preview.clear()
            return

        texture = model.texture(index.row())

        # asking marks this as the one texture the window is on, so a decode
        # the selection has already been walked past is dropped when it lands.
        # the grid and the pane read smaller and sooner, and whichever of them
        # has already been through this texture stands in until it lands
        self._preview.show_texture(texture, model.preview(texture), model.standing(texture))

    def selection_action(self, *_: object) -> None:
        self.fill_inspector()
        self.fill_preview()
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

    def fill_inspector(self) -> None:
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

        # only the texture on top is worth a decode on the spot
        model.full(self._stack[-1])

        cards = []

        for texture in self._stack:
            # the rest go in with whatever the grid or an earlier selection left
            # behind, until the selection settles and they are decoded properly
            ready = model.standing(texture)

            if ready is not None:
                cards.append((texture.uuid, laid_card(*ready)))

        self._inspector.set_sidebar(
            stack_pixmap(cards, self._inspector.sidebar_room()),
            self.shape(model, self._stack[-1]),
        )

    def shape(self, model: TextureModel, texture: Texture) -> QSize | None:
        natural = model.natural(texture)

        if not natural.isEmpty():
            return natural

        return QSize() if model.full(texture, decode=False) is not None else None

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
        self._view.pin_to_bottom()

    def open_cache(self, cache_dir: Path) -> None:
        try:
            cache = TextureCache(cache_dir)
        except (FileNotFoundError, TextureCacheError) as e:
            self._status.rest(f"Could not open {cache_dir}: {e}")
            return

        RecentCaches.shared().remember(cache.cache_dir)

        if self._cache is None:
            self.set_cache(cache)
        else:
            self.new_window(cache)

    def new_window(self, cache: TextureCache | None = None) -> "MainWindow":
        window = MainWindow()

        window.move(self.pos() + NEW_WINDOW_OFFSET)

        if cache is not None:
            window.set_cache(cache)

        window.show()

        return window

    def set_cache(self, cache: TextureCache) -> None:
        self._cache = cache

        self._actions.reload.setEnabled(True)
        self.sync_inspector()
        self.sync_preview()
        self.sync_filters()
        self.sync_incomplete()
        self._status.set_opened(True)

        MainWindow.save_session()

        self.setWindowTitle(f"{cache.cache_dir} — {APP_DISPLAY_NAME}")
        self.setWindowFilePath(str(cache.cache_dir))
        self.populate_grid()

    def sync_selection(self) -> None:
        model = self._view.model()

        if not isinstance(model, TextureModel):
            return

        self._status.show_selection(len(self._view.selectionModel().selectedIndexes()), model.rowCount())

    def populate_grid(self, note: str | None = None) -> None:
        if self._cache is None:
            return

        incomplete = self.showing_incomplete()
        textures = [texture for texture in self._cache if incomplete or texture.whole()]

        self._view.set_message("Cache is empty")

        old_model = self._view.model()

        if isinstance(old_model, TextureModel):
            old_model.shutdown()

        model = TextureModel(textures, self)
        model.full_ready.connect(self.ready_action)
        model.preview_ready.connect(self.preview_ready_action)
        model.ranked.connect(self.ranked_action)

        self._view.setModel(model)

        if old_model is not None:
            old_model.deleteLater()

        selection = self._view.selectionModel()
        selection.selectionChanged.connect(self.selection_action)
        selection.currentChanged.connect(self.selection_action)

        model.modelAboutToBeReset.connect(self.keep_selection)
        model.modelReset.connect(self.restore_selection)

        self._stack = []
        self._inspector.clear()

        # the window was showing a texture out of the model just retired, and
        # is filled again by whatever selection lands in the new one
        if self._preview is not None:
            self._preview.clear()

        model.set_filters(self._filters.colors())

        self.sync_export()

        if not self.ranking():
            self.scroll_to_end()

        self._summary = (
            f"Showing {format_count(len(textures))} textures of {format_count(len(self._cache))} entries in cache"
        )

        unfinished = sum(1 for texture in textures if not texture.whole()) if incomplete else 0

        if unfinished:
            self._summary += f", {format_count(unfinished)} incomplete"

        self._status.set_summary(note if note else self.summary())

    def about_action(self) -> None:
        if MainWindow._about is None:
            MainWindow._about = AboutDialog()

        MainWindow._about.show()
        MainWindow._about.raise_()
        MainWindow._about.activateWindow()
