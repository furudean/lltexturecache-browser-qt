"""The main window: the pure helpers around it, and the state it keeps"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QByteArray, QSettings
from PySide6.QtWidgets import QApplication

from lltexturecache_browser_qt.model import TextureModel
from lltexturecache_browser_qt.selection import row_spans
from lltexturecache_browser_qt.settings import SESSION_KEY, stored_blob, stored_paths
from lltexturecache_browser_qt.window import MainWindow
from tests import fakes


@pytest.fixture
def windows(app: QApplication, settings: None, quiet_scan: None) -> Iterator[None]:
    """Leave the app's window list the way each test found it"""

    kept = list(MainWindow._windows)
    quitting = MainWindow._quitting

    MainWindow._windows = []
    MainWindow._quitting = False

    yield

    for window in list(MainWindow._windows):
        window.close()

    # the preview host outlives any one window, and a test that pointed it at
    # one of these must not leave it pointed at a window that has since gone
    MainWindow._preview_host.follow(None)

    MainWindow._windows = kept
    MainWindow._quitting = quitting


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
        assert window in MainWindow._windows

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

        assert MainWindow._quitting is True

    def test_quitting_twice_changes_nothing(self, windows: None) -> None:
        MainWindow()
        MainWindow.quitting()

        # a window closing on the way out would otherwise empty the session
        # that was just written
        MainWindow._windows = []
        MainWindow.quitting()

        assert MainWindow._quitting is True


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
