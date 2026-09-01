"""The strip of colours the grid is filtered by"""

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from lltexturecache_browser_qt.panes.filters import (
    DEFAULT_COLORS,
    OFF_MARK,
    ON_MARK,
    ColorFilterBar,
    Swatch,
    plus_icon,
)


@pytest.fixture
def bar(app: QApplication) -> ColorFilterBar:
    return ColorFilterBar()


class TestPlusIcon:
    def test_an_icon_is_drawn_at_the_device_ratio(self, app: QApplication) -> None:
        assert not plus_icon(QColor("black"), 2.0).isNull()


class TestSwatch:
    def test_a_swatch_opens_on_the_colour_it_was_given(self, app: QApplication) -> None:
        assert Swatch(QColor("red")).color == QColor("red")

    def test_a_swatch_can_be_recoloured(self, app: QApplication) -> None:
        swatch = Swatch(QColor("red"))
        swatch.set_color(QColor("blue"))

        assert swatch.color == QColor("blue")

    def test_the_tip_names_the_colour_and_says_what_a_click_does(self, app: QApplication) -> None:
        swatch = Swatch(QColor("#c0392b"))

        assert "#C0392B" in swatch.toolTip()
        assert "disable" in swatch.toolTip().lower()

        swatch.setChecked(False)

        assert "enable" in swatch.toolTip().lower()

    def test_a_swatch_can_be_built_already_disabled(self, app: QApplication) -> None:
        assert Swatch(QColor("red"), on=False).isChecked() is False

    def test_the_remove_badge_sits_in_the_top_corner(self, app: QApplication) -> None:
        swatch = Swatch(QColor("red"))
        badge = swatch.badge()

        assert badge.top() == 0
        assert badge.right() == pytest.approx(swatch.width())


class TestDefaults:
    def test_the_strip_opens_on_the_default_colours(self, bar: ColorFilterBar) -> None:
        assert len(bar.state()) == len(DEFAULT_COLORS)

    def test_none_of_the_defaults_is_asked_for_to_begin_with(self, bar: ColorFilterBar) -> None:
        assert bar.colors() == []
        assert bar.asking() is False

    def test_with_nothing_asked_for_the_off_button_is_greyed(self, bar: ColorFilterBar) -> None:
        assert bar._off.isEnabled() is False


class TestAdding:
    def test_an_added_colour_is_asked_for(self, bar: ColorFilterBar) -> None:
        bar.add(QColor("#123456"))

        assert QColor("#123456") in bar.colors()
        assert bar.asking() is True

    def test_adding_a_colour_already_on_the_strip_enables_it_rather_than_repeating_it(
        self, bar: ColorFilterBar
    ) -> None:
        before = len(bar.state())

        bar.add(QColor(DEFAULT_COLORS[0]))
        bar.add(QColor(DEFAULT_COLORS[0]))

        assert len(bar.state()) == before
        assert bar.colors() == [QColor(DEFAULT_COLORS[0])]

    def test_adding_reports_the_new_set(self, bar: ColorFilterBar) -> None:
        seen: list[list[QColor]] = []
        bar.changed.connect(seen.append)

        bar.add(QColor("#123456"))

        assert seen == [[QColor("#123456")]]


class TestRemoving:
    def test_a_removed_swatch_leaves_the_strip(self, bar: ColorFilterBar) -> None:
        bar.add(QColor("#123456"))

        before = len(bar.state())

        bar.remove(bar._swatches[-1])

        assert len(bar.state()) == before - 1
        assert bar.colors() == []

    def test_disabling_reports_the_empty_set_once(self, bar: ColorFilterBar) -> None:
        bar.add(QColor("#123456"))
        bar.add(QColor("#654321"))

        seen: list[list[QColor]] = []
        bar.changed.connect(seen.append)

        bar.disable_action()

        assert seen == [[]]

    def test_disabling_keeps_the_colours_on_the_strip(self, bar: ColorFilterBar) -> None:
        bar.add(QColor("#123456"))

        before = len(bar.state())

        bar.disable_action()

        assert len(bar.state()) == before
        assert bar.asking() is False


class TestSuggestion:
    def test_with_nothing_asked_for_the_picker_opens_on_white(self, bar: ColorFilterBar) -> None:
        assert bar.suggestion() == QColor("white")

    def test_the_picker_opens_on_the_colour_last_asked_for(self, bar: ColorFilterBar) -> None:
        bar.add(QColor("#123456"))
        bar.add(QColor("#654321"))

        assert bar.suggestion() == QColor("#654321")


class TestState:
    def test_state_marks_which_colours_are_asked_for(self, bar: ColorFilterBar) -> None:
        bar.add(QColor("#123456"))

        state = bar.state()

        assert state[-1] == f"{ON_MARK}#123456"
        assert all(entry.startswith(OFF_MARK) for entry in state[:-1])

    def test_a_strip_survives_a_round_trip_through_the_store(self, bar: ColorFilterBar) -> None:
        bar.add(QColor("#123456"))

        stored = bar.state()

        revived = ColorFilterBar()
        revived.revive(stored)

        assert revived.state() == stored
        assert revived.colors() == bar.colors()

    def test_a_strip_of_one_comes_back_from_the_store_as_a_string(self, bar: ColorFilterBar) -> None:
        bar.revive(f"{ON_MARK}#abcdef")

        assert bar.colors() == [QColor("#abcdef")]

    def test_an_empty_store_falls_back_to_the_defaults(self, bar: ColorFilterBar) -> None:
        bar.revive([])

        assert len(bar.state()) == len(DEFAULT_COLORS)
        assert bar.colors() == []

    def test_a_store_of_nothing_usable_falls_back_to_the_defaults(self, bar: ColorFilterBar) -> None:
        bar.revive(["nonsense", 17, None, "+not-a-color"])

        assert len(bar.state()) == len(DEFAULT_COLORS)

    def test_unmarked_entries_are_skipped(self, bar: ColorFilterBar) -> None:
        bar.revive(["#123456", f"{ON_MARK}#abcdef"])

        assert bar.state() == [f"{ON_MARK}#abcdef"]

    def test_a_store_that_is_not_a_list_falls_back_to_the_defaults(self, bar: ColorFilterBar) -> None:
        bar.revive(None)

        assert len(bar.state()) == len(DEFAULT_COLORS)
