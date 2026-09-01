from pathlib import Path
from threading import Lock
from typing import ClassVar

from PySide6.QtCore import (
    QDir,
    QEvent,
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
from lltexturecache_browser_qt.app.about import AboutDialog
from lltexturecache_browser_qt.app.actions import WindowActions
from lltexturecache_browser_qt.app.drag import DRAG_LIMIT, drag_data, staged
from lltexturecache_browser_qt.app.exporting import ExportRun, ask_for_directory
from lltexturecache_browser_qt.app.session import AppSession
from lltexturecache_browser_qt.cache.export import Format
from lltexturecache_browser_qt.cache.recents import RecentCaches
from lltexturecache_browser_qt.cache.suggested import paths as suggested_paths
from lltexturecache_browser_qt.grid.cards import grid_cards, stack_textures
from lltexturecache_browser_qt.grid.cells import CELL_PADDING, CellDelegate, TextureGrid
from lltexturecache_browser_qt.grid.model import TextureModel, sidebar_key
from lltexturecache_browser_qt.grid.prefetch import prefetch
from lltexturecache_browser_qt.grid.selection import KeptSelection
from lltexturecache_browser_qt.grid.summary import empty_message, narrowed_summary
from lltexturecache_browser_qt.grid.summary import grid_summary as summary_of
from lltexturecache_browser_qt.panes.dropzone import DropZone
from lltexturecache_browser_qt.panes.filters import ColorFilterBar
from lltexturecache_browser_qt.panes.inspector import INSPECTOR_WIDTH, InspectorPane
from lltexturecache_browser_qt.panes.preview import PreviewWindow
from lltexturecache_browser_qt.panes.previewing import PreviewHost
from lltexturecache_browser_qt.panes.sidebar import paint as paint_pane
from lltexturecache_browser_qt.panes.status import WindowStatus
from lltexturecache_browser_qt.settings import (
    FILTERS_KEY,
    GEOMETRY_KEY,
    SPLITTER_KEY,
    stored_blob,
)
from lltexturecache_browser_qt.view.checkerboard import (
    CheckerboardChanges,
    reset_pane_tone,
    set_picked_lightness,
    sync_checkerboard,
)
from lltexturecache_browser_qt.view.formatting import format_count
from lltexturecache_browser_qt.view.images import THUMBNAIL_SIZE
from lltexturecache_browser_qt.view.stack import stack_pixmap

NEW_WINDOW_OFFSET = QPoint(32, 32)


class MainWindow(QMainWindow):
    _about: ClassVar["AboutDialog | None"] = None

    # the windows the app has open and the preview they share both belong to
    # the app rather than to any one window, so they are kept beside the
    # windows rather than inside one of them
    _session: ClassVar[AppSession] = AppSession()
    _preview_host: ClassVar[PreviewHost]

    def __init__(self) -> None:
        super().__init__()

        MainWindow._session.add(self)

        settings = QSettings()

        self.setWindowTitle(APP_DISPLAY_NAME)

        # a directory dropped anywhere on the window is opened in it
        self.setAcceptDrops(True)

        # default window size
        self.resize(800, 600)

        self.restoreGeometry(stored_blob(settings, GEOMETRY_KEY))

        self._cache: TextureCache | None = None

        # the model the grid is on. the view hands back a QAbstractItemModel,
        # which every caller would otherwise have to narrow again
        self._model: TextureModel | None = None
        self._stack: list[Texture] = []
        self._job: ExportRun | None = None

        self._summary = ""

        # what was selected before the model was last reset, put back once the
        # rows it was picked out of have landed again
        self._kept = KeptSelection()

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

    def opened_cache(self) -> Path | None:
        """The cache this window is showing, which is what the session saves"""

        return self._cache.cache_dir if self._cache is not None else None

    @classmethod
    def session(cls) -> list[Path]:
        return cls._session.stored()

    @classmethod
    def save_session(cls) -> None:
        cls._session.save()

    @classmethod
    def any_open(cls) -> bool:
        return cls._session.any_open()

    @classmethod
    def quitting(cls) -> None:
        cls._session.quit()

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

        model = self._model

        if model is not None:
            model.shutdown()

        MainWindow._session.remove(self)

        # the preview is left with whichever window is still open to take it
        if MainWindow._preview_host.release(self):
            MainWindow.follow_preview()

        if not MainWindow._session.quitting:
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

        model = self._model

        if model is None or not model.restyle():
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
        model = self._model

        if model is None or self._job is not None:
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
        model = self._model

        if model is None:
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
        model = self._model

        if model is None:
            return

        selection = self._view.selectionModel()
        index = self._view.indexAt(at)

        if index.isValid() and not selection.isSelected(index):
            selection.setCurrentIndex(index, QItemSelectionModel.SelectionFlag.ClearAndSelect)

        self.show_context_menu(self._view, self._view.viewport().mapToGlobal(at))

    def inspector_context_action(self, at: QPoint) -> None:
        self.show_context_menu(self._inspector, at)

    def show_context_menu(self, parent: QWidget, at: QPoint) -> None:
        if self._model is None:
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
        model = self._model

        selected = len(self._view.selectionModel().selectedIndexes()) if model is not None else 0
        total = model.rowCount() if model is not None else 0

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
        model = self._model

        if model is None:
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
        model = self._model

        return model is not None and model.narrowed

    def ranking(self) -> bool:
        return bool(self._filters.colors())

    def filter_action(self, colors: list[QColor]) -> None:
        model = self._model

        if model is None:
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
        """What the status bar rests on, which is the filters if any are asking"""

        model = self._model

        if model is not None and model.narrowed:
            return narrowed_summary(model)

        return self.grid_summary()

    def grid_summary(self) -> str:
        """What the grid holds out of the cache, whatever is being asked of it"""

        model = self._model

        if self._cache is None or model is None:
            return self._summary

        return summary_of(model, len(self._cache), counting_incomplete=self.showing_incomplete())

    def sync_empty(self) -> None:
        model = self._model

        self._view.set_message(empty_message(model))

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
        model = self._model

        if model is None:
            return

        current = self.selected_index()

        self._kept = KeptSelection.taken(
            model,
            [index.row() for index in self._view.selectionModel().selectedIndexes()],
            current.row() if current.isValid() else None,
        )

    def restore_selection(self) -> None:
        model = self._model

        if model is None:
            return

        kept, self._kept = self._kept, KeptSelection()

        kept.restore(model, self._view.selectionModel())

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

        model = self._model
        preview = MainWindow._preview_host.window

        if not MainWindow._preview_host.followed_by(self) or preview is None or not preview.isVisible():
            return

        if model is None:
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
        model = self._model
        index = self.selected_index()

        standing = model.texture(index.row()).uuid if model is not None and index.isValid() else ""

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
        model = self._model

        if model is None:
            return

        for texture in self._stack:
            model.full(texture)

        self.paint_inspector()

    def fill_inspector(self) -> None:
        model = self._model

        if not self._inspector.isVisible() or model is None:
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
        model = self._model

        if model is not None:
            paint_pane(self._inspector, model, self._stack)

    def selected_index(self) -> QModelIndex:
        selection = self._view.selectionModel()
        current = self._view.currentIndex()

        if current.isValid() and selection.isSelected(current):
            return current

        selected = selection.selectedIndexes()

        return selected[-1] if selected else QModelIndex()

    def prefetch_action(self) -> None:
        model = self._model

        if model is not None:
            prefetch(self._view, model)

    def select_texture(self, uuid: str) -> None:
        model = self._model

        if model is None:
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
        model = self._model

        if model is None:
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

        self._model = model

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
    clients=lambda: [window for window in MainWindow._session if isinstance(window, MainWindow)],
    closed=MainWindow.preview_closed_action,
)
