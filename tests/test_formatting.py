"""Numbers, sizes and times as the window shows them"""

from datetime import UTC, datetime

from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QApplication

from lltexturecache_browser_qt.formatting import format_count, format_size, format_time


class TestFormatCount:
    def test_a_small_count_is_written_out_plainly(self, app: QApplication) -> None:
        assert format_count(7) == QLocale().toString(7)

    def test_a_large_count_is_grouped(self, app: QApplication) -> None:
        # whichever separator the locale uses, a million is not seven bare digits
        assert format_count(1_000_000) != "1000000"

    def test_zero_is_written_out(self, app: QApplication) -> None:
        assert format_count(0) == QLocale().toString(0)


class TestFormatSize:
    def test_a_size_carries_a_unit(self, app: QApplication) -> None:
        assert any(character.isalpha() for character in format_size(1024))

    def test_a_size_is_written_in_the_largest_unit_that_fits(self, app: QApplication) -> None:
        assert "1.0" in format_size(1024 * 1024)

    def test_nothing_is_still_a_size(self, app: QApplication) -> None:
        assert format_size(0)


class TestFormatTime:
    def test_a_time_is_written_out(self, app: QApplication, moment: datetime) -> None:
        assert format_time(moment)

    def test_two_different_times_read_differently(self, app: QApplication, moment: datetime) -> None:
        later = datetime(2025, 11, 30, 9, 15, 0, tzinfo=UTC)

        assert format_time(moment) != format_time(later)

    def test_the_epoch_is_written_out_rather_than_refused(self, app: QApplication) -> None:
        assert format_time(datetime.fromtimestamp(0, tz=UTC))
