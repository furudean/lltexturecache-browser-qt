"""The one line a window reports what it is holding on"""

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication, QMainWindow

from lltexturecache_browser_qt.panes.status import WindowStatus


@pytest.fixture
def status(app: QApplication) -> Iterator[WindowStatus]:
    # the bar belongs to the window, and goes with it if nothing here holds on
    window = QMainWindow()

    yield WindowStatus(window)

    window.close()


class TestVisibility:
    def test_an_empty_window_keeps_the_bar_down(self, status: WindowStatus) -> None:
        assert status._bar.isHidden() is True

    def test_a_message_brings_the_bar_up_even_with_nothing_open(self, status: WindowStatus) -> None:
        status.rest("something to say")

        assert status._bar.isHidden() is False

    def test_the_bar_stays_up_once_a_cache_is_open(self, status: WindowStatus) -> None:
        status.set_opened(True)

        assert status._bar.isHidden() is False

    def test_closing_a_cache_puts_the_bar_back_down(self, status: WindowStatus) -> None:
        status.set_opened(True)
        status.set_opened(False)

        assert status._bar.isHidden() is True


class TestMessages:
    def test_a_resting_message_is_shown(self, status: WindowStatus) -> None:
        status.rest("2 textures")

        assert status._bar.currentMessage() == "2 textures"

    def test_a_summary_becomes_the_resting_message(self, status: WindowStatus) -> None:
        status.set_summary("2 textures")

        assert status._bar.currentMessage() == "2 textures"

    def test_a_notice_is_shown_over_the_resting_message(self, status: WindowStatus) -> None:
        status.set_summary("2 textures")
        status.flash("exported 1 texture")

        assert status._bar.currentMessage() == "exported 1 texture"

    def test_the_bar_returns_to_the_resting_message(self, status: WindowStatus) -> None:
        status.set_summary("2 textures")
        status.flash("exported 1 texture")

        status._bar.clearMessage()

        assert status._bar.currentMessage() == "2 textures"


class TestSelection:
    def test_a_selection_is_written_over_the_summary(self, status: WindowStatus) -> None:
        status.set_summary("2 textures")
        status.show_selection(1, 2)

        assert "1" in status._bar.currentMessage()
        assert "2" in status._bar.currentMessage()

    def test_selecting_nothing_falls_back_to_the_summary(self, status: WindowStatus) -> None:
        status.set_summary("2 textures")
        status.show_selection(1, 2)
        status.show_selection(0, 2)

        assert status._bar.currentMessage() == "2 textures"

    def test_a_large_selection_is_written_out_grouped(self, status: WindowStatus) -> None:
        status.show_selection(1000, 20000)

        assert "1000 of 20000" not in status._bar.currentMessage()
