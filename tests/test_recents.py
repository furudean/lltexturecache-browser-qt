"""The list of caches the app offers to reopen"""

from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from lltexturecache_browser_qt.recents import RECENT_KEY, RECENT_LIMIT, RecentCaches


class TestRemembering:
    def test_a_fresh_list_is_empty(self, settings: None) -> None:
        assert RecentCaches().paths() == []

    def test_an_opened_cache_is_remembered(self, settings: None) -> None:
        recents = RecentCaches()
        recents.remember(Path("/caches/one"))

        assert recents.paths() == [Path("/caches/one")]

    def test_the_newest_cache_comes_first(self, settings: None) -> None:
        recents = RecentCaches()
        recents.remember(Path("/caches/one"))
        recents.remember(Path("/caches/two"))

        assert recents.paths() == [Path("/caches/two"), Path("/caches/one")]

    def test_reopening_a_cache_moves_it_back_to_the_front(self, settings: None) -> None:
        recents = RecentCaches()

        for name in ("one", "two", "three"):
            recents.remember(Path(f"/caches/{name}"))

        recents.remember(Path("/caches/one"))

        assert recents.paths()[0] == Path("/caches/one")

    def test_a_cache_is_never_listed_twice(self, settings: None) -> None:
        recents = RecentCaches()
        recents.remember(Path("/caches/one"))
        recents.remember(Path("/caches/one"))

        assert recents.paths() == [Path("/caches/one")]

    def test_the_list_stops_at_the_limit(self, settings: None) -> None:
        recents = RecentCaches()

        for index in range(RECENT_LIMIT + 5):
            recents.remember(Path(f"/caches/{index}"))

        assert len(recents.paths()) == RECENT_LIMIT

    def test_the_oldest_falls_off_the_end(self, settings: None) -> None:
        recents = RecentCaches()

        for index in range(RECENT_LIMIT + 1):
            recents.remember(Path(f"/caches/{index}"))

        assert Path("/caches/0") not in recents.paths()

    def test_the_list_handed_out_is_a_copy(self, settings: None) -> None:
        recents = RecentCaches()
        recents.remember(Path("/caches/one"))

        recents.paths().clear()

        assert recents.paths() == [Path("/caches/one")]


class TestClearing:
    def test_clearing_empties_the_list(self, settings: None) -> None:
        recents = RecentCaches()
        recents.remember(Path("/caches/one"))
        recents.clear()

        assert recents.paths() == []

    def test_clearing_is_written_through_to_the_store(self, settings: None) -> None:
        recents = RecentCaches()
        recents.remember(Path("/caches/one"))
        recents.clear()

        assert RecentCaches().paths() == []


class TestStore:
    def test_the_list_survives_a_restart(self, settings: None) -> None:
        recents = RecentCaches()
        recents.remember(Path("/caches/one"))
        recents.remember(Path("/caches/two"))

        assert RecentCaches().paths() == recents.paths()

    def test_a_list_of_one_comes_back_out_of_the_store_as_a_string(self, settings: None) -> None:
        QSettings().setValue(RECENT_KEY, "/caches/only")

        assert RecentCaches().paths() == [Path("/caches/only")]

    def test_an_unwritten_key_reads_as_an_empty_list(self, settings: None) -> None:
        assert RecentCaches().load() == []


class TestSignals:
    def test_remembering_announces_the_change(self, settings: None) -> None:
        seen: list[None] = []

        recents = RecentCaches()
        recents.changed.connect(lambda: seen.append(None))
        recents.remember(Path("/caches/one"))

        assert len(seen) == 1

    def test_clearing_announces_the_change(self, settings: None) -> None:
        seen: list[None] = []

        recents = RecentCaches()
        recents.changed.connect(lambda: seen.append(None))
        recents.clear()

        assert len(seen) == 1


class TestShared:
    def test_everything_asking_for_the_shared_list_gets_the_one_list(self, app: QApplication, settings: None) -> None:
        assert RecentCaches.shared() is RecentCaches.shared()
