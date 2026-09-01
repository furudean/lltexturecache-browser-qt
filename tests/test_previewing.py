"""Which window the app's one preview is following"""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication

from lltexturecache_browser_qt.previewing import PREVIEW_GEOMETRY_KEY, PreviewClient, PreviewHost


class FakeWindow:
    """Stands in for a main window, which brings a cache and a grid with it"""

    def __init__(self, *, wanting: bool = True) -> None:
        self.wanting = wanting
        self.fills = 0
        self.entry = QAction("Show Preview")
        self.entry.setCheckable(True)

    def wants_preview(self) -> bool:
        return self.wanting

    def fill_preview(self) -> None:
        self.fills += 1

    def preview_menu_entry(self) -> QAction:
        return self.entry


@pytest.fixture
def open_windows() -> list[PreviewClient]:
    return []


@pytest.fixture
def host(app: QApplication, settings: None, open_windows: list[PreviewClient]) -> Iterator[PreviewHost]:
    closings: list[None] = []

    built = PreviewHost(clients=lambda: list(open_windows), closed=lambda: closings.append(None))

    yield built

    if built.window is not None:
        built.window.close()


class TestSharedWindow:
    def test_no_preview_is_built_until_one_is_asked_for(self, host: PreviewHost) -> None:
        assert host.window is None

    def test_everything_asking_gets_the_one_window(self, host: PreviewHost) -> None:
        assert host.shared() is host.shared()
        assert host.window is host.shared()

    def test_the_geometry_of_a_window_never_opened_is_not_saved(self, host: PreviewHost) -> None:
        host.save_geometry(QSettings())

        assert QSettings().value(PREVIEW_GEOMETRY_KEY) is None

    def test_the_geometry_of_an_open_window_is_saved(self, host: PreviewHost) -> None:
        host.shared()
        host.save_geometry(QSettings())

        assert QSettings().value(PREVIEW_GEOMETRY_KEY) is not None


class TestFollowing:
    def test_nothing_is_followed_to_begin_with(self, host: PreviewHost) -> None:
        assert host.followed_by(FakeWindow()) is False

    def test_a_window_that_wants_the_preview_gets_it(
        self, host: PreviewHost, open_windows: list[PreviewClient]
    ) -> None:
        window = FakeWindow()
        open_windows.append(window)

        host.follow(window)

        assert host.followed_by(window) is True
        assert window.fills == 1

    def test_a_window_that_does_not_want_it_is_passed_over(
        self, host: PreviewHost, open_windows: list[PreviewClient]
    ) -> None:
        wanting = FakeWindow()
        idle = FakeWindow(wanting=False)
        open_windows.extend([idle, wanting])

        host.follow(idle)

        assert host.followed_by(wanting) is True

    def test_with_nobody_asking_the_preview_goes_down(self, host: PreviewHost) -> None:
        host.shared().show()
        host.follow(None)

        assert host.window is not None
        assert host.window.isVisible() is False

    def test_the_window_the_preview_is_on_giving_it_up_hands_it_on(
        self, host: PreviewHost, open_windows: list[PreviewClient]
    ) -> None:
        holding = FakeWindow()
        other = FakeWindow()
        open_windows.extend([holding, other])

        host.follow(holding)

        holding.wanting = False

        host.follow(holding)

        assert host.followed_by(other) is True

    def test_a_window_asking_while_another_holds_it_leaves_it_alone(
        self, host: PreviewHost, open_windows: list[PreviewClient]
    ) -> None:
        holding = FakeWindow()
        asking = FakeWindow(wanting=False)
        open_windows.extend([holding, asking])

        host.follow(holding)
        host.follow(asking)

        assert host.followed_by(holding) is True


class TestRelease:
    def test_a_window_that_never_held_it_releases_nothing(self, host: PreviewHost) -> None:
        assert host.release(FakeWindow()) is False

    def test_the_window_holding_it_lets_it_go(self, host: PreviewHost, open_windows: list[PreviewClient]) -> None:
        window = FakeWindow()
        open_windows.append(window)

        host.follow(window)

        assert host.release(window) is True
        assert host.followed_by(window) is False


class TestTicks:
    def test_every_window_is_ticked(self, host: PreviewHost, open_windows: list[PreviewClient]) -> None:
        windows = [FakeWindow(), FakeWindow()]
        open_windows.extend(windows)

        host.sync_ticks(shown=True)

        assert all(window.entry.isChecked() for window in windows)

    def test_a_tick_is_moved_without_being_clicked(self, host: PreviewHost, open_windows: list[PreviewClient]) -> None:
        window = FakeWindow()
        open_windows.append(window)

        asked: list[bool] = []
        window.entry.toggled.connect(asked.append)

        host.sync_ticks(shown=True)

        assert window.entry.isChecked() is True
        assert asked == []

    def test_a_tick_already_where_it_belongs_is_left_alone(
        self, host: PreviewHost, open_windows: list[PreviewClient]
    ) -> None:
        window = FakeWindow()
        window.entry.setChecked(True)
        open_windows.append(window)

        host.sync_ticks(shown=True)

        assert window.entry.isChecked() is True


class TestClosing:
    def test_closing_the_preview_lets_go_of_the_window(
        self, host: PreviewHost, open_windows: list[PreviewClient]
    ) -> None:
        window = FakeWindow()
        open_windows.append(window)

        host.follow(window)
        host.was_closed()

        assert host.followed_by(window) is False
