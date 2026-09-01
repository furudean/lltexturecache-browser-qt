from pathlib import Path
from threading import Lock
from typing import ClassVar

from PySide6.QtCore import (
    QDir,
    QEvent,
    QItemSelection,
    QItemSelectionModel,
    QModelIndex,
    QPoint,
    QSettings,
    QSize,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QDrag,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QGuiApplication,
    QPixmap,
    QPixmapCache,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QListView,
    QMainWindow,
    QSplitter,
    QWidget,
)
from texture_courier import Texture, TextureCache, TextureCacheError

from lltexturecache_browser_qt import APP_DISPLAY_NAME
from lltexturecache_browser_qt.about import AboutDialog
from lltexturecache_browser_qt.actions import WindowActions
from lltexturecache_browser_qt.cards import grid_cards, stack_textures
from lltexturecache_browser_qt.checkerboard import (
    CheckerboardChanges,
    pixmap_lightness,
    reset_pane_tone,
    set_picked_lightness,
    sync_checkerboard,
)
from lltexturecache_browser_qt.drag import DRAG_LIMIT, drag_data, staged
from lltexturecache_browser_qt.dropzone import DropZone
from lltexturecache_browser_qt.export import Format
from lltexturecache_browser_qt.exporting import ExportRun, ask_for_directory
from lltexturecache_browser_qt.filters import ColorFilterBar
from lltexturecache_browser_qt.formatting import format_count
from lltexturecache_browser_qt.grid import CELL_PADDING, CellDelegate, TextureGrid
from lltexturecache_browser_qt.images import THUMBNAIL_SIZE
from lltexturecache_browser_qt.inspector import INSPECTOR_WIDTH, InspectorPane
from lltexturecache_browser_qt.model import TextureModel, full_size, sidebar_key
from lltexturecache_browser_qt.prefetch import prefetch
from lltexturecache_browser_qt.preview import PreviewWindow
from lltexturecache_browser_qt.previewing import PreviewHost
from lltexturecache_browser_qt.recents import RecentCaches
from lltexturecache_browser_qt.settings import (
    FILTERS_KEY,
    GEOMETRY_KEY,
    SESSION_KEY,
    SPLITTER_KEY,
    stored_blob,
    stored_paths,
)
from lltexturecache_browser_qt.stack import stack_pixmap
from lltexturecache_browser_qt.status import WindowStatus
from lltexturecache_browser_qt.suggested import paths as suggested_paths

NEW_WINDOW_OFFSET = QPoint(32, 32)


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

    # the preview belongs to the app rather than to any window, so what it is
    # doing is kept beside the windows rather than in one of them
    _preview_host: ClassVar[PreviewHost]

    def __init__(self) -> None:
        super().__init__()

        MainWindow._windows.append(self)

        settings = QSettings()

        self.setWindowTitle(APP_DISPLAY_NAME)

        # a directory dropped anywhere on the window is opened in it
        self.setAcceptDrops(True)

        # default window size
        self.resize(800, 600)

        self.restoreGeometry(stored_blob(settings, GEOMETRY_KEY))

        self._cache: TextureCache | None = None
        self._stack: list[Texture] = []
        self._job: ExportRun | None = None

        self._summary = ""

        # after filters
        self._kept: list[str] = []
        self._current: str | None = None

        # the texture the panes are showing, which is what says whether a click on
        # one of them is still about what is in front of the user
        self._standing = ""

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
        # a texture is dragged out of the window as a file, and nothing is
        # ever dropped into the grid
        self._view.setDragDropMode(QListView.DragDropMode.DragOnly)
        self._view.setDefaultDropAction(Qt.DropAction.CopyAction)
        self._view.setUniformItemSizes(True)
        self._view.setSelectionMode(QListView.SelectionMode.ExtendedSelection)
        self._view.setSelectionRectVisible(True)
        self._view.set_message("No texture cache selected")
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._view.dragged.connect(self.drag_action)
        self._view.previewed.connect(self.toggle_preview_action)
        self._view.customContextMenuRequested.connect(self.context_action)
        self._view.verticalScrollBar().valueChanged.connect(self.prefetch_action)
        # a grid that has been resized, filtered or filled has a new band under
        # it without anything having scrolled
        self._view.verticalScrollBar().rangeChanged.connect(self.prefetch_action)

        self._inspector = InspectorPane()
        self._inspector.dragged.connect(self.inspector_drag_action)
        self._inspector.menued.connect(self.inspector_context_action)

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

        # laid over the central widget while a cache is held over the window
        self._zone = DropZone(self)

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
        self._actions.preview_toggled.connect(self.toggle_preview_action)
        self._actions.inspected.connect(self.inspector_action)
        self._actions.filtered.connect(self.filters_action)
        self._actions.incompleted.connect(self.incomplete_action)
        self._actions.simple_shown.connect(self.simple_action)
        self._actions.abouted.connect(self.about_action)

        # how much is selected and how much is in the cache both move around
        # under the menu, and only this end knows either of them
        self._actions.exports.aboutToShow.connect(self.sync_export)

        # the checkerboard is the app's rather than this window's, and a click in one
        # window is a repaint in every one of them
        CheckerboardChanges.shared().changed.connect(self.restyle)

        # both entries come up out of their stored settings, before anything is
        # listening to them, so the pane and the window are put where the menu
        # already says they are here
        self.sync_inspector()
        self.sync_preview()
        self.sync_filters()
        self.sync_incomplete()
        self.sync_simple()

    @classmethod
    def session(cls) -> list[Path]:
        return stored_paths(QSettings(), SESSION_KEY)

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

    @classmethod
    def shared_preview(cls) -> "PreviewWindow":
        """The one preview window, which belongs to the app rather than a window"""

        return cls._preview_host.shared()

    @classmethod
    def set_preview_shown(cls, shown: bool) -> None:
        """Say across the app whether the shared preview is up"""

        # the menus are moved without being listened to, so what they say the
        # preview is doing is put away here instead
        WindowActions.store_preview(shown)

        cls._preview_host.sync_ticks(shown=shown)

    @classmethod
    def follow_preview(cls, window: "MainWindow | None" = None) -> None:
        """Point the shared preview at a window, or at whichever one is left to take it"""

        cls._preview_host.follow(window)

    @classmethod
    def preview_closed_action(cls) -> None:
        cls.set_preview_shown(False)

    def save_layout(self) -> None:
        settings = QSettings()

        settings.setValue(GEOMETRY_KEY, self.saveGeometry())
        settings.setValue(SPLITTER_KEY, self._splitter.saveState())
        settings.setValue(FILTERS_KEY, self._filters.state())

        MainWindow._preview_host.save_geometry(settings)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.save_layout()

        self._actions.shutdown()

        CheckerboardChanges.shared().changed.disconnect(self.restyle)

        if self._job is not None:
            self._job.shutdown()

        model = self._view.model()

        if isinstance(model, TextureModel):
            model.shutdown()

        if self in MainWindow._windows:
            MainWindow._windows.remove(self)

        # the preview is left with whichever window is still open to take it
        if MainWindow._preview_host.release(self):
            MainWindow.follow_preview()

        if not MainWindow._quitting:
            MainWindow.save_session()

        super().closeEvent(event)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)

        if event.type() == QEvent.Type.PaletteChange:
            self.restyle()

        # the shared preview follows the window being worked in
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            MainWindow.follow_preview(self)

    def restyle(self) -> None:
        sync_checkerboard()

        # both panes keep the texture's alpha and lay the checkerboard down
        # behind it, so a new checkerboard is a repaint rather than a fresh
        # decode. the checkerboard they draw is their own, and moves without the
        # cells' checkerboard moving with it
        preview = MainWindow._preview_host.window

        if preview is not None:
            preview.update()

        self.paint_inspector()

        model = self._view.model()

        if not isinstance(model, TextureModel) or not model.restyle():
            return

        # a cell has the checkerboard painted into it, so it is decoded again
        self._view.viewport().update()

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

        out_dir = ask_for_directory(self, textures, format)

        if out_dir is not None:
            self.export(textures, out_dir, format, model.reads)

    def inspector_drag_action(self) -> None:
        self.drag_action(self._inspector)

    def drag_action(self, source: QWidget | None = None) -> None:
        model = self._view.model()

        if not isinstance(model, TextureModel):
            return

        textures = self.export_textures(model, everything=False)

        if not textures:
            return

        if len(textures) > DRAG_LIMIT:
            self._status.flash("Can't drag that many; export them instead")
            return

        QGuiApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)

        try:
            paths = staged(textures, model.reads)
        finally:
            QGuiApplication.restoreOverrideCursor()

        if not paths:
            return

        pixmap = self.drag_pixmap(model)

        drag = QDrag(source if source is not None else self._view)
        drag.setMimeData(drag_data(paths))

        if not pixmap.isNull():
            drag.setPixmap(pixmap)
            drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))

        drag.exec(Qt.DropAction.CopyAction)

    def drag_pixmap(self, model: TextureModel) -> QPixmap:
        index = self.selected_index()

        if not index.isValid():
            return QPixmap()

        selected = self._view.selectionModel().selectedIndexes()

        return stack_pixmap(grid_cards(model, stack_textures(model, index, selected)))

    def context_action(self, at: QPoint) -> None:
        model = self._view.model()

        if not isinstance(model, TextureModel):
            return

        selection = self._view.selectionModel()
        index = self._view.indexAt(at)

        if index.isValid() and not selection.isSelected(index):
            selection.setCurrentIndex(index, QItemSelectionModel.SelectionFlag.ClearAndSelect)

        self.show_context_menu(self._view, self._view.viewport().mapToGlobal(at))

    def inspector_context_action(self, at: QPoint) -> None:
        self.show_context_menu(self._inspector, at)

    def show_context_menu(self, parent: QWidget, at: QPoint) -> None:
        if not isinstance(self._view.model(), TextureModel):
            return

        selected = len(self._view.selectionModel().selectedIndexes())

        if not selected:
            return

        menu = self._actions.context_menu(
            parent,
            selected,
            idle=self._job is None,
            previewing=self.holds_preview(),
        )

        menu.exec(at)
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
        self._job = ExportRun(self, textures, out_dir, format, reads, done=self.exported)

        # a refresh reads the cache's files in again and puts the new ones in
        # place of the ones the export is halfway through reading
        self._actions.reload.setEnabled(False)
        self.sync_export()

        self._job.start()

    def exported(self, summary: str) -> None:
        self._job = None

        self._actions.reload.setEnabled(self._cache is not None)
        self.sync_export()

        self._status.flash(summary)

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

    def simple_action(self, shown: bool) -> None:
        model = self._view.model()

        if not isinstance(model, TextureModel):
            return

        place = self._view.place()

        if not model.set_simple_hidden(not shown):
            # the scan that says which textures hold a picture is still out, and
            # what was asked for here is applied the moment it lands
            self._status.flash("Please wait...")
            return

        self.sync_empty()
        self.sync_export()

        self._status.set_summary(self.summary())

        if self.ranking():
            self.scroll_ranked()
        else:
            # the rows go from all through the grid rather than off one end of
            # it, so where the view already was is the nearest thing to where
            # it should be left
            self._view.pin_to(place)

    def sync_simple(self) -> None:
        self._actions.simple.setEnabled(self._cache is not None)

    def showing_simple(self) -> bool:
        return self._actions.simple.isChecked()

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

        if not isinstance(model, TextureModel):
            return self._summary

        if model.narrowed:
            return (
                f"Showing {format_count(model.rowCount())} of {format_count(model.total())} textures matching filters"
            )

        return self.grid_summary()

    def grid_summary(self) -> str:
        model = self._view.model()

        if self._cache is None or not isinstance(model, TextureModel):
            return self._summary

        shown = model.rowCount()

        summary = f"Showing {format_count(shown)} textures of {format_count(len(self._cache))} entries in cache"

        # both counts are of the rows the grid ended up with rather than of the
        # cache, since an entry left out of it is neither shown nor news
        unfinished = (
            sum(1 for row in range(shown) if not model.texture(row).whole()) if self.showing_incomplete() else 0
        )

        if unfinished:
            summary += f", {format_count(unfinished)} incomplete"

        hidden = model.hidden()

        if hidden:
            summary += f", {format_count(hidden)} simple textures hidden"

        return summary

    def sync_empty(self) -> None:
        model = self._view.model()

        if not isinstance(model, TextureModel) or not (model.narrowed or model.hidden()):
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
        # one window's menu says whether the shared window is up, so the rest of
        # them are put where it says without being asked to do this again
        MainWindow.set_preview_shown(shown)

        self.sync_preview()

    def toggle_preview_action(self) -> None:
        if self.holds_preview():
            self._actions.preview.setChecked(False)
            return

        if not self._view.has_selection():
            return

        self.open_preview_action()

    def open_preview_action(self) -> None:
        self._actions.preview.setChecked(True)

        MainWindow.follow_preview(self)

        preview = MainWindow._preview_host.window

        if preview is not None:
            preview.present()

    def wants_preview(self) -> bool:
        return self._cache is not None and self._actions.preview.isChecked()

    def holds_preview(self) -> bool:
        return self.wants_preview() and MainWindow._preview_host.followed_by(self)

    def preview_menu_entry(self) -> QAction:
        """The tick this window carries for the preview, which the host keeps in step"""

        return self._actions.preview

    def sync_preview(self) -> None:
        self._actions.preview.setEnabled(self._cache is not None)

        MainWindow.follow_preview(self)

    def preview_ready_action(self, _uuid: str) -> None:
        self.fill_preview()

    def fill_preview(self) -> None:
        """Show whatever is selected in the preview window, if it is following this one"""

        model = self._view.model()
        preview = MainWindow._preview_host.window

        if not MainWindow._preview_host.followed_by(self) or preview is None or not preview.isVisible():
            return

        if not isinstance(model, TextureModel):
            return

        index = self.selected_index()

        if not index.isValid():
            preview.clear()
            return

        texture = model.texture(index.row())

        # asking marks this as the one texture the window is on, so a decode
        # the selection has already been walked past is dropped when it lands.
        # the grid and the pane read smaller and sooner, and whichever of them
        # has already been through this texture stands in until it lands
        preview.show_texture(texture, model.preview(texture), model.standing(texture))

    def selection_action(self, *_: object) -> None:
        self.sync_pane_tone()
        self.fill_inspector()
        self.fill_preview()
        self.sync_export()
        self.sync_selection()

    def sync_pane_tone(self) -> None:
        model = self._view.model()
        index = self.selected_index()

        standing = model.texture(index.row()).uuid if isinstance(model, TextureModel) and index.isValid() else ""

        # growing a selection, or walking the current index around inside one, is
        # still the same texture in the panes
        if standing == self._standing:
            return

        self._standing = standing

        reset_pane_tone()

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

            # with nothing shown there is nothing for the automatic checkerboard to
            # have been measured against
            set_picked_lightness(None)
            return

        selected = self._view.selectionModel().selectedIndexes()

        self._inspector.show_texture(
            model.texture(index.row()),
            len(selected),
            sum(model.texture(other.row()).image_size for other in selected),
        )

        self._stack = stack_textures(model, index, selected)
        self._settle.start()

        self.paint_inspector()

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

        # a hidden pane is repainted with whatever the last visible one was left on,
        # which is not what the preview beside it is showing
        if cards and self._inspector.isVisible():
            # the card on top is the one the pane is really about, so the automatic
            # checkerboard behind that one is where a click in the pane carries on from
            set_picked_lightness(pixmap_lightness(cards[-1][1]))

        self._inspector.set_sidebar(
            stack_pixmap(cards, self._inspector.sidebar_room()),
            self.shape(model, self._stack[-1]),
            transparent=any(card.hasAlphaChannel() for _, card in cards),
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

    def prefetch_action(self) -> None:
        model = self._view.model()

        if isinstance(model, TextureModel):
            prefetch(self._view, model)

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

    def open_cache(self, cache_dir: Path, *, replace: bool = False) -> None:
        try:
            cache = TextureCache(cache_dir)
        except (FileNotFoundError, TextureCacheError) as e:
            self._status.rest(f"Could not open {cache_dir}: {e}")
            return

        RecentCaches.shared().remember(cache.cache_dir)

        if replace or self._cache is None:
            self.set_cache(cache)
        else:
            self.new_window(cache)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        self.dragMoveEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        urls = event.mimeData().urls()

        if self._job is not None or len(urls) != 1:
            return

        cache_dir = Path(urls[0].toLocalFile())

        if not cache_dir.is_dir():
            return

        actions = event.possibleActions()

        if actions & Qt.DropAction.LinkAction:
            event.setDropAction(Qt.DropAction.LinkAction)
        elif actions & Qt.DropAction.CopyAction:
            event.setDropAction(Qt.DropAction.CopyAction)
        else:
            return

        event.accept()

        central = self.centralWidget()

        if central is not None:
            self._zone.offer(f"Drop to open {cache_dir.name}", central.geometry())

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._zone.withdraw()

        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self._zone.withdraw()

        urls = event.mimeData().urls()

        if self._job is not None or len(urls) != 1:
            return

        cache_dir = Path(urls[0].toLocalFile())

        if not cache_dir.is_dir():
            return

        event.accept()

        self.open_cache(cache_dir, replace=True)

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
        self.sync_simple()
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

        model = TextureModel(textures, self._cache, self)
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
        preview = MainWindow._preview_host.window

        if preview is not None and MainWindow._preview_host.followed_by(self):
            preview.clear()

        model.set_simple_hidden(not self.showing_simple())
        model.set_filters(self._filters.colors())

        self.sync_export()

        if not self.ranking():
            self.scroll_to_end()

        self._summary = self.grid_summary()

        self._status.set_summary(note if note else self.summary())

    def about_action(self) -> None:
        if MainWindow._about is None:
            MainWindow._about = AboutDialog()

        MainWindow._about.show()
        MainWindow._about.raise_()
        MainWindow._about.activateWindow()


# the preview follows the windows, and the windows are the class's own list, so
# the host is given a way to ask for them rather than a copy taken here
MainWindow._preview_host = PreviewHost(
    clients=lambda: list(MainWindow._windows),
    closed=MainWindow.preview_closed_action,
)
