"""Which textures the grid shows, and in what order"""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from lltexturecache_browser_qt.cache.color import ColorIndex, Signature, to_lab
from lltexturecache_browser_qt.grid.narrowing import Narrowing


def scanned(count: int, **rows: object) -> ColorIndex:
    """An index over `count` rows, with the named rows given a colour or flagged flat"""

    index = ColorIndex(count)

    for name, signature in rows.items():
        assert isinstance(signature, Signature)

        index.add(int(name.removeprefix("row")), signature)

    return index


class TestAsking:
    def test_a_fresh_narrowing_asks_for_nothing(self) -> None:
        assert Narrowing().asking is False

    def test_a_colour_is_something_asked_for(self, app: QApplication) -> None:
        assert Narrowing(colors=[QColor("red")]).asking is True

    def test_hiding_simple_textures_is_something_asked_for(self) -> None:
        assert Narrowing(simple_hidden=True).asking is True


class TestNarrowed:
    def test_nothing_asked_for_narrows_nothing(self) -> None:
        assert Narrowing().narrowed is False

    def test_a_colour_with_no_scan_behind_it_narrows_nothing_yet(self, app: QApplication) -> None:
        assert Narrowing(colors=[QColor("red")]).narrowed is False

    def test_a_colour_the_scan_can_answer_narrows_the_grid(self, app: QApplication) -> None:
        narrowing = Narrowing(colors=[QColor("red")], index=ColorIndex(3))

        assert narrowing.narrowed is True

    def test_hiding_simple_textures_is_not_narrowing_by_colour(self) -> None:
        assert Narrowing(simple_hidden=True, index=ColorIndex(3)).narrowed is False


class TestHidden:
    def test_nothing_is_hidden_before_the_scan(self) -> None:
        assert Narrowing(simple_hidden=True).hidden() == 0

    def test_nothing_is_hidden_while_simple_textures_are_shown(self) -> None:
        index = scanned(3, row0=Signature(flat=True))

        assert Narrowing(index=index).hidden() == 0

    def test_the_flat_textures_are_counted_when_they_are_hidden(self) -> None:
        index = scanned(3, row0=Signature(flat=True), row1=Signature(flat=True))

        assert Narrowing(simple_hidden=True, index=index).hidden() == 2


class TestFlatUuids:
    def test_no_scan_means_nothing_is_known_to_be_flat(self) -> None:
        assert Narrowing().flat_uuids(["a", "b", "c"]) == set()

    def test_the_flat_rows_are_named(self) -> None:
        index = scanned(3, row0=Signature(flat=True), row2=Signature(flat=True))

        assert Narrowing(index=index).flat_uuids(["a", "b", "c"]) == {"a", "c"}

    def test_flat_textures_are_named_whether_or_not_they_are_hidden(self) -> None:
        index = scanned(2, row0=Signature(flat=True))

        assert Narrowing(simple_hidden=True, index=index).flat_uuids(["a", "b"]) == {"a"}


class TestKept:
    def test_nothing_asked_for_keeps_every_row_in_order(self) -> None:
        assert Narrowing().kept(4) == [0, 1, 2, 3]

    def test_a_colour_with_no_scan_behind_it_cannot_be_answered(self, app: QApplication) -> None:
        assert Narrowing(colors=[QColor("red")]).kept(4) is None

    def test_hiding_simple_textures_with_no_scan_cannot_be_answered(self) -> None:
        assert Narrowing(simple_hidden=True).kept(4) is None

    def test_hiding_simple_textures_leaves_them_out(self) -> None:
        index = scanned(4, row1=Signature(flat=True))

        assert Narrowing(simple_hidden=True, index=index).kept(4) == [0, 2, 3]

    def test_showing_them_keeps_every_row(self) -> None:
        index = scanned(4, row1=Signature(flat=True))

        assert Narrowing(index=index).kept(4) == [0, 1, 2, 3]

    def test_a_colour_keeps_what_answers_for_it(self, app: QApplication) -> None:
        index = scanned(
            3,
            row0=Signature(colors=[(to_lab(0xFF0000), 1.0)]),
            row1=Signature(colors=[(to_lab(0x0000FF), 1.0)]),
        )

        kept = Narrowing(colors=[QColor("red")], index=index).kept(3)

        assert kept == [0]

    def test_the_best_match_comes_first(self, app: QApplication) -> None:
        index = scanned(
            3,
            row0=Signature(colors=[(to_lab(0xFF0000), 0.3)]),
            row1=Signature(colors=[(to_lab(0xFF0000), 1.0)]),
        )

        kept = Narrowing(colors=[QColor("red")], index=index).kept(3)

        assert kept is not None
        assert kept[0] == 1

    def test_a_colour_nothing_holds_keeps_nothing(self, app: QApplication) -> None:
        index = scanned(2, row0=Signature(colors=[(to_lab(0x0000FF), 1.0)]))

        assert Narrowing(colors=[QColor("red")], index=index).kept(2) == []

    def test_a_flat_texture_is_hidden_even_when_it_answers_for_the_colour(self, app: QApplication) -> None:
        index = ColorIndex(2)
        index.add(0, Signature(colors=[(to_lab(0xFF0000), 1.0)], flat=True))
        index.add(1, Signature(colors=[(to_lab(0xFF0000), 1.0)]))

        kept = Narrowing(colors=[QColor("red")], simple_hidden=True, index=index).kept(2)

        assert kept == [1]

    def test_asking_for_two_colours_keeps_what_holds_both(self, app: QApplication) -> None:
        index = ColorIndex(2)
        index.add(0, Signature(colors=[(to_lab(0xFF0000), 1.0)]))
        index.add(1, Signature(colors=[(to_lab(0xFF0000), 0.5), (to_lab(0x0000FF), 0.5)]))

        kept = Narrowing(colors=[QColor("red"), QColor("blue")], index=index).kept(2)

        assert kept == [1]
