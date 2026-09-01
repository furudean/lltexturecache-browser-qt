"""The entry point: session restore, shutdown, and the app-wide error report"""

from pathlib import Path
from typing import cast

import pytest
from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication, QMessageBox
from texture_courier import TextureCacheError

from lltexturecache_browser_qt import main as module
from lltexturecache_browser_qt.main import AppWatcher, ErrorReporter, restore, stop


def restored(paths: list[Path]) -> list["FakeWindow"]:
    """What restore opened, as the stand-ins it was really handed"""

    return cast("list[FakeWindow]", restore(paths))


# every window the fake opened during a test, so what did not open can be
# asserted on as readily as what did
opened_windows: list["FakeWindow"] = []


class FakeWindow:
    """Stands in for a MainWindow, which brings the whole app up with it"""

    def __init__(self) -> None:
        self.cache: object | None = None
        self.shown = False
        self.children: list[FakeWindow] = []

        opened_windows.append(self)

    def set_cache(self, cache: object) -> None:
        self.cache = cache

    def show(self) -> None:
        self.shown = True

    def new_window(self, cache: object) -> "FakeWindow":
        window = FakeWindow()
        window.set_cache(cache)

        self.children.append(window)

        return window


@pytest.fixture
def windows(monkeypatch: pytest.MonkeyPatch) -> type[FakeWindow]:
    opened_windows.clear()

    monkeypatch.setattr(module, "MainWindow", FakeWindow)

    return FakeWindow


@pytest.fixture
def caches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every path opens as a cache named for itself"""

    monkeypatch.setattr(module, "TextureCache", lambda path: f"cache:{path}")


class TestRestore:
    def test_an_empty_session_opens_nothing(self, windows: type[FakeWindow], caches: None) -> None:
        assert restored([]) == []

    def test_the_first_cache_opens_in_a_new_window(self, windows: type[FakeWindow], caches: None) -> None:
        opened = restored([Path("/caches/one")])

        assert len(opened) == 1
        assert opened[0].cache == "cache:/caches/one"
        assert opened[0].shown is True

    def test_further_caches_open_beside_the_first(self, windows: type[FakeWindow], caches: None) -> None:
        opened = restored([Path("/caches/one"), Path("/caches/two")])

        assert len(opened) == 2
        assert opened[0].children == [opened[1]]

    def test_a_cache_that_is_gone_is_skipped(self, windows: type[FakeWindow], monkeypatch: pytest.MonkeyPatch) -> None:
        def opening(path: Path) -> str:
            if path.name == "gone":
                raise FileNotFoundError

            return f"cache:{path}"

        monkeypatch.setattr(module, "TextureCache", opening)

        opened = restored([Path("/caches/gone"), Path("/caches/one")])

        assert [window.cache for window in opened] == ["cache:/caches/one"]

    def test_a_cache_that_will_not_open_is_skipped(
        self, windows: type[FakeWindow], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def refusing(path: Path) -> str:
            raise TextureCacheError("not a cache")

        monkeypatch.setattr(module, "TextureCache", refusing)

        assert restored([Path("/caches/one")]) == []

    def test_a_session_of_nothing_openable_opens_no_windows(
        self, windows: type[FakeWindow], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(module, "TextureCache", lambda path: (_ for _ in ()).throw(FileNotFoundError()))

        restored([Path("/caches/one"), Path("/caches/two")])

        assert opened_windows == []


class TestStop:
    def test_stopping_saves_the_session_and_closes_everything(
        self, windows: type[FakeWindow], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        done: list[str] = []

        monkeypatch.setattr(FakeWindow, "quitting", classmethod(lambda cls: done.append("saved")), raising=False)

        class FakeApp:
            def closeAllWindows(self) -> None:
                done.append("closed")

            def quit(self) -> None:
                done.append("quit")

        stop(cast("QApplication", FakeApp()))

        assert done == ["saved", "closed", "quit"]


class TestErrorReporter:
    def test_a_report_reaches_the_dialog(self, app: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[tuple[str, str]] = []

        monkeypatch.setattr(
            QMessageBox,
            "critical",
            staticmethod(lambda parent, title, message: seen.append((title, message))),
        )

        reporter = ErrorReporter()
        reporter.error_occurred.emit("Unhandled Exception", "the traceback")

        assert seen == [("Unhandled Exception", "the traceback")]


class TestAppWatcher:
    def test_a_quit_saves_the_session(
        self, app: QApplication, windows: type[FakeWindow], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        saved: list[None] = []

        monkeypatch.setattr(FakeWindow, "quitting", classmethod(lambda cls: saved.append(None)), raising=False)
        monkeypatch.setattr(FakeWindow, "any_open", classmethod(lambda cls: True), raising=False)

        AppWatcher().eventFilter(QObject(), QEvent(QEvent.Type.Quit))

        assert len(saved) == 1

    def test_an_event_the_app_does_not_watch_is_passed_along(
        self, app: QApplication, windows: type[FakeWindow], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(FakeWindow, "any_open", classmethod(lambda cls: True), raising=False)

        assert AppWatcher().eventFilter(QObject(), QEvent(QEvent.Type.User)) is False
