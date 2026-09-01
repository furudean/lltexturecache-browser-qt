"""The main window: the pure helpers around it, and the state it keeps"""

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import cast

import pytest
from PySide6.QtCore import QByteArray, QMimeData, QPoint, QPointF, QSettings, Qt, QUrl
from PySide6.QtGui import QDragLeaveEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QApplication
from texture_courier import Texture, TextureCache, TextureCacheError

from lltexturecache_browser_qt.app import window as module
from lltexturecache_browser_qt.app.session import AppSession
from lltexturecache_browser_qt.grid.model import TextureModel
from lltexturecache_browser_qt.cache.recents import RecentCaches
from lltexturecache_browser_qt.grid.selection import row_spans
from lltexturecache_browser_qt.settings import SESSION_KEY, stored_blob, stored_paths
from lltexturecache_browser_qt.app.window import MainWindow
from tests import fakes


@pytest.fixture
def windows(app: QApplication, settings: None, quiet_scan: None) -> Iterator[None]:
    """Leave the app's window list the way each test found it"""

    kept = MainWindow._session

    MainWindow._session = AppSession()

    yield

    for window in list(MainWindow._session):
        if isinstance(window, MainWindow):
            window.close()

    # the preview host outlives any one window, and a test that pointed it at
    # one of these must not leave it pointed at a window that has since gone
    MainWindow._preview_host.follow(None)

    MainWindow._session = kept


class TestStoredBlob:
    def test_a_key_that_was_never_written_reads_back_empty(self, settings: None) -> None:
        assert stored_blob(QSettings(), "neverWritten") == QByteArray()

    def test_a_stored_blob_reads_back(self, settings: None) -> None:
        QSettings().setValue("geometry", QByteArray(b"abc"))

        assert stored_blob(QSettings(), "geometry") == QByteArray(b"abc")

    def test_a_key_holding_something_else_reads_back_empty(self, settings: None) -> None:
        QSettings().setValue("geometry", "not a blob")

        assert stored_blob(QSettings(), "geometry") == QByteArray()


class TestRowSpans:
    @staticmethod
    def model(count: int) -> TextureModel:
        return TextureModel(fakes.textures(count), fakes.cache())

    def test_one_row_is_one_span(self, app: QApplication, quiet_scan: None) -> None:
        built = self.model(5)

        try:
            spans = row_spans(built, [2])

            assert spans.count() == 1
            assert (spans.at(0).top(), spans.at(0).bottom()) == (2, 2)
        finally:
            built.shutdown()

    def test_rows_running_together_are_one_span(self, app: QApplication, quiet_scan: None) -> None:
        built = self.model(8)

        try:
            spans = row_spans(built, [1, 2, 3])

            assert spans.count() == 1
            assert (spans.at(0).top(), spans.at(0).bottom()) == (1, 3)
        finally:
            built.shutdown()

    def test_a_gap_starts_a_new_span(self, app: QApplication, quiet_scan: None) -> None:
        built = self.model(8)

        try:
            spans = row_spans(built, [0, 1, 4, 5])

            assert [(spans.at(at).top(), spans.at(at).bottom()) for at in range(spans.count())] == [(0, 1), (4, 5)]
        finally:
            built.shutdown()

    def test_scattered_rows_are_each_their_own_span(self, app: QApplication, quiet_scan: None) -> None:
        built = self.model(8)

        try:
            assert row_spans(built, [0, 2, 4, 6]).count() == 4
        finally:
            built.shutdown()


class TestSession:
    def test_nothing_stored_restores_nothing(self, settings: None) -> None:
        assert MainWindow.session() == []

    def test_a_stored_session_reads_back(self, settings: None) -> None:
        QSettings().setValue(SESSION_KEY, ["/caches/one", "/caches/two"])

        assert MainWindow.session() == [Path("/caches/one"), Path("/caches/two")]

    def test_a_session_of_one_comes_back_out_of_the_store_as_a_string(self, settings: None) -> None:
        QSettings().setValue(SESSION_KEY, "/caches/only")

        assert MainWindow.session() == [Path("/caches/only")]


class TestWindowList:
    def test_no_windows_are_open_to_begin_with(self, windows: None) -> None:
        assert MainWindow.any_open() is False

    def test_an_open_window_is_listed(self, windows: None) -> None:
        window = MainWindow()

        assert MainWindow.any_open() is True
        assert window in list(MainWindow._session)

    def test_a_closed_window_leaves_the_list(self, windows: None) -> None:
        window = MainWindow()
        window.close()

        assert MainWindow.any_open() is False

    def test_a_window_with_no_cache_saves_nothing_to_the_session(self, windows: None) -> None:
        MainWindow()
        MainWindow.save_session()

        assert MainWindow.session() == []


class TestQuitting:
    def test_quitting_saves_the_session_once(self, windows: None) -> None:
        MainWindow.quitting()

        assert MainWindow._session.quitting is True

    def test_quitting_twice_changes_nothing(self, windows: None) -> None:
        window = MainWindow()
        MainWindow.quitting()

        # a window closing on the way out would otherwise empty the session
        # that was just written
        MainWindow._session.remove(window)
        MainWindow.quitting()

        assert MainWindow._session.quitting is True


class TestStoredPaths:
    def test_a_key_that_was_never_written_reads_back_empty(self, settings: None) -> None:
        assert stored_paths(QSettings(), "neverWritten") == []

    def test_a_stored_list_reads_back(self, settings: None) -> None:
        QSettings().setValue("caches", ["/caches/one", "/caches/two"])

        assert stored_paths(QSettings(), "caches") == [Path("/caches/one"), Path("/caches/two")]

    def test_a_list_of_one_comes_back_out_of_the_store_as_a_string(self, settings: None) -> None:
        QSettings().setValue("caches", "/caches/only")

        assert stored_paths(QSettings(), "caches") == [Path("/caches/only")]


class TestPreviewWindow:
    def test_the_preview_belongs_to_the_app_rather_than_a_window(self, windows: None) -> None:
        host = MainWindow._preview_host

        try:
            assert MainWindow.shared_preview() is MainWindow.shared_preview()
        finally:
            if host.window is not None:
                host.window.close()


class FakeCacheDir:
    """A texture cache the window can be opened on

    A real TextureCache wants a viewer's cache directory on disk. The window
    only iterates it, counts it, and names it, so this stands in.
    """

    def __init__(self, cache_dir: Path, textures: list[Texture]) -> None:
        self.cache_dir = cache_dir
        self._textures = textures

    def __iter__(self) -> Iterator[Texture]:
        return iter(self._textures)

    def __len__(self) -> int:
        return len(self._textures)


@pytest.fixture
def opening(monkeypatch: pytest.MonkeyPatch) -> Callable[[int], None]:
    """Make TextureCache(path) open as a cache of the given size"""

    def holds(count: int) -> None:
        monkeypatch.setattr(
            module,
            "TextureCache",
            lambda cache_dir: FakeCacheDir(Path(cache_dir), fakes.textures(count)),
        )

    return holds


@pytest.fixture
def window(windows: None, opening: Callable[[int], None]) -> Iterator[MainWindow]:
    RecentCaches._shared = None

    built = MainWindow()

    yield built

    built.close()

    # the shared list is left standing: the windows fixture around this one
    # still has windows to close, and each of them disconnects from it


class TestOpenCache:
    def test_an_empty_window_takes_the_cache_it_is_given(
        self, window: MainWindow, opening: Callable[[int], None], tmp_path: Path
    ) -> None:
        opening(4)

        window.open_cache(tmp_path)

        assert window.opened_cache() == tmp_path
        assert window._model is not None
        assert window._model.rowCount() == 4

    def test_opening_a_cache_titles_the_window_for_it(
        self, window: MainWindow, opening: Callable[[int], None], tmp_path: Path
    ) -> None:
        opening(2)

        window.open_cache(tmp_path)

        assert str(tmp_path) in window.windowTitle()

    def test_an_opened_cache_is_remembered(
        self, window: MainWindow, opening: Callable[[int], None], tmp_path: Path
    ) -> None:
        opening(2)

        window.open_cache(tmp_path)

        assert RecentCaches.shared().paths() == [tmp_path]

    def test_a_cache_that_is_not_there_says_so_rather_than_raising(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        def missing(cache_dir: Path) -> object:
            raise FileNotFoundError("no such directory")

        monkeypatch.setattr(module, "TextureCache", missing)

        window.open_cache(tmp_path)

        assert window.opened_cache() is None
        assert "Could not open" in window._status._bar.currentMessage()

    def test_a_directory_that_is_not_a_cache_says_so(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        def refused(cache_dir: Path) -> object:
            raise TextureCacheError("not a texture cache")

        monkeypatch.setattr(module, "TextureCache", refused)

        window.open_cache(tmp_path)

        assert window.opened_cache() is None
        assert "not a texture cache" in window._status._bar.currentMessage()

    def test_a_second_cache_opens_beside_the_first(
        self, window: MainWindow, opening: Callable[[int], None], tmp_path: Path
    ) -> None:
        opening(2)

        window.open_cache(tmp_path / "one")
        window.open_cache(tmp_path / "two")

        assert window.opened_cache() == tmp_path / "one"
        assert len(MainWindow._session) == 2

    def test_a_replacing_open_takes_over_the_window(
        self, window: MainWindow, opening: Callable[[int], None], tmp_path: Path
    ) -> None:
        opening(2)

        window.open_cache(tmp_path / "one")
        window.open_cache(tmp_path / "two", replace=True)

        assert window.opened_cache() == tmp_path / "two"
        assert len(MainWindow._session) == 1


class TestSetCache:
    def test_opening_a_cache_turns_the_menus_on(
        self, window: MainWindow, opening: Callable[[int], None], tmp_path: Path
    ) -> None:
        assert window._actions.reload.isEnabled() is False

        opening(2)
        window.open_cache(tmp_path)

        assert window._actions.reload.isEnabled() is True
        assert window._actions.inspector.isEnabled() is True
        assert window._actions.simple.isEnabled() is True

    def test_an_open_cache_is_saved_to_the_session(
        self, window: MainWindow, opening: Callable[[int], None], tmp_path: Path
    ) -> None:
        opening(2)
        window.open_cache(tmp_path)

        assert MainWindow.session() == [tmp_path]

    def test_the_status_bar_reports_what_the_grid_holds(
        self, window: MainWindow, opening: Callable[[int], None], tmp_path: Path
    ) -> None:
        opening(3)
        window.open_cache(tmp_path)

        assert "3 textures" in window._status._bar.currentMessage()


class TestPopulateGrid:
    def test_a_window_with_no_cache_populates_nothing(self, window: MainWindow) -> None:
        window.populate_grid()

        assert window._model is None

    def test_incomplete_entries_are_left_out_by_default(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        textures = [*fakes.textures(3), fakes.texture(uuid="half", complete=False)]

        monkeypatch.setattr(module, "TextureCache", lambda d: FakeCacheDir(Path(d), textures))

        window.open_cache(tmp_path)

        assert window._model is not None
        assert window._model.rowCount() == 3

    def test_showing_incomplete_entries_lets_them_in(
        self, window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        textures = [*fakes.textures(3), fakes.texture(uuid="half", complete=False)]

        monkeypatch.setattr(module, "TextureCache", lambda d: FakeCacheDir(Path(d), textures))

        window._actions.incomplete.setChecked(True)
        window.open_cache(tmp_path)

        assert window._model is not None
        assert window._model.rowCount() == 4

    def test_repopulating_retires_the_model_it_replaces(
        self, window: MainWindow, opening: Callable[[int], None], tmp_path: Path
    ) -> None:
        opening(3)
        window.open_cache(tmp_path)

        first = window._model

        window.populate_grid()

        assert window._model is not first
        assert window._view.model() is window._model


# a Qt event does not take ownership of the mime data it carries, so the
# payload of every event a test builds is kept alive here for the run
_payloads: list[QMimeData] = []


def urls_of(*paths: Path) -> QMimeData:
    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])

    _payloads.append(data)

    return data


class TestDropping:
    @staticmethod
    def drop_of(*paths: Path) -> QDropEvent:
        return QDropEvent(
            QPointF(1, 1),
            Qt.DropAction.CopyAction,
            urls_of(*paths),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

    def test_a_dropped_directory_is_opened(
        self, window: MainWindow, opening: Callable[[int], None], tmp_path: Path
    ) -> None:
        opening(2)

        window.dropEvent(self.drop_of(tmp_path))

        assert window.opened_cache() == tmp_path

    def test_a_dropped_file_is_refused(
        self, window: MainWindow, opening: Callable[[int], None], tmp_path: Path
    ) -> None:
        opening(2)

        dropped = tmp_path / "texture.jp2"
        dropped.write_bytes(b"")

        window.dropEvent(self.drop_of(dropped))

        assert window.opened_cache() is None

    def test_dropping_two_directories_is_refused(
        self, window: MainWindow, opening: Callable[[int], None], tmp_path: Path
    ) -> None:
        opening(2)

        first = tmp_path / "one"
        second = tmp_path / "two"

        first.mkdir()
        second.mkdir()

        window.dropEvent(self.drop_of(first, second))

        assert window.opened_cache() is None

    def test_a_directory_dragged_over_offers_to_open_it(self, window: MainWindow, tmp_path: Path) -> None:
        window.dragMoveEvent(self.drag_of(tmp_path))

        assert window._zone.isHidden() is False
        assert tmp_path.name in window._zone._message

    def test_a_file_dragged_over_offers_nothing(self, window: MainWindow, tmp_path: Path) -> None:
        dragged = tmp_path / "texture.jp2"
        dragged.write_bytes(b"")

        window.dragMoveEvent(self.drag_of(dragged))

        assert window._zone.isHidden() is True

    def test_dragging_away_takes_the_offer_down(self, window: MainWindow, tmp_path: Path) -> None:
        window.dragMoveEvent(self.drag_of(tmp_path))
        window.dragLeaveEvent(QDragLeaveEvent())

        assert window._zone.isHidden() is True

    @staticmethod
    def drag_of(path: Path) -> QDragMoveEvent:
        return QDragMoveEvent(
            QPoint(1, 1),
            Qt.DropAction.CopyAction | Qt.DropAction.LinkAction,
            urls_of(path),
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )


class TestNewWindow:
    def test_a_new_window_opens_beside_this_one(self, window: MainWindow) -> None:
        opened = window.new_window()

        try:
            assert opened is not window
            assert len(MainWindow._session) == 2
        finally:
            opened.close()

    def test_a_new_window_can_be_handed_a_cache(
        self, window: MainWindow, opening: Callable[[int], None], tmp_path: Path
    ) -> None:
        opening(2)

        opened = window.new_window(cast("TextureCache", FakeCacheDir(tmp_path, fakes.textures(2))))

        try:
            assert opened.opened_cache() == tmp_path
        finally:
            opened.close()
