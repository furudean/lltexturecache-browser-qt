"""The menu bar and the signals its entries report through"""

from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMainWindow, QMenu, QMenuBar, QWidget

from lltexturecache_browser_qt.app import actions as module
from lltexturecache_browser_qt.app.actions import (
    FILTERS_KEY,
    INCOMPLETE_KEY,
    INSPECTOR_KEY,
    PREVIEW_KEY,
    SIMPLE_KEY,
    TONES,
    WindowActions,
    export_title,
    fallback_menu,
)
from lltexturecache_browser_qt.cache.export import DEFAULT_FORMAT, FORMATS
from lltexturecache_browser_qt.cache.recents import RecentCaches
from lltexturecache_browser_qt.view.checkerboard import CheckerTone, grid_tone, set_grid_tone


@pytest.fixture
def window(app: QApplication) -> Iterator[QMainWindow]:
    built = QMainWindow()

    yield built

    built.close()


@pytest.fixture
def actions(window: QMainWindow, settings: None) -> Iterator[WindowActions]:
    # the shared lists outlive one set of menus, so each test gets its own
    RecentCaches._shared = None

    built = WindowActions(window)

    yield built

    built.shutdown()

    RecentCaches._shared = None


class TestExportTitle:
    def test_the_whole_cache_is_named_whatever_is_selected(self) -> None:
        assert export_title(0, everything=True) == "Export Full Cache As..."
        assert export_title(9, everything=True) == "Export Full Cache As..."

    def test_one_texture_is_not_counted(self) -> None:
        assert export_title(1, everything=False) == "Export As..."

    def test_a_selection_is_counted(self) -> None:
        assert "4" in export_title(4, everything=False)

    def test_nothing_selected_still_names_the_action(self) -> None:
        assert export_title(0, everything=False) == "Export Selected As..."


class TestMenus:
    def test_the_window_gets_a_menu_bar(self, actions: WindowActions, window: QMainWindow) -> None:
        titles = [menu.title() for menu in window.menuBar().findChildren(QMenu)]

        assert "&File" in titles
        assert "&View" in titles

    def test_every_format_is_offered(self, actions: WindowActions) -> None:
        labels = [entry.text() for entry in actions._selected_export.actions()]

        assert labels == [fmt.label for fmt in FORMATS]

    def test_the_original_format_carries_the_shortcut(self, actions: WindowActions) -> None:
        quick = actions._selected_export.actions()[FORMATS.index(DEFAULT_FORMAT)]

        assert not quick.shortcut().isEmpty()

    def test_only_one_format_carries_a_shortcut(self, actions: WindowActions) -> None:
        carried = [entry for entry in actions._selected_export.actions() if not entry.shortcut().isEmpty()]

        assert len(carried) == 1

    def test_reloading_is_off_until_a_cache_is_open(self, actions: WindowActions) -> None:
        assert actions.reload.isEnabled() is False


class TestExportState:
    def test_with_nothing_open_neither_export_is_offered(self, actions: WindowActions) -> None:
        actions.sync_export(0, 0, idle=True)

        assert actions._selected_export.isEnabled() is False
        assert actions._all_export.isEnabled() is False

    def test_a_selection_offers_the_selected_export(self, actions: WindowActions) -> None:
        actions.sync_export(3, 100, idle=True)

        assert actions._selected_export.isEnabled() is True
        assert "3" in actions._selected_export.title()

    def test_a_cache_with_textures_offers_the_full_export(self, actions: WindowActions) -> None:
        actions.sync_export(0, 100, idle=True)

        assert actions._all_export.isEnabled() is True

    def test_an_export_already_running_holds_the_menus_shut(self, actions: WindowActions) -> None:
        actions.sync_export(3, 100, idle=False)

        assert actions._selected_export.isEnabled() is False
        assert actions._all_export.isEnabled() is False

    def test_picking_a_format_reports_it(self, actions: WindowActions) -> None:
        seen: list[tuple[object, bool]] = []
        actions.exported.connect(lambda fmt, everything: seen.append((fmt, everything)))

        actions._selected_export.actions()[1].trigger()

        assert seen == [(FORMATS[1], False)]

    def test_the_full_export_says_it_is_the_full_export(self, actions: WindowActions) -> None:
        seen: list[tuple[object, bool]] = []
        actions.exported.connect(lambda fmt, everything: seen.append((fmt, everything)))

        actions._all_export.actions()[0].trigger()

        assert seen == [(FORMATS[0], True)]


class TestToggles:
    def test_a_toggle_reports_its_new_state(self, actions: WindowActions) -> None:
        seen: list[bool] = []
        actions.inspected.connect(seen.append)

        actions.inspector.setChecked(not actions.inspector.isChecked())

        assert len(seen) == 1

    def test_a_toggle_is_written_through_to_the_store(self, actions: WindowActions) -> None:
        actions.filters.setChecked(False)

        assert QSettings().value(FILTERS_KEY, type=bool) is False

    def test_every_toggle_has_a_key_of_its_own(self) -> None:
        keys = {PREVIEW_KEY, INSPECTOR_KEY, FILTERS_KEY, INCOMPLETE_KEY, SIMPLE_KEY}

        assert len(keys) == 5

    def test_a_stored_toggle_is_read_back_when_the_menus_are_rebuilt(
        self, actions: WindowActions, window: QMainWindow
    ) -> None:
        actions.simple.setChecked(True)

        rebuilt = WindowActions(QMainWindow())

        try:
            assert rebuilt.simple.isChecked() is True
        finally:
            rebuilt.shutdown()


class TestCheckerboardTones:
    def test_every_tone_is_offered(self, actions: WindowActions) -> None:
        assert set(actions._tones) == set(TONES)

    def test_only_one_tone_is_ticked(self, actions: WindowActions) -> None:
        ticked = [tone for tone, entry in actions._tones.items() if entry.isChecked()]

        assert len(ticked) == 1

    def test_the_ticked_tone_is_the_one_in_use(self, actions: WindowActions) -> None:
        set_grid_tone(CheckerTone.DARK)

        assert actions._tones[CheckerTone.DARK].isChecked() is True

    def test_picking_a_tone_puts_the_grid_on_it(self, actions: WindowActions) -> None:
        actions._tones[CheckerTone.NONE].trigger()

        assert grid_tone() is CheckerTone.NONE


class TestRecents:
    def test_an_empty_list_greys_the_menu(self, actions: WindowActions) -> None:
        assert actions._recents.isEnabled() is False

    def test_a_remembered_cache_is_listed(self, actions: WindowActions) -> None:
        RecentCaches.shared().remember(Path("/caches/one"))

        labels = [entry.text() for entry in actions._recents.actions() if entry.text()]

        assert "/caches/one" in labels
        assert actions._recents.isEnabled() is True

    def test_an_ampersand_in_a_path_is_not_read_as_a_mnemonic(self, actions: WindowActions) -> None:
        RecentCaches.shared().remember(Path("/caches/a&b"))

        labels = [entry.text() for entry in actions._recents.actions()]

        assert "/caches/a&&b" in labels

    def test_picking_a_recent_cache_asks_for_it(self, actions: WindowActions) -> None:
        RecentCaches.shared().remember(Path("/caches/one"))

        seen: list[Path] = []
        actions.reopened.connect(seen.append)

        actions._recents.actions()[0].trigger()

        assert seen == [Path("/caches/one")]

    def test_the_list_can_be_cleared_from_the_menu(self, actions: WindowActions) -> None:
        RecentCaches.shared().remember(Path("/caches/one"))

        actions._recents.actions()[-1].trigger()

        assert RecentCaches.shared().paths() == []

    def test_the_menu_is_rebuilt_rather_than_added_to(self, actions: WindowActions) -> None:
        RecentCaches.shared().remember(Path("/caches/one"))

        before = len(actions._recents.actions())

        RecentCaches.shared().remember(Path("/caches/one"))

        assert len(actions._recents.actions()) == before


class TestSuggested:
    def test_with_nothing_found_the_menu_is_greyed(
        self, actions: WindowActions, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert actions._suggested.isEnabled() is False

    def test_a_found_cache_is_listed(
        self, window: QMainWindow, settings: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(module, "suggested_paths", lambda: [Path("/caches/found")])

        built = WindowActions(window)

        try:
            labels = [entry.text() for entry in built._suggested.actions()]

            assert "/caches/found" in labels
            assert built._suggested.isEnabled() is True
        finally:
            built.shutdown()


class TestContextMenu:
    def test_the_menu_offers_a_preview_and_the_formats(self, actions: WindowActions, holder: QWidget) -> None:
        menu = actions.context_menu(holder, 2, idle=True, previewing=False)
        labels = [entry.text() for entry in menu.actions()]

        assert "Preview" in labels
        assert any("Export" in label for label in labels)

    def test_an_open_preview_is_offered_as_hiding_it(self, actions: WindowActions, holder: QWidget) -> None:
        menu = actions.context_menu(holder, 2, idle=True, previewing=True)

        assert "Hide Preview" in [entry.text() for entry in menu.actions()]

    def test_the_export_entry_is_named_for_the_selection(self, actions: WindowActions, holder: QWidget) -> None:
        menu = actions.context_menu(holder, 5, idle=True, previewing=False)

        assert any("5" in entry.text() for entry in menu.actions())

    def test_an_export_already_running_holds_the_entry_shut(self, actions: WindowActions, holder: QWidget) -> None:
        menu = actions.context_menu(holder, 5, idle=False, previewing=False)
        export = next(entry for entry in menu.actions() if "Export" in entry.text())

        assert export.isEnabled() is False


class TestFallbackMenu:
    """The bar macOS keeps up while the app is running with no window"""

    @staticmethod
    def entries(bar: QMenuBar) -> list[QAction]:
        menus = [cast("QMenu", opener.menu()) for opener in bar.actions()]

        return [entry for menu in menus for entry in menu.actions()]

    def test_the_bar_offers_only_a_new_window(self, app: QApplication) -> None:
        bar = fallback_menu(lambda: None)

        assert [entry.text() for entry in self.entries(bar)] == ["&New Window"]

    def test_the_entry_carries_the_standard_shortcut(self, app: QApplication) -> None:
        bar = fallback_menu(lambda: None)

        assert not self.entries(bar)[0].shortcut().isEmpty()

    def test_picking_it_opens_a_window(self, app: QApplication) -> None:
        opened: list[None] = []

        bar = fallback_menu(lambda: opened.append(None))
        self.entries(bar)[0].trigger()

        assert len(opened) == 1
